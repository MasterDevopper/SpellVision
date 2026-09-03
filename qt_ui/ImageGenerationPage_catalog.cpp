#include "ImageGenerationPage.h"
#include "generation/ErrorPillLabel.h"
#include "ImageGenerationPage_units.h"
#include "generation/OutputPathHelpers.h"
#include "generation/UpscaleController.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QComboBox>
#include <QCryptographicHash>
#include <QDir>
#include <QDoubleSpinBox>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QIODevice>
#include <QMessageBox>
#include <QTextStream>
#include <QVector>
#include <QFrame>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QPainter>
#include <QPixmap>
#include <QPushButton>
#include <QResizeEvent>
#include <QScrollArea>
#include <QImageReader>
#include <QSettings>
#include <QShowEvent>
#include <QSignalBlocker>
#include <QSlider>
#include <QSpinBox>
#include <QSplitter>
#include <QStackedWidget>
#include <QStandardPaths>
#include <QStringList>
#include <QTextEdit>
#include <QTimer>
#include <QtConcurrent>

using spellvision::assets::CatalogEntry;
using spellvision::assets::CatalogPickerDialog;
using spellvision::assets::humanImageFamily;
using spellvision::assets::humanVideoFamily;
using spellvision::assets::inferImageFamilyFromText;
using spellvision::assets::inferVideoFamilyFromText;
using spellvision::assets::persistRecentSelection;
using spellvision::assets::resolveCatalogValueByCandidates;
using spellvision::assets::scanCatalog;
using spellvision::assets::scanImageModelCatalog;
using spellvision::assets::scanVideoModelStackCatalog;
using spellvision::assets::shortDisplayFromValue;
using spellvision::generation::chooseComfyOutputPath;
using spellvision::generation::chooseModelsRootPath;
using spellvision::generation::salvageHuntPlate;
using spellvision::widgets::createSectionBody;
using spellvision::widgets::createSectionTitle;

namespace
{
CatalogEntry lastUserRecentSelection(const QVector<CatalogEntry> &entries, const QString &settingsKey)
{
    QSettings settings;
    const QStringList recents = settings.value(settingsKey).toStringList();
    for (const QString &recent : recents)
    {
        for (const CatalogEntry &entry : entries)
        {
            if (entry.value.compare(recent, Qt::CaseInsensitive) == 0)
                return entry;
        }
    }
    return CatalogEntry{};
}

CatalogEntry lastUserImageCheckpoint(const QVector<CatalogEntry> &entries)
{
    return lastUserRecentSelection(entries, QStringLiteral("image_generation/recent_checkpoints"));
}
} // namespace


void ImageGenerationPage::rescanModelCatalog()
{
    // Worker-ready recovery: a full idempotent rebuild that repopulates model
    // families from the (now-reachable) classifier. reloadCatalogs preserves the
    // selected model, so a mid-session re-scan doesn't disturb the user's pick.
    refreshModelCatalog();
}

void ImageGenerationPage::applyPersistedOutputFolder()
{
    if (!outputFolderLabel_)
        return;
    QSettings settings;
    const QString folder = settings.value(QStringLiteral("image_generation/output_folder")).toString().trimmed();
    if (!folder.isEmpty() && QDir(folder).exists())
        outputFolderLabel_->setText(QDir::toNativeSeparators(folder));
}

void ImageGenerationPage::refreshModelCatalog()
{
    if (catalogRefreshInFlight_ || !catalogRefreshWatcher_)
        return; // churn guard: a double-click / navigate-during-refresh must not stack scans

    catalogRefreshInFlight_ = true;
    if (refreshModelsButton_)
    {
        refreshModelsButton_->setEnabled(false);
        refreshModelsButton_->setText(QStringLiteral("Refreshing…"));
    }
    const QString modelsRoot = chooseModelsRootPath();
    const bool videoMode = isVideoMode();
    catalogRefreshWatcher_->setFuture(QtConcurrent::run([modelsRoot, videoMode]() {
        return scanCatalogs(modelsRoot, videoMode);
    }));
}

QString ImageGenerationPage::catalogSignature(const QString &root)
{
    // (path,size,mtime) hash of the model-bearing trees. Stat-only, no worker call
    // -> a few ms, safe to run on every navigate to gate the expensive rescan.
    if (root.trimmed().isEmpty())
        return QString();

    const QStringList subDirs = {QStringLiteral("checkpoints"), QStringLiteral("loras"),
                                 QStringLiteral("diffusion_models"), QStringLiteral("video")};
    const QStringList filters = spellvision::assets::modelNameFilters();

    QStringList records;
    for (const QString &sub : subDirs)
    {
        const QString dirPath = QDir(root).filePath(sub);
        if (!QDir(dirPath).exists())
            continue;
        QDirIterator it(dirPath, filters, QDir::Files, QDirIterator::Subdirectories);
        while (it.hasNext())
        {
            it.next();
            const QFileInfo fi = it.fileInfo();
            records << QStringLiteral("%1|%2|%3")
                           .arg(fi.absoluteFilePath())
                           .arg(fi.size())
                           .arg(fi.lastModified().toMSecsSinceEpoch());
        }
    }
    records.sort(); // stable regardless of FS enumeration order
    QCryptographicHash hash(QCryptographicHash::Md5);
    for (const QString &record : records)
        hash.addData(record.toUtf8());
    return QString::fromLatin1(hash.result().toHex());
}

void ImageGenerationPage::reloadCatalogs()
{
    refreshModelCatalog();
}

ImageGenerationPage::CatalogRefreshResult ImageGenerationPage::scanCatalogs(
    const QString &modelsRoot,
    bool videoMode)
{
    CatalogRefreshResult result;
    result.root = modelsRoot;
    result.models = videoMode
        ? scanVideoModelStackCatalog(modelsRoot)
        : scanImageModelCatalog(modelsRoot);
    result.loras = scanCatalog(modelsRoot, QStringLiteral("loras"));
    result.upscaleModels = scanCatalog(modelsRoot, QStringLiteral("upscale_models"));
    if (result.upscaleModels.isEmpty())
        result.upscaleModels = scanCatalog(modelsRoot, QStringLiteral("upscale"));
    result.signature = catalogSignature(modelsRoot);
    return result;
}

void ImageGenerationPage::applyCatalogRefreshResult(const CatalogRefreshResult &result)
{
    modelsRootDir_ = result.root;

    updateAssetIntelligenceUi();

    const QVector<CatalogEntry> &modelEntries = result.models;
    modelDisplayByValue_.clear();
    modelFamilyByValue_.clear();
    modelModalityByValue_.clear();
    modelRoleByValue_.clear();
    modelNoteByValue_.clear();
    modelStackByValue_.clear();
    for (const CatalogEntry &entry : modelEntries)
    {
        modelDisplayByValue_.insert(entry.value, entry.display);
        modelFamilyByValue_.insert(entry.value, entry.family);
        modelModalityByValue_.insert(entry.value, entry.modality);
        modelRoleByValue_.insert(entry.value, entry.role);
        modelNoteByValue_.insert(entry.value, entry.note);
        if (!entry.metadata.isEmpty())
            modelStackByValue_.insert(entry.value, entry.metadata);
    }

    populateVideoComponentControls();

    const QString priorModel = selectedModelPath_;
    if (!priorModel.trimmed().isEmpty())
        setSelectedModel(priorModel, resolveSelectedModelDisplay(priorModel));
    else if (!modelEntries.isEmpty())
    {
        const QString recentsKey = isVideoMode()
                                       ? QStringLiteral("image_generation/recent_video_model_stacks")
                                       : QStringLiteral("image_generation/recent_checkpoints");
        const CatalogEntry last = lastUserRecentSelection(modelEntries, recentsKey);
        if (!last.value.trimmed().isEmpty())
            setSelectedModel(last.value, last.display);
        else
            setSelectedModel(QString(), QString());
    }
    else
        setSelectedModel(QString(), QString());

    loraDisplayByValue_.clear();
    for (const CatalogEntry &entry : result.loras)
        loraDisplayByValue_.insert(entry.value, entry.display);

    for (LoraStackEntry &entry : loraStack_)
    {
        if (entry.display.trimmed().isEmpty())
            entry.display = resolveLoraDisplay(entry.value);
    }

    refreshSelectedModelUi();
    rebuildLoraStackUi();

    if (workflowCombo_)
        workflowCombo_->setToolTip(currentComboValue(workflowCombo_));

    // Remember what this scan saw, so the on-navigate dirty-check can compare the
    // current disk state against it and skip the expensive rescan when unchanged.
    lastCatalogSignature_ = result.signature;
    reloadUpscaleModelCatalog(result.upscaleModels);
}

void ImageGenerationPage::onCatalogRefreshFinished()
{
    if (!catalogRefreshWatcher_)
        return;
    const CatalogRefreshResult result = catalogRefreshWatcher_->result();
    catalogRefreshInFlight_ = false;
    if (result.root != chooseModelsRootPath())
    {
        refreshModelCatalog();
        return;
    }
    applyCatalogRefreshResult(result);
    if (refreshModelsButton_)
    {
        refreshModelsButton_->setText(QStringLiteral("Refresh"));
        refreshModelsButton_->setEnabled(true);
    }
}

void ImageGenerationPage::checkCatalogSignatureAsync()
{
    if (!catalogSignatureWatcher_ || catalogSignatureWatcher_->isRunning()
        || catalogRefreshInFlight_ || lastCatalogSignature_.isEmpty())
        return;
    catalogSignatureRoot_ = chooseModelsRootPath();
    const QString modelsRoot = catalogSignatureRoot_;
    catalogSignatureWatcher_->setFuture(QtConcurrent::run([modelsRoot]() {
        return catalogSignature(modelsRoot);
    }));
}

void ImageGenerationPage::onCatalogSignatureFinished()
{
    if (!catalogSignatureWatcher_ || catalogRefreshInFlight_)
        return;
    if (catalogSignatureRoot_ != chooseModelsRootPath())
        return;
    if (catalogSignatureWatcher_->result() != lastCatalogSignature_)
        refreshModelCatalog();
}

