from pathlib import Path

builder_h_path = Path("qt_ui/generation/GenerationRequestBuilder.h")
builder_cpp_path = Path("qt_ui/generation/GenerationRequestBuilder.cpp")
submission_policy_path = Path("qt_ui/workers/WorkerSubmissionPolicy.cpp")
doc_path = Path("docs/sprints/SPRINT15C_PASS29F_HARD_ROUTE_LTX_PROMPT_API_README.md")
script_path = Path("scripts/refactors/apply_sprint15c_pass29f_hard_route_ltx_prompt_api.py")

builder_h = builder_h_path.read_text(encoding="utf-8")
builder_cpp = builder_cpp_path.read_text(encoding="utf-8")
submission_policy = submission_policy_path.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# 1) Make sure GenerationRequestDraft has the LTX fields even if an earlier
#    local patch was partially applied.
# ----------------------------------------------------------------------

if "QString promptApiExportPath;" not in builder_h:
    marker = """    QString workflowBackend;
    QString workflowMediaType;

    QVector<LoraRequestEntry> loras;"""
    replacement = """    QString workflowBackend;
    QString workflowMediaType;
    QString promptApiExportPath;

    QVector<LoraRequestEntry> loras;"""
    if marker not in builder_h:
        raise SystemExit("Could not find workflow metadata marker in GenerationRequestBuilder.h.")
    builder_h = builder_h.replace(marker, replacement, 1)

if "QString ltxPrimaryModelName;" not in builder_h:
    marker = """    QString promptApiExportPath;

    QVector<LoraRequestEntry> loras;"""
    replacement = """    QString promptApiExportPath;

    QString ltxPrimaryModelName;
    QString ltxTextEncoderName;
    QString ltxTextProjectionName;
    QString ltxAudioVaeName;
    QString ltxVideoVaeName;
    QString ltxVisionEncoderName;
    QString ltxOutputVariant;

    QVector<LoraRequestEntry> loras;"""
    if marker not in builder_h:
        raise SystemExit("Could not find promptApiExportPath marker in GenerationRequestBuilder.h.")
    builder_h = builder_h.replace(marker, replacement, 1)

builder_h_path.write_text(builder_h, encoding="utf-8")


# ----------------------------------------------------------------------
# 2) Ensure builder has LTX prompt API path/component locals.
# ----------------------------------------------------------------------

workflow_marker = """    payload.insert(QStringLiteral("workflow_backend"), draft.workflowBackend);
    payload.insert(QStringLiteral("workflow_media_type"), draft.workflowMediaType);"""

workflow_replacement = """    payload.insert(QStringLiteral("workflow_backend"), draft.workflowBackend);
    payload.insert(QStringLiteral("workflow_media_type"), draft.workflowMediaType);

    const QString ltxPromptApiExportPath = draft.promptApiExportPath.trimmed().isEmpty()
                                               ? QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI/user/default/workflows/ltx_api.json")
                                               : draft.promptApiExportPath.trimmed();
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

    payload.insert(QStringLiteral("prompt_api_export_path"), ltxPromptApiExportPath);
    payload.insert(QStringLiteral("api_workflow_path"), ltxPromptApiExportPath);
    payload.insert(QStringLiteral("ltx_prompt_api_export_path"), ltxPromptApiExportPath);
    payload.insert(QStringLiteral("default_ltx_api_json"), ltxPromptApiExportPath);

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
    payload.insert(QStringLiteral("preferred_ltx_output_variant"), ltxOutputVariant);"""

if "const QString ltxPromptApiExportPath" not in builder_cpp:
    if workflow_marker not in builder_cpp:
        raise SystemExit("Could not find workflow metadata insert marker in GenerationRequestBuilder.cpp.")
    builder_cpp = builder_cpp.replace(workflow_marker, workflow_replacement, 1)


# ----------------------------------------------------------------------
# 3) Hard-force LTX Prompt API route inside video payloads.
# ----------------------------------------------------------------------

route_marker = """        payload.insert(QStringLiteral("video_readiness_warnings"), videoWarnings);"""

route_insert = """        payload.insert(QStringLiteral("video_readiness_warnings"), videoWarnings);

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
            payload.insert(QStringLiteral("source_command"), sourceCommand.isEmpty() ? draft.mode : sourceCommand);
            payload.insert(QStringLiteral("task_command"), draft.mode);
            payload.insert(QStringLiteral("workflow_task_command"), draft.mode);
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
        }"""

if "Sprint 15C Pass 29F:" not in builder_cpp:
    if route_marker not in builder_cpp:
        raise SystemExit("Could not find video_readiness_warnings marker in GenerationRequestBuilder.cpp.")
    builder_cpp = builder_cpp.replace(route_marker, route_insert, 1)

builder_cpp_path.write_text(builder_cpp, encoding="utf-8")


# ----------------------------------------------------------------------
# 4) Make Qt submission logs/status call this Prompt API video, not native video.
# ----------------------------------------------------------------------

old_backend = """    const QString backendSummary = videoMode
                                       ? (hasWorkflowBinding ? QStringLiteral("workflow video") : QStringLiteral("native video"))
                                       : QStringLiteral("native image");"""

new_backend = """    const QString route = payload.value(QStringLiteral("video_backend_route")).toString().trimmed().toLower();
    const QString command = payload.value(QStringLiteral("command")).toString().trimmed().toLower();
    const bool promptApiVideo =
        videoMode &&
        (route == QStringLiteral("prompt_api") ||
         payload.value(QStringLiteral("video_uses_prompt_api_backend")).toBool(false) ||
         command == QStringLiteral("ltx_prompt_api_gated_submission"));

    const QString backendSummary = videoMode
                                       ? (promptApiVideo
                                              ? QStringLiteral("Prompt API video")
                                              : (hasWorkflowBinding ? QStringLiteral("workflow video") : QStringLiteral("native video")))
                                       : QStringLiteral("native image");"""

if "const bool promptApiVideo =" not in submission_policy:
    if old_backend not in submission_policy:
        raise SystemExit("Could not find acceptedRequestLogLine backendSummary block.")
    submission_policy = submission_policy.replace(old_backend, new_backend, 1)

submission_policy_path.write_text(submission_policy, encoding="utf-8")


# ----------------------------------------------------------------------
# 5) Documentation.
# ----------------------------------------------------------------------

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text("""# Sprint 15C Pass 29F — Hard Route LTX Prompt API

## Problem

The UI showed LTX readiness, but the queue failed with:

- command: `t2v`
- status: `loading native video pipeline`

That means the request still entered the native video worker route.

## Fix

GenerationRequestBuilder now hard-routes any LTX video request to:

- `command = ltx_prompt_api_gated_submission`
- `backend = comfy_prompt_api`
- `video_backend_route = prompt_api`
- `video_backend_name = LTX Prompt API`

It also emits the explicit LTX component aliases again inside the final route block so downstream worker code cannot lose them.

## Expected behavior

LTX Generate should no longer say `loading native video pipeline`.

The queue/log status should identify the request as LTX Prompt API / Prompt API video.
""", encoding="utf-8")

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 29F: LTX Generate is hard-routed to Prompt API.")
