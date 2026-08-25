#include "EyePickStore.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIODevice>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QStandardPaths>

namespace
{
QString legacyStorePath(const QString &projectRoot)
{
    if (projectRoot.trimmed().isEmpty())
        return {};
    return QDir(projectRoot).filePath(QStringLiteral("runtime/eye_picks.json"));
}
}

QString EyePickStore::normalizePath(const QString &path)
{
    const QString trimmed = path.trimmed();
    if (trimmed.isEmpty())
        return {};
    return QDir::fromNativeSeparators(QFileInfo(trimmed).absoluteFilePath());
}

void EyePickStore::setProjectRoot(const QString &root)
{
    projectRoot_ = QDir::fromNativeSeparators(root.trimmed());
}

QString EyePickStore::storePath() const
{
    QString stateRoot = qEnvironmentVariable("SPELLVISION_STATE_ROOT").trimmed();
    if (stateRoot.isEmpty())
        stateRoot = QDir(QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation))
                        .filePath(QStringLiteral("runtime"));
    return QDir(stateRoot).filePath(QStringLiteral("eye_picks.json"));
}

QString EyePickStore::markFor(const QString &mediaPath) const
{
    return marks_.value(normalizePath(mediaPath));
}

void EyePickStore::setMark(const QString &mediaPath, const QString &mark)
{
    const QString key = normalizePath(mediaPath);
    if (key.isEmpty())
        return;
    const QString trimmed = mark.trimmed().toLower();
    if (trimmed.isEmpty() || (trimmed != QLatin1String("keep") && trimmed != QLatin1String("no")))
        marks_.remove(key);
    else
        marks_.insert(key, trimmed);
}

bool EyePickStore::load()
{
    marks_.clear();
    const QString path = storePath();
    if (path.isEmpty())
        return false;
    QString sourcePath = path;
    const QString legacyPath = legacyStorePath(projectRoot_);
    const bool migrateLegacy = !QFileInfo::exists(path)
                               && !legacyPath.isEmpty()
                               && QFileInfo::exists(legacyPath);
    if (migrateLegacy)
        sourcePath = legacyPath;

    QFile file(sourcePath);
    if (!file.open(QIODevice::ReadOnly))
        return false;
    QJsonParseError parseError{};
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject())
        return false;
    const QJsonObject root = document.object();
    if (!root.value(QStringLiteral("picks")).isObject())
        return false;
    const QJsonObject picks = root.value(QStringLiteral("picks")).toObject();
    for (auto it = picks.begin(); it != picks.end(); ++it)
    {
        const QString mark = it.value().toString().trimmed().toLower();
        if (mark == QLatin1String("keep") || mark == QLatin1String("no"))
            marks_.insert(normalizePath(it.key()), mark);
    }
    if (migrateLegacy)
        save();
    return true;
}

bool EyePickStore::save() const
{
    const QString path = storePath();
    if (path.isEmpty())
        return false;
    if (!QDir().mkpath(QFileInfo(path).absolutePath()))
        return false;
    QJsonObject picks;
    for (auto it = marks_.constBegin(); it != marks_.constEnd(); ++it)
        picks.insert(it.key(), it.value());
    QJsonObject root;
    root.insert(QStringLiteral("version"), 1);
    root.insert(QStringLiteral("picks"), picks);
    const QByteArray data = QJsonDocument(root).toJson(QJsonDocument::Indented);
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly))
        return false;
    if (file.write(data) != data.size())
        return false;
    return file.commit();
}

bool EyePickStore::exportTo(const QString &destPath) const
{
    const QString dest = destPath.trimmed();
    if (dest.isEmpty())
        return false;
    if (!save())
        return false;
    if (!QDir().mkpath(QFileInfo(dest).absolutePath()))
        return false;
    QFile source(storePath());
    if (!source.open(QIODevice::ReadOnly))
        return false;
    const QByteArray data = source.readAll();
    QSaveFile exportFile(dest);
    if (!exportFile.open(QIODevice::WriteOnly))
        return false;
    if (exportFile.write(data) != data.size())
        return false;
    return exportFile.commit();
}
