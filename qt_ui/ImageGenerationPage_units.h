#pragma once

// Shared includes + usings for ImageGenerationPage_* split TUs.

#include "generation/CockpitWidgetKit.h"
#include "generation/OutputPathHelpers.h"
#include "generation/SamplingController.h"
#include "ThemeManager.h"
#include "preview/MediaPreviewController.h"
#include "preview/ImagePreviewController.h"
#include "assets/CatalogPickerDialog.h"
#include "assets/AssetCatalogScanner.h"
#include "assets/LoraStackController.h"
#include "assets/ModelThumbnailCache.h"
#include "widgets/ClickOnlyComboBox.h"
#include "widgets/SectionCardWidgets.h"
#include "generation/CockpitInspector.h"
#include "generation/VideoReadinessPresenter.h"
#include "assets/ModelStackState.h"
#include "widgets/DropTargetFrame.h"

#include <QHBoxLayout>
#include <QDir>
#include <QDirIterator>
#include <QLayoutItem>
#include <QMessageBox>
#include <QPointer>
#include <QStackedWidget>
#include <QTimer>
#include <QToolButton>

using spellvision::assets::CatalogEntry;
using spellvision::assets::CatalogPickerDialog;
using spellvision::assets::looksLikeWanHighNoisePath;
using spellvision::assets::looksLikeWanLowNoisePath;
using spellvision::assets::normalizedPathText;
using spellvision::assets::scanCatalog;
using spellvision::assets::shortDisplayFromValue;
using spellvision::assets::inferVideoFamilyFromText;
using spellvision::assets::ModelStackState;
using spellvision::generation::comboDisplayValue;
using spellvision::generation::comboStoredValue;
using spellvision::generation::configureComboBox;
using spellvision::generation::configureDoubleSpinBox;
using spellvision::generation::configureSpinBox;
using spellvision::generation::isImageAssetPath;
using spellvision::generation::isVideoAssetPath;
using spellvision::generation::latestGeneratedImageOutputPath;
using spellvision::generation::normalizedVideoStackModeToken;
using spellvision::generation::persistLatestGeneratedOutput;
using spellvision::generation::populateComboFromCatalog;
using spellvision::generation::rgbaToken;
using spellvision::generation::selectComboByContains;
using spellvision::widgets::repolishWidget;

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

enum class LoraArch { Unknown, ImgSdxl, ImgFlux, ImgSd15, ImgSd3, VidWan, VidLtx, VidHunyuan, VidCog, VidMochi };

inline LoraArch archFromFamily(const QString &family)
{
    const QString f = family.trimmed().toLower();
    if (f == QStringLiteral("wan")) return LoraArch::VidWan;
    if (f == QStringLiteral("ltx")) return LoraArch::VidLtx;
    if (f == QStringLiteral("hunyuan_video") || f == QStringLiteral("hunyuan")) return LoraArch::VidHunyuan;
    if (f == QStringLiteral("cogvideox") || f == QStringLiteral("cogvideo")) return LoraArch::VidCog;
    if (f == QStringLiteral("mochi")) return LoraArch::VidMochi;
    if (f == QStringLiteral("sdxl") || f == QStringLiteral("pony") || f == QStringLiteral("illustrious")
        || f == QStringLiteral("noobai") || f == QStringLiteral("animagine")) return LoraArch::ImgSdxl;
    if (f == QStringLiteral("flux")) return LoraArch::ImgFlux;
    if (f == QStringLiteral("sd15") || f == QStringLiteral("sd1.5")) return LoraArch::ImgSd15;
    if (f == QStringLiteral("sd3")) return LoraArch::ImgSd3;
    return LoraArch::Unknown;
}

