#include "WorkflowDraftBuilder.h"

#include "WorkflowLaunchController.h"

#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QJsonValue>
#include <QList>
#include <QSet>
#include <QStringList>

namespace spellvision::workflows
{
namespace
{

// --- moved verbatim from WorkflowLibraryPage.cpp -------------------------------------------------
//
// These were a private anonymous namespace inside the Flows page, used by nothing but
// buildReusableDraft, which is why a second caller could not reach them without copying them. They
// are unchanged: the point of the move is that there is still exactly ONE answer to "what does this
// graph say the checkpoint is", not a new one written for the drop path.

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

// Walk the conditioning graph UPSTREAM from a node to find its source CLIPTextEncode text.
//
// The conditioning graph can contain CYCLES (IPAdapter / reroute feedback loops are common in complex
// ComfyUI workflows). This was previously a plain recursion with no visited-set, so a cyclic chain
// recursed until the native stack overflowed (STATUS_STACK_OVERFLOW, 0xC00000FD). That crashed startup
// as soon as ONE such workflow was in the imported library and hit during the (background) library
// scan -- surfaced by the 81-workflow import, whose "ip-adapter-json" profile has a self-referential
// conditioning node (node 10 -> ... -> node 10). It looked count-dependent only because that profile
// sorts partway through the scan; it is really a single pathological graph.
//
// Fixed by an explicit-stack iterative DFS with a visited-set: bounded native stack (O(1) frames) and
// O(nodes) work, cycle-safe. Semantics are preserved -- passthrough keys are explored in their
// original order (reverse-pushed so LIFO yields the same pre-order), the first non-empty CLIPTextEncode
// text wins, and empty encode nodes are skipped exactly as the recursive version's callers did.
QString textFromClipEncode(const QJsonObject &prompt, const QString &startNodeId)
{
    static const QStringList passthroughKeys = {
        QStringLiteral("text"),
        QStringLiteral("conditioning"),
        QStringLiteral("positive"),
        QStringLiteral("negative"),
        QStringLiteral("base_cond"),
        QStringLiteral("refiner_cond")
    };

    QStringList pending;
    if (!startNodeId.trimmed().isEmpty())
        pending.push_back(startNodeId);

    QSet<QString> visited;
    while (!pending.isEmpty())
    {
        const QString nodeId = pending.takeLast();
        if (nodeId.trimmed().isEmpty() || visited.contains(nodeId))
            continue;
        visited.insert(nodeId);

        const QJsonValue nodeValue = prompt.value(nodeId);
        if (!nodeValue.isObject())
            continue;

        const QJsonObject node = nodeValue.toObject();
        const QString classType = node.value(QStringLiteral("class_type")).toString().trimmed();
        const QJsonObject inputs = node.value(QStringLiteral("inputs")).toObject();

        if (classType == QStringLiteral("CLIPTextEncode"))
        {
            const QString text = inputs.value(QStringLiteral("text")).toString().trimmed();
            if (!text.isEmpty())
                return text;
            continue; // empty encode node: keep searching (matches the recursive skip-empty behaviour)
        }

        // Reverse-push so the first passthrough key is popped first (LIFO => original DFS pre-order).
        for (int i = passthroughKeys.size() - 1; i >= 0; --i)
        {
            const QString nextNodeId = nodeInputRefId(inputs.value(passthroughKeys.at(i)));
            if (!nextNodeId.trimmed().isEmpty())
                pending.push_back(nextNodeId);
        }
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
} // namespace

bool WorkflowDraftBuilder::isVideoMode(const QString &modeId, const QString &mediaType)
{
    const QString mode = modeId.trimmed().toLower();
    const QString media = mediaType.trimmed().toLower();

    return mode == QStringLiteral("t2v")
        || mode == QStringLiteral("i2v")
        || mode == QStringLiteral("v2v")
        || media == QStringLiteral("video");
}

bool WorkflowDraftBuilder::isImageMode(const QString &modeId, const QString &mediaType)
{
    const QString mode = modeId.trimmed().toLower();
    const QString media = mediaType.trimmed().toLower();

    return mode == QStringLiteral("t2i")
        || mode == QStringLiteral("i2i")
        || media == QStringLiteral("image");
}

bool WorkflowDraftBuilder::isDraftableShape(const QString &modeId, const QString &mediaType)
{
    const bool image = isImageMode(modeId, mediaType);
    // A v2v graph reads as video by media_type, so the mode has to be excluded explicitly -- the
    // same carve-out WorkflowLaunchController makes by keeping v2v out of its routable set.
    const bool video = isVideoMode(modeId, mediaType)
        && WorkflowLaunchController::normalizeModeId(modeId) != QStringLiteral("v2v");
    return image || video;
}

QString WorkflowDraftBuilder::resolvePromptPath(const Source &source)
{
    QString promptPath = source.compiledPromptPath.trimmed();
    if (!promptPath.isEmpty() && QFileInfo::exists(promptPath))
        return promptPath;

    // No compiled prompt on disk. If the source graph IS an API prompt there is nothing to compile
    // and it can be read directly; a UI graph cannot be, and saying so is the honest answer --
    // compiling one needs the live /object_info schema, which is the worker's compile_workflow_prompt
    // command and the step the drop path never called.
    if (source.sourceWorkflowFormat == QStringLiteral("comfy_api_prompt")
        && !source.sourceWorkflowPath.trimmed().isEmpty())
    {
        promptPath = source.sourceWorkflowPath.trimmed();
        if (QFileInfo::exists(promptPath))
            return promptPath;
    }

    return {};
}

WorkflowDraftBuilder::Result WorkflowDraftBuilder::build(const Source &source)
{
    Result result;

    if (!isDraftableShape(source.modeId, source.mediaType))
    {
        result.reason = QStringLiteral(
            "Only image, text-to-video, and image-to-video workflows can currently open as editable drafts.");
        return result;
    }

    const QString promptPath = resolvePromptPath(source);
    if (promptPath.isEmpty())
    {
        result.reason = QStringLiteral("No compiled or API prompt is available for reusable handoff.");
        return result;
    }

    QFile file(promptPath);
    if (!file.open(QIODevice::ReadOnly))
    {
        result.reason = QStringLiteral("Compiled prompt could not be opened.");
        return result;
    }

    QJsonParseError parseError{};
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
    {
        result.reason = QStringLiteral("Compiled prompt is not valid JSON.");
        return result;
    }

    Source resolved = source;
    resolved.compiledPromptPath = promptPath;
    return buildFromPrompt(doc.object(), resolved);
}

WorkflowDraftBuilder::Result WorkflowDraftBuilder::buildFromPrompt(const QJsonObject &prompt,
                                                                  const Source &source)
{
    Result result;

    if (!isDraftableShape(source.modeId, source.mediaType))
    {
        result.reason = QStringLiteral(
            "Only image, text-to-video, and image-to-video workflows can currently open as editable drafts.");
        return result;
    }

    if (prompt.isEmpty())
    {
        result.reason = QStringLiteral("Compiled prompt is empty.");
        return result;
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
    draft.insert(QStringLiteral("source_name"), source.displayName);
    draft.insert(QStringLiteral("source_profile_path"), source.profilePath);
    draft.insert(QStringLiteral("source_workflow_path"), source.sourceWorkflowPath);
    draft.insert(QStringLiteral("compiled_prompt_path"), source.compiledPromptPath);
    draft.insert(QStringLiteral("mode_id"), WorkflowLaunchController::normalizeModeId(source.modeId));
    draft.insert(QStringLiteral("media_type"), source.mediaType);
    draft.insert(QStringLiteral("backend"), source.backend);
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
    if (checkpointName.trimmed().isEmpty() && !isVideoMode(source.modeId, source.mediaType))
    {
        safeToSubmit = false;
        draftWarnings.push_back(QStringLiteral("No checkpoint could be inferred from the compiled prompt."));
    }
    else if (checkpointName.trimmed().isEmpty() && isVideoMode(source.modeId, source.mediaType))
    {
        draftWarnings.push_back(QStringLiteral("No standalone checkpoint was inferred. The video workflow may carry its own model stack through the compiled prompt."));
    }
    if (loraNames.size() > 1)
    {
        draftWarnings.push_back(QStringLiteral("This workflow uses %1 LoRAs. Review the imported stack before generating.").arg(loraNames.size()));
    }
    if (!source.missingRuntimeAssets.isEmpty())
    {
        safeToSubmit = false;
        draftWarnings.push_back(QStringLiteral("Runtime asset validation failed for %1 imported assets. Remap the stack on the generation page before submitting.").arg(source.missingRuntimeAssets.size()));
    }
    if (!source.missingCustomNodes.isEmpty())
        draftWarnings.push_back(QStringLiteral("The original workflow references missing custom nodes, so this draft should be treated as a reusable approximation."));

    QJsonArray warningArray;
    for (const QString &warning : draftWarnings)
        warningArray.append(warning);
    draft.insert(QStringLiteral("warnings"), warningArray);
    draft.insert(QStringLiteral("safe_to_submit"), safeToSubmit);
    draft.insert(QStringLiteral("supports_apply"), true);

    result.present = true;
    result.safeToSubmit = safeToSubmit;
    result.reason = safeToSubmit
        ? QStringLiteral("This workflow can open as an editable generation draft.")
        : QStringLiteral("This workflow can open as an editable draft, but it still needs review before submission.");
    result.draft = draft;
    return result;
}

} // namespace spellvision::workflows
