from pathlib import Path

root = Path(".")
submission_path = root / "python" / "ltx_prompt_api_submission.py"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS11_LTX_RESULT_SURFACING_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass11_ltx_result_surfacing.py"

text = submission_path.read_text(encoding="utf-8")

# 1) Add native result/queue/history helper functions after _write_metadata_sidecars.
needle = '''def _write_metadata_sidecars(
    outputs: list[dict[str, Any]],
    metadata: dict[str, Any],
    enabled: bool,
) -> list[dict[str, Any]]:
    if not enabled:
        return []

    sidecars: list[dict[str, Any]] = []

    for output in outputs:
        output_path = Path(str(output.get("path") or ""))
        if not output_path.name:
            continue

        sidecar_path = output_path.with_suffix(output_path.suffix + ".spellvision.json")
        payload = dict(metadata)
        payload["output"] = output

        try:
            sidecar_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            sidecars.append(
                {
                    "output_path": str(output_path),
                    "metadata_path": str(sidecar_path),
                    "ok": True,
                    "error": "",
                }
            )
        except Exception as exc:
            sidecars.append(
                {
                    "output_path": str(output_path),
                    "metadata_path": str(sidecar_path),
                    "ok": False,
                    "error": str(exc),
                }
            )

    return sidecars


def ltx_prompt_api_gated_submission_snapshot(
'''

