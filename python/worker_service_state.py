"""Job state machine for the SpellVision worker service.

This module owns the data types and helper functions that describe the
lifecycle of a worker job: the JobState enum and its allowed transitions,
the JobRecord / JobProgress / JobError / JobResult / JobTimestamps
dataclasses, the per-job transition / progress / completion helpers, the
QueueItemState enum used by the queue manager, the JobEmitter protocol
shared with anything that emits messages back to the client, and the
ActiveJobHandle registry used for cooperative cancellation.

Extracted from worker_service.py in the Sprint16 refactor (Option A).
Behavior is intentionally unchanged: every symbol below was copy-moved
verbatim from worker_service.py with no edits. The only difference is
that worker_service.py now imports these names from here instead of
defining them inline.

Anything new added here should also stay pure: no torch, no comfy, no
network I/O, no module-level work beyond constants. Keep it cheap to
import.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Time helper
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Active-job registry (used for cooperative cancellation)
# ---------------------------------------------------------------------------

ACTIVE_JOBS: dict[str, "ActiveJobHandle"] = {}
ACTIVE_JOBS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Emitter protocol -- anything that ships messages back to the client must
# satisfy this. EventEmitter and QueueEmitter (defined in worker_service.py)
# both implement it.
# ---------------------------------------------------------------------------

class JobEmitter(Protocol):
    def emit(self, payload: dict[str, Any]) -> None: ...
    def emit_job_update(self, job: "JobRecord") -> None: ...
    def status(self, job: "JobRecord", message: str) -> None: ...
    def progress(self, job: "JobRecord", step: int, total: int, message: str | None = None) -> None: ...


# ---------------------------------------------------------------------------
# Queue-item state (used by QueueManager in worker_service.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Cancellation machinery
# ---------------------------------------------------------------------------

class JobCancelledError(RuntimeError):
    pass


@dataclass
class ActiveJobHandle:
    job: "JobRecord"
    cancel_event: threading.Event = field(default_factory=threading.Event)


# ---------------------------------------------------------------------------
# Job state machine
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Job record dataclasses
# ---------------------------------------------------------------------------

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
    active_adapters: list[Any] | None = None
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
    video_input_name: str | None = None
    video_completion_summary: str | None = None
    video_prompt_id: str | None = None
    output_video: str | None = None
    video_path: str | None = None
    video_validated_backend: bool = False
    video_family: str | None = None
    video_family_display_name: str | None = None
    video_family_validation_status: str | None = None
    video_family_validated: bool = False
    video_family_production_ready: bool = False
    video_family_backend_route: str | None = None
    video_family_contract_stack_kind: str | None = None
    video_family_required_components: list[Any] | None = None
    video_family_optional_components: list[Any] | None = None
    video_family_history_label_style: str | None = None
    video_family_runtime_affinity_fields: list[Any] | None = None
    video_family_readiness_notes: list[Any] | None = None
    video_family_contract_version: int = 0
    video_model_stack_summary: str | None = None
    video_low_model: str | None = None
    video_low_model_name: str | None = None
    video_high_model: str | None = None
    video_high_model_name: str | None = None
    video_primary_model: str | None = None
    video_primary_model_name: str | None = None
    video_vae: str | None = None
    video_vae_name: str | None = None
    video_text_encoder: str | None = None
    video_text_encoder_name: str | None = None
    video_width: int = 0
    video_height: int = 0
    video_resolution: str | None = None
    video_frame_count: int = 0
    runtime_transition: str | None = None
    runtime_target: str | None = None
    runtime_previous: str | None = None
    runtime_notes: str | None = None
    image_cache_active_before_runtime: bool = False
    image_cache_unloaded_before_video: bool = False
    image_cache_key_before_runtime: str | None = None
    video_runtime_signature_before: str | None = None
    video_runtime_reused: bool = False
    video_warm_reuse_candidate: bool = False
    video_warm_reuse_source: str | None = None
    video_runtime_affinity_signature: str | None = None
    video_runtime_transition: str | None = None
    video_runtime_truth_checked: bool = False
    video_runtime_truth_ok: bool = False
    video_runtime_truth_reason: str | None = None
    video_runtime_same_process: bool = False
    video_runtime_same_endpoint: bool = False
    video_runtime_comfy_pid_before: str | None = None
    video_runtime_comfy_pid_current: str | None = None
    video_runtime_comfy_endpoint_before: str | None = None
    video_runtime_comfy_endpoint_current: str | None = None
    video_runtime_cache_updated: bool = False
    video_runtime_cache: dict[str, Any] | None = None
    output_contract_version: int = 0
    output_contract_ok: bool = False
    output_contract_warnings: list[Any] | None = None
    final_output: str | None = None
    final_output_path: str | None = None
    original_output: str | None = None
    original_output_path: str | None = None
    output_exists: bool = False
    output_file_size_bytes: int = 0
    output_modified_at: str | None = None
    output_finalized_at: str | None = None
    final_metadata: str | None = None
    final_metadata_path: str | None = None
    metadata_exists: bool = False
    metadata_file_size_bytes: int = 0
    metadata_modified_at: str | None = None
    metadata_finalized_at: str | None = None
    metadata_write_status: str | None = None
    metadata_write_error: str | None = None
    video_outputs: list[Any] | None = None
    video_output_count: int = 0
    video_primary_output_role: str | None = None
    video_preferred_output_role: str | None = None
    ltx_preferred_output: str | None = None
    video_secondary_output: str | None = None
    video_secondary_metadata_output: str | None = None
    ltx_full_output: str | None = None
    ltx_full_metadata_output: str | None = None
    ltx_distilled_output: str | None = None
    ltx_distilled_metadata_output: str | None = None


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


# ---------------------------------------------------------------------------
# Job lifecycle helpers
# ---------------------------------------------------------------------------

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
        # Instant jobs (ping) ask for COMPLETED from QUEUED. That hop stays illegal;
        # walk the legal path instead so the terminal state is honest.
        if new_state == JobState.COMPLETED:
            return _walk_to_completed(job)
        return False

    _apply_job_state(job, new_state)
    return True


def _apply_job_state(job: JobRecord, new_state: JobState) -> None:
    now = utc_now_iso()
    job.state = new_state
    job.timestamps.updated_at = now

    if new_state == JobState.STARTING and not job.timestamps.started_at:
        job.timestamps.started_at = now

    if new_state in TERMINAL_STATES:
        job.timestamps.finished_at = now


def _walk_to_completed(job: JobRecord) -> bool:
    for hop in (JobState.STARTING, JobState.RUNNING, JobState.COMPLETED):
        if job.state == hop:
            continue
        if hop not in VALID_TRANSITIONS.get(job.state, set()):
            return False
        _apply_job_state(job, hop)
    return job.state == JobState.COMPLETED


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
    contract_version = int(payload.get("output_contract_version") or 0)
    if contract_version > 0 and not bool(payload.get("output_contract_ok", False)):
        warnings = payload.get("output_contract_warnings")
        fail_job(
            job,
            "Generated artifact failed finalization validation.",
            code="output_contract_failed",
            details={
                "output_contract_version": contract_version,
                "output_contract_warnings": warnings if isinstance(warnings, list) else [],
                "final_output_path": payload.get("final_output_path") or payload.get("output"),
                "final_metadata_path": payload.get("final_metadata_path") or payload.get("metadata_output"),
            },
        )
        return

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
        active_adapters=payload.get("active_adapters") if isinstance(payload.get("active_adapters"), list) else None,
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
        video_input_name=payload.get("video_input_name"),
        video_completion_summary=payload.get("video_completion_summary"),
        video_prompt_id=payload.get("video_prompt_id"),
        output_video=payload.get("output_video"),
        video_path=payload.get("video_path"),
        video_validated_backend=bool(payload.get("video_validated_backend", False)),
        video_family=payload.get("video_family"),
        video_family_display_name=payload.get("video_family_display_name"),
        video_family_validation_status=payload.get("video_family_validation_status"),
        video_family_validated=bool(payload.get("video_family_validated", False)),
        video_family_production_ready=bool(payload.get("video_family_production_ready", False)),
        video_family_backend_route=payload.get("video_family_backend_route"),
        video_family_contract_stack_kind=payload.get("video_family_contract_stack_kind"),
        video_family_required_components=payload.get("video_family_required_components") if isinstance(payload.get("video_family_required_components"), list) else None,
        video_family_optional_components=payload.get("video_family_optional_components") if isinstance(payload.get("video_family_optional_components"), list) else None,
        video_family_history_label_style=payload.get("video_family_history_label_style"),
        video_family_runtime_affinity_fields=payload.get("video_family_runtime_affinity_fields") if isinstance(payload.get("video_family_runtime_affinity_fields"), list) else None,
        video_family_readiness_notes=payload.get("video_family_readiness_notes") if isinstance(payload.get("video_family_readiness_notes"), list) else None,
        video_family_contract_version=int(payload.get("video_family_contract_version") or 0),
        video_model_stack_summary=payload.get("video_model_stack_summary"),
        video_low_model=payload.get("video_low_model"),
        video_low_model_name=payload.get("video_low_model_name"),
        video_high_model=payload.get("video_high_model"),
        video_high_model_name=payload.get("video_high_model_name"),
        video_primary_model=payload.get("video_primary_model"),
        video_primary_model_name=payload.get("video_primary_model_name"),
        video_vae=payload.get("video_vae"),
        video_vae_name=payload.get("video_vae_name"),
        video_text_encoder=payload.get("video_text_encoder"),
        video_text_encoder_name=payload.get("video_text_encoder_name"),
        video_width=int(payload.get("video_width") or 0),
        video_height=int(payload.get("video_height") or 0),
        video_resolution=payload.get("video_resolution"),
        video_frame_count=int(payload.get("video_frame_count") or payload.get("video_frames") or 0),
        runtime_transition=payload.get("runtime_transition"),
        runtime_target=payload.get("runtime_target"),
        runtime_previous=payload.get("runtime_previous"),
        runtime_notes=payload.get("runtime_notes"),
        image_cache_active_before_runtime=bool(payload.get("image_cache_active_before_runtime", False)),
        image_cache_unloaded_before_video=bool(payload.get("image_cache_unloaded_before_video", False)),
        image_cache_key_before_runtime=payload.get("image_cache_key_before_runtime"),
        video_runtime_signature_before=payload.get("video_runtime_signature_before"),
        video_runtime_reused=bool(payload.get("video_runtime_reused", False)),
        video_warm_reuse_candidate=bool(payload.get("video_warm_reuse_candidate", False)),
        video_warm_reuse_source=payload.get("video_warm_reuse_source"),
        video_runtime_affinity_signature=payload.get("video_runtime_affinity_signature"),
        video_runtime_transition=payload.get("video_runtime_transition"),
        video_runtime_truth_checked=bool(payload.get("video_runtime_truth_checked", False)),
        video_runtime_truth_ok=bool(payload.get("video_runtime_truth_ok", False)),
        video_runtime_truth_reason=payload.get("video_runtime_truth_reason"),
        video_runtime_same_process=bool(payload.get("video_runtime_same_process", False)),
        video_runtime_same_endpoint=bool(payload.get("video_runtime_same_endpoint", False)),
        video_runtime_comfy_pid_before=payload.get("video_runtime_comfy_pid_before"),
        video_runtime_comfy_pid_current=payload.get("video_runtime_comfy_pid_current"),
        video_runtime_comfy_endpoint_before=payload.get("video_runtime_comfy_endpoint_before"),
        video_runtime_comfy_endpoint_current=payload.get("video_runtime_comfy_endpoint_current"),
        video_runtime_cache_updated=bool(payload.get("video_runtime_cache_updated", False)),
        video_runtime_cache=payload.get("video_runtime_cache") if isinstance(payload.get("video_runtime_cache"), dict) else None,
        output_contract_version=int(payload.get("output_contract_version") or 0),
        output_contract_ok=bool(payload.get("output_contract_ok", False)),
        output_contract_warnings=payload.get("output_contract_warnings") if isinstance(payload.get("output_contract_warnings"), list) else None,
        final_output=payload.get("final_output"),
        final_output_path=payload.get("final_output_path"),
        original_output=payload.get("original_output"),
        original_output_path=payload.get("original_output_path"),
        output_exists=bool(payload.get("output_exists", False)),
        output_file_size_bytes=int(payload.get("output_file_size_bytes") or 0),
        output_modified_at=payload.get("output_modified_at"),
        output_finalized_at=payload.get("output_finalized_at"),
        final_metadata=payload.get("final_metadata"),
        final_metadata_path=payload.get("final_metadata_path"),
        metadata_exists=bool(payload.get("metadata_exists", False)),
        metadata_file_size_bytes=int(payload.get("metadata_file_size_bytes") or 0),
        metadata_modified_at=payload.get("metadata_modified_at"),
        metadata_finalized_at=payload.get("metadata_finalized_at"),
        metadata_write_status=payload.get("metadata_write_status"),
        metadata_write_error=payload.get("metadata_write_error"),
        video_outputs=payload.get("video_outputs") if isinstance(payload.get("video_outputs"), list) else None,
        video_output_count=int(payload.get("video_output_count") or 0),
        video_primary_output_role=payload.get("video_primary_output_role"),
        video_preferred_output_role=payload.get("video_preferred_output_role"),
        ltx_preferred_output=payload.get("ltx_preferred_output"),
        video_secondary_output=payload.get("video_secondary_output"),
        video_secondary_metadata_output=payload.get("video_secondary_metadata_output"),
        ltx_full_output=payload.get("ltx_full_output"),
        ltx_full_metadata_output=payload.get("ltx_full_metadata_output"),
        ltx_distilled_output=payload.get("ltx_distilled_output"),
        ltx_distilled_metadata_output=payload.get("ltx_distilled_metadata_output"),
    )
    completion_message = "generation complete"
    request_kind = str(payload.get("video_request_kind") or "").strip().lower()
    if request_kind == "i2v":
        completion_message = str(payload.get("video_completion_summary") or "image-to-video complete")
    elif request_kind == "t2v" or payload.get("video_backend_type"):
        completion_message = str(payload.get("video_completion_summary") or "video generation complete")
    update_job_progress(job, job.progress.total or job.progress.current or 1, job.progress.total or 1, completion_message)
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


def register_active_job(active_job: ActiveJobHandle) -> bool:
    with ACTIVE_JOBS_LOCK:
        if active_job.job.job_id in ACTIVE_JOBS:
            return False
        ACTIVE_JOBS[active_job.job.job_id] = active_job
        return True


def unregister_active_job(job_id: str, expected_owner: ActiveJobHandle | None = None) -> bool:
    with ACTIVE_JOBS_LOCK:
        if expected_owner is not None and ACTIVE_JOBS.get(job_id) is not expected_owner:
            return False
        return ACTIVE_JOBS.pop(job_id, None) is not None


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


# --- request option parsing -----------------------------------------------------------------

def numeric_option(req: dict, key: str, default: float) -> float:
    """A numeric request option where **zero is a legitimate value**.

    ``float(req.get(key) or default)`` is the idiom this replaces, and it is wrong whenever 0 means
    something: 0 is falsy, so an explicit zero is silently swapped for the default. Measured
    instances in this repo, all of which a caller could reasonably ask for:

    * ``graceful_timeout_sec=0``  -- stop now, do not wait for a clean exit
    * ``startup_timeout_sec=0``   -- do not block on startup
    * ``limit=0``                 -- return no rows
    * ``budget_sec=0``            -- do one slice, do not loop

    The last one bit during the class-index build: the driver passed 0 to mean "single attempt" and
    got the 120-second default, so a probe against an unreachable ComfyUI hung for two minutes.

    Returns the default only when the key is ABSENT or unparseable -- never because the value was
    zero, empty, or False.
    """
    if key not in req:
        return float(default)
    value = req.get(key)
    if value is None or isinstance(value, bool):
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