void ImageGenerationPage::showCheckpointPicker()
{
    QVector<CatalogEntry> checkpoints;
    checkpoints.reserve(modelDisplayByValue_.size());
    for (auto it = modelDisplayByValue_.constBegin(); it != modelDisplayByValue_.constEnd(); ++it)
        checkpoints.push_back({it.value(), it.key()});

    CatalogPickerDialog dialog(isVideoMode() ? QStringLiteral("Choose Video Model Stack") : QStringLiteral("Choose Checkpoint"),
                                checkpoints,
                                selectedModelPath_,
                                isVideoMode() ? QStringLiteral("image_generation/recent_video_model_stacks") : QStringLiteral("image_generation/recent_checkpoints"),
                                this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    setSelectedModel(dialog.selectedValue(), dialog.selectedDisplay());
    persistRecentSelection(isVideoMode() ? QStringLiteral("image_generation/recent_video_model_stacks") : QStringLiteral("image_generation/recent_checkpoints"), dialog.selectedValue());
    scheduleUiRefresh(0);
}

void ImageGenerationPage::showLoraPicker()
{
    QVector<CatalogEntry> loras;
    loras.reserve(loraDisplayByValue_.size());
    for (auto it = loraDisplayByValue_.constBegin(); it != loraDisplayByValue_.constEnd(); ++it)
        loras.push_back({it.value(), it.key()});

    CatalogPickerDialog dialog(QStringLiteral("Add LoRA to Stack"), loras, QString(), QStringLiteral("image_generation/recent_loras"), this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    addLoraToStack(dialog.selectedValue(), dialog.selectedDisplay(), 1.0, true);
    persistRecentSelection(QStringLiteral("image_generation/recent_loras"), dialog.selectedValue());
    scheduleUiRefresh(0);
}

void ImageGenerationPage::setSelectedModel(const QString &value, const QString &display)
{
    const bool modelChanged = value.trimmed().compare(selectedModelPath_, Qt::CaseInsensitive) != 0;
    selectedModelPath_ = value.trimmed();
    selectedModelDisplay_ = display.trimmed().isEmpty() ? resolveSelectedModelDisplay(selectedModelPath_) : display.trimmed();
    refreshSelectedModelUi();
    updatePrimaryActionAvailability();
    // A2: resolve the compatible component stack OFF the current signal-handler stack. The worker
    // round-trip runs a nested event loop; calling it inline from a combo-change handler re-enters
    // the UI (with the combo popup possibly still open) and crashes. singleShot(0) runs it clean.
    if (modelChanged && isVideoMode() && componentStackResolver_ && !selectedModelPath_.trimmed().isEmpty())
        QTimer::singleShot(0, this, [this]() { resolveAndApplyVideoComponents(); });
    else if (modelChanged)
        updateOperatingPointSelector();
}

void ImageGenerationPage::resolveAndApplyVideoComponents()
{
    maybeAutoPopulateVideoComponents();            // worker resolve (deferred -> clean stack)
    syncVideoComponentControlsFromSelectedStack(); // apply the stored results + constrain the menus
    updateAssetIntelligenceUi();                   // surface T3 (missing required) in readiness
    updateOperatingPointSelector();                // the resolved family may have changed -> refresh
}

void ImageGenerationPage::refreshSelectedModelUi()
{
    if (selectedModelLabel_)
    {
        if (selectedModelPath_.trimmed().isEmpty())
            selectedModelLabel_->setText(isVideoMode() ? QStringLiteral("No video model stack selected") : QStringLiteral("No checkpoint selected"));
        else
        {
            const QString shown = selectedModelDisplay_.isEmpty()
                                      ? shortDisplayFromValue(selectedModelPath_)
                                      : selectedModelDisplay_;
            QString labelText = shown;
            const QString note = modelNoteByValue_.value(selectedModelPath_).trimmed();
            if (isVideoMode() && !note.isEmpty())
                labelText += QStringLiteral("\n%1").arg(note);
            selectedModelLabel_->setText(labelText);
        }
        selectedModelLabel_->setToolTip(selectedModelPath_);
    }

    if (clearModelButton_)
        clearModelButton_->setEnabled(!selectedModelPath_.trimmed().isEmpty());

    syncVideoComponentControlsFromSelectedStack();
    updateVideoFamilyUi();
    updateVideoStackModeUi();
    updateAssetIntelligenceUi();
}

QString ImageGenerationPage::resolveSelectedModelDisplay(const QString &value) const
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return QString();

    const auto it = modelDisplayByValue_.constFind(trimmed);
    if (it != modelDisplayByValue_.constEnd())
        return it.value();

    return shortDisplayFromValue(trimmed);
}

QString ImageGenerationPage::resolveLoraDisplay(const QString &value) const
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return QString();

    const auto it = loraDisplayByValue_.constFind(trimmed);
    if (it != loraDisplayByValue_.constEnd())
        return it.value();

    return shortDisplayFromValue(trimmed);
}

bool ImageGenerationPage::applyModelHandoff(const QString &value, const QString &display)
{
    QStringList candidates{value};
    if (!display.trimmed().isEmpty())
        candidates << display;
    candidates << shortDisplayFromValue(value);
    return trySetSelectedModelByCandidate(candidates);
}

bool ImageGenerationPage::applyLoraHandoff(const QString &value, const QString &display, double weight)
{
    QStringList candidates{value};
    if (!display.trimmed().isEmpty())
        candidates << display;
    candidates << shortDisplayFromValue(value);
    return tryAddLoraByCandidate(candidates, weight, true);
}

void ImageGenerationPage::appendTriggerWords(const QStringList &words)
{
    if (!promptEdit_ || words.isEmpty())
        return;

    QString prompt = promptEdit_->toPlainText();
    const QString haystack = prompt.toLower();

    QStringList toAdd;
    for (const QString &word : words)
    {
        const QString trimmed = word.trimmed();
        if (!trimmed.isEmpty() && !haystack.contains(trimmed.toLower()))
            toAdd << trimmed;
    }
    if (toAdd.isEmpty())
        return;

    const QString addition = toAdd.join(QStringLiteral(", "));
    const QString existing = prompt.trimmed();
    if (existing.isEmpty())
        prompt = addition;
    else
        prompt = existing.endsWith(QLatin1Char(',')) ? existing + QLatin1Char(' ') + addition
                                                      : existing + QStringLiteral(", ") + addition;
    promptEdit_->setPlainText(prompt);
}

bool ImageGenerationPage::trySetSelectedModelByCandidate(const QStringList &candidates)
{
    QVector<CatalogEntry> checkpoints;
    checkpoints.reserve(modelDisplayByValue_.size());
    for (auto it = modelDisplayByValue_.constBegin(); it != modelDisplayByValue_.constEnd(); ++it)
        checkpoints.push_back({it.value(), it.key()});

    const QString match = resolveCatalogValueByCandidates(checkpoints, candidates);
    if (match.isEmpty())
        return false;

    setSelectedModel(match, resolveSelectedModelDisplay(match));
    return true;
}

bool ImageGenerationPage::tryAddLoraByCandidate(const QStringList &candidates, double weight, bool enabled)
{
    QVector<CatalogEntry> loras;
    loras.reserve(loraDisplayByValue_.size());
    for (auto it = loraDisplayByValue_.constBegin(); it != loraDisplayByValue_.constEnd(); ++it)
        loras.push_back({it.value(), it.key()});

    const QString match = resolveCatalogValueByCandidates(loras, candidates);
    if (match.isEmpty())
        return false;

    addLoraToStack(match, resolveLoraDisplay(match), weight, enabled);
    return true;
}

void ImageGenerationPage::addLoraToStack(const QString &value, const QString &display, double weight, bool enabled)
{
    const QString trimmed = ModelStackState::normalizedPath(value);
    if (trimmed.isEmpty())
        return;

    const QString resolvedDisplay = display.trimmed().isEmpty() ? resolveLoraDisplay(trimmed) : display.trimmed();
    if (loraStackController_)
    {
        loraStackController_->addOrUpdate(trimmed, resolvedDisplay, weight, enabled);
        persistRecentSelection(QStringLiteral("image_generation/recent_loras"), trimmed);
        return;
    }

    LoraStackEntry entry;
    entry.value = trimmed;
    entry.display = resolvedDisplay;
    entry.weight = weight;
    entry.enabled = enabled;

    ModelStackState::upsertLora(loraStack_, entry);
    persistRecentSelection(QStringLiteral("image_generation/recent_loras"), trimmed);
    rebuildLoraStackUi();
}

