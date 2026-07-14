#include "AssetCatalogScanner.h"

#include <QDir>
#include <QDirIterator>
#include <QFileInfo>
#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QSet>

#include <algorithm>

namespace spellvision::assets
{

namespace
{
// Installed once at app startup (MainWindow). When present, scanImageModelCatalog
// consults the worker's layered classifier instead of the inferImageFamilyFromText
// substring guess. Left null in headless/test builds -> falls back automatically.
ModelFamilyClassifier g_modelFamilyClassifier;
} // namespace

void setModelFamilyClassifier(ModelFamilyClassifier classifier)
{
    g_modelFamilyClassifier = std::move(classifier);
}

// Normalize a model filename to lowercase, space-separated tokens so ONE set of token tests
// works across every Wan naming convention: underscore (wan2.2_t2v_high_noise), camelCase
// (smoothMixWan22I2VT2V_t2vHighV20), and spaced ("Wan2.2 V3 High Noise I2V"). A camelCase
// boundary -- a LOWERCASE letter immediately followed by an UPPERCASE letter -- becomes a space;
// '_', '-', and existing whitespace collapse to single spaces. (Digit->uppercase is deliberately
// NOT a boundary: it would shred "I2V" into "i2 v" and break task-marker adjacency.) The result
// is padded with a leading + trailing space so whole-word tests (" high ") also catch the first
// and last token. Operates on the base filename only -- folder names never contribute a signal.
QString normalizedExpertText(const QString &value)
{
    const QString base = QFileInfo(QDir::fromNativeSeparators(value)).completeBaseName();
    QString out;
    out.reserve(base.size() + 8);
    for (int i = 0; i < base.size(); ++i)
    {
        const QChar c = base.at(i);
        if (c == QLatin1Char('_') || c == QLatin1Char('-') || c.isSpace())
        {
            out += QLatin1Char(' ');
            continue;
        }
        if (c.isUpper() && i > 0 && base.at(i - 1).isLower())
            out += QLatin1Char(' ');
        out += c.toLower();
    }
    return QStringLiteral(" ") + out.simplified() + QStringLiteral(" ");
}

// The Lightx2v 4-step acceleration LoRAs carry "high_noise"/"low_noise" tokens but are NOT
// dual-noise experts. Exclude anything with an explicit LoRA / accel marker so the detector can
// never mis-pair one as an expert -- belt-and-suspenders on top of the scan scope, which already
// reads diffusion_models/unet/checkpoints and NOT loras/.
bool looksLikeAccelOrLoraName(const QString &normalized)
{
    return normalized.contains(QStringLiteral(" lora ")) ||
           normalized.contains(QStringLiteral("lightx2v")) ||
           normalized.contains(QStringLiteral("4step"));
}

// A Wan dual-noise HIGH expert: Wan-family context (from the filename) + a *noise-ish* high
// signal, and NOT an accel LoRA. "noise-ish" is deliberately conservative -- the high token must
// sit next to "noise", follow a task marker (t2v/i2v), or be the trailing word -- so "highres",
// "highway", or a mid-name "high quality" never trip it. A false positive silently mis-pairs a
// render; a false negative just means the user pairs manually, so when in doubt: don't detect.
bool looksLikeWanHighNoisePath(const QString &value)
{
    const QString n = normalizedExpertText(value);
    if (!n.contains(QStringLiteral(" wan")) || looksLikeAccelOrLoraName(n))
        return false;
    return n.contains(QStringLiteral(" high noise ")) ||
           n.contains(QStringLiteral(" noise high ")) ||
           n.contains(QStringLiteral(" t2v high ")) ||
           n.contains(QStringLiteral(" i2v high ")) ||
           n.endsWith(QStringLiteral(" high "));
}

bool looksLikeWanLowNoisePath(const QString &value)
{
    const QString n = normalizedExpertText(value);
    if (!n.contains(QStringLiteral(" wan")) || looksLikeAccelOrLoraName(n))
        return false;
    return n.contains(QStringLiteral(" low noise ")) ||
           n.contains(QStringLiteral(" noise low ")) ||
           n.contains(QStringLiteral(" t2v low ")) ||
           n.contains(QStringLiteral(" i2v low ")) ||
           n.endsWith(QStringLiteral(" low "));
}

// The "expert signature": the normalized name with the high<->low marker neutralized to a
// sentinel, so the two halves of a genuine pair collapse to ONE signature while everything that
// must match (task t2v/i2v, version, size, precision, and the model name itself) is preserved.
// It operates on the SAME normalized token stream as detection, so it pairs correctly across all
// three naming conventions -- smoothMixWan22I2VT2V_t2vHighV20 pairs with ..._t2vLowV20, and never
// with dasiwaWAN22I2V14B_midnightflirtHigh (different model name -> different signature). Two
// experts form a valid pair iff they are opposite halves AND share this signature.
QString wanExpertSignature(const QString &value)
{
    QString n = normalizedExpertText(value);
    n.replace(QStringLiteral(" high "), QStringLiteral(" # "));
    n.replace(QStringLiteral(" low "), QStringLiteral(" # "));
    return n;
}

QString compactCatalogDisplay(const QString &rootPath, const QString &absolutePath, bool addDisambiguator)
{
    Q_UNUSED(rootPath);

    const QFileInfo info(absolutePath);
    const QString baseName = info.completeBaseName().trimmed().isEmpty()
                                 ? info.fileName()
                                 : info.completeBaseName().trimmed();

    if (!addDisambiguator)
        return baseName;

    const QString parentName = info.dir().dirName().trimmed();
    if (parentName.isEmpty())
        return baseName;

    return QStringLiteral("%1 • %2").arg(baseName, parentName);
}

QString shortDisplayFromValue(const QString &value)
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return QStringLiteral("none");

