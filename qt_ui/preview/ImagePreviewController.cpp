#include "ImagePreviewController.h"

#include "MediaPreviewController.h"

#include <QFileInfo>
#include <QLabel>
#include <QRect>
#include <QWidget>

namespace spellvision::preview
{

ImagePreviewController::ImagePreviewController(QObject *parent)
    : QObject(parent)
{
}

void ImagePreviewController::bind(const ImagePreviewBindings &bindings)
{
    bindings_ = bindings;
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

    QSize target = bindings_.previewLabel->contentsRect().size();
    if (target.width() < 64 || target.height() < 64)
        target = QSize(640, 480);

    const QString fingerprint = buildRenderedPreviewFingerprint(sourcePath, summaryText, target);
    if (lastRenderedPreviewFingerprint_ == fingerprint)
        return false;

    lastRenderedPreviewFingerprint_ = fingerprint;
    lastPreviewTargetSize_ = target;

    if (bindings_.mediaPreviewController)
        bindings_.mediaPreviewController->clearVideoPreview();

    setEmptyState(false);
    bindings_.previewLabel->setText(QString());
    bindings_.previewLabel->setPixmap(pixmap.scaled(target, Qt::KeepAspectRatio, Qt::SmoothTransformation));
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
        bindings_.previewLabel->setPixmap(QPixmap());
    bindings_.previewLabel->setText(text);
}

void ImagePreviewController::clearLabelPixmap()
{
    if (bindings_.previewLabel)
        bindings_.previewLabel->setPixmap(QPixmap());
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
