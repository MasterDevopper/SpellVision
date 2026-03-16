from __future__ import annotations

import copy
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from model_sources import materialize_request_assets
from runtime_adapters.base import AdapterExecutionError, RuntimeAdapter, RuntimeContext, RuntimeRequest, RuntimeResult


class ComfyWorkflowAdapter(RuntimeAdapter):
    backend_kind = "comfy_workflow"

    def supports(self, request: RuntimeRequest) -> bool:
        return request.backend_kind == self.backend_kind

    def run(self, request: RuntimeRequest, context: RuntimeContext) -> RuntimeResult:
        request = _with_materialized_assets(request)
        api_url = str(request.get("comfy_api_url") or "http://127.0.0.1:8188").rstrip("/")
        workflow = _load_workflow(request)
        workflow = copy.deepcopy(workflow)

        context.status("preparing ComfyUI workflow")
        context.progress(0, 100, "loading workflow")
        context.check_cancelled()

        _apply_common_overrides(workflow, request)
        _apply_explicit_overrides(workflow, request.get("workflow_overrides") or {})

        prompt_id = _submit_prompt(api_url, workflow)
        context.status(f"ComfyUI prompt submitted: {prompt_id}")

        history = _poll_history(api_url, prompt_id, context, request)
        source_asset = _extract_output_asset(history)
        if source_asset is None:
            raise AdapterExecutionError("ComfyUI finished but no output asset was found in history")

        source_path = _resolve_asset_path(api_url, source_asset, request)
        output_path = _materialize_output(source_path, api_url, source_asset, request)
        metadata_output = str(request.metadata_output or request.get("metadata_output") or "") or None

        return RuntimeResult(
            ok=True,
            output=output_path,
            metadata_output=metadata_output,
            backend_name="ComfyUI",
            detected_pipeline=request.get("workflow_name") or Path(str(request.get("workflow_path") or "workflow.json")).stem,
            task_type=request.command,
            media_type=request.media_type,
            details={
                "prompt_id": prompt_id,
                "workflow_path": request.get("workflow_path"),
                "asset": source_asset,
                "source_path": source_path,
            },
        )


