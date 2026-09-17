#include "ModelManagerPage.h"
#include <QInputDialog>
#include "ThemeManager.h"
#include "assets/ModelSidecar.h"
#include "assets/ModelThumbnailCache.h"
#include "assets/ModelOverlayStore.h"
#include "assets/ModelCardModel.h"
#include "assets/ModelCardDelegate.h"
#include "assets/ModelCardView.h"
#include "assets/ModelInspectorPanel.h"
#include "assets/ModelIntelSidecar.h"
#include "assets/ModelKindTabs.h"
#include "assets/ModelRefreshController.h"
#include "assets/CatalogPickerDialog.h"
#include "style/SvKit.h"
#include "shell/ModelsLibraryPaths.h"
#include "widgets/ElidingLabel.h"

#include <QClipboard>
#include <QDebug>
#include <QGuiApplication>
#include <QItemSelectionModel>
#include <QPixmap>
#include <QPixmapCache>
#include <QRegularExpression>
#include <QStackedWidget>

#include <QDesktopServices>
#include <QFileDialog>
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
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QMessageBox>
#include <QMimeData>
#include <QProgressBar>
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

using spellvision::kit::setRole;
using spellvision::kit::setSurface;
namespace svstyle = spellvision::style;

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
    setAcceptDrops(true);

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
        return spellvision::shell::resolveModelsLibraryRoot(QDir::fromNativeSeparators(QDir(envPath).absolutePath()));

    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString configured = settings.value(QStringLiteral("runtime/modelsRoot")).toString().trimmed();
    if (!configured.isEmpty())
        return spellvision::shell::resolveModelsLibraryRoot(QDir::fromNativeSeparators(QDir(configured).absolutePath()));

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
        {QStringLiteral("displayName"), entry.displayName},
        {QStringLiteral("type"), entry.type},
        {QStringLiteral("kind"), entry.kind},
        {QStringLiteral("family"), entry.family},
        {QStringLiteral("sizeText"), entry.sizeText},
        {QStringLiteral("status"), entry.status},
        {QStringLiteral("path"), entry.path},
        {QStringLiteral("imagePreviewPath"), entry.imagePreviewPath},
        {QStringLiteral("videoPreviewPath"), entry.videoPreviewPath},
        {QStringLiteral("metadataPath"), entry.metadataPath},
        {QStringLiteral("sha256"), entry.sha256},
        {QStringLiteral("baseModel"), entry.baseModel},
        {QStringLiteral("siteBadge"), entry.siteBadge},
        {QStringLiteral("quantisation"), entry.quantisation},
        {QStringLiteral("coverPath"), entry.coverPath},
        {QStringLiteral("previewNsfwLevel"), entry.previewNsfwLevel},
        {QStringLiteral("identification"), entry.identification},
    };
}

