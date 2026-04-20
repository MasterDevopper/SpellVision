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
                "items": items_payload,
            }

    def enqueue(self, req: dict[str, Any]) -> dict[str, Any]:
        task_command = str(req.get("task_command") or req.get("generation_command") or req.get("task") or "").strip()
        if task_command not in {"t2i", "i2i", "comfy_workflow"}:
            raise ValueError("enqueue requires task_command of 't2i', 'i2i', or 'comfy_workflow'")

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
    return {
        "task_type": req.get("task_type", req.get("command", "unknown")),
        "generator": "spellvision_worker_service",
        "backend": backend_name,
        "detected_pipeline": detected_pipeline,
        "timestamp": datetime.now().isoformat(),
        "prompt": req.get("prompt", ""),
        "negative_prompt": req.get("negative_prompt", ""),
        "model": req.get("model", ""),
        "width": req.get("width"),
        "height": req.get("height"),
        "steps": req.get("steps"),
        "cfg": req.get("cfg"),
        "seed": req.get("seed"),
        "device": device,
        "dtype": dtype,
        "image_path": image_path,
        "metadata_output": metadata_output,
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cache_hit": cache_hit,
        "job_id": job.job_id if job else req.get("job_id"),
        "state": job.state.value if job else "completed",
        "timestamps": asdict(job.timestamps) if job else None,
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
    job.progress.message = message
    job.timestamps.updated_at = utc_now_iso()
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

    def error(
        self,
        job: JobRecord,
        error_text: str,
        tb: str | None = None,
        code: str = "generation_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        fail_job(job, error_text, code=code, tb=tb, details=details)
        self.emit_job_update(job)
        payload: dict[str, Any] = {
            "type": "error",
            "ok": False,
            "job_id": job.job_id,
            "state": job.state.value,
            "error": error_text,
        }
        if details:
            payload["details"] = details
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


def _prompt_node_id(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, str):
        return value.strip()
    return ""


def _short_json(value: Any, limit: int = 800) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _validate_comfy_api_prompt(workflow: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings_out: list[str] = []

    if not isinstance(workflow, dict) or not workflow:
        return ["Compiled prompt is empty or not a JSON object."], warnings_out

    node_ids = {str(key) for key in workflow.keys()}
    found_output_like_node = False

    for node_id, node_payload in workflow.items():
        node_id_str = str(node_id)

        if not isinstance(node_payload, dict):
            errors.append(f"Node {node_id_str} is not an object.")
            continue

        class_type = str(node_payload.get("class_type") or "").strip()
        if not class_type:
            errors.append(f"Node {node_id_str} is missing class_type.")

        inputs = node_payload.get("inputs")
        if not isinstance(inputs, dict):
            errors.append(f"Node {node_id_str} is missing an inputs object.")
            continue

        class_type_lower = class_type.lower()
        if class_type_lower.startswith("save") or "preview" in class_type_lower or "output" in class_type_lower:
            found_output_like_node = True

        for input_name, input_value in inputs.items():
            if not isinstance(input_value, list):
                continue
            if len(input_value) < 2:
                continue
            if not isinstance(input_value[1], (int, float)):
                continue

            referenced_node_id = _prompt_node_id(input_value[0])
            if not referenced_node_id:
                warnings_out.append(
                    f"Node {node_id_str} input '{input_name}' has an empty node reference."
                )
                continue

            if referenced_node_id not in node_ids:
                errors.append(
                    f"Node {node_id_str} input '{input_name}' references missing node {referenced_node_id}."
                )

            try:
                slot_index = int(input_value[1])
                if slot_index < 0:
                    warnings_out.append(
                        f"Node {node_id_str} input '{input_name}' references negative output slot {slot_index}."
                    )
            except Exception:
                warnings_out.append(
                    f"Node {node_id_str} input '{input_name}' uses a non-integer slot reference."
                )

    if not found_output_like_node:
        warnings_out.append("No obvious save/output node was detected in the prompt graph.")

    return errors, warnings_out


def _format_comfy_prompt_rejection(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()

    if not isinstance(payload, dict):
        return _short_json(payload)

    parts: list[str] = []

    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        error_type = str(error_payload.get("type") or "").strip()
        error_message = str(
            error_payload.get("message")
            or error_payload.get("details")
            or error_payload.get("detail")
            or ""
        ).strip()
        if error_type and error_message:
            parts.append(f"{error_type}: {error_message}")
        elif error_type:
            parts.append(error_type)
        elif error_message:
            parts.append(error_message)
    elif isinstance(error_payload, str) and error_payload.strip():
        parts.append(error_payload.strip())

    for key in ("message", "detail", "details", "exception_message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in parts:
            parts.append(value.strip())

    node_errors = payload.get("node_errors")
    if isinstance(node_errors, dict) and node_errors:
        node_parts: list[str] = []
        for node_id, node_payload in list(node_errors.items())[:6]:
            if isinstance(node_payload, dict):
                node_class = str(
                    node_payload.get("class_type")
                    or node_payload.get("type")
                    or "node"
                ).strip()

                errors_list = node_payload.get("errors")
                if isinstance(errors_list, list) and errors_list:
                    rendered_errors: list[str] = []
                    for entry in errors_list[:3]:
                        if isinstance(entry, dict):
                            entry_message = str(
                                entry.get("message")
                                or entry.get("details")
                                or entry.get("detail")
                                or _short_json(entry)
                            ).strip()
                        else:
                            entry_message = str(entry).strip()
                        if entry_message:
                            rendered_errors.append(entry_message)
                    if rendered_errors:
                        node_parts.append(
                            f"node {node_id} ({node_class}): {' | '.join(rendered_errors)}"
                        )
                        continue

                node_parts.append(f"node {node_id} ({node_class}): {_short_json(node_payload)}")
            else:
                node_parts.append(f"node {node_id}: {_short_json(node_payload)}")

        if node_parts:
            parts.append("Node errors: " + "; ".join(node_parts))

    if parts:
        return " | ".join(parts)

    return _short_json(payload)


def _submit_comfy_prompt(api_url: str, workflow: dict[str, Any], *, skip_validation: bool = False) -> str:
    if not skip_validation:
        validation_errors, _ = _validate_comfy_api_prompt(workflow)
        if validation_errors:
            raise RuntimeError(
                "Compiled prompt validation failed: " + " | ".join(validation_errors[:6])
            )

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
        body_text = ""
        parsed_body: Any = None
        try:
            body_text = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body_text = ""

        if body_text:
            try:
                parsed_body = json.loads(body_text)
            except Exception:
                parsed_body = body_text

        detail = _format_comfy_prompt_rejection(parsed_body if parsed_body is not None else body_text)
        if not detail:
            detail = str(exc)

        raise RuntimeError(
            f"ComfyUI rejected prompt at {api_url}/prompt (HTTP {exc.code}): {detail}"
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
        emitter.progress(job, min(95, max(1, tick)), 100, f"waiting for ComfyUI ({int(elapsed)}s)")
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


def _extract_comfy_asset(history: dict[str, Any]) -> dict[str, Any] | None:
    outputs = history.get("outputs") or {}
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for key in ("images", "videos", "gifs", "audio"):
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

    validation_errors, validation_warnings = _validate_comfy_api_prompt(workflow)
    if validation_errors:
        raise RuntimeError(
            "Compiled prompt validation failed before submission: "
            + " | ".join(validation_errors[:6])
        )

    if validation_warnings:
        emitter.status(job, f"prompt validation warning: {validation_warnings[0]}")
    else:
        emitter.status(job, "compiled prompt validated")

    transition_job(job, JobState.RUNNING)
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

    emitter.status(job, "submitting prompt to ComfyUI")
    start = time.perf_counter()
    prompt_id = _submit_comfy_prompt(api_url, workflow, skip_validation=True)
    emitter.status(job, f"ComfyUI prompt submitted: {prompt_id}")

    history = _poll_comfy_history(api_url, prompt_id, req, emitter, job, active_job)
    asset = _extract_comfy_asset(history)
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
        "workflow_path": workflow_path,
        "prompt_id": prompt_id,
        "metadata": metadata_payload,
        "metadata_write_deferred": True,
        "comfy_runtime_endpoint": runtime_status.get("endpoint"),
        "comfy_runtime_pid": runtime_status.get("pid"),
    }

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

    def error(
        self,
        job: JobRecord,
        error_text: str,
        tb: str | None = None,
        code: str = "generation_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        fail_job(job, error_text, code=code, tb=tb, details=details)
        self.emit_job_update(job)


def imported_workflows_root() -> str:
    return str(Path(__file__).resolve().parent.parent / "runtime" / "imported_workflows")


def default_comfy_root() -> str:
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

        if command not in {"t2i", "i2i", "comfy_workflow"}:
            emitter.error(job, f"Unknown command: {command}", code="unknown_command")
            return

        active_job = ActiveJobHandle(job=job)
        register_active_job(active_job)

        try:
            if command == "t2i":
                run_t2i(req, emitter, job, active_job)
            elif command == "i2i":
                run_i2i(req, emitter, job, active_job)
            else:
                run_comfy_workflow(req, emitter, job, active_job)
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