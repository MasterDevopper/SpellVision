#include "WorkflowDraftBuilder.h"

#include "WorkflowLaunchController.h"

#include "assets/AssetCatalogScanner.h"

#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QJsonValue>
#include <QList>
#include <QSet>
#include <QStringList>
#include <QVariant>

#include <optional>

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
//
// `reachedEncode` separates "the graph says the prompt is empty" from "the prompt is not readable
// from here". Both return an empty string, and the draft must not treat them the same: the first is
// a value, the second is a field the user has to be told was not carried over.
QString textFromClipEncode(const QJsonObject &prompt, const QString &startNodeId, bool *reachedEncode = nullptr)
{
    if (reachedEncode)
        *reachedEncode = false;

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
            if (reachedEncode)
                *reachedEncode = true;
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
        // .sft is safetensors under its short name, and .gguf is how every quantized Wan / Flux /
        // Qwen checkpoint in the library is shipped. Their absence here is why the model walk below
        // ran off the end of four Wan graphs whose loader is a UnetLoaderGGUF: the file was right
        // there, and the value did not read as a model.
        || suffix == QStringLiteral("sft")
        || suffix == QStringLiteral("gguf")
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

// --- the modern custom-sampler chain -------------------------------------------------------------
//
// KSampler is not how a current graph samples. Flux, SD3, Qwen and Krea graphs build the same job
// out of SamplerCustomAdvanced + a guider + a noise source + a sampler selector + a sigma schedule.
// Those are CORE ComfyUI classes, so reading only KSampler / KSamplerAdvanced was not a gap for one
// owner workflow -- it was a gap for the whole present-day vocabulary, and the builder answered it
// with zero-initialised fields that then read on the page as if the workflow had asked for cfg 0.
//
// The values are not on the sampler node. Every one of them arrives over a link, so each has to be
// walked to. The walk follows a link exactly ONE hop to a node that carries a literal of the right
// type. Two hops is where reading stops and guessing starts: a number behind a math node, an
// expression or a custom author's pipe is not in the graph AS a number, and inventing one is the
// defect this exists to remove. Every walk carries a visited-set -- a ComfyUI graph can contain
// cycles, and this file has already been bitten by one (see textFromClipEncode above).

QJsonObject nodeInputsFor(const QJsonObject &prompt, const QString &nodeId)
{
    if (nodeId.trimmed().isEmpty())
        return {};
    return prompt.value(nodeId).toObject().value(QStringLiteral("inputs")).toObject();
}

QString nodeClassFor(const QJsonObject &prompt, const QString &nodeId)
{
    if (nodeId.trimmed().isEmpty())
        return {};
    return prompt.value(nodeId).toObject().value(QStringLiteral("class_type")).toString().trimmed();
}

// A prompt input is either a literal or a ["nodeId", slot] link. Resolve a literal number: the input
// itself when it is one, otherwise one hop past the link -- preferring the SAME input name on the far
// node (a passthrough keeps the name) and otherwise accepting the far node's ONLY numeric literal,
// which is what a PrimitiveInt / PrimitiveFloat / rgthree Seed node is. More than one candidate is
// ambiguous, and an ambiguous pick is a guess, so it refuses instead.
std::optional<QJsonValue> resolveNumericInput(const QJsonObject &prompt,
                                              const QJsonObject &inputs,
                                              const QString &key)
{
    const QJsonValue direct = inputs.value(key);
    if (direct.isDouble())
        return direct;

    const QJsonObject farInputs = nodeInputsFor(prompt, nodeInputRefId(direct));
    if (farInputs.isEmpty())
        return std::nullopt;

    const QJsonValue sameName = farInputs.value(key);
    if (sameName.isDouble())
        return sameName;

    std::optional<QJsonValue> only;
    for (auto it = farInputs.constBegin(); it != farInputs.constEnd(); ++it)
    {
        if (!it.value().isDouble())
            continue;
        if (only.has_value())
            return std::nullopt;
        only = it.value();
    }
    return only;
}

QString resolveStringInput(const QJsonObject &prompt, const QJsonObject &inputs, const QString &key)
{
    const QJsonValue direct = inputs.value(key);
    if (direct.isString())
        return direct.toString().trimmed();

    const QJsonObject farInputs = nodeInputsFor(prompt, nodeInputRefId(direct));
    if (farInputs.isEmpty())
        return {};

    const QJsonValue sameName = farInputs.value(key);
    if (sameName.isString())
        return sameName.toString().trimmed();

    QString only;
    bool ambiguous = false;
    for (auto it = farInputs.constBegin(); it != farInputs.constEnd(); ++it)
    {
        if (!it.value().isString())
            continue;
        if (!only.isEmpty())
        {
            ambiguous = true;
            break;
        }
        only = it.value().toString().trimmed();
    }
    return ambiguous ? QString() : only;
}

// What a graph says about sampling, with "did not say" kept distinct from "said zero".
struct SamplingFacts
{
    // A sampler node of some kind was located. Without this, NOTHING below was read, and the draft
    // must carry no sampling fields at all rather than a row of zeroes.
    bool found = false;
    std::optional<int> steps;
    std::optional<double> cfg;
    std::optional<qlonglong> seed;
    // DisableNoise / add_noise=false: there IS no seed here, which is not a failure to read one.
    bool seedDisabledByDesign = false;
    // A BasicGuider is unguided -- no negative conditioning and no cfg exist in this graph to read.
    bool negativeSlotAbsent = false;
    bool cfgSlotAbsent = false;
    QString sampler;
    QString scheduler;
    QString positiveRef;
    QString negativeRef;
    QString latentRef;
    // What this sampler samples WITH. The checkpoint is found by walking upstream from here, not by
    // matching input names anywhere in the graph -- see loaderOnModelPath below.
    QString modelRef;
};

void recoverGuiderFacts(const QJsonObject &prompt, const QString &guiderRef, SamplingFacts *facts)
{
    const QString classType = nodeClassFor(prompt, guiderRef);
    const QJsonObject inputs = nodeInputsFor(prompt, guiderRef);
    if (inputs.isEmpty() && classType.isEmpty())
        return;

    // Every guider shape takes `model`, whatever it does with the conditioning, so this is read once
    // rather than per class -- the same reason the sampler slot is read by its input name above.
    facts->modelRef = nodeInputRefId(inputs.value(QStringLiteral("model")));

    if (classType == QStringLiteral("CFGGuider"))
    {
        facts->positiveRef = nodeInputRefId(inputs.value(QStringLiteral("positive")));
        facts->negativeRef = nodeInputRefId(inputs.value(QStringLiteral("negative")));
        const auto cfg = resolveNumericInput(prompt, inputs, QStringLiteral("cfg"));
        if (cfg)
            facts->cfg = cfg->toDouble();
    }
    else if (classType == QStringLiteral("DualCFGGuider"))
    {
        facts->positiveRef = nodeInputRefId(inputs.value(QStringLiteral("cond1")));
        facts->negativeRef = nodeInputRefId(inputs.value(QStringLiteral("negative")));
        const auto cfg = resolveNumericInput(prompt, inputs, QStringLiteral("cfg_conds"));
        if (cfg)
            facts->cfg = cfg->toDouble();
    }
    else if (classType == QStringLiteral("BasicGuider"))
    {
        facts->positiveRef = nodeInputRefId(inputs.value(QStringLiteral("conditioning")));
        facts->negativeSlotAbsent = true;
        facts->cfgSlotAbsent = true;
    }
}

void recoverNoiseFacts(const QJsonObject &prompt, const QString &noiseRef, SamplingFacts *facts)
{
    if (nodeClassFor(prompt, noiseRef) == QStringLiteral("DisableNoise"))
    {
        facts->seedDisabledByDesign = true;
        return;
    }

    const auto seed = resolveNumericInput(prompt, nodeInputsFor(prompt, noiseRef), QStringLiteral("noise_seed"));
    if (seed)
        facts->seed = seed->toVariant().toLongLong();
}

// Sigmas are a chain, not a node: a scheduler produces them and splitters/modifiers pass them on.
// Walk it for the first steps count and the first named schedule.
void recoverSigmaFacts(const QJsonObject &prompt, const QString &sigmasRef, SamplingFacts *facts)
{
    static const QStringList sigmaPassthroughKeys = {
        QStringLiteral("sigmas"),
        QStringLiteral("sigmas_1"),
        QStringLiteral("sigmas_2")
    };

    QStringList pending;
    if (!sigmasRef.trimmed().isEmpty())
        pending.push_back(sigmasRef);

    QSet<QString> visited;
    while (!pending.isEmpty())
    {
        const QString nodeId = pending.takeLast();
        if (nodeId.trimmed().isEmpty() || visited.contains(nodeId))
            continue;
        visited.insert(nodeId);

        const QString classType = nodeClassFor(prompt, nodeId);
        const QJsonObject inputs = nodeInputsFor(prompt, nodeId);

        if (!facts->steps.has_value())
        {
            const auto steps = resolveNumericInput(prompt, inputs, QStringLiteral("steps"));
            if (steps)
                facts->steps = steps->toVariant().toInt();
        }

        if (facts->scheduler.isEmpty())
        {
            const QString named = resolveStringInput(prompt, inputs, QStringLiteral("scheduler"));
            if (!named.isEmpty())
                facts->scheduler = named;
            // BetaSamplingScheduler carries no `scheduler` input because the class IS the schedule,
            // and "beta" is the name core's own scheduler list gives it -- so this is reading the
            // core vocabulary, not inventing a name for it.
            else if (classType == QStringLiteral("BetaSamplingScheduler"))
                facts->scheduler = QStringLiteral("beta");
        }

        if (facts->steps.has_value() && !facts->scheduler.isEmpty())
            return;

        for (int i = sigmaPassthroughKeys.size() - 1; i >= 0; --i)
        {
            const QString next = nodeInputRefId(inputs.value(sigmaPassthroughKeys.at(i)));
            if (!next.trimmed().isEmpty())
                pending.push_back(next);
        }
    }
}

SamplingFacts recoverFromCustomSampler(const QJsonObject &prompt)
{
    SamplingFacts facts;

    for (auto it = prompt.constBegin(); it != prompt.constEnd(); ++it)
    {
        const QJsonObject node = it.value().toObject();
        const QString classType = node.value(QStringLiteral("class_type")).toString().trimmed();
        if (classType != QStringLiteral("SamplerCustomAdvanced") && classType != QStringLiteral("SamplerCustom"))
            continue;

        const QJsonObject inputs = node.value(QStringLiteral("inputs")).toObject();
        facts.found = true;
        facts.latentRef = nodeInputRefId(inputs.value(QStringLiteral("latent_image")));
        facts.modelRef = nodeInputRefId(inputs.value(QStringLiteral("model")));

        if (classType == QStringLiteral("SamplerCustom"))
        {
            // The older of the two: conditioning, cfg and the seed sit on the sampler itself.
            facts.positiveRef = nodeInputRefId(inputs.value(QStringLiteral("positive")));
            facts.negativeRef = nodeInputRefId(inputs.value(QStringLiteral("negative")));
            const auto cfg = resolveNumericInput(prompt, inputs, QStringLiteral("cfg"));
            if (cfg)
                facts.cfg = cfg->toDouble();
            if (!inputs.value(QStringLiteral("add_noise")).toBool(true))
                facts.seedDisabledByDesign = true;
            else
            {
                const auto seed = resolveNumericInput(prompt, inputs, QStringLiteral("noise_seed"));
                if (seed)
                    facts.seed = seed->toVariant().toLongLong();
            }
        }
        else
        {
            recoverGuiderFacts(prompt, nodeInputRefId(inputs.value(QStringLiteral("guider"))), &facts);
            recoverNoiseFacts(prompt, nodeInputRefId(inputs.value(QStringLiteral("noise"))), &facts);
        }

        // KSamplerSelect is the core one, but the sampler slot is an interface: any node that names
        // a sampler does it through a `sampler_name` input, so read the INPUT rather than keep a
        // list of classes that would be stale the next time somebody publishes a selector.
        facts.sampler = resolveStringInput(prompt,
                                           nodeInputsFor(prompt, nodeInputRefId(inputs.value(QStringLiteral("sampler")))),
                                           QStringLiteral("sampler_name"));
        recoverSigmaFacts(prompt, nodeInputRefId(inputs.value(QStringLiteral("sigmas"))), &facts);

        // First wins, which is the rule the KSampler path has always used.
        break;
    }

    return facts;
}

// The canvas is the size of the latent the sampler samples -- so find it by walking there, not by
// taking the first `width` input in the graph. That scan is how Pro Grade v17 reported 100x100: the
// first node in key order with a literal `width` was an LCImageCrop, a node with nothing to do with
// the output size. Measured over the 83 imported workflows that have a compiled prompt, this walk
// agrees with the old scan on 60, corrects 1 (it took a later ImageScale over the sampler's own
// latent), and honestly reports nothing on 4 where the old answer came from a node that was not on
// the latent path at all -- including that 100x100.
struct CanvasSize
{
    std::optional<int> width;
    std::optional<int> height;
};

CanvasSize canvasFromLatent(const QJsonObject &prompt, const QString &latentRef)
{
    static const QStringList latentPassthroughKeys = {
        QStringLiteral("samples"),
        QStringLiteral("latent"),
        QStringLiteral("latent_image"),
        QStringLiteral("pixels"),
        QStringLiteral("image")
    };

    QStringList pending;
    if (!latentRef.trimmed().isEmpty())
        pending.push_back(latentRef);

    QSet<QString> visited;
    while (!pending.isEmpty())
    {
        const QString nodeId = pending.takeLast();
        if (nodeId.trimmed().isEmpty() || visited.contains(nodeId))
            continue;
        visited.insert(nodeId);

        const QJsonObject inputs = nodeInputsFor(prompt, nodeId);
        const auto width = resolveNumericInput(prompt, inputs, QStringLiteral("width"));
        const auto height = resolveNumericInput(prompt, inputs, QStringLiteral("height"));
        if (width && height && width->toVariant().toInt() > 0 && height->toVariant().toInt() > 0)
        {
            CanvasSize size;
            size.width = width->toVariant().toInt();
            size.height = height->toVariant().toInt();
            return size;
        }

        for (int i = latentPassthroughKeys.size() - 1; i >= 0; --i)
        {
            const QString next = nodeInputRefId(inputs.value(latentPassthroughKeys.at(i)));
            if (!next.trimmed().isEmpty())
                pending.push_back(next);
        }
    }

    return {};
}

// --- the model path ------------------------------------------------------------------------------
//
// The graph STATES which model it samples with, structurally: the sampler has a `model` input, and
// following it upstream through the LoRA loaders, the ModelSampling* patches and the untyped
// switches reaches the node that loads a model from a filename. Read that node's filename input,
// whatever it is called, and an upscale model stops being reachable BY CONSTRUCTION -- it is not on
// the model path -- rather than by a blacklist that would go stale the next time somebody publishes
// a loader. That is the whole fix: the old scan matched input NAMES anywhere in the graph, its set
// held `model_name` (an upscaler's input) and not `unet_name` (every Wan / Flux / Qwen diffusion
// loader's), and whichever node the prompt map happened to yield first decided the answer.
//
// Same shape as the three walks above: an explicit stack, a visited-set, reverse-pushed so LIFO
// gives the graph's own input order. An imported graph has overflowed the stack on a cycle here
// before.

// A MODEL-typed slot, by the name ComfyUI gives it. `model` is what 106 of the 112 direct links off
// a loader in the owner's library are called; the rest are untyped switch inputs, handled below. The
// two exclusions matter: `model_name` and `model_path` name a FILE, not a MODEL, which is exactly
// the confusion this file exists to end.
bool isModelSlotKey(const QString &key)
{
    const QString normalized = key.trimmed().toLower();
    if (normalized == QStringLiteral("unet") || normalized == QStringLiteral("diffusion_model"))
        return true;
    if (!normalized.startsWith(QStringLiteral("model")))
        return false;
    return !normalized.contains(QStringLiteral("name")) && !normalized.contains(QStringLiteral("path"));
}

// The first string input on this node that names a model file, in key order so the answer is
// deterministic. A UNETLoader carries `unet_name` beside `weight_dtype`; a CheckpointLoaderSimple
// carries `ckpt_name`; a UnetLoaderGGUF carries `unet_name` beside a device string. None of those
// companions read as an asset, so the name of the input never has to be known in advance.
QString modelFileInputOf(const QJsonObject &inputs)
{
    for (auto it = inputs.constBegin(); it != inputs.constEnd(); ++it)
    {
        if (!it.value().isString())
            continue;
        const QString value = it.value().toString().trimmed();
        if (isLikelyAssetValue(value))
            return value;
    }
    return {};
}

// Follow a MODEL link upstream to the node that loads it from a file.
//
// A node that has a model-typed link is a patch, a LoRA or a switch ON the way to the loader, never
// the loader itself -- LoraLoaderModelOnly carries a `lora_name` that looks exactly like a
// checkpoint, and stopping there would report the LoRA as the model. So: model slots first, always;
// only a node with none of them is allowed to answer with a filename; and a node with neither (a
// Reroute, an "Any Switch") passes its other links through, which is how the untyped passthroughs
// in the library are crossed without naming any of their classes.
QString loaderOnModelPath(const QJsonObject &prompt, const QString &startNodeId)
{
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

        const QJsonObject inputs = nodeInputsFor(prompt, nodeId);

        QStringList modelRefs;
        QStringList otherRefs;
        for (auto it = inputs.constBegin(); it != inputs.constEnd(); ++it)
        {
            const QString ref = nodeInputRefId(it.value());
            if (ref.trimmed().isEmpty())
                continue;
            if (isModelSlotKey(it.key()))
                modelRefs.push_back(ref);
            else
                otherRefs.push_back(ref);
        }

        if (!modelRefs.isEmpty())
        {
            for (int i = modelRefs.size() - 1; i >= 0; --i)
                pending.push_back(modelRefs.at(i));
            continue;
        }

        const QString file = modelFileInputOf(inputs);
        if (!file.isEmpty())
            return file;

        for (int i = otherRefs.size() - 1; i >= 0; --i)
            pending.push_back(otherRefs.at(i));
    }

    return {};
}

