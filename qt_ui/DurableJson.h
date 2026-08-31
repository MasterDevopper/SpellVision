#pragma once

#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QSaveFile>
#include <QString>

namespace spellvision
{

inline bool writeJsonAtomically(const QString &path, const QJsonDocument &document)
{
    const QString trimmed = path.trimmed();
    if (trimmed.isEmpty() || !QDir().mkpath(QFileInfo(trimmed).absolutePath()))
        return false;

    const QByteArray data = document.toJson(QJsonDocument::Indented);
    QSaveFile file(trimmed);
    if (!file.open(QIODevice::WriteOnly))
        return false;
    if (file.write(data) != data.size())
        return false;
    return file.commit();
}

} // namespace spellvision
