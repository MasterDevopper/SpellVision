from pathlib import Path

service_path = Path("python/worker_service.py")
client_path = Path("python/worker_client.py")

service = service_path.read_text(encoding="utf-8")

# 1) Add import
if "from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot" not in service:
    service = service.replace(
        "from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot",
        "from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot\n"
        "from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot",
    )

# 2) Add command handler after existing Pass 7/8 adapter handler
needle = '''        if command in {"ltx_prompt_api_conversion_adapter", "ltx_prompt_api_export_adapter", "ltx_prompt_api_conversion_preview", "video_family_prompt_api_conversion_adapter"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
                emitter.emit({
                    "type": "video_family_prompt_api_conversion_adapter",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_prompt_api_adapter_family",
                })
                return
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_prompt_api_conversion_adapter_snapshot(req, runtime_status=runtime_status))
            return
'''

insert = needle + '''        if command in {"ltx_prompt_api_gated_submission", "ltx_prompt_api_submit", "ltx_submit_prompt_api", "video_family_prompt_api_gated_submission"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
                emitter.emit({
                    "type": "video_family_prompt_api_gated_submission",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_prompt_api_submission_family",
                })
                return
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_prompt_api_gated_submission_snapshot(req, runtime_status=runtime_status))
            return

'''

if "ltx_prompt_api_gated_submission" not in service:
    if needle not in service:
        raise SystemExit("Could not find exact adapter handler block in worker_service.py.")
    service = service.replace(needle, insert)

service_path.write_text(service, encoding="utf-8")

# 3) Add worker_client allowlist entry if needed
client = client_path.read_text(encoding="utf-8")
if "ltx_prompt_api_gated_submission" not in client:
    if '"ltx_prompt_api_conversion_adapter"' in client:
        client = client.replace(
            '"ltx_prompt_api_conversion_adapter"',
            '"ltx_prompt_api_conversion_adapter", "ltx_prompt_api_gated_submission"',
            1,
        )
    elif "'ltx_prompt_api_conversion_adapter'" in client:
        client = client.replace(
            "'ltx_prompt_api_conversion_adapter'",
            "'ltx_prompt_api_conversion_adapter', 'ltx_prompt_api_gated_submission'",
            1,
        )
    else:
        raise SystemExit("Could not find worker_client adapter allowlist entry.")

client_path.write_text(client, encoding="utf-8")

print("Patched Pass 9 worker_service and worker_client command routing.")
