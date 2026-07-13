#include "ModelManagerPage.h"
#include "ThemeManager.h"
#include "assets/ModelSidecar.h"
#include "assets/ModelThumbnailCache.h"
#include "assets/ModelOverlayStore.h"
#include "assets/ModelCardModel.h"
#include "assets/ModelCardDelegate.h"
#include "assets/ModelCardView.h"

#include <QClipboard>
#include <QDebug>
#include <QGuiApplication>
#include <QItemSelectionModel>
#include <QPixmapCache>
#include <QRegularExpression>
#include <QStackedWidget>

#include <QDesktopServices>
#include <QDateTime>
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QAbstractItemView>
#include <QFrame>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QSaveFile>
#include <QStandardPaths>
#include <QTreeWidget>
#include <QTreeWidgetItem>
#include <QUrl>
#include <QtConcurrent>

#include <algorithm>
#include <QVBoxLayout>

namespace
{
// Derive the model family from the metadata base_model — far more reliable than the path heuristic,
// which misses e.g. a Wan LoRA sitting flat in loras/ (only "/wan" path segments matched). This also
// gives the image sub-families (SDXL / Pony / Illustrious / Flux) the distinction they need so a video
// LoRA never crosses into image generation and vice-versa. Empty -> caller keeps the path heuristic.
QString familyFromBaseModel(const QString &baseModel)
{
    const QString b = baseModel.trimmed().toLower();
    if (b.isEmpty() || b == QStringLiteral("unknown"))
        return QString();

    // Video families (route to T2V).
    if (b.contains(QStringLiteral("wan"))) return QStringLiteral("wan");
    if (b.contains(QStringLiteral("ltx"))) return QStringLiteral("ltx");
    if (b.contains(QStringLiteral("hunyuan"))) return QStringLiteral("hunyuan_video");
    if (b.contains(QStringLiteral("cogvideo"))) return QStringLiteral("cogvideox");
    if (b.contains(QStringLiteral("mochi"))) return QStringLiteral("mochi");

    // Image families (route to T2I) — distinguished from each other for compatibility.
    if (b.contains(QStringLiteral("pony"))) return QStringLiteral("pony");
    if (b.contains(QStringLiteral("illustrious"))) return QStringLiteral("illustrious");
    if (b.contains(QStringLiteral("noobai")) || b.contains(QStringLiteral("noob"))) return QStringLiteral("noobai");
    if (b.contains(QStringLiteral("flux"))) return QStringLiteral("flux");
    if (b.contains(QStringLiteral("sd3")) || b.contains(QStringLiteral("sd 3")) || b.contains(QStringLiteral("stable diffusion 3")))
        return QStringLiteral("sd3");
    if (b.contains(QStringLiteral("sdxl")) || b.contains(QStringLiteral("sd xl")) || b.contains(QStringLiteral("xl")))
        return QStringLiteral("sdxl");
    if (b.contains(QStringLiteral("sd 1.5")) || b.contains(QStringLiteral("sd1.5")) || b.contains(QStringLiteral("1.5")))
        return QStringLiteral("sd15");
    return QString();
}

QString humanSize(qint64 bytes)
{
    const double b = static_cast<double>(bytes);
    if (b >= 1024.0 * 1024.0 * 1024.0)
        return QStringLiteral("%1 GB").arg(b / (1024.0 * 1024.0 * 1024.0), 0, 'f', 2);
    if (b >= 1024.0 * 1024.0)
        return QStringLiteral("%1 MB").arg(b / (1024.0 * 1024.0), 0, 'f', 1);
    if (b >= 1024.0)
        return QStringLiteral("%1 KB").arg(b / 1024.0, 0, 'f', 1);
    return QStringLiteral("%1 B").arg(bytes);
}

bool isModelFile(const QString &suffix)
{
    const QString s = suffix.trimmed().toLower();
    return s == QStringLiteral("safetensors")
        || s == QStringLiteral("ckpt")
        || s == QStringLiteral("bin")
        || s == QStringLiteral("pt")
        || s == QStringLiteral("pth")
        || s == QStringLiteral("gguf")
        || s == QStringLiteral("onnx");
}
}

ModelManagerPage::ModelManagerPage(QWidget *parent)
    : QWidget(parent)
{
    buildUi();

    refreshWatcher_ = new QFutureWatcher<RefreshResult>(this);
    connect(refreshWatcher_, &QFutureWatcher<RefreshResult>::finished, this, &ModelManagerPage::onRefreshFinished);

    // Re-apply the token/typography stylesheet when the theme switches (colors are per-preset).
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &ModelManagerPage::applyThemeStyling);
}

void ModelManagerPage::setProjectRoot(const QString &projectRoot)
{
    projectRoot_ = projectRoot;
}

void ModelManagerPage::setModelsRoot(const QString &modelsRoot)
{
    explicitModelsRoot_ = modelsRoot;
}

QString ModelManagerPage::resolveModelsRoot() const
{
    if (!explicitModelsRoot_.trimmed().isEmpty())
        return explicitModelsRoot_;

    const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_MODELS")).trimmed();
    if (!envPath.isEmpty())
        return QDir::fromNativeSeparators(QDir(envPath).absolutePath());

    const QString preferred = QStringLiteral("D:/AI_ASSETS/models");
    if (QDir(preferred).exists())
        return preferred;

    if (!projectRoot_.trimmed().isEmpty())
        return QDir(projectRoot_).filePath(QStringLiteral("external_assets/models"));

    return QDir::current().filePath(QStringLiteral("external_assets/models"));
}

