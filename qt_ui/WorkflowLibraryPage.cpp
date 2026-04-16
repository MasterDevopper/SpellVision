#include "WorkflowLibraryPage.h"

#include "ThemeManager.h"

#include <QComboBox>
#include <QDesktopServices>
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QJsonValue>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QListWidgetItem>
#include <QPlainTextEdit>
#include <QProcess>
#include <QPushButton>
#include <QSet>
#include <QSplitter>
#include <QUrl>
#include <QVBoxLayout>

namespace
{
QString joinLines(const QStringList &lines)
{
    return lines.join(QLatin1Char('\n'));
}

struct LinkEdge
{
    QString sourceNodeId;
    int sourceSlot = 0;
};

QJsonValue nodeRefValue(const QString &nodeId)
{
    return QJsonValue(nodeId);
}

QJsonArray buildNodeRef(const QString &nodeId, int slot)
{
    QJsonArray ref;
    ref.append(nodeRefValue(nodeId));
    ref.append(slot);
    return ref;
}

QString nodeInputRefId(const QJsonValue &value)
{
    if (!value.isArray())
        return {};

    const QJsonArray ref = value.toArray();
    if (ref.isEmpty())
        return {};

    const QJsonValue nodeValue = ref.at(0);
    if (nodeValue.isString())
        return nodeValue.toString().trimmed();
    if (nodeValue.isDouble())
        return QString::number(nodeValue.toInt());
    return {};
}

QString textFromClipEncode(const QJsonObject &prompt, const QString &nodeId)
{
    if (nodeId.trimmed().isEmpty())
        return {};

    const QJsonValue nodeValue = prompt.value(nodeId);
    if (!nodeValue.isObject())
        return {};

    const QJsonObject node = nodeValue.toObject();
    const QString classType = node.value(QStringLiteral("class_type")).toString().trimmed();
    const QJsonObject inputs = node.value(QStringLiteral("inputs")).toObject();

    if (classType == QStringLiteral("CLIPTextEncode"))
        return inputs.value(QStringLiteral("text")).toString().trimmed();

    const QStringList passthroughKeys = {
        QStringLiteral("text"),
        QStringLiteral("conditioning"),
        QStringLiteral("positive"),
        QStringLiteral("negative"),
        QStringLiteral("base_cond"),
        QStringLiteral("refiner_cond")
    };

    for (const QString &key : passthroughKeys)
    {
        const QString nextNodeId = nodeInputRefId(inputs.value(key));
        const QString nested = textFromClipEncode(prompt, nextNodeId);
        if (!nested.isEmpty())
            return nested;
    }

    return {};
}

QString compactBaseName(const QString &value)
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return {};

    const QFileInfo info(trimmed);
    const QString baseName = info.completeBaseName().trimmed();
    if (!baseName.isEmpty())
        return baseName;

    const QString fileName = info.fileName().trimmed();
    return fileName.isEmpty() ? trimmed : fileName;
}

QStringList widgetSchemaForClassType(const QString &classType)
{
    static const QHash<QString, QStringList> kSchemas = {
        {QStringLiteral("CheckpointLoaderSimple"), {QStringLiteral("ckpt_name")}},
        {QStringLiteral("CheckpointLoader"), {QStringLiteral("ckpt_name")}},
        {QStringLiteral("VAELoader"), {QStringLiteral("vae_name")}},
        {QStringLiteral("CLIPLoader"), {QStringLiteral("clip_name")}},
        {QStringLiteral("LoraLoader"), {QStringLiteral("lora_name"), QStringLiteral("strength_model"), QStringLiteral("strength_clip")}},
        {QStringLiteral("CLIPTextEncode"), {QStringLiteral("text")}},
        {QStringLiteral("EmptyLatentImage"), {QStringLiteral("width"), QStringLiteral("height"), QStringLiteral("batch_size")}},
        {QStringLiteral("KSampler"), {QStringLiteral("seed"), QStringLiteral("steps"), QStringLiteral("cfg"), QStringLiteral("sampler_name"), QStringLiteral("scheduler"), QStringLiteral("denoise")}},
        {QStringLiteral("KSamplerAdvanced"), {QStringLiteral("noise_seed"), QStringLiteral("steps"), QStringLiteral("cfg"), QStringLiteral("sampler_name"), QStringLiteral("scheduler"), QStringLiteral("start_at_step"), QStringLiteral("end_at_step"), QStringLiteral("return_with_leftover_noise")}},
        {QStringLiteral("LoadImage"), {QStringLiteral("image")}},
        {QStringLiteral("LoadImageMask"), {QStringLiteral("image"), QStringLiteral("channel")}},
        {QStringLiteral("LoadVideo"), {QStringLiteral("video")}},
        {QStringLiteral("SaveImage"), {QStringLiteral("filename_prefix")}},
        {QStringLiteral("SaveAnimatedWEBP"), {QStringLiteral("filename_prefix"), QStringLiteral("fps"), QStringLiteral("lossless"), QStringLiteral("quality"), QStringLiteral("method")}},
        {QStringLiteral("SaveWEBM"), {QStringLiteral("filename_prefix"), QStringLiteral("codec"), QStringLiteral("fps"), QStringLiteral("crf")}},
        {QStringLiteral("ImageScale"), {QStringLiteral("upscale_method"), QStringLiteral("width"), QStringLiteral("height"), QStringLiteral("crop")}},
        {QStringLiteral("ControlNetLoader"), {QStringLiteral("control_net_name")}},
        {QStringLiteral("ControlNetApply"), {QStringLiteral("strength")}},
        {QStringLiteral("ControlNetApplyAdvanced"), {QStringLiteral("strength"), QStringLiteral("start_percent"), QStringLiteral("end_percent")}},
        {QStringLiteral("Note"), {QStringLiteral("text")}},
    };
    return kSchemas.value(classType);
}

bool valueIsLinkedInput(const QJsonObject &inputObj)
{
    const QJsonValue linkValue = inputObj.value(QStringLiteral("link"));
    if (linkValue.isDouble())
        return linkValue.toInt() > 0;
    if (linkValue.isString())
        return !linkValue.toString().trimmed().isEmpty() && linkValue.toString() != QStringLiteral("0");
    return false;
}

QString linkIdFromInput(const QJsonObject &inputObj)
{
    const QJsonValue linkValue = inputObj.value(QStringLiteral("link"));
    if (linkValue.isDouble())
        return QString::number(linkValue.toInt());
    if (linkValue.isString())
        return linkValue.toString().trimmed();
    return {};
}

bool inputOwnsWidget(const QJsonObject &inputObj)
{
    return inputObj.value(QStringLiteral("widget")).isObject();
}

QString nextSchemaName(const QStringList &schema, int *cursor, const QSet<QString> &used)
{
    if (!cursor)
        return {};
    while (*cursor < schema.size())
    {
        const QString candidate = schema.at(*cursor);
        ++(*cursor);
        if (!candidate.isEmpty() && !used.contains(candidate))
            return candidate;
    }
    return {};
}

bool mapSpecialWidgetInputs(
    const QString &classType,
    const QString &nodeId,
    const QJsonArray &widgetValues,
    QJsonObject *inputs,
    QSet<QString> *assignedNames,
    QStringList *warnings)
{
    if (!inputs || !assignedNames)
        return false;

    if (classType != QStringLiteral("KSamplerAdvanced"))
        return false;

    const QStringList mappedNames = {
        QStringLiteral("add_noise"),
        QStringLiteral("noise_seed"),
        QStringLiteral("steps"),
        QStringLiteral("cfg"),
        QStringLiteral("sampler_name"),
        QStringLiteral("scheduler"),
        QStringLiteral("start_at_step"),
        QStringLiteral("end_at_step"),
        QStringLiteral("return_with_leftover_noise")
    };

    const int expectedUiWidgetCount = 10; // includes UI-only seed control mode after noise_seed
    const int usableCount = qMin(widgetValues.size(), expectedUiWidgetCount);
    const int valueIndexes[] = {0, 1, 3, 4, 5, 6, 7, 8, 9};

    for (int i = 0; i < mappedNames.size(); ++i)
    {
        const int valueIndex = valueIndexes[i];
        if (valueIndex >= usableCount)
            break;

        inputs->insert(mappedNames.at(i), widgetValues.at(valueIndex));
        assignedNames->insert(mappedNames.at(i));
    }

    if (widgetValues.size() < expectedUiWidgetCount)
    {
        if (warnings)
        {
            warnings->push_back(QStringLiteral("Node %1 (%2) has %3 widget values but %4 were expected for deterministic compilation.")
                                    .arg(nodeId, classType)
                                    .arg(widgetValues.size())
                                    .arg(expectedUiWidgetCount));
        }
    }
    else if (widgetValues.size() > expectedUiWidgetCount)
    {
        if (warnings)
        {
            warnings->push_back(QStringLiteral("Node %1 (%2) has %3 extra widget values beyond the supported KSamplerAdvanced mapping.")
                                    .arg(nodeId, classType)
                                    .arg(widgetValues.size() - expectedUiWidgetCount));
        }
    }

    return true;
}

const QSet<QString> kCheckpointInputNames = {
    QStringLiteral("ckpt_name"),
    QStringLiteral("checkpoint"),
    QStringLiteral("model"),
    QStringLiteral("model_name")
};

const QSet<QString> kLoraInputNames = {
    QStringLiteral("lora_name"),
    QStringLiteral("lora")
};

const QSet<QString> kLoraStrengthInputNames = {
    QStringLiteral("strength_model"),
    QStringLiteral("strength"),
    QStringLiteral("lora_strength"),
    QStringLiteral("weight")
};

const QSet<QString> kImageInputNames = {
    QStringLiteral("image"),
    QStringLiteral("input_image"),
    QStringLiteral("image_path")
};

bool hasLikelyModelExtension(const QString &value)
{
    const QString suffix = QFileInfo(value.trimmed()).suffix().trimmed().toLower();
    return suffix == QStringLiteral("safetensors")
        || suffix == QStringLiteral("ckpt")
        || suffix == QStringLiteral("pt")
        || suffix == QStringLiteral("pth")
        || suffix == QStringLiteral("bin");
}

bool hasModelFolderHint(const QString &value)
{
    const QString normalized = value.trimmed().toLower();
    return normalized.contains(QStringLiteral("checkpoint"))
        || normalized.contains(QStringLiteral("checkpoints"))
        || normalized.contains(QStringLiteral("models/checkpoints"))
        || normalized.contains(QStringLiteral("models\\checkpoints"))
        || normalized.contains(QStringLiteral("loras"))
        || normalized.contains(QStringLiteral("models/loras"))
        || normalized.contains(QStringLiteral("models\\loras"));
}

bool isLikelyAssetValue(const QString &value)
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return false;
    if (trimmed.startsWith(QLatin1Char('<')) || trimmed.startsWith(QLatin1Char('{')))
        return false;
    return hasLikelyModelExtension(trimmed) || hasModelFolderHint(trimmed);
}

QString stringInputByNames(const QJsonObject &inputs, const QSet<QString> &names)
{
    for (auto it = inputs.constBegin(); it != inputs.constEnd(); ++it)
    {
        if (!names.contains(it.key().trimmed().toLower()) || !it.value().isString())
            continue;

        const QString value = it.value().toString().trimmed();
        if (!value.isEmpty())
            return value;
    }

    return {};
}