// Where every model walk in the graph starts: the `model` input of each sampler, and for the custom
// chain the guider's, because that is where SamplerCustomAdvanced keeps it. Key order, so a graph
// with two samplers answers the same way twice.
QStringList samplerModelRefs(const QJsonObject &prompt)
{
    QStringList refs;
    for (auto it = prompt.constBegin(); it != prompt.constEnd(); ++it)
    {
        const QJsonObject node = it.value().toObject();
        const QString classType = node.value(QStringLiteral("class_type")).toString().trimmed();
        const QJsonObject inputs = node.value(QStringLiteral("inputs")).toObject();

        QString ref;
        if (classType == QStringLiteral("KSampler")
            || classType == QStringLiteral("KSamplerAdvanced")
            || classType == QStringLiteral("SamplerCustom"))
        {
            ref = nodeInputRefId(inputs.value(QStringLiteral("model")));
        }
        else if (classType == QStringLiteral("SamplerCustomAdvanced"))
        {
            const QJsonObject guider =
                nodeInputsFor(prompt, nodeInputRefId(inputs.value(QStringLiteral("guider"))));
            ref = nodeInputRefId(guider.value(QStringLiteral("model")));
        }

        if (!ref.trimmed().isEmpty() && !refs.contains(ref))
            refs.push_back(ref);
    }
    return refs;
}

