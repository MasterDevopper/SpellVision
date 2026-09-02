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
    // The widget whose maximum size follows the picture's aspect (the preview stack). Optional;
    // without it the label fills whatever box it is given, which is the pre-fix behaviour.
    QWidget *sizeCapWidget = nullptr;
    // The widget whose contents rect is the space the picture MAY take (the preview area). The cap
    // never shrinks it, so it is the only safe thing to measure a fit against -- see fitBudget().
    // Optional; without it the fit is measured on the label, which the cap constrains.
    QWidget *sizeBudgetWidget = nullptr;
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

    // Re-scale the currently-displayed source pixmap to fit the label's CURRENT size. Called on show
    // and (via the resize eventFilter) whenever the surface resizes -- this is what makes the preview
    // reliably fill the canvas instead of freezing at a cold-render size. No-op when showing text.
    void refit();

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;

private:
    [[nodiscard]] QString buildRenderedPreviewFingerprint(const QString &sourcePath,
                                                          const QString &summaryText,
                                                          const QSize &targetSize) const;
    void repolishPreviewLabel();
    // Fill the target, KeepAspectRatio, but never upscale beyond kMaxUpscale x native (avoid blowing a
    // 512px source into a blurry wall).
    [[nodiscard]] QSize computeFittedSize(const QSize &sourceSize, const QSize &target) const;

    ImagePreviewBindings bindings_;
    QSize lastPreviewTargetSize_{};
    QString cachedPreviewSourcePath_;
    QPixmap cachedPreviewPixmap_;
    qint64 cachedPreviewLastModifiedMs_ = -1;
    qint64 cachedPreviewFileSize_ = -1;
    QString lastRenderedPreviewFingerprint_;

    // What is currently painted on the label (full-res), so a resize can re-scale it losslessly.
    QPixmap displayedFullPixmap_;
    QString displayedSourcePath_;
    QSize lastScaledSize_{};
};

} // namespace spellvision::preview
