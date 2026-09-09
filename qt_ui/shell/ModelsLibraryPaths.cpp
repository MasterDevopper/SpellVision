#include "ModelsLibraryPaths.h"

#include <QDir>
#include <QFile>
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

QString composeManagedExtraModelPathsBlock(const QStringList &libraries)
{
    static const char *kBegin = "# >>> SpellVision managed model paths >>>";
    static const char *kEnd = "# <<< SpellVision managed model paths <<<";
    QStringList roots;
    for (const QString &raw : libraries)
    {
        QString path = QDir::fromNativeSeparators(raw.trimmed());
        while (path.endsWith(QLatin1Char('/')))
            path.chop(1);
        if (path.isEmpty() || roots.contains(path))
            continue;
        roots.append(path);
    }
    if (roots.isEmpty())
        return {};

    static const char *kKeys[][2] = {
        {"checkpoints", "checkpoints"},
        {"configs", "configs"},
        {"vae", "vae"},
        {"clip", "text_encoders"},
        {"text_encoders", "text_encoders"},
        {"clip_vision", "clip_vision"},
        {"loras", "loras"},
        {"controlnet", "controlnet"},
        {"embeddings", "embeddings"},
        {"upscale_models", "upscale_models"},
        {"latent_upscale_models", "latent_upscale_models"},
        {"unet", "diffusion_models"},
        {"diffusion_models", "diffusion_models"},
    };
    QString block;
    block += QString::fromLatin1(kBegin);
    block += QLatin1Char('\n');
    for (int i = 0; i < roots.size(); ++i)
    {
        const QString name = (i == 0)
            ? QStringLiteral("spellvision")
            : QStringLiteral("spellvision_extra_%1").arg(i - 1);
        block += name;
        block += QStringLiteral(":\n    base_path: ");
        block += roots.at(i);
        block += QLatin1Char('\n');
        for (const auto &pair : kKeys)
        {
            block += QStringLiteral("    ");
            block += QString::fromLatin1(pair[0]);
            block += QStringLiteral(": ");
            block += QString::fromLatin1(pair[1]);
            block += QLatin1Char('\n');
        }
    }
    block += QString::fromLatin1(kEnd);
    block += QLatin1Char('\n');
    return block;
}

bool writeManagedExtraModelPaths(const QString &yamlPath, const QStringList &libraries)
{
    if (yamlPath.trimmed().isEmpty())
        return false;
    const QString begin = QStringLiteral("# >>> SpellVision managed model paths >>>");
    const QString end = QStringLiteral("# <<< SpellVision managed model paths <<<");
    const QString block = composeManagedExtraModelPathsBlock(libraries);
    QFile file(yamlPath);
    QString existing;
    if (file.exists() && file.open(QIODevice::ReadOnly | QIODevice::Text))
    {
        existing = QString::fromUtf8(file.readAll());
        file.close();
    }
    QString merged;
    const int start = existing.indexOf(begin);
    const int stop = existing.indexOf(end);
    if (start >= 0 && stop > start)
    {
        merged = existing.left(start);
        if (!block.isEmpty())
            merged += block;
        merged += existing.mid(stop + end.size());
        if (!merged.endsWith(QLatin1Char('\n')))
            merged += QLatin1Char('\n');
    }
    else if (block.isEmpty())
    {
        merged = existing;
    }
    else if (existing.trimmed().isEmpty())
    {
        merged = block;
    }
    else
    {
        merged = existing.trimmed();
        merged += QStringLiteral("\n\n");
        merged += block;
    }
    if (merged == existing)
        return false;
    QDir().mkpath(QFileInfo(yamlPath).absolutePath());
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text | QIODevice::Truncate))
        return false;
    file.write(merged.toUtf8());
    return true;
}

} // namespace spellvision::shell