QString ModelManagerPage::resolveDownloadsRoot() const
{
    const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_ASSET_CACHE")).trimmed();
    if (!envPath.isEmpty())
        return QDir::fromNativeSeparators(QDir(envPath).absolutePath());

    if (!projectRoot_.trimmed().isEmpty())
    {
        const QString runtimeCache = QDir(projectRoot_).filePath(QStringLiteral("runtime/cache/assets"));
        if (QDir(runtimeCache).exists())
            return runtimeCache;

        const QString pyCache = QDir(projectRoot_).filePath(QStringLiteral("python/.cache/assets"));
        if (QDir(pyCache).exists())
            return pyCache;
    }

    return QString();
}

QString ModelManagerPage::cacheFilePath() const
{
    QString base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    if (base.trimmed().isEmpty())
    {
        if (!projectRoot_.trimmed().isEmpty())
            base = QDir(projectRoot_).filePath(QStringLiteral("runtime/cache/ui"));
        else
            base = QDir::current().filePath(QStringLiteral("runtime/cache/ui"));
    }

    QDir dir(base);
    dir.mkpath(QStringLiteral("."));
    return dir.filePath(QStringLiteral("model_inventory_cache.json"));
}

QJsonObject ModelManagerPage::entryToJson(const ModelEntry &entry)
{
    return QJsonObject{
        {QStringLiteral("name"), entry.name},
        {QStringLiteral("type"), entry.type},
        {QStringLiteral("family"), entry.family},
        {QStringLiteral("sizeText"), entry.sizeText},
        {QStringLiteral("status"), entry.status},
        {QStringLiteral("path"), entry.path},
        {QStringLiteral("imagePreviewPath"), entry.imagePreviewPath},
        {QStringLiteral("videoPreviewPath"), entry.videoPreviewPath},
        {QStringLiteral("metadataPath"), entry.metadataPath},
        {QStringLiteral("sha256"), entry.sha256},
        {QStringLiteral("baseModel"), entry.baseModel},
    };
}

ModelManagerPage::ModelEntry ModelManagerPage::entryFromJson(const QJsonObject &object)
{
    ModelEntry entry;
    entry.name = object.value(QStringLiteral("name")).toString();
    entry.type = object.value(QStringLiteral("type")).toString();
    entry.family = object.value(QStringLiteral("family")).toString();
    entry.sizeText = object.value(QStringLiteral("sizeText")).toString();
    entry.status = object.value(QStringLiteral("status")).toString();
    entry.path = object.value(QStringLiteral("path")).toString();
    entry.imagePreviewPath = object.value(QStringLiteral("imagePreviewPath")).toString();
    entry.videoPreviewPath = object.value(QStringLiteral("videoPreviewPath")).toString();
    entry.metadataPath = object.value(QStringLiteral("metadataPath")).toString();
    entry.sha256 = object.value(QStringLiteral("sha256")).toString();
    entry.baseModel = object.value(QStringLiteral("baseModel")).toString();
    return entry;
}

QString ModelManagerPage::detectFamily(const QString &path)
{
    const QString normalized = path.toLower();
    if (normalized.contains(QStringLiteral("/wan")) || normalized.contains(QStringLiteral("\\wan")))
        return QStringLiteral("wan");
    if (normalized.contains(QStringLiteral("hunyuan")))
        return QStringLiteral("hunyuan_video");
    if (normalized.contains(QStringLiteral("ltx")))
        return QStringLiteral("ltx");
    if (normalized.contains(QStringLiteral("cogvideo")))
        return QStringLiteral("cogvideox");
    if (normalized.contains(QStringLiteral("mochi")))
        return QStringLiteral("mochi");
    if (normalized.contains(QStringLiteral("controlnet")))
        return QStringLiteral("controlnet");
    if (normalized.contains(QStringLiteral("upscale")))
        return QStringLiteral("upscale");
    if (normalized.contains(QStringLiteral("vae")))
        return QStringLiteral("vae");
    if (normalized.contains(QStringLiteral("lora")) || normalized.contains(QStringLiteral("loras")))
        return QStringLiteral("lora");
    if (normalized.contains(QStringLiteral("clip")))
        return QStringLiteral("clip");
    if (normalized.contains(QStringLiteral("sdxl")))
        return QStringLiteral("sdxl");
    return QStringLiteral("unknown");
}

QString ModelManagerPage::detectType(const QString &path)
{
    const QString normalized = path.toLower();
    if (normalized.contains(QStringLiteral("loras")))
        return QStringLiteral("LoRA");
    if (normalized.contains(QStringLiteral("vae")))
        return QStringLiteral("VAE");
    if (normalized.contains(QStringLiteral("clip_vision")) || normalized.contains(QStringLiteral("text_encoders")))
        return QStringLiteral("Encoder");
    if (normalized.contains(QStringLiteral("upscale")) || normalized.contains(QStringLiteral("upscaler")))
        return QStringLiteral("Upscaler");
    if (normalized.contains(QStringLiteral("controlnet")))
        return QStringLiteral("ControlNet");
    return QStringLiteral("Model");
}

bool ModelManagerPage::loadCache()
{
    QFile file(cacheFilePath());
    if (!file.exists() || !file.open(QIODevice::ReadOnly))
        return false;

    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    file.close();
    if (!doc.isObject())
        return false;

    const QJsonObject root = doc.object();
    const QJsonArray items = root.value(QStringLiteral("entries")).toArray();
    QList<ModelEntry> entries;
    for (const QJsonValue &value : items)
    {
        if (value.isObject())
            entries.push_back(entryFromJson(value.toObject()));
    }

    const qint64 checkedAtMs = static_cast<qint64>(root.value(QStringLiteral("checkedAtMs")).toDouble(0.0));
    RefreshResult result;
    result.entries = entries;
    result.modelsRoot = resolveModelsRoot();
    result.downloadsRoot = resolveDownloadsRoot();
    result.checkedAtMs = checkedAtMs;
    if (!result.downloadsRoot.isEmpty() && QDir(result.downloadsRoot).exists())
    {
        QDirIterator downloadsIt(result.downloadsRoot, QDir::Files, QDirIterator::Subdirectories);
        while (downloadsIt.hasNext())
        {
            downloadsIt.next();
            ++result.downloadCount;
        }
    }
    applyEntries(result, QStringLiteral("disk"));
    return !entries.isEmpty();
}