void ImageGenerationPage::replaceLoraStackEntry(int index)
{
    if (index < 0 || index >= loraStack_.size())
        return;

    QVector<CatalogEntry> loras;
    loras.reserve(loraDisplayByValue_.size());
    for (auto it = loraDisplayByValue_.constBegin(); it != loraDisplayByValue_.constEnd(); ++it)
        loras.push_back({it.value(), it.key()});

    CatalogPickerDialog dialog(QStringLiteral("Replace LoRA"), loras, loraStack_[index].value, QStringLiteral("image_generation/recent_loras"), this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    const QString value = dialog.selectedValue().trimmed();
    const QString display = dialog.selectedDisplay().trimmed().isEmpty() ? resolveLoraDisplay(value) : dialog.selectedDisplay().trimmed();
    if (loraStackController_)
        loraStackController_->replaceAt(index, value, display);
    else
    {
        loraStack_[index].value = value;
        loraStack_[index].display = display;
        rebuildLoraStackUi();
        scheduleUiRefresh(0);
    }

    persistRecentSelection(QStringLiteral("image_generation/recent_loras"), value);
}

void ImageGenerationPage::rebuildLoraStackUi()
{
    if (loraStackController_)
    {
        loraStackController_->rebuild();
        updateAssetIntelligenceUi();
        return;
    }

    if (loraStackSummaryLabel_)
        loraStackSummaryLabel_->setText(ModelStackState::summaryText(loraStack_));
    if (clearLorasButton_)
        clearLorasButton_->setEnabled(!loraStack_.isEmpty());

    updateAssetIntelligenceUi();
}

void ImageGenerationPage::refreshEmbeddingLabels()
{
    if (positiveEmbeddingLabel_) {
        if (positiveEmbeddingDisplays_.isEmpty())
            positiveEmbeddingLabel_->setText(QStringLiteral("Positive: none"));
        else
            positiveEmbeddingLabel_->setText(QStringLiteral("Positive: %1").arg(positiveEmbeddingDisplays_.join(QStringLiteral(", "))));
    }
    if (negativeEmbeddingLabel_) {
        if (negativeEmbeddingDisplays_.isEmpty())
            negativeEmbeddingLabel_->setText(QStringLiteral("Negative: none"));
        else
            negativeEmbeddingLabel_->setText(QStringLiteral("Negative: %1").arg(negativeEmbeddingDisplays_.join(QStringLiteral(", "))));
    }
}

void ImageGenerationPage::chooseOutputFolder()
{
    const QString current = outputFolderLabel_ ? outputFolderLabel_->text().trimmed() : QString();
    const QString chosen = QFileDialog::getExistingDirectory(this, QStringLiteral("Output folder"), current);
    if (chosen.trimmed().isEmpty() || !outputFolderLabel_)
        return;
    const QString normalized = QDir::fromNativeSeparators(QDir(chosen).absolutePath());
    outputFolderLabel_->setText(QDir::toNativeSeparators(normalized));
    QSettings settings;
    settings.setValue(QStringLiteral("image_generation/output_folder"), normalized);
}

void ImageGenerationPage::queueHuntList()
{
    const QString blockReason = readinessBlockReason();
    if (!blockReason.isEmpty())
    {
        QMessageBox::information(this, QStringLiteral("Queue list"), blockReason);
        return;
    }

    const QString path = QFileDialog::getOpenFileName(
        this,
        QStringLiteral("Queue named job list"),
        QString(),
        QStringLiteral("Text (*.txt *.tsv *.csv);;All files (*.*)"));
    if (path.trimmed().isEmpty())
        return;

    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
    {
        QMessageBox::warning(this, QStringLiteral("Queue list"), QStringLiteral("Could not read the list file."));
        return;
    }

    struct HuntJob
    {
        QString stem;
        int seed = 0;
        QString prompt;
    };
    QVector<HuntJob> jobs;
    QTextStream in(&file);
    while (!in.atEnd())
    {
        const QString raw = in.readLine().trimmed();
        if (raw.isEmpty() || raw.startsWith(QLatin1Char('#')))
            continue;
        QString line = raw;
        line.replace(QLatin1Char('\t'), QStringLiteral(" | "));
        const QStringList parts = line.split(QStringLiteral(" | "), Qt::KeepEmptyParts);
        if (parts.size() < 3)
        {
            QMessageBox::warning(this,
                                 QStringLiteral("Queue list"),
                                 QStringLiteral("Each line must be: stem | seed | prompt\nOffending line:\n%1").arg(raw));
            return;
        }
        HuntJob job;
        job.stem = parts.at(0).trimmed();
        bool ok = false;
        job.seed = parts.at(1).trimmed().toInt(&ok);
        if (!ok)
            job.seed = 0;
        job.prompt = QStringList(parts.mid(2)).join(QStringLiteral(" | ")).trimmed();
        if (job.stem.isEmpty() || job.prompt.isEmpty())
            continue;
        jobs.push_back(job);
    }
    if (jobs.isEmpty())
    {
        QMessageBox::information(this, QStringLiteral("Queue list"), QStringLiteral("No jobs in that file."));
        return;
    }

    const QString savedPrompt = promptEdit_ ? promptEdit_->toPlainText() : QString();
    const int savedSeed = sampling_ && sampling_->seedSpin() ? sampling_->seedSpin()->value() : 0;
    const QString savedPrefix = outputPrefixEdit_ ? outputPrefixEdit_->text() : QString();

    int queued = 0;
    int skipped = 0;
    int salvaged = 0;
    const QString dest = outputFolderLabel_
                             ? QDir::fromNativeSeparators(QDir(outputFolderLabel_->text().trimmed()).absolutePath())
                             : QString();
    const QString comfyOut = QDir::fromNativeSeparators(chooseComfyOutputPath());
    const bool huntLayout = !dest.isEmpty() && dest.compare(comfyOut, Qt::CaseInsensitive) != 0;
    for (const HuntJob &job : jobs)
    {
        if (huntLayout)
        {
            const QString plate = QDir(QDir(dest).filePath(job.stem)).filePath(QStringLiteral("plate.png"));
            if (QFileInfo::exists(plate) && QFileInfo(plate).size() > 40960)
            {
                ++skipped;
                continue;
            }
            if (salvageHuntPlate(dest, job.stem, comfyOut))
            {
                ++salvaged;
                continue;
            }
        }
        if (promptEdit_)
            promptEdit_->setPlainText(job.prompt);
        if (sampling_ && sampling_->seedSpin())
            sampling_->seedSpin()->setValue(job.seed);
        if (outputPrefixEdit_)
            outputPrefixEdit_->setText(job.stem);
        persistWorkspaceSettings();
        emit generateRequested(buildRequestPayload());
        ++queued;
    }

    if (promptEdit_)
        promptEdit_->setPlainText(savedPrompt);
    if (sampling_ && sampling_->seedSpin())
        sampling_->seedSpin()->setValue(savedSeed);
    if (outputPrefixEdit_)
        outputPrefixEdit_->setText(savedPrefix);
    persistWorkspaceSettings();

    QMessageBox::information(this,
                             QStringLiteral("Queue list"),
                             QStringLiteral("Queued %1 named job(s), skipped %2 existing plate.png, salvaged %3 from Comfy output.")
                                 .arg(queued)
                                 .arg(skipped)
                                 .arg(salvaged));
}

void ImageGenerationPage::pickPositiveEmbedding()
{
    using namespace spellvision::assets;
    const QString root = modelsRootDir_.isEmpty() ? chooseModelsRootPath() : modelsRootDir_;
    QVector<CatalogEntry> entries = scanCatalog(root, QStringLiteral("embeddings"));
    if (entries.isEmpty())
        entries = scanCatalog(root, QStringLiteral("embeddings/SDXL"));
    if (entries.isEmpty()) {
        if (readinessHintLabel_)
            readinessHintLabel_->setText(QStringLiteral("No embeddings found under models/embeddings."));
        return;
    }
    CatalogPickerDialog dlg(QStringLiteral("Positive embedding"), entries, QString(),
                            QStringLiteral("image_generation/recent_embeddings_pos"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    const QString v = dlg.selectedValue();
    if (v.isEmpty() || positiveEmbeddings_.contains(v))
        return;
    positiveEmbeddings_.push_back(v);
    positiveEmbeddingDisplays_.push_back(dlg.selectedDisplay().isEmpty() ? QFileInfo(v).completeBaseName()
                                                                         : dlg.selectedDisplay());
    persistRecentSelection(QStringLiteral("image_generation/recent_embeddings_pos"), v);
    refreshEmbeddingLabels();
}

void ImageGenerationPage::pickNegativeEmbedding()
{
    using namespace spellvision::assets;
    const QString root = modelsRootDir_.isEmpty() ? chooseModelsRootPath() : modelsRootDir_;
    QVector<CatalogEntry> entries = scanCatalog(root, QStringLiteral("embeddings"));
    if (entries.isEmpty())
        entries = scanCatalog(root, QStringLiteral("embeddings/SDXL"));
    if (entries.isEmpty()) {
        if (readinessHintLabel_)
            readinessHintLabel_->setText(QStringLiteral("No embeddings found under models/embeddings."));
        return;
    }
    CatalogPickerDialog dlg(QStringLiteral("Negative embedding"), entries, QString(),
                            QStringLiteral("image_generation/recent_embeddings_neg"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    const QString v = dlg.selectedValue();
    if (v.isEmpty() || negativeEmbeddings_.contains(v))
        return;
    negativeEmbeddings_.push_back(v);
    negativeEmbeddingDisplays_.push_back(dlg.selectedDisplay().isEmpty() ? QFileInfo(v).completeBaseName()
                                                                         : dlg.selectedDisplay());
    persistRecentSelection(QStringLiteral("image_generation/recent_embeddings_neg"), v);
    refreshEmbeddingLabels();
}

void ImageGenerationPage::clearEmbeddings()
{
    positiveEmbeddings_.clear();
    negativeEmbeddings_.clear();
    positiveEmbeddingDisplays_.clear();
    negativeEmbeddingDisplays_.clear();
    refreshEmbeddingLabels();
}

void ImageGenerationPage::reloadUpscaleModelCatalog(
    const QVector<spellvision::assets::CatalogEntry> &entries)
{
    if (upscale_)
        upscale_->setModelCatalog(entries);
}

void ImageGenerationPage::acceptDroppedWorkflow(const QString &path)
{
    const QString normalized = QDir::fromNativeSeparators(path.trimmed());
    if (normalized.isEmpty() || !QFileInfo::exists(normalized))
        return;
    if (!normalized.endsWith(QStringLiteral(".json"), Qt::CaseInsensitive)
        && !normalized.endsWith(QStringLiteral(".api.json"), Qt::CaseInsensitive)) {
        if (workflowDropLabel_)
            workflowDropLabel_->setText(QStringLiteral("Need a .json workflow file"));
        return;
    }
    pendingWorkflowPath_ = normalized;
    if (workflowDropLabel_)
        workflowDropLabel_->setText(QStringLiteral("Loaded: %1").arg(QFileInfo(normalized).fileName()));
    if (runWorkflowButton_)
        runWorkflowButton_->setEnabled(true);
    // Import + draft open via MainWindow (source of truth for worker import).
    emit workflowFileDropped(normalized);
}

void ImageGenerationPage::browseWorkflowFile()
{
    const QString path = QFileDialog::getOpenFileName(
        this, QStringLiteral("Load Comfy workflow"), QString(),
        QStringLiteral("Comfy workflows (*.json);;All files (*.*)"));
    if (!path.isEmpty())
        acceptDroppedWorkflow(path);
}

void ImageGenerationPage::runPendingWorkflow()
{
    if (pendingWorkflowPath_.isEmpty()) {
        browseWorkflowFile();
        return;
    }
    // Re-emit so MainWindow can import + launch (queue), not only draft.
    emit workflowFileDropped(pendingWorkflowPath_);
}

void ImageGenerationPage::applyTheme()
{
    setStyleSheet(ThemeManager::instance().imageGenerationStyleSheet());
    applyThemeStyling();
}

// Phase 8: re-apply the per-widget (member) cockpit styling from tokens so these widgets
// switch live with the theme. buildUi sets the same token-based values at construction
// (boot-correctness + a clean bleed audit); this method re-runs on every themeChanged via
// applyTheme(), which is why the members re-color on a live switch. Local-only chrome (the
// IMG chip, NEG label, empty-canvas glow, segmented frame) is tokenized inline in buildUi
// and is boot-correct, but those are not members so they are not re-driven here.

void ImageGenerationPage::applyThemeStyling()
{
    const auto &tm = ThemeManager::instance();

    if (videoFamilyResolvesLabel_)
        videoFamilyResolvesLabel_->setStyleSheet(QStringLiteral(
            "font-family:'JetBrains Mono',monospace;font-size:10px;color:%1;background:transparent;border:0;")
            .arg(tm.css(ThemeManager::Color::TextLo)));

    const QString segButtonStyle = QStringLiteral(
        "QPushButton{border:1px solid transparent;border-radius:6px;padding:3px 13px;font-size:11px;"
        "color:%1;background:transparent;}"
        "QPushButton:checked{color:%2;background:%3;border:1px solid %4;}")
        .arg(tm.css(ThemeManager::Color::TextMid),
             tm.css(ThemeManager::Color::TextHi),
             tm.css(ThemeManager::Color::AccentSubtle),
             rgbaToken(ThemeManager::Color::Accent, 0.40));
    for (QPushButton *b : {videoFamilyAutoButton_, videoFamilyWanButton_, videoFamilyLtxButton_})
        if (b)
            b->setStyleSheet(segButtonStyle);

    // Phase 3b: the Speed selector's segmented buttons (created dynamically -> style via the card so
    // children inherit it and it re-colors on a theme switch).
    if (operatingPointCard_)
        operatingPointCard_->setStyleSheet(QStringLiteral(
            "#OperatingPointLabel{color:%1;font-size:11px;font-weight:700;background:transparent;}"
            "#OperatingPointButton{border:1px solid %2;border-radius:6px;padding:4px 14px;font-size:11px;color:%3;background:transparent;}"
            "#OperatingPointButton:checked{color:%4;background:%5;border:1px solid %6;}")
            .arg(tm.css(ThemeManager::Color::TextHi),
                 tm.css(ThemeManager::Color::Border),
                 tm.css(ThemeManager::Color::TextMid),
                 tm.css(ThemeManager::Color::TextHi),
                 tm.css(ThemeManager::Color::AccentSubtle),
                 rgbaToken(ThemeManager::Color::Accent, 0.40)));

    if (inputChipHint_)
        inputChipHint_->setStyleSheet(QStringLiteral("color:%1;font-size:9px;background:transparent;border:0;")
            .arg(tm.css(ThemeManager::Color::TextMid)));
    if (inputChipClear_)
        inputChipClear_->setStyleSheet(QStringLiteral(
            "#PromptInputClear{background:%1;color:%2;border:0;border-radius:5px;font-size:12px;}")
            .arg(rgbaToken(ThemeManager::Color::Surface0, 0.78), tm.css(ThemeManager::Color::TextHi)));
    if (inputChipDropzone_)
    {
        const bool loaded = inputChipThumb_ && inputChipThumb_->isVisible();
        inputChipDropzone_->setStyleSheet(loaded
            ? QStringLiteral("#PromptInputDropzone{border:1px solid %1;border-radius:9px;background:%2;}")
                  .arg(rgbaToken(ThemeManager::Color::Success, 0.35), rgbaToken(ThemeManager::Color::Surface0, 0.50))
            : QStringLiteral("#PromptInputDropzone{border:1px dashed %1;border-radius:9px;background:%2;}")
                  .arg(rgbaToken(ThemeManager::Color::Border, 0.30), rgbaToken(ThemeManager::Color::Surface0, 0.30)));
    }

    if (canvasEmptyTitle_)
        canvasEmptyTitle_->setStyleSheet(QStringLiteral(
            "color:%1;font-size:14px;letter-spacing:0.3px;background:transparent;border:0;")
            .arg(tm.css(ThemeManager::Color::TextMid)));
    if (canvasEmptySub_)
        canvasEmptySub_->setStyleSheet(QStringLiteral("color:%1;font-size:12px;background:transparent;border:0;")
            .arg(tm.css(ThemeManager::Color::TextLo)));
    const QString chipStyle = QStringLiteral(
        "font-family:'JetBrains Mono',monospace;font-size:10px;color:%1;"
        "border:1px solid %2;border-radius:5px;padding:3px 8px;background:transparent;")
        .arg(tm.css(ThemeManager::Color::TextLo), tm.css(ThemeManager::Color::Border));
    for (QLabel *c : {canvasEmptyChipDim_, canvasEmptyChipSteps_, canvasEmptyChipCfg_})
        if (c)
            c->setStyleSheet(chipStyle);

    // Dynamic-state widget: re-invoke with its current state so it re-reads the tokens.
    if (negativeToggleButton_)
        setNegativePromptVisible(negativeRow_ && negativeRow_->isVisible());
}

void ImageGenerationPage::updateDisclosure(bool advanced)
{
    advanced_ = advanced;

    // Phase 7 step 2: Output-tab raw knobs are Advanced-only (Width / Height / Batch / Prefix);
    // Preset (Quality) stays Simple. HIDE-not-delete -- the rows keep their values and the request
    // builder reads by member (draft.width = widthSpin_->value(), never visibility-gated), so a
    // value set in Advanced still drives generation in Simple. These rows carry NO existing
    // visibility guard, so the gate is a plain setVisible(advanced) (rows that DO have a mode/family
    // guard must AND with it -- handled per-row as later tabs are added).
    if (widthRow_)
        widthRow_->setVisible(advanced);
    if (heightRow_)
        heightRow_->setVisible(advanced);
    if (batchRow_)
        batchRow_->setVisible(advanced);
    if (prefixRow_)
        prefixRow_->setVisible(advanced);
    const bool image = !isVideoMode();
    if (embeddingRow_)
        embeddingRow_->setVisible(advanced && image);
    // Phase (c): the upscale TIER is an intent-level control, so it stays in Simple; Advanced
    // reveals the method / exact scale / model below it, in the same card. Before this the whole
    // group was Advanced-only, which meant Simple offered no upscale at all -- and "reveals in
    // place" cannot be satisfied by a control that is not there in the first place.
    if (upscaleRow_)
        upscaleRow_->setVisible(image);
    if (upscale_)
        upscale_->setAdvanced(advanced);

    // Phase 7 step 3: Sampling-tab raw knobs are Advanced-only. Aspect + Frames/FPS stay Simple
    // (untouched here). GUARD COMPOSITION -- AND the disclosure gate with the row's existing
    // mode guard so disclosure can never reveal a row the mode already hides (image sampler stays
    // hidden in video; video sampler stays hidden in image).
    if (stepsRow_)
        stepsRow_->setVisible(advanced);
    if (cfgRow_)
        cfgRow_->setVisible(advanced);
    if (seedRow_)
        seedRow_->setVisible(advanced);
    if (samplerRow_)
        samplerRow_->setVisible(advanced && image);
    if (schedulerRow_)
        schedulerRow_->setVisible(advanced && image);
    if (videoSamplerRow_)
        videoSamplerRow_->setVisible(advanced && !image);
    if (videoSchedulerRow_)
        videoSchedulerRow_->setVisible(advanced && !image);

    // Phase 7 step 4 -- Model tab: fake Workflow presets dropped (real drop/load below).
    // Video Components stay visible in Simple — auto-population is the product value.
    if (workflowRowLabel_)
        workflowRowLabel_->setVisible(false);
    if (workflowCombo_)
        workflowCombo_->setVisible(false);
    if (componentsRowLabel_)
        componentsRowLabel_->setVisible(!image);
    if (videoComponentPanel_)
        videoComponentPanel_->setVisible(!image);
    // LTX Prompt-API panel is legacy (native LTX). Advanced-only so I2V isn't disjointed.
    if (ltxLaunchOptionsPanel_)
        ltxLaunchOptionsPanel_->setVisible(false);

    // Piece A (D8): hide the Advanced inspector TAB in Simple. After the denoise relocation the
    // Advanced tab has content only in video modes (wan dual-noise / LTX launch), so it is hidden
    // for image modes entirely -- which also clears the pre-existing empty-Advanced-tab-in-T2I.
    if (cockpitInspector_)
        cockpitInspector_->setTabVisible(CockpitInspector::Advanced, advanced && !image);

    refreshAdvancedOverrideNotice();

    qWarning().noquote() << QStringLiteral("[disclosure] page=%1 advanced=%2")
                                .arg(modeKey(), advanced ? QStringLiteral("true") : QStringLiteral("false"));
}

void ImageGenerationPage::refreshAdvancedOverrideNotice()
{
    if (!advancedOverrideLabel_)
        return;

    // Advanced shows every one of these controls, so there is nothing to disclose.
    if (advanced_)
    {
        advancedOverrideLabel_->setVisible(false);
        return;
    }

    QStringList overrides;

    // A pinned seed is the one that reads as a broken app: same prompt, same picture, every time.
    if (sampling_ && sampling_->seedRandomCheck() && !sampling_->seedRandomCheck()->isChecked())
    {
        overrides << QStringLiteral("fixed seed %1")
                         .arg(sampling_->seedSpin() ? sampling_->seedSpin()->value() : 0);
    }

    if (batchSpin_ && batchSpin_->value() > 1)
        overrides << QStringLiteral("batch of %1").arg(batchSpin_->value());

    const int embeddingCount = positiveEmbeddings_.size() + negativeEmbeddings_.size();
    if (embeddingCount > 0)
        overrides << QStringLiteral("%1 embedding(s)").arg(embeddingCount);

    if (upscale_ && upscale_->enabled())
        overrides << QStringLiteral("upscale %1").arg(
            spellvision::generation::UpscaleController::tierLabel(upscale_->tier()).toLower());

    if (overrides.isEmpty())
    {
        advancedOverrideLabel_->setVisible(false);
        return;
    }

    const QString summary = overrides.join(QStringLiteral(", "));
    advancedOverrideLabel_->setText(QStringLiteral("Advanced: %1").arg(summary));
    // The tooltip carries the remedy. The label stays short because it shares the action row with
    // the readiness hint and the Generate button, and this row must not wrap at half-screen.
    advancedOverrideLabel_->setToolTip(
        QStringLiteral("These Advanced settings are in force and will affect this generation:\n%1\n\n"
                       "Switch to Advanced to see or change them.")
            .arg(summary));
    advancedOverrideLabel_->setVisible(true);
}

void ImageGenerationPage::setNegativePromptVisible(bool open)
{
    // HIDE-not-delete: only flips visibility of the wrapper -- negativePromptEdit_ and its text
    // persist while hidden, and the request builder reads it null-guarded (not visibility-guarded),
    // so a typed-then-collapsed negative still reaches generation.
    if (negativeRow_)
        negativeRow_->setVisible(open);
    if (negativeToggleButton_)
    {
        negativeToggleButton_->setStyleSheet(QStringLiteral(
            "#NegativeToggleButton{padding:0 12px;border-radius:8px;font-size:12px;color:%1;"
            "background:%2;border:1px solid %3;}")
            .arg(open ? ThemeManager::instance().css(ThemeManager::Color::AccentHover)
                      : ThemeManager::instance().css(ThemeManager::Color::TextMid),
                 open ? ThemeManager::instance().css(ThemeManager::Color::AccentSubtle)
                      : rgbaToken(ThemeManager::Color::Surface0, 0.40),
                 open ? rgbaToken(ThemeManager::Color::Accent, 0.40)
                      : ThemeManager::instance().css(ThemeManager::Color::BorderStrong)));
    }
}

void ImageGenerationPage::applyPreset(const QString &presetName)
{
    if (isVideoMode())
    {
        if (presetName == QStringLiteral("Portrait Detail"))
        {
            promptEdit_->setPlainText(QStringLiteral("cinematic character motion, subtle camera movement, expressive face, clean animation, coherent lighting, detailed environment"));
            negativePromptEdit_->setPlainText(QStringLiteral("flicker, morphing anatomy, broken hands, jitter, low quality, blurry, text, watermark"));
        }
        else if (presetName == QStringLiteral("Stylized Concept"))
        {
            promptEdit_->setPlainText(QStringLiteral("stylized cinematic shot, elegant motion, strong silhouette, clean temporal coherence, dramatic lighting, production concept animation"));
            negativePromptEdit_->setPlainText(QStringLiteral("muddy colors, frame flicker, unstable subject, duplicate limbs, heavy blur, low detail"));
        }
        else if (presetName == QStringLiteral("Upscale / Repair"))
        {
            promptEdit_->setPlainText(QStringLiteral("stabilize motion, restore details, preserve composition, improve temporal consistency, clean edges"));
            negativePromptEdit_->setPlainText(QStringLiteral("new objects, warped anatomy, heavy flicker, jitter, ghosting, blur"));
        }
        else
        {
            promptEdit_->setPlainText(QStringLiteral("cinematic animated scene, clean motion, strong subject read, consistent lighting, high quality video"));
            negativePromptEdit_->setPlainText(QStringLiteral("flicker, jitter, low quality, blurry, text, watermark, warped anatomy"));
        }

        // No sampler here on purpose. karras is not in wan's allow-list and LTX has no scheduler
        // input at all, so the pair this used to force was unreachable on two of the three video
        // families and silently ignored on them. The family resolver already supplies a declared
        // default per family; a video preset's business is the prompt, the size and the length.
        if (sampling_->stepsSpin())
            sampling_->stepsSpin()->setValue(30);
        if (sampling_->cfgSpin())
            sampling_->cfgSpin()->setValue(5.0);
        if (widthSpin_)
            widthSpin_->setValue(832);
        if (heightSpin_)
            heightSpin_->setValue(480);
        if (frameCountSpin_)
            frameCountSpin_->setValue(81);
        if (fpsSpin_)
            fpsSpin_->setValue(16);
        if (denoiseSpin_)
            denoiseSpin_->setValue(0.55);

        schedulePreviewRefresh(0);
        scheduleUiRefresh(0);
        return;
    }
    if (presetName == QStringLiteral("Portrait Detail"))
    {
        promptEdit_->setPlainText(QStringLiteral("portrait of a confident fantasy heroine, detailed face, studio rim lighting, shallow depth of field, high micro-detail"));
        negativePromptEdit_->setPlainText(QStringLiteral("blurry, low quality, extra fingers, malformed hands, watermark, text"));
        selectComboValue(workflowCombo_, QStringLiteral("Portrait Detail"));
        loraStack_.clear();
        rebuildLoraStackUi();
        applyPresetSampling(presetName, QStringLiteral("dpmpp_2m"), QStringLiteral("karras"));
        sampling_->stepsSpin()->setValue(35);
        sampling_->cfgSpin()->setValue(6.5);
        widthSpin_->setValue(1024);
        heightSpin_->setValue(1344);
    }
    else if (presetName == QStringLiteral("Stylized Concept"))
    {
        promptEdit_->setPlainText(QStringLiteral("stylized concept art, dynamic pose, cinematic lighting, strong silhouette, clean material read, production concept render"));
        negativePromptEdit_->setPlainText(QStringLiteral("muddy colors, blurry, oversaturated, low detail, duplicate limbs"));
        selectComboValue(workflowCombo_, QStringLiteral("Stylized Concept"));
        loraStack_.clear();
        rebuildLoraStackUi();
        applyPresetSampling(presetName, QStringLiteral("dpmpp_sde"), QStringLiteral("karras"));
        sampling_->stepsSpin()->setValue(30);
        sampling_->cfgSpin()->setValue(5.0);
        widthSpin_->setValue(1216);
        heightSpin_->setValue(832);
    }
    else if (presetName == QStringLiteral("Upscale / Repair"))
    {
        promptEdit_->setPlainText(QStringLiteral("restore detail, clean edges, improve texture fidelity, maintain original composition, crisp focus"));
        negativePromptEdit_->setPlainText(QStringLiteral("new objects, warped anatomy, duplicated features, heavy noise, blur"));
        selectComboValue(workflowCombo_, QStringLiteral("Upscale / Repair"));
        loraStack_.clear();
        rebuildLoraStackUi();
        // uni_pc is this preset's real preference; dpmpp_2m is the second choice, and both are
        // preferences rather than impositions.
        if (!selectComboValue(sampling_->samplerCombo(), QStringLiteral("uni_pc")))
            applyPresetSampling(presetName, QStringLiteral("dpmpp_2m"), QString());
        applyPresetSampling(presetName, QString(), QStringLiteral("normal"));
        sampling_->stepsSpin()->setValue(24);
        sampling_->cfgSpin()->setValue(5.5);
        if (denoiseSpin_)
            denoiseSpin_->setValue(0.35);
    }
    else
    {
        promptEdit_->setPlainText(QStringLiteral("high quality image, clean composition, strong subject read, balanced lighting"));
        negativePromptEdit_->setPlainText(QStringLiteral("low quality, blurry, text, watermark"));
        selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));
        loraStack_.clear();
        rebuildLoraStackUi();
        applyPresetSampling(presetName, QStringLiteral("dpmpp_2m"), QStringLiteral("karras"));
        sampling_->stepsSpin()->setValue(28);
        sampling_->cfgSpin()->setValue(7.0);
        widthSpin_->setValue(1024);
        heightSpin_->setValue(1024);
        if (denoiseSpin_)
            denoiseSpin_->setValue(0.45);
    }

    schedulePreviewRefresh(0);
}

void ImageGenerationPage::updateAssetIntelligenceUi()
{
    // --- SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: structured population ---
    if (!modelsRootLabel_)
        return;

    // ---- Data (same shape as the pre-mockup implementation) ----
    const QString modelDisplay = selectedModelPath_.trimmed().isEmpty()
        ? QStringLiteral("none selected")
        : (selectedModelDisplay_.trimmed().isEmpty() ? shortDisplayFromValue(selectedModelPath_) : selectedModelDisplay_.trimmed());

    const QString rawFamily = modelFamilyByValue_.value(selectedModelPath_).trimmed();
    const QString rawModality = modelModalityByValue_.value(selectedModelPath_, isVideoMode() ? QStringLiteral("video") : QStringLiteral("image"));
    const QString rawRole = modelRoleByValue_.value(selectedModelPath_).trimmed();
    const QString stackNote = modelNoteByValue_.value(selectedModelPath_).trimmed();
    const QJsonObject stackObject = isVideoMode() ? selectedVideoStackForPayload() : modelStackByValue_.value(selectedModelPath_);
    const QString modelPathLower = selectedModelPath_.toLower();

    QString modelFamily = QStringLiteral("unknown");
    if (!rawFamily.isEmpty())
        modelFamily = isVideoMode() ? humanVideoFamily(rawFamily) : humanImageFamily(rawFamily);
    else if (modelPathLower.contains(QStringLiteral("pony")))
        modelFamily = QStringLiteral("Pony family");
    else if (modelPathLower.contains(QStringLiteral("illustri")))
        modelFamily = QStringLiteral("Illustrious family");
    else if (modelPathLower.contains(QStringLiteral("sdxl")) || modelPathLower.contains(QStringLiteral("xl")))
        modelFamily = QStringLiteral("SDXL / XL family");
    else if (modelPathLower.contains(QStringLiteral("flux")))
        modelFamily = QStringLiteral("Flux family");
    else if (modelPathLower.contains(QStringLiteral("wan")))
        modelFamily = QStringLiteral("WAN video family");
    else if (modelPathLower.contains(QStringLiteral("krea2")) || modelPathLower.contains(QStringLiteral("krea-2")))
        modelFamily = QStringLiteral("Krea 2");
    else if (modelPathLower.contains(QStringLiteral("zimage")) || modelPathLower.contains(QStringLiteral("z-image")))
        modelFamily = QStringLiteral("Z-Image family");
    else if (!modelPathLower.trimmed().isEmpty())
        modelFamily = QStringLiteral("custom / uncategorized");

    QString stackSummary = stackNote.isEmpty() ? QStringLiteral("\u2014") : stackNote;
    if (!stackObject.isEmpty())
    {
        const QString kind = stackObject.value(QStringLiteral("stack_kind")).toString().trimmed();
        const bool readyStack = stackObject.value(QStringLiteral("stack_ready")).toBool(false);
        const QJsonArray missing = stackObject.value(QStringLiteral("missing_parts")).toArray();
        QStringList missingParts;
        for (const QJsonValue &item : missing)
            missingParts << item.toString();
        stackSummary = QStringLiteral("%1 \u2022 %2").arg(kind.isEmpty() ? QStringLiteral("stack") : kind, readyStack ? QStringLiteral("resolved") : QStringLiteral("partial"));
        if (!missingParts.isEmpty())
            stackSummary += QStringLiteral(" \u2022 missing %1").arg(missingParts.join(QStringLiteral(", ")));
    }

    const int enabledLoras = ModelStackState::enabledLoraCount(loraStack_);
    const QString rootText = modelsRootDir_.trimmed().isEmpty()
        ? QStringLiteral("not configured")
        : shortDisplayFromValue(modelsRootDir_);
    const QString blockReason = readinessBlockReason();
    const bool ready = blockReason.isEmpty();
    const QString readiness = ready ? QStringLiteral("ready") : blockReason;

    // ---- Surface: readiness strip ----
    if (aiReadinessStrip_)
    {
        const QString readinessState = ready ? QStringLiteral("ready") : QStringLiteral("warn");
        aiReadinessStrip_->setProperty("readiness", readinessState);
        spellvision::widgets::repolishWidget(aiReadinessStrip_);
        if (aiReadinessDot_)
        {
            aiReadinessDot_->setProperty("readiness", readinessState);
            spellvision::widgets::repolishWidget(aiReadinessDot_);
        }
        if (aiReadinessText_)
            aiReadinessText_->setText(ready ? QStringLiteral("Ready to generate") : blockReason);

        if (aiReadinessSub_)
        {
            // --- SPRINT MOCKUP PASS 1 FIXUP: empty sub when not ready ---
            // The headline already shows the block reason; leaving the
            // sub empty avoids a duplicate-text overlap in the pill.
            QString sub;
            if (!ready)
            {
                sub.clear();
            }
            else if (isVideoMode())
            {
                const QString backendLabel = hasVideoWorkflowBinding()
                    ? QStringLiteral("imported workflow")
                    : QStringLiteral("native");
                sub = QStringLiteral("%1 \u00B7 %2").arg(modelFamily, backendLabel);
            }
            else
            {
                sub = modelFamily;
            }
            aiReadinessSub_->setText(sub);
            // --- END SPRINT MOCKUP PASS 1 FIXUP ---
        }
    }

    // ---- Item 2: non-blocking LoRA/checkpoint architecture-mismatch warning ----
    if (aiCompatWarningLabel_)
    {
        const bool imagePage = !isVideoMode();
        const LoraArch ckptArch = archFromFamily(rawFamily);
        QString warning;
        for (const auto &loraEntry : loraStack_)
        {
            if (!loraEntry.enabled)
                continue;
            const LoraArch loraArch = archFromLoraText(loraEntry.value + QStringLiteral(" ") + loraEntry.display);
            if (loraArch == LoraArch::Unknown)
                continue;

            bool mismatch = false;
            if (imagePage && isVideoArch(loraArch))
                mismatch = true; // video LoRA on image generation
            else if (!imagePage && isImageArch(loraArch))
                mismatch = true; // image LoRA on video generation
            else if (imagePage && isImageArch(ckptArch) && isImageArch(loraArch) && loraArch != ckptArch)
                mismatch = true; // clear image sub-arch cross (e.g. Flux LoRA on an SDXL checkpoint)

            if (mismatch)
            {
                const QString ckptLabel = (ckptArch != LoraArch::Unknown)
                    ? archName(ckptArch)
                    : (imagePage ? QStringLiteral("image") : QStringLiteral("video"));
                const QString name = loraEntry.display.trimmed().isEmpty()
                    ? shortDisplayFromValue(loraEntry.value)
                    : loraEntry.display.trimmed();
                warning = QStringLiteral("⚠ ‘%1’ looks like a %2 LoRA but this is a %3 setup — it may not apply.")
                    .arg(name, archName(loraArch), ckptLabel);
                break; // one clear warning is enough
            }
        }
        aiCompatWarningLabel_->setText(warning);
        aiCompatWarningLabel_->setVisible(!warning.isEmpty());
    }

    // ---- Surface: chip rows (clear then rebuild) ----
    auto clearChips = [](QBoxLayout *layout) {
        if (!layout)
            return;
        while (layout->count() > 0)
        {
            QLayoutItem *item = layout->takeAt(0);
            if (item->widget())
                item->widget()->deleteLater();
            delete item;
        }
    };

    const QColor accentColor = ThemeManager::instance().accentColor();
    const QColor textMutedColor = ThemeManager::instance().textMutedColor();

    auto addChip = [&](QBoxLayout *layout, QWidget *parent,
                       const QString &label, const QString &value, bool isSet) {
        if (!layout || !parent)
            return;
        auto *chip = new QLabel(parent);
        // --- FIXUP 3: distinct object names, no attribute selector ---
        chip->setObjectName(isSet ? QStringLiteral("AiChipSet") : QStringLiteral("AiChipAuto"));
        chip->setTextFormat(Qt::RichText);
        chip->setToolTip(QStringLiteral("%1: %2").arg(label, value));
        chip->setMaximumWidth(148);
        chip->setSizePolicy(QSizePolicy::Maximum, QSizePolicy::Fixed);
        // Elide the value in the chip so a long checkpoint/model filename can't blow the chips row
        // (and the inspector) past its width; the full value stays in the tooltip above.
        const int kMaxChipValue = 14; // tighter so T2V component chips fit half-screen inspector
        const QString valueShown = value.size() > kMaxChipValue
                                       ? value.left(kMaxChipValue - 1) + QChar(0x2026)
                                       : value;
        const QString labelEsc = label.toHtmlEscaped();
        const QString valueEsc = valueShown.toHtmlEscaped();
        if (isSet)
        {
            chip->setText(QStringLiteral("%1 <b style=\"color:%3;\">%2</b>")
                .arg(labelEsc, valueEsc, accentColor.name()));
        }
        else
        {
            chip->setText(QStringLiteral("%1 <span style=\"color:%3;\">%2</span>")
                .arg(labelEsc, valueEsc, textMutedColor.name()));
        }
        layout->addWidget(chip);
    };

    auto chipValueIsSet = [](const QString &v) {
        const QString t = v.trimmed();
        return !t.isEmpty()
            && t.compare(QStringLiteral("auto"), Qt::CaseInsensitive) != 0
            && t.compare(QStringLiteral("none"), Qt::CaseInsensitive) != 0
            && t != QStringLiteral("\u2014");
    };

    clearChips(aiStackChipsLayout_);
    if (aiStackChipsRow_ && aiStackChipsLayout_)
    {
        if (isVideoMode())
        {
            const QString stackMode = effectiveVideoStackMode();
            const QString famShort = resolvedVideoFamilyToken().toUpper();
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Family"),
                    famShort.isEmpty() ? QStringLiteral("auto") : famShort,
                    !famShort.isEmpty());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Mode"),
                    stackMode == QStringLiteral("wan_dual_noise") ? QStringLiteral("dual-noise") : QStringLiteral("single"),
                    true);
            const QString primary = shortDisplayFromValue(stackObject.value(QStringLiteral("primary_path")).toString());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Primary"),
                    chipValueIsSet(primary) ? primary : QStringLiteral("auto"),
                    chipValueIsSet(primary));
        }
        else
        {
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Checkpoint"),
                    modelDisplay,
                    !selectedModelPath_.trimmed().isEmpty());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Family"),
                    modelFamily,
                    !rawFamily.isEmpty());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("LoRAs"),
                    QStringLiteral("%1 / %2").arg(loraStack_.size()).arg(enabledLoras),
                    enabledLoras > 0);
        }
        aiStackChipsLayout_->addStretch(1);
    }

    clearChips(aiComponentsChipsLayout_);
    if (aiComponentsGroupContainer_)
        aiComponentsGroupContainer_->setVisible(isVideoMode());
    if (isVideoMode() && aiComponentsChipsRow_ && aiComponentsChipsLayout_)
    {
        const QString textEnc = shortDisplayFromValue(stackObject.value(QStringLiteral("text_encoder_path")).toString());
        const QString vae = shortDisplayFromValue(stackObject.value(QStringLiteral("vae_path")).toString());
        const QString vision = shortDisplayFromValue(stackObject.value(QStringLiteral("clip_vision_path")).toString());
        addChip(aiComponentsChipsLayout_, aiComponentsChipsRow_,
                QStringLiteral("Text"),
                chipValueIsSet(textEnc) ? textEnc : QStringLiteral("auto"),
                chipValueIsSet(textEnc));
        addChip(aiComponentsChipsLayout_, aiComponentsChipsRow_,
                QStringLiteral("VAE"),
                chipValueIsSet(vae) ? vae : QStringLiteral("auto"),
                chipValueIsSet(vae));
        addChip(aiComponentsChipsLayout_, aiComponentsChipsRow_,
                QStringLiteral("Vision"),
                chipValueIsSet(vision) ? vision : QStringLiteral("auto"),
                chipValueIsSet(vision));
        aiComponentsChipsLayout_->addStretch(1);
    }

    // ---- Surface: timing row (video modes only) ----
    if (aiTimingRow_)
        aiTimingRow_->setVisible(isVideoMode());
    if (isVideoMode())
    {
        const int frames = frameCountSpin_ ? frameCountSpin_->value() : 0;
        const int fps = fpsSpin_ ? fpsSpin_->value() : 0;
        const double seconds = fps > 0 ? static_cast<double>(frames) / static_cast<double>(fps) : 0.0;
        if (aiTimingFramesValue_)
            aiTimingFramesValue_->setText(QStringLiteral("%1 frames").arg(frames));
        if (aiTimingFpsValue_)
            aiTimingFpsValue_->setText(QStringLiteral("%1 fps").arg(fps));
        if (aiTimingDurationValue_)
            aiTimingDurationValue_->setText(QStringLiteral("%1 s").arg(QString::number(seconds, 'f', 1)));
    }

    // ---- Legacy HTML dump (kept behind the "Show all fields" disclosure) ----
    auto row = [ready](const QString &label, const QString &value, bool readinessRow = false) {
        const QString valueClass = readinessRow ? (ready ? QStringLiteral("v good") : QStringLiteral("v bad")) : QStringLiteral("v");
        return QStringLiteral("<tr><td class='k'>%1</td><td class='%2'>%3</td></tr>")
            .arg(label.toHtmlEscaped(), valueClass, value.toHtmlEscaped());
    };

    QString html;
    html += QStringLiteral("<style>"
                           "table{border-collapse:collapse;width:100%;}"
                           "td{padding:2px 0;vertical-align:top;}"
                           ".k{opacity:.74;font-weight:800;white-space:nowrap;padding-right:12px;}"
                           ".v{font-weight:700;}"
                           ".good{color:%1;}"   // Phase 8: was soft-mint #9ff5ca -> semantic Success
                           ".bad{color:%2;}"    // Phase 8: was soft-pink #ffd1dc -> semantic Error
                           "</style>")
                       .arg(ThemeManager::instance().css(ThemeManager::Color::Success),
                            ThemeManager::instance().css(ThemeManager::Color::Error));
    html += QStringLiteral("<table>");
    html += row(isVideoMode() ? QStringLiteral("Model Stack") : QStringLiteral("Checkpoint"), modelDisplay);
    html += row(QStringLiteral("Family"), modelFamily);
    if (isVideoMode())
    {
        const QString stackMode = effectiveVideoStackMode();
        html += row(QStringLiteral("Modality"), rawModality.trimmed().isEmpty() ? QStringLiteral("video") : rawModality);
        html += row(QStringLiteral("Stack Role"), rawRole.trimmed().isEmpty() ? QStringLiteral("native video") : rawRole);
        html += row(QStringLiteral("Stack Mode"), stackMode == QStringLiteral("wan_dual_noise") ? QStringLiteral("WAN dual-noise") : QStringLiteral("single model"));
        html += row(QStringLiteral("Stack"), stackSummary);
        html += row(QStringLiteral("Primary"), shortDisplayFromValue(stackObject.value(QStringLiteral("primary_path")).toString()));
        if (stackMode == QStringLiteral("wan_dual_noise"))
        {
            html += row(QStringLiteral("High Noise"), shortDisplayFromValue(stackObject.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty() ? stackObject.value(QStringLiteral("high_noise_model_path")).toString() : stackObject.value(QStringLiteral("high_noise_path")).toString()));
            html += row(QStringLiteral("Low Noise"), shortDisplayFromValue(stackObject.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty() ? stackObject.value(QStringLiteral("low_noise_model_path")).toString() : stackObject.value(QStringLiteral("low_noise_path")).toString()));
            html += row(QStringLiteral("Wan Split"), wanSplitCombo_ ? currentComboValue(wanSplitCombo_) : QStringLiteral("auto"));
        }
        html += row(QStringLiteral("Text Encoder"), shortDisplayFromValue(stackObject.value(QStringLiteral("text_encoder_path")).toString()));
        html += row(QStringLiteral("VAE"), shortDisplayFromValue(stackObject.value(QStringLiteral("vae_path")).toString()));
        const QString vision = stackObject.value(QStringLiteral("clip_vision_path")).toString().trimmed();
        if (!vision.isEmpty())
            html += row(QStringLiteral("Vision Encoder"), shortDisplayFromValue(vision));
        if (stackMode == QStringLiteral("wan_dual_noise"))
        {
            html += row(QStringLiteral("High Steps"), highNoiseStepsSpin_ ? QString::number(highNoiseStepsSpin_->value()) : QStringLiteral("14"));
            html += row(QStringLiteral("Low Steps"), lowNoiseStepsSpin_ ? QString::number(lowNoiseStepsSpin_->value()) : QStringLiteral("14"));
            html += row(QStringLiteral("Split Step"), splitStepSpin_ ? QString::number(splitStepSpin_->value()) : QStringLiteral("14"));
            html += row(QStringLiteral("High Shift"), highNoiseShiftSpin_ ? QString::number(highNoiseShiftSpin_->value(), 'f', 2) : QStringLiteral("5.00"));
            html += row(QStringLiteral("Low Shift"), lowNoiseShiftSpin_ ? QString::number(lowNoiseShiftSpin_->value(), 'f', 2) : QStringLiteral("5.00"));
            html += row(QStringLiteral("VAE Tiling"), enableVaeTilingCheck_ && enableVaeTilingCheck_->isChecked() ? QStringLiteral("enabled") : QStringLiteral("disabled"));
        }
    }
    html += row(QStringLiteral("LoRAs"), QStringLiteral("%1 stack / %2 enabled").arg(loraStack_.size()).arg(enabledLoras));
    if (isVideoMode())
    {
        const int frames = frameCountSpin_ ? frameCountSpin_->value() : 0;
        const int fps = fpsSpin_ ? fpsSpin_->value() : 0;
        const double seconds = fps > 0 ? static_cast<double>(frames) / static_cast<double>(fps) : 0.0;
        html += row(QStringLiteral("Timing"), QStringLiteral("%1 frames @ %2 fps (%3s)").arg(frames).arg(fps).arg(QString::number(seconds, 'f', 1)));
        html += row(QStringLiteral("Backend"), hasVideoWorkflowBinding() ? QStringLiteral("Imported workflow") : QStringLiteral("Native video model"));
        const QString inputImagePath = inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString();
        if (!inputImagePath.isEmpty())
            html += row(QStringLiteral("Keyframe"), shortDisplayFromValue(inputImagePath));
    }
    html += row(QStringLiteral("Readiness"), readiness, true);
    html += row(QStringLiteral("Assets"), rootText);
    html += QStringLiteral("</table>");

    modelsRootLabel_->setText(html);

    // Tooltip on the readiness strip — exposes the full dump in plain text
    // so users get the data without having to expand the disclosure.
    QStringList plain;
    plain << QStringLiteral("%1: %2").arg(isVideoMode() ? QStringLiteral("Model Stack") : QStringLiteral("Checkpoint"), modelDisplay);
    plain << QStringLiteral("Family: %1").arg(modelFamily);
    plain << QStringLiteral("LoRAs: %1 in stack / %2 enabled").arg(loraStack_.size()).arg(enabledLoras);
    plain << QStringLiteral("Readiness: %1").arg(readiness);
    plain << QStringLiteral("Assets: %1").arg(rootText);
    const QString tooltip = plain.join(QStringLiteral("\n"));
    if (aiReadinessStrip_)
        aiReadinessStrip_->setToolTip(tooltip);
    modelsRootLabel_->setToolTip(tooltip);
    // --- END SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: structured population ---  // SPRINT MOCKUP PASS 1 FIXUP 2 + SPRINT MOCKUP PASS 1 FIXUP 3
}

