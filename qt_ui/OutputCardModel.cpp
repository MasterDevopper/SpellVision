#include "OutputCardModel.h"

#include "assets/ModelCardModel.h"
#include "assets/ModelCardView.h"
#include "generation/OutputPathHelpers.h"

#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QFileInfoList>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSet>

#include <algorithm>

namespace
{
using Role = spellvision::assets::ModelCardModel::Role;
using Overlay = spellvision::assets::ModelCardView::OverlayRole;

bool isVideoExtension(const QString &suffixLower)
{
    return suffixLower == QStringLiteral("mp4") || suffixLower == QStringLiteral("mov")
           || suffixLower == QStringLiteral("webm") || suffixLower == QStringLiteral("mkv")
           || suffixLower == QStringLiteral("avi") || suffixLower == QStringLiteral("m4v");
}

OutputCardModel::Output buildOutput(const QFileInfo &fi, const QString &sidecarPath)
{
    OutputCardModel::Output o;
    o.path = QDir::fromNativeSeparators(fi.absoluteFilePath());
    const QString base = fi.completeBaseName();
    if (base.compare(QLatin1String("plate"), Qt::CaseInsensitive) == 0
        || base.startsWith(QLatin1String("plate_"), Qt::CaseInsensitive))
        o.strippedName = fi.dir().dirName();
    else
        o.strippedName = base;
    o.fullName = fi.fileName();
    o.isVideo = isVideoExtension(fi.suffix().toLower());

    QJsonObject meta;
    QFile f(sidecarPath);
    if (f.open(QIODevice::ReadOnly))
    {
        meta = QJsonDocument::fromJson(f.readAll()).object();
        f.close();
    }
    o.modeId = meta.value(QStringLiteral("task_type")).toString().trimmed().toLower();
    if (o.modeId.isEmpty())
        o.modeId = o.isVideo ? QStringLiteral("t2v") : QStringLiteral("t2i");

    const QString model = meta.value(QStringLiteral("model_display")).toString().trimmed();
    const int w = meta.value(QStringLiteral("width")).toInt();
    const int h = meta.value(QStringLiteral("height")).toInt();
    const int seed = meta.value(QStringLiteral("seed")).toInt();
    QStringList sub;
    if (!model.isEmpty())
        sub << model;
    if (w > 0 && h > 0)
        sub << QStringLiteral("%1×%2").arg(w).arg(h);
    sub << QStringLiteral("seed %1").arg(seed == 0 ? QStringLiteral("random") : QString::number(seed));
    o.subtitle = sub.join(QStringLiteral("   ·   "));
    return o;
}
} // namespace

OutputCardModel::OutputCardModel(QObject *parent)
    : QAbstractListModel(parent)
{
}

int OutputCardModel::maxRecords()
{
    return 800;
}

void OutputCardModel::setExtraRoots(const QStringList &roots)
{
    extraRoots_.clear();
    QSet<QString> seen;
    for (const QString &root : roots)
    {
        const QString normalized = QDir::fromNativeSeparators(QFileInfo(root.trimmed()).absoluteFilePath());
        if (normalized.isEmpty() || seen.contains(normalized.toLower()))
            continue;
        if (!QDir(normalized).exists())
            continue;
        seen.insert(normalized.toLower());
        extraRoots_.push_back(normalized);
    }
}

void OutputCardModel::setPickMarks(const QHash<QString, QString> &marks)
{
    pickMarks_ = marks;
    if (!outputs_.isEmpty())
        emit dataChanged(index(0), index(outputs_.size() - 1), {spellvision::assets::ModelCardModel::Role::TypeRole});
}

void OutputCardModel::setPickFilter(const QString &filter)
{
    const QString next = filter.trimmed().toLower();
    pickFilter_ = next.isEmpty() ? QStringLiteral("all") : next;
}

void OutputCardModel::setNameNeedle(const QString &needle)
{
    nameNeedle_ = needle.trimmed();
}

bool OutputCardModel::acceptsPickFilter(const QString &path) const
{
    if (pickFilter_ == QLatin1String("all"))
        return true;
    const QString mark = pickMarks_.value(path);
    if (pickFilter_ == QLatin1String("keep"))
        return mark == QLatin1String("keep");
    if (pickFilter_ == QLatin1String("no"))
        return mark == QLatin1String("no");
    if (pickFilter_ == QLatin1String("unmarked"))
        return mark.isEmpty();
    return true;
}

int OutputCardModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : outputs_.size();
}

const OutputCardModel::Output *OutputCardModel::outputAt(int row) const
{
    if (row < 0 || row >= outputs_.size())
        return nullptr;
    return &outputs_.at(row);
}

