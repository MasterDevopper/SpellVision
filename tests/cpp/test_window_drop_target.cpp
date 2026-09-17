// A workflow dropped anywhere in the window is a workflow the window handles.
//
// Before this, MainWindow had no dragEnterEvent, no dropEvent and no setAcceptDrops -- verified by a
// repo-wide grep -- so Qt's own walk (QWidgetWindow::findDnDTarget: from the widget under the cursor
// UP to the first ancestor whose acceptDrops() is true) found nobody for a .json dropped on the rail,
// the title bar, Flows, Home, History, Settings, a studio or the dataset page, and the file was
// dropped on the floor with no message. Nothing in the app ever knew it happened.
//
// These cases drive the REAL delivery path, not a convenient one. The platform hands a drag to the
// QWindow (QGuiApplicationPrivate::processDrag -> sendEvent(window, ...)), and QWidgetWindow is what
// then hunts for a widget that will take it. So the events here go to `window.windowHandle()` and the
// widget tree has real geometry, which is what makes both halves observable:
//
//   * the window-level filter runs BEFORE QWidgetWindow ever looks for a target, so a workflow is
//     claimed wherever it lands;
//   * an IMAGE is not claimed, so QWidgetWindow still finds the cockpit and the cockpit still gets
//     it -- drop-to-reference is a feature the owner uses, and a filter that swallowed every URL
//     would have deleted it to add workflow routing.
//
// The first version of this file sent the events straight to the WIDGET with QCoreApplication::
// sendEvent, and every delivery case failed with the filter never running once: QApplication::notify
// does not route drag events to a widget that way, and neither does the platform. A test written to
// the shape of the API rather than to the shape of the real path would have gone green only after
// the production code had been bent to match it.

#include <QtTest>

#include <QDragEnterEvent>
#include <QDropEvent>
#include <QMimeData>
#include <QPointF>
#include <QSignalSpy>
#include <QTextEdit>
#include <QUrl>
#include <QWidget>
#include <QWindow>

#include "shell/WindowDropTarget.h"

using spellvision::shell::WindowDropTarget;

namespace
{

// A stand-in for any page that handles its own drops -- the cockpit, whose acceptDrops() is true and
// whose dropEvent routes stills to the input image. It counts what reaches it, which is the only way
// to tell "the filter let it through" from "the filter ate it quietly".
class DropCountingWidget final : public QWidget
{
public:
    explicit DropCountingWidget(QWidget *parent = nullptr)
        : QWidget(parent)
    {
        setAcceptDrops(true);
    }

    int drops = 0;

protected:
    void dragEnterEvent(QDragEnterEvent *event) override { event->acceptProposedAction(); }
    void dropEvent(QDropEvent *event) override
    {
        ++drops;
        event->acceptProposedAction();
    }
};

// One drag, start to finish, at a point inside the window: enter then drop, exactly as the platform
// sequences it (QWidgetWindow will not deliver a drop it never saw an enter for).
void dragAndDrop(QWidget &window, const QPoint &pos, const QString &path)
{
    QMimeData mime;
    mime.setUrls({QUrl::fromLocalFile(path)});
    QWindow *handle = window.windowHandle();
    if (!handle)
        return;

    QDragEnterEvent enter(pos, Qt::CopyAction, &mime, Qt::LeftButton, Qt::NoModifier);
    QCoreApplication::sendEvent(handle, &enter);
    QDropEvent drop(QPointF(pos), Qt::CopyAction, &mime, Qt::LeftButton, Qt::NoModifier);
    QCoreApplication::sendEvent(handle, &drop);
}

// The shell, in miniature: a title bar across the top, a rail down the left, a page with no drop
// handling, a cockpit that has its own, and a prompt editor inside the cockpit with
// acceptDrops(false). Same shape, same three behaviours.
class ShellFixture
{
public:
    ShellFixture()
    {
        window.setGeometry(100, 100, 420, 420);
        titleBar = new QWidget(&window);
        titleBar->setGeometry(0, 0, 420, 40);
        rail = new QWidget(&window);
        rail->setGeometry(0, 40, 60, 380);
        plainPage = new QWidget(&window); // Flows / Home / History / Settings: no drop handling
        plainPage->setGeometry(60, 40, 360, 180);
        cockpit = new DropCountingWidget(&window);
        cockpit->setGeometry(60, 220, 360, 200);
        promptEdit = new QTextEdit(cockpit);
        promptEdit->setObjectName(QStringLiteral("PromptEditor"));
        promptEdit->setGeometry(10, 10, 200, 60);
        // ImageGenerationPage.cpp:718 / :745 and the studios: a dropped file must not become text.
        promptEdit->setAcceptDrops(false);
        promptEdit->setPlainText(QStringLiteral("a lantern-lit alley"));
        window.show();
        window.winId();
    }

