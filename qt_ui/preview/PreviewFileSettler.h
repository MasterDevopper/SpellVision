#pragma once

#include <QDateTime>
#include <QFileInfo>
#include <QString>
#include <QtGlobal>

namespace spellvision::preview
{

struct FileSnapshot
{
    QString path;
    bool exists = false;
    bool isFile = false;
    qint64 size = -1;
    qint64 modifiedMs = -1;
    qint64 ageMs = -1;

    [[nodiscard]] bool isUsable(qint64 minBytes = 1) const;
    [[nodiscard]] bool sameFileVersionAs(const FileSnapshot &other) const;
};

class PreviewFileSettler
{
public:
    static constexpr qint64 DefaultMinimumBytes = 1024;
    static constexpr qint64 DefaultMinimumAgeMs = 450;

    [[nodiscard]] static FileSnapshot snapshot(const QString &path);
    [[nodiscard]] static bool isSettled(const FileSnapshot &snapshot,
                                        qint64 minBytes = DefaultMinimumBytes,
                                        qint64 minAgeMs = DefaultMinimumAgeMs);
    [[nodiscard]] static bool hasChanged(const FileSnapshot &current,
                                         qint64 previousSize,
                                         qint64 previousModifiedMs);
    [[nodiscard]] static bool shouldDeferLoad(const FileSnapshot &snapshot,
                                              qint64 minBytes = DefaultMinimumBytes,
                                              qint64 minAgeMs = DefaultMinimumAgeMs);
};

} // namespace spellvision::preview
