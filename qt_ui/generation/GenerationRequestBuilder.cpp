#include "GenerationRequestBuilder.h"

#include <QJsonArray>

namespace spellvision::generation
{

QString GenerationRequestBuilder::normalizeAutoValue(const QString &value)
{
    if (value.compare(QStringLiteral("auto"), Qt::CaseInsensitive) == 0)
        return QString();
    return value;
}

QJsonObject GenerationRequestBuilder::build(const GenerationRequestDraft &draft)
{
    QJsonObject payload;
    payload.insert(QStringLiteral("mode"), draft.mode);
    payload.insert(QStringLiteral("prompt"), draft.prompt);
    payload.insert(QStringLiteral("negative_prompt"), draft.negativePrompt);
    payload.insert(QStringLiteral("preset"), draft.preset);
    payload.insert(QStringLiteral("model"), draft.model);
    payload.insert(QStringLiteral("model_display"), draft.modelDisplay);
    payload.insert(QStringLiteral("model_family"), draft.modelFamily);
    payload.insert(QStringLiteral("model_modality"), draft.modelModality);
    payload.insert(QStringLiteral("model_role"), draft.modelRole);

    if (draft.isVideoMode && !draft.selectedVideoStack.isEmpty())
    {
        payload.insert(QStringLiteral("video_model_stack"), draft.selectedVideoStack);
        payload.insert(QStringLiteral("model_stack"), draft.selectedVideoStack);
        payload.insert(QStringLiteral("native_video_stack_kind"), draft.selectedVideoStack.value(QStringLiteral("stack_kind")).toString());
    }

    payload.insert(QStringLiteral("workflow_profile"), draft.workflowProfile);
    payload.insert(QStringLiteral("workflow_draft_source"), draft.workflowDraftSource);
    payload.insert(QStringLiteral("workflow_profile_path"), draft.workflowProfilePath);
    payload.insert(QStringLiteral("workflow_path"), draft.workflowPath);
    payload.insert(QStringLiteral("compiled_prompt_path"), draft.compiledPromptPath);
    payload.insert(QStringLiteral("workflow_backend"), draft.workflowBackend);
    payload.insert(QStringLiteral("workflow_media_type"), draft.workflowMediaType);

    QJsonArray loraArray;
    QString primaryLora;
    QString primaryLoraDisplay;
    double primaryLoraWeight = 1.0;
    for (const LoraRequestEntry &entry : draft.loras)
    {
        QJsonObject item;
        item.insert(QStringLiteral("name"), entry.value);
        item.insert(QStringLiteral("display"), entry.display);
        item.insert(QStringLiteral("strength"), entry.weight);
        item.insert(QStringLiteral("enabled"), entry.enabled);
        loraArray.append(item);

        if (primaryLora.isEmpty() && entry.enabled && !entry.value.trimmed().isEmpty())
        {
            primaryLora = entry.value.trimmed();
            primaryLoraDisplay = entry.display.trimmed();
            primaryLoraWeight = entry.weight;
        }
    }

    payload.insert(QStringLiteral("loras"), loraArray);
    payload.insert(QStringLiteral("lora_stack"), loraArray);
    payload.insert(QStringLiteral("lora"), primaryLora);
    payload.insert(QStringLiteral("lora_display"), primaryLoraDisplay);
    payload.insert(QStringLiteral("lora_summary"), primaryLora);
    payload.insert(QStringLiteral("lora_stack_summary"), draft.loraStackSummary);
    payload.insert(QStringLiteral("lora_scale"), primaryLoraWeight);

    if (draft.isVideoMode)
    {
        const QString videoSamplerValue = normalizeAutoValue(draft.videoSampler);
        const QString videoSchedulerValue = normalizeAutoValue(draft.videoScheduler);

        payload.insert(QStringLiteral("image_sampler"), draft.imageSampler);
        payload.insert(QStringLiteral("image_scheduler"), draft.imageScheduler);
        payload.insert(QStringLiteral("sampler"), videoSamplerValue);
        payload.insert(QStringLiteral("scheduler"), videoSchedulerValue);
        payload.insert(QStringLiteral("video_sampler"), videoSamplerValue);
        payload.insert(QStringLiteral("video_scheduler"), videoSchedulerValue);
        payload.insert(QStringLiteral("sampler_scope"), QStringLiteral("video"));
    }
    else
    {
        payload.insert(QStringLiteral("sampler"), draft.imageSampler);
        payload.insert(QStringLiteral("scheduler"), draft.imageScheduler);
        payload.insert(QStringLiteral("sampler_scope"), QStringLiteral("image"));
    }

    payload.insert(QStringLiteral("steps"), draft.steps);
    payload.insert(QStringLiteral("cfg_scale"), draft.cfg);
    payload.insert(QStringLiteral("cfg"), draft.cfg);
    payload.insert(QStringLiteral("seed"), draft.seed);
    payload.insert(QStringLiteral("width"), draft.width);
    payload.insert(QStringLiteral("height"), draft.height);

    if (draft.isVideoMode)
    {
        payload.insert(QStringLiteral("frames"), draft.frames);
        payload.insert(QStringLiteral("num_frames"), draft.frames);
        payload.insert(QStringLiteral("frame_count"), draft.frames);
        payload.insert(QStringLiteral("fps"), draft.fps);
        payload.insert(QStringLiteral("duration_seconds"), draft.fps > 0 ? static_cast<double>(draft.frames) / static_cast<double>(draft.fps) : 0.0);
        payload.insert(QStringLiteral("video_stack_mode"), draft.videoStackMode);
        payload.insert(QStringLiteral("wan_split"), draft.wanSplit);
        payload.insert(QStringLiteral("wan_split_mode"), draft.wanSplit);
        payload.insert(QStringLiteral("high_steps"), draft.highSteps);
        payload.insert(QStringLiteral("low_steps"), draft.lowSteps);
        payload.insert(QStringLiteral("split_step"), draft.splitStep);
        payload.insert(QStringLiteral("noise_split_step"), draft.splitStep);
        payload.insert(QStringLiteral("wan_noise_split_step"), draft.splitStep);
        payload.insert(QStringLiteral("high_noise_shift"), draft.highNoiseShift);
        payload.insert(QStringLiteral("low_noise_shift"), draft.lowNoiseShift);
        payload.insert(QStringLiteral("enable_vae_tiling"), draft.enableVaeTiling);
    }

    payload.insert(QStringLiteral("batch_count"), draft.batchCount);
    payload.insert(QStringLiteral("output_prefix"), draft.outputPrefix);
    payload.insert(QStringLiteral("output_folder"), draft.outputFolder);
    payload.insert(QStringLiteral("models_root"), draft.modelsRoot);

    if (draft.isImageInputMode)
    {
        payload.insert(QStringLiteral("input_image"), draft.inputImage);
        payload.insert(QStringLiteral("denoise_strength"), draft.denoiseStrength);
        payload.insert(QStringLiteral("strength"), draft.denoiseStrength);
    }

    return payload;
}

} // namespace spellvision::generation
