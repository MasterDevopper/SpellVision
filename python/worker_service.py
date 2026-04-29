from __future__ import annotations

import copy
import gc
from collections import deque
import inspect
import json
import os
import re
import sys
import socketserver
import threading
import time
import traceback
import warnings
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol
from queue import Queue
from pathlib import Path
import uuid

from comfy_bootstrap import bootstrap_comfy_runtime, default_comfy_python
from comfy_runtime_manager import ComfyRuntimeManager
import urllib.error
import urllib.parse
import urllib.request

warnings.filterwarnings("ignore", message="A matching Triton is not available*")
warnings.filterwarnings("ignore", category=FutureWarning, module="diffusers")
try:
    from requests.exceptions import RequestsDependencyWarning
except Exception:
    RequestsDependencyWarning = None
if RequestsDependencyWarning is not None:
    warnings.filterwarnings("ignore", category=RequestsDependencyWarning)

import torch
from PIL import Image
from diffusers.pipelines.auto_pipeline import AutoPipelineForText2Image
from diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion import StableDiffusionPipeline
from diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion_img2img import StableDiffusionImg2ImgPipeline
from diffusers.pipelines.stable_diffusion_xl.pipeline_stable_diffusion_xl import StableDiffusionXLPipeline
from diffusers.pipelines.stable_diffusion_xl.pipeline_stable_diffusion_xl_img2img import StableDiffusionXLImg2ImgPipeline

try:
    from diffusers.schedulers.scheduling_ddim import DDIMScheduler
    from diffusers.schedulers.scheduling_ddpm import DDPMScheduler
    from diffusers.schedulers.scheduling_deis_multistep import DEISMultistepScheduler
    from diffusers.schedulers.scheduling_dpmsolver_multistep import DPMSolverMultistepScheduler
    from diffusers.schedulers.scheduling_dpmsolver_singlestep import DPMSolverSinglestepScheduler
    from diffusers.schedulers.scheduling_euler_ancestral_discrete import EulerAncestralDiscreteScheduler
    from diffusers.schedulers.scheduling_euler_discrete import EulerDiscreteScheduler
    from diffusers.schedulers.scheduling_heun_discrete import HeunDiscreteScheduler
    from diffusers.schedulers.scheduling_k_dpm_2_ancestral_discrete import KDPM2AncestralDiscreteScheduler
    from diffusers.schedulers.scheduling_k_dpm_2_discrete import KDPM2DiscreteScheduler
    from diffusers.schedulers.scheduling_lcm import LCMScheduler
    from diffusers.schedulers.scheduling_lms_discrete import LMSDiscreteScheduler
    from diffusers.schedulers.scheduling_pndm import PNDMScheduler
    from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler
except Exception:
    DDIMScheduler = None
    DDPMScheduler = None
    DEISMultistepScheduler = None
    DPMSolverMultistepScheduler = None
    DPMSolverSinglestepScheduler = None
    EulerAncestralDiscreteScheduler = None
    EulerDiscreteScheduler = None
    HeunDiscreteScheduler = None
    KDPM2AncestralDiscreteScheduler = None
    KDPM2DiscreteScheduler = None
    LCMScheduler = None
    LMSDiscreteScheduler = None
    PNDMScheduler = None
    UniPCMultistepScheduler = None

try:
    from diffusers.pipelines.stable_diffusion_3.pipeline_stable_diffusion_3 import StableDiffusion3Pipeline
except Exception:
    StableDiffusion3Pipeline = None

try:
    from diffusers.pipelines.flux.pipeline_flux import FluxPipeline
except Exception:
    FluxPipeline = None

MODEL_CACHE: dict[str, Any] = {
    "key": None,
    "pipe": None,
    "img2img_pipe": None,
    "device": None,
    "dtype": None,
    "detected": None,
    "active_lora_path_t2i": None,
    "active_lora_scale_t2i": None,
    "active_lora_path_i2i": None,
    "active_lora_scale_i2i": None,
}
CACHE_LOCK = threading.Lock()

ACTIVE_JOBS: dict[str, "ActiveJobHandle"] = {}
ACTIVE_JOBS_LOCK = threading.Lock()
JOB_ARCHIVE: dict[str, dict[str, Any]] = {}
JOB_ARCHIVE_ORDER: list[str] = []
JOB_ARCHIVE_LOCK = threading.Lock()
MAX_ARCHIVED_JOBS = 200

COMFY_RUNTIME_MANAGER: ComfyRuntimeManager | None = None
COMFY_RUNTIME_MANAGER_LOCK = threading.Lock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()




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


def cuda_memory_snapshot() -> dict[str, float]:
    if not torch.cuda.is_available():
        return {
            "allocated_gb": 0.0,
            "reserved_gb": 0.0,
            "max_allocated_gb": 0.0,
            "max_reserved_gb": 0.0,
        }

    return {
        "allocated_gb": round(torch.cuda.memory_allocated() / (1024 ** 3), 2),
        "reserved_gb": round(torch.cuda.memory_reserved() / (1024 ** 3), 2),
        "max_allocated_gb": round(torch.cuda.max_memory_allocated() / (1024 ** 3), 2),
        "max_reserved_gb": round(torch.cuda.max_memory_reserved() / (1024 ** 3), 2),
    }


def clear_cuda_memory() -> dict[str, float]:
    gc.collect()

    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        try:
            torch.cuda.ipc_collect()
        except Exception:
            pass

    return cuda_memory_snapshot()


def unload_cached_pipelines() -> dict[str, Any]:
    before = cuda_memory_snapshot()
    start = time.perf_counter()

    with CACHE_LOCK:
        old_key = MODEL_CACHE.get("key")
        old_t2i = MODEL_CACHE.get("pipe")
        old_i2i = MODEL_CACHE.get("img2img_pipe")

        MODEL_CACHE["key"] = None
        MODEL_CACHE["pipe"] = None
        MODEL_CACHE["img2img_pipe"] = None
        MODEL_CACHE["device"] = None
        MODEL_CACHE["dtype"] = None
        MODEL_CACHE["detected"] = None
        MODEL_CACHE["active_lora_path_t2i"] = None
        MODEL_CACHE["active_lora_scale_t2i"] = None
        MODEL_CACHE["active_lora_path_i2i"] = None
        MODEL_CACHE["active_lora_scale_i2i"] = None

    try:
        if old_t2i is not None:
            del old_t2i
    except Exception:
        pass

    try:
        if old_i2i is not None:
            del old_i2i
    except Exception:
        pass

    after = clear_cuda_memory()
    elapsed = round(time.perf_counter() - start, 3)

    return {
        "old_key": old_key,
        "cleanup_time_sec": elapsed,
        "memory_before": before,
        "memory_after": after,
    }


def cleanup_for_model_swap(requested_key: str) -> dict[str, Any] | None:
    with CACHE_LOCK:
        active_key = MODEL_CACHE.get("key")

    if not active_key or active_key == requested_key:
        return None

    stats = unload_cached_pipelines()
    stats["requested_key"] = requested_key
    return stats


class JobEmitter(Protocol):
    def emit(self, payload: dict[str, Any]) -> None: ...
    def emit_job_update(self, job: "JobRecord") -> None: ...
    def status(self, job: "JobRecord", message: str) -> None: ...
    def progress(self, job: "JobRecord", step: int, total: int, message: str | None = None) -> None: ...


class QueueItemState(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


QUEUE_TERMINAL_STATES = {
    QueueItemState.COMPLETED,
    QueueItemState.FAILED,
    QueueItemState.CANCELLED,
    QueueItemState.SKIPPED,
}


def queue_state_from_job_state(job_state: "JobState") -> QueueItemState:
    mapping = {
        JobState.QUEUED: QueueItemState.QUEUED,
        JobState.STARTING: QueueItemState.PREPARING,
        JobState.RUNNING: QueueItemState.RUNNING,
        JobState.COMPLETED: QueueItemState.COMPLETED,
        JobState.FAILED: QueueItemState.FAILED,
        JobState.CANCELLED: QueueItemState.CANCELLED,
    }
    return mapping.get(job_state, QueueItemState.FAILED)


@dataclass
class QueueItemProgress:
    current: int = 0
    total: int = 0
    percent: float = 0.0
    message: str = "queued"


@dataclass
class QueueItemTimestamps:
    created_at: str = field(default_factory=utc_now_iso)
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class QueueItem:
    queue_item_id: str
    command: str
    request_snapshot: dict[str, Any]
    state: QueueItemState = QueueItemState.QUEUED
    worker_job_id: str | None = None
    source_job_id: str | None = None
    retry_count: int = 0
    progress: QueueItemProgress = field(default_factory=QueueItemProgress)
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    timestamps: QueueItemTimestamps = field(default_factory=QueueItemTimestamps)

    def payload(self) -> dict[str, Any]:
        prompt_summary = str(
            self.request_snapshot.get("prompt")
            or self.request_snapshot.get("workflow_profile_name")
            or ""
        )[:160]

        return {
            "queue_item_id": self.queue_item_id,
            "command": self.command,
            "state": self.state.value,
            "worker_job_id": self.worker_job_id,
            "source_job_id": self.source_job_id,
            "retry_count": self.retry_count,
            "progress": asdict(self.progress),
            "result": copy.deepcopy(self.result),
            "error": copy.deepcopy(self.error),
            "timestamps": asdict(self.timestamps),
            "output": self.request_snapshot.get("output"),
            "original_output": self.request_snapshot.get("original_output"),
            "prompt": prompt_summary,
            "metadata_output": self.request_snapshot.get("metadata_output"),
            "original_metadata_output": self.request_snapshot.get("original_metadata_output"),
            "affinity_signature": affinity_signature_for_request(self.request_snapshot),
            "affinity_summary": affinity_summary_for_request(self.request_snapshot),
    }


class QueueManager:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pending: deque[str] = deque()
        self.items: dict[str, QueueItem] = {}
        self.order: list[str] = []
        self.active_queue_item_id: str | None = None
        self.paused: bool = False

    def _timestamp_touch(self, item: QueueItem) -> None:
        item.timestamps.updated_at = utc_now_iso()

    def snapshot_payload(self) -> dict[str, Any]:
        with self.lock:
            ordered_ids: list[str] = []
            if self.active_queue_item_id and self.active_queue_item_id in self.items:
                ordered_ids.append(self.active_queue_item_id)
            ordered_ids.extend([qid for qid in self.pending if qid in self.items and qid not in ordered_ids])
            ordered_ids.extend([qid for qid in reversed(self.order) if qid in self.items and qid not in ordered_ids])

            items_payload: list[dict[str, Any]] = []
            previous_signature: str | None = None
            for qid in ordered_ids[:100]:
                item = self.items[qid]
                payload = item.payload()
                warm_reuse_candidate, warm_reuse_source, item_signature = queue_warm_reuse_prediction(
                    item.request_snapshot,
                    previous_signature=previous_signature,
                )
                payload["warm_reuse_candidate"] = warm_reuse_candidate
                payload["warm_reuse_source"] = warm_reuse_source
                if item.state in {QueueItemState.QUEUED, QueueItemState.PREPARING, QueueItemState.RUNNING}:
                    previous_signature = item_signature
                items_payload.append(payload)

            return {
                "type": "queue_snapshot",
                "ok": True,
                "active_queue_item_id": self.active_queue_item_id,
                "queue_paused": self.paused,
                "pending_count": sum(1 for qid in self.pending if qid in self.items),
                "total_count": len(self.items),
                "queue_order_preserved": True,
                "active_affinity_t2i": active_affinity_signature_for_command("t2i"),
                "active_affinity_i2i": active_affinity_signature_for_command("i2i"),
                "active_affinity_t2v": active_affinity_signature_for_command("t2v"),
                "active_affinity_i2v": active_affinity_signature_for_command("i2v"),
                "items": items_payload,
            }

    def enqueue(self, req: dict[str, Any]) -> dict[str, Any]:
        task_command = str(req.get("task_command") or req.get("generation_command") or req.get("task") or "").strip()
        if task_command not in {"t2i", "i2i", "t2v", "i2v", "comfy_workflow"}:
            raise ValueError("enqueue requires task_command of 't2i', 'i2i', 't2v', 'i2v', or 'comfy_workflow'")

        queue_item_id = str(req.get("queue_item_id") or f"queue_{uuid.uuid4().hex[:12]}")

        request_snapshot = clone_request_snapshot(req)
        request_snapshot["command"] = task_command
        request_snapshot.pop("task_command", None)
        request_snapshot.pop("generation_command", None)
        request_snapshot.pop("queue_item_id", None)
        request_snapshot["job_id"] = str(request_snapshot.get("job_id") or f"job_{uuid.uuid4().hex[:12]}")
        request_snapshot["original_output"] = str(
            request_snapshot.get("original_output") or request_snapshot.get("output") or ""
        ).strip()
        request_snapshot["original_metadata_output"] = str(
            request_snapshot.get("original_metadata_output") or request_snapshot.get("metadata_output") or ""
        ).strip()

        item = QueueItem(
            queue_item_id=queue_item_id,
            command=task_command,
            request_snapshot=request_snapshot,
            source_job_id=request_snapshot.get("retry_of"),
            retry_count=int(request_snapshot.get("retry_count") or 0),
        )

        with self.lock:
            self.items[queue_item_id] = item
            if queue_item_id in self.order:
                self.order.remove(queue_item_id)
            self.order.append(queue_item_id)
            self.pending.append(queue_item_id)
            self._start_next_locked()

        return {
            "type": "queue_ack",
            "ok": True,
            "action": "enqueue",
            "queue_item_id": queue_item_id,
            "job_id": request_snapshot["job_id"],
        }

    def update_from_job(self, queue_item_id: str, job: "JobRecord") -> None:
        with self.lock:
            item = self.items.get(queue_item_id)
            if item is None:
                return
            item.worker_job_id = job.job_id
            item.state = queue_state_from_job_state(job.state)
            item.source_job_id = job.source_job_id
            item.retry_count = job.retry_count
            item.progress.current = job.progress.current
            item.progress.total = job.progress.total
            item.progress.percent = job.progress.percent
            item.progress.message = job.progress.message
            item.result = asdict(job.result) if job.result else None
            item.error = asdict(job.error) if job.error else None
            if job.timestamps.started_at:
                item.timestamps.started_at = job.timestamps.started_at
            item.timestamps.updated_at = job.timestamps.updated_at
            if job.timestamps.finished_at:
                item.timestamps.finished_at = job.timestamps.finished_at

    def _start_next_locked(self) -> None:
        if self.paused:
            return
        if self.active_queue_item_id is not None:
            return
        while self.pending:
            queue_item_id = self.pending.popleft()
            item = self.items.get(queue_item_id)
            if item is None or item.state != QueueItemState.QUEUED:
                continue
            self.active_queue_item_id = queue_item_id
            item.state = QueueItemState.PREPARING
            item.timestamps.started_at = item.timestamps.started_at or utc_now_iso()
            self._timestamp_touch(item)
            thread = threading.Thread(target=self._run_queue_item, args=(queue_item_id,), daemon=True)
            thread.start()
            return

    def _finalize_queue_item(self, queue_item_id: str) -> None:
        with self.lock:
            if self.active_queue_item_id == queue_item_id:
                self.active_queue_item_id = None
            self._start_next_locked()

    def _run_queue_item(self, queue_item_id: str) -> None:
        with self.lock:
            item = self.items.get(queue_item_id)
            if item is None:
                return
            req = clone_request_snapshot(item.request_snapshot)
            item_command = item.command

        base_output = str(req.get("original_output") or req.get("output") or "").strip()
        base_metadata_output = str(
            req.get("original_metadata_output") or req.get("metadata_output") or ""
        ).strip()

        if base_output:
            unique_output, unique_metadata_output = safe_unique_output_paths(
                base_output,
                queue_item_id=queue_item_id,
                retry_count=int(req.get("retry_count") or 0),
                original_metadata_output=base_metadata_output or None,
            )
            req["output"] = unique_output
            req["metadata_output"] = unique_metadata_output

            with self.lock:
                item = self.items.get(queue_item_id)
                if item is not None:
                    item.request_snapshot["output"] = unique_output
                    item.request_snapshot["metadata_output"] = unique_metadata_output
                    item.request_snapshot["original_output"] = base_output
                    item.request_snapshot["original_metadata_output"] = base_metadata_output

        queue_warm_reuse_expected, queue_warm_reuse_source, queue_affinity_signature = queue_warm_reuse_prediction(req)
        req["queue_warm_reuse_expected"] = queue_warm_reuse_expected
        req["queue_warm_reuse_source"] = queue_warm_reuse_source
        req["queue_affinity_signature"] = queue_affinity_signature

        with self.lock:
            item = self.items.get(queue_item_id)
            if item is not None:
                item.progress.message = "warm reuse expected" if queue_warm_reuse_expected else "queue waiting"
                self._timestamp_touch(item)

        job = create_job(req)
        active_job = ActiveJobHandle(job=job)
        register_active_job(active_job)
        emitter = QueueEmitter(self, queue_item_id)

        try:
            if item_command == "t2i":
                run_t2i(req, emitter, job, active_job)
            elif item_command == "i2i":
                run_i2i(req, emitter, job, active_job)
            elif item_command == "comfy_workflow":
                run_comfy_workflow(req, emitter, job, active_job)
            elif item_command in {"t2v", "i2v"}:
                if request_has_workflow_binding(req):
                    run_comfy_workflow(req, emitter, job, active_job)
                else:
                    run_native_video(req, emitter, job, active_job)
            else:
                raise RuntimeError(f"Unsupported queued command: {item_command}")
            emitter.result(job)
        except JobCancelledError as exc:
            if job.state != JobState.CANCELLED:
                cancel_job(job, str(exc))
                emitter.emit_job_update(job)
            emitter.result(job)
        except Exception as exc:
            emitter.error(job, str(exc), traceback.format_exc())

        finally:
            unregister_active_job(job.job_id)
            archive_job(job, req)
            self._finalize_queue_item(queue_item_id)

    def queue_status(self) -> dict[str, Any]:
        return self.snapshot_payload()

    def _rebuild_pending_from_order_locked(self) -> None:
        self.pending = deque(
            qid for qid in self.order
            if qid in self.items and self.items[qid].state == QueueItemState.QUEUED
        )

    def move_up(self, queue_item_id: str) -> tuple[bool, str]:
        with self.lock:
            item = self.items.get(queue_item_id)
            if item is None:
                return False, "queue item not found"
            if item.state != QueueItemState.QUEUED:
                return False, f"queue item is not pending (state={item.state.value})"
            idx = self.order.index(queue_item_id) if queue_item_id in self.order else -1
            if idx <= 0:
                return False, "queue item is already at the top"
            self.order[idx - 1], self.order[idx] = self.order[idx], self.order[idx - 1]
            self._rebuild_pending_from_order_locked()
            return True, "queue item moved up"

    def move_down(self, queue_item_id: str) -> tuple[bool, str]:
        with self.lock:
            item = self.items.get(queue_item_id)
            if item is None:
                return False, "queue item not found"
            if item.state != QueueItemState.QUEUED:
                return False, f"queue item is not pending (state={item.state.value})"
            idx = self.order.index(queue_item_id) if queue_item_id in self.order else -1
            if idx < 0 or idx >= len(self.order) - 1:
                return False, "queue item is already at the bottom"
            self.order[idx], self.order[idx + 1] = self.order[idx + 1], self.order[idx]
            self._rebuild_pending_from_order_locked()
            return True, "queue item moved down"

    def duplicate_queue_item(self, queue_item_id: str) -> tuple[bool, str, str | None]:
        with self.lock:
            source = self.items.get(queue_item_id)
            if source is None:
                return False, "queue item not found", None
            request_snapshot = clone_request_snapshot(source.request_snapshot)
            request_snapshot["job_id"] = f"job_{uuid.uuid4().hex[:12]}"
            request_snapshot.pop("queue_item_id", None)
            request_snapshot.pop("task_command", None)
            request_snapshot["command"] = source.command
            request_snapshot["task_type"] = request_snapshot.get("task_type") or source.command
            request_snapshot["retry_of"] = source.worker_job_id or source.source_job_id or request_snapshot.get("retry_of")
            request_snapshot["retry_count"] = 0
            original_output = str(request_snapshot.get("original_output") or request_snapshot.get("output") or "").strip()
            original_metadata_output = str(request_snapshot.get("original_metadata_output") or request_snapshot.get("metadata_output") or "").strip()
            if original_output:
                new_output, new_metadata_output = safe_unique_output_paths(
                    original_output,
                    queue_item_id=f"queue_{uuid.uuid4().hex[:12]}",
                    retry_count=0,
                    original_metadata_output=original_metadata_output or None,
                )
                request_snapshot["output"] = new_output
                request_snapshot["metadata_output"] = new_metadata_output
                request_snapshot["original_output"] = original_output
                request_snapshot["original_metadata_output"] = original_metadata_output

        ack = self.enqueue({**request_snapshot, "task_command": source.command})
        return True, "queue item duplicated", ack.get("queue_item_id")

    def pause(self) -> tuple[bool, str]:
        with self.lock:
            if self.paused:
                return False, "queue is already paused"
            self.paused = True
            return True, "queue paused"

    def resume(self) -> tuple[bool, str]:
        with self.lock:
            if not self.paused:
                return False, "queue is not paused"
            self.paused = False
            self._start_next_locked()
            return True, "queue resumed"

    def cancel_all(self) -> tuple[int, bool]:
        with self.lock:
            pending_ids = list(self.pending)
            self.pending.clear()
            removed = 0
            for queue_item_id in pending_ids:
                item = self.items.get(queue_item_id)
                if item and item.state == QueueItemState.QUEUED:
                    item.state = QueueItemState.CANCELLED
                    item.error = {"code": "cancelled", "message": "Queue item cancelled before execution"}
                    item.timestamps.finished_at = utc_now_iso()
                    self._timestamp_touch(item)
                    removed += 1
            active_id = self.active_queue_item_id
            active_item = self.items.get(active_id) if active_id else None
        active_cancelled = False
        if active_item and active_item.worker_job_id:
            active_cancelled, _job = request_job_cancel(active_item.worker_job_id)
        return removed, active_cancelled

    def enqueue_dataset(self, req: dict[str, Any]) -> dict[str, Any]:
        prompts = req.get("prompts") or []
        if isinstance(prompts, str):
            prompts = [p.strip() for p in prompts.splitlines() if p.strip()]
        prompts = [str(p).strip() for p in prompts if str(p).strip()]
        base_prompt = str(req.get("prompt") or "").strip()
        if base_prompt:
            prompts.insert(0, base_prompt)
        if not prompts:
            raise ValueError("generate_dataset requires prompt or prompts")

        images_per_prompt = max(1, int(req.get("images_per_prompt", 1)))
        seed_start = int(req.get("seed_start", req.get("seed", 42)))
        output_root = Path(str(req.get("dataset_root") or req.get("output_root") or "").strip() or str(Path(req.get("output") or "dataset_output").with_suffix("")))
        images_dir = output_root / "images"
        metadata_dir = output_root / "metadata"
        images_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)

        queued_ids: list[str] = []
        total_jobs = 0
        base_request = clone_request_snapshot(req)
        base_request.pop("prompts", None)
        base_request.pop("images_per_prompt", None)
        base_request.pop("seed_start", None)
        base_request.pop("dataset_root", None)
        base_request.pop("output_root", None)
        base_request.pop("command", None)
        base_request.pop("task_command", None)
        base_request["task_type"] = "t2i"

        for prompt_index, prompt_text in enumerate(prompts):
            for image_index in range(images_per_prompt):
                total_jobs += 1
                job_req = clone_request_snapshot(base_request)
                job_req["job_id"] = f"job_{uuid.uuid4().hex[:12]}"
                job_req["prompt"] = prompt_text
                job_req["command"] = "t2i"
                job_req["seed"] = seed_start + total_jobs - 1
                filename = f"dataset_{prompt_index+1:03d}_{image_index+1:03d}.png"
                output_path = str(images_dir / filename)
                metadata_path = str(metadata_dir / f"{Path(filename).stem}.json")
                job_req["output"] = output_path
                job_req["metadata_output"] = metadata_path
                job_req["original_output"] = output_path
                job_req["original_metadata_output"] = metadata_path
                ack = self.enqueue({**job_req, "task_command": "t2i"})
                queued_ids.append(ack["queue_item_id"])

        return {
            "type": "queue_ack",
            "ok": True,
            "action": "generate_dataset",
            "queued_count": total_jobs,
            "queue_item_ids": queued_ids,
            "dataset_root": str(output_root),
            "images_dir": str(images_dir),
            "metadata_dir": str(metadata_dir),
        }

    def remove_pending(self, queue_item_id: str) -> tuple[bool, str]:
        with self.lock:
            item = self.items.get(queue_item_id)
            if item is None:
                return False, "queue item not found"
            if self.active_queue_item_id == queue_item_id:
                return False, "cannot remove active queue item"
            if item.state != QueueItemState.QUEUED:
                return False, f"queue item is not pending (state={item.state.value})"
            self.pending = deque(qid for qid in self.pending if qid != queue_item_id)
            item.state = QueueItemState.SKIPPED
            item.error = {"code": "removed", "message": "Queue item removed before execution"}
            item.timestamps.finished_at = utc_now_iso()
            self._timestamp_touch(item)
            return True, "queue item removed"

    def clear_pending(self) -> int:
        with self.lock:
            removed = 0
            pending_ids = list(self.pending)
            self.pending.clear()
            for queue_item_id in pending_ids:
                item = self.items.get(queue_item_id)
                if item and item.state == QueueItemState.QUEUED:
                    item.state = QueueItemState.SKIPPED
                    item.error = {"code": "cleared", "message": "Queue item cleared before execution"}
                    item.timestamps.finished_at = utc_now_iso()
                    self._timestamp_touch(item)
                    removed += 1
            return removed

    def cancel(self, queue_item_id: str | None = None) -> tuple[bool, str, QueueItem | None]:
        with self.lock:
            target_id = queue_item_id or self.active_queue_item_id
            if not target_id:
                return False, "no active queue item", None
            item = self.items.get(target_id)
            if item is None:
                return False, "queue item not found", None
            if self.active_queue_item_id == target_id and item.worker_job_id:
                pass
            elif item.state == QueueItemState.QUEUED:
                self.pending = deque(qid for qid in self.pending if qid != target_id)
                item.state = QueueItemState.CANCELLED
                item.error = {"code": "cancelled", "message": "Queue item cancelled before execution"}
                item.timestamps.finished_at = utc_now_iso()
                self._timestamp_touch(item)
                return True, "queue item cancelled", item
            else:
                return False, f"queue item cannot be cancelled in state={item.state.value}", item

        accepted, _job = request_job_cancel(item.worker_job_id)
        if not accepted:
            return False, "active worker job not found", item
        return True, "cancel requested", item

    def retry_from_archive(self, source_job_id: str, req: dict[str, Any]) -> dict[str, Any]:
        retry_req = build_retry_request(source_job_id, req)
        if retry_req is None:
            raise ValueError("retry source job not found")
        retry_req["task_command"] = retry_req.get("command")
        retry_req["command"] = "enqueue"
        return self.enqueue(retry_req)


