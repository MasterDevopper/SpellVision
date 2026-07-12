#pragma once

#include "CatalogPickerDialog.h"

#include <QHash>
#include <QString>
#include <QStringList>
#include <QVector>

#include <functional>

namespace spellvision::assets
{

// Detection accelerator (Qt-consumption follow-up, option A): a batch hook the
// app installs once at startup to consult the worker's ONE layered classifier
// (model_classification.classify_model) for authoritative model families. When
// installed, scanImageModelCatalog uses it instead of inferImageFamilyFromText
// (which becomes the offline fallback when the worker is unavailable). Returns
// path -> family token; an empty result means "worker unavailable, keep fallback".
using ModelFamilyClassifier = std::function<QHash<QString, QString>(const QStringList &paths)>;
void setModelFamilyClassifier(ModelFamilyClassifier classifier);

QStringList modelNameFilters();
QString compactCatalogDisplay(const QString &rootPath, const QString &absolutePath, bool addDisambiguator);
QString shortDisplayFromValue(const QString &value);
QString normalizedPathText(const QString &value);

bool looksLikeWanHighNoisePath(const QString &value);
bool looksLikeWanLowNoisePath(const QString &value);

QString inferVideoFamilyFromText(const QString &text);
QString humanVideoFamily(const QString &family);
// The canonical video-family set (wan/ltx/hunyuan_video/cogvideox/mochi). Single source for both the
// image-picker filter and send-to-generation routing (family -> t2v vs t2i).
bool isVideoFamily(const QString &family);
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
