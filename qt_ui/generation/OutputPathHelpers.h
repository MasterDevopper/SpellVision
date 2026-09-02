#pragma once

#include <QString>

namespace spellvision::generation
{

QString chooseModelsRootPath();
QString chooseComfyOutputPath();
// User dest from first-run / T2I Browse. Empty if unset or still Comfy output/.
QString userGenerationDestFolder();

bool isImageAssetPath(const QString &path);
bool isVideoAssetPath(const QString &path);
bool isMediaAssetPath(const QString &path);

// Opens a rendered output with the OS handler ONLY if its suffix is media this app produces
// (isMediaAssetPath). Anything else is revealed in its folder instead. The suffix of a downloaded
// output is taken from the ComfyUI history entry -- i.e. authored by whichever machine served the
// render -- and ShellExecute on an arbitrary suffix is one click from running it.
void openOutputAsset(const QString &path);

QString normalizedOutputFolder(const QString &folder);
QString sanitizedOutputPrefix(const QString &prefix, const QString &fallback = QStringLiteral("spellvision_render"));

QString metadataPathForOutputPath(const QString &outputPath, const QString &metadataRoot = QString());

// Hunt dest (not Comfy output/): <folder>/<prefix>/plate.png
// Default Comfy dest: <folder>/<prefix>_<task>_<stamp>.png
void resolveGenerationOutputPaths(const QString &folder,
                                  const QString &prefix,
                                  const QString &taskCommand,
                                  bool videoOutput,
                                  QString *outputPath,
                                  QString *metadataPath);

// If dest/<stem>/plate.png is missing/small, copy newest Comfy <stem>_*.png (>40KB).
bool salvageHuntPlate(const QString &destRoot, const QString &stem, const QString &comfyOutputRoot);

void persistLatestGeneratedOutput(const QString &path);
QString latestGeneratedImageOutputPath();
QString latestGeneratedVideoOutputPath();

void persistStagedI2IInputPath(const QString &path);
QString stagedI2IInputPath();

} // namespace spellvision::generation
