#include "ModelManagerPage.h"
#include <QInputDialog>
#include "ThemeManager.h"
#include "assets/ModelSidecar.h"
#include "assets/ModelThumbnailCache.h"
#include "assets/ModelOverlayStore.h"
#include "assets/ModelCardModel.h"
#include "assets/ModelCardDelegate.h"
#include "assets/ModelCardView.h"
#include "assets/CatalogPickerDialog.h"

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
#include <QComboBox>
#include <QMessageBox>
#include <QPushButton>
#include <QSaveFile>
#include <QSettings>
#include <QSignalBlocker>
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

    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString configured = settings.value(QStringLiteral("runtime/modelsRoot")).toString().trimmed();
    if (!configured.isEmpty())
        return QDir::fromNativeSeparators(QDir(configured).absolutePath());

    return QString();
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

ModelManagerPage::RefreshResult ModelManagerPage::scanModelInventory(
    const QString &modelsRoot,
    const QString &downloadsRoot)
{
    RefreshResult result;
    result.modelsRoot = modelsRoot;
    result.downloadsRoot = downloadsRoot;
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

    const QString modelsRoot = resolveModelsRoot();
    const QString downloadsRoot = resolveDownloadsRoot();
    setRefreshBusy(true, QStringLiteral("Refreshing model inventory in background..."));
    refreshWatcher_->setFuture(QtConcurrent::run([modelsRoot, downloadsRoot]() {
        return scanModelInventory(modelsRoot, downloadsRoot);
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
    rebuildFilterCombos();
}

void ModelManagerPage::rebuildFilterCombos()
{
    if (!typeFilterCombo_ || !familyFilterCombo_)
        return;

    QStringList types;
    QStringList families;
    types.reserve(entries_.size());
    families.reserve(entries_.size());
    for (const ModelEntry &e : entries_) {
        if (!e.type.trimmed().isEmpty())
            types.push_back(e.type.trimmed());
        if (!e.family.trimmed().isEmpty())
            families.push_back(e.family.trimmed());
    }
    types.removeDuplicates();
    families.removeDuplicates();
    std::sort(types.begin(), types.end(), [](const QString &a, const QString &b) {
        return a.compare(b, Qt::CaseInsensitive) < 0;
    });
    std::sort(families.begin(), families.end(), [](const QString &a, const QString &b) {
        return a.compare(b, Qt::CaseInsensitive) < 0;
    });

    const QString prevType = typeFilterCombo_->currentData().toString();
    const QString prevFamily = familyFilterCombo_->currentData().toString();

    {
        QSignalBlocker blockType(typeFilterCombo_);
        typeFilterCombo_->clear();
        typeFilterCombo_->addItem(QStringLiteral("All types"), QStringLiteral("All"));
        for (const QString &t : types)
            typeFilterCombo_->addItem(t, t);
        int idx = typeFilterCombo_->findData(prevType);
        if (idx < 0)
            idx = 0;
        typeFilterCombo_->setCurrentIndex(idx);
    }
    {
        QSignalBlocker blockFamily(familyFilterCombo_);
        familyFilterCombo_->clear();
        familyFilterCombo_->addItem(QStringLiteral("All families"), QStringLiteral("All"));
        for (const QString &f : families)
            familyFilterCombo_->addItem(f, f);
        int idx = familyFilterCombo_->findData(prevFamily);
        if (idx < 0)
            idx = 0;
        familyFilterCombo_->setCurrentIndex(idx);
    }

    if (cardProxy_) {
        cardProxy_->setTypeFilter(typeFilterCombo_->currentData().toString());
        cardProxy_->setFamilyFilter(familyFilterCombo_->currentData().toString());
    }
    applyTreeFilters();
}

void ModelManagerPage::applyTreeFilters()
{
    if (!modelsTree_)
        return;

    const QString needle = searchModelEdit_ ? searchModelEdit_->text().trimmed().toLower() : QString();
    const QString typeFilter = typeFilterCombo_ ? typeFilterCombo_->currentData().toString() : QStringLiteral("All");
    const QString familyFilter = familyFilterCombo_ ? familyFilterCombo_->currentData().toString() : QStringLiteral("All");
    const bool typeAll = typeFilter.isEmpty() || typeFilter.compare(QStringLiteral("All"), Qt::CaseInsensitive) == 0;
    const bool familyAll = familyFilter.isEmpty() || familyFilter.compare(QStringLiteral("All"), Qt::CaseInsensitive) == 0;

    for (int row = 0; row < modelsTree_->topLevelItemCount(); ++row) {
        QTreeWidgetItem *item = modelsTree_->topLevelItem(row);
        if (!item)
            continue;
        const QString type = item->text(1);
        const QString family = item->text(2);
        const QString haystack = QStringLiteral("%1 %2 %3 %4")
                                     .arg(item->text(0), type, family, item->data(0, Qt::UserRole).toString())
                                     .toLower();
        bool hide = false;
        if (!needle.isEmpty() && !haystack.contains(needle))
            hide = true;
        if (!typeAll && type.compare(typeFilter, Qt::CaseInsensitive) != 0)
            hide = true;
        if (!familyAll && family.compare(familyFilter, Qt::CaseInsensitive) != 0)
            hide = true;
        item->setHidden(hide);
    }
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
        currentDetailRow_ = -1;
        updateWorkflowSectionForRow(-1);
        return;
    }

    currentDetailRow_ = row;

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
    if (deleteModelButton_)
        deleteModelButton_->setVisible(!e.path.trimmed().isEmpty());
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

    updateWorkflowSectionForRow(row);
}

QString ModelManagerPage::overlayKeyForEntry(const ModelManagerPage::ModelEntry &entry)
{
    // Mirrors ModelCard::overlayKey(): sha256 identity, or the native path when the hash is absent.
    return entry.sha256.isEmpty() ? entry.path : entry.sha256;
}

QJsonObject ModelManagerPage::workflowSummaryForSlug(const QString &slug) const
{
    const QString target = slug.trimmed();
    if (target.isEmpty())
        return {};
    for (const QJsonObject &wf : importedWorkflows_)
        if (wf.value(QStringLiteral("import_slug")).toString() == target)
            return wf;
    return {};
}

void ModelManagerPage::setImportedWorkflows(const QVector<QJsonObject> &workflows)
{
    importedWorkflows_ = workflows;
    // Refresh the currently-shown model so a freshly-imported/rescanned workflow's readiness updates.
    updateWorkflowSectionForRow(currentDetailRow_);
}

void ModelManagerPage::updateWorkflowSectionForRow(int row)
{
    if (!workflowBindingLabel_)
        return;

    auto hideActions = [this]() {
        if (bindWorkflowButton_) bindWorkflowButton_->hide();
        if (useWorkflowButton_) useWorkflowButton_->hide();
        if (resolveDepsButton_) resolveDepsButton_->hide();
        if (workflowNoteLabel_) workflowNoteLabel_->hide();
    };

    if (row < 0 || row >= entries_.size() || !overlayStore_)
    {
        workflowBindingLabel_->hide();
        hideActions();
        return;
    }

    workflowBindingLabel_->show();
    bindWorkflowButton_->show();

    const ModelEntry &e = entries_.at(row);
    // VAEs / text encoders are not standalone-generatable; a workflow binding only makes sense for a
    // checkpoint or diffusion model (or a LoRA that a workflow's lora slot can take). Keep the row
    // visible but only offer binding for the model-ish types.
    const bool bindable = e.type.compare(QStringLiteral("VAE"), Qt::CaseInsensitive) != 0;
    bindWorkflowButton_->setEnabled(bindable);

    const QString slug = overlayStore_->workflowProfile(overlayKeyForEntry(e));
    if (slug.isEmpty())
    {
        workflowBindingLabel_->setText(QStringLiteral("Workflow: none bound."));
        useWorkflowButton_->hide();
        resolveDepsButton_->hide();
        workflowNoteLabel_->hide();
        return;
    }

    const QJsonObject wf = workflowSummaryForSlug(slug);
    if (wf.isEmpty())
    {
        // Bound to a slug that is no longer in the imported library (deleted / not yet refreshed).
        workflowBindingLabel_->setText(QStringLiteral("Workflow: %1 — not found in the library.").arg(slug));
        useWorkflowButton_->hide();
        resolveDepsButton_->hide();
        workflowNoteLabel_->show();
        workflowNoteLabel_->setText(QStringLiteral(
            "The bound workflow is missing. Re-import it, or bind a different one."));
        return;
    }

    const QString name = wf.value(QStringLiteral("profile_name")).toString();
    const QString task = wf.value(QStringLiteral("task_command")).toString();
    const QString readiness = wf.value(QStringLiteral("readiness_label")).toString();
    const bool ready = wf.value(QStringLiteral("ready")).toBool();
    const int loaderCount = wf.value(QStringLiteral("model_loader_count")).toInt();

    workflowBindingLabel_->setText(QStringLiteral("Workflow: %1   ·   %2   ·   %3")
                                       .arg(name,
                                            task.isEmpty() ? QStringLiteral("unknown task") : task,
                                            readiness.isEmpty() ? QStringLiteral("Unknown") : readiness));

    // Dual-loader note: a Wan high/low-noise graph (two UNETLoaders) can't take a single model
    // unambiguously, so "Use workflow" launches it unbound (baked-in pair wins). Say so plainly.
    const bool dualLoader = loaderCount >= 2 && bindable;

    if (ready)
    {
        useWorkflowButton_->show();
        useWorkflowButton_->setEnabled(true);
        resolveDepsButton_->hide();
        if (dualLoader)
        {
            workflowNoteLabel_->show();
            workflowNoteLabel_->setText(QStringLiteral(
                "This workflow uses its own model pair (two loaders) — it launches with those, not this model."));
        }
        else
        {
            workflowNoteLabel_->hide();
        }
    }
    else
    {
        // Not Ready: don't just grey out — show what's missing and offer the Flows dependency flow.
        useWorkflowButton_->hide();
        resolveDepsButton_->show();
        QStringList missing;
        for (const QJsonValue &node : wf.value(QStringLiteral("metadata")).toObject()
                                          .value(QStringLiteral("missing_custom_nodes")).toArray())
            missing << node.toString();
        const QString reason = wf.value(QStringLiteral("readiness_reason")).toString();
        QString note = reason.isEmpty() ? QStringLiteral("This workflow is not ready to launch.") : reason;
        if (!missing.isEmpty())
            note += QStringLiteral("\nMissing custom nodes: %1").arg(missing.join(QStringLiteral(", ")));
        workflowNoteLabel_->show();
        workflowNoteLabel_->setText(note);
    }
}

void ModelManagerPage::onBindWorkflowClicked()
{
    if (currentDetailRow_ < 0 || currentDetailRow_ >= entries_.size() || !overlayStore_)
        return;
    if (importedWorkflows_.isEmpty())
    {
        QMessageBox::information(this, QStringLiteral("Bind Workflow"),
            QStringLiteral("No imported workflows are available yet. Import one on the Flows page first."));
        return;
    }

    const ModelEntry &e = entries_.at(currentDetailRow_);
    const QString key = overlayKeyForEntry(e);
    const QString current = overlayStore_->workflowProfile(key);

    QVector<spellvision::assets::CatalogEntry> catalog;
    catalog.reserve(importedWorkflows_.size());
    for (const QJsonObject &wf : importedWorkflows_)
    {
        spellvision::assets::CatalogEntry entry;
        const QString slug = wf.value(QStringLiteral("import_slug")).toString();
        entry.value = slug;
        entry.display = wf.value(QStringLiteral("profile_name")).toString();
        if (entry.display.isEmpty())
            entry.display = slug;
        entry.family = wf.value(QStringLiteral("task_command")).toString();
        entry.modality = wf.value(QStringLiteral("media_type")).toString();
        entry.role = wf.value(QStringLiteral("readiness_label")).toString();
        entry.note = wf.value(QStringLiteral("readiness_reason")).toString();
        entry.metadata = wf;
        catalog.push_back(entry);
    }

    spellvision::assets::CatalogPickerDialog dialog(
        QStringLiteral("Bind workflow to %1").arg(e.name),
        catalog, current, QStringLiteral("models/bind_workflow_recent"), this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    const QString chosen = dialog.selectedValue().trimmed();
    if (chosen.isEmpty())
        return;

    overlayStore_->setWorkflowProfile(key, chosen); // explicit user action only (never auto-guessed)
    updateWorkflowSectionForRow(currentDetailRow_);
}

void ModelManagerPage::onUseWorkflowClicked()
{
    if (currentDetailRow_ < 0 || currentDetailRow_ >= entries_.size() || !overlayStore_)
        return;
    const ModelEntry &e = entries_.at(currentDetailRow_);
    const QString slug = overlayStore_->workflowProfile(overlayKeyForEntry(e));
    const QJsonObject wf = workflowSummaryForSlug(slug);
    if (wf.isEmpty() || !wf.value(QStringLiteral("ready")).toBool())
        return;

    // Dual-loader (two UNETLoaders): launch unbound so the graph's own model pair wins. Otherwise
    // substitute THIS asset -- routed by type so a LoRA fills the lora slot, not the checkpoint. Pass
    // the full path; the worker resolves it to ComfyUI's exact catalogued loader name.
    const bool dualLoader = wf.value(QStringLiteral("model_loader_count")).toInt() >= 2;
    const QString assetPath = e.path.isEmpty() ? e.name : e.path;
    const bool isLora = e.type.compare(QStringLiteral("LoRA"), Qt::CaseInsensitive) == 0;
    QString modelValue, loraValue;
    if (!dualLoader)
    {
        if (isLora)
            loraValue = assetPath;
        else
            modelValue = assetPath;
    }

    overlayStore_->noteUsed(overlayKeyForEntry(e), e.family);
    emit useWorkflowRequested(wf, modelValue, loraValue);
}

void ModelManagerPage::onResolveDependenciesClicked()
{
    if (currentDetailRow_ < 0 || currentDetailRow_ >= entries_.size() || !overlayStore_)
        return;
    const ModelEntry &e = entries_.at(currentDetailRow_);
    const QString slug = overlayStore_->workflowProfile(overlayKeyForEntry(e));
    if (!slug.isEmpty())
        emit resolveWorkflowDependenciesRequested(slug);
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
    // Ensure the inspect surface is visible — scroll the page if needed.
    if (modelDetailsLabel_)
        modelDetailsLabel_->setFocus(Qt::OtherFocusReason);
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

    typeFilterCombo_ = new QComboBox(this);
    typeFilterCombo_->setObjectName(QStringLiteral("ModelsFilterCombo"));
    typeFilterCombo_->setMinimumContentsLength(10);
    typeFilterCombo_->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    typeFilterCombo_->addItem(QStringLiteral("All types"), QStringLiteral("All"));
    typeFilterCombo_->setToolTip(QStringLiteral("Filter by asset type (Checkpoint, LoRA, …)"));

    familyFilterCombo_ = new QComboBox(this);
    familyFilterCombo_->setObjectName(QStringLiteral("ModelsFilterCombo"));
    familyFilterCombo_->setMinimumContentsLength(8);
    familyFilterCombo_->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    familyFilterCombo_->addItem(QStringLiteral("All families"), QStringLiteral("All"));
    familyFilterCombo_->setToolTip(QStringLiteral("Filter by model family (sdxl, wan, flux, …)"));

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
    toolbarRow->addWidget(typeFilterCombo_);
    toolbarRow->addWidget(familyFilterCombo_);
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

    // --- S3 bound-workflow row: name / task / readiness + Bind / Use / Resolve actions ---
    workflowBindingLabel_ = new QLabel(this);
    workflowBindingLabel_->setObjectName(QStringLiteral("ModelsDetailsText"));
    workflowBindingLabel_->setWordWrap(true);
    workflowBindingLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);

    workflowNoteLabel_ = new QLabel(this);
    workflowNoteLabel_->setObjectName(QStringLiteral("ModelsMeta"));
    workflowNoteLabel_->setWordWrap(true);
    workflowNoteLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    workflowNoteLabel_->hide();

    bindWorkflowButton_ = new QPushButton(QStringLiteral("Bind workflow…"), this);
    bindWorkflowButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    bindWorkflowButton_->setCursor(Qt::PointingHandCursor);
    useWorkflowButton_ = new QPushButton(QStringLiteral("Use workflow"), this);
    useWorkflowButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    useWorkflowButton_->setCursor(Qt::PointingHandCursor);
    resolveDepsButton_ = new QPushButton(QStringLiteral("Resolve dependencies…"), this);
    resolveDepsButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    resolveDepsButton_->setCursor(Qt::PointingHandCursor);
    resolveDepsButton_->hide(); // shown only when the bound workflow is not Ready

    connect(bindWorkflowButton_, &QPushButton::clicked, this, &ModelManagerPage::onBindWorkflowClicked);
    connect(useWorkflowButton_, &QPushButton::clicked, this, &ModelManagerPage::onUseWorkflowClicked);
    connect(resolveDepsButton_, &QPushButton::clicked, this, &ModelManagerPage::onResolveDependenciesClicked);

    // Download is the lane that already exists (download_manager + the progress bar in
    // MainWindow::startModelDownload); its only caller was the Flows page. Delete is new, and the
    // worker refuses anything outside the models root, so this button can only remove what the
    // library shows.
    downloadModelButton_ = new QPushButton(QStringLiteral("Download model…"), this);
    downloadModelButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    downloadModelButton_->setCursor(Qt::PointingHandCursor);
    downloadModelButton_->setToolTip(QStringLiteral("Paste a Civitai or Hugging Face link. Downloads in the background with progress."));
    deleteModelButton_ = new QPushButton(QStringLiteral("Delete…"), this);
    deleteModelButton_->setObjectName(QStringLiteral("ModelsDangerButton"));
    deleteModelButton_->setCursor(Qt::PointingHandCursor);
    deleteModelButton_->hide();
    connect(downloadModelButton_, &QPushButton::clicked, this, &ModelManagerPage::onDownloadModelClicked);
    connect(deleteModelButton_, &QPushButton::clicked, this, &ModelManagerPage::onDeleteModelClicked);

    auto *workflowRow = new QHBoxLayout();
    workflowRow->setContentsMargins(0, 0, 0, 0);
    workflowRow->setSpacing(tight);
    workflowRow->addWidget(bindWorkflowButton_);
    workflowRow->addWidget(useWorkflowButton_);
    workflowRow->addWidget(resolveDepsButton_);
    workflowRow->addWidget(downloadModelButton_);
    workflowRow->addStretch(1);
    workflowRow->addWidget(deleteModelButton_);

    auto *detailsCard = new QFrame(this);
    detailsCard->setObjectName(QStringLiteral("ModelsDetailsCard"));
    detailsCard->setMinimumHeight(168);
    detailsCard->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    auto *detailsCol = new QVBoxLayout(detailsCard);
    detailsCol->setContentsMargins(snug, snug, snug, snug);
    detailsCol->setSpacing(hair);
    detailsCol->addWidget(modelDetailsLabel_);
    detailsCol->addLayout(triggersRow);
    detailsCol->addWidget(modelDescriptionLabel_);
    detailsCol->addWidget(workflowBindingLabel_);
    detailsCol->addWidget(workflowNoteLabel_);
    detailsCol->addLayout(workflowRow);

    mainLayout->addLayout(headerCol);
    mainLayout->addWidget(summaryCard);
    mainLayout->addLayout(toolbarRow);
    mainLayout->addWidget(viewStack_, 1);
    mainLayout->addWidget(detailsCard, 0);

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
        applyTreeFilters();
    });
    connect(typeFilterCombo_, &QComboBox::currentIndexChanged, this, [this](int) {
        if (cardProxy_ && typeFilterCombo_)
            cardProxy_->setTypeFilter(typeFilterCombo_->currentData().toString());
        applyTreeFilters();
    });
    connect(familyFilterCombo_, &QComboBox::currentIndexChanged, this, [this](int) {
        if (cardProxy_ && familyFilterCombo_)
            cardProxy_->setFamilyFilter(familyFilterCombo_->currentData().toString());
        applyTreeFilters();
    });

    applyThemeStyling();
}

