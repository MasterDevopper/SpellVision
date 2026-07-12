#pragma once

// Model Library Arc — S0 data layer (design doc 22, §2.5 + §2.2).
// Disk-backed, lazy, viewport-driven thumbnail cache + the type-colored fallback tile. NEVER
// pre-generates all 710 — thumbnail() enqueues generation only for the source it is asked about,
// off the UI thread, and emits thumbnailReady() when a tile lands so the view repaints one row.

#include <QObject>
#include <QPixmap>
#include <QRectF>
#include <QSet>
#include <QString>

class QPainter;

namespace spellvision::assets
{

class ModelThumbnailCache : public QObject
{
    Q_OBJECT
public:
    explicit ModelThumbnailCache(QObject *parent = nullptr);

    // Ready pixmap (memory or valid disk cache) at `size`, or a NULL pixmap if not ready yet — in
    // which case generation is enqueued and thumbnailReady(key, size) fires later. `key` is a stable
    // identity (prefer sha256, else an abspath hash); `sourcePreviewPath` is the .png/.mp4-frame/etc.
    QPixmap thumbnail(const QString &sourcePreviewPath, const QString &key, int size);

    // True once generation for this key gave up (undecodable source). The delegate then shows the
    // fallback tile instead of an eternal "loading" state.
    bool isFailed(const QString &key, int size) const;

    // Optional venv python (with Pillow) used to transcode formats Qt can't decode — notably WebP,
    // which THIS Qt build has no plugin for and which is ~94% of Civitai previews.
    void setTranscodePython(const QString &pythonExe);

signals:
    void thumbnailReady(const QString &key, int size);

private:
    void enqueue(const QString &sourcePreviewPath, const QString &key, int size);
    QString cacheDir() const;
    QString cacheFilePath(const QString &key, int size) const;
    static QString memKeyFor(const QString &key, int size);

    QSet<QString> inFlight_;
    QSet<QString> failed_;
    QString transcodePython_;
};

// §2.2 (+ Amendment A.2) — the fallback for the ~43% of models with no preview. A type-colored rounded
// tile, theme-token derived (hue-rotates the accent per type for a stable, learnable color; no raw
// colors). paintModelPlaceholder fills an arbitrary rounded rect (the card delegate paints it straight
// into the 2/3 preview area, so the fallback is card-proportioned, not a small icon in a big box).
void paintModelPlaceholder(QPainter *painter, const QRectF &rect, qreal radius,
                           const QString &type, const QString &family);
QPixmap modelPlaceholderThumbnail(const QString &type, const QString &family, int size);

} // namespace spellvision::assets