    QPoint titleBarPoint() const { return QPoint(200, 20); }
    QPoint railPoint() const { return QPoint(30, 200); }
    QPoint plainPagePoint() const { return QPoint(240, 120); }
    QPoint cockpitPoint() const { return QPoint(300, 380); }
    QPoint promptPoint() const { return cockpit->pos() + promptEdit->pos() + QPoint(20, 20); }

    QWidget window;
    QWidget *titleBar = nullptr;
    QWidget *rail = nullptr;
    QWidget *plainPage = nullptr;
    DropCountingWidget *cockpit = nullptr;
    QTextEdit *promptEdit = nullptr;
};

} // namespace

class WindowDropTargetTest : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();

    void aJsonIsAWorkflowAnImageIsAnImageEverythingElseIsIgnored();
    void withoutTheFilterAWorkflowOnTheRailIsDiscarded();
    void aWorkflowDroppedOnTheTitleBarReachesTheWindow();
    void aWorkflowDroppedOnTheRailReachesTheWindow();
    void aWorkflowDroppedOnAPageWithNoDropHandlingReachesTheWindow();
    void anImageDroppedOnTheCockpitIsStillHandledByTheCockpit();
    void aWorkflowDroppedOnAPromptEditorReachesTheWindowNotTheEditor();
    void aDragCarryingSomethingUnhandledIsLeftAlone();

private:
    QString workflowPath_;
    QString imagePath_;
    QString otherPath_;
};

void WindowDropTargetTest::initTestCase()
{
    workflowPath_ = QStringLiteral("C:/tmp/krea2-compact-t2i-v10.json");
    imagePath_ = QStringLiteral("C:/tmp/keyframe.png");
    otherPath_ = QStringLiteral("C:/tmp/notes.txt");
}

// --- 1: the classification, with no widgets at all -----------------------------------------------

void WindowDropTargetTest::aJsonIsAWorkflowAnImageIsAnImageEverythingElseIsIgnored()
{
    QMimeData workflow;
    workflow.setUrls({QUrl::fromLocalFile(workflowPath_)});
    QMimeData image;
    image.setUrls({QUrl::fromLocalFile(imagePath_)});
    QMimeData other;
    other.setUrls({QUrl::fromLocalFile(otherPath_)});

    QCOMPARE(WindowDropTarget::classifyDrop(&workflow), WindowDropTarget::DropKind::Workflow);
    QCOMPARE(WindowDropTarget::classifyDrop(&image), WindowDropTarget::DropKind::Image);
    QCOMPARE(WindowDropTarget::classifyDrop(&other), WindowDropTarget::DropKind::Ignored);
    QCOMPARE(WindowDropTarget::classifyDrop(nullptr), WindowDropTarget::DropKind::Ignored);

    // A drag with no URL at all -- text out of a browser, say -- is not a file and must not be
    // treated as one.
    QMimeData textOnly;
    textOnly.setText(QStringLiteral("https://example.com/workflow.json"));
    QCOMPARE(WindowDropTarget::classifyDrop(&textOnly), WindowDropTarget::DropKind::Ignored);

    // Case, and the .api.json spelling the importer also accepts.
    QVERIFY(WindowDropTarget::isWorkflowFile(QStringLiteral("D:/x/Graph.API.JSON")));
    QVERIFY(WindowDropTarget::isImageFile(QStringLiteral("D:/x/Frame.JPEG")));
}

// --- 2: the defect, stated as a test -------------------------------------------------------------

void WindowDropTargetTest::withoutTheFilterAWorkflowOnTheRailIsDiscarded()
{
    // With nothing installed this is exactly what the app did: the drag reaches the window, Qt finds
    // no widget in the chain that accepts drops, and the file is gone. Asserting the OLD behaviour
    // is what makes the next five cases mean something -- otherwise they could all be passing
    // because Qt would have delivered the drop anyway.
    ShellFixture shell;
    dragAndDrop(shell.window, shell.railPoint(), workflowPath_);
    QCOMPARE(shell.cockpit->drops, 0);
}

// --- 3: the title bar ----------------------------------------------------------------------------

void WindowDropTargetTest::aWorkflowDroppedOnTheTitleBarReachesTheWindow()
{
    ShellFixture shell;
    WindowDropTarget target;
    target.installOn(qApp);
    QSignalSpy spy(&target, &WindowDropTarget::workflowDropped);

    dragAndDrop(shell.window, shell.titleBarPoint(), workflowPath_);

    QCOMPARE(spy.count(), 1);
    QCOMPARE(spy.at(0).at(0).toString(), workflowPath_);
    qApp->removeEventFilter(&target);
}

// --- 4: the rail ---------------------------------------------------------------------------------

void WindowDropTargetTest::aWorkflowDroppedOnTheRailReachesTheWindow()
{
    ShellFixture shell;
    WindowDropTarget target;
    target.installOn(qApp);
    QSignalSpy spy(&target, &WindowDropTarget::workflowDropped);

    dragAndDrop(shell.window, shell.railPoint(), workflowPath_);

    QCOMPARE(spy.count(), 1);
    qApp->removeEventFilter(&target);
}

// --- 5: a page that has never handled a drop -----------------------------------------------------

void WindowDropTargetTest::aWorkflowDroppedOnAPageWithNoDropHandlingReachesTheWindow()
{
    ShellFixture shell;
    QVERIFY(!shell.plainPage->acceptDrops()); // Flows, Home, History, Settings are all this shape

    WindowDropTarget target;
    target.installOn(qApp);
    QSignalSpy spy(&target, &WindowDropTarget::workflowDropped);

    dragAndDrop(shell.window, shell.plainPagePoint(), workflowPath_);

    QCOMPARE(spy.count(), 1);
    qApp->removeEventFilter(&target);
}

// --- 6: the image the cockpit must keep ----------------------------------------------------------

void WindowDropTargetTest::anImageDroppedOnTheCockpitIsStillHandledByTheCockpit()
{
    ShellFixture shell;
    WindowDropTarget target;
    target.installOn(qApp);
    QSignalSpy spy(&target, &WindowDropTarget::workflowDropped);

    dragAndDrop(shell.window, shell.cockpitPoint(), imagePath_);

    // The window did NOT claim it, and the page did handle it. Both halves matter.
    QCOMPARE(spy.count(), 0);
    QCOMPARE(shell.cockpit->drops, 1);

    // ...and the same page's workflow drop goes to the window instead of to the page's own router,
    // because the answer to "which page does this graph belong on" is not "the one you were looking
    // at" -- which is the whole of task 3.
    dragAndDrop(shell.window, shell.cockpitPoint(), workflowPath_);
    QCOMPARE(spy.count(), 1);
    QCOMPARE(shell.cockpit->drops, 1);

    qApp->removeEventFilter(&target);
}

// --- 7: the prompt editor ------------------------------------------------------------------------

void WindowDropTargetTest::aWorkflowDroppedOnAPromptEditorReachesTheWindowNotTheEditor()
{
    // The editors carry setAcceptDrops(false) so a dropped file cannot become pasted text. Assert
    // BOTH halves: the window gets the path, and the editor's text is untouched.
    ShellFixture shell;
    WindowDropTarget target;
    target.installOn(qApp);
    QSignalSpy spy(&target, &WindowDropTarget::workflowDropped);

    dragAndDrop(shell.window, shell.promptPoint(), workflowPath_);

    QCOMPARE(spy.count(), 1);
    QCOMPARE(spy.at(0).at(0).toString(), workflowPath_);
    QCOMPARE(shell.promptEdit->toPlainText(), QStringLiteral("a lantern-lit alley"));
    QVERIFY(!shell.promptEdit->toPlainText().contains(QStringLiteral(".json")));
    // And it did not fall through to the cockpit's own image router either.
    QCOMPARE(shell.cockpit->drops, 0);

    qApp->removeEventFilter(&target);
}

// --- 8: silence for a file the app has no use for ------------------------------------------------

void WindowDropTargetTest::aDragCarryingSomethingUnhandledIsLeftAlone()
{
    ShellFixture shell;
    WindowDropTarget target;
    target.installOn(qApp);
    QSignalSpy spy(&target, &WindowDropTarget::workflowDropped);

    QMimeData mime;
    mime.setUrls({QUrl::fromLocalFile(otherPath_)});
    QDragEnterEvent enter(shell.railPoint(), Qt::CopyAction, &mime, Qt::LeftButton, Qt::NoModifier);
    QCoreApplication::sendEvent(shell.window.windowHandle(), &enter);

    // Not claimed and not accepted: an overlay that appears and then refuses is worse than silence.
    QVERIFY(!enter.isAccepted());
    QCOMPARE(spy.count(), 0);

    qApp->removeEventFilter(&target);
}

QTEST_MAIN(WindowDropTargetTest)
#include "test_window_drop_target.moc"
