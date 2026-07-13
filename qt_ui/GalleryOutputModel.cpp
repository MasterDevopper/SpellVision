#include "GalleryOutputModel.h"

#include "generation/OutputPathHelpers.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFileInfoList>
#include <QJsonDocument>
#include <QJsonObject>

#include <algorithm>

namespace
{
bool isVideoExtension(const QString &suffixLower)
{
    return suffixLower == QStringLiteral("mp4") || suffixLower == QStringLiteral("mov")
           || suffixLower == QStringLiteral("webm") || suffixLower == QStringLiteral("mkv")
           || suffixLower == QStringLiteral("avi") || suffixLower == QStringLiteral("m4v");
}

GalleryOutputModel::Record buildRecord(const QFileInfo &fi, const QString &sidecarPath)
{
    GalleryOutputModel::Record rec;
    rec.path = QDir::fromNativeSeparators(fi.absoluteFilePath());

    QJsonObject meta;
    QFile f(sidecarPath);
    if (f.open(QIODevice::ReadOnly))
    {
        meta = QJsonDocument::fromJson(f.readAll()).object();
        f.close();
    }

    const QString suffix = fi.suffix().toLower();
    rec.isVideo = isVideoExtension(suffix);

    rec.modeId = meta.value(QStringLiteral("task_type")).toString().trimmed().toLower();
    if (rec.modeId.isEmpty())
        rec.modeId = rec.isVideo ? QStringLiteral("t2v") : QStringLiteral("t2i");

    const QString prompt = meta.value(QStringLiteral("prompt")).toString().trimmed();
    rec.title = prompt.isEmpty() ? fi.completeBaseName() : prompt;

    const QString model = meta.value(QStringLiteral("model_display")).toString().trimmed();
    const int w = meta.value(QStringLiteral("width")).toInt();
    const int h = meta.value(QStringLiteral("height")).toInt();
    QStringList sub;
    if (!model.isEmpty())
        sub << model;
    if (w > 0 && h > 0)
        sub << QStringLiteral("%1×%2").arg(w).arg(h);
    rec.subtitle = sub.join(QStringLiteral("   ·   "));

    // Fuller hover tooltip.
    QStringList tip;
    tip << fi.fileName();
    tip << QStringLiteral("Mode: %1").arg(rec.modeId.toUpper());
    if (!model.isEmpty())
        tip << QStringLiteral("Model: %1").arg(model);
    const int seed = meta.value(QStringLiteral("seed")).toInt();
    tip << QStringLiteral("Seed: %1").arg(seed == 0 ? QStringLiteral("random") : QString::number(seed));
    const int steps = meta.value(QStringLiteral("steps")).toInt();
    if (steps > 0)
        tip << QStringLiteral("Steps: %1").arg(steps);
    if (!prompt.isEmpty())
        tip << QStringLiteral("\n%1").arg(prompt);
    rec.tooltip = tip.join(QChar('\n'));

    // Images thumbnail from the file itself; video posters aren't cheap to extract for a whole grid,
    // so the delegate paints a play-badged placeholder (v1 tradeoff -- see the build report).
    rec.thumbnailPath = rec.isVideo ? QString() : rec.path;
    return rec;
}
} // namespace

GalleryOutputModel::GalleryOutputModel(QObject *parent)
    : QAbstractListModel(parent)
{
}

int GalleryOutputModel::maxRecords()
{
    return 120; // enough to fill the grid + scroll without stalling the scan on a huge history
}

int GalleryOutputModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : records_.size();
}

const GalleryOutputModel::Record *GalleryOutputModel::recordAt(int row) const
{
    if (row < 0 || row >= records_.size())
        return nullptr;
    return &records_.at(row);
}

QVariant GalleryOutputModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= records_.size())
        return {};
    const Record &r = records_.at(index.row());
    switch (role)
    {
    case ThumbnailPathRole:
        return r.thumbnailPath;
    case TitleRole:
        return r.title;
    case SubtitleRole:
        return r.subtitle;
    case ModeIdRole:
        return r.modeId;
    case IsVideoRole:
        return r.isVideo;
    case PathRole:
        return r.path;
    case TooltipRole:
    case Qt::ToolTipRole:
        return r.tooltip;
    default:
        return {};
    }
}

QHash<int, QByteArray> GalleryOutputModel::roleNames() const
{
    return {
        {ThumbnailPathRole, "thumbnailPath"},
        {TitleRole, "title"},
        {SubtitleRole, "subtitle"},
        {ModeIdRole, "modeId"},
        {IsVideoRole, "isVideo"},
        {PathRole, "path"},
        {TooltipRole, "tooltip"},
    };
}

int GalleryOutputModel::reload()
{
    beginResetModel();
    records_.clear();

    const QString root = spellvision::generation::chooseComfyOutputPath();
    QDir dir(root);
    if (dir.exists())
    {
        static const QStringList mediaFilters = {
            QStringLiteral("*.png"), QStringLiteral("*.jpg"), QStringLiteral("*.jpeg"),
            QStringLiteral("*.webp"), QStringLiteral("*.bmp"), QStringLiteral("*.gif"),
            QStringLiteral("*.mp4"), QStringLiteral("*.mov"), QStringLiteral("*.webm"),
            QStringLiteral("*.mkv"), QStringLiteral("*.avi"), QStringLiteral("*.m4v")};

        QFileInfoList files = dir.entryInfoList(mediaFilters, QDir::Files);
        std::sort(files.begin(), files.end(), [](const QFileInfo &a, const QFileInfo &b) {
            return a.lastModified() > b.lastModified(); // newest first
        });

        for (const QFileInfo &fi : files)
        {
            if (records_.size() >= maxRecords())
                break;
            // Only canonical SpellVision outputs (those with a base .json sidecar); skip raw ComfyUI
            // intermediates like "..._job_xxx_00001_.png" that carry no SpellVision record.
            const QString sidecar = dir.filePath(fi.completeBaseName() + QStringLiteral(".json"));
            if (!QFileInfo::exists(sidecar))
                continue;
            Record rec = buildRecord(fi, sidecar);
            if (!rec.path.isEmpty())
                records_.push_back(rec);
        }
    }

    endResetModel();
    return records_.size();
}