// Every node whose output is consumed through a MODEL-typed slot. This is the graph saying what a
// node IS without anyone reading its class name: a loader wired to `model` is on a model path even
// when no sampler this build knows sits at the end of it, and a loader wired to `upscale_model`,
// `vae`, `clip` or `control_net` is not, whatever its filename input happens to be called.
QSet<QString> nodesFeedingAModelSlot(const QJsonObject &prompt)
{
    QSet<QString> feeding;
    for (auto it = prompt.constBegin(); it != prompt.constEnd(); ++it)
    {
        const QJsonObject inputs = it.value().toObject().value(QStringLiteral("inputs")).toObject();
        for (auto input = inputs.constBegin(); input != inputs.constEnd(); ++input)
        {
            if (!isModelSlotKey(input.key()))
                continue;
            const QString ref = nodeInputRefId(input.value());
            if (!ref.trimmed().isEmpty())
                feeding.insert(ref);
        }
    }
    return feeding;
}

// What the graph loads as a diffusion model, in the order the graph reaches it, and by which tier.
// Both tiers are structural; there is no name-matching rung under them. The brief asked for one --
// the old scan, kept as a net so the 71 graphs that are right today could not regress -- and the
// measurement said no: over the 84 imported prompts that rung protects ZERO correct answers and
// fires on exactly four, every one of which is a graph whose compiled prompt lost its model links
// (a wanBlockSwap with empty inputs, UNETLoaders wired to nothing) and every one of which it
// answers with `RealESRGAN_x4plus.pth`. That is the original symptom, one tier lower. A net that
// only ever catches the thing it was built to stop is not a net.
struct ModelsFound
{
    QStringList files;
    // "walk" | "model-slot" | "" -- reported so the weaker tier is visible rather than silently
    // standing in for the strong one.
    QString tier;
};

