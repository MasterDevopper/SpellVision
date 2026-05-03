from pathlib import Path
import re

service_path = Path("python/worker_service.py")
client_path = Path("python/worker_client.py")
doc_path = Path("docs/sprints/SPRINT15C_PASS18_LTX_REQUEUE_DRAFT_GATED_SUBMISSION_README.md")

service = service_path.read_text(encoding="utf-8")

import_line = "from ltx_requeue_draft_submission import ltx_requeue_draft_gated_submission_snapshot\n"
if import_line.strip() not in service:
    marker = "from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot\n"
    if marker not in service:
        raise SystemExit("Could not find ltx_prompt_api_submission import marker.")
    service = service.replace(marker, import_line + marker, 1)

route = '''            if command in {"ltx_requeue_draft_gated_submission", "ltx_execute_requeue_draft", "video_family_ltx_requeue_gated_submission"}:
                runtime_status = handle_comfy_runtime_status_command({})
                emitter.emit(ltx_requeue_draft_gated_submission_snapshot(req, runtime_status=runtime_status))
                return

'''

if "ltx_requeue_draft_gated_submission" not in service:
    marker = '''            if command in {"ltx_prompt_api_gated_submission", "ltx_prompt_api_submit", "ltx_submit_prompt_api", "ltx_prompt_api_submit_and_capture", "ltx_prompt_api_submit_wait", "video_family_prompt_api_gated_submission"}:
'''
    if marker not in service:
        raise SystemExit("Could not find exact LTX gated submission dispatcher marker.")
    service = service.replace(marker, route + marker, 1)

service_path.write_text(service, encoding="utf-8")

client = client_path.read_text(encoding="utf-8")
if '"ltx_requeue_draft_gated_submission"' not in client:
    if '"ltx_prompt_api_gated_submission"' not in client:
        raise SystemExit("Could not find ltx_prompt_api_gated_submission in worker_client.py.")
    client = client.replace(
        '"ltx_prompt_api_gated_submission"',
        '"ltx_prompt_api_gated_submission", "ltx_requeue_draft_gated_submission"',
        1,
    )

client_path.write_text(client, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 18 — Execute LTX Requeue Draft Through Gated Submission\n\n"
    "Adds `ltx_requeue_draft_gated_submission`.\n\n"
    "The command reads the newest Pass 17 `.requeue.json` draft and routes it through the existing safe LTX Prompt API gated submission path.\n\n"
    "Default behavior is dry-run. Actual submission requires `submit_to_comfy=true` and `dry_run=false`.\n",
    encoding="utf-8",
)

print("Repaired Pass 18 worker dispatcher routing.")
