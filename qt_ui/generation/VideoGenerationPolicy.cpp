#include "VideoGenerationPolicy.h"

#include <QFileInfo>
#include <QJsonArray>
#include <QJsonObject>

namespace spellvision::generation
{

bool VideoGenerationPolicy::requiresInputImageForMode(const QString &mode)
{
    const QString key = mode.trimmed().toLower();
    return key == QStringLiteral("i2v") ||
           key == QStringLiteral("image_to_video") ||
           key == QStringLiteral("imagetovideo");
}

QString VideoGenerationPolicy::formatDurationLabel(int frames, int fps)
{
    if (frames <= 0 || fps <= 0)
        return QStringLiteral("0.00s");

    const double seconds = static_cast<double>(frames) / static_cast<double>(fps);
    return QStringLiteral("%1s").arg(seconds, 0, 'f', 2);
}


QString VideoGenerationPolicy::resolvedVideoFamily(const GenerationRequestDraft &draft)
{
    // P1 #4: an explicit UI family pick (Wan/LTX) wins over model-derived resolution.
    // Empty or "auto" falls through to the derive-from-model path below (unchanged behavior).
    const QString familyOverride = draft.videoFamilyOverride.trimmed().toLower().replace(QStringLiteral("-"), QStringLiteral("_"));
    if (!familyOverride.isEmpty() && familyOverride != QStringLiteral("auto"))
        return familyOverride;

    const QString explicitFamily = draft.modelFamily.trimmed().toLower().replace(QStringLiteral("-"), QStringLiteral("_"));
    if (!explicitFamily.isEmpty())
        return explicitFamily;

    const QJsonObject stack = draft.selectedVideoStack;
    const QStringList familyKeys = {QStringLiteral("family"), QStringLiteral("model_family"), QStringLiteral("video_family")};
    for (const QString &key : familyKeys)
    {
        const QString value = stack.value(key).toString().trimmed().toLower().replace(QStringLiteral("-"), QStringLiteral("_"));
        if (!value.isEmpty())
            return value;
    }

    QString haystack = draft.model + QStringLiteral(" ") + draft.modelDisplay;
    for (auto it = stack.constBegin(); it != stack.constEnd(); ++it)
        haystack += QStringLiteral(" ") + it.value().toString();
    haystack = haystack.toLower();

    if (haystack.contains(QStringLiteral("wan")) || haystack.contains(QStringLiteral("wan2")))
        return QStringLiteral("wan");
    if (haystack.contains(QStringLiteral("ltx")) || haystack.contains(QStringLiteral("ltxv")))
        return QStringLiteral("ltx");
    if (haystack.contains(QStringLiteral("hunyuan")) || haystack.contains(QStringLiteral("hyvideo")))
        return QStringLiteral("hunyuan_video");
    if (haystack.contains(QStringLiteral("cogvideo")))
        return QStringLiteral("cogvideox");
    if (haystack.contains(QStringLiteral("mochi")))
        return QStringLiteral("mochi");

    return QStringLiteral("unknown");
}

bool VideoGenerationPolicy::isValidatedNativeFamily(const QString &family)
{
    const QString key = family.trimmed().toLower().replace(QStringLiteral("-"), QStringLiteral("_"));

    // Wan and (since the Step 3 native-LTX migration) LTX are production native
    // video families. LTX runs through the embedded native audio+video Comfy template
    // (ltx_av_native.json), mirroring Wan's native_comfy_template route.
    return key == QStringLiteral("wan") || key.startsWith(QStringLiteral("wan")) ||
           key == QStringLiteral("ltx") || key == QStringLiteral("ltx_video") ||
           key == QStringLiteral("ltxv") || key.startsWith(QStringLiteral("ltx_"));
}

bool VideoGenerationPolicy::isValidatedPromptApiFamily(const QString &family)
{
    Q_UNUSED(family);

    // Step 3 (native-LTX migration): LTX moved to the native validated family path
    // (isValidatedNativeFamily). No video family currently routes through the prompt-api
    // backend from the UI; the explicit ltx_prompt_api_gated_submission command remains a
    // worker-side fallback only.
    return false;
}

bool VideoGenerationPolicy::hasWorkflowBinding(const GenerationRequestDraft &draft)
{
    return !draft.workflowProfilePath.trimmed().isEmpty() ||
           !draft.workflowPath.trimmed().isEmpty() ||
           !draft.compiledPromptPath.trimmed().isEmpty();
}

bool VideoGenerationPolicy::hasNativeVideoStack(const GenerationRequestDraft &draft)
{
    return !draft.selectedVideoStack.isEmpty() ||
           !draft.videoStackMode.trimmed().isEmpty() ||
           !draft.model.trimmed().isEmpty();
}

bool VideoGenerationPolicy::isStackReady(const GenerationRequestDraft &draft)
{
    if (draft.selectedVideoStack.isEmpty())
        return false;

    if (draft.selectedVideoStack.contains(QStringLiteral("stack_ready")))
        return draft.selectedVideoStack.value(QStringLiteral("stack_ready")).toBool(false);

    const QString stackKind = draft.selectedVideoStack.value(QStringLiteral("stack_kind")).toString().trimmed();
    const QString primaryPath = draft.selectedVideoStack.value(QStringLiteral("primary_path")).toString().trimmed();
    const QString diffusersPath = draft.selectedVideoStack.value(QStringLiteral("diffusers_path")).toString().trimmed();
    const QString transformerPath = draft.selectedVideoStack.value(QStringLiteral("transformer_path")).toString().trimmed();
    const QString unetPath = draft.selectedVideoStack.value(QStringLiteral("unet_path")).toString().trimmed();

    if (stackKind == QStringLiteral("diffusers_folder"))
        return !diffusersPath.isEmpty() || !primaryPath.isEmpty();

    return !primaryPath.isEmpty() || !transformerPath.isEmpty() || !unetPath.isEmpty();
}

VideoGenerationPolicySnapshot VideoGenerationPolicy::evaluate(const GenerationRequestDraft &draft)
{
    VideoGenerationPolicySnapshot out;
    out.isVideoMode = draft.isVideoMode;
    out.requestKind = draft.mode.trimmed().toLower();
    out.isI2V = requiresInputImageForMode(out.requestKind);
    out.requiresInputImage = out.isI2V || draft.isImageInputMode;
    out.hasInputImage = !draft.inputImage.trimmed().isEmpty();
    out.hasWorkflowBinding = hasWorkflowBinding(draft);
    out.hasNativeVideoStack = hasNativeVideoStack(draft);
    out.resolvedFamily = resolvedVideoFamily(draft);
    out.validatedPromptApiFamily = isValidatedPromptApiFamily(out.resolvedFamily);
    out.usesPromptApiBackend = out.validatedPromptApiFamily && !out.hasWorkflowBinding;
    out.validatedVideoBackend = isValidatedNativeFamily(out.resolvedFamily) ||
                                out.validatedPromptApiFamily ||
                                out.hasWorkflowBinding;
    out.backendRoute = out.hasWorkflowBinding
                           ? QStringLiteral("workflow")
                           : (out.usesPromptApiBackend
                                  ? QStringLiteral("prompt_api")
                                  : (out.hasNativeVideoStack ? QStringLiteral("native") : QStringLiteral("missing")));
    out.validationStatus = isValidatedNativeFamily(out.resolvedFamily)
                               ? QStringLiteral("production_native")
                               : (out.validatedPromptApiFamily
                                      ? QStringLiteral("experimental_prompt_api")
                                      : QStringLiteral("unvalidated"));

    // A validated native family (Wan dual-noise, or LTX single-pass) is stack-ready
    // with just the selected model, even before the full per-part stack is resolved.
    out.stackReady = isStackReady(draft) ||
                     out.hasWorkflowBinding ||
                     (out.validatedVideoBackend && !draft.model.trimmed().isEmpty());
    out.dimensionsValid = draft.width > 0 && draft.height > 0;
    out.frameCountValid = draft.frames > 0;
    out.fpsValid = draft.fps > 0;
    out.durationLabel = formatDurationLabel(draft.frames, draft.fps);
    out.stackKind = draft.selectedVideoStack.value(QStringLiteral("stack_kind")).toString().trimmed();
    out.stackMode = draft.videoStackMode.trimmed();

    if (!out.isVideoMode)
    {
        out.ready = true;
        out.diagnosticSummary = QStringLiteral("not a video request");
        return out;
    }

    if (!out.dimensionsValid)
        out.warnings << QStringLiteral("Video dimensions must be greater than zero.");
    if (!out.frameCountValid)
        out.warnings << QStringLiteral("Frame count must be greater than zero.");
    if (!out.fpsValid)
        out.warnings << QStringLiteral("FPS must be greater than zero.");
    if (out.requiresInputImage && !out.hasInputImage)
        out.warnings << QStringLiteral("I2V requires an input image.");
    if (!out.hasWorkflowBinding && !out.hasNativeVideoStack)
        out.warnings << QStringLiteral("Choose a native video model stack or open an imported workflow draft.");
    if (out.hasNativeVideoStack && !out.stackReady && !out.hasWorkflowBinding && !out.validatedPromptApiFamily)
        out.warnings << QStringLiteral("Selected native video stack is partial or unresolved.");
    if (out.hasNativeVideoStack &&
        !out.hasWorkflowBinding &&
        !isValidatedNativeFamily(out.resolvedFamily) &&
        !out.validatedPromptApiFamily)
    {
        out.warnings << QStringLiteral("Only Wan and LTX native video are enabled. Other video families are recognized but experimental until validated.");
    }

    out.ready = out.warnings.isEmpty();

    const QString backend = out.backendRoute.trimmed().isEmpty()
                                ? (out.hasWorkflowBinding
                                       ? QStringLiteral("workflow")
                                       : (out.hasNativeVideoStack ? QStringLiteral("native") : QStringLiteral("missing")))
                                : out.backendRoute;
    const QString input = out.requiresInputImage
                              ? (out.hasInputImage ? QStringLiteral("input ready") : QStringLiteral("input missing"))
                              : QStringLiteral("text only");
    const QString stack = out.stackReady ? QStringLiteral("stack ready") : QStringLiteral("stack unresolved");

    const QString family = out.resolvedFamily.isEmpty() ? QStringLiteral("unknown") : out.resolvedFamily;
    out.diagnosticSummary = QStringLiteral("%1 video • %2 • %3 • %4 • %5 • %6 • %7")
                                .arg(out.requestKind.toUpper(),
                                     backend,
                                     input,
                                     stack,
                                     family,
                                     out.durationLabel,
                                     out.validationStatus);

    return out;
}

} // namespace spellvision::generation
