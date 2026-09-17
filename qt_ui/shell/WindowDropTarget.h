#pragma once

#include <QObject>
#include <QPointer>
#include <QString>

class QEvent;
class QLabel;
class QMimeData;
class QWidget;

namespace spellvision::shell
{

// The window's answer to "somebody dropped a file on me".
//
// Qt delivers a drag only to a widget whose acceptDrops() is true, walking up from the widget under
// the cursor and stopping at the first taker. Where that walk finds nobody the drag is discarded,
// silently and with no feedback at all -- which is what happened to every workflow dropped on the
// rail, the title bar, Flows, Home, History, Settings, the studios and the dataset page, because
// MainWindow had no dragEnterEvent, no dropEvent and no setAcceptDrops. The user saw nothing, which
// reads as the app being broken rather than as the drop being in the wrong place.
//
// This is the ancestor that was missing. Installed on the application, it sees every drag before the
// widget tree does and claims the ones the WINDOW owns.
//
// WHAT IT CLAIMS, and what it deliberately does not:
//
//   Workflow (.json)  -- claimed, everywhere, unconditionally. There is exactly one thing to do with
//                        a dropped workflow (import it, classify it, open it on the page its graph
//                        belongs to) and it does not depend on which pixel the file landed on. The
//                        model-stack card's own drop zone keeps working through Browse/Run.
//
//   Image             -- NEVER claimed. The cockpit already handles image drops per surface (prompt
//                        chip, input-image card, canvas) and those are the affordances the owner uses
//                        to set a reference. A window filter that swallowed them would take a working
//                        feature away to add a new one. Classified all the same, because "this is an
//                        image, leave it to the page" is a decision, not a fall-through.
//
//   Anything else     -- ignored, and no overlay. Silence is right for a file the app has no use for;
//                        an overlay that appears and then refuses is not.
//
// Prompt editors carry setAcceptDrops(false) so a dropped file cannot become pasted text. That fix
// stays: this filter runs BEFORE the editor is even consulted, so a workflow dropped on a prompt box
// is handled by the window rather than by anything downstream.
class WindowDropTarget final : public QObject
{
    Q_OBJECT

public:
    enum class DropKind
    {
        Ignored = 0,
        Workflow,
        Image,
    };
    Q_ENUM(DropKind)

    explicit WindowDropTarget(QObject *parent = nullptr);

    // Pure, and the reason this class is testable without a running drag: given the payload, what is
    // it? No widget, no position, no platform.
    static DropKind classifyDrop(const QMimeData *mime);
    static QString droppedLocalFile(const QMimeData *mime);
    static bool isWorkflowFile(const QString &path);
    static bool isImageFile(const QString &path);

    // Usually qApp: an application-level filter sees the drag delivered to the QWindow, which is the
    // only place it exists when no widget accepted it.
    void installOn(QObject *filterHost);
    // Usually MainWindow: where the "drop to load" overlay is drawn. Optional -- the filter routes
    // files with or without one.
    void setOverlayHost(QWidget *host);

signals:
    void workflowDropped(const QString &path);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;

private:
    void showOverlay(const QString &fileName);
    void hideOverlay();

    QPointer<QWidget> overlayHost_;
    QPointer<QWidget> overlay_;
    QPointer<QLabel> overlayLabel_;
};

} // namespace spellvision::shell
