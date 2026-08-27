"""TCP JSON handler for the SpellVision worker.

Extracted from worker_service.py. The handler is a thin command switch;
generation work stays in worker_service / adapters.
"""
from __future__ import annotations

import json
import socketserver
import traceback
import uuid
from typing import Any

from worker_service_state import (
    ActiveJobHandle,
    JobCancelledError,
    JobRecord,
    JobResult,
    JobState,
    cancel_job,
    create_job,
    fail_job,
    register_active_job,
    request_job_cancel,
    set_job_message,
    transition_job,
    unregister_active_job,
    update_job_progress,
)
from dataclasses import asdict
import threading


MAX_REQUEST_BYTES = 8 * 1024 * 1024
WORKER_SERVICE_ID = "spellvision_worker"
WORKER_PROTOCOL_VERSION = 1


def _ws():
    import worker_service as ws
    return ws


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
        runtime_failure = _ws().invalidate_video_runtime_cache_for_failure(job, code, error_text)
        fail_job(job, error_text, code=code, tb=tb, details=runtime_failure)
        self.emit_job_update(job)
        payload: dict[str, Any] = {
            "type": "error",
            "ok": False,
            "job_id": job.job_id,
            "state": job.state.value,
            "error": error_text,
            "error_code": code,
        }
        if runtime_failure:
            payload["runtime_failure"] = runtime_failure
        if tb:
            payload["traceback"] = tb
        self.emit(payload)


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

        retry_req = _ws().build_retry_request(source_job_id, req)
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
            ack = _ws().QUEUE_MANAGER.enqueue(req)
            payload = {**ack, **_ws().QUEUE_MANAGER.snapshot_payload()}
            emitter.emit(payload)
        except Exception as exc:
            emitter.emit({"type": "queue_ack", "ok": False, "action": "enqueue", "error": str(exc)})

    def handle_queue_status_command(self, emitter: EventEmitter) -> None:
        emitter.emit(_ws().QUEUE_MANAGER.queue_status())

    def handle_remove_queue_item_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        queue_item_id = str(req.get("queue_item_id") or "").strip()
        ok, message = _ws().QUEUE_MANAGER.remove_pending(queue_item_id)
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "remove_queue_item", "queue_item_id": queue_item_id, "message": message, **_ws().QUEUE_MANAGER.snapshot_payload()})

    def handle_clear_pending_queue_command(self, emitter: EventEmitter) -> None:
        removed = _ws().QUEUE_MANAGER.clear_pending()
        emitter.emit({"type": "queue_ack", "ok": True, "action": "clear_pending_queue", "removed_count": removed, **_ws().QUEUE_MANAGER.snapshot_payload()})

    def handle_cancel_queue_item_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        queue_item_id = str(req.get("queue_item_id") or "").strip() or None
        ok, message, item = _ws().QUEUE_MANAGER.cancel(queue_item_id)
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "cancel_queue_item", "queue_item_id": item.queue_item_id if item else queue_item_id, "message": message, **_ws().QUEUE_MANAGER.snapshot_payload()})

    def handle_retry_queue_item_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        source_job_id = str(req.get("job_id") or req.get("source_job_id") or "").strip()
        try:
            ack = _ws().QUEUE_MANAGER.retry_from_archive(source_job_id, req)
            emitter.emit({**ack, **_ws().QUEUE_MANAGER.snapshot_payload()})
        except Exception as exc:
            emitter.emit({"type": "queue_ack", "ok": False, "action": "retry_queue_item", "source_job_id": source_job_id, "error": str(exc), **_ws().QUEUE_MANAGER.snapshot_payload()})


    def handle_move_queue_item_up_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        queue_item_id = str(req.get("queue_item_id") or "").strip()
        ok, message = _ws().QUEUE_MANAGER.move_up(queue_item_id)
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "move_queue_item_up", "queue_item_id": queue_item_id, "message": message, **_ws().QUEUE_MANAGER.snapshot_payload()})

    def handle_move_queue_item_down_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        queue_item_id = str(req.get("queue_item_id") or "").strip()
        ok, message = _ws().QUEUE_MANAGER.move_down(queue_item_id)
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "move_queue_item_down", "queue_item_id": queue_item_id, "message": message, **_ws().QUEUE_MANAGER.snapshot_payload()})

    def handle_duplicate_queue_item_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        queue_item_id = str(req.get("queue_item_id") or "").strip()
        ok, message, new_queue_item_id = _ws().QUEUE_MANAGER.duplicate_queue_item(queue_item_id)
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "duplicate_queue_item", "queue_item_id": queue_item_id, "new_queue_item_id": new_queue_item_id, "message": message, **_ws().QUEUE_MANAGER.snapshot_payload()})

    def handle_pause_queue_command(self, emitter: EventEmitter) -> None:
        ok, message = _ws().QUEUE_MANAGER.pause()
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "pause_queue", "message": message, **_ws().QUEUE_MANAGER.snapshot_payload()})

    def handle_resume_queue_command(self, emitter: EventEmitter) -> None:
        ok, message = _ws().QUEUE_MANAGER.resume()
        emitter.emit({"type": "queue_ack", "ok": ok, "action": "resume_queue", "message": message, **_ws().QUEUE_MANAGER.snapshot_payload()})

    def handle_cancel_all_queue_items_command(self, emitter: EventEmitter) -> None:
        removed_count, active_cancel_requested = _ws().QUEUE_MANAGER.cancel_all()
        emitter.emit({"type": "queue_ack", "ok": True, "action": "cancel_all_queue_items", "removed_count": removed_count, "active_cancel_requested": active_cancel_requested, "message": f"Cancelled active={active_cancel_requested} and cleared {removed_count} pending item(s).", **_ws().QUEUE_MANAGER.snapshot_payload()})

    def handle_generate_dataset_command(self, req: dict[str, Any], emitter: EventEmitter) -> None:
        try:
            ack = _ws().QUEUE_MANAGER.enqueue_dataset(req)
            emitter.emit({**ack, **_ws().QUEUE_MANAGER.snapshot_payload()})
        except Exception as exc:
            emitter.emit({"type": "queue_ack", "ok": False, "action": "generate_dataset", "error": str(exc), **_ws().QUEUE_MANAGER.snapshot_payload()})

    def handle(self) -> None:
        ws = _ws()
        emitter = EventEmitter(self)
        raw_line = self.rfile.readline(MAX_REQUEST_BYTES + 2)
        if not raw_line:
            return

        try:
            if len(raw_line) > MAX_REQUEST_BYTES:
                raise ValueError(
                    f"request exceeds the {MAX_REQUEST_BYTES}-byte protocol limit"
                )
            line = raw_line.decode("utf-8").strip()
            if not line:
                return
            req = json.loads(line)
            if not isinstance(req, dict):
                raise TypeError("request JSON must be an object")
        except Exception as exc:
            # Protocol errors occur after a connection has started handling a request.
            # STARTING -> FAILED is valid; QUEUED -> FAILED is intentionally not.
            fallback_job = JobRecord(
                job_id=f"job_{uuid.uuid4().hex[:12]}",
                command="unknown",
                state=JobState.STARTING,
            )
            emitter.error(fallback_job, str(exc), code="invalid_request")
            return

        # Fail LOUDLY on encoding-corrupted prompt text (lone UTF-16 surrogates) before it can reach
        # the umt5 SentencePiece tokenizer ("TypeError: not a string") or silently mangle a render.
        # Control commands have no prompt fields, so they pass through untouched.
        prompt_encoding_error = ws.first_unencodable_prompt_field(req)
        if prompt_encoding_error:
            fallback_job = JobRecord(
                job_id=f"job_{uuid.uuid4().hex[:12]}",
                command=str(req.get("command") or req.get("action") or "unknown"),
                state=JobState.STARTING,
            )
            emitter.error(fallback_job, prompt_encoding_error, code="prompt_encoding_corruption")
            return

        command = ws.canonical_command(req)  # C3: plain dispatch reads route through the single accessor
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
        if command in {"video_history_status", "history_video_status"}:
            emitter.emit(ws.video_history_snapshot(ws._safe_int(req.get("limit"), 25)))
            return
        if command in {"video_family_contracts", "video_family_status"}:
            emitter.emit(_ws().video_family_contracts_snapshot())
            return
        if command in {"credential_status", "secrets_status"}:
            from credential_store import credential_status
            emitter.emit(credential_status())
            return
        if command in {"family_install_plan", "guided_install_plan"}:
            from family_install_plan import build_family_install_plan
            present = req.get("present_basenames") or req.get("present") or []
            if not isinstance(present, list):
                present = []
            emitter.emit(build_family_install_plan(
                str(req.get("family") or req.get("video_family") or ""),
                task=str(req.get("task") or req.get("command") or "t2v"),
                present_basenames=[str(item) for item in present],
            ))
            return
        if command in {"apply_family_install_plan", "apply_guided_install_plan"}:
            from family_install_plan import apply_family_install_plan, build_family_install_plan
            present = req.get("present_basenames") or req.get("present") or []
            if not isinstance(present, list):
                present = []
            plan = req.get("plan") if isinstance(req.get("plan"), dict) else build_family_install_plan(
                str(req.get("family") or req.get("video_family") or ""),
                task=str(req.get("task") or req.get("command") or "t2v"),
                present_basenames=[str(item) for item in present],
            )
            dry_run = True if req.get("dry_run") is None else bool(req.get("dry_run"))
            only = req.get("only_components") or req.get("components") or []
            if not isinstance(only, list):
                only = [only]
            emitter.emit(apply_family_install_plan(
                plan,
                dry_run=dry_run,
                cache_root=req.get("cache_root"),
                install_root=req.get("install_root") or req.get("models_root"),
                only_components=[str(item) for item in only if str(item).strip()],
            ))
            return
        if command in {"inspect_model_url", "model_import_inspect"}:
            from model_import import inspect_model_url
            emitter.emit(inspect_model_url(str(req.get("url") or req.get("source") or "")))
            return
        if command in {"import_model_url", "model_import_apply"}:
            from model_import import import_model_choices, inspect_model_url
            catalog = req.get("catalog") if isinstance(req.get("catalog"), dict) else inspect_model_url(str(req.get("url") or ""))
            ids = req.get("choice_ids") or req.get("choices") or []
            if not isinstance(ids, list):
                ids = [ids]
            emitter.emit(import_model_choices(
                catalog,
                [str(item) for item in ids],
                install_root=str(req.get("install_root") or req.get("models_root") or ""),
                include_pairs=bool(req.get("include_pairs", True)),
            ))
            return
        if command in {"set_credential", "save_credential"}:
            from credential_store import set_credential
            name = str(req.get("name") or req.get("credential") or "").strip()
            value = str(req.get("value") or req.get("token") or "")
            try:
                emitter.emit(set_credential(name, value))
            except ValueError as exc:
                emitter.emit({"ok": False, "type": "credential_status", "error": str(exc)})
            return
        if command == "clear_credential":
            from credential_store import clear_credential
            name = str(req.get("name") or req.get("credential") or "").strip()
            try:
                emitter.emit(clear_credential(name))
            except ValueError as exc:
                emitter.emit({"ok": False, "type": "credential_status", "error": str(exc)})
            return
        if command in {"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status"}:
            family = ws.normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = ws.video_family_contract(family)
                emitter.emit({
                    "type": "video_family_readiness_status",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_readiness_family",
                    "ready_to_test": False,
                    "message": "Readiness probing is implemented for LTX in Sprint 15C Pass 2.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = ws.handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(_ws().ltx_readiness_snapshot(runtime_status=runtime_status))
            return
        if command in {"ltx_test_workflow_contract", "ltx_workflow_contract", "video_family_test_workflow_contract", "video_family_workflow_contract"}:
            family = ws.normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = ws.video_family_contract(family)
                emitter.emit({
                    "type": "video_family_workflow_contract",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_workflow_contract_family",
                    "ready_to_test": False,
                    "generation_enabled": False,
                    "message": "Test workflow contract selection is implemented for LTX in Sprint 15C Pass 3.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = ws.handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(_ws().ltx_test_workflow_contract_snapshot(runtime_status=runtime_status))
            return
        if command in {"ltx_t2v_smoke_test", "ltx_smoke_test_route", "video_family_smoke_test_route"}:
            family = ws.normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = ws.video_family_contract(family)
                emitter.emit({
                    "type": "video_family_smoke_test_route",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_smoke_test_family",
                    "ready_to_test": False,
                    "generation_enabled": False,
                    "submitted": False,
                    "message": "Gated smoke-test route is implemented for LTX in Sprint 15C Pass 4.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = ws.handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(_ws().ltx_t2v_smoke_test_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"ltx_workflow_materialization_dry_run", "ltx_materialize_workflow", "ltx_t2v_materialize_dry_run", "video_family_materialization_dry_run"}:
            family = ws.normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = ws.video_family_contract(family)
                emitter.emit({
                    "type": "video_family_materialization_dry_run",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_materialization_family",
                    "ready_to_test": False,
                    "generation_enabled": False,
                    "submitted": False,
                    "message": "Workflow materialization dry run is implemented for LTX in Sprint 15C Pass 5.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = ws.handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(_ws().ltx_workflow_materialization_dry_run_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"ltx_workflow_graph_inspection", "ltx_prompt_api_normalization_preview", "video_family_graph_inspection", "video_family_prompt_api_normalization_preview"}:
            family = ws.normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = ws.video_family_contract(family)
                emitter.emit({
                    "type": "video_family_graph_inspection",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_graph_inspection_family",
                    "ready_to_test": False,
                    "generation_enabled": False,
                    "submitted": False,
                    "message": "Workflow graph inspection is implemented for LTX in Sprint 15C Pass 6.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = ws.handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(_ws().ltx_workflow_graph_inspection_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"ltx_prompt_api_conversion_adapter", "ltx_prompt_api_export_adapter", "ltx_prompt_api_conversion_preview", "video_family_prompt_api_conversion_adapter"}:
            family = ws.normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = ws.video_family_contract(family)
                emitter.emit({
                    "type": "video_family_prompt_api_conversion_adapter",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_prompt_api_adapter_family",
                    "ready_to_test": False,
                    "generation_enabled": False,
                    "submitted": False,
                    "message": "Prompt API conversion adapter is implemented for LTX in Sprint 15C Pass 7.",
                })
                return
            runtime_status = {}
            try:
                runtime_status = ws.handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(_ws().ltx_prompt_api_conversion_adapter_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"ltx_requeue_draft_gated_submission", "ltx_execute_requeue_draft", "video_family_ltx_requeue_gated_submission"}:
            runtime_status = ws.handle_comfy_runtime_status_command({})
            emitter.emit(_ws().ltx_requeue_draft_gated_submission_snapshot(req, runtime_status=runtime_status))
            return

        if command in {"ltx_prompt_api_gated_submission", "ltx_prompt_api_submit", "ltx_submit_prompt_api", "ltx_prompt_api_submit_and_capture", "ltx_prompt_api_submit_wait", "video_family_prompt_api_gated_submission"}:
            family = ws.normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = ws.video_family_contract(family)
                emitter.emit({
                    "type": "video_family_prompt_api_gated_submission",
                    "ok": False,
                    "family": family,
                    "display_name": contract.display_name,
                    "validation_status": contract.validation_status,
                    "readiness": "unsupported_prompt_api_submission_family",
                })
                return
            runtime_status = {}
            try:
                runtime_status = ws.handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(_ws().ltx_prompt_api_gated_submission_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"ltx_ui_queue_history_contract", "ltx_ui_registry_snapshot", "ltx_ui_results_contract", "video_family_ltx_ui_contract"}:
            runtime_status = {}
            try:
                runtime_status = ws.handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(_ws().ltx_ui_queue_history_snapshot(
                runtime_status=runtime_status,
                limit=int(req.get("limit") or 20),
                include_queue=bool(req.get("include_queue", True)),
                include_history=bool(req.get("include_history", True)),
            ))
            return
        if command in {"ltx_registry_history", "ltx_history_registry", "ltx_recent_history", "video_family_ltx_history_registry"}:
            runtime_status = {}
            try:
                runtime_status = ws.handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(_ws().read_recent_ltx_history(runtime_status=runtime_status, limit=int(req.get("limit") or 20)))
            return
        if command in {"ltx_registry_queue", "ltx_queue_registry", "ltx_recent_queue", "video_family_ltx_queue_registry"}:
            runtime_status = {}
            try:
                runtime_status = ws.handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(_ws().read_recent_ltx_queue_events(runtime_status=runtime_status, limit=int(req.get("limit") or 20)))
            return
        if command in {"runtime_memory_status", "runtime_diagnostics", "unload_image_runtime", "unload_video_runtime", "unload_all_runtimes", "clear_cuda_cache"}:
            emitter.emit(_ws().handle_runtime_memory_control_command(req))
            return
        if command == "classify_models":
            emitter.emit(ws.handle_classify_models_command(req))
            return
        if command == "resolve_component_stack":
            emitter.emit(_ws().handle_resolve_component_stack_command(req))
            return

        if command == "import_workflow":
            emitter.emit(_ws().handle_import_workflow_command(req))
            return
        if command == "list_workflow_profiles":
            emitter.emit(ws.handle_list_workflow_profiles_command(req))
            return
        if command == "discover_comfy_workflows":
            emitter.emit(_ws().handle_discover_comfy_workflows_command(req))
            return
        if command == "check_workflow_launch_readiness":
            emitter.emit(_ws().handle_check_workflow_launch_readiness_command(req))
            return
        if command == "retry_workflow_dependencies":
            emitter.emit(_ws().handle_retry_workflow_dependencies_command(req))
            return
        if command == "compile_workflow_prompt":
            emitter.emit(_ws().handle_compile_workflow_prompt_command(req))
            return
        if command == "build_node_class_index":
            emitter.emit(_ws().handle_build_node_class_index_command(req))
            return
        if command == "delete_workflow_profile":
            emitter.emit(_ws().handle_delete_workflow_profile_command(req))
            return
        if command == "comfy_runtime_status":
            emitter.emit(ws.handle_comfy_runtime_status_command(req))
            return
        if command == "ensure_comfy_runtime":
            emitter.emit(ws.handle_ensure_comfy_runtime_command(req))
            return
        if command == "start_comfy_runtime":
            emitter.emit(ws.handle_start_comfy_runtime_command(req))
            return
        if command == "stop_comfy_runtime":
            emitter.emit(ws.handle_stop_comfy_runtime_command(req))
            return
        if command == "restart_comfy_runtime":
            emitter.emit(ws.handle_restart_comfy_runtime_command(req))
            return
        if command == "comfy_manager_status":
            emitter.emit(ws.handle_comfy_manager_status_command(req))
            return
        if command == "install_comfy_manager":
            emitter.emit(ws.handle_install_comfy_manager_command(req))
            return
        if command == "install_custom_node":
            emitter.emit(_ws().handle_install_custom_node_command(req))
            return
        if command == "install_recommended_video_nodes":
            emitter.emit(ws.handle_install_recommended_video_nodes_command(req))
            return
        if command == "prepare_model_swap":
            emitter.emit(ws.handle_prepare_model_swap_command(req))
            return
        if command == "retry" or command == "retry_job":
            retry_req = self.handle_retry_command(req, emitter)
            if retry_req is None:
                return
            req = retry_req
            command = ws.canonical_command(req)  # C3: re-read after retry rebuilds req, through the same accessor

        job = create_job(req)
        emitter.emit_job_update(job)

        if command == "ping":
            transition_job(job, JobState.COMPLETED)
            job.result = JobResult(task_type="ping")
            emitter.emit_job_update(job)
            emitter.emit({
                "type": "result",
                "ok": True,
                "pong": True,
                "service": WORKER_SERVICE_ID,
                "protocol_version": WORKER_PROTOCOL_VERSION,
                "job_id": job.job_id,
                "state": job.state.value,
            })
            return

        # COUPLING (C1): this allow-set must stay a subset of {"noop_slow"} u _ws().dispatch_generation's
        # handled commands. Anything admitted here that is NOT "noop_slow" falls through to
        # _ws().dispatch_generation below; if _ws().dispatch_generation doesn't handle it, it raises
        # "Unsupported generation command". Add a command here only after wiring it into _ws().dispatch_generation.
        if command not in {
            "t2i",
            "i2i",
            "t2v",
            "i2v",
            "comfy_workflow",
            "noop_slow",
            "i23d",
            "t23d",
            "gen3d",
            "clothes_only",
            "garment_shrinkwrap",
            "krea2_regional_inpaint",
            "look_complete",
        }:
            emitter.error(job, f"Unknown command: {command}", code="unknown_command")
            return

        active_job = ActiveJobHandle(job=job)
        if not register_active_job(active_job):
            transition_job(job, JobState.STARTING)
            emitter.error(
                job,
                f"An active job already owns job_id '{job.job_id}'.",
                code="duplicate_job_id",
            )
            _ws().archive_job(job, req)
            return

        try:
            if command == "noop_slow":
                _ws().run_noop_slow(req, emitter, job, active_job)
            else:
                _ws().dispatch_generation(command, req, emitter, job, active_job)  # C1: single generation dispatcher (adds the native-image fork the TCP path lacked)
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


class ThreadedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

