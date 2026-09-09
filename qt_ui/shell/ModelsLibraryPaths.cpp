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

QString resolveModelsLibraryRoot(const QString &raw)
{
    const QString trimmed = raw.trimmed();
    if (trimmed.isEmpty())
        return {};

    const QString path = QDir::fromNativeSeparators(QFileInfo(trimmed).absoluteFilePath());
    if (path.isEmpty())
        return {};

    auto hasComfyModelTree = [](const QString &root) {
        const QDir dir(root);
        return dir.exists(QStringLiteral("checkpoints"))
            || dir.exists(QStringLiteral("diffusion_models"))
            || dir.exists(QStringLiteral("loras"));
    };

    if (!QDir(path).exists())
        return path;
    if (hasComfyModelTree(path))
        return path;
    const QString models = QDir::fromNativeSeparators(QDir(path).filePath(QStringLiteral("models")));
    if (hasComfyModelTree(models))
        return models;
    const QString nested = QDir::fromNativeSeparators(QDir(path).filePath(QStringLiteral("AI_ASSETS/models")));
    if (hasComfyModelTree(nested))
        return nested;
    return path;
}

QStringList scannableModelsRoots(const QString &primaryRoot, const QStringList &extraRoots)
{
    QStringList out;
    auto consider = [&out](const QString &raw) {
        if (raw.trimmed().isEmpty())
            return;
        const QString path = QDir::fromNativeSeparators(QFileInfo(raw.trimmed()).absoluteFilePath());
        if (path.isEmpty())
            return;
        const QStorageInfo storage(path);
        if (!storage.isValid() || !storage.isReady())
            return;
        if (!QDir(path).exists())
            return;
        const QString library = resolveModelsLibraryRoot(path);
        if (!QDir(library).exists())
            return;
        if (!out.contains(library))
            out.append(library);
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
