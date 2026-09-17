#include "WindowDropTarget.h"

#include "../ThemeManager.h"

#include <QDragEnterEvent>
#include <QDragLeaveEvent>
#include <QDragMoveEvent>
#include <QDropEvent>
#include <QEvent>
#include <QFileInfo>
#include <QLabel>
#include <QMimeData>
#include <QUrl>
#include <QVBoxLayout>
#include <QWidget>

namespace spellvision::shell
{
namespace
{

// The extensions the cockpit already treats as a still (ImageGenerationPage::setInputImagePath and
// the model thumbnail cache). Listed so "not a workflow" and "an image the page wants" are two
// different answers rather than one negation.
bool hasImageSuffix(const QString &suffix)
{
    return suffix == QStringLiteral("png")
        || suffix == QStringLiteral("jpg")
        || suffix == QStringLiteral("jpeg")
        || suffix == QStringLiteral("webp")
        || suffix == QStringLiteral("bmp")
        || suffix == QStringLiteral("tif")
        || suffix == QStringLiteral("tiff")
        || suffix == QStringLiteral("gif");
}

} // namespace

WindowDropTarget::WindowDropTarget(QObject *parent)
    : QObject(parent)
{
}

bool WindowDropTarget::isWorkflowFile(const QString &path)
{
    const QString trimmed = path.trimmed();
    if (trimmed.isEmpty())
        return false;
    // .api.json is a plain .json as far as the suffix goes; both are workflows and both import
    // through the same command.
    return trimmed.endsWith(QStringLiteral(".json"), Qt::CaseInsensitive);
}

bool WindowDropTarget::isImageFile(const QString &path)
{
    return hasImageSuffix(QFileInfo(path.trimmed()).suffix().trimmed().toLower());
}

QString WindowDropTarget::droppedLocalFile(const QMimeData *mime)
{
    if (!mime || !mime->hasUrls())
        return {};
    const QList<QUrl> urls = mime->urls();
    if (urls.isEmpty())
        return {};
    const QUrl first = urls.first();
    if (!first.isLocalFile())
        return {};
    return first.toLocalFile();
}

WindowDropTarget::DropKind WindowDropTarget::classifyDrop(const QMimeData *mime)
{
    const QString path = droppedLocalFile(mime);
    if (path.trimmed().isEmpty())
        return DropKind::Ignored;
    if (isWorkflowFile(path))
        return DropKind::Workflow;
    if (isImageFile(path))
        return DropKind::Image;
    return DropKind::Ignored;
}

void WindowDropTarget::installOn(QObject *filterHost)
{
    if (filterHost)
        filterHost->installEventFilter(this);
}

void WindowDropTarget::setOverlayHost(QWidget *host)
{
    if (overlayHost_ == host)
        return;
    hideOverlay();
    if (overlay_)
    {
        overlay_->deleteLater();
        overlay_ = nullptr;
        overlayLabel_ = nullptr;
    }
    overlayHost_ = host;
}

bool WindowDropTarget::eventFilter(QObject *watched, QEvent *event)
{
    Q_UNUSED(watched);
    if (!event)
        return false;

    switch (event->type())
    {
    case QEvent::DragEnter:
    case QEvent::DragMove:
    {
        auto *drag = static_cast<QDragMoveEvent *>(event);
        if (classifyDrop(drag->mimeData()) != DropKind::Workflow)
            return false; // images and everything else keep whatever behaviour the page already has
        drag->setDropAction(Qt::CopyAction);
        drag->accept();
        showOverlay(QFileInfo(droppedLocalFile(drag->mimeData())).fileName());
        return true;
    }
    case QEvent::DragLeave:
        hideOverlay();
        return false;
    case QEvent::Drop:
    {
        auto *drop = static_cast<QDropEvent *>(event);
        if (classifyDrop(drop->mimeData()) != DropKind::Workflow)
            return false;
        hideOverlay();
        const QString path = droppedLocalFile(drop->mimeData());
        drop->setDropAction(Qt::CopyAction);
        drop->accept();
        if (!path.trimmed().isEmpty())
            emit workflowDropped(path);
        return true;
    }
    default:
        break;
    }

    return false;
}

void WindowDropTarget::showOverlay(const QString &fileName)
{
    if (!overlayHost_)
        return;

    if (!overlay_)
    {
        auto *frame = new QWidget(overlayHost_);
        frame->setObjectName(QStringLiteral("WindowDropOverlay"));
        frame->setAttribute(Qt::WA_TransparentForMouseEvents, true);
        auto *layout = new QVBoxLayout(frame);
        const int pad = ThemeManager::instance().spacing(ThemeManager::Spacing::Card);
        layout->setContentsMargins(pad, pad, pad, pad);
        layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
        auto *label = new QLabel(frame);
        label->setObjectName(QStringLiteral("WindowDropOverlayLabel"));
        label->setAlignment(Qt::AlignCenter);
        label->setWordWrap(true);
        layout->addWidget(label);
        overlay_ = frame;
        overlayLabel_ = label;
    }

    ThemeManager &theme = ThemeManager::instance();
    overlay_->setStyleSheet(QStringLiteral(
                                "QWidget#WindowDropOverlay{background:%1;border:1px solid %2;border-radius:%3px;}")
                                .arg(theme.css(ThemeManager::Color::GlassFill),
                                     theme.css(ThemeManager::Color::Accent))
                                .arg(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug)));
    if (overlayLabel_)
    {
        overlayLabel_->setStyleSheet(QStringLiteral("color:%1;background:transparent;border:0;font-size:13px;")
                                         .arg(theme.css(ThemeManager::Color::TextHi)));
        overlayLabel_->setText(fileName.trimmed().isEmpty()
                                   ? QStringLiteral("Drop to load this workflow")
                                   : QStringLiteral("Drop to load %1 — SpellVision opens it on the page its graph belongs to.")
                                         .arg(fileName.trimmed()));
    }

    const QRect host = overlayHost_->rect();
    const int width = qMin(560, qMax(280, host.width() - 2 * ThemeManager::instance().spacing(ThemeManager::Spacing::Section)));
    const int height = 96;
    overlay_->setGeometry(host.center().x() - width / 2, host.center().y() - height / 2, width, height);
    overlay_->raise();
    overlay_->show();
}

void WindowDropTarget::hideOverlay()
{
    if (overlay_)
        overlay_->hide();
}

} // namespace spellvision::shell
