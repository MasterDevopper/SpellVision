#pragma once

#include "CatalogPickerDialog.h"

#include <QString>
#include <QStringList>
#include <QVector>

namespace spellvision::assets
{

QStringList modelNameFilters();
QString compactCatalogDisplay(const QString &rootPath, const QString &absolutePath, bool addDisambiguator);
QString shortDisplayFromValue(const QString &value);
QString normalizedPathText(const QString &value);

bool looksLikeWanHighNoisePath(const QString &value);
bool looksLikeWanLowNoisePath(const QString &value);

QString inferVideoFamilyFromText(const QString &text);
QString humanVideoFamily(const QString &family);
QString inferImageFamilyFromText(const QString &text);
QString humanImageFamily(const QString &family);
QStringList familyNeedles(const QString &family);
bool textMatchesAnyNeedle(const QString &text, const QStringList &needles);

QVector<CatalogEntry> scanCatalog(const QString &rootPath, const QString &subDir);
QStringList scanAssetPaths(const QString &rootPath, const QStringList &subDirs);
QString findBestCompanionPath(const QStringList &paths,
                              const QString &family,
                              const QStringList &roleNeedles,
                              const QString &avoidPath = QString());

QVector<CatalogEntry> scanImageModelCatalog(const QString &rootPath);
QVector<CatalogEntry> scanDiffusersVideoFolders(const QString &rootPath);
QVector<CatalogEntry> scanVideoModelStackCatalog(const QString &rootPath);
QString resolveCatalogValueByCandidates(const QVector<CatalogEntry> &entries, const QStringList &candidates);

} // namespace spellvision::assets