void ModelManagerPage::applyThemeStyling()
{
    const ThemeManager &theme = ThemeManager::instance();
    using C = ThemeManager::Color;

    // Use @tokens@ — QString::arg only supports %1..%9 reliably; %10+ becomes %1 + "0".
    setStyleSheet(QStringLiteral(
        "#ModelManagerPage { background: transparent; }"
        "QFrame#ModelsSummaryCard, QFrame#ModelsDetailsCard {"
        " background: @s1@; border: 1px solid @bd@; border-radius: 14px; }"
        "QLabel#ModelsEyebrow { color: @acc@; @caption@ letter-spacing: 0.12em; text-transform: uppercase; }"
        "QLabel#ModelsTitle { color: @hi@; @display@ }"
        "QLabel#ModelsSummary { color: @hi@; @body@ }"
        "QLabel#ModelsMeta { color: @mid@; @detail@ }"
        "QLabel#ModelsDetailsText { color: @mid@; @detail@ }"
        "QLineEdit#ModelsSearch { background: @s0@; color: @hi@; border: 1px solid @bd@; border-radius: 10px; padding: 7px 10px; @body@ }"
        "QLineEdit#ModelsSearch:focus { border: 1px solid @acc@; }"
        "QPushButton#ModelsActionButton { background: @sub@; color: @hi@; border: 1px solid @bd@; border-radius: 10px; padding: 8px 14px; @label@ }"
        "QPushButton#ModelsActionButton:hover { background: @glow@; border-color: @acc@; }"
        "QPushButton#ModelsActionButton:pressed { background: @glow@; }"
        "QPushButton#ModelsActionButton:disabled { color: @dis@; background: @bds@; }"
        "QTreeWidget#ModelsTree { background: @s0@; color: @hi@; border: 1px solid @bd@; border-radius: 14px;"
        " outline: none; alternate-background-color: @s2@; selection-background-color: @glow@; @detail@ }"
        "QTreeWidget#ModelsTree::item { padding: 7px 8px; border: none; color: @hi@; }"
        "QTreeWidget#ModelsTree::item:hover { background: @sub@; }"
        "QTreeWidget#ModelsTree::item:selected { background: @glow@; color: @hi@; }"
        "QTreeWidget#ModelsTree QHeaderView::section { background: @sub@; color: @mid@; border: none;"
        " border-bottom: 1px solid @bd@; padding: 8px 8px; @label@ }"
        "QStackedWidget { background: transparent; }"
        "QPushButton#ModelsViewToggle { background: @s0@; color: @mid@; border: 1px solid @bd@; border-radius: 9px; padding: 7px 14px; @label@ }"
        "QPushButton#ModelsViewToggle:hover { border-color: @acc@; }"
        "QPushButton#ModelsViewToggle:checked { background: @sub@; color: @hi@; border-color: @acc@; }")
                      .replace(QLatin1String("@s0@"), theme.css(C::Surface0))
                      .replace(QLatin1String("@s1@"), theme.css(C::Surface1))
                      .replace(QLatin1String("@s2@"), theme.css(C::Surface2))
                      .replace(QLatin1String("@hi@"), theme.css(C::TextHi))
                      .replace(QLatin1String("@mid@"), theme.css(C::TextMid))
                      .replace(QLatin1String("@dis@"), theme.css(C::TextDisabled))
                      .replace(QLatin1String("@acc@"), theme.css(C::Accent))
                      .replace(QLatin1String("@bd@"), theme.css(C::BorderStrong))
                      .replace(QLatin1String("@bds@"), theme.css(C::BorderSubtle))
                      .replace(QLatin1String("@sub@"), theme.css(C::AccentSubtle))
                      .replace(QLatin1String("@glow@"), theme.css(C::AccentGlow))
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

void ModelManagerPage::onDownloadModelClicked()
{
    bool ok = false;
    const QString reference = QInputDialog::getText(
        this,
        QStringLiteral("Download model"),
        QStringLiteral("Civitai or Hugging Face link:"),
        QLineEdit::Normal, QString(), &ok).trimmed();
    if (!ok || reference.isEmpty())
        return;
    emit downloadModelRequested(reference);
}

void ModelManagerPage::onDeleteModelClicked()
{
    if (currentDetailRow_ < 0 || currentDetailRow_ >= entries_.size())
        return;
    const ModelEntry &e = entries_.at(currentDetailRow_);
    if (e.path.trimmed().isEmpty())
        return;
    const QFileInfo info(e.path);
    QMessageBox box(this);
    box.setIcon(QMessageBox::Warning);
    box.setWindowTitle(QStringLiteral("Delete %1?").arg(info.fileName()));
    box.setText(QStringLiteral("This removes the file from disk, along with its preview and metadata sidecars. "
                               "It cannot be undone from here."));
    box.setInformativeText(QDir::toNativeSeparators(e.path));
    QPushButton *remove = box.addButton(QStringLiteral("Delete"), QMessageBox::DestructiveRole);
    box.addButton(QMessageBox::Cancel);
    box.setDefaultButton(QMessageBox::Cancel);
    box.setEscapeButton(QMessageBox::Cancel);
    box.exec();
    if (box.clickedButton() != remove)
        return;
    emit deleteModelRequested(e.path);
}
