from pathlib import Path

service_path = Path("python/worker_service.py")
client_path = Path("python/worker_client.py")
doc_path = Path("docs/sprints/SPRINT15C_PASS18_LTX_REQUEUE_DRAFT_GATED_SUBMISSION_README.md")

service = service_path.read_text(encoding="utf-8")

if "from ltx_requeue_draft_submission import ltx_requeue_draft_gated_submission_snapshot" not in service:
    service = service.replace(
        "from ltx_prompt_api_submission import",
        "from ltx_requeue_draft_submission import ltx_requeue_draft_gated_submission_snapshot\nfrom ltx_prompt_api_submission import",
        1,
    )

if 'command == "ltx_requeue_draft_gated_submission"' not in service:
    marker = '    if command == "ltx_prompt_api_gated_submission":'
    route = '''    if command == "ltx_requeue_draft_gated_submission":
        return ltx_requeue_draft_gated_submission_snapshot(request)

'''
    if marker not in service:
        raise SystemExit("Could not find gated submission route marker in worker_service.py.")
    service = service.replace(marker, route + marker, 1)

service_path.write_text(service, encoding="utf-8")

client = client_path.read_text(encoding="utf-8")
if '"ltx_requeue_draft_gated_submission"' not in client:
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

print("Patched Pass 18 worker routing and docs.")
