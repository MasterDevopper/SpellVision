#pragma once

#include <QObject>
#include <QPixmap>
#include <QSize>
#include <QString>
#include <QtGlobal>

#include <functional>

class QLabel;
class QWidget;

namespace spellvision::preview
{

class MediaPreviewController;

struct ImagePreviewBindings
{
    QLabel *previewLabel = nullptr;
    MediaPreviewController *mediaPreviewController = nullptr;
    std::function<void(QWidget *)> repolishWidget;
};

class ImagePreviewController : public QObject
{
    Q_OBJECT

public:
    explicit ImagePreviewController(QObject *parent = nullptr);

    void bind(const ImagePreviewBindings &bindings);
    [[nodiscard]] const ImagePreviewBindings &bindings() const;

    [[nodiscard]] bool hasCachedPixmap() const;
    [[nodiscard]] const QPixmap &cachedPixmap() const;
    [[nodiscard]] QString cachedSourcePath() const;
    [[nodiscard]] QSize lastTargetSize() const;

    bool loadPixmapIfNeeded(const QString &path, bool forceReload = false);
    bool loadPixmapIntoCache(const QString &path, bool forceReload = false);
    bool showPixmap(const QString &sourcePath, const QPixmap &pixmap, const QString &summaryText);
    bool showCachedPixmap(const QString &sourcePath, const QString &summaryText);

    void clearCache(bool resetFingerprint = true);
    void clearRenderedFingerprint();
    void markVideoRendered(const QString &videoPath, const QString &caption);
    void resetTargetSize();

    void setEmptyState(bool emptyState);
    void showText(const QString &text, bool clearPixmap = true);
    void clearLabelPixmap();

private:
    [[nodiscard]] QString buildRenderedPreviewFingerprint(const QString &sourcePath,
                                                          const QString &summaryText,
                                                          const QSize &targetSize) const;
    void repolishPreviewLabel();

    ImagePreviewBindings bindings_;
    QSize lastPreviewTargetSize_{};
    QString cachedPreviewSourcePath_;
    QPixmap cachedPreviewPixmap_;
    qint64 cachedPreviewLastModifiedMs_ = -1;
    qint64 cachedPreviewFileSize_ = -1;
    QString lastRenderedPreviewFingerprint_;
};

} // namespace spellvision::preview
