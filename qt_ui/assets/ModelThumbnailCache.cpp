#include "ModelThumbnailCache.h"

#include "../ThemeManager.h"

#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFont>
#include <QImage>
#include <QPainter>
#include <QPainterPath>
#include <QPixmapCache>
#include <QPointer>
#include <QStandardPaths>
#include <QtConcurrent>

#include <webp/decode.h>

namespace spellvision::assets
{

namespace
{
// Decode a WebP file by CONTENT (never by extension — Civitai previews are frequently misnamed .jpeg).
// Returns a null QImage if the file isn't WebP or fails to decode. Uses libwebp's WebPDecodeRGBA, which
// maps 1:1 to QImage::Format_RGBA8888 (R,G,B,A byte order) — no channel swizzle. The libwebp buffer is
// deep-copied into the QImage before WebPFree, so nothing aliases freed memory. Thread-safe (pure).
QImage decodeWebpByContent(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return {};
    const QByteArray data = file.readAll();
    if (data.size() <= 12
        || data.left(4) != QByteArrayLiteral("RIFF")
        || data.mid(8, 4) != QByteArrayLiteral("WEBP"))
        return {};

    int width = 0;
    int height = 0;
    uint8_t *rgba = WebPDecodeRGBA(reinterpret_cast<const uint8_t *>(data.constData()),
                                   static_cast<size_t>(data.size()), &width, &height);
    if (!rgba)
        return {};

    QImage image;
    if (width > 0 && height > 0)
        image = QImage(rgba, width, height, width * 4, QImage::Format_RGBA8888).copy(); // deep copy
    WebPFree(rgba);
    return image;
}

// A per-type hue rotation (degrees) applied to the theme accent, so each asset type gets a stable,
// learnable color while staying theme-derived. Default 0 == the accent itself.
int typeHueShift(const QString &type)
{
    const QString t = type.trimmed().toLower();
    if (t == QStringLiteral("lora")) return 40;
    if (t == QStringLiteral("vae")) return 195;
    if (t == QStringLiteral("upscaler")) return 95;
    if (t == QStringLiteral("encoder")) return 150;
    if (t == QStringLiteral("controlnet")) return 275;
    return 0; // Checkpoint / Model
}

QString typeMonogram(const QString &type)
{
    const QString t = type.trimmed().toLower();
    if (t == QStringLiteral("lora")) return QStringLiteral("LoRA");
    if (t == QStringLiteral("vae")) return QStringLiteral("VAE");
    if (t == QStringLiteral("upscaler")) return QStringLiteral("UP");
    if (t == QStringLiteral("encoder")) return QStringLiteral("ENC");
    if (t == QStringLiteral("controlnet")) return QStringLiteral("CN");
    if (t == QStringLiteral("checkpoint")) return QStringLiteral("CKPT");
    return QStringLiteral("MDL");
}

QColor withAlphaF(QColor color, qreal alpha)
{
    color.setAlphaF(alpha);
    return color;
}
} // namespace

ModelThumbnailCache::ModelThumbnailCache(QObject *parent)
    : QObject(parent)
{
}

QString ModelThumbnailCache::cacheDir() const
{
    QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    if (base.trimmed().isEmpty())
        base = QDir::current().filePath(QStringLiteral("runtime/cache/ui"));
    QDir dir(base);
    dir.mkpath(QStringLiteral("model_thumbnails"));
    return dir.filePath(QStringLiteral("model_thumbnails"));
}

QString ModelThumbnailCache::cacheFilePath(const QString &key, int size) const
{
    // Hash the caller's key (sha256 or abspath) to a bounded, filesystem-safe name.
    const QByteArray digest = QCryptographicHash::hash(key.toUtf8(), QCryptographicHash::Md5).toHex();
    return QDir(cacheDir()).filePath(QStringLiteral("%1_%2.png").arg(QString::fromLatin1(digest)).arg(size));
}

QString ModelThumbnailCache::memKeyFor(const QString &key, int size)
{
    return QStringLiteral("svmodelthumb:%1:%2").arg(key).arg(size);
}

QPixmap ModelThumbnailCache::thumbnail(const QString &sourcePreviewPath, const QString &key, int size)
{
    if (sourcePreviewPath.trimmed().isEmpty() || key.trimmed().isEmpty() || size <= 0)
        return {};

    const QString memKey = memKeyFor(key, size);

    QPixmap pm;
    if (QPixmapCache::find(memKey, &pm))
        return pm;

    // Disk cache is valid unless the source preview is newer (mtime invalidation, §2.5).
    const QString disk = cacheFilePath(key, size);
    const QFileInfo diskInfo(disk);
    if (diskInfo.exists())
    {
        const QFileInfo srcInfo(sourcePreviewPath);
        if (!srcInfo.exists() || diskInfo.lastModified() >= srcInfo.lastModified())
        {
            if (pm.load(disk))
            {
                QPixmapCache::insert(memKey, pm);
                return pm;
            }
        }
    }

    enqueue(sourcePreviewPath, key, size);
    return {};
}

void ModelThumbnailCache::enqueue(const QString &sourcePreviewPath, const QString &key, int size)
{
    const QString memKey = memKeyFor(key, size);
    if (inFlight_.contains(memKey))
        return;
    inFlight_.insert(memKey);

    const QString disk = cacheFilePath(key, size);
    QPointer<ModelThumbnailCache> self(this);

    (void)QtConcurrent::run([self, sourcePreviewPath, key, size, memKey, disk]() {
        // Off the UI thread: decode + scale + persist.
        QImage scaled;
        QDir().mkpath(QFileInfo(disk).absolutePath());

        QImage image(sourcePreviewPath);
        if (image.isNull())
        {
            // Qt couldn't decode it. Nearly all Civitai previews are WebP (this Qt has no WebP plugin)
            // and are frequently misnamed .jpeg -> decode by CONTENT, never by extension, via libwebp.
            image = decodeWebpByContent(sourcePreviewPath);
        }
        if (!image.isNull())
        {
            scaled = image.scaled(size, size, Qt::KeepAspectRatio, Qt::SmoothTransformation);
            scaled.save(disk, "PNG");
        }

        // Marshal back to the UI thread: QPixmapCache + signal emission are main-thread only. Emit
        // thumbnailReady either way so the delegate repaints (image on success, fallback on failure).
        QMetaObject::invokeMethod(qApp, [self, memKey, key, size, scaled]() {
            if (!self)
                return;
            self->inFlight_.remove(memKey);
            if (!scaled.isNull())
                QPixmapCache::insert(memKey, QPixmap::fromImage(scaled));
            else
                self->failed_.insert(memKey);
            emit self->thumbnailReady(key, size);
        }, Qt::QueuedConnection);
    });
}

bool ModelThumbnailCache::isFailed(const QString &key, int size) const
{
    return failed_.contains(memKeyFor(key, size));
}

void paintModelPlaceholder(QPainter *painter, const QRectF &rect, qreal radius,
                           const QString &type, const QString &family)
{
    if (!painter || rect.isEmpty())
        return;

    ThemeManager &tm = ThemeManager::instance();
    const QColor surface = tm.color(ThemeManager::Color::Surface2);
    const QColor accent = tm.color(ThemeManager::Color::Accent);
    const QColor border = tm.color(ThemeManager::Color::Border);
    const QColor textHi = tm.color(ThemeManager::Color::TextHi);
    const QColor textMid = tm.color(ThemeManager::Color::TextMid);

    // Hue-rotate the theme accent per type -> stable, learnable, still theme-derived.
    QColor tint = accent;
    if (accent.saturation() > 0)
        tint = QColor::fromHsv((accent.hue() + typeHueShift(type) + 360) % 360,
                               accent.saturation(), accent.value());

    painter->save();
    painter->setRenderHint(QPainter::Antialiasing, true);

    QPainterPath path;
    path.addRoundedRect(rect, radius, radius);
    painter->fillPath(path, surface);
    painter->fillPath(path, withAlphaF(tint, 0.20));
    painter->setPen(QPen(withAlphaF(border, 0.9), 1.0));
    painter->drawPath(path);

    const qreal shortSide = qMin(rect.width(), rect.height());

    // Type monogram (upper), family (lower). Sized off the short side so it reads at any card size.
    QFont mono = painter->font();
    mono.setBold(true);
    mono.setPixelSize(qMax(9, static_cast<int>(shortSide * 0.22)));
    painter->setFont(mono);
    painter->setPen(textHi);
    painter->drawText(QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.62),
                      Qt::AlignCenter, typeMonogram(type));

    const QString fam = family.trimmed();
    if (!fam.isEmpty())
    {
        QFont famFont = painter->font();
        famFont.setBold(false);
        famFont.setPixelSize(qMax(8, static_cast<int>(shortSide * 0.11)));
        painter->setFont(famFont);
        painter->setPen(textMid);
        painter->drawText(QRectF(rect.left(), rect.top() + rect.height() * 0.58, rect.width(), rect.height() * 0.36),
                          Qt::AlignHCenter | Qt::AlignTop, fam);
    }

    painter->restore();
}

QPixmap modelPlaceholderThumbnail(const QString &type, const QString &family, int size)
{
    if (size <= 0)
        return {};

    QPixmap pm(size, size);
    pm.fill(Qt::transparent);
    QPainter painter(&pm);
    paintModelPlaceholder(&painter, QRectF(0.75, 0.75, size - 1.5, size - 1.5), size * 0.16, type, family);
    painter.end();
    return pm;
}

} // namespace spellvision::assets