double doubleInputByNames(const QJsonObject &inputs, const QSet<QString> &names, double fallback)
{
    for (auto it = inputs.constBegin(); it != inputs.constEnd(); ++it)
    {
        if (!names.contains(it.key().trimmed().toLower()))
            continue;
        if (it.value().isDouble())
            return it.value().toDouble(fallback);
        if (it.value().isString())
        {
            bool ok = false;
            const double parsed = it.value().toString().trimmed().toDouble(&ok);
            if (ok)
                return parsed;
        }
    }

    return fallback;
}

QString extractCheckpointFromInputs(const QString &, const QJsonObject &inputs)
{
    const QString direct = stringInputByNames(inputs, kCheckpointInputNames);
    if (!direct.isEmpty() && isLikelyAssetValue(direct))
        return direct;

    for (auto it = inputs.constBegin(); it != inputs.constEnd(); ++it)
    {
        if (!it.value().isString())
            continue;

        const QString key = it.key().trimmed().toLower();
        if (!kCheckpointInputNames.contains(key) && !key.contains(QStringLiteral("checkpoint")) && !key.contains(QStringLiteral("ckpt")))
            continue;

        const QString value = it.value().toString().trimmed();
        if (isLikelyAssetValue(value))
            return value;
    }

    return {};
}

QString extractLoraNameFromInputs(const QString &classType, const QJsonObject &inputs)
{
    const QString loweredClassType = classType.trimmed().toLower();
    const QString direct = stringInputByNames(inputs, kLoraInputNames);
    if (!direct.isEmpty() && (isLikelyAssetValue(direct) || loweredClassType.contains(QStringLiteral("lora"))))
        return direct;

    for (auto it = inputs.constBegin(); it != inputs.constEnd(); ++it)
    {
        if (!it.value().isString())
            continue;

        const QString key = it.key().trimmed().toLower();
        if (!kLoraInputNames.contains(key) && !key.contains(QStringLiteral("lora")))
            continue;

        const QString value = it.value().toString().trimmed();
        if (!value.isEmpty() && (isLikelyAssetValue(value) || loweredClassType.contains(QStringLiteral("lora"))))
            return value;
    }

    return {};
}

QString extractImageInputFromInputs(const QString &classType, const QJsonObject &inputs)
{
    const QString loweredClassType = classType.trimmed().toLower();
    if (!loweredClassType.contains(QStringLiteral("image")) && loweredClassType != QStringLiteral("loadimage"))
        return {};

    const QString direct = stringInputByNames(inputs, kImageInputNames);
    if (!direct.isEmpty())
        return direct;

    return {};
}
}

WorkflowLibraryPage::WorkflowLibraryPage(QWidget *parent)
    : QWidget(parent)
{
    buildUi();
    applyTheme();
}

void WorkflowLibraryPage::setProjectRoot(const QString &projectRoot)
{
    projectRoot_ = projectRoot;
}

void WorkflowLibraryPage::setPythonExecutable(const QString &pythonExecutable)
{
    pythonExecutable_ = pythonExecutable;
}

void WorkflowLibraryPage::setImportedWorkflowsRoot(const QString &importedWorkflowsRoot)
{
    importedWorkflowsRoot_ = importedWorkflowsRoot;
    refreshLibrary();
}

void WorkflowLibraryPage::refreshLibrary()
{
    scanImportedWorkflows();
    rebuildFilters();
    rebuildList();
    updateSummary();
    updateDetailsPanel();
}

void WorkflowLibraryPage::onImportClicked()
{
    emit importWorkflowRequested();
}

void WorkflowLibraryPage::onRefreshClicked()
{
    refreshLibrary();
}

void WorkflowLibraryPage::onSearchChanged(const QString &)
{
    rebuildList();
    updateSummary();
}

void WorkflowLibraryPage::onFilterChanged()
{
    rebuildList();
    updateSummary();
}

void WorkflowLibraryPage::onCurrentWorkflowChanged(QListWidgetItem *, QListWidgetItem *)
{
    updateDetailsPanel();
}

void WorkflowLibraryPage::onLaunchClicked()
{
    const QListWidgetItem *item = workflowList_->currentItem();
    if (!item)
        return;

    const int index = item->data(Qt::UserRole).toInt();
    if (index < 0 || index >= workflows_.size())
        return;

    const WorkflowRecord &record = workflows_.at(index);
    if (record.readiness != ReadinessState::Ready)
        return;

    if (record.launchArtifactPath.trimmed().isEmpty())
        return;

    QJsonObject profile;
    profile.insert(QStringLiteral("profile_name"), record.displayName);
    profile.insert(QStringLiteral("name"), record.displayName);
    profile.insert(QStringLiteral("task_command"), record.modeId);
    profile.insert(QStringLiteral("media_type"), record.mediaType);
    profile.insert(QStringLiteral("backend_kind"), record.backend);
    profile.insert(QStringLiteral("backend"), record.backend);
    profile.insert(QStringLiteral("profile_path"), record.profilePath);
    profile.insert(QStringLiteral("workflow_path"), record.launchArtifactPath);
    profile.insert(QStringLiteral("workflow_source"), record.launchArtifactPath);
    profile.insert(QStringLiteral("workflow_format"), record.launchArtifactFormat);
    profile.insert(QStringLiteral("source_workflow_path"), record.sourceWorkflowPath);
    profile.insert(QStringLiteral("compiled_prompt_path"), record.compiledPromptPath);

    QJsonObject metadata;
    if (!record.missingCustomNodes.isEmpty())
    {
        QJsonArray missingNodes;
        for (const QString &node : record.missingCustomNodes)
            missingNodes.append(node);
        metadata.insert(QStringLiteral("missing_custom_nodes"), missingNodes);
    }

    if (!record.compileWarnings.isEmpty())
    {
        QJsonArray compileWarnings;
        for (const QString &warning : record.compileWarnings)
            compileWarnings.append(warning);
        metadata.insert(QStringLiteral("compile_warnings"), compileWarnings);
    }

    if (!record.launchValidationWarnings.isEmpty())
    {
        QJsonArray validationWarnings;
        for (const QString &warning : record.launchValidationWarnings)
            validationWarnings.append(warning);
        metadata.insert(QStringLiteral("launch_validation_warnings"), validationWarnings);
    }

    if (!record.runtimeAssetWarnings.isEmpty())
    {
        QJsonArray assetWarnings;
        for (const QString &warning : record.runtimeAssetWarnings)
            assetWarnings.append(warning);
        metadata.insert(QStringLiteral("runtime_asset_warnings"), assetWarnings);
    }

    if (!record.missingRuntimeAssets.isEmpty())
    {
        QJsonArray missingAssets;
        for (const QString &asset : record.missingRuntimeAssets)
            missingAssets.append(asset);
        metadata.insert(QStringLiteral("missing_runtime_assets"), missingAssets);
    }

    profile.insert(QStringLiteral("metadata"), metadata);
    emit launchWorkflowRequested(profile);
}

void WorkflowLibraryPage::onApplyClicked()
{
    const QListWidgetItem *item = workflowList_ ? workflowList_->currentItem() : nullptr;
    if (!item)
        return;

    const int index = item->data(Qt::UserRole).toInt();
    if (index < 0 || index >= workflows_.size())
        return;

    const WorkflowRecord &record = workflows_.at(index);
    if (!record.reusableDraftPresent)
        return;

    emit workflowDraftRequested(record.reusableDraft);
}

void WorkflowLibraryPage::onRevealFolderClicked()
{
    const QListWidgetItem *item = workflowList_->currentItem();
    if (!item)
        return;

    const int index = item->data(Qt::UserRole).toInt();
    if (index < 0 || index >= workflows_.size())
        return;

    const WorkflowRecord &record = workflows_.at(index);
    const QString folder = !record.importRoot.isEmpty()
        ? record.importRoot
        : QFileInfo(record.profilePath).absolutePath();

    if (!folder.isEmpty())
        QDesktopServices::openUrl(QUrl::fromLocalFile(folder));
}

void WorkflowLibraryPage::onOpenWorkflowJsonClicked()
{
    const QListWidgetItem *item = workflowList_->currentItem();
    if (!item)
        return;

    const int index = item->data(Qt::UserRole).toInt();
    if (index < 0 || index >= workflows_.size())
        return;

    const WorkflowRecord &record = workflows_.at(index);
    const QString path = !record.sourceWorkflowPath.isEmpty() ? record.sourceWorkflowPath : record.compiledPromptPath;
    if (!path.isEmpty())
        QDesktopServices::openUrl(QUrl::fromLocalFile(path));
}

void WorkflowLibraryPage::buildUi()
{
    auto *rootLayout = new QVBoxLayout(this);
    rootLayout->setContentsMargins(16, 16, 16, 16);
    rootLayout->setSpacing(12);

    titleLabel_ = new QLabel(tr("Workflow Library"), this);
    summaryLabel_ = new QLabel(this);
    summaryLabel_->setWordWrap(true);

    importButton_ = new QPushButton(tr("Import Workflow"), this);
    refreshButton_ = new QPushButton(tr("Refresh Library"), this);

    connect(importButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onImportClicked);
    connect(refreshButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onRefreshClicked);

    auto *headerRow = new QHBoxLayout();
    headerRow->setSpacing(8);
    headerRow->addWidget(importButton_);
    headerRow->addWidget(refreshButton_);
    headerRow->addStretch(1);

    searchEdit_ = new QLineEdit(this);
    searchEdit_->setPlaceholderText(tr("Search by workflow name, task, media type, or tags"));

    taskFilter_ = new QComboBox(this);
    backendFilter_ = new QComboBox(this);
    readinessFilter_ = new QComboBox(this);

    connect(searchEdit_, &QLineEdit::textChanged, this, &WorkflowLibraryPage::onSearchChanged);
    connect(taskFilter_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &WorkflowLibraryPage::onFilterChanged);
    connect(backendFilter_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &WorkflowLibraryPage::onFilterChanged);
    connect(readinessFilter_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &WorkflowLibraryPage::onFilterChanged);

    auto *filterRow = new QHBoxLayout();
    filterRow->setSpacing(8);
    filterRow->addWidget(searchEdit_, 1);
    filterRow->addWidget(taskFilter_);
    filterRow->addWidget(backendFilter_);
    filterRow->addWidget(readinessFilter_);

    workflowList_ = new QListWidget(this);
    connect(workflowList_, &QListWidget::currentItemChanged, this, &WorkflowLibraryPage::onCurrentWorkflowChanged);

    auto *detailPane = new QWidget(this);
    auto *detailLayout = new QVBoxLayout(detailPane);
    detailLayout->setContentsMargins(0, 0, 0, 0);
    detailLayout->setSpacing(8);

    detailTitleLabel_ = new QLabel(detailPane);
    detailMetaLabel_ = new QLabel(detailPane);
    detailMetaLabel_->setWordWrap(true);

    detailStatusLabel_ = new QLabel(detailPane);
    detailStatusLabel_->setWordWrap(true);

    detailText_ = new QPlainTextEdit(detailPane);
    detailText_->setReadOnly(true);

    applyButton_ = new QPushButton(tr("Open in T2I"), detailPane);
    launchButton_ = new QPushButton(tr("Launch Workflow"), detailPane);
    revealFolderButton_ = new QPushButton(tr("Reveal Folder"), detailPane);
    openWorkflowJsonButton_ = new QPushButton(tr("Open Workflow JSON"), detailPane);

    connect(applyButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onApplyClicked);
    connect(launchButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onLaunchClicked);
    connect(revealFolderButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onRevealFolderClicked);
    connect(openWorkflowJsonButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onOpenWorkflowJsonClicked);

    auto *detailButtons = new QHBoxLayout();
    detailButtons->setSpacing(8);
    detailButtons->addWidget(applyButton_);
    detailButtons->addWidget(launchButton_);
    detailButtons->addWidget(revealFolderButton_);
    detailButtons->addWidget(openWorkflowJsonButton_);
    detailButtons->addStretch(1);

    detailLayout->addWidget(detailTitleLabel_);
    detailLayout->addWidget(detailMetaLabel_);
    detailLayout->addWidget(detailStatusLabel_);
    detailLayout->addWidget(detailText_, 1);
    detailLayout->addLayout(detailButtons);

    auto *splitter = new QSplitter(Qt::Horizontal, this);
    splitter->addWidget(workflowList_);
    splitter->addWidget(detailPane);
    splitter->setStretchFactor(0, 0);
    splitter->setStretchFactor(1, 1);
    splitter->setSizes({360, 800});

    rootLayout->addWidget(titleLabel_);
    rootLayout->addWidget(summaryLabel_);
    rootLayout->addLayout(headerRow);
    rootLayout->addLayout(filterRow);
    rootLayout->addWidget(splitter, 1);

    clearDetailsPanel();
    rebuildFilters();
    updateSummary();
}