void ImageGenerationPage::updateDraftCompatibilityUi()
{
    QStringList lines;
    if (!workflowDraftSource_.isEmpty())
        lines << QStringLiteral("Loaded from workflow: %1").arg(workflowDraftSource_);
    for (const QString &warning : workflowDraftWarnings_)
    {
        if (!warning.trimmed().isEmpty())
            lines << warning.trimmed();
    }
    const QString tooltip = lines.join(QStringLiteral("\n"));

    if (!tooltip.isEmpty())
    {
        if (generateButton_)
            generateButton_->setToolTip(tooltip);
        if (queueButton_)
            queueButton_->setToolTip(tooltip);
        if (openWorkflowsButton_)
            openWorkflowsButton_->setToolTip(tooltip);
    }

    updateAssetIntelligenceUi();
}

bool ImageGenerationPage::hasReadyModelSelection() const
{
    if (isVideoMode() && resolvedVideoFamilyToken() == QStringLiteral("flux3"))
        return true;

    if (!selectedModelValue().trimmed().isEmpty())
        return true;

    if (isVideoMode())
    {
        const QJsonObject stack = selectedVideoStackForPayload();
        const QString stackMode = stack.value(QStringLiteral("stack_mode")).toString().trimmed();
        const QString primary = stack.value(QStringLiteral("primary_path")).toString().trimmed();
        const QString highNoise = stack.value(QStringLiteral("high_noise_path")).toString().trimmed();
        const QString lowNoise = stack.value(QStringLiteral("low_noise_path")).toString().trimmed();

        if (stackMode == QStringLiteral("wan_dual_noise"))
        {
            if (!highNoise.isEmpty() || !lowNoise.isEmpty() || !primary.isEmpty())
                return true;
        }
        else if (!primary.isEmpty())
        {
            return true;
        }

        // Imported video workflow drafts may carry their own model stack inside the
        // compiled Comfy prompt. Native video generation still requires an explicit
        // model selection, but workflow-bound generation does not.
        return hasVideoWorkflowBinding();
    }

    return false;
}

