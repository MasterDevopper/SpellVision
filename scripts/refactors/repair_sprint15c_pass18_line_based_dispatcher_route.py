from pathlib import Path

service_path = Path("python/worker_service.py")
service = service_path.read_text(encoding="utf-8")

import_line = "from ltx_requeue_draft_submission import ltx_requeue_draft_gated_submission_snapshot\n"
if import_line.strip() not in service:
    import_marker = "from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot\n"
    if import_marker not in service:
        raise SystemExit("Could not find ltx_prompt_api_submission import marker.")
    service = service.replace(import_marker, import_line + import_marker, 1)

route_signature = 'if command in {"ltx_requeue_draft_gated_submission"'
route_block = (
    '            if command in {"ltx_requeue_draft_gated_submission", "ltx_execute_requeue_draft", "video_family_ltx_requeue_gated_submission"}:\n'
    '                runtime_status = handle_comfy_runtime_status_command({})\n'
    '                emitter.emit(ltx_requeue_draft_gated_submission_snapshot(req, runtime_status=runtime_status))\n'
    '                return\n'
    '\n'
)

if route_signature not in service:
    lines = service.splitlines(keepends=True)

    insert_at = None
    for index, line in enumerate(lines):
        stripped = line.strip()

        if not stripped.startswith("if command in "):
            continue

        if "ltx_prompt_api_gated_submission" not in stripped:
            continue

        insert_at = index
        break

    if insert_at is None:
        for index, line in enumerate(lines):
            stripped = line.strip()

            if not stripped.startswith("if command in "):
                continue

            if "ltx_ui_queue_history_contract" not in stripped:
                continue

            insert_at = index
            break

    if insert_at is None:
        raise SystemExit("Could not find an LTX dispatcher insertion point.")

    lines.insert(insert_at, route_block)
    service = "".join(lines)

service_path.write_text(service, encoding="utf-8")

print("Inserted Pass 18 dispatcher route using line-based insertion.")