    const QFileInfo info(trimmed);
    if (info.exists())
    {
        const QString baseName = info.completeBaseName().trimmed();
        if (!baseName.isEmpty())
            return baseName;
    }

    if (!trimmed.contains(QChar('/')) && !trimmed.contains(QChar('\\')))
        return trimmed;

    const QFileInfo pathInfo(trimmed);
    return pathInfo.completeBaseName().trimmed().isEmpty() ? pathInfo.fileName() : pathInfo.completeBaseName().trimmed();
}

QStringList modelNameFilters()
{
    return {
        QStringLiteral("*.safetensors"),
        QStringLiteral("*.ckpt"),
        QStringLiteral("*.pt"),
        QStringLiteral("*.pth"),
        QStringLiteral("*.bin"),
        QStringLiteral("*.gguf")};
}

QVector<CatalogEntry> scanCatalog(const QString &rootPath, const QString &subDir)
{
    QVector<CatalogEntry> entries;
    if (rootPath.trimmed().isEmpty())
        return entries;

    const QString targetDir = QDir(rootPath).filePath(subDir);
    if (!QDir(targetDir).exists())
        return entries;

    QStringList absolutePaths;
    QHash<QString, int> baseNameCounts;

    QDirIterator it(targetDir, modelNameFilters(), QDir::Files, QDirIterator::Subdirectories);

    while (it.hasNext())
    {
        const QString absolutePath = QDir::fromNativeSeparators(it.next());
        absolutePaths.push_back(absolutePath);

        const QFileInfo info(absolutePath);
        const QString baseKey = info.completeBaseName().trimmed().toLower();
        baseNameCounts[baseKey] += 1;
    }

    for (const QString &absolutePath : absolutePaths)
    {
        const QFileInfo info(absolutePath);
        const QString baseKey = info.completeBaseName().trimmed().toLower();
        const bool needsDisambiguator = baseNameCounts.value(baseKey) > 1;
        entries.push_back({compactCatalogDisplay(rootPath, absolutePath, needsDisambiguator), absolutePath});
    }

    std::sort(entries.begin(), entries.end(), [](const CatalogEntry &lhs, const CatalogEntry &rhs) {
        return QString::compare(lhs.display, rhs.display, Qt::CaseInsensitive) < 0;
    });

    return entries;
}