insert = '''def _write_metadata_sidecars(
    outputs: list[dict[str, Any]],
    metadata: dict[str, Any],
    enabled: bool,
) -> list[dict[str, Any]]:
    if not enabled:
        return []

    sidecars: list[dict[str, Any]] = []

    for output in outputs:
        output_path = Path(str(output.get("path") or ""))
        if not output_path.name:
            continue

        sidecar_path = output_path.with_suffix(output_path.suffix + ".spellvision.json")
        payload = dict(metadata)
        payload["output"] = output

        try:
            sidecar_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            sidecars.append(
                {
                    "output_path": str(output_path),
                    "metadata_path": str(sidecar_path),
                    "ok": True,
                    "error": "",
                }
            )
        except Exception as exc:
            sidecars.append(
                {
                    "output_path": str(output_path),
                    "metadata_path": str(sidecar_path),
                    "ok": False,
                    "error": str(exc),
                }
            )

    return sidecars


def _sidecar_for_output(output_path: str, sidecars: list[dict[str, Any]]) -> str:
    normalized = str(Path(str(output_path or "")))
    for sidecar in sidecars:
        if str(Path(str(sidecar.get("output_path") or ""))) == normalized:
            return str(sidecar.get("metadata_path") or "")
    return ""


def _classify_output_role(output: dict[str, Any]) -> str:
    filename = str(output.get("filename") or "").lower()
    node_id = str(output.get("node_id") or "")

    if filename.startswith("output_f") or node_id == "4823":
        return "full"
    if filename.startswith("output_d") or node_id == "4852":
        return "distilled"
    return "video"


def _build_spellvision_output_records(
    outputs: list[dict[str, Any]],
    sidecars: list[dict[str, Any]],
    prompt_id: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for index, output in enumerate(outputs):
        path = str(output.get("path") or "")
        filename = str(output.get("filename") or "")
        role = _classify_output_role(output)

        records.append(
            {
                "id": f"ltx-{prompt_id}-{index}",
                "kind": "video",
                "role": role,
                "family": "ltx",
                "label": "LTX Full" if role == "full" else ("LTX Distilled" if role == "distilled" else "LTX Video"),
                "node_id": str(output.get("node_id") or ""),
                "filename": filename,
                "path": path,
                "uri": Path(path).as_uri() if path and Path(path).is_absolute() else path,
                "exists": bool(output.get("exists", False)),
                "size_bytes": int(output.get("size_bytes") or 0),
                "animated": bool(output.get("animated", False)),
                "metadata_path": _sidecar_for_output(path, sidecars),
                "preview_path": path,
                "openable": bool(output.get("exists", False)),
                "requeue_supported": True,
                "send_to_mode": "t2v",
            }
        )

    return records


def _build_spellvision_result_contract(
    *,
    prompt_id: str,
    client_id: str,
    endpoint: str,
    output_root: Path,
    submission_status: str,
    result_completed: bool,
    outputs: list[dict[str, Any]],
    metadata_sidecars: list[dict[str, Any]],
    model_stack: dict[str, Any],
    result_polling: dict[str, Any],
    workflow_api_path: str,
) -> dict[str, Any]:
    output_records = _build_spellvision_output_records(outputs, metadata_sidecars, prompt_id)

    primary_output = output_records[0] if output_records else {}
    full_outputs = [item for item in output_records if item.get("role") == "full"]
    distilled_outputs = [item for item in output_records if item.get("role") == "distilled"]

    if full_outputs:
        primary_output = full_outputs[0]
    elif distilled_outputs:
        primary_output = distilled_outputs[0]

    return {
        "type": "spellvision_generation_result",
        "schema_version": 1,
        "family": "ltx",
        "display_name": "LTX-Video",
        "validation_status": "experimental",
        "task_type": "t2v",
        "backend": "comfy_prompt_api",
        "prompt_id": prompt_id,
        "client_id": client_id,
        "endpoint": endpoint,
        "output_root": str(output_root),
        "workflow_api_path": workflow_api_path,
        "status": "completed" if result_completed else submission_status,
        "completed": bool(result_completed),
        "primary_output": primary_output,
        "outputs": output_records,
        "output_count": len(output_records),
        "metadata_sidecars": metadata_sidecars,
        "model_stack": model_stack,
        "result_polling": result_polling,
        "history_ready": bool(result_completed and output_records),
        "queue_ready": True,
        "preview_ready": bool(primary_output),
        "retry_supported": True,
        "requeue_request": {
            "command": "ltx_prompt_api_gated_submission",
            "prompt_api_export_path": workflow_api_path,
            "submit_to_comfy": True,
            "dry_run": False,
            "wait_for_result": True,
            "capture_metadata": True,
        },
    }


def _build_spellvision_queue_event(
    result_contract: dict[str, Any],
    *,
    submission_status: str,
    prompt_id: str,
) -> dict[str, Any]:
    primary = result_contract.get("primary_output") if isinstance(result_contract.get("primary_output"), dict) else {}

    return {
        "type": "spellvision_queue_result_event",
        "schema_version": 1,
        "family": "ltx",
        "task_type": "t2v",
        "backend": "comfy_prompt_api",
        "prompt_id": prompt_id,
        "state": "completed" if result_contract.get("completed") else submission_status,
        "title": "LTX Prompt API generation",
        "summary": f"{result_contract.get('output_count', 0)} video output(s) captured",
        "primary_output_path": primary.get("path", ""),
        "primary_metadata_path": primary.get("metadata_path", ""),
        "outputs": result_contract.get("outputs", []),
        "result": result_contract,
    }


def _build_spellvision_history_record(
    result_contract: dict[str, Any],
    *,
    model_stack: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    primary = result_contract.get("primary_output") if isinstance(result_contract.get("primary_output"), dict) else {}

    return {
        "type": "spellvision_history_record",
        "schema_version": 1,
        "created_at": created_at,
        "family": "ltx",
        "task_type": "t2v",
        "backend": "comfy_prompt_api",
        "title": "LTX Prompt API generation",
        "prompt": model_stack.get("prompt", ""),
        "negative_prompt": model_stack.get("negative_prompt", ""),
        "model": model_stack.get("model", ""),
        "seed": model_stack.get("seed"),
        "width": model_stack.get("width"),
        "height": model_stack.get("height"),
        "frames": model_stack.get("frames"),
        "fps": model_stack.get("fps"),
        "primary_output_path": primary.get("path", ""),
        "primary_metadata_path": primary.get("metadata_path", ""),
        "outputs": result_contract.get("outputs", []),
        "result": result_contract,
    }


def ltx_prompt_api_gated_submission_snapshot(
'''

if needle not in text:
    raise SystemExit("Could not find _write_metadata_sidecars block.")
