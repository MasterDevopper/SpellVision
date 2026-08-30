"""Persistent generation queue for the SpellVision worker.

Extracted from worker_service.py. Runtime helpers (dispatch, emitters, LTX
normalize) are resolved lazily so this module can be imported mid-load.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
import traceback
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from worker_service_state import (
    ActiveJobHandle,
    JobCancelledError,
    JobRecord,
    JobState,
    QUEUE_TERMINAL_STATES,
    QueueItemState,
    cancel_job,
    create_job,
    queue_state_from_job_state,
    get_active_job,
    register_active_job,
    request_job_cancel,
    transition_job,
    unregister_active_job,
    utc_now_iso,
)
from worker_durable_state import atomic_write_json, worker_state_root

# WARNING and above, because the root logger sits at WARNING and info() is invisible in this repo
# (CLAUDE.md 4). What this module logs is a backend cancel that failed -- a card still held.
log = logging.getLogger("spellvision.worker.queue")


def _ws():
    import worker_service as ws
    return ws


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

    # snapshot_payload() runs on every UI poll (1800ms) over up to 100 items. Profiling a full
    # 100-item queue put 60% of the build in video_request_metadata_from_request, which each item
    # re-derived ~5x per snapshot: once here, and again inside affinity_signature_for_request,
    # affinity_summary_for_request and queue_warm_reuse_prediction. All of it is a pure function
    # of request_snapshot, so it is derived once and cached.
    #
    # request_snapshot is NOT immutable -- _run_queue_item() rewrites the output paths when the
    # item starts -- so that one mutation site calls invalidate_derived(). Every mutation and
    # every read happens under QueueManager.lock, so the cache needs no lock of its own.
    _derived: dict[str, Any] | None = field(default=None, repr=False, compare=False)
    # result is only ever REASSIGNED (update_from_job builds a fresh asdict), never mutated in
    # place, so identity is a sound cache key: it misses on every update while a job runs and
    # hits for good once the item reaches a terminal state.
    _result_copy_src: dict[str, Any] | None = field(default=None, repr=False, compare=False)
    _result_copy: dict[str, Any] | None = field(default=None, repr=False, compare=False)

    def invalidate_derived(self) -> None:
        self._derived = None

    def derived(self) -> dict[str, Any]:
        if self._derived is None:
            req = self.request_snapshot
            is_video = _ws().is_video_request(req)
            self._derived = {
                "prompt_summary": str(req.get("prompt") or req.get("workflow_profile_name") or "")[:160],
                "video_request_details": _ws().video_request_metadata_from_request(req) if is_video else {},
                "affinity_signature": _ws().affinity_signature_for_request(req),
                "affinity_summary": _ws().affinity_summary_for_request(req),
            }
        return self._derived

    def _result_payload(self) -> dict[str, Any] | None:
        if self.result is None:
            self._result_copy_src = None
            self._result_copy = None
            return None
        if self._result_copy_src is not self.result:
            self._result_copy_src = self.result
            trimmed = copy.deepcopy(self.result)
            # The queue snapshot ships every item's result on every poll. video_runtime_cache is
            # the largest thing in there (~1.3KB/item) and the UI never reads it -- both C++ call
            # sites take the video_runtime_cache_updated bool instead. Dropping it here trims the
            # wire only; the item's own result, the disk manifest and the job archive keep it.
            trimmed.pop("video_runtime_cache", None)
            self._result_copy = trimmed
        return self._result_copy

    def payload(self) -> dict[str, Any]:
        derived = self.derived()
        prompt_summary = derived["prompt_summary"]
        video_request_details = derived["video_request_details"]

        return {
            "queue_item_id": self.queue_item_id,
            "command": self.command,
            "state": self.state.value,
            "worker_job_id": self.worker_job_id,
            "source_job_id": self.source_job_id,
            "retry_count": self.retry_count,
            # QueueItemProgress / QueueItemTimestamps are flat scalar dataclasses, so a shallow
            # copy of __dict__ is equivalent to asdict() and skips its recursive walk.
            "progress": dict(vars(self.progress)),
            "result": self._result_payload(),
            "error": copy.deepcopy(self.error),
            "timestamps": dict(vars(self.timestamps)),
            "output": self.request_snapshot.get("output"),
            "original_output": self.request_snapshot.get("original_output"),
            "prompt": prompt_summary,
            "metadata_output": self.request_snapshot.get("metadata_output"),
            "input_image": self.request_snapshot.get("input_image"),
            "video_input_image": self.request_snapshot.get("video_input_image") or self.request_snapshot.get("input_keyframe") or self.request_snapshot.get("source_image"),
            "video_input_name": self.request_snapshot.get("video_input_name") or os.path.basename(str(self.request_snapshot.get("video_input_image") or self.request_snapshot.get("input_keyframe") or self.request_snapshot.get("source_image") or self.request_snapshot.get("input_image") or "")),
            "video_has_input_image": bool(self.request_snapshot.get("video_has_input_image", False)),
            **video_request_details,
            "original_metadata_output": self.request_snapshot.get("original_metadata_output"),
            "affinity_signature": derived["affinity_signature"],
            "affinity_summary": derived["affinity_summary"],
    }


# Request keys that carry a secret. The queue manifest is written to DISK in plain JSON and
# survives restarts, so anything in a request_snapshot is persisted verbatim and readable by
# anything that can read the file.
#
# No credential-bearing command is enqueued today -- import_workflow, start_download and
# civitai_variants are all control commands that never touch the queue -- so this is defence in
# depth rather than a live leak. It is here because the failure mode is silent and permanent: the
# day someone enqueues a command that carries a key, the key lands in a file on disk and nothing
# reports it. The redaction costs nothing and cannot regress.
SECRET_REQUEST_KEYS = frozenset({
    "civitai_api_key", "hf_token", "huggingface_token", "api_key", "authorization",
    "access_token", "bearer_token", "password", "secret",
    # The worker's own integration token. An enqueued request carries it, and the queue manifest is
    # plain JSON on disk, so without this a token would be written out in the clear.
    "auth_token",
})
_REDACTED = "<redacted>"


def redact_secrets(payload: Any) -> Any:
    """A deep copy with known credential keys replaced. Matching is case-insensitive."""
    if isinstance(payload, dict):
        return {
            key: (_REDACTED if str(key).strip().lower() in SECRET_REQUEST_KEYS
                  else redact_secrets(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_secrets(entry) for entry in payload]
    return payload



def _failed_backend_cancels(handle: ActiveJobHandle | None) -> list[Any]:
    """The cancel hooks that could NOT reach the backend.

    An empty list means either that everything worked or that there was nothing out of process to
    stop; both are a clean cancel. A non-empty one means the user let go of a card that is still
    held, and saying so is the difference between a cancel and the appearance of one.
    """
    if handle is None:
        return []
    return [o for o in handle.last_cancel_outcomes if isinstance(o, dict) and not o.get("ok")]


class QueueManager:
    def __init__(self, manifest_path: Path | None = None) -> None:
        self.lock = threading.Lock()
        self.pending: deque[str] = deque()
        self.items: dict[str, QueueItem] = {}
        self.order: list[str] = []
        self.active_queue_item_id: str | None = None
        self.paused: bool = False
        self.manifest_path = manifest_path or (worker_state_root() / "queue_manifest.json")
        self._manifest_recovered = False
        self._recovered_started = False

    def recover_from_manifest(self) -> None:
        with self.lock:
            if self._manifest_recovered:
                return
            self._manifest_recovered = True
            self._load_manifest_unlocked()

    @staticmethod
    def _item_manifest_payload(item: QueueItem) -> dict[str, Any]:
        return {
            "queue_item_id": item.queue_item_id,
            "command": item.command,
            # Redacted, not raw: this dict is written to disk and kept across restarts.
            "request_snapshot": redact_secrets(copy.deepcopy(item.request_snapshot)),
            "state": item.state.value,
            "worker_job_id": item.worker_job_id,
            "source_job_id": item.source_job_id,
            "retry_count": item.retry_count,
            "progress": asdict(item.progress),
            "result": copy.deepcopy(item.result),
            "error": copy.deepcopy(item.error),
            "timestamps": asdict(item.timestamps),
        }

    def _persist_locked(self) -> None:
        atomic_write_json(
            self.manifest_path,
            {
                "type": "spellvision_queue_manifest",
                "schema_version": 1,
                "updated_at": utc_now_iso(),
                "paused": self.paused,
                "active_queue_item_id": self.active_queue_item_id,
                "order": list(self.order),
                "items": [
                    self._item_manifest_payload(self.items[queue_item_id])
                    for queue_item_id in self.order
                    if queue_item_id in self.items
                ],
            },
        )

    def _load_manifest_unlocked(self) -> None:
        if not self.manifest_path.is_file():
            return
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return
        raw_items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(raw_items, list):
            return

        recovered_interrupted = False
        for raw in raw_items[-200:]:
            if not isinstance(raw, dict):
                continue
            queue_item_id = str(raw.get("queue_item_id") or "").strip()
            command = str(raw.get("command") or "").strip().lower()
            request_snapshot = raw.get("request_snapshot")
            try:
                state = QueueItemState(str(raw.get("state") or ""))
            except ValueError:
                continue
            if not queue_item_id or not command or not isinstance(request_snapshot, dict):
                continue

            progress = raw.get("progress") if isinstance(raw.get("progress"), dict) else {}
            timestamps = raw.get("timestamps") if isinstance(raw.get("timestamps"), dict) else {}
            item = QueueItem(
                queue_item_id=queue_item_id,
                command=command,
                request_snapshot=copy.deepcopy(request_snapshot),
                state=state,
                worker_job_id=str(raw.get("worker_job_id") or "").strip() or None,
                source_job_id=str(raw.get("source_job_id") or "").strip() or None,
                retry_count=int(raw.get("retry_count") or 0),
                progress=QueueItemProgress(
                    current=int(progress.get("current") or 0),
                    total=int(progress.get("total") or 0),
                    percent=float(progress.get("percent") or 0.0),
                    message=str(progress.get("message") or "queued"),
                ),
                result=copy.deepcopy(raw.get("result")) if isinstance(raw.get("result"), dict) else None,
                error=copy.deepcopy(raw.get("error")) if isinstance(raw.get("error"), dict) else None,
                timestamps=QueueItemTimestamps(
                    created_at=str(timestamps.get("created_at") or utc_now_iso()),
                    started_at=str(timestamps.get("started_at") or "").strip() or None,
                    finished_at=str(timestamps.get("finished_at") or "").strip() or None,
                    updated_at=str(timestamps.get("updated_at") or utc_now_iso()),
                ),
            )
            if item.state in {QueueItemState.PREPARING, QueueItemState.RUNNING}:
                item.state = QueueItemState.FAILED
                item.error = {
                    "code": "worker_restart_interrupted",
                    "message": "Worker restarted before this queue item reached a terminal state.",
                    "retryable": True,
                }
                item.timestamps.finished_at = utc_now_iso()
                item.timestamps.updated_at = item.timestamps.finished_at
                recovered_interrupted = True
            elif item.state == QueueItemState.QUEUED and item.error:
                # A QUEUED item carrying an error is a contradiction, and it was a permanent loop.
                # QUEUED -> FAILED was not a legal job transition and fail_job discarded the result,
                # so a handler that raised before reaching STARTING left the job at QUEUED with an
                # error; the item reverted PREPARING -> QUEUED, was persisted, and was rebuilt into
                # `pending` by the line below on every start -- re-running and re-failing forever.
                #
                # The state machine no longer produces this (see _walk_to_failed), but manifests
                # written before that fix are on disk NOW, and they would keep looping. Recovering
                # them here is what stops an existing install from repeating the bug after the fix.
                item.state = QueueItemState.FAILED
                item.timestamps.finished_at = utc_now_iso()
                item.timestamps.updated_at = item.timestamps.finished_at
                recovered_interrupted = True
            self.items[queue_item_id] = item

        raw_order = payload.get("order") if isinstance(payload.get("order"), list) else []
        self.order = [str(qid) for qid in raw_order if str(qid) in self.items]
        self.order.extend(qid for qid in self.items if qid not in self.order)
        self.pending = deque(
            qid for qid in self.order if self.items[qid].state == QueueItemState.QUEUED
        )
        self.active_queue_item_id = None
        self.paused = bool(payload.get("paused", False))
        if recovered_interrupted:
            self._persist_locked()

    def start_recovered(self) -> None:
        with self.lock:
            if self._recovered_started:
                return
            self._recovered_started = True
            if not self._manifest_recovered:
                self._manifest_recovered = True
                self._load_manifest_unlocked()
            self._start_next_locked()

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
                # Hand over the signature payload() already derived so the prediction does not
                # recompute it (it is the expensive half of this loop for video items).
                warm_reuse_candidate, warm_reuse_source, item_signature = _ws().queue_warm_reuse_prediction(
                    item.request_snapshot,
                    previous_signature=previous_signature,
                    item_signature=payload.get("affinity_signature"),
                )
                payload["warm_reuse_candidate"] = warm_reuse_candidate
                payload["warm_reuse_source"] = warm_reuse_source
                if item.state in {QueueItemState.QUEUED, QueueItemState.PREPARING, QueueItemState.RUNNING}:
                    previous_signature = item_signature
                items_payload.append(payload)

            def active_queue_affinity_for(command: str) -> str | None:
                if self.active_queue_item_id and self.active_queue_item_id in self.items:
                    active_item = self.items[self.active_queue_item_id]
                    if active_item.command == command:
                        return _ws().affinity_signature_for_request(active_item.request_snapshot)
                return _ws().active_affinity_signature_for_command(command)

            return {
                "type": "queue_snapshot",
                "ok": True,
                "active_queue_item_id": self.active_queue_item_id,
                "queue_paused": self.paused,
                "pending_count": sum(1 for qid in self.pending if qid in self.items),
                "total_count": len(self.items),
                "queue_order_preserved": True,
                "active_affinity_t2i": active_queue_affinity_for("t2i"),
                "active_affinity_i2i": active_queue_affinity_for("i2i"),
                "active_affinity_t2v": active_queue_affinity_for("t2v"),
                "active_affinity_i2v": active_queue_affinity_for("i2v"),
                "items": items_payload,
            }

    def enqueue(self, req: dict[str, Any]) -> dict[str, Any]:
        raw_task_command = str(req.get("task_command") or req.get("generation_command") or req.get("task") or "").strip().lower()
        execution_command = _ws()._queue_ltx_execution_command(req, raw_task_command)
        task_command = _ws()._queue_display_command_for_execution(req, execution_command, raw_task_command)

        if task_command not in {
            "t2i",
            "i2i",
            "t2v",
            "i2v",
            "comfy_workflow",
            "i23d",
            "t23d",
            "gen3d",
            "clothes_only",
            "garment_shrinkwrap",
            "krea2_regional_inpaint",
            "look_complete",
        }:
            raise ValueError("enqueue requires display task_command of 't2i', 'i2i', 't2v', 'i2v', 'comfy_workflow', or 'i23d'")

        if execution_command not in {
            "t2i",
            "i2i",
            "t2v",
            "i2v",
            "comfy_workflow",
            "ltx_prompt_api_gated_submission",
            "i23d",
            "t23d",
            "gen3d",
            "clothes_only",
            "garment_shrinkwrap",
            "krea2_regional_inpaint",
            "look_complete",
        }:
            raise ValueError(f"enqueue received unsupported execution command: {execution_command}")

        queue_item_id = str(req.get("queue_item_id") or f"queue_{uuid.uuid4().hex[:12]}")

        request_snapshot = _ws().clone_request_snapshot(req)

        # Sprint 15C Pass 29I:
        # Keep the visible queue command as t2v/i2v, but preserve the worker
        # execution command. The old code rewrote command=t2v and removed
        # task_command, which forced LTX into run_native_video().
        request_snapshot["command"] = execution_command
        request_snapshot["worker_command"] = execution_command
        request_snapshot["execution_command"] = execution_command
        request_snapshot["dispatch_command"] = execution_command
        request_snapshot["task_command"] = execution_command
        request_snapshot["workflow_task_command"] = execution_command

        request_snapshot["queue_display_command"] = task_command
        request_snapshot["source_generation_mode"] = request_snapshot.get("source_generation_mode") or task_command
        request_snapshot["generation_mode"] = request_snapshot.get("generation_mode") or task_command
        request_snapshot["task_type"] = request_snapshot.get("task_type") or task_command
        request_snapshot["mode"] = request_snapshot.get("mode") or task_command

        request_snapshot.pop("generation_command", None)
        request_snapshot.pop("queue_item_id", None)

        if execution_command == "ltx_prompt_api_gated_submission":
            request_snapshot = _ws()._normalize_ltx_prompt_api_request(request_snapshot)
            request_snapshot["queue_display_command"] = task_command
            request_snapshot["source_generation_mode"] = task_command
            request_snapshot["generation_mode"] = task_command
            request_snapshot["task_type"] = task_command
            request_snapshot["mode"] = task_command

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
            existing = self.items.get(queue_item_id)
            if existing is not None and existing.state not in QUEUE_TERMINAL_STATES:
                raise ValueError(f"duplicate live queue_item_id: {queue_item_id}")
            self.items[queue_item_id] = item
            if queue_item_id in self.order:
                self.order.remove(queue_item_id)
            self.order.append(queue_item_id)
            self.pending.append(queue_item_id)
            self._persist_locked()
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
            previous_state = item.state
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
            if item.state != previous_state or item.state in QUEUE_TERMINAL_STATES:
                self._persist_locked()

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
            self._persist_locked()
            thread = threading.Thread(target=self._run_queue_item, args=(queue_item_id,), daemon=True)
            thread.start()
            return

    def _finalize_queue_item(self, queue_item_id: str) -> None:
        with self.lock:
            if self.active_queue_item_id == queue_item_id:
                self.active_queue_item_id = None
            self._start_next_locked()
            self._persist_locked()

    def _run_queue_item(self, queue_item_id: str) -> None:
        with self.lock:
            item = self.items.get(queue_item_id)
            if item is None:
                return
            req = _ws().clone_request_snapshot(item.request_snapshot)
            # C3-FOLLOW-UP CANDIDATE (NOT migrated): the queue plain switch reads item.command, which
            # equals req["command"] only post-enqueue. Routing it through canonical_command(req) would
            # change behavior when they differ (pinned by test_dispatch_characterization), so per the
            # behavior-preserving rule it stays as-is until that invariant is proven/asserted.
            item_command = item.command
            execution_command = _ws()._queue_ltx_execution_command(req, item_command)
            if execution_command == "ltx_prompt_api_gated_submission":
                req = _ws()._normalize_ltx_prompt_api_request(req)
                req["queue_display_command"] = item_command
                req["source_generation_mode"] = item_command
                req["generation_mode"] = item_command
                req["task_type"] = item_command
                req["mode"] = item_command

        base_output = str(req.get("original_output") or req.get("output") or "").strip()
        base_metadata_output = str(
            req.get("original_metadata_output") or req.get("metadata_output") or ""
        ).strip()

        if base_output:
            unique_output, unique_metadata_output = _ws().safe_unique_output_paths(
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
                    # The only place request_snapshot changes after enqueue -- drop the payload
                    # derivations cached off it.
                    item.invalidate_derived()
                    self._persist_locked()

        queue_warm_reuse_expected, queue_warm_reuse_source, queue_affinity_signature = _ws().queue_warm_reuse_prediction(req)
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
        emitter = _ws().QueueEmitter(self, queue_item_id)
        if not register_active_job(active_job):
            transition_job(job, JobState.STARTING)
            emitter.error(
                job,
                f"An active job already owns job_id '{job.job_id}'.",
                code="duplicate_job_id",
            )
            _ws().archive_job(job, req)
            self._finalize_queue_item(queue_item_id)
            return

        try:
            if execution_command == "ltx_prompt_api_gated_submission":
                _ws().run_ltx_prompt_api_queued_job(req, emitter, job, active_job)
            else:
                _ws().dispatch_generation(item_command, req, emitter, job, active_job)  # C1: single generation dispatcher
            emitter.result(job)
        except JobCancelledError as exc:
            if job.state != JobState.CANCELLED:
                cancel_job(job, str(exc))
                emitter.emit_job_update(job)
            emitter.result(job)
        except Exception as exc:
            emitter.error(job, str(exc), traceback.format_exc())

        finally:
            unregister_active_job(job.job_id, active_job)
            _ws().archive_job(job, req)
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
            self._persist_locked()
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
            self._persist_locked()
            return True, "queue item moved down"

    def duplicate_queue_item(self, queue_item_id: str) -> tuple[bool, str, str | None]:
        with self.lock:
            source = self.items.get(queue_item_id)
            if source is None:
                return False, "queue item not found", None
            request_snapshot = _ws().clone_request_snapshot(source.request_snapshot)
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
                new_output, new_metadata_output = _ws().safe_unique_output_paths(
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
            self._persist_locked()
            return True, "queue paused"

    def resume(self) -> tuple[bool, str]:
        with self.lock:
            if not self.paused:
                return False, "queue is not paused"
            self.paused = False
            self._start_next_locked()
            self._persist_locked()
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
            self._persist_locked()
        active_cancelled = False
        if active_item and active_item.worker_job_id:
            handle = get_active_job(active_item.worker_job_id)
            active_cancelled, _job = request_job_cancel(active_item.worker_job_id)
            for failure in _failed_backend_cancels(handle):
                log.warning("cancel_all: backend cancel failed: %s", failure)
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
        base_request = _ws().clone_request_snapshot(req)
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
                job_req = _ws().clone_request_snapshot(base_request)
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
            self._persist_locked()
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
            self._persist_locked()
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
                self._persist_locked()
                return True, "queue item cancelled", item
            else:
                return False, f"queue item cannot be cancelled in state={item.state.value}", item

        # The handle is read BEFORE the cancel, because request_job_cancel is what runs the hooks
        # and the job thread may unregister the moment it sees the flag.
        handle = get_active_job(item.worker_job_id)
        accepted, _job = request_job_cancel(item.worker_job_id)
        if not accepted:
            return False, "active worker job not found", item
        failed = _failed_backend_cancels(handle)
        if failed:
            # The UI cancels through this method, not the raw cancel command, so this is the path
            # that has to be honest: the queue item is cancelled but the card may still be held.
            return True, (
                f"cancel requested, but {len(failed)} backend cancel(s) failed -- ComfyUI may still "
                "be rendering"
            ), item
        return True, "cancel requested", item

    def retry_from_archive(self, source_job_id: str, req: dict[str, Any]) -> dict[str, Any]:
        # An empty id must be refused before the lookup, not passed into it. The fallback below
        # matches source_job_id against a SET that includes "" whenever an item has no worker job
        # id yet -- so an empty id matched an arbitrary terminal item and retried THAT, re-running
        # a job the user never pointed at. Measured live: a retry with no job_id enqueued work.
        source_job_id = str(source_job_id or "").strip()
        if not source_job_id:
            raise ValueError("retry requires the job id of the run to repeat")

        retry_req = _ws().build_retry_request(source_job_id, req)
        if retry_req is None:
            with self.lock:
                source_item = next(
                    (
                        item for item in self.items.values()
                        if item.state in QUEUE_TERMINAL_STATES
                        and source_job_id in {
                            candidate
                            for candidate in (
                                str(item.worker_job_id or ""),
                                str(item.source_job_id or ""),
                                str(item.request_snapshot.get("job_id") or ""),
                            )
                            # Empty ids are not identities. Kept out of the set so a blank never
                            # matches an item that simply has not been assigned one yet.
                            if candidate
                        }
                    ),
                    None,
                )
                if source_item is not None:
                    retry_req = _ws().clone_request_snapshot(source_item.request_snapshot)
                    retry_req["job_id"] = str(req.get("job_id") or f"job_{uuid.uuid4().hex[:12]}")
                    retry_req["retry_of"] = source_job_id
                    retry_req["retry_count"] = int(source_item.retry_count or 0) + 1
                    original_output = str(
                        retry_req.get("original_output") or retry_req.get("output") or ""
                    ).strip()
                    original_metadata_output = str(
                        retry_req.get("original_metadata_output")
                        or retry_req.get("metadata_output")
                        or ""
                    ).strip()
                    if original_output:
                        retry_output, retry_metadata = _ws().safe_unique_output_paths(
                            original_output,
                            retry_count=int(retry_req["retry_count"]),
                            original_metadata_output=original_metadata_output or None,
                        )
                        retry_req["output"] = retry_output
                        retry_req["metadata_output"] = retry_metadata
                        retry_req["original_output"] = original_output
                        retry_req["original_metadata_output"] = original_metadata_output
            if retry_req is None:
                raise ValueError("retry source job not found")
        retry_req["task_command"] = retry_req.get("command")
        retry_req["command"] = "enqueue"
        return self.enqueue(retry_req)