QString normalizedPathText(const QString &value)
{
    return QDir::fromNativeSeparators(value).toLower();
}

QString inferVideoFamilyFromText(const QString &text)
{
    const QString haystack = normalizedPathText(text);
    if (haystack.contains(QStringLiteral("wan")) || haystack.contains(QStringLiteral("wan2")))
        return QStringLiteral("wan");
    if (haystack.contains(QStringLiteral("ltx")) || haystack.contains(QStringLiteral("ltxv")))
        return QStringLiteral("ltx");
    if (haystack.contains(QStringLiteral("hunyuan")) || haystack.contains(QStringLiteral("hyvideo")))
        return QStringLiteral("hunyuan_video");
    if (haystack.contains(QStringLiteral("cogvideo")) || haystack.contains(QStringLiteral("cogvideox")))
        return QStringLiteral("cogvideox");
    if (haystack.contains(QStringLiteral("mochi")))
        return QStringLiteral("mochi");
    if (haystack.contains(QStringLiteral("animatediff")) || haystack.contains(QStringLiteral("animate_diff")))
        return QStringLiteral("animatediff");
    if (haystack.contains(QStringLiteral("svd")) || haystack.contains(QStringLiteral("stable-video")))
        return QStringLiteral("svd");
    return QStringLiteral("video");
}

QString humanVideoFamily(const QString &family)
{
    const QString key = family.trimmed().toLower();
    if (key == QStringLiteral("wan"))
        return QStringLiteral("WAN");
    if (key == QStringLiteral("ltx"))
        return QStringLiteral("LTX Video");
    if (key == QStringLiteral("hunyuan_video"))
        return QStringLiteral("Hunyuan Video");
    if (key == QStringLiteral("cogvideox"))
        return QStringLiteral("CogVideoX");
    if (key == QStringLiteral("mochi"))
        return QStringLiteral("Mochi");
    if (key == QStringLiteral("animatediff"))
        return QStringLiteral("AnimateDiff");
    if (key == QStringLiteral("svd"))
        return QStringLiteral("SVD");
    return QStringLiteral("Video");
}

bool isVideoFamily(const QString &family)
{
    static const QStringList kVideoFamilies = {
        QStringLiteral("wan"), QStringLiteral("ltx"), QStringLiteral("hunyuan_video"),
        QStringLiteral("cogvideox"), QStringLiteral("mochi")};
    return kVideoFamilies.contains(family.trimmed().toLower());
}

// OFFLINE FALLBACK ONLY. When the worker classifier is installed (the normal
// case), scanImageModelCatalog overrides this with the authoritative family from
// model_classification.classify_model. This substring guess is used only when the
// worker is unavailable (e.g. standalone/headless, or the backend is down).
QString inferImageFamilyFromText(const QString &text)
{
    const QString haystack = normalizedPathText(text);
    if (haystack.contains(QStringLiteral("pony")))
        return QStringLiteral("pony");
    if (haystack.contains(QStringLiteral("illustri")))
        return QStringLiteral("illustrious");
    if (haystack.contains(QStringLiteral("flux")))
        return QStringLiteral("flux");
    if (haystack.contains(QStringLiteral("z-image")) || haystack.contains(QStringLiteral("zimage")))
        return QStringLiteral("z_image");
    if (haystack.contains(QStringLiteral("qwen")))
        return QStringLiteral("qwen_image");
    if (haystack.contains(QStringLiteral("sdxl")) || haystack.contains(QStringLiteral("xl")))
        return QStringLiteral("sdxl");
    if (haystack.contains(QStringLiteral("sd15")) || haystack.contains(QStringLiteral("sd1.5")))
        return QStringLiteral("sd15");
    return QStringLiteral("image");
}