inline LoraArch archFromLoraText(const QString &text)
{
    const QString h = text.toLower();
    if (h.contains(QStringLiteral("wan"))) return LoraArch::VidWan;
    if (h.contains(QStringLiteral("ltx"))) return LoraArch::VidLtx;
    if (h.contains(QStringLiteral("hunyuan")) || h.contains(QStringLiteral("hyvideo"))) return LoraArch::VidHunyuan;
    if (h.contains(QStringLiteral("cogvideo"))) return LoraArch::VidCog;
    if (h.contains(QStringLiteral("mochi"))) return LoraArch::VidMochi;
    if (h.contains(QStringLiteral("flux"))) return LoraArch::ImgFlux;
    if (h.contains(QStringLiteral("pony")) || h.contains(QStringLiteral("illustri"))
        || h.contains(QStringLiteral("noobai")) || h.contains(QStringLiteral("sdxl"))) return LoraArch::ImgSdxl;
    if (h.contains(QStringLiteral("sd15")) || h.contains(QStringLiteral("sd1.5")) || h.contains(QStringLiteral("sd 1.5"))
        || h.contains(QStringLiteral("v1-5"))) return LoraArch::ImgSd15;
    if (h.contains(QStringLiteral("sd3"))) return LoraArch::ImgSd3;
    return LoraArch::Unknown;
}

inline bool isVideoArch(LoraArch a)
{
    return a == LoraArch::VidWan || a == LoraArch::VidLtx || a == LoraArch::VidHunyuan
        || a == LoraArch::VidCog || a == LoraArch::VidMochi;
}

inline bool isImageArch(LoraArch a)
{
    return a == LoraArch::ImgSdxl || a == LoraArch::ImgFlux || a == LoraArch::ImgSd15 || a == LoraArch::ImgSd3;
}

inline QString archName(LoraArch a)
{
    switch (a)
    {
    case LoraArch::ImgSdxl: return QStringLiteral("SDXL");
    case LoraArch::ImgFlux: return QStringLiteral("Flux");
    case LoraArch::ImgSd15: return QStringLiteral("SD 1.5");
    case LoraArch::ImgSd3: return QStringLiteral("SD3");
    case LoraArch::VidWan: return QStringLiteral("Wan video");
    case LoraArch::VidLtx: return QStringLiteral("LTX video");
    case LoraArch::VidHunyuan: return QStringLiteral("Hunyuan video");
    case LoraArch::VidCog: return QStringLiteral("CogVideoX");
    case LoraArch::VidMochi: return QStringLiteral("Mochi");
    default: return QStringLiteral("unknown");
    }
}

inline QString serializeLoraStack(const QVector<ImageGenerationPage::LoraStackEntry> &stack)
{
    QJsonArray array;
    for (const auto &entry : stack)
    {
        QJsonObject obj;
        obj.insert(QStringLiteral("display"), entry.display);
        obj.insert(QStringLiteral("value"), entry.value);
        obj.insert(QStringLiteral("weight"), entry.weight);
        obj.insert(QStringLiteral("enabled"), entry.enabled);
        array.append(obj);
    }
    return QString::fromUtf8(QJsonDocument(array).toJson(QJsonDocument::Compact));
}

inline QVector<ImageGenerationPage::LoraStackEntry> deserializeLoraStack(const QString &json)
{
    QVector<ImageGenerationPage::LoraStackEntry> stack;
    const QJsonDocument doc = QJsonDocument::fromJson(json.toUtf8());
    if (!doc.isArray())
        return stack;
    for (const QJsonValue &value : doc.array())
    {
        if (!value.isObject())
            continue;
        const QJsonObject obj = value.toObject();
        ImageGenerationPage::LoraStackEntry entry;
        entry.display = obj.value(QStringLiteral("display")).toString().trimmed();
        entry.value = obj.value(QStringLiteral("value")).toString().trimmed();
        entry.weight = obj.value(QStringLiteral("weight")).toDouble(1.0);
        entry.enabled = obj.value(QStringLiteral("enabled")).toBool(true);
        if (!entry.value.isEmpty())
            stack.push_back(entry);
    }
    return stack;
}

inline QString operatingPointLabel(const QJsonObject &point)
{
    QString name = point.value(QStringLiteral("name")).toString().trimmed();
    if (!name.isEmpty())
        name[0] = name[0].toUpper();
    const int steps = point.value(QStringLiteral("params")).toObject().value(QStringLiteral("steps")).toInt();
    if (steps > 0)
        return QStringLiteral("%1 (%2 steps)").arg(name).arg(steps);
    return name.isEmpty() ? QStringLiteral("Default") : name;
}

inline QString krea2OperatingPointForPath(const QString &path)
{
    const QString hay = QDir::fromNativeSeparators(path).toLower();
    if (hay.contains(QStringLiteral("turbo")))
        return QStringLiteral("turbo");
    return QStringLiteral("raw");
}