void WorkflowLibraryPage::applyTheme()
{
    setStyleSheet(ThemeManager::instance().shellStyleSheet());
}

void WorkflowLibraryPage::scanImportedWorkflows()
{
    workflows_.clear();

    if (importedWorkflowsRoot_.isEmpty())
        return;

    const QDir rootDir(importedWorkflowsRoot_);
    if (!rootDir.exists())
        return;

    QDirIterator it(
        importedWorkflowsRoot_,
        QStringList() << QStringLiteral("profile.json"),
        QDir::Files,
        QDirIterator::Subdirectories);

    while (it.hasNext())
    {
        WorkflowRecord record = loadWorkflowRecord(it.next());
        if (record.workflowJsonPresent && record.sourceWorkflowFormat == QStringLiteral("comfy_ui_graph"))
            ensureCompiledPrompt(record);
        buildReusableDraft(record);
        updateRuntimeState(record);
        validateRuntimeAssets(record);
        classifyWorkflow(record);
        workflows_.push_back(record);
    }
}

WorkflowLibraryPage::WorkflowRecord WorkflowLibraryPage::loadWorkflowRecord(const QString &profilePath) const
{
    WorkflowRecord record;
    record.profilePath = profilePath;
    record.importRoot = QFileInfo(profilePath).absolutePath();

    QFile file(profilePath);
    if (!file.open(QIODevice::ReadOnly))
    {
        record.displayName = QFileInfo(profilePath).absolutePath();
        record.modeId = QStringLiteral("unknown");
        record.mediaType = QStringLiteral("unknown");
        record.backend = QStringLiteral("unknown");
        record.supportedInCurrentBuild = false;
        record.workflowJsonPresent = false;
        record.readiness = ReadinessState::NeedsReview;
        record.readinessLabel = tr("Needs review");
        record.readinessReason = tr("Profile could not be read.");
        return record;
    }

    const QJsonDocument document = QJsonDocument::fromJson(file.readAll());
    const QJsonObject object = document.object();

    record.displayName = safeObjectString(object, {
        QStringLiteral("display_name"),
        QStringLiteral("name"),
        QStringLiteral("title")
    });
    if (record.displayName.isEmpty())
        record.displayName = QFileInfo(record.importRoot).fileName();

    record.modeId = normalizedModeId(safeObjectString(object, {
        QStringLiteral("mode_id"),
        QStringLiteral("task"),
        QStringLiteral("mode"),
        QStringLiteral("task_command")
    }));
    record.mediaType = safeObjectString(object, {
        QStringLiteral("media_type"),
        QStringLiteral("media"),
        QStringLiteral("artifact_type")
    }).trimmed().toLower();
    record.backend = safeObjectString(object, {
        QStringLiteral("backend"),
        QStringLiteral("backend_type"),
        QStringLiteral("backend_kind")
    }).trimmed();

    record.tags = safeObjectStringList(object, {
        QStringLiteral("tags"),
        QStringLiteral("labels")
    });

    record.importRoot = resolvePossiblyRelativePath(
        record.importRoot,
        safeObjectString(object, {QStringLiteral("import_root")})
    );
    if (record.importRoot.isEmpty())
        record.importRoot = QFileInfo(profilePath).absolutePath();

    record.compiledPromptPath = QDir(record.importRoot).filePath(QStringLiteral("prompt_api.json"));

    record.sourceWorkflowPath = resolvePossiblyRelativePath(
        record.importRoot,
        safeObjectString(object, {
            QStringLiteral("workflow_json"),
            QStringLiteral("workflow_path"),
            QStringLiteral("workflow_json_path"),
            QStringLiteral("workflow_source")
        })
    );
    if (record.sourceWorkflowPath.isEmpty())
    {
        const QString defaultWorkflow = QDir(record.importRoot).filePath(QStringLiteral("workflow.json"));
        if (QFileInfo::exists(defaultWorkflow))
            record.sourceWorkflowPath = defaultWorkflow;
    }

    record.scanReportPath = resolvePossiblyRelativePath(
        record.importRoot,
        safeObjectString(object, {
            QStringLiteral("scan_report"),
            QStringLiteral("scan_report_path")
        })
    );
    if (record.scanReportPath.isEmpty())
    {
        const QString defaultScan = QDir(record.importRoot).filePath(QStringLiteral("scan_report.json"));
        if (QFileInfo::exists(defaultScan))
            record.scanReportPath = defaultScan;
    }

    record.missingCustomNodes = safeObjectStringList(object, {
        QStringLiteral("missing_custom_nodes"),
        QStringLiteral("missing_nodes")
    });
    record.warnings = safeObjectStringList(object, {
        QStringLiteral("warnings"),
        QStringLiteral("scan_warnings")
    });
    record.referencedModelCount = safeObjectInt(object, {
        QStringLiteral("referenced_model_count"),
        QStringLiteral("models_referenced"),
        QStringLiteral("required_models_count")
    }, 0);
    record.unresolvedDependencyActions = safeObjectInt(object, {
        QStringLiteral("unresolved_dependency_actions"),
        QStringLiteral("unresolved_actions_count")
    }, 0);

    if (!record.scanReportPath.isEmpty())
    {
        QFile scanFile(record.scanReportPath);
        if (scanFile.open(QIODevice::ReadOnly))
        {
            const QJsonDocument scanDoc = QJsonDocument::fromJson(scanFile.readAll());
            const QJsonObject scanObj = scanDoc.object();

            QStringList scanMissing = safeObjectStringList(scanObj, {
                QStringLiteral("missing_custom_nodes"),
                QStringLiteral("missing_nodes")
            });

            if (scanMissing.isEmpty()
                && scanObj.contains(QStringLiteral("missing_custom_nodes"))
                && scanObj.value(QStringLiteral("missing_custom_nodes")).isArray())
            {
                const QJsonArray array = scanObj.value(QStringLiteral("missing_custom_nodes")).toArray();
                for (const QJsonValue &value : array)
                {
                    if (value.isString())
                    {
                        scanMissing.push_back(value.toString());
                    }
                    else if (value.isObject())
                    {
                        const QJsonObject nodeObj = value.toObject();
                        const QString name = safeObjectString(nodeObj, {
                            QStringLiteral("class_type"),
                            QStringLiteral("node_class"),
                            QStringLiteral("name")
                        });
                        if (!name.isEmpty())
                            scanMissing.push_back(name);
                    }
                }
            }

            for (const QString &node : scanMissing)
            {
                if (!record.missingCustomNodes.contains(node))
                    record.missingCustomNodes.push_back(node);
            }

            const QStringList scanWarnings = safeObjectStringList(scanObj, {
                QStringLiteral("warnings"),
                QStringLiteral("notes")
            });
            for (const QString &warning : scanWarnings)
            {
                if (!record.warnings.contains(warning))
                    record.warnings.push_back(warning);
            }

            if (record.referencedModelCount == 0)
            {
                record.referencedModelCount = safeObjectInt(scanObj, {
                    QStringLiteral("referenced_model_count"),
                    QStringLiteral("models_referenced"),
                    QStringLiteral("required_models_count")
                }, 0);
            }

            if (record.unresolvedDependencyActions == 0)
            {
                record.unresolvedDependencyActions = safeObjectInt(scanObj, {
                    QStringLiteral("unresolved_dependency_actions"),
                    QStringLiteral("unresolved_actions_count")
                }, 0);
            }
        }
    }

    record.workflowJsonPresent = !record.sourceWorkflowPath.isEmpty() && QFileInfo::exists(record.sourceWorkflowPath);
    record.supportedInCurrentBuild = isImageMode(record.modeId, record.mediaType)
        && !isVideoMode(record.modeId, record.mediaType);

    if (record.workflowJsonPresent)
    {
        QFile workflowFile(record.sourceWorkflowPath);
        if (workflowFile.open(QIODevice::ReadOnly))
        {
            const QJsonDocument workflowDoc = QJsonDocument::fromJson(workflowFile.readAll());
            if (workflowDoc.isObject())
                record.sourceWorkflowFormat = detectWorkflowFormat(workflowDoc.object());
        }
    }

    if (QFileInfo::exists(record.compiledPromptPath))
    {
        QFile compiledFile(record.compiledPromptPath);
        if (compiledFile.open(QIODevice::ReadOnly))
        {
            const QJsonDocument compiledDoc = QJsonDocument::fromJson(compiledFile.readAll());
            if (compiledDoc.isObject())
            {
                record.compiledPromptFormat = detectWorkflowFormat(compiledDoc.object());
                record.compiledPromptPresent = (record.compiledPromptFormat == QStringLiteral("comfy_api_prompt"));
            }
        }
    }

    record.launchArtifactPath.clear();
    record.launchArtifactFormat = QStringLiteral("unknown");

    if (record.compiledPromptPresent)
    {
        record.launchArtifactPath = record.compiledPromptPath;
        record.launchArtifactFormat = record.compiledPromptFormat;
    }
    else if (record.sourceWorkflowFormat == QStringLiteral("comfy_api_prompt"))
    {
        record.launchArtifactPath = record.sourceWorkflowPath;
        record.launchArtifactFormat = record.sourceWorkflowFormat;
    }

    if (!record.launchArtifactPath.isEmpty())
    {
        QFile launchFile(record.launchArtifactPath);
        record.launchArtifactValidated = true;

        if (launchFile.open(QIODevice::ReadOnly))
        {
            const QJsonDocument launchDoc = QJsonDocument::fromJson(launchFile.readAll());
            if (launchDoc.isObject())
            {
                record.launchArtifactValid = validateApiPromptObject(
                    launchDoc.object(),
                    &record.launchValidationErrors,
                    &record.launchValidationWarnings);
            }
            else
            {
                record.launchArtifactValid = false;
                record.launchValidationErrors.push_back(tr("Launch artifact is not a JSON object."));
            }
        }
        else
        {
            record.launchArtifactValid = false;
            record.launchValidationErrors.push_back(
                tr("Launch artifact could not be opened: %1").arg(record.launchArtifactPath));
        }
    }

    record.apiPromptCompatible =
        !record.launchArtifactPath.isEmpty()
        && record.launchArtifactFormat == QStringLiteral("comfy_api_prompt");

    return record;
}

