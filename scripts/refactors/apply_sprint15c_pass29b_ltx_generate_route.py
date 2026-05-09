from pathlib import Path

builder_path = Path("qt_ui/generation/GenerationRequestBuilder.cpp")
doc_path = Path("docs/sprints/SPRINT15C_PASS29B_LTX_GENERATE_ROUTE_README.md")
script_path = Path("scripts/refactors/apply_sprint15c_pass29b_ltx_generate_route.py")

builder = builder_path.read_text(encoding="utf-8")

marker = '''        payload.insert(QStringLiteral("video_validated_prompt_api_family"), videoPolicy.validatedPromptApiFamily);'''

insert = '''        payload.insert(QStringLiteral("video_validated_prompt_api_family"), videoPolicy.validatedPromptApiFamily);

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
        }'''

if "Sprint 15C Pass 29B" not in builder:
    if marker not in builder:
        raise SystemExit("Could not find Pass 29A video_validated_prompt_api_family marker.")
    builder = builder.replace(marker, insert, 1)

builder_path.write_text(builder, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text("""# Sprint 15C Pass 29B — LTX Generate Route

## Goal

Route Qt Generate for LTX T2V/I2V into the existing LTX Prompt API gated submission worker path.

## What changed

When the video readiness policy reports:

- `video_uses_prompt_api_backend=true`
- `video_family=ltx`

the generated worker payload is routed to:

- `ltx_prompt_api_gated_submission`

The payload also enables:

- `submit_to_comfy=true`
- `dry_run=false`
- `wait_for_result=true`
- `capture_metadata=true`
- `register_result=true`

## What remains unchanged

- Wan native routing remains unchanged.
- Non-LTX video families remain blocked unless separately validated.
- The LTX worker-side adapter remains the safety gate before Comfy submission.

## Expected behavior

Pressing Generate from T2V/I2V with an LTX-ready stack should submit through the LTX Prompt API path, capture Comfy outputs, and register results into queue/history.
""", encoding="utf-8")

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 29B: LTX Generate now routes to Prompt API gated submission.")