bool ImageGenerationPage::hasRequiredGenerationInput() const
{
    if (!isImageInputMode())
        return true;

    if (!inputImageEdit_)
        return false;

    const QString path = inputImageEdit_->text().trimmed();
    if (path.isEmpty())
        return false;

    const QFileInfo info(path);
    return info.exists() && info.isFile();
}

bool ImageGenerationPage::hasVideoWorkflowBinding() const
{
    if (!isVideoMode())
        return true;

    if (!workflowDraftProfilePath_.trimmed().isEmpty())
        return true;
    if (!workflowDraftWorkflowPath_.trimmed().isEmpty())
        return true;
    if (!workflowDraftCompiledPromptPath_.trimmed().isEmpty())
        return true;

    return false;
}

namespace
{
// Fit a source size into maxSide on its long edge and snap both edges to `multiple`, never below
// 64. The builders snap again for their family; this only has to be a sensible starting canvas.
QSize snapCanvas(QSize source, int multiple, int maxSide)
{
    if (source.isEmpty())
        return {};
    if (source.width() > maxSide || source.height() > maxSide)
        source = source.scaled(maxSide, maxSide, Qt::KeepAspectRatio);
    const auto snap = [multiple](int v) { return std::max(64, qRound(double(v) / multiple) * multiple); };
    return QSize(snap(source.width()), snap(source.height()));
}
} // namespace

