from pathlib import Path

client_path = Path("python/worker_client.py")
module_path = Path("python/ltx_requeue_draft_submission.py")

client = client_path.read_text(encoding="utf-8")

if '"spellvision_ltx_requeue_gated_submission"' not in client:
    client = client.replace(
        '"ltx_requeue_draft_gated_submission"',
        '"ltx_requeue_draft_gated_submission", "spellvision_ltx_requeue_gated_submission"',
        1,
    )

client_path.write_text(client, encoding="utf-8")

module = module_path.read_text(encoding="utf-8")

module = module.replace(
'''        "ok": bool(gated.get("ok", True)),
        "execution_mode": "submit" if should_submit else "dry_run",
''',
'''        "ok": bool(gated.get("ok", True)) if should_submit else True,
        "execution_mode": "submit" if should_submit else "dry_run",
''',
1,
)

module_path.write_text(module, encoding="utf-8")

print("Repaired Pass 18 response type recognition and dry-run ok status.")