QString humanImageFamily(const QString &family)
{
    const QString key = family.trimmed().toLower();
    if (key == QStringLiteral("pony"))
        return QStringLiteral("Pony");
    if (key == QStringLiteral("illustrious"))
        return QStringLiteral("Illustrious");
    if (key == QStringLiteral("flux"))
        return QStringLiteral("Flux");
    if (key == QStringLiteral("z_image"))
        return QStringLiteral("Z-Image");
    if (key == QStringLiteral("qwen_image"))
        return QStringLiteral("Qwen Image");
    if (key == QStringLiteral("sdxl"))
        return QStringLiteral("SDXL / XL");
    if (key == QStringLiteral("sd15") || key == QStringLiteral("stable_diffusion"))
        return QStringLiteral("SD 1.5");
    if (key == QStringLiteral("sd3"))
        return QStringLiteral("SD 3");
    return QStringLiteral("Image");
}

QStringList familyNeedles(const QString &family)
{
    const QString key = family.trimmed().toLower();
    if (key == QStringLiteral("wan"))
        return {QStringLiteral("wan"), QStringLiteral("wan2")};
    if (key == QStringLiteral("ltx"))
        return {QStringLiteral("ltx"), QStringLiteral("ltxv")};
    if (key == QStringLiteral("hunyuan_video"))
        return {QStringLiteral("hunyuan"), QStringLiteral("hyvideo")};
    if (key == QStringLiteral("cogvideox"))
        return {QStringLiteral("cogvideo"), QStringLiteral("cogvideox")};
    if (key == QStringLiteral("mochi"))
        return {QStringLiteral("mochi")};
    if (key == QStringLiteral("animatediff"))
        return {QStringLiteral("animatediff"), QStringLiteral("animate_diff")};
    if (key == QStringLiteral("svd"))
        return {QStringLiteral("svd"), QStringLiteral("stable-video")};
    return {};
}

bool textMatchesAnyNeedle(const QString &text, const QStringList &needles)
{
    if (needles.isEmpty())
        return true;
    const QString haystack = normalizedPathText(text);
    for (const QString &needle : needles)
    {
        const QString n = needle.trimmed().toLower();
        if (!n.isEmpty() && haystack.contains(n))
            return true;
    }
    return false;
}

QStringList scanAssetPaths(const QString &rootPath, const QStringList &subDirs)
{
    QStringList paths;
    for (const QString &subDir : subDirs)
    {
        const QString targetDir = QDir(rootPath).filePath(subDir);
        if (!QDir(targetDir).exists())
            continue;
        QDirIterator it(targetDir, modelNameFilters(), QDir::Files, QDirIterator::Subdirectories);
        while (it.hasNext())
            paths << QDir::fromNativeSeparators(it.next());
    }
    paths.removeDuplicates();
    paths.sort(Qt::CaseInsensitive);
    return paths;
}

QString findBestCompanionPath(const QStringList &paths,
                              const QString &family,
                              const QStringList &roleNeedles,
                              const QString &avoidPath)
{
    const QStringList famNeedles = familyNeedles(family);
    QString fallback;
    for (const QString &path : paths)
    {
        if (!avoidPath.isEmpty() && path.compare(avoidPath, Qt::CaseInsensitive) == 0)
            continue;
        const QString haystack = normalizedPathText(path);
        bool roleMatch = false;
        for (const QString &roleNeedle : roleNeedles)
        {
            const QString n = roleNeedle.trimmed().toLower();
            if (!n.isEmpty() && haystack.contains(n))
            {
                roleMatch = true;
                break;
            }
        }
        if (!roleMatch)
            continue;
        if (textMatchesAnyNeedle(path, famNeedles))
            return path;
        if (fallback.isEmpty())
            fallback = path;
    }
    return fallback;
}

