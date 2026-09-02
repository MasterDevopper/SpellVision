#include "ImagePreviewController.h"
#include "AspectCap.h"

#include "MediaPreviewController.h"

#include <QEvent>
#include <QFileInfo>
#include <QLabel>
#include <QRect>
#include <QWidget>

#include <algorithm>

namespace
{
// Fill the frame, but a small source shouldn't be blown into a blurry wall (the "don't upscale a
// 512px image to 4K" rule). 2x native is the crisp/space-used compromise; downscaling is unbounded.
constexpr double kMaxUpscale = 2.0;
} // namespace

namespace spellvision::preview
{

ImagePreviewController::ImagePreviewController(QObject *parent)
    : QObject(parent)
{
}

void ImagePreviewController::bind(const ImagePreviewBindings &bindings)
{
    bindings_ = bindings;
    // Re-fit on resize, exactly like the video surface does. This is the key fix for the "1/3 of the
    // frame" bug: previewLabel_ is the hidden page of a StackOne QStackedWidget, so at cold-render time
    // its geometry is stale and showPixmap used to cap the scale at 640x480 and cement it. When the
    // label later becomes current and is sized, QStackedLayout sends a Resize -> refit() -> fill.
    if (bindings_.previewLabel)
        bindings_.previewLabel->installEventFilter(this);
    // With a budget widget, its Resize is what changes the fit (window grew or shrank) and refit
    // recomputes the cap from it directly. Without one (older callers), the parent's resize is the
    // one event that may LOOSEN the cap: release it there and let the label's Resize re-apply.
    if (bindings_.sizeBudgetWidget)
        bindings_.sizeBudgetWidget->installEventFilter(this);
    else if (bindings_.sizeCapWidget && bindings_.sizeCapWidget->parentWidget())
        bindings_.sizeCapWidget->parentWidget()->installEventFilter(this);
}

bool ImagePreviewController::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == bindings_.previewLabel && event->type() == QEvent::Resize)
        refit();
    else if (bindings_.sizeBudgetWidget && watched == bindings_.sizeBudgetWidget && event->type() == QEvent::Resize)
        refit();
    else if (!bindings_.sizeBudgetWidget && bindings_.sizeCapWidget && watched == bindings_.sizeCapWidget->parentWidget()
             && event->type() == QEvent::Resize)
        releaseAspectCap(bindings_.sizeCapWidget);
    return QObject::eventFilter(watched, event);
}

QSize ImagePreviewController::computeFittedSize(const QSize &sourceSize, const QSize &target) const
{
    if (sourceSize.isEmpty() || target.isEmpty())
        return {};
    const double fitScale = std::min(static_cast<double>(target.width()) / sourceSize.width(),
                                     static_cast<double>(target.height()) / sourceSize.height());
    const double scale = std::min(fitScale, kMaxUpscale); // fill, but cap upscaling
    return QSize(std::max(1, qRound(sourceSize.width() * scale)),
                 std::max(1, qRound(sourceSize.height() * scale)));
}

void ImagePreviewController::refit()
{
    if (!bindings_.previewLabel || displayedFullPixmap_.isNull())
        return;

    // Fit against the BUDGET, never the label: the label is the widget the cap constrains, so
    // measuring it feeds the cap its own last answer and a cold 48x86 label stays 48x86 forever.
    const QSize target = (bindings_.sizeBudgetWidget && bindings_.sizeCapWidget)
        ? fitBudget(bindings_.sizeBudgetWidget, bindings_.sizeCapWidget, bindings_.previewLabel)
        : bindings_.previewLabel->contentsRect().size();
    if (target.width() < 16 || target.height() < 16)
        return; // not laid out yet; the resize eventFilter will call refit() once it is

    const QSize fitted = computeFittedSize(displayedFullPixmap_.size(), target);
    // Hug the picture. Only while this label is the visible page: a cap computed for an image
    // must not be applied while the stack is showing the video surface.
    if (bindings_.previewLabel->isVisible())
        applyAspectCap(bindings_.sizeCapWidget, bindings_.previewLabel, fitted);
    if (fitted.isEmpty() || fitted == lastScaledSize_)
        return; // nothing to redo at this size

    lastScaledSize_ = fitted;
    lastPreviewTargetSize_ = target;
    bindings_.previewLabel->setPixmap(displayedFullPixmap_.scaled(fitted, Qt::KeepAspectRatio, Qt::SmoothTransformation));
}

const ImagePreviewBindings &ImagePreviewController::bindings() const
{
    return bindings_;
}

bool ImagePreviewController::hasCachedPixmap() const
{
    return !cachedPreviewPixmap_.isNull();
}

const QPixmap &ImagePreviewController::cachedPixmap() const
{
    return cachedPreviewPixmap_;
}

QString ImagePreviewController::cachedSourcePath() const
{
    return cachedPreviewSourcePath_;
}

QSize ImagePreviewController::lastTargetSize() const
{
    return lastPreviewTargetSize_;
}

bool ImagePreviewController::loadPixmapIfNeeded(const QString &path, bool forceReload)
{
    return loadPixmapIntoCache(path, forceReload);
}

