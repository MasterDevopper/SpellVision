"""Background model downloads, on their own lane, with real byte-level progress.

Two requirements shaped this, both from the owner:

  1. **Real streamed progress**, reusing the progress bar the queue already drives.
  2. **The download must not interrupt the rest of the app being used.**

Requirement 2 is why this is not a queue command. ``QueueManager._start_next_locked`` returns
immediately when ``active_queue_item_id is not None`` -- the generation queue is strictly serial
by design, so a 6 GB checkpoint fetch enqueued there would block every render until it finished.
Downloads get their own lane, their own threads, and their own lock, and never touch the queue's.

Requirement 1 is nearly free: ``model_sources._download_remote_asset`` already reads in 1 MB
chunks with full byte accounting for its size and disk-headroom guards. It simply never told
anyone. It now takes a ``progress_cb``, and this module turns those callbacks into the same
``{current, total, percent, message}`` shape a queue item exposes, so the existing bar renders a
download with no new widget.

## Shape of the contract

The UI polls ``snapshot()`` on the status poll it already runs. Nothing here holds a socket open,
so a client can disconnect, reconnect, and still see a download that has been running the whole
time -- which is the difference between a progress bar and a progress bar you can walk away from.

## What is deliberately not here

No resume. A partial transfer is discarded and restarted, because the existing download path
writes to a ``.part`` temp file and validates the final size against both Content-Length and the
provider's declared size. Range-resume would have to re-establish those guarantees against a
partial file, and getting that subtly wrong produces a corrupt checkpoint that loads and renders
garbage -- the exact failure class this codebase keeps getting bitten by. Restarting is slower and
honest.
"""
from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from model_sources import DownloadCancelled, materialize_asset

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"

TERMINAL_STATES = frozenset({COMPLETED, FAILED, CANCELLED})

# Two at a time. One serialises a batch behind whichever file is largest; unbounded saturates the
# link and the disk, and makes every individual bar crawl, which reads as a hang even though the
# aggregate is fine.
DEFAULT_MAX_CONCURRENT = 2

# Terminal records are kept so the UI can show "done" after the fact, but not forever.
COMPLETED_RETENTION_SEC = 30 * 60


def _human_bytes(n: Optional[int]) -> str:
    if n is None:
        return "unknown size"
    step = 1024.0
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < step or unit == "TB":
            return f"{value:.0f} {unit}" if unit in ("B", "KB") else f"{value:.1f} {unit}"
        value /= step
    return f"{value:.1f} TB"


@dataclass
class DownloadProgress:
    """Mirrors worker_service_state.JobProgress so the existing progress bar needs no changes."""

    current: int = 0
    total: int = 0
    percent: float = 0.0
    message: str = "waiting"


@dataclass
class DownloadRecord:
    download_id: str
    reference: str
    label: str
    asset_type: str = "model"
    state: str = QUEUED
    progress: DownloadProgress = field(default_factory=DownloadProgress)
    local_path: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    bytes_per_sec: float = 0.0
    eta_sec: Optional[float] = None
    cache_hit: bool = False
    created_at: float = 0.0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    # Context for the caller that requested it -- e.g. which workflow needed this checkpoint.
    context: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "download_id": self.download_id,
            "reference": self.reference,
            "label": self.label,
            "asset_type": self.asset_type,
            "state": self.state,
            "progress": {
                "current": self.progress.current,
                "total": self.progress.total,
                "percent": round(self.progress.percent, 2),
                "message": self.progress.message,
            },
            "local_path": self.local_path,
            "error": self.error,
            "error_code": self.error_code,
            "bytes_per_sec": round(self.bytes_per_sec, 1),
            "eta_sec": round(self.eta_sec, 1) if self.eta_sec is not None else None,
            "cache_hit": self.cache_hit,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "context": dict(self.context),
        }