QVector<CatalogEntry> scanImageModelCatalog(const QString &rootPath)
{
    QVector<CatalogEntry> entries = scanCatalog(rootPath, QStringLiteral("checkpoints"));

    // Split-stack image families (Z-Image, ...) ship their transformer in diffusion_models/ and load
    // via UNETLoader, not CheckpointLoaderSimple -- so include that tree too. It ALSO holds the video
    // transformers (wan/ltx/hunyuan), which are dropped below by classified family so only image
    // models surface in the image picker.
    entries += scanCatalog(rootPath, QStringLiteral("diffusion_models"));

    // 1) Fallback family per entry (used as-is only when the worker classifier
    //    is unavailable).
    for (CatalogEntry &entry : entries)
    {
        entry.family = inferImageFamilyFromText(entry.value + QStringLiteral(" ") + entry.display);
        entry.modality = QStringLiteral("image");
        entry.role = QStringLiteral("checkpoint");
    }

    // 2) Authoritative override: consult the ONE worker classifier in a single
    //    batch. Empty result (worker down) => keep the fallback families above.
    if (g_modelFamilyClassifier && !entries.isEmpty())
    {
        QStringList paths;
        paths.reserve(entries.size());
        for (const CatalogEntry &entry : entries)
            paths << entry.value;
        const QHash<QString, QString> byPath = g_modelFamilyClassifier(paths);
        for (CatalogEntry &entry : entries)
        {
            const auto it = byPath.constFind(entry.value);
            if (it != byPath.constEnd() && !it.value().isEmpty())
                entry.family = it.value();
        }
    }

    // 2b) Drop VIDEO transformers pulled in from diffusion_models/ -- they must not appear in the
    //     IMAGE picker. Keyed on the classified family via isVideoFamily() (the single canonical set);
    //     image families and unknowns are kept. checkpoints/ entries are image, so this is a no-op.
    QVector<CatalogEntry> imageOnly;
    imageOnly.reserve(entries.size());
    for (const CatalogEntry &entry : entries)
    {
        if (!isVideoFamily(entry.family))
            imageOnly.push_back(entry);
    }
    entries = imageOnly;

    // 3) Derive note + metadata from the (possibly overridden) family, so the
    //    picker label and the family Qt SENDS both trace to the one classifier.
    for (CatalogEntry &entry : entries)
    {
        entry.note = humanImageFamily(entry.family);
        QJsonObject metadata;
        metadata.insert(QStringLiteral("family"), entry.family);
        metadata.insert(QStringLiteral("modality"), QStringLiteral("image"));
        metadata.insert(QStringLiteral("role"), QStringLiteral("checkpoint"));
        metadata.insert(QStringLiteral("path"), entry.value);
        entry.metadata = metadata;
    }
    return entries;
}

QVector<CatalogEntry> scanDiffusersVideoFolders(const QString &rootPath)
{
    QVector<CatalogEntry> entries;
    if (rootPath.trimmed().isEmpty() || !QDir(rootPath).exists())
        return entries;

    const QStringList searchRoots = {
        QString(),
        QStringLiteral("diffusers"),
        QStringLiteral("video"),
        QStringLiteral("wan"),
        QStringLiteral("ltx"),
        QStringLiteral("hunyuan_video"),
        QStringLiteral("cogvideox"),
        QStringLiteral("mochi")};

    QStringList dirs;
    for (const QString &subDir : searchRoots)
    {
        const QString target = subDir.isEmpty() ? rootPath : QDir(rootPath).filePath(subDir);
        if (!QDir(target).exists())
            continue;
        if (QFileInfo::exists(QDir(target).filePath(QStringLiteral("model_index.json"))))
            dirs << QDir::fromNativeSeparators(QDir(target).absolutePath());
        if (subDir.isEmpty())
            continue;

        QDirIterator it(target, QDir::Dirs | QDir::NoDotAndDotDot, QDirIterator::Subdirectories);
        while (it.hasNext())
        {
            const QString dirPath = QDir::fromNativeSeparators(it.next());
            if (QFileInfo::exists(QDir(dirPath).filePath(QStringLiteral("model_index.json"))))
                dirs << dirPath;
        }
    }
    dirs.removeDuplicates();

    for (const QString &dirPath : dirs)
    {
        const QString family = inferVideoFamilyFromText(dirPath);
        const QString display = QStringLiteral("%1 • %2 Diffusers folder").arg(QFileInfo(dirPath).fileName(), humanVideoFamily(family));
        QJsonObject metadata;
        metadata.insert(QStringLiteral("family"), family);
        metadata.insert(QStringLiteral("modality"), QStringLiteral("video"));
        metadata.insert(QStringLiteral("role"), QStringLiteral("diffusers_folder"));
        metadata.insert(QStringLiteral("stack_kind"), QStringLiteral("diffusers_folder"));
        metadata.insert(QStringLiteral("primary_path"), dirPath);
        metadata.insert(QStringLiteral("diffusers_path"), dirPath);
        metadata.insert(QStringLiteral("stack_ready"), true);
        entries.push_back({display, dirPath, family, QStringLiteral("video"), QStringLiteral("diffusers folder"), QStringLiteral("Native-ready Diffusers model folder"), metadata});
    }
    return entries;
}