void ModelManagerPage::persistCache(const QList<ModelEntry> &entries, qint64 checkedAtMs) const
{
    QJsonArray items;
    for (const ModelEntry &entry : entries)
        items.append(entryToJson(entry));

    QSaveFile file(cacheFilePath());
    if (!file.open(QIODevice::WriteOnly))
        return;

    QJsonObject root{
        {QStringLiteral("checkedAtMs"), static_cast<double>(checkedAtMs)},
        {QStringLiteral("entries"), items},
    };
    file.write(QJsonDocument(root).toJson(QJsonDocument::Compact));
    file.commit();
}

void ModelManagerPage::warmCache()
{
    if (!loadCache())
    {
        if (summaryLabel_)
            summaryLabel_->setText(QStringLiteral("No cached model inventory yet. Refreshing installed assets in background..."));
        if (cacheSourceLabel_)
            cacheSourceLabel_->setText(QStringLiteral("Cache source: none"));
        if (cachePathLabel_)
            cachePathLabel_->setText(QStringLiteral("Cache path: %1").arg(QDir::toNativeSeparators(cacheFilePath())));
    }

    if (!refreshBusy_)
        refreshInventory();
}

ModelManagerPage::RefreshResult ModelManagerPage::scanModelInventory() const
{
    RefreshResult result;
    result.modelsRoot = resolveModelsRoot();
    result.downloadsRoot = resolveDownloadsRoot();
    result.checkedAtMs = QDateTime::currentMSecsSinceEpoch();

    if (!result.downloadsRoot.isEmpty() && QDir(result.downloadsRoot).exists())
    {
        QDirIterator downloadsIt(result.downloadsRoot, QDir::Files, QDirIterator::Subdirectories);
        while (downloadsIt.hasNext())
        {
            downloadsIt.next();
            ++result.downloadCount;
        }
    }

    if (result.modelsRoot.trimmed().isEmpty() || !QDir(result.modelsRoot).exists())
        return result;

    QList<ModelEntry> entries;
    const QString root = result.modelsRoot;

    QDirIterator it(root, QDir::Files, QDirIterator::Subdirectories);
    while (it.hasNext())
    {
        const QString path = it.next();
        const QFileInfo info(path);
        if (!isModelFile(info.suffix()))
            continue;

        ModelEntry entry;
        entry.name = info.fileName();
        entry.type = detectType(path);
        entry.family = detectFamily(path);
        entry.sizeText = humanSize(info.size());
        entry.status = QStringLiteral("Installed");
        entry.path = QDir::toNativeSeparators(path);

        // S0 (doc 22 §2): resolve sidecars (stat-only) + cheap metadata. Runs on the scan thread;
        // resolveSidecars/parseModelMetadata are pure and thread-safe.
        const spellvision::assets::SidecarSet sidecars = spellvision::assets::resolveSidecars(path);
        entry.imagePreviewPath = sidecars.imagePath;
        entry.videoPreviewPath = sidecars.videoPath;
        entry.metadataPath = sidecars.metadataPath;
        if (sidecars.hasImage())
            ++result.imagePreviewCount;
        if (sidecars.hasVideo())
            ++result.videoPreviewCount;
        if (sidecars.hasMetadata())
        {
            ++result.metadataCount;
            const spellvision::assets::ModelMetadata meta = spellvision::assets::parseModelMetadata(sidecars.metadataPath);
            entry.sha256 = meta.sha256;
            entry.baseModel = meta.baseModel;
            // base_model is authoritative for family when present (fixes flat-folder Wan LoRAs; adds
            // the SDXL/Pony/Illustrious/Flux distinction). Path heuristic remains the fallback.
            const QString famFromBase = familyFromBaseModel(meta.baseModel);
            if (!famFromBase.isEmpty())
                entry.family = famFromBase;
        }

        entries.push_back(entry);
    }
    std::sort(entries.begin(), entries.end(), [](const ModelEntry &a, const ModelEntry &b)
    {
        return a.name.toLower() < b.name.toLower();
    });
    result.entries = entries;
    return result;
}

void ModelManagerPage::setRefreshBusy(bool busy, const QString &statusText)
{
    refreshBusy_ = busy;
    if (refreshButton_)
    {
        refreshButton_->setEnabled(!busy);
        refreshButton_->setText(busy ? QStringLiteral("Refreshing...") : QStringLiteral("Refresh Models"));
    }
    if (openRootButton_)
        openRootButton_->setEnabled(true);
    if (searchModelEdit_)
        searchModelEdit_->setEnabled(!busy);
    if (modelsTree_)
        modelsTree_->setEnabled(!busy);
    if (modelDetailsLabel_ && busy && !statusText.trimmed().isEmpty())
        modelDetailsLabel_->setText(statusText);
}

void ModelManagerPage::refreshInventory()
{
    if (!refreshWatcher_)
        return;
    if (refreshWatcher_->isRunning())
        return;

    setRefreshBusy(true, QStringLiteral("Refreshing model inventory in background..."));
    refreshWatcher_->setFuture(QtConcurrent::run([this]() {
        return scanModelInventory();
    }));
}

