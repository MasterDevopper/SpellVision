"""History sidecars and generation metadata.

Extracted from worker_service.py. Schema attach stays in history_schema.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from typing import Any

from history_schema import attach_mode_payload
from worker_service_state import JobRecord, JobState, utc_now_iso
from comfy_graph_helpers import _first_nonempty_text
from worker_durable_state import worker_state_root
from worker_runtime import runtime_prep_metadata

VIDEO_OUTPUT_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif"}
VIDEO_COMMANDS = {"t2v", "i2v", "v2v", "ti2v", "video"}


def _file_mtime_iso(path: str) -> str | None:
    try:
        stat = os.stat(path)
    except Exception:
        return None
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()


def _ws():
    import worker_service as ws
    return ws


VIDEO_HISTORY_LOCK = threading.Lock()
VIDEO_HISTORY_MAX_ITEMS = 250
VIDEO_HISTORY_DIR = worker_state_root() / "history"
VIDEO_HISTORY_INDEX_PATH = VIDEO_HISTORY_DIR / "video_history_index.json"
VIDEO_HISTORY_JSONL_PATH = VIDEO_HISTORY_DIR / "video_history.jsonl"
VIDEO_HISTORY_JSONL_RECOVERY_MAX_BYTES = 32 * 1024 * 1024
VIDEO_HISTORY_JSONL_MAX_LINE_BYTES = 1024 * 1024


def _file_size_bytes(path: str) -> int:
    try:
        return int(os.path.getsize(path))
    except Exception:
        return 0


def _media_signature_valid(path: str, media_type: str | None) -> bool:
    """Validate known generated-media containers without decoding the artifact."""
    suffix = Path(path).suffix.lower()
    try:
        with open(path, "rb") as handle:
            head = handle.read(4096)
    except OSError:
        return False
    if not head:
        return False

    if suffix == ".png":
        return head.startswith(bytes.fromhex("89504e470d0a1a0a"))
    if suffix in {".jpg", ".jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    if suffix == ".webp":
        return len(head) >= 12 and head.startswith(b"RIFF") and head[8:12] == b"WEBP"
    if suffix == ".bmp":
        return head.startswith(b"BM")
    if suffix == ".gif":
        return head.startswith((b"GIF87a", b"GIF89a"))
    if suffix in {".mp4", ".mov", ".m4v"}:
        return b"ftyp" in head
    if suffix in {".webm", ".mkv"}:
        return head.startswith(b"\x1a\x45\xdf\xa3")
    if suffix == ".avi":
        return len(head) >= 12 and head.startswith(b"RIFF") and head[8:12] == b"AVI "

    # Unknown artifact formats retain the non-empty regular-file contract.
    return True


def output_finalization_contract(
    output_path: str | None,
    metadata_output: str | None,
    *,
    original_output: str | None = None,
    media_type: str | None = None,
    metadata_write_status: str = "unknown",
    metadata_write_error: str | None = None,
) -> dict[str, Any]:
    output = str(output_path or "").strip()
    metadata = str(metadata_output or "").strip()
    original = str(original_output or "").strip()
    output_exists = bool(output and os.path.exists(output))
    output_is_file = bool(output_exists and os.path.isfile(output))
    output_size = _file_size_bytes(output) if output_is_file else 0
    output_media_valid = bool(
        output_is_file and output_size > 0 and _media_signature_valid(output, media_type)
    )
    metadata_exists = bool(metadata and os.path.exists(metadata))
    metadata_is_file = bool(metadata_exists and os.path.isfile(metadata))
    metadata_size = _file_size_bytes(metadata) if metadata_is_file else 0
    metadata_ready = bool(
        (metadata_is_file and metadata_size > 0)
        or metadata_write_status in {"queued", "writing"}
    )
    warnings: list[str] = []
    if not output:
        warnings.append("missing_output_path")
    elif not output_exists:
        warnings.append("output_file_missing")
    elif not output_is_file:
        warnings.append("output_not_regular_file")
    elif output_size <= 0:
        warnings.append("output_file_empty")
    elif not output_media_valid:
        warnings.append("output_media_invalid")
    if not metadata:
        warnings.append("missing_metadata_path")
    elif not metadata_exists and metadata_write_status == "written":
        warnings.append("metadata_file_missing_after_write")
    elif metadata_exists and not metadata_is_file:
        warnings.append("metadata_not_regular_file")
    elif metadata_is_file and metadata_size <= 0:
        warnings.append("metadata_file_empty")
    if metadata_write_error:
        warnings.append("metadata_write_failed")

    now = utc_now_iso()
    contract = {
        "output_contract_version": 1,
        "output_contract_ok": bool(output and output_media_valid and metadata and metadata_ready and not metadata_write_error),
        "output_contract_warnings": warnings,
        "final_output": output,
        "final_output_path": output,
        "original_output": original or None,
        "original_output_path": original or None,
        "output_exists": output_exists,
        "output_is_file": output_is_file,
        "output_media_valid": output_media_valid,
        "output_file_size_bytes": output_size,
        "output_modified_at": _file_mtime_iso(output) if output_exists else None,
        "output_finalized_at": now if output_exists else None,
        "final_metadata": metadata,
        "final_metadata_path": metadata,
        "metadata_exists": metadata_exists,
        "metadata_is_file": metadata_is_file,
        "metadata_file_size_bytes": metadata_size,
        "metadata_modified_at": _file_mtime_iso(metadata) if metadata_exists else None,
        "metadata_finalized_at": now if metadata_exists else None,
        "metadata_write_status": metadata_write_status,
        "metadata_write_deferred": False,
        "metadata_write_error": metadata_write_error,
    }
    if str(media_type or "").strip().lower() == "video":
        contract["final_video_output"] = output
        contract["final_video_path"] = output
    return contract


def finalize_metadata_payload(
    data: dict[str, Any],
    *,
    output_path: str,
    metadata_output: str,
    original_output: str | None = None,
    media_type: str | None = None,
) -> dict[str, Any]:
    data.update(output_finalization_contract(
        output_path,
        metadata_output,
        original_output=original_output,
        media_type=media_type,
        metadata_write_status="writing",
    ))
    try:
        write_metadata_file(metadata_output, data)
        data.update(output_finalization_contract(
            output_path,
            metadata_output,
            original_output=original_output,
            media_type=media_type,
            metadata_write_status="written",
        ))
        write_metadata_file(metadata_output, data)
    except Exception as exc:
        data.update(output_finalization_contract(
            output_path,
            metadata_output,
            original_output=original_output,
            media_type=media_type,
            metadata_write_status="failed",
            metadata_write_error=str(exc),
        ))
        print(f"[metadata-writer] failed to finalize {metadata_output}: {exc}", flush=True)
    return data



def _video_history_result_dict(job: "JobRecord") -> dict[str, Any]:
    return asdict(job.result) if job.result else {}


def _video_history_output_path(result: dict[str, Any], request_snapshot: dict[str, Any]) -> str:
    return _first_nonempty_text(
        result.get("output_video"),
        result.get("video_path"),
        result.get("video_output"),
        result.get("output"),
        request_snapshot.get("output"),
        request_snapshot.get("workflow_media_output"),
    )


def _video_history_metadata_path(result: dict[str, Any], request_snapshot: dict[str, Any]) -> str:
    return _first_nonempty_text(
        result.get("metadata_output"),
        result.get("video_metadata_output"),
        request_snapshot.get("metadata_output"),
    )


def _image_history_details(request_snapshot: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Image-specific history fields, parallel to the video `details` block (P1 #3)."""
    def _as_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _as_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    width = _as_int(request_snapshot.get("width"))
    height = _as_int(request_snapshot.get("height"))
    model_display = str(request_snapshot.get("model_display") or request_snapshot.get("model") or "").strip()
    return {
        "resolution": (f"{width}×{height}" if width and height else ""),
        "image_width": width,
        "image_height": height,
        "image_steps": _as_int(request_snapshot.get("steps")),
        "image_cfg": _as_float(request_snapshot.get("cfg") if request_snapshot.get("cfg") is not None else request_snapshot.get("cfg_scale")),
        "image_seed": request_snapshot.get("seed"),
        "image_sampler": str(request_snapshot.get("sampler") or "").strip(),
        "image_scheduler": str(request_snapshot.get("scheduler") or "").strip(),
        "model_display": model_display,
        "model_name": (Path(model_display).name if model_display else ""),
    }