void WorkflowLibraryPage::updateRuntimeState(WorkflowRecord &record) const
{
    record.runtimeProbe.ok = true;
    record.runtimeProbe.message = tr("Runtime ready.");

    if (record.backend.compare(QStringLiteral("comfy_workflow"), Qt::CaseInsensitive) != 0)
        return;

    if (!record.supportedInCurrentBuild)
    {
        record.runtimeProbe.ok = false;
        record.runtimeProbe.message = tr("Video execution is not implemented in the current build.");
        return;
    }

    record.runtimeProbe = probeComfyRuntime();
}

void WorkflowLibraryPage::validateRuntimeAssets(WorkflowRecord &record) const
{
    record.runtimeAssetValidationAttempted = false;
    record.runtimeAssetValidationPassed = false;
    record.runtimeAssetValidationMessage.clear();
    record.missingRuntimeAssets.clear();
    record.runtimeAssetWarnings.clear();

    if (record.backend.compare(QStringLiteral("comfy_workflow"), Qt::CaseInsensitive) != 0)
        return;

    if (!record.runtimeProbe.ok || !record.apiPromptCompatible || record.launchArtifactPath.trimmed().isEmpty())
        return;

    QFile launchFile(record.launchArtifactPath);
    if (!launchFile.open(QIODevice::ReadOnly))
    {
        record.runtimeAssetValidationAttempted = true;
        record.runtimeAssetValidationMessage = tr("Launch artifact could not be opened for runtime asset validation.");
        record.missingRuntimeAssets.push_back(
            tr("Launch artifact could not be opened: %1").arg(record.launchArtifactPath));
        return;
    }

    const QJsonDocument launchDoc = QJsonDocument::fromJson(launchFile.readAll());
    if (!launchDoc.isObject())
    {
        record.runtimeAssetValidationAttempted = true;
        record.runtimeAssetValidationMessage = tr("Launch artifact is not a JSON object.");
        record.missingRuntimeAssets.push_back(tr("Launch artifact is not a JSON object."));
        return;
    }

    const RuntimeAssetCatalogResult catalog = fetchComfyAssetCatalog();
    record.runtimeAssetValidationAttempted = true;
    record.runtimeAssetValidationMessage = catalog.message;

    if (!catalog.ok)
    {
        record.runtimeAssetWarnings.push_back(
            catalog.message.isEmpty()
                ? tr("Comfy object_info could not be read for runtime asset validation.")
                : catalog.message);
        return;
    }

    const QJsonObject prompt = launchDoc.object();
    QStringList missingAssets;
    QStringList warnings;

    for (auto it = prompt.constBegin(); it != prompt.constEnd(); ++it)
    {
        if (!it.value().isObject())
            continue;

        const QString nodeId = it.key();
        const QJsonObject nodeObj = it.value().toObject();
        const QString classType = nodeObj.value(QStringLiteral("class_type")).toString().trimmed();
        const QStringList assetInputs = assetInputNamesForClassType(classType);
        if (assetInputs.isEmpty())
            continue;

        const QJsonObject inputs = nodeObj.value(QStringLiteral("inputs")).toObject();
        for (const QString &inputName : assetInputs)
        {
            const QJsonValue inputValue = inputs.value(inputName);
            if (!inputValue.isString())
                continue;

            const QString requestedValue = inputValue.toString().trimmed();
            if (requestedValue.isEmpty())
                continue;

            const QString key = assetCatalogKey(classType, inputName);
            if (!catalog.cataloguedKeys.contains(key))
            {
                warnings.push_back(
                    tr("Comfy object_info did not expose option values for %1.%2 while validating node %3.")
                        .arg(classType, inputName, nodeId));
                continue;
            }

            const QSet<QString> allowedValues = catalog.allowedValuesByKey.value(key);
            if (!allowedValues.contains(requestedValue))
            {
                missingAssets.push_back(
                    tr("Node %1 (%2) requires %3 '%4', but the runtime does not currently expose that asset.")
                        .arg(nodeId, classType, inputName, requestedValue));
            }
        }
    }

    record.runtimeAssetWarnings = warnings;
    record.missingRuntimeAssets = missingAssets;
    record.runtimeAssetValidationPassed = missingAssets.isEmpty();

    if (record.runtimeAssetValidationPassed)
    {
        record.runtimeAssetValidationMessage = catalog.message.isEmpty()
            ? tr("Runtime asset validation passed.")
            : catalog.message;
    }
    else if (record.runtimeAssetValidationMessage.isEmpty())
    {
        record.runtimeAssetValidationMessage = tr("One or more loader assets are unavailable in the current Comfy runtime.");
    }
}

void WorkflowLibraryPage::classifyWorkflow(WorkflowRecord &record) const
{
    if (!record.supportedInCurrentBuild)
    {
        record.readiness = ReadinessState::Unsupported;
        record.readinessLabel = tr("Unsupported");
        record.readinessReason = tr("This workflow targets video execution, which is not implemented in the current build.");
        return;
    }

    if (!record.workflowJsonPresent)
    {
        record.readiness = ReadinessState::MissingWorkflow;
        record.readinessLabel = tr("Missing workflow");
        record.readinessReason = tr("The workflow profile is present, but workflow.json is missing.");
        return;
    }

    if (record.backend.compare(QStringLiteral("comfy_workflow"), Qt::CaseInsensitive) == 0
        && !record.apiPromptCompatible)
    {
        record.readiness = ReadinessState::NeedsCompilation;
        record.readinessLabel = tr("Needs compilation");
        record.readinessReason = record.compileError.trimmed().isEmpty()
            ? tr("This imported workflow still does not have a validated API prompt launch artifact.")
            : tr("Compilation failed: %1").arg(record.compileError);
        return;
    }

    if (!record.missingCustomNodes.isEmpty() || record.unresolvedDependencyActions > 0)
    {
        record.readiness = ReadinessState::MissingDependencies;
        record.readinessLabel = tr("Missing dependencies");
        record.readinessReason = tr("This workflow still needs runtime dependencies before it can launch.");
        return;
    }

    if (record.backend.compare(QStringLiteral("comfy_workflow"), Qt::CaseInsensitive) == 0)
    {
        if (!record.launchArtifactValidated)
        {
            record.readiness = ReadinessState::NeedsReview;
            record.readinessLabel = tr("Needs review");
            record.readinessReason = tr("The launch artifact has not been validated yet.");
            return;
        }

        if (!record.launchArtifactValid)
        {
            record.readiness = ReadinessState::NeedsReview;
            record.readinessLabel = tr("Needs review");
            record.readinessReason = record.launchValidationErrors.isEmpty()
                ? tr("The compiled prompt failed validation.")
                : tr("Prompt validation failed: %1").arg(record.launchValidationErrors.front());
            return;
        }

        if (!record.launchValidationWarnings.isEmpty())
        {
            record.readiness = ReadinessState::NeedsReview;
            record.readinessLabel = tr("Needs review");
            record.readinessReason = tr("Prompt validation warning: %1").arg(record.launchValidationWarnings.front());
            return;
        }
    }

    if (!record.runtimeProbe.ok)
    {
        record.readiness = ReadinessState::RuntimeOffline;
        record.readinessLabel = tr("Runtime offline");
        record.readinessReason = tr("SpellVision could not reach the configured runtime. Start or connect the runtime before launch.");
        return;
    }

    if (record.backend.compare(QStringLiteral("comfy_workflow"), Qt::CaseInsensitive) == 0
        && record.runtimeAssetValidationAttempted
        && !record.runtimeAssetValidationPassed)
    {
        record.readiness = ReadinessState::MissingDependencies;
        record.readinessLabel = tr("Missing dependencies");
        record.readinessReason = !record.missingRuntimeAssets.isEmpty()
            ? record.missingRuntimeAssets.front()
            : (!record.runtimeAssetValidationMessage.isEmpty()
                   ? record.runtimeAssetValidationMessage
                   : tr("The workflow references runtime assets that are not currently available."));
        return;
    }

    if (!record.compileWarnings.isEmpty())
    {
        record.readiness = ReadinessState::NeedsReview;
        record.readinessLabel = tr("Needs review");
        record.readinessReason = tr("The workflow compiled with warnings. Inspect the detail pane before launch.");
        return;
    }

    if (!record.warnings.isEmpty())
    {
        record.readiness = ReadinessState::NeedsReview;
        record.readinessLabel = tr("Needs review");
        record.readinessReason = tr("The workflow can be inspected, but warnings are still present.");
        return;
    }

    record.readiness = ReadinessState::Ready;
    record.readinessLabel = tr("Ready");
    record.readinessReason = tr("This workflow is currently launchable.");
}

bool WorkflowLibraryPage::ensureCompiledPrompt(WorkflowRecord &record) const
{
    if (!record.workflowJsonPresent)
        return false;

    if (record.sourceWorkflowFormat == QStringLiteral("comfy_api_prompt"))
    {
        record.compiledPromptPath.clear();
        record.compiledPromptPresent = false;
        record.compiledPromptFormat = QStringLiteral("unknown");
        record.launchArtifactPath = record.sourceWorkflowPath;
        record.launchArtifactFormat = record.sourceWorkflowFormat;
        record.apiPromptCompatible = true;

        QFile launchFile(record.launchArtifactPath);
        record.launchArtifactValidated = true;
        if (launchFile.open(QIODevice::ReadOnly))
        {
            const QJsonDocument launchDoc = QJsonDocument::fromJson(launchFile.readAll());
            if (launchDoc.isObject())
            {
                record.launchArtifactValid = validateApiPromptObject(
                    launchDoc.object(),
                    &record.launchValidationErrors,
                    &record.launchValidationWarnings);
            }
            else
            {
                record.launchArtifactValid = false;
                record.launchValidationErrors = {tr("Launch artifact is not a JSON object.")};
            }
        }
        else
        {
            record.launchArtifactValid = false;
            record.launchValidationErrors = {tr("Launch artifact could not be opened: %1").arg(record.launchArtifactPath)};
        }

        return true;
    }

    if (record.sourceWorkflowFormat != QStringLiteral("comfy_ui_graph"))
        return false;

    record.compiledPromptPresent = false;
    record.compiledPromptFormat = QStringLiteral("unknown");
    record.launchArtifactPath.clear();
    record.launchArtifactFormat = QStringLiteral("unknown");
    record.apiPromptCompatible = false;
    record.launchArtifactValidated = false;
    record.launchArtifactValid = false;
    record.launchValidationErrors.clear();
    record.launchValidationWarnings.clear();

    QFile sourceFile(record.sourceWorkflowPath);
    if (!sourceFile.open(QIODevice::ReadOnly))
    {
        record.compileError = tr("Could not open source workflow for compilation.");
        return false;
    }

    const QJsonDocument sourceDoc = QJsonDocument::fromJson(sourceFile.readAll());
    if (!sourceDoc.isObject())
    {
        record.compileError = tr("Source workflow is not a JSON object.");
        return false;
    }

    QStringList compileWarnings;
    QString compileError;
    const QJsonObject compiledPrompt = compileUiGraphToApiPrompt(sourceDoc.object(), &compileWarnings, &compileError);
    record.compileWarnings = compileWarnings;
    record.compileError = compileError;

    if (compiledPrompt.isEmpty())
        return false;

    QFile outFile(record.compiledPromptPath);
    if (!outFile.open(QIODevice::WriteOnly | QIODevice::Truncate))
    {
        record.compileError = tr("Compiled prompt was created in memory but could not be written to %1.").arg(record.compiledPromptPath);
        return false;
    }

    outFile.write(QJsonDocument(compiledPrompt).toJson(QJsonDocument::Indented));
    outFile.close();

    record.compiledPromptPresent = true;
    record.compiledPromptFormat = QStringLiteral("comfy_api_prompt");
    record.launchArtifactPath = record.compiledPromptPath;
    record.launchArtifactFormat = record.compiledPromptFormat;
    record.launchArtifactValidated = true;
    record.launchArtifactValid = validateApiPromptObject(
        compiledPrompt,
        &record.launchValidationErrors,
        &record.launchValidationWarnings);
    record.apiPromptCompatible = record.launchArtifactValid;

    return true;
}