bool ImagePreviewController::loadPixmapIntoCache(const QString &path, bool forceReload)
{
    const QString normalizedPath = path.trimmed();
    if (normalizedPath.isEmpty())
        return false;

    const QFileInfo info(normalizedPath);
    if (!info.exists() || !info.isFile())
        return false;

    const qint64 modifiedMs = info.lastModified().toMSecsSinceEpoch();
    const qint64 fileSize = info.size();
    const bool sameSource = cachedPreviewSourcePath_ == normalizedPath;
    const bool fileUnchanged = sameSource &&
                               cachedPreviewLastModifiedMs_ == modifiedMs &&
                               cachedPreviewFileSize_ == fileSize;

    if (!forceReload && fileUnchanged && !cachedPreviewPixmap_.isNull())
        return true;

    QPixmap pixmap;
    if (!pixmap.load(normalizedPath))
        return false;

    cachedPreviewSourcePath_ = normalizedPath;
    cachedPreviewPixmap_ = pixmap;
    cachedPreviewLastModifiedMs_ = modifiedMs;
    cachedPreviewFileSize_ = fileSize;
    return true;
}

bool ImagePreviewController::showPixmap(const QString &sourcePath, const QPixmap &pixmap, const QString &summaryText)
{
    if (!bindings_.previewLabel || pixmap.isNull())
        return false;

    if (bindings_.mediaPreviewController)
        bindings_.mediaPreviewController->clearVideoPreview();

    setEmptyState(false);
    bindings_.previewLabel->setText(QString());

    // Keep the full-res source so a resize can re-scale losslessly; only reset the size cache when the
    // source actually changes so repeated same-image refreshes don't re-scale needlessly.
    const bool sameSource = (displayedSourcePath_ == sourcePath && !displayedFullPixmap_.isNull());
    displayedFullPixmap_ = pixmap;
    displayedSourcePath_ = sourcePath;
    lastRenderedPreviewFingerprint_ = buildRenderedPreviewFingerprint(sourcePath, summaryText, QSize());
    if (!sameSource)
        lastScaledSize_ = QSize();

    refit();
    return true;
}

bool ImagePreviewController::showCachedPixmap(const QString &sourcePath, const QString &summaryText)
{
    return showPixmap(sourcePath, cachedPreviewPixmap_, summaryText);
}

void ImagePreviewController::clearCache(bool resetFingerprint)
{
    cachedPreviewSourcePath_.clear();
    cachedPreviewPixmap_ = QPixmap();
    cachedPreviewLastModifiedMs_ = -1;
    cachedPreviewFileSize_ = -1;
    if (resetFingerprint)
        clearRenderedFingerprint();
}

void ImagePreviewController::clearRenderedFingerprint()
{
    lastRenderedPreviewFingerprint_.clear();
}

void ImagePreviewController::markVideoRendered(const QString &videoPath, const QString &caption)
{
    lastRenderedPreviewFingerprint_ = QStringLiteral("video:%1:%2").arg(videoPath, caption);
}

void ImagePreviewController::resetTargetSize()
{
    lastPreviewTargetSize_ = QSize();
    lastScaledSize_ = QSize();
}

void ImagePreviewController::setEmptyState(bool emptyState)
{
    if (!bindings_.previewLabel)
        return;

    if (bindings_.previewLabel->property("emptyState").toBool() == emptyState)
        return;

    bindings_.previewLabel->setProperty("emptyState", emptyState);
    repolishPreviewLabel();
}

void ImagePreviewController::showText(const QString &text, bool clearPixmap)
{
    if (!bindings_.previewLabel)
        return;

    if (clearPixmap)
    {
        bindings_.previewLabel->setPixmap(QPixmap());
        releaseAspectCap(bindings_.sizeCapWidget);
        // Drop the retained source so a later resize refit() can't repaint the image over this text.
        displayedFullPixmap_ = QPixmap();
        displayedSourcePath_.clear();
        lastScaledSize_ = QSize();
    }
    bindings_.previewLabel->setText(text);
}

void ImagePreviewController::clearLabelPixmap()
{
    releaseAspectCap(bindings_.sizeCapWidget);
    if (bindings_.previewLabel)
        bindings_.previewLabel->setPixmap(QPixmap());
    displayedFullPixmap_ = QPixmap();
    displayedSourcePath_.clear();
    lastScaledSize_ = QSize();
}

QString ImagePreviewController::buildRenderedPreviewFingerprint(const QString &sourcePath,
                                                               const QString &summaryText,
                                                               const QSize &targetSize) const
{
    return QStringLiteral("%1|%2|%3x%4|%5|%6")
        .arg(sourcePath)
        .arg(summaryText)
        .arg(targetSize.width())
        .arg(targetSize.height())
        .arg(cachedPreviewLastModifiedMs_)
        .arg(cachedPreviewFileSize_);
}

void ImagePreviewController::repolishPreviewLabel()
{
    if (!bindings_.previewLabel)
        return;

    if (bindings_.repolishWidget)
        bindings_.repolishWidget(bindings_.previewLabel);
}

} // namespace spellvision::preview
