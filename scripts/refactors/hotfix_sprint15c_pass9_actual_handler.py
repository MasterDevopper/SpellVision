from pathlib import Path

service_path = Path("python/worker_service.py")
client_path = Path("python/worker_client.py")

service = service_path.read_text(encoding="utf-8")

# Add import if missing.
if "from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot" not in service:
    service = service.replace(
        "from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot",
        "from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot\n"
        "from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot",
    )

# Add command handler if the actual route is missing.
handler_marker = 'if command in {"ltx_prompt_api_gated_submission", "ltx_prompt_api_submit", "ltx_submit_prompt_api", "video_family_prompt_api_gated_submission"}:'

if handler_marker not in service:
    needle = '''            emitter.emit(ltx_prompt_api_conversion_adapter_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"runtime_memory_status", "runtime_diagnostics", "unload_image_runtime", "unload_video_runtime", "unload_all_runtimes", "clear_cuda_cache"}:
'''

    insert = '''            emitter.emit(ltx_prompt_api_conversion_adapter_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"ltx_prompt_api_gated_submission", "ltx_prompt_api_submit", "ltx_submit_prompt_api", "video_family_prompt_api_gated_submission"}:
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
        if command in {"runtime_memory_status", "runtime_diagnostics", "unload_image_runtime", "unload_video_runtime", "unload_all_runtimes", "clear_cuda_cache"}:
'''

    if needle not in service:
        raise SystemExit("Could not find insertion point before runtime_memory_status block.")

    service = service.replace(needle, insert, 1)

service_path.write_text(service, encoding="utf-8")

client = client_path.read_text(encoding="utf-8")

# Add to worker_client direct LTX action normalization set if missing there.
if '"ltx_prompt_api_gated_submission"' not in client[client.find("if action in {"):client.find('if action == "install_recommended_video_nodes"')]:
    client = client.replace(
        '"ltx_prompt_api_conversion_adapter",\n"ltx_prompt_api_export_adapter",',
        '"ltx_prompt_api_conversion_adapter",\n"ltx_prompt_api_gated_submission",\n"ltx_prompt_api_export_adapter",',
        1,
    )

client_path.write_text(client, encoding="utf-8")

print("Patched actual Pass 9 handler route and client normalization.")