text = text.replace(needle, insert, 1)

# 2) Add local variables before status calculation.
old = '''    if blocked_reasons:
        submission_status = "blocked"
'''
new = '''    model_stack = _extract_prompt_node_inputs(prompt_api_preview)
    created_at = _utc_now_iso()

    if blocked_reasons:
        submission_status = "blocked"
'''
if old not in text:
    raise SystemExit("Could not find submission_status block.")
text = text.replace(old, new, 1)

# 3) Replace model_metadata reuse block to use model_stack.
text = text.replace(
'''            model_metadata = _extract_prompt_node_inputs(prompt_api_preview)
            metadata_payload = {
''',
'''            metadata_payload = {
''',
1,
)

text = text.replace(
'''                "model_stack": model_metadata,
''',
'''                "model_stack": model_stack,
''',
1,
)

# 4) Add result/queue/history contracts before return.
old = '''    ok = not blocked_reasons or submitted
    if wait_for_result and submitted:
        ok = ok and (result_completed or bool(result_polling.get("timed_out")))

    return {
'''
new = '''    result_contract = _build_spellvision_result_contract(
        prompt_id=prompt_id,
        client_id=client_id,
        endpoint=endpoint,
        output_root=output_root,
        submission_status=submission_status,
        result_completed=result_completed,
        outputs=outputs,
        metadata_sidecars=metadata_sidecars,
        model_stack=model_stack,
        result_polling=result_polling,
        workflow_api_path=str(req.get("prompt_api_export_path") or ""),
    )

    queue_result_event = _build_spellvision_queue_event(
        result_contract,
        submission_status=submission_status,
        prompt_id=prompt_id,
    )

    history_record = _build_spellvision_history_record(
        result_contract,
        model_stack=model_stack,
        created_at=created_at,
    )

    ok = not blocked_reasons or submitted
    if wait_for_result and submitted:
        ok = ok and (result_completed or bool(result_polling.get("timed_out")))

    return {
'''
if old not in text:
    raise SystemExit("Could not find ok/return block.")
text = text.replace(old, new, 1)

# 5) Add returned fields near outputs/metadata/model_stack.
old = '''        "outputs": outputs,
        "metadata_sidecars": metadata_sidecars,
        "model_stack": _extract_prompt_node_inputs(prompt_api_preview),
        "adapter": adapter if bool(req.get("include_adapter", False)) else {},
'''
new = '''        "outputs": outputs,
        "metadata_sidecars": metadata_sidecars,
        "model_stack": model_stack,
        "spellvision_result": result_contract,
        "queue_result_event": queue_result_event,
        "history_record": history_record,
        "primary_output": result_contract.get("primary_output", {}),
        "ui_outputs": result_contract.get("outputs", []),
        "adapter": adapter if bool(req.get("include_adapter", False)) else {},
'''
if old not in text:
    raise SystemExit("Could not find outputs return block.")
text = text.replace(old, new, 1)

submission_path.write_text(text, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
'''# Sprint 15C Pass 11 — LTX Result Surfacing into Queue/History Contract

## Goal

Surface captured LTX Prompt API results as SpellVision-native queue/history/UI contracts.

## Builds on

Sprint 15C Pass 10 added:

- gated Prompt API submission
- result polling
- output path resolution
- `.spellvision.json` sidecar metadata

## New response fields

- `spellvision_result`
- `queue_result_event`
- `history_record`
- `primary_output`
- `ui_outputs`

## Contract intent

This pass does not yet insert records into the Qt History page or persistent queue store. It creates the stable payload those layers should consume in the next UI-facing pass.

## Why this matters

The UI should not parse raw Comfy history. SpellVision should consume its own normalized result objects.

## Expected status

A successful captured LTX run should return:

- `submission_status = submitted_completed_captured`
- `result_completed = true`
- `spellvision_result.completed = true`
- `spellvision_result.history_ready = true`
- `spellvision_result.preview_ready = true`
- `queue_result_event.state = completed`
- `history_record.primary_output_path` points to the primary mp4
''',
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 11 LTX result surfacing contract.")
