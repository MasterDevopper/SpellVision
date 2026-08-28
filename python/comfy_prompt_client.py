"""ComfyUI HTTP prompt client + imported-workflow runner.

Extracted from worker_service.py. Graph builders stay in native_*_graphs;
this module submits, polls, uploads, and runs bound Comfy workflows.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from worker_service_state import (
    ActiveJobHandle,
    JobEmitter,
    JobRecord,
    JobState,
    complete_job,
    raise_if_cancelled,
    transition_job,
)
from comfy_graph_helpers import (
    _comfy_required_inputs,
    _sv_choose_comfy_choice,
    _sv_comfy_input_choices,
)
from comfy_graph_converter import convert_ui_graph_to_api_prompt, is_ui_graph
from comfy_node_aliases import apply_node_aliases, unresolved_classes


log = logging.getLogger(__name__)


def _ws():
    import worker_service as ws
    return ws


def request_comfy_free_memory(*, api_url: str | None = None, timeout_sec: float = 8.0) -> dict[str, Any]:
    """Ask a live ComfyUI to drop loaded models. Best-effort; never raises."""
    root = (
        api_url
        or os.environ.get("COMFY_API_URL")
        or os.environ.get("SPELLVISION_COMFY_URL")
        or "http://127.0.0.1:8188"
    ).rstrip("/")
    url = f"{root}/free"
    body = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=float(timeout_sec)) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            return {"ok": True, "status": getattr(resp, "status", 200), "body": raw}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "url": url}


def _apply_workflow_slot_bindings(
    workflow: dict[str, Any],
    slot_bindings: dict[str, Any],
    req: dict[str, Any],
    object_info: dict[str, Any] | None = None,
) -> None:
    slot_values = _ws()._workflow_slot_values_from_request(req)
    for slot, raw_value in slot_values.items():
        if raw_value in (None, ""):
            continue
        binding = slot_bindings.get(slot)
        if not isinstance(binding, dict):
            continue
        node_id = str(binding.get("node_id") or "").strip()
        input_name = str(binding.get("input_name") or binding.get("input") or "").strip()
        path_expr = str(binding.get("path") or "").strip()
        if not path_expr and node_id and input_name:
            path_expr = f"{node_id}.inputs.{input_name}"
        if not path_expr:
            continue

        value: Any = raw_value
        # Resolve a model/checkpoint/lora override (which may arrive as a full path or bare filename)
        # to the loader node's exact catalogued name. Without object_info we leave it verbatim (a UI
        # already in ComfyUI-relative form still works; a full path would not, but that is the no-schema
        # fallback).
        if object_info and slot in _ws()._MODEL_SLOTS_TO_RESOLVE and node_id:
            node = workflow.get(node_id)
            if isinstance(node, dict):
                class_name = str(node.get("class_type") or "")
                target_input = input_name or (path_expr.rsplit(".", 1)[-1] if "." in path_expr else "")
                if class_name and target_input:
                    value = _sv_choose_comfy_choice(object_info, class_name, target_input, str(raw_value))

        _ws()._set_workflow_path(workflow, path_expr, value)


# Loader class -> (slot, input_name). A just-converted UI-graph carries no profile bindings, so we
# derive them from the API-prompt graph. Both "checkpoint" and "model" slots draw their value from
# req["model"] (see _workflow_slot_values_from_request), so a checkpoint loader binds the "checkpoint"
# slot and a diffusion-model (UNET) loader binds "model".
_MODEL_LOADER_SLOTS = {
    "CheckpointLoaderSimple": ("checkpoint", "ckpt_name"),
    "CheckpointLoader": ("checkpoint", "ckpt_name"),
    "UNETLoader": ("model", "unet_name"),
    "UnetLoaderGGUF": ("model", "unet_name"),
}
_LORA_LOADER_SLOTS = {
    "LoraLoader": "lora_name",
    "LoraLoaderModelOnly": "lora_name",
}


def _derive_checkpoint_slot_bindings(workflow: dict[str, Any]) -> dict[str, Any]:
    """Best-effort slot bindings for a just-converted API-prompt graph whose profile carried none
    (the UI-graph import path produces empty bindings). Only binds when the loader is unambiguous:
    a single checkpoint/diffusion-model loader binds the checkpoint/model slot, and a single lora
    loader binds the lora slot. Multi-loader graphs (e.g. a Wan high/low-noise dual UNETLoader) are
    left unbound -- still launchable, just not model-substitutable -- pending a multi-loader slot
    vocabulary (Stage 1.5 dual-loader design decision, deliberately not built here)."""
    model_loaders: list[tuple[str, str, str]] = []  # (slot, node_id, input_name)
    lora_loaders: list[tuple[str, str]] = []  # (node_id, input_name)
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if class_type in _MODEL_LOADER_SLOTS:
            slot, input_name = _MODEL_LOADER_SLOTS[class_type]
            if input_name in inputs:
                model_loaders.append((slot, str(node_id), input_name))
        elif class_type in _LORA_LOADER_SLOTS:
            input_name = _LORA_LOADER_SLOTS[class_type]
            if input_name in inputs:
                lora_loaders.append((str(node_id), input_name))
    bindings: dict[str, Any] = {}
    if len(model_loaders) == 1:
        slot, node_id, input_name = model_loaders[0]
        bindings[slot] = {"node_id": node_id, "input_name": input_name}
    if len(lora_loaders) == 1:
        node_id, input_name = lora_loaders[0]
        bindings["lora"] = {"node_id": node_id, "input_name": input_name}
    return bindings


def _apply_common_comfy_overrides(
    workflow: dict[str, Any], req: dict[str, Any], object_info: dict[str, Any] | None = None
) -> None:
    mapping = {
        "prompt": req.get("prompt"),
        "negative_prompt": req.get("negative_prompt"),
        "seed": req.get("seed"),
        "steps": req.get("steps"),
        "cfg": req.get("cfg"),
        "width": req.get("width"),
        "height": req.get("height"),
        "input_image": req.get("input_image"),
        "strength": req.get("strength"),
        "model": req.get("model"),
    }
    aliases = {
        "prompt": {"text", "prompt", "positive", "positive_prompt"},
        "negative_prompt": {"negative", "negative_prompt", "negative_text"},
        "seed": {"seed", "noise_seed"},
        "steps": {"steps", "num_steps", "num_inference_steps"},
        "cfg": {"cfg", "cfg_scale", "guidance", "guidance_scale"},
        "width": {"width"},
        "height": {"height"},
        "input_image": {"image", "image_path", "input_image"},
        "strength": {"strength", "denoise", "denoise_strength"},
        "model": {"model", "model_name", "ckpt_name", "checkpoint", "unet_name", "repo_id"},
    }
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "")
        for field_name, value in mapping.items():
            if value in (None, ""):
                continue
            for key in aliases.get(field_name, set()):
                if key in inputs and not isinstance(inputs.get(key), (list, dict)):
                    resolved = value
                    # The model override may arrive as a full path / bare name; resolve it to this
                    # loader's exact catalogued entry (matching _apply_workflow_slot_bindings), else
                    # this broad override would clobber the bound slot with an unvalidatable value.
                    if field_name == "model" and object_info and class_type:
                        resolved = _sv_choose_comfy_choice(object_info, class_type, key, str(value))
                    inputs[key] = resolved


# Loader inputs whose value names a model FILE. A workflow's own baked-in values (not just an override)
# routinely arrive as a bare filename or a subfolder-relative name that does not match ComfyUI's exact
# catalogued string (e.g. "nova.safetensors" vs "sdxl\nova.safetensors"), which /prompt rejects with
# value_not_in_list. Normalize every such input against the live catalog before submission.
_MODEL_FILE_INPUT_NAMES = {
    "ckpt_name", "unet_name", "lora_name", "vae_name", "clip_name", "clip_name1", "clip_name2",
    "control_net_name", "style_model_name", "upscale_model_name", "clip_vision_name", "model_name",
    "gguf_name", "ipadapter_file", "instantid_file",
}


def _normalized_model_name(value: str) -> str:
    """Compare model names the way ComfyUI's own catalog does not: separator- and case-insensitively.

    A workflow may bake ``sdxl/foo.safetensors`` while the catalog says ``sdxl\\foo.safetensors``,
    and a user's choice arrives in whichever form the UI happened to have. Matching on the raw
    string means a substitution silently fails to apply and the launch quietly uses the model the
    user was replacing.
    """
    return str(value or "").strip().replace("\\", "/").lower()


def apply_model_substitutions(
    workflow: dict[str, Any], substitutions: dict[str, str] | None
) -> list[dict[str, str]]:
    """Replace named model files throughout the graph. Returns what was applied.

    This is the tier-3/tier-4 chosen substitute reaching the launch. It is deliberately explicit
    and deliberately reported: Doc 19's rule is that a substitution is never silent, so the caller
    gets back every ``{node_id, input, wanted, used}`` it performed and is expected to surface it
    as "wanted X, ran Y". An empty return means nothing matched, which is itself worth showing --
    a substitution the user chose that then failed to apply is exactly the silent wrong render
    this codebase keeps getting bitten by.
    """
    if not substitutions:
        return []

    wanted_map = {_normalized_model_name(k): str(v) for k, v in substitutions.items() if k and v}
    if not wanted_map:
        return []

    applied: list[dict[str, str]] = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for input_name in _MODEL_FILE_INPUT_NAMES:
            value = inputs.get(input_name)
            if not isinstance(value, str) or not value.strip():
                continue
            replacement = wanted_map.get(_normalized_model_name(value))
            if replacement is None or replacement == value:
                continue
            inputs[input_name] = replacement
            applied.append({
                "node_id": str(node_id),
                "input": input_name,
                "wanted": value,
                "used": replacement,
            })
    return applied


def _resolve_graph_model_names(workflow: dict[str, Any], object_info: dict[str, Any] | None) -> None:
    if not object_info:
        return
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or not class_type:
            continue
        for input_name in _MODEL_FILE_INPUT_NAMES:
            value = inputs.get(input_name)
            if not isinstance(value, str) or not value.strip():
                continue
            choices = _sv_comfy_input_choices(object_info, class_type, input_name)
            if not choices or value in choices:
                continue  # no catalog for this input, or already an exact match
            resolved = _sv_choose_comfy_choice(object_info, class_type, input_name, value)
            if resolved in choices:
                inputs[input_name] = resolved  # only rewrite when we land on a real catalogued entry


def _read_http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read()
    except Exception:
        return ""

    if not body:
        return ""

    try:
        return body.decode("utf-8", errors="replace")
    except Exception:
        return repr(body[:4000])


def _submit_comfy_prompt(api_url: str, workflow: dict[str, Any]) -> str:
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"{api_url}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = _read_http_error_body(exc).strip()
        body_excerpt = body[:5000] if body else "<empty response body>"
        raise RuntimeError(
            f"Failed to submit prompt to ComfyUI at {api_url}: HTTP {exc.code} {exc.reason}. "
            f"Comfy response body: {body_excerpt}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to submit prompt to ComfyUI at {api_url}: {exc}") from exc
    prompt_id = str(data.get("prompt_id") or "").strip()
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return a prompt_id: {data}")
    return prompt_id


def _comfy_status_is_completed(status: Any) -> bool:
    """True when ComfyUI marks a prompt terminally finished (success), independent of outputs.

    ComfyUI writes the /history `status` for a finished prompt, but `outputs` can lag (or, for a
    genuinely empty result, never appear). Detecting the terminal-success flag lets the poller
    stop waiting the full timeout on a completed-but-empty prompt instead of hanging the queue."""
    if not isinstance(status, dict):
        return False
    if status.get("completed") is True:
        return True
    return str(status.get("status_str") or "").strip().lower() in {"success", "completed"}


def _describe_comfy_execution_error(prompt_id: str, status: dict[str, Any]) -> str:
    """Name the node that failed and why, instead of dumping the whole status dict.

    ComfyUI records the real cause in status.messages as an ``execution_error`` entry carrying the
    node id, node type, exception type and message. Reporting ``{status}`` buried that under the
    full message log, and a caller that never reached this branch at all reported nothing.
    Measured on a real failure, the useful line is:

        node 11 (CLIPTextEncode) raised MemoryError: VBAR allocation failed

    which points straight at ComfyUI's allocator, where "ComfyUI prompt failed: {...}" did not.
    """
    for message in (status.get("messages") or []):
        if not (isinstance(message, (list, tuple)) and len(message) >= 2):
            continue
        if message[0] != "execution_error" or not isinstance(message[1], dict):
            continue
        detail = message[1]
        node_id = detail.get("node_id")
        node_type = detail.get("node_type") or "unknown node"
        exc_type = detail.get("exception_type") or "error"
        exc_message = str(detail.get("exception_message") or "").strip().splitlines()
        summary = exc_message[0] if exc_message else ""
        return (
            f"ComfyUI failed to run prompt {prompt_id}: node {node_id} ({node_type}) "
            f"raised {exc_type}: {summary}"
        )
    return f"ComfyUI prompt {prompt_id} failed: {status.get('status_str') or status}"


def _poll_comfy_history(api_url: str, prompt_id: str, req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    # Explicit None checks, not `or`: every one of these is a number a caller may legitimately set
    # to ZERO (poll as fast as possible, do not wait, no grace window), and zero is falsy, so `or`
    # silently substitutes the default. A test asking for a 0s timeout got 1800 and hung.
    def _seconds(key: str, default: float) -> float:
        value = req.get(key)
        return default if value is None else float(value)

    poll_interval = _seconds("comfy_poll_interval_sec", 1.0)
    timeout_sec = _seconds("comfy_timeout_sec", 1800.0)
    completed_grace_sec = _seconds("comfy_completed_grace_sec", 15.0)
    completed_seen_at: float | None = None
    start = time.monotonic()
    tick = 0
    while True:
        raise_if_cancelled(active_job, emitter, "waiting for ComfyUI")
        elapsed = time.monotonic() - start
        tick += 1
        emitter.progress(job, min(95, max(1, tick)), 100, _ws().comfy_waiting_message(req, elapsed))
        try:
            with urllib.request.urlopen(f"{api_url}/history/{prompt_id}", timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            # URLError alone is not enough, and the gap is not theoretical. A timeout while READING
            # the body raises TimeoutError, which is an OSError and NOT a URLError, so it escaped
            # this handler and killed the job outright -- with str(exc) being the bare word
            # "timed out". Measured: a wedged ComfyUI made /history slow, the job was reported as
            # "timed out", and the REAL cause (a MemoryError on a CLIPTextEncode node, which
            # ComfyUI had already written into /history) was never surfaced at all.
            #
            # This is the same class as the /object_info ConnectionResetError: an OSError that is
            # not a URLError slipping past a too-narrow except. A transient read failure must be
            # retried like any other, so the loop can go on to READ the error ComfyUI recorded.
            # ValueError covers a truncated/!JSON body, which is likewise transient.
            if elapsed >= timeout_sec:
                raise RuntimeError(
                    f"Timed out waiting for ComfyUI prompt {prompt_id} after {elapsed:.0f}s "
                    f"(last transport error: {exc.__class__.__name__}: {exc})"
                ) from exc
            time.sleep(poll_interval)
            continue

        history = payload.get(prompt_id)
        if isinstance(history, dict):
            status = history.get("status") or {}
            if isinstance(status, dict) and status.get("status_str") in {"error", "failed"}:
                raise RuntimeError(_describe_comfy_execution_error(prompt_id, status))
            outputs = history.get("outputs")
            if isinstance(outputs, dict) and outputs:
                return history
            # ComfyUI reported this prompt terminally finished but /history carries no outputs yet.
            # Grant a bounded grace window for outputs to materialize, then fail cleanly instead of
            # spinning to the full timeout — a completed-but-empty prompt must terminate the job
            # (COMPLETED via outputs, or a clear error) so it can never hang the queue at 95%.
            if _comfy_status_is_completed(status):
                now = time.monotonic()
                if completed_seen_at is None:
                    completed_seen_at = now
                elif now - completed_seen_at >= completed_grace_sec:
                    raise RuntimeError(
                        f"ComfyUI reported prompt {prompt_id} completed but produced no outputs "
                        f"after {completed_grace_sec:.0f}s grace (status={status})."
                    )

        if elapsed >= timeout_sec:
            raise RuntimeError(f"Timed out waiting for ComfyUI prompt {prompt_id}")
        time.sleep(poll_interval)


def _extract_comfy_asset(history: dict[str, Any], preferred_kinds: list[str] | None = None) -> dict[str, Any] | None:
    outputs = history.get("outputs") or {}
    kind_order = list(preferred_kinds or [])
    for fallback in ("images", "videos", "gifs", "audio"):
        if fallback not in kind_order:
            kind_order.append(fallback)

    for key in kind_order:
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            assets = node_output.get(key)
            if isinstance(assets, list) and assets:
                asset = assets[0]
                if isinstance(asset, dict) and asset.get("filename"):
                    enriched = dict(asset)
                    enriched["_asset_kind"] = key
                    return enriched
    return None


def _download_comfy_asset(api_url: str, asset: dict[str, Any], destination: str) -> str:
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    query = urllib.parse.urlencode({
        "filename": asset.get("filename", ""),
        "subfolder": asset.get("subfolder", ""),
        "type": asset.get("type", "output"),
    })
    view_url = f"{api_url}/view?{query}"
    try:
        with urllib.request.urlopen(view_url, timeout=120) as resp:
            data = resp.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to download ComfyUI output asset: {exc}") from exc
    Path(destination).write_bytes(data)
    return destination


def _native_prompt_debug_path(req: dict[str, Any], job_id: str) -> str:
    metadata_output = str(req.get("metadata_output") or "").strip()
    output_path = str(req.get("output") or "").strip()
    base_path = Path(metadata_output or output_path or f"native_split_{job_id}.json")
    parent = base_path.parent if str(base_path.parent) not in {"", "."} else Path.cwd()
    stem = base_path.stem or f"native_split_{job_id}"
    return str(parent / f"{stem}_native_prompt_api.json")


def _write_native_prompt_debug_file(path_value: str, workflow: dict[str, Any]) -> str:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    return str(path)


def _required_input_allows_empty(class_type: str, input_name: str) -> bool:
    class_key = str(class_type or "").strip().lower()
    input_key = str(input_name or "").strip().lower()

    # Text-prompt inputs on any *TextEncode* node may legitimately be empty (e.g. an empty NEGATIVE
    # prompt). Lumina's CLIPTextEncodeLumina2 uses user_prompt/system_prompt instead of "text"; without
    # these the negative node (user_prompt="") was falsely flagged "required input is empty", failing the
    # whole lumina render at local validation before submit.
    if input_key in {"text", "prompt", "negative_prompt", "user_prompt", "system_prompt"} and "textencode" in class_key:
        return True

    if class_key in {"cliptextencode"} and input_key == "text":
        return True

    return False


def _validate_comfy_prompt_against_object_info(workflow: dict[str, Any], object_info: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            issues.append(f"node {node_id}: node payload is not an object")
            continue

        class_type = str(node.get("class_type") or "").strip()
        if not class_type:
            issues.append(f"node {node_id}: missing class_type")
            continue

        if class_type not in object_info:
            issues.append(f"node {node_id}: Comfy class {class_type!r} is not available")
            continue

        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            issues.append(f"node {node_id} ({class_type}): inputs must be an object")
            continue

        required_inputs = _comfy_required_inputs(object_info, class_type)
        for input_name in sorted(required_inputs):
            if input_name not in inputs:
                issues.append(f"node {node_id} ({class_type}): missing required input {input_name!r}")
                continue

            value = inputs.get(input_name)
            if value is None:
                issues.append(f"node {node_id} ({class_type}): required input {input_name!r} is empty")
                continue
            if value == "" and not _required_input_allows_empty(class_type, input_name):
                issues.append(f"node {node_id} ({class_type}): required input {input_name!r} is empty")
                continue

        for input_name, value in inputs.items():
            if not isinstance(value, list) or len(value) != 2:
                continue

            source_node_id = str(value[0])
            if source_node_id not in workflow:
                issues.append(
                    f"node {node_id} ({class_type}): input {input_name!r} references missing node {source_node_id!r}"
                )

    return issues


_OBJECT_INFO_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_OBJECT_INFO_LOCK = threading.Lock()
# /object_info only changes when ComfyUI restarts or a custom node is installed -- both of which
# call invalidate_comfy_object_info() explicitly. The TTL is a backstop for anything that mutates
# the node set behind our back (a manual restart, a node installed through Comfy's own UI).
_OBJECT_INFO_TTL_SEC = 60.0
# How long a single /object_info read may keep retrying, and the ceiling on its backoff.
# Sized for "ComfyUI is unresponsive while swapping a multi-GB model", which is the observed
# failure, not for a permanently-down server (that still fails, just after the budget).
_OBJECT_INFO_RETRY_BUDGET_SEC = 120.0
_OBJECT_INFO_RETRY_MAX_DELAY_SEC = 8.0


def invalidate_comfy_object_info(reason: str = "") -> None:
    """Drop the cached /object_info. Call after any restart or custom-node install."""
    with _OBJECT_INFO_LOCK:
        had = bool(_OBJECT_INFO_CACHE)
        _OBJECT_INFO_CACHE.clear()
    if had:
        log.warning("Invalidated cached ComfyUI /object_info%s", f": {reason}" if reason else "")


def _comfy_object_info(api_url: str, *, force_refresh: bool = False,
                       budget_sec: float | None = None) -> dict[str, Any]:
    # This is ~2MB of JSON fetched and parsed on EVERY native image/video job and every workflow
    # launch. The node set it describes is static for the lifetime of a ComfyUI process, so cache
    # it per endpoint and let restart/install paths invalidate.
    if not force_refresh:
        with _OBJECT_INFO_LOCK:
            entry = _OBJECT_INFO_CACHE.get(api_url)
            if entry and (time.monotonic() - entry[0]) < _OBJECT_INFO_TTL_SEC:
                return entry[1]

    payload = _fetch_comfy_object_info(api_url, budget_sec=budget_sec)
    with _OBJECT_INFO_LOCK:
        _OBJECT_INFO_CACHE[api_url] = (time.monotonic(), payload)
    return payload


def _http_get_json(api_url: str, path: str, *, timeout: float = 90.0) -> Any:
    """GET a JSON body without urllib's forced ``Connection: close`` (see _fetch_comfy_object_info).

    gzip is requested because ComfyUI's larger bodies compress roughly tenfold, which is worth the
    few lines on a response this size.
    """
    import gzip
    import http.client

    parsed = urllib.parse.urlparse(api_url if "://" in api_url else f"http://{api_url}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(host, port, timeout=timeout)
    try:
        conn.request("GET", (parsed.path.rstrip("/") + path) or path, headers={
            "Host": f"{host}:{port}",
            "User-Agent": "SpellVision/1.0",
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        })
        resp = conn.getresponse()
        body = resp.read()
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status} from {api_url}{path}")
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            body = gzip.decompress(body)
        return json.loads(body.decode("utf-8"))
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _fetch_comfy_object_info(api_url: str, *, budget_sec: float | None = None) -> dict[str, Any]:
    # ComfyUI's /object_info body is large (~2MB+) and the connection can be reset
    # mid-read under load (ConnectionResetError, which is NOT a urllib URLError, so a
    # plain single urlopen slips it through). Every native video gen calls this, so a
    # transient reset must not abort the job: retry a few times with a short backoff, and
    # use a generous timeout. On exhaustion, raise a clear error rather than returning a
    # partial/empty dict (a truncated object_info would cause confusing downstream
    # node-resolution failures).
    #
    # This uses http.client rather than urllib, and that is the whole fix for the reset. Measured
    # against core v0.34.0 on :8189 (6.76MB body), with the request otherwise identical:
    #
    #   bare / Accept-Encoding: identity / Accept-Encoding: gzip -> 3 of 3 succeeded
    #   Connection: close, with or without gzip                  -> 3 of 3 ConnectionResetError
    #
    # The server tears the socket down at its end before the body is fully flushed. urllib ALWAYS
    # sends `Connection: close` (AbstractHTTPHandler.do_open puts it unconditionally), so there is
    # no way to avoid the header while still using urlopen -- deleting the explicit header this
    # function used to pass changes nothing. The old core on :8188 (2.4MB) tolerated it, which is
    # why this looked like "one run in three" flakiness rather than a header bug, and why the
    # earlier fix was retries instead of a different client.
    # Retry against a TIME BUDGET, not a fixed attempt count. The old form slept
    # 0.5*(attempt+1) over 4 gaps -- five tries inside ~5 seconds. That is far too short for the
    # case this actually hits: ComfyUI stops serving HTTP while it swaps a large model (observed
    # failing a Wan job outright when a 43GB LTX checkpoint was being evicted), and the socket
    # refuses/resets immediately, so all five attempts burn in a couple of seconds and the job
    # dies while ComfyUI is merely busy. Exponential backoff to a cap keeps the chatter low and
    # rides out a swap that takes tens of seconds.
    # An INTERACTIVE caller passes a short budget. The long default exists for generation, where
    # riding out a model swap is worth a two-minute wait; a UI asking "what is missing?" must not
    # inherit that, and a connection actively refused for six seconds means ComfyUI is down, not busy.
    budget = _OBJECT_INFO_RETRY_BUDGET_SEC if budget_sec is None else max(0.0, float(budget_sec))
    deadline = time.monotonic() + budget
    delay = 1.0
    attempt = 0
    last_error: Exception | None = None
    while True:
        attempt += 1
        try:
            payload = _http_get_json(api_url, "/object_info", timeout=min(90.0, budget) if budget else 90.0)
            if not isinstance(payload, dict):
                raise RuntimeError("ComfyUI /object_info did not return a JSON object")
            return payload
        except Exception as exc:  # URLError, ConnectionResetError/OSError, JSON decode, etc.
            last_error = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if attempt == 1 or attempt % 4 == 0:
                log.warning(
                    "ComfyUI /object_info attempt %d failed (%s); retrying for another %.0fs "
                    "-- ComfyUI is typically mid model-swap when this happens.",
                    attempt, exc, remaining,
                )
            time.sleep(min(delay, remaining))
            delay = min(delay * 2.0, _OBJECT_INFO_RETRY_MAX_DELAY_SEC)
    raise RuntimeError(
        f"Failed to read ComfyUI object_info from {api_url} after {attempt} attempts over "
        f"{budget:.0f}s: {last_error}"
    ) from last_error


def _upload_comfy_image(api_url: str, local_path: str) -> dict[str, Any]:
    """Upload a local image into ComfyUI's input dir via POST /upload/image.

    Needed for native i2v: LoadImage.image is a COMBO of files in ComfyUI's input
    directory, so an arbitrary local path can't be referenced directly -- the keyframe
    must live where Comfy can see it. Returns ComfyUI's RESPONSE descriptor
    {"name","subfolder","type"}; callers MUST use response["name"] (Comfy may rename
    on collision), never the basename sent. Mirrors _comfy_object_info hardening:
    Connection: close, retry, clear raise on failure (never a bogus name).
    """
    path = Path(local_path)
    if not path.is_file():
        raise RuntimeError(f"i2v input image not found on disk: {local_path}")
    data = path.read_bytes()
    filename = path.name

    attempts = 4
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            boundary = "----spellvision" + uuid.uuid4().hex
            body = bytearray()
            body += (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode("utf-8")
            body += data
            body += b"\r\n"
            for field, value in (("type", "input"), ("overwrite", "true")):
                body += (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'
                ).encode("utf-8")
            body += f"--{boundary}--\r\n".encode("utf-8")

            request = urllib.request.Request(
                f"{api_url}/upload/image",
                data=bytes(body),
                method="POST",
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(request, timeout=90) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            name = str((payload or {}).get("name") or "").strip()
            if not name:
                raise RuntimeError(f"ComfyUI /upload/image returned no name: {payload}")
            return {
                "name": name,
                "subfolder": str(payload.get("subfolder") or ""),
                "type": str(payload.get("type") or "input"),
            }
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(
        f"Failed to upload i2v input image to ComfyUI at {api_url} after {attempts} attempts: {last_error}"
    ) from last_error


def _comfy_image_ref(uploaded: dict[str, Any]) -> str:
    """ComfyUI LoadImage value for an uploaded asset: 'name', or 'subfolder/name'."""
    name = str(uploaded.get("name") or "").strip()
    subfolder = str(uploaded.get("subfolder") or "").strip().strip("/")
    return f"{subfolder}/{name}" if subfolder else name


def run_comfy_workflow(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    req = _ws().normalize_video_input_fields(req)
    transition_job(job, JobState.STARTING)
    emitter.status(job, "loading workflow profile")
    emitter.emit_job_update(job)
    runtime_prep = _ws().prepare_runtime_for_request(req, emitter, job)

    profile_path = str(req.get("profile_path") or req.get("workflow_profile_path") or "").strip()
    profile_payload = _ws()._load_json_file(profile_path) if profile_path else {}

    workflow_path = str(req.get("workflow_path") or profile_payload.get("workflow_source") or "").strip()
    if not workflow_path:
        raise RuntimeError("comfy_workflow requires workflow_path or profile_path")

    if workflow_path and not os.path.isabs(workflow_path) and profile_path:
        workflow_path = str((Path(profile_path).resolve().parent / workflow_path).resolve())

    workflow = _ws()._load_json_file(workflow_path)
    slot_bindings = profile_payload.get("slot_bindings") if isinstance(profile_payload, dict) else {}
    if not isinstance(slot_bindings, dict):
        slot_bindings = {}

    # The Comfy runtime must be up before we build the prompt: ComfyUI's /prompt accepts only the
    # API-prompt format, and converting a UI-graph export to it needs the live /object_info schema.
    transition_job(job, JobState.RUNNING)
    emitter.status(job, "preparing ComfyUI runtime")
    raise_if_cancelled(active_job, emitter, "workflow preparation")

    runtime_status = _ws().handle_ensure_comfy_runtime_command(req)
    if not runtime_status.get("healthy"):
        raise RuntimeError(runtime_status.get("message") or "Managed Comfy runtime is not ready")

    api_url = str(
        req.get("comfy_api_url")
        or runtime_status.get("endpoint")
        or os.environ.get("COMFY_API_URL")
        or "http://127.0.0.1:8188"
    ).rstrip("/")

    # object_info (the live /object_info schema) is needed to convert a UI-graph and, on every launch, to
    # normalize model-file names to ComfyUI's exact catalogued strings (a workflow's baked-in ckpt/lora
    # names are routinely bare or subfolder-relative and would fail /prompt validation). Fetch it once.
    object_info: dict[str, Any] | None = None
    try:
        object_info = _comfy_object_info(api_url)
    except Exception as exc:
        # A UI-graph cannot be submitted without the schema; an API-prompt graph can still try as-is.
        if is_ui_graph(workflow):
            raise
        log.warning("comfy_workflow: /object_info unavailable (%s); submitting graph without name normalization", exc)

    # A ComfyUI *UI-graph* export ({"nodes": [...], "links": [...]}, what Save produces and what nearly
    # every community workflow ships as) is rejected by /prompt (HTTP 500). Convert it to API-prompt
    # form using the live schema. This also makes the graph's model inputs bindable -- they become the
    # named `inputs` dict the slot logic reads -- so we can substitute a model even when the import-time
    # scan (which never sees /object_info) produced no bindings.
    if is_ui_graph(workflow):
        emitter.status(job, "converting workflow graph to ComfyUI prompt format")
        assert object_info is not None  # fetched above (and re-raised on failure) whenever is_ui_graph
        workflow = convert_ui_graph_to_api_prompt(workflow, object_info)
        if not slot_bindings:
            slot_bindings = _derive_checkpoint_slot_bindings(workflow)

    _apply_workflow_slot_bindings(workflow, slot_bindings, req, object_info)
    _apply_common_comfy_overrides(workflow, req, object_info)

    # A substitute the user explicitly chose for a model they do not have (the tier-3/tier-4 offer).
    # Applied BEFORE name normalization so the replacement itself gets resolved to the catalog, and
    # reported at WARNING so "wanted X, ran Y" is in the log of the run that produced the output --
    # a substitution nobody can see afterwards is indistinguishable from the wrong model loading.
    requested_substitutions = req.get("model_substitutions")
    if isinstance(requested_substitutions, dict) and requested_substitutions:
        applied_substitutions = apply_model_substitutions(workflow, requested_substitutions)
        for entry in applied_substitutions:
            log.warning(
                "comfy_workflow: model substituted -- node %s.%s wanted %r, running %r",
                entry["node_id"], entry["input"], entry["wanted"], entry["used"],
            )
            emitter.status(job, f"substituted {entry['wanted']} -> {entry['used']}")
        unmatched = [
            name for name in requested_substitutions
            if not any(_normalized_model_name(e["wanted"]) == _normalized_model_name(name)
                       for e in applied_substitutions)
        ]
        if unmatched:
            # Do not launch a graph that still references a model the user just told us they do not
            # have. It would either fail validation or, worse, resolve to something else.
            raise RuntimeError(
                "Requested model substitution did not match anything in the graph: "
                + ", ".join(sorted(unmatched))
            )

    # Normalize every model-file input (baked-in AND just-substituted) to ComfyUI's exact catalogued name.
    _resolve_graph_model_names(workflow, object_info)
    # Absorb node/input renames from a ComfyUI update. Same idea as the line above, one level up:
    # that one reconciles model FILE names against the live catalog, this one reconciles node and
    # input IDENTITY. Every rewrite is validated against the live schema, so it is a no-op on a
    # core that still defines what the builder named.
    for note in apply_node_aliases(workflow, object_info):
        log.warning("comfy_workflow: node alias applied -- %s", note)
    missing_classes = unresolved_classes(workflow, object_info)
    if missing_classes:
        # Fail with the actual cause instead of letting /prompt answer with a generic validation
        # error that does not name the node.
        raise RuntimeError(
            "ComfyUI does not provide these node classes: "
            + ", ".join(missing_classes)
            + ". Install the custom node pack that supplies them, or add a rename to "
              "python/comfy_node_aliases.json."
        )

    # Debug: write the submitted (post-conversion, post-substitution) workflow graph next to the output
    # so a launch's graph -- including any model/lora slot substitution applied above -- is inspectable,
    # mirroring the native video path's debug dump. Best-effort; never blocks the launch.
    try:
        _write_native_prompt_debug_file(_native_prompt_debug_path(req, job.job_id), workflow)
    except Exception:
        pass

    emitter.status(job, "submitting prompt to ComfyUI")
    start = time.perf_counter()
    prompt_id = _submit_comfy_prompt(api_url, workflow)
    emitter.status(job, f"ComfyUI prompt submitted: {prompt_id}")

    history = _poll_comfy_history(api_url, prompt_id, req, emitter, job, active_job)
    asset = _extract_comfy_asset(history, ["videos", "gifs", "images", "audio"] if str(req.get("media_type") or req.get("workflow_media_type") or req.get("task_type") or req.get("command") or "").lower() in {"video", "t2v", "i2v"} else None)
    if asset is None:
        raise RuntimeError("ComfyUI completed but produced no output asset")

    output_path = str(req.get("output") or "").strip()
    if not output_path:
        filename = str(asset.get("filename") or f"comfy_{prompt_id}.png")
        output_path = str(Path.cwd() / filename)
    else:
        requested_suffix = Path(output_path).suffix
        asset_suffix = Path(str(asset.get("filename") or "")).suffix
        if requested_suffix and asset_suffix and requested_suffix.lower() != asset_suffix.lower():
            output_path = str(Path(output_path).with_suffix(asset_suffix))
    output_path = _download_comfy_asset(api_url, asset, output_path)
    elapsed = time.perf_counter() - start
    steps_per_sec = float(req.get("steps") or 0) / elapsed if elapsed > 0 and req.get("steps") else 0.0

    metadata_output = str(req.get("metadata_output") or "").strip()
    req["comfy_asset_kind"] = str(asset.get("_asset_kind") or "")
    req["media_type"] = _ws().output_media_type_for_metadata(req, output_path)
    metadata_payload = _ws().save_metadata(
        req=req,
        image_path=output_path,
        metadata_output=metadata_output,
        backend_name="ComfyUI",
        device="external",
        dtype="n/a",
        detected_pipeline=str(profile_payload.get("profile_name") or Path(workflow_path).stem),
        lora_used=bool(req.get("lora")),
        elapsed=elapsed,
        steps_per_sec=steps_per_sec,
        job=job,
        cache_hit=False,
        model_swap_cleanup=None,
        lora_cache_hit=False,
        lora_reloaded=False,
        queue_warm_reuse_expected=bool(req.get("queue_warm_reuse_expected")),
        queue_warm_reuse_source=req.get("queue_warm_reuse_source"),
        queue_affinity_signature=req.get("queue_affinity_signature"),
    )

    payload = {
        "ok": True,
        "cache_hit": False,
        "output": output_path,
        "output_path": output_path,
        "media_type": _ws().output_media_type_for_metadata(req, output_path),
        "video_path": output_path if _ws().output_media_type_for_metadata(req, output_path) == "video" else "",
        "metadata_output": metadata_output,
        "backend_name": "ComfyUI",
        "detected_pipeline": str(profile_payload.get("profile_name") or Path(workflow_path).stem),
        "task_type": req.get("task_type", req.get("workflow_task_command", "comfy_workflow")),
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cuda_allocated_gb": 0.0,
        "cuda_reserved_gb": 0.0,
        "workflow_profile_name": profile_payload.get("profile_name"),
        "workflow_profile_path": profile_path,
        "workflow_media_output": output_path,
        "asset_kind": str(asset.get("_asset_kind") or ""),
        "workflow_path": workflow_path,
        "prompt_id": prompt_id,
        "metadata": metadata_payload,
        "metadata_write_deferred": False,
        **_ws().output_finalization_contract(output_path if 'output_path' in locals() else req.get("output"), metadata_output if 'metadata_output' in locals() else req.get("metadata_output"), original_output=str(req.get("original_output") or ""), media_type=_ws().output_media_type_for_metadata(req, output_path if 'output_path' in locals() else req.get("output")), metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"), metadata_write_error=metadata_payload.get("metadata_write_error")),
        **_ws().runtime_prep_metadata(req),
        "comfy_runtime_endpoint": runtime_status.get("endpoint"),
        "comfy_runtime_pid": runtime_status.get("pid"),
    }

    payload.update(_ws().video_completion_diagnostics(
        req,
        backend_type="comfy_workflow",
        backend_name="ComfyUI",
        output_path=output_path,
        metadata_output=metadata_output,
        prompt_id=prompt_id,
    ))
    video_cache_update = _ws().update_video_runtime_cache_from_result(req, payload)
    if video_cache_update:
        payload["video_runtime_cache_updated"] = True
        payload["video_runtime_cache"] = video_cache_update
    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload

