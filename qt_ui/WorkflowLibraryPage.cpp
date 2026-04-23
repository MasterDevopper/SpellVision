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
#include <QMessageBox>
#include <QPlainTextEdit>
#include <QProcess>
#include <QtConcurrent>
#include <QPushButton>
#include <QSaveFile>
#include <QStandardPaths>
#include <QSet>
#include <QSplitter>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>

#include <utility>

namespace
{
QString joinLines(const QStringList &lines)
{
    return lines.join(QLatin1Char('\n'));
}

QJsonObject parseLastJsonObjectFromStdout(const QString &allStdout, QString *errorText = nullptr)
{
    QString lastJsonLine;
    const QStringList lines = allStdout.split('\n', Qt::SkipEmptyParts);

    for (auto it = lines.crbegin(); it != lines.crend(); ++it)
    {
        const QString candidate = it->trimmed();
        if (candidate.startsWith(QLatin1Char('{')) && candidate.endsWith(QLatin1Char('}')))
        {
            lastJsonLine = candidate;
            break;
        }
    }

    if (lastJsonLine.isEmpty())
    {
        if (errorText)
            *errorText = QStringLiteral("Worker returned no JSON payload.");
        return {};
    }

    QJsonParseError parseError{};
    const QJsonDocument doc = QJsonDocument::fromJson(lastJsonLine.toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
    {
        if (errorText)
            *errorText = QStringLiteral("Worker returned invalid JSON: %1").arg(lastJsonLine);
        return {};
    }

    return doc.object();
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

QString boolText(bool value)
{
    return value ? QStringLiteral("yes") : QStringLiteral("no");
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

QString stringFromJsonValue(const QJsonValue &value)
{
    if (value.isString())
        return value.toString().trimmed();

    if (value.isDouble())
        return QString::number(value.toDouble(), 'f', 2);

    if (value.isBool())
        return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");

    if (value.isObject())
    {
        const QJsonObject object = value.toObject();
        const QStringList preferredKeys = {
            QStringLiteral("label"),
            QStringLiteral("message"),
            QStringLiteral("name"),
            QStringLiteral("value"),
            QStringLiteral("mode"),
            QStringLiteral("kind"),
            QStringLiteral("slot"),
            QStringLiteral("code")
        };

        for (const QString &key : preferredKeys)
        {
            const QJsonValue nested = object.value(key);
            if (!nested.isString())
                continue;

            const QString text = nested.toString().trimmed();
            if (!text.isEmpty())
                return text;
        }
    }

    return {};
}

QStringList stringListFromJsonValue(const QJsonValue &value)
{
    QStringList out;

    auto appendUnique = [&out](const QString &text)
    {
        const QString trimmed = text.trimmed();
        if (!trimmed.isEmpty() && !out.contains(trimmed, Qt::CaseInsensitive))
            out.push_back(trimmed);
    };

    if (value.isArray())
    {
        const QJsonArray array = value.toArray();
        for (const QJsonValue &entry : array)
            appendUnique(stringFromJsonValue(entry));
    }
    else
    {
        appendUnique(stringFromJsonValue(value));
    }

    return out;
}

QJsonObject capabilityObjectFromProfile(const QJsonObject &object)
{
    const QStringList topLevelKeys = {
        QStringLiteral("capability_report"),
        QStringLiteral("capability"),
        QStringLiteral("workflow_capability"),
        QStringLiteral("classification"),
        QStringLiteral("classification_report")
    };

    for (const QString &key : topLevelKeys)
    {
        const QJsonValue value = object.value(key);
        if (value.isObject())
            return value.toObject();
    }

    const QJsonObject metadata = object.value(QStringLiteral("metadata")).toObject();
    for (const QString &key : topLevelKeys)
    {
        const QJsonValue value = metadata.value(key);
        if (value.isObject())
            return value.toObject();
    }

    if (object.contains(QStringLiteral("primary_task"))
        || object.contains(QStringLiteral("supported_modes"))
        || object.contains(QStringLiteral("required_inputs"))
        || object.contains(QStringLiteral("output_kinds")))
    {
        return object;
    }

    return {};
}

}

WorkflowLibraryPage::WorkflowLibraryPage(QWidget *parent)
    : QWidget(parent)
{
    buildUi();
    applyTheme();

    libraryRefreshWatcher_ = new QFutureWatcher<LibraryRefreshResult>(this);
    connect(libraryRefreshWatcher_, &QFutureWatcher<LibraryRefreshResult>::finished, this, &WorkflowLibraryPage::onLibraryRefreshFinished);
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
    warmCache();
}

void WorkflowLibraryPage::warmCache()
{
    if (loadLibraryCache())
    {
        rebuildFilters();
        rebuildList();
        updateSummary();
        updateDetailsPanel();
    }
    else if (summaryLabel_)
    {
        summaryLabel_->setText(tr("No cached workflow library yet. Refreshing imported workflows in background..."));
    }

    if (!libraryRefreshBusy_)
        refreshLibrary();
}

void WorkflowLibraryPage::setLibraryRefreshBusy(bool busy, const QString &statusText)
{
    libraryRefreshBusy_ = busy;

    if (refreshButton_)
    {
        refreshButton_->setEnabled(!busy && !workflowLifecycleBusy_);
        refreshButton_->setText(busy ? tr("Refreshing...") : tr("Refresh Library"));
    }

    if (importButton_)
        importButton_->setEnabled(!busy && !workflowLifecycleBusy_);
    if (workflowList_)
        workflowList_->setEnabled(!busy && !workflowLifecycleBusy_);

    if (detailStatusLabel_ && busy && !statusText.trimmed().isEmpty())
        detailStatusLabel_->setText(statusText);
    else if (!busy)
        updateDetailsPanel();
}

WorkflowLibraryPage::LibraryRefreshResult WorkflowLibraryPage::buildLibraryRefreshResult() const
{
    LibraryRefreshResult result;
    result.checkedAtMs = QDateTime::currentMSecsSinceEpoch();

    if (importedWorkflowsRoot_.isEmpty())
        return result;

    const QDir rootDir(importedWorkflowsRoot_);
    if (!rootDir.exists())
        return result;

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
        result.workflows.push_back(record);
    }

    return result;
}

void WorkflowLibraryPage::applyLibraryRefreshResult(const WorkflowLibraryPage::LibraryRefreshResult &result, const QString &sourceLabel)
{
    workflows_ = result.workflows;
    libraryCacheLoaded_ = !workflows_.isEmpty();
    libraryCacheSource_ = sourceLabel;
    libraryCacheAtMs_ = result.checkedAtMs;
    if (libraryCacheLoaded_)
        persistLibraryCache();

    rebuildFilters();
    rebuildList();
    updateSummary();
    updateDetailsPanel();
}

void WorkflowLibraryPage::refreshLibrary()
{
    if (workflowLifecycleBusy_ || libraryRefreshBusy_)
        return;

    if (!libraryRefreshWatcher_)
        return;

    setLibraryRefreshBusy(true, tr("Refreshing workflow library in background..."));
    libraryRefreshWatcher_->setFuture(QtConcurrent::run([this]() {
        return buildLibraryRefreshResult();
    }));
}

void WorkflowLibraryPage::onLibraryRefreshFinished()
{
    if (!libraryRefreshWatcher_)
        return;

    const LibraryRefreshResult result = libraryRefreshWatcher_->result();
    applyLibraryRefreshResult(result, QStringLiteral("live"));
    setLibraryRefreshBusy(false);
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


int WorkflowLibraryPage::currentWorkflowIndex() const
{
    const QListWidgetItem *item = workflowList_ ? workflowList_->currentItem() : nullptr;
    if (!item)
        return -1;

    const int index = item->data(Qt::UserRole).toInt();
    if (index < 0 || index >= workflows_.size())
        return -1;

    return index;
}

QJsonObject WorkflowLibraryPage::sendWorkerCommand(const QJsonObject &request, int timeoutMs, QString *stderrText) const
{
    if (stderrText)
        stderrText->clear();

    if (projectRoot_.trimmed().isEmpty())
    {
        return QJsonObject{
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), QStringLiteral("Project root is not configured.")}
        };
    }

    if (pythonExecutable_.trimmed().isEmpty())
    {
        return QJsonObject{
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), QStringLiteral("Python executable is not configured.")}
        };
    }

    const QString workerClient = QDir(projectRoot_).filePath(QStringLiteral("python/worker_client.py"));
    if (!QFileInfo::exists(workerClient))
    {
        return QJsonObject{
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), QStringLiteral("worker_client.py was not found at %1.").arg(workerClient)}
        };
    }

    QProcess process;
    process.setProgram(pythonExecutable_);
    process.setArguments({workerClient});
    process.setWorkingDirectory(projectRoot_);

    process.start();
    if (!process.waitForStarted(10000))
    {
        return QJsonObject{
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), QStringLiteral("Failed to start worker_client.py.")}
        };
    }

    process.write(QJsonDocument(request).toJson(QJsonDocument::Compact));
    process.write("\n");
    process.closeWriteChannel();

    if (!process.waitForFinished(timeoutMs))
    {
        process.kill();
        process.waitForFinished(1000);
        return QJsonObject{
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), QStringLiteral("Worker command timed out.")}
        };
    }

    const QString allStdout = QString::fromUtf8(process.readAllStandardOutput()).trimmed();
    const QString allStderr = QString::fromUtf8(process.readAllStandardError()).trimmed();
    if (stderrText)
        *stderrText = allStderr;

    QString parseErrorText;
    QJsonObject response = parseLastJsonObjectFromStdout(allStdout, &parseErrorText);
    if (response.isEmpty())
    {
        return QJsonObject{
            {QStringLiteral("ok"), false},
            {QStringLiteral("error"), parseErrorText.isEmpty() ? QStringLiteral("Worker returned no usable JSON payload.") : parseErrorText},
            {QStringLiteral("stderr"), allStderr}
        };
    }

    if (!(process.exitStatus() == QProcess::NormalExit && process.exitCode() == 0)
        && response.value(QStringLiteral("ok")).toBool(false))
    {
        response.insert(QStringLiteral("ok"), false);
        if (!response.contains(QStringLiteral("error")))
            response.insert(QStringLiteral("error"), allStderr.isEmpty() ? QStringLiteral("worker_client.py exited with code %1.").arg(process.exitCode()) : allStderr);
    }

    return response;
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

void WorkflowLibraryPage::onCheckReadinessClicked()
{
    const int index = currentWorkflowIndex();
    if (index < 0)
        return;

    if (workflowLifecycleProcess_)
    {
        QMessageBox::information(
            this,
            tr("Workflow Readiness"),
            tr("A workflow lifecycle operation is already running. Wait for it to finish before starting another."));
        return;
    }

    const WorkflowRecord record = workflows_.at(index);
    if (record.profilePath.trimmed().isEmpty() && record.launchArtifactPath.trimmed().isEmpty())
        return;

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("check_workflow_launch_readiness"));
    request.insert(QStringLiteral("profile_path"), record.profilePath);
    request.insert(QStringLiteral("import_root"), record.importRoot);
    request.insert(QStringLiteral("workflow_path"), record.sourceWorkflowPath);
    request.insert(QStringLiteral("compiled_prompt_path"), record.launchArtifactPath.isEmpty() ? record.compiledPromptPath : record.launchArtifactPath);
    request.insert(QStringLiteral("workflow_task_command"), record.modeId);
    request.insert(QStringLiteral("workflow_media_type"), record.mediaType);
    request.insert(QStringLiteral("ensure_runtime"), true);

    startWorkflowLifecycleCommand(
        request,
        tr("Checking launch readiness for %1...").arg(record.displayName),
        tr("Workflow launch readiness check timed out."),
        3 * 60 * 1000,
        [this, displayName = record.displayName](const QJsonObject &response, const QString &stderrText) {
            const bool ok = response.value(QStringLiteral("ok")).toBool(false);
            const QString errorText = response.value(QStringLiteral("error")).toString().trimmed();
            const QString summary = response.value(QStringLiteral("summary")).toString().trimmed();

            refreshLibrary();

            if (!ok)
            {
                QMessageBox::warning(
                    this,
                    tr("Workflow Launch Readiness"),
                    tr("Launch readiness check found blockers for %1.\n\n%2%3")
                        .arg(displayName,
                             summary.isEmpty() ? (errorText.isEmpty() ? tr("Review the workflow details panel for missing nodes/assets.") : errorText) : summary,
                             stderrText.trimmed().isEmpty() ? QString() : tr("\n\nWorker stderr:\n%1").arg(stderrText.trimmed())));
                return;
            }

            QMessageBox::information(
                this,
                tr("Workflow Launch Readiness"),
                tr("Launch readiness check passed for %1.\n\n%2")
                    .arg(displayName, summary.isEmpty() ? tr("The compiled prompt, runtime, node classes, and loader assets look ready.") : summary));
        });
}

void WorkflowLibraryPage::onRetryDependenciesClicked()
{
    const int index = currentWorkflowIndex();
    if (index < 0)
        return;

    if (workflowLifecycleProcess_)
    {
        QMessageBox::information(
            this,
            tr("Workflow Dependencies"),
            tr("A workflow lifecycle operation is already running. Wait for it to finish before starting another."));
        return;
    }

    const WorkflowRecord record = workflows_.at(index);
    const QString profilePath = record.profilePath.trimmed();
    const QString importRoot = record.importRoot.trimmed();

    if (profilePath.isEmpty() && importRoot.isEmpty())
        return;

    const QMessageBox::StandardButton answer = QMessageBox::question(
        this,
        tr("Rescan / Retry Workflow Dependencies"),
        tr("Rescan this workflow and retry dependency resolution/download?\n\n%1\n\n"
           "SpellVision will rebuild the scan report, refresh the workflow profile/capability classifier data, "
           "rebuild the dependency plan, reinstall missing custom nodes where it has a catalog match, "
           "and retry model materialization for resolvable model references.")
            .arg(record.displayName),
        QMessageBox::Yes | QMessageBox::No,
        QMessageBox::No);

    if (answer != QMessageBox::Yes)
        return;

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("retry_workflow_dependencies"));
    request.insert(QStringLiteral("profile_path"), profilePath);
    request.insert(QStringLiteral("import_root"), importRoot);
    request.insert(QStringLiteral("workflow_path"), record.sourceWorkflowPath);
    request.insert(QStringLiteral("auto_apply_node_deps"), true);
    request.insert(QStringLiteral("auto_apply_model_deps"), true);

    startWorkflowLifecycleCommand(
        request,
        tr("Rescanning and retrying dependencies for %1...").arg(record.displayName),
        tr("Workflow rescan/dependency retry timed out."),
        30 * 60 * 1000,
        [this, displayName = record.displayName](const QJsonObject &response, const QString &stderrText) {
            const bool ok = response.value(QStringLiteral("ok")).toBool(false);
            const QString errorText = response.value(QStringLiteral("error")).toString().trimmed();

            refreshLibrary();

            if (!ok)
            {
                QMessageBox::warning(
                    this,
                    tr("Rescan / Retry Workflow Dependencies"),
                    tr("Workflow rescan/dependency retry failed.\n\n%1%2")
                        .arg(errorText.isEmpty() ? tr("No error detail returned.") : errorText,
                             stderrText.trimmed().isEmpty() ? QString() : tr("\n\nWorker stderr:\n%1").arg(stderrText.trimmed())));
                return;
            }

            QMessageBox::information(
                this,
                tr("Rescan / Retry Workflow Dependencies"),
                tr("Workflow rescan/dependency retry finished for %1. Review the refreshed capability and readiness state before launch.")
                    .arg(displayName));
        });
}

