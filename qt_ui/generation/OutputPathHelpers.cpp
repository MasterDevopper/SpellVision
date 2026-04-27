#include "OutputPathHelpers.h"

#include <QDir>
#include <QFileInfo>
#include <QRegularExpression>
#include <QSettings>
#include <QStringList>

namespace spellvision::generation
{
namespace
{
constexpr auto OrganizationName = "DarkDuck";
constexpr auto ApplicationName = "SpellVision";

constexpr auto LastGeneratedImageKey = "workspace/last_generated_image_path";
constexpr auto LastGeneratedVideoKey = "workspace/last_generated_video_path";
constexpr auto StagedI2IInputKey = "workspace/staged_i2i_input_path";

QString suffixForPath(const QString &path)
{
    return QFileInfo(path.trimmed()).suffix().toLower();
}

QSettings spellVisionSettings()
{
    return QSettings(QString::fromLatin1(OrganizationName), QString::fromLatin1(ApplicationName));
}

QStringList imageSuffixes()
{
    return {
        QStringLiteral("png"),
        QStringLiteral("jpg"),
        QStringLiteral("jpeg"),
        QStringLiteral("webp"),
        QStringLiteral("bmp"),
        QStringLiteral("gif")};
}

QStringList videoSuffixes()
{
    return {
        QStringLiteral("mp4"),
        QStringLiteral("webm"),
        QStringLiteral("mov"),
        QStringLiteral("mkv"),
        QStringLiteral("avi"),
        QStringLiteral("gif")};
}
} // namespace

QString chooseModelsRootPath()
{
    const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_MODELS")).trimmed();
    if (!envPath.isEmpty() && QDir(envPath).exists())
        return QDir::fromNativeSeparators(QDir(envPath).absolutePath());

    const QString preferred = QStringLiteral("D:/AI_ASSETS/models");
    if (QDir(preferred).exists())
        return preferred;

    const QString alternate = QStringLiteral("D:\\AI_ASSETS\\models");
    if (QDir(alternate).exists())
        return QDir::fromNativeSeparators(QDir(alternate).absolutePath());

    return preferred;
}

QString chooseComfyOutputPath()
{
    const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY")).trimmed();
    if (!envPath.isEmpty() && QDir(envPath).exists())
        return QDir(QDir::fromNativeSeparators(QDir(envPath).absolutePath())).filePath(QStringLiteral("output"));

    const QString preferred = QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI");
    if (QDir(preferred).exists())
        return QDir(preferred).filePath(QStringLiteral("output"));

    return QDir::fromNativeSeparators(QDir(preferred).filePath(QStringLiteral("output")));
}

bool isImageAssetPath(const QString &path)
{
    return imageSuffixes().contains(suffixForPath(path));
}

bool isVideoAssetPath(const QString &path)
{
    return videoSuffixes().contains(suffixForPath(path));
}

bool isMediaAssetPath(const QString &path)
{
    return isImageAssetPath(path) || isVideoAssetPath(path);
}

QString normalizedOutputFolder(const QString &folder)
{
    const QString trimmed = folder.trimmed();
    if (trimmed.isEmpty())
        return chooseComfyOutputPath();

    return QDir::fromNativeSeparators(QDir(trimmed).absolutePath());
}

QString sanitizedOutputPrefix(const QString &prefix, const QString &fallback)
{
    QString cleaned = prefix.trimmed();
    if (cleaned.isEmpty())
        cleaned = fallback.trimmed().isEmpty() ? QStringLiteral("spellvision_render") : fallback.trimmed();

    cleaned.replace(QRegularExpression(QStringLiteral("[\\\\/:*?\"<>|]+")), QStringLiteral("_"));
    cleaned.replace(QRegularExpression(QStringLiteral("\\s+")), QStringLiteral("_"));
    cleaned.replace(QRegularExpression(QStringLiteral("_+")), QStringLiteral("_"));
    cleaned = cleaned.trimmed();

    while (cleaned.startsWith(QChar('_')))
        cleaned.remove(0, 1);
    while (cleaned.endsWith(QChar('_')))
        cleaned.chop(1);

    return cleaned.isEmpty() ? QStringLiteral("spellvision_render") : cleaned;
}

QString metadataPathForOutputPath(const QString &outputPath, const QString &metadataRoot)
{
    const QString normalizedOutput = QDir::fromNativeSeparators(outputPath.trimmed());
    if (normalizedOutput.isEmpty())
        return QString();

    const QFileInfo outputInfo(normalizedOutput);
    QString stem = outputInfo.completeBaseName().trimmed();
    if (stem.isEmpty())
        stem = outputInfo.baseName().trimmed();
    if (stem.isEmpty())
        stem = sanitizedOutputPrefix(outputInfo.fileName(), QStringLiteral("spellvision_render"));

    const QString root = metadataRoot.trimmed().isEmpty()
                             ? outputInfo.dir().absolutePath()
                             : normalizedOutputFolder(metadataRoot);

    return QDir(root).filePath(QStringLiteral("%1.json").arg(stem));
}

void persistLatestGeneratedOutput(const QString &path)
{
    const QString normalizedPath = path.trimmed();
    if (normalizedPath.isEmpty())
        return;

    QSettings settings = spellVisionSettings();
    if (isImageAssetPath(normalizedPath))
        settings.setValue(QString::fromLatin1(LastGeneratedImageKey), normalizedPath);
    if (isVideoAssetPath(normalizedPath))
        settings.setValue(QString::fromLatin1(LastGeneratedVideoKey), normalizedPath);
    settings.sync();
}

QString latestGeneratedImageOutputPath()
{
    QSettings settings = spellVisionSettings();
    return settings.value(QString::fromLatin1(LastGeneratedImageKey)).toString().trimmed();
}

QString latestGeneratedVideoOutputPath()
{
    QSettings settings = spellVisionSettings();
    return settings.value(QString::fromLatin1(LastGeneratedVideoKey)).toString().trimmed();
}

void persistStagedI2IInputPath(const QString &path)
{
    const QString normalizedPath = path.trimmed();
    if (normalizedPath.isEmpty())
        return;

    QSettings settings = spellVisionSettings();
    settings.setValue(QString::fromLatin1(StagedI2IInputKey), normalizedPath);
    settings.sync();
}

QString stagedI2IInputPath()
{
    QSettings settings = spellVisionSettings();
    return settings.value(QString::fromLatin1(StagedI2IInputKey)).toString().trimmed();
}

} // namespace spellvision::generation