QVector<CatalogEntry> scanVideoModelStackCatalog(const QString &rootPath)
{
    QVector<CatalogEntry> entries = scanDiffusersVideoFolders(rootPath);
    if (rootPath.trimmed().isEmpty() || !QDir(rootPath).exists())
        return entries;

    const QStringList primaryDirs = {
        QStringLiteral("diffusion_models"),
        QStringLiteral("unet"),
        QStringLiteral("video"),
        QStringLiteral("wan"),
        QStringLiteral("ltx"),
        QStringLiteral("hunyuan_video"),
        QStringLiteral("cogvideox"),
        QStringLiteral("mochi"),
        QStringLiteral("checkpoints")};
    const QStringList companionDirs = {
        QStringLiteral("vae"),
        QStringLiteral("vae_approx"),
        QStringLiteral("text_encoders"),
        QStringLiteral("clip"),
        QStringLiteral("clip_vision"),
        QStringLiteral("encoders"),
        QStringLiteral("diffusion_models"),
        QStringLiteral("unet")};

    const QStringList primaryPaths = scanAssetPaths(rootPath, primaryDirs);
    const QStringList companionPaths = scanAssetPaths(rootPath, companionDirs);
    QSet<QString> seenValues;
    for (const CatalogEntry &entry : entries)
        seenValues.insert(entry.value.toLower());

    for (const QString &primaryPath : primaryPaths)
    {
        const QString haystack = normalizedPathText(primaryPath);
        const bool looksVideo = haystack.contains(QStringLiteral("wan")) ||
                                haystack.contains(QStringLiteral("ltx")) ||
                                haystack.contains(QStringLiteral("hunyuan")) ||
                                haystack.contains(QStringLiteral("hyvideo")) ||
                                haystack.contains(QStringLiteral("cogvideo")) ||
                                haystack.contains(QStringLiteral("mochi")) ||
                                haystack.contains(QStringLiteral("animatediff")) ||
                                haystack.contains(QStringLiteral("svd")) ||
                                haystack.contains(QStringLiteral("video"));
        if (!looksVideo)
            continue;
        if (seenValues.contains(primaryPath.toLower()))
            continue;
        seenValues.insert(primaryPath.toLower());

        const QString family = inferVideoFamilyFromText(primaryPath);
        const QString vaePath = findBestCompanionPath(companionPaths, family, {QStringLiteral("vae")}, primaryPath);
        const QString textEncoderPath = findBestCompanionPath(companionPaths, family, {QStringLiteral("text_encoder"), QStringLiteral("text-encoder"), QStringLiteral("t5"), QStringLiteral("umt5"), QStringLiteral("clip_l")}, primaryPath);
        const QString textEncoder2Path = findBestCompanionPath(companionPaths, family, {QStringLiteral("text_encoder_2"), QStringLiteral("clip_g"), QStringLiteral("llm")}, textEncoderPath);
        const QString clipVisionPath = findBestCompanionPath(companionPaths, family, {QStringLiteral("clip_vision"), QStringLiteral("clipvision"), QStringLiteral("image_encoder")}, primaryPath);

        QString highNoisePath;
        QString lowNoisePath;
        if (family == QStringLiteral("wan"))
        {
            // Signature-matched dual-noise pairing. Anchor on the selected primary's half and find the
            // OPPOSITE half whose expert signature matches -- so a t2v_high only ever pairs with a
            // t2v_low, a 2.2 with a 2.2, an fp8 with an fp8, regardless of scan order or which other
            // experts sit on disk. The old code grabbed the first low-noise file it saw, so t2v_high
            // wrongly paired with i2v_low. No signature-matching partner -> left empty (reported missing
            // below) rather than mis-paired with an unrelated expert.
            const QStringList expertCandidates = primaryPaths + companionPaths;
            auto findSignaturePartner = [&](const QString &anchorPath, bool wantHigh) -> QString {
                const QString anchorSignature = wanExpertSignature(anchorPath);
                for (const QString &candidatePath : expertCandidates)
                {
                    if (candidatePath.compare(anchorPath, Qt::CaseInsensitive) == 0)
                        continue;
                    if (!normalizedPathText(candidatePath).contains(QStringLiteral("wan")))
                        continue;
                    if (wantHigh && !looksLikeWanHighNoisePath(candidatePath))
                        continue;
                    if (!wantHigh && !looksLikeWanLowNoisePath(candidatePath))
                        continue;
                    if (wanExpertSignature(candidatePath) == anchorSignature)
                        return candidatePath;
                }
                return QString();
            };

            if (looksLikeWanHighNoisePath(primaryPath))
            {
                highNoisePath = primaryPath;
                lowNoisePath = findSignaturePartner(primaryPath, /*wantHigh=*/false);
            }
            else if (looksLikeWanLowNoisePath(primaryPath))
            {
                lowNoisePath = primaryPath;
                highNoisePath = findSignaturePartner(primaryPath, /*wantHigh=*/true);
            }
            // else: a single-model Wan (e.g. 2.1) primary -> not a dual-noise stack; both halves stay
            // empty and wanDualNoise resolves false below.
        }

        const bool wanDualNoise = family == QStringLiteral("wan") && (!highNoisePath.isEmpty() || !lowNoisePath.isEmpty());

        QStringList parts;
        if (wanDualNoise)
        {
            parts << QStringLiteral("high noise");
            parts << QStringLiteral("low noise");
        }
        else
        {
            parts << QStringLiteral("model");
        }
        if (!textEncoderPath.isEmpty())
            parts << QStringLiteral("text");
        if (!vaePath.isEmpty())
            parts << QStringLiteral("vae");
        if (!clipVisionPath.isEmpty())
            parts << QStringLiteral("vision");

        QStringList missing;
        if (wanDualNoise)
        {
            if (highNoisePath.isEmpty())
                missing << QStringLiteral("high noise");
            if (lowNoisePath.isEmpty())
                missing << QStringLiteral("low noise");
        }
        if (textEncoderPath.isEmpty())
            missing << QStringLiteral("text encoder");
        if (vaePath.isEmpty())
            missing << QStringLiteral("vae");

        QJsonObject metadata;
        metadata.insert(QStringLiteral("family"), family);
        metadata.insert(QStringLiteral("modality"), QStringLiteral("video"));
        metadata.insert(QStringLiteral("role"), QStringLiteral("split_stack"));
        metadata.insert(QStringLiteral("stack_kind"), wanDualNoise ? QStringLiteral("wan_dual_noise") : QStringLiteral("split_stack"));
        metadata.insert(QStringLiteral("stack_mode"), wanDualNoise ? QStringLiteral("wan_dual_noise") : QStringLiteral("auto"));
        metadata.insert(QStringLiteral("primary_path"), primaryPath);
        metadata.insert(QStringLiteral("transformer_path"), primaryPath);
        metadata.insert(QStringLiteral("unet_path"), primaryPath);
        metadata.insert(QStringLiteral("vae_path"), vaePath);
        metadata.insert(QStringLiteral("text_encoder_path"), textEncoderPath);
        metadata.insert(QStringLiteral("text_encoder_2_path"), textEncoder2Path);
        metadata.insert(QStringLiteral("clip_vision_path"), clipVisionPath);
        if (wanDualNoise)
        {
            metadata.insert(QStringLiteral("high_noise_path"), highNoisePath);
            metadata.insert(QStringLiteral("high_noise_model_path"), highNoisePath);
            metadata.insert(QStringLiteral("wan_high_noise_path"), highNoisePath);
            metadata.insert(QStringLiteral("low_noise_path"), lowNoisePath);
            metadata.insert(QStringLiteral("low_noise_model_path"), lowNoisePath);
            metadata.insert(QStringLiteral("wan_low_noise_path"), lowNoisePath);
        }
        metadata.insert(QStringLiteral("stack_ready"), missing.isEmpty());
        QJsonArray missingArray;
        for (const QString &item : missing)
            missingArray.append(item);
        metadata.insert(QStringLiteral("missing_parts"), missingArray);

        const QString base = QFileInfo(primaryPath).completeBaseName();
        const QString readiness = missing.isEmpty() ? QStringLiteral("resolved") : QStringLiteral("partial");
        const QString display = QStringLiteral("%1 • %2 stack • %3").arg(base, humanVideoFamily(family), readiness);
        const QString note = missing.isEmpty()
                                 ? QStringLiteral("Resolved %1 video stack: %2").arg(wanDualNoise ? QStringLiteral("WAN dual-noise") : QStringLiteral("split"), parts.join(QStringLiteral(" + ")))
                                 : QStringLiteral("Partial %1 stack; missing %2").arg(wanDualNoise ? QStringLiteral("WAN dual-noise") : QStringLiteral("video"), missing.join(QStringLiteral(", ")));
        entries.push_back({display, primaryPath, family, QStringLiteral("video"), QStringLiteral("model stack"), note, metadata});
    }

    std::sort(entries.begin(), entries.end(), [](const CatalogEntry &lhs, const CatalogEntry &rhs) {
        if (lhs.metadata.value(QStringLiteral("stack_ready")).toBool(false) != rhs.metadata.value(QStringLiteral("stack_ready")).toBool(false))
            return lhs.metadata.value(QStringLiteral("stack_ready")).toBool(false);
        if (lhs.metadata.value(QStringLiteral("stack_kind")).toString() != rhs.metadata.value(QStringLiteral("stack_kind")).toString())
            return lhs.metadata.value(QStringLiteral("stack_kind")).toString() < rhs.metadata.value(QStringLiteral("stack_kind")).toString();
        return QString::compare(lhs.display, rhs.display, Qt::CaseInsensitive) < 0;
    });

    return entries;
}

QString resolveCatalogValueByCandidates(const QVector<CatalogEntry> &entries, const QStringList &candidates)
{
    for (const QString &candidate : candidates)
    {
        const QString trimmed = candidate.trimmed();
        if (trimmed.isEmpty())
            continue;

        for (const CatalogEntry &entry : entries)
        {
            if (entry.value.compare(trimmed, Qt::CaseInsensitive) == 0 ||
                entry.display.compare(trimmed, Qt::CaseInsensitive) == 0)
            {
                return entry.value;
            }
        }
    }

    for (const QString &candidate : candidates)
    {
        const QString needle = candidate.trimmed().toLower();
        if (needle.isEmpty())
            continue;

        for (const CatalogEntry &entry : entries)
        {
            const QString haystack = QStringLiteral("%1 %2 %3")
                                         .arg(entry.display, entry.value, shortDisplayFromValue(entry.value))
                                         .toLower();
            if (haystack.contains(needle))
                return entry.value;
        }
    }

    return QString();
}

} // namespace spellvision::assets
