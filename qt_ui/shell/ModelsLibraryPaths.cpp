#include "ModelsLibraryPaths.h"

#include <QDir>
#include <QFileInfo>
#include <QSettings>
#include <QStorageInfo>

namespace spellvision::shell
{

QString proposedModelsLibraryOnVolume(const QString &volumeRoot)
{
    const QString trimmed = volumeRoot.trimmed();
    if (trimmed.isEmpty())
        return {};

    QString root = QDir::fromNativeSeparators(trimmed);
    if (!root.endsWith(QLatin1Char('/')))
        root += QLatin1Char('/');
    return root + QStringLiteral("AI_ASSETS/models");
}

QStringList scannableModelsRoots(const QString &primaryRoot, const QStringList &extraRoots)
{
    QStringList out;
    auto consider = [&out](const QString &raw) {
        const QString path = QDir::fromNativeSeparators(QFileInfo(raw.trimmed()).absoluteFilePath());
        if (path.isEmpty())
            return;
        const QStorageInfo storage(path);
        if (!storage.isValid() || !storage.isReady())
            return;
        if (!QDir(path).exists())
            return;
        if (!out.contains(path))
            out.append(path);
    };

    consider(primaryRoot);
    for (const QString &extra : extraRoots)
        consider(extra);
    return out;
}

QStringList extraModelsRootsFromSettings()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    return settings.value(QStringLiteral("runtime/extraModelsRoots")).toStringList();
}

} // namespace spellvision::shell
