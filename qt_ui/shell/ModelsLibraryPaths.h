#pragma once

#include <QString>
#include <QStringList>

namespace spellvision::shell
{

// Volume root ("D:/", "E:\\") -> "<volume>/AI_ASSETS/models". Empty in, empty out.
// Does not invent a drive. The caller picks the volume.
QString proposedModelsLibraryOnVolume(const QString &volumeRoot);

// Roots that currently exist and whose volume is ready (BitLocker locked / unplugged
// removable drives are skipped rather than emptying the whole inventory).
QStringList scannableModelsRoots(const QString &primaryRoot, const QStringList &extraRoots);

} // namespace spellvision::shell