void ImageGenerationPage::ensureCanvasSizeDefault()
{
    if (!widthSpin_ || !heightSpin_)
        return;
    if (widthSpin_->value() >= 64 && heightSpin_->value() >= 64)
        return;

    // Two of the four generation pages opened with "Choose a canvas size to generate." on
    // 2026-09-02: the spin boxes start at 0 and only a preset or a saved value ever set them, so a
    // fresh I2I (even one reached through "Prep for I2I") and a fresh T2V were dead on arrival.
    QSize size = isVideoMode() ? QSize(832, 480) : QSize(1024, 1024);
    if (isImageInputMode() && inputImageEdit_)
    {
        const QString inputPath = inputImageEdit_->text().trimmed();
        if (!inputPath.isEmpty())
        {
            const QSize source = QImageReader(inputPath).size();
            // Video keyframes stay within 1280 on the long edge; images within 2048.
            const QSize fromInput = snapCanvas(source, 16, isVideoMode() ? 1280 : 2048);
            if (fromInput.isValid())
                size = fromInput;
        }
    }
    widthSpin_->setValue(size.width());
    heightSpin_->setValue(size.height());
}

QString ImageGenerationPage::readinessBlockReason() const
{
    if (busy_)
        return busyMessage_.isEmpty() ? QStringLiteral("Generation in progress.") : busyMessage_;

    if (!hasReadyModelSelection())
    {
        if (isVideoMode())
            return QStringLiteral("Select a video model stack or open a video workflow draft.");
        return QStringLiteral("Select a checkpoint to generate.");
    }

    if ((widthSpin_ && widthSpin_->value() < 64) || (heightSpin_ && heightSpin_->value() < 64))
        return QStringLiteral("Choose a canvas size to generate.");

    if (outputFolderLabel_)
    {
        const QString destText = outputFolderLabel_->text().trimmed();
        if (destText.isEmpty() || destText.startsWith(QLatin1String("Not set"), Qt::CaseInsensitive))
            return QStringLiteral("Choose an output folder to generate.");
    }

    // A2 (T3): a required component the engine could not resolve on disk blocks generation with a
    // clear message rather than a cryptic backend failure (the download hook is a later pass).
    const bool usesRemoteFlux3 = isVideoMode() && resolvedVideoFamilyToken() == QStringLiteral("flux3");
    if (usesRemoteFlux3 && qgetenv("BFL_API_KEY").trimmed().isEmpty())
        return QStringLiteral("Set BFL_API_KEY before using the paid FLUX.3 BFL API preview.");
    if (isVideoMode() && !usesRemoteFlux3 && !videoMissingRequiredComponents_.isEmpty())
        return QStringLiteral("Missing required component: %1 — download or locate it to continue.")
                   .arg(videoMissingRequiredComponents_.join(QStringLiteral(", ")));

    if (isImageInputMode() && inputImageEdit_)
    {
        const QString inputPath = inputImageEdit_->text().trimmed();
        if (!inputPath.isEmpty())
        {
            const QFileInfo info(inputPath);
            if (!info.exists() || !info.isFile())
            {
                // Stale path left over from a deleted output / moved file — clear via the
                // normal writer so chip UI + drop labels stay in sync.
                const_cast<ImageGenerationPage *>(this)->setInputImagePath(QString());
                return isVideoMode()
                           ? QStringLiteral("Previous keyframe is gone — drop or browse a new source image.")
                           : QStringLiteral("Previous input image is gone — drop or browse a new source image.");
            }
        }
    }

    if (!hasRequiredGenerationInput())
        return isVideoMode()
                   ? QStringLiteral("Add a source keyframe image to run image-to-video.")
                   : QStringLiteral("Add an input image to generate.");

    if (isVideoMode() && !usesRemoteFlux3 && !hasVideoWorkflowBinding())
    {
        const QJsonObject stack = selectedVideoStackForPayload();
        QStringList missing;
        for (const QJsonValue &value : stack.value(QStringLiteral("missing_parts")).toArray())
        {
            const QString item = value.toString().trimmed();
            if (!item.isEmpty())
                missing << item;
        }
        if (!missing.isEmpty())
            return QStringLiteral("Complete the video stack: missing %1.").arg(missing.join(QStringLiteral(", ")));
    }

    if (workflowDraftBlocking_)
        return QStringLiteral("Resolve workflow draft review items.");


    if (isVideoMode())
    {
        const QJsonObject videoPayload = buildRequestPayload();
        const QString videoBlockReason = spellvision::generation::VideoReadinessPresenter::blockingMessage(videoPayload);
        if (!videoBlockReason.isEmpty())
            return videoBlockReason;
    }

    return QString();
}

