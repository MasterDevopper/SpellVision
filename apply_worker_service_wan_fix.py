from __future__ import annotations

import re
import sys
from pathlib import Path

TARGET = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("python/worker_service.py")


def die(message: str) -> None:
    raise SystemExit(f"[worker_service patch] {message}")


def insert_before_once(text: str, marker: str, block: str, anchor: str) -> str:
    if anchor in text:
        return text
    index = text.find(marker)
    if index < 0:
        die(f"Could not find insertion marker: {marker[:80]!r}")
    return text[:index] + block.rstrip() + "\n\n" + text[index:]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        die(f"Expected exactly one match for {label}, found {count}")
    return text.replace(old, new, 1)


def replace_last(text: str, old: str, new: str, label: str) -> str:
    index = text.rfind(old)
    if index < 0:
        die(f"Could not find last match for {label}")
    return text[:index] + new + text[index + len(old):]


def replace_regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL | re.MULTILINE)
    if count != 1:
        die(f"Expected exactly one regex match for {label}, found {count}")
    return new_text


def main() -> None:
    if not TARGET.exists():
        die(f"Target file not found: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")

    # Safety gate: this patch is for the current video-capable worker, not the older image-only worker.
    required_tokens = [
        "def run_native_video(",
        "def run_native_split_stack_video(",
        "def _build_native_wan_core_video_prompt(",
        "def _build_native_wan_split_video_prompt(",
    ]
    for token in required_tokens:
        if token not in text:
            die(
                f"This worker_service.py does not contain {token!r}. "
                "Refusing to patch because this looks like an older/non-video worker."
            )

    backup = TARGET.with_suffix(TARGET.suffix + ".pre_wan_fix.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")

    metadata_helpers = r'''
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".gif"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _output_media_type(req: dict[str, Any], output_path: str | None) -> str:
    explicit = str(
        req.get("resolved_media_type")
        or req.get("media_type")
        or req.get("workflow_media_type")
        or ""
    ).strip().lower()
    if explicit in {"video", "image", "audio"}:
        return explicit

    command = str(req.get("task_type") or req.get("command") or req.get("workflow_task_command") or "").strip().lower()
    if command in {"t2v", "i2v", "v2v", "ti2v"}:
        return "video"

    suffix = Path(str(output_path or "")).suffix.lower()
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    return explicit or "image"


def _final_metadata_state(job: "JobRecord | None", output_path: str | None) -> str:
    if job is None:
        return "completed"

    state = job.state.value
    if state in {"queued", "starting", "running"} and output_path and os.path.exists(str(output_path)):
        return "completed"
    return state


def _final_metadata_timestamps(job: "JobRecord | None", output_path: str | None) -> dict[str, Any] | None:
    if job is None:
        now = utc_now_iso()
        return {
            "created_at": now,
            "started_at": now,
            "finished_at": now,
            "updated_at": now,
        }

    payload = asdict(job.timestamps)
    if _final_metadata_state(job, output_path) == "completed" and not payload.get("finished_at"):
        now = utc_now_iso()
        payload["finished_at"] = now
        payload["updated_at"] = now
    return payload
'''
    text = insert_before_once(
        text,
        "def build_metadata_payload(\n",
        metadata_helpers,
        "def _final_metadata_state(job:",
    )

    old = '''        "image_path": image_path,
        "metadata_output": metadata_output,
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cache_hit": cache_hit,
        "job_id": job.job_id if job else req.get("job_id"),
        "state": job.state.value if job else "completed",
        "timestamps": asdict(job.timestamps) if job else None,
'''
    new = '''        "image_path": image_path,
        "output_path": image_path,
        "video_path": image_path if _output_media_type(req, image_path) == "video" else "",
        "media_type": _output_media_type(req, image_path),
        "metadata_output": metadata_output,
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cache_hit": cache_hit,
        "job_id": job.job_id if job else req.get("job_id"),
        "state": _final_metadata_state(job, image_path),
        "timestamps": _final_metadata_timestamps(job, image_path),
'''
    if '"output_path": image_path,' not in text:
        text = replace_once(text, old, new, "metadata output/state/timestamps fields")

    old = '''@dataclass
class JobResult:
    output: str | None = None
    cache_hit: bool = False
'''
    new = '''@dataclass
class JobResult:
    output: str | None = None
    output_path: str | None = None
    media_type: str | None = None
    video_path: str | None = None
    workflow_media_output: str | None = None
    asset_kind: str | None = None
    cache_hit: bool = False
'''
    if "output_path: str | None = None" not in text[text.find("class JobResult:"):text.find("class JobTimestamps:")]:
        text = replace_once(text, old, new, "JobResult media fields")

    old = '''def complete_job(job: JobRecord, payload: dict[str, Any]) -> None:
    job.result = JobResult(
        output=payload.get("output"),
        cache_hit=bool(payload.get("cache_hit", False)),
        generation_time_sec=payload.get("generation_time_sec"),
'''
    new = '''def complete_job(job: JobRecord, payload: dict[str, Any]) -> None:
    output_path = payload.get("output_path") or payload.get("output")
    media_type = str(payload.get("media_type") or _output_media_type({}, output_path)).strip() or None
    video_path = payload.get("video_path") or (output_path if media_type == "video" else None)
    job.result = JobResult(
        output=payload.get("output") or output_path,
        output_path=output_path,
        media_type=media_type,
        video_path=video_path,
        workflow_media_output=payload.get("workflow_media_output"),
        asset_kind=payload.get("asset_kind"),
        cache_hit=bool(payload.get("cache_hit", False)),
        generation_time_sec=payload.get("generation_time_sec"),
'''
    if "output_path = payload.get(\"output_path\")" not in text:
        text = replace_once(text, old, new, "complete_job media result contract")

    stack_helpers = r'''
def _stack_path_value(stack: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(stack.get(key) or "").strip()
        if value:
            return value
    return ""


def _normalized_path_text(value: Any) -> str:
    return str(value or "").replace("\\", "/").lower()


def _path_looks_high_noise(path_value: Any) -> bool:
    value = _normalized_path_text(path_value)
    return any(token in value for token in ("high_noise", "high-noise", "high noise", "t2v_high", "_high_"))


def _path_looks_low_noise(path_value: Any) -> bool:
    value = _normalized_path_text(path_value)
    return any(token in value for token in ("low_noise", "low-noise", "low noise", "t2v_low", "_low_"))


def _path_looks_wan22(path_value: Any) -> bool:
    value = _normalized_path_text(path_value)
    return any(token in value for token in ("wan2.2", "wan_2.2", "wan-2.2", "wan22"))


def _infer_stack_family_from_paths(stack: dict[str, Any]) -> str:
    explicit = str(stack.get("family") or stack.get("model_family") or stack.get("video_family") or "").strip().lower().replace("-", "_")
    if explicit:
        return explicit

    haystack = " ".join(str(value or "") for value in stack.values()).lower().replace("\\", "/")
    if any(marker in haystack for marker in ("wan", "wan2", "wan_2", "wan-2")):
        return "wan"
    if any(marker in haystack for marker in ("ltx", "ltxv")):
        return "ltx"
    if any(marker in haystack for marker in ("hunyuan", "hyvideo")):
        return "hunyuan_video"
    return explicit or "unknown"


def _wan_stack_requires_dual_noise(stack: dict[str, Any]) -> bool:
    family = _infer_stack_family_from_paths(stack)
    if family != "wan":
        return False

    stack_kind = str(stack.get("stack_kind") or stack.get("native_video_stack_kind") or stack.get("role") or "").strip().lower()
    if stack_kind in {"wan_dual_noise", "wan_split_stack", "wan2_2_split_stack", "wan2.2_split_stack", "split_stack"}:
        return True

    high = _stack_path_value(stack, "high_noise_path", "high_noise_model_path", "wan_high_noise_path", "high_noise")
    low = _stack_path_value(stack, "low_noise_path", "low_noise_model_path", "wan_low_noise_path", "low_noise")
    primary = _stack_path_value(stack, "primary_path", "transformer_path", "unet_path", "model_path", "model")
    return bool(high or low or _path_looks_high_noise(primary) or _path_looks_low_noise(primary) or _path_looks_wan22(primary))


def _is_wan_dual_noise_stack(stack: dict[str, Any]) -> bool:
    return _wan_stack_requires_dual_noise(stack)


def normalize_wan_video_stack(stack: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(stack or {})
    if not normalized:
        return normalized

    family = _infer_stack_family_from_paths(normalized)
    if family != "wan":
        return normalized

    normalized["family"] = "wan"
    normalized["model_family"] = "wan"
    normalized["video_family"] = "wan"

    if not _wan_stack_requires_dual_noise(normalized):
        return normalized

    primary = _stack_path_value(normalized, "primary_path", "transformer_path", "unet_path", "model_path", "model")
    high = _stack_path_value(normalized, "high_noise_path", "high_noise_model_path", "wan_high_noise_path", "high_noise")
    low = _stack_path_value(normalized, "low_noise_path", "low_noise_model_path", "wan_low_noise_path", "low_noise")

    if not high and _path_looks_high_noise(primary):
        high = primary
    if not low and _path_looks_low_noise(primary):
        low = primary

    normalized["stack_kind"] = "wan_dual_noise"
    normalized["native_video_stack_kind"] = "wan_dual_noise"
    normalized["high_noise_path"] = high
    normalized["low_noise_path"] = low
    normalized["high_noise_model_path"] = high
    normalized["low_noise_model_path"] = low
    normalized["wan_high_noise_path"] = high
    normalized["wan_low_noise_path"] = low

    if low:
        normalized["primary_path"] = low
        normalized["transformer_path"] = low
        normalized["unet_path"] = low
        normalized["model_path"] = low

    missing: list[str] = []
    if not high:
        missing.append("high noise model")
    if not low:
        missing.append("low noise model")
    if not _stack_path_value(normalized, "text_encoder_path", "text_encoder", "clip_path", "clip"):
        missing.append("text encoder")
    if not _stack_path_value(normalized, "vae_path", "vae"):
        missing.append("vae")

    normalized["missing_parts"] = missing
    normalized["stack_ready"] = not missing
    return normalized


def _sync_video_model_stack_to_request(req: dict[str, Any]) -> dict[str, Any]:
    stack = _video_model_stack_from_request(req)
    if stack:
        req["video_model_stack"] = stack
        req["model_stack"] = stack
        if not str(req.get("model") or "").strip():
            model_path = _stack_path_value(stack, "primary_path", "transformer_path", "unet_path", "model_path")
            if model_path:
                req["model"] = model_path
    return stack
'''
    text = insert_before_once(
        text,
        "def _video_model_stack_from_request(req: dict[str, Any]) -> dict[str, Any]:\n",
        stack_helpers,
        "def normalize_wan_video_stack(stack:",
    )

    old = '''def _video_model_stack_from_request(req: dict[str, Any]) -> dict[str, Any]:
    raw = req.get("video_model_stack") or req.get("model_stack") or {}
    return dict(raw) if isinstance(raw, dict) else {}
'''
    new = '''def _video_model_stack_from_request(req: dict[str, Any]) -> dict[str, Any]:
    raw = req.get("video_model_stack") or req.get("model_stack") or {}
    return normalize_wan_video_stack(dict(raw)) if isinstance(raw, dict) else {}
'''
    if "return normalize_wan_video_stack" not in text[text.find("def _video_model_stack_from_request"):text.find("def _first_stack_value")]:
        text = replace_once(text, old, new, "video stack normalization entrypoint")

    text = replace_regex_once(
        text,
        r'def _stack_summary\(stack: dict\[str, Any\]\) -> str:\n.*?\n\ndef _native_video_model_reference',
        '''def _stack_summary(stack: dict[str, Any]) -> str:
    if not stack:
        return "no video model stack"
    family = str(stack.get("family") or "unknown").strip()
    kind = str(stack.get("stack_kind") or stack.get("role") or "stack").strip()
    primary = _first_stack_value(stack, ("diffusers_path", "primary_path", "transformer_path", "unet_path", "model_path"))
    high = _stack_path_value(stack, "high_noise_path", "high_noise_model_path", "wan_high_noise_path")
    low = _stack_path_value(stack, "low_noise_path", "low_noise_model_path", "wan_low_noise_path")
    missing = _stack_missing_parts(stack)
    bits = [f"family={family}", f"kind={kind}"]
    if primary:
        bits.append(f"primary={primary}")
    if high:
        bits.append(f"high_noise={high}")
    if low:
        bits.append(f"low_noise={low}")
    if missing:
        bits.append("missing=" + ", ".join(missing))
    return "; ".join(bits)


def _native_video_model_reference''',
        "stack summary high/low display",
    )

    old = '''def _is_split_video_stack_request(req: dict[str, Any]) -> bool:
    stack = _video_model_stack_from_request(req)
    stack_kind = str(stack.get("stack_kind") or req.get("native_video_stack_kind") or "").strip().lower()
    if stack_kind == "split_stack":
        return True
    model_ref = _native_video_model_reference(req)
    return Path(model_ref).suffix.lower() in {".safetensors", ".ckpt", ".bin", ".gguf"}
'''
    new = '''def _is_split_video_stack_request(req: dict[str, Any]) -> bool:
    stack = _video_model_stack_from_request(req)
    stack_kind = str(stack.get("stack_kind") or req.get("native_video_stack_kind") or "").strip().lower()
    if stack_kind in {"split_stack", "wan_dual_noise", "wan_split_stack", "native_split_stack"}:
        return True
    if _is_wan_dual_noise_stack(stack):
        return True
    model_ref = _native_video_model_reference(req)
    return Path(model_ref).suffix.lower() in {".safetensors", ".ckpt", ".bin", ".gguf"}
'''
    if "wan_dual_noise" not in text[text.find("def _is_split_video_stack_request"):text.find("def _comfy_object_info")]:
        text = replace_once(text, old, new, "split-stack detection")

    dual_helper = r'''
def _set_wan_dual_noise_inputs_or_raise(
    inputs: dict[str, Any],
    allowed: set[str],
    object_info: dict[str, Any],
    class_name: str,
    stack: dict[str, Any],
) -> bool:
    if not _is_wan_dual_noise_stack(stack):
        return False

    missing = _stack_missing_parts(stack)
    if missing:
        raise RuntimeError(
            "WAN native video stack is incomplete. Missing: "
            + ", ".join(missing)
            + ". Select both high-noise and low-noise models, plus text encoder and VAE."
        )

    high_path = _stack_path_value(stack, "high_noise_path", "high_noise_model_path", "wan_high_noise_path")
    low_path = _stack_path_value(stack, "low_noise_path", "low_noise_model_path", "wan_low_noise_path")
    high_name = _sv_choose_comfy_choice(object_info, class_name, "model", _comfy_unet_name(high_path))
    low_name = _sv_choose_comfy_choice(object_info, class_name, "model", _comfy_unet_name(low_path))

    high_set = _set_if_allowed(
        inputs,
        allowed,
        ("high_noise_model", "high_noise_model_name", "high_noise_unet_name", "high_unet_name", "unet_name_high", "model_high", "high_model"),
        high_name,
    )
    low_set = _set_if_allowed(
        inputs,
        allowed,
        ("low_noise_model", "low_noise_model_name", "low_noise_unet_name", "low_unet_name", "unet_name_low", "model_low", "low_model"),
        low_name,
    )

    if high_set and low_set:
        return True

    available = ", ".join(sorted(allowed)) or "<no inputs reported by /object_info>"
    raise RuntimeError(
        "The active native WAN template does not expose separate high/low-noise model inputs. "
        f"Loader class {class_name!r} exposes: {available}. "
        "Use an imported Wan 2.2 workflow that already wires both models, or update SpellVision's native Wan template adapter to a dual-noise graph."
    )
'''
    text = insert_before_once(
        text,
        "def _build_native_wan_core_video_prompt(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str) -> dict[str, Any]:\n",
        dual_helper,
        "def _set_wan_dual_noise_inputs_or_raise(",
    )

    old = '''    unet_class = _first_available_class(object_info, ("UNETLoader",), label="WAN core diffusion model loading")
    allowed = _comfy_class_inputs(object_info, unet_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("unet_name", "model_name", "ckpt_name", "checkpoint"), _sv_video_primary_name(object_info, primary_path, class_name=unet_class))
    _set_if_allowed(inputs, allowed, ("weight_dtype",), _sv_core_choice_or_default(object_info, unet_class, "weight_dtype", req.get("weight_dtype"), "default"))
    _add_node(prompt, "4", unet_class, inputs)
'''
    new = '''    unet_class = _first_available_class(object_info, ("UNETLoader",), label="WAN core diffusion model loading")
    allowed = _comfy_class_inputs(object_info, unet_class)
    inputs = {}
    dual_noise_wired = _set_wan_dual_noise_inputs_or_raise(inputs, allowed, object_info, unet_class, stack)
    if not dual_noise_wired:
        _set_if_allowed(inputs, allowed, ("unet_name", "model_name", "ckpt_name", "checkpoint"), _sv_video_primary_name(object_info, primary_path, class_name=unet_class))
    _set_if_allowed(inputs, allowed, ("weight_dtype",), _sv_core_choice_or_default(object_info, unet_class, "weight_dtype", req.get("weight_dtype"), "default"))
    _add_node(prompt, "4", unet_class, inputs)
'''
    if "dual_noise_wired = _set_wan_dual_noise_inputs_or_raise(inputs, allowed, object_info, unet_class, stack)" not in text:
        text = replace_once(text, old, new, "WAN core dual-noise model loader gate")

    old = '''    stack = _video_model_stack_from_request(req)
    primary_path = _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path"))
    if not primary_path:
        raise RuntimeError("The selected WAN video stack has no primary diffusion model path.")
'''
    new = '''    stack = _video_model_stack_from_request(req)
    missing = _stack_missing_parts(stack)
    if missing:
        raise RuntimeError(
            "WAN native video stack is incomplete. Missing: "
            + ", ".join(missing)
            + ". Select both high-noise and low-noise models, plus text encoder and VAE."
        )
    primary_path = _first_stack_value(stack, ("low_noise_path", "primary_path", "transformer_path", "unet_path", "model_path"))
    if not primary_path:
        raise RuntimeError("The selected WAN video stack has no primary diffusion model path.")
'''
    text = replace_once(text, old, new, "WAN wrapper primary/missing validation")

    old = '''    model_class = _first_available_class(object_info, ("WanVideoModelLoader",), label="WAN video model loading")
    allowed = _comfy_class_inputs(object_info, model_class)
    inputs: dict[str, Any] = {}
    _set_if_allowed(inputs, allowed, ("model",), _sv_video_primary_name(object_info, primary_path, class_name=model_class))
    _set_if_allowed(inputs, allowed, ("base_precision",), str(req.get("base_precision") or "bf16"))
'''
    new = '''    model_class = _first_available_class(object_info, ("WanVideoModelLoader",), label="WAN video model loading")
    allowed = _comfy_class_inputs(object_info, model_class)
    inputs: dict[str, Any] = {}
    dual_noise_wired = _set_wan_dual_noise_inputs_or_raise(inputs, allowed, object_info, model_class, stack)
    if not dual_noise_wired:
        _set_if_allowed(inputs, allowed, ("model",), _sv_video_primary_name(object_info, primary_path, class_name=model_class))
    _set_if_allowed(inputs, allowed, ("base_precision",), str(req.get("base_precision") or "bf16"))
'''
    if "dual_noise_wired = _set_wan_dual_noise_inputs_or_raise(inputs, allowed, object_info, model_class, stack)" not in text:
        text = replace_once(text, old, new, "WAN wrapper dual-noise model loader gate")

    old = '''    if family_key.startswith("wan"):
        req["resolved_native_video_family"] = "wan"
        if _should_use_native_wan_core_route(req, object_info) and "CLIPLoader" in object_info and "KSamplerAdvanced" in object_info:
            req["native_video_route"] = "wan_core"
            return _build_native_wan_core_video_prompt(
                req,
                object_info,
                command=command,
                family=family,
                job_id=job_id,
            )
        if "WanVideoModelLoader" in object_info:
            req["native_video_route"] = "wan_wrapper"
            return _build_native_wan_split_video_prompt(
                req,
                object_info,
                command=command,
                family=family,
                job_id=job_id,
            )
'''
    new = '''    if family_key.startswith("wan"):
        req["resolved_native_video_family"] = "wan"
        stack = _video_model_stack_from_request(req)
        if _is_wan_dual_noise_stack(stack):
            if "WanVideoModelLoader" in object_info:
                req["native_video_route"] = "wan_wrapper_dual_noise"
                return _build_native_wan_split_video_prompt(
                    req,
                    object_info,
                    command=command,
                    family=family,
                    job_id=job_id,
                )
            raise RuntimeError(
                "The selected Wan 2.2 stack requires separate high/low-noise model inputs, "
                "but the active Comfy runtime does not expose a compatible WanVideoModelLoader. "
                "Use an imported Wan 2.2 workflow or install/enable the required Wan video nodes."
            )
        if _should_use_native_wan_core_route(req, object_info) and "CLIPLoader" in object_info and "KSamplerAdvanced" in object_info:
            req["native_video_route"] = "wan_core"
            return _build_native_wan_core_video_prompt(
                req,
                object_info,
                command=command,
                family=family,
                job_id=job_id,
            )
        if "WanVideoModelLoader" in object_info:
            req["native_video_route"] = "wan_wrapper"
            return _build_native_wan_split_video_prompt(
                req,
                object_info,
                command=command,
                family=family,
                job_id=job_id,
            )
'''
    if "wan_wrapper_dual_noise" not in text:
        text = replace_once(text, old, new, "WAN routing dual-noise branch")

    old = '''def run_native_split_stack_video(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    command = str(req.get("command") or req.get("task_type") or "").strip().lower()
    family = _infer_native_video_family(req)
'''
    new = '''def run_native_split_stack_video(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    _sync_video_model_stack_to_request(req)
    command = str(req.get("command") or req.get("task_type") or "").strip().lower()
    family = _infer_native_video_family(req)
'''
    if "def run_native_split_stack_video" in text and "_sync_video_model_stack_to_request(req)\n    command = str(req.get(\"command\")" not in text[text.find("def run_native_split_stack_video"):text.find("def _load_native_video_pipeline")]:
        text = replace_once(text, old, new, "run_native_split_stack_video stack sync")

    old = '''    object_info = _comfy_object_info(api_url)
    req = _prepare_native_video_adapter_request(req, object_info, command=command, family=family)

    family = str(req.get("resolved_native_video_family") or req.get("video_family") or req.get("model_family") or family)
'''
    new = '''    object_info = _comfy_object_info(api_url)
    req = _prepare_native_video_adapter_request(req, object_info, command=command, family=family)
    _sync_video_model_stack_to_request(req)

    family = str(req.get("resolved_native_video_family") or req.get("video_family") or req.get("model_family") or family)
'''
    if "req = _prepare_native_video_adapter_request(req, object_info, command=command, family=family)\n    _sync_video_model_stack_to_request(req)" not in text:
        text = replace_once(text, old, new, "adapter result stack resync")

    old = '''def run_native_video(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    command = str(req.get("command") or req.get("task_type") or "").strip().lower()
'''
    new = '''def run_native_video(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    _sync_video_model_stack_to_request(req)
    command = str(req.get("command") or req.get("task_type") or "").strip().lower()
'''
    if "def run_native_video" in text and "_sync_video_model_stack_to_request(req)\n    command = str(req.get(\"command\")" not in text[text.find("def run_native_video"):text.find("def run_comfy_workflow")]:
        text = replace_once(text, old, new, "run_native_video stack sync")

    if '"video_path": output_path if resolved_media_type == "video" else None,' not in text:
        text = replace_once(
            text,
            '''        "media_type": resolved_media_type,
        "asset_kind": "native_split_stack",
''',
            '''        "media_type": resolved_media_type,
        "video_path": output_path if resolved_media_type == "video" else None,
        "asset_kind": "native_split_stack",
''',
            "native split video_path payload",
        )

    if '"video_path": output_path,\n        "asset_kind": "native_video"' not in text:
        text = replace_once(
            text,
            '''        "media_type": "video",
        "asset_kind": "native_video",
''',
            '''        "media_type": "video",
        "video_path": output_path,
        "asset_kind": "native_video",
''',
            "native video video_path payload",
        )

    old = '''    output_path = _download_comfy_asset(api_url, asset, output_path)
    elapsed = time.perf_counter() - start
    steps_per_sec = float(req.get("steps") or 0) / elapsed if elapsed > 0 and req.get("steps") else 0.0

    metadata_output = str(req.get("metadata_output") or "").strip()
'''
    new = '''    output_path = _download_comfy_asset(api_url, asset, output_path)
    elapsed = time.perf_counter() - start
    steps_per_sec = float(req.get("steps") or 0) / elapsed if elapsed > 0 and req.get("steps") else 0.0
    asset_kind = str(asset.get("_asset_kind") or "").strip()
    resolved_media_type = "video" if asset_kind in {"videos", "gifs"} else ("audio" if asset_kind == "audio" else _output_media_type(req, output_path))
    req["resolved_media_type"] = resolved_media_type
    req["comfy_asset_kind"] = asset_kind or "asset"

    metadata_output = str(req.get("metadata_output") or "").strip() or str(Path(output_path).with_suffix(".json"))
'''
    if "resolved_media_type = \"video\" if asset_kind" not in text[text.find("def run_comfy_workflow"):text.find("def run_i2i")]:
        text = replace_once(text, old, new, "Comfy workflow media type resolution")

    old = '''        "output": output_path,
        "metadata_output": metadata_output,
        "backend_name": "ComfyUI",
'''
    new = '''        "output": output_path,
        "output_path": output_path,
        "media_type": resolved_media_type,
        "video_path": output_path if resolved_media_type == "video" else None,
        "metadata_output": metadata_output,
        "backend_name": "ComfyUI",
'''
    if '"backend_name": "ComfyUI"' in text and '"media_type": resolved_media_type,' not in text[text.find("def run_comfy_workflow"):text.find("def run_i2i")]:
        text = replace_last(text, old, new, "Comfy workflow result media fields")

    TARGET.write_text(text, encoding="utf-8")
    print(f"Patched {TARGET}")
    print(f"Backup: {backup}")


if __name__ == "__main__":
    main()
