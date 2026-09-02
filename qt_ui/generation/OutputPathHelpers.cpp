#include "OutputPathHelpers.h"
#include "shell/RuntimeProfile.h"

#include <QDesktopServices>
#include <QDir>
#include <QUrl>
#include <QDateTime>
#include <QFile>
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

bool outputCandidateOccupied(const QString &path)
{
    return QFileInfo::exists(path) || QFileInfo::exists(metadataPathForOutputPath(path));
}

QString nextAvailableOutputPath(const QString &directory,
                                const QString &baseName,
                                const QString &extension)
{
    const QDir dir(directory);
    QString candidate = dir.filePath(baseName + extension);
    quint64 n = 2;
    while (outputCandidateOccupied(candidate))
    {
        candidate = dir.filePath(
            QStringLiteral("%1_%2%3").arg(baseName).arg(n, 2, 10, QLatin1Char('0')).arg(extension));
        ++n;
    }
    return candidate;
}
} // namespace

QString chooseModelsRootPath()
{
    const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_MODELS")).trimmed();
    if (!envPath.isEmpty() && QDir(envPath).exists())
        return QDir::fromNativeSeparators(QDir(envPath).absolutePath());

    const QString configured = spellVisionSettings().value(QStringLiteral("runtime/modelsRoot")).toString().trimmed();
    if (!configured.isEmpty() && QDir(configured).exists())
        return QDir::fromNativeSeparators(QDir(configured).absolutePath());

    return QString();
}

QString chooseComfyOutputPath()
{
    const QString configured = spellVisionSettings().value(QStringLiteral("runtime/comfyRoot")).toString().trimmed();
    const QString root = spellvision::shell::resolvePreferredComfyRoot(configured);
    if (!root.isEmpty() && QDir(root).exists())
        return QDir(QDir::fromNativeSeparators(root)).filePath(QStringLiteral("output"));
    return {};
}

QString userGenerationDestFolder()
{
    const QString dest = QDir::fromNativeSeparators(
        spellVisionSettings().value(QStringLiteral("image_generation/output_folder")).toString().trimmed());
    if (dest.isEmpty() || !QDir(dest).exists())
        return QString();
    const QString comfy = QDir::fromNativeSeparators(chooseComfyOutputPath());
    if (!comfy.isEmpty() && dest.compare(comfy, Qt::CaseInsensitive) == 0)
        return QString();
    return dest;
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

void openOutputAsset(const QString &path)
{
    const QFileInfo info(path);
    if (!info.exists())
        return;
    if (isMediaAssetPath(info.absoluteFilePath()))
    {
        QDesktopServices::openUrl(QUrl::fromLocalFile(info.absoluteFilePath()));
        return;
    }
    QDesktopServices::openUrl(QUrl::fromLocalFile(info.absolutePath()));
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

void resolveGenerationOutputPaths(const QString &folder,
                                  const QString &prefix,
                                  const QString &taskCommand,
                                  bool videoOutput,
                                  QString *outputPath,
                                  QString *metadataPath)
{
    const QString dest = normalizedOutputFolder(folder);
    const QString stem = sanitizedOutputPrefix(prefix);
    const QString ext = videoOutput ? QStringLiteral(".mp4") : QStringLiteral(".png");
    const QString comfyOut = QDir::fromNativeSeparators(chooseComfyOutputPath());
    const bool huntLayout = !dest.isEmpty() && dest.compare(comfyOut, Qt::CaseInsensitive) != 0;

    QString file;
    if (huntLayout)
    {
        const QString jobDir = QDir(dest).filePath(stem);
        QDir().mkpath(jobDir);
        file = nextAvailableOutputPath(jobDir, QStringLiteral("plate"), ext);
    }
    else
    {
        const QString stamp = QDateTime::currentDateTimeUtc().toString(QStringLiteral("yyyyMMdd_HHmmss_zzz"));
        const QString baseName = QStringLiteral("%1_%2_%3").arg(stem, taskCommand.trimmed().isEmpty() ? QStringLiteral("t2i") : taskCommand.trimmed(), stamp);
        file = nextAvailableOutputPath(dest, baseName, ext);
    }

    if (outputPath)
        *outputPath = QDir::fromNativeSeparators(file);
    if (metadataPath)
        *metadataPath = metadataPathForOutputPath(file);
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

bool salvageHuntPlate(const QString &destRoot, const QString &stem, const QString &comfyOutputRoot)
{
    const QString dest = QDir::fromNativeSeparators(destRoot.trimmed());
    const QString prefix = sanitizedOutputPrefix(stem, QString());
    const QString comfy = QDir::fromNativeSeparators(comfyOutputRoot.trimmed());
    if (dest.isEmpty() || prefix.isEmpty() || comfy.isEmpty())
        return false;

    const QDir destDir(QDir(dest).filePath(prefix));
    const QString plate = destDir.filePath(QStringLiteral("plate.png"));
    if (QFileInfo::exists(plate))
        return false;

    QDir comfyDir(comfy);
    if (!comfyDir.exists())
        return false;
    const QFileInfoList hits = comfyDir.entryInfoList({prefix + QStringLiteral("_*.png")},
                                                      QDir::Files,
                                                      QDir::Time);
    QString source;
    for (const QFileInfo &fi : hits)
    {
        if (fi.size() > 40960)
        {
            source = QDir::fromNativeSeparators(fi.absoluteFilePath());
            break;
        }
    }
    if (source.isEmpty())
        return false;
    if (!destDir.exists() && !QDir().mkpath(destDir.absolutePath()))
        return false;
    return QFile::copy(source, plate);
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