void WorkflowLibraryPage::onDeleteWorkflowClicked()
{
    const int index = currentWorkflowIndex();
    if (index < 0)
        return;

    if (workflowLifecycleProcess_)
    {
        QMessageBox::information(
            this,
            tr("Delete Workflow"),
            tr("A workflow lifecycle operation is already running. Wait for it to finish before starting another."));
        return;
    }

    const WorkflowRecord record = workflows_.at(index);
    if (record.importRoot.trimmed().isEmpty())
        return;

    const QMessageBox::StandardButton answer = QMessageBox::warning(
        this,
        tr("Delete Workflow"),
        tr("Delete this imported workflow from SpellVision?\n\n%1\n\nFolder:\n%2\n\n"
           "This removes the imported profile, scan report, dependency plans, compiled prompt, and copied workflow JSON. "
           "It does not delete your original source workflow outside the imported-workflows library.")
            .arg(record.displayName, QDir::toNativeSeparators(record.importRoot)),
        QMessageBox::Yes | QMessageBox::No,
        QMessageBox::No);

    if (answer != QMessageBox::Yes)
        return;

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("delete_workflow_profile"));
    request.insert(QStringLiteral("profile_path"), record.profilePath);
    request.insert(QStringLiteral("import_root"), record.importRoot);

    startWorkflowLifecycleCommand(
        request,
        tr("Deleting workflow %1...").arg(record.displayName),
        tr("Workflow deletion timed out."),
        5 * 60 * 1000,
        [this, displayName = record.displayName](const QJsonObject &response, const QString &stderrText) {
            const bool ok = response.value(QStringLiteral("ok")).toBool(false);
            const QString errorText = response.value(QStringLiteral("error")).toString().trimmed();

            refreshLibrary();

            if (!ok)
            {
                QMessageBox::warning(
                    this,
                    tr("Delete Workflow"),
                    tr("Workflow deletion failed.\n\n%1%2")
                        .arg(errorText.isEmpty() ? tr("No error detail returned.") : errorText,
                             stderrText.trimmed().isEmpty() ? QString() : tr("\n\nWorker stderr:\n%1").arg(stderrText.trimmed())));
                return;
            }

            QMessageBox::information(
                this,
                tr("Delete Workflow"),
                tr("Deleted imported workflow: %1").arg(displayName));
        });
}

void WorkflowLibraryPage::setWorkflowLifecycleBusy(bool busy, const QString &statusText)
{
    workflowLifecycleBusy_ = busy;

    if (importButton_)
        importButton_->setEnabled(!busy && !libraryRefreshBusy_);
    if (refreshButton_)
        refreshButton_->setEnabled(!busy && !libraryRefreshBusy_);
    if (workflowList_)
        workflowList_->setEnabled(!busy && !libraryRefreshBusy_);

    if (launchButton_)
        launchButton_->setEnabled(!busy && launchButton_->isVisible());
    if (applyButton_)
        applyButton_->setEnabled(!busy && applyButton_->isVisible());
    if (revealFolderButton_)
        revealFolderButton_->setEnabled(!busy && revealFolderButton_->isVisible());
    if (openWorkflowJsonButton_)
        openWorkflowJsonButton_->setEnabled(!busy && openWorkflowJsonButton_->isVisible());

    if (checkReadinessButton_)
    {
        checkReadinessButton_->setEnabled(!busy && checkReadinessButton_->isVisible());
        checkReadinessButton_->setText(busy ? tr("Working...") : tr("Check Readiness"));
    }

    if (retryDependenciesButton_)
    {
        retryDependenciesButton_->setEnabled(!busy && retryDependenciesButton_->isVisible());
        retryDependenciesButton_->setText(busy ? tr("Working...") : tr("Rescan / Retry Deps"));
    }

    if (deleteWorkflowButton_)
    {
        deleteWorkflowButton_->setEnabled(!busy && deleteWorkflowButton_->isVisible());
        deleteWorkflowButton_->setText(busy ? tr("Working...") : tr("Delete Workflow"));
    }

    if (detailStatusLabel_ && busy && !statusText.trimmed().isEmpty())
        detailStatusLabel_->setText(statusText);
    else if (!busy)
        updateDetailsPanel();
}