class DownloadManager:
    """Owns the download lane. Thread-safe; every public method takes ``self.lock`` briefly."""

    def __init__(
        self,
        *,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        materializer: Callable[..., Any] = materialize_asset,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.lock = threading.RLock()
        self.records: dict[str, DownloadRecord] = {}
        self.order: list[str] = []
        self.pending: list[str] = []
        self.active: set[str] = set()
        self.max_concurrent = max(1, int(max_concurrent))
        self._materializer = materializer
        self._clock = clock
        self._cancel_flags: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._extra_kwargs: dict[str, dict[str, Any]] = {}
        self._shutdown = threading.Event()

    # --- public API ----------------------------------------------------------------------

    def start(
        self,
        reference: str,
        *,
        label: str | None = None,
        asset_type: str = "model",
        context: dict[str, Any] | None = None,
        **materialize_kwargs: Any,
    ) -> DownloadRecord:
        """Enqueue a download. Returns immediately -- the transfer runs on the lane."""
        ref = str(reference or "").strip()
        if not ref:
            raise ValueError("download requires a non-empty reference")

        with self.lock:
            existing = self._find_live_locked(ref)
            if existing is not None:
                # Asking twice for the same file is a double-click, not a second download.
                return existing

            download_id = f"dl_{uuid.uuid4().hex[:12]}"
            record = DownloadRecord(
                download_id=download_id,
                reference=ref,
                label=str(label or _label_from_reference(ref)),
                asset_type=str(asset_type or "model"),
                created_at=self._clock(),
                context=dict(context or {}),
            )
            record.progress.message = "queued"
            self.records[download_id] = record
            self.order.append(download_id)
            self.pending.append(download_id)
            self._cancel_flags[download_id] = threading.Event()
            self._extra_kwargs[download_id] = dict(materialize_kwargs)
            self._pump_locked()
            return record

    def cancel(self, download_id: str) -> bool:
        """Request cancellation. A running transfer stops within one chunk read."""
        with self.lock:
            record = self.records.get(str(download_id or ""))
            if record is None or record.state in TERMINAL_STATES:
                return False
            flag = self._cancel_flags.get(record.download_id)
            if flag is not None:
                flag.set()
            if record.state == QUEUED:
                # Never started, so no thread will ever observe the flag. Finish it here.
                if record.download_id in self.pending:
                    self.pending.remove(record.download_id)
                self._finish_locked(record, CANCELLED, message="cancelled before it started")
            else:
                record.progress.message = "cancelling..."
            return True

    def snapshot(self) -> dict[str, Any]:
        """What the UI polls. Includes an aggregate so a single bar can represent the lane."""
        with self.lock:
            self._evict_stale_locked()
            items = [self.records[i].payload() for i in self.order if i in self.records]
            live = [r for r in (self.records.get(i) for i in self.order) if r and r.state not in TERMINAL_STATES]
            total_bytes = sum(r.progress.total for r in live)
            done_bytes = sum(r.progress.current for r in live)
            aggregate_percent = (done_bytes / total_bytes * 100.0) if total_bytes else 0.0
            return {
                "type": "download_status",
                "ok": True,
                "items": items,
                "active": len(self.active),
                "pending": len(self.pending),
                "max_concurrent": self.max_concurrent,
                # An aggregate bar for the shell: one number for "downloads are happening".
                "aggregate": {
                    "current": done_bytes,
                    "total": total_bytes,
                    "percent": round(aggregate_percent, 2),
                    "message": _aggregate_message(live),
                },
            }

    def get(self, download_id: str) -> Optional[DownloadRecord]:
        with self.lock:
            return self.records.get(str(download_id or ""))

    def shutdown(self, timeout: float = 5.0) -> None:
        """Cancel everything and let the threads unwind. Safe to call twice."""
        self._shutdown.set()
        with self.lock:
            for flag in self._cancel_flags.values():
                flag.set()
            threads = list(self._threads.values())
        for thread in threads:
            thread.join(timeout=timeout)

    # --- internals -----------------------------------------------------------------------

    def _find_live_locked(self, reference: str) -> Optional[DownloadRecord]:
        for download_id in self.order:
            record = self.records.get(download_id)
            if record and record.reference == reference and record.state not in TERMINAL_STATES:
                return record
        return None

    def _pump_locked(self) -> None:
        while self.pending and len(self.active) < self.max_concurrent and not self._shutdown.is_set():
            download_id = self.pending.pop(0)
            record = self.records.get(download_id)
            if record is None or record.state != QUEUED:
                continue
            record.state = RUNNING
            record.started_at = self._clock()
            record.progress.message = "starting"
            self.active.add(download_id)
            thread = threading.Thread(
                target=self._run, args=(download_id,), name=f"download-{download_id}", daemon=True
            )
            self._threads[download_id] = thread
            thread.start()

    def _run(self, download_id: str) -> None:
        with self.lock:
            record = self.records.get(download_id)
            kwargs = dict(self._extra_kwargs.get(download_id) or {})
            cancel_flag = self._cancel_flags.get(download_id)
        if record is None or cancel_flag is None:
            return

        started = self._clock()

        def on_progress(done: int, total: Optional[int]) -> None:
            with self.lock:
                record.progress.current = int(done)
                record.progress.total = int(total or 0)
                record.progress.percent = (done / total * 100.0) if total else 0.0
                elapsed = max(1e-6, self._clock() - started)
                record.bytes_per_sec = done / elapsed
                if total and record.bytes_per_sec > 0:
                    record.eta_sec = max(0.0, (total - done) / record.bytes_per_sec)
                else:
                    record.eta_sec = None
                record.progress.message = (
                    f"{record.label} - {_human_bytes(done)} / {_human_bytes(total)}"
                    if total else f"{record.label} - {_human_bytes(done)} downloaded"
                )

        try:
            result = self._materializer(
                record.reference,
                asset_type=record.asset_type,
                progress_cb=on_progress,
                cancel_cb=cancel_flag.is_set,
                **kwargs,
            )
        except DownloadCancelled:
            with self.lock:
                self._finish_locked(record, CANCELLED, message="cancelled")
            return
        except Exception as exc:  # noqa: BLE001 -- surfaced to the user, not swallowed
            with self.lock:
                # A cancel that surfaces as some other exception (a socket torn down mid-read)
                # is still a cancel. Reporting it as a failure would put a red error in front of
                # a user who pressed Cancel themselves.
                if cancel_flag.is_set():
                    self._finish_locked(record, CANCELLED, message="cancelled")
                else:
                    record.error = str(exc) or exc.__class__.__name__
                    record.error_code = exc.__class__.__name__
                    record.progress.message = f"failed: {record.error}"
                    self._finish_locked(record, FAILED, message=record.progress.message)
                    _log_failure(record, exc)
            return

        with self.lock:
            local_path = getattr(result, "local_path", None) or getattr(result, "value", None)
            record.local_path = str(local_path) if local_path else None
            metadata = getattr(result, "metadata", None) or {}
            record.cache_hit = bool(metadata.get("cache_hit"))
            if record.cache_hit:
                size = _safe_size(record.local_path)
                record.progress.current = size
                record.progress.total = size
            record.progress.percent = 100.0
            self._finish_locked(
                record, COMPLETED,
                message="already downloaded" if record.cache_hit else f"{record.label} - done",
            )

    def _finish_locked(self, record: DownloadRecord, state: str, *, message: str) -> None:
        record.state = state
        record.finished_at = self._clock()
        record.progress.message = message
        record.eta_sec = None
        self.active.discard(record.download_id)
        self._threads.pop(record.download_id, None)
        self._pump_locked()

    def _evict_stale_locked(self) -> None:
        now = self._clock()
        for download_id in list(self.order):
            record = self.records.get(download_id)
            if record is None:
                self.order.remove(download_id)
                continue
            if (
                record.state in TERMINAL_STATES
                and record.finished_at is not None
                and now - record.finished_at > COMPLETED_RETENTION_SEC
            ):
                self.order.remove(download_id)
                self.records.pop(download_id, None)
                self._cancel_flags.pop(download_id, None)
                self._extra_kwargs.pop(download_id, None)


def _aggregate_message(live: list[DownloadRecord]) -> str:
    if not live:
        return "no downloads"
    if len(live) == 1:
        return live[0].progress.message
    return f"{len(live)} downloads in progress"


def _label_from_reference(reference: str) -> str:
    text = str(reference or "").strip()
    for sep in ("?", "#"):
        if sep in text:
            text = text.split(sep, 1)[0]
    tail = text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return tail or text


def _safe_size(path: Optional[str]) -> int:
    try:
        return os.path.getsize(path) if path else 0
    except OSError:
        return 0


def _log_failure(record: DownloadRecord, exc: BaseException) -> None:
    # logging.info is invisible in this process -- the root logger sits at WARNING.
    import logging

    logging.getLogger(__name__).warning(
        "download %s (%s) failed: %s\n%s",
        record.download_id, record.reference, exc,
        "".join(traceback.format_exception_only(type(exc), exc)).strip(),
    )


_MANAGER: Optional[DownloadManager] = None
_MANAGER_LOCK = threading.Lock()


def get_download_manager() -> DownloadManager:
    """Process-wide lane. Created lazily so importing this module starts no threads."""
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            _MANAGER = DownloadManager()
        return _MANAGER