def build_history_entry(job: "JobRecord", request_snapshot: dict[str, Any]) -> dict[str, Any] | None:
    # P1 #3: generalized from build_video_history_entry to record IMAGE jobs too. The video
    # branch below is byte-identical to the old behavior (video history is preserved); the
    # gate now only requires an output path, and media_type discriminates the branches.
    if job.state != JobState.COMPLETED or not job.result:
        return None

    result = _video_history_result_dict(job)
    output_path = _video_history_output_path(result, request_snapshot)
    if not output_path:
        return None

    is_video = _ws().is_video_request(request_snapshot, output_path)
    media_type = "video" if is_video else "image"

    metadata_path = _video_history_metadata_path(result, request_snapshot)
    history_id = f"{media_type}_{job.job_id}"
    prompt = str(request_snapshot.get("prompt") or request_snapshot.get("positive_prompt") or "").strip()
    output_info = Path(output_path)
    metadata_info = Path(metadata_path) if metadata_path else None
    finalization = output_finalization_contract(
        output_path,
        metadata_path,
        original_output=str(result.get("original_output") or result.get("original_output_path") or request_snapshot.get("original_output") or ""),
        media_type=media_type,
        metadata_write_status=str(result.get("metadata_write_status") or ("written" if metadata_path and Path(metadata_path).exists() else "unknown")),
        metadata_write_error=result.get("metadata_write_error"),
    )

    entry: dict[str, Any] = {
        "history_id": history_id,
        "media_type": media_type,
        "job_id": job.job_id,
        "queue_item_id": str(request_snapshot.get("queue_item_id") or ""),
        "command": str(request_snapshot.get("command") or job.command or media_type),
        "task_type": str(result.get("task_type") or request_snapshot.get("task_type") or job.command or media_type),
        "state": job.state.value,
        "created_at": job.timestamps.created_at,
        "started_at": job.timestamps.started_at,
        "finished_at": job.timestamps.finished_at,
        "updated_at": utc_now_iso(),
        "output": output_path,
        "output_exists": bool(result.get("output_exists", finalization.get("output_exists", output_info.exists()))),
        "metadata_output": metadata_path,
        "metadata_exists": bool(result.get("metadata_exists", finalization.get("metadata_exists", bool(metadata_info and metadata_info.exists())))),
        **finalization,
        "prompt": prompt[:600],
        "prompt_preview": prompt[:160],
        "backend_name": result.get("backend_name"),
        "detected_pipeline": result.get("detected_pipeline"),
        "generation_time_sec": result.get("generation_time_sec"),
        "source_job_id": job.source_job_id,
        "retry_count": job.retry_count,
        "affinity_signature": _ws().affinity_signature_for_request(request_snapshot),
        "affinity_summary": _ws().affinity_summary_for_request(request_snapshot),
    }

    if is_video:
        # Video branch — preserves the existing video-history fields exactly.
        details = _ws().video_completion_diagnostics(
            request_snapshot,
            backend_type=str(result.get("video_backend_type") or result.get("backend_name") or ""),
            backend_name=str(result.get("video_backend_name") or result.get("backend_name") or ""),
            output_path=output_path,
            metadata_output=metadata_path,
            prompt_id=str(result.get("video_prompt_id") or ""),
        )
        if not details:
            details = _ws().video_request_metadata_from_request(request_snapshot)
        entry["output_video"] = output_path
        entry["video_path"] = output_path
        entry.update(details)
        attach_mode_payload(
            entry,
            media_type="video",
            command=entry.get("command"),
            video_details={
                "duration_label": entry.get("_ws().video_duration_label") or entry.get("duration_label") or "",
                "resolution": entry.get("video_resolution") or entry.get("resolution") or "",
                "frames": entry.get("frames") or entry.get("video_frames"),
                "fps": entry.get("fps"),
                "stack_summary": entry.get("video_model_stack_summary") or "",
                "low_model_name": entry.get("video_low_model_name") or "",
                "high_model_name": entry.get("video_high_model_name") or "",
            },
        )
    else:
        image_details = _image_history_details(request_snapshot, result)
        entry["output_image"] = output_path
        entry.update(image_details)
        attach_mode_payload(
            entry,
            media_type="image",
            command=entry.get("command") or request_snapshot.get("task_command") or request_snapshot.get("task_type"),
            image_details=image_details,
        )

    return entry