ModelsFound modelsOnEveryModelPath(const QJsonObject &prompt)
{
    ModelsFound found;

    // Tier 1: from the samplers. This is the answer whenever the graph samples through a class this
    // build knows, which is 67 of the owner's 84 imported prompts.
    const QStringList starts = samplerModelRefs(prompt);
    for (const QString &start : starts)
    {
        const QString file = loaderOnModelPath(prompt, start);
        if (!file.isEmpty() && !found.files.contains(file))
            found.files.push_back(file);
    }
    if (!found.files.isEmpty())
    {
        found.tier = QStringLiteral("walk");
        return found;
    }

    const QSet<QString> viaModelSlot = nodesFeedingAModelSlot(prompt);

    // Tier 2: a graph whose sampler is a custom class -- Pro Grade v17 samples through an author's
    // own pipe node -- still wires its loader into somebody's `model` input. Start from every node
    // that feeds one.
    for (auto it = prompt.constBegin(); it != prompt.constEnd(); ++it)
    {
        if (!viaModelSlot.contains(it.key()))
            continue;
        const QString file = loaderOnModelPath(prompt, it.key());
        if (!file.isEmpty() && !found.files.contains(file))
            found.files.push_back(file);
    }
    if (!found.files.isEmpty())
        found.tier = QStringLiteral("model-slot");

    // Nothing else. A graph with no diffusion loader on any model path -- an upscale-only or
    // post-process graph, or one whose compiled prompt lost its model links -- reports NO
    // checkpoint and says so in `warnings`. Reaching for whatever filename is lying around is how a
    // 1x skin-detail upscaler came to fill the model row of a Krea graph.
    return found;
}