def _load_workflow(request: RuntimeRequest) -> dict[str, Any]:
    workflow_json = request.get("workflow_json") or request.get("comfy_workflow")
    if isinstance(workflow_json, dict):
        return workflow_json
    if isinstance(workflow_json, str) and workflow_json.strip().startswith('{'):
        try:
            payload = json.loads(workflow_json)
            if isinstance(payload, dict):
                return payload
        except Exception as exc:
            raise AdapterExecutionError(f"Invalid workflow_json payload: {exc}") from exc

    workflow_path = str(request.get("workflow_path") or request.model or "").strip()
    if not workflow_path:
        raise AdapterExecutionError("Comfy workflow adapter requires workflow_path or workflow_json")
    workflow_file = Path(workflow_path)
    if not workflow_file.exists():
        raise AdapterExecutionError(f"Workflow file not found: {workflow_path}")
    try:
        payload = json.loads(workflow_file.read_text(encoding='utf-8'))
    except Exception as exc:
        raise AdapterExecutionError(f"Failed to load workflow JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AdapterExecutionError("Workflow JSON must be an object keyed by node id")
    return payload


def _apply_common_overrides(workflow: dict[str, Any], request: RuntimeRequest) -> None:
    mapping = {
        "prompt": request.get("prompt", ""),
        "negative_prompt": request.get("negative_prompt", ""),
        "seed": request.get("seed"),
        "steps": request.get("steps"),
        "cfg": request.get("cfg"),
        "width": request.get("width"),
        "height": request.get("height"),
        "fps": request.get("fps"),
        "num_frames": request.get("num_frames"),
        "input_image": request.get("input_image", ""),
        "input_video": request.get("input_video", ""),
        "model": request.get("model", request.model),
        "output": request.output_path or "",
    }
    aliases = {
        "prompt": {"text", "prompt", "positive", "positive_prompt"},
        "negative_prompt": {"negative", "negative_prompt", "negative_text"},
        "seed": {"seed", "noise_seed"},
        "steps": {"steps", "num_steps"},
        "cfg": {"cfg", "cfg_scale", "guidance", "guidance_scale"},
        "width": {"width"},
        "height": {"height"},
        "fps": {"fps", "frame_rate"},
        "num_frames": {"num_frames", "frames", "length"},
        "input_image": {"image", "image_path", "input_image"},
        "input_video": {"video", "video_path", "input_video"},
        "model": {"model", "model_name", "ckpt_name", "unet_name", "repo_id"},
        "output": {"filename_prefix", "output_path"},
    }

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for field, value in mapping.items():
            if value in (None, ""):
                continue
            for key in aliases.get(field, set()):
                if key in inputs and not isinstance(inputs.get(key), (list, dict)):
                    inputs[key] = value


def _apply_explicit_overrides(workflow: dict[str, Any], overrides: dict[str, Any]) -> None:
    if not isinstance(overrides, dict):
        return
    for path_expr, value in overrides.items():
        _set_path(workflow, str(path_expr), value)


def _set_path(root: dict[str, Any], path_expr: str, value: Any) -> None:
    if not path_expr:
        return
    parts = path_expr.split('.')
    cursor: Any = root
    for part in parts[:-1]:
        if isinstance(cursor, dict):
            if part not in cursor:
                return
            cursor = cursor[part]
        elif isinstance(cursor, list):
            try:
                cursor = cursor[int(part)]
            except Exception:
                return
        else:
            return
    leaf = parts[-1]
    if isinstance(cursor, dict) and leaf in cursor:
        cursor[leaf] = value
    elif isinstance(cursor, list):
        try:
            idx = int(leaf)
        except Exception:
            return
        if 0 <= idx < len(cursor):
            cursor[idx] = value


def _submit_prompt(api_url: str, workflow: dict[str, Any]) -> str:
    payload = json.dumps({"prompt": workflow}).encode('utf-8')
    req = urllib.request.Request(
        f"{api_url}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.URLError as exc:
        raise AdapterExecutionError(f"Failed to submit prompt to ComfyUI: {exc}") from exc
    prompt_id = str(data.get('prompt_id') or '')
    if not prompt_id:
        raise AdapterExecutionError(f"ComfyUI did not return a prompt_id: {data}")
    return prompt_id


def _poll_history(api_url: str, prompt_id: str, context: RuntimeContext, request: RuntimeRequest) -> dict[str, Any]:
    poll_interval = float(request.get('comfy_poll_interval_sec') or 1.0)
    timeout_sec = float(request.get('comfy_timeout_sec') or 3600)
    start = time.monotonic()
    ticks = 0
    while True:
        context.check_cancelled()
        ticks += 1
        elapsed = time.monotonic() - start
        context.progress(min(95, 5 + ticks), 100, f"waiting for ComfyUI ({int(elapsed)}s)")
        try:
            with urllib.request.urlopen(f"{api_url}/history/{prompt_id}", timeout=30) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
        except urllib.error.URLError as exc:
            if elapsed >= timeout_sec:
                raise AdapterExecutionError(f"Timed out polling ComfyUI history: {exc}") from exc
            time.sleep(poll_interval)
            continue

        history = payload.get(prompt_id)
        if isinstance(history, dict):
            status = history.get('status') or {}
            if isinstance(status, dict):
                if status.get('status_str') in {'error', 'failed'}:
                    raise AdapterExecutionError(f"ComfyUI prompt failed: {status}")
            outputs = history.get('outputs')
            if isinstance(outputs, dict) and outputs:
                context.progress(98, 100, 'ComfyUI finished')
                return history

        if elapsed >= timeout_sec:
            raise AdapterExecutionError(f"Timed out waiting for ComfyUI prompt {prompt_id}")
        time.sleep(poll_interval)


def _extract_output_asset(history: dict[str, Any]) -> dict[str, Any] | None:
    outputs = history.get('outputs') or {}
    priority_keys = ('videos', 'gifs', 'images', 'audio')
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for key in priority_keys:
            assets = node_output.get(key)
            if isinstance(assets, list) and assets:
                asset = assets[0]
                if isinstance(asset, dict) and asset.get('filename'):
                    asset = dict(asset)
                    asset['_asset_kind'] = key
                    return asset
    return None


def _resolve_asset_path(api_url: str, asset: dict[str, Any], request: RuntimeRequest) -> str | None:
    comfy_output_dir = str(request.get('comfy_output_dir') or '').strip()
    filename = str(asset.get('filename') or '')
    subfolder = str(asset.get('subfolder') or '')
    if comfy_output_dir and filename:
        return str(Path(comfy_output_dir) / subfolder / filename)
    return None


def _materialize_output(source_path: str | None, api_url: str, asset: dict[str, Any], request: RuntimeRequest) -> str:
    requested_output = str(request.output_path or '').strip()
    filename = str(asset.get('filename') or '')
    if not requested_output:
        if source_path:
            return source_path
        requested_output = str(Path.cwd() / filename)

    os.makedirs(os.path.dirname(requested_output), exist_ok=True)

    if source_path and os.path.exists(source_path):
        if os.path.abspath(source_path) != os.path.abspath(requested_output):
            shutil.copy2(source_path, requested_output)
        return requested_output

    query = urllib.parse.urlencode({
        'filename': asset.get('filename', ''),
        'subfolder': asset.get('subfolder', ''),
        'type': asset.get('type', 'output'),
    })
    view_url = f"{api_url}/view?{query}"
    try:
        with urllib.request.urlopen(view_url, timeout=60) as resp:
            data = resp.read()
    except urllib.error.URLError as exc:
        raise AdapterExecutionError(f"Failed to download ComfyUI output asset: {exc}") from exc
    Path(requested_output).write_bytes(data)
    return requested_output