void ImageGenerationPage::applyActionReadinessStyle(QPushButton *button, bool enabled, const QString &tooltip)
{
    if (!button)
        return;

    const bool blocked = !enabled;
    if (button->property("readinessBlocked").toBool() != blocked)
        button->setProperty("readinessBlocked", blocked);

    // Keep action buttons clickable when a request is blocked so the click can
    // surface the exact readiness reason instead of feeling dead. The click
    // handler still prevents submission while blocked. Busy state remains a
    // true hard-disable because the page is already handing work to the worker.
    button->setEnabled(!busy_);
    button->setToolTip(tooltip);
    repolishWidget(button);
}

void ImageGenerationPage::updatePrimaryActionAvailability()
{
    const QString blockReason = readinessBlockReason();
    const bool enabled = blockReason.isEmpty();

    applyActionReadinessStyle(generateButton_, enabled,
                              enabled ? QStringLiteral("Generate with the current prompt and model stack.")
                                      : blockReason);
    applyActionReadinessStyle(queueButton_, enabled,
                              enabled ? QStringLiteral("Add this job to the queue.")
                                      : blockReason);

    // Keep the inspector footer's readiness strip in lockstep with Asset Intelligence + action row.
    // It used to stay on the construction-time default ("select a checkpoint") even when ready.
    if (cockpitInspector_ && cockpitInspector_->readinessLabel()) {
        cockpitInspector_->readinessLabel()->setText(
            enabled ? QStringLiteral("Ready to generate.")
                    : (blockReason.trimmed().isEmpty()
                           ? QStringLiteral("Not ready.")
                           : QStringLiteral("Readiness — %1").arg(blockReason)));
    }

    // Don't clobber an active error banner with the normal readiness hint — it stays
    // until clearGenerationError() (next submit / next completed output).
    if (readinessHintLabel_ && !errorBannerActive_)
    {
        readinessHintLabel_->setText(enabled ? QString() : blockReason);
        readinessHintLabel_->setToolTip(enabled ? QString() : blockReason);
        readinessHintLabel_->setVisible(!enabled && !blockReason.trimmed().isEmpty());
    }

    updateAssetIntelligenceUi();
}

void ImageGenerationPage::clearForm()
{
    if (presetCombo_)
        presetCombo_->setCurrentText(QStringLiteral("Balanced"));

    if (promptEdit_)
        promptEdit_->clear();
    if (negativePromptEdit_)
        negativePromptEdit_->clear();
    setNegativePromptVisible(false); // mockup reset re-collapses the negative row
    if (inputImageEdit_)
        inputImageEdit_->clear();

    setSelectedModel(QString(), QString());

    if (workflowCombo_)
        selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));
    loraStack_.clear();
    rebuildLoraStackUi();
    // Reset restores the family DEFAULT rather than sdxl's pair. "auto" is the combo entry that
    // means exactly that, and it is the only value correct for every family -- the previous literal
    // was silently a no-op wherever the family did not offer it.
    if (sampling_->samplerCombo())
        selectComboValue(sampling_->samplerCombo(), QStringLiteral("auto"));
    if (sampling_->schedulerCombo())
        selectComboValue(sampling_->schedulerCombo(), QStringLiteral("auto"));
    if (sampling_->stepsSpin())
        sampling_->stepsSpin()->setValue(isVideoMode() ? 30 : 28);
    if (sampling_->cfgSpin())
        sampling_->cfgSpin()->setValue(isVideoMode() ? 5.0 : 7.0);
    if (sampling_->seedSpin())
        sampling_->seedSpin()->setValue(0);
    if (widthSpin_)
        widthSpin_->setValue(isVideoMode() ? 832 : 1024);
    if (heightSpin_)
        heightSpin_->setValue(isVideoMode() ? 480 : 1024);
    if (frameCountSpin_)
        frameCountSpin_->setValue(81);
    if (fpsSpin_)
        fpsSpin_->setValue(16);
    if (videoStackModeCombo_)
        selectComboValue(videoStackModeCombo_, QStringLiteral("auto"));
    if (wanSplitCombo_)
        selectComboValue(wanSplitCombo_, QStringLiteral("auto"));
    if (highNoiseStepsSpin_)
        highNoiseStepsSpin_->setValue(14);
    if (lowNoiseStepsSpin_)
        lowNoiseStepsSpin_->setValue(14);
    if (splitStepSpin_)
        splitStepSpin_->setValue(14);
    if (highNoiseShiftSpin_)
        highNoiseShiftSpin_->setValue(5.0);
    if (lowNoiseShiftSpin_)
        lowNoiseShiftSpin_->setValue(5.0);
    if (enableVaeTilingCheck_)
        enableVaeTilingCheck_->setChecked(false);
    if (batchSpin_)
        batchSpin_->setValue(1);
    if (denoiseSpin_)
        denoiseSpin_->setValue(0.45);
    if (outputPrefixEdit_)
        outputPrefixEdit_->clear();

    workflowDraftSource_.clear();
    workflowDraftProfilePath_.clear();
    workflowDraftWorkflowPath_.clear();
    workflowDraftCompiledPromptPath_.clear();
    workflowDraftBackend_.clear();
    workflowDraftMediaType_.clear();
    workflowDraftWarnings_.clear();
    workflowDraftBlocking_ = false;

    generatedPreviewPath_.clear();
    generatedPreviewCaption_.clear();
    busy_ = false;
    busyMessage_.clear();

    setInputImagePath(QString());

    updatePrimaryActionAvailability();
    if (savePresetButton_)
        savePresetButton_->setEnabled(true);
    if (clearButton_)
        clearButton_->setEnabled(true);

    updateAssetIntelligenceUi();
    schedulePreviewRefresh(0);
}

