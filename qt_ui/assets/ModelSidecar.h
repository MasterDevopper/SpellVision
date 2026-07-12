#pragma once

// Model Library Arc — S0 data layer (design doc 22, §2.1 + §2.3).
// Pure, stat/parse-only helpers for resolving a model file's sidecars and reading the frozen
// metadata schema the download manager (Pass 3) must produce. Absence of a sidecar is NORMAL
// (~43% of the library has none), never an error.

#include <QString>
#include <QStringList>

namespace spellvision::assets
{

// §2.1 — resolved sidecar paths for one model file. Empty string == not present.
struct SidecarSet
{
    QString imagePath;    // .png / .jpg / .jpeg / .webp (first found, in that order)
    QString videoPath;    // .mp4
    QString metadataPath; // .metadata.json / .json / .civitai.info

    bool hasImage() const { return !imagePath.isEmpty(); }
    bool hasVideo() const { return !videoPath.isEmpty(); }
    bool hasAnyPreview() const { return hasImage() || hasVideo(); }
    bool hasMetadata() const { return !metadataPath.isEmpty(); }
};

// §2.3 — the fields SpellVision reads from a metadata sidecar. `loaded == false` means there was no
// sidecar or it could not be parsed: the consumer degrades gracefully ("local file only"), never errors.
struct ModelMetadata
{
    bool loaded = false;
    QString baseModel;         // "" or "Unknown" -> treat as absent
    QStringList tags;
    QString description;       // modelDescription (may be markdown / HTML)
    QStringList triggerWords;  // civitai.trainedWords  (CORRECTION: NOT usage_tips, which is "{}")
    QString sha256;            // identity / thumbnail-cache + overlay key / download checksum
    QString modelType;         // sidecar model_type (ADVISORY — path detectType() is the authority)
    QString modelName;
    QString previewUrl;        // remote fallback if no LOCAL preview

    bool hasBaseModel() const { return !baseModel.isEmpty() && baseModel != QStringLiteral("Unknown"); }
    bool hasRich() const { return !description.isEmpty() || !tags.isEmpty() || hasBaseModel() || !triggerWords.isEmpty(); }
};

// Pure + stat-only. Does not read file contents. `modelPath` is the model file (e.g. foo.safetensors).
SidecarSet resolveSidecars(const QString &modelPath);

// Parse the frozen schema. Returns { loaded=false } on missing / unreadable / invalid JSON.
ModelMetadata parseModelMetadata(const QString &metadataPath);

} // namespace spellvision::assets
