from __future__ import annotations

from pathlib import Path
import sys

MARKER = "# --- SPELLVISION VIDEO METADATA FINALIZATION FIX V1 ---"

OVERRIDE_BLOCK = '\n# --- SPELLVISION VIDEO METADATA FINALIZATION FIX V1 ---\n# Normalizes completed video metadata after any image-first legacy payload construction.\n# This keeps T2V/I2V MP4/WebM/MOV/MKV outputs from being recorded as media_type=image.\n\n_spellvision_original_build_metadata_payload = build_metadata_payload\n\n\ndef _spellvision_media_type_from_output(req: dict[str, Any], output_path: str) -> str:\n    explicit = str(req.get("resolved_media_type") or req.get("media_type") or req.get("workflow_media_type") or "").strip().lower()\n    suffix = Path(str(output_path or "")).suffix.lower()\n    task = str(req.get("task_type") or req.get("command") or req.get("workflow_task_command") or "").strip().lower()\n\n    if suffix in {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif"}:\n        return "video"\n    if explicit in {"video", "image", "audio"}:\n        return explicit\n    if task in {"t2v", "i2v", "v2v", "ti2v"}:\n        return "video"\n    if suffix in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:\n        return "audio"\n    return explicit or "image"\n\n\ndef _spellvision_fix_metadata_video_fields(data: dict[str, Any], req: dict[str, Any], output_path: str) -> dict[str, Any]:\n    output_path = str(\n        data.get("output_path")\n        or data.get("workflow_media_output")\n        or data.get("image_path")\n        or output_path\n        or ""\n    ).strip()\n\n    media_type = _spellvision_media_type_from_output(req, output_path)\n\n    data["output_path"] = output_path\n    data["media_path"] = output_path\n    data["media_type"] = media_type\n\n    if media_type == "video":\n        data["video_path"] = output_path\n        data["workflow_media_output"] = output_path\n    else:\n        data["video_path"] = str(data.get("video_path") or "")\n\n    state = str(data.get("state") or "").strip().lower()\n    if state in {"queued", "starting", "preparing", "running"} and output_path and Path(output_path).exists():\n        data["state"] = "completed"\n\n    timestamps = data.get("timestamps")\n    if isinstance(timestamps, dict) and str(data.get("state") or "").lower() == "completed" and not timestamps.get("finished_at"):\n        now = utc_now_iso()\n        timestamps["finished_at"] = now\n        timestamps["updated_at"] = now\n        data["timestamps"] = timestamps\n\n    stack = data.get("video_model_stack")\n    if isinstance(stack, dict):\n        route = str(req.get("native_video_route") or "").strip()\n        split_step = req.get("wan_noise_split_step") or req.get("noise_split_step")\n        if str(stack.get("stack_kind") or "").strip().lower() == "wan_dual_noise":\n            stack["native_video_route"] = route or "wan_core_dual_noise"\n            stack["wan_noise_split_step"] = split_step\n            stack["backend_kind"] = str(req.get("backend_kind") or stack.get("backend_kind") or "native_video")\n            stack["missing_parts"] = []\n            stack["stack_ready"] = True\n            data["video_model_stack"] = stack\n\n    if str(req.get("native_video_route") or "").strip():\n        data["native_video_route"] = str(req.get("native_video_route")).strip()\n    if req.get("wan_noise_split_step") is not None:\n        data["wan_noise_split_step"] = req.get("wan_noise_split_step")\n\n    return data\n\n\ndef build_metadata_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:\n    data = _spellvision_original_build_metadata_payload(*args, **kwargs)\n\n    req = kwargs.get("req")\n    image_path = kwargs.get("image_path")\n\n    if req is None and args:\n        req = args[0]\n    if image_path is None and len(args) > 1:\n        image_path = args[1]\n\n    if not isinstance(req, dict):\n        return data\n\n    return _spellvision_fix_metadata_video_fields(data, req, str(image_path or ""))\n# --- END SPELLVISION VIDEO METADATA FINALIZATION FIX V1 ---\n'


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_worker_service_video_metadata_fix.py .\\python\\worker_service.py")
        return 2

    target = Path(sys.argv[1])
    if not target.exists():
        print(f"worker_service.py not found: {target}")
        return 1

    text = target.read_text(encoding="utf-8")

    if MARKER in text:
        print("Video metadata finalization fix is already installed.")
        return 0

    anchor = "\nclass WorkerTCPHandler(socketserver.StreamRequestHandler):"
    if anchor not in text:
        print("Could not find WorkerTCPHandler anchor. No changes made.")
        return 1

    backup = target.with_suffix(target.suffix + ".pre_video_metadata_fix.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
        print(f"Backup written: {backup}")

    patched = text.replace(anchor, "\n\n" + OVERRIDE_BLOCK + anchor, 1)
    target.write_text(patched, encoding="utf-8")
    print(f"Patched: {target}")
    print("Next: python -m py_compile .\\python\\worker_service.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