QUEUE_MANAGER = QueueManager()


class JobCancelledError(RuntimeError):
    pass


@dataclass
class ActiveJobHandle:
    job: "JobRecord"
    cancel_event: threading.Event = field(default_factory=threading.Event)


def clone_request_snapshot(req: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(req)


_GENERATED_SUFFIX_RE = re.compile(
    r"(?:_queue_[A-Za-z0-9_-]+|_retry\d{2,}|_retry_\d{8}_\d{6}|_job_[A-Za-z0-9_-]+)+$"
)


def strip_generated_suffixes(stem: str) -> str:
    return _GENERATED_SUFFIX_RE.sub("", stem)



def normalized_lora_path(lora_path: str | None) -> str:
    value = str(lora_path or "").strip()
    return os.path.abspath(value) if value else ""


def affinity_signature_for_request(req: dict[str, Any]) -> str:
    command = str(req.get("command") or req.get("task_command") or "").strip().lower()
    model = str(req.get("model") or "").strip()
    lora = normalized_lora_path(req.get("lora"))
    try:
        lora_scale = float(req.get("lora_scale", 1.0))
    except Exception:
        lora_scale = 1.0
    return f"{command}|{model}|{lora}|{lora_scale:.4f}"


def affinity_summary_for_request(req: dict[str, Any]) -> str:
    command = str(req.get("command") or req.get("task_command") or "").strip().lower()
    model = str(req.get("model") or "").strip()
    lora = normalized_lora_path(req.get("lora"))
    lora_scale = float(req.get("lora_scale", 1.0) or 1.0)
    model_name = os.path.basename(model) if os.path.exists(model) else model
    lora_name = os.path.basename(lora) if lora else "none"
    return f"{command.upper()} | {model_name} | LoRA {lora_name} @ {lora_scale:.2f}"


def active_affinity_signature_for_command(command: str) -> str | None:
    command = str(command or "").strip().lower()
    with CACHE_LOCK:
        model_key = MODEL_CACHE.get("key")
    if not model_key:
        return None

    cached_path, cached_scale = get_cached_lora_state(command if command in {"t2i", "i2i"} else "t2i")
    lora_path = normalized_lora_path(cached_path)
    scale = float(cached_scale) if cached_scale is not None else 1.0
    return f"{command}|{model_key}|{lora_path}|{scale:.4f}"


def queue_warm_reuse_prediction(req: dict[str, Any], previous_signature: str | None = None) -> tuple[bool, str | None, str]:
    item_signature = affinity_signature_for_request(req)
    active_signature = active_affinity_signature_for_command(str(req.get("command") or req.get("task_command") or "").strip().lower())

    if active_signature and active_signature == item_signature:
        return True, "warm-cache", item_signature
    if previous_signature and previous_signature == item_signature:
        return True, "adjacent-queue", item_signature
    return False, None, item_signature


def safe_unique_output_paths(
    base_output: str,
    *,
    queue_item_id: str | None = None,
    retry_count: int = 0,
    original_metadata_output: str | None = None,
) -> tuple[str, str]:
    output_path = Path(base_output)
    parent = output_path.parent
    suffix = output_path.suffix or ".png"

    clean_stem = strip_generated_suffixes(output_path.stem)

    suffix_parts: list[str] = []
    if queue_item_id:
        suffix_parts.append(queue_item_id)
    if retry_count > 0:
        suffix_parts.append(f"retry{retry_count:02d}")

    new_stem = clean_stem
    if suffix_parts:
        new_stem = f"{clean_stem}_{'_'.join(suffix_parts)}"

    if len(new_stem) > 120:
        new_stem = new_stem[:120]

    image_output = str(parent / f"{new_stem}{suffix}")

    if original_metadata_output:
        metadata_parent = Path(original_metadata_output).parent
    else:
        metadata_parent = parent
    metadata_output = str(metadata_parent / f"{new_stem}.json")

    return image_output, metadata_output


def build_retry_output_path(base_output: str) -> str:
    retry_output, _ = safe_unique_output_paths(
        base_output,
        retry_count=1,
    )
    return retry_output


def build_retry_metadata_path(metadata_output: str | None, retry_output: str) -> str:
    _, retry_metadata = safe_unique_output_paths(
        retry_output,
        original_metadata_output=metadata_output,
    )
    return retry_metadata


def archive_job(job: "JobRecord", request_snapshot: dict[str, Any]) -> None:
    entry = {
        "job_id": job.job_id,
        "command": job.command,
        "state": job.state.value,
        "request": clone_request_snapshot(request_snapshot),
        "result": asdict(job.result) if job.result else None,
        "error": asdict(job.error) if job.error else None,
        "timestamps": asdict(job.timestamps),
        "source_job_id": job.source_job_id,
        "retry_count": job.retry_count,
    }
    with JOB_ARCHIVE_LOCK:
        JOB_ARCHIVE[job.job_id] = entry
        if job.job_id in JOB_ARCHIVE_ORDER:
            JOB_ARCHIVE_ORDER.remove(job.job_id)
        JOB_ARCHIVE_ORDER.append(job.job_id)
        while len(JOB_ARCHIVE_ORDER) > MAX_ARCHIVED_JOBS:
            stale_id = JOB_ARCHIVE_ORDER.pop(0)
            JOB_ARCHIVE.pop(stale_id, None)


def get_archived_job(job_id: str) -> dict[str, Any] | None:
    with JOB_ARCHIVE_LOCK:
        entry = JOB_ARCHIVE.get(job_id)
        return copy.deepcopy(entry) if entry is not None else None


def build_retry_request(source_job_id: str, req: dict[str, Any]) -> dict[str, Any] | None:
    source_entry = get_archived_job(source_job_id)
    if not source_entry:
        return None

    new_req = clone_request_snapshot(source_entry["request"])
    new_req["job_id"] = str(req.get("job_id") or f"job_{uuid.uuid4().hex[:12]}")
    new_req["retry_of"] = source_job_id
    new_req["retry_count"] = int(source_entry.get("retry_count") or 0) + 1

    original_output = str(
        new_req.get("original_output") or new_req.get("output") or ""
    ).strip()
    original_metadata_output = str(
        new_req.get("original_metadata_output") or new_req.get("metadata_output") or ""
    ).strip()

    if original_output:
        retry_output, retry_metadata_output = safe_unique_output_paths(
            original_output,
            retry_count=int(new_req["retry_count"]),
            original_metadata_output=original_metadata_output or None,
        )
        new_req["output"] = retry_output
        new_req["metadata_output"] = retry_metadata_output
        new_req["original_output"] = original_output
        new_req["original_metadata_output"] = original_metadata_output

    return new_req


def is_local_file(path: str) -> bool:
    return os.path.isfile(path)


def torch_dtype_and_device() -> tuple[torch.dtype, str]:
    if torch.cuda.is_available():
        return torch.float16, "cuda"
    return torch.float32, "cpu"


def detect_pipeline_type(model_name_or_path: str) -> str:
    lower = model_name_or_path.lower()
    if "flux" in lower:
        return "flux"
    if "stable-diffusion-3" in lower or "sd3" in lower:
        return "sd3"
    if "xl" in lower or "sdxl" in lower:
        return "sdxl"
    return "sd"


def optimize_pipeline(pipe: Any, device: str) -> Any:
    try:
        if hasattr(pipe, "set_progress_bar_config"):
            pipe.set_progress_bar_config(disable=True)
    except Exception:
        pass

    try:
        if hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()
    except Exception:
        pass

    try:
        if hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_slicing"):
            pipe.vae.enable_slicing()
    except Exception:
        pass

    try:
        if device == "cuda" and hasattr(pipe, "enable_xformers_memory_efficient_attention"):
            pipe.enable_xformers_memory_efficient_attention()
    except Exception:
        pass

    return pipe


def _lora_cache_keys(pipe_role: str) -> tuple[str, str]:
    role = pipe_role.lower().strip()
    if role not in {"t2i", "i2i"}:
        raise ValueError(f"Unknown LoRA pipe role: {pipe_role}")
    return (f"active_lora_path_{role}", f"active_lora_scale_{role}")


def get_cached_lora_state(pipe_role: str) -> tuple[str | None, float | None]:
    path_key, scale_key = _lora_cache_keys(pipe_role)
    with CACHE_LOCK:
        return MODEL_CACHE.get(path_key), MODEL_CACHE.get(scale_key)


def set_cached_lora_state(pipe_role: str, lora_path: str | None, lora_scale: float | None) -> None:
    path_key, scale_key = _lora_cache_keys(pipe_role)
    with CACHE_LOCK:
        MODEL_CACHE[path_key] = lora_path
        MODEL_CACHE[scale_key] = lora_scale


def reset_lora_state(pipe: Any, pipe_role: str | None = None) -> None:
    try:
        if hasattr(pipe, "unfuse_lora"):
            pipe.unfuse_lora()
    except Exception:
        pass

    try:
        if hasattr(pipe, "unload_lora_weights"):
            pipe.unload_lora_weights()
    except Exception:
        pass

    if pipe_role:
        set_cached_lora_state(pipe_role, None, None)


def maybe_load_lora(pipe: Any, lora_path: str, lora_scale: float, pipe_role: str) -> tuple[bool, dict[str, Any]]:
    normalized_path = os.path.abspath(lora_path).strip() if lora_path else ""
    cached_path, cached_scale = get_cached_lora_state(pipe_role)

    if not normalized_path:
        if cached_path:
            reset_lora_state(pipe, pipe_role)
            return False, {
                "lora_cache_hit": False,
                "lora_reloaded": False,
                "lora_cleared": True,
                "active_lora_path": None,
                "active_lora_scale": None,
            }
        return False, {
            "lora_cache_hit": False,
            "lora_reloaded": False,
            "lora_cleared": False,
            "active_lora_path": None,
            "active_lora_scale": None,
        }

    if cached_path == normalized_path and cached_scale is not None and abs(float(cached_scale) - float(lora_scale)) < 1e-9:
        return True, {
            "lora_cache_hit": True,
            "lora_reloaded": False,
            "lora_cleared": False,
            "active_lora_path": normalized_path,
            "active_lora_scale": float(lora_scale),
        }

    reset_lora_state(pipe, pipe_role)

    if not os.path.exists(normalized_path):
        raise FileNotFoundError(f"LoRA file not found: {normalized_path}")

    try:
        import peft  # noqa: F401
    except Exception as exc:
        raise RuntimeError("LoRA support requires 'peft' in the venv.") from exc

    pipe.load_lora_weights(normalized_path)

    try:
        pipe.fuse_lora(lora_scale=lora_scale)
    except Exception:
        pass

    set_cached_lora_state(pipe_role, normalized_path, float(lora_scale))

    return True, {
        "lora_cache_hit": False,
        "lora_reloaded": True,
        "lora_cleared": False,
        "active_lora_path": normalized_path,
        "active_lora_scale": float(lora_scale),
    }


def _scheduler_from_config(scheduler_cls: Any, base_config: Any, **kwargs: Any) -> Any:
    if scheduler_cls is None:
        return None
    try:
        return scheduler_cls.from_config(base_config, **kwargs)
    except TypeError:
        return scheduler_cls.from_config(base_config)


def apply_sampler_and_scheduler(pipe: Any, req: dict[str, Any]) -> dict[str, Any]:
    if pipe is None or not hasattr(pipe, "scheduler"):
        return {"applied": False, "sampler": None, "scheduler": None}

    sampler_name = str(req.get("sampler") or "").strip().lower()
    scheduler_name = str(req.get("scheduler") or "").strip().lower()

    scheduler_map: dict[str, Any] = {
        "euler": EulerDiscreteScheduler,
        "euler_ancestral": EulerAncestralDiscreteScheduler,
        "heun": HeunDiscreteScheduler,
        "dpm_2": KDPM2DiscreteScheduler,
        "dpm_2_ancestral": KDPM2AncestralDiscreteScheduler,
        "lms": LMSDiscreteScheduler,
        "dpmpp_2m": DPMSolverMultistepScheduler,
        "dpmpp_sde": DPMSolverSinglestepScheduler,
        "ddpm": DDPMScheduler,
        "ddim": DDIMScheduler,
        "deis": DEISMultistepScheduler,
        "pndm": PNDMScheduler,
        "lcm": LCMScheduler,
        "uni_pc": UniPCMultistepScheduler,
    }

    scheduler_cls = scheduler_map.get(sampler_name)
    if scheduler_cls is None:
        return {"applied": False, "sampler": sampler_name or None, "scheduler": scheduler_name or None}

    extra_config: dict[str, Any] = {}
    if scheduler_name == "karras":
        extra_config["use_karras_sigmas"] = True
    elif scheduler_name == "exponential":
        extra_config["use_exponential_sigmas"] = True
    elif scheduler_name == "beta":
        extra_config["use_beta_sigmas"] = True

    try:
        new_scheduler = _scheduler_from_config(scheduler_cls, pipe.scheduler.config, **extra_config)
        if new_scheduler is not None:
            pipe.scheduler = new_scheduler
            return {
                "applied": True,
                "sampler": sampler_name or None,
                "scheduler": scheduler_name or None,
                "scheduler_class": scheduler_cls.__name__,
            }
    except Exception as exc:
        return {
            "applied": False,
            "sampler": sampler_name or None,
            "scheduler": scheduler_name or None,
            "error": str(exc),
        }

    return {"applied": False, "sampler": sampler_name or None, "scheduler": scheduler_name or None}


def build_pipelines(model_name_or_path: str) -> tuple[Any, Any, str, str, str]:
    dtype, device = torch_dtype_and_device()
    detected = detect_pipeline_type(model_name_or_path)
    use_safetensors = model_name_or_path.lower().endswith(".safetensors")

    if is_local_file(model_name_or_path):
        if detected == "sdxl":
            try:
                t2i_pipe = StableDiffusionXLPipeline.from_single_file(
                    model_name_or_path,
                    torch_dtype=dtype,
                    use_safetensors=use_safetensors,
                )
                i2i_pipe = StableDiffusionXLImg2ImgPipeline.from_single_file(
                    model_name_or_path,
                    torch_dtype=dtype,
                    use_safetensors=use_safetensors,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to load local SDXL checkpoint as an SDXL pipeline: {model_name_or_path}. "
                    f"SpellVision will not fall back to the legacy SD pipeline for a checkpoint that looks like SDXL. Original error: {exc}"
                ) from exc
        elif detected in {"flux", "sd3"}:
            raise RuntimeError(
                f"Direct local single-file loading for {detected.upper()} checkpoints is not configured in the worker yet: {model_name_or_path}"
            )
        else:
            t2i_pipe = StableDiffusionPipeline.from_single_file(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=use_safetensors,
            )
            i2i_pipe = StableDiffusionImg2ImgPipeline.from_single_file(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=use_safetensors,
            )
            detected = "sd"
    else:
        if detected == "sdxl":
            t2i_pipe = StableDiffusionXLPipeline.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
                variant="fp16" if device == "cuda" else None,
            )
            i2i_pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
                variant="fp16" if device == "cuda" else None,
            )
        else:
            t2i_pipe = AutoPipelineForText2Image.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
            )
            i2i_pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
            )

    t2i_pipe = optimize_pipeline(t2i_pipe.to(device), device)
    i2i_pipe = optimize_pipeline(i2i_pipe.to(device), device)

    return t2i_pipe, i2i_pipe, device, str(dtype), detected