void WorkflowLibraryPage::buildReusableDraft(WorkflowRecord &record) const
{
    record.reusableDraftPresent = false;
    record.reusableDraftSafeToSubmit = false;
    record.reusableDraftReason.clear();
    record.reusableDraft = {};

    if (!isImageMode(record.modeId, record.mediaType))
    {
        record.reusableDraftReason = tr("Only image workflows can currently open as editable drafts.");
        return;
    }

    QString promptPath = record.compiledPromptPath.trimmed();
    if (promptPath.isEmpty() || !QFileInfo::exists(promptPath))
    {
        if (record.sourceWorkflowFormat == QStringLiteral("comfy_api_prompt") && !record.sourceWorkflowPath.trimmed().isEmpty())
            promptPath = record.sourceWorkflowPath.trimmed();
    }

    if (promptPath.isEmpty() || !QFileInfo::exists(promptPath))
    {
        record.reusableDraftReason = tr("No compiled or API prompt is available for reusable handoff.");
        return;
    }

    QFile file(promptPath);
    if (!file.open(QIODevice::ReadOnly))
    {
        record.reusableDraftReason = tr("Compiled prompt could not be opened.");
        return;
    }

    QJsonParseError parseError{};
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
    {
        record.reusableDraftReason = tr("Compiled prompt is not valid JSON.");
        return;
    }

    const QJsonObject prompt = doc.object();
    if (prompt.isEmpty())
    {
        record.reusableDraftReason = tr("Compiled prompt is empty.");
        return;
    }

    QString checkpointName;
    QStringList loraNames;
    QList<double> loraStrengths;
    QSet<QString> seenLoras;
    QString samplerName;
    QString schedulerName;
    int steps = 0;
    double cfg = 0.0;
    qlonglong seed = 0;
    int width = 0;
    int height = 0;
    QString positivePrompt;
    QString negativePrompt;
    QString inputImage;

    for (auto it = prompt.constBegin(); it != prompt.constEnd(); ++it)
    {
        const QJsonObject node = it.value().toObject();
        const QString classType = node.value(QStringLiteral("class_type")).toString().trimmed();
        const QJsonObject inputs = node.value(QStringLiteral("inputs")).toObject();

        if (checkpointName.isEmpty())
        {
            const QString extractedCheckpoint = extractCheckpointFromInputs(classType, inputs);
            if (!extractedCheckpoint.isEmpty())
                checkpointName = extractedCheckpoint;
        }

        const QString extractedLora = extractLoraNameFromInputs(classType, inputs);
        if (!extractedLora.isEmpty())
        {
            const QString dedupeKey = extractedLora.trimmed().toLower();
            if (!seenLoras.contains(dedupeKey))
            {
                seenLoras.insert(dedupeKey);
                loraNames.push_back(extractedLora);
                loraStrengths.push_back(doubleInputByNames(inputs, kLoraStrengthInputNames, 1.0));
            }
        }

        if ((classType == QStringLiteral("KSampler") || classType == QStringLiteral("KSamplerAdvanced")) && steps <= 0)
        {
            samplerName = inputs.value(QStringLiteral("sampler_name")).toString().trimmed();
            schedulerName = inputs.value(QStringLiteral("scheduler")).toString().trimmed();
            steps = inputs.value(QStringLiteral("steps")).toInt(0);
            cfg = inputs.value(QStringLiteral("cfg")).toDouble(0.0);
            seed = inputs.value(classType == QStringLiteral("KSampler") ? QStringLiteral("seed") : QStringLiteral("noise_seed")).toVariant().toLongLong();
            positivePrompt = textFromClipEncode(prompt, nodeInputRefId(inputs.value(QStringLiteral("positive"))));
            negativePrompt = textFromClipEncode(prompt, nodeInputRefId(inputs.value(QStringLiteral("negative"))));
        }

        if (width <= 0)
            width = inputs.value(QStringLiteral("width")).toInt(width);
        if (height <= 0)
            height = inputs.value(QStringLiteral("height")).toInt(height);

        if (inputImage.isEmpty())
        {
            const QString extractedInputImage = extractImageInputFromInputs(classType, inputs);
            if (!extractedInputImage.isEmpty())
                inputImage = extractedInputImage;
        }
    }

    QJsonObject draft;
    draft.insert(QStringLiteral("source_name"), record.displayName);
    draft.insert(QStringLiteral("source_profile_path"), record.profilePath);
    draft.insert(QStringLiteral("source_workflow_path"), record.sourceWorkflowPath);
    draft.insert(QStringLiteral("compiled_prompt_path"), promptPath);
    draft.insert(QStringLiteral("mode_id"), normalizedModeId(record.modeId));
    draft.insert(QStringLiteral("media_type"), record.mediaType);
    draft.insert(QStringLiteral("backend"), record.backend);
    draft.insert(QStringLiteral("prompt"), positivePrompt);
    draft.insert(QStringLiteral("negative_prompt"), negativePrompt);
    draft.insert(QStringLiteral("checkpoint"), checkpointName);
    draft.insert(QStringLiteral("checkpoint_display"), compactBaseName(checkpointName));
    draft.insert(QStringLiteral("sampler"), samplerName);
    draft.insert(QStringLiteral("scheduler"), schedulerName);
    draft.insert(QStringLiteral("steps"), steps);
    draft.insert(QStringLiteral("cfg"), cfg);
    draft.insert(QStringLiteral("seed"), QString::number(seed));
    draft.insert(QStringLiteral("width"), width);
    draft.insert(QStringLiteral("height"), height);
    if (!inputImage.isEmpty())
        draft.insert(QStringLiteral("input_image"), inputImage);

    QJsonArray loraArray;
    for (int i = 0; i < loraNames.size(); ++i)
    {
        QJsonObject loraEntry;
        loraEntry.insert(QStringLiteral("name"), loraNames.at(i));
        loraEntry.insert(QStringLiteral("display"), compactBaseName(loraNames.at(i)));
        loraEntry.insert(QStringLiteral("strength"), i < loraStrengths.size() ? loraStrengths.at(i) : 1.0);
        loraArray.append(loraEntry);
    }
    draft.insert(QStringLiteral("lora_stack"), loraArray);

    QStringList draftWarnings;
    bool safeToSubmit = true;
    if (checkpointName.trimmed().isEmpty())
    {
        safeToSubmit = false;
        draftWarnings.push_back(tr("No checkpoint could be inferred from the compiled prompt."));
    }
    if (loraNames.size() > 1)
    {
        draftWarnings.push_back(tr("This workflow uses %1 LoRAs. Review the imported stack before generating.").arg(loraNames.size()));
    }
    if (!record.missingRuntimeAssets.isEmpty())
    {
        safeToSubmit = false;
        draftWarnings.push_back(tr("Runtime asset validation failed for %1 imported assets. Remap the stack on the generation page before submitting.").arg(record.missingRuntimeAssets.size()));
    }
    if (!record.missingCustomNodes.isEmpty())
        draftWarnings.push_back(tr("The original workflow references missing custom nodes, so this draft should be treated as a reusable approximation."));

    QJsonArray warningArray;
    for (const QString &warning : draftWarnings)
        warningArray.append(warning);
    draft.insert(QStringLiteral("warnings"), warningArray);
    draft.insert(QStringLiteral("safe_to_submit"), safeToSubmit);
    draft.insert(QStringLiteral("supports_apply"), true);

    record.reusableDraftPresent = true;
    record.reusableDraftSafeToSubmit = safeToSubmit;
    record.reusableDraftReason = safeToSubmit ? tr("This workflow can open as an editable generation draft.") : tr("This workflow can open as an editable draft, but it still needs review before submission.");
    record.reusableDraft = draft;
}

void WorkflowLibraryPage::rebuildFilters()
{
    const QString taskCurrent = taskFilter_->currentData().toString();
    const QString backendCurrent = backendFilter_->currentData().toString();
    const QString readinessCurrent = readinessFilter_->currentData().toString();

    taskFilter_->blockSignals(true);
    backendFilter_->blockSignals(true);
    readinessFilter_->blockSignals(true);

    taskFilter_->clear();
    backendFilter_->clear();
    readinessFilter_->clear();

    taskFilter_->addItem(tr("All Tasks"), QString());
    backendFilter_->addItem(tr("All Backends"), QString());
    readinessFilter_->addItem(tr("All Readiness"), QString());

    QStringList tasks;
    QStringList backends;
    for (const WorkflowRecord &record : workflows_)
    {
        if (!record.modeId.isEmpty() && !tasks.contains(record.modeId))
            tasks.push_back(record.modeId);
        if (!record.backend.isEmpty() && !backends.contains(record.backend))
            backends.push_back(record.backend);
    }

    tasks.sort();
    backends.sort();

    for (const QString &task : tasks)
        taskFilter_->addItem(task.toUpper(), task);

    for (const QString &backend : backends)
        backendFilter_->addItem(backend, backend);

    readinessFilter_->addItem(tr("Ready"), readinessFilterKey(ReadinessState::Ready));
    readinessFilter_->addItem(tr("Unsupported"), readinessFilterKey(ReadinessState::Unsupported));
    readinessFilter_->addItem(tr("Needs Compilation"), readinessFilterKey(ReadinessState::NeedsCompilation));
    readinessFilter_->addItem(tr("Runtime Offline"), readinessFilterKey(ReadinessState::RuntimeOffline));
    readinessFilter_->addItem(tr("Missing Dependencies"), readinessFilterKey(ReadinessState::MissingDependencies));
    readinessFilter_->addItem(tr("Missing Workflow"), readinessFilterKey(ReadinessState::MissingWorkflow));
    readinessFilter_->addItem(tr("Needs Review"), readinessFilterKey(ReadinessState::NeedsReview));

    taskFilter_->setCurrentIndex(qMax(0, taskFilter_->findData(taskCurrent)));
    backendFilter_->setCurrentIndex(qMax(0, backendFilter_->findData(backendCurrent)));
    readinessFilter_->setCurrentIndex(qMax(0, readinessFilter_->findData(readinessCurrent)));

    taskFilter_->blockSignals(false);
    backendFilter_->blockSignals(false);
    readinessFilter_->blockSignals(false);
}