void WorkflowLibraryPage::startWorkflowLifecycleCommand(const QJsonObject &request,
                                                        const QString &busyText,
                                                        const QString &timeoutText,
                                                        int timeoutMs,
                                                        WorkerCommandFinishedHandler finishedHandler)
{
    if (workflowLifecycleProcess_)
        return;

    if (projectRoot_.trimmed().isEmpty())
    {
        QMessageBox::warning(this, tr("Workflow Library"), tr("Project root is not configured."));
        return;
    }

    if (pythonExecutable_.trimmed().isEmpty())
    {
        QMessageBox::warning(this, tr("Workflow Library"), tr("Python executable is not configured."));
        return;
    }

    const QString workerClient = QDir(projectRoot_).filePath(QStringLiteral("python/worker_client.py"));
    if (!QFileInfo::exists(workerClient))
    {
        QMessageBox::warning(
            this,
            tr("Workflow Library"),
            tr("worker_client.py was not found at %1.").arg(workerClient));
        return;
    }

    auto *process = new QProcess(this);
    workflowLifecycleProcess_ = process;
    workflowLifecycleFinishedHandler_ = std::move(finishedHandler);

    process->setProgram(pythonExecutable_);
    process->setArguments({workerClient});
    process->setWorkingDirectory(projectRoot_);

    auto *timeoutTimer = new QTimer(process);
    timeoutTimer->setSingleShot(true);
    timeoutTimer->setInterval(qMax(1000, timeoutMs));

    setWorkflowLifecycleBusy(true, busyText);

    connect(timeoutTimer, &QTimer::timeout, this, [this, process, timeoutText]() {
        if (workflowLifecycleProcess_ != process)
            return;

        process->setProperty("spellvision_timeout_error", timeoutText);
        process->kill();
    });

    connect(process, &QProcess::started, this, [process, request, timeoutTimer]() {
        process->write(QJsonDocument(request).toJson(QJsonDocument::Compact));
        process->write("\n");
        process->closeWriteChannel();
        timeoutTimer->start();
    });

    connect(process, &QProcess::errorOccurred, this, [this, process](QProcess::ProcessError) {
        if (workflowLifecycleProcess_ != process)
            return;

        const QString errorText = process->errorString().trimmed();
        workflowLifecycleProcess_ = nullptr;
        const auto handler = std::move(workflowLifecycleFinishedHandler_);
        workflowLifecycleFinishedHandler_ = {};

        setWorkflowLifecycleBusy(false, QString());
        process->deleteLater();

        if (handler)
        {
            handler(QJsonObject{
                        {QStringLiteral("ok"), false},
                        {QStringLiteral("error"), errorText.isEmpty() ? QStringLiteral("Worker process failed to start or crashed.") : errorText}},
                    QString());
        }
    });

    connect(process,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this,
            [this, process](int exitCode, QProcess::ExitStatus exitStatus) {
                if (workflowLifecycleProcess_ != process)
                {
                    process->deleteLater();
                    return;
                }

                workflowLifecycleProcess_ = nullptr;
                const auto handler = std::move(workflowLifecycleFinishedHandler_);
                workflowLifecycleFinishedHandler_ = {};

                const QString allStdout = QString::fromUtf8(process->readAllStandardOutput()).trimmed();
                const QString allStderr = QString::fromUtf8(process->readAllStandardError()).trimmed();
                const QString timeoutError = process->property("spellvision_timeout_error").toString().trimmed();

                QString parseErrorText;
                QJsonObject response;
                if (!timeoutError.isEmpty())
                {
                    response = QJsonObject{
                        {QStringLiteral("ok"), false},
                        {QStringLiteral("error"), timeoutError}
                    };
                }
                else
                {
                    response = parseLastJsonObjectFromStdout(allStdout, &parseErrorText);
                    if (response.isEmpty())
                    {
                        response = QJsonObject{
                            {QStringLiteral("ok"), false},
                            {QStringLiteral("error"), parseErrorText.isEmpty() ? QStringLiteral("Worker returned no usable JSON payload.") : parseErrorText},
                            {QStringLiteral("stderr"), allStderr}
                        };
                    }
                    else if (!(exitStatus == QProcess::NormalExit && exitCode == 0)
                             && response.value(QStringLiteral("ok")).toBool(false))
                    {
                        response.insert(QStringLiteral("ok"), false);
                        if (!response.contains(QStringLiteral("error")))
                            response.insert(QStringLiteral("error"), allStderr.isEmpty() ? QStringLiteral("worker_client.py exited with code %1.").arg(exitCode) : allStderr);
                    }
                }

                setWorkflowLifecycleBusy(false, QString());
                process->deleteLater();

                if (handler)
                    handler(response, allStderr);
            });

    process->start();
}


void WorkflowLibraryPage::buildUi()
{
    auto *rootLayout = new QVBoxLayout(this);
    rootLayout->setContentsMargins(16, 16, 16, 16);
    rootLayout->setSpacing(12);

    titleLabel_ = new QLabel(tr("Workflow Library"), this);
    summaryLabel_ = new QLabel(this);
    summaryLabel_->setWordWrap(true);
    cacheStatusLabel_ = new QLabel(tr("Cache: none"), this);
    cacheStatusLabel_->setWordWrap(true);

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
    checkReadinessButton_ = new QPushButton(tr("Check Readiness"), detailPane);
    retryDependenciesButton_ = new QPushButton(tr("Rescan / Retry Deps"), detailPane);
    revealFolderButton_ = new QPushButton(tr("Reveal Folder"), detailPane);
    openWorkflowJsonButton_ = new QPushButton(tr("Open Workflow JSON"), detailPane);
    deleteWorkflowButton_ = new QPushButton(tr("Delete Workflow"), detailPane);

    checkReadinessButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    retryDependenciesButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    deleteWorkflowButton_->setObjectName(QStringLiteral("TertiaryActionButton"));

    connect(applyButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onApplyClicked);
    connect(launchButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onLaunchClicked);
    connect(checkReadinessButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onCheckReadinessClicked);
    connect(retryDependenciesButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onRetryDependenciesClicked);
    connect(revealFolderButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onRevealFolderClicked);
    connect(openWorkflowJsonButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onOpenWorkflowJsonClicked);
    connect(deleteWorkflowButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::onDeleteWorkflowClicked);

    auto *detailButtons = new QHBoxLayout();
    detailButtons->setSpacing(8);
    detailButtons->addWidget(applyButton_);
    detailButtons->addWidget(launchButton_);
    detailButtons->addWidget(checkReadinessButton_);
    detailButtons->addWidget(retryDependenciesButton_);
    detailButtons->addWidget(revealFolderButton_);
    detailButtons->addWidget(openWorkflowJsonButton_);
    detailButtons->addStretch(1);
    detailButtons->addWidget(deleteWorkflowButton_);

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
    rootLayout->addWidget(cacheStatusLabel_);
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

    applyCapabilityReport(record, capabilityObjectFromProfile(object));

    const QJsonObject metadataObject = object.value(QStringLiteral("metadata")).toObject();
    const QJsonObject readinessObject = metadataObject.value(QStringLiteral("last_launch_readiness")).toObject();
    if (!readinessObject.isEmpty())
    {
        record.launchReadinessChecked = true;
        record.launchReadinessPassed = readinessObject.value(QStringLiteral("ok")).toBool(false);
        record.launchReadinessSummary = readinessObject.value(QStringLiteral("summary")).toString().trimmed();
        record.launchReadinessErrors = stringListFromJsonValue(readinessObject.value(QStringLiteral("errors")));
        record.launchReadinessWarnings = stringListFromJsonValue(readinessObject.value(QStringLiteral("warnings")));
        record.launchReadinessMissingNodes = stringListFromJsonValue(readinessObject.value(QStringLiteral("missing_node_classes")));
        record.launchReadinessMissingAssets = stringListFromJsonValue(readinessObject.value(QStringLiteral("missing_runtime_assets")));
        for (const QString &nodeClass : record.launchReadinessMissingNodes)
        {
            if (!record.missingCustomNodes.contains(nodeClass, Qt::CaseInsensitive))
                record.missingCustomNodes.push_back(nodeClass);
        }
        for (const QString &warning : record.launchReadinessWarnings)
        {
            if (!record.runtimeAssetWarnings.contains(warning, Qt::CaseInsensitive))
                record.runtimeAssetWarnings.push_back(warning);
        }
        for (const QString &asset : record.launchReadinessMissingAssets)
        {
            if (!record.missingRuntimeAssets.contains(asset, Qt::CaseInsensitive))
                record.missingRuntimeAssets.push_back(asset);
        }
    }

    const QString taskOverride = normalizedModeId(safeObjectString(object, {
        QStringLiteral("user_task_override"),
        QStringLiteral("task_override")
    }));
    if (!taskOverride.isEmpty())
        record.modeId = taskOverride;

    const QString mediaOverride = safeObjectString(object, {
        QStringLiteral("user_media_override"),
        QStringLiteral("media_override")
    }).trimmed().toLower();
    if (!mediaOverride.isEmpty())
        record.mediaType = mediaOverride;

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

            if (!record.capabilityFromGraph)
                applyCapabilityReport(record, capabilityObjectFromProfile(scanObj));

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

    if (record.mediaType.trimmed().isEmpty() || record.mediaType == QStringLiteral("unknown"))
    {
        if (record.outputKinds.contains(QStringLiteral("video")) || record.outputKinds.contains(QStringLiteral("gif")))
            record.mediaType = QStringLiteral("video");
        else if (record.outputKinds.contains(QStringLiteral("image")))
            record.mediaType = QStringLiteral("image");
    }

    const bool supportedImageWorkflow = isImageMode(record.modeId, record.mediaType);
    const bool supportedVideoWorkflow = isVideoMode(record.modeId, record.mediaType);
    record.supportedInCurrentBuild = supportedImageWorkflow || supportedVideoWorkflow;

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
    record.runtimeProbe.message = tr("Runtime validation deferred until launch.");

    if (record.backend.compare(QStringLiteral("comfy_workflow"), Qt::CaseInsensitive) != 0)
    {
        record.runtimeProbe.message = tr("Runtime validation is not required for this backend.");
        return;
    }

    if (!record.supportedInCurrentBuild)
    {
        record.runtimeProbe.ok = false;
        record.runtimeProbe.message = tr("Workflow capability is not supported by the current build.");
        return;
    }

    record.runtimeProbe.message = tr("Comfy runtime reachability is checked when the workflow is launched, not during library refresh.");
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

    record.runtimeAssetValidationMessage = tr("Runtime asset validation is deferred until launch to keep the workflow library responsive.");
    record.runtimeAssetWarnings.push_back(record.runtimeAssetValidationMessage);
}

