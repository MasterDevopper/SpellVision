#pragma once

#include <QString>

namespace spellvision::generation
{

QString chooseModelsRootPath();
QString chooseComfyOutputPath();

bool isImageAssetPath(const QString &path);
bool isVideoAssetPath(const QString &path);
bool isMediaAssetPath(const QString &path);

QString normalizedOutputFolder(const QString &folder);
QString sanitizedOutputPrefix(const QString &prefix, const QString &fallback = QStringLiteral("spellvision_render"));

QString metadataPathForOutputPath(const QString &outputPath, const QString &metadataRoot = QString());

void persistLatestGeneratedOutput(const QString &path);
QString latestGeneratedImageOutputPath();
QString latestGeneratedVideoOutputPath();

void persistStagedI2IInputPath(const QString &path);
QString stagedI2IInputPath();

} // namespace spellvision::generation
