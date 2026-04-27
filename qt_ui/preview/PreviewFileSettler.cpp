#include "PreviewFileSettler.h"

namespace spellvision::preview
{

bool FileSnapshot::isUsable(qint64 minBytes) const
{
    return exists && isFile && size >= minBytes;
}

bool FileSnapshot::sameFileVersionAs(const FileSnapshot &other) const
{
    return path == other.path && size == other.size && modifiedMs == other.modifiedMs;
}

FileSnapshot PreviewFileSettler::snapshot(const QString &path)
{
    const QString normalizedPath = path.trimmed();
    QFileInfo info(normalizedPath);

    FileSnapshot result;
    result.path = normalizedPath;
    result.exists = !normalizedPath.isEmpty() && info.exists();
    result.isFile = result.exists && info.isFile();
    result.size = result.isFile ? info.size() : -1;
    result.modifiedMs = result.isFile ? info.lastModified().toMSecsSinceEpoch() : -1;

    if (result.modifiedMs > 0)
    {
        const qint64 nowMs = QDateTime::currentDateTimeUtc().toMSecsSinceEpoch();
        result.ageMs = qMax<qint64>(0, nowMs - result.modifiedMs);
    }

    return result;
}

bool PreviewFileSettler::isSettled(const FileSnapshot &snapshot, qint64 minBytes, qint64 minAgeMs)
{
    if (!snapshot.isUsable(minBytes))
        return false;

    if (snapshot.ageMs < 0)
        return false;

    return snapshot.ageMs >= minAgeMs;
}

bool PreviewFileSettler::hasChanged(const FileSnapshot &current, qint64 previousSize, qint64 previousModifiedMs)
{
    if (!current.exists || !current.isFile)
        return false;

    return current.size != previousSize || current.modifiedMs != previousModifiedMs;
}

bool PreviewFileSettler::shouldDeferLoad(const FileSnapshot &snapshot, qint64 minBytes, qint64 minAgeMs)
{
    return !isSettled(snapshot, minBytes, minAgeMs);
}

} // namespace spellvision::preview