void WorkflowLibraryPage::rebuildList()
{
    workflowList_->clear();

    for (int i = 0; i < workflows_.size(); ++i)
    {
        const WorkflowRecord &record = workflows_.at(i);
        if (!matchesFilters(record))
            continue;

        auto *item = new QListWidgetItem(workflowList_);
        item->setData(Qt::UserRole, i);
        item->setText(workflowListLine(record));
        item->setToolTip(workflowSummaryText(record));
        workflowList_->addItem(item);
    }

    if (workflowList_->count() > 0)
        workflowList_->setCurrentRow(0);
    else
        clearDetailsPanel();
}

bool WorkflowLibraryPage::matchesFilters(const WorkflowRecord &record) const
{
    const QString search = searchEdit_->text().trimmed().toLower();
    if (!search.isEmpty())
    {
        QString haystack = record.displayName + QLatin1Char(' ')
            + record.modeId + QLatin1Char(' ')
            + record.mediaType + QLatin1Char(' ')
            + record.backend + QLatin1Char(' ')
            + record.sourceWorkflowFormat + QLatin1Char(' ')
            + record.compiledPromptFormat + QLatin1Char(' ')
            + record.tags.join(QLatin1Char(' '));
        haystack = haystack.toLower();

        if (!haystack.contains(search))
            return false;
    }

    const QString task = taskFilter_->currentData().toString();
    if (!task.isEmpty() && record.modeId.compare(task, Qt::CaseInsensitive) != 0)
        return false;

    const QString backend = backendFilter_->currentData().toString();
    if (!backend.isEmpty() && record.backend.compare(backend, Qt::CaseInsensitive) != 0)
        return false;

    const QString readiness = readinessFilter_->currentData().toString();
    if (!readiness.isEmpty() && readiness != readinessFilterKey(record.readiness))
        return false;

    return true;
}

void WorkflowLibraryPage::updateSummary()
{
    int ready = 0;
    int unsupported = 0;
    int needsCompilation = 0;
    int runtimeOffline = 0;
    int missingDependencies = 0;
    int missingWorkflow = 0;
    int needsReview = 0;

    for (const WorkflowRecord &record : workflows_)
    {
        switch (record.readiness)
        {
        case ReadinessState::Ready:
            ++ready;
            break;
        case ReadinessState::Unsupported:
            ++unsupported;
            break;
        case ReadinessState::NeedsCompilation:
            ++needsCompilation;
            break;
        case ReadinessState::RuntimeOffline:
            ++runtimeOffline;
            break;
        case ReadinessState::MissingDependencies:
            ++missingDependencies;
            break;
        case ReadinessState::MissingWorkflow:
            ++missingWorkflow;
            break;
        case ReadinessState::NeedsReview:
            ++needsReview;
            break;
        }
    }

    summaryLabel_->setText(
        tr("Review imported workflows, inspect dependency health, and only launch profiles that are truly ready.\n"
           "Workflows: %1   Ready: %2   Unsupported: %3   Needs Compilation: %4   Runtime Offline: %5   Missing Dependencies: %6   Missing Workflow: %7   Needs Review: %8")
            .arg(workflows_.size())
            .arg(ready)
            .arg(unsupported)
            .arg(needsCompilation)
            .arg(runtimeOffline)
            .arg(missingDependencies)
            .arg(missingWorkflow)
            .arg(needsReview));
}

void WorkflowLibraryPage::updateDetailsPanel()
{
    const QListWidgetItem *item = workflowList_->currentItem();
    if (!item)
    {
        clearDetailsPanel();
        return;
    }

    const int index = item->data(Qt::UserRole).toInt();
    if (index < 0 || index >= workflows_.size())
    {
        clearDetailsPanel();
        return;
    }

    const WorkflowRecord &record = workflows_.at(index);

    detailTitleLabel_->setText(record.displayName);
    detailMetaLabel_->setText(workflowSummaryText(record));
    QString statusText = record.readinessLabel + QStringLiteral(" — ") + record.readinessReason;
    if (record.reusableDraftPresent && !record.reusableDraftSafeToSubmit)
        statusText += QStringLiteral("\nDraft handoff: %1").arg(record.reusableDraftReason);
    detailStatusLabel_->setText(statusText);
    detailText_->setPlainText(workflowDetailsText(record));

    const bool canApplyDraft = record.reusableDraftPresent && isImageMode(record.modeId, record.mediaType);
    if (applyButton_)
    {
        applyButton_->setVisible(canApplyDraft);
        applyButton_->setEnabled(canApplyDraft);
        applyButton_->setText(record.modeId.compare(QStringLiteral("i2i"), Qt::CaseInsensitive) == 0 ? tr("Open in I2I") : tr("Open in T2I"));
        applyButton_->setToolTip(record.reusableDraftReason);
    }

    launchButton_->setEnabled(record.readiness == ReadinessState::Ready);
    revealFolderButton_->setEnabled(!record.importRoot.isEmpty());
    openWorkflowJsonButton_->setEnabled(record.workflowJsonPresent || record.compiledPromptPresent);
}

void WorkflowLibraryPage::clearDetailsPanel()
{
    detailTitleLabel_->setText(tr("No workflow selected"));
    detailMetaLabel_->clear();
    detailStatusLabel_->setText(tr("Select a workflow to inspect its capability and launch readiness."));
    detailText_->clear();

    if (applyButton_)
    {
        applyButton_->setVisible(false);
        applyButton_->setEnabled(false);
        applyButton_->setToolTip(QString());
    }
    launchButton_->setEnabled(false);
    revealFolderButton_->setEnabled(false);
    openWorkflowJsonButton_->setEnabled(false);
}

QString WorkflowLibraryPage::readinessFilterKey(ReadinessState state) const
{
    switch (state)
    {
    case ReadinessState::Ready:
        return QStringLiteral("ready");
    case ReadinessState::Unsupported:
        return QStringLiteral("unsupported");
    case ReadinessState::NeedsCompilation:
        return QStringLiteral("needs_compilation");
    case ReadinessState::RuntimeOffline:
        return QStringLiteral("runtime_offline");
    case ReadinessState::MissingDependencies:
        return QStringLiteral("missing_dependencies");
    case ReadinessState::MissingWorkflow:
        return QStringLiteral("missing_workflow");
    case ReadinessState::NeedsReview:
        return QStringLiteral("needs_review");
    }
    return QStringLiteral("unknown");
}

QString WorkflowLibraryPage::workflowListLine(const WorkflowRecord &record) const
{
    const QString formatLabel = record.compiledPromptPresent
        ? QStringLiteral("compiled")
        : record.sourceWorkflowFormat;
    return QStringLiteral("%1\n%2 • %3 • %4\nModels: %5   Missing Nodes: %6   Unresolved: %7")
        .arg(record.displayName)
        .arg(record.mediaType.isEmpty() ? QStringLiteral("unknown") : record.mediaType)
        .arg(record.readinessLabel)
        .arg(formatLabel)
        .arg(record.referencedModelCount)
        .arg(record.missingCustomNodes.size())
        .arg(record.unresolvedDependencyActions);
}

QString WorkflowLibraryPage::workflowSummaryText(const WorkflowRecord &record) const
{
    const QString assetState =
        !record.runtimeAssetValidationAttempted ? QStringLiteral("skipped")
        : (record.runtimeAssetValidationPassed ? QStringLiteral("yes") : QStringLiteral("missing"));

    return QStringLiteral("Task: %1\nBackend: %2\nMedia: %3\nSource Format: %4\nLaunch Artifact: %5\nValidated: %6\nAssets Ready: %7\nStatus: %8")
        .arg(record.modeId.toUpper())
        .arg(record.backend)
        .arg(record.mediaType)
        .arg(record.sourceWorkflowFormat)
        .arg(record.launchArtifactFormat.isEmpty() ? QStringLiteral("unknown") : record.launchArtifactFormat)
        .arg(record.launchArtifactValidated
                 ? (record.launchArtifactValid ? QStringLiteral("yes") : QStringLiteral("failed"))
                 : QStringLiteral("no"))
        .arg(assetState)
        .arg(record.readinessLabel);
}

