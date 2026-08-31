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

    // Step 3 (A5 scoping): only LTX video requests carry LTX default fields. Wan/T2I
    // requests no longer get LTX export-path / asset-name defaults injected. The worker
    // now routes by resolved_native_video_family, so this is clean-up, not a correctness fix.
    const QString resolvedFamilyForFields =
        VideoGenerationPolicy::resolvedVideoFamily(draft).trimmed().toLower();
    const bool isLtxRequest = draft.isVideoMode &&
                              resolvedFamilyForFields.startsWith(QStringLiteral("ltx"));

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

    QString ltxPreferredOutputRole = ltxOutputVariant.trimmed().toLower();
    ltxPreferredOutputRole.replace(QStringLiteral("-"), QStringLiteral("_"));
    ltxPreferredOutputRole.replace(QStringLiteral(" "), QStringLiteral("_"));

    if (ltxPreferredOutputRole == QStringLiteral("d") ||
        ltxPreferredOutputRole == QStringLiteral("output_d") ||
        ltxPreferredOutputRole == QStringLiteral("ltx_distilled") ||
        ltxPreferredOutputRole == QStringLiteral("distilled_output"))
    {
        ltxPreferredOutputRole = QStringLiteral("distilled");
    }
    else if (ltxPreferredOutputRole == QStringLiteral("f") ||
             ltxPreferredOutputRole == QStringLiteral("output_f") ||
             ltxPreferredOutputRole == QStringLiteral("ltx_full") ||
             ltxPreferredOutputRole == QStringLiteral("full_output"))
    {
        ltxPreferredOutputRole = QStringLiteral("full");
    }
    else if (ltxPreferredOutputRole != QStringLiteral("distilled") &&
             ltxPreferredOutputRole != QStringLiteral("full"))
    {
        ltxPreferredOutputRole = QStringLiteral("full");
    }

    if (isLtxRequest)
    {
        payload.insert(QStringLiteral("video_primary_model_name"), ltxPrimaryModelName);
        payload.insert(QStringLiteral("ltx_primary_model_name"), ltxPrimaryModelName);
        payload.insert(QStringLiteral("video_checkpoint_name"), ltxPrimaryModelName);

        payload.insert(QStringLiteral("video_text_encoder_name"), ltxTextEncoderName);
        payload.insert(QStringLiteral("ltx_text_encoder_name"), ltxTextEncoderName);

        payload.insert(QStringLiteral("video_text_projection_name"), ltxTextProjectionName);
        payload.insert(QStringLiteral("ltx_text_projection_name"), ltxTextProjectionName);

        // Preferred LTX output aliases (distilled/full).
        payload.insert(QStringLiteral("ltx_output_variant"), ltxPreferredOutputRole);
        payload.insert(QStringLiteral("ltx_preferred_output"), ltxPreferredOutputRole);
        payload.insert(QStringLiteral("video_preferred_output"), ltxPreferredOutputRole);
        payload.insert(QStringLiteral("video_output_preference"), ltxPreferredOutputRole);
        payload.insert(QStringLiteral("primary_output_role"), ltxPreferredOutputRole);

        payload.insert(QStringLiteral("video_audio_vae_name"), ltxAudioVaeName);
        payload.insert(QStringLiteral("ltx_audio_vae_name"), ltxAudioVaeName);

        payload.insert(QStringLiteral("video_video_vae_name"), ltxVideoVaeName);
        payload.insert(QStringLiteral("video_vae_name"), ltxVideoVaeName);
        payload.insert(QStringLiteral("ltx_video_vae_name"), ltxVideoVaeName);

        payload.insert(QStringLiteral("video_vision_encoder_name"), ltxVisionEncoderName);
        payload.insert(QStringLiteral("ltx_vision_encoder_name"), ltxVisionEncoderName);
        payload.insert(QStringLiteral("preferred_ltx_output_variant"), ltxOutputVariant);
    }

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
        payload.insert(QStringLiteral("video_uses_remote_api_backend"), videoPolicy.usesRemoteApiBackend);
        payload.insert(QStringLiteral("video_validated_prompt_api_family"), videoPolicy.validatedPromptApiFamily);
        payload.insert(QStringLiteral("video_validated_remote_api_family"), videoPolicy.validatedRemoteApiFamily);

        // Native-LTX migration (Step 4): the LTX -> prompt-api soft-route command
        // injection that lived here was removed. LTX t2v/i2v keeps its native command
        // and flows to the worker native path + gate, exactly like Wan. The policy
        // metadata above (video_backend_route etc.) is descriptive only; routing is
        // decided worker-side by resolved_native_video_family.
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

        // Native-LTX migration (Step 4): the LTX hard-route block (mode==t2v/i2v &&
        // "ltx"-in-haystack -> stamp command=ltx_prompt_api_gated_submission everywhere)
        // was removed. That substring haystack also matched Wan via the unconditional
        // LTX field defaults, so it was the entanglement root. LTX now keeps its native
        // command; the worker routes by resolved_native_video_family and blocks LTX at
        // the gate until its contract is production.
    }

    payload.insert(QStringLiteral("batch_count"), draft.batchCount);
        payload.insert(QStringLiteral("output_prefix"), draft.outputPrefix);
        payload.insert(QStringLiteral("output_folder"), draft.outputFolder);
        payload.insert(QStringLiteral("models_root"), draft.modelsRoot);

        // Embeddings (TI) — names only; UI also injects tokens into the prompt text for A1111-style paths.
        {
            QJsonArray posEmb;
            for (const QString &e : draft.positiveEmbeddings) {
                if (!e.trimmed().isEmpty())
                    posEmb.append(e.trimmed());
            }
            QJsonArray negEmb;
            for (const QString &e : draft.negativeEmbeddings) {
                if (!e.trimmed().isEmpty())
                    negEmb.append(e.trimmed());
            }
            if (!posEmb.isEmpty())
                payload.insert(QStringLiteral("positive_embeddings"), posEmb);
            if (!negEmb.isEmpty())
                payload.insert(QStringLiteral("negative_embeddings"), negEmb);
        }

        // Upscale
        payload.insert(QStringLiteral("upscale_enabled"), draft.upscaleEnabled);
        payload.insert(QStringLiteral("upscale_method"), draft.upscaleMethod);
        payload.insert(QStringLiteral("upscale_scale"), draft.upscaleScale);
        if (!draft.upscaleModel.trimmed().isEmpty())
            payload.insert(QStringLiteral("upscale_model_name"), draft.upscaleModel.trimmed());

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

    // Native-LTX migration (Step 4): the Pass-29G "final safety net" that re-stamped
    // ltx_prompt_api_gated_submission across every *_command field was removed with the
    // soft/hard routes above. Fresh LTX video keeps its native command end-to-end.

    return payload;
}

} // namespace spellvision::generation