def get_or_load_pipelines(model_name_or_path: str) -> tuple[Any, Any, str, str, str, bool, dict[str, Any] | None]:
    with CACHE_LOCK:
        if MODEL_CACHE["key"] == model_name_or_path and MODEL_CACHE["pipe"] is not None:
            return (
                MODEL_CACHE["pipe"],
                MODEL_CACHE["img2img_pipe"],
                MODEL_CACHE["device"],
                MODEL_CACHE["dtype"],
                MODEL_CACHE["detected"],
                True,
                None,
            )

    swap_cleanup_stats = cleanup_for_model_swap(model_name_or_path)

    load_start = time.perf_counter()
    t2i_pipe, i2i_pipe, device, dtype, detected = build_pipelines(model_name_or_path)
    load_time_sec = round(time.perf_counter() - load_start, 3)
    memory_after_load = cuda_memory_snapshot()

    with CACHE_LOCK:
        MODEL_CACHE["key"] = model_name_or_path
        MODEL_CACHE["pipe"] = t2i_pipe
        MODEL_CACHE["img2img_pipe"] = i2i_pipe
        MODEL_CACHE["device"] = device
        MODEL_CACHE["dtype"] = dtype
        MODEL_CACHE["detected"] = detected

    if swap_cleanup_stats is None:
        current_memory = cuda_memory_snapshot()
        swap_cleanup_stats = {
            "old_key": None,
            "requested_key": model_name_or_path,
            "cleanup_time_sec": 0.0,
            "memory_before": current_memory,
            "memory_after": current_memory,
        }

    swap_cleanup_stats["model_load_time_sec"] = load_time_sec
    swap_cleanup_stats["memory_after_load"] = memory_after_load

    return t2i_pipe, i2i_pipe, device, dtype, detected, False, swap_cleanup_stats


VIDEO_OUTPUT_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif"}
VIDEO_COMMANDS = {"t2v", "i2v", "v2v", "ti2v", "video"}


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
    os.makedirs(os.path.dirname(metadata_output), exist_ok=True)
    with open(metadata_output, "w", encoding="utf-8") as file_obj:
        json.dump(data, file_obj, indent=2)


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
        data.update(_spellvision_teacache_metadata(req))
    queue_metadata_write(metadata_output, data)
    return data


