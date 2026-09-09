#pragma once

#include <QString>
#include <QStringList>

namespace spellvision::shell
{

// Volume root ("D:/", "E:\\") -> "<volume>/AI_ASSETS/models". Empty in, empty out.
// Does not invent a drive. The caller picks the volume.
QString proposedModelsLibraryOnVolume(const QString &volumeRoot);

// Drive, AI_ASSETS, or models folder → the Comfy library (…/AI_ASSETS/models) when that
// tree exists. Empty in, empty out. Does not invent a drive or create folders.
QString resolveModelsLibraryRoot(const QString &path);

// Roots that currently exist and whose volume is ready (BitLocker locked / unplugged
// removable drives are skipped rather than emptying the whole inventory).
QStringList scannableModelsRoots(const QString &primaryRoot, const QStringList &extraRoots);

QStringList extraModelsRootsFromSettings();

QString composeManagedExtraModelPathsBlock(const QStringList &libraries);
bool writeManagedExtraModelPaths(const QString &yamlPath, const QStringList &libraries);

} // namespace spellvision::shell
