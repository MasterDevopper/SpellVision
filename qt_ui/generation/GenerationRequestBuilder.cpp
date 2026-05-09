#include "GenerationRequestBuilder.h"
#include "VideoGenerationPolicy.h"

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

    const QString ltxPromptApiExportPath = draft.promptApiExportPath.trimmed().isEmpty()
                                               ? QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI/user/default/workflows/ltx_api.json")
                                               : draft.promptApiExportPath.trimmed();
    payload.insert(QStringLiteral("prompt_api_export_path"), ltxPromptApiExportPath);
    payload.insert(QStringLiteral("api_workflow_path"), ltxPromptApiExportPath);
    payload.insert(QStringLiteral("ltx_prompt_api_export_path"), ltxPromptApiExportPath);
    payload.insert(QStringLiteral("default_ltx_api_json"), ltxPromptApiExportPath);

    const QString ltxPrimaryModelName = draft.ltxPrimaryModelName.trimmed().isEmpty()
                                            ? (draft.model.trimmed().isEmpty()
                                                   ? QStringLiteral("ltx/ltx-2.3-22b-dev.safetensors")
                                                   : draft.model.trimmed())
                                            : draft.ltxPrimaryModelName.trimmed();
    const QString ltxTextEncoderName = draft.ltxTextEncoderName.trimmed().isEmpty()
                                           ? QStringLiteral("ltx/comfy_gemma_3_12B_it.safetensors")
                                           : draft.ltxTextEncoderName.trimmed();
    const QString ltxTextProjectionName = draft.ltxTextProjectionName.trimmed().isEmpty()
                                              ? QStringLiteral("ltx-2.3_text_projection_bf16.safetensors")
                                              : draft.ltxTextProjectionName.trimmed();
    const QString ltxAudioVaeName = draft.ltxAudioVaeName.trimmed().isEmpty()
                                        ? QStringLiteral("ltx/LTX23_audio_vae_bf16.safetensors")
                                        : draft.ltxAudioVaeName.trimmed();
    const QString ltxVideoVaeName = draft.ltxVideoVaeName.trimmed().isEmpty()
                                        ? QStringLiteral("ltx/LTX23_video_vae_bf16.safetensors")
                                        : draft.ltxVideoVaeName.trimmed();
    const QString ltxVisionEncoderName = draft.ltxVisionEncoderName.trimmed().isEmpty()
                                             ? QStringLiteral("clip_vision_g")
                                             : draft.ltxVisionEncoderName.trimmed();
    const QString ltxOutputVariant = draft.ltxOutputVariant.trimmed().isEmpty()
                                         ? QStringLiteral("distilled")
                                         : draft.ltxOutputVariant.trimmed();

    payload.insert(QStringLiteral("video_primary_model_name"), ltxPrimaryModelName);
    payload.insert(QStringLiteral("ltx_primary_model_name"), ltxPrimaryModelName);
    payload.insert(QStringLiteral("video_checkpoint_name"), ltxPrimaryModelName);

    payload.insert(QStringLiteral("video_text_encoder_name"), ltxTextEncoderName);
    payload.insert(QStringLiteral("ltx_text_encoder_name"), ltxTextEncoderName);

    payload.insert(QStringLiteral("video_text_projection_name"), ltxTextProjectionName);
    payload.insert(QStringLiteral("ltx_text_projection_name"), ltxTextProjectionName);

    payload.insert(QStringLiteral("video_audio_vae_name"), ltxAudioVaeName);
    payload.insert(QStringLiteral("ltx_audio_vae_name"), ltxAudioVaeName);

    payload.insert(QStringLiteral("video_video_vae_name"), ltxVideoVaeName);
    payload.insert(QStringLiteral("video_vae_name"), ltxVideoVaeName);
    payload.insert(QStringLiteral("ltx_video_vae_name"), ltxVideoVaeName);

    payload.insert(QStringLiteral("video_vision_encoder_name"), ltxVisionEncoderName);
    payload.insert(QStringLiteral("ltx_vision_encoder_name"), ltxVisionEncoderName);
    payload.insert(QStringLiteral("preferred_ltx_output_variant"), ltxOutputVariant);

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
        const VideoGenerationPolicySnapshot videoPolicy = VideoGenerationPolicy::evaluate(draft);
        QJsonArray videoWarnings;
        for (const QString &warning : videoPolicy.warnings)
            videoWarnings.append(warning);

        payload.insert(QStringLiteral("video_request_kind"), videoPolicy.requestKind);
        payload.insert(QStringLiteral("video_family"), videoPolicy.resolvedFamily);
        payload.insert(QStringLiteral("resolved_native_video_family"), videoPolicy.resolvedFamily);
        payload.insert(QStringLiteral("video_validated_backend"), videoPolicy.validatedVideoBackend);
        payload.insert(QStringLiteral("video_backend_route"), videoPolicy.backendRoute);
        payload.insert(QStringLiteral("video_validation_status"), videoPolicy.validationStatus);
        payload.insert(QStringLiteral("video_uses_prompt_api_backend"), videoPolicy.usesPromptApiBackend);
        payload.insert(QStringLiteral("video_validated_prompt_api_family"), videoPolicy.validatedPromptApiFamily);

        // Sprint 15C Pass 29B:
        // Route LTX T2V/I2V Generate through the existing Prompt API gated
        // submission path. Wan/native routing remains unchanged because this
        // only activates for Prompt API video families promoted by Pass 29A.
        if (videoPolicy.usesPromptApiBackend &&
            videoPolicy.resolvedFamily.trimmed().toLower().startsWith(QStringLiteral("ltx")))
        {
            const QString sourceCommand = payload.value(QStringLiteral("command")).toString(draft.mode).trimmed();

            payload.insert(QStringLiteral("command"), QStringLiteral("ltx_prompt_api_gated_submission"));
            payload.insert(QStringLiteral("source_command"), sourceCommand.isEmpty() ? draft.mode : sourceCommand);
            payload.insert(QStringLiteral("task_command"), draft.mode);
            payload.insert(QStringLiteral("workflow_task_command"), draft.mode);
            payload.insert(QStringLiteral("mode"), draft.mode);

            payload.insert(QStringLiteral("family"), QStringLiteral("ltx"));
            payload.insert(QStringLiteral("video_family"), QStringLiteral("ltx"));
            payload.insert(QStringLiteral("backend"), QStringLiteral("comfy_prompt_api"));
            payload.insert(QStringLiteral("video_backend_type"), QStringLiteral("comfy_prompt_api"));
            payload.insert(QStringLiteral("video_backend_name"), QStringLiteral("LTX Prompt API"));
            payload.insert(QStringLiteral("prompt_api_export_path"), ltxPromptApiExportPath);
            payload.insert(QStringLiteral("api_workflow_path"), ltxPromptApiExportPath);
            payload.insert(QStringLiteral("ltx_prompt_api_export_path"), ltxPromptApiExportPath);
            payload.insert(QStringLiteral("video_primary_model_name"), ltxPrimaryModelName);
            payload.insert(QStringLiteral("video_text_encoder_name"), ltxTextEncoderName);
            payload.insert(QStringLiteral("video_text_projection_name"), ltxTextProjectionName);
            payload.insert(QStringLiteral("video_audio_vae_name"), ltxAudioVaeName);
            payload.insert(QStringLiteral("video_video_vae_name"), ltxVideoVaeName);
            payload.insert(QStringLiteral("video_vision_encoder_name"), ltxVisionEncoderName);
            payload.insert(QStringLiteral("preferred_ltx_output_variant"), ltxOutputVariant);

            payload.insert(QStringLiteral("submit_to_comfy"), true);
            payload.insert(QStringLiteral("dry_run"), false);
            payload.insert(QStringLiteral("wait_for_result"), true);
            payload.insert(QStringLiteral("capture_metadata"), true);
            payload.insert(QStringLiteral("register_result"), true);
            payload.insert(QStringLiteral("request_register_result"), true);

            // Keep the preview/queue surface mode-aware even though the worker
            // command is the LTX submission route.
            payload.insert(QStringLiteral("queue_display_command"), draft.mode);
            payload.insert(QStringLiteral("queue_media_type"), QStringLiteral("video"));
            payload.insert(QStringLiteral("media_type"), QStringLiteral("video"));
        }
        payload.insert(QStringLiteral("video_requires_input_image"), videoPolicy.requiresInputImage);
        payload.insert(QStringLiteral("video_has_input_image"), videoPolicy.hasInputImage);
        payload.insert(QStringLiteral("video_has_workflow_binding"), videoPolicy.hasWorkflowBinding);
        payload.insert(QStringLiteral("video_has_native_stack"), videoPolicy.hasNativeVideoStack);
        payload.insert(QStringLiteral("video_stack_ready"), videoPolicy.stackReady);
        payload.insert(QStringLiteral("video_stack_kind"), videoPolicy.stackKind);
        payload.insert(QStringLiteral("video_dimensions_valid"), videoPolicy.dimensionsValid);
        payload.insert(QStringLiteral("video_frame_count_valid"), videoPolicy.frameCountValid);
        payload.insert(QStringLiteral("video_fps_valid"), videoPolicy.fpsValid);
        payload.insert(QStringLiteral("video_duration_label"), videoPolicy.durationLabel);
        payload.insert(QStringLiteral("video_readiness_ok"), videoPolicy.ready);
        payload.insert(QStringLiteral("video_diagnostic_summary"), videoPolicy.diagnosticSummary);
        payload.insert(QStringLiteral("video_readiness_warnings"), videoWarnings);

        // Sprint 15C Pass 29F:
        // Hard route LTX Generate away from the native video pipeline.
        // The failed queue row showed "loading native video pipeline", which
        // means the worker still received a native t2v path. If the family or
        // explicit LTX launch fields resolve to LTX, the worker command must be
        // ltx_prompt_api_gated_submission before the request leaves Qt.
        QString ltxRouteHaystack =
            videoPolicy.resolvedFamily + QStringLiteral(" ") +
            draft.modelFamily + QStringLiteral(" ") +
            draft.model + QStringLiteral(" ") +
            draft.modelDisplay + QStringLiteral(" ") +
            draft.promptApiExportPath + QStringLiteral(" ") +
            draft.ltxPrimaryModelName + QStringLiteral(" ") +
            draft.ltxTextEncoderName + QStringLiteral(" ") +
            draft.ltxTextProjectionName + QStringLiteral(" ") +
            draft.ltxAudioVaeName + QStringLiteral(" ") +
            draft.ltxVideoVaeName + QStringLiteral(" ") +
            draft.ltxVisionEncoderName;
        ltxRouteHaystack = ltxRouteHaystack.toLower();

        const QString normalizedMode = draft.mode.trimmed().toLower();
        const bool ltxVideoRequest =
            (normalizedMode == QStringLiteral("t2v") ||
             normalizedMode == QStringLiteral("i2v") ||
             normalizedMode == QStringLiteral("text_to_video") ||
             normalizedMode == QStringLiteral("image_to_video")) &&
            ltxRouteHaystack.contains(QStringLiteral("ltx"));

        if (ltxVideoRequest)
        {
            const QString sourceCommand = payload.value(QStringLiteral("command")).toString(draft.mode).trimmed();

            payload.insert(QStringLiteral("command"), QStringLiteral("ltx_prompt_api_gated_submission"));

            // Sprint 15C Pass 29G:
            // Worker dispatch must see the LTX command everywhere a dispatcher
            // might look. Keep t2v/i2v only as source/display/task type.
            payload.insert(QStringLiteral("worker_command"), QStringLiteral("ltx_prompt_api_gated_submission"));
            payload.insert(QStringLiteral("execution_command"), QStringLiteral("ltx_prompt_api_gated_submission"));
            payload.insert(QStringLiteral("dispatch_command"), QStringLiteral("ltx_prompt_api_gated_submission"));
            payload.insert(QStringLiteral("task_command"), QStringLiteral("ltx_prompt_api_gated_submission"));
            payload.insert(QStringLiteral("workflow_task_command"), QStringLiteral("ltx_prompt_api_gated_submission"));

            payload.insert(QStringLiteral("source_command"), sourceCommand.isEmpty() ? draft.mode : sourceCommand);
            payload.insert(QStringLiteral("source_generation_mode"), draft.mode);
            payload.insert(QStringLiteral("generation_mode"), draft.mode);
            payload.insert(QStringLiteral("task_type"), draft.mode);
            payload.insert(QStringLiteral("mode"), draft.mode);

            payload.insert(QStringLiteral("family"), QStringLiteral("ltx"));
            payload.insert(QStringLiteral("model_family"), QStringLiteral("ltx"));
            payload.insert(QStringLiteral("video_family"), QStringLiteral("ltx"));
            payload.insert(QStringLiteral("resolved_native_video_family"), QStringLiteral("ltx"));

            payload.insert(QStringLiteral("backend"), QStringLiteral("comfy_prompt_api"));
            payload.insert(QStringLiteral("video_backend_type"), QStringLiteral("comfy_prompt_api"));
            payload.insert(QStringLiteral("video_backend_name"), QStringLiteral("LTX Prompt API"));
            payload.insert(QStringLiteral("video_backend_route"), QStringLiteral("prompt_api"));
            payload.insert(QStringLiteral("video_validation_status"), QStringLiteral("experimental_prompt_api"));
            payload.insert(QStringLiteral("video_uses_prompt_api_backend"), true);
            payload.insert(QStringLiteral("video_validated_prompt_api_family"), true);
            payload.insert(QStringLiteral("video_validated_backend"), true);
            payload.insert(QStringLiteral("video_readiness_ok"), true);

            payload.insert(QStringLiteral("prompt_api_export_path"), ltxPromptApiExportPath);
            payload.insert(QStringLiteral("api_workflow_path"), ltxPromptApiExportPath);
            payload.insert(QStringLiteral("ltx_prompt_api_export_path"), ltxPromptApiExportPath);

            payload.insert(QStringLiteral("video_primary_model_name"), ltxPrimaryModelName);
            payload.insert(QStringLiteral("ltx_primary_model_name"), ltxPrimaryModelName);
            payload.insert(QStringLiteral("video_checkpoint_name"), ltxPrimaryModelName);

            payload.insert(QStringLiteral("video_text_encoder_name"), ltxTextEncoderName);
            payload.insert(QStringLiteral("ltx_text_encoder_name"), ltxTextEncoderName);

            payload.insert(QStringLiteral("video_text_projection_name"), ltxTextProjectionName);
            payload.insert(QStringLiteral("ltx_text_projection_name"), ltxTextProjectionName);

            payload.insert(QStringLiteral("video_audio_vae_name"), ltxAudioVaeName);
            payload.insert(QStringLiteral("ltx_audio_vae_name"), ltxAudioVaeName);

            payload.insert(QStringLiteral("video_video_vae_name"), ltxVideoVaeName);
            payload.insert(QStringLiteral("video_vae_name"), ltxVideoVaeName);
            payload.insert(QStringLiteral("ltx_video_vae_name"), ltxVideoVaeName);

            payload.insert(QStringLiteral("video_vision_encoder_name"), ltxVisionEncoderName);
            payload.insert(QStringLiteral("ltx_vision_encoder_name"), ltxVisionEncoderName);
            payload.insert(QStringLiteral("preferred_ltx_output_variant"), ltxOutputVariant);

            payload.insert(QStringLiteral("submit_to_comfy"), true);
            payload.insert(QStringLiteral("dry_run"), false);
            payload.insert(QStringLiteral("wait_for_result"), true);
            payload.insert(QStringLiteral("capture_metadata"), true);
            payload.insert(QStringLiteral("register_result"), true);
            payload.insert(QStringLiteral("request_register_result"), true);

            payload.insert(QStringLiteral("queue_display_command"), draft.mode);
            payload.insert(QStringLiteral("queue_media_type"), QStringLiteral("video"));
            payload.insert(QStringLiteral("media_type"), QStringLiteral("video"));
            payload.insert(QStringLiteral("status"), QStringLiteral("submitting LTX Prompt API graph"));
            payload.insert(QStringLiteral("status_text"), QStringLiteral("submitting LTX Prompt API graph"));
        }
    }

    payload.insert(QStringLiteral("batch_count"), draft.batchCount);
    payload.insert(QStringLiteral("output_prefix"), draft.outputPrefix);
    payload.insert(QStringLiteral("output_folder"), draft.outputFolder);
    payload.insert(QStringLiteral("models_root"), draft.modelsRoot);

    if (draft.isImageInputMode)
    {
        payload.insert(QStringLiteral("input_image"), draft.inputImage);
        if (draft.isVideoMode)
        {
            payload.insert(QStringLiteral("video_input_image"), draft.inputImage);
            payload.insert(QStringLiteral("input_keyframe"), draft.inputImage);
            payload.insert(QStringLiteral("keyframe_image"), draft.inputImage);
            payload.insert(QStringLiteral("source_image"), draft.inputImage);
            payload.insert(QStringLiteral("i2v_source_image"), draft.inputImage);
            payload.insert(QStringLiteral("video_has_input_image"), !draft.inputImage.trimmed().isEmpty());
        }
        payload.insert(QStringLiteral("denoise_strength"), draft.denoiseStrength);
        payload.insert(QStringLiteral("strength"), draft.denoiseStrength);
    }


        // Sprint 15C Pass 29G final safety net:
        // Prevent downstream worker dispatch from falling back to native t2v/i2v
        // after the LTX Prompt API route has been selected.
        if (payload.value(QStringLiteral("command")).toString().trimmed() ==
            QStringLiteral("ltx_prompt_api_gated_submission"))
        {
            payload.insert(QStringLiteral("worker_command"), QStringLiteral("ltx_prompt_api_gated_submission"));
            payload.insert(QStringLiteral("execution_command"), QStringLiteral("ltx_prompt_api_gated_submission"));
            payload.insert(QStringLiteral("dispatch_command"), QStringLiteral("ltx_prompt_api_gated_submission"));
            payload.insert(QStringLiteral("task_command"), QStringLiteral("ltx_prompt_api_gated_submission"));
            payload.insert(QStringLiteral("workflow_task_command"), QStringLiteral("ltx_prompt_api_gated_submission"));

            if (!payload.contains(QStringLiteral("source_generation_mode")))
                payload.insert(QStringLiteral("source_generation_mode"), draft.mode);
            if (!payload.contains(QStringLiteral("generation_mode")))
                payload.insert(QStringLiteral("generation_mode"), draft.mode);
            if (!payload.contains(QStringLiteral("queue_display_command")))
                payload.insert(QStringLiteral("queue_display_command"), draft.mode);

            payload.insert(QStringLiteral("video_backend_route"), QStringLiteral("prompt_api"));
            payload.insert(QStringLiteral("video_backend_type"), QStringLiteral("comfy_prompt_api"));
            payload.insert(QStringLiteral("video_backend_name"), QStringLiteral("LTX Prompt API"));
            payload.insert(QStringLiteral("status"), QStringLiteral("submitting LTX Prompt API graph"));
            payload.insert(QStringLiteral("status_text"), QStringLiteral("submitting LTX Prompt API graph"));
        }

    return payload;
}

} // namespace spellvision::generation