def _history_identity(item: dict[str, Any]) -> tuple[str, str]:
    identity = str(item.get("history_id") or item.get("job_id") or item.get("output") or "").strip()
    output = str(item.get("output") or item.get("video_path") or "").strip()
    return identity, output


def _dedupe_history_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the newest record for either stable identity or output path."""
    seen_identities: set[str] = set()
    seen_outputs: set[str] = set()
    newest_first: list[dict[str, Any]] = []
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        identity, output = _history_identity(item)
        if identity and identity in seen_identities:
            continue
        if output and output in seen_outputs:
            continue
        if identity:
            seen_identities.add(identity)
        if output:
            seen_outputs.add(output)
        newest_first.append(item)
    return list(reversed(newest_first))[-VIDEO_HISTORY_MAX_ITEMS:]


def _read_video_history_jsonl_unlocked() -> list[dict[str, Any]]:
    if not VIDEO_HISTORY_JSONL_PATH.is_file():
        return []
    recovered: list[dict[str, Any]] = []
    try:
        with VIDEO_HISTORY_JSONL_PATH.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            offset = max(0, size - VIDEO_HISTORY_JSONL_RECOVERY_MAX_BYTES)
            handle.seek(offset)
            if offset:
                handle.readline(VIDEO_HISTORY_JSONL_MAX_LINE_BYTES + 1)
            for raw_line in handle:
                if len(raw_line) > VIDEO_HISTORY_JSONL_MAX_LINE_BYTES:
                    continue
                try:
                    item = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(item, dict):
                    recovered.append(item)
    except OSError:
        return []
    return _dedupe_history_items(recovered)


def _read_video_history_index_unlocked() -> list[dict[str, Any]]:
    index_items: list[dict[str, Any]] | None = None
    if VIDEO_HISTORY_INDEX_PATH.is_file():
        try:
            payload = json.loads(VIDEO_HISTORY_INDEX_PATH.read_text(encoding="utf-8"))
            raw_items = payload.get("items") if isinstance(payload, dict) else None
            if isinstance(raw_items, list):
                index_items = [item for item in raw_items if isinstance(item, dict)]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            index_items = None

    ledger_items = _read_video_history_jsonl_unlocked()
    merged = _dedupe_history_items((index_items or []) + ledger_items)
    if merged and (index_items is None or merged != index_items):
        try:
            _write_video_history_index_unlocked(merged)
        except OSError:
            # Recovery remains available from JSONL even if index repair cannot publish now.
            pass
    return merged


def _fsync_parent_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(target: Path, payload: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        temp_name = ""
        _fsync_parent_directory(target)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def _write_video_history_index_unlocked(items: list[dict[str, Any]]) -> None:
    VIDEO_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "video_history_index",
        "schema_version": 2,
        "updated_at": utc_now_iso(),
        "total_count": len(items),
        "items": items,
    }
    _atomic_write_json(VIDEO_HISTORY_INDEX_PATH, payload)


def _append_video_history_jsonl_unlocked(entry: dict[str, Any]) -> None:
    VIDEO_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with VIDEO_HISTORY_JSONL_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def persist_video_history_entry(entry: dict[str, Any] | None) -> None:
    if not entry:
        return

    with VIDEO_HISTORY_LOCK:
        VIDEO_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        items = _read_video_history_index_unlocked()
        # Ledger first: if index publication is interrupted, the next read reconciles this tail.
        _append_video_history_jsonl_unlocked(entry)
        deduped = _dedupe_history_items(items + [entry])
        _write_video_history_index_unlocked(deduped)


def video_history_snapshot(limit: int = 25) -> dict[str, Any]:
    limit = max(1, min(int(limit or 25), VIDEO_HISTORY_MAX_ITEMS))
    with VIDEO_HISTORY_LOCK:
        items = _read_video_history_index_unlocked()
    selected = list(reversed(items[-limit:]))
    return {
        "type": "video_history_snapshot",
        "ok": True,
        "schema_version": 2,
        "history_index_path": str(VIDEO_HISTORY_INDEX_PATH),
        "history_jsonl_path": str(VIDEO_HISTORY_JSONL_PATH),
        "total_count": len(items),
        "items": selected,
        "latest": selected[0] if selected else None,
    }


def output_media_type_for_metadata(req: dict[str, Any], output_path: str | None) -> str:
    suffix = Path(str(output_path or "")).suffix.lower()
    if suffix in VIDEO_OUTPUT_EXTENSIONS:
        return "video"

    for key in ("media_type", "workflow_media_type", "resolved_media_type", "task_type", "command"):
        value = str(req.get(key) or "").strip().lower()
        if value in VIDEO_COMMANDS:
            return "video"
        if value == "image":
            return "image"

    return "image"


def final_metadata_state(job: "JobRecord | None", output_path: str | None) -> str:
    if job is None:
        return "completed"

    state = job.state.value
    if state in {"queued", "starting", "running"} and output_path and os.path.exists(str(output_path)):
        return "completed"
    return state


def final_metadata_timestamps(job: "JobRecord | None", output_path: str | None) -> dict[str, Any] | None:
    if job is None:
        now = utc_now_iso()
        return {"created_at": now, "started_at": None, "finished_at": now, "updated_at": now}

    payload = asdict(job.timestamps)
    if final_metadata_state(job, output_path) == "completed" and not payload.get("finished_at"):
        now = utc_now_iso()
        payload["finished_at"] = now
        payload["updated_at"] = now
    return payload


def numeric_request_value(req: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = req.get(key)
        if value not in (None, ""):
            return value
    return None


def build_metadata_payload(
    req: dict[str, Any],
    image_path: str,
    metadata_output: str,
    backend_name: str,
    device: str,
    dtype: str,
    detected_pipeline: str,
    lora_used: bool,
    elapsed: float,
    steps_per_sec: float,
    job: JobRecord | None = None,
    cache_hit: bool = False,
    model_swap_cleanup: dict[str, Any] | None = None,
    lora_cache_hit: bool = False,
    lora_reloaded: bool = False,
    queue_warm_reuse_expected: bool = False,
    queue_warm_reuse_source: str | None = None,
    queue_affinity_signature: str | None = None,
) -> dict[str, Any]:
    media_type = output_media_type_for_metadata(req, image_path)
    metadata_state = final_metadata_state(job, image_path)
    metadata_timestamps = final_metadata_timestamps(job, image_path)

    return {
        "task_type": req.get("task_type", req.get("command", "unknown")),
        "generator": "spellvision_worker_service",
        "backend": backend_name,
        "detected_pipeline": detected_pipeline,
        "timestamp": datetime.now().isoformat(),
        "prompt": req.get("prompt", ""),
        "negative_prompt": req.get("negative_prompt", ""),
        "model": req.get("model", ""),
        "model_display": req.get("model_display"),
        "model_family": req.get("model_family"),
        "model_modality": req.get("model_modality"),
        "model_role": req.get("model_role"),
        "video_model_stack": req.get("video_model_stack") or req.get("model_stack"),
        "width": req.get("width"),
        "height": req.get("height"),
        "steps": req.get("steps"),
        "cfg": req.get("cfg"),
        "seed": req.get("seed"),
        "strength": req.get("strength"),
        "device": device,
        "dtype": dtype,
        "image_path": image_path,
        "output_path": image_path,
        "media_type": media_type,
        "video_path": image_path if media_type == "video" else "",
        "metadata_output": metadata_output,
        "frames": numeric_request_value(req, "frames", "num_frames", "frame_count"),
        "fps": numeric_request_value(req, "fps", "frame_rate"),
        "duration_seconds": numeric_request_value(req, "duration_seconds", "duration_sec", "duration"),
        "asset_kind": req.get("asset_kind") or req.get("comfy_asset_kind"),
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cache_hit": cache_hit,
        "job_id": job.job_id if job else req.get("job_id"),
        "state": metadata_state,
        "timestamps": metadata_timestamps,
        "source_job_id": job.source_job_id if job else req.get("retry_of"),
        "retry_count": job.retry_count if job else int(req.get("retry_count") or 0),
        "model_swap_cleanup": model_swap_cleanup,
        "model_cleanup_time_sec": model_swap_cleanup.get("cleanup_time_sec") if model_swap_cleanup else 0.0,
        "model_load_time_sec": model_swap_cleanup.get("model_load_time_sec") if model_swap_cleanup else None,
        "memory_after_load": model_swap_cleanup.get("memory_after_load") if model_swap_cleanup else None,
        "lora_cache_hit": lora_cache_hit,
        "lora_reloaded": lora_reloaded,
        "queue_warm_reuse_expected": queue_warm_reuse_expected,
        "queue_warm_reuse_source": queue_warm_reuse_source,
        "queue_affinity_signature": queue_affinity_signature,
        **runtime_prep_metadata(req),
        "backend_kind": req.get("backend_kind"),
        "workflow_profile_name": req.get("workflow_profile_name"),
        "workflow_profile_path": req.get("profile_path") or req.get("workflow_profile_path"),
        "workflow_path": req.get("workflow_path"),
        "workflow_task_command": req.get("workflow_task_command"),
    }


METADATA_WRITE_QUEUE: "Queue[tuple[str, dict[str, Any]]]" = Queue()
_METADATA_WRITER_LOCK = threading.Lock()
_METADATA_WRITER_STARTED = False


def write_metadata_file(metadata_output: str, data: dict[str, Any]) -> None:
    _atomic_write_json(Path(metadata_output), data)


def _metadata_writer_loop() -> None:
    while True:
        metadata_output, data = METADATA_WRITE_QUEUE.get()
        try:
            write_metadata_file(metadata_output, data)
        except Exception as exc:
            print(f"[metadata-writer] failed to write {metadata_output}: {exc}", flush=True)
        finally:
            METADATA_WRITE_QUEUE.task_done()


def ensure_metadata_writer() -> None:
    global _METADATA_WRITER_STARTED
    if _METADATA_WRITER_STARTED:
        return
    with _METADATA_WRITER_LOCK:
        if _METADATA_WRITER_STARTED:
            return
        thread = threading.Thread(target=_metadata_writer_loop, name="spellvision-metadata-writer", daemon=True)
        thread.start()
        _METADATA_WRITER_STARTED = True


def queue_metadata_write(metadata_output: str, data: dict[str, Any]) -> None:
    ensure_metadata_writer()
    METADATA_WRITE_QUEUE.put((metadata_output, data))


def save_metadata(
    req: dict[str, Any],
    image_path: str,
    metadata_output: str,
    backend_name: str,
    device: str,
    dtype: str,
    detected_pipeline: str,
    lora_used: bool,
    elapsed: float,
    steps_per_sec: float,
    job: JobRecord | None = None,
    cache_hit: bool = False,
    model_swap_cleanup: dict[str, Any] | None = None,
    lora_cache_hit: bool = False,
    lora_reloaded: bool = False,
    queue_warm_reuse_expected: bool = False,
    queue_warm_reuse_source: str | None = None,
    queue_affinity_signature: str | None = None,
) -> dict[str, Any]:
    data = build_metadata_payload(
        req=req,
        image_path=image_path,
        metadata_output=metadata_output,
        backend_name=backend_name,
        device=device,
        dtype=dtype,
        detected_pipeline=detected_pipeline,
        lora_used=lora_used,
        elapsed=elapsed,
        steps_per_sec=steps_per_sec,
        job=job,
        cache_hit=cache_hit,
        model_swap_cleanup=model_swap_cleanup,
        lora_cache_hit=lora_cache_hit,
        lora_reloaded=lora_reloaded,
        queue_warm_reuse_expected=queue_warm_reuse_expected,
        queue_warm_reuse_source=queue_warm_reuse_source,
        queue_affinity_signature=queue_affinity_signature,
    )
    if isinstance(req, dict):
        data.update(_ws()._spellvision_teacache_metadata(req))
    return finalize_metadata_payload(
        data,
        output_path=image_path,
        metadata_output=metadata_output,
        original_output=str(req.get("original_output") or ""),
        media_type=data.get("media_type"),
    )

