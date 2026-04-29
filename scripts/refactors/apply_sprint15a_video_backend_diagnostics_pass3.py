from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]


def fail(message: str) -> None:
    print(f"[sprint15a-pass3] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: Path) -> str:
    if not path.exists():
        fail(f"Missing file: {path}")
    return path.read_text(encoding="utf-8")


def write_if_changed(path: Path, text: str) -> bool:
    old = read(path)
    if old == text:
        return False
    path.write_text(text, encoding="utf-8", newline="")
    return True


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        fail(f"Could not find patch target for {label}")
    return text.replace(old, new, 1)


def function_bounds(text: str, function_name: str) -> tuple[int, int] | None:
    match = re.search(rf"^def\s+{re.escape(function_name)}\s*\(", text, flags=re.MULTILINE)
    if not match:
        return None
    start = match.start()
    next_match = re.search(r"^def\s+\w+\s*\(", text[match.end():], flags=re.MULTILINE)
    if not next_match:
        return start, len(text)
    return start, match.end() + next_match.start()


def patch_function(text: str, function_name: str, patcher) -> str:
    bounds = function_bounds(text, function_name)
    if bounds is None:
        return text
    start, end = bounds
    original = text[start:end]
    patched = patcher(original)
    return text[:start] + patched + text[end:]


def patch_generation_request_builder() -> bool:
    path = ROOT / "qt_ui" / "generation" / "GenerationRequestBuilder.cpp"
    text = read(path)
    if "video_input_image" in text:
        return False

    old = """    if (draft.isImageInputMode)\n    {\n        payload.insert(QStringLiteral(\"input_image\"), draft.inputImage);\n        payload.insert(QStringLiteral(\"denoise_strength\"), draft.denoiseStrength);\n        payload.insert(QStringLiteral(\"strength\"), draft.denoiseStrength);\n    }\n"""
    new = """    if (draft.isImageInputMode)\n    {\n        payload.insert(QStringLiteral(\"input_image\"), draft.inputImage);\n        if (draft.isVideoMode)\n        {\n            payload.insert(QStringLiteral(\"video_input_image\"), draft.inputImage);\n            payload.insert(QStringLiteral(\"input_keyframe\"), draft.inputImage);\n            payload.insert(QStringLiteral(\"keyframe_image\"), draft.inputImage);\n            payload.insert(QStringLiteral(\"source_image\"), draft.inputImage);\n        }\n        payload.insert(QStringLiteral(\"denoise_strength\"), draft.denoiseStrength);\n        payload.insert(QStringLiteral(\"strength\"), draft.denoiseStrength);\n    }\n"""
    return write_if_changed(path, replace_once(text, old, new, "GenerationRequestBuilder I2V input aliases"))


VIDEO_HELPERS = r'''

def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _video_request_command(req: dict[str, Any]) -> str:
    return str(
        req.get("command")
        or req.get("task_command")
        or req.get("task_type")
        or req.get("workflow_task_command")
        or ""
    ).strip().lower()


def _first_nonempty_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def is_video_request(req: dict[str, Any], output_path: str | None = None) -> bool:
    command = _video_request_command(req)
    media_type = str(req.get("workflow_media_type") or req.get("media_type") or "").strip().lower()
    stack_kind = str(req.get("native_video_stack_kind") or req.get("video_stack_kind") or "").strip().lower()
    output = str(output_path or req.get("output") or req.get("workflow_media_output") or "").strip().lower()
    return (
        command in {"t2v", "i2v"}
        or media_type == "video"
        or bool(stack_kind)
        or output.endswith((".mp4", ".mov", ".webm", ".mkv", ".avi", ".gif"))
    )


def video_duration_label(frames: int, fps: int) -> str:
    if frames <= 0 or fps <= 0:
        return "unknown"
    seconds = float(frames) / float(fps)
    return f"{frames} frames @ {fps} fps ({seconds:.1f}s)"


def video_input_image_for_request(req: dict[str, Any]) -> str:
    return _first_nonempty_text(
        req.get("video_input_image"),
        req.get("input_keyframe"),
        req.get("keyframe_image"),
        req.get("source_image"),
        req.get("input_image"),
    )


def video_completion_diagnostics(
    req: dict[str, Any],
    *,
    backend_type: str,
    backend_name: str,
    output_path: str | None = None,
    metadata_output: str | None = None,
    prompt_id: str | None = None,
) -> dict[str, Any]:
    if not is_video_request(req, output_path):
        return {}

    stack = req.get("video_model_stack") or req.get("model_stack") or {}
    if not isinstance(stack, dict):
        stack = {}

    frames = _safe_int(req.get("frames") or req.get("num_frames") or req.get("frame_count"), 0)
    fps = _safe_int(req.get("fps"), 0)
    duration_seconds = round(float(frames) / float(fps), 3) if frames > 0 and fps > 0 else 0.0
    stack_kind = _first_nonempty_text(
        req.get("native_video_stack_kind"),
        req.get("video_stack_kind"),
        stack.get("stack_kind"),
        stack.get("stack_mode"),
    )
    stack_mode = _first_nonempty_text(req.get("video_stack_mode"), stack.get("stack_mode"), stack_kind)
    input_image = video_input_image_for_request(req)
    output = _first_nonempty_text(output_path, req.get("output"), req.get("workflow_media_output"))
    metadata_path = _first_nonempty_text(metadata_output, req.get("metadata_output"))
    request_kind = _video_request_command(req) or "video"

    return {
        "video_backend_type": backend_type,
        "video_backend_name": backend_name,
        "video_output": output,
        "video_metadata_output": metadata_path,
        "video_request_kind": request_kind,
        "video_stack_kind": stack_kind,
        "video_stack_mode": stack_mode,
        "video_stack_ready": bool(req.get("video_stack_ready", stack.get("stack_ready", False))),
        "video_frames": frames,
        "video_fps": fps,
        "video_duration_seconds": duration_seconds,
        "video_duration_label": video_duration_label(frames, fps),
        "video_has_input_image": bool(input_image),
        "video_input_image": input_image,
        "video_prompt_id": prompt_id or "",
    }


def comfy_waiting_message(req: dict[str, Any], elapsed_seconds: float) -> str:
    if is_video_request(req):
        frames = _safe_int(req.get("frames") or req.get("num_frames") or req.get("frame_count"), 0)
        fps = _safe_int(req.get("fps"), 0)
        timing = video_duration_label(frames, fps)
        stack_kind = _first_nonempty_text(
            req.get("native_video_stack_kind"),
            req.get("video_stack_kind"),
            (req.get("video_model_stack") or {}).get("stack_kind") if isinstance(req.get("video_model_stack"), dict) else "",
        )
        stack_text = f" • {stack_kind}" if stack_kind else ""
        return f"waiting for ComfyUI video render ({int(elapsed_seconds)}s • {timing}{stack_text})"
    return f"waiting for ComfyUI ({int(elapsed_seconds)}s)"
'''


JOB_RESULT_FIELDS = """    video_backend_type: str | None = None\n    video_backend_name: str | None = None\n    video_output: str | None = None\n    video_metadata_output: str | None = None\n    video_request_kind: str | None = None\n    video_stack_kind: str | None = None\n    video_stack_mode: str | None = None\n    video_stack_ready: bool = False\n    video_frames: int = 0\n    video_fps: int = 0\n    video_duration_seconds: float = 0.0\n    video_duration_label: str | None = None\n    video_has_input_image: bool = False\n    video_input_image: str | None = None\n    video_prompt_id: str | None = None\n"""

JOB_RESULT_ASSIGNMENTS = """        video_backend_type=payload.get(\"video_backend_type\"),\n        video_backend_name=payload.get(\"video_backend_name\"),\n        video_output=payload.get(\"video_output\"),\n        video_metadata_output=payload.get(\"video_metadata_output\"),\n        video_request_kind=payload.get(\"video_request_kind\"),\n        video_stack_kind=payload.get(\"video_stack_kind\"),\n        video_stack_mode=payload.get(\"video_stack_mode\"),\n        video_stack_ready=bool(payload.get(\"video_stack_ready\", False)),\n        video_frames=int(payload.get(\"video_frames\") or 0),\n        video_fps=int(payload.get(\"video_fps\") or 0),\n        video_duration_seconds=float(payload.get(\"video_duration_seconds\") or 0.0),\n        video_duration_label=payload.get(\"video_duration_label\"),\n        video_has_input_image=bool(payload.get(\"video_has_input_image\", False)),\n        video_input_image=payload.get(\"video_input_image\"),\n        video_prompt_id=payload.get(\"video_prompt_id\"),\n"""


def patch_worker_service() -> bool:
    path = ROOT / "python" / "worker_service.py"
    text = read(path)
    original = text

    if "def video_completion_diagnostics(" not in text:
        marker = "def cuda_memory_snapshot() -> dict[str, float]:\n"
        text = replace_once(text, marker, VIDEO_HELPERS + "\n\n" + marker, "video diagnostics helpers")

    if "video_backend_type: str | None = None" not in text:
        text = replace_once(
            text,
            "    retry_count: int = 0\n\n\n@dataclass\nclass JobTimestamps:",
            "    retry_count: int = 0\n" + JOB_RESULT_FIELDS + "\n\n@dataclass\nclass JobTimestamps:",
            "JobResult video fields",
        )

    if "video_backend_type=payload.get(\"video_backend_type\")" not in text:
        text = replace_once(
            text,
            "        retry_count=int(payload.get(\"retry_count\") or 0),\n    )\n",
            "        retry_count=int(payload.get(\"retry_count\") or 0),\n" + JOB_RESULT_ASSIGNMENTS + "    )\n",
            "complete_job video assignments",
        )

    text = text.replace(
        'emitter.progress(job, min(95, max(1, tick)), 100, f"waiting for ComfyUI ({int(elapsed)}s)")',
        'emitter.progress(job, min(95, max(1, tick)), 100, comfy_waiting_message(req, elapsed))',
    )

    def patch_comfy(func_text: str) -> str:
        if "backend_type=\"comfy_workflow\"" in func_text:
            return func_text
        old = "    complete_job(job, payload)\n"
        new = """    payload.update(video_completion_diagnostics(\n        req,\n        backend_type=\"comfy_workflow\",\n        backend_name=\"ComfyUI\",\n        output_path=output_path,\n        metadata_output=metadata_output,\n        prompt_id=prompt_id,\n    ))\n    complete_job(job, payload)\n"""
        if old not in func_text:
            return func_text
        return func_text.replace(old, new, 1)

    text = patch_function(text, "run_comfy_workflow", patch_comfy)

    def patch_native(func_text: str) -> str:
        if "backend_type=\"native_video\"" in func_text:
            return func_text
        old = "    complete_job(job, payload)\n"
        new = """    payload.update(video_completion_diagnostics(\n        req,\n        backend_type=\"native_video\",\n        backend_name=str(payload.get(\"backend_name\") or \"Native Video\"),\n        output_path=str(payload.get(\"output\") or req.get(\"output\") or \"\"),\n        metadata_output=str(payload.get(\"metadata_output\") or req.get(\"metadata_output\") or \"\"),\n    ))\n    complete_job(job, payload)\n"""
        if old not in func_text:
            return func_text
        return func_text.replace(old, new, 1)

    text = patch_function(text, "run_native_video", patch_native)

    return write_if_changed(path, text) or (text != original)


def main() -> None:
    changed = []
    if patch_generation_request_builder():
        changed.append("qt_ui/generation/GenerationRequestBuilder.cpp")
    if patch_worker_service():
        changed.append("python/worker_service.py")

    if changed:
        print("[sprint15a-pass3] patched:")
        for item in changed:
            print(f"  - {item}")
    else:
        print("[sprint15a-pass3] no changes needed; pass already applied")


if __name__ == "__main__":
    main()
