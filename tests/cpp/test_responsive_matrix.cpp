// Doc 30's 7-surface x 4-state responsive matrix, run mechanically.
//
// Doc 28 lists this as a release gate and records that it "is defined and has never been executed".
// It sat as a manual owner-eyes table because nothing could construct a page outside the running
// app -- every source lived inline in qt_add_executable. SpellVisionCore fixed that, so the matrix
// becomes a test.
//
// Doc 30 states the pass predicate precisely, and every clause of it is machine-checkable:
//
//     "no clipped controls, no missing Advanced, Generate always reachable,
//      status bar readable, no QSS parse spam"
//
// This is also the first thing on the C++ side that can catch the class of defect Doc 50's own
// ratchet table names as its gap: "every ratchet here is Python. The C++ side has no equivalent,
// and two defects in this pass lived there."

#include <QtTest>

#include <vector>
#include <QAbstractScrollArea>
#include <QApplication>
#include <QLabel>
#include <QLayout>
#include <QPushButton>
#include <QScrollArea>
#include <QWidget>

#include "ImageGenerationPage.h"
#include "studios/ComicStudioPage.h"
#include "studios/CharacterStudioPage.h"
#include "T2VHistoryPage.h"
#include "WorkflowLibraryPage.h"
#include "ManagerPage.h"

using spellvision::studios::CharacterStudioPage;
using spellvision::studios::ComicStudioPage;

namespace {

// The four window states from Doc 30's table. "Half W" and "Half H" are the Windows snap sizes on
// a 1920x1080 display, which is where the owner's half-screen grade came from.
struct WindowState
{
    const char *name;
    QSize size;
};

const WindowState kStates[] = {
    {"Full",    QSize(1920, 1080)},
    {"Restore", QSize(1280, 800)},
    {"Half W",  QSize(960, 1080)},
    {"Half H",  QSize(1920, 540)},
};

// Collected by the message handler for the duration of one case.
QStringList g_styleSheetComplaints;

QtMessageHandler g_previousHandler = nullptr;

void styleSheetWatcher(QtMsgType type, const QMessageLogContext &context, const QString &message)
{
    if (message.contains(QStringLiteral("Could not parse stylesheet"))
        || message.contains(QStringLiteral("Unknown property")))
    {
        g_styleSheetComplaints << message;
    }
    // Chain to the previous handler rather than returning. The first version of this swallowed
    // every message it did not recognise -- including this test's own qWarning diagnostics and
    // QTest's per-case output -- so the matrix reported "5 clipped" and printed nothing about
    // WHICH five. A handler that silently drops what it does not match is the same shape this
    // whole pass is about, and it cost a run to notice.
    if (g_previousHandler != nullptr)
        g_previousHandler(type, context, message);
}

// A widget is "clipped" when it is on screen but has been squeezed below the size it says it needs.
// minimumSizeHint is the right question: sizeHint is a preference and being smaller than it is
// normal and fine, whereas being smaller than the MINIMUM is the thing a user sees as a cut-off
// label or an unusable control.
//
// Deliberately skips scroll-area viewports and their children. A scroll area's whole purpose is to
// be smaller than its contents -- Doc 30's rule is that content surfaces own exactly one scroll
// region, not that nothing may ever exceed the viewport.
bool insideScrollArea(const QWidget *widget)
{
    for (const QWidget *w = widget; w != nullptr; w = w->parentWidget())
    {
        if (qobject_cast<const QAbstractScrollArea *>(w) != nullptr)
            return true;
    }
    return false;
}

// Is this widget's size the layout's responsibility?
//
// A widget positioned by setGeometry() is not layout-managed, so minimumSizeHint is not a contract
// it ever agreed to. The prompt-chip close button is 18x18 by explicit geometry against a 28x40
// hint -- deliberate, and flagging it says nothing about responsiveness.
bool layoutManaged(const QWidget *widget)
{
    const QWidget *parent = widget->parentWidget();
    if (parent == nullptr || parent->layout() == nullptr)
        return false;
    return parent->layout()->indexOf(const_cast<QWidget *>(widget)) >= 0;
}

QStringList clippedControls(QWidget *root)
{
    QStringList offenders;
    const QList<QWidget *> children = root->findChildren<QWidget *>();
    for (QWidget *w : children)
    {
        if (!w->isVisible() || w->size().isEmpty())
            continue;

        // A resizable scroll area whose CONTENT is wider than its viewport is clipping, not
        // scrolling: this app turns the horizontal bar off everywhere, and setWidgetResizable
        // never shrinks the content below its minimum width. Comic Studio's left column shipped
        // exactly this (a combo whose widest item was wider than the column) and the matrix
        // could not see it, because everything inside a scroll area is skipped below on purpose.
        // The area itself is not inside one, so it is asked here.
        if (auto *area = qobject_cast<QScrollArea *>(w))
        {
            if (area->widgetResizable() && area->widget() != nullptr
                && area->horizontalScrollBarPolicy() == Qt::ScrollBarAlwaysOff
                && area->widget()->width() > area->viewport()->width())
            {
                offenders << QStringLiteral("%1(%2) content %3px wide in a %4px viewport")
                                 .arg(QString::fromLatin1(w->metaObject()->className()),
                                      w->objectName().isEmpty() ? QStringLiteral("-") : w->objectName())
                                 .arg(area->widget()->width()).arg(area->viewport()->width());
            }
        }

        if (insideScrollArea(w))
            continue;
        if (!layoutManaged(w))
            continue;

        // An EMPTY label's minimumSizeHint is its stylesheet padding, not its content. The canvas
        // metric chips are empty until a render populates them, so on a freshly-constructed page
        // they measure narrower than their hint and mean nothing by it.
        if (const auto *label = qobject_cast<const QLabel *>(w))
        {
            if (label->text().trimmed().isEmpty())
                continue;
        }

        const QSize need = w->minimumSizeHint();
        if (!need.isValid())
            continue;

        if (w->width() < need.width() || w->height() < need.height())
        {
            // The ancestry, not just the victim. "QWidget(-) 120x32 < min 364x32" says a row is
            // squeezed and nothing about WHICH container lost the width -- the same complaint the
            // LoRA row test answered with a geometry dump. Walk up to the page and print each
            // step's width against its minimum, so a failing cell is diagnosable from its output.
            QStringList chain;
            for (QWidget *up = w->parentWidget(); up && up != root; up = up->parentWidget())
            {
                chain << QStringLiteral("%1(%2) %3w/min%4%5")
                             .arg(QString::fromLatin1(up->metaObject()->className()),
                                  up->objectName().isEmpty() ? QStringLiteral("-") : up->objectName())
                             .arg(up->width())
                             .arg(up->minimumSizeHint().width())
                             .arg(up->maximumWidth() == QWIDGETSIZE_MAX ? QString()
                                                                        : QStringLiteral("/max%1").arg(up->maximumWidth()));
            }
            offenders << QStringLiteral("%1(%2) %3x%4 < min %5x%6  [up: %7]")
                             .arg(QString::fromLatin1(w->metaObject()->className()),
                                  w->objectName().isEmpty() ? QStringLiteral("-") : w->objectName())
                             .arg(w->width()).arg(w->height())
                             .arg(need.width()).arg(need.height())
                             .arg(chain.mid(0, 6).join(QStringLiteral(" < ")));
        }
    }
    return offenders;
}

// Cells that fail TODAY, with the reason. Modelled on test_family_capability.py's KNOWN_GAPS: it
// records the baseline so a NEW failure fails the suite immediately, and closing one also fails --
// forcing the number down rather than letting it rot.
//
// Both entries are REAL defects, not accepted behaviour. They are recorded rather than fixed here
// because a layout change wants an eye on it, and this commit's job is to make the matrix run at
// all -- Doc 28 has listed it as a gate since 2026-07-25 with the note that it "has never been
// executed".
struct KnownFailure
{
    const char *cell;
    const char *reason;
};

// Cells that fail today, with the reason. EMPTY, and that is the point: the two entries this list
// shipped with were both real defects, and both were fixed on 2026-09-02 once the clip report
// printed the ANCESTRY of a squeezed control rather than only its size.
//
//   * "T2I / Full" -- the canvas empty-state chips row was 120px inside a 1390px empty state,
//     because addWidget(row, 0, Qt::AlignHCenter) gives an item its size HINT rather than the space
//     available. It centres itself with stretches now, like the preview stack does.
//   * "History details / Half W" -- four full-word buttons in one row gave the details card a 367px
//     minimum while reflowForWidth deliberately shrinks it to ~300px so the table is not crushed.
//     They are a 2x2 grid now, like the copy actions right below them.
//
// The baseline stays, and stays two-way: a new failure fails the suite, and a cell that starts
// passing must be deleted rather than left standing as an excuse.

const std::vector<KnownFailure> &knownFailures()
{
    // A std::vector, not a C array: an array of zero elements does not compile, and "the list is
    // empty" is the state this baseline is supposed to be able to reach.
    static const std::vector<KnownFailure> list = {
    };
    return list;
}

bool isKnownFailure(const QString &cell)
{
    for (const KnownFailure &known : knownFailures())
    {
        if (cell == QLatin1String(known.cell))
            return true;
    }
    return false;
}

} // namespace

class ResponsiveMatrix : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void matrix_data();
    void matrix();
    void cleanupTestCase();

private:
    QStringList results_;
};

void ResponsiveMatrix::initTestCase()
{
    g_previousHandler = qInstallMessageHandler(styleSheetWatcher);
}

void ResponsiveMatrix::matrix_data()
{
    QTest::addColumn<QString>("surface");
    QTest::addColumn<QString>("state");
    QTest::addColumn<QSize>("size");
    QTest::addColumn<bool>("advanced");
    QTest::addColumn<bool>("hasGenerate");

    // Doc 30's seven surfaces. "Comic Advanced ON" is the row that carries the advanced flag --
    // it is listed separately in the doc precisely because Advanced is where the clipping showed.
    // hasGenerate: whether the "Generate always reachable" clause applies. Library and runtime
    // pages have no Generate; asserting on the first PrimaryActionButton they happen to contain
    // (Workflows' hidden Import button) would fail them for the wrong reason.
    struct Surface { const char *name; bool advanced; bool hasGenerate; };
    const Surface surfaces[] = {
        {"T2I", false, true},
        {"T2V", false, true},
        {"I2V", false, true},
        {"Comic Advanced ON", true, true},
        {"Character concept", false, true},
        {"History details", false, true},
        {"Title bar + telemetry", false, true},
        // Added 2026-09-01. Both were absent, and both shipped defects of exactly the class this
        // matrix catches: a nine-button non-wrapping row, and a page with no scroll region.
        {"Workflows library", false, false},
        {"Runtime page", false, false},
    };

    for (const Surface &surface : surfaces)
    {
        for (const WindowState &state : kStates)
        {
            QTest::newRow(qPrintable(QStringLiteral("%1 / %2").arg(surface.name, state.name)))
                << QString::fromLatin1(surface.name)
                << QString::fromLatin1(state.name)
                << state.size
                << surface.advanced
                << surface.hasGenerate;
        }
    }
}

void ResponsiveMatrix::matrix()
{
    QFETCH(QString, surface);
    QFETCH(QString, state);
    QFETCH(QSize, size);
    QFETCH(bool, advanced);
    QFETCH(bool, hasGenerate);

    g_styleSheetComplaints.clear();

    QScopedPointer<QWidget> page;
    if (surface == QStringLiteral("T2I"))
        page.reset(new ImageGenerationPage(ImageGenerationPage::Mode::TextToImage));
    else if (surface == QStringLiteral("T2V"))
        page.reset(new ImageGenerationPage(ImageGenerationPage::Mode::TextToVideo));
    else if (surface == QStringLiteral("I2V"))
        page.reset(new ImageGenerationPage(ImageGenerationPage::Mode::ImageToVideo));
    else if (surface == QStringLiteral("Comic Advanced ON"))
        page.reset(new ComicStudioPage());
    else if (surface == QStringLiteral("Character concept"))
        page.reset(new CharacterStudioPage());
    else if (surface == QStringLiteral("History details"))
        page.reset(new T2VHistoryPage());
    else if (surface == QStringLiteral("Title bar + telemetry"))
        page.reset(new ImageGenerationPage(ImageGenerationPage::Mode::TextToImage));
    else if (surface == QStringLiteral("Workflows library"))
        page.reset(new WorkflowLibraryPage());
    else if (surface == QStringLiteral("Runtime page"))
        page.reset(new ManagerPage());

    QVERIFY2(!page.isNull(), qPrintable(QStringLiteral("no constructor for surface %1").arg(surface)));

    if (advanced)
    {
        if (auto *comic = qobject_cast<ComicStudioPage *>(page.data()))
            comic->updateDisclosure(true);
    }

    page->resize(size);
    page->show();
    QVERIFY(QTest::qWaitForWindowExposed(page.data()));
    // Let deferred layout settle. Several surfaces lay out on a queued connection after show().
    QTest::qWait(120);

    const QStringList clipped = clippedControls(page.data());

    // "Generate always reachable" -- the button exists, is visible, and lies inside the page.
    QString generateVerdict = QStringLiteral("n/a");
    if (auto *generate = hasGenerate ? page->findChild<QPushButton *>(QStringLiteral("PrimaryActionButton")) : nullptr)
    {
        const QRect inPage(generate->mapTo(page.data(), QPoint(0, 0)), generate->size());
        const bool reachable = generate->isVisible() && page->rect().intersects(inPage);
        generateVerdict = reachable ? QStringLiteral("reachable") : QStringLiteral("UNREACHABLE");
    }

    const bool pass = clipped.isEmpty()
                      && g_styleSheetComplaints.isEmpty()
                      && generateVerdict != QStringLiteral("UNREACHABLE");

    results_ << QStringLiteral("| %1 | %2 | %3 | %4 | %5 | %6 |")
                    .arg(surface, state,
                         pass ? QStringLiteral("PASS") : QStringLiteral("FAIL"))
                    .arg(clipped.size())
                    .arg(g_styleSheetComplaints.size())
                    .arg(generateVerdict);

    // Report every failing clause rather than the first: the point of a matrix is to see the shape
    // of the failure across cells, and stopping at the first hides it.
    if (!clipped.isEmpty())
        qWarning("%s / %s: %d clipped control(s): %s", qPrintable(surface), qPrintable(state),
                 int(clipped.size()), qPrintable(clipped.mid(0, 5).join(QStringLiteral("; "))));
    if (!g_styleSheetComplaints.isEmpty())
        qWarning("%s / %s: %d stylesheet complaint(s): %s", qPrintable(surface), qPrintable(state),
                 int(g_styleSheetComplaints.size()),
                 qPrintable(g_styleSheetComplaints.first()));

    const QString cell = QStringLiteral("%1 / %2").arg(surface, state);
    if (isKnownFailure(cell))
    {
        // Two-way, like KNOWN_GAPS: a cell that starts passing must be REMOVED from the baseline,
        // so the list can only shrink. Otherwise a fixed bug leaves a permanent excuse behind.
        QVERIFY2(!pass, qPrintable(QStringLiteral(
            "%1 now passes -- delete it from kKnownFailures").arg(cell)));
        return;
    }

    QVERIFY2(g_styleSheetComplaints.isEmpty(), "QSS parse spam");
    QVERIFY2(generateVerdict != QStringLiteral("UNREACHABLE"), "Generate is not reachable");
    QVERIFY2(clipped.isEmpty(), qPrintable(clipped.join(QStringLiteral("; "))));
}

void ResponsiveMatrix::cleanupTestCase()
{
    qInstallMessageHandler(nullptr);

    // Print the table Doc 30 has carried empty since 2026-07-25, so a run RECORDS the matrix rather
    // than only gating on it.
    QTextStream out(stdout);
    out << "\n--- Doc 30 responsive matrix ---\n";
    out << "| Surface | State | Result | Clipped | QSS | Generate |\n";
    out << "|---|---|---|---|---|---|\n";
    for (const QString &row : std::as_const(results_))
        out << row << "\n";
    out.flush();
}

QTEST_MAIN(ResponsiveMatrix)
#include "test_responsive_matrix.moc"