QVariant OutputCardModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= outputs_.size())
        return {};
    const Output &o = outputs_.at(index.row());

    switch (role)
    {
    // --- ModelCardDelegate paints from these (unchanged delegate) ---
    case Role::StrippedNameRole:
        return o.strippedName;
    case Role::FullNameRole:
        return o.fullName;
    case Role::TypeRole:
        if (pickMarks_.value(o.path) == QLatin1String("keep"))
            return QStringLiteral("KEEP");
        if (pickMarks_.value(o.path) == QLatin1String("no"))
            return QStringLiteral("NO");
        return o.isVideo ? QStringLiteral("Video") : QStringLiteral("Image"); // badge
    case Role::FamilyRole:
        return o.modeId.toUpper(); // subtext line = source mode
    case Role::PreviewPathRole:
        return o.path; // media path; the cache turns a video into a poster
    case Role::NativePathRole:
    case Role::ModelValueRole:
        return o.path;
    case Role::Sha256Role:
        return QString(); // path-based cache key
    case Role::FavoriteRole:
        return false;

    // --- ModelCardView hover overlay labels (outputs reuse the view with output actions) ---
    case Overlay::PrimaryActionLabelRole:
        return QStringLiteral("Open");
    case Overlay::PrimaryActionEnabledRole:
        return true;
    case Overlay::SecondaryActionLabelRole:
        // Image -> send to I2I as input (cheap). Video -> none: I2V input is a still keyframe, not a
        // clip, so "re-animate this video" isn't a clean send-as-input (reported; deferred).
        return o.isVideo ? QString() : QStringLiteral("To I2I");
    case Overlay::SecondaryActionEnabledRole:
        return !o.isVideo;

    case Qt::ToolTipRole:
        return o.subtitle.isEmpty() ? o.fullName : QStringLiteral("%1\n%2").arg(o.fullName, o.subtitle);
    default:
        return {};
    }
}

void OutputCardModel::noteThumbnailReady(const QString &previewPathKey)
{
    const auto it = pathToRow_.constFind(previewPathKey);
    if (it == pathToRow_.constEnd())
        return;
    const int row = it.value();
    if (row >= 0 && row < outputs_.size())
        emit dataChanged(index(row), index(row));
}

int OutputCardModel::reload()
{
    beginResetModel();
    outputs_.clear();
    pathToRow_.clear();

    static const QStringList mediaFilters = {
        QStringLiteral("*.png"), QStringLiteral("*.jpg"), QStringLiteral("*.jpeg"),
        QStringLiteral("*.webp"), QStringLiteral("*.bmp"), QStringLiteral("*.gif"),
        QStringLiteral("*.mp4"), QStringLiteral("*.mov"), QStringLiteral("*.webm"),
        QStringLiteral("*.mkv"), QStringLiteral("*.avi"), QStringLiteral("*.m4v")};
    static const QStringList huntPlateFilters = {
        QStringLiteral("plate.png"), QStringLiteral("plate_*.png")};

    QFileInfoList files;
    const auto appendDir = [&](const QString &root, bool recursive, const QStringList &filters, int cap) {
        QDir dir(root);
        if (!dir.exists())
            return;
        if (!recursive)
        {
            files += dir.entryInfoList(filters, QDir::Files);
            return;
        }
        QDirIterator it(root, filters, QDir::Files, QDirIterator::Subdirectories);
        int seen = 0;
        while (it.hasNext() && seen < cap)
        {
            it.next();
            files.push_back(it.fileInfo());
            ++seen;
        }
    };

    const QString destRoot = spellvision::generation::userGenerationDestFolder();
    if (!destRoot.isEmpty())
        appendDir(destRoot, true, huntPlateFilters, 2000);
    if (extraRoots_.isEmpty() && destRoot.isEmpty())
        appendDir(spellvision::generation::chooseComfyOutputPath(), false, mediaFilters, 0);
    for (const QString &root : extraRoots_)
        appendDir(root, true, huntPlateFilters, 2000);

    std::sort(files.begin(), files.end(), [](const QFileInfo &a, const QFileInfo &b) {
        return a.lastModified() > b.lastModified();
    });

    QSet<QString> seenPaths;
    for (const QFileInfo &fi : files)
    {
        if (outputs_.size() >= maxRecords())
            break;
        Output o = buildOutput(fi, fi.absolutePath() + QLatin1Char('/') + fi.completeBaseName() + QStringLiteral(".json"));
        if (seenPaths.contains(o.path) || !acceptsPickFilter(o.path))
            continue;
        if (!nameNeedle_.isEmpty()
            && !o.fullName.contains(nameNeedle_, Qt::CaseInsensitive)
            && !o.strippedName.contains(nameNeedle_, Qt::CaseInsensitive)
            && !o.subtitle.contains(nameNeedle_, Qt::CaseInsensitive)
            && !o.path.contains(nameNeedle_, Qt::CaseInsensitive))
            continue;
        seenPaths.insert(o.path);
        pathToRow_.insert(o.path, outputs_.size());
        outputs_.push_back(o);
    }

    endResetModel();
    return outputs_.size();
}
