#include "DropTargetFrame.h"

#include <QDragEnterEvent>
#include <QDropEvent>
#include <QList>
#include <QMimeData>
#include <QUrl>

namespace spellvision::widgets
{

DropTargetFrame::DropTargetFrame(QWidget *parent)
    : QFrame(parent)
{
    setAcceptDrops(true);
}

void DropTargetFrame::dragEnterEvent(QDragEnterEvent *event)
{
    if (!event)
        return;

    const QMimeData *mimeData = event->mimeData();
    if (!mimeData || !mimeData->hasUrls())
    {
        event->ignore();
        return;
    }

    const QList<QUrl> urls = mimeData->urls();
    if (urls.isEmpty() || !urls.first().isLocalFile())
    {
        event->ignore();
        return;
    }

    event->acceptProposedAction();
}

void DropTargetFrame::dropEvent(QDropEvent *event)
{
    if (!event)
        return;

    const QMimeData *mimeData = event->mimeData();
    if (!mimeData || !mimeData->hasUrls())
    {
        event->ignore();
        return;
    }

    const QList<QUrl> urls = mimeData->urls();
    if (urls.isEmpty() || !urls.first().isLocalFile())
    {
        event->ignore();
        return;
    }

    const QString localPath = urls.first().toLocalFile();
    if (onFileDropped)
        onFileDropped(localPath);

    event->acceptProposedAction();
}

} // namespace spellvision::widgets