ModelManagerPage::ModelEntry ModelManagerPage::entryFromJson(const QJsonObject &object)
{
    ModelEntry entry;
    entry.name = object.value(QStringLiteral("name")).toString();
    entry.displayName = object.value(QStringLiteral("displayName")).toString();
    entry.type = object.value(QStringLiteral("type")).toString();
    // A cache written before W5 carries no kind. Deriving it from the path here rather than
    // leaving it empty is what keeps a warm start from parking the whole library in Other until
    // the background rescan lands.
    entry.kind = object.value(QStringLiteral("kind")).toString().trimmed();
    if (entry.kind.isEmpty())
        entry.kind = spellvision::assets::ModelKindTabs::kindFromPath(object.value(QStringLiteral("path")).toString());
    entry.family = object.value(QStringLiteral("family")).toString();
    entry.sizeText = object.value(QStringLiteral("sizeText")).toString();
    entry.status = object.value(QStringLiteral("status")).toString();
    entry.path = object.value(QStringLiteral("path")).toString();
    entry.imagePreviewPath = object.value(QStringLiteral("imagePreviewPath")).toString();
    entry.videoPreviewPath = object.value(QStringLiteral("videoPreviewPath")).toString();
    entry.metadataPath = object.value(QStringLiteral("metadataPath")).toString();
    entry.sha256 = object.value(QStringLiteral("sha256")).toString();
    entry.baseModel = object.value(QStringLiteral("baseModel")).toString();
    entry.siteBadge = object.value(QStringLiteral("siteBadge")).toString();
    entry.quantisation = object.value(QStringLiteral("quantisation")).toString();
    entry.coverPath = object.value(QStringLiteral("coverPath")).toString();
    entry.previewNsfwLevel = object.value(QStringLiteral("previewNsfwLevel")).toInt();
    entry.identification = object.value(QStringLiteral("identification")).toInt();
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

QString ModelManagerPage::kindForWeight(const QString &path)
{
    // The classifier's answer first. `detectType` used to decide this from six path substrings,
    // which put `clip_vision` and `text_encoders` in one "Encoder" bucket and had no name at all
    // for an embedding or a style model -- so those sat under "Model" next to the checkpoints.
    const spellvision::assets::ModelIntel intel = spellvision::assets::readModelIntel(path);
    if (intel.present && !intel.kind.isEmpty())
        return intel.kind;
    // No sidecar: the folder a ComfyUI library files a kind under. It answers in the same
    // vocabulary and ends at "other" rather than guessing "checkpoint".
    return spellvision::assets::ModelKindTabs::kindFromPath(path);
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

        // W5: ONE read of `<stem>.spellvision.json` per weight. The kind, the name the site gave
        // the file, the site badge, the quantisation and the cover all come out of the same
        // document -- reading it twice would let two answers about one file diverge.
        const spellvision::assets::ModelIntel intel = spellvision::assets::readModelIntel(path);
        entry.kind = intel.present && !intel.kind.isEmpty()
            ? intel.kind
            : spellvision::assets::ModelKindTabs::kindFromPath(path);
        entry.type = spellvision::assets::ModelKindTabs::kindLabel(entry.kind);
        entry.family = detectFamily(path);
        entry.identification = static_cast<int>(intel.identification());
        if (intel.identified())
        {
            // The display name goes on the PAGE. Nothing here touches the file.
            if (!intel.displayName.isEmpty())
                entry.displayName = intel.displayName;
            entry.siteBadge = intel.primarySource().siteLabel();
        }
        entry.quantisation = intel.quantisation;
        if (!intel.family.isEmpty())
            entry.family = intel.family;
        if (!intel.sha256.isEmpty())
            entry.sha256 = intel.sha256;
        const spellvision::assets::ModelIntelImage cover = intel.coverImage();
        if (!cover.localPath.isEmpty() && QFileInfo::exists(cover.localPath))
        {
            entry.coverPath = cover.localPath;
            entry.previewNsfwLevel = cover.nsfwLevel;
        }
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
            if (entry.sha256.isEmpty())
                entry.sha256 = meta.sha256;
            entry.baseModel = meta.baseModel;
            // The import sidecar's model_name only fills a gap now: `<stem>.spellvision.json` is
            // the identity document, and a name it established must not be overwritten by the
            // older, thinner one.
            if (entry.displayName.trimmed().isEmpty())
                entry.displayName = meta.modelName.trimmed();
            // base_model is authoritative for family when present (fixes flat-folder Wan LoRAs; adds
            // the SDXL/Pony/Illustrious/Flux distinction). Path heuristic remains the fallback.
            const QString famFromBase = familyFromBaseModel(meta.baseModel);
            if (!famFromBase.isEmpty() && !intel.present)
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
    if (rebuildCacheButton_)
        rebuildCacheButton_->setEnabled(!busy);
    if (openRootButton_)
        openRootButton_->setEnabled(true);
    if (searchModelEdit_)
        searchModelEdit_->setEnabled(!busy);
    if (modelsTree_)
        modelsTree_->setEnabled(!busy);
    if (modelDetailsLabel_ && busy && !statusText.trimmed().isEmpty())
        modelDetailsLabel_->setText(statusText);
}

void ModelManagerPage::rebuildThumbnailCache()
{
    if (thumbCache_)
        thumbCache_->clear();
    if (gridView_)
        gridView_->viewport()->update();
    refreshInventory();
}

void ModelManagerPage::refreshInventory()
{
    if (!refreshWatcher_)
        return;
    if (refreshWatcher_->isRunning())
        return;

    emit inventoryRefreshStarted();
    const QString modelsRoot = resolveModelsRoot();
    const QString downloadsRoot = resolveDownloadsRoot();
    const QStringList extra = spellvision::shell::extraModelsRootsFromSettings();
    const QStringList roots = spellvision::shell::scannableModelsRoots(modelsRoot, extra);
    setRefreshBusy(true, QStringLiteral("Refreshing model inventory in background..."));
    refreshWatcher_->setFuture(QtConcurrent::run([modelsRoot, downloadsRoot, roots]() {
        RefreshResult merged = scanModelInventory(QString(), downloadsRoot);
        merged.modelsRoot = modelsRoot;
        for (const QString &root : roots)
        {
            const RefreshResult part = scanModelInventory(root, QString());
            merged.entries += part.entries;
            merged.imagePreviewCount += part.imagePreviewCount;
            merged.videoPreviewCount += part.videoPreviewCount;
            merged.metadataCount += part.metadataCount;
        }
        return merged;
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
    // A metadata refresh ENDS by rescanning the inventory, and re-selecting the row rebuilds the
    // inspector from disk -- which clears its status line. Measured on the live page: the outcome
    // of the refresh the user had just watched was on screen for about a second and then wiped by
    // its own follow-up. Re-assert it after the rebuild.
    syncMetadataRefreshRow();
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
            item->setText(0, entry.displayName.trimmed().isEmpty() ? entry.name : entry.displayName);
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

    // Read the setting ONCE per rebuild rather than per card: a QSettings hit inside a loop over
    // 759 weights is the kind of cost that only shows up on the owner's library.
    const int nsfwCeiling = spellvision::assets::nsfwPreviewCeiling();

    QVector<spellvision::assets::ModelCardModel::Card> cards;
    cards.reserve(entries_.size());
    for (const ModelEntry &e : entries_)
    {
        spellvision::assets::ModelCardModel::Card c;
        // The tooltip is the FILE. The card prints the display name when the site gave one --
        // the site's own title rather than loxsUtopicWorldKrea2_v20Quants.safetensors --
        // and the file on disk keeps its name, which is an explicit owner requirement.
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
        c.strippedName = e.displayName.trimmed().isEmpty() ? stripped : e.displayName.trimmed();
        c.type = e.type;
        c.kind = e.kind;
        c.family = e.family;
        // The sidecar's cover first (the picture the site publishes for this weight), then the
        // hand-placed `<stem>.png` the old S0 scan resolved. mp4 hover-play is S4.
        c.previewPath = e.coverPath.isEmpty() ? e.imagePreviewPath : e.coverPath;
        c.siteBadge = e.siteBadge;
        c.quantisation = e.quantisation;
        c.identification = static_cast<spellvision::assets::ModelIdentification>(e.identification);
        c.previewNsfwLevel = e.previewNsfwLevel;
        c.blurPreview = spellvision::assets::previewShouldBlur(e.previewNsfwLevel, nsfwCeiling);
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
    if (!familyFilterCombo_)
        return;

    QStringList families;
    families.reserve(entries_.size());
    for (const ModelEntry &e : entries_) {
        if (!e.family.trimmed().isEmpty())
            families.push_back(e.family.trimmed());
    }
    families.removeDuplicates();
    std::sort(families.begin(), families.end(), [](const QString &a, const QString &b) {
        return a.compare(b, Qt::CaseInsensitive) < 0;
    });

    const QString prevFamily = familyFilterCombo_->currentData().toString();

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

    if (cardProxy_)
        cardProxy_->setFamilyFilter(familyFilterCombo_->currentData().toString());
    rebuildKindTabs();
    applyTreeFilters();
}

void ModelManagerPage::rebuildKindTabs()
{
    if (!kindTabBar_)
        return;
    QStringList kinds;
    kinds.reserve(entries_.size());
    for (const ModelEntry &e : entries_)
        kinds.push_back(e.kind);
    kindTabBar_->setCounts(spellvision::assets::ModelKindTabs::counts(kinds));
    if (cardProxy_)
        cardProxy_->setKindTab(kindTabBar_->currentTabId());
}

void ModelManagerPage::applyTreeFilters()
{
    if (!modelsTree_)
        return;

    const QString needle = searchModelEdit_ ? searchModelEdit_->text().trimmed().toLower() : QString();
    const QString kindTab = kindTabBar_ ? kindTabBar_->currentTabId()
                                        : spellvision::assets::ModelKindTabs::allTabId();
    const QString familyFilter = familyFilterCombo_ ? familyFilterCombo_->currentData().toString() : QStringLiteral("All");
    const bool familyAll = familyFilter.isEmpty() || familyFilter.compare(QStringLiteral("All"), Qt::CaseInsensitive) == 0;

    // The tree row index is the entry index (applyEntries builds them in lockstep), so the list
    // view filters on the same `kind` the grid does rather than on the label in its Type column.
    for (int row = 0; row < modelsTree_->topLevelItemCount(); ++row) {
        QTreeWidgetItem *item = modelsTree_->topLevelItem(row);
        if (!item)
            continue;
        const QString type = item->text(1);
        const QString family = item->text(2);
        const QString kind = (row < entries_.size()) ? entries_.at(row).kind : QString();
        const QString haystack = QStringLiteral("%1 %2 %3 %4")
                                     .arg(item->text(0), type, family, item->data(0, Qt::UserRole).toString())
                                     .toLower();
        bool hide = false;
        if (!needle.isEmpty() && !haystack.contains(needle))
            hide = true;
        if (!spellvision::assets::ModelKindTabs::tabAccepts(kindTab, kind))
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

void ModelManagerPage::applyModelIntelReply(const QJsonObject &reply)
{
    if (inspectorPanel_)
        inspectorPanel_->applyWorkerReply(reply);
    // The controller runs SECOND so its ending is the one on screen. The panel re-reads the
    // sidecar a refresh just wrote; the controller writes what the pass actually did, including
    // the counts a "Metadata refreshed." would have covered up.
    if (refreshController_)
        refreshController_->applyWorkerReply(reply);
}

QStringList ModelManagerPage::currentModelRoots() const
{
    return spellvision::shell::scannableModelsRoots(
        resolveModelsRoot(),
        spellvision::shell::extraModelsRootsFromSettings());
}

void ModelManagerPage::syncMetadataRefreshRow()
{
    if (!refreshController_)
        return;
    const bool running = refreshController_->isRunning();

    if (metadataProgressRow_)
        metadataProgressRow_->setVisible(running);
    if (metadataRefreshButton_)
        metadataRefreshButton_->setEnabled(!running);
    if (metadataCancelButton_)
        metadataCancelButton_->setEnabled(refreshController_->canCancel());
    if (metadataProgressBar_)
    {
        const int percent = refreshController_->percent();
        if (percent < 0)
        {
            // Busy, not 0%. The worker has not counted the library yet, and a bar sitting at zero
            // for the minutes that takes is indistinguishable from one that is stuck.
            metadataProgressBar_->setRange(0, 0);
        }
        else
        {
            metadataProgressBar_->setRange(0, 100);
            metadataProgressBar_->setValue(percent);
        }
    }
    if (metadataProgressLabel_)
        metadataProgressLabel_->setText(refreshController_->progressText());

    // The inspector's own button and status line follow the same job: a library pass and a
    // per-model pass are the same command, and a second "Refresh metadata" that looks available
    // while one is running is a click that gets refused.
    if (inspectorPanel_)
    {
        inspectorPanel_->setRefreshBusy(running);
        if (!refreshController_->statusText().isEmpty())
            inspectorPanel_->setRefreshStatus(refreshController_->statusText(),
                                              refreshController_->statusIsError());
    }
    // Deliberately NOT the summary card: its first line is the library's own census (installed
    // assets, families, the models root), and writing the refresh outcome over it replaced a
    // standing fact with a transient one -- seen on the live page as "Examined 1 · 1 identified"
    // sitting where "Installed assets: 759" belongs. The refresh has two places of its own.
}

void ModelManagerPage::updateDetailsForRow(int row)
{
    if (!modelDetailsLabel_)
        return;

    auto hideExtras = [this]() {
        if (inspectorPanel_)
            inspectorPanel_->clear();
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

    if (deleteModelButton_)
        deleteModelButton_->setVisible(!e.path.trimmed().isEmpty());

    // Everything the sidecar knows -- the gallery, the description, the trigger words, the licence
    // and the settings this model publishes with their provenance -- is one unit, and it reads the
    // document itself rather than being handed four already-flattened strings.
    if (inspectorPanel_)
    {
        inspectorPanel_->setModelRoots(spellvision::shell::scannableModelsRoots(
            resolveModelsRoot(), spellvision::shell::extraModelsRootsFromSettings()));
        inspectorPanel_->showModel(e.path, e.name);
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
    setSurface(summaryCard, svstyle::Surface::Panel);
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

    // The Type combo is gone: the TAB is the type now (W5 Task 1). A combo whose vocabulary came
    // from a path substring could not name an embedding, and a filter you have to open to read
    // cannot show you that the library holds 23 LoRAs and one VAE.
    kindTabBar_ = new spellvision::assets::ModelKindTabBar(this);
    connect(kindTabBar_, &spellvision::assets::ModelKindTabBar::tabChanged, this,
            [this](const QString &tabId) {
                if (cardProxy_)
                    cardProxy_->setKindTab(tabId);
                applyTreeFilters();
            });

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
    setRole(gridToggleButton_, svstyle::Role::Chip);
    listToggleButton_ = new QPushButton(QStringLiteral("List"), this);
    listToggleButton_->setObjectName(QStringLiteral("ModelsViewToggle"));
    listToggleButton_->setCheckable(true);
    listToggleButton_->setCursor(Qt::PointingHandCursor);
    setRole(listToggleButton_, svstyle::Role::Chip);

    favoritesToggleButton_ = new QPushButton(QStringLiteral("★ Favorites"), this);
    favoritesToggleButton_->setObjectName(QStringLiteral("ModelsViewToggle"));
    favoritesToggleButton_->setCheckable(true);
    favoritesToggleButton_->setCursor(Qt::PointingHandCursor);
    setRole(favoritesToggleButton_, svstyle::Role::Chip);

    refreshButton_ = new QPushButton(QStringLiteral("Refresh Models"), this);
    refreshButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    refreshButton_->setCursor(Qt::PointingHandCursor);
    setRole(refreshButton_, svstyle::Role::Secondary);
    rebuildCacheButton_ = new QPushButton(QStringLiteral("Rebuild cache"), this);
    rebuildCacheButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    rebuildCacheButton_->setCursor(Qt::PointingHandCursor);
    setRole(rebuildCacheButton_, svstyle::Role::Secondary);
    rebuildCacheButton_->setToolTip(QStringLiteral("Delete generated thumbnails and rebuild them as you scroll."));
    openRootButton_ = new QPushButton(QStringLiteral("Open Models Root"), this);
    openRootButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    openRootButton_->setCursor(Qt::PointingHandCursor);
    setRole(openRootButton_, svstyle::Role::Secondary);
    addFolderButton_ = new QPushButton(QStringLiteral("Add folder…"), this);
    addFolderButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    addFolderButton_->setCursor(Qt::PointingHandCursor);
    setRole(addFolderButton_, svstyle::Role::Secondary);
    addFolderButton_->setToolTip(QStringLiteral("Also scan another drive or a removable disk. Locked or unplugged volumes are skipped."));

    // W5 Task 4. "Refresh Models" rescans the FOLDERS; this asks the site who each weight IS. Two
    // different questions that a single button could not answer, which is why the caption W2 wrote
    // ("run Refresh metadata on the Models page") had to be deleted rather than repointed.
    metadataRefreshButton_ = new QPushButton(QStringLiteral("Refresh metadata"), this);
    metadataRefreshButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    metadataRefreshButton_->setCursor(Qt::PointingHandCursor);
    setRole(metadataRefreshButton_, svstyle::Role::Secondary);
    metadataRefreshButton_->setToolTip(QStringLiteral(
        "Ask Civitai and Hugging Face who each weight is, and write what they say beside it: the "
        "name, the pictures, the trigger words and the settings it was published with.\n"
        "No account or API key is needed. The whole library takes a while — it runs in the "
        "background and you can stop it at any time."));

    auto *toolbarRow = new QHBoxLayout();
    toolbarRow->setSpacing(tight);
    toolbarRow->addWidget(searchModelEdit_, 1);
    toolbarRow->addWidget(familyFilterCombo_);
    toolbarRow->addWidget(favoritesToggleButton_);
    toolbarRow->addWidget(gridToggleButton_);
    toolbarRow->addWidget(listToggleButton_);
    toolbarRow->addWidget(refreshButton_);
    toolbarRow->addWidget(metadataRefreshButton_);
    toolbarRow->addWidget(rebuildCacheButton_);
    toolbarRow->addWidget(openRootButton_);
    toolbarRow->addWidget(addFolderButton_);

    // --- W5 Task 4: the metadata-refresh progress row ---
    //
    // Hidden entirely while nothing is running. A bar parked at 0% with no job behind it is a
    // claim about a denominator nobody counted, and on a page whose other long action already owns
    // the word "Refreshing" it would read as a second, stuck one.
    metadataProgressBar_ = new QProgressBar(this);
    metadataProgressBar_->setObjectName(QStringLiteral("ModelsMetadataProgress"));
    metadataProgressBar_->setTextVisible(false);
    metadataProgressBar_->setMinimumWidth(160);
    metadataProgressLabel_ = new spellvision::widgets::ElidingLabel(this);
    metadataProgressLabel_->setObjectName(QStringLiteral("ModelsMeta"));
    metadataCancelButton_ = new QPushButton(QStringLiteral("Stop"), this);
    metadataCancelButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    metadataCancelButton_->setCursor(Qt::PointingHandCursor);
    setRole(metadataCancelButton_, svstyle::Role::Secondary);

    metadataProgressRow_ = new QWidget(this);
    auto *metadataRow = new QHBoxLayout(metadataProgressRow_);
    metadataRow->setContentsMargins(0, 0, 0, 0);
    metadataRow->setSpacing(tight);
    metadataRow->addWidget(metadataProgressBar_);
    metadataRow->addWidget(metadataProgressLabel_, 1);
    metadataRow->addWidget(metadataCancelButton_);
    metadataProgressRow_->hide();

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
    // StyledPanel, not NoFrame: the surface and its hairline used to come from this page's
    // stylesheet, and SvStyle draws an item view's field panel through PE_Frame -- a view with no
    // frame asks for no primitive and would sit on the page with no edge at all.
    modelsTree_->setFrameShape(QFrame::StyledPanel);
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

    inspectorPanel_ = new spellvision::assets::ModelInspectorPanel(this);
    connect(inspectorPanel_, &spellvision::assets::ModelInspectorPanel::workerRequested,
            this, &ModelManagerPage::modelIntelRequested);
    connect(inspectorPanel_, &spellvision::assets::ModelInspectorPanel::applyRecommendedRequested,
            this, &ModelManagerPage::applyModelSettingsRequested);

    // W5 Task 4. ONE owner for the refresh conversation, shared by the per-model button in the
    // inspector and the library button in the toolbar -- otherwise the two actions can drift into
    // sending different wires for the same command, and only one of them carries the `files` list
    // that keeps a single model's refresh from reading 2.09 TB.
    refreshController_ = new spellvision::assets::ModelRefreshController(this);
    connect(refreshController_, &spellvision::assets::ModelRefreshController::workerRequested,
            this, &ModelManagerPage::modelIntelRequested);
    connect(refreshController_, &spellvision::assets::ModelRefreshController::stateChanged,
            this, &ModelManagerPage::syncMetadataRefreshRow);
    connect(refreshController_, &spellvision::assets::ModelRefreshController::refreshFinished,
            this, [this](const QString &weightPath, const QJsonObject &) {
                // The cockpit's cached answers were resolved from the sidecars this pass just
                // rewrote, so they are now claims nobody has re-checked.
                emit modelIntelRefreshFinished(weightPath);
                // And the CARD's kind is read at scan time, so a sidecar written just now does not
                // move a model between tabs until the inventory is read again.
                refreshInventory();
            });
    connect(inspectorPanel_, &spellvision::assets::ModelInspectorPanel::refreshRequested,
            this, [this](const QString &weightPath) {
                refreshController_->startModelRefresh(currentModelRoots(), weightPath);
            });

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
    setRole(bindWorkflowButton_, svstyle::Role::Secondary);
    useWorkflowButton_ = new QPushButton(QStringLiteral("Use workflow"), this);
    useWorkflowButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    useWorkflowButton_->setCursor(Qt::PointingHandCursor);
    setRole(useWorkflowButton_, svstyle::Role::Secondary);
    resolveDepsButton_ = new QPushButton(QStringLiteral("Resolve dependencies…"), this);
    resolveDepsButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    resolveDepsButton_->setCursor(Qt::PointingHandCursor);
    setRole(resolveDepsButton_, svstyle::Role::Secondary);
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
    setRole(downloadModelButton_, svstyle::Role::Secondary);
    downloadModelButton_->setToolTip(QStringLiteral("Paste a Civitai or Hugging Face link. Downloads in the background with progress."));
    deleteModelButton_ = new QPushButton(QStringLiteral("Delete…"), this);
    deleteModelButton_->setObjectName(QStringLiteral("ModelsDangerButton"));
    deleteModelButton_->setCursor(Qt::PointingHandCursor);
    setRole(deleteModelButton_, svstyle::Role::Danger);
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
    setSurface(detailsCard, svstyle::Surface::Panel);
    detailsCard->setMinimumHeight(168);
    detailsCard->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Maximum);
    auto *detailsCol = new QVBoxLayout(detailsCard);
    detailsCol->setContentsMargins(snug, snug, snug, snug);
    detailsCol->setSpacing(hair);
    detailsCol->addWidget(modelDetailsLabel_);
    detailsCol->addWidget(inspectorPanel_);
    detailsCol->addWidget(workflowBindingLabel_);
    detailsCol->addWidget(workflowNoteLabel_);
    detailsCol->addLayout(workflowRow);

    mainLayout->addLayout(headerCol);
    mainLayout->addWidget(summaryCard);
    mainLayout->addLayout(toolbarRow);
    mainLayout->addWidget(metadataProgressRow_);
    mainLayout->addWidget(kindTabBar_);
    mainLayout->addWidget(viewStack_, 1);
    mainLayout->addWidget(detailsCard, 0);

    connect(refreshButton_, &QPushButton::clicked, this, &ModelManagerPage::refreshInventory);
    connect(metadataRefreshButton_, &QPushButton::clicked, this, [this]() {
        refreshController_->startLibraryRefresh(currentModelRoots());
    });
    connect(metadataCancelButton_, &QPushButton::clicked, this, [this]() {
        refreshController_->cancel();
    });
    connect(rebuildCacheButton_, &QPushButton::clicked, this, &ModelManagerPage::rebuildThumbnailCache);
    connect(openRootButton_, &QPushButton::clicked, this, [this]()
    {
        const QString root = resolveModelsRoot();
        if (!root.trimmed().isEmpty())
            QDesktopServices::openUrl(QUrl::fromLocalFile(root));
    });
    connect(addFolderButton_, &QPushButton::clicked, this, [this]()
    {
        const QString chosen = QFileDialog::getExistingDirectory(
            this, QStringLiteral("Also look for models in"), resolveModelsRoot());
        if (chosen.trimmed().isEmpty())
            return;
        const QString path = QDir::fromNativeSeparators(QDir(chosen).absolutePath());
        QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        QStringList extra = settings.value(QStringLiteral("runtime/extraModelsRoots")).toStringList();
        if (!extra.contains(path) && path != resolveModelsRoot())
        {
            extra.append(path);
            settings.setValue(QStringLiteral("runtime/extraModelsRoots"), extra);
        }
        const QString comfyRoot = settings.value(QStringLiteral("runtime/comfyRoot")).toString().trimmed();
        if (!comfyRoot.isEmpty())
        {
            const QStringList libraries = spellvision::shell::scannableModelsRoots(resolveModelsRoot(), extra);
            spellvision::shell::writeManagedExtraModelPaths(
                QDir(comfyRoot).filePath(QStringLiteral("extra_model_paths.yaml")), libraries);
        }
        refreshInventory();
    });
    connect(modelsTree_, &QTreeWidget::itemSelectionChanged, this, &ModelManagerPage::updateModelDetails);
    connect(searchModelEdit_, &QLineEdit::textChanged, this, [this](const QString &text)
    {
        if (cardProxy_)
            cardProxy_->setNeedle(text); // filter the grid (primary view)
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
    //
    // Spacing and type only. The cards are Surface::Panel, the action buttons Role::Secondary, the
    // Delete button Role::Danger and the three view toggles Role::Chip, all set at their creation
    // sites -- so their fill, hairline and radius come from SvStyle and follow the material. The
    // tree's own surface is the style's field panel (it is a StyledPanel again for that reason),
    // its rows are PE_PanelItemViewItem and its header CE_HeaderSection; the palette carries the
    // text, the selection and the alternating row.
    //
    // The tree and its header keep @detail@ / @label@. A type token is not paint -- fontCss emits
    // font-size and font-weight and nothing else -- and the 11px face is the view's DENSITY, not
    // its decoration. Dropping it moved every view in this task to the 12px app font, which is a
    // different product decision wearing a retreat's clothes.
    setStyleSheet(QStringLiteral(
        "#ModelManagerPage { background: transparent; }"
        "QLabel#ModelsEyebrow { color: @acc@; @caption@ letter-spacing: 0.12em; text-transform: uppercase; }"
        "QLabel#ModelsTitle { color: @hi@; @display@ }"
        "QLabel#ModelsSummary { color: @hi@; @body@ }"
        "QLabel#ModelsMeta { color: @mid@; @detail@ }"
        "QLabel#ModelsDetailsText { color: @mid@; @detail@ }"
        "QLineEdit#ModelsSearch { padding: 7px 10px; }"
        "QTreeWidget#ModelsTree { @detail@ }"
        "QTreeWidget#ModelsTree::item { padding: 7px 8px; }"
        "QTreeWidget#ModelsTree QHeaderView::section { padding: 8px 8px; @label@ }"
        "QStackedWidget { background: transparent; }")
                      .replace(QLatin1String("@hi@"), theme.css(C::TextHi))
                      .replace(QLatin1String("@mid@"), theme.css(C::TextMid))
                      .replace(QLatin1String("@acc@"), theme.css(C::Accent))
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

void ModelManagerPage::dragEnterEvent(QDragEnterEvent *event)
{
    if (!event)
        return;
    const QMimeData *mime = event->mimeData();
    if (!mime) {
        event->ignore();
        return;
    }
    if (mime->hasUrls()) {
        event->acceptProposedAction();
        return;
    }
    const QString text = mime->text().trimmed();
    if (text.startsWith(QStringLiteral("http://"), Qt::CaseInsensitive)
        || text.startsWith(QStringLiteral("https://"), Qt::CaseInsensitive)) {
        event->acceptProposedAction();
        return;
    }
    event->ignore();
}

void ModelManagerPage::dropEvent(QDropEvent *event)
{
    if (!event)
        return;
    const QMimeData *mime = event->mimeData();
    if (!mime) {
        event->ignore();
        return;
    }
    QString reference;
    if (mime->hasUrls() && !mime->urls().isEmpty()) {
        const QUrl url = mime->urls().first();
        reference = url.isLocalFile() ? url.toLocalFile() : url.toString();
    } else {
        reference = mime->text().trimmed();
    }
    if (reference.isEmpty()) {
        event->ignore();
        return;
    }
    event->acceptProposedAction();
    handleDroppedReference(reference);
}

QString ModelManagerPage::destSubdirForWeight(const QString &fileName) const
{
    const QString n = fileName.toLower();
    if (n.contains(QStringLiteral("lora")))
        return QStringLiteral("loras");
    if (n.contains(QStringLiteral("vae")))
        return QStringLiteral("vae");
    if (n.contains(QStringLiteral("qwen3vl")) || n.contains(QStringLiteral("_txt"))
        || n.contains(QStringLiteral("clip")) || n.contains(QStringLiteral("umt5"))
        || n.contains(QStringLiteral("gemma")))
        return QStringLiteral("text_encoders");
    if (n.contains(QStringLiteral("krea2")) || n.contains(QStringLiteral("unet"))
        || n.contains(QStringLiteral("diffusion")))
        return QStringLiteral("diffusion_models");
    return QStringLiteral("checkpoints");
}

void ModelManagerPage::handleDroppedReference(const QString &reference)
{
    const QString trimmed = reference.trimmed();
    if (trimmed.startsWith(QStringLiteral("http://"), Qt::CaseInsensitive)
        || trimmed.startsWith(QStringLiteral("https://"), Qt::CaseInsensitive)) {
        emit downloadModelRequested(trimmed);
        return;
    }

    const QFileInfo src(trimmed);
    if (!src.exists() || !src.isFile()) {
        QMessageBox::warning(this, QStringLiteral("Drop model"),
                             QStringLiteral("Not a file: %1").arg(trimmed));
        return;
    }
    const QString suffix = src.suffix().toLower();
    static const QStringList okSuffixes = {
        QStringLiteral("safetensors"), QStringLiteral("ckpt"), QStringLiteral("pt"),
        QStringLiteral("pth"), QStringLiteral("bin"), QStringLiteral("gguf"),
        QStringLiteral("sft")};
    if (!okSuffixes.contains(suffix)) {
        QMessageBox::warning(this, QStringLiteral("Drop model"),
                             QStringLiteral("Unsupported weight suffix: .%1").arg(suffix));
        return;
    }

    const QString root = resolveModelsRoot().trimmed();
    if (root.isEmpty()) {
        QMessageBox::warning(this, QStringLiteral("Drop model"),
                             QStringLiteral("Choose a model library folder first."));
        return;
    }

    // Filename on disk is the identity. Display names live in sidecars — never rewrite the file.
    const QString destDir = QDir(root).filePath(destSubdirForWeight(src.fileName()));
    QDir().mkpath(destDir);
    const QString dest = QDir(destDir).filePath(src.fileName());
    if (QFileInfo::exists(dest)) {
        QMessageBox::information(this, QStringLiteral("Drop model"),
                                 QStringLiteral("Already in the library:\n%1").arg(QDir::toNativeSeparators(dest)));
        return;
    }
    if (!QFile::copy(src.absoluteFilePath(), dest)) {
        QMessageBox::warning(this, QStringLiteral("Drop model"),
                             QStringLiteral("Copy failed into:\n%1").arg(QDir::toNativeSeparators(dest)));
        return;
    }
    if (summaryLabel_)
        summaryLabel_->setText(QStringLiteral("Imported %1").arg(src.fileName()));
    refreshInventory();
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