void WorkflowLibraryPage::classifyWorkflow(WorkflowRecord &record) const
{
    if (!record.supportedInCurrentBuild)
    {
        record.readiness = ReadinessState::Unsupported;
        record.readinessLabel = tr("Unsupported");
        record.readinessReason = tr("This workflow capability is not supported by the current build or could not be classified with enough evidence.");
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

    if (record.launchReadinessChecked && record.launchReadinessPassed)
    {
        record.readiness = ReadinessState::Ready;
        record.readinessLabel = tr("Ready");
        record.readinessReason = !record.launchReadinessSummary.isEmpty()
            ? record.launchReadinessSummary
            : tr("Explicit launch preflight passed.");
        return;
    }

    if (record.launchReadinessChecked && !record.launchReadinessPassed)
    {
        record.readiness = (!record.launchReadinessMissingNodes.isEmpty() || !record.launchReadinessMissingAssets.isEmpty())
            ? ReadinessState::MissingDependencies
            : ReadinessState::NeedsReview;
        record.readinessLabel = record.readiness == ReadinessState::MissingDependencies
            ? tr("Missing dependencies")
            : tr("Needs review");
        record.readinessReason = !record.launchReadinessSummary.isEmpty()
            ? record.launchReadinessSummary
            : tr("The last explicit launch preflight found blockers.");
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

void WorkflowLibraryPage::applyCapabilityReport(WorkflowRecord &record, const QJsonObject &capability) const
{
    if (capability.isEmpty())
        return;

    const QString primaryTask = normalizedModeId(safeObjectString(capability, {
        QStringLiteral("primary_task"),
        QStringLiteral("task_command"),
        QStringLiteral("mode_id"),
        QStringLiteral("task")
    }));
    const QString mediaType = safeObjectString(capability, {
        QStringLiteral("media_type"),
        QStringLiteral("media")
    }).trimmed().toLower();

    const QStringList supportedModes = stringListFromJsonValue(capability.value(QStringLiteral("supported_modes")));
    const QStringList requiredInputs = stringListFromJsonValue(capability.value(QStringLiteral("required_inputs")));
    const QStringList optionalInputs = stringListFromJsonValue(capability.value(QStringLiteral("optional_inputs")));
    const QStringList outputKinds = stringListFromJsonValue(capability.value(QStringLiteral("output_kinds")));
    const QStringList warnings = stringListFromJsonValue(capability.value(QStringLiteral("warnings")));
    const QStringList evidence = stringListFromJsonValue(capability.value(QStringLiteral("evidence")));

    if (!primaryTask.isEmpty() && primaryTask != QStringLiteral("unknown"))
    {
        record.primaryTask = primaryTask;
        record.modeId = primaryTask;
        record.capabilityFromGraph = true;
    }

    if (!mediaType.isEmpty() && mediaType != QStringLiteral("unknown"))
        record.mediaType = mediaType;

    if (!supportedModes.isEmpty())
        record.supportedModes = supportedModes;
    if (!requiredInputs.isEmpty())
        record.requiredInputs = requiredInputs;
    if (!optionalInputs.isEmpty())
        record.optionalInputs = optionalInputs;
    if (!outputKinds.isEmpty())
        record.outputKinds = outputKinds;
    if (!warnings.isEmpty())
        record.capabilityWarnings = warnings;
    if (!evidence.isEmpty())
        record.capabilityEvidence = evidence;

    if (capability.value(QStringLiteral("confidence")).isDouble())
        record.classificationConfidence = capability.value(QStringLiteral("confidence")).toDouble();

    const QString version = capability.value(QStringLiteral("classification_version")).toString().trimmed();
    if (!version.isEmpty())
        record.capabilityVersion = version;

    for (const QString &mode : record.supportedModes)
    {
        const QString tag = normalizedModeId(mode);
        if (!tag.isEmpty() && !record.tags.contains(tag, Qt::CaseInsensitive))
            record.tags.push_back(tag);
    }
    for (const QString &kind : record.outputKinds)
    {
        if (!kind.trimmed().isEmpty() && !record.tags.contains(kind, Qt::CaseInsensitive))
            record.tags.push_back(kind.trimmed().toLower());
    }
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

    const bool draftImageWorkflow = isImageMode(record.modeId, record.mediaType);
    const bool draftVideoWorkflow = isVideoMode(record.modeId, record.mediaType)
        && normalizedModeId(record.modeId) != QStringLiteral("v2v");
    if (!draftImageWorkflow && !draftVideoWorkflow)
    {
        record.reusableDraftReason = tr("Only image, text-to-video, and image-to-video workflows can currently open as editable drafts.");
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
    int frames = 0;
    int fps = 0;
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
        if (frames <= 0)
            frames = inputs.value(QStringLiteral("num_frames")).toInt(
                inputs.value(QStringLiteral("frames")).toInt(
                    inputs.value(QStringLiteral("frame_count")).toInt(frames)));
        if (fps <= 0)
            fps = inputs.value(QStringLiteral("fps")).toInt(
                inputs.value(QStringLiteral("frame_rate")).toInt(fps));

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
    if (frames > 0)
        draft.insert(QStringLiteral("frames"), frames);
    if (fps > 0)
        draft.insert(QStringLiteral("fps"), fps);
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
    if (checkpointName.trimmed().isEmpty() && !isVideoMode(record.modeId, record.mediaType))
    {
        safeToSubmit = false;
        draftWarnings.push_back(tr("No checkpoint could be inferred from the compiled prompt."));
    }
    else if (checkpointName.trimmed().isEmpty() && isVideoMode(record.modeId, record.mediaType))
    {
        draftWarnings.push_back(tr("No standalone checkpoint was inferred. The video workflow may carry its own model stack through the compiled prompt."));
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
            + record.supportedModes.join(QLatin1Char(' ')) + QLatin1Char(' ')
            + record.requiredInputs.join(QLatin1Char(' ')) + QLatin1Char(' ')
            + record.outputKinds.join(QLatin1Char(' ')) + QLatin1Char(' ')
            + record.capabilityEvidence.join(QLatin1Char(' ')) + QLatin1Char(' ')
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

    if (cacheStatusLabel_)
    {
        const QString source = libraryCacheSource_.trimmed().isEmpty() ? QStringLiteral("none") : libraryCacheSource_;
        const QString ts = libraryCacheAtMs_ > 0
            ? QDateTime::fromMSecsSinceEpoch(libraryCacheAtMs_).toLocalTime().toString(QStringLiteral("yyyy-MM-dd hh:mm:ss AP"))
            : QStringLiteral("never");
        cacheStatusLabel_->setText(tr("Cache source: %1   Last checked: %2   Cache path: %3")
                                       .arg(source,
                                            ts,
                                            QDir::toNativeSeparators(cacheFilePath())));
    }
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
    if (record.launchReadinessChecked)
        statusText += QStringLiteral("\nLast launch preflight: %1").arg(record.launchReadinessPassed ? tr("passed") : tr("needs attention"));
    detailStatusLabel_->setText(statusText);
    detailText_->setPlainText(workflowDetailsText(record));

    const bool canApplyDraft = record.reusableDraftPresent
        && (isImageMode(record.modeId, record.mediaType) || isVideoMode(record.modeId, record.mediaType))
        && normalizedModeId(record.modeId) != QStringLiteral("v2v");
    if (applyButton_)
    {
        applyButton_->setVisible(canApplyDraft);
        applyButton_->setEnabled(canApplyDraft);
        const QString normalized = normalizedModeId(record.modeId);
        if (normalized == QStringLiteral("i2i"))
            applyButton_->setText(tr("Open in I2I"));
        else if (normalized == QStringLiteral("i2v"))
            applyButton_->setText(tr("Open in I2V"));
        else if (normalized == QStringLiteral("t2v"))
            applyButton_->setText(tr("Open in T2V"));
        else
            applyButton_->setText(tr("Open in T2I"));
        applyButton_->setToolTip(record.reusableDraftReason);
    }

    const bool canCheckReadiness =
        record.backend.compare(QStringLiteral("comfy_workflow"), Qt::CaseInsensitive) == 0
        && (!record.launchArtifactPath.trimmed().isEmpty() || !record.compiledPromptPath.trimmed().isEmpty() || !record.profilePath.trimmed().isEmpty());

    if (checkReadinessButton_)
    {
        checkReadinessButton_->setText(tr("Check Readiness"));
        checkReadinessButton_->setVisible(canCheckReadiness);
        checkReadinessButton_->setEnabled(canCheckReadiness && !workflowLifecycleBusy_);
        checkReadinessButton_->setToolTip(
            canCheckReadiness
                ? tr("Start/connect Comfy if needed, validate the compiled prompt, check missing node classes, and verify loader assets against the live runtime.")
                : QString());
    }

    const bool canRescanOrRetry =
        !record.importRoot.trimmed().isEmpty()
        || !record.profilePath.trimmed().isEmpty()
        || record.workflowJsonPresent
        || record.compiledPromptPresent;

    if (retryDependenciesButton_)
    {
        retryDependenciesButton_->setText(tr("Rescan / Retry Deps"));
        retryDependenciesButton_->setVisible(canRescanOrRetry);
        retryDependenciesButton_->setEnabled(canRescanOrRetry && !workflowLifecycleBusy_);
        retryDependenciesButton_->setToolTip(
            canRescanOrRetry
                ? tr("Rescan this workflow, refresh capability classification, rebuild the dependency plan, and retry custom-node/model dependency installation when needed.")
                : QString());
    }

    if (deleteWorkflowButton_)
    {
        deleteWorkflowButton_->setText(tr("Delete Workflow"));
        deleteWorkflowButton_->setVisible(!record.importRoot.isEmpty());
        deleteWorkflowButton_->setEnabled(!record.importRoot.isEmpty() && !workflowLifecycleBusy_);
        deleteWorkflowButton_->setToolTip(tr("Remove this imported workflow folder from SpellVision's workflow library."));
    }

    launchButton_->setEnabled(!workflowLifecycleBusy_ && record.readiness == ReadinessState::Ready);
    revealFolderButton_->setEnabled(!workflowLifecycleBusy_ && !record.importRoot.isEmpty());
    openWorkflowJsonButton_->setEnabled(!workflowLifecycleBusy_ && (record.workflowJsonPresent || record.compiledPromptPresent));
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
    if (checkReadinessButton_)
    {
        checkReadinessButton_->setVisible(false);
        checkReadinessButton_->setEnabled(false);
        checkReadinessButton_->setToolTip(QString());
        checkReadinessButton_->setText(tr("Check Readiness"));
    }
    if (retryDependenciesButton_)
    {
        retryDependenciesButton_->setVisible(false);
        retryDependenciesButton_->setEnabled(false);
        retryDependenciesButton_->setToolTip(QString());
        retryDependenciesButton_->setText(tr("Rescan / Retry Deps"));
    }
    if (deleteWorkflowButton_)
    {
        deleteWorkflowButton_->setVisible(false);
        deleteWorkflowButton_->setEnabled(false);
        deleteWorkflowButton_->setToolTip(QString());
        deleteWorkflowButton_->setText(tr("Delete Workflow"));
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
    return QStringLiteral("%1\n%2 • %3 • %4 • %5\nModels: %6   Missing Nodes: %7   Unresolved: %8")
        .arg(record.displayName)
        .arg(record.modeId.isEmpty() ? QStringLiteral("UNKNOWN") : record.modeId.toUpper())
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

    return QStringLiteral("Task: %1\nBackend: %2\nMedia: %3\nSupported Modes: %4\nConfidence: %5\nSource Format: %6\nLaunch Artifact: %7\nValidated: %8\nAssets Ready: %9\nStatus: %10")
        .arg(record.modeId.toUpper())
        .arg(record.backend)
        .arg(record.mediaType)
        .arg(record.supportedModes.isEmpty() ? QStringLiteral("—") : record.supportedModes.join(QStringLiteral(", ")).toUpper())
        .arg(record.classificationConfidence > 0.0 ? QString::number(record.classificationConfidence, 'f', 2) : QStringLiteral("—"))
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
    lines << tr("Capability classifier: %1").arg(record.capabilityVersion.isEmpty() ? tr("legacy / unavailable") : record.capabilityVersion);
    lines << tr("Classification confidence: %1").arg(record.classificationConfidence > 0.0 ? QString::number(record.classificationConfidence, 'f', 2) : QStringLiteral("—"));
    lines << tr("Supported modes: %1").arg(record.supportedModes.isEmpty() ? QStringLiteral("—") : record.supportedModes.join(QStringLiteral(", ")).toUpper());
    lines << tr("Required inputs: %1").arg(record.requiredInputs.isEmpty() ? QStringLiteral("—") : record.requiredInputs.join(QStringLiteral(", ")));
    lines << tr("Optional inputs: %1").arg(record.optionalInputs.isEmpty() ? QStringLiteral("—") : record.optionalInputs.join(QStringLiteral(", ")));
    lines << tr("Output kinds: %1").arg(record.outputKinds.isEmpty() ? QStringLiteral("—") : record.outputKinds.join(QStringLiteral(", ")));
    if (!record.capabilityEvidence.isEmpty())
    {
        lines << tr("Capability evidence:");
        for (const QString &evidence : record.capabilityEvidence)
            lines << QStringLiteral("• %1").arg(evidence);
    }
    if (!record.capabilityWarnings.isEmpty())
    {
        lines << tr("Capability warnings:");
        for (const QString &warning : record.capabilityWarnings)
            lines << QStringLiteral("• %1").arg(warning);
    }
    lines << QString();
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

    if (record.launchReadinessChecked)
    {
        lines << tr("Last launch preflight: %1").arg(record.launchReadinessPassed ? tr("passed") : tr("needs attention"));
        if (!record.launchReadinessSummary.isEmpty())
            lines << tr("Preflight summary: %1").arg(record.launchReadinessSummary);
        if (!record.launchReadinessMissingNodes.isEmpty())
            lines << tr("Preflight missing node classes: %1").arg(record.launchReadinessMissingNodes.join(QStringLiteral(", ")));
        if (!record.launchReadinessMissingAssets.isEmpty())
            lines << tr("Preflight missing runtime assets: %1").arg(record.launchReadinessMissingAssets.join(QStringLiteral(", ")));
        for (const QString &warning : record.launchReadinessWarnings)
            lines << QStringLiteral("• %1").arg(warning);
        for (const QString &error : record.launchReadinessErrors)
            lines << QStringLiteral("! %1").arg(error);
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


QString WorkflowLibraryPage::cacheFilePath() const
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
    return dir.filePath(QStringLiteral("workflow_library_cache.json"));
}

QJsonObject WorkflowLibraryPage::workflowRecordToJson(const WorkflowRecord &record)
{
    QJsonObject object{
        {QStringLiteral("displayName"), record.displayName},
        {QStringLiteral("modeId"), record.modeId},
        {QStringLiteral("mediaType"), record.mediaType},
        {QStringLiteral("backend"), record.backend},
        {QStringLiteral("tags"), QJsonArray::fromStringList(record.tags)},
        {QStringLiteral("primaryTask"), record.primaryTask},
        {QStringLiteral("supportedModes"), QJsonArray::fromStringList(record.supportedModes)},
        {QStringLiteral("requiredInputs"), QJsonArray::fromStringList(record.requiredInputs)},
        {QStringLiteral("optionalInputs"), QJsonArray::fromStringList(record.optionalInputs)},
        {QStringLiteral("outputKinds"), QJsonArray::fromStringList(record.outputKinds)},
        {QStringLiteral("capabilityEvidence"), QJsonArray::fromStringList(record.capabilityEvidence)},
        {QStringLiteral("capabilityWarnings"), QJsonArray::fromStringList(record.capabilityWarnings)},
        {QStringLiteral("capabilityVersion"), record.capabilityVersion},
        {QStringLiteral("classificationConfidence"), record.classificationConfidence},
        {QStringLiteral("capabilityFromGraph"), record.capabilityFromGraph},
        {QStringLiteral("importRoot"), record.importRoot},
        {QStringLiteral("profilePath"), record.profilePath},
        {QStringLiteral("sourceWorkflowPath"), record.sourceWorkflowPath},
        {QStringLiteral("compiledPromptPath"), record.compiledPromptPath},
        {QStringLiteral("scanReportPath"), record.scanReportPath},
        {QStringLiteral("sourceWorkflowFormat"), record.sourceWorkflowFormat},
        {QStringLiteral("compiledPromptFormat"), record.compiledPromptFormat},
        {QStringLiteral("apiPromptCompatible"), record.apiPromptCompatible},
        {QStringLiteral("compiledPromptPresent"), record.compiledPromptPresent},
        {QStringLiteral("compileWarnings"), QJsonArray::fromStringList(record.compileWarnings)},
        {QStringLiteral("compileError"), record.compileError},
        {QStringLiteral("launchArtifactPath"), record.launchArtifactPath},
        {QStringLiteral("launchArtifactFormat"), record.launchArtifactFormat},
        {QStringLiteral("launchArtifactValidated"), record.launchArtifactValidated},
        {QStringLiteral("launchArtifactValid"), record.launchArtifactValid},
        {QStringLiteral("launchValidationErrors"), QJsonArray::fromStringList(record.launchValidationErrors)},
        {QStringLiteral("launchValidationWarnings"), QJsonArray::fromStringList(record.launchValidationWarnings)},
        {QStringLiteral("runtimeAssetValidationAttempted"), record.runtimeAssetValidationAttempted},
        {QStringLiteral("runtimeAssetValidationPassed"), record.runtimeAssetValidationPassed},
        {QStringLiteral("runtimeAssetValidationMessage"), record.runtimeAssetValidationMessage},
        {QStringLiteral("missingRuntimeAssets"), QJsonArray::fromStringList(record.missingRuntimeAssets)},
        {QStringLiteral("runtimeAssetWarnings"), QJsonArray::fromStringList(record.runtimeAssetWarnings)},
        {QStringLiteral("launchReadinessChecked"), record.launchReadinessChecked},
        {QStringLiteral("launchReadinessPassed"), record.launchReadinessPassed},
        {QStringLiteral("launchReadinessSummary"), record.launchReadinessSummary},
        {QStringLiteral("launchReadinessErrors"), QJsonArray::fromStringList(record.launchReadinessErrors)},
        {QStringLiteral("launchReadinessWarnings"), QJsonArray::fromStringList(record.launchReadinessWarnings)},
        {QStringLiteral("launchReadinessMissingNodes"), QJsonArray::fromStringList(record.launchReadinessMissingNodes)},
        {QStringLiteral("launchReadinessMissingAssets"), QJsonArray::fromStringList(record.launchReadinessMissingAssets)},
        {QStringLiteral("reusableDraftPresent"), record.reusableDraftPresent},
        {QStringLiteral("reusableDraftSafeToSubmit"), record.reusableDraftSafeToSubmit},
        {QStringLiteral("reusableDraftReason"), record.reusableDraftReason},
        {QStringLiteral("reusableDraft"), record.reusableDraft},
        {QStringLiteral("missingCustomNodes"), QJsonArray::fromStringList(record.missingCustomNodes)},
        {QStringLiteral("warnings"), QJsonArray::fromStringList(record.warnings)},
        {QStringLiteral("referencedModelCount"), record.referencedModelCount},
        {QStringLiteral("unresolvedDependencyActions"), record.unresolvedDependencyActions},
        {QStringLiteral("supportedInCurrentBuild"), record.supportedInCurrentBuild},
        {QStringLiteral("workflowJsonPresent"), record.workflowJsonPresent},
        {QStringLiteral("readiness"), static_cast<int>(record.readiness)},
        {QStringLiteral("readinessLabel"), record.readinessLabel},
        {QStringLiteral("readinessReason"), record.readinessReason},
        {QStringLiteral("runtimeProbeOk"), record.runtimeProbe.ok},
        {QStringLiteral("runtimeProbeMessage"), record.runtimeProbe.message},
    };
    return object;
}

WorkflowLibraryPage::WorkflowRecord WorkflowLibraryPage::workflowRecordFromJson(const QJsonObject &object)
{
    WorkflowRecord record;
    record.displayName = object.value(QStringLiteral("displayName")).toString();
    record.modeId = object.value(QStringLiteral("modeId")).toString();
    record.mediaType = object.value(QStringLiteral("mediaType")).toString();
    record.backend = object.value(QStringLiteral("backend")).toString();
    record.tags = safeObjectStringList(object, {QStringLiteral("tags")});
    record.primaryTask = object.value(QStringLiteral("primaryTask")).toString();
    record.supportedModes = safeObjectStringList(object, {QStringLiteral("supportedModes")});
    record.requiredInputs = safeObjectStringList(object, {QStringLiteral("requiredInputs")});
    record.optionalInputs = safeObjectStringList(object, {QStringLiteral("optionalInputs")});
    record.outputKinds = safeObjectStringList(object, {QStringLiteral("outputKinds")});
    record.capabilityEvidence = safeObjectStringList(object, {QStringLiteral("capabilityEvidence")});
    record.capabilityWarnings = safeObjectStringList(object, {QStringLiteral("capabilityWarnings")});
    record.capabilityVersion = object.value(QStringLiteral("capabilityVersion")).toString();
    record.classificationConfidence = object.value(QStringLiteral("classificationConfidence")).toDouble();
    record.capabilityFromGraph = object.value(QStringLiteral("capabilityFromGraph")).toBool(false);
    record.importRoot = object.value(QStringLiteral("importRoot")).toString();
    record.profilePath = object.value(QStringLiteral("profilePath")).toString();
    record.sourceWorkflowPath = object.value(QStringLiteral("sourceWorkflowPath")).toString();
    record.compiledPromptPath = object.value(QStringLiteral("compiledPromptPath")).toString();
    record.scanReportPath = object.value(QStringLiteral("scanReportPath")).toString();
    record.sourceWorkflowFormat = object.value(QStringLiteral("sourceWorkflowFormat")).toString(QStringLiteral("unknown"));
    record.compiledPromptFormat = object.value(QStringLiteral("compiledPromptFormat")).toString(QStringLiteral("unknown"));
    record.apiPromptCompatible = object.value(QStringLiteral("apiPromptCompatible")).toBool(false);
    record.compiledPromptPresent = object.value(QStringLiteral("compiledPromptPresent")).toBool(false);
    record.compileWarnings = safeObjectStringList(object, {QStringLiteral("compileWarnings")});
    record.compileError = object.value(QStringLiteral("compileError")).toString();
    record.launchArtifactPath = object.value(QStringLiteral("launchArtifactPath")).toString();
    record.launchArtifactFormat = object.value(QStringLiteral("launchArtifactFormat")).toString(QStringLiteral("unknown"));
    record.launchArtifactValidated = object.value(QStringLiteral("launchArtifactValidated")).toBool(false);
    record.launchArtifactValid = object.value(QStringLiteral("launchArtifactValid")).toBool(false);
    record.launchValidationErrors = safeObjectStringList(object, {QStringLiteral("launchValidationErrors")});
    record.launchValidationWarnings = safeObjectStringList(object, {QStringLiteral("launchValidationWarnings")});
    record.runtimeAssetValidationAttempted = object.value(QStringLiteral("runtimeAssetValidationAttempted")).toBool(false);
    record.runtimeAssetValidationPassed = object.value(QStringLiteral("runtimeAssetValidationPassed")).toBool(false);
    record.runtimeAssetValidationMessage = object.value(QStringLiteral("runtimeAssetValidationMessage")).toString();
    record.missingRuntimeAssets = safeObjectStringList(object, {QStringLiteral("missingRuntimeAssets")});
    record.runtimeAssetWarnings = safeObjectStringList(object, {QStringLiteral("runtimeAssetWarnings")});
    record.launchReadinessChecked = object.value(QStringLiteral("launchReadinessChecked")).toBool(false);
    record.launchReadinessPassed = object.value(QStringLiteral("launchReadinessPassed")).toBool(false);
    record.launchReadinessSummary = object.value(QStringLiteral("launchReadinessSummary")).toString();
    record.launchReadinessErrors = safeObjectStringList(object, {QStringLiteral("launchReadinessErrors")});
    record.launchReadinessWarnings = safeObjectStringList(object, {QStringLiteral("launchReadinessWarnings")});
    record.launchReadinessMissingNodes = safeObjectStringList(object, {QStringLiteral("launchReadinessMissingNodes")});
    record.launchReadinessMissingAssets = safeObjectStringList(object, {QStringLiteral("launchReadinessMissingAssets")});
    record.reusableDraftPresent = object.value(QStringLiteral("reusableDraftPresent")).toBool(false);
    record.reusableDraftSafeToSubmit = object.value(QStringLiteral("reusableDraftSafeToSubmit")).toBool(false);
    record.reusableDraftReason = object.value(QStringLiteral("reusableDraftReason")).toString();
    record.reusableDraft = object.value(QStringLiteral("reusableDraft")).toObject();
    record.missingCustomNodes = safeObjectStringList(object, {QStringLiteral("missingCustomNodes")});
    record.warnings = safeObjectStringList(object, {QStringLiteral("warnings")});
    record.referencedModelCount = object.value(QStringLiteral("referencedModelCount")).toInt();
    record.unresolvedDependencyActions = object.value(QStringLiteral("unresolvedDependencyActions")).toInt();
    record.supportedInCurrentBuild = object.value(QStringLiteral("supportedInCurrentBuild")).toBool(false);
    record.workflowJsonPresent = object.value(QStringLiteral("workflowJsonPresent")).toBool(false);
    record.readiness = static_cast<ReadinessState>(object.value(QStringLiteral("readiness")).toInt(static_cast<int>(ReadinessState::NeedsReview)));
    record.readinessLabel = object.value(QStringLiteral("readinessLabel")).toString();
    record.readinessReason = object.value(QStringLiteral("readinessReason")).toString();
    record.runtimeProbe.ok = object.value(QStringLiteral("runtimeProbeOk")).toBool(false);
    record.runtimeProbe.message = object.value(QStringLiteral("runtimeProbeMessage")).toString();
    return record;
}

bool WorkflowLibraryPage::loadLibraryCache()
{
    libraryCacheLoaded_ = false;
    libraryCacheSource_ = QStringLiteral("none");
    libraryCacheAtMs_ = 0;
    workflows_.clear();

    QFile file(cacheFilePath());
    if (!file.exists() || !file.open(QIODevice::ReadOnly))
        return false;

    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    file.close();
    if (!doc.isObject())
        return false;

    const QJsonObject root = doc.object();
    const QString cachedRoot = root.value(QStringLiteral("importedWorkflowsRoot")).toString();
    if (!cachedRoot.isEmpty() && !importedWorkflowsRoot_.isEmpty() &&
        QDir::cleanPath(cachedRoot) != QDir::cleanPath(importedWorkflowsRoot_))
    {
        return false;
    }

    const QJsonArray items = root.value(QStringLiteral("workflows")).toArray();
    for (const QJsonValue &value : items)
    {
        if (value.isObject())
            workflows_.push_back(workflowRecordFromJson(value.toObject()));
    }

    libraryCacheLoaded_ = !workflows_.isEmpty();
    libraryCacheSource_ = libraryCacheLoaded_ ? QStringLiteral("disk") : QStringLiteral("none");
    libraryCacheAtMs_ = static_cast<qint64>(root.value(QStringLiteral("cachedAtMs")).toDouble(0.0));
    return libraryCacheLoaded_;
}

void WorkflowLibraryPage::persistLibraryCache() const
{
    QDir(QFileInfo(cacheFilePath()).absolutePath()).mkpath(QStringLiteral("."));

    QJsonArray items;
    for (const WorkflowRecord &record : workflows_)
        items.append(workflowRecordToJson(record));

    QJsonObject root{
        {QStringLiteral("importedWorkflowsRoot"), importedWorkflowsRoot_},
        {QStringLiteral("cachedAtMs"), static_cast<double>(QDateTime::currentMSecsSinceEpoch())},
        {QStringLiteral("workflows"), items},
    };

    QSaveFile file(cacheFilePath());
    if (!file.open(QIODevice::WriteOnly))
        return;

    file.write(QJsonDocument(root).toJson(QJsonDocument::Compact));
    file.commit();
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