QString WorkflowLibraryPage::workflowDetailsText(const WorkflowRecord &record) const
{
    QStringList lines;
    lines << tr("Mode: %1").arg(record.modeId.toUpper());
    lines << tr("Media: %1").arg(record.mediaType);
    lines << tr("Backend: %1").arg(record.backend);
    lines << tr("Source workflow format: %1").arg(record.sourceWorkflowFormat);
    lines << tr("Compiled prompt present: %1").arg(record.compiledPromptPresent ? tr("yes") : tr("no"));
    lines << tr("Compiled prompt format: %1").arg(record.compiledPromptFormat.isEmpty() ? QStringLiteral("unknown") : record.compiledPromptFormat);
    lines << tr("Launch artifact path: %1").arg(record.launchArtifactPath.isEmpty() ? tr("<missing>") : record.launchArtifactPath);
    lines << tr("Launch artifact format: %1").arg(record.launchArtifactFormat.isEmpty() ? QStringLiteral("unknown") : record.launchArtifactFormat);
    lines << tr("API prompt compatible: %1").arg(record.apiPromptCompatible ? tr("yes") : tr("no"));
    lines << tr("Launch artifact validated: %1").arg(record.launchArtifactValidated ? tr("yes") : tr("no"));
    lines << tr("Launch artifact valid: %1").arg(record.launchArtifactValid ? tr("yes") : tr("no"));
    lines << tr("Readiness: %1").arg(record.readinessLabel);
    lines << tr("Reason: %1").arg(record.readinessReason);
    lines << tr("Reusable draft present: %1").arg(record.reusableDraftPresent ? tr("yes") : tr("no"));
    if (record.reusableDraftPresent)
    {
        lines << tr("Reusable draft safe to submit: %1").arg(record.reusableDraftSafeToSubmit ? tr("yes") : tr("review first"));
        if (!record.reusableDraftReason.isEmpty())
            lines << tr("Reusable draft note: %1").arg(record.reusableDraftReason);
    }
    lines << QString();

    lines << tr("Runtime: %1").arg(record.runtimeProbe.ok ? tr("reachable") : tr("unavailable"));
    if (!record.runtimeProbe.message.isEmpty())
        lines << tr("Runtime detail: %1").arg(record.runtimeProbe.message);
    lines << tr("Runtime asset validation attempted: %1").arg(record.runtimeAssetValidationAttempted ? tr("yes") : tr("no"));
    if (record.runtimeAssetValidationAttempted)
    {
        lines << tr("Runtime asset validation passed: %1").arg(record.runtimeAssetValidationPassed ? tr("yes") : tr("no"));
        if (!record.runtimeAssetValidationMessage.isEmpty())
            lines << tr("Runtime asset detail: %1").arg(record.runtimeAssetValidationMessage);
    }
    lines << QString();

    lines << tr("Referenced models: %1").arg(record.referencedModelCount);
    lines << tr("Missing custom nodes: %1").arg(record.missingCustomNodes.size());
    if (!record.missingCustomNodes.isEmpty())
        lines << tr("Missing node classes: %1").arg(record.missingCustomNodes.join(QStringLiteral(", ")));
    lines << tr("Unresolved dependency actions: %1").arg(record.unresolvedDependencyActions);
    lines << tr("Warnings: %1").arg(record.warnings.size());
    if (!record.warnings.isEmpty())
    {
        lines << tr("Warning details:");
        for (const QString &warning : record.warnings)
            lines << QStringLiteral("• %1").arg(warning);
    }

    lines << tr("Compile warnings: %1").arg(record.compileWarnings.size());
    if (!record.compileWarnings.isEmpty())
    {
        lines << tr("Compile warning details:");
        for (const QString &warning : record.compileWarnings)
            lines << QStringLiteral("• %1").arg(warning);
    }

    if (!record.compileError.trimmed().isEmpty())
        lines << tr("Compile error: %1").arg(record.compileError);

    lines << tr("Validation errors: %1").arg(record.launchValidationErrors.size());
    if (!record.launchValidationErrors.isEmpty())
    {
        lines << tr("Validation error details:");
        for (const QString &error : record.launchValidationErrors)
            lines << QStringLiteral("• %1").arg(error);
    }

    lines << tr("Validation warnings: %1").arg(record.launchValidationWarnings.size());
    if (!record.launchValidationWarnings.isEmpty())
    {
        lines << tr("Validation warning details:");
        for (const QString &warning : record.launchValidationWarnings)
            lines << QStringLiteral("• %1").arg(warning);
    }

    lines << tr("Missing runtime assets: %1").arg(record.missingRuntimeAssets.size());
    if (!record.missingRuntimeAssets.isEmpty())
    {
        lines << tr("Missing runtime asset details:");
        for (const QString &asset : record.missingRuntimeAssets)
            lines << QStringLiteral("• %1").arg(asset);
    }

    lines << tr("Runtime asset warnings: %1").arg(record.runtimeAssetWarnings.size());
    if (!record.runtimeAssetWarnings.isEmpty())
    {
        lines << tr("Runtime asset warning details:");
        for (const QString &warning : record.runtimeAssetWarnings)
            lines << QStringLiteral("• %1").arg(warning);
    }

    lines << QString();
    lines << tr("Import Root: %1").arg(record.importRoot);
    lines << tr("Profile: %1").arg(record.profilePath);
    lines << tr("Source Workflow JSON: %1").arg(record.sourceWorkflowPath.isEmpty() ? tr("<missing>") : record.sourceWorkflowPath);
    lines << tr("Compiled Prompt JSON: %1").arg(record.compiledPromptPath.isEmpty() ? tr("<missing>") : record.compiledPromptPath);
    lines << tr("Scan Report: %1").arg(record.scanReportPath.isEmpty() ? tr("<missing>") : record.scanReportPath);

    return joinLines(lines);
}

QString WorkflowLibraryPage::assetCatalogKey(const QString &classType, const QString &inputName)
{
    return classType + QStringLiteral("|") + inputName;
}

QStringList WorkflowLibraryPage::assetInputNamesForClassType(const QString &classType)
{
    if (classType == QStringLiteral("CheckpointLoaderSimple") || classType == QStringLiteral("CheckpointLoader"))
        return {QStringLiteral("ckpt_name")};
    if (classType == QStringLiteral("LoraLoader"))
        return {QStringLiteral("lora_name")};
    if (classType == QStringLiteral("VAELoader"))
        return {QStringLiteral("vae_name")};
    if (classType == QStringLiteral("ControlNetLoader"))
        return {QStringLiteral("control_net_name")};
    if (classType == QStringLiteral("CLIPLoader"))
        return {QStringLiteral("clip_name")};
    return {};
}

QString WorkflowLibraryPage::normalizedModeId(const QString &value)
{
    QString normalized = value.trimmed().toLower();
    normalized.remove(QLatin1Char(' '));
    normalized.remove(QLatin1Char('_'));
    normalized.remove(QLatin1Char('-'));
    return normalized;
}

QString WorkflowLibraryPage::safeObjectString(const QJsonObject &object, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = object.value(key);
        if (value.isString())
        {
            const QString text = value.toString().trimmed();
            if (!text.isEmpty())
                return text;
        }
    }
    return {};
}

QStringList WorkflowLibraryPage::safeObjectStringList(const QJsonObject &object, const QStringList &keys)
{
    QStringList results;
    for (const QString &key : keys)
    {
        const QJsonValue value = object.value(key);
        if (!value.isArray())
            continue;

        const QJsonArray array = value.toArray();
        for (const QJsonValue &entry : array)
        {
            if (entry.isString())
            {
                const QString text = entry.toString().trimmed();
                if (!text.isEmpty())
                    results.push_back(text);
            }
        }

        if (!results.isEmpty())
            return results;
    }
    return results;
}

int WorkflowLibraryPage::safeObjectInt(const QJsonObject &object, const QStringList &keys, int fallback)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = object.value(key);
        if (value.isDouble())
            return value.toInt(fallback);
    }
    return fallback;
}

QString WorkflowLibraryPage::resolvePossiblyRelativePath(const QString &root, const QString &candidate)
{
    if (candidate.trimmed().isEmpty())
        return {};

    const QFileInfo info(candidate);
    if (info.isAbsolute())
        return QDir::cleanPath(candidate);

    return QDir(root).filePath(candidate);
}

bool WorkflowLibraryPage::isVideoMode(const QString &modeId, const QString &mediaType)
{
    const QString mode = modeId.trimmed().toLower();
    const QString media = mediaType.trimmed().toLower();

    return mode == QStringLiteral("t2v")
        || mode == QStringLiteral("i2v")
        || mode == QStringLiteral("v2v")
        || media == QStringLiteral("video");
}

bool WorkflowLibraryPage::isImageMode(const QString &modeId, const QString &mediaType)
{
    const QString mode = modeId.trimmed().toLower();
    const QString media = mediaType.trimmed().toLower();

    return mode == QStringLiteral("t2i")
        || mode == QStringLiteral("i2i")
        || media == QStringLiteral("image");
}

QString WorkflowLibraryPage::detectWorkflowFormat(const QJsonObject &object)
{
    if (object.isEmpty())
        return QStringLiteral("unknown");

    if (object.contains(QStringLiteral("prompt")) && object.value(QStringLiteral("prompt")).isObject())
    {
        const QString nested = detectWorkflowFormat(object.value(QStringLiteral("prompt")).toObject());
        if (nested == QStringLiteral("comfy_api_prompt"))
            return QStringLiteral("comfy_api_prompt");
    }

    if (object.contains(QStringLiteral("nodes")) && object.value(QStringLiteral("nodes")).isArray())
        return QStringLiteral("comfy_ui_graph");

    bool foundNodeObject = false;
    for (auto it = object.constBegin(); it != object.constEnd(); ++it)
    {
        if (!it.value().isObject())
            return QStringLiteral("unknown");

        const QJsonObject nodeObj = it.value().toObject();
        if (!nodeObj.contains(QStringLiteral("class_type")) || !nodeObj.contains(QStringLiteral("inputs")))
            return QStringLiteral("unknown");
        foundNodeObject = true;
    }

    if (foundNodeObject)
        return QStringLiteral("comfy_api_prompt");

    return QStringLiteral("unknown");
}

bool WorkflowLibraryPage::validateApiPromptObject(
    const QJsonObject &prompt,
    QStringList *errors,
    QStringList *warnings)
{
    if (errors)
        errors->clear();
    if (warnings)
        warnings->clear();

    if (prompt.isEmpty())
    {
        if (errors)
            errors->push_back(QObject::tr("Prompt artifact is empty."));
        return false;
    }

    QSet<QString> nodeIds;
    for (auto it = prompt.constBegin(); it != prompt.constEnd(); ++it)
        nodeIds.insert(it.key());

    bool foundOutputLikeNode = false;

    for (auto it = prompt.constBegin(); it != prompt.constEnd(); ++it)
    {
        const QString nodeId = it.key();
        if (!it.value().isObject())
        {
            if (errors)
                errors->push_back(QObject::tr("Node %1 is not an object.").arg(nodeId));
            continue;
        }

        const QJsonObject nodeObj = it.value().toObject();
        const QString classType = nodeObj.value(QStringLiteral("class_type")).toString().trimmed();
        if (classType.isEmpty())
        {
            if (errors)
                errors->push_back(QObject::tr("Node %1 is missing class_type.").arg(nodeId));
        }

        const QJsonValue inputsValue = nodeObj.value(QStringLiteral("inputs"));
        if (!inputsValue.isObject())
        {
            if (errors)
                errors->push_back(QObject::tr("Node %1 is missing an inputs object.").arg(nodeId));
            continue;
        }

        const QString classTypeLower = classType.toLower();
        if (classTypeLower.startsWith(QStringLiteral("save"))
            || classTypeLower.contains(QStringLiteral("preview"))
            || classTypeLower.contains(QStringLiteral("output")))
        {
            foundOutputLikeNode = true;
        }

        const QJsonObject inputs = inputsValue.toObject();
        for (auto inputIt = inputs.constBegin(); inputIt != inputs.constEnd(); ++inputIt)
        {
            const QJsonValue inputValue = inputIt.value();
            if (!inputValue.isArray())
                continue;

            const QJsonArray ref = inputValue.toArray();
            if (ref.size() < 2 || !ref.at(1).isDouble())
                continue;

            QString refNodeId;
            if (ref.at(0).isString())
            {
                refNodeId = ref.at(0).toString().trimmed();
            }
            else if (ref.at(0).isDouble())
            {
                if (errors)
                {
                    errors->push_back(
                        QObject::tr("Node %1 input '%2' uses numeric node reference %3; ComfyUI prompt refs must use string node IDs.")
                            .arg(nodeId, inputIt.key())
                            .arg(ref.at(0).toInt()));
                }
                continue;
            }

            if (refNodeId.isEmpty())
            {
                if (warnings)
                {
                    warnings->push_back(
                        QObject::tr("Node %1 input '%2' has an empty node reference.")
                            .arg(nodeId, inputIt.key()));
                }
                continue;
            }

            if (!nodeIds.contains(refNodeId))
            {
                if (errors)
                {
                    errors->push_back(
                        QObject::tr("Node %1 input '%2' references missing node %3.")
                            .arg(nodeId, inputIt.key(), refNodeId));
                }
            }

            if (ref.at(1).toInt() < 0 && warnings)
            {
                warnings->push_back(
                    QObject::tr("Node %1 input '%2' references negative output slot %3.")
                        .arg(nodeId, inputIt.key())
                        .arg(ref.at(1).toInt()));
            }
        }
    }

    if (!foundOutputLikeNode && warnings)
    {
        warnings->push_back(QObject::tr("No obvious save/output node was detected in the launch artifact."));
    }

    return !errors || errors->isEmpty();
}