void ImageGenerationPage::persistWorkspaceSettings()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString group = QStringLiteral("ImageGenerationPage/%1").arg(modeKey());

    settings.beginGroup(group);
    settings.setValue(QStringLiteral("preset"), currentComboValue(presetCombo_));
    settings.setValue(QStringLiteral("prompt"), promptEdit_ ? promptEdit_->toPlainText() : QString());
    settings.setValue(QStringLiteral("negativePrompt"), negativePromptEdit_ ? negativePromptEdit_->toPlainText() : QString());
    settings.setValue(QStringLiteral("inputImage"), inputImageEdit_ ? inputImageEdit_->text() : QString());
    settings.setValue(QStringLiteral("model"), selectedModelValue());
    settings.setValue(QStringLiteral("modelDisplay"), selectedModelDisplay_);
    settings.setValue(QStringLiteral("workflow"), currentComboValue(workflowCombo_));
    settings.setValue(QStringLiteral("loraStackJson"), serializeLoraStack(loraStack_));
    settings.setValue(QStringLiteral("sampler"), currentComboValue(sampling_->samplerCombo()));
    settings.setValue(QStringLiteral("scheduler"), currentComboValue(sampling_->schedulerCombo()));
    settings.setValue(QStringLiteral("steps"), sampling_->stepsSpin() ? sampling_->stepsSpin()->value() : 28);
    settings.setValue(QStringLiteral("cfg"), sampling_->cfgSpin() ? sampling_->cfgSpin()->value() : 7.0);
    settings.setValue(QStringLiteral("seed"), sampling_->seedSpin() ? sampling_->seedSpin()->value() : 0);
    settings.setValue(QStringLiteral("width"), widthSpin_ ? widthSpin_->value() : 1024);
    settings.setValue(QStringLiteral("height"), heightSpin_ ? heightSpin_->value() : 1024);
    settings.setValue(QStringLiteral("frames"), frameCountSpin_ ? frameCountSpin_->value() : 81);
    settings.setValue(QStringLiteral("fps"), fpsSpin_ ? fpsSpin_->value() : 16);
    settings.setValue(QStringLiteral("batch"), batchSpin_ ? batchSpin_->value() : 1);
    settings.setValue(QStringLiteral("denoise"), denoiseSpin_ ? denoiseSpin_->value() : 0.45);
    settings.setValue(QStringLiteral("videoStackMode"), videoStackModeCombo_ ? videoStackModeSelection() : QStringLiteral("auto"));
    settings.setValue(QStringLiteral("wanSplit"), wanSplitCombo_ ? currentComboValue(wanSplitCombo_) : QStringLiteral("auto"));
    settings.setValue(QStringLiteral("highSteps"), highNoiseStepsSpin_ ? highNoiseStepsSpin_->value() : 14);
    settings.setValue(QStringLiteral("lowSteps"), lowNoiseStepsSpin_ ? lowNoiseStepsSpin_->value() : 14);
    settings.setValue(QStringLiteral("splitStep"), splitStepSpin_ ? splitStepSpin_->value() : 14);
    settings.setValue(QStringLiteral("highShift"), highNoiseShiftSpin_ ? highNoiseShiftSpin_->value() : 5.0);
    settings.setValue(QStringLiteral("lowShift"), lowNoiseShiftSpin_ ? lowNoiseShiftSpin_->value() : 5.0);
    settings.setValue(QStringLiteral("enableVaeTiling"), enableVaeTilingCheck_ && enableVaeTilingCheck_->isChecked());
    settings.setValue(QStringLiteral("outputPrefix"), outputPrefixEdit_ ? outputPrefixEdit_->text() : QString());
    if (outputFolderLabel_)
    {
        const QString destText = outputFolderLabel_->text().trimmed();
        if (!destText.isEmpty() && !destText.startsWith(QLatin1String("Not set"), Qt::CaseInsensitive))
            settings.setValue(QStringLiteral("outputFolder"), destText);
    }
    settings.endGroup();
    settings.sync();
}

void ImageGenerationPage::saveSnapshot()
{
    persistWorkspaceSettings();

    QString sourcePath = generatedPreviewPath_.trimmed();
    if (sourcePath.isEmpty() && isImageInputMode() && inputImageEdit_)
        sourcePath = inputImageEdit_->text().trimmed();

    if (sourcePath.isEmpty() || !QFileInfo::exists(sourcePath))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Save Snapshot"),
                                 QStringLiteral("Generation settings were saved. No rendered output is available to copy yet."));
        return;
    }

    QFileInfo sourceInfo(sourcePath);
    QString extension = sourceInfo.suffix().trimmed().toLower();
    const QStringList supportedSnapshotExtensions = {QStringLiteral("png"),
                                                     QStringLiteral("jpg"),
                                                     QStringLiteral("jpeg"),
                                                     QStringLiteral("webp"),
                                                     QStringLiteral("bmp"),
                                                     QStringLiteral("gif"),
                                                     QStringLiteral("mp4"),
                                                     QStringLiteral("webm"),
                                                     QStringLiteral("mov"),
                                                     QStringLiteral("mkv")};
    if (!supportedSnapshotExtensions.contains(extension))
        extension = isVideoMode() ? QStringLiteral("mp4") : QStringLiteral("png");

    QString picturesRoot = QStandardPaths::writableLocation(QStandardPaths::PicturesLocation);
    if (picturesRoot.trimmed().isEmpty())
        picturesRoot = QDir::homePath();

    QDir snapshotDir(QDir(picturesRoot).filePath(QStringLiteral("SpellVision/Snapshots")));
    snapshotDir.mkpath(QStringLiteral("."));

    const QString defaultName = QStringLiteral("%1_snapshot_%2.%3")
                                    .arg(modeKey(),
                                         QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd_HHmmss")),
                                         extension);
    QString savePath = QFileDialog::getSaveFileName(this,
                                                    QStringLiteral("Save SpellVision Snapshot"),
                                                    snapshotDir.filePath(defaultName),
                                                    isVideoMode()
                                                        ? QStringLiteral("Video / Animated Outputs (*.mp4 *.webm *.mov *.mkv *.gif);;All Files (*)")
                                                        : QStringLiteral("Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All Files (*)"));
    if (savePath.trimmed().isEmpty())
        return;

    if (QFileInfo(savePath).suffix().trimmed().isEmpty())
        savePath += QStringLiteral(".") + extension;

    QFileInfo targetInfo(savePath);
    const QString canonicalSource = sourceInfo.canonicalFilePath();
    const QString canonicalTarget = targetInfo.exists() ? targetInfo.canonicalFilePath() : targetInfo.absoluteFilePath();
    if (!canonicalSource.isEmpty() && canonicalSource == canonicalTarget)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Save Snapshot"),
                                 QStringLiteral("Snapshot already exists at this location."));
        return;
    }

    if (QFileInfo::exists(savePath) && !QFile::remove(savePath))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Save Snapshot"),
                             QStringLiteral("Could not replace the existing file:\n%1").arg(savePath));
        return;
    }

    bool saved = QFile::copy(sourcePath, savePath);
    if (!saved && imagePreviewController_ && imagePreviewController_->hasCachedPixmap())
        saved = imagePreviewController_->cachedPixmap().save(savePath);

    if (!saved)
    {
        QMessageBox::warning(this,
                             QStringLiteral("Save Snapshot"),
                             QStringLiteral("Could not save the snapshot:\n%1").arg(savePath));
        return;
    }

    QSettings workspaceSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    workspaceSettings.setValue(QStringLiteral("workspace/last_saved_snapshot_path"), savePath);
    workspaceSettings.sync();

    QMessageBox::information(this,
                             QStringLiteral("Save Snapshot"),
                             QStringLiteral("Snapshot saved:\n%1").arg(savePath));
}

void ImageGenerationPage::restoreSnapshot()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString group = QStringLiteral("ImageGenerationPage/%1").arg(modeKey());
    settings.beginGroup(group);

    if (presetCombo_)
        selectComboValue(presetCombo_, settings.value(QStringLiteral("preset"), QStringLiteral("Balanced")).toString());
    if (promptEdit_)
        promptEdit_->setPlainText(settings.value(QStringLiteral("prompt")).toString());
    if (negativePromptEdit_)
        negativePromptEdit_->setPlainText(settings.value(QStringLiteral("negativePrompt")).toString());
    const QString snapModel = settings.value(QStringLiteral("model")).toString().trimmed();
    const QString snapDisplay = settings.value(QStringLiteral("modelDisplay")).toString();
    if (!snapModel.isEmpty())
        setSelectedModel(snapModel, snapDisplay);
    if (workflowCombo_)
        selectComboValue(workflowCombo_, settings.value(QStringLiteral("workflow"), QStringLiteral("Default Canvas")).toString());
    loraStack_ = deserializeLoraStack(settings.value(QStringLiteral("loraStackJson")).toString());
    rebuildLoraStackUi();
    if (sampling_->samplerCombo() && settings.contains(QStringLiteral("sampler")))
        selectComboValue(sampling_->samplerCombo(), settings.value(QStringLiteral("sampler")).toString());
    if (sampling_->schedulerCombo() && settings.contains(QStringLiteral("scheduler")))
        selectComboValue(sampling_->schedulerCombo(), settings.value(QStringLiteral("scheduler")).toString());
    if (sampling_->stepsSpin() && settings.contains(QStringLiteral("steps")))
        sampling_->stepsSpin()->setValue(settings.value(QStringLiteral("steps")).toInt());
    if (sampling_->cfgSpin() && settings.contains(QStringLiteral("cfg")))
        sampling_->cfgSpin()->setValue(settings.value(QStringLiteral("cfg")).toDouble());
    if (sampling_->seedSpin() && settings.contains(QStringLiteral("seed")))
        sampling_->seedSpin()->setValue(settings.value(QStringLiteral("seed")).toInt());
    if (widthSpin_ && settings.contains(QStringLiteral("width")))
        widthSpin_->setValue(settings.value(QStringLiteral("width")).toInt());
    if (heightSpin_ && settings.contains(QStringLiteral("height")))
        heightSpin_->setValue(settings.value(QStringLiteral("height")).toInt());
    // A saved 0x0 (a page that was never sized) restores as 0x0; give it its default now.
    ensureCanvasSizeDefault();
    if (frameCountSpin_)
        frameCountSpin_->setValue(settings.value(QStringLiteral("frames"), 81).toInt());
    if (fpsSpin_)
        fpsSpin_->setValue(settings.value(QStringLiteral("fps"), 16).toInt());
    if (batchSpin_)
        batchSpin_->setValue(settings.value(QStringLiteral("batch"), 1).toInt());
    if (denoiseSpin_)
        denoiseSpin_->setValue(settings.value(QStringLiteral("denoise"), 0.45).toDouble());
    if (videoStackModeCombo_)
        selectComboValue(videoStackModeCombo_, settings.value(QStringLiteral("videoStackMode"), QStringLiteral("auto")).toString());
    if (wanSplitCombo_)
        selectComboValue(wanSplitCombo_, settings.value(QStringLiteral("wanSplit"), QStringLiteral("auto")).toString());
    if (highNoiseStepsSpin_)
        highNoiseStepsSpin_->setValue(settings.value(QStringLiteral("highSteps"), 14).toInt());
    if (lowNoiseStepsSpin_)
        lowNoiseStepsSpin_->setValue(settings.value(QStringLiteral("lowSteps"), 14).toInt());
    if (splitStepSpin_)
        splitStepSpin_->setValue(settings.value(QStringLiteral("splitStep"), 14).toInt());
    if (highNoiseShiftSpin_)
        highNoiseShiftSpin_->setValue(settings.value(QStringLiteral("highShift"), 5.0).toDouble());
    if (lowNoiseShiftSpin_)
        lowNoiseShiftSpin_->setValue(settings.value(QStringLiteral("lowShift"), 5.0).toDouble());
    if (enableVaeTilingCheck_)
        enableVaeTilingCheck_->setChecked(settings.value(QStringLiteral("enableVaeTiling"), false).toBool());
    if (outputPrefixEdit_)
        outputPrefixEdit_->setText(settings.value(QStringLiteral("outputPrefix")).toString());
    if (outputFolderLabel_)
    {
        const QString folder = settings.value(QStringLiteral("outputFolder")).toString().trimmed();
        const QString normalized = QDir::fromNativeSeparators(folder);
        const QString comfyOut = QDir::fromNativeSeparators(chooseComfyOutputPath());
        if (!normalized.isEmpty() && QDir(normalized).exists()
            && normalized.compare(comfyOut, Qt::CaseInsensitive) != 0)
            outputFolderLabel_->setText(QDir::toNativeSeparators(normalized));
    }

    setInputImagePath(settings.value(QStringLiteral("inputImage")).toString());
    updateVideoFamilyUi();
    updateVideoStackModeUi();
    settings.endGroup();
}