void ModelManagerPage::onRefreshFinished()
{
    if (!refreshWatcher_)
        return;

    const RefreshResult result = refreshWatcher_->result();
    persistCache(result.entries, result.checkedAtMs);
    applyEntries(result, QStringLiteral("live"));
    setRefreshBusy(false);
}

void ModelManagerPage::applyEntries(const RefreshResult &result, const QString &sourceLabel)
{
    const QList<ModelEntry> &entries = result.entries;
    const qint64 checkedAtMs = result.checkedAtMs;
    entries_ = QVector<ModelEntry>(entries.cbegin(), entries.cend()); // row i == tree row == card row
    if (modelsTree_)
        modelsTree_->clear();

    int installedCount = 0;
    QSet<QString> families;
    for (const ModelEntry &entry : entries)
    {
        if (modelsTree_)
        {
            auto *item = new QTreeWidgetItem(modelsTree_);
            item->setText(0, entry.name);
            item->setText(1, entry.type);
            item->setText(2, entry.family);
            item->setText(3, entry.sizeText);
            item->setText(4, entry.status);
            item->setData(0, Qt::UserRole, entry.path);
        }
        ++installedCount;
        if (!entry.family.trimmed().isEmpty())
            families.insert(entry.family);
    }

    if (summaryLabel_)
    {
        summaryLabel_->setText(QStringLiteral("Installed assets: %1   Families: %2   Models root: %3")
                                   .arg(installedCount)
                                   .arg(families.size())
                                   .arg(QDir::toNativeSeparators(result.modelsRoot)));
    }

    // S0 verification: sidecar coverage across the scan. Should track the recon (~297 img / 88 mp4 /
    // 399 meta of 710). qWarning so it survives filtered logging.
    qWarning().noquote() << QStringLiteral("[ModelLibrary S0] scanned %1 models — image previews: %2, "
                                           "mp4 previews: %3, metadata sidecars: %4")
                                .arg(installedCount)
                                .arg(result.imagePreviewCount)
                                .arg(result.videoPreviewCount)
                                .arg(result.metadataCount);

    const QString downloadsRoot = result.downloadsRoot;
    if (downloadsLabel_)
    {
        downloadsLabel_->setText(QStringLiteral("Downloads / asset cache root: %1   Files: %2")
                                     .arg(downloadsRoot.isEmpty() ? QStringLiteral("not configured") : QDir::toNativeSeparators(downloadsRoot))
                                     .arg(result.downloadCount));
    }

    if (cacheSourceLabel_)
        cacheSourceLabel_->setText(QStringLiteral("Cache source: %1").arg(sourceLabel.trimmed().isEmpty() ? QStringLiteral("none") : sourceLabel));
    if (lastCheckedLabel_)
    {
        const QString checkedText = checkedAtMs > 0
            ? QDateTime::fromMSecsSinceEpoch(checkedAtMs).toLocalTime().toString(QStringLiteral("yyyy-MM-dd hh:mm:ss AP"))
            : QStringLiteral("never");
        lastCheckedLabel_->setText(QStringLiteral("Last checked: %1").arg(checkedText));
    }
    if (cachePathLabel_)
        cachePathLabel_->setText(QStringLiteral("Cache path: %1").arg(QDir::toNativeSeparators(cacheFilePath())));

    populateGridFromEntries();

    if (!entries_.isEmpty())
    {
        if (modelsTree_ && modelsTree_->topLevelItemCount() > 0)
            modelsTree_->setCurrentItem(modelsTree_->topLevelItem(0));
        if (gridView_ && cardProxy_ && cardProxy_->rowCount() > 0)
            gridView_->setCurrentIndex(cardProxy_->index(0, 0)); // seeds details via currentChanged
        else
            updateDetailsForRow(0);
    }
    else if (modelDetailsLabel_)
        modelDetailsLabel_->setText(QStringLiteral("No cached models yet. Refresh the inventory to scan installed assets."));
}

void ModelManagerPage::populateGridFromEntries()
{
    if (!cardModel_)
        return;

    static const QStringList kExts = {QStringLiteral(".safetensors"), QStringLiteral(".gguf"),
                                      QStringLiteral(".ckpt"), QStringLiteral(".pt"),
                                      QStringLiteral(".pth"), QStringLiteral(".bin"),
                                      QStringLiteral(".onnx")};

    QVector<spellvision::assets::ModelCardModel::Card> cards;
    cards.reserve(entries_.size());
    for (const ModelEntry &e : entries_)
    {
        spellvision::assets::ModelCardModel::Card c;
        c.fullName = e.name;
        QString stripped = e.name;
        for (const QString &ext : kExts)
        {
            if (stripped.endsWith(ext, Qt::CaseInsensitive))
            {
                stripped.chop(ext.size());
                break;
            }
        }
        c.strippedName = stripped;
        c.type = e.type;
        c.family = e.family;
        c.previewPath = e.imagePreviewPath; // image sidecar; mp4 hover-play is S4
        c.nativePath = e.path;
        c.sha256 = e.sha256;
        c.modelValue = e.name;
        c.favorite = overlayStore_ && overlayStore_->isFavorite(c.overlayKey());
        cards.push_back(c);
    }
    cardModel_->setCards(std::move(cards));
}

void ModelManagerPage::onCardFavoriteToggled(const QModelIndex &index)
{
    if (!index.isValid() || !cardProxy_ || !cardModel_ || !overlayStore_)
        return;
    const int row = cardProxy_->mapToSource(index).row();
    if (!cardModel_->isValidRow(row))
        return;
    const QString key = cardModel_->cardAt(row).overlayKey();
    const bool next = !overlayStore_->isFavorite(key);
    overlayStore_->setFavorite(key, next); // app-owned; never written to the sidecar (§2.4)
    cardModel_->setFavorite(row, next);
}

void ModelManagerPage::updateDetailsForRow(int row)
{
    if (!modelDetailsLabel_)
        return;

    currentTriggerWords_.clear();
    auto hideExtras = [this]() {
        if (modelTriggersLabel_) modelTriggersLabel_->hide();
        if (copyTriggersButton_) copyTriggersButton_->hide();
        if (modelDescriptionLabel_) modelDescriptionLabel_->hide();
    };

    if (row < 0 || row >= entries_.size())
    {
        modelDetailsLabel_->setText(QStringLiteral("Select a model to view details."));
        hideExtras();
        return;
    }

    const ModelEntry &e = entries_.at(row);

    // Read the frozen metadata schema on demand (doc 22 §2.3). Degrades gracefully when there's no
    // sidecar (~44% of models).
    spellvision::assets::ModelMetadata meta;
    if (!e.metadataPath.isEmpty())
        meta = spellvision::assets::parseModelMetadata(e.metadataPath);

    const QString baseModel = meta.hasBaseModel()
        ? meta.baseModel
        : ((e.baseModel.isEmpty() || e.baseModel == QStringLiteral("Unknown")) ? QString() : e.baseModel);

    QStringList lines;
    lines << QStringLiteral("Name: %1").arg(e.name);
    lines << QStringLiteral("Type: %1   ·   Family: %2   ·   Size: %3").arg(e.type, e.family, e.sizeText);
    if (!baseModel.isEmpty())
        lines << QStringLiteral("Base model: %1").arg(baseModel);
    if (!meta.tags.isEmpty())
        lines << QStringLiteral("Tags: %1").arg(QStringList(meta.tags.mid(0, 12)).join(QStringLiteral(", ")));
    lines << QStringLiteral("Path: %1").arg(e.path);
    if (e.metadataPath.isEmpty())
        lines << QStringLiteral("No metadata — local file only.");
    modelDetailsLabel_->setText(lines.join(QLatin1Char('\n')));

    // Trigger words (civitai.trainedWords) + copy button.
    currentTriggerWords_ = meta.triggerWords;
    if (!currentTriggerWords_.isEmpty())
    {
        modelTriggersLabel_->setText(QStringLiteral("Triggers: %1").arg(currentTriggerWords_.join(QStringLiteral(", "))));
        modelTriggersLabel_->show();
        copyTriggersButton_->show();
    }
    else
    {
        modelTriggersLabel_->hide();
        copyTriggersButton_->hide();
    }

    // Description (strip HTML, collapse whitespace, truncate — the card stays compact).
    QString desc = meta.description;
    if (!desc.isEmpty())
    {
        desc.remove(QRegularExpression(QStringLiteral("<[^>]*>")));
        desc = desc.simplified();
        if (desc.size() > 600)
            desc = desc.left(600) + QStringLiteral("…");
        modelDescriptionLabel_->setText(desc);
        modelDescriptionLabel_->show();
    }
    else
    {
        modelDescriptionLabel_->hide();
    }
}

void ModelManagerPage::onCardLoadRequested(const QModelIndex &index)
{
    if (!index.isValid() || !cardProxy_)
        return;
    const int row = cardProxy_->mapToSource(index).row();
    if (row < 0 || row >= entries_.size())
        return;
    const ModelEntry &e = entries_.at(row);
    // VAE has no destination yet (§3.3) — the card button is disabled, but guard anyway.
    if (e.type.compare(QStringLiteral("VAE"), Qt::CaseInsensitive) == 0)
        return;

    // Trigger words (civitai.trainedWords) travel with the handoff so the router can auto-populate them.
    QStringList triggers;
    if (!e.metadataPath.isEmpty())
        triggers = spellvision::assets::parseModelMetadata(e.metadataPath).triggerWords;

    emit useModelRequested(e.name, e.family, e.type, triggers);
}

QVector<ModelManagerPage::InventoryItem> ModelManagerPage::inventorySnapshot() const
{
    QVector<InventoryItem> out;
    out.reserve(entries_.size());
    for (const ModelEntry &e : entries_)
        out.push_back(InventoryItem{e.name, e.type, e.family, e.path, e.metadataPath});
    return out;
}

QStringList ModelManagerPage::triggerWordsFor(const QString &metadataPath) const
{
    // Mirrors onCardLoadRequested's derivation so a palette handoff carries the same trigger words a
    // card Load would.
    if (metadataPath.isEmpty())
        return {};
    return spellvision::assets::parseModelMetadata(metadataPath).triggerWords;
}

void ModelManagerPage::onCardInspectRequested(const QModelIndex &index)
{
    if (!index.isValid() || !cardProxy_)
        return;
    const int row = cardProxy_->mapToSource(index).row();
    if (gridView_)
        gridView_->setCurrentIndex(index);
    updateDetailsForRow(row); // S1: the existing details pane. S3 opens the real metadata panel.
}

void ModelManagerPage::setGridViewActive(bool grid)
{
    if (viewStack_)
        viewStack_->setCurrentIndex(grid ? 0 : 1);
    if (gridToggleButton_)
        gridToggleButton_->setChecked(grid);
    if (listToggleButton_)
        listToggleButton_->setChecked(!grid);
}