// One sentence shape for every field the graph did not yield, so the list reads as a list.
QString couldNotRead(const QString &field)
{
    return QStringLiteral("%1 could not be read from this workflow, so the page keeps its own.").arg(field);
}

// Who this draft is FOR -- the identity fields every draft carries whatever was or was not read out
// of a prompt. One author, so the unverified draft cannot come out a different shape from the
// verified one and have the cockpit notice.
QJsonObject identityDraft(const WorkflowDraftBuilder::Source &source)
{
    QJsonObject draft;
    draft.insert(QStringLiteral("source_name"), source.displayName);
    draft.insert(QStringLiteral("source_profile_path"), source.profilePath);
    draft.insert(QStringLiteral("source_workflow_path"), source.sourceWorkflowPath);
    draft.insert(QStringLiteral("compiled_prompt_path"), source.compiledPromptPath);
    draft.insert(QStringLiteral("mode_id"), WorkflowLaunchController::normalizeModeId(source.modeId));
    draft.insert(QStringLiteral("media_type"), source.mediaType);
    draft.insert(QStringLiteral("backend"), source.backend);
    return draft;
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
    {
        const QString graph = source.sourceWorkflowPath.trimmed();
        const bool namedIsTheSourceGraph = !graph.isEmpty()
            && QFileInfo(promptPath).absoluteFilePath() == QFileInfo(graph).absoluteFilePath();
        // A compile named it, or it IS the imported graph (an API prompt). Anything else is the
        // directory guess -- the file whose age nobody vouched for.
        if (source.compiledPromptVerified || namedIsTheSourceGraph)
            return promptPath;
    }

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

WorkflowDraftBuilder::Result WorkflowDraftBuilder::buildUnverified(const Source &source,
                                                                  const QString &reason)
{
    Result result;

    // Unchanged. A shape with no page to open on has nowhere to go whether or not ComfyUI answered.
    if (!isDraftableShape(source.modeId, source.mediaType))
    {
        result.reason = QStringLiteral(
            "Only image, text-to-video, and image-to-video workflows can currently open as editable drafts.");
        return result;
    }

    const QString warning = reason.trimmed().isEmpty()
        ? QStringLiteral("Nothing has verified this workflow against the live ComfyUI schema, so it "
                         "is opened for inspection and cannot be submitted.")
        : reason.trimmed();

    // The one file that may be read offline is the SOURCE GRAPH. Any other path -- above all the
    // prompt_api.json a caller may still be carrying on the record -- is dropped unread, because
    // nothing in an offline reply vouches for its age or for the converter that wrote it, and that
    // artefact reaching the cockpit is the defect this whole arc removed. Enforced HERE rather than
    // trusted of the caller: a builder that cannot be handed a stale artefact cannot read one.
    Source offline = source;
    const QString named = source.compiledPromptPath.trimmed();
    const QString graph = source.sourceWorkflowPath.trimmed();
    const bool namedIsTheSourceGraph =
        !named.isEmpty() && !graph.isEmpty()
        && QFileInfo(named).absoluteFilePath() == QFileInfo(graph).absoluteFilePath();
    offline.compiledPromptPath = namedIsTheSourceGraph ? graph : QString();

    const QString promptPath = resolvePromptPath(offline);
    if (!promptPath.isEmpty())
    {
        QFile file(promptPath);
        if (file.open(QIODevice::ReadOnly))
        {
            QJsonParseError parseError{};
            const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parseError);
            if (parseError.error == QJsonParseError::NoError && doc.isObject()
                && !doc.object().isEmpty())
            {
                Source resolved = offline;
                resolved.compiledPromptPath = promptPath;
                Result extracted = buildFromPrompt(doc.object(), resolved);
                if (extracted.present)
                {
                    // Submission is closed by CONSTRUCTION, on the draft the cockpit actually reads,
                    // not by a flag beside it. finalizeDraft treats this as a ceiling, so a readiness
                    // pass answering "ready" cannot reopen it.
                    extracted.safeToSubmit = false;
                    extracted.draft.insert(QStringLiteral("safe_to_submit"), false);

                    QJsonArray warnings;
                    warnings.append(warning);
                    for (const QJsonValue &value : extracted.draft.value(QStringLiteral("warnings")).toArray())
                        warnings.append(value);
                    extracted.draft.insert(QStringLiteral("warnings"), warnings);
                    extracted.reason = warning;
                    return extracted;
                }
            }
        }
    }

    // Nothing readable: a UI graph, which needs the live schema to become a prompt. It still opens,
    // with its identity and nothing else, because "we could not check" is not a reason to hide a
    // workflow the user just asked for.
    QJsonObject draft = identityDraft(offline);
    draft.insert(QStringLiteral("lora_stack"), QJsonArray());

    QJsonArray warnings;
    warnings.append(warning);
    warnings.append(QStringLiteral(
        "None of this workflow's settings could be read, because converting it needs the live "
        "ComfyUI schema. The page keeps its own values."));
    draft.insert(QStringLiteral("warnings"), warnings);
    draft.insert(QStringLiteral("safe_to_submit"), false);
    draft.insert(QStringLiteral("supports_apply"), true);

    result.present = true;
    result.safeToSubmit = false;
    result.reason = warning;
    result.draft = draft;
    return result;
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
    SamplingFacts facts;
    int frames = 0;
    int fps = 0;
    QString inputImage;

    for (auto it = prompt.constBegin(); it != prompt.constEnd(); ++it)
    {
        const QJsonObject node = it.value().toObject();
        const QString classType = node.value(QStringLiteral("class_type")).toString().trimmed();
        const QJsonObject inputs = node.value(QStringLiteral("inputs")).toObject();

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

        // Unchanged in behaviour: the same two classes, the same first-non-zero-steps-wins rule. What
        // changed is that a value the node does not literally carry now stays UNSET instead of
        // becoming 0 -- and that a graph with no KSampler at all is no longer the end of the road.
        if ((classType == QStringLiteral("KSampler") || classType == QStringLiteral("KSamplerAdvanced"))
            && facts.steps.value_or(0) <= 0)
        {
            facts.found = true;
            facts.sampler = resolveStringInput(prompt, inputs, QStringLiteral("sampler_name"));
            facts.scheduler = resolveStringInput(prompt, inputs, QStringLiteral("scheduler"));
            facts.steps.reset();
            facts.cfg.reset();
            facts.seed.reset();
            const auto resolvedSteps = resolveNumericInput(prompt, inputs, QStringLiteral("steps"));
            if (resolvedSteps)
                facts.steps = resolvedSteps->toVariant().toInt();
            const auto resolvedCfg = resolveNumericInput(prompt, inputs, QStringLiteral("cfg"));
            if (resolvedCfg)
                facts.cfg = resolvedCfg->toDouble();
            const auto resolvedSeed = resolveNumericInput(
                prompt,
                inputs,
                classType == QStringLiteral("KSampler") ? QStringLiteral("seed") : QStringLiteral("noise_seed"));
            if (resolvedSeed)
                facts.seed = resolvedSeed->toVariant().toLongLong();
            facts.positiveRef = nodeInputRefId(inputs.value(QStringLiteral("positive")));
            facts.negativeRef = nodeInputRefId(inputs.value(QStringLiteral("negative")));
            facts.latentRef = nodeInputRefId(inputs.value(QStringLiteral("latent_image")));
            facts.modelRef = nodeInputRefId(inputs.value(QStringLiteral("model")));
        }

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

    // No KSampler in the graph does not mean no sampling in the graph.
    if (!facts.found)
        facts = recoverFromCustomSampler(prompt);

    // The model comes off the MODEL PATH, not off an input name. Everything below is about which of
    // the models on that path the single `checkpoint` field shows, and about saying out loud what
    // the other ones are.
    const ModelsFound models = modelsOnEveryModelPath(prompt);

    // A Wan 2.2 graph carries two experts -- a high-noise first stage and a low-noise refiner -- and
    // each has its own sampler, so the walk reaches both. Which one lands in `checkpoint` must not
    // depend on the numeric node ids the converter happened to emit, so it is anchored on the HIGH
    // expert: it is the stage that runs first in the MoE handoff. Both halves are reported under the
    // names AssetCatalogScanner already uses for this pair (high_noise_path / low_noise_path,
    // stack_kind wan_dual_noise) rather than a second vocabulary for the same fact, and the pair is
    // detected by that file's own predicates so there is one detector, not two.
    QString wanHighNoise;
    QString wanLowNoise;
    for (const QString &file : models.files)
    {
        if (wanHighNoise.isEmpty() && assets::looksLikeWanHighNoisePath(file))
            wanHighNoise = file;
        if (wanLowNoise.isEmpty() && assets::looksLikeWanLowNoisePath(file))
            wanLowNoise = file;
    }
    const bool wanDualNoise = !wanHighNoise.isEmpty() && !wanLowNoise.isEmpty();

    if (wanDualNoise)
    {
        checkpointName = wanHighNoise;
    }
    else if (!models.files.isEmpty())
    {
        // Otherwise: the model the sampler THIS draft reports actually samples with, so the model
        // row and the sampling row describe the same pass. Falling back to the first on the path
        // covers the graphs whose sampler this build could not identify at all.
        const QString fromReportedSampler = loaderOnModelPath(prompt, facts.modelRef);
        checkpointName = models.files.contains(fromReportedSampler) ? fromReportedSampler
                                                                    : models.files.first();
    }

    if (models.files.isEmpty())
    {
        qWarning("workflow draft: no model path in this graph reaches a loader, so the model row is "
                 "left empty rather than filled from an unrelated filename");
    }

    std::optional<QString> positivePrompt;
    std::optional<QString> negativePrompt;
    if (facts.found)
    {
        bool reachedEncode = false;
        const QString positive = textFromClipEncode(prompt, facts.positiveRef, &reachedEncode);
        if (reachedEncode)
            positivePrompt = positive;

        if (facts.negativeSlotAbsent)
            negativePrompt = QString();
        else
        {
            reachedEncode = false;
            const QString negative = textFromClipEncode(prompt, facts.negativeRef, &reachedEncode);
            if (reachedEncode)
                negativePrompt = negative;
        }
    }

    const CanvasSize canvas = canvasFromLatent(prompt, facts.latentRef);

    QJsonObject draft = identityDraft(source);
    // A field the graph did not yield is ABSENT, not zero. A key carrying 0 / 0.0 / 100 reaches the
    // cockpit as a value the workflow asked for, and the page cannot tell it from one it did: that is
    // how a graph with no readable settings came up as "cfg 0.0" rather than as the page's own
    // default. Absent means the page keeps what it had, and the warnings below say which fields
    // those were. `checkpoint` stays unconditional because an empty one is already a stated
    // outcome here -- video graphs carry no standalone checkpoint and warn about it by name.
    if (positivePrompt)
        draft.insert(QStringLiteral("prompt"), *positivePrompt);
    if (negativePrompt)
        draft.insert(QStringLiteral("negative_prompt"), *negativePrompt);
    draft.insert(QStringLiteral("checkpoint"), checkpointName);
    draft.insert(QStringLiteral("checkpoint_display"), compactBaseName(checkpointName));
    if (wanDualNoise)
    {
        draft.insert(QStringLiteral("stack_kind"), QStringLiteral("wan_dual_noise"));
        draft.insert(QStringLiteral("high_noise_path"), wanHighNoise);
        draft.insert(QStringLiteral("low_noise_path"), wanLowNoise);
    }
    if (!facts.sampler.isEmpty())
        draft.insert(QStringLiteral("sampler"), facts.sampler);
    if (!facts.scheduler.isEmpty())
        draft.insert(QStringLiteral("scheduler"), facts.scheduler);
    if (facts.steps)
        draft.insert(QStringLiteral("steps"), *facts.steps);
    if (facts.cfg)
        draft.insert(QStringLiteral("cfg"), *facts.cfg);
    if (facts.seed)
        draft.insert(QStringLiteral("seed"), QString::number(*facts.seed));
    if (canvas.width)
        draft.insert(QStringLiteral("width"), *canvas.width);
    if (canvas.height)
        draft.insert(QStringLiteral("height"), *canvas.height);
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

    // Never silently drop the other half. A Wan 2.2 pair is named as a pair; anything else the model
    // path reached and this draft did not choose is listed, because a graph that loads two models
    // and shows one is a graph the user has to be told about.
    if (wanDualNoise)
    {
        draftWarnings.push_back(
            QStringLiteral("This workflow runs a Wan dual-noise expert pair: high noise %1, low noise %2. "
                           "The model row shows the high-noise expert.")
                .arg(compactBaseName(wanHighNoise), compactBaseName(wanLowNoise)));
    }
    else if (models.files.size() > 1)
    {
        QStringList others;
        for (const QString &file : models.files)
        {
            if (file != checkpointName)
                others.push_back(compactBaseName(file));
        }
        draftWarnings.push_back(
            QStringLiteral("This workflow loads %1 models. The model row shows %2; it also loads %3.")
                .arg(models.files.size())
                .arg(compactBaseName(checkpointName), others.join(QStringLiteral(", "))));
    }

    if (checkpointName.trimmed().isEmpty() && !isVideoMode(source.modeId, source.mediaType))
    {
        safeToSubmit = false;
        draftWarnings.push_back(QStringLiteral("No checkpoint could be inferred from the compiled prompt."));
    }
    else if (checkpointName.trimmed().isEmpty() && isVideoMode(source.modeId, source.mediaType))
    {
        draftWarnings.push_back(QStringLiteral("No standalone checkpoint was inferred. The video workflow may carry its own model stack through the compiled prompt."));
    }

    // Name every field that was not carried over, in the words a user would use for it. Silence here
    // is what made the empty draft read as a broken page rather than as a workflow whose settings
    // live somewhere this build cannot follow.
    if (!positivePrompt)
        draftWarnings.push_back(couldNotRead(QStringLiteral("The prompt text")));
    if (!negativePrompt)
        draftWarnings.push_back(couldNotRead(QStringLiteral("The negative prompt")));
    if (!facts.steps)
        draftWarnings.push_back(couldNotRead(QStringLiteral("The step count")));
    if (!facts.cfg && !facts.cfgSlotAbsent)
        draftWarnings.push_back(couldNotRead(QStringLiteral("The guidance scale (CFG)")));
    if (facts.sampler.isEmpty())
        draftWarnings.push_back(couldNotRead(QStringLiteral("The sampler")));
    if (facts.scheduler.isEmpty())
        draftWarnings.push_back(couldNotRead(QStringLiteral("The scheduler")));
    if (!facts.seed && !facts.seedDisabledByDesign)
        draftWarnings.push_back(couldNotRead(QStringLiteral("The seed")));
    if (!canvas.width || !canvas.height)
        draftWarnings.push_back(couldNotRead(QStringLiteral("The output size")));

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