class JobState(str, Enum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATES = {
    JobState.COMPLETED,
    JobState.FAILED,
    JobState.CANCELLED,
}


VALID_TRANSITIONS = {
    JobState.QUEUED: {JobState.STARTING, JobState.CANCELLED},
    JobState.STARTING: {JobState.RUNNING, JobState.FAILED, JobState.CANCELLED},
    JobState.RUNNING: {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED},
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}


@dataclass
class JobProgress:
    current: int = 0
    total: int = 0
    percent: float = 0.0
    message: str = "waiting"


@dataclass
class JobError:
    code: str
    message: str
    details: dict[str, Any] | None = None
    traceback: str | None = None


@dataclass
class JobResult:
    output: str | None = None
    cache_hit: bool = False
    generation_time_sec: float | None = None
    steps_per_sec: float | None = None
    cuda_allocated_gb: float | None = None
    cuda_reserved_gb: float | None = None
    metadata_output: str | None = None
    backend_name: str | None = None
    detected_pipeline: str | None = None
    task_type: str | None = None
    source_job_id: str | None = None
    retry_count: int = 0
    video_backend_type: str | None = None
    video_backend_name: str | None = None
    video_output: str | None = None
    video_metadata_output: str | None = None
    video_request_kind: str | None = None
    video_stack_kind: str | None = None
    video_stack_mode: str | None = None
    video_stack_ready: bool = False
    video_frames: int = 0
    video_fps: int = 0
    video_duration_seconds: float = 0.0
    video_duration_label: str | None = None
    video_has_input_image: bool = False
    video_input_image: str | None = None
    video_prompt_id: str | None = None


@dataclass
class JobTimestamps:
    created_at: str = field(default_factory=utc_now_iso)
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class JobRecord:
    job_id: str
    command: str
    state: JobState = JobState.QUEUED
    progress: JobProgress = field(default_factory=JobProgress)
    result: JobResult | None = None
    error: JobError | None = None
    timestamps: JobTimestamps = field(default_factory=JobTimestamps)
    cancel_requested: bool = False
    source_job_id: str | None = None
    retry_count: int = 0

    def payload(self) -> dict[str, Any]:
        return {
            "type": "job_update",
            "job_id": self.job_id,
            "command": self.command,
            "state": self.state.value,
            "progress": asdict(self.progress),
            "result": asdict(self.result) if self.result else None,
            "error": asdict(self.error) if self.error else None,
            "timestamps": asdict(self.timestamps),
            "source_job_id": self.source_job_id,
            "retry_count": self.retry_count,
        }


def create_job(req: dict[str, Any]) -> JobRecord:
    return JobRecord(
        job_id=req.get("job_id") or f"job_{uuid.uuid4().hex[:12]}",
        command=str(req.get("command", "unknown")),
        source_job_id=req.get("retry_of"),
        retry_count=int(req.get("retry_count") or 0),
    )


def transition_job(job: JobRecord, new_state: JobState) -> bool:
    if job.state == new_state:
        return True
    if job.state in TERMINAL_STATES:
        return False
    if new_state not in VALID_TRANSITIONS.get(job.state, set()):
        return False

    now = utc_now_iso()
    job.state = new_state
    job.timestamps.updated_at = now

    if new_state == JobState.STARTING and not job.timestamps.started_at:
        job.timestamps.started_at = now

    if new_state in TERMINAL_STATES:
        job.timestamps.finished_at = now

    return True


def set_job_message(job: JobRecord, message: str) -> None:
    job.progress.message = message
    job.timestamps.updated_at = utc_now_iso()


def update_job_progress(job: JobRecord, step: int, total: int, message: str | None = None) -> None:
    total = max(int(total), 0)
    step = max(int(step), 0)
    percent = 0.0 if total <= 0 else round((step / total) * 100.0, 2)

    job.progress.current = step
    job.progress.total = total
    job.progress.percent = max(0.0, min(100.0, percent))
    if message is not None:
        job.progress.message = message
    job.timestamps.updated_at = utc_now_iso()


def complete_job(job: JobRecord, payload: dict[str, Any]) -> None:
    job.result = JobResult(
        output=payload.get("output"),
        cache_hit=bool(payload.get("cache_hit", False)),
        generation_time_sec=payload.get("generation_time_sec"),
        steps_per_sec=payload.get("steps_per_sec"),
        cuda_allocated_gb=payload.get("cuda_allocated_gb"),
        cuda_reserved_gb=payload.get("cuda_reserved_gb"),
        metadata_output=payload.get("metadata_output"),
        backend_name=payload.get("backend_name"),
        detected_pipeline=payload.get("detected_pipeline"),
        task_type=payload.get("task_type"),
        source_job_id=payload.get("source_job_id"),
        retry_count=int(payload.get("retry_count") or 0),
        video_backend_type=payload.get("video_backend_type"),
        video_backend_name=payload.get("video_backend_name"),
        video_output=payload.get("video_output"),
        video_metadata_output=payload.get("video_metadata_output"),
        video_request_kind=payload.get("video_request_kind"),
        video_stack_kind=payload.get("video_stack_kind"),
        video_stack_mode=payload.get("video_stack_mode"),
        video_stack_ready=bool(payload.get("video_stack_ready", False)),
        video_frames=int(payload.get("video_frames") or 0),
        video_fps=int(payload.get("video_fps") or 0),
        video_duration_seconds=float(payload.get("video_duration_seconds") or 0.0),
        video_duration_label=payload.get("video_duration_label"),
        video_has_input_image=bool(payload.get("video_has_input_image", False)),
        video_input_image=payload.get("video_input_image"),
        video_prompt_id=payload.get("video_prompt_id"),
    )
    update_job_progress(job, job.progress.total or job.progress.current or 1, job.progress.total or 1, "generation complete")
    transition_job(job, JobState.COMPLETED)


def fail_job(job: JobRecord, message: str, code: str = "generation_error", tb: str | None = None, details: dict[str, Any] | None = None) -> None:
    job.error = JobError(
        code=code,
        message=message,
        details=details,
        traceback=tb,
    )
    transition_job(job, JobState.FAILED)


def cancel_job(job: JobRecord, message: str = "Generation cancelled", details: dict[str, Any] | None = None) -> None:
    if job.state in TERMINAL_STATES:
        return
    job.cancel_requested = True
    job.error = JobError(
        code="cancelled",
        message=message,
        details=details,
        traceback=None,
    )
    transition_job(job, JobState.CANCELLED)


def register_active_job(active_job: ActiveJobHandle) -> None:
    with ACTIVE_JOBS_LOCK:
        ACTIVE_JOBS[active_job.job.job_id] = active_job


def unregister_active_job(job_id: str) -> None:
    with ACTIVE_JOBS_LOCK:
        ACTIVE_JOBS.pop(job_id, None)


def get_active_job(job_id: str) -> ActiveJobHandle | None:
    with ACTIVE_JOBS_LOCK:
        return ACTIVE_JOBS.get(job_id)


def request_job_cancel(job_id: str) -> tuple[bool, JobRecord | None]:
    active_job = get_active_job(job_id)
    if active_job is None:
        return False, None

    active_job.job.cancel_requested = True
    active_job.cancel_event.set()
    return True, active_job.job


def raise_if_cancelled(active_job: ActiveJobHandle, emitter: JobEmitter, stage: str) -> None:
    if not active_job.cancel_event.is_set() and not active_job.job.cancel_requested:
        return

    cancel_job(active_job.job, f"Generation cancelled during {stage}")
    emitter.emit_job_update(active_job.job)
    raise JobCancelledError(active_job.job.error.message if active_job.job.error else "Generation cancelled")


class EventEmitter:
    def __init__(self, handler: socketserver.StreamRequestHandler):
        self.handler = handler
        self.lock = threading.Lock()
        self.client_disconnected = False

    def emit(self, payload: dict[str, Any]) -> None:
        if self.client_disconnected:
            return
        with self.lock:
            try:
                self.handler.wfile.write((json.dumps(payload) + "\n").encode("utf-8"))
                self.handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                self.client_disconnected = True

    def emit_job_update(self, job: JobRecord) -> None:
        self.emit(job.payload())

    def status(self, job: JobRecord, message: str) -> None:
        set_job_message(job, message)
        self.emit_job_update(job)
        self.emit({"type": "status", "job_id": job.job_id, "message": message})

    def progress(self, job: JobRecord, step: int, total: int, message: str | None = None) -> None:
        update_job_progress(job, step, total, message)
        self.emit_job_update(job)
        self.emit(
            {
                "type": "progress",
                "job_id": job.job_id,
                "step": step,
                "total": total,
                "percent": int(job.progress.percent),
            }
        )

    def result(self, job: JobRecord) -> None:
        payload: dict[str, Any] = {"type": "result", "ok": job.state == JobState.COMPLETED, "job_id": job.job_id, "state": job.state.value}
        if job.result is not None:
            payload.update(asdict(job.result))
        if job.error is not None:
            payload["error"] = job.error.message
            if job.error.traceback:
                payload["traceback"] = job.error.traceback
        self.emit(payload)

    def error(self, job: JobRecord, error_text: str, tb: str | None = None, code: str = "generation_error") -> None:
        fail_job(job, error_text, code=code, tb=tb)
        self.emit_job_update(job)
        payload: dict[str, Any] = {"type": "error", "ok": False, "job_id": job.job_id, "state": job.state.value, "error": error_text}
        if tb:
            payload["traceback"] = tb
        self.emit(payload)


def build_generation_kwargs(
    req: dict[str, Any],
    generator: torch.Generator,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "prompt": req["prompt"],
        "num_inference_steps": int(req["steps"]),
        "guidance_scale": float(req["cfg"]),
        "generator": generator,
    }

    if req.get("negative_prompt"):
        kwargs["negative_prompt"] = req["negative_prompt"]

    if extra:
        kwargs.update(extra)

    return kwargs


def attach_progress_callback(
    pipe: Any,
    kwargs: dict[str, Any],
    req: dict[str, Any],
    emitter: JobEmitter,
    job: JobRecord,
    active_job: ActiveJobHandle,
) -> None:
    total_steps = int(req["steps"])
    signature = inspect.signature(pipe.__call__)

    def step_end_callback(_pipe: Any, step_index: int, _timestep: Any, callback_kwargs: dict[str, Any]) -> dict[str, Any]:
        if active_job.cancel_event.is_set() or job.cancel_requested:
            cancel_job(job, f"Generation cancelled during step {step_index + 1}/{total_steps}")
            emitter.emit_job_update(job)
            raise JobCancelledError(job.error.message if job.error else "Generation cancelled")
        emitter.progress(job, step_index + 1, total_steps, f"running step {step_index + 1}/{total_steps}")
        return callback_kwargs

    def legacy_callback(step: int, _timestep: Any, _latents: Any) -> None:
        if active_job.cancel_event.is_set() or job.cancel_requested:
            cancel_job(job, f"Generation cancelled during step {step + 1}/{total_steps}")
            emitter.emit_job_update(job)
            raise JobCancelledError(job.error.message if job.error else "Generation cancelled")
        emitter.progress(job, step + 1, total_steps, f"running step {step + 1}/{total_steps}")

    if "callback_on_step_end" in signature.parameters:
        kwargs["callback_on_step_end"] = step_end_callback
    elif "callback" in signature.parameters:
        kwargs["callback"] = legacy_callback
        kwargs["callback_steps"] = 1


def run_t2i(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    emitter.status(job, "loading pipeline")
    transition_job(job, JobState.STARTING)
    emitter.emit_job_update(job)

    pipe, _, device, dtype, detected, cache_hit, model_swap_cleanup = get_or_load_pipelines(req["model"])
    raise_if_cancelled(active_job, emitter, "pipeline loading")

    lora_used = False
    lora_stats = {
        "lora_cache_hit": False,
        "lora_reloaded": False,
        "lora_cleared": False,
        "active_lora_path": None,
        "active_lora_scale": None,
    }
    if req.get("lora"):
        emitter.status(job, "loading lora")
        lora_used, lora_stats = maybe_load_lora(pipe, req["lora"], float(req.get("lora_scale", 1.0)), "t2i")
        raise_if_cancelled(active_job, emitter, "lora loading")
    else:
        reset_lora_state(pipe, "t2i")

    scheduler_stats = apply_sampler_and_scheduler(pipe, req)

    if device == "cuda":
        generator = torch.Generator(device="cuda").manual_seed(int(req["seed"]))
    else:
        generator = torch.Generator().manual_seed(int(req["seed"]))

    kwargs = build_generation_kwargs(
        req,
        generator,
        {
            "width": int(req["width"]),
            "height": int(req["height"]),
        },
    )
    attach_progress_callback(pipe, kwargs, req, emitter, job, active_job)

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "running pipeline")
    raise_if_cancelled(active_job, emitter, "pipeline startup")

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start

    raise_if_cancelled(active_job, emitter, "pipeline completion")

    image = result.images[0]
    os.makedirs(os.path.dirname(req["output"]), exist_ok=True)
    if len(req["output"]) > 240:
        raise RuntimeError(f"Output path too long after queue/retry naming: {req['output']}")
    image.save(req["output"], "PNG")

    steps_per_sec = int(req["steps"]) / elapsed if elapsed > 0 else 0.0

    raise_if_cancelled(active_job, emitter, "metadata handoff")

    lora_cache_hit = bool(lora_stats.get("lora_cache_hit", False))
    lora_reloaded = bool(lora_stats.get("lora_reloaded", False))

    metadata_payload = save_metadata(
        req=req,
        image_path=req["output"],
        metadata_output=req["metadata_output"],
        backend_name=pipe.__class__.__name__,
        device=device,
        dtype=dtype,
        detected_pipeline=detected,
        lora_used=lora_used,
        elapsed=elapsed,
        steps_per_sec=steps_per_sec,
        job=job,
        cache_hit=cache_hit,
        model_swap_cleanup=model_swap_cleanup,
        lora_cache_hit=lora_cache_hit,
        lora_reloaded=lora_reloaded,
        queue_warm_reuse_expected=bool(req.get("queue_warm_reuse_expected")),
        queue_warm_reuse_source=req.get("queue_warm_reuse_source"),
        queue_affinity_signature=req.get("queue_affinity_signature"),
    )

    payload = {
        "ok": True,
        "cache_hit": cache_hit,
        "output": req["output"],
        "metadata_output": req["metadata_output"],
        "backend_name": pipe.__class__.__name__,
        "detected_pipeline": detected,
        "task_type": req.get("task_type", req.get("command", "unknown")),
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cuda_allocated_gb": round(torch.cuda.memory_allocated() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "cuda_reserved_gb": round(torch.cuda.memory_reserved() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "model_swap_cleanup": model_swap_cleanup,
        "model_cleanup_time_sec": model_swap_cleanup.get("cleanup_time_sec") if model_swap_cleanup else 0.0,
        "model_load_time_sec": model_swap_cleanup.get("model_load_time_sec") if model_swap_cleanup else None,
        "memory_after_load": model_swap_cleanup.get("memory_after_load") if model_swap_cleanup else None,
        "lora_cache_hit": lora_cache_hit,
        "lora_reloaded": lora_reloaded,
        "queue_warm_reuse_expected": bool(req.get("queue_warm_reuse_expected")),
        "queue_warm_reuse_source": req.get("queue_warm_reuse_source"),
        "queue_affinity_signature": req.get("queue_affinity_signature"),
        "sampler": req.get("sampler"),
        "scheduler": req.get("scheduler"),
        "scheduler_applied": bool(scheduler_stats.get("applied")),
        "scheduler_class": scheduler_stats.get("scheduler_class"),
        "metadata": metadata_payload,
        "metadata_write_deferred": True,
    }

    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


def _load_json_file(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.exists():
        raise RuntimeError(f"File not found: {path_value}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object in {path_value}")
    return payload


def _workflow_slot_values_from_request(req: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": req.get("prompt"),
        "negative_prompt": req.get("negative_prompt"),
        "seed": req.get("seed"),
        "steps": req.get("steps"),
        "cfg": req.get("cfg"),
        "width": req.get("width"),
        "height": req.get("height"),
        "input_image": req.get("input_image"),
        "strength": req.get("strength"),
        "checkpoint": req.get("model"),
        "model": req.get("model"),
        "lora": req.get("lora"),
        "lora_scale": req.get("lora_scale"),
    }


def _set_workflow_path(root: dict[str, Any], path_expr: str, value: Any) -> None:
    if value is None or path_expr is None:
        return
    parts = [part for part in str(path_expr).split('.') if part]
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
    leaf = parts[-1] if parts else ""
    if isinstance(cursor, dict):
        cursor[leaf] = value
    elif isinstance(cursor, list):
        try:
            idx = int(leaf)
        except Exception:
            return
        if 0 <= idx < len(cursor):
            cursor[idx] = value


def _apply_workflow_slot_bindings(workflow: dict[str, Any], slot_bindings: dict[str, Any], req: dict[str, Any]) -> None:
    slot_values = _workflow_slot_values_from_request(req)
    for slot, raw_value in slot_values.items():
        if raw_value in (None, ""):
            continue
        binding = slot_bindings.get(slot)
        if not isinstance(binding, dict):
            continue
        path_expr = str(binding.get("path") or "").strip()
        if not path_expr:
            node_id = str(binding.get("node_id") or "").strip()
            input_name = str(binding.get("input_name") or binding.get("input") or "").strip()
            if node_id and input_name:
                path_expr = f"{node_id}.inputs.{input_name}"
        if path_expr:
            _set_workflow_path(workflow, path_expr, raw_value)


def _apply_common_comfy_overrides(workflow: dict[str, Any], req: dict[str, Any]) -> None:
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
        for field_name, value in mapping.items():
            if value in (None, ""):
                continue
            for key in aliases.get(field_name, set()):
                if key in inputs and not isinstance(inputs.get(key), (list, dict)):
                    inputs[key] = value


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


def _poll_comfy_history(api_url: str, prompt_id: str, req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    poll_interval = float(req.get("comfy_poll_interval_sec") or 1.0)
    timeout_sec = float(req.get("comfy_timeout_sec") or 1800.0)
    start = time.monotonic()
    tick = 0
    while True:
        raise_if_cancelled(active_job, emitter, "waiting for ComfyUI")
        elapsed = time.monotonic() - start
        tick += 1
        emitter.progress(job, min(95, max(1, tick)), 100, comfy_waiting_message(req, elapsed))
        try:
            with urllib.request.urlopen(f"{api_url}/history/{prompt_id}", timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError:
            if elapsed >= timeout_sec:
                raise RuntimeError(f"Timed out waiting for ComfyUI prompt {prompt_id}")
            time.sleep(poll_interval)
            continue

        history = payload.get(prompt_id)
        if isinstance(history, dict):
            status = history.get("status") or {}
            if isinstance(status, dict) and status.get("status_str") in {"error", "failed"}:
                raise RuntimeError(f"ComfyUI prompt failed: {status}")
            outputs = history.get("outputs")
            if isinstance(outputs, dict) and outputs:
                return history

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

    if input_key in {"text", "prompt", "negative_prompt"} and "textencode" in class_key:
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




def request_has_workflow_binding(req: dict[str, Any]) -> bool:
    for key in ("compiled_prompt_path", "workflow_path", "profile_path", "workflow_profile_path"):
        if str(req.get(key) or "").strip():
            return True
    return False


def _import_diffusers_symbol(name: str) -> Any | None:
    try:
        import diffusers  # type: ignore
    except Exception:
        return None
    return getattr(diffusers, name, None)



def _video_model_stack_from_request(req: dict[str, Any]) -> dict[str, Any]:
    raw = req.get("video_model_stack") or req.get("model_stack") or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _first_stack_value(stack: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(stack.get(key) or "").strip()
        if value:
            return value
    return ""


def _stack_missing_parts(stack: dict[str, Any]) -> list[str]:
    raw = stack.get("missing_parts")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _stack_summary(stack: dict[str, Any]) -> str:
    if not stack:
        return "no video model stack"
    family = str(stack.get("family") or "unknown").strip()
    kind = str(stack.get("stack_kind") or stack.get("role") or "stack").strip()
    primary = _first_stack_value(stack, ("diffusers_path", "primary_path", "transformer_path", "unet_path", "model_path"))
    missing = _stack_missing_parts(stack)
    bits = [f"family={family}", f"kind={kind}"]
    if primary:
        bits.append(f"primary={primary}")
    if missing:
        bits.append("missing=" + ", ".join(missing))
    return "; ".join(bits)

def _native_video_model_reference(req: dict[str, Any]) -> str:
    stack = _video_model_stack_from_request(req)
    if stack:
        diffusers_path = _first_stack_value(stack, ("diffusers_path", "model_dir", "model_directory"))
        if diffusers_path:
            return diffusers_path

        primary = _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path"))
        if primary:
            return primary

    model = str(req.get("model") or req.get("model_id") or "").strip()
    if model.startswith("hf://"):
        model = model[5:]
    if not model:
        raise RuntimeError("Native video generation requires a model directory, Hugging Face repo id, or configured video model stack.")
    return model

def _infer_native_video_family(req: dict[str, Any]) -> str:
    stack = _video_model_stack_from_request(req)
    stack_family = str(stack.get("family") or "").strip().lower().replace("-", "_")
    if stack_family:
        return stack_family

    explicit = str(req.get("model_family") or req.get("family") or "").strip().lower().replace("-", "_")
    if explicit:
        return explicit
    model_text = " ".join([
        str(req.get("model") or ""),
        str(req.get("model_display") or ""),
        _stack_summary(stack),
    ]).strip().lower()
    for family, markers in {
        "wan": ("wan", "wan2", "wan-2"),
        "ltx": ("ltx", "ltxv"),
        "hunyuan_video": ("hunyuan", "hyvideo"),
        "cogvideox": ("cogvideo", "cogvideox"),
        "mochi": ("mochi",),
    }.items():
        if any(marker in model_text for marker in markers):
            return family
    return "unknown"

def _native_video_pipeline_candidates(command: str, family: str) -> list[str]:
    command = str(command or "").strip().lower()
    family = str(family or "unknown").strip().lower()

    if family == "wan":
        return ["WanImageToVideoPipeline", "WanPipeline"] if command == "i2v" else ["WanPipeline"]
    if family == "ltx":
        return ["LTXImageToVideoPipeline", "LTXVideoPipeline", "LTXPipeline"] if command == "i2v" else ["LTXVideoPipeline", "LTXPipeline"]
    if family == "hunyuan_video":
        return ["HunyuanVideoImageToVideoPipeline", "HunyuanVideoPipeline"] if command == "i2v" else ["HunyuanVideoPipeline"]
    if family == "cogvideox":
        return ["CogVideoXImageToVideoPipeline", "CogVideoXPipeline"] if command == "i2v" else ["CogVideoXPipeline"]
    if family == "mochi":
        return ["MochiPipeline"]

    return [
        "WanImageToVideoPipeline",
        "WanPipeline",
        "LTXImageToVideoPipeline",
        "LTXVideoPipeline",
        "CogVideoXImageToVideoPipeline",
        "CogVideoXPipeline",
        "HunyuanVideoPipeline",
        "MochiPipeline",
    ] if command == "i2v" else [
        "WanPipeline",
        "LTXVideoPipeline",
        "CogVideoXPipeline",
        "HunyuanVideoPipeline",
        "MochiPipeline",
    ]


def _is_split_video_stack_request(req: dict[str, Any]) -> bool:
    stack = _video_model_stack_from_request(req)
    stack_kind = str(stack.get("stack_kind") or req.get("native_video_stack_kind") or "").strip().lower()
    if stack_kind == "split_stack":
        return True
    model_ref = _native_video_model_reference(req)
    return Path(model_ref).suffix.lower() in {".safetensors", ".ckpt", ".bin", ".gguf"}


def _comfy_object_info(api_url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(f"{api_url}/object_info", timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to read ComfyUI object_info from {api_url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("ComfyUI /object_info did not return a JSON object")
    return payload


def _comfy_input_info(object_info: dict[str, Any], class_name: str) -> dict[str, Any]:
    class_info = object_info.get(class_name)
    if not isinstance(class_info, dict):
        return {}

    input_info = class_info.get("input")
    if not isinstance(input_info, dict):
        return {}

    return input_info


def _comfy_input_bucket(object_info: dict[str, Any], class_name: str, bucket: str) -> dict[str, Any]:
    input_info = _comfy_input_info(object_info, class_name)
    bucket_value = input_info.get(bucket)
    if not isinstance(bucket_value, dict):
        return {}

    return bucket_value


def _comfy_class_inputs(object_info: dict[str, Any], class_name: str) -> set[str]:
    names: set[str] = set()
    for bucket in ("required", "optional"):
        values = _comfy_input_bucket(object_info, class_name, bucket)
        names.update(str(name) for name in values.keys())
    return names


def _comfy_required_inputs(object_info: dict[str, Any], class_name: str) -> set[str]:
    values = _comfy_input_bucket(object_info, class_name, "required")
    return {str(name) for name in values.keys()}


def _first_available_class(object_info: dict[str, Any], candidates: tuple[str, ...], *, label: str) -> str:
    for class_name in candidates:
        if class_name in object_info:
            return class_name
    raise RuntimeError(
        f"The SpellVision native video template needs a Comfy node for {label}, but none of these classes are available: "
        + ", ".join(candidates)
        + ". Install/enable the appropriate Comfy video nodes, then retry."
    )


def _path_after_named_dir(path_value: str, dir_names: tuple[str, ...]) -> str:
    normalized = Path(path_value).as_posix()
    parts = normalized.split("/")
    lowered = [part.lower() for part in parts]
    for dir_name in dir_names:
        token = dir_name.lower()
        if token in lowered:
            idx = lowered.index(token)
            tail = "/".join(parts[idx + 1:]).strip("/")
            if tail:
                return tail
    return Path(path_value).name


def _comfy_unet_name(path_value: str) -> str:
    return _path_after_named_dir(path_value, ("diffusion_models", "unet", "checkpoints"))


def _comfy_vae_name(path_value: str) -> str:
    return _path_after_named_dir(path_value, ("vae",))


def _comfy_clip_name(path_value: str) -> str:
    return _path_after_named_dir(path_value, ("text_encoders", "clip", "encoders"))


def _filename_prefix_from_output(output_path: str, job_id: str) -> str:
    raw = str(output_path or "").strip()
    if not raw:
        return f"spellvision_native_video_{job_id}"
    stem = Path(raw).stem or f"spellvision_native_video_{job_id}"
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", stem)[:96] or f"spellvision_native_video_{job_id}"


def _set_if_allowed(inputs: dict[str, Any], allowed: set[str], aliases: tuple[str, ...], value: Any) -> bool:
    if value is None:
        return False
    for name in aliases:
        if name in allowed:
            inputs[name] = value
            return True
    return False


def _input_default_choice(object_info: dict[str, Any], class_name: str, input_name: str, fallback: Any = None) -> Any:
    for bucket in ("required", "optional"):
        values = _comfy_input_bucket(object_info, class_name, bucket)
        if input_name not in values:
            continue

        spec = values.get(input_name)
        if isinstance(spec, dict):
            default_value = spec.get("default")
            if default_value is not None:
                return default_value

        if isinstance(spec, (list, tuple)) and spec:
            first = spec[0]
            if isinstance(first, list) and first:
                return first[0]
            if isinstance(first, tuple) and first:
                return first[0]

            # Modern Comfy schemas often look like ["INT", {"default": 30}]
            # or ["COMBO", {"default": "auto", "options": [...]}].
            if len(spec) > 1 and isinstance(spec[1], dict):
                default_value = spec[1].get("default")
                if default_value is not None:
                    return default_value
                options = spec[1].get("options")
                if isinstance(options, list) and options:
                    return options[0]

        if isinstance(spec, (list, tuple)) and len(spec) > 1 and isinstance(spec[1], dict):
            default_value = spec[1].get("default")
            if default_value is not None:
                return default_value

    return fallback



def _clip_loader_type_for_family(family: str) -> str:
    family = str(family or "").strip().lower()
    if family == "wan":
        return "wan"
    if family == "hunyuan_video":
        return "hunyuan_video"
    if family == "ltx":
        return "ltxv"
    if family == "mochi":
        return "mochi"
    return "stable_diffusion"


def _add_node(prompt: dict[str, Any], node_id: str, class_type: str, inputs: dict[str, Any]) -> None:
    prompt[node_id] = {"class_type": class_type, "inputs": inputs}


def _int_or_default(value: Any, default: int) -> int:
    if value in (None, ""):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_clip_loader_node(
    prompt: dict[str, Any],
    object_info: dict[str, Any],
    stack: dict[str, Any],
    family: str,
) -> str:
    clip1_path = str(stack.get("text_encoder_path") or "").strip()
    clip2_path = str(stack.get("text_encoder_2_path") or "").strip()
    if not clip1_path:
        raise RuntimeError("The selected native split video stack does not include a text encoder path.")

    if clip2_path and "DualCLIPLoader" in object_info:
        class_name = "DualCLIPLoader"
        allowed = _comfy_class_inputs(object_info, class_name)
        inputs: dict[str, Any] = {}
        _set_if_allowed(inputs, allowed, ("clip_name1", "clip1_name"), _comfy_clip_name(clip1_path))
        _set_if_allowed(inputs, allowed, ("clip_name2", "clip2_name"), _comfy_clip_name(clip2_path))
        _set_if_allowed(inputs, allowed, ("type", "clip_type"), _clip_loader_type_for_family(family))
        _add_node(prompt, "2", class_name, inputs)
        return "2"

    class_name = _first_available_class(object_info, ("CLIPLoader", "DualCLIPLoader"), label="text encoder loading")
    allowed = _comfy_class_inputs(object_info, class_name)
    inputs = {}
    if class_name == "DualCLIPLoader":
        _set_if_allowed(inputs, allowed, ("clip_name1", "clip1_name"), _comfy_clip_name(clip1_path))
        _set_if_allowed(inputs, allowed, ("clip_name2", "clip2_name"), _comfy_clip_name(clip1_path))
    else:
        _set_if_allowed(inputs, allowed, ("clip_name", "clip", "text_encoder_name"), _comfy_clip_name(clip1_path))
    _set_if_allowed(inputs, allowed, ("type", "clip_type"), _clip_loader_type_for_family(family))
    _add_node(prompt, "2", class_name, inputs)
    return "2"




def _comfy_input_choices(object_info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    if not isinstance(object_info, dict):
        return []

    info = object_info.get(class_name)
    if not isinstance(info, dict):
        return []

    raw_input_info = info.get("input")
    if not isinstance(raw_input_info, dict):
        return []

    for bucket in ("required", "optional"):
        values = raw_input_info.get(bucket)
        if not isinstance(values, dict):
            continue

        spec = values.get(input_name)
        if not isinstance(spec, (list, tuple)) or not spec:
            continue

        first = spec[0]
        if isinstance(first, (list, tuple)):
            return [str(item) for item in first if str(item).strip()]

    return []


def _preferred_video_vae_name(object_info: dict[str, Any], family: str, vae_path: str) -> str:
    requested = _comfy_vae_name(vae_path)
    available = _comfy_input_choices(object_info, "VAELoader", "vae_name")
    available_lower = {item.lower(): item for item in available}

    family_key = str(family or "").strip().lower()

    if family_key == "wan":
        for preferred in (
            "wan2.2_vae.safetensors",
            "wan_2.2_vae.safetensors",
            "wan2.1_vae.safetensors",
            "wan_2.1_vae.safetensors",
        ):
            found = available_lower.get(preferred.lower())
            if found:
                return found

        for item in available:
            lowered = item.lower()
            if "wan" in lowered and "vae" in lowered and "onthefly" not in lowered:
                return item

    if family_key in {"hunyuan_video", "hunyuan"}:
        for preferred in (
            "hunyuan_video_vae_bf16.safetensors",
            "hunyuan_video_vae_fp16.safetensors",
        ):
            found = available_lower.get(preferred.lower())
            if found:
                return found

    if requested in available:
        return requested

    return requested




def _sv_comfy_input_choices(object_info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    for bucket in ("required", "optional"):
        values = _comfy_input_bucket(object_info, class_name, bucket)
        spec = values.get(input_name)
        if isinstance(spec, (list, tuple)) and spec:
            first = spec[0]
            if isinstance(first, (list, tuple)):
                return [str(item) for item in first if str(item).strip()]
            if len(spec) > 1 and isinstance(spec[1], dict):
                options = spec[1].get("options")
                if isinstance(options, list):
                    return [str(item) for item in options if str(item).strip()]
    return []


def _sv_choose_comfy_choice(object_info: dict[str, Any], class_name: str, input_name: str, requested: str) -> str:
    requested = str(requested or "").strip()
    requested_name = Path(requested).name
    available = _sv_comfy_input_choices(object_info, class_name, input_name)
    if not available:
        return requested_name or requested

    by_lower = {item.lower(): item for item in available}
    for candidate in (requested, requested_name):
        found = by_lower.get(str(candidate).lower())
        if found:
            return found

    # Prefer a basename match when a stale subfolder-prefixed value leaks through.
    for item in available:
        if Path(item).name.lower() == requested_name.lower():
            return item

    return requested_name or requested


def _sv_video_primary_name(object_info: dict[str, Any], primary_path: str, *, class_name: str = "WanVideoModelLoader") -> str:
    return _sv_choose_comfy_choice(object_info, class_name, "model", _comfy_unet_name(primary_path))


def _sv_video_text_encoder_name(object_info: dict[str, Any], stack: dict[str, Any]) -> str:
    explicit = str(stack.get("text_encoder_path") or stack.get("text_encoder") or "").strip()
    available = _sv_comfy_input_choices(object_info, "LoadWanVideoT5TextEncoder", "model_name")
    by_lower = {item.lower(): item for item in available}

    if explicit:
        found = by_lower.get(Path(explicit).name.lower())
        if found:
            return found

    for preferred in (
        "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "umt5_xxl_fp16.safetensors",
        "umt5_xxl_bf16.safetensors",
        "t5xxl_fp8_e4m3fn_scaled.safetensors",
        "t5xxl_fp16.safetensors",
        "t5xxl_bf16.safetensors",
    ):
        found = by_lower.get(preferred.lower())
        if found:
            return found

    for item in available:
        lowered = item.lower()
        if "umt5" in lowered or "t5xxl" in lowered or "t5" in lowered:
            return item

    return Path(explicit).name if explicit else ""


def _sv_video_vae_name(object_info: dict[str, Any], stack: dict[str, Any]) -> str:
    explicit = str(stack.get("vae_path") or stack.get("vae") or "").strip()
    available = _sv_comfy_input_choices(object_info, "WanVideoVAELoader", "model_name")
    by_lower = {item.lower(): item for item in available}

    if explicit:
        found = by_lower.get(Path(explicit).name.lower())
        if found:
            return found

    for preferred in (
        "wan2.2_vae.safetensors",
        "wan_2.1_vae.safetensors",
        "onTHEFLYWanAIWan21VideoModel_kijaiWan21VAE.safetensors",
    ):
        found = by_lower.get(preferred.lower())
        if found:
            return found

    for item in available:
        lowered = item.lower()
        if "wan" in lowered and "vae" in lowered:
            return item

    return Path(explicit).name if explicit else ""


def _sv_set_default_required_inputs(
    inputs: dict[str, Any],
    object_info: dict[str, Any],
    class_name: str,
    *,
    skip: set[str] | None = None,
) -> None:
    skip = skip or set()
    for input_name in sorted(_comfy_required_inputs(object_info, class_name)):
        if input_name in inputs or input_name in skip:
            continue
        default_value = _input_default_choice(object_info, class_name, input_name, None)
        if default_value is not None:
            inputs[input_name] = default_value


def _sv_add_wan_empty_embeds_node(
    prompt: dict[str, Any],
    object_info: dict[str, Any],
    req: dict[str, Any],
    *,
    node_id: str,
) -> str:
    class_name = _first_available_class(
        object_info,
        (
            "WanVideoEmptyEmbeds",
            "WanVideoEmptyTextEmbeds",
            "WanVideoEmptyMMAudioLatents",
            "WanVideoImageToVideoEncode",
        ),
        label="WAN empty/text-to-video image embeds",
    )
    allowed = _comfy_class_inputs(object_info, class_name)
    inputs: dict[str, Any] = {}
    width = int(req.get("width") or 832)
    height = int(req.get("height") or 480)
    frames = int(req.get("frames") or req.get("num_frames") or req.get("frame_count") or 81)

    _set_if_allowed(inputs, allowed, ("width",), width)
    _set_if_allowed(inputs, allowed, ("height",), height)
    _set_if_allowed(inputs, allowed, ("num_frames", "frames", "length", "video_length", "frame_count"), frames)
    _set_if_allowed(inputs, allowed, ("batch_size",), 1)
    _sv_set_default_required_inputs(inputs, object_info, class_name)
    _add_node(prompt, node_id, class_name, inputs)
    return node_id




def _sv_choice_or_default(
    object_info: dict[str, Any],
    class_name: str,
    input_name: str,
    requested: Any,
    default: str,
) -> str:
    choices = _sv_comfy_input_choices(object_info, class_name, input_name)
    by_lower = {str(item).strip().lower(): str(item).strip() for item in choices}

    requested_text = str(requested or "").strip()
    if requested_text:
        found = by_lower.get(requested_text.lower())
        if found:
            return found

    found_default = by_lower.get(str(default).strip().lower())
    if found_default:
        return found_default

    if choices:
        return str(choices[0]).strip()

    return default




def _sv_basename(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    return Path(text).name


def _sv_is_fp8_scaled_name(value: Any) -> bool:
    name = _sv_basename(value).lower()
    return bool(name and "fp8" in name and "scaled" in name)


def _sv_core_wan_choice(object_info: dict[str, Any], class_name: str, input_name: str, requested: Any, defaults: tuple[str, ...]) -> str:
    choices = _comfy_input_choices(object_info, class_name, input_name)
    if not choices:
        return str(requested or (defaults[0] if defaults else "")).strip()

    by_lower = {str(choice).strip().lower(): str(choice).strip() for choice in choices}
    requested_text = str(requested or "").strip()
    if requested_text:
        found = by_lower.get(requested_text.lower())
        if found:
            return found

    for default in defaults:
        found = by_lower.get(str(default).lower())
        if found:
            return found

    return str(choices[0]).strip()


def _sv_core_wan_clip_name(object_info: dict[str, Any], stack: dict[str, Any], req: dict[str, Any]) -> str:
    explicit = str(req.get("video_text_encoder") or req.get("text_encoder") or stack.get("text_encoder") or stack.get("text_encoder_path") or stack.get("clip") or stack.get("clip_path") or "").strip()
    requested = _sv_basename(explicit)
    choices = _comfy_input_choices(object_info, "CLIPLoader", "clip_name")
    if not choices:
        return requested

    by_lower = {choice.lower(): choice for choice in choices}
    if requested:
        found = by_lower.get(requested.lower())
        if found:
            return found

    for preferred in ("umt5_xxl_fp8_e4m3fn_scaled.safetensors", "t5xxl_fp8_e4m3fn_scaled.safetensors", "t5xxl_fp16.safetensors"):
        found = by_lower.get(preferred.lower())
        if found:
            return found

    for choice in choices:
        lowered = choice.lower()
        if "umt5" in lowered or "t5" in lowered:
            return choice

    return choices[0]


def _sv_core_wan_vae_name(object_info: dict[str, Any], stack: dict[str, Any]) -> str:
    explicit = str(stack.get("vae_path") or stack.get("vae") or "").strip()
    requested = _sv_basename(explicit)
    choices = _comfy_input_choices(object_info, "VAELoader", "vae_name")
    if not choices:
        return requested

    by_lower = {choice.lower(): choice for choice in choices}
    if requested:
        found = by_lower.get(requested.lower())
        if found:
            return found

    for preferred in ("wan2.2_vae.safetensors", "wan_2.1_vae.safetensors", "onTHEFLYWanAIWan21VideoModel_kijaiWan21VAE.safetensors"):
        found = by_lower.get(preferred.lower())
        if found:
            return found

    for choice in choices:
        lowered = choice.lower()
        if "wan" in lowered and "vae" in lowered:
            return choice

    return choices[0]


def _should_use_native_wan_core_route(req: dict[str, Any], object_info: dict[str, Any]) -> bool:
    route = str(req.get("native_video_route") or req.get("wan_text_route") or req.get("video_route") or "auto").strip().lower().replace("-", "_")
    if route in {"wrapper", "wan_wrapper", "wanvideowrapper", "wan_video_wrapper"}:
        return False
    if route in {"core", "wan_core", "core_wan", "comfy_core"}:
        return True

    stack = _video_model_stack_from_request(req)
    text_encoder = str(req.get("video_text_encoder") or req.get("text_encoder") or stack.get("text_encoder") or stack.get("text_encoder_path") or stack.get("clip") or stack.get("clip_path") or "").strip()
    if _sv_is_fp8_scaled_name(text_encoder):
        return True

    return True




def _sv_core_choice_or_default(
    object_info: dict[str, Any],
    class_name: str,
    input_name: str,
    requested: Any,
    default: str,
) -> str:
    choices = _comfy_input_choices(object_info, class_name, input_name)
    by_lower = {str(item).strip().lower(): str(item).strip() for item in choices}

    requested_text = str(requested or "").strip()
    if requested_text:
        found = by_lower.get(requested_text.lower())
        if found:
            return found

    found_default = by_lower.get(str(default).strip().lower())
    if found_default:
        return found_default

    if choices:
        return str(choices[0]).strip()

    return default


def _build_native_wan_core_video_prompt(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str) -> dict[str, Any]:
    if command != "t2v":
        raise RuntimeError("The native WAN core adapter currently supports T2V only. Use a compiled I2V workflow for I2V until the I2V adapter is wired.")

    stack = _video_model_stack_from_request(req)
    primary_path = _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path")) or str(req.get("model") or "")
    if not primary_path:
        raise RuntimeError("The selected WAN video stack has no primary diffusion model path.")

    frames = int(req.get("frames") or req.get("num_frames") or req.get("frame_count") or 81)
    fps = int(req.get("fps") or req.get("frame_rate") or 16)
    steps = int(req.get("steps") or 30)
    width = int(req.get("width") or 832)
    height = int(req.get("height") or 480)
    cfg = float(req.get("cfg") or req.get("guidance_scale") or 5.0)
    seed = int(req.get("seed") or req.get("noise_seed") or 1)
    if seed <= 0:
        seed = 1

    prompt: dict[str, Any] = {}

    clip_class = _first_available_class(object_info, ("CLIPLoader",), label="WAN core CLIP loading")
    allowed = _comfy_class_inputs(object_info, clip_class)
    inputs: dict[str, Any] = {}
    _set_if_allowed(inputs, allowed, ("clip_name",), _sv_core_wan_clip_name(object_info, stack, req))
    _set_if_allowed(inputs, allowed, ("type", "clip_type"), "wan")
    _set_if_allowed(inputs, allowed, ("device",), str(req.get("text_encoder_device") or stack.get("text_encoder_device") or "default"))
    _add_node(prompt, "1", clip_class, inputs)

    text_class = _first_available_class(object_info, ("CLIPTextEncode",), label="WAN core text encoding")
    allowed = _comfy_class_inputs(object_info, text_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("clip",), ["1", 0])
    _set_if_allowed(inputs, allowed, ("text", "prompt"), str(req.get("prompt") or ""))
    _add_node(prompt, "2", text_class, inputs)

    inputs = {}
    _set_if_allowed(inputs, allowed, ("clip",), ["1", 0])
    _set_if_allowed(inputs, allowed, ("text", "prompt"), str(req.get("negative_prompt") or ""))
    _add_node(prompt, "3", text_class, inputs)

    unet_class = _first_available_class(object_info, ("UNETLoader",), label="WAN core diffusion model loading")
    allowed = _comfy_class_inputs(object_info, unet_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("unet_name", "model_name", "ckpt_name", "checkpoint"), _sv_video_primary_name(object_info, primary_path, class_name=unet_class))
    _set_if_allowed(inputs, allowed, ("weight_dtype",), _sv_core_choice_or_default(object_info, unet_class, "weight_dtype", req.get("weight_dtype"), "default"))
    _add_node(prompt, "4", unet_class, inputs)

    vae_class = _first_available_class(object_info, ("VAELoader",), label="WAN core VAE loading")
    allowed = _comfy_class_inputs(object_info, vae_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("vae_name", "vae", "model_name"), _sv_core_wan_vae_name(object_info, stack))
    _add_node(prompt, "5", vae_class, inputs)

    sampling_class = _first_available_class(object_info, ("ModelSamplingSD3",), label="WAN core model sampling config")
    allowed = _comfy_class_inputs(object_info, sampling_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model",), ["4", 0])
    _set_if_allowed(inputs, allowed, ("shift",), float(req.get("shift") or req.get("model_sampling_shift") or 5.0))
    _add_node(prompt, "6", sampling_class, inputs)

    latent_class = _first_available_class(object_info, ("EmptyHunyuanLatentVideo", "EmptyWanLatentVideo", "WanEmptyLatentVideo", "EmptyLatentVideo"), label="WAN core latent video creation")
    allowed = _comfy_class_inputs(object_info, latent_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("width",), width)
    _set_if_allowed(inputs, allowed, ("height",), height)
    _set_if_allowed(inputs, allowed, ("length", "frames", "num_frames", "frame_count"), frames)
    _set_if_allowed(inputs, allowed, ("batch_size",), int(req.get("batch_size") or 1))
    _add_node(prompt, "7", latent_class, inputs)

    sampler_class = _first_available_class(object_info, ("KSamplerAdvanced",), label="WAN core sampling")
    allowed = _comfy_class_inputs(object_info, sampler_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model",), ["6", 0])
    _set_if_allowed(inputs, allowed, ("add_noise",), str(req.get("add_noise") or "enable"))
    _set_if_allowed(inputs, allowed, ("noise_seed", "seed"), seed)
    _set_if_allowed(inputs, allowed, ("steps",), steps)
    _set_if_allowed(inputs, allowed, ("cfg",), cfg)
    _set_if_allowed(inputs, allowed, ("sampler_name", "sampler"), _sv_core_wan_choice(object_info, sampler_class, "sampler_name", req.get("video_sampler") or req.get("sampler"), ("dpmpp_2m", "dpm++_2m", "euler", "uni_pc", "unipc")))
    _set_if_allowed(inputs, allowed, ("scheduler", "scheduler_name"), _sv_core_wan_choice(object_info, sampler_class, "scheduler", req.get("video_scheduler") or req.get("scheduler"), ("sgm_uniform", "normal", "simple", "karras")))
    _set_if_allowed(inputs, allowed, ("positive",), ["2", 0])
    _set_if_allowed(inputs, allowed, ("negative",), ["3", 0])
    _set_if_allowed(inputs, allowed, ("latent_image", "samples"), ["7", 0])
    _set_if_allowed(inputs, allowed, ("start_at_step",), int(req.get("start_at_step") or 0))
    _set_if_allowed(inputs, allowed, ("end_at_step",), int(req.get("end_at_step") or steps))
    _set_if_allowed(inputs, allowed, ("return_with_leftover_noise",), str(req.get("return_with_leftover_noise") or "disable"))
    _add_node(prompt, "8", sampler_class, inputs)

    decode_class = _first_available_class(object_info, ("VAEDecode",), label="WAN core VAE decode")
    allowed = _comfy_class_inputs(object_info, decode_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("samples",), ["8", 0])
    _set_if_allowed(inputs, allowed, ("vae",), ["5", 0])
    _add_node(prompt, "9", decode_class, inputs)

    create_video_class = _first_available_class(object_info, ("CreateVideo",), label="WAN core video assembly")
    allowed = _comfy_class_inputs(object_info, create_video_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("images",), ["9", 0])
    _set_if_allowed(inputs, allowed, ("fps",), fps)
    _add_node(prompt, "10", create_video_class, inputs)

    save_class = _first_available_class(object_info, ("SaveVideo", "SaveWEBM"), label="WAN core video saving")
    allowed = _comfy_class_inputs(object_info, save_class)
    output_value = str(req.get("output") or req.get("output_path") or f"spellvision_render_t2v_{job_id}")
    filename_prefix = str(Path(output_value).with_suffix(""))
    inputs = {}
    _set_if_allowed(inputs, allowed, ("video",), ["10", 0])
    _set_if_allowed(inputs, allowed, ("filename_prefix", "filename", "path"), filename_prefix)
    _set_if_allowed(inputs, allowed, ("format",), "mp4")
    _set_if_allowed(inputs, allowed, ("codec",), "h264")
    _add_node(prompt, "11", save_class, inputs)

    return _spellvision_apply_teacache_to_native_video_prompt(prompt, req, object_info)


def _build_native_wan_split_video_prompt(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
    job_id: str,
) -> dict[str, Any]:
    if command != "t2v":
        raise RuntimeError("The native WAN template adapter currently supports T2V only. Use a compiled I2V workflow for I2V until the I2V adapter is wired.")

    stack = _video_model_stack_from_request(req)
    primary_path = _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path"))
    if not primary_path:
        raise RuntimeError("The selected WAN video stack has no primary diffusion model path.")

    frames = int(req.get("frames") or req.get("num_frames") or req.get("frame_count") or 81)
    fps = int(req.get("fps") or req.get("frame_rate") or 16)
    steps = int(req.get("steps") or 30)
    cfg = float(req.get("cfg") or req.get("cfg_scale") or 6.0)
    shift = float(req.get("sampling_shift") or req.get("shift") or 5.0)
    seed = _int_or_default(req.get("seed"), 0)
    if seed <= 0:
        seed = int(time.time() * 1000) % 2147483647

    prompt: dict[str, Any] = {}

    model_class = _first_available_class(object_info, ("WanVideoModelLoader",), label="WAN video model loading")
    allowed = _comfy_class_inputs(object_info, model_class)
    inputs: dict[str, Any] = {}
    _set_if_allowed(inputs, allowed, ("model",), _sv_video_primary_name(object_info, primary_path, class_name=model_class))
    _set_if_allowed(inputs, allowed, ("base_precision",), str(req.get("base_precision") or "bf16"))
    _set_if_allowed(inputs, allowed, ("quantization",), str(req.get("model_quantization") or req.get("quantization") or "disabled"))
    _set_if_allowed(inputs, allowed, ("load_device",), str(req.get("model_load_device") or "offload_device"))
    _set_if_allowed(inputs, allowed, ("attention_mode",), str(req.get("attention_mode") or "sdpa"))
    _sv_set_default_required_inputs(inputs, object_info, model_class)
    _add_node(prompt, "1", model_class, inputs)

    t5_class = _first_available_class(object_info, ("LoadWanVideoT5TextEncoder",), label="WAN T5 text encoder loading")
    allowed = _comfy_class_inputs(object_info, t5_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model_name",), _sv_video_text_encoder_name(object_info, stack))
    _set_if_allowed(inputs, allowed, ("precision",), str(req.get("text_encoder_precision") or "bf16"))
    _set_if_allowed(inputs, allowed, ("load_device",), str(req.get("text_encoder_load_device") or "offload_device"))
    _set_if_allowed(inputs, allowed, ("quantization",), str(req.get("text_encoder_quantization") or "disabled"))
    _sv_set_default_required_inputs(inputs, object_info, t5_class)
    _add_node(prompt, "2", t5_class, inputs)

    text_class = _first_available_class(object_info, ("WanVideoTextEncode",), label="WAN text encoding")
    allowed = _comfy_class_inputs(object_info, text_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("positive_prompt",), str(req.get("prompt") or ""))
    _set_if_allowed(inputs, allowed, ("negative_prompt",), str(req.get("negative_prompt") or ""))
    _set_if_allowed(inputs, allowed, ("t5",), ["2", 0])
    _set_if_allowed(inputs, allowed, ("force_offload",), False)
    _set_if_allowed(inputs, allowed, ("device",), str(req.get("text_encoder_device") or "gpu"))
    _sv_set_default_required_inputs(inputs, object_info, text_class)
    _add_node(prompt, "3", text_class, inputs)

    image_embeds_node_id = _sv_add_wan_empty_embeds_node(prompt, object_info, req, node_id="4")

    sampler_class = _first_available_class(object_info, ("WanVideoSampler",), label="WAN video sampling")
    allowed = _comfy_class_inputs(object_info, sampler_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model",), ["1", 0])
    _set_if_allowed(inputs, allowed, ("image_embeds",), [image_embeds_node_id, 0])
    _set_if_allowed(inputs, allowed, ("text_embeds",), ["3", 0])
    _set_if_allowed(inputs, allowed, ("steps",), steps)
    _set_if_allowed(inputs, allowed, ("cfg",), cfg)
    _set_if_allowed(inputs, allowed, ("shift",), shift)
    _set_if_allowed(inputs, allowed, ("seed",), seed)
    _set_if_allowed(inputs, allowed, ("force_offload",), True)
    _set_if_allowed(inputs, allowed, ("scheduler",), _sv_choice_or_default(object_info, sampler_class, "scheduler", req.get("video_scheduler") or req.get("scheduler"), "unipc"))
    _set_if_allowed(inputs, allowed, ("riflex_freq_index",), int(req.get("riflex_freq_index") or 0))
    _set_if_allowed(inputs, allowed, ("denoise_strength",), float(req.get("denoise") or req.get("denoise_strength") or 1.0))
    _sv_set_default_required_inputs(inputs, object_info, sampler_class)
    _add_node(prompt, "5", sampler_class, inputs)

    vae_class = _first_available_class(object_info, ("WanVideoVAELoader",), label="WAN VAE loading")
    allowed = _comfy_class_inputs(object_info, vae_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model_name",), _sv_video_vae_name(object_info, stack))
    _set_if_allowed(inputs, allowed, ("precision",), str(req.get("vae_precision") or "bf16"))
    _set_if_allowed(inputs, allowed, ("use_cpu_cache",), bool(req.get("vae_use_cpu_cache", False)))
    _set_if_allowed(inputs, allowed, ("verbose",), bool(req.get("vae_verbose", False)))
    _sv_set_default_required_inputs(inputs, object_info, vae_class)
    _add_node(prompt, "6", vae_class, inputs)

    decode_class = _first_available_class(object_info, ("WanVideoDecode",), label="WAN video decode")
    allowed = _comfy_class_inputs(object_info, decode_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("vae",), ["6", 0])
    _set_if_allowed(inputs, allowed, ("samples",), ["5", 0])
    _set_if_allowed(inputs, allowed, ("enable_vae_tiling",), bool(req.get("enable_vae_tiling", False)))
    _set_if_allowed(inputs, allowed, ("tile_x",), int(req.get("tile_x") or 272))
    _set_if_allowed(inputs, allowed, ("tile_y",), int(req.get("tile_y") or 272))
    _set_if_allowed(inputs, allowed, ("tile_stride_x",), int(req.get("tile_stride_x") or 144))
    _set_if_allowed(inputs, allowed, ("tile_stride_y",), int(req.get("tile_stride_y") or 128))
    _sv_set_default_required_inputs(inputs, object_info, decode_class)
    _add_node(prompt, "7", decode_class, inputs)

    create_class = _first_available_class(object_info, ("CreateVideo",), label="video creation")
    allowed = _comfy_class_inputs(object_info, create_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("images",), ["7", 0])
    _set_if_allowed(inputs, allowed, ("fps",), float(fps))
    _sv_set_default_required_inputs(inputs, object_info, create_class)
    _add_node(prompt, "8", create_class, inputs)

    save_class = _first_available_class(object_info, ("SaveVideo",), label="video output saving")
    allowed = _comfy_class_inputs(object_info, save_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("video",), ["8", 0])
    _set_if_allowed(inputs, allowed, ("filename_prefix",), _filename_prefix_from_output(str(req.get("output") or ""), job_id))
    _set_if_allowed(inputs, allowed, ("format",), str(req.get("video_format") or "mp4"))
    _set_if_allowed(inputs, allowed, ("codec",), str(req.get("video_codec") or "h264"))
    _sv_set_default_required_inputs(inputs, object_info, save_class)
    _add_node(prompt, "9", save_class, inputs)

    return _spellvision_apply_teacache_to_native_video_prompt(prompt, req, object_info)




def _infer_native_video_family_key(req: dict[str, Any], family: str) -> str:
    explicit = str(
        family
        or req.get("model_family")
        or req.get("family")
        or req.get("video_family")
        or ""
    ).strip().lower().replace("-", "_")

    if explicit and explicit not in {"unknown", "video", "native_video", "split_stack"}:
        return explicit

    stack = _video_model_stack_from_request(req)
    haystack_parts: list[str] = [
        str(req.get("model") or ""),
        str(req.get("selected_model") or ""),
        str(req.get("model_path") or ""),
        str(req.get("primary_path") or ""),
    ]

    if isinstance(stack, dict):
        for key in (
            "family",
            "model_family",
            "primary",
            "primary_path",
            "model",
            "model_path",
            "transformer",
            "transformer_path",
            "unet",
            "unet_path",
            "text_encoder",
            "text_encoder_path",
            "vae",
            "vae_path",
        ):
            value = stack.get(key)
            if value:
                haystack_parts.append(str(value))

    haystack = " ".join(haystack_parts).lower().replace("\\", "/")

    if any(marker in haystack for marker in ("hunyuan", "hyvideo")):
        return "hunyuan_video"

    if any(marker in haystack for marker in ("wan", "wan2", "wan_2", "wan22")):
        return "wan"

    if any(marker in haystack for marker in ("ltx", "ltxv")):
        return "ltx"

    if "mochi" in haystack:
        return "mochi"

    return explicit or "unknown"


def _build_native_split_video_prompt(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
    job_id: str,
) -> dict[str, Any]:
    family_key = _infer_native_video_family_key(req, family)
    if family_key.startswith("wan"):
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

    stack = _video_model_stack_from_request(req)
    missing = _stack_missing_parts(stack)
    if missing:
        raise RuntimeError("The selected native video stack is incomplete: missing " + ", ".join(missing))

    primary_path = _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path"))
    vae_path = str(stack.get("vae_path") or "").strip()
    if not primary_path:
        raise RuntimeError("The selected native split video stack has no primary diffusion model path.")
    if not vae_path:
        raise RuntimeError("The selected native split video stack has no VAE path.")

    unet_class = _first_available_class(
        object_info,
        ("UNETLoader", "DiffusionModelLoader", "LoadDiffusionModel"),
        label="diffusion model loading",
    )
    vae_class = _first_available_class(object_info, ("VAELoader",), label="VAE loading")
    text_class = _first_available_class(object_info, ("CLIPTextEncode",), label="prompt text encoding")
    sampler_class = _first_available_class(object_info, ("KSampler", "KSamplerAdvanced"), label="sampling")
    decode_class = _first_available_class(object_info, ("VAEDecode",), label="VAE decode")
    latent_class = _first_available_class(
        object_info,
        (
            "EmptyHunyuanLatentVideo",
            "EmptyWanLatentVideo",
            "WanEmptyLatentVideo",
            "EmptyLTXVLatentVideo",
            "EmptyLatentVideo",
        ),
        label="video latent creation",
    )
    save_class = _first_available_class(
        object_info,
        ("SaveWEBM", "SaveAnimatedWEBP", "VHS_VideoCombine", "SaveVideo"),
        label="video output saving",
    )

    frames = int(req.get("frames") or req.get("num_frames") or req.get("frame_count") or 81)
    fps = int(req.get("fps") or req.get("frame_rate") or 16)
    width = int(req.get("width") or 832)
    height = int(req.get("height") or 480)
    steps = int(req.get("steps") or 30)
    cfg = float(req.get("cfg") or req.get("cfg_scale") or 7.0)
    seed = _int_or_default(req.get("seed"), 0)
    if seed <= 0:
        seed = int(time.time() * 1000) % 2147483647

    prompt: dict[str, Any] = {}

    allowed = _comfy_class_inputs(object_info, unet_class)
    inputs: dict[str, Any] = {}
    _set_if_allowed(inputs, allowed, ("unet_name", "model_name", "ckpt_name", "checkpoint"), _comfy_unet_name(primary_path))
    _set_if_allowed(inputs, allowed, ("weight_dtype", "dtype"), _input_default_choice(object_info, unet_class, "weight_dtype", "default"))
    _add_node(prompt, "1", unet_class, inputs)

    clip_node_id = _build_clip_loader_node(prompt, object_info, stack, family)

    allowed = _comfy_class_inputs(object_info, vae_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("vae_name", "vae"), _preferred_video_vae_name(object_info, family, vae_path))
    _add_node(prompt, "3", vae_class, inputs)

    model_link: list[Any] = ["1", 0]
    if "ModelSamplingSD3" in object_info:
        allowed = _comfy_class_inputs(object_info, "ModelSamplingSD3")
        inputs = {}
        _set_if_allowed(inputs, allowed, ("model",), model_link)
        _set_if_allowed(inputs, allowed, ("shift",), float(req.get("sampling_shift") or req.get("shift") or 8.0))
        _add_node(prompt, "4", "ModelSamplingSD3", inputs)
        model_link = ["4", 0]

    allowed = _comfy_class_inputs(object_info, text_class)
    pos_inputs = {}
    _set_if_allowed(pos_inputs, allowed, ("clip",), [clip_node_id, 0])
    _set_if_allowed(pos_inputs, allowed, ("text", "prompt"), str(req.get("prompt") or ""))
    _add_node(prompt, "5", text_class, pos_inputs)

    neg_inputs = {}
    _set_if_allowed(neg_inputs, allowed, ("clip",), [clip_node_id, 0])
    _set_if_allowed(neg_inputs, allowed, ("text", "prompt"), str(req.get("negative_prompt") or ""))
    _add_node(prompt, "6", text_class, neg_inputs)

    allowed = _comfy_class_inputs(object_info, latent_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("width",), width)
    _set_if_allowed(inputs, allowed, ("height",), height)
    _set_if_allowed(inputs, allowed, ("length", "frames", "num_frames", "video_length", "frame_count"), frames)
    _set_if_allowed(inputs, allowed, ("batch_size",), 1)
    _add_node(prompt, "7", latent_class, inputs)

    allowed = _comfy_class_inputs(object_info, sampler_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model",), model_link)
    _set_if_allowed(inputs, allowed, ("positive",), ["5", 0])
    _set_if_allowed(inputs, allowed, ("negative",), ["6", 0])
    _set_if_allowed(inputs, allowed, ("latent_image", "latent"), ["7", 0])
    _set_if_allowed(inputs, allowed, ("seed", "noise_seed"), seed)
    _set_if_allowed(inputs, allowed, ("steps",), steps)
    _set_if_allowed(inputs, allowed, ("cfg", "cfg_scale"), cfg)
    _set_if_allowed(inputs, allowed, ("sampler_name", "sampler"), str(req.get("sampler") or "dpmpp_2m"))
    _set_if_allowed(inputs, allowed, ("scheduler",), str(req.get("scheduler") or "karras"))
    _set_if_allowed(inputs, allowed, ("denoise",), float(req.get("denoise") or 1.0))
    _add_node(prompt, "8", sampler_class, inputs)

    allowed = _comfy_class_inputs(object_info, decode_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("samples", "latent", "latents"), ["8", 0])
    _set_if_allowed(inputs, allowed, ("vae",), ["3", 0])
    _add_node(prompt, "9", decode_class, inputs)

    allowed = _comfy_class_inputs(object_info, save_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("images", "image", "frames"), ["9", 0])
    _set_if_allowed(inputs, allowed, ("fps", "frame_rate"), fps)
    _set_if_allowed(inputs, allowed, ("filename_prefix", "filename", "output_path"), _filename_prefix_from_output(str(req.get("output") or ""), job_id))
    _set_if_allowed(inputs, allowed, ("codec",), _input_default_choice(object_info, save_class, "codec", "vp9"))
    _set_if_allowed(inputs, allowed, ("format",), _input_default_choice(object_info, save_class, "format", "webm"))
    _set_if_allowed(inputs, allowed, ("crf",), _input_default_choice(object_info, save_class, "crf", 23))
    _set_if_allowed(inputs, allowed, ("quality",), _input_default_choice(object_info, save_class, "quality", 80))
    _set_if_allowed(inputs, allowed, ("save_output",), _input_default_choice(object_info, save_class, "save_output", True))
    _add_node(prompt, "10", save_class, inputs)

    return prompt



def _prepare_native_video_adapter_request(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
) -> dict[str, Any]:
    """Apply the family adapter before native video prompt construction.

    This keeps generic image/sampler defaults from leaking into family-specific
    Comfy nodes, such as WAN's sampler scheduler vocabulary.
    """
    try:
        from video_adapters.registry import select_native_video_adapter
    except Exception as exc:
        adapted = dict(req)
        warnings = list(adapted.get("native_video_adapter_warnings") or [])
        warnings.append(f"Native video adapter registry unavailable: {exc}")
        adapted["native_video_adapter_warnings"] = warnings
        return adapted

    adapter = select_native_video_adapter(req, object_info, command=command, family=family)
    result = adapter.prepare_request(req, object_info, command=command, family=family)
    adapted = result.payload
    adapted["native_video_adapter_family"] = adapter.family
    if result.warnings:
        adapted["native_video_adapter_warnings"] = result.warnings
    return adapted

def run_native_split_stack_video(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    command = str(req.get("command") or req.get("task_type") or "").strip().lower()
    family = _infer_native_video_family(req)
    if command not in {"t2v", "i2v"}:
        raise RuntimeError(f"Native split-stack video only supports t2v/i2v, got {command!r}.")
    if command == "i2v":
        raise RuntimeError("Native split-stack I2V templates are not wired yet. Use a compiled I2V Comfy workflow for now.")

    transition_job(job, JobState.STARTING)
    emitter.status(job, "starting Comfy runtime for native split-stack video")
    emitter.emit_job_update(job)

    runtime_status = handle_ensure_comfy_runtime_command(req)
    if not runtime_status.get("healthy"):
        raise RuntimeError(runtime_status.get("message") or "Managed Comfy runtime is not ready")
    api_url = str(
        req.get("comfy_api_url")
        or runtime_status.get("endpoint")
        or os.environ.get("COMFY_API_URL")
        or "http://127.0.0.1:8188"
    ).rstrip("/")

    raise_if_cancelled(active_job, emitter, "Comfy runtime startup")
    emitter.status(job, "building native WAN/LTX split-stack Comfy template")
    object_info = _comfy_object_info(api_url)
    req = _prepare_native_video_adapter_request(req, object_info, command=command, family=family)

    family = str(req.get("resolved_native_video_family") or req.get("video_family") or req.get("model_family") or family)

    workflow = _build_native_split_video_prompt(req, object_info, command=command, family=family, job_id=job.job_id)
    debug_prompt_path = _native_prompt_debug_path(req, job.job_id)
    _write_native_prompt_debug_file(debug_prompt_path, workflow)
    req["native_prompt_api_path"] = debug_prompt_path

    validation_issues = _validate_comfy_prompt_against_object_info(workflow, object_info)
    if validation_issues:
        raise RuntimeError(
            "Generated native split-stack Comfy prompt failed local validation before submit. "
            f"Debug prompt: {debug_prompt_path}. Issues: "
            + "; ".join(validation_issues[:30])
        )

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "submitting native split-stack video template")
    start = time.perf_counter()
    prompt_id = _submit_comfy_prompt(api_url, workflow)
    emitter.status(job, f"ComfyUI native template submitted: {prompt_id}")

    history = _poll_comfy_history(api_url, prompt_id, req, emitter, job, active_job)
    asset = _extract_comfy_asset(history, ["videos", "gifs", "images", "audio"])
    if asset is None:
        raise RuntimeError("ComfyUI completed the native split-stack template but produced no output asset")

    output_path = str(req.get("output") or "").strip()
    if not output_path:
        filename = str(asset.get("filename") or f"native_split_{prompt_id}.webm")
        output_path = str(Path.cwd() / filename)
    else:
        requested_suffix = Path(output_path).suffix
        asset_suffix = Path(str(asset.get("filename") or "")).suffix
        if requested_suffix and asset_suffix and requested_suffix.lower() != asset_suffix.lower():
            output_path = str(Path(output_path).with_suffix(asset_suffix))
    output_path = _download_comfy_asset(api_url, asset, output_path)

    elapsed = time.perf_counter() - start
    steps_per_sec = float(req.get("steps") or 0) / elapsed if elapsed > 0 and req.get("steps") else 0.0
    asset_kind = str(asset.get("_asset_kind") or "").strip()
    resolved_media_type = "video" if asset_kind in {"videos", "gifs"} else ("audio" if asset_kind == "audio" else "image")
    req["resolved_media_type"] = resolved_media_type
    req["comfy_asset_kind"] = "native_split_stack_" + (asset_kind or "asset")

    metadata_output = str(req.get("metadata_output") or "").strip() or str(Path(output_path).with_suffix(".json"))
    metadata_payload = save_metadata(
        req=req,
        image_path=output_path,
        metadata_output=metadata_output,
        backend_name="SpellVisionNativeComfyTemplate",
        device="comfy",
        dtype="n/a",
        detected_pipeline=f"{family}_split_stack_template",
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
        "metadata_output": metadata_output,
        "backend_name": "SpellVisionNativeComfyTemplate",
        "detected_pipeline": f"{family}_split_stack_template",
        "task_type": command,
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cuda_allocated_gb": 0.0,
        "cuda_reserved_gb": 0.0,
        "media_type": resolved_media_type,
        "video_path": output_path if resolved_media_type == "video" else "",
        "asset_kind": "native_split_stack",
        "model_family": family,
        "video_model_stack": _video_model_stack_from_request(req) or None,
        "workflow_media_output": output_path,
        "prompt_id": prompt_id,
        "metadata": metadata_payload,
        "metadata_write_deferred": True,
        "comfy_runtime_endpoint": runtime_status.get("endpoint"),
        "comfy_runtime_pid": runtime_status.get("pid"),
        "native_template": True,
    }
    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


def _load_native_video_pipeline(req: dict[str, Any], command: str, family: str) -> tuple[Any, str, str, str]:
    stack = _video_model_stack_from_request(req)
    model_ref = _native_video_model_reference(req)
    model_path = Path(model_ref)
    suffix = model_path.suffix.lower()
    stack_kind = str(stack.get("stack_kind") or req.get("native_video_stack_kind") or "").strip().lower()

    if suffix in {".safetensors", ".ckpt", ".bin", ".gguf"}:
        stack_summary = _stack_summary(stack)
        raise RuntimeError(
            "SpellVision resolved this selection as a native video model stack, but split-stack execution is not wired into "
            "Diffusers yet. Native execution currently needs a Diffusers-format folder/repo with model_index.json. "
            f"Selected stack: {stack_summary}. "
            "Use a compiled Comfy workflow for split WAN/LTX/Hunyuan assets for now, or select a Diffusers-format video model folder."
        )

    if stack and stack_kind == "split_stack":
        missing = _stack_missing_parts(stack)
        if missing:
            raise RuntimeError(
                "The selected native video stack is incomplete: missing "
                + ", ".join(missing)
                + ". Add the missing assets or use an imported Comfy workflow that already binds them."
            )

    dtype, device = torch_dtype_and_device()
    if device == "cuda" and dtype == torch.float16:
        # Many modern video transformer pipelines prefer bfloat16 on Ada/Blackwell when available.
        try:
            if torch.cuda.is_bf16_supported():
                dtype = torch.bfloat16
        except Exception:
            pass

    errors: list[str] = []
    for class_name in _native_video_pipeline_candidates(command, family):
        pipe_cls = _import_diffusers_symbol(class_name)
        if pipe_cls is None:
            errors.append(f"{class_name}: not available in installed diffusers")
            continue

        try:
            pipe = pipe_cls.from_pretrained(model_ref, torch_dtype=dtype)
        except Exception as exc:
            errors.append(f"{class_name}: {exc}")
            continue

        try:
            pipe = optimize_pipeline(pipe.to(device), device)
        except Exception:
            try:
                pipe.to(device)
            except Exception:
                pass

        try:
            if hasattr(pipe, "enable_model_cpu_offload") and bool(req.get("enable_cpu_offload", True)):
                pipe.enable_model_cpu_offload()
        except Exception:
            pass

        return pipe, device, str(dtype), class_name

    raise RuntimeError(
        "No native video Diffusers pipeline could load this model. Tried: "
        + "; ".join(errors[:8])
    )


def _native_video_frames_from_result(result: Any) -> Any:
    frames = getattr(result, "frames", None)
    if frames is not None:
        if isinstance(frames, (list, tuple)) and frames and isinstance(frames[0], (list, tuple)):
            return frames[0]
        if isinstance(frames, (list, tuple)) and frames:
            return frames[0] if not hasattr(frames[0], "save") else frames
        return frames

    videos = getattr(result, "videos", None)
    if videos is not None:
        if isinstance(videos, (list, tuple)) and videos:
            return videos[0]
        return videos

    images = getattr(result, "images", None)
    if images is not None:
        if isinstance(images, (list, tuple)) and images and isinstance(images[0], (list, tuple)):
            return images[0]
        return images

    if isinstance(result, dict):
        for key in ("frames", "videos", "images"):
            if key in result:
                value = result[key]
                if isinstance(value, (list, tuple)) and value and isinstance(value[0], (list, tuple)):
                    return value[0]
                return value

    raise RuntimeError("Native video pipeline completed but did not return frames/videos/images.")


def _native_video_kwargs(req: dict[str, Any], command: str) -> dict[str, Any]:
    frames = int(req.get("frames") or req.get("num_frames") or req.get("frame_count") or 81)
    fps = int(req.get("fps") or req.get("frame_rate") or 16)
    steps = int(req.get("steps") or req.get("num_inference_steps") or 30)
    cfg = float(req.get("cfg") or req.get("cfg_scale") or req.get("guidance_scale") or 5.0)

    kwargs: dict[str, Any] = {
        "prompt": str(req.get("prompt") or ""),
        "num_frames": frames,
        "num_inference_steps": steps,
        "guidance_scale": cfg,
    }

    negative_prompt = str(req.get("negative_prompt") or "").strip()
    if negative_prompt:
        kwargs["negative_prompt"] = negative_prompt

    width = int(req.get("width") or 0)
    height = int(req.get("height") or 0)
    if width > 0:
        kwargs["width"] = width
    if height > 0:
        kwargs["height"] = height

    seed = int(req.get("seed") or 0)
    if seed > 0:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        kwargs["generator"] = torch.Generator(device=device).manual_seed(seed)

    if command == "i2v":
        input_image = str(req.get("input_image") or "").strip()
        if not input_image:
            raise RuntimeError("Native I2V requires input_image.")
        try:
            from diffusers.utils import load_image  # type: ignore
            kwargs["image"] = load_image(input_image)
        except Exception:
            kwargs["image"] = Image.open(input_image).convert("RGB")

    return kwargs


def run_native_video(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    command = str(req.get("command") or req.get("task_type") or "").strip().lower()
    if command not in {"t2v", "i2v"}:
        raise RuntimeError(f"Native video backend only supports t2v/i2v, got {command!r}.")

    transition_job(job, JobState.STARTING)
    emitter.status(job, "loading native video pipeline")
    emitter.emit_job_update(job)

    family = _infer_native_video_family(req)
    if _is_split_video_stack_request(req):
        return run_native_split_stack_video(req, emitter, job, active_job)

    pipe, device, dtype, pipeline_class = _load_native_video_pipeline(req, command, family)
    raise_if_cancelled(active_job, emitter, "native video pipeline loading")

    kwargs = _native_video_kwargs(req, command)
    transition_job(job, JobState.RUNNING)
    emitter.status(job, f"running native {pipeline_class}")
    raise_if_cancelled(active_job, emitter, "native video startup")

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start
    raise_if_cancelled(active_job, emitter, "native video completion")

    frames = _native_video_frames_from_result(result)
    output_path = str(req.get("output") or "").strip()
    if not output_path:
        output_path = str(Path.cwd() / f"{job.job_id}.mp4")
    if Path(output_path).suffix.lower() not in {".mp4", ".webm", ".gif"}:
        output_path = str(Path(output_path).with_suffix(".mp4"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        from diffusers.utils import export_to_video  # type: ignore
    except Exception as exc:
        raise RuntimeError("Native video generation requires diffusers.utils.export_to_video.") from exc

    export_to_video(frames, output_path, fps=int(req.get("fps") or req.get("frame_rate") or 16))

    metadata_output = str(req.get("metadata_output") or "").strip() or str(Path(output_path).with_suffix(".json"))
    req["resolved_media_type"] = "video"
    req["comfy_asset_kind"] = "native_video"

    steps_per_sec = float(req.get("steps") or 0) / elapsed if elapsed > 0 and req.get("steps") else 0.0
    metadata_payload = save_metadata(
        req=req,
        image_path=output_path,
        metadata_output=metadata_output,
        backend_name=pipeline_class,
        device=device,
        dtype=dtype,
        detected_pipeline=family,
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
        "metadata_output": metadata_output,
        "backend_name": pipeline_class,
        "detected_pipeline": family,
        "task_type": command,
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cuda_allocated_gb": round(torch.cuda.memory_allocated() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "cuda_reserved_gb": round(torch.cuda.memory_reserved() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "media_type": "video",
        "asset_kind": "native_video",
        "model_family": family,
        "video_model_stack": _video_model_stack_from_request(req) or None,
        "metadata": metadata_payload,
        "metadata_write_deferred": True,
    }

    payload.update(video_completion_diagnostics(
        req,
        backend_type="native_video",
        backend_name=str(payload.get("backend_name") or "Native Video"),
        output_path=str(payload.get("output") or req.get("output") or ""),
        metadata_output=str(payload.get("metadata_output") or req.get("metadata_output") or ""),
    ))
    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


def run_comfy_workflow(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    transition_job(job, JobState.STARTING)
    emitter.status(job, "loading workflow profile")
    emitter.emit_job_update(job)

    profile_path = str(req.get("profile_path") or req.get("workflow_profile_path") or "").strip()
    profile_payload = _load_json_file(profile_path) if profile_path else {}

    workflow_path = str(req.get("workflow_path") or profile_payload.get("workflow_source") or "").strip()
    if not workflow_path:
        raise RuntimeError("comfy_workflow requires workflow_path or profile_path")

    if workflow_path and not os.path.isabs(workflow_path) and profile_path:
        workflow_path = str((Path(profile_path).resolve().parent / workflow_path).resolve())

    workflow = _load_json_file(workflow_path)
    slot_bindings = profile_payload.get("slot_bindings") if isinstance(profile_payload, dict) else {}
    if not isinstance(slot_bindings, dict):
        slot_bindings = {}

    _apply_workflow_slot_bindings(workflow, slot_bindings, req)
    _apply_common_comfy_overrides(workflow, req)

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "submitting prompt to ComfyUI")
    raise_if_cancelled(active_job, emitter, "workflow preparation")

    runtime_status = handle_ensure_comfy_runtime_command(req)
    if not runtime_status.get("healthy"):
        raise RuntimeError(runtime_status.get("message") or "Managed Comfy runtime is not ready")

    api_url = str(
        req.get("comfy_api_url")
        or runtime_status.get("endpoint")
        or os.environ.get("COMFY_API_URL")
        or "http://127.0.0.1:8188"
    ).rstrip("/")
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
    req["media_type"] = output_media_type_for_metadata(req, output_path)
    metadata_payload = save_metadata(
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
        "media_type": output_media_type_for_metadata(req, output_path),
        "video_path": output_path if output_media_type_for_metadata(req, output_path) == "video" else "",
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
        "metadata_write_deferred": True,
        "comfy_runtime_endpoint": runtime_status.get("endpoint"),
        "comfy_runtime_pid": runtime_status.get("pid"),
    }

    payload.update(video_completion_diagnostics(
        req,
        backend_type="comfy_workflow",
        backend_name="ComfyUI",
        output_path=output_path,
        metadata_output=metadata_output,
        prompt_id=prompt_id,
    ))
    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload



def run_i2i(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    emitter.status(job, "loading pipeline")
    transition_job(job, JobState.STARTING)
    emitter.emit_job_update(job)

    _, pipe, device, dtype, detected, cache_hit, model_swap_cleanup = get_or_load_pipelines(req["model"])
    raise_if_cancelled(active_job, emitter, "pipeline loading")

    lora_used = False
    lora_stats = {
        "lora_cache_hit": False,
        "lora_reloaded": False,
        "lora_cleared": False,
        "active_lora_path": None,
        "active_lora_scale": None,
    }
    if req.get("lora"):
        emitter.status(job, "loading lora")
        lora_used, lora_stats = maybe_load_lora(pipe, req["lora"], float(req.get("lora_scale", 1.0)), "i2i")
        raise_if_cancelled(active_job, emitter, "lora loading")
    else:
        reset_lora_state(pipe, "i2i")

    scheduler_stats = apply_sampler_and_scheduler(pipe, req)

    if device == "cuda":
        generator = torch.Generator(device="cuda").manual_seed(int(req["seed"]))
    else:
        generator = torch.Generator().manual_seed(int(req["seed"]))

    input_image = Image.open(req["input_image"]).convert("RGB")
    raise_if_cancelled(active_job, emitter, "input image preparation")

    kwargs = build_generation_kwargs(
        req,
        generator,
        {
            "image": input_image,
            "strength": float(req.get("strength", 0.6)),
        },
    )
    attach_progress_callback(pipe, kwargs, req, emitter, job, active_job)

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "running pipeline")
    raise_if_cancelled(active_job, emitter, "pipeline startup")

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start

    raise_if_cancelled(active_job, emitter, "pipeline completion")

    image = result.images[0]
    os.makedirs(os.path.dirname(req["output"]), exist_ok=True)
    if len(req["output"]) > 240:
        raise RuntimeError(f"Output path too long after queue/retry naming: {req['output']}")
    image.save(req["output"], "PNG")

    steps_per_sec = int(req["steps"]) / elapsed if elapsed > 0 else 0.0

    raise_if_cancelled(active_job, emitter, "metadata handoff")

    lora_cache_hit = bool(lora_stats.get("lora_cache_hit", False))
    lora_reloaded = bool(lora_stats.get("lora_reloaded", False))

    metadata_payload = save_metadata(
        req=req,
        image_path=req["output"],
        metadata_output=req["metadata_output"],
        backend_name=pipe.__class__.__name__,
        device=device,
        dtype=dtype,
        detected_pipeline=detected,
        lora_used=lora_used,
        elapsed=elapsed,
        steps_per_sec=steps_per_sec,
        job=job,
        cache_hit=cache_hit,
        model_swap_cleanup=model_swap_cleanup,
        lora_cache_hit=lora_cache_hit,
        lora_reloaded=lora_reloaded,
        queue_warm_reuse_expected=bool(req.get("queue_warm_reuse_expected")),
        queue_warm_reuse_source=req.get("queue_warm_reuse_source"),
        queue_affinity_signature=req.get("queue_affinity_signature"),
    )

    payload = {
        "ok": True,
        "cache_hit": cache_hit,
        "output": req["output"],
        "metadata_output": req["metadata_output"],
        "backend_name": pipe.__class__.__name__,
        "detected_pipeline": detected,
        "task_type": req.get("task_type", req.get("command", "unknown")),
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cuda_allocated_gb": round(torch.cuda.memory_allocated() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "cuda_reserved_gb": round(torch.cuda.memory_reserved() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "model_swap_cleanup": model_swap_cleanup,
        "model_cleanup_time_sec": model_swap_cleanup.get("cleanup_time_sec") if model_swap_cleanup else 0.0,
        "model_load_time_sec": model_swap_cleanup.get("model_load_time_sec") if model_swap_cleanup else None,
        "memory_after_load": model_swap_cleanup.get("memory_after_load") if model_swap_cleanup else None,
        "lora_cache_hit": lora_cache_hit,
        "lora_reloaded": lora_reloaded,
        "queue_warm_reuse_expected": bool(req.get("queue_warm_reuse_expected")),
        "queue_warm_reuse_source": req.get("queue_warm_reuse_source"),
        "queue_affinity_signature": req.get("queue_affinity_signature"),
        "sampler": req.get("sampler"),
        "scheduler": req.get("scheduler"),
        "scheduler_applied": bool(scheduler_stats.get("applied")),
        "scheduler_class": scheduler_stats.get("scheduler_class"),
    }

    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


class QueueEmitter:
    def __init__(self, queue_manager: QueueManager, queue_item_id: str):
        self.queue_manager = queue_manager
        self.queue_item_id = queue_item_id

    def emit(self, payload: dict[str, Any]) -> None:
        return

    def emit_job_update(self, job: JobRecord) -> None:
        self.queue_manager.update_from_job(self.queue_item_id, job)

    def status(self, job: JobRecord, message: str) -> None:
        set_job_message(job, message)
        self.emit_job_update(job)

    def progress(self, job: JobRecord, step: int, total: int, message: str | None = None) -> None:
        update_job_progress(job, step, total, message)
        self.emit_job_update(job)

    def result(self, job: JobRecord) -> None:
        self.emit_job_update(job)

    def error(self, job: JobRecord, error_text: str, tb: str | None = None, code: str = "generation_error") -> None:
        fail_job(job, error_text, code=code, tb=tb)
        self.emit_job_update(job)


def imported_workflows_root() -> str:
    return str(Path(__file__).resolve().parent.parent / "runtime" / "imported_workflows")


def default_comfy_root() -> str:
    override = os.environ.get("SPELLVISION_COMFY", "").strip()
    if override:
        return str(Path(override).expanduser().resolve())
    return str(Path(__file__).resolve().parent.parent / "runtime" / "comfy" / "ComfyUI")


def starter_node_catalog_path() -> str:
    return str(Path(__file__).resolve().parent / "starter_node_catalog.json")




def _managed_comfy_host(req: dict[str, Any] | None = None) -> str:
    req = req or {}
    return str(req.get("comfy_host") or os.environ.get("SPELLVISION_COMFY_HOST") or "127.0.0.1").strip() or "127.0.0.1"


def _managed_comfy_port(req: dict[str, Any] | None = None) -> int:
    req = req or {}
    raw = req.get("comfy_port") or os.environ.get("SPELLVISION_COMFY_PORT") or 8188
    try:
        return int(raw)
    except Exception:
        return 8188


def _managed_comfy_python(req: dict[str, Any] | None = None) -> str:
    req = req or {}
    comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
    return str(
        req.get("comfy_python_executable")
        or req.get("python_executable")
        or os.environ.get("SPELLVISION_COMFY_PYTHON")
        or default_comfy_python(comfy_root)
    ).strip()


def get_comfy_runtime_manager(req: dict[str, Any] | None = None) -> ComfyRuntimeManager:
    global COMFY_RUNTIME_MANAGER
    req = req or {}
    comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
    host = _managed_comfy_host(req)
    port = _managed_comfy_port(req)
    python_executable = _managed_comfy_python(req)
    with COMFY_RUNTIME_MANAGER_LOCK:
        if (
            COMFY_RUNTIME_MANAGER is None
            or COMFY_RUNTIME_MANAGER.comfy_root != comfy_root
            or COMFY_RUNTIME_MANAGER.host != host
            or COMFY_RUNTIME_MANAGER.port != port
            or COMFY_RUNTIME_MANAGER.python_executable != python_executable
        ):
            COMFY_RUNTIME_MANAGER = ComfyRuntimeManager(
                comfy_root,
                python_executable=python_executable,
                host=host,
                port=port,
            )
        return COMFY_RUNTIME_MANAGER


def _runtime_message(message_type: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["type"] = message_type
    normalized["action"] = action
    normalized.setdefault("endpoint", normalized.get("endpoint") or f"http://{normalized.get('host', '127.0.0.1')}:{normalized.get('port', 8188)}")
    return normalized


def handle_comfy_runtime_status_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    manager = get_comfy_runtime_manager(req)
    payload = manager.status()
    return _runtime_message("comfy_runtime_status", "comfy_runtime_status", payload)


def handle_ensure_comfy_runtime_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    manager = get_comfy_runtime_manager(req)
    payload = manager.ensure_running(timeout_sec=float(req.get("startup_timeout_sec") or 60.0))
    return _runtime_message("comfy_runtime_ack", "ensure_comfy_runtime", payload)


def handle_start_comfy_runtime_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    manager = get_comfy_runtime_manager(req)
    payload = manager.start(timeout_sec=float(req.get("startup_timeout_sec") or 60.0))
    return _runtime_message("comfy_runtime_ack", "start_comfy_runtime", payload)


def handle_stop_comfy_runtime_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    manager = get_comfy_runtime_manager(req)
    payload = manager.stop(graceful_timeout_sec=float(req.get("graceful_timeout_sec") or 8.0))
    return _runtime_message("comfy_runtime_ack", "stop_comfy_runtime", payload)


def handle_restart_comfy_runtime_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    manager = get_comfy_runtime_manager(req)
    payload = manager.restart(timeout_sec=float(req.get("startup_timeout_sec") or 60.0))
    return _runtime_message("comfy_runtime_ack", "restart_comfy_runtime", payload)


def handle_import_workflow_command(req: dict[str, Any]) -> dict[str, Any]:
    try:
        from workflow_importer import import_workflow
    except Exception as exc:
        return {
            "type": "workflow_import_result",
            "ok": False,
            "action": "import_workflow",
            "error": f"workflow_importer import failed: {exc}",
        }

    source = str(req.get("source") or req.get("workflow_path") or "").strip()
    if not source:
        return {
            "type": "workflow_import_result",
            "ok": False,
            "action": "import_workflow",
            "error": "import_workflow requires source",
        }

    destination_root = str(req.get("destination_root") or imported_workflows_root()).strip()
    profile_name = str(req.get("profile_name") or "").strip() or None
    auto_apply_node_deps = bool(req.get("auto_apply_node_deps", False))
    auto_apply_model_deps = bool(req.get("auto_apply_model_deps", False))
    comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
    python_executable = str(req.get("python_executable") or sys.executable).strip()
    model_cache_root = str(req.get("model_cache_root") or (Path(__file__).resolve().parent.parent / "python" / ".cache" / "assets")).strip()
    civitai_api_key = str(req.get("civitai_api_key") or os.environ.get("CIVITAI_API_KEY") or "").strip() or None
    node_catalog = str(req.get("node_catalog") or starter_node_catalog_path()).strip()

    try:
        result = import_workflow(
            source=source,
            destination_root=destination_root,
            profile_name=profile_name,
            comfy_root=comfy_root,
            python_executable=python_executable,
            node_catalog=node_catalog,
            auto_apply_node_deps=auto_apply_node_deps,
            auto_apply_model_deps=auto_apply_model_deps,
            civitai_api_key=civitai_api_key,
            model_cache_root=model_cache_root,
        )

        payload: dict[str, Any]
        if hasattr(result, "to_dict"):
            payload = result.to_dict()
        elif isinstance(result, dict):
            payload = dict(result)
        else:
            payload = {
                "ok": False,
                "error": f"Unexpected import_workflow result type: {type(result).__name__}",
            }

        payload["type"] = "workflow_import_result"
        payload["action"] = "import_workflow"
        return payload
    except Exception as exc:
        return {
            "type": "workflow_import_result",
            "ok": False,
            "action": "import_workflow",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def handle_list_workflow_profiles_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(imported_workflows_root())
    root.mkdir(parents=True, exist_ok=True)
    profiles: list[dict[str, Any]] = []
    for profile_path in sorted(root.glob("*/profile.json")):
        try:
            payload = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        profile_payload = dict(payload) if isinstance(payload, dict) else {}
        profile_payload.update(
            {
                "name": profile_payload.get("profile_name") or profile_path.parent.name,
                "workflow_path": profile_payload.get("workflow_source"),
                "profile_path": str(profile_path),
                "import_root": str(profile_path.parent),
                "import_slug": profile_path.parent.name,
            }
        )
        profiles.append(profile_payload)
    return {
        "type": "workflow_profiles",
        "ok": True,
        "action": "list_workflow_profiles",
        "profiles": profiles,
        "count": len(profiles),
        "profiles_root": str(root),
    }

def handle_prepare_model_swap_command(req: dict[str, Any]) -> dict[str, Any]:
    requested_key = str(req.get("requested_key") or "").strip()

    if not requested_key:
        return {
            "type": "model_cache",
            "ok": False,
            "action": "prepare_model_swap",
            "error": "requested_key is required",
        }

    stats = cleanup_for_model_swap(requested_key)

    return {
        "type": "model_cache",
        "ok": True,
        "action": "prepare_model_swap",
        "requested_key": requested_key,
        "cleanup_performed": stats is not None,
        "cleanup_stats": stats,
        "memory": cuda_memory_snapshot(),
    }



# --- SPELLVISION SPRINT 13 PASS 2 TEACACHE WORKER HELPERS ---
def _spellvision_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return default


def _spellvision_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _spellvision_clamped_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, _spellvision_float(value, default)))


def _spellvision_teacache_enabled(req: dict[str, Any]) -> bool:
    if _spellvision_bool(req.get("teacache_enabled"), False):
        return True
    accel = req.get("video_acceleration")
    if isinstance(accel, dict):
        return _spellvision_bool(accel.get("enabled"), False)
    return False


def _spellvision_teacache_settings(req: dict[str, Any]) -> dict[str, Any]:
    raw_accel = req.get("video_acceleration")
    accel: dict[str, Any] = raw_accel if isinstance(raw_accel, dict) else {}

    profile = str(req.get("teacache_profile") or accel.get("profile") or "off").strip().lower() or "off"
    model_type = str(req.get("teacache_model_type") or accel.get("model_type") or "wan2.1_t2v_14b").strip() or "wan2.1_t2v_14b"
    cache_device = str(req.get("teacache_cache_device") or accel.get("cache_device") or "cpu").strip().lower() or "cpu"
    if cache_device not in {"cpu", "cuda"}:
        cache_device = "cpu"

    rel_l1 = _spellvision_clamped_float(
        req.get("teacache_rel_l1_thresh", accel.get("rel_l1_thresh", 0.20)),
        0.20,
        0.0,
        2.0,
    )
    start = _spellvision_clamped_float(
        req.get("teacache_start_percent", accel.get("start_percent", 0.0)),
        0.0,
        0.0,
        1.0,
    )
    end = _spellvision_clamped_float(
        req.get("teacache_end_percent", accel.get("end_percent", 1.0)),
        1.0,
        0.0,
        1.0,
    )
    if end < start:
        start, end = end, start
    return {
        "enabled": _spellvision_teacache_enabled(req),
        "profile": profile,
        "model_type": model_type,
        "rel_l1_thresh": rel_l1,
        "start_percent": start,
        "end_percent": end,
        "cache_device": cache_device,
    }


def _spellvision_teacache_class(object_info: dict[str, Any]) -> str | None:
    for class_name in ("TeaCache", "TeaCacheForVidGen", "TeaCacheForImgGen"):
        if class_name in object_info:
            return class_name
    for class_name in object_info:
        if "teacache" in str(class_name).lower().replace("_", ""):
            return str(class_name)
    return None


def _spellvision_choice_casefold(choices: list[str], requested: str) -> str | None:
    normalized_requested = requested.strip().lower().replace("-", "_").replace(" ", "_")
    for choice in choices:
        normalized_choice = str(choice).strip().lower().replace("-", "_").replace(" ", "_")
        if normalized_choice == normalized_requested:
            return str(choice).strip()
    return None


def _spellvision_teacache_model_type(object_info: dict[str, Any], class_name: str, requested: str) -> str:
    choices = _comfy_input_choices(object_info, class_name, "model_type")
    if not choices:
        return requested
    found = _spellvision_choice_casefold(choices, requested)
    if found:
        return found
    wanted = requested.lower().replace("-", "_").replace(" ", "_")
    for choice in choices:
        candidate = str(choice).lower().replace("-", "_").replace(" ", "_")
        if "wan" in wanted and "wan" in candidate and "14" in candidate and "t2v" in candidate:
            return str(choice).strip()
    for choice in choices:
        candidate = str(choice).lower()
        if "wan" in candidate:
            return str(choice).strip()
    return str(choices[0]).strip()


def _spellvision_teacache_metadata(req: dict[str, Any]) -> dict[str, Any]:
    settings = _spellvision_teacache_settings(req)
    return {
        "teacache_enabled": bool(settings.get("enabled")),
        "teacache_applied": bool(req.get("teacache_applied", False)),
        "teacache_available": bool(req.get("teacache_available", False)),
        "teacache_node_count": int(req.get("teacache_node_count") or 0),
        "teacache_profile": settings.get("profile"),
        "teacache_model_type": settings.get("model_type"),
        "teacache_rel_l1_thresh": settings.get("rel_l1_thresh"),
        "teacache_start_percent": settings.get("start_percent"),
        "teacache_end_percent": settings.get("end_percent"),
        "teacache_cache_device": settings.get("cache_device"),
        "teacache_warning": req.get("teacache_warning"),
        "video_acceleration": {
            "backend": "ComfyUI-TeaCache",
            **settings,
            "available": bool(req.get("teacache_available", False)),
            "applied": bool(req.get("teacache_applied", False)),
            "node_count": int(req.get("teacache_node_count") or 0),
            "warning": req.get("teacache_warning"),
        },
    }


def _spellvision_apply_teacache_to_native_video_prompt(
    prompt: dict[str, Any],
    req: dict[str, Any],
    object_info: dict[str, Any],
) -> dict[str, Any]:
    settings = _spellvision_teacache_settings(req)
    if not settings["enabled"] or settings["profile"] == "off":
        req["teacache_applied"] = False
        req["teacache_available"] = bool(_spellvision_teacache_class(object_info))
        req["teacache_node_count"] = 0
        return prompt

    tea_class = _spellvision_teacache_class(object_info)
    req["teacache_available"] = bool(tea_class)
    if not tea_class:
        req["teacache_applied"] = False
        req["teacache_node_count"] = 0
        req["teacache_warning"] = "ComfyUI-TeaCache node is not installed; generated without TeaCache."
        return prompt

    if any(str(node.get("class_type") or "").lower().replace("_", "") == str(tea_class).lower().replace("_", "") for node in prompt.values() if isinstance(node, dict)):
        req["teacache_applied"] = True
        req["teacache_node_count"] = sum(1 for node in prompt.values() if isinstance(node, dict) and str(node.get("class_type") or "").lower().replace("_", "") == str(tea_class).lower().replace("_", ""))
        return prompt

    model_node_ids: list[str] = []
    for node_id, node in list(prompt.items()):
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        if class_type in {"UNETLoader", "DiffusionModelLoader", "LoadDiffusionModel"}:
            model_node_ids.append(str(node_id))

    if not model_node_ids:
        req["teacache_applied"] = False
        req["teacache_node_count"] = 0
        req["teacache_warning"] = "TeaCache enabled, but no native diffusion model loader was found in the generated prompt."
        return prompt

    allowed = _comfy_class_inputs(object_info, tea_class)
    inserted: dict[str, str] = {}
    for model_node_id in model_node_ids:
        tea_node_id = f"tc_{model_node_id}"
        while tea_node_id in prompt:
            tea_node_id = f"tc_{tea_node_id}"
        inputs: dict[str, Any] = {}
        _set_if_allowed(inputs, allowed, ("model",), [model_node_id, 0])
        _set_if_allowed(inputs, allowed, ("model_type",), _spellvision_teacache_model_type(object_info, tea_class, str(settings["model_type"])))
        _set_if_allowed(inputs, allowed, ("rel_l1_thresh",), float(settings["rel_l1_thresh"]))
        _set_if_allowed(inputs, allowed, ("start_percent",), float(settings["start_percent"]))
        _set_if_allowed(inputs, allowed, ("end_percent",), float(settings["end_percent"]))
        _set_if_allowed(inputs, allowed, ("cache_device",), str(settings["cache_device"]))
        _sv_set_default_required_inputs(inputs, object_info, tea_class)
        _add_node(prompt, tea_node_id, tea_class, inputs)
        inserted[model_node_id] = tea_node_id

    # Route downstream model consumers through TeaCache. Leave the TeaCache node's own input untouched.
    for node_id, node in prompt.items():
        if str(node_id).startswith("tc_") or not isinstance(node, dict):
            continue

        node_inputs_any = node.get("inputs")
        if not isinstance(node_inputs_any, dict):
            continue

        node_inputs: dict[str, Any] = node_inputs_any
        for input_name, value in list(node_inputs.items()):
            if not (isinstance(value, list) and len(value) >= 2):
                continue

            source_id = str(value[0])
            tea_node_id = inserted.get(source_id)
            if not tea_node_id:
                continue

            if input_name not in {"model", "diffusion_model"}:
                continue

            node_inputs[input_name] = [tea_node_id, value[1]]

    req["teacache_applied"] = bool(inserted)
    req["teacache_node_count"] = len(inserted)
    req["teacache_warning"] = None
    req["video_acceleration_backend"] = "ComfyUI-TeaCache"
    return prompt
# --- END SPELLVISION SPRINT 13 PASS 2 TEACACHE WORKER HELPERS ---


# --- SPELLVISION MANAGER FOUNDATION V1 ---
def _load_starter_node_catalog_payload() -> dict[str, Any]:
    path = Path(starter_node_catalog_path())
    if not path.exists():
        return {"packages": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"packages": []}
    except Exception:
        return {"packages": []}


def _package_looks_installed(entry: dict[str, Any], installed_names: set[str], custom_nodes_root: str) -> tuple[bool, str]:
    package_name = str(entry.get("package_name") or "").strip()
    repo_url = str(entry.get("repo_url") or "").strip()
    aliases = [str(item).strip() for item in entry.get("aliases") or [] if str(item).strip()]
    candidates = [package_name, *aliases]
    if repo_url:
        candidates.append(Path(repo_url.rstrip("/").replace(".git", "")).name)

    normalized_installed = {name.lower() for name in installed_names}
    for candidate in candidates:
        if candidate.lower() in normalized_installed:
            return True, f"matched installed node '{candidate}'"

    root = Path(custom_nodes_root)
    for candidate in candidates:
        if candidate and (root / candidate).exists():
            return True, f"folder exists: {candidate}"

    return False, "not detected"


def _recommended_node_entries(installed_names: set[str], custom_nodes_root: str) -> list[dict[str, Any]]:
    catalog = _load_starter_node_catalog_payload()
    entries: list[dict[str, Any]] = []
    video_families = {"wan", "ltx", "hunyuan_video", "cogvideox", "mochi"}
    for raw_entry in catalog.get("packages") or []:
        if not isinstance(raw_entry, dict):
            continue
        package_name = str(raw_entry.get("package_name") or "").strip()
        if not package_name:
            continue
        model_families = [str(item) for item in raw_entry.get("model_families") or []]
        is_video_related = bool(set(model_families).intersection(video_families)) or "teacache" in package_name.lower()
        if not is_video_related:
            continue
        installed, note = _package_looks_installed(raw_entry, installed_names, custom_nodes_root)
        entry = dict(raw_entry)
        entry["installed"] = installed
        entry["notes"] = note
        entries.append(entry)
    entries.sort(key=lambda item: (bool(item.get("installed")), str(item.get("package_name") or "").lower()))
    return entries


def _manager_python_executable(req: dict[str, Any] | None = None) -> str:
    req = req or {}
    return str(req.get("python_executable") or _managed_comfy_python(req) or sys.executable).strip() or sys.executable


def handle_comfy_manager_status_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    try:
        from comfy_manager_bridge import detect_manager_paths, list_installed_nodes
    except Exception as exc:
        return {
            "type": "comfy_manager_status",
            "ok": False,
            "action": "comfy_manager_status",
            "error": f"comfy_manager_bridge import failed: {exc}",
        }

    comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
    python_executable = _manager_python_executable(req)
    paths = detect_manager_paths(comfy_root)
    installed_snapshot = list_installed_nodes(comfy_root, python_executable=python_executable)
    installed_names = {str(name).lower() for name in installed_snapshot.get("names") or []}
    recommended = _recommended_node_entries(installed_names, paths.custom_nodes_root)

    try:
        runtime_status = handle_comfy_runtime_status_command(req)
    except Exception as exc:
        runtime_status = {"ok": False, "error": str(exc)}

    return {
        "type": "comfy_manager_status",
        "ok": True,
        "action": "comfy_manager_status",
        "comfy_root": comfy_root,
        "python_executable": python_executable,
        "manager_paths": paths.to_dict(),
        "manager_present": bool(paths.exists),
        "installed_nodes": sorted(installed_names),
        "installed_snapshot": installed_snapshot,
        "recommended_nodes": recommended,
        "recommended_missing_count": sum(1 for item in recommended if not item.get("installed")),
        "starter_node_catalog": starter_node_catalog_path(),
        "runtime_status": runtime_status,
    }


def handle_install_comfy_manager_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    try:
        from comfy_manager_bridge import ensure_manager_installed
    except Exception as exc:
        return {
            "type": "comfy_manager_ack",
            "ok": False,
            "action": "install_comfy_manager",
            "error": f"comfy_manager_bridge import failed: {exc}",
        }

    comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
    python_executable = _manager_python_executable(req)
    try:
        paths, logs = ensure_manager_installed(
            comfy_root,
            python_executable=python_executable,
            install_requirements=True,
            timeout_sec=int(req.get("timeout_sec") or 1800),
        )
        return {
            "type": "comfy_manager_ack",
            "ok": all(log.ok for log in logs) if logs else bool(paths.exists),
            "action": "install_comfy_manager",
            "manager_paths": paths.to_dict(),
            "logs": [log.to_dict() for log in logs],
            "message": "ComfyUI Manager is installed or repaired." if paths.exists else "ComfyUI Manager install did not complete.",
        }
    except Exception as exc:
        return {
            "type": "comfy_manager_ack",
            "ok": False,
            "action": "install_comfy_manager",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def _find_catalog_node_entry(package_name: str) -> dict[str, Any] | None:
    target = package_name.strip().lower()
    if not target:
        return None
    catalog = _load_starter_node_catalog_payload()
    for entry in catalog.get("packages") or []:
        if not isinstance(entry, dict):
            continue
        names = [str(entry.get("package_name") or "").strip().lower()]
        names.extend(str(alias).strip().lower() for alias in entry.get("aliases") or [])
        if target in names:
            return dict(entry)
    return None


def handle_install_custom_node_command(req: dict[str, Any]) -> dict[str, Any]:
    try:
        from comfy_manager_bridge import clone_custom_node_repo, install_registered_nodes
    except Exception as exc:
        return {
            "type": "comfy_manager_ack",
            "ok": False,
            "action": "install_custom_node",
            "error": f"comfy_manager_bridge import failed: {exc}",
        }

    package_name = str(req.get("package_name") or "").strip()
    if not package_name:
        return {"type": "comfy_manager_ack", "ok": False, "action": "install_custom_node", "error": "package_name is required"}

    catalog_entry = _find_catalog_node_entry(package_name) or {}
    repo_url = str(req.get("repo_url") or catalog_entry.get("repo_url") or "").strip()
    install_method = str(req.get("install_method") or catalog_entry.get("install_method") or "git").strip().lower()
    comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
    python_executable = _manager_python_executable(req)

    try:
        outcomes: list[dict[str, Any]] = []
        if install_method == "manager":
            results = install_registered_nodes(comfy_root, [package_name], python_executable=python_executable, timeout_sec=int(req.get("timeout_sec") or 1800))
            outcomes = [result.to_dict() for result in results]
            ok = all(result.ok for result in results)
        else:
            if not repo_url:
                return {"type": "comfy_manager_ack", "ok": False, "action": "install_custom_node", "error": f"No repo_url is known for {package_name}"}
            result = clone_custom_node_repo(
                comfy_root,
                repo_url,
                package_name=package_name,
                python_executable=python_executable,
                timeout_sec=int(req.get("timeout_sec") or 1800),
                install_requirements=True,
            )
            outcomes = [result.to_dict()]
            ok = result.ok
        return {
            "type": "comfy_manager_ack",
            "ok": ok,
            "action": "install_custom_node",
            "package_name": package_name,
            "install_method": install_method,
            "repo_url": repo_url,
            "outcomes": outcomes,
        }
    except Exception as exc:
        return {
            "type": "comfy_manager_ack",
            "ok": False,
            "action": "install_custom_node",
            "package_name": package_name,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def handle_install_recommended_video_nodes_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    status = handle_comfy_manager_status_command(req)
    if not status.get("ok"):
        return {"type": "comfy_manager_ack", "ok": False, "action": "install_recommended_video_nodes", "error": status.get("error") or "manager status failed"}

    selected_names = [str(item).strip() for item in req.get("package_names") or [] if str(item).strip()]
    recommended = status.get("recommended_nodes") or []
    if selected_names:
        install_entries = [item for item in recommended if str(item.get("package_name") or "") in selected_names]
    else:
        install_entries = [item for item in recommended if not item.get("installed")]

    outcomes: list[dict[str, Any]] = []
    errors: list[str] = []
    for entry in install_entries:
        package_name = str(entry.get("package_name") or "").strip()
        if not package_name:
            continue
        payload = dict(req)
        payload.update({
            "package_name": package_name,
            "install_method": entry.get("install_method"),
            "repo_url": entry.get("repo_url"),
        })
        result = handle_install_custom_node_command(payload)
        outcomes.append(result)
        if not result.get("ok"):
            errors.append(str(result.get("error") or f"Failed to install {package_name}"))

    return {
        "type": "comfy_manager_ack",
        "ok": not errors,
        "action": "install_recommended_video_nodes",
        "requested_count": len(install_entries),
        "outcomes": outcomes,
        "errors": errors,
    }
# --- END SPELLVISION MANAGER FOUNDATION V1 ---

class WorkerTCPHandler(socketserver.StreamRequestHandler):
    def handle_cancel_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        job_id = str(req.get("job_id", "")).strip()
        if not job_id:
            emitter.emit({"ok": False, "error": "cancel requires job_id", "cancel_requested": False})
            return

        accepted, job = request_job_cancel(job_id)
        if not accepted or job is None:
            emitter.emit({"ok": False, "job_id": job_id, "cancel_requested": False, "error": "job not found"})
            return

        emitter.emit(
            {
                "ok": True,
                "job_id": job_id,
                "cancel_requested": True,
                "state": job.state.value,
                "message": "Cancel requested",
            }
        )

    def handle_retry_command(self, req: dict[str, Any], emitter: EventEmitter) -> dict[str, Any] | None:
        source_job_id = str(req.get("job_id") or req.get("source_job_id") or "").strip()
        if not source_job_id:
            emitter.emit({"ok": False, "error": "retry requires job_id", "retry_started": False})
            return None

        retry_req = build_retry_request(source_job_id, req)
        if retry_req is None:
            emitter.emit({"ok": False, "error": "retry source job not found", "retry_started": False, "source_job_id": source_job_id})
            return None

        emitter.emit({
            "ok": True,
            "retry_started": True,
            "source_job_id": source_job_id,
            "job_id": retry_req["job_id"],
            "message": "Retry request accepted",
        })
        return retry_req

    def handle_enqueue_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        try:
            ack = QUEUE_MANAGER.enqueue(req)
            payload = {**ack, **QUEUE_MANAGER.snapshot_payload()}
            emitter.emit(payload)
        except Exception as exc:
            emitter.emit({"type": "queue_ack", "ok": False, "action": "enqueue", "error": str(exc)})

    def handle_queue_status_command(self, emitter: EventEmitter) -> None:
        emitter.emit(QUEUE_MANAGER.queue_status())

    def handle_remove_queue_item_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        queue_item_id = str(req.get("queue_item_id") or "").strip()
        ok, message = QUEUE_MANAGER.remove_pending(queue_item_id)
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "remove_queue_item", "queue_item_id": queue_item_id, "message": message, **QUEUE_MANAGER.snapshot_payload()})

    def handle_clear_pending_queue_command(self, emitter: EventEmitter) -> None:
        removed = QUEUE_MANAGER.clear_pending()
        emitter.emit({"type": "queue_ack", "ok": True, "action": "clear_pending_queue", "removed_count": removed, **QUEUE_MANAGER.snapshot_payload()})

    def handle_cancel_queue_item_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        queue_item_id = str(req.get("queue_item_id") or "").strip() or None
        ok, message, item = QUEUE_MANAGER.cancel(queue_item_id)
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "cancel_queue_item", "queue_item_id": item.queue_item_id if item else queue_item_id, "message": message, **QUEUE_MANAGER.snapshot_payload()})

    def handle_retry_queue_item_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        source_job_id = str(req.get("job_id") or req.get("source_job_id") or "").strip()
        try:
            ack = QUEUE_MANAGER.retry_from_archive(source_job_id, req)
            emitter.emit({**ack, **QUEUE_MANAGER.snapshot_payload()})
        except Exception as exc:
            emitter.emit({"type": "queue_ack", "ok": False, "action": "retry_queue_item", "source_job_id": source_job_id, "error": str(exc), **QUEUE_MANAGER.snapshot_payload()})


    def handle_move_queue_item_up_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        queue_item_id = str(req.get("queue_item_id") or "").strip()
        ok, message = QUEUE_MANAGER.move_up(queue_item_id)
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "move_queue_item_up", "queue_item_id": queue_item_id, "message": message, **QUEUE_MANAGER.snapshot_payload()})

    def handle_move_queue_item_down_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        queue_item_id = str(req.get("queue_item_id") or "").strip()
        ok, message = QUEUE_MANAGER.move_down(queue_item_id)
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "move_queue_item_down", "queue_item_id": queue_item_id, "message": message, **QUEUE_MANAGER.snapshot_payload()})

    def handle_duplicate_queue_item_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        queue_item_id = str(req.get("queue_item_id") or "").strip()
        ok, message, new_queue_item_id = QUEUE_MANAGER.duplicate_queue_item(queue_item_id)
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "duplicate_queue_item", "queue_item_id": queue_item_id, "new_queue_item_id": new_queue_item_id, "message": message, **QUEUE_MANAGER.snapshot_payload()})

    def handle_pause_queue_command(self, emitter: EventEmitter) -> None:
        ok, message = QUEUE_MANAGER.pause()
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "pause_queue", "message": message, **QUEUE_MANAGER.snapshot_payload()})

    def handle_resume_queue_command(self, emitter: EventEmitter) -> None:
        ok, message = QUEUE_MANAGER.resume()
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "resume_queue", "message": message, **QUEUE_MANAGER.snapshot_payload()})

    def handle_cancel_all_queue_items_command(self, emitter: EventEmitter) -> None:
        removed_count, active_cancel_requested = QUEUE_MANAGER.cancel_all()
        emitter.emit({"type": "queue_ack", "ok": True, "action": "cancel_all_queue_items", "removed_count": removed_count, "active_cancel_requested": active_cancel_requested, "message": f"Cancelled active={active_cancel_requested} and cleared {removed_count} pending item(s).", **QUEUE_MANAGER.snapshot_payload()})

    def handle_generate_dataset_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        try:
            ack = QUEUE_MANAGER.enqueue_dataset(req)
            emitter.emit({**ack, **QUEUE_MANAGER.snapshot_payload()})
        except Exception as exc:
            emitter.emit({"type": "queue_ack", "ok": False, "action": "generate_dataset", "error": str(exc), **QUEUE_MANAGER.snapshot_payload()})

    def handle(self) -> None:
        emitter = EventEmitter(self)
        line = self.rfile.readline().decode("utf-8").strip()
        if not line:
            return

        try:
            req = json.loads(line)
        except Exception as exc:
            fallback_job = JobRecord(job_id=f"job_{uuid.uuid4().hex[:12]}", command="unknown")
            emitter.error(fallback_job, str(exc), traceback.format_exc(), code="invalid_request")
            return

        command = str(req.get("command") or req.get("action") or "").strip()
        if command == "cancel" or command == "cancel_job":
            self.handle_cancel_command(req, emitter)
            return
        if command in {"enqueue", "enqueue_job"}:
            self.handle_enqueue_command(req, emitter)
            return
        if command == "queue_status":
            self.handle_queue_status_command(emitter)
            return
        if command == "remove_queue_item":
            self.handle_remove_queue_item_command(req, emitter)
            return
        if command == "clear_pending_queue":
            self.handle_clear_pending_queue_command(emitter)
            return
        if command in {"cancel_queue_item", "cancel_active_queue_item"}:
            self.handle_cancel_queue_item_command(req, emitter)
            return
        if command == "retry_queue_item":
            self.handle_retry_queue_item_command(req, emitter)
            return
        if command == "move_queue_item_up":
            self.handle_move_queue_item_up_command(req, emitter)
            return
        if command == "move_queue_item_down":
            self.handle_move_queue_item_down_command(req, emitter)
            return
        if command == "duplicate_queue_item":
            self.handle_duplicate_queue_item_command(req, emitter)
            return
        if command == "pause_queue":
            self.handle_pause_queue_command(emitter)
            return
        if command == "resume_queue":
            self.handle_resume_queue_command(emitter)
            return
        if command == "cancel_all_queue_items":
            self.handle_cancel_all_queue_items_command(emitter)
            return
        if command == "generate_dataset":
            self.handle_generate_dataset_command(req, emitter)
            return

        if command == "import_workflow":
            emitter.emit(handle_import_workflow_command(req))
            return
        if command == "list_workflow_profiles":
            emitter.emit(handle_list_workflow_profiles_command(req))
            return
        if command == "comfy_runtime_status":
            emitter.emit(handle_comfy_runtime_status_command(req))
            return
        if command == "ensure_comfy_runtime":
            emitter.emit(handle_ensure_comfy_runtime_command(req))
            return
        if command == "start_comfy_runtime":
            emitter.emit(handle_start_comfy_runtime_command(req))
            return
        if command == "stop_comfy_runtime":
            emitter.emit(handle_stop_comfy_runtime_command(req))
            return
        if command == "restart_comfy_runtime":
            emitter.emit(handle_restart_comfy_runtime_command(req))
            return
        if command == "comfy_manager_status":
            emitter.emit(handle_comfy_manager_status_command(req))
            return
        if command == "install_comfy_manager":
            emitter.emit(handle_install_comfy_manager_command(req))
            return
        if command == "install_custom_node":
            emitter.emit(handle_install_custom_node_command(req))
            return
        if command == "install_recommended_video_nodes":
            emitter.emit(handle_install_recommended_video_nodes_command(req))
            return
        if command == "prepare_model_swap":
            emitter.emit(handle_prepare_model_swap_command(req))
            return
        if command == "retry" or command == "retry_job":
            retry_req = self.handle_retry_command(req, emitter)
            if retry_req is None:
                return
            req = retry_req
            command = str(req.get("command") or req.get("action") or "").strip()

        job = create_job(req)
        emitter.emit_job_update(job)

        if command == "ping":
            transition_job(job, JobState.COMPLETED)
            job.result = JobResult(task_type="ping")
            emitter.emit_job_update(job)
            emitter.emit({"type": "result", "ok": True, "pong": True, "job_id": job.job_id, "state": job.state.value})
            return

        if command not in {"t2i", "i2i", "t2v", "i2v", "comfy_workflow"}:
            emitter.error(job, f"Unknown command: {command}", code="unknown_command")
            return

        active_job = ActiveJobHandle(job=job)
        register_active_job(active_job)

        try:
            if command == "t2i":
                run_t2i(req, emitter, job, active_job)
            elif command == "i2i":
                run_i2i(req, emitter, job, active_job)
            elif command == "comfy_workflow":
                run_comfy_workflow(req, emitter, job, active_job)
            elif command in {"t2v", "i2v"}:
                if request_has_workflow_binding(req):
                    run_comfy_workflow(req, emitter, job, active_job)
                else:
                    run_native_video(req, emitter, job, active_job)
            emitter.result(job)
        except JobCancelledError as exc:
            if job.state != JobState.CANCELLED:
                cancel_job(job, str(exc))
                emitter.emit_job_update(job)
            emitter.result(job)
        except Exception as exc:
            emitter.error(job, str(exc), traceback.format_exc())
        finally:
            unregister_active_job(job.job_id)
            archive_job(job, req)


class ThreadedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def main() -> None:
    host = "127.0.0.1"
    port = 8765
    with ThreadedTCPServer((host, port), WorkerTCPHandler) as server:
        print(f"[service] SpellVision worker service listening on {host}:{port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()