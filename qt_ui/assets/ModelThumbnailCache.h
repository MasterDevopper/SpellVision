#pragma once

// Model Library Arc — S0 data layer (design doc 22, §2.5 + §2.2).
// Disk-backed, lazy, viewport-driven thumbnail cache + the type-colored fallback tile. NEVER
// pre-generates all 710 — thumbnail() enqueues generation only for the source it is asked about,
// off the UI thread, and emits thumbnailReady() when a tile lands so the view repaints one row.

#include <QObject>
#include <QPixmap>
#include <QSet>
#include <QString>

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

signals:
    void thumbnailReady(const QString &key, int size);

private:
    void enqueue(const QString &sourcePreviewPath, const QString &key, int size);
    QString cacheDir() const;
    QString cacheFilePath(const QString &key, int size) const;
    static QString memKeyFor(const QString &key, int size);

    QSet<QString> inFlight_;
};

// §2.2 — the fallback for the ~43% of models with no preview. A type-colored rounded tile the same
// shape/size as a real thumbnail, so layout never shifts. Theme-token derived (hue-rotates the
// theme accent per type for a stable, learnable color); no raw colors.
QPixmap modelPlaceholderThumbnail(const QString &type, const QString &family, int size);

} // namespace spellvision::assets