void ModelManagerPage::buildUi()
{
    setObjectName(QStringLiteral("ModelManagerPage"));

    ThemeManager &theme = ThemeManager::instance();
    const int card = theme.spacing(ThemeManager::Spacing::Card);
    const int snug = theme.spacing(ThemeManager::Spacing::Snug);
    const int tight = theme.spacing(ThemeManager::Spacing::Tight);
    const int hair = theme.spacing(ThemeManager::Spacing::Hairline);

    auto *mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(card, card, card, card);
    mainLayout->setSpacing(snug);

    // --- Header: eyebrow + page title ---
    auto *eyebrow = new QLabel(QStringLiteral("MODEL LIBRARY"), this);
    eyebrow->setObjectName(QStringLiteral("ModelsEyebrow"));
    auto *title = new QLabel(QStringLiteral("Models"), this);
    title->setObjectName(QStringLiteral("ModelsTitle"));

    auto *headerCol = new QVBoxLayout();
    headerCol->setContentsMargins(0, 0, 0, 0);
    headerCol->setSpacing(0);
    headerCol->addWidget(eyebrow);
    headerCol->addWidget(title);

    // --- Summary card: live counts + cache metadata ---
    summaryLabel_ = new QLabel(QStringLiteral("Installed assets: not checked"), this);
    summaryLabel_->setObjectName(QStringLiteral("ModelsSummary"));
    summaryLabel_->setWordWrap(true);
    downloadsLabel_ = new QLabel(QStringLiteral("Downloads / asset cache root: not checked"), this);
    downloadsLabel_->setObjectName(QStringLiteral("ModelsMeta"));
    downloadsLabel_->setWordWrap(true);
    cacheSourceLabel_ = new QLabel(QStringLiteral("Cache source: none"), this);
    cacheSourceLabel_->setObjectName(QStringLiteral("ModelsMeta"));
    lastCheckedLabel_ = new QLabel(QStringLiteral("Last checked: never"), this);
    lastCheckedLabel_->setObjectName(QStringLiteral("ModelsMeta"));
    cachePathLabel_ = new QLabel(QStringLiteral("Cache path: unknown"), this);
    cachePathLabel_->setObjectName(QStringLiteral("ModelsMeta"));
    cachePathLabel_->setWordWrap(true);

    auto *summaryCard = new QFrame(this);
    summaryCard->setObjectName(QStringLiteral("ModelsSummaryCard"));
    auto *summaryCol = new QVBoxLayout(summaryCard);
    summaryCol->setContentsMargins(snug, snug, snug, snug);
    summaryCol->setSpacing(hair);
    summaryCol->addWidget(summaryLabel_);
    summaryCol->addWidget(downloadsLabel_);
    summaryCol->addWidget(cacheSourceLabel_);
    summaryCol->addWidget(lastCheckedLabel_);
    summaryCol->addWidget(cachePathLabel_);

    // --- Toolbar: search + actions ---
    searchModelEdit_ = new QLineEdit(this);
    searchModelEdit_->setObjectName(QStringLiteral("ModelsSearch"));
    searchModelEdit_->setPlaceholderText(QStringLiteral("Search models..."));
    searchModelEdit_->setClearButtonEnabled(true);

    // Grid / List view toggle (Amendment A.1: grid is primary; the tree stays as a compact list).
    gridToggleButton_ = new QPushButton(QStringLiteral("Grid"), this);
    gridToggleButton_->setObjectName(QStringLiteral("ModelsViewToggle"));
    gridToggleButton_->setCheckable(true);
    gridToggleButton_->setChecked(true);
    gridToggleButton_->setCursor(Qt::PointingHandCursor);
    listToggleButton_ = new QPushButton(QStringLiteral("List"), this);
    listToggleButton_->setObjectName(QStringLiteral("ModelsViewToggle"));
    listToggleButton_->setCheckable(true);
    listToggleButton_->setCursor(Qt::PointingHandCursor);

    favoritesToggleButton_ = new QPushButton(QStringLiteral("★ Favorites"), this);
    favoritesToggleButton_->setObjectName(QStringLiteral("ModelsViewToggle"));
    favoritesToggleButton_->setCheckable(true);
    favoritesToggleButton_->setCursor(Qt::PointingHandCursor);

    refreshButton_ = new QPushButton(QStringLiteral("Refresh Models"), this);
    refreshButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    refreshButton_->setCursor(Qt::PointingHandCursor);
    openRootButton_ = new QPushButton(QStringLiteral("Open Models Root"), this);
    openRootButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    openRootButton_->setCursor(Qt::PointingHandCursor);

    auto *toolbarRow = new QHBoxLayout();
    toolbarRow->setSpacing(tight);
    toolbarRow->addWidget(searchModelEdit_, 1);
    toolbarRow->addWidget(favoritesToggleButton_);
    toolbarRow->addWidget(gridToggleButton_);
    toolbarRow->addWidget(listToggleButton_);
    toolbarRow->addWidget(refreshButton_);
    toolbarRow->addWidget(openRootButton_);

    // --- Tree: the visual centre; sits on its own themed surface ---
    modelsTree_ = new QTreeWidget(this);
    modelsTree_->setObjectName(QStringLiteral("ModelsTree"));
    modelsTree_->setHeaderLabels(QStringList()
                                 << QStringLiteral("Name")
                                 << QStringLiteral("Type")
                                 << QStringLiteral("Family")
                                 << QStringLiteral("Size")
                                 << QStringLiteral("Status"));
    modelsTree_->setRootIsDecorated(false);
    modelsTree_->setAlternatingRowColors(true);
    modelsTree_->setUniformRowHeights(true);
    modelsTree_->setFrameShape(QFrame::NoFrame); // the card border comes from the stylesheet
    modelsTree_->setSelectionBehavior(QAbstractItemView::SelectRows);
    modelsTree_->setSelectionMode(QAbstractItemView::SingleSelection);
    if (QHeaderView *header = modelsTree_->header())
    {
        header->setStretchLastSection(false);
        header->setSectionResizeMode(0, QHeaderView::Stretch);           // Name takes the slack
        header->setSectionResizeMode(1, QHeaderView::ResizeToContents);  // Type
        header->setSectionResizeMode(2, QHeaderView::ResizeToContents);  // Family
        header->setSectionResizeMode(3, QHeaderView::ResizeToContents);  // Size
        header->setSectionResizeMode(4, QHeaderView::ResizeToContents);  // Status
        header->setHighlightSections(false);
    }

    // --- Card grid (primary view, Amendment A) ---
    overlayStore_ = new spellvision::assets::ModelOverlayStore(); // app-owned favorites/hidden (S5)
    thumbCache_ = new spellvision::assets::ModelThumbnailCache(this);
    cardModel_ = new spellvision::assets::ModelCardModel(this);
    cardProxy_ = new spellvision::assets::ModelCardFilterProxy(this);
    cardProxy_->setSourceModel(cardModel_);
    cardDelegate_ = new spellvision::assets::ModelCardDelegate(thumbCache_, this);
    gridView_ = new spellvision::assets::ModelCardView(this);
    gridView_->setModel(cardProxy_);
    gridView_->setItemDelegate(cardDelegate_);

    // A generous pixmap cache keeps scroll-back smooth (256px master ~ 256KB each).
    QPixmapCache::setCacheLimit(96 * 1024);

    connect(thumbCache_, &spellvision::assets::ModelThumbnailCache::thumbnailReady,
            this, [this](const QString &key, int) { cardModel_->noteThumbnailReady(key); });
    connect(gridView_, &spellvision::assets::ModelCardView::loadRequested,
            this, &ModelManagerPage::onCardLoadRequested);
    connect(gridView_, &spellvision::assets::ModelCardView::inspectRequested,
            this, &ModelManagerPage::onCardInspectRequested);
    connect(gridView_, &spellvision::assets::ModelCardView::favoriteToggleRequested,
            this, &ModelManagerPage::onCardFavoriteToggled);
    connect(gridView_->selectionModel(), &QItemSelectionModel::currentChanged, this,
            [this](const QModelIndex &current, const QModelIndex &) {
                updateDetailsForRow(current.isValid() ? cardProxy_->mapToSource(current).row() : -1);
            });

    // --- View stack: grid (primary) + tree (compact list toggle) ---
    viewStack_ = new QStackedWidget(this);
    viewStack_->addWidget(gridView_);   // index 0 (default)
    viewStack_->addWidget(modelsTree_); // index 1
    viewStack_->setCurrentIndex(0);

    connect(gridToggleButton_, &QPushButton::clicked, this, [this]() { setGridViewActive(true); });
    connect(listToggleButton_, &QPushButton::clicked, this, [this]() { setGridViewActive(false); });
    connect(favoritesToggleButton_, &QPushButton::toggled, this, [this](bool on) {
        if (cardProxy_)
            cardProxy_->setFavoritesOnly(on);
    });

    // --- Details / Inspect card (S3 metadata panel) ---
    modelDetailsLabel_ = new QLabel(QStringLiteral("Select a model to view details."), this);
    modelDetailsLabel_->setObjectName(QStringLiteral("ModelsDetailsText"));
    modelDetailsLabel_->setWordWrap(true);
    modelDetailsLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);

    // Trigger words (civitai.trainedWords, doc 22 §0 correction #1) + copy-to-clipboard.
    modelTriggersLabel_ = new QLabel(this);
    modelTriggersLabel_->setObjectName(QStringLiteral("ModelsDetailsText"));
    modelTriggersLabel_->setWordWrap(true);
    modelTriggersLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    modelTriggersLabel_->hide();
    copyTriggersButton_ = new QPushButton(QStringLiteral("Copy trigger words"), this);
    copyTriggersButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    copyTriggersButton_->setCursor(Qt::PointingHandCursor);
    copyTriggersButton_->hide();
    connect(copyTriggersButton_, &QPushButton::clicked, this, [this]() {
        if (!currentTriggerWords_.isEmpty())
            QGuiApplication::clipboard()->setText(currentTriggerWords_.join(QStringLiteral(", ")));
    });
    auto *triggersRow = new QHBoxLayout();
    triggersRow->setContentsMargins(0, 0, 0, 0);
    triggersRow->setSpacing(tight);
    triggersRow->addWidget(modelTriggersLabel_, 1);
    triggersRow->addWidget(copyTriggersButton_, 0, Qt::AlignTop);

    modelDescriptionLabel_ = new QLabel(this);
    modelDescriptionLabel_->setObjectName(QStringLiteral("ModelsMeta"));
    modelDescriptionLabel_->setWordWrap(true);
    modelDescriptionLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    modelDescriptionLabel_->setMaximumHeight(64); // keep the card compact; long descriptions truncate
    modelDescriptionLabel_->hide();

    auto *detailsCard = new QFrame(this);
    detailsCard->setObjectName(QStringLiteral("ModelsDetailsCard"));
    auto *detailsCol = new QVBoxLayout(detailsCard);
    detailsCol->setContentsMargins(snug, snug, snug, snug);
    detailsCol->setSpacing(hair);
    detailsCol->addWidget(modelDetailsLabel_);
    detailsCol->addLayout(triggersRow);
    detailsCol->addWidget(modelDescriptionLabel_);

    mainLayout->addLayout(headerCol);
    mainLayout->addWidget(summaryCard);
    mainLayout->addLayout(toolbarRow);
    mainLayout->addWidget(viewStack_, 1);
    mainLayout->addWidget(detailsCard);

    connect(refreshButton_, &QPushButton::clicked, this, &ModelManagerPage::refreshInventory);
    connect(openRootButton_, &QPushButton::clicked, this, [this]()
    {
        const QString root = resolveModelsRoot();
        if (!root.trimmed().isEmpty())
            QDesktopServices::openUrl(QUrl::fromLocalFile(root));
    });
    connect(modelsTree_, &QTreeWidget::itemSelectionChanged, this, &ModelManagerPage::updateModelDetails);
    connect(searchModelEdit_, &QLineEdit::textChanged, this, [this](const QString &text)
    {
        if (cardProxy_)
            cardProxy_->setNeedle(text); // filter the grid (primary view)

        const QString needle = text.trimmed().toLower();
        for (int row = 0; row < modelsTree_->topLevelItemCount(); ++row)
        {
            QTreeWidgetItem *item = modelsTree_->topLevelItem(row);
            const QString haystack = QStringLiteral("%1 %2 %3 %4")
                .arg(item->text(0), item->text(1), item->text(2), item->data(0, Qt::UserRole).toString())
                .toLower();
            item->setHidden(!needle.isEmpty() && !haystack.contains(needle));
        }
    });

    applyThemeStyling();
}