QJsonObject WorkflowLibraryPage::compileUiGraphToApiPrompt(
    const QJsonObject &graph,
    QStringList *warnings,
    QString *errorText)
{
    if (warnings)
        warnings->clear();
    if (errorText)
        errorText->clear();

    const QJsonValue nodesValue = graph.value(QStringLiteral("nodes"));
    if (!nodesValue.isArray())
    {
        if (errorText)
            *errorText = QStringLiteral("UI graph payload does not contain a nodes array.");
        return {};
    }

    QHash<QString, LinkEdge> linksById;
    const QJsonValue linksValue = graph.value(QStringLiteral("links"));
    if (linksValue.isArray())
    {
        const QJsonArray links = linksValue.toArray();
        for (const QJsonValue &value : links)
        {
            if (value.isArray())
            {
                const QJsonArray link = value.toArray();
                if (link.size() >= 5)
                {
                    LinkEdge edge;
                    edge.sourceNodeId = QString::number(link.at(1).toInt());
                    edge.sourceSlot = link.at(2).toInt();
                    linksById.insert(QString::number(link.at(0).toInt()), edge);
                }
            }
            else if (value.isObject())
            {
                const QJsonObject link = value.toObject();
                LinkEdge edge;
                edge.sourceNodeId = QString::number(link.value(QStringLiteral("origin_id")).toInt(link.value(QStringLiteral("from_node")).toInt()));
                edge.sourceSlot = link.value(QStringLiteral("origin_slot")).toInt(link.value(QStringLiteral("from_slot")).toInt());
                const QString linkId = QString::number(link.value(QStringLiteral("id")).toInt());
                if (!linkId.isEmpty())
                    linksById.insert(linkId, edge);
            }
        }
    }

    QJsonObject prompt;
    const QJsonArray nodes = nodesValue.toArray();
    for (const QJsonValue &nodeValue : nodes)
    {
        if (!nodeValue.isObject())
            continue;

        const QJsonObject node = nodeValue.toObject();
        const QString nodeId = QString::number(node.value(QStringLiteral("id")).toInt(node.value(QStringLiteral("index")).toInt(-1)));
        const QString classType = node.value(QStringLiteral("type")).toString(node.value(QStringLiteral("class_type")).toString()).trimmed();
        if (nodeId.isEmpty() || classType.isEmpty())
        {
            if (warnings)
                warnings->push_back(QStringLiteral("Skipped a node with missing id or class type."));
            continue;
        }

        QJsonObject inputs;
        QSet<QString> assignedNames;
        const QJsonArray inputDefs = node.value(QStringLiteral("inputs")).toArray();
        const QJsonArray widgetValues = node.value(QStringLiteral("widgets_values")).toArray();
        const QStringList schema = widgetSchemaForClassType(classType);

        int widgetCursor = 0;
        int schemaCursor = 0;
        const bool specialMapped = mapSpecialWidgetInputs(classType, nodeId, widgetValues, &inputs, &assignedNames, warnings);

        for (const QJsonValue &inputValue : inputDefs)
        {
            if (!inputValue.isObject())
                continue;

            const QJsonObject inputObj = inputValue.toObject();
            const QString inputName = inputObj.value(QStringLiteral("name")).toString().trimmed();
            if (inputName.isEmpty())
                continue;

            if (valueIsLinkedInput(inputObj))
            {
                const QString linkId = linkIdFromInput(inputObj);
                const LinkEdge edge = linksById.value(linkId);
                if (!edge.sourceNodeId.isEmpty())
                {
                    inputs.insert(inputName, buildNodeRef(edge.sourceNodeId, edge.sourceSlot));
                    assignedNames.insert(inputName);
                }
                else if (warnings)
                {
                    warnings->push_back(QStringLiteral("Node %1 input '%2' references missing link %3.")
                                            .arg(nodeId, inputName, linkId));
                }
                continue;
            }

            if (specialMapped)
                continue;

            if (inputOwnsWidget(inputObj) && widgetCursor < widgetValues.size())
            {
                inputs.insert(inputName, widgetValues.at(widgetCursor));
                assignedNames.insert(inputName);
                ++widgetCursor;
            }
        }

        if (!specialMapped)
        {
            while (widgetCursor < widgetValues.size())
            {
                const QString targetName = nextSchemaName(schema, &schemaCursor, assignedNames);
                if (targetName.isEmpty())
                    break;

                inputs.insert(targetName, widgetValues.at(widgetCursor));
                assignedNames.insert(targetName);
                ++widgetCursor;
            }

            if (widgetCursor < widgetValues.size() && warnings)
            {
                warnings->push_back(QStringLiteral("Node %1 (%2) has %3 unmapped widget values.")
                                        .arg(nodeId, classType)
                                        .arg(widgetValues.size() - widgetCursor));
            }
        }

        QJsonObject promptNode;
        promptNode.insert(QStringLiteral("class_type"), classType);
        promptNode.insert(QStringLiteral("inputs"), inputs);

        const QString title = node.value(QStringLiteral("title")).toString().trimmed();
        if (!title.isEmpty())
        {
            QJsonObject meta;
            meta.insert(QStringLiteral("title"), title);
            promptNode.insert(QStringLiteral("_meta"), meta);
        }

        prompt.insert(nodeId, promptNode);
    }

    if (prompt.isEmpty() && errorText)
        *errorText = QStringLiteral("The workflow graph could not be converted into an API prompt.");

    return prompt;
}


WorkflowLibraryPage::RuntimeAssetCatalogResult WorkflowLibraryPage::fetchComfyAssetCatalog() const
{
    RuntimeAssetCatalogResult result;
    result.ok = false;

    if (pythonExecutable_.trimmed().isEmpty())
    {
        result.message = tr("Python executable is not configured, so Comfy object_info could not be queried.");
        return result;
    }

    QProcess process;
    process.setProgram(pythonExecutable_);

    const QString script =
        "import json, sys, urllib.request\n"
        "base = sys.argv[1].rstrip('/')\n"
        "timeout = float(sys.argv[2])\n"
        "url = base + '/object_info'\n"
        "try:\n"
        "    with urllib.request.urlopen(url, timeout=timeout) as resp:\n"
        "        payload = json.loads(resp.read().decode('utf-8'))\n"
        "    print(json.dumps(payload))\n"
        "except Exception as e:\n"
        "    print(type(e).__name__ + ': ' + str(e))\n"
        "    sys.exit(1)\n";

    process.setArguments(QStringList()
                         << QStringLiteral("-c")
                         << script
                         << comfyEndpoint_
                         << QStringLiteral("2.0"));

    process.start();
    if (!process.waitForFinished(4000))
    {
        process.kill();
        process.waitForFinished(500);
        result.message = tr("Comfy object_info probe timed out while checking %1/object_info.").arg(comfyEndpoint_);
        return result;
    }

    const QString stdOut = QString::fromUtf8(process.readAllStandardOutput()).trimmed();
    const QString stdErr = QString::fromUtf8(process.readAllStandardError()).trimmed();

    if (!(process.exitStatus() == QProcess::NormalExit && process.exitCode() == 0))
    {
        const QString detail = !stdOut.isEmpty() ? stdOut : stdErr;
        result.message = tr("Comfy object_info could not be read from %1/object_info. %2")
                             .arg(comfyEndpoint_, detail.isEmpty() ? tr("Start or connect the runtime before launch.") : detail);
        return result;
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(stdOut.toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject())
    {
        result.message = tr("Comfy object_info returned invalid JSON: %1")
                             .arg(parseError.errorString().isEmpty() ? tr("not an object") : parseError.errorString());
        return result;
    }

    const QJsonObject root = document.object();
    const QList<QPair<QString, QString>> assetInputs = {
        {QStringLiteral("CheckpointLoaderSimple"), QStringLiteral("ckpt_name")},
        {QStringLiteral("CheckpointLoader"), QStringLiteral("ckpt_name")},
        {QStringLiteral("LoraLoader"), QStringLiteral("lora_name")},
        {QStringLiteral("VAELoader"), QStringLiteral("vae_name")},
        {QStringLiteral("ControlNetLoader"), QStringLiteral("control_net_name")},
        {QStringLiteral("CLIPLoader"), QStringLiteral("clip_name")}
    };

    for (const auto &entry : assetInputs)
    {
        const QString classType = entry.first;
        const QString inputName = entry.second;
        const QString key = assetCatalogKey(classType, inputName);

        const QJsonObject classObj = root.value(classType).toObject();
        const QJsonObject inputObj = classObj.value(QStringLiteral("input")).toObject();
        const QJsonObject requiredObj = inputObj.value(QStringLiteral("required")).toObject();
        const QJsonValue inputValue = requiredObj.value(inputName);

        if (!inputValue.isArray())
            continue;

        const QJsonArray descriptor = inputValue.toArray();
        if (descriptor.isEmpty() || !descriptor.at(0).isArray())
            continue;

        result.cataloguedKeys.insert(key);

        const QJsonArray allowed = descriptor.at(0).toArray();
        QSet<QString> values;
        for (const QJsonValue &value : allowed)
        {
            if (value.isString())
                values.insert(value.toString().trimmed());
        }
        result.allowedValuesByKey.insert(key, values);
    }

    result.ok = true;
    result.message = tr("Comfy runtime asset catalog loaded from %1/object_info.").arg(comfyEndpoint_);
    return result;
}

WorkflowLibraryPage::RuntimeProbeResult WorkflowLibraryPage::probeComfyRuntime() const
{
    RuntimeProbeResult result;
    result.ok = false;

    if (pythonExecutable_.trimmed().isEmpty())
    {
        result.message = tr("Python executable is not configured, so the Comfy runtime could not be probed.");
        return result;
    }

    QProcess process;
    process.setProgram(pythonExecutable_);

    const QString script =
        "import sys, urllib.request\n"
        "url = sys.argv[1]\n"
        "timeout = float(sys.argv[2])\n"
        "try:\n"
        "    urllib.request.urlopen(url, timeout=timeout)\n"
        "    print('OK')\n"
        "except Exception as e:\n"
        "    print(type(e).__name__ + ': ' + str(e))\n"
        "    sys.exit(1)\n";

    process.setArguments(QStringList()
                         << QStringLiteral("-c")
                         << script
                         << comfyEndpoint_
                         << QStringLiteral("1.5"));

    process.start();
    if (!process.waitForFinished(3000))
    {
        process.kill();
        process.waitForFinished(500);
        result.message = tr("Runtime probe timed out while checking %1.").arg(comfyEndpoint_);
        return result;
    }

    const QString stdOut = QString::fromUtf8(process.readAllStandardOutput()).trimmed();
    const QString stdErr = QString::fromUtf8(process.readAllStandardError()).trimmed();

    if (process.exitStatus() == QProcess::NormalExit && process.exitCode() == 0)
    {
        result.ok = true;
        result.message = tr("Comfy runtime responded at %1.").arg(comfyEndpoint_);
        return result;
    }

    const QString detail = !stdOut.isEmpty() ? stdOut : stdErr;
    result.message = tr("SpellVision could not reach ComfyUI at %1. %2")
                         .arg(comfyEndpoint_, detail.isEmpty() ? tr("Start or connect the runtime before launch.") : detail);
    return result;
}
