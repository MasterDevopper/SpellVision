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
    return key == QStringLiteral("wan") || key.startsWith(QStringLiteral("wan"));
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
    out.stackReady = isStackReady(draft) || out.hasWorkflowBinding;
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
    if (out.hasNativeVideoStack && !out.stackReady && !out.hasWorkflowBinding)
        out.warnings << QStringLiteral("Selected native video stack is partial or unresolved.");
    if (out.hasNativeVideoStack && !out.hasWorkflowBinding && !isValidatedNativeFamily(out.resolvedFamily))
        out.warnings << QStringLiteral("Only Wan native T2V is production-enabled in Sprint 15B Pass 1. Other video families are recognized but experimental until validated.");

    out.ready = out.warnings.isEmpty();

    const QString backend = out.hasWorkflowBinding
                                ? QStringLiteral("workflow")
                                : (out.hasNativeVideoStack ? QStringLiteral("native") : QStringLiteral("missing"));
    const QString input = out.requiresInputImage
                              ? (out.hasInputImage ? QStringLiteral("input ready") : QStringLiteral("input missing"))
                              : QStringLiteral("text only");
    const QString stack = out.stackReady ? QStringLiteral("stack ready") : QStringLiteral("stack unresolved");

    const QString family = out.resolvedFamily.isEmpty() ? QStringLiteral("unknown") : out.resolvedFamily;
    out.diagnosticSummary = QStringLiteral("%1 video • %2 • %3 • %4 • %5 • %6")
                                .arg(out.requestKind.toUpper(), backend, input, stack, family, out.durationLabel);

    return out;
}

} // namespace spellvision::generation