void ModelManagerPage::applyThemeStyling()
{
    const ThemeManager &theme = ThemeManager::instance();
    using C = ThemeManager::Color;

    // Mirrors the sibling content surfaces (T2VHistoryPage): the page is transparent so the shell
    // gradient shows through; content sits on Surface cards; the tree gets the item/hover/selection
    // rules the global sheet only ships for QTableView, so no native grey leaks into the tree body.
    setStyleSheet(QStringLiteral(
        "#ModelManagerPage { background: transparent; }"
        "QFrame#ModelsSummaryCard, QFrame#ModelsDetailsCard {"
        " background: %1; border: 1px solid %6; border-radius: 16px; }"
        "QLabel#ModelsEyebrow { color: %5; @caption@ letter-spacing: 0.12em; text-transform: uppercase; }"
        "QLabel#ModelsTitle { color: %2; @display@ }"
        "QLabel#ModelsSummary { color: %2; @body@ }"
        "QLabel#ModelsMeta { color: %3; @detail@ }"
        "QLabel#ModelsDetailsText { color: %3; @detail@ }"
        "QLineEdit#ModelsSearch { background: %4; color: %2; border: 1px solid %6; border-radius: 10px; padding: 7px 10px; @body@ }"
        "QLineEdit#ModelsSearch:focus { border: 1px solid %5; }"
        "QPushButton#ModelsActionButton { background: %7; color: %2; border: 1px solid %6; border-radius: 11px; padding: 8px 14px; @label@ }"
        "QPushButton#ModelsActionButton:hover { background: %8; border-color: %5; }"
        "QPushButton#ModelsActionButton:pressed { background: %8; }"
        "QPushButton#ModelsActionButton:disabled { color: %9; background: %10; }"
        "QTreeWidget#ModelsTree { background: %4; color: %2; border: 1px solid %6; border-radius: 14px;"
        " outline: none; alternate-background-color: %11; selection-background-color: %8; @detail@ }"
        "QTreeWidget#ModelsTree::item { padding: 7px 8px; border: none; color: %2; }"
        "QTreeWidget#ModelsTree::item:hover { background: %7; }"
        "QTreeWidget#ModelsTree::item:selected { background: %8; color: %2; }"
        "QTreeWidget#ModelsTree QHeaderView::section { background: %7; color: %3; border: none;"
        " border-bottom: 1px solid %6; padding: 8px 8px; @label@ }"
        "QStackedWidget { background: transparent; }"
        "QPushButton#ModelsViewToggle { background: %4; color: %3; border: 1px solid %6; border-radius: 9px; padding: 7px 14px; @label@ }"
        "QPushButton#ModelsViewToggle:hover { border-color: %5; }"
        "QPushButton#ModelsViewToggle:checked { background: %7; color: %2; border-color: %5; }")
                      .arg(theme.css(C::Surface1))       // %1 card bg
                      .arg(theme.css(C::TextHi))         // %2 titles / primary text
                      .arg(theme.css(C::TextMid))        // %3 body / meta / details
                      .arg(theme.css(C::Surface0))       // %4 tree + search bg (recessed)
                      .arg(theme.css(C::Accent))         // %5 eyebrow / focus / accent
                      .arg(theme.css(C::BorderStrong))   // %6 borders
                      .arg(theme.css(C::AccentSubtle))   // %7 header / hover / button tint
                      .arg(theme.css(C::AccentGlow))     // %8 selection / button-hover
                      .arg(theme.css(C::TextDisabled))   // %9 disabled text
                      .arg(theme.css(C::BorderSubtle))   // %10 disabled bg
                      .arg(theme.css(C::Surface2))       // %11 alternate row
                      .replace(QLatin1String("@display@"), theme.fontCss(ThemeManager::Type::Display))
                      .replace(QLatin1String("@body@"), theme.fontCss(ThemeManager::Type::Body))
                      .replace(QLatin1String("@detail@"), theme.fontCss(ThemeManager::Type::Detail))
                      .replace(QLatin1String("@label@"), theme.fontCss(ThemeManager::Type::Label))
                      .replace(QLatin1String("@caption@"), theme.fontCss(ThemeManager::Type::Caption)));
}

void ModelManagerPage::updateModelDetails()
{
    // Tree selection -> shared details helper (tree row == entries_ index).
    QTreeWidgetItem *item = modelsTree_ ? modelsTree_->currentItem() : nullptr;
    updateDetailsForRow(item ? modelsTree_->indexOfTopLevelItem(item) : -1);
}
