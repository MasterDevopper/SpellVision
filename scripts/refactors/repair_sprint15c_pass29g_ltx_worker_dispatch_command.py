from pathlib import Path

path = Path("qt_ui/generation/GenerationRequestBuilder.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass29g_ltx_worker_dispatch_command.py")
text = path.read_text(encoding="utf-8")

needle = '''            payload.insert(QStringLiteral("command"), QStringLiteral("ltx_prompt_api_gated_submission"));
            payload.insert(QStringLiteral("source_command"), sourceCommand.isEmpty() ? draft.mode : sourceCommand);
            payload.insert(QStringLiteral("task_command"), draft.mode);
            payload.insert(QStringLiteral("workflow_task_command"), draft.mode);
            payload.insert(QStringLiteral("task_type"), draft.mode);
            payload.insert(QStringLiteral("mode"), draft.mode);'''

replacement = '''            payload.insert(QStringLiteral("command"), QStringLiteral("ltx_prompt_api_gated_submission"));

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
            payload.insert(QStringLiteral("mode"), draft.mode);'''

if "Sprint 15C Pass 29G:" not in text:
    count = text.count(needle)
    if count == 0:
        raise SystemExit("Could not find LTX command routing block to canonicalize.")
    text = text.replace(needle, replacement)

# Safety net: if any earlier/duplicate LTX route block still writes task_command
# or workflow_task_command back to t2v/i2v after command has been set, normalize it.
safety_block = '''
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
'''

if "Pass 29G final safety net" not in text:
    marker = "    return payload;\n"
    if marker not in text:
        raise SystemExit("Could not find return payload marker.")
    text = text.replace(marker, safety_block + "\n" + marker, 1)

path.write_text(text, encoding="utf-8")
script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 29G: canonical LTX worker dispatch command.")
