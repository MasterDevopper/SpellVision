from __future__ import annotations

import copy
import gc
from collections import deque
import hashlib
import inspect
import json
import logging
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
from typing import Any, Callable, Protocol
from queue import Queue
from pathlib import Path
import uuid

from comfy_bootstrap import bootstrap_comfy_runtime, default_comfy_python
from comfy_runtime_manager import ComfyRuntimeManager
from memory_optimization import auto_select_memory_profile, build_paired_pipelines
from model_classification import classify_model, detect_image_pipeline_type
from family_operating_points import (
    family_operating_points_payload,
    operating_point_params,
    resolve_family_defaults,
    resolve_operating_point,
)
from model_registry import MODEL_FAMILIES
from video_family_contracts import (
    infer_video_family_from_text,
    normalize_video_family_id,
    video_family_contract,
    video_family_contracts_snapshot,
    video_family_pipeline_candidates,
)
from video_family_readiness import ltx_readiness_snapshot
from ltx_workflow_contract import ltx_test_workflow_contract_snapshot
from ltx_smoke_test_route import ltx_t2v_smoke_test_snapshot
from ltx_workflow_materialization import ltx_workflow_materialization_dry_run_snapshot
from ltx_workflow_graph_inspection import ltx_workflow_graph_inspection_snapshot
from ltx_prompt_api_adapter import ltx_prompt_api_conversion_adapter_snapshot
from ltx_requeue_draft_submission import ltx_requeue_draft_gated_submission_snapshot
from ltx_prompt_api_submission import ltx_prompt_api_gated_submission_snapshot
from ltx_queue_history_registry import read_recent_ltx_history, read_recent_ltx_queue_events
from ltx_ui_queue_history_contract import ltx_ui_queue_history_snapshot
from comfy_graph_converter import convert_ui_graph_to_api_prompt, is_ui_graph

from worker_service_state import (
    ACTIVE_JOBS,
    ACTIVE_JOBS_LOCK,
    ActiveJobHandle,
    JobCancelledError,
    JobEmitter,
    JobError,
    JobProgress,
    JobRecord,
    JobResult,
    JobState,
    JobTimestamps,
    QUEUE_TERMINAL_STATES,
    QueueItemState,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    cancel_job,
    complete_job,
    create_job,
    fail_job,
    get_active_job,
    queue_state_from_job_state,
    raise_if_cancelled,
    register_active_job,
    request_job_cancel,
    set_job_message,
    transition_job,
    unregister_active_job,
    update_job_progress,
    utc_now_iso,
)
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
    "lora_adapters": {},
}
CACHE_LOCK = threading.Lock()

JOB_ARCHIVE: dict[str, dict[str, Any]] = {}
JOB_ARCHIVE_ORDER: list[str] = []
JOB_ARCHIVE_LOCK = threading.Lock()
MAX_ARCHIVED_JOBS = 200
VIDEO_HISTORY_LOCK = threading.Lock()
VIDEO_HISTORY_MAX_ITEMS = 250
VIDEO_HISTORY_DIR = Path(__file__).resolve().parent.parent / "runtime" / "history"
VIDEO_HISTORY_INDEX_PATH = VIDEO_HISTORY_DIR / "video_history_index.json"
VIDEO_HISTORY_JSONL_PATH = VIDEO_HISTORY_DIR / "video_history.jsonl"

VIDEO_RUNTIME_LOCK = threading.Lock()
VIDEO_RUNTIME_CACHE: dict[str, Any] = {
    "active_command": None,
    "active_signature": None,
    "active_summary": None,
    "active_family": None,
    "active_stack_kind": None,
    "active_backend_type": None,
    "active_backend_name": None,
    "updated_at": None,
    "reset_reason": None,
    "last_success_at": None,
    "last_prompt_id": None,
    "last_output": None,
    "last_error": None,
    "last_failure_code": None,
    "invalidated_at": None,
    "invalidation_reason": None,
    "comfy_runtime_endpoint": None,
    "comfy_runtime_pid": None,
    "comfy_runtime_detected_pid": None,
    "comfy_runtime_started_at": None,
    "comfy_runtime_state": None,
    "comfy_runtime_ownership": None,
    "comfy_runtime_running": False,
    "comfy_runtime_healthy": False,
    "comfy_runtime_endpoint_alive": False,
    "comfy_runtime_checked_at": None,
}

COMFY_RUNTIME_MANAGER: ComfyRuntimeManager | None = None
COMFY_RUNTIME_MANAGER_LOCK = threading.Lock()






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



LTX_PROMPT_API_DISPATCH_COMMANDS = {
    "ltx_prompt_api_gated_submission",
    "ltx_prompt_api_submit",
    "ltx_submit_prompt_api",
    "ltx_prompt_api_submit_and_capture",
    "ltx_prompt_api_submit_wait",
    "video_family_prompt_api_gated_submission",
}


# _looks_like_ltx_prompt_api_request was removed in the native-LTX migration (Step 4).
# Its only caller -- the run_native_video redirect -- is gone, so LTX requests now flow
# to the native gate. Explicit prompt-api dispatch is matched by exact command name via
# LTX_PROMPT_API_DISPATCH_COMMANDS, never by a broad substring predicate (which also
# matched Wan, given the unconditional LTX field injection from the UI).


def _normalize_ltx_prompt_api_request(req: dict[str, Any]) -> dict[str, Any]:
    ltx_req = copy.deepcopy(req)
    ltx_req["command"] = "ltx_prompt_api_gated_submission"
    ltx_req["worker_command"] = "ltx_prompt_api_gated_submission"
    ltx_req["execution_command"] = "ltx_prompt_api_gated_submission"
    ltx_req["dispatch_command"] = "ltx_prompt_api_gated_submission"
    ltx_req["task_command"] = "ltx_prompt_api_gated_submission"
    ltx_req["workflow_task_command"] = "ltx_prompt_api_gated_submission"

    ltx_req["queue_display_command"] = ltx_req.get("queue_display_command") or ltx_req.get("mode") or "t2v"
    ltx_req["source_generation_mode"] = ltx_req.get("source_generation_mode") or ltx_req["queue_display_command"]
    ltx_req["generation_mode"] = ltx_req.get("generation_mode") or ltx_req["queue_display_command"]
    ltx_req["mode"] = ltx_req.get("mode") or ltx_req["queue_display_command"]

    ltx_req["family"] = "ltx"
    ltx_req["model_family"] = "ltx"
    ltx_req["video_family"] = "ltx"
    ltx_req["resolved_native_video_family"] = "ltx"
    ltx_req["backend"] = "comfy_prompt_api"
    ltx_req["video_backend_route"] = "prompt_api"
    ltx_req["video_backend_type"] = "comfy_prompt_api"
    ltx_req["video_backend_name"] = "LTX Prompt API"
    ltx_req["video_uses_prompt_api_backend"] = True
    ltx_req["video_validated_prompt_api_family"] = True
    ltx_req["video_validated_backend"] = True
    ltx_req["video_readiness_ok"] = True

    # Sprint 15C Pass 29L:
    # Qt may queue an LTX request without carrying the Prompt API export path.
    # The LTX backend is Prompt-API-template based, so preserve any explicit
    # path and otherwise fall back to the standard exported LTX API graph.
    ltx_prompt_api_export_path = str(
        ltx_req.get("prompt_api_export_path")
        or ltx_req.get("ltx_prompt_api_export_path")
        or ltx_req.get("api_workflow_path")
        or ltx_req.get("workflow_prompt_api_path")
        or os.environ.get(
            "SPELLVISION_LTX_PROMPT_API_EXPORT",
            r"D:\AI_ASSETS\comfy_runtime\ComfyUI\user\default\workflows\ltx_api.json",
        )
        or ""
    ).strip()
    if ltx_prompt_api_export_path:
        ltx_req["prompt_api_export_path"] = ltx_prompt_api_export_path
        ltx_req["ltx_prompt_api_export_path"] = ltx_prompt_api_export_path
        ltx_req["api_workflow_path"] = ltx_prompt_api_export_path
        ltx_req["workflow_prompt_api_path"] = ltx_prompt_api_export_path
    ltx_req["submit_to_comfy"] = True
    ltx_req["dry_run"] = False
    ltx_req["wait_for_result"] = True
    ltx_req["capture_metadata"] = True
    ltx_req["register_result"] = True
    ltx_req["request_register_result"] = True
    ltx_req["status"] = "submitting LTX Prompt API graph"
    ltx_req["status_text"] = "submitting LTX Prompt API graph"

    return ltx_req



def _queue_ltx_execution_command(req: dict[str, Any], fallback: str = "") -> str:
    """Return the execution command for queued jobs without losing display mode."""
    ltx_command = "ltx_prompt_api_gated_submission"

    for key in ("worker_command", "execution_command", "dispatch_command", "command", "task_command", "workflow_task_command"):
        command = str(req.get(key) or "").strip().lower()
        if command == ltx_command:
            return ltx_command

    if "LTX_PROMPT_API_DISPATCH_COMMANDS" in globals():
        for key in ("worker_command", "execution_command", "dispatch_command", "command", "task_command", "workflow_task_command"):
            command = str(req.get(key) or "").strip().lower()
            if command in LTX_PROMPT_API_DISPATCH_COMMANDS:
                return ltx_command

    # Native-LTX migration (Step 4): the old broad "ltx-in-haystack" auto-promotion
    # was removed. A fresh t2v/i2v LTX request now flows to the native path + gate
    # (run_native_video -> _infer_native_video_family -> gate), exactly like Wan.
    # Only an EXPLICIT ltx_prompt_api_* command (history requeue / fallback) routes
    # to the prompt-api engine. Family decisions live in resolved_native_video_family,
    # never a substring haystack (that haystack also matched Wan — the entanglement).
    return str(fallback or "").strip().lower()


def _queue_display_command_for_execution(req: dict[str, Any], execution_command: str, fallback: str = "") -> str:
    display_commands = {"t2i", "i2i", "t2v", "i2v", "comfy_workflow"}

    for key in ("queue_display_command", "source_generation_mode", "generation_mode", "source_command", "task_type", "mode", "video_request_kind"):
        command = str(req.get(key) or "").strip().lower()
        if command in display_commands:
            return command

    fallback = str(fallback or "").strip().lower()
    if fallback in display_commands:
        return fallback

    if execution_command == "ltx_prompt_api_gated_submission":
        return "t2v"

    return execution_command


def canonical_command(req: dict[str, Any]) -> str:
    """Single accessor for the PLAIN dispatch reads (Doc 21 C3, scope narrowed on live inspection).

    Encodes EXACTLY the TCP-direct dispatcher's current read -- ``req["command"]`` else
    ``req["action"]``, ``.strip()`` (NOT lowercased, matching ``WorkerTCPHandler.handle`` today).
    That is the only precedence the plain dispatch reads observe; the six-key aliasing and the LTX
    detection heuristic (``_queue_ltx_execution_command``, an ordered-precedence membership +
    substring-haystack check a key accessor cannot replace) are deliberately NOT folded in here --
    each is its own later pass. The QUEUE dispatcher reads ``item.command`` (a QueueItem field, equal
    to ``req["command"]`` only post-enqueue) and is intentionally NOT routed through this accessor:
    doing so would change behavior when the two differ (pinned by test_dispatch_characterization's
    ``test_queue_reads_item_command_not_req_command``), so it stays as-is and is flagged at the call site.
    """
    return str(req.get("command") or req.get("action") or "").strip()


def first_unencodable_prompt_field(req: dict[str, Any]) -> str | None:
    """Return a LOUD error message if any prompt-bearing field carries text that is not
    UTF-8-encodable (lone UTF-16 surrogates = encoding corruption), else None.

    This is the request-path backstop for the worker_client.py stdin-UTF-8 fix. A mangled CJK
    prompt must FAIL the job with a clear message -- never be silently stripped (a silently-mangled
    negative renders subtly wrong and the user never knows) and never be allowed to reach the umt5
    SentencePiece tokenizer, which dies with the opaque 'TypeError: not a string' mid-render.
    Checked once here, not per-builder.
    """
    def bad(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            value.encode("utf-8")
            return False
        except UnicodeEncodeError:
            return True

    for key in ("prompt", "negative_prompt", "prompt_2", "negative_prompt_2"):
        if bad(req.get(key)):
            return (
                f"The {key.replace('_', ' ')} contains invalid characters (encoding corruption -- "
                "lone UTF-16 surrogates, not valid UTF-8). This is a text-encoding bug, not your "
                "input. Re-enter the prompt; if it persists, report it."
            )
    for value in req.get("prompts") or []:
        if bad(value):
            return (
                "A batch prompt contains invalid characters (encoding corruption -- lone UTF-16 "
                "surrogates, not valid UTF-8). This is a text-encoding bug, not your input."
            )
    return None


def dispatch_generation(command: str, req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> Any:
    """The single generation dispatcher (Doc 21 C1). BOTH entry points route here with an
    ALREADY-RESOLVED command -- the queue passes ``item.command``, the TCP handler passes
    ``canonical_command(req)`` -- it does NOT re-derive the command (the two sources are distinct and
    must stay distinct; pinned by test_dispatch_characterization). Encodes the UNION of the correct forks:
      t2i / i2i        -> _should_route_native_image(req) ? run_native_image : run_t2i / run_i2i
      comfy_workflow   -> run_comfy_workflow
      t2v / i2v        -> request_has_workflow_binding(req) ? run_comfy_workflow : run_native_video
    The t2i/i2i native-image fork is the branch the TCP-direct path historically LACKED -- collapsing
    onto this function fixes that divergence (behavior-fixing for the TCP path, identical for the queue).
    noop_slow (a non-generation test command) and ltx_prompt_api_gated_submission (resolved from
    execution_command) are NOT part of generation dispatch and stay at their call sites.
    """
    if command == "t2i":
        # A workflow launch keeps its display command (t2i) but must run through ComfyUI, not the
        # native diffusers path -- mirror the t2v/i2v workflow-binding fork below. Without this a
        # t2i workflow "Use workflow"/Flows Launch dispatches to run_t2i and dies on KeyError('model').
        if request_has_workflow_binding(req):
            return run_comfy_workflow(req, emitter, job, active_job)
        if _should_route_native_image(req):
            return run_native_image(req, emitter, job, active_job)
        return run_t2i(req, emitter, job, active_job)
    if command == "i2i":
        if request_has_workflow_binding(req):
            return run_comfy_workflow(req, emitter, job, active_job)
        if _should_route_native_image(req):
            return run_native_image(req, emitter, job, active_job)
        return run_i2i(req, emitter, job, active_job)
    if command == "comfy_workflow":
        return run_comfy_workflow(req, emitter, job, active_job)
    if command in {"t2v", "i2v"}:
        if request_has_workflow_binding(req):
            return run_comfy_workflow(req, emitter, job, active_job)
        return run_native_video(req, emitter, job, active_job)
    raise RuntimeError(f"Unsupported generation command: {command!r}")


def _ltx_prompt_api_job_payload(snapshot: dict[str, Any], req: dict[str, Any], job: "JobRecord") -> dict[str, Any]:
    result = snapshot.get("spellvision_result") if isinstance(snapshot.get("spellvision_result"), dict) else {}
    model_stack = result.get("model_stack") if isinstance(result.get("model_stack"), dict) else {}
    if not model_stack and isinstance(snapshot.get("model_stack"), dict):
        model_stack = snapshot.get("model_stack") or {}

    def _preferred_ltx_output_role() -> str:
        raw = str(
            req.get("ltx_preferred_output")
            or req.get("ltx_output_variant")
            or req.get("video_output_variant")
            or req.get("preferred_output_variant")
            or req.get("video_ltx_preferred_output")
            or req.get("preferred_ltx_output")
            or req.get("video_preferred_output")
            or req.get("preferred_output")
            or req.get("ltx_output_preference")
            or req.get("video_output_preference")
            or req.get("ltx_primary_output_role")
            or req.get("primary_output_role")
            or ""
        ).strip().lower()

        normalized = raw.replace("-", "_").replace(" ", "_")

        if normalized in {"distilled", "d", "output_d", "ltx_distilled", "distilled_output"}:
            return "distilled"

        if normalized in {"full", "f", "output_f", "ltx_full", "full_output"}:
            return "full"

        # Sprint 15C Pass 29P v5:
        # Match the visible UI default. The LTX Launch Options panel defaults
        # Preferred output to "distilled", so missing request fields should not
        # silently promote Full.
        return "distilled"

    def _infer_ltx_output_role(item: dict[str, Any]) -> str:
        role = str(item.get("role") or "").strip().lower()
        if role:
            return role

        filename = str(item.get("filename") or item.get("path") or item.get("uri") or "").lower()
        if "output_f" in filename or "_f_" in filename:
            return "full"
        if "output_d" in filename or "_d_" in filename:
            return "distilled"
        return "video"

    def _label_for_role(role: str) -> str:
        if role == "full":
            return "LTX Full"
        if role == "distilled":
            return "LTX Distilled"
        return "LTX Video"

    def _normalize_ltx_output(item: dict[str, Any], index: int) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None

        filename = str(item.get("filename") or "").strip()
        path = str(item.get("path") or item.get("uri") or item.get("preview_path") or "").strip()

        if not path and filename:
            root = str(snapshot.get("output_root") or result.get("output_root") or "").strip()
            subfolder = str(item.get("subfolder") or "").strip()
            if root:
                path_obj = Path(root)
                if subfolder:
                    path_obj = path_obj / subfolder
                path = str(path_obj / filename)

        if not path:
            return None

        if not filename:
            filename = Path(path).name

        role = _infer_ltx_output_role(item)
        metadata_path = str(item.get("metadata_path") or f"{path}.spellvision.json").strip()

        return {
            "id": str(item.get("id") or f"ltx-{snapshot.get('prompt_id') or result.get('prompt_id') or job.job_id}-{index}"),
            "kind": str(item.get("kind") or item.get("media_type") or "video"),
            "role": role,
            "family": "ltx",
            "label": str(item.get("label") or _label_for_role(role)),
            "node_id": str(item.get("node_id") or ""),
            "bucket": str(item.get("bucket") or ""),
            "filename": filename,
            "path": path,
            "uri": path,
            "exists": bool(item.get("exists", Path(path).exists())),
            "size_bytes": int(item.get("size_bytes") or (_file_size_bytes(path) if Path(path).exists() else 0)),
            "animated": bool(item.get("animated", True)),
            "metadata_path": metadata_path,
            "metadata_exists": bool(Path(metadata_path).exists()) if metadata_path else False,
            "preview_path": path,
            "openable": True,
            "requeue_supported": True,
            "send_to_mode": "t2v",
        }

    raw_outputs: list[Any] = []
    for candidate in (
        result.get("outputs"),
        snapshot.get("ui_outputs"),
        snapshot.get("outputs"),
    ):
        if isinstance(candidate, list) and candidate:
            raw_outputs = candidate
            break

    video_outputs: list[dict[str, Any]] = []
    for index, item in enumerate(raw_outputs):
        normalized = _normalize_ltx_output(item, index)
        if normalized:
            video_outputs.append(normalized)

    preferred_role = _preferred_ltx_output_role()

    primary = snapshot.get("primary_output") if isinstance(snapshot.get("primary_output"), dict) else {}
    if not primary and isinstance(result.get("primary_output"), dict):
        primary = result.get("primary_output") or {}

    primary_variant = None
    if video_outputs:
        # Sprint 15C Pass 29P: preferred output controls primary preview/result.
        primary_variant = next((item for item in video_outputs if item.get("role") == preferred_role), None)

        # Fallback: Full remains the default final-quality candidate.
        if primary_variant is None:
            primary_variant = next((item for item in video_outputs if item.get("role") == "full"), None)

        if primary_variant is None and primary:
            primary_path = str(primary.get("path") or primary.get("uri") or "").strip()
            primary_variant = next((item for item in video_outputs if str(item.get("path") or "") == primary_path), None)

        if primary_variant is None:
            primary_variant = video_outputs[0]

    if primary_variant:
        primary = primary_variant

    if not primary and isinstance(snapshot.get("ui_outputs"), list) and snapshot.get("ui_outputs"):
        first = snapshot.get("ui_outputs", [])[0]
        if isinstance(first, dict):
            primary = first

    output_path = str(
        primary.get("path")
        or primary.get("uri")
        or snapshot.get("primary_output_path")
        or result.get("primary_output_path")
        or req.get("output")
        or ""
    ).strip()

    metadata_path = str(
        primary.get("metadata_path")
        or snapshot.get("primary_metadata_path")
        or result.get("primary_metadata_path")
        or req.get("metadata_output")
        or ""
    ).strip()

    prompt_id = str(snapshot.get("prompt_id") or result.get("prompt_id") or "").strip()

    full_output = next((item for item in video_outputs if item.get("role") == "full"), None)
    distilled_output = next((item for item in video_outputs if item.get("role") == "distilled"), None)
    secondary_output = next((item for item in video_outputs if item.get("path") != output_path), None)

    frames = _safe_int(
        req.get("frames")
        or req.get("video_frames")
        or req.get("frame_count")
        or req.get("video_frame_count")
        or model_stack.get("frames"),
        0,
    )
    fps = _safe_int(req.get("fps") or req.get("video_fps") or model_stack.get("fps"), 0)
    width = _safe_int(req.get("width") or req.get("video_width") or model_stack.get("width"), 0)
    height = _safe_int(req.get("height") or req.get("video_height") or model_stack.get("height"), 0)
    duration_seconds = round(float(frames) / float(fps), 3) if frames > 0 and fps > 0 else 0.0

    payload = {
        "ok": bool(snapshot.get("ok", False)),
        "output": output_path,
        "metadata_output": metadata_path,
        "video_output": output_path,
        "output_video": output_path,
        "video_path": output_path,
        "video_metadata_output": metadata_path,
        "backend_name": "LTX Prompt API",
        "detected_pipeline": "ltx_prompt_api_gated_submission",
        "task_type": str(req.get("queue_display_command") or req.get("source_generation_mode") or req.get("mode") or "t2v"),
        "source_job_id": req.get("retry_of"),
        "retry_count": int(req.get("retry_count") or 0),
        "video_backend_type": "comfy_prompt_api",
        "video_backend_name": "LTX Prompt API",
        "video_request_kind": str(req.get("queue_display_command") or req.get("mode") or "t2v"),
        "video_stack_kind": "ltx_prompt_api",
        "video_stack_mode": str(req.get("video_stack_mode") or "single_model"),
        "video_stack_ready": True,
        "video_prompt_id": prompt_id,
        "prompt_id": prompt_id,
        "submission_status": snapshot.get("submission_status"),
        "video_family": "ltx",
        "video_family_display_name": "LTX-Video",
        "video_family_validation_status": "experimental",
        "video_family_validated": False,
        "video_family_production_ready": False,
        "video_family_backend_route": "comfy_prompt_api",
        "video_family_contract_stack_kind": "single_transformer_or_workflow",
        "video_family_required_components": ["model", "vae", "text_encoder"],
        "video_family_optional_components": ["image_encoder", "lora", "scheduler_profile"],
        "video_family_history_label_style": "single_model_stack",
        "video_family_runtime_affinity_fields": ["family", "stack_kind", "model", "vae", "text_encoder", "workflow_or_template", "backend_route"],
        "video_family_readiness_notes": ["LTX Prompt API path completed through Comfy workflow export."],
        "video_family_contract_version": 1,
        "video_model_stack_summary": _video_stack_basename(model_stack.get("model") or req.get("video_primary_model") or req.get("model")),
        "video_primary_model": str(req.get("video_primary_model") or model_stack.get("model") or ""),
        "video_primary_model_name": _video_stack_basename(req.get("video_primary_model") or model_stack.get("model")),
        "video_vae": str(req.get("video_vae") or model_stack.get("video_vae") or model_stack.get("audio_vae") or ""),
        "video_vae_name": _video_stack_basename(req.get("video_vae") or model_stack.get("video_vae") or model_stack.get("audio_vae")),
        "video_text_encoder": str(req.get("video_text_encoder") or model_stack.get("text_encoder") or model_stack.get("text_projection") or ""),
        "video_text_encoder_name": _video_stack_basename(req.get("video_text_encoder") or model_stack.get("text_encoder") or model_stack.get("text_projection")),
        "video_width": width,
        "video_height": height,
        "video_resolution": f"{width}x{height}" if width > 0 and height > 0 else "",
        "video_frames": frames,
        "video_frame_count": frames,
        "video_fps": fps,
        "video_duration_seconds": duration_seconds,
        "video_duration_label": video_duration_label(frames, fps) if frames > 0 and fps > 0 else None,
        "video_has_input_image": bool(req.get("video_has_input_image", False)),
        "video_input_image": req.get("video_input_image") or req.get("input_image"),
        "video_input_name": req.get("video_input_name"),
        "video_completion_summary": "LTX Prompt API video generation complete",
        "video_outputs": video_outputs,
        "video_output_count": len(video_outputs),
        "video_primary_output_role": str(primary.get("role") or ""),
        "video_preferred_output_role": preferred_role,
        "ltx_preferred_output": preferred_role,
        "video_secondary_output": secondary_output.get("path") if secondary_output else None,
        "video_secondary_metadata_output": secondary_output.get("metadata_path") if secondary_output else None,
        "ltx_full_output": full_output.get("path") if full_output else None,
        "ltx_full_metadata_output": full_output.get("metadata_path") if full_output else None,
        "ltx_distilled_output": distilled_output.get("path") if distilled_output else None,
        "ltx_distilled_metadata_output": distilled_output.get("metadata_path") if distilled_output else None,
    }

    try:
        payload.update(output_finalization_contract(
            output_path,
            metadata_path,
            original_output=str(req.get("original_output") or req.get("output") or ""),
            media_type="video",
            metadata_write_status="written" if metadata_path and Path(metadata_path).exists() else "unknown",
        ))
    except Exception as exc:
        payload["output_contract_ok"] = False
        payload["output_contract_warnings"] = ["output_contract_build_failed"]
        payload["metadata_write_error"] = str(exc)

    return payload


def run_ltx_prompt_api_queued_job(req: dict[str, Any], emitter: JobEmitter, job: "JobRecord", active_job: ActiveJobHandle) -> dict[str, Any]:
    ltx_req = _normalize_ltx_prompt_api_request(req)

    transition_job(job, JobState.STARTING)
    emitter.status(job, "submitting LTX Prompt API graph")
    emitter.emit_job_update(job)
    raise_if_cancelled(active_job, emitter, "ltx prompt api submission")

    runtime_status: dict[str, Any] = {}
    try:
        runtime_status = handle_comfy_runtime_status_command({})
    except Exception as exc:
        runtime_status = {"ok": False, "error": str(exc)}

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "running LTX Prompt API submission")
    emitter.emit_job_update(job)

    snapshot = ltx_prompt_api_gated_submission_snapshot(ltx_req, runtime_status=runtime_status)
    emitter.emit(snapshot)

    raise_if_cancelled(active_job, emitter, "ltx prompt api completion")

    ok = bool(snapshot.get("ok", False))
    submitted = bool(snapshot.get("submitted", False))
    completed = bool(snapshot.get("result_completed", False) or snapshot.get("completed", False))

    if not ok or not submitted:
        reasons = snapshot.get("blocked_submit_reasons") or snapshot.get("adapter_blocked_submit_reasons") or []
        submit_error = str(snapshot.get("submit_error") or snapshot.get("error") or "").strip()
        reason_text = ", ".join(str(reason) for reason in reasons) if reasons else ""
        message = submit_error or reason_text or str(snapshot.get("submission_status") or "LTX Prompt API submission failed")
        raise RuntimeError(message)

    payload = _ltx_prompt_api_job_payload(snapshot, ltx_req, job)

    if completed:
        update_job_progress(job, 1, 1, "LTX Prompt API completed")

    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload

def _video_request_command(req: dict[str, Any]) -> str:
    return str(
        req.get("worker_command")
        or req.get("execution_command")
        or req.get("dispatch_command")
        or req.get("command")
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


def _video_stack_basename(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    return os.path.basename(text)


def _video_stack_first(stack: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(stack.get(key) or "").strip()
        if text:
            return text
    return ""


VIDEO_LOW_MODEL_KEYS = (
    "low_model",
    "low_model_path",
    "low_noise_model",
    "low_noise_model_path",
    "low_noise_path",
    "wan_low_noise_path",
    "low_unet_path",
    "low_noise_unet_path",
)

VIDEO_HIGH_MODEL_KEYS = (
    "high_model",
    "high_model_path",
    "high_noise_model",
    "high_noise_model_path",
    "high_noise_path",
    "wan_high_noise_path",
    "high_unet_path",
    "high_noise_unet_path",
)

VIDEO_PRIMARY_MODEL_KEYS = (
    "primary",
    "primary_path",
    "diffusers_path",
    "transformer",
    "transformer_path",
    "unet",
    "unet_path",
    "model",
    "model_path",
)

VIDEO_VAE_KEYS = ("vae", "vae_path", "vae_name")
VIDEO_TEXT_ENCODER_KEYS = ("text_encoder", "text_encoder_path", "clip", "clip_path", "text_encoder_2_path")


def _video_stack_summary_for_details(stack: dict[str, Any]) -> str:
    if not stack:
        return ""

    low = _video_stack_basename(_video_stack_first(stack, *VIDEO_LOW_MODEL_KEYS))
    high = _video_stack_basename(_video_stack_first(stack, *VIDEO_HIGH_MODEL_KEYS))
    primary = _video_stack_basename(_video_stack_first(stack, *VIDEO_PRIMARY_MODEL_KEYS))

    if low and high:
        return f"low={low} • high={high}"
    if high:
        return f"high={high}"
    if low:
        return f"low={low}"
    if primary:
        return primary
    return "configured"


def _video_family_from_request_parts(req: dict[str, Any], stack: dict[str, Any]) -> str:
    explicit = _first_nonempty_text(
        req.get("resolved_native_video_family"),
        req.get("video_family"),
        req.get("model_family"),
        req.get("family"),
        stack.get("video_family"),
        stack.get("model_family"),
        stack.get("family"),
    )
    if explicit:
        return normalize_video_family_id(explicit)

    return infer_video_family_from_text(
        req.get("model"),
        req.get("model_display"),
        req.get("workflow_profile_name"),
        req.get("profile_path"),
        req.get("workflow_profile_path"),
        json.dumps(stack, sort_keys=True) if stack else "",
    )


def _video_family_contract_payload(family: str) -> dict[str, Any]:
    contract = video_family_contract(family)
    # Phase 3a: ship the family's operating points so the UI can render a fast/quality selector
    # GENERICALLY (no family names in the UI). Keyed to the CANONICAL/flagship route per family
    # (dual-noise for Wan, where fast/quality live); route-specific single-point configs stay internal.
    # Empty for a family with no table row (LTX is template-driven; cogvideox/mochi/workflow have none).
    ops = family_operating_points_payload(normalize_video_family_id(family))
    return {
        "video_family_display_name": contract.display_name,
        "video_family_validation_status": contract.validation_status,
        "video_family_validated": contract.validated,
        "video_family_production_ready": contract.production_ready,
        "video_family_backend_route": contract.backend_route,
        "video_family_contract_stack_kind": contract.stack_kind,
        "video_family_required_components": list(contract.required_components),
        "video_family_optional_components": list(contract.optional_components),
        "video_family_history_label_style": contract.history_label_style,
        "video_family_runtime_affinity_fields": list(contract.runtime_affinity_fields),
        "video_family_readiness_notes": list(contract.readiness_notes),
        "video_family_contract_version": contract.to_payload().get("schema_version", 1),
        "video_family_operating_points": ops["operating_points"],
        "video_family_default_operating_point": ops["default_operating_point"],
    }


def video_request_metadata_from_request(req: dict[str, Any]) -> dict[str, Any]:
    stack = req.get("video_model_stack") or req.get("model_stack") or {}
    if not isinstance(stack, dict):
        stack = {}

    frames = _safe_int(req.get("frames") or req.get("num_frames") or req.get("frame_count"), 0)
    fps = _safe_int(req.get("fps"), 0)
    width = _safe_int(req.get("width"), 0)
    height = _safe_int(req.get("height"), 0)
    family = _video_family_from_request_parts(req, stack)
    family_contract = video_family_contract(family)
    stack_kind = _first_nonempty_text(
        req.get("native_video_stack_kind"),
        req.get("video_stack_kind"),
        stack.get("stack_kind"),
        stack.get("stack_mode"),
        family_contract.stack_kind,
    )
    stack_mode = _first_nonempty_text(req.get("video_stack_mode"), stack.get("stack_mode"), stack_kind)
    low_model = _video_stack_first(stack, *VIDEO_LOW_MODEL_KEYS)
    high_model = _video_stack_first(stack, *VIDEO_HIGH_MODEL_KEYS)
    primary_model = _video_stack_first(stack, *VIDEO_PRIMARY_MODEL_KEYS)
    vae_model = _video_stack_first(stack, *VIDEO_VAE_KEYS)
    text_encoder = _video_stack_first(stack, *VIDEO_TEXT_ENCODER_KEYS)
    input_image = video_input_image_for_request(req)
    duration_seconds = round(float(frames) / float(fps), 3) if frames > 0 and fps > 0 else 0.0

    return {
        "video_request_kind": _video_request_command(req) or str(req.get("video_request_kind") or "video"),
        "video_family": family,
        "video_stack_kind": stack_kind,
        "video_stack_mode": stack_mode,
        "video_stack_ready": bool(req.get("video_stack_ready", stack.get("stack_ready", False))),
        "video_model_stack_summary": _video_stack_summary_for_details(stack),
        "video_low_model": low_model,
        "video_low_model_name": _video_stack_basename(low_model),
        "video_high_model": high_model,
        "video_high_model_name": _video_stack_basename(high_model),
        "video_primary_model": primary_model,
        "video_primary_model_name": _video_stack_basename(primary_model),
        "video_vae": vae_model,
        "video_vae_name": _video_stack_basename(vae_model),
        "video_text_encoder": text_encoder,
        "video_text_encoder_name": _video_stack_basename(text_encoder),
        "video_width": width,
        "video_height": height,
        "video_resolution": f"{width}x{height}" if width > 0 and height > 0 else "",
        "video_frames": frames,
        "video_frame_count": frames,
        "video_fps": fps,
        "video_duration_seconds": duration_seconds,
        "video_duration_label": video_duration_label(frames, fps),
        "video_has_input_image": bool(input_image),
        "video_input_image": input_image,
        "video_input_name": os.path.basename(input_image) if input_image else "",
        **_video_family_contract_payload(family),
    }


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

    details = video_request_metadata_from_request(req)
    output = _first_nonempty_text(output_path, req.get("output"), req.get("workflow_media_output"))
    metadata_path = _first_nonempty_text(metadata_output, req.get("metadata_output"))
    request_kind = str(details.get("video_request_kind") or _video_request_command(req) or "video").strip().lower()
    input_name = str(details.get("video_input_name") or "").strip()
    family = str(details.get("video_family") or "").strip()

    details.update({
        "video_backend_type": backend_type,
        "video_backend_name": backend_name,
        "video_validated_backend": video_family_contract(family).production_ready if family else backend_type == "comfy_workflow",
        "video_output": output,
        "output_video": output,
        "video_path": output,
        "video_metadata_output": metadata_path,
        "video_completion_summary": (f"Image-to-video complete from keyframe {input_name}" if request_kind == "i2v" and input_name else ("Text-to-video complete" if request_kind == "t2v" else "Video generation complete")),
        "video_prompt_id": prompt_id or "",
    })
    return details


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
        input_image = video_input_image_for_request(req)
        input_name = os.path.basename(input_image) if input_image else ""
        source_text = f" • keyframe {input_name}" if input_name else ""
        request_kind = str(req.get("video_request_kind") or _video_request_command(req) or "video").strip().lower()
        mode_text = "image-to-video" if request_kind == "i2v" or input_name else "text-to-video"
        return f"waiting for ComfyUI {mode_text} render ({int(elapsed_seconds)}s • {timing}{stack_text}{source_text})"
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
        MODEL_CACHE["lora_adapters"] = {}

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


def image_runtime_cache_key() -> str:
    with CACHE_LOCK:
        return str(MODEL_CACHE.get("key") or "").strip()


def image_runtime_cache_active() -> bool:
    with CACHE_LOCK:
        return bool(MODEL_CACHE.get("key") and (MODEL_CACHE.get("pipe") is not None or MODEL_CACHE.get("img2img_pipe") is not None))


def _video_runtime_cache_snapshot() -> dict[str, Any]:
    with VIDEO_RUNTIME_LOCK:
        return dict(VIDEO_RUNTIME_CACHE)


def active_video_runtime_signature_for_command(command: str) -> str | None:
    command = str(command or "").strip().lower()
    if command not in {"t2v", "i2v"}:
        return None
    with VIDEO_RUNTIME_LOCK:
        active_command = str(VIDEO_RUNTIME_CACHE.get("active_command") or "").strip().lower()
        active_signature = str(VIDEO_RUNTIME_CACHE.get("active_signature") or "").strip()
    if active_command == command and active_signature:
        return active_signature
    return None



def comfy_runtime_identity_snapshot(result_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result_payload = result_payload or {}
    status: dict[str, Any] = {}
    try:
        status = handle_comfy_runtime_status_command({})
        if not isinstance(status, dict):
            status = {}
    except Exception as exc:
        status = {
            "ok": False,
            "running": False,
            "healthy": False,
            "endpoint_alive": False,
            "error": str(exc),
        }

    endpoint = _first_nonempty_text(
        result_payload.get("comfy_runtime_endpoint"),
        status.get("endpoint"),
        os.environ.get("COMFY_API_URL"),
    )
    pid = _safe_int(result_payload.get("comfy_runtime_pid") or status.get("pid"), 0)
    detected_pid = _safe_int(result_payload.get("comfy_runtime_detected_pid") or status.get("detected_pid"), 0)
    healthy = bool(status.get("healthy", False))
    running = bool(status.get("running", False))
    endpoint_alive = bool(status.get("endpoint_alive", False))
    return {
        "ok": bool(status.get("ok", False)),
        "endpoint": endpoint or None,
        "pid": pid or None,
        "detected_pid": detected_pid or None,
        "started_at": status.get("started_at"),
        "state": status.get("state"),
        "ownership": status.get("ownership"),
        "running": running,
        "healthy": healthy,
        "endpoint_alive": endpoint_alive,
        "checked_at": utc_now_iso(),
        "error": status.get("error"),
    }


def _runtime_identity_value(value: Any) -> str:
    return str(value or "").strip()


def video_runtime_truth_for_snapshot(video_snapshot: dict[str, Any], request_signature: str = "") -> dict[str, Any]:
    active_signature = _runtime_identity_value(video_snapshot.get("active_signature"))
    if not active_signature:
        return {
            "ok": False,
            "reason": "no_active_video_runtime",
            "same_signature": False,
            "same_process": False,
            "same_endpoint": False,
            "healthy": False,
        }

    identity = comfy_runtime_identity_snapshot()
    same_signature = not request_signature or active_signature == request_signature

    cached_endpoint = _runtime_identity_value(video_snapshot.get("comfy_runtime_endpoint"))
    current_endpoint = _runtime_identity_value(identity.get("endpoint"))
    same_endpoint = bool(cached_endpoint and current_endpoint and cached_endpoint == current_endpoint)

    cached_pid = _runtime_identity_value(video_snapshot.get("comfy_runtime_pid") or video_snapshot.get("comfy_runtime_detected_pid"))
    current_pid = _runtime_identity_value(identity.get("pid") or identity.get("detected_pid"))
    same_process = bool(cached_pid and current_pid and cached_pid == current_pid)

    healthy = bool(identity.get("running") and identity.get("healthy") and identity.get("endpoint_alive"))
    if not same_signature:
        reason = "video_affinity_changed"
    elif not healthy:
        reason = "comfy_runtime_not_healthy"
    elif not same_endpoint:
        reason = "comfy_endpoint_changed_or_unknown"
    elif not same_process:
        reason = "comfy_process_changed_or_unknown"
    else:
        reason = "same_healthy_comfy_runtime"

    return {
        "ok": bool(same_signature and healthy and same_endpoint and same_process),
        "reason": reason,
        "same_signature": same_signature,
        "same_process": same_process,
        "same_endpoint": same_endpoint,
        "healthy": healthy,
        "identity": identity,
        "cached_signature": active_signature,
        "cached_endpoint": cached_endpoint or None,
        "current_endpoint": current_endpoint or None,
        "cached_pid": cached_pid or None,
        "current_pid": current_pid or None,
    }


def update_video_runtime_cache_from_result(req: dict[str, Any], result_payload: dict[str, Any]) -> dict[str, Any]:
    if not is_video_request(req, str(result_payload.get("output") or result_payload.get("video_path") or "")):
        return {}

    command = str(req.get("command") or req.get("task_command") or result_payload.get("task_type") or "video").strip().lower()
    if command not in {"t2v", "i2v"}:
        command = str(result_payload.get("video_request_kind") or command or "video").strip().lower()

    details = video_request_metadata_from_request(req)
    signature = affinity_signature_for_request(req)
    summary = affinity_summary_for_request(req)
    runtime_identity = comfy_runtime_identity_snapshot(result_payload)
    cache_entry = {
        "active_command": command,
        "active_signature": signature,
        "active_summary": summary,
        "active_family": result_payload.get("video_family") or details.get("video_family"),
        "active_stack_kind": result_payload.get("video_stack_kind") or details.get("video_stack_kind"),
        "active_backend_type": result_payload.get("video_backend_type") or result_payload.get("backend_name"),
        "active_backend_name": result_payload.get("video_backend_name") or result_payload.get("backend_name"),
        "updated_at": utc_now_iso(),
        "reset_reason": None,
        "last_success_at": utc_now_iso(),
        "last_prompt_id": result_payload.get("video_prompt_id") or result_payload.get("prompt_id"),
        "last_output": _first_nonempty_text(result_payload.get("output_video"), result_payload.get("video_path"), result_payload.get("output")),
        "last_error": None,
        "last_failure_code": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "comfy_runtime_endpoint": runtime_identity.get("endpoint"),
        "comfy_runtime_pid": runtime_identity.get("pid"),
        "comfy_runtime_detected_pid": runtime_identity.get("detected_pid"),
        "comfy_runtime_started_at": runtime_identity.get("started_at"),
        "comfy_runtime_state": runtime_identity.get("state"),
        "comfy_runtime_ownership": runtime_identity.get("ownership"),
        "comfy_runtime_running": bool(runtime_identity.get("running", False)),
        "comfy_runtime_healthy": bool(runtime_identity.get("healthy", False)),
        "comfy_runtime_endpoint_alive": bool(runtime_identity.get("endpoint_alive", False)),
        "comfy_runtime_checked_at": runtime_identity.get("checked_at"),
    }
    with VIDEO_RUNTIME_LOCK:
        VIDEO_RUNTIME_CACHE.update(cache_entry)
    return dict(cache_entry)


def runtime_prep_metadata(req: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_transition": req.get("runtime_transition"),
        "runtime_target": req.get("runtime_target"),
        "runtime_previous": req.get("runtime_previous"),
        "runtime_notes": req.get("runtime_notes") or [],
        "image_cache_active_before_runtime": bool(req.get("image_cache_active_before_runtime", False)),
        "image_cache_unloaded_before_video": bool(req.get("image_cache_unloaded_before_video", False)),
        "image_cache_key_before_runtime": req.get("image_cache_key_before_runtime"),
        "video_runtime_signature_before": req.get("video_runtime_signature_before"),
        "video_runtime_reused": bool(req.get("video_runtime_reused", False)),
        "video_warm_reuse_candidate": bool(req.get("video_warm_reuse_candidate", False)),
        "video_warm_reuse_source": req.get("video_warm_reuse_source"),
        "video_runtime_affinity_signature": req.get("video_runtime_affinity_signature"),
        "video_runtime_transition": req.get("video_runtime_transition"),
        "video_runtime_truth_checked": bool(req.get("video_runtime_truth_checked", False)),
        "video_runtime_truth_ok": bool(req.get("video_runtime_truth_ok", False)),
        "video_runtime_truth_reason": req.get("video_runtime_truth_reason"),
        "video_runtime_same_process": bool(req.get("video_runtime_same_process", False)),
        "video_runtime_same_endpoint": bool(req.get("video_runtime_same_endpoint", False)),
        "video_runtime_comfy_pid_before": req.get("video_runtime_comfy_pid_before"),
        "video_runtime_comfy_pid_current": req.get("video_runtime_comfy_pid_current"),
        "video_runtime_comfy_endpoint_before": req.get("video_runtime_comfy_endpoint_before"),
        "video_runtime_comfy_endpoint_current": req.get("video_runtime_comfy_endpoint_current"),
        "runtime_cleanup": req.get("runtime_cleanup"),
    }


def prepare_runtime_for_request(req: dict[str, Any], emitter: "JobEmitter | None" = None, job: "JobRecord | None" = None) -> dict[str, Any]:
    command = str(req.get("command") or req.get("task_command") or req.get("task_type") or "").strip().lower()
    target = "video" if is_video_request(req) else ("image" if command in {"t2i", "i2i"} else "workflow")
    active_image_key = image_runtime_cache_key()
    image_active = image_runtime_cache_active()
    video_snapshot = _video_runtime_cache_snapshot()
    video_signature = str(video_snapshot.get("active_signature") or "").strip()
    request_signature = affinity_signature_for_request(req) if target == "video" else ""

    notes: list[str] = []
    cleanup: dict[str, Any] | None = None
    video_truth: dict[str, Any] = {}

    if target == "video" and video_signature:
        video_truth = video_runtime_truth_for_snapshot(video_snapshot, request_signature)
        if not video_truth.get("ok"):
            reset_video_runtime_cache(f"stale_video_runtime:{video_truth.get('reason') or 'unknown'}")
            notes.append(f"Video warm cache invalidated: {video_truth.get('reason') or 'unknown'}")
            video_snapshot = _video_runtime_cache_snapshot()
            video_signature = ""
        elif emitter is not None and job is not None:
            emitter.status(job, "reusing healthy Comfy video runtime for matching Wan stack")

    previous = "image" if image_active else ("video" if video_signature else "cold")
    transition = f"{previous}_to_{target}" if previous != target else f"{target}_reuse_check"

    video_reused = bool(target == "video" and video_signature and video_signature == request_signature and video_truth.get("ok"))
    if target == "video" and image_active:
        if emitter is not None and job is not None:
            emitter.status(job, "freeing image VRAM before video generation")
        cleanup = unload_cached_pipelines()
        notes.append("Unloaded image pipeline cache before video generation")
    elif target == "image" and video_signature:
        cleanup = {"memory_before": cuda_memory_snapshot(), "memory_after": clear_cuda_memory()}
        notes.append("Cleared local CUDA allocator state before image generation after video runtime")

    metadata = {
        "runtime_transition": transition,
        "runtime_target": target,
        "runtime_previous": previous,
        "runtime_notes": notes,
        "image_cache_active_before_runtime": image_active,
        "image_cache_unloaded_before_video": bool(target == "video" and image_active),
        "image_cache_key_before_runtime": active_image_key,
        "video_runtime_signature_before": video_truth.get("cached_signature") or video_signature or None,
        "video_runtime_reused": video_reused,
        "video_warm_reuse_candidate": video_reused,
        "video_warm_reuse_source": "video-warm-cache" if video_reused else None,
        "video_runtime_affinity_signature": request_signature or None,
        "video_runtime_transition": transition if target == "video" else None,
        "video_runtime_truth_checked": bool(target == "video" and bool(video_truth)),
        "video_runtime_truth_ok": bool(video_truth.get("ok", False)),
        "video_runtime_truth_reason": video_truth.get("reason"),
        "video_runtime_same_process": bool(video_truth.get("same_process", False)),
        "video_runtime_same_endpoint": bool(video_truth.get("same_endpoint", False)),
        "video_runtime_comfy_pid_before": video_truth.get("cached_pid"),
        "video_runtime_comfy_pid_current": video_truth.get("current_pid"),
        "video_runtime_comfy_endpoint_before": video_truth.get("cached_endpoint"),
        "video_runtime_comfy_endpoint_current": video_truth.get("current_endpoint"),
        "runtime_cleanup": cleanup,
    }
    req.update(metadata)
    return metadata


def reset_video_runtime_cache(reason: str = "manual") -> dict[str, Any]:
    before = _video_runtime_cache_snapshot()
    reset_entry = {
        "active_command": None,
        "active_signature": None,
        "active_summary": None,
        "active_family": None,
        "active_stack_kind": None,
        "active_backend_type": None,
        "active_backend_name": None,
        "updated_at": utc_now_iso(),
        "reset_reason": reason,
        "last_success_at": before.get("last_success_at"),
        "last_prompt_id": before.get("last_prompt_id"),
        "last_output": before.get("last_output"),
        "last_error": before.get("last_error"),
        "last_failure_code": before.get("last_failure_code"),
        "invalidated_at": utc_now_iso(),
        "invalidation_reason": reason,
        "comfy_runtime_endpoint": None,
        "comfy_runtime_pid": None,
        "comfy_runtime_detected_pid": None,
        "comfy_runtime_started_at": None,
        "comfy_runtime_state": None,
        "comfy_runtime_ownership": None,
        "comfy_runtime_running": False,
        "comfy_runtime_healthy": False,
        "comfy_runtime_endpoint_alive": False,
        "comfy_runtime_checked_at": None,
    }
    with VIDEO_RUNTIME_LOCK:
        VIDEO_RUNTIME_CACHE.update(reset_entry)
    return {
        "previous": before,
        "current": _video_runtime_cache_snapshot(),
        "reason": reason,
    }


def invalidate_video_runtime_cache_for_failure(job: "JobRecord", code: str, message: str) -> dict[str, Any] | None:
    command = str(job.command or "").strip().lower()
    if command not in {"t2v", "i2v"}:
        return None

    reason = f"job_failed:{code or 'generation_error'}"
    reset = reset_video_runtime_cache(reason)
    with VIDEO_RUNTIME_LOCK:
        VIDEO_RUNTIME_CACHE["last_error"] = str(message or "")[:500]
        VIDEO_RUNTIME_CACHE["last_failure_code"] = code or "generation_error"
        VIDEO_RUNTIME_CACHE["invalidated_at"] = utc_now_iso()
        VIDEO_RUNTIME_CACHE["invalidation_reason"] = reason

    cleanup: dict[str, Any] | None = None
    lowered = str(message or "").lower()
    if "out of memory" in lowered or ("cuda" in lowered and "memory" in lowered):
        cleanup = {"memory_before": cuda_memory_snapshot(), "memory_after": clear_cuda_memory()}

    return {
        "video_runtime_invalidated": True,
        "reason": reason,
        "reset": reset,
        "cleanup": cleanup,
    }


def runtime_memory_status_snapshot(action: str = "runtime_memory_status") -> dict[str, Any]:
    image_active = image_runtime_cache_active()
    image_key = image_runtime_cache_key()
    video_cache = _video_runtime_cache_snapshot()
    memory = cuda_memory_snapshot()
    comfy_status: dict[str, Any] | None = None
    try:
        comfy_status = handle_comfy_runtime_status_command({})
    except Exception as exc:
        comfy_status = {
            "type": "comfy_runtime_status",
            "ok": False,
            "error": str(exc),
        }

    return {
        "type": "runtime_memory_status",
        "ok": True,
        "action": action,
        "timestamp": utc_now_iso(),
        "image_runtime": {
            "active": image_active,
            "model_key": image_key or None,
            "affinity_t2i": active_affinity_signature_for_command("t2i"),
            "affinity_i2i": active_affinity_signature_for_command("i2i"),
        },
        "video_runtime": {
            "active": bool(video_cache.get("active_signature")),
            "active_command": video_cache.get("active_command"),
            "active_signature": video_cache.get("active_signature"),
            "active_summary": video_cache.get("active_summary"),
            "active_family": video_cache.get("active_family"),
            "active_stack_kind": video_cache.get("active_stack_kind"),
            "active_backend_type": video_cache.get("active_backend_type"),
            "active_backend_name": video_cache.get("active_backend_name"),
            "updated_at": video_cache.get("updated_at"),
            "reset_reason": video_cache.get("reset_reason"),
            "last_success_at": video_cache.get("last_success_at"),
            "last_prompt_id": video_cache.get("last_prompt_id"),
            "last_output": video_cache.get("last_output"),
            "last_error": video_cache.get("last_error"),
            "last_failure_code": video_cache.get("last_failure_code"),
            "invalidated_at": video_cache.get("invalidated_at"),
            "invalidation_reason": video_cache.get("invalidation_reason"),
            "comfy_runtime_endpoint": video_cache.get("comfy_runtime_endpoint"),
            "comfy_runtime_pid": video_cache.get("comfy_runtime_pid"),
            "comfy_runtime_detected_pid": video_cache.get("comfy_runtime_detected_pid"),
            "comfy_runtime_started_at": video_cache.get("comfy_runtime_started_at"),
            "comfy_runtime_state": video_cache.get("comfy_runtime_state"),
            "comfy_runtime_ownership": video_cache.get("comfy_runtime_ownership"),
            "comfy_runtime_running": bool(video_cache.get("comfy_runtime_running", False)),
            "comfy_runtime_healthy": bool(video_cache.get("comfy_runtime_healthy", False)),
            "comfy_runtime_endpoint_alive": bool(video_cache.get("comfy_runtime_endpoint_alive", False)),
            "comfy_runtime_checked_at": video_cache.get("comfy_runtime_checked_at"),
            "affinity_t2v": active_affinity_signature_for_command("t2v"),
            "affinity_i2v": active_affinity_signature_for_command("i2v"),
        },
        "memory": memory,
        "comfy_runtime": comfy_status,
    }


def runtime_memory_ack(action: str, ok: bool = True, **fields: Any) -> dict[str, Any]:
    payload = runtime_memory_status_snapshot(action)
    payload["type"] = "runtime_memory_ack"
    payload["ok"] = ok
    payload.update(fields)
    return payload


def handle_runtime_memory_control_command(req: dict[str, Any]) -> dict[str, Any]:
    command = str(req.get("command") or "").strip().lower()

    if command in {"runtime_memory_status", "runtime_diagnostics"}:
        return runtime_memory_status_snapshot(command)

    if command == "unload_image_runtime":
        cleanup = unload_cached_pipelines()
        return runtime_memory_ack(
            command,
            image_runtime_unloaded=True,
            cleanup=cleanup,
            message="Image runtime cache unloaded and local CUDA cache cleared.",
        )

    if command == "unload_video_runtime":
        reset = reset_video_runtime_cache("manual_unload_video_runtime")
        memory_before = cuda_memory_snapshot()
        memory_after = clear_cuda_memory()
        return runtime_memory_ack(
            command,
            video_runtime_unloaded=True,
            video_runtime_reset=reset,
            cleanup={"memory_before": memory_before, "memory_after": memory_after},
            message="Video runtime affinity cache reset and local CUDA cache cleared. ComfyUI process was not stopped.",
        )

    if command == "unload_all_runtimes":
        image_cleanup = unload_cached_pipelines()
        video_reset = reset_video_runtime_cache("manual_unload_all_runtimes")
        memory_after = clear_cuda_memory()
        return runtime_memory_ack(
            command,
            image_runtime_unloaded=True,
            video_runtime_unloaded=True,
            image_cleanup=image_cleanup,
            video_runtime_reset=video_reset,
            cleanup={"memory_after": memory_after},
            message="Image runtime cache unloaded, video runtime affinity cache reset, and local CUDA cache cleared. ComfyUI process was not stopped.",
        )

    if command == "clear_cuda_cache":
        memory_before = cuda_memory_snapshot()
        memory_after = clear_cuda_memory()
        return runtime_memory_ack(
            command,
            cuda_cache_cleared=True,
            cleanup={"memory_before": memory_before, "memory_after": memory_after},
            message="Local Python CUDA cache cleared.",
        )

    return {
        "type": "runtime_memory_ack",
        "ok": False,
        "action": command,
        "error": f"Unknown runtime memory command: {command}",
    }



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
        video_request_details = (
            video_request_metadata_from_request(self.request_snapshot)
            if is_video_request(self.request_snapshot)
            else {}
        )

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
            "input_image": self.request_snapshot.get("input_image"),
            "video_input_image": self.request_snapshot.get("video_input_image") or self.request_snapshot.get("input_keyframe") or self.request_snapshot.get("source_image"),
            "video_input_name": self.request_snapshot.get("video_input_name") or os.path.basename(str(self.request_snapshot.get("video_input_image") or self.request_snapshot.get("input_keyframe") or self.request_snapshot.get("source_image") or self.request_snapshot.get("input_image") or "")),
            "video_has_input_image": bool(self.request_snapshot.get("video_has_input_image", False)),
            **video_request_details,
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

            def active_queue_affinity_for(command: str) -> str | None:
                if self.active_queue_item_id and self.active_queue_item_id in self.items:
                    active_item = self.items[self.active_queue_item_id]
                    if active_item.command == command:
                        return affinity_signature_for_request(active_item.request_snapshot)
                return active_affinity_signature_for_command(command)

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
        execution_command = _queue_ltx_execution_command(req, raw_task_command)
        task_command = _queue_display_command_for_execution(req, execution_command, raw_task_command)

        if task_command not in {"t2i", "i2i", "t2v", "i2v", "comfy_workflow"}:
            raise ValueError("enqueue requires display task_command of 't2i', 'i2i', 't2v', 'i2v', or 'comfy_workflow'")

        if execution_command not in {"t2i", "i2i", "t2v", "i2v", "comfy_workflow", "ltx_prompt_api_gated_submission"}:
            raise ValueError(f"enqueue received unsupported execution command: {execution_command}")

        queue_item_id = str(req.get("queue_item_id") or f"queue_{uuid.uuid4().hex[:12]}")

        request_snapshot = clone_request_snapshot(req)

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
            request_snapshot = _normalize_ltx_prompt_api_request(request_snapshot)
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
            # C3-FOLLOW-UP CANDIDATE (NOT migrated): the queue plain switch reads item.command, which
            # equals req["command"] only post-enqueue. Routing it through canonical_command(req) would
            # change behavior when they differ (pinned by test_dispatch_characterization), so per the
            # behavior-preserving rule it stays as-is until that invariant is proven/asserted.
            item_command = item.command
            execution_command = _queue_ltx_execution_command(req, item_command)
            if execution_command == "ltx_prompt_api_gated_submission":
                req = _normalize_ltx_prompt_api_request(req)
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
            if execution_command == "ltx_prompt_api_gated_submission":
                run_ltx_prompt_api_queued_job(req, emitter, job, active_job)
            else:
                dispatch_generation(item_command, req, emitter, job, active_job)  # C1: single generation dispatcher
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




def normalize_video_input_fields(req: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(req, dict):
        return req

    def _first(*keys: str) -> str:
        for key in keys:
            value = str(req.get(key) or "").strip()
            if value:
                return value
        return ""

    command = str(
        req.get("command")
        or req.get("task_command")
        or req.get("task_type")
        or req.get("workflow_task_command")
        or ""
    ).strip().lower()
    media_type = str(req.get("workflow_media_type") or req.get("media_type") or "").strip().lower()
    stack_kind = str(req.get("native_video_stack_kind") or req.get("video_stack_kind") or "").strip().lower()
    is_video_context = command in {"t2v", "i2v", "comfy_workflow"} or media_type == "video" or bool(stack_kind)

    input_image = _first(
        "video_input_image",
        "input_keyframe",
        "keyframe_image",
        "source_image",
        "i2v_source_image",
        "input_image",
    )

    if input_image:
        for key in ("input_image", "video_input_image", "input_keyframe", "keyframe_image", "source_image", "i2v_source_image"):
            req[key] = input_image
        req["video_has_input_image"] = True
        req.setdefault("video_input_name", os.path.basename(input_image))
        req.setdefault("video_request_kind", "i2v" if is_video_context else str(req.get("video_request_kind") or ""))
    elif command == "i2v" or str(req.get("video_request_kind") or "").strip().lower() == "i2v":
        req.setdefault("video_has_input_image", False)
        req.setdefault("video_request_kind", "i2v")

    return req

def clone_request_snapshot(req: dict[str, Any]) -> dict[str, Any]:
    return normalize_video_input_fields(copy.deepcopy(req))


_GENERATED_SUFFIX_RE = re.compile(
    r"(?:_queue_[A-Za-z0-9_-]+|_retry\d{2,}|_retry_\d{8}_\d{6}|_job_[A-Za-z0-9_-]+)+$"
)


def strip_generated_suffixes(stem: str) -> str:
    return _GENERATED_SUFFIX_RE.sub("", stem)



def normalized_lora_path(lora_path: str | None) -> str:
    value = str(lora_path or "").strip()
    return os.path.abspath(value) if value else ""


def _video_affinity_model_token(req: dict[str, Any]) -> str:
    details = video_request_metadata_from_request(req)
    parts = [
        f"family={details.get('video_family') or 'unknown'}",
        f"kind={details.get('video_stack_kind') or 'unknown'}",
    ]
    for label, key in (
        ("low", "video_low_model_name"),
        ("high", "video_high_model_name"),
        ("primary", "video_primary_model_name"),
        ("vae", "video_vae_name"),
        ("text", "video_text_encoder_name"),
    ):
        value = str(details.get(key) or "").strip()
        if value:
            parts.append(f"{label}={value}")
    return ";".join(parts)


def affinity_signature_for_request(req: dict[str, Any]) -> str:
    command = str(req.get("command") or req.get("task_command") or "").strip().lower()
    lora = normalized_lora_path(req.get("lora"))
    try:
        lora_scale = float(req.get("lora_scale", 1.0))
    except Exception:
        lora_scale = 1.0

    if is_video_request(req):
        return f"{command}|video:{_video_affinity_model_token(req)}|{lora}|{lora_scale:.4f}"

    model = str(req.get("model") or "").strip()
    return f"{command}|{model}|{lora}|{lora_scale:.4f}"


def affinity_summary_for_request(req: dict[str, Any]) -> str:
    command = str(req.get("command") or req.get("task_command") or "").strip().lower()
    lora = normalized_lora_path(req.get("lora"))
    lora_scale = float(req.get("lora_scale", 1.0) or 1.0)
    lora_name = os.path.basename(lora) if lora else "none"

    if is_video_request(req):
        details = video_request_metadata_from_request(req)
        family = str(details.get("video_family") or "Video").strip() or "Video"
        stack = str(details.get("video_model_stack_summary") or _video_affinity_model_token(req)).strip()
        duration = str(details.get("video_duration_label") or "").strip()
        duration_part = f" | {duration}" if duration and duration != "unknown" else ""
        return f"{command.upper()} | {family} | {stack}{duration_part} | LoRA {lora_name} @ {lora_scale:.2f}"

    model = str(req.get("model") or "").strip()
    model_name = os.path.basename(model) if os.path.exists(model) else model
    return f"{command.upper()} | {model_name} | LoRA {lora_name} @ {lora_scale:.2f}"


def active_affinity_signature_for_command(command: str) -> str | None:
    command = str(command or "").strip().lower()
    if command in {"t2v", "i2v"}:
        return active_video_runtime_signature_for_command(command)

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
    command = str(req.get("command") or req.get("task_command") or "").strip().lower()
    active_signature = active_affinity_signature_for_command(command)
    is_video = is_video_request(req)

    if active_signature and active_signature == item_signature:
        return True, "video-warm-cache" if is_video else "warm-cache", item_signature
    if previous_signature and previous_signature == item_signature:
        return True, "adjacent-video-stack" if is_video else "adjacent-queue", item_signature
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


def _file_mtime_iso(path: str) -> str | None:
    try:
        stat = os.stat(path)
    except Exception:
        return None
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()


def _file_size_bytes(path: str) -> int:
    try:
        return int(os.path.getsize(path))
    except Exception:
        return 0


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
    metadata_exists = bool(metadata and os.path.exists(metadata))
    warnings: list[str] = []
    if not output:
        warnings.append("missing_output_path")
    elif not output_exists:
        warnings.append("output_file_missing")
    if not metadata:
        warnings.append("missing_metadata_path")
    elif not metadata_exists and metadata_write_status == "written":
        warnings.append("metadata_file_missing_after_write")
    if metadata_write_error:
        warnings.append("metadata_write_failed")

    now = utc_now_iso()
    contract = {
        "output_contract_version": 1,
        "output_contract_ok": bool(output and output_exists and metadata and (metadata_exists or metadata_write_status in {"queued", "writing"}) and not metadata_write_error),
        "output_contract_warnings": warnings,
        "final_output": output,
        "final_output_path": output,
        "original_output": original or None,
        "original_output_path": original or None,
        "output_exists": output_exists,
        "output_file_size_bytes": _file_size_bytes(output) if output_exists else 0,
        "output_modified_at": _file_mtime_iso(output) if output_exists else None,
        "output_finalized_at": now if output_exists else None,
        "final_metadata": metadata,
        "final_metadata_path": metadata,
        "metadata_exists": metadata_exists,
        "metadata_file_size_bytes": _file_size_bytes(metadata) if metadata_exists else 0,
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

    is_video = is_video_request(request_snapshot, output_path)
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
        "affinity_signature": affinity_signature_for_request(request_snapshot),
        "affinity_summary": affinity_summary_for_request(request_snapshot),
    }

    if is_video:
        # Video branch — preserves the existing video-history fields exactly.
        details = video_completion_diagnostics(
            request_snapshot,
            backend_type=str(result.get("video_backend_type") or result.get("backend_name") or ""),
            backend_name=str(result.get("video_backend_name") or result.get("backend_name") or ""),
            output_path=output_path,
            metadata_output=metadata_path,
            prompt_id=str(result.get("video_prompt_id") or ""),
        )
        if not details:
            details = video_request_metadata_from_request(request_snapshot)
        entry["output_video"] = output_path
        entry["video_path"] = output_path
        entry.update(details)
    else:
        entry["output_image"] = output_path
        entry.update(_image_history_details(request_snapshot, result))

    return entry


def _read_video_history_index_unlocked() -> list[dict[str, Any]]:
    if not VIDEO_HISTORY_INDEX_PATH.exists():
        return []
    try:
        payload = json.loads(VIDEO_HISTORY_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _write_video_history_index_unlocked(items: list[dict[str, Any]]) -> None:
    VIDEO_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "video_history_index",
        "schema_version": 1,
        "updated_at": utc_now_iso(),
        "total_count": len(items),
        "items": items,
    }
    tmp_path = VIDEO_HISTORY_INDEX_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(VIDEO_HISTORY_INDEX_PATH)


def persist_video_history_entry(entry: dict[str, Any] | None) -> None:
    if not entry:
        return

    with VIDEO_HISTORY_LOCK:
        VIDEO_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        items = _read_video_history_index_unlocked()
        identity = str(entry.get("history_id") or entry.get("job_id") or entry.get("output") or "").strip()
        output_path = str(entry.get("output") or entry.get("video_path") or "").strip()
        deduped: list[dict[str, Any]] = []
        for item in items:
            item_identity = str(item.get("history_id") or item.get("job_id") or item.get("output") or "").strip()
            item_output = str(item.get("output") or item.get("video_path") or "").strip()
            if identity and item_identity == identity:
                continue
            if output_path and item_output == output_path:
                continue
            deduped.append(item)

        deduped.append(entry)
        deduped = deduped[-VIDEO_HISTORY_MAX_ITEMS:]
        _write_video_history_index_unlocked(deduped)
        with VIDEO_HISTORY_JSONL_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


def video_history_snapshot(limit: int = 25) -> dict[str, Any]:
    limit = max(1, min(int(limit or 25), VIDEO_HISTORY_MAX_ITEMS))
    with VIDEO_HISTORY_LOCK:
        items = _read_video_history_index_unlocked()
    selected = list(reversed(items[-limit:]))
    return {
        "type": "video_history_snapshot",
        "ok": True,
        "schema_version": 1,
        "history_index_path": str(VIDEO_HISTORY_INDEX_PATH),
        "history_jsonl_path": str(VIDEO_HISTORY_JSONL_PATH),
        "total_count": len(items),
        "items": selected,
        "latest": selected[0] if selected else None,
    }
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

    try:
        persist_video_history_entry(build_history_entry(job, request_snapshot))
    except Exception as exc:
        print(f"[history] failed to persist history entry: {exc}", file=sys.stderr, flush=True)


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


def detect_pipeline_type(model_name_or_path: str, requested_family: str | None = None) -> str:
    # Delegates to the ONE layered classifier (model_classification): safetensors
    # metadata -> request tag -> directory -> filename. This subsumes the old
    # Pony/Illustrious filename carve-out --
    # SDXL finetunes route to the SDXL pipeline via directory + registry family
    # rather than an "xl" filename token. The classifier's shim clamps to a valid
    # image pipeline type (sd/sdxl/sd3/flux) and falls back to the legacy substring
    # for anything non-image, so this contract is unchanged.
    return detect_image_pipeline_type(model_name_or_path, requested_family)


def handle_classify_models_command(req: dict[str, Any]) -> dict[str, Any]:
    # Batch classification for the Qt catalog scanner (option A of the detection
    # accelerator's Qt-consumption follow-up): the UI stops guessing families with
    # its own substring matcher and instead consults THIS -- the one classifier --
    # so the family Qt DISPLAYS matches the family the worker ROUTES. No
    # requested_family is passed: the scan wants the classifier's own verdict.
    paths = req.get("paths") or []
    classifications: list[dict[str, Any]] = []
    for raw in paths:
        path = str(raw)
        try:
            c = classify_model(path)
            spec = MODEL_FAMILIES.get(c.family)
            classifications.append({
                "path": path,
                "family": c.family,
                "display": spec.display_name if spec is not None else c.family.replace("_", " ").title(),
                "sub_family": c.sub_family,
                "pipeline_type": c.pipeline_type,
                "task_family": c.task_family,
                "confidence": c.confidence,
                "source_layer": c.source_layer,
                "model_type": c.model_type,
            })
        except Exception as exc:  # never fail the whole batch on one bad file
            classifications.append({"path": path, "family": "unknown", "error": str(exc)})
    # No "type" key -> worker_client passes this through unwrapped (ok-based branch).
    return {"ok": True, "classifications": classifications}


def handle_resolve_component_stack_command(req: dict[str, Any]) -> dict[str, Any]:
    # Component Auto-Population (Doc 19 §6 A2): the cockpit's producer. On model select the UI
    # sends the chosen primary + task + the file basenames it can offer per component; we run the
    # proven A1 engine (component_resolver.resolve_stack -- byte-equivalent to the worker-side
    # resolvers) and return the per-slot {tier, value, valid_options, required}. The engine is the
    # single source of truth; the worker-side resolvers remain the runtime backstop. No "type" key.
    try:
        from component_resolver import resolve_stack
        from video_family_contracts import VIDEO_FAMILY_CONTRACTS
    except Exception as exc:
        return {"ok": False, "error": f"component resolver unavailable: {exc}"}

    primary = str(req.get("primary") or req.get("model") or "").strip()
    task = str(req.get("task") or req.get("command") or "").strip().lower()
    family = str(req.get("family") or "").strip().lower() or None
    stack = req.get("stack") if isinstance(req.get("stack"), dict) else {}
    # choices: {comfy_class: {comfy_input: [filename, ...]}} -- the cockpit's own combo file set,
    # so value/valid_options come back aligned to what the UI can display.
    choices = req.get("choices") if isinstance(req.get("choices"), dict) else {}

    def choices_for(cls: str, inp: str) -> list[str]:
        bucket = choices.get(cls)
        if not isinstance(bucket, dict):
            return []
        vals = bucket.get(inp)
        return [str(x) for x in vals] if isinstance(vals, (list, tuple)) else []

    contract = VIDEO_FAMILY_CONTRACTS.get(family) if family else None
    try:
        resolved = resolve_stack(
            primary,
            family=family,
            requested_family=family,
            stack=stack,
            req=req,
            task=task or None,
            choices_for=choices_for,
            contract_required=contract.required_components if contract else None,
        )
    except Exception as exc:
        return {"ok": False, "error": f"resolve_stack failed: {exc}"}

    slots = [
        {
            "component": s.component,
            "tier": s.tier,
            "value": s.value,
            "valid_options": list(s.valid_options),
            "required": bool(s.required),
        }
        for s in resolved.slots
    ]
    return {"ok": True, "family": resolved.family, "slots": slots}


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


def _lora_adapter_name(normalized_path: str) -> str:
    # peft adapter names must be simple identifiers; derive a stable,
    # collision-free name from the LoRA's absolute path.
    digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()[:12]
    return f"lora_{digest}"


def _lora_adapter_registry() -> dict[str, str]:
    # normalized LoRA path -> adapter name, for adapters already loaded onto the
    # current model's (shared) pipelines. Reset on model swap; kept across
    # t2i<->i2i role switches within a model. Call under CACHE_LOCK.
    registry = MODEL_CACHE.get("lora_adapters")
    if not isinstance(registry, dict):
        registry = {}
        MODEL_CACHE["lora_adapters"] = registry
    return registry


def active_adapter_names(pipe: Any) -> list[str]:
    try:
        if hasattr(pipe, "get_active_adapters"):
            return [str(name) for name in pipe.get_active_adapters()]
    except Exception:
        pass
    return []


def _disable_pipe_adapters(pipe: Any) -> None:
    # Run pristine base weights for THIS generation without unloading any
    # adapters -- they stay resident on the shared modules for the other role.
    try:
        if hasattr(pipe, "disable_lora"):
            pipe.disable_lora()
            return
    except Exception:
        pass
    try:
        if hasattr(pipe, "set_adapters"):
            pipe.set_adapters([])
    except Exception:
        pass


def ensure_lora_adapter_loaded(pipe: Any, normalized_path: str) -> tuple[str, bool]:
    # Load the LoRA exactly once as a NAMED adapter (never fused, so the base
    # UNet weights -- shared between the t2i/i2i pipes -- are never mutated).
    # Returns (adapter_name, newly_loaded).
    adapter_name = _lora_adapter_name(normalized_path)
    with CACHE_LOCK:
        existing = _lora_adapter_registry().get(normalized_path)
    if existing:
        return existing, False

    pipe.load_lora_weights(normalized_path, adapter_name=adapter_name)
    with CACHE_LOCK:
        _lora_adapter_registry()[normalized_path] = adapter_name
    return adapter_name, True


def reset_lora_state(pipe: Any, pipe_role: str | None = None) -> None:
    # Non-destructive no-LoRA path: DISABLE adapters for this pipe's next
    # generation, but do NOT unload -- the other role's adapter must stay
    # resident on the shared UNet. Base weights are never mutated (we never
    # fuse), so disabling == clean base output.
    _disable_pipe_adapters(pipe)
    if pipe_role:
        set_cached_lora_state(pipe_role, None, None)


def maybe_load_lora(pipe: Any, lora_path: str, lora_scale: float, pipe_role: str) -> tuple[bool, dict[str, Any]]:
    normalized_path = os.path.abspath(lora_path).strip() if lora_path else ""
    cached_path, cached_scale = get_cached_lora_state(pipe_role)

    if not normalized_path:
        cleared = bool(cached_path)
        reset_lora_state(pipe, pipe_role)
        return False, {
            "lora_cache_hit": False,
            "lora_reloaded": False,
            "lora_cleared": cleared,
            "active_lora_path": None,
            "active_lora_scale": None,
        }

    if not os.path.exists(normalized_path):
        raise FileNotFoundError(f"LoRA file not found: {normalized_path}")

    try:
        import peft  # noqa: F401
    except Exception as exc:
        raise RuntimeError("LoRA support requires 'peft' in the venv.") from exc

    adapter_name, newly_loaded = ensure_lora_adapter_loaded(pipe, normalized_path)

    # ALWAYS (re)select + scale this role's adapter right before generating. The
    # UNet is shared between the t2i/i2i pipes, so the active adapter is global
    # state the other role may have changed -- selecting every time is what makes
    # the two roles independent. set_adapters is a cheap toggle (no reload, no
    # fuse), so there is deliberately no cache-hit short-circuit that skips it.
    try:
        if hasattr(pipe, "enable_lora"):
            pipe.enable_lora()
    except Exception:
        pass
    pipe.set_adapters([adapter_name], adapter_weights=[float(lora_scale)])

    same_as_cached = (
        cached_path == normalized_path
        and cached_scale is not None
        and abs(float(cached_scale) - float(lora_scale)) < 1e-9
    )
    set_cached_lora_state(pipe_role, normalized_path, float(lora_scale))

    return True, {
        "lora_cache_hit": (not newly_loaded) and same_as_cached,
        "lora_reloaded": newly_loaded,
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


# Kill switch for the CPU-side fp32->fp16 cast applied during pipeline load.
# Set False to keep whatever dtype the checkpoint carries on disk (much higher
# VRAM for fp32 single-file SDXL checkpoints). See
# memory_optimization.build_paired_pipelines.
CAST_FP32_TO_FP16 = True


def build_pipelines(model_name_or_path: str, requested_family: str | None = None) -> tuple[Any, Any, str, str, str]:
    # ONE shared-weight load (t2i + a from_pipe i2i companion) instead of two
    # independent from_single_file copies on the GPU, plus a CPU-side
    # fp32->fp16 cast for fp32-on-disk checkpoints. This is the drop-in
    # integration documented in memory_optimization.build_paired_pipelines.
    #
    # Return shape and the MODEL_CACHE contract are preserved EXACTLY: callers
    # (run_t2i, run_i2i, cleanup_for_model_swap) still receive
    # (t2i_pipe, i2i_pipe, device, dtype_str, detected). The i2i pipe stays
    # reachable as a weight-sharing companion rather than a second full GPU copy.
    #
    # On a >=16GB card auto_select_memory_profile returns PERFORMANCE, so no CPU
    # offload is enabled -- full speed, just deduplicated + fp16.
    profile = auto_select_memory_profile()
    result = build_paired_pipelines(
        model_name_or_path,
        detect_pipeline_type=detect_pipeline_type,
        profile=profile,
        cast_fp32_to_fp16=CAST_FP32_TO_FP16,
        requested_family=requested_family,
    )

    report = result.report
    # WARNING (not INFO): the root logger defaults to WARNING, so INFO is
    # filtered. This line finally makes the actually-resident dtype and the
    # post-load VRAM visible in the worker log.
    logging.warning(
        "[t2i] pipeline ready: detected=%s requested_dtype=%s resident_dtype=%s "
        "profile=%s cuda_allocated_gb=%.2f cuda_reserved_gb=%.2f total_gb=%.2f "
        "cast_fp32_to_fp16=%s notes=%s",
        result.detected,
        result.dtype_str,
        report.resident_dtype,
        report.profile,
        report.allocated_gb,
        report.reserved_gb,
        report.total_gb,
        CAST_FP32_TO_FP16,
        ",".join(report.notes),
    )

    return (
        result.t2i_pipe,
        result.i2i_pipe,
        result.device,
        result.dtype_str,
        result.detected,
    )


def get_or_load_pipelines(model_name_or_path: str, requested_family: str | None = None) -> tuple[Any, Any, str, str, str, bool, dict[str, Any] | None]:
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
    t2i_pipe, i2i_pipe, device, dtype, detected = build_pipelines(model_name_or_path, requested_family)
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
    os.makedirs(os.path.dirname(metadata_output), exist_ok=True)
    target = Path(metadata_output)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as file_obj:
        json.dump(data, file_obj, indent=2)
    tmp_path.replace(target)


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
    return finalize_metadata_payload(
        data,
        output_path=image_path,
        metadata_output=metadata_output,
        original_output=str(req.get("original_output") or ""),
        media_type=data.get("media_type"),
    )



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
        runtime_failure = invalidate_video_runtime_cache_for_failure(job, code, error_text)
        fail_job(job, error_text, code=code, tb=tb, details=runtime_failure)
        self.emit_job_update(job)
        payload: dict[str, Any] = {"type": "error", "ok": False, "job_id": job.job_id, "state": job.state.value, "error": error_text}
        if runtime_failure:
            payload["runtime_failure"] = runtime_failure
        if tb:
            payload["traceback"] = tb
        self.emit(payload)


# Long-prompt / weighting support (design doc 12). The SDXL CLIP tokenizer truncates at 77 tokens
# (silently dropping the tail) and ignores civitai (word:1.2) weighting. sd_embed's
# get_weighted_text_embeddings_sdxl chunks past 77 and honors that weighting. A same-seed A/B (short
# weight-free prompt, string path vs sd_embed) showed sd_embed's encoding drifts MEANINGFULLY from
# diffusers' native encode_prompt (MAE ~24-35, a visibly different -- though coherent -- image), so we
# use OPTION B: keep the native prompt= path (byte-identical, preserves reproducibility) for simple
# prompts and route through sd_embed ONLY when it's actually needed -- i.e. >77 tokens OR weighting
# syntax present (the cases that were truncated/ignored before, where there is no old output to keep).
# Escape literal parens as \( \) so they aren't read as weighting.
_WEIGHTING_SYNTAX_RE = re.compile(r"(?<!\\)[()\[\]]")


def _has_weighting_syntax(text: str) -> bool:
    return bool(text) and _WEIGHTING_SYNTAX_RE.search(text) is not None


def _exceeds_clip_window(pipe: Any, text: str) -> bool:
    if not text:
        return False
    tokenizer = getattr(pipe, "tokenizer", None)
    if tokenizer is None:
        return False
    try:
        # verbose=False silences transformers' "Token indices sequence length is longer than 77"
        # notice -- this is a deliberate length PROBE (we never feed this untruncated sequence to the
        # model; sd_embed chunks it), so the warning would be misleading log noise.
        ids = tokenizer(text, truncation=False, padding=False, add_special_tokens=True, verbose=False)["input_ids"]
    except Exception:
        return False
    return len(ids) > 77  # CLIP window incl. BOS/EOS; >77 => the native path would truncate the tail


def _prompt_needs_weighted_embeds(pipe: Any, prompt: str, negative: str) -> bool:
    return (
        _has_weighting_syntax(prompt)
        or _has_weighting_syntax(negative)
        or _exceeds_clip_window(pipe, prompt)
        or _exceeds_clip_window(pipe, negative)
    )


def build_generation_kwargs(
    req: dict[str, Any],
    generator: torch.Generator,
    extra: dict[str, Any] | None = None,
    pipe: Any = None,
) -> dict[str, Any]:
    prompt = req["prompt"]
    negative = req.get("negative_prompt") or ""

    kwargs: dict[str, Any] = {
        "num_inference_steps": int(req["steps"]),
        "guidance_scale": float(req["cfg"]),
        "generator": generator,
    }

    # OPTION B routing (see note above): native string path unless the prompt needs sd_embed.
    if pipe is not None and _prompt_needs_weighted_embeds(pipe, prompt, negative):
        from sd_embed.embedding_funcs import get_weighted_text_embeddings_sdxl

        pe, npe, ppe, nppe = get_weighted_text_embeddings_sdxl(pipe, prompt=prompt, neg_prompt=negative)
        # MUST NOT also pass prompt=/negative_prompt= -- diffusers rejects string + embeds together.
        kwargs["prompt_embeds"] = pe
        kwargs["pooled_prompt_embeds"] = ppe
        kwargs["negative_prompt_embeds"] = npe
        kwargs["negative_pooled_prompt_embeds"] = nppe
        logging.warning(
            "[long-prompt] sd_embed embed path: prompt_chars=%d weighting=%s (>77 tokens or (word:w) syntax)",
            len(prompt),
            _has_weighting_syntax(prompt) or _has_weighting_syntax(negative),
        )
    else:
        kwargs["prompt"] = prompt
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
    runtime_prep = prepare_runtime_for_request(req, emitter, job)

    pipe, _, device, dtype, detected, cache_hit, model_swap_cleanup = get_or_load_pipelines(req["model"], req.get("model_family"))
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
        pipe=pipe,
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
        "active_adapters": active_adapter_names(pipe),
        "metadata": metadata_payload,
        "metadata_write_deferred": False,
        **output_finalization_contract(output_path if 'output_path' in locals() else req.get("output"), metadata_output if 'metadata_output' in locals() else req.get("metadata_output"), original_output=str(req.get("original_output") or ""), media_type=output_media_type_for_metadata(req, output_path if 'output_path' in locals() else req.get("output")), metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"), metadata_write_error=metadata_payload.get("metadata_write_error")),
        **runtime_prep_metadata(req),
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


# Slots whose value names a model file: a full path / bare name from the UI must be resolved to the
# EXACT string ComfyUI's loader lists (subfolder-relative, ComfyUI's separator) or /prompt rejects it
# with value_not_in_list. Other slots (prompt, seed, dims...) are set verbatim.
_MODEL_SLOTS_TO_RESOLVE = {"checkpoint", "model", "lora"}


def _apply_workflow_slot_bindings(
    workflow: dict[str, Any],
    slot_bindings: dict[str, Any],
    req: dict[str, Any],
    object_info: dict[str, Any] | None = None,
) -> None:
    slot_values = _workflow_slot_values_from_request(req)
    for slot, raw_value in slot_values.items():
        if raw_value in (None, ""):
            continue
        binding = slot_bindings.get(slot)
        if not isinstance(binding, dict):
            continue
        node_id = str(binding.get("node_id") or "").strip()
        input_name = str(binding.get("input_name") or binding.get("input") or "").strip()
        path_expr = str(binding.get("path") or "").strip()
        if not path_expr and node_id and input_name:
            path_expr = f"{node_id}.inputs.{input_name}"
        if not path_expr:
            continue

        value: Any = raw_value
        # Resolve a model/checkpoint/lora override (which may arrive as a full path or bare filename)
        # to the loader node's exact catalogued name. Without object_info we leave it verbatim (a UI
        # already in ComfyUI-relative form still works; a full path would not, but that is the no-schema
        # fallback).
        if object_info and slot in _MODEL_SLOTS_TO_RESOLVE and node_id:
            node = workflow.get(node_id)
            if isinstance(node, dict):
                class_name = str(node.get("class_type") or "")
                target_input = input_name or (path_expr.rsplit(".", 1)[-1] if "." in path_expr else "")
                if class_name and target_input:
                    value = _sv_choose_comfy_choice(object_info, class_name, target_input, str(raw_value))

        _set_workflow_path(workflow, path_expr, value)


# Loader class -> (slot, input_name). A just-converted UI-graph carries no profile bindings, so we
# derive them from the API-prompt graph. Both "checkpoint" and "model" slots draw their value from
# req["model"] (see _workflow_slot_values_from_request), so a checkpoint loader binds the "checkpoint"
# slot and a diffusion-model (UNET) loader binds "model".
_MODEL_LOADER_SLOTS = {
    "CheckpointLoaderSimple": ("checkpoint", "ckpt_name"),
    "CheckpointLoader": ("checkpoint", "ckpt_name"),
    "UNETLoader": ("model", "unet_name"),
    "UnetLoaderGGUF": ("model", "unet_name"),
}
_LORA_LOADER_SLOTS = {
    "LoraLoader": "lora_name",
    "LoraLoaderModelOnly": "lora_name",
}


def _derive_checkpoint_slot_bindings(workflow: dict[str, Any]) -> dict[str, Any]:
    """Best-effort slot bindings for a just-converted API-prompt graph whose profile carried none
    (the UI-graph import path produces empty bindings). Only binds when the loader is unambiguous:
    a single checkpoint/diffusion-model loader binds the checkpoint/model slot, and a single lora
    loader binds the lora slot. Multi-loader graphs (e.g. a Wan high/low-noise dual UNETLoader) are
    left unbound -- still launchable, just not model-substitutable -- pending a multi-loader slot
    vocabulary (Stage 1.5 dual-loader design decision, deliberately not built here)."""
    model_loaders: list[tuple[str, str, str]] = []  # (slot, node_id, input_name)
    lora_loaders: list[tuple[str, str]] = []  # (node_id, input_name)
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if class_type in _MODEL_LOADER_SLOTS:
            slot, input_name = _MODEL_LOADER_SLOTS[class_type]
            if input_name in inputs:
                model_loaders.append((slot, str(node_id), input_name))
        elif class_type in _LORA_LOADER_SLOTS:
            input_name = _LORA_LOADER_SLOTS[class_type]
            if input_name in inputs:
                lora_loaders.append((str(node_id), input_name))
    bindings: dict[str, Any] = {}
    if len(model_loaders) == 1:
        slot, node_id, input_name = model_loaders[0]
        bindings[slot] = {"node_id": node_id, "input_name": input_name}
    if len(lora_loaders) == 1:
        node_id, input_name = lora_loaders[0]
        bindings["lora"] = {"node_id": node_id, "input_name": input_name}
    return bindings


def _apply_common_comfy_overrides(
    workflow: dict[str, Any], req: dict[str, Any], object_info: dict[str, Any] | None = None
) -> None:
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
        class_type = str(node.get("class_type") or "")
        for field_name, value in mapping.items():
            if value in (None, ""):
                continue
            for key in aliases.get(field_name, set()):
                if key in inputs and not isinstance(inputs.get(key), (list, dict)):
                    resolved = value
                    # The model override may arrive as a full path / bare name; resolve it to this
                    # loader's exact catalogued entry (matching _apply_workflow_slot_bindings), else
                    # this broad override would clobber the bound slot with an unvalidatable value.
                    if field_name == "model" and object_info and class_type:
                        resolved = _sv_choose_comfy_choice(object_info, class_type, key, str(value))
                    inputs[key] = resolved


# Loader inputs whose value names a model FILE. A workflow's own baked-in values (not just an override)
# routinely arrive as a bare filename or a subfolder-relative name that does not match ComfyUI's exact
# catalogued string (e.g. "nova.safetensors" vs "sdxl\nova.safetensors"), which /prompt rejects with
# value_not_in_list. Normalize every such input against the live catalog before submission.
_MODEL_FILE_INPUT_NAMES = {
    "ckpt_name", "unet_name", "lora_name", "vae_name", "clip_name", "clip_name1", "clip_name2",
    "control_net_name", "style_model_name", "upscale_model_name", "clip_vision_name", "model_name",
    "gguf_name", "ipadapter_file", "instantid_file",
}


def _resolve_graph_model_names(workflow: dict[str, Any], object_info: dict[str, Any] | None) -> None:
    if not object_info:
        return
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or not class_type:
            continue
        for input_name in _MODEL_FILE_INPUT_NAMES:
            value = inputs.get(input_name)
            if not isinstance(value, str) or not value.strip():
                continue
            choices = _sv_comfy_input_choices(object_info, class_type, input_name)
            if not choices or value in choices:
                continue  # no catalog for this input, or already an exact match
            resolved = _sv_choose_comfy_choice(object_info, class_type, input_name, value)
            if resolved in choices:
                inputs[input_name] = resolved  # only rewrite when we land on a real catalogued entry


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


def _comfy_status_is_completed(status: Any) -> bool:
    """True when ComfyUI marks a prompt terminally finished (success), independent of outputs.

    ComfyUI writes the /history `status` for a finished prompt, but `outputs` can lag (or, for a
    genuinely empty result, never appear). Detecting the terminal-success flag lets the poller
    stop waiting the full timeout on a completed-but-empty prompt instead of hanging the queue."""
    if not isinstance(status, dict):
        return False
    if status.get("completed") is True:
        return True
    return str(status.get("status_str") or "").strip().lower() in {"success", "completed"}


def _poll_comfy_history(api_url: str, prompt_id: str, req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    poll_interval = float(req.get("comfy_poll_interval_sec") or 1.0)
    timeout_sec = float(req.get("comfy_timeout_sec") or 1800.0)
    completed_grace_sec = float(req.get("comfy_completed_grace_sec") or 15.0)
    completed_seen_at: float | None = None
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
            # ComfyUI reported this prompt terminally finished but /history carries no outputs yet.
            # Grant a bounded grace window for outputs to materialize, then fail cleanly instead of
            # spinning to the full timeout — a completed-but-empty prompt must terminate the job
            # (COMPLETED via outputs, or a clear error) so it can never hang the queue at 95%.
            if _comfy_status_is_completed(status):
                now = time.monotonic()
                if completed_seen_at is None:
                    completed_seen_at = now
                elif now - completed_seen_at >= completed_grace_sec:
                    raise RuntimeError(
                        f"ComfyUI reported prompt {prompt_id} completed but produced no outputs "
                        f"after {completed_grace_sec:.0f}s grace (status={status})."
                    )

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
    family = _video_family_from_request_parts(req, stack)
    return family if family != "unknown" else "unknown"

def _native_video_pipeline_candidates(command: str, family: str) -> list[str]:
    candidates = video_family_pipeline_candidates(command, family)
    if candidates:
        return candidates

    return [
        "WanImageToVideoPipeline",
        "WanPipeline",
        "LTXImageToVideoPipeline",
        "LTXVideoPipeline",
        "CogVideoXImageToVideoPipeline",
        "CogVideoXPipeline",
        "HunyuanVideoPipeline",
        "MochiPipeline",
    ] if str(command or "").strip().lower() == "i2v" else [
        "WanPipeline",
        "LTXVideoPipeline",
        "CogVideoXPipeline",
        "HunyuanVideoPipeline",
        "MochiPipeline",
    ]

def _is_split_video_stack_request(req: dict[str, Any]) -> bool:
    stack = _video_model_stack_from_request(req)
    stack_kind = str(stack.get("stack_kind") or req.get("native_video_stack_kind") or "").strip().lower()
    # wan_dual_noise routes to the split path the same way split_stack does -- BEFORE the primary-model
    # requirement below. The dual-noise builder reads high/low experts from the stack and ignores a
    # primary model, so requiring one was never meaningful for this stack kind; without this early
    # return a dual-noise request whose `model` is empty (the frontend sends the key but draft.model
    # can be blank when only high/low experts are selected) raises in _native_video_model_reference
    # before the builder ever runs.
    if stack_kind in ("split_stack", "wan_dual_noise"):
        return True
    model_ref = _native_video_model_reference(req)
    return Path(model_ref).suffix.lower() in {".safetensors", ".ckpt", ".bin", ".gguf"}


def _comfy_object_info(api_url: str) -> dict[str, Any]:
    # ComfyUI's /object_info body is large (~2MB+) and the connection can be reset
    # mid-read under load (ConnectionResetError, which is NOT a urllib URLError, so a
    # plain single urlopen slips it through). Every native video gen calls this, so a
    # transient reset must not abort the job: send Connection: close, retry a few times
    # with a short backoff, and use a generous timeout. On exhaustion, raise a clear
    # error rather than returning a partial/empty dict (a truncated object_info would
    # cause confusing downstream node-resolution failures).
    attempts = 5
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                f"{api_url}/object_info",
                headers={"Connection": "close"},
            )
            with urllib.request.urlopen(request, timeout=90) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise RuntimeError("ComfyUI /object_info did not return a JSON object")
            return payload
        except Exception as exc:  # URLError, ConnectionResetError/OSError, JSON decode, etc.
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(
        f"Failed to read ComfyUI object_info from {api_url} after {attempts} attempts: {last_error}"
    ) from last_error


def _upload_comfy_image(api_url: str, local_path: str) -> dict[str, Any]:
    """Upload a local image into ComfyUI's input dir via POST /upload/image.

    Needed for native i2v: LoadImage.image is a COMBO of files in ComfyUI's input
    directory, so an arbitrary local path can't be referenced directly -- the keyframe
    must live where Comfy can see it. Returns ComfyUI's RESPONSE descriptor
    {"name","subfolder","type"}; callers MUST use response["name"] (Comfy may rename
    on collision), never the basename sent. Mirrors _comfy_object_info hardening:
    Connection: close, retry, clear raise on failure (never a bogus name).
    """
    path = Path(local_path)
    if not path.is_file():
        raise RuntimeError(f"i2v input image not found on disk: {local_path}")
    data = path.read_bytes()
    filename = path.name

    attempts = 4
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            boundary = "----spellvision" + uuid.uuid4().hex
            body = bytearray()
            body += (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode("utf-8")
            body += data
            body += b"\r\n"
            for field, value in (("type", "input"), ("overwrite", "true")):
                body += (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'
                ).encode("utf-8")
            body += f"--{boundary}--\r\n".encode("utf-8")

            request = urllib.request.Request(
                f"{api_url}/upload/image",
                data=bytes(body),
                method="POST",
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(request, timeout=90) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            name = str((payload or {}).get("name") or "").strip()
            if not name:
                raise RuntimeError(f"ComfyUI /upload/image returned no name: {payload}")
            return {
                "name": name,
                "subfolder": str(payload.get("subfolder") or ""),
                "type": str(payload.get("type") or "input"),
            }
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(
        f"Failed to upload i2v input image to ComfyUI at {api_url} after {attempts} attempts: {last_error}"
    ) from last_error


def _comfy_image_ref(uploaded: dict[str, Any]) -> str:
    """ComfyUI LoadImage value for an uploaded asset: 'name', or 'subfolder/name'."""
    name = str(uploaded.get("name") or "").strip()
    subfolder = str(uploaded.get("subfolder") or "").strip().strip("/")
    return f"{subfolder}/{name}" if subfolder else name


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
    # Always fold the unique job_id into the prefix so every submission yields a NOVEL
    # filename_prefix. Without this, re-submitting an identical graph (fixed seed + same output:
    # a re-gen, a re-queue, or a concurrent near-duplicate) is byte-identical, so ComfyUI fully
    # caches every node INCLUDING SaveVideo, re-executes nothing, and reports EMPTY /history
    # outputs -- the worker then has no asset to retrieve and the poll stalls at 95%. A unique
    # prefix invalidates the terminal save node's cache entry so it always re-runs (upstream
    # stays cached -- no wasted compute) and its output is always reported. The worker copies the
    # saved file to req["output"], so the ComfyUI-side name never surfaces to the user.
    safe_job = re.sub(r"[^a-zA-Z0-9_\-]+", "_", str(job_id or "")).strip("_")[:24] or "job"
    stem = re.sub(r"[^a-zA-Z0-9_\-]+", "_", Path(str(output_path or "").strip()).stem).strip("_")[:72]
    if stem:
        return f"{stem}_{safe_job}"
    return f"spellvision_native_video_{safe_job}"


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


def _preferred_video_vae_name(object_info: dict[str, Any], family: str, vae_path: str, primary_path: str = "") -> str:
    requested = _comfy_vae_name(vae_path)
    available = _comfy_input_choices(object_info, "VAELoader", "vae_name")
    available_lower = {item.lower(): item for item in available}

    family_key = str(family or "").strip().lower()

    if family_key == "wan":
        # Version-aware order (interim VAE-variant fix), same as the core resolver.
        for preferred in _wan_vae_preference(primary_path, vae_path):
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


def _sv_core_wan_vae_name(object_info: dict[str, Any], stack: dict[str, Any], primary_path: str = "", *, force_version: str = "") -> str:
    explicit = str(stack.get("vae_path") or stack.get("vae") or "").strip()
    requested = _sv_basename(explicit)
    choices = _comfy_input_choices(object_info, "VAELoader", "vae_name")
    if not choices:
        return requested

    by_lower = {choice.lower(): choice for choice in choices}
    if requested:  # explicit stack VAE always wins
        found = by_lower.get(requested.lower())
        if found:
            return found

    # Auto-resolve version-matched (interim VAE-variant fix): pick the VAE matching the
    # loaded Wan version instead of a blind 2.2-first guess. The probe reads the model
    # path (from the builder, which is req["model"] when the stack is bare -- the exact
    # crashing repro). Inconclusive -> the original 2.2-first order.
    # force_version overrides the filename probe: the Wan 2.2 A14B DUAL-NOISE stack uses the 16-ch
    # 2.1 VAE (wan_2.1_vae), which the "high_noise"/"low_noise" filename probe would otherwise mis-map
    # to the 48-ch 2.2 VAE. (The 5B TI2V path, which DOES use the 2.2 VAE, has no route yet -- future.)
    if force_version:
        preference = _wan_vae_preference_for_version(force_version)
    else:
        probe_path = primary_path or _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path"))
        preference = _wan_vae_preference(probe_path, str(stack.get("family") or ""))
    for preferred in preference:
        found = by_lower.get(preferred.lower())
        if found:
            return found

    for choice in choices:
        lowered = choice.lower()
        if "wan" in lowered and "vae" in lowered:
            return choice

    return choices[0]


def _path_looks_high_noise(path_value: str) -> bool:
    # Wan 2.2 dual-noise HIGH half by filename (lifted from the archived dual-core
    # fix). Noise-half is NOT a family concept and the classifier/registry don't carry
    # it, so it stays a filename predicate. Used only by the single-model i2v refuse-guard.
    haystack = str(path_value or "").replace("\\", "/").lower()
    return any(tok in haystack for tok in ("high_noise", "high-noise", "t2v_high", "_high_"))


def _path_looks_low_noise(path_value: str) -> bool:
    haystack = str(path_value or "").replace("\\", "/").lower()
    return any(tok in haystack for tok in ("low_noise", "low-noise", "t2v_low", "_low_"))


def _wan_vae_version_marker(*path_values: str) -> str:
    # "2.1" / "2.2" / "" from the model filename signal, to pick the VAE that matches
    # the loaded Wan version (2.1 latent = 16ch -> wan_2.1_vae; 2.2 = 48ch -> wan2.2_vae).
    # INTERIM for Doc 19's variant disambiguation -- reuses the existing filename signal,
    # invents no new classifier. The full producer-side resolution supersedes this later.
    h = " ".join(str(p or "") for p in path_values).replace("\\", "/").lower()
    if any(t in h for t in ("wan2.2", "wan_2.2", "wan-2.2", "wan22")) or "high_noise" in h or "low_noise" in h:
        return "2.2"
    if any(t in h for t in ("wan2.1", "wan_2.1", "wan-2.1", "wan21", "i2v_480p_14b", "i2v_720p_14b")):
        return "2.1"
    return ""


def _wan_vae_preference_for_version(marker: str) -> tuple[str, ...]:
    # Version-ranked VAE order for a KNOWN version. "2.1" -> 2.1-first (Wan 2.1 single-model AND
    # Wan 2.2 A14B dual-noise, which uses the 16-ch 2.1 VAE, NOT the 48-ch 2.2 VAE); anything else
    # -> the original 2.2-first order.
    if str(marker).strip() == "2.1":
        return ("wan_2.1_vae.safetensors", "wan2.1_vae.safetensors", "wan2.2_vae.safetensors", "wan_2.2_vae.safetensors")
    return ("wan2.2_vae.safetensors", "wan_2.2_vae.safetensors", "wan2.1_vae.safetensors", "wan_2.1_vae.safetensors")


def _wan_vae_preference(*path_values: str) -> tuple[str, ...]:
    # Version-aware VAE preference order from the FILENAME probe. On an inconclusive probe, falls
    # back to the original 2.2-first order (unchanged behavior for unmarked models).
    return _wan_vae_preference_for_version(_wan_vae_version_marker(*path_values))


def _sv_core_wan_clip_vision_name(object_info: dict[str, Any], stack: dict[str, Any], req: dict[str, Any]) -> str:
    # Resolve the Wan i2v CLIP-vision (CLIP-ViT-H) filename from the request/stack,
    # validated against the LIVE CLIPVisionLoader choices. Empty return -> omit
    # clip_vision (WanImageToVideo.clip_vision_output is optional -> the no-clip_vision
    # branch, valid for Wan 2.2 i2v which needs no CLIP-vision).
    requested = str(
        req.get("clip_vision") or req.get("clip_vision_path")
        or stack.get("clip_vision") or stack.get("clip_vision_path") or ""
    ).strip()
    requested_name = Path(requested).name if requested else ""
    choices = _comfy_input_choices(object_info, "CLIPVisionLoader", "clip_name")
    by_lower = {str(c).strip().lower(): str(c).strip() for c in choices}
    if requested_name and requested_name.lower() in by_lower:
        return by_lower[requested_name.lower()]
    for pref in ("clip_vision_h.safetensors", "clip_vision_vit_h.safetensors"):
        if pref in by_lower:
            return by_lower[pref]
    for low, orig in by_lower.items():
        if "clip_vision_h" in low or ("vit" in low and "_h" in low):
            return orig
    return ""


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


def _wan_dual_expert_path(req: dict[str, Any], stack: dict[str, Any], keys: tuple[str, ...]) -> str:
    # A dual-noise expert path lives in the video_model_stack (AssetCatalogScanner populates
    # high_noise_path/high_noise_model_path/wan_high_noise_path + low equivalents), but may also
    # arrive at the request top level -- check the stack first, then the request, across all aliases.
    value = _video_stack_first(stack, *keys)
    if value:
        return value
    for key in keys:
        value = str(req.get(key) or "").strip()
        if value:
            return value
    return ""


def _is_wan_dual_noise_request(req: dict[str, Any]) -> bool:
    # True iff the request is a Wan 2.2 A14B dual-noise stack (stack_kind marker) carrying BOTH
    # experts. The C++ frontend sets native_video_stack_kind (GenerationRequestBuilder) and stacks
    # stack_kind/stack_mode (AssetCatalogScanner); accept any of them.
    stack = _video_model_stack_from_request(req)
    kind = str(
        req.get("native_video_stack_kind")
        or req.get("video_stack_kind")
        or stack.get("stack_kind")
        or stack.get("stack_mode")
        or ""
    ).strip().lower()
    if kind != "wan_dual_noise":
        return False
    high = _wan_dual_expert_path(req, stack, VIDEO_HIGH_MODEL_KEYS)
    low = _wan_dual_expert_path(req, stack, VIDEO_LOW_MODEL_KEYS)
    return bool(high and low)


def _sv_video_lora_name(object_info: dict[str, Any], lora_path: str, *, class_name: str) -> str:
    # Resolve a LoRA path to the LoraLoaderModelOnly.lora_name COMBO entry -- the same subdir-qualified
    # basename resolution _sv_video_primary_name does for UNET names (loras/ is the named model dir).
    return _sv_choose_comfy_choice(object_info, class_name, "lora_name", _path_after_named_dir(lora_path, ("loras",)))


def _wan_lora_stack_entries(req: dict[str, Any]) -> list[dict[str, Any]]:
    # The frontend sends lora_stack (== loras) = [{"name": <path>, "strength": <double>, "enabled": <bool>}].
    # Read name/strength (NOT path/scale -- those are model_sources.py's keys, a different layer). Keep
    # only enabled==True entries, preserving stack order.
    raw = req.get("lora_stack")
    if not isinstance(raw, list):
        raw = req.get("loras")
    entries: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict) or item.get("enabled") is False:
                continue
            name = str(item.get("name") or item.get("value") or "").strip()
            if not name:
                continue
            try:
                strength = float(item.get("strength", item.get("weight", 1.0)))
            except (TypeError, ValueError):
                strength = 1.0
            entries.append({"name": name, "strength": strength})
    return entries


def _wan_expert_task_variant(path_value: str) -> str:
    # t2v / i2v task variant from an expert filename (for the dual-noise pairing guard). "" if neither.
    haystack = str(path_value or "").replace("\\", "/").lower()
    if "t2v" in haystack:
        return "t2v"
    if "i2v" in haystack:
        return "i2v"
    return ""


def _emit_wan_lora_chain(prompt: dict[str, Any], object_info: dict[str, Any], model_ref: list[Any], lora_entries: list[dict[str, Any]], *, node_prefix: str) -> list[Any]:
    """Thread a chain of LoraLoaderModelOnly (model-only) nodes onto model_ref: UNET -> LoRA_1 -> LoRA_2
    -> ... -> returned ref. Each node's `model` input = the PREVIOUS node's output (the chain), lora_name
    resolved against the live LoraLoaderModelOnly choices, strength_model = the entry's single strength.
    An empty list returns model_ref unchanged and emits NO nodes -- the no-LoRA path stays byte-identical."""
    if not lora_entries:
        return model_ref
    lora_class = _first_available_class(object_info, ("LoraLoaderModelOnly",), label="WAN dual-noise LoRA loading")
    allowed = _comfy_class_inputs(object_info, lora_class)
    current = model_ref
    for index, entry in enumerate(lora_entries):
        node_id = f"{node_prefix}{index}"
        inputs: dict[str, Any] = {}
        _set_if_allowed(inputs, allowed, ("model",), current)
        _set_if_allowed(inputs, allowed, ("lora_name",), _sv_video_lora_name(object_info, str(entry["name"]), class_name=lora_class))
        _set_if_allowed(inputs, allowed, ("strength_model",), float(entry["strength"]))
        _add_node(prompt, node_id, lora_class, inputs)
        current = [node_id, 0]
    return current


def _build_native_wan_dual_noise_video_prompt(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str) -> dict[str, Any]:
    """Wan 2.2 A14B dual-expert (MoE) T2V. TWO diffusion checkpoints (high-noise + low-noise), one per
    KSamplerAdvanced stage: the high-noise expert denoises steps [0, split) and passes its leftover
    noise to the low-noise expert, which finishes [split, steps]. Grounded on the official ComfyUI
    video_wan2_2_14B_t2v template (two UNETLoader weight_dtype="default", two ModelSamplingSD3 shift 5.0,
    EmptyHunyuanLatentVideo, umt5 CLIP type "wan", wan_2.1 VAE, both text-encodes feed BOTH samplers).
    The template's LoRA/switch/primitive/math/markdown scaffolding is flattened away (literals baked) --
    same pruning discipline as the LTX migration; optional LoRA is a later pass via the contract's
    optional_components slot, not the switch machinery.

    Defaults are BASE-MODEL (full fp8 14B, no acceleration LoRA): steps=20 / cfg=3.5 is a sane Wan-T2V
    budget. The official template's steps=4 / cfg=1 / split=2 is the Lightx2v-LoRA config -- a no-LoRA
    render at 4 steps looks terrible, so it is NOT the default, but every knob is req-overridable, so the
    LoRA path is reachable later by passing steps=4, cfg=1. split = steps // 2 (grounded)."""
    if command != "t2v":
        raise RuntimeError(
            "The Wan 2.2 dual-noise MoE builder supports T2V only; dual-noise I2V is a separate, "
            "unwired topology (use a single-file I2V checkpoint for Wan I2V)."
        )

    stack = _video_model_stack_from_request(req)
    high_path = _wan_dual_expert_path(req, stack, VIDEO_HIGH_MODEL_KEYS)
    low_path = _wan_dual_expert_path(req, stack, VIDEO_LOW_MODEL_KEYS)
    # Dual-noise contract required_components: BOTH experts. A dual-noise request missing one is an
    # error naming the absent expert -- NOT a silent fall-back to a single-model primary_path render.
    if not high_path:
        raise RuntimeError(
            "Wan 2.2 dual-noise T2V requires the HIGH-noise expert checkpoint "
            "(high_noise_path / high_noise_model_path / wan_high_noise_path); none was provided."
        )
    if not low_path:
        raise RuntimeError(
            "Wan 2.2 dual-noise T2V requires the LOW-noise expert checkpoint "
            "(low_noise_path / low_noise_model_path / wan_low_noise_path); none was provided."
        )

    # Expert-pairing guard (HARD ERROR by choice): the two experts must be the SAME task variant.
    # A t2v-high + i2v-low pairing renders off-model (the i2v refiner runs without its image
    # conditioning -> a degraded/noisy clip after ~8 min of compute, diagnosed live). A clear upfront
    # error beats silently burning the render and shipping bad output; the frontend should offer only
    # matched pairs. (Empty variant on either side -> no signal -> allowed.)
    high_variant = _wan_expert_task_variant(high_path)
    low_variant = _wan_expert_task_variant(low_path)
    if high_variant and low_variant and high_variant != low_variant:
        raise RuntimeError(
            f"Wan 2.2 dual-noise expert mismatch: the HIGH-noise expert is a {high_variant.upper()} "
            f"checkpoint but the LOW-noise expert is a {low_variant.upper()} checkpoint. Both experts "
            "must be the same task variant (both t2v, or both i2v) -- a mixed pair renders off-model. "
            f"high={os.path.basename(high_path)} low={os.path.basename(low_path)}"
        )

    # Per-family operating point (Phase 1 + 3a): validate the request's operating_point NAME first
    # (unknown -> warn + fall back to the family default; never raise), then resolve sampling params
    # with the valid name. The table fills blank/auto params; an explicit request value always wins;
    # anything the table lacks falls to the inline literal safety net kept below. Absent operating_point
    # -> the family default ("quality" for Wan), so a NORMAL request (frontend sends concrete
    # steps/cfg/sampler) is byte-identical to before this change.
    _op_name = resolve_operating_point("wan", req.get("operating_point"))
    _op = resolve_family_defaults("wan", _op_name, req)
    frames = int(req.get("frames") or req.get("num_frames") or req.get("frame_count") or 81)
    fps = int(req.get("fps") or req.get("frame_rate") or 16)
    steps = int(_op.get("steps") or 20)
    if steps < 2:
        steps = 2
    split = steps // 2
    width = int(req.get("width") or 832)
    height = int(req.get("height") or 480)
    cfg = float(_op.get("cfg") or 3.5)
    seed = int(req.get("seed") or req.get("noise_seed") or 1)
    if seed <= 0:
        seed = 1
    # Per-expert shift: high_noise_shift/low_noise_shift still OVERRIDE the resolved base shift (they
    # are per-expert, not an operating-point axis). The base falls to the resolved shift, then 5.0.
    _base_shift = _op.get("shift") or 5.0
    high_shift = float(req.get("high_noise_shift") or _base_shift)
    low_shift = float(req.get("low_noise_shift") or _base_shift)

    # LoRA stack (enabled entries only), routed per expert by filename: high_noise -> high only,
    # low_noise -> low only, neither -> both (content LoRA applies to the whole model). Reuses the
    # existing _path_looks_high/low_noise predicates -- no new detection.
    lora_entries = _wan_lora_stack_entries(req)
    # LoRA FOOTGUN CLOSE (phase 3a): an operating point may DECLARE accel LoRAs (the "fast" point is
    # 4 steps / cfg 1 -- garbage on the non-distilled base model WITHOUT its Lightx2v accel LoRAs). If
    # the resolved operating point declares lora.accel AND the request supplied NO LoRA stack, auto-
    # inject the declared high/low accel LoRAs with a LOUD warning: an API/script caller sending
    # operating_point="fast" alone must never silently get a 4-step garbage render. The UI path (3b)
    # always populates the visible LoRA stack, so lora_entries is non-empty there and this never fires;
    # a caller who supplied ANY LoRA stack is left untouched (their explicit intent wins). The injected
    # names route through the SAME per-expert filename logic below (high_noise->high, low_noise->low).
    if not lora_entries:
        _op_lora = operating_point_params("wan", _op_name).get("lora", {})
        if _op_lora.get("accel"):
            _accel = [{"name": str(p).strip(), "strength": 1.0}
                      for p in (_op_lora.get("high"), _op_lora.get("low")) if str(p or "").strip()]
            if _accel:
                logging.warning(
                    "operating_point %r declares accel LoRAs but the request supplied no lora_stack; "
                    "AUTO-INJECTING %s (this operating point runs %d steps / cfg %s, which renders "
                    "garbage on the base model without them). Supply an explicit lora_stack to override.",
                    _op_name, [e["name"] for e in _accel], steps, cfg,
                )
                lora_entries = _accel
    high_loras: list[dict[str, Any]] = []
    low_loras: list[dict[str, Any]] = []
    for _lora in lora_entries:
        _is_high = _path_looks_high_noise(_lora["name"])
        _is_low = _path_looks_low_noise(_lora["name"])
        if _is_high and not _is_low:
            high_loras.append(_lora)
        elif _is_low and not _is_high:
            low_loras.append(_lora)
        else:
            high_loras.append(_lora)
            low_loras.append(_lora)

    prompt: dict[str, Any] = {}

    # --- shared CLIP + text encodes (feed BOTH samplers) ---
    clip_class = _first_available_class(object_info, ("CLIPLoader",), label="WAN dual-noise CLIP loading")
    allowed = _comfy_class_inputs(object_info, clip_class)
    inputs: dict[str, Any] = {}
    _set_if_allowed(inputs, allowed, ("clip_name",), _sv_core_wan_clip_name(object_info, stack, req))
    _set_if_allowed(inputs, allowed, ("type", "clip_type"), "wan")
    _set_if_allowed(inputs, allowed, ("device",), str(req.get("text_encoder_device") or stack.get("text_encoder_device") or "default"))
    _add_node(prompt, "1", clip_class, inputs)

    text_class = _first_available_class(object_info, ("CLIPTextEncode",), label="WAN dual-noise text encoding")
    allowed = _comfy_class_inputs(object_info, text_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("clip",), ["1", 0])
    _set_if_allowed(inputs, allowed, ("text", "prompt"), str(req.get("prompt") or ""))
    _add_node(prompt, "2", text_class, inputs)

    inputs = {}
    _set_if_allowed(inputs, allowed, ("clip",), ["1", 0])
    _set_if_allowed(inputs, allowed, ("text", "prompt"), str(req.get("negative_prompt") or ""))
    _add_node(prompt, "3", text_class, inputs)

    # --- TWO UNETLoader experts (weight_dtype "default"; fp8 is baked into the checkpoint) ---
    unet_class = _first_available_class(object_info, ("UNETLoader",), label="WAN dual-noise diffusion model loading")
    unet_allowed = _comfy_class_inputs(object_info, unet_class)
    weight_dtype = _sv_core_choice_or_default(object_info, unet_class, "weight_dtype", req.get("weight_dtype"), "default")

    inputs = {}
    _set_if_allowed(inputs, unet_allowed, ("unet_name", "model_name", "ckpt_name", "checkpoint"), _sv_video_primary_name(object_info, high_path, class_name=unet_class))
    _set_if_allowed(inputs, unet_allowed, ("weight_dtype",), weight_dtype)
    _add_node(prompt, "4", unet_class, inputs)   # HIGH-noise expert

    inputs = {}
    _set_if_allowed(inputs, unet_allowed, ("unet_name", "model_name", "ckpt_name", "checkpoint"), _sv_video_primary_name(object_info, low_path, class_name=unet_class))
    _set_if_allowed(inputs, unet_allowed, ("weight_dtype",), weight_dtype)
    _add_node(prompt, "12", unet_class, inputs)  # LOW-noise expert

    # --- VAE: dual-noise A14B is ARCHITECTURALLY LOCKED to the 16-ch 2.1 VAE. An explicit VAE in the
    # stack (the frontend defaults to wan2.2_vae for a "2.2" model) is INVALID here, not a preference --
    # the 48-ch 2.2 VAE crashes VAEDecode 48-vs-16 on the 16-ch latent the 14B experts produce. Strip
    # the explicit VAE keys so _sv_core_wan_vae_name's "explicit wins" branch can't return it and the
    # resolver falls through to force_version="2.1". Only THIS builder strips it -- the "explicit wins"
    # rule stays intact for every other Wan path (the single-model core call passes the stack unmodified).
    vae_stack = {k: v for k, v in stack.items() if k not in ("vae", "vae_path")}
    vae_class = _first_available_class(object_info, ("VAELoader",), label="WAN dual-noise VAE loading")
    allowed = _comfy_class_inputs(object_info, vae_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("vae_name", "vae", "model_name"), _sv_core_wan_vae_name(object_info, vae_stack, high_path, force_version="2.1"))
    _add_node(prompt, "5", vae_class, inputs)

    # --- per-expert LoRA chains inserted between each UNETLoader and its ModelSamplingSD3:
    # UNETLoader -> [LoraLoaderModelOnly ...] -> ModelSamplingSD3 (the template's node-83/85 slot).
    # Empty list -> the ref stays the UNETLoader, no nodes emitted (no-LoRA path byte-identical). ---
    high_model_ref = _emit_wan_lora_chain(prompt, object_info, ["4", 0], high_loras, node_prefix="h_lora_")
    low_model_ref = _emit_wan_lora_chain(prompt, object_info, ["12", 0], low_loras, node_prefix="l_lora_")

    # --- TWO ModelSamplingSD3 (per-expert shift), one per expert ---
    sampling_class = _first_available_class(object_info, ("ModelSamplingSD3",), label="WAN dual-noise model sampling config")
    sampling_allowed = _comfy_class_inputs(object_info, sampling_class)
    inputs = {}
    _set_if_allowed(inputs, sampling_allowed, ("model",), high_model_ref)
    _set_if_allowed(inputs, sampling_allowed, ("shift",), high_shift)
    _add_node(prompt, "6", sampling_class, inputs)   # HIGH

    inputs = {}
    _set_if_allowed(inputs, sampling_allowed, ("model",), low_model_ref)
    _set_if_allowed(inputs, sampling_allowed, ("shift",), low_shift)
    _add_node(prompt, "13", sampling_class, inputs)  # LOW

    # --- latent (t2v: empty) ---
    latent_class = _first_available_class(object_info, ("EmptyHunyuanLatentVideo", "EmptyWanLatentVideo", "WanEmptyLatentVideo", "EmptyLatentVideo"), label="WAN dual-noise latent video creation")
    allowed = _comfy_class_inputs(object_info, latent_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("width",), width)
    _set_if_allowed(inputs, allowed, ("height",), height)
    _set_if_allowed(inputs, allowed, ("length", "frames", "num_frames", "frame_count"), frames)
    _set_if_allowed(inputs, allowed, ("batch_size",), int(req.get("batch_size") or 1))
    _add_node(prompt, "7", latent_class, inputs)

    # --- TWO chained KSamplerAdvanced: HIGH [0, split) leaves leftover noise -> LOW [split, steps] ---
    sampler_class = _first_available_class(object_info, ("KSamplerAdvanced",), label="WAN dual-noise sampling")
    sampler_allowed = _comfy_class_inputs(object_info, sampler_class)
    sampler_name = _sv_core_wan_choice(object_info, sampler_class, "sampler_name", _op.get("sampler"), ("euler", "dpmpp_2m", "dpm++_2m", "uni_pc", "unipc"))
    scheduler_name = _sv_core_wan_choice(object_info, sampler_class, "scheduler", _op.get("scheduler"), ("simple", "normal", "sgm_uniform", "karras"))

    inputs = {}
    _set_if_allowed(inputs, sampler_allowed, ("model",), ["6", 0])
    _set_if_allowed(inputs, sampler_allowed, ("add_noise",), "enable")
    _set_if_allowed(inputs, sampler_allowed, ("noise_seed", "seed"), seed)
    _set_if_allowed(inputs, sampler_allowed, ("steps",), steps)
    _set_if_allowed(inputs, sampler_allowed, ("cfg",), cfg)
    _set_if_allowed(inputs, sampler_allowed, ("sampler_name", "sampler"), sampler_name)
    _set_if_allowed(inputs, sampler_allowed, ("scheduler", "scheduler_name"), scheduler_name)
    _set_if_allowed(inputs, sampler_allowed, ("positive",), ["2", 0])
    _set_if_allowed(inputs, sampler_allowed, ("negative",), ["3", 0])
    _set_if_allowed(inputs, sampler_allowed, ("latent_image", "samples"), ["7", 0])
    _set_if_allowed(inputs, sampler_allowed, ("start_at_step",), 0)
    _set_if_allowed(inputs, sampler_allowed, ("end_at_step",), split)
    _set_if_allowed(inputs, sampler_allowed, ("return_with_leftover_noise",), "enable")
    _add_node(prompt, "8", sampler_class, inputs)   # HIGH-noise stage

    inputs = {}
    _set_if_allowed(inputs, sampler_allowed, ("model",), ["13", 0])
    _set_if_allowed(inputs, sampler_allowed, ("add_noise",), "disable")
    _set_if_allowed(inputs, sampler_allowed, ("noise_seed", "seed"), seed)
    _set_if_allowed(inputs, sampler_allowed, ("steps",), steps)
    _set_if_allowed(inputs, sampler_allowed, ("cfg",), cfg)
    _set_if_allowed(inputs, sampler_allowed, ("sampler_name", "sampler"), sampler_name)
    _set_if_allowed(inputs, sampler_allowed, ("scheduler", "scheduler_name"), scheduler_name)
    _set_if_allowed(inputs, sampler_allowed, ("positive",), ["2", 0])
    _set_if_allowed(inputs, sampler_allowed, ("negative",), ["3", 0])
    # THE MoE HANDOFF: the low stage consumes the HIGH sampler's leftover-noise latent (node 8), NOT
    # the empty latent. Getting this link right is the entire dual-expert mechanism.
    _set_if_allowed(inputs, sampler_allowed, ("latent_image", "samples"), ["8", 0])
    _set_if_allowed(inputs, sampler_allowed, ("start_at_step",), split)
    _set_if_allowed(inputs, sampler_allowed, ("end_at_step",), steps)
    _set_if_allowed(inputs, sampler_allowed, ("return_with_leftover_noise",), "disable")
    _add_node(prompt, "14", sampler_class, inputs)  # LOW-noise stage

    # --- decode (from the LOW sampler) -> create video -> save ---
    decode_class = _first_available_class(object_info, ("VAEDecode",), label="WAN dual-noise VAE decode")
    allowed = _comfy_class_inputs(object_info, decode_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("samples",), ["14", 0])
    _set_if_allowed(inputs, allowed, ("vae",), ["5", 0])
    _add_node(prompt, "9", decode_class, inputs)

    create_video_class = _first_available_class(object_info, ("CreateVideo",), label="WAN dual-noise video assembly")
    allowed = _comfy_class_inputs(object_info, create_video_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("images",), ["9", 0])
    _set_if_allowed(inputs, allowed, ("fps",), fps)
    _add_node(prompt, "10", create_video_class, inputs)

    save_class = _first_available_class(object_info, ("SaveVideo", "SaveWEBM"), label="WAN dual-noise video saving")
    allowed = _comfy_class_inputs(object_info, save_class)
    output_value = str(req.get("output") or req.get("output_path") or f"spellvision_render_t2v_{job_id}")
    filename_prefix = _filename_prefix_from_output(output_value, job_id)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("video",), ["10", 0])
    _set_if_allowed(inputs, allowed, ("filename_prefix", "filename", "path"), filename_prefix)
    _set_if_allowed(inputs, allowed, ("format",), "mp4")
    _set_if_allowed(inputs, allowed, ("codec",), "h264")
    _add_node(prompt, "11", save_class, inputs)

    return _spellvision_apply_teacache_to_native_video_prompt(prompt, req, object_info)


def _build_native_wan_core_video_prompt(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str) -> dict[str, Any]:
    if command not in ("t2v", "i2v"):
        raise RuntimeError("The native WAN core adapter supports T2V and single-model I2V only.")

    stack = _video_model_stack_from_request(req)
    primary_path = _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path")) or str(req.get("model") or "")
    if not primary_path:
        raise RuntimeError("The selected WAN video stack has no primary diffusion model path.")

    # Single-model i2v refuse-guard: a Wan 2.2 dual-noise HALF cannot drive the single-UNET
    # core i2v graph -- warn and refuse rather than silently build a degraded render. (Dual-
    # noise i2v is a separate, unwired topology.)
    if command == "i2v" and (_path_looks_high_noise(primary_path) or _path_looks_low_noise(primary_path)):
        raise RuntimeError(
            "This is a Wan 2.2 dual-noise model half; single-model i2v needs a single-file "
            "i2v checkpoint (Wan 2.1 i2v, or a single-file 2.2). Dual-noise i2v is a separate topology."
        )

    # Phase 2a: default values lifted to the operating-point table; each read keeps its verbatim
    # request aliases and inserts the table default before the (kept) literal safety net.
    _defaults = operating_point_params("wan_core", "default")
    frames = int(req.get("frames") or req.get("num_frames") or req.get("frame_count") or 81)
    fps = int(req.get("fps") or req.get("frame_rate") or 16)
    steps = int(req.get("steps") or _defaults.get("steps") or 30)
    width = int(req.get("width") or 832)
    height = int(req.get("height") or 480)
    cfg = float(req.get("cfg") or req.get("guidance_scale") or _defaults.get("cfg") or 5.0)
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
    _set_if_allowed(inputs, allowed, ("vae_name", "vae", "model_name"), _sv_core_wan_vae_name(object_info, stack, primary_path))
    _add_node(prompt, "5", vae_class, inputs)

    sampling_class = _first_available_class(object_info, ("ModelSamplingSD3",), label="WAN core model sampling config")
    allowed = _comfy_class_inputs(object_info, sampling_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model",), ["4", 0])
    _set_if_allowed(inputs, allowed, ("shift",), float(req.get("shift") or req.get("model_sampling_shift") or _defaults.get("shift") or 5.0))
    _add_node(prompt, "6", sampling_class, inputs)

    # --- node 7: the sampler's latent source. FORK A: t2v = empty latent; i2v = the
    # WanImageToVideo image-conditioning subgraph (nodes 1-6 and 9-11 stay identical). ---
    sampler_positive: list[Any] = ["2", 0]
    sampler_negative: list[Any] = ["3", 0]
    sampler_latent: list[Any] = ["7", 0]
    if command == "i2v":
        # Image ingress: the keyframe was already uploaded to ComfyUI's input dir by
        # run_native_split_stack_video (req["input_image_comfy_name"]); LoadImage refs it
        # (a raw local path 400s against LoadImage's input-dir COMBO). Same bridge as LTX.
        image_class = _first_available_class(object_info, ("LoadImage",), label="WAN i2v keyframe load")
        allowed = _comfy_class_inputs(object_info, image_class)
        inputs = {}
        _set_if_allowed(inputs, allowed, ("image",), str(req.get("input_image_comfy_name") or ""))
        _add_node(prompt, "20", image_class, inputs)

        # Conditional clip_vision: WanImageToVideo.clip_vision_output is OPTIONAL, so wire
        # the CLIPVisionLoader->CLIPVisionEncode chain only when the encoder nodes exist AND
        # a CLIP-ViT-H model resolves (Wan 2.1 i2v needs it; Wan 2.2 i2v omits it -- the one
        # optional input covers both branches).
        clip_vision_link: list[Any] | None = None
        clip_vision_model = _sv_core_wan_clip_vision_name(object_info, stack, req)
        if "CLIPVisionLoader" in object_info and "CLIPVisionEncode" in object_info and clip_vision_model:
            cv_loader_class = _first_available_class(object_info, ("CLIPVisionLoader",), label="WAN i2v clip-vision loading")
            allowed = _comfy_class_inputs(object_info, cv_loader_class)
            inputs = {}
            _set_if_allowed(inputs, allowed, ("clip_name",), clip_vision_model)
            _add_node(prompt, "21", cv_loader_class, inputs)

            cv_encode_class = _first_available_class(object_info, ("CLIPVisionEncode",), label="WAN i2v clip-vision encode")
            allowed = _comfy_class_inputs(object_info, cv_encode_class)
            inputs = {}
            _set_if_allowed(inputs, allowed, ("clip_vision",), ["21", 0])
            _set_if_allowed(inputs, allowed, ("image",), ["20", 0])
            _set_if_allowed(inputs, allowed, ("crop",), str(req.get("clip_vision_crop") or "center"))
            _add_node(prompt, "22", cv_encode_class, inputs)
            clip_vision_link = ["22", 0]

        i2v_class = _first_available_class(object_info, ("WanImageToVideo",), label="WAN i2v image conditioning")
        allowed = _comfy_class_inputs(object_info, i2v_class)
        inputs = {}
        _set_if_allowed(inputs, allowed, ("positive",), ["2", 0])
        _set_if_allowed(inputs, allowed, ("negative",), ["3", 0])
        _set_if_allowed(inputs, allowed, ("vae",), ["5", 0])
        _set_if_allowed(inputs, allowed, ("start_image",), ["20", 0])
        if clip_vision_link is not None:
            _set_if_allowed(inputs, allowed, ("clip_vision_output",), clip_vision_link)
        _set_if_allowed(inputs, allowed, ("width",), width)
        _set_if_allowed(inputs, allowed, ("height",), height)
        _set_if_allowed(inputs, allowed, ("length", "frames", "num_frames", "frame_count"), frames)
        _set_if_allowed(inputs, allowed, ("batch_size",), int(req.get("batch_size") or 1))
        _add_node(prompt, "7", i2v_class, inputs)
        # WanImageToVideo emits (positive', negative', latent) -> the sampler reads these
        # instead of nodes 2/3 and the empty latent.
        sampler_positive = ["7", 0]
        sampler_negative = ["7", 1]
        sampler_latent = ["7", 2]
    else:
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
    _set_if_allowed(inputs, allowed, ("sampler_name", "sampler"), _sv_core_wan_choice(object_info, sampler_class, "sampler_name", req.get("video_sampler") or req.get("sampler") or _defaults.get("sampler"), ("dpmpp_2m", "dpm++_2m", "euler", "uni_pc", "unipc")))
    _set_if_allowed(inputs, allowed, ("scheduler", "scheduler_name"), _sv_core_wan_choice(object_info, sampler_class, "scheduler", req.get("video_scheduler") or req.get("scheduler") or _defaults.get("scheduler"), ("sgm_uniform", "normal", "simple", "karras")))
    _set_if_allowed(inputs, allowed, ("positive",), sampler_positive)
    _set_if_allowed(inputs, allowed, ("negative",), sampler_negative)
    _set_if_allowed(inputs, allowed, ("latent_image", "samples"), sampler_latent)
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
    # SaveVideo saves UNDER ComfyUI's output dir -- an absolute path outside it is rejected
    # ("Saving image outside the output folder is not allowed"). Use the same safe stem
    # helper the LTX + wrapper builders use; the worker maps the saved file back to output.
    filename_prefix = _filename_prefix_from_output(output_value, job_id)
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
    _defaults = operating_point_params("wan_wrapper", "default")  # Phase 2a: default values lifted to the table
    fps = int(req.get("fps") or req.get("frame_rate") or 16)
    steps = int(req.get("steps") or _defaults.get("steps") or 30)
    cfg = float(req.get("cfg") or req.get("cfg_scale") or _defaults.get("cfg") or 6.0)
    shift = float(req.get("sampling_shift") or req.get("shift") or _defaults.get("shift") or 5.0)
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
    _set_if_allowed(inputs, allowed, ("scheduler",), _sv_choice_or_default(object_info, sampler_class, "scheduler", req.get("video_scheduler") or req.get("scheduler") or _defaults.get("scheduler"), "unipc"))
    _set_if_allowed(inputs, allowed, ("riflex_freq_index",), int(req.get("riflex_freq_index") or 0))
    _set_if_allowed(inputs, allowed, ("denoise_strength",), float(req.get("denoise") or req.get("denoise_strength") or _defaults.get("denoise") or 1.0))
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
    ).strip()
    if explicit and normalize_video_family_id(explicit) not in {"unknown", "video", "native_video", "split_stack"}:
        return normalize_video_family_id(explicit)

    stack = _video_model_stack_from_request(req)
    inferred = _video_family_from_request_parts(req, stack)
    return inferred if inferred != "unknown" else (normalize_video_family_id(explicit) if explicit else "unknown")



def _build_native_ltx_video_prompt(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
    job_id: str,
) -> dict[str, Any]:
    # Repo-owned EMBEDDED template (pruned single-pass audio+video graph seeded
    # from ltx_api.json). Never read the live D: workflow at runtime.
    template_path = Path(__file__).resolve().parent / "video_templates" / "ltx_av_native.json"
    graph = json.loads(template_path.read_text(encoding="utf-8"))
    warnings: list[str] = []

    if isinstance(object_info, dict):
        missing_classes = sorted({
            str(node.get("class_type"))
            for node in graph.values()
            if isinstance(node, dict) and node.get("class_type") and node["class_type"] not in object_info
        })
        if missing_classes:
            warnings.append("LTX template references node classes missing from ComfyUI /object_info: " + ", ".join(missing_classes))

    def patch(node_id: str, key: str, value: Any) -> None:
        node = graph.get(node_id)
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict) and value is not None:
            node["inputs"][key] = value

    def first(*keys: str) -> Any:
        for key in keys:
            value = req.get(key)
            if value not in (None, ""):
                return value
        return None

    # Prompts.
    patch("2483", "text", first("prompt"))
    negative = first("negative_prompt", "negative")
    if negative is not None:
        patch("2612", "text", negative)

    # Dimensions / length / fps. length (4979) + fps (4978) drive BOTH video and audio.
    width = first("width")
    height = first("height")
    if width is not None:
        patch("3059", "width", int(width))
    if height is not None:
        patch("3059", "height", int(height))
    length = first("length", "frames", "num_frames")
    if length is not None:
        patch("4979", "value", int(length))
    fps = first("fps", "frame_rate")
    if fps is not None:
        patch("4978", "value", float(fps))

    # Sampling.
    seed = first("seed")
    if seed is not None:
        patch("4814", "noise_seed", int(seed))
    steps = first("steps")
    if steps is not None:
        patch("4966", "steps", int(steps))
    cfg = first("cfg", "cfg_scale")
    if cfg is not None:
        patch("4964", "cfg", float(cfg))  # VIDEO guider; AUDIO guider (4963) stays fixed.

    # Asset names (keep the template's proven defaults when not provided).
    patch("3940", "ckpt_name", first("ltx_transformer"))
    patch("4986", "vae_name", first("ltx_video_vae"))
    patch("4010", "ckpt_name", first("ltx_audio_vae"))
    patch("4960", "text_encoder", first("ltx_text_encoder"))
    patch("4960", "ckpt_name", first("ltx_text_projection"))

    # LoRA: OFF by default. chel was only ever a lora-application test, never an intended
    # default (it also skewed composition regardless of prompt). So ABSENCE of a lora now
    # bypasses node 4968 cleanly (rewire every referrer to the checkpoint MODEL output --
    # the verified no-dangling path). A provided name (+ optional strength) still wires
    # 4968 with that lora; chel remains in the template JSON only as a fallback reachable
    # by explicitly re-selecting it.
    explicit_lora = next((req.get(k) for k in ("lora", "lora_name", "ltx_lora") if k in req), KeyError)
    explicit_opt_out = (
        req.get("use_lora") is False
        or (explicit_lora is not KeyError and str(explicit_lora or "").strip().lower() in {"", "none", "off", "disabled", "no"})
    )
    # An opt-out token ("none"/"off"/...) is truthy as a string, so clear lora_name
    # to fall through to the bypass branch instead of patching a bogus lora file.
    lora_name = None if explicit_opt_out else first("lora", "lora_name", "ltx_lora")
    if lora_name:
        patch("4968", "lora_name", lora_name)
        lora_strength = first("lora_scale", "lora_strength")
        if lora_strength is not None:
            patch("4968", "strength_model", float(lora_strength))
    elif "4968" in graph:
        for node in graph.values():
            inputs = node.get("inputs") if isinstance(node, dict) else None
            if not isinstance(inputs, dict):
                continue
            for key, value in inputs.items():
                if isinstance(value, list) and len(value) == 2 and str(value[0]) == "4968":
                    inputs[key] = ["3940", 0]  # LoraLoaderModelOnly MODEL -> CheckpointLoaderSimple MODEL
        graph.pop("4968", None)

    # t2v vs i2v: the bypass boolean (4977) gates LTXVImgToVideoConditionOnly (3159).
    # The keyframe is already uploaded to ComfyUI by run_native_split_stack_video, which
    # stashes the Comfy-side LoadImage name in req["input_image_comfy_name"] (LoadImage
    # is a COMBO of input-dir files -- a raw local path would 400). If i2v is requested
    # but no image was uploaded, fall back to t2v (bypass=True) with a warning.
    comfy_image = first("input_image_comfy_name")
    want_i2v = command == "i2v"
    is_i2v = want_i2v and bool(comfy_image)
    if want_i2v and not comfy_image:
        warnings.append("LTX i2v requested but no input image was uploaded; falling back to t2v (bypass).")
    patch("4977", "value", (not is_i2v))  # bypass=True => t2v (image ignored)
    if is_i2v:
        patch("2004", "image", str(comfy_image))
        # Image-conditioning strength (how strongly the render adheres to the keyframe).
        # Only an explicit knob overrides the template default (3159.strength=0.7);
        # denoise is intentionally NOT auto-mapped (inverse semantics).
        strength = first("ltx_image_strength", "i2v_strength", "image_conditioning_strength")
        if strength is not None:
            try:
                patch("3159", "strength", float(strength))
            except (TypeError, ValueError):
                pass

    # Output prefix.
    output = first("output")
    if output:
        patch("4823", "filename_prefix", _filename_prefix_from_output(str(output), job_id))

    req["resolved_native_video_family"] = "ltx"
    req["native_video_route"] = "ltx_template"
    req["native_video_adapter_warnings"] = list(req.get("native_video_adapter_warnings") or []) + warnings
    return graph


def _resolve_native_video_stack(req: dict[str, Any], object_info: dict[str, Any], family: str):
    """Producer-side component resolution for a native-VIDEO family via the generic engine -- the
    video analog of _resolve_native_image_stack. FIRST used by HunyuanVideo: it proves
    component_resolver.resolve_stack (the image path's core) works for a video family too. The video
    family's contract required_components are passed as the floor so the readiness gate matches the
    contract. Wan/LTX keep their inline resolvers for now; unifying the whole video run path onto this
    is what the deferred family-plugin decomposition inherits (Hunyuan is the reference implementation).
    """
    from component_resolver import resolve_stack
    fam = str(family or "").strip().lower()
    try:
        from video_family_contracts import VIDEO_FAMILY_CONTRACTS
        contract = VIDEO_FAMILY_CONTRACTS.get(fam)
        contract_required = contract.required_components if contract else None
    except Exception:
        contract_required = None
    primary = str(req.get("model") or "")
    stack = req.get("stack") if isinstance(req.get("stack"), dict) else {}
    return resolve_stack(
        primary,
        family=fam,
        requested_family=fam,
        stack=stack,
        req=req,
        task=str(req.get("command") or req.get("task_type") or "t2v").strip().lower(),
        choices_for=lambda cls, inp: _comfy_input_choices(object_info, cls, inp),
        contract_required=contract_required,
    )


def _build_native_hunyuan_video_prompt(req: dict[str, Any], object_info: dict[str, Any], *,
                                       command: str, family: str, job_id: str) -> dict[str, Any]:
    """HunyuanVideo T2V native graph (build-order #4). The FIRST video builder to thread the GENERIC
    component resolver (_resolve_native_video_stack -> component_resolver.resolve_stack) rather than
    family-private resolvers -- the video path's proof that the image core works for video. GROUNDED
    from the official hunyuan_video_text_to_video.json blueprint: the dual encoder loads via ONE
    DualCLIPLoader(type="hunyuan_video", clip_l + llava) -- like Flux, not two CLIPLoaders -- then
    ModelSamplingSD3(shift 7) + FluxGuidance (cfg MAPPED, NON-distilled, not pinned) feed the
    SamplerCustomAdvanced chain (RandomNoise / BasicGuider / KSamplerSelect(euler) / BasicScheduler
    (simple)); EmptyHunyuanLatentVideo -> VAEDecodeTiled -> CreateVideo -> SaveVideo. Companions are
    resolver-driven (llava precision-matched to the transformer dtype + clip_l + hunyuan vae).
    Render-proven clean (STEP 0). I2V is NOT wired this pass: the on-disk i2v checkpoint is the
    ORIGINAL HunyuanVideo model, but the only i2v blueprint is HunyuanVideo 1.5 (a version fork) --
    run_native_split_stack_video's i2v carve-out refuses it cleanly; a dedicated i2v grounding pass owns it.
    """
    if command == "i2v":
        # i2v GROUNDED graph (v1 "concat"), constructed verbatim from ComfyUI_examples/hunyuan_video/
        # hunyuan_video_image_to_video.json: CLIPVisionLoader(llava_llama3_vision) -> CLIPVisionEncode ->
        # TextEncodeHunyuanVideo_ImageToVideo(clip_vision_output) -> HunyuanImageToVideo(start_image,
        # guidance_type="v1 (concat)") -> [positive, latent] into the shared SamplerCustomAdvanced chain.
        # The registry-plugin seam CONSTRUCTS this as the first new i2v spec instance (validated against
        # the grounded source). RENDER stays deferred behind a GATED ComfyUI update: CLIPVisionEncode's
        # 768-vs-1024 projection on llava_llama3_vision is a stale-build regression (the on-disk file is
        # byte-identical to canonical Comfy-Org, sha256 7d0f89bf...), NOT a wiring bug. The render gate
        # lives downstream in run_native_split_stack_video, not here.
        i2v_model_path = str(req.get("model") or "")
        i2v_unet_name = _comfy_unet_name_for_model(object_info, i2v_model_path)
        if not i2v_unet_name:
            raise RuntimeError(
                f"HunyuanVideo transformer is not visible to ComfyUI UNETLoader: {i2v_model_path!r} (must be under diffusion_models/)."
            )
        i2v_resolved = _resolve_native_video_stack(req, object_info, "hunyuan_video")
        i2v_missing = [s.component for s in i2v_resolved.missing_required()]
        if i2v_missing:
            raise RuntimeError(
                "HunyuanVideo stack incomplete -- missing required component(s): " + ", ".join(i2v_missing)
                + ". The resolver found no valid on-disk file for them; resolve or download before generating."
            )
        i2v_clip_l = i2v_resolved.value("text_encoder_clip_l") or "clip_l.safetensors"
        i2v_llava = i2v_resolved.value("text_encoder") or "llava_llama3_fp16.safetensors"
        i2v_vae = i2v_resolved.value("vae") or "hunyuan_video_vae_bf16.safetensors"
        # clip_vision: the i2v-only optional companion (manifest applies_to_tasks:["i2v"]); default to
        # the grounded canonical file when the resolver has none.
        i2v_clip_vision = i2v_resolved.value("clip_vision") or "llava_llama3_vision.safetensors"
        i2v_image = str(req.get("input_image_comfy_name") or req.get("input_image") or "").strip()

        def _i2v_snap(value: Any, default: int, mult: int) -> int:
            try:
                v = int(value)
            except Exception:
                v = default
            return max(mult, v - (v % mult))

        i2v_prompt = str(req.get("prompt") or "")
        i2v_width = _i2v_snap(req.get("width"), 848, 16)
        i2v_height = _i2v_snap(req.get("height"), 480, 16)
        try:
            i2v_raw_len = int(req.get("length") or req.get("num_frames") or 73)
        except Exception:
            i2v_raw_len = 73
        i2v_length = ((max(5, i2v_raw_len) - 1) // 4) * 4 + 1   # Hunyuan /4 temporal: (N*4)+1
        _i2v_defaults = operating_point_params("hunyuan_video", "default")
        try:
            i2v_steps = int(req.get("steps") or _i2v_defaults.get("steps") or 20)
        except Exception:
            i2v_steps = 20
        if i2v_steps < 1:
            i2v_steps = 20
        try:
            i2v_guidance = float(str(req.get("cfg") or "").strip() or _i2v_defaults.get("cfg") or 6.0)
        except Exception:
            i2v_guidance = 6.0
        if i2v_guidance <= 0:
            i2v_guidance = 6.0
        try:
            i2v_fps = float(req.get("fps") or 24.0)
        except Exception:
            i2v_fps = 24.0
        try:
            i2v_seed = int(req.get("seed")) if str(req.get("seed") or "").strip() not in {"", "None"} else 0
        except Exception:
            i2v_seed = 0
        i2v_shift = 7.0
        i2v_prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)

        return {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": i2v_unet_name, "weight_dtype": "default"}},
            "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": i2v_clip_l, "clip_name2": i2v_llava, "type": "hunyuan_video", "device": "default"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": i2v_vae}},
            "16": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": i2v_clip_vision}},
            "17": {"class_type": "LoadImage", "inputs": {"image": i2v_image}},
            "18": {"class_type": "CLIPVisionEncode", "inputs": {"clip_vision": ["16", 0], "image": ["17", 0], "crop": "none"}},
            "4": {"class_type": "TextEncodeHunyuanVideo_ImageToVideo", "inputs": {"clip": ["2", 0], "clip_vision_output": ["18", 0], "prompt": i2v_prompt, "image_interleave": 2}},
            "19": {"class_type": "HunyuanImageToVideo", "inputs": {"positive": ["4", 0], "vae": ["3", 0], "start_image": ["17", 0], "width": i2v_width, "height": i2v_height, "length": i2v_length, "batch_size": 1, "guidance_type": "v1 (concat)"}},
            "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["19", 0], "guidance": i2v_guidance}},
            "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": i2v_shift}},
            "7": {"class_type": "BasicGuider", "inputs": {"model": ["6", 0], "conditioning": ["5", 0]}},
            "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "9": {"class_type": "BasicScheduler", "inputs": {"model": ["6", 0], "scheduler": "simple", "steps": i2v_steps, "denoise": 1.0}},
            "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": i2v_seed}},
            "12": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["10", 0], "guider": ["7", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["19", 1]}},
            "13": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["12", 0], "vae": ["3", 0], "tile_size": 256, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
            "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": i2v_fps}},
            "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": i2v_prefix, "format": "auto", "codec": "auto"}},
        }
    model_path = str(req.get("model") or "")
    unet_name = _comfy_unet_name_for_model(object_info, model_path)
    if not unet_name:
        raise RuntimeError(
            f"HunyuanVideo transformer is not visible to ComfyUI UNETLoader: {model_path!r} (must be under diffusion_models/)."
        )
    resolved = _resolve_native_video_stack(req, object_info, "hunyuan_video")
    missing = [s.component for s in resolved.missing_required()]
    if missing:
        raise RuntimeError(
            "HunyuanVideo stack incomplete -- missing required component(s): " + ", ".join(missing)
            + ". The resolver found no valid on-disk file for them; resolve or download before generating."
        )
    clip_l = resolved.value("text_encoder_clip_l") or "clip_l.safetensors"
    llava = resolved.value("text_encoder") or "llava_llama3_fp16.safetensors"   # precision-matched
    vae = resolved.value("vae") or "hunyuan_video_vae_bf16.safetensors"

    def _snap(value: Any, default: int, mult: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        return max(mult, v - (v % mult))

    prompt = str(req.get("prompt") or "")
    width = _snap(req.get("width"), 848, 16)
    height = _snap(req.get("height"), 480, 16)
    # Hunyuan temporal compression is /4 -> frame length must be (N*4)+1 (73/61/49...).
    try:
        raw_len = int(req.get("length") or req.get("num_frames") or 73)
    except Exception:
        raw_len = 73
    length = ((max(5, raw_len) - 1) // 4) * 4 + 1
    # Phase 2a: steps/cfg defaults lifted to the table (shift=7 below stays a hardcoded constant --
    # not a req-fallback -- so it is only recorded in the table, not routed).
    _defaults = operating_point_params("hunyuan_video", "default")
    try:
        steps = int(req.get("steps") or _defaults.get("steps") or 20)
    except Exception:
        steps = 20
    if steps < 1:
        steps = 20  # standard (non-distilled); blueprint default 20, honor the cockpit otherwise
    try:
        guidance = float(str(req.get("cfg") or "").strip() or _defaults.get("cfg") or 6.0)
    except Exception:
        guidance = 6.0
    if guidance <= 0:
        guidance = 6.0  # cfg MAPPED -> FluxGuidance (blueprint 6); NOT pinned (Hunyuan is non-distilled)
    try:
        fps = float(req.get("fps") or 24.0)
    except Exception:
        fps = 24.0
    try:
        seed = int(req.get("seed")) if str(req.get("seed") or "").strip() not in {"", "None"} else 0
    except Exception:
        seed = 0
    shift = 7.0  # ModelSamplingSD3 shift (grounded from the blueprint)
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)

    graph: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": clip_l, "clip_name2": llava, "type": "hunyuan_video", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": guidance}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": shift}},
        "7": {"class_type": "BasicGuider", "inputs": {"model": ["6", 0], "conditioning": ["5", 0]}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "BasicScheduler", "inputs": {"model": ["6", 0], "scheduler": "simple", "steps": steps, "denoise": 1.0}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "11": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {"width": width, "height": height, "length": length, "batch_size": 1}},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["10", 0], "guider": ["7", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["11", 0]}},
        "13": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["12", 0], "vae": ["3", 0], "tile_size": 256, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": fps}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}},
    }
    return graph


# ---------------------------------------------------------------------------
# FamilySpec registry-plugin seam (god-file decomposition, pure structural).
#
# The per-family graph construction was inline if/elif branching inside
# _build_native_split_video_prompt (video) and _build_native_image_prompt (image).
# This seam extracts that branching into a data registry of NativeFamilyPlugin
# entries whose `build` callable is the EXACT existing per-family builder. Routing
# a family "through the seam" means the dispatcher looks the plugin up and invokes
# `build` instead of running its inline branch -- byte-identical by construction.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class NativeFamilyPlugin:
    """One registry entry: a family's spec-key + its graph builder.

    kind='image' -> build(req, object_info, job_id, resolved) -> graph
    kind='video' -> build(req, object_info, *, command, family, job_id) -> graph | None
      (None signals "matched the family but no sub-route fired" -> the dispatcher
       falls through to the generic native-video fallback, exactly as the inline
       wan branch did.)
    match_prefix (video only) matches _infer_native_video_family_key via startswith.
    """
    family: str
    kind: str
    build: Callable[..., Any]
    match_prefix: str = ""


def _hunyuan_video_build(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str):
    req["resolved_native_video_family"] = "hunyuan_video"
    req["native_video_route"] = "hunyuan_template"
    return _build_native_hunyuan_video_prompt(req, object_info, command=command, family=family, job_id=job_id)


def _wan_video_build(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str):
    req["resolved_native_video_family"] = "wan"
    # Wan 2.2 A14B dual-noise (MoE) T2V: two experts + two-stage sampler. Routed BEFORE the
    # single-model core/wrapper checks and ONLY for t2v with both experts present -- single-model
    # Wan (and i2v) keep their existing core/wrapper routing unchanged.
    if (
        command == "t2v"
        and _is_wan_dual_noise_request(req)
        and "UNETLoader" in object_info
        and "KSamplerAdvanced" in object_info
    ):
        req["native_video_route"] = "wan_dual_noise"
        return _build_native_wan_dual_noise_video_prompt(req, object_info, command=command, family=family, job_id=job_id)
    if _should_use_native_wan_core_route(req, object_info) and "CLIPLoader" in object_info and "KSamplerAdvanced" in object_info:
        req["native_video_route"] = "wan_core"
        return _build_native_wan_core_video_prompt(req, object_info, command=command, family=family, job_id=job_id)
    if "WanVideoModelLoader" in object_info:
        req["native_video_route"] = "wan_wrapper"
        return _build_native_wan_split_video_prompt(req, object_info, command=command, family=family, job_id=job_id)
    return None  # no wan sub-route matched -> fall through to the generic fallback


def _ltx_video_build(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str):
    req["resolved_native_video_family"] = "ltx"
    req["native_video_route"] = "ltx_template"
    return _build_native_ltx_video_prompt(req, object_info, command=command, family=family, job_id=job_id)


# Ordered by the original if-chain precedence; matched via family_key.startswith(match_prefix).
NATIVE_VIDEO_FAMILY_PLUGINS: tuple[NativeFamilyPlugin, ...] = (
    NativeFamilyPlugin(family="hunyuan_video", kind="video", build=_hunyuan_video_build, match_prefix="hunyuan"),
    NativeFamilyPlugin(family="wan", kind="video", build=_wan_video_build, match_prefix="wan"),
    NativeFamilyPlugin(family="ltx", kind="video", build=_ltx_video_build, match_prefix="ltx"),
)


def _native_video_plugin_for(family_key: str) -> "NativeFamilyPlugin | None":
    for plugin in NATIVE_VIDEO_FAMILY_PLUGINS:
        if plugin.match_prefix and family_key.startswith(plugin.match_prefix):
            return plugin
    return None


def _build_native_split_video_prompt(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
    job_id: str,
) -> dict[str, Any]:
    family_key = _infer_native_video_family_key(req, family)
    _raise_if_unvalidated_native_video_family(family_key, command=command)
    # STAGE 2b: the inline hunyuan/wan/ltx branching is fully replaced by the registry-plugin seam.
    # _native_video_plugin_for matches family_key.startswith(match_prefix) in the original if-chain
    # order; build returns None only for wan's no-sub-route case -> fall through to the generic fallback.
    video_plugin = _native_video_plugin_for(family_key)
    if video_plugin is not None:
        graph = video_plugin.build(req, object_info, command=command, family=family, job_id=job_id)
        if graph is not None:
            return graph

    # GENERIC unknown-family fallback: no hunyuan/wan/ltx builder matched. Make it OBSERVABLE -- these
    # defaults are REASONED (aligned to the validated video shape) but NOT render-validated for this
    # specific model. logging.info is filtered at the worker's root WARNING level, so this is a warning.
    _defaults = operating_point_params("native_split_generic", "default")
    req["native_video_route"] = "generic_fallback"
    logging.warning(
        "No specific native-video builder matched video family %r; using the GENERIC fallback "
        "(cfg=%s sampler=%s scheduler=%s shift=%s) -- these defaults are reasoned, not validated for this model.",
        family_key, _defaults.get("cfg"), _defaults.get("sampler"), _defaults.get("scheduler"), _defaults.get("shift"),
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
    # Defaults come from the native_split_generic table row (resolved above, with the generic-fallback
    # warning). The inline literals here are the last-resort safety net if that row is ever removed;
    # retuned to match the row (was cfg 7.0 / dpmpp_2m / karras / shift 8.0).
    steps = int(req.get("steps") or _defaults.get("steps") or 30)
    cfg = float(req.get("cfg") or req.get("cfg_scale") or _defaults.get("cfg") or 4.5)
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
    _set_if_allowed(inputs, allowed, ("vae_name", "vae"), _preferred_video_vae_name(object_info, family, vae_path, primary_path))
    _add_node(prompt, "3", vae_class, inputs)

    model_link: list[Any] = ["1", 0]
    if "ModelSamplingSD3" in object_info:
        allowed = _comfy_class_inputs(object_info, "ModelSamplingSD3")
        inputs = {}
        _set_if_allowed(inputs, allowed, ("model",), model_link)
        _set_if_allowed(inputs, allowed, ("shift",), float(req.get("sampling_shift") or req.get("shift") or _defaults.get("shift") or 5.0))
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
    _set_if_allowed(inputs, allowed, ("sampler_name", "sampler"), str(req.get("sampler") or _defaults.get("sampler") or "euler"))
    _set_if_allowed(inputs, allowed, ("scheduler",), str(req.get("scheduler") or _defaults.get("scheduler") or "simple"))
    _set_if_allowed(inputs, allowed, ("denoise",), float(req.get("denoise") or _defaults.get("denoise") or 1.0))
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

def _canonical_native_video_family(family: str) -> str:
    return normalize_video_family_id(family)


def _raise_if_unvalidated_native_video_family(family: str, *, command: str) -> None:
    canonical = _canonical_native_video_family(family)
    contract = video_family_contract(canonical)
    if contract.production_ready:
        return
    raise RuntimeError(
        f"{command.upper()} native video is production-enabled only for families marked production in the video family registry. "
        f"Resolved family '{canonical}' is {contract.validation_status}; {contract.display_name} is not validated end-to-end yet. "
        "Use the production Wan video stack or run this family through an imported Comfy workflow/profile until it has its own validation pass."
    )


def run_native_split_stack_video(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    command = str(req.get("command") or req.get("task_type") or "").strip().lower()
    family = _infer_native_video_family(req)
    _raise_if_unvalidated_native_video_family(family, command=command)
    if command not in {"t2v", "i2v"}:
        raise RuntimeError(f"Native split-stack video only supports t2v/i2v, got {command!r}.")
    if command == "i2v" and not (str(family).lower().startswith("ltx") or str(family).lower().startswith("wan")):
        # LTX i2v and native single-model Wan i2v ARE wired: LTX via its embedded
        # LoadImage->...->LTXVImgToVideoConditionOnly chain; Wan via the core builder's
        # WanImageToVideo branch. Both use the keyframe upload bridge below. Other families
        # have no native image-conditioning graph, so they stay blocked.
        raise RuntimeError("Native split-stack I2V templates are not wired yet for this family. Use a compiled I2V Comfy workflow for now.")

    transition_job(job, JobState.STARTING)
    emitter.status(job, "starting Comfy runtime for native split-stack video")
    emitter.emit_job_update(job)
    runtime_prep = prepare_runtime_for_request(req, emitter, job)

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
    emitter.status(job, "building native Wan split-stack Comfy template")
    object_info = _comfy_object_info(api_url)
    req = _prepare_native_video_adapter_request(req, object_info, command=command, family=family)

    family = str(req.get("resolved_native_video_family") or req.get("video_family") or req.get("model_family") or family)

    # Native i2v (LTX + Wan): the keyframe must live in ComfyUI's input dir for LoadImage
    # (a COMBO of input-dir files) to reference it. Upload it now and stash the Comfy-side
    # name for the builder. Only families carved-in above reach here; if i2v is requested
    # but no image resolves, the builder falls back to t2v rather than emitting a 400.
    if command == "i2v" and (str(family).lower().startswith("ltx") or str(family).lower().startswith("wan")):
        local_image = video_input_image_for_request(req)
        if local_image:
            raise_if_cancelled(active_job, emitter, "i2v keyframe upload")
            uploaded = _upload_comfy_image(api_url, local_image)
            req["input_image_comfy_name"] = _comfy_image_ref(uploaded)
            emitter.status(job, f"uploaded i2v keyframe to ComfyUI: {req['input_image_comfy_name']}")
        else:
            emitter.status(job, "i2v requested but no input image resolved; falling back to t2v")

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
        "metadata_write_deferred": False,
        **output_finalization_contract(output_path if 'output_path' in locals() else req.get("output"), metadata_output if 'metadata_output' in locals() else req.get("metadata_output"), original_output=str(req.get("original_output") or ""), media_type=output_media_type_for_metadata(req, output_path if 'output_path' in locals() else req.get("output")), metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"), metadata_write_error=metadata_payload.get("metadata_write_error")),
        **runtime_prep_metadata(req),
        "comfy_runtime_endpoint": runtime_status.get("endpoint"),
        "comfy_runtime_pid": runtime_status.get("pid"),
        "native_template": True,
    }
    payload.update(video_completion_diagnostics(
        req,
        backend_type="native_video",
        backend_name=str(payload.get("backend_name") or "SpellVisionNativeComfyTemplate"),
        output_path=output_path,
        metadata_output=metadata_output,
        prompt_id=prompt_id,
    ))
    video_cache_update = update_video_runtime_cache_from_result(req, payload)
    if video_cache_update:
        payload["video_runtime_cache_updated"] = True
        payload["video_runtime_cache"] = video_cache_update
    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


# ============================================================================
# Native IMAGE path (route B, Flux-B / B-img1). The `native_comfy_template` path
# existed only for VIDEO (run_native_video). Flux single-file transformers can't be
# loaded by diffusers from_single_file without the gated FLUX.1-dev config/tokenizers
# (fresh-machine STOP, proven live), but ComfyUI's UNETLoader/DualCLIPLoader/VAELoader
# eat the on-disk single-file format natively with zero downloads. So Flux renders
# through a ComfyUI graph, mirroring run_native_split_stack_video but producing a PNG.
# B-img1 = the scaffold with a HAND-CODED Flux graph + FIXED companions; the grounded
# template + resolve_stack (Flux-A) precision-matched companions + readiness are B-img2.
# ============================================================================

def _comfy_ckpt_name_for_model(object_info: dict[str, Any], model_path: str) -> str:
    """Map a local checkpoint path to the exact CheckpointLoaderSimple.ckpt_name combo entry.

    ComfyUI lists checkpoints as subdir-qualified names (e.g. "flux\\fluxmania_kreamania.safetensors").
    We match by basename against the live /object_info choices so the graph references the name the
    loader actually expects (separator + subdir included), not the absolute path.
    """
    base = Path(str(model_path or "").replace("\\", "/")).name.strip().lower()
    if not base:
        return ""
    node = object_info.get("CheckpointLoaderSimple") or {}
    spec = ((node.get("input") or {}).get("required") or {}).get("ckpt_name")
    choices = spec[0] if isinstance(spec, list) and spec and isinstance(spec[0], list) else []
    for c in choices:
        if Path(str(c).replace("\\", "/")).name.strip().lower() == base:
            return str(c)
    return ""


def _comfy_unet_name_for_model(object_info: dict[str, Any], model_path: str) -> str:
    """UNETLoader sibling of _comfy_ckpt_name_for_model, for split-stack families (Z-Image, ...) whose
    transformer lives in diffusion_models/ and loads via UNETLoader.unet_name -- NOT CheckpointLoaderSimple.
    Match by basename against the live /object_info UNETLoader choices (subdir + separator included).
    """
    base = Path(str(model_path or "").replace("\\", "/")).name.strip().lower()
    if not base:
        return ""
    node = object_info.get("UNETLoader") or {}
    spec = ((node.get("input") or {}).get("required") or {}).get("unet_name")
    choices = spec[0] if isinstance(spec, list) and spec and isinstance(spec[0], list) else []
    for c in choices:
        if Path(str(c).replace("\\", "/")).name.strip().lower() == base:
            return str(c)
    return ""


# Families that render through the ComfyUI-native image path (route B) instead of diffusers. Each
# needs a per-family graph builder in _build_native_image_prompt; the resolve/route/T3/dispatch
# scaffold below is family-general. Registering a new native-image family = add it here + a manifest
# row (model_dependency_manifest) + a builder branch. (Flux: transformer can't load via diffusers
# from_single_file w/o the gated config; PixArt: has a distinct ComfyUI-native DiT graph.)
NATIVE_IMAGE_FAMILIES = {"flux", "pixart", "lumina", "z_image", "anima"}


def _native_image_family(req: dict[str, Any]) -> str:
    """Classified family for native-image routing (metadata -> request tag -> directory -> filename),
    the same classifier the rest of the worker uses. Empty string if unresolvable."""
    model = str(req.get("model") or "").strip()
    if not model:
        return ""
    try:
        from model_classification import classify_model
        return (classify_model(model, requested_family=req.get("model_family")).family or "").strip().lower()
    except Exception:
        return str(req.get("model_family") or "").strip().lower()


def _resolve_native_image_stack(req: dict[str, Any], object_info: dict[str, Any], family: str):
    """Producer-side component resolution for a native-image family (Doc 19 §6). FAMILY-GENERAL:
    resolve_stack against the on-disk ComfyUI choices, keyed on the classified family (flux / pixart /
    ...). Image mode has no A2 cockpit auto-populate, so the loader resolves worker-side. choices_for
    is _comfy_input_choices == EXACTLY the files ComfyUI can reference in the graph, so the resolver's
    choice set never diverges from what actually loads. Precision-matched companions (e.g. T5 to the
    transformer dtype) come from the family's manifest row.
    """
    from component_resolver import resolve_stack
    primary = str(req.get("model") or "")
    stack = req.get("stack") if isinstance(req.get("stack"), dict) else {}
    fam = str(family or "").strip().lower()
    return resolve_stack(
        primary,
        family=fam,
        requested_family=fam,
        stack=stack,
        req=req,
        task=str(req.get("command") or req.get("task_type") or "t2i").strip().lower(),
        choices_for=lambda cls, inp: _comfy_input_choices(object_info, cls, inp),
    )


def _flux_guidance_from_request(req: dict[str, Any]) -> float:
    """Cockpit 'cfg' -> Flux distilled guidance (FluxGuidance.guidance); KSampler cfg stays pinned 1.0.

    Flux uses distilled guidance, not real classifier-free guidance, so the user-facing cfg slider
    drives the FluxGuidance node. Falls back to 3.5 (the Flux sweet spot) when cfg is absent/<=0.
    (The cockpit default cfg ~6.5 is SDXL-tuned and reads a bit high for Flux; a Simple-mode Flux
    default is a later tuning item, not a correctness issue.)
    """
    raw = req.get("cfg")
    if raw is None:
        raw = req.get("guidance")
    try:
        g = float(raw) if raw is not None else 0.0
    except Exception:
        g = 0.0
    return g if g > 0 else 3.5


def _flux_denoise_from_request(req: dict[str, Any]) -> float:
    """Cockpit i2i strength -> Flux KSampler.denoise, REMAPPED onto a higher band.

    Empirically (2x2 prompt x input swap at denoise 0.9, warmth = mean(R-B)): i2i lets the SUBJECT
    follow the prompt but the OUTPUT TONE is dominated by the INPUT's palette at moderate denoise -- a
    warm input yields warm outputs and a cool input cool outputs, REGARDLESS of the prompt's color
    words. (Same beach prompt: a WARM beach on a warm input, a COOL beach on a cool input; a "cold
    blue winter" prompt on a warm input still comes out warm.) So a prompt whose palette opposes the
    input looks like it "didn't apply". TESTED mechanism (denoise sweep + steps-isolation): the tone
    is carried by the RETAINED INPUT LATENT, not sampling -- at fixed denoise 0.85, 20 vs 60 steps
    give the same warmth (+69.0 / +67.9), ruling out step-count. And it is FREQUENCY-DEPENDENT, not
    proportional: warmth stays pinned to the input (~+69) across denoise 0.4-0.9 while MAE/structure
    rises smoothly (9->20), then tone CLIFFS (0.95 -> +48, 1.0 -> -85). So the prompt rewrites
    high-freq STRUCTURE at moderate denoise while the input's low-freq TONE survives almost to denoise
    1.0. Remapping strength [0,1] -> denoise ~[0.55, 1.0] therefore makes STRUCTURE/detail edits
    responsive across the whole slider, but a palette INVERSION still needs strength -> near-max
    (denoise >~0.95, where the input is nearly ignored) -- a fundamental i2i limit here, not something
    the remap overcomes. Flux-native path only; SDXL i2i (the separate
    diffusers run_i2i) keeps the literal strength=denoise mapping. NOTE: this is INPUT-PALETTE
    DOMINANCE, not prompt-strength and not subject-overlap -- both were falsified by the swap test.
    """
    raw = req.get("strength")
    if raw is None:
        raw = req.get("denoise")
    try:
        s = float(raw) if raw is not None else -1.0
    except Exception:
        s = -1.0
    if not (0.0 <= s <= 1.0):
        s = 0.6  # sensible default strength when absent/out-of-range
    return round(0.55 + 0.45 * s, 4)  # [0,1] strength -> [0.55, 1.0] Flux denoise


def _build_flux_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                             resolved: Any) -> dict[str, Any]:
    """Grounded Flux t2i graph. Companions come from resolve_stack (precision-matched T5), NOT
    hardcoded; cockpit cfg -> FluxGuidance.guidance. Structure is B-img1's proven live binding
    (DualCLIPLoader clip_name1=clip_l / clip_name2=T5 / type=flux, FluxGuidance, EmptySD3LatentImage);
    only the filenames are supplied by the resolver.
    """
    model_path = str(req.get("model") or "")
    ckpt_name = _comfy_ckpt_name_for_model(object_info, model_path)
    if not ckpt_name:
        raise RuntimeError(
            f"Flux checkpoint is not visible to ComfyUI CheckpointLoaderSimple: {model_path!r}. "
            "It must live under the ComfyUI checkpoints path."
        )
    # Resolver-driven companions (precision-matched T5). The canonical-name fallbacks only guard a
    # slot that resolved empty WITHOUT being flagged missing; the T3 gate in run_native_image is the
    # real completeness guard.
    clip_l = resolved.value("text_encoder") or "clip_l.safetensors"
    t5 = resolved.value("text_encoder_2") or "t5xxl_fp16.safetensors"
    vae = resolved.value("vae") or "ae.safetensors"

    def _snap16(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 16)  # Flux latent (16ch, /8 VAE + /2 patch) needs dims divisible by 16

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")
    width = _snap16(req.get("width"), 1024)
    height = _snap16(req.get("height"), 1024)
    # Phase 2b: steps default lifted to the table (flux_image). cfg is PINNED 1.0 + FluxGuidance
    # mapping and sampler/scheduler are hardcoded euler/simple -- recorded in the table, NOT routed.
    _defaults = operating_point_params("flux_image", "default")
    try:
        steps = max(1, int(req.get("steps") or _defaults.get("steps") or 20))
    except Exception:
        steps = 20
    try:
        seed = int(req.get("seed")) if str(req.get("seed") or "").strip() not in {"", "None"} else 0
    except Exception:
        seed = 0
    guidance = _flux_guidance_from_request(req)  # cockpit cfg -> FluxGuidance.guidance
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    is_i2i = str(req.get("command") or req.get("task_type") or "").strip().lower() == "i2i"

    # Shared Flux stack (resolver-driven companions, precision-matched T5, cfg->guidance) -- identical
    # for t2i and i2i. Only the LATENT SOURCE + KSampler denoise differ between the two.
    graph: dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {
            "clip_name1": clip_l, "clip_name2": t5, "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": guidance}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }
    if is_i2i:
        # i2i: uploaded input image -> LoadImage -> VAEEncode -> latent. denoise < 1.0 is what makes
        # the output conditioned on the input (1.0 would ignore it = a from-scratch render).
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("Flux i2i graph requires an uploaded input image (input_image_comfy_name).")
        denoise = _flux_denoise_from_request(req)  # cockpit strength -> KSampler.denoise
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["3", 0]}}
        latent_ref: list[Any] = ["12", 0]
    else:
        graph["7"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["1", 0], "seed": seed, "steps": steps, "cfg": 1.0,
        "sampler_name": "euler", "scheduler": "simple",
        "positive": ["5", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph


def _build_pixart_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                               resolved: Any) -> dict[str, Any]:
    """PixArt-Sigma t2i/i2i graph -- grounded live + render-proven (STEP 0). Architecturally distinct
    from Flux: transformer via CheckpointLoaderSimple, T5 via CLIPLoader(type="pixart"), the SDXL 4-ch
    VAE, CLIPTextEncodePixArtAlpha (resolution-aware, takes width/height), and REAL classifier-free
    guidance (KSampler.cfg), NOT the Flux DualCLIP+FluxGuidance graph. Companions are resolver-driven
    (resolved.value), same provenance as the Flux builder.
    """
    model_path = str(req.get("model") or "")
    ckpt_name = _comfy_ckpt_name_for_model(object_info, model_path)
    if not ckpt_name:
        raise RuntimeError(
            f"PixArt checkpoint is not visible to ComfyUI CheckpointLoaderSimple: {model_path!r}."
        )
    t5 = resolved.value("text_encoder") or "t5xxl_fp16.safetensors"   # precision-matched via manifest
    vae = resolved.value("vae") or "sdxl_vae.safetensors"

    def _snap8(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 8)  # SD/SDXL 4-ch VAE latent is /8

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")
    width = _snap8(req.get("width"), 1024)
    height = _snap8(req.get("height"), 1024)
    _defaults = operating_point_params("pixart_image", "default")  # Phase 2b: steps/cfg lifted (sampler/scheduler pinned)
    try:
        steps = max(1, int(req.get("steps") or _defaults.get("steps") or 20))
    except Exception:
        steps = 20
    try:
        seed = int(req.get("seed")) if str(req.get("seed") or "").strip() not in {"", "None"} else 0
    except Exception:
        seed = 0
    try:
        cfg = float(req.get("cfg") or _defaults.get("cfg") or 4.5)  # PixArt uses REAL CFG (unlike Flux's pinned 1.0 + FluxGuidance)
    except Exception:
        cfg = 4.5
    if cfg <= 0:
        cfg = 4.5
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    is_i2i = str(req.get("command") or req.get("task_type") or "").strip().lower() == "i2i"

    graph: dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": t5, "type": "pixart"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncodePixArtAlpha", "inputs": {"width": width, "height": height, "text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncodePixArtAlpha", "inputs": {"width": width, "height": height, "text": negative, "clip": ["2", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }
    if is_i2i:
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("PixArt i2i graph requires an uploaded input image (input_image_comfy_name).")
        # Literal strength->denoise (NOT the Flux remap -- that was calibrated to Flux's measured
        # input-tone dominance; PixArt uses real CFG + real negative and its i2i behavior is untested).
        try:
            denoise = float(req.get("strength")) if str(req.get("strength") or "").strip() not in {"", "None"} else 0.0
        except Exception:
            denoise = 0.0
        if not (0.0 < denoise <= 1.0):
            denoise = 0.6
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["3", 0]}}
        latent_ref: list[Any] = ["12", 0]
    else:
        graph["7"] = {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["1", 0], "seed": seed, "steps": steps, "cfg": cfg,
        "sampler_name": "euler", "scheduler": "normal",
        "positive": ["4", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph


def _build_lumina_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                               resolved: Any) -> dict[str, Any]:
    """Lumina Image 2.0 t2i/i2i graph -- grounded live + render-proven (STEP 0). The all-in-one
    lumina_2 checkpoint BAKES the VAE, so VAEDecode/VAEEncode use CheckpointLoaderSimple's VAE output
    (["1",2]) -- NO VAELoader. The Gemma-2-2B text encoder IS resolver-driven (separate
    CLIPLoader(type=lumina2), size-specific predicate excludes LTX's gemma_3_12B). Distinct from
    Flux/PixArt: sigma shift via ModelSamplingAuraFlow, CLIPTextEncodeLumina2 (system_prompt="superior"
    handles Lumina's prompt convention -- no manual prefix), res_multistep sampler, real cfg.
    """
    model_path = str(req.get("model") or "")
    ckpt_name = _comfy_ckpt_name_for_model(object_info, model_path)
    if not ckpt_name:
        raise RuntimeError(f"Lumina checkpoint is not visible to ComfyUI CheckpointLoaderSimple: {model_path!r}.")
    gemma = resolved.value("text_encoder") or "gemma_2_2b_fp16.safetensors"   # size-specific gemma_2_2b

    def _snap16(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 16)  # Lumina uses the 16-ch VAE latent (EmptySD3LatentImage), /16 like Flux

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")
    width = _snap16(req.get("width"), 1024)
    height = _snap16(req.get("height"), 1024)
    _defaults = operating_point_params("lumina_image", "default")  # Phase 2b: steps/cfg lifted (shift 6.0 + sampler/scheduler pinned)
    try:
        steps = max(1, int(req.get("steps") or _defaults.get("steps") or 30))
    except Exception:
        steps = 30
    try:
        seed = int(req.get("seed")) if str(req.get("seed") or "").strip() not in {"", "None"} else 0
    except Exception:
        seed = 0
    try:
        cfg = float(req.get("cfg") or _defaults.get("cfg") or 4.0)  # Lumina uses REAL cfg
    except Exception:
        cfg = 4.0
    if cfg <= 0:
        cfg = 4.0
    shift = 6.0  # Lumina 2.0 sigma shift (official regime; render-proven clean at shift 6 / res_multistep)
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    is_i2i = str(req.get("command") or req.get("task_type") or "").strip().lower() == "i2i"

    graph: dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": gemma, "type": "lumina2"}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": shift}},
        "4": {"class_type": "CLIPTextEncodeLumina2", "inputs": {"system_prompt": "superior", "user_prompt": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncodeLumina2", "inputs": {"system_prompt": "superior", "user_prompt": negative, "clip": ["2", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},  # baked VAE from checkpoint
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }
    if is_i2i:
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("Lumina i2i graph requires an uploaded input image (input_image_comfy_name).")
        try:
            denoise = float(req.get("strength")) if str(req.get("strength") or "").strip() not in {"", "None"} else 0.0
        except Exception:
            denoise = 0.0
        if not (0.0 < denoise <= 1.0):
            denoise = 0.6
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["1", 2]}}  # baked VAE
        latent_ref: list[Any] = ["12", 0]
    else:
        graph["7"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["5", 0], "seed": seed, "steps": steps, "cfg": cfg,  # model = the shifted MODEL from node 5
        "sampler_name": "res_multistep", "scheduler": "normal",
        "positive": ["4", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph


def _build_zimage_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                               resolved: Any) -> dict[str, Any]:
    """Z-Image Turbo t2i/i2i graph -- the FIRST split-stack image family (STEP 0, render-proven). The
    transformer loads via UNETLoader (diffusion_models/, NOT CheckpointLoaderSimple); the Qwen-3-4B
    encoder + Flux ae VAE are EXTERNAL, resolver-driven. Distilled Turbo: cfg is PINNED at 1.0 (CFG is
    baked in -- the cockpit's SDXL-tuned cfg 6.5 would over-cook) and steps default to 4 (the official
    Turbo NFE), ignoring the SDXL-default 35. Graph GROUNDED from the official Comfy-Org/z_image_turbo
    blueprint (Text to Image (Z-Image-Turbo).json): CLIPLoader(type="lumina2" -- Z-Image is
    Lumina-derived) + generic CLIPTextEncode + ModelSamplingAuraFlow(shift 3) + KSampler(res_multistep,
    simple). BASE bf16 only -- SVDQ/int4/nunchaku/GGUF quant variants are the deferred quant-loader arc.
    """
    model_path = str(req.get("model") or "")
    unet_name = _comfy_unet_name_for_model(object_info, model_path)
    if not unet_name:
        raise RuntimeError(
            f"Z-Image transformer is not visible to ComfyUI UNETLoader: {model_path!r} (must be under diffusion_models/)."
        )
    qwen = resolved.value("text_encoder") or "qwen_3_4b.safetensors"   # size-specific gemma... qwen_3_4b
    vae = resolved.value("vae") or "ae.safetensors"                    # Flux ae (NOT zImage_vae)

    def _snap16(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 16)  # 16-ch ae latent (EmptySD3LatentImage), /16 like Flux/Lumina

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")  # inert at cfg 1.0; wired for completeness
    width = _snap16(req.get("width"), 1024)
    height = _snap16(req.get("height"), 1024)
    # Phase 2b: steps default lifted (zimage_image). cfg 1.0 (baked, cockpit IGNORED) and shift 3.0
    # are PINNED -- recorded in the table, NOT routed. The <1 / >16 -> 4 clamp below stays inline.
    _defaults = operating_point_params("zimage_image", "default")
    try:
        steps = int(req.get("steps") or _defaults.get("steps") or 4)
    except Exception:
        steps = 4
    if steps < 1 or steps > 16:
        steps = 4  # official Turbo is 4 NFE; ignore the SDXL-default 35 (Simple-mode default fix)
    try:
        seed = int(req.get("seed")) if str(req.get("seed") or "").strip() not in {"", "None"} else 0
    except Exception:
        seed = 0
    cfg = 1.0     # distilled Turbo: CFG is baked in; real cfg over-saturates. Cockpit cfg IGNORED.
    shift = 3.0   # Z-Image sigma shift (render-proven clean)
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    is_i2i = str(req.get("command") or req.get("task_type") or "").strip().lower() == "i2i"

    graph: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": qwen, "type": "lumina2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": shift}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }
    if is_i2i:
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("Z-Image i2i graph requires an uploaded input image (input_image_comfy_name).")
        try:
            denoise = float(req.get("strength")) if str(req.get("strength") or "").strip() not in {"", "None"} else 0.0
        except Exception:
            denoise = 0.0
        if not (0.0 < denoise <= 1.0):
            denoise = 0.6
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["3", 0]}}
        latent_ref: list[Any] = ["12", 0]
    else:
        graph["7"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["5", 0], "seed": seed, "steps": steps, "cfg": cfg,
        "sampler_name": "res_multistep", "scheduler": "simple",
        "positive": ["4", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph


def _build_anima_image_prompt(req: dict[str, Any], object_info: dict[str, Any], job_id: str,
                              resolved: Any) -> dict[str, Any]:
    """Anima t2i/i2i graph -- the 4th image family, CLOSES the arc. Split-stack like Z-Image
    (UNETLoader, diffusion_models/anima/, a Cosmos-Predict2-derived 2B DiT) but the recipe is the
    OPPOSITE: Anima is NON-distilled. Companions are the MIRROR-HALF of Z-Image's: the Qwen-3-0.6B
    encoder (NOT the 4B) + qwen_image_vae (the FLIP of Z-Image's ae) -- both resolver-driven, both
    coexisting with Z-Image's on the same disk. Recipe GROUNDED from the official ComfyUI
    Template-Library blueprint (image_anima_preview.json): CLIPLoader(type="stable_diffusion") +
    generic CLIPTextEncode + EmptyLatentImage + KSampler(er_sde, simple) with NO ModelSamplingAuraFlow
    shift node. cfg is MAPPED from the cockpit (default 4, the blueprint value; NOT pinned to 1.0 like
    Z-Image's Turbo) and steps default to 30 (mapped, NOT the Turbo 4) -- do NOT copy Z-Image's pinning.
    Anima is anime/illustration-only by design (no realism). License: non-commercial -- see
    MODEL_FAMILIES["anima"].
    """
    model_path = str(req.get("model") or "")
    unet_name = _comfy_unet_name_for_model(object_info, model_path)
    if not unet_name:
        raise RuntimeError(
            f"Anima transformer is not visible to ComfyUI UNETLoader: {model_path!r} (must be under diffusion_models/)."
        )
    qwen = resolved.value("text_encoder") or "qwen_3_06b_base.safetensors"   # 0.6B (mirror-half of Z-Image's 4B)
    vae = resolved.value("vae") or "qwen_image_vae.safetensors"              # qwen_image_vae (FLIP of Z-Image's ae)

    def _snap16(value: Any, default: int) -> int:
        try:
            v = int(value)
        except Exception:
            v = default
        v = max(256, v)
        return v - (v % 16)

    prompt = str(req.get("prompt") or "")
    negative = str(req.get("negative_prompt") or req.get("negative") or "")  # active (cfg > 1, unlike Z-Image)
    width = _snap16(req.get("width"), 1024)
    height = _snap16(req.get("height"), 1024)
    _defaults = operating_point_params("anima_image", "default")  # Phase 2b: steps/cfg lifted (sampler/scheduler pinned; cfg NOT pinned -- mapped)
    try:
        steps = int(req.get("steps") or _defaults.get("steps") or 30)
    except Exception:
        steps = 30
    if steps < 1:
        steps = 30  # NON-distilled: honor the cockpit (30-50 typical); blueprint default 30, NO Turbo-4 pin
    try:
        cfg = float(str(req.get("cfg") or "").strip() or _defaults.get("cfg") or 4.0)
    except Exception:
        cfg = 4.0
    if cfg <= 0:
        cfg = 4.0   # MAPPED from cockpit (blueprint 4-5 band); NOT pinned like Z-Image's Turbo cfg=1.0
    try:
        seed = int(req.get("seed")) if str(req.get("seed") or "").strip() not in {"", "None"} else 0
    except Exception:
        seed = 0
    prefix = _filename_prefix_from_output(str(req.get("output") or ""), job_id)
    is_i2i = str(req.get("command") or req.get("task_type") or "").strip().lower() == "i2i"

    graph: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": qwen, "type": "stable_diffusion"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }
    if is_i2i:
        comfy_image = str(req.get("input_image_comfy_name") or "").strip()
        if not comfy_image:
            raise RuntimeError("Anima i2i graph requires an uploaded input image (input_image_comfy_name).")
        try:
            denoise = float(req.get("strength")) if str(req.get("strength") or "").strip() not in {"", "None"} else 0.0
        except Exception:
            denoise = 0.0
        if not (0.0 < denoise <= 1.0):
            denoise = 0.6
        graph["11"] = {"class_type": "LoadImage", "inputs": {"image": comfy_image}}
        graph["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["3", 0]}}
        latent_ref: list[Any] = ["12", 0]
    else:
        graph["7"] = {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        denoise = 1.0
        latent_ref = ["7", 0]
    # NO shift node: KSampler.model comes straight from UNETLoader (blueprint has no ModelSamplingAuraFlow).
    graph["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["1", 0], "seed": seed, "steps": steps, "cfg": cfg,
        "sampler_name": "er_sde", "scheduler": "simple",
        "positive": ["4", 0], "negative": ["6", 0], "latent_image": latent_ref, "denoise": denoise}}
    return graph


# Native-image family registry (seam). Each build is the existing per-family image builder,
# signature build(req, object_info, job_id, resolved) -> graph. "flux" is the default when no
# family key matches (preserving the inline `return _build_flux_image_prompt(...)` fallthrough).
NATIVE_IMAGE_FAMILY_PLUGINS: dict[str, NativeFamilyPlugin] = {
    "flux": NativeFamilyPlugin(family="flux", kind="image", build=_build_flux_image_prompt),
    "pixart": NativeFamilyPlugin(family="pixart", kind="image", build=_build_pixart_image_prompt),
    "lumina": NativeFamilyPlugin(family="lumina", kind="image", build=_build_lumina_image_prompt),
    "z_image": NativeFamilyPlugin(family="z_image", kind="image", build=_build_zimage_image_prompt),
    "anima": NativeFamilyPlugin(family="anima", kind="image", build=_build_anima_image_prompt),
}


def _build_native_image_prompt(family: str, req: dict[str, Any], object_info: dict[str, Any],
                               job_id: str, resolved: Any) -> dict[str, Any]:
    """Dispatch to the per-family native-image graph builder. Each family's architecture differs
    (Flux DualCLIP+FluxGuidance; PixArt CLIPLoader(pixart)+PixArtAlpha; Lumina CLIPLoader(lumina2)+
    ModelSamplingAuraFlow+Lumina2+res_multistep; Z-Image UNETLoader+CLIPLoader(lumina2)+cfg~1.0;
    Anima UNETLoader+CLIPLoader(stable_diffusion)+er_sde+cfg-mapped, no shift), so the GRAPH is
    per-family even though resolve/route/T3 are shared. Add a branch to register a family.
    """
    fam = str(family or "").strip().lower()
    # STAGE 2b: inline per-family branching fully replaced by the registry-plugin seam. An unknown or
    # absent family falls back to flux, preserving the inline `return _build_flux_image_prompt(...)`.
    plugin = NATIVE_IMAGE_FAMILY_PLUGINS.get(fam) or NATIVE_IMAGE_FAMILY_PLUGINS["flux"]
    return plugin.build(req, object_info, job_id, resolved)


def _should_route_native_image(req: dict[str, Any]) -> bool:
    """Route a NATIVE-IMAGE family's t2i/i2i to the ComfyUI-native path instead of the diffusers loader.

    Native-image families (NATIVE_IMAGE_FAMILIES: flux, pixart, ...) are transformer-only checkpoints
    that either can't load through diffusers from_single_file (Flux's gated-config STOP) or have a
    distinct ComfyUI-native DiT graph (PixArt). Family is the same classifier the rest of the worker
    uses; every other family (SDXL i2i included) keeps its existing diffusers path.
    """
    command = str(req.get("command") or req.get("task_type") or "").strip().lower()
    if command not in {"t2i", "i2i"}:
        return False
    return _native_image_family(req) in NATIVE_IMAGE_FAMILIES


def run_native_image(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    """Render an image through a ComfyUI-native graph (route B). Flux t2i + i2i."""
    command = str(req.get("command") or req.get("task_type") or "t2i").strip().lower()
    if command not in {"t2i", "i2i"}:
        raise RuntimeError(f"Native image path supports t2i/i2i only, got {command!r}.")

    transition_job(job, JobState.STARTING)
    emitter.status(job, "starting Comfy runtime for native image")
    emitter.emit_job_update(job)
    prepare_runtime_for_request(req, emitter, job)
    # The transformer + T5 render inside ComfyUI's process; free any diffusers pipeline the worker
    # holds so the two don't contend for VRAM.
    unload_cached_pipelines()

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
    # i2i: the input image must live in ComfyUI's input dir for LoadImage (a COMBO of input-dir files)
    # to reference it -- an arbitrary local path can't be passed. Upload it now and stash the
    # Comfy-side name for the builder (the exact keyframe bridge native i2v uses).
    if command == "i2i":
        input_image = str(req.get("input_image") or "").strip()
        if not input_image:
            raise RuntimeError("Native i2i requires an input image (req['input_image']).")
        uploaded = _upload_comfy_image(api_url, input_image)
        req["input_image_comfy_name"] = _comfy_image_ref(uploaded)
        emitter.status(job, f"uploaded i2i input to ComfyUI: {req['input_image_comfy_name']}")
    family = _native_image_family(req) or "flux"
    emitter.status(job, f"building native {family} image template")
    object_info = _comfy_object_info(api_url)
    # Producer-side companion resolution (Doc 19 §6): resolve_stack drives the family's companions
    # (precision-matched where applicable) from the on-disk ComfyUI choices, not fixed strings.
    resolved = _resolve_native_image_stack(req, object_info, family)
    missing = [s.component for s in resolved.missing_required()]
    if missing:
        # Image analog of the video readiness gate: surface a T3-missing companion as a clear block
        # BEFORE submitting the graph, never a mid-render ComfyUI failure.
        raise RuntimeError(
            f"{family} stack incomplete -- missing required component(s): " + ", ".join(missing)
            + ". The resolver found no valid on-disk file for them; resolve or download before generating."
        )
    workflow = _build_native_image_prompt(family, req, object_info, job.job_id, resolved)
    # The submitted graph is written to the native-prompt debug file below (always) -- that JSON is the
    # authoritative record of the resolver-driven companions (clip_l / precision-matched T5 / ae) and
    # the cfg->guidance mapping, the same observability the native video path relies on.
    debug_prompt_path = _native_prompt_debug_path(req, job.job_id)
    _write_native_prompt_debug_file(debug_prompt_path, workflow)
    req["native_prompt_api_path"] = debug_prompt_path

    validation_issues = _validate_comfy_prompt_against_object_info(workflow, object_info)
    if validation_issues:
        raise RuntimeError(
            f"Generated native {family} image prompt failed local validation before submit. "
            f"Debug prompt: {debug_prompt_path}. Issues: " + "; ".join(validation_issues[:30])
        )

    transition_job(job, JobState.RUNNING)
    emitter.status(job, f"submitting native {family} image template")
    start = time.perf_counter()
    prompt_id = _submit_comfy_prompt(api_url, workflow)
    emitter.status(job, f"ComfyUI native {family} template submitted: {prompt_id}")

    history = _poll_comfy_history(api_url, prompt_id, req, emitter, job, active_job)
    asset = _extract_comfy_asset(history, ["images"])
    if asset is None:
        raise RuntimeError(f"ComfyUI completed the native {family} template but produced no image asset")

    output_path = str(req.get("output") or "").strip()
    if not output_path:
        output_path = str(Path.cwd() / (str(asset.get("filename")) or f"flux_native_{prompt_id}.png"))
    else:
        requested_suffix = Path(output_path).suffix
        asset_suffix = Path(str(asset.get("filename") or "")).suffix
        if requested_suffix and asset_suffix and requested_suffix.lower() != asset_suffix.lower():
            output_path = str(Path(output_path).with_suffix(asset_suffix))
    output_path = _download_comfy_asset(api_url, asset, output_path)

    elapsed = time.perf_counter() - start
    steps_per_sec = float(req.get("steps") or 0) / elapsed if elapsed > 0 and req.get("steps") else 0.0
    req["resolved_media_type"] = "image"
    req["comfy_asset_kind"] = f"native_{family}_image"

    metadata_output = str(req.get("metadata_output") or "").strip() or str(Path(output_path).with_suffix(".json"))
    metadata_payload = save_metadata(
        req=req,
        image_path=output_path,
        metadata_output=metadata_output,
        backend_name="SpellVisionNativeComfyTemplate",
        device="comfy",
        dtype="n/a",
        detected_pipeline=f"{family}_native_image_template",
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
        "detected_pipeline": f"{family}_native_image_template",
        "task_type": command,
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cuda_allocated_gb": 0.0,
        "cuda_reserved_gb": 0.0,
        "media_type": "image",
        "model_family": family,
        "prompt_id": prompt_id,
        "metadata": metadata_payload,
        "metadata_write_deferred": False,
        "native_template": True,
        **output_finalization_contract(
            output_path,
            metadata_output,
            original_output=str(req.get("original_output") or ""),
            media_type=output_media_type_for_metadata(req, output_path),
            metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"),
            metadata_write_error=metadata_payload.get("metadata_write_error"),
        ),
        **runtime_prep_metadata(req),
        "comfy_runtime_endpoint": runtime_status.get("endpoint"),
        "comfy_runtime_pid": runtime_status.get("pid"),
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
    _defaults = operating_point_params("wan_diffusers", "default")  # Phase 2a: defaults lifted to the table
    steps = int(req.get("steps") or req.get("num_inference_steps") or _defaults.get("steps") or 30)
    cfg = float(req.get("cfg") or req.get("cfg_scale") or req.get("guidance_scale") or _defaults.get("cfg") or 5.0)

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

    # Native-LTX migration (Step 4): the LTX -> prompt-api redirect that used to sit
    # here is gone. Every t2v/i2v request (LTX included) now proceeds to family
    # inference + the native gate below. LTX's contract is production (see
    # video_family_contracts), so it PASSES the gate and renders natively; only
    # families still marked non-production (hunyuan/cogvideox/mochi) are blocked by
    # the gate until theirs flip. The prompt-api engine remains reachable only via the
    # explicit ltx_prompt_api_gated_submission command (history requeue / fallback).
    emitter.status(job, "loading native video pipeline")
    emitter.emit_job_update(job)

    family = _infer_native_video_family(req)
    _raise_if_unvalidated_native_video_family(family, command=command)
    if _is_split_video_stack_request(req):
        return run_native_split_stack_video(req, emitter, job, active_job)
    runtime_prep = prepare_runtime_for_request(req, emitter, job)

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
        "metadata_write_deferred": False,
        **output_finalization_contract(output_path if 'output_path' in locals() else req.get("output"), metadata_output if 'metadata_output' in locals() else req.get("metadata_output"), original_output=str(req.get("original_output") or ""), media_type=output_media_type_for_metadata(req, output_path if 'output_path' in locals() else req.get("output")), metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"), metadata_write_error=metadata_payload.get("metadata_write_error")),
        **runtime_prep_metadata(req),
    }

    payload.update(video_completion_diagnostics(
        req,
        backend_type="native_video",
        backend_name=str(payload.get("backend_name") or "Native Video"),
        output_path=str(payload.get("output") or req.get("output") or ""),
        metadata_output=str(payload.get("metadata_output") or req.get("metadata_output") or ""),
    ))
    video_cache_update = update_video_runtime_cache_from_result(req, payload)
    if video_cache_update:
        payload["video_runtime_cache_updated"] = True
        payload["video_runtime_cache"] = video_cache_update
    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


def run_comfy_workflow(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    req = normalize_video_input_fields(req)
    transition_job(job, JobState.STARTING)
    emitter.status(job, "loading workflow profile")
    emitter.emit_job_update(job)
    runtime_prep = prepare_runtime_for_request(req, emitter, job)

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

    # The Comfy runtime must be up before we build the prompt: ComfyUI's /prompt accepts only the
    # API-prompt format, and converting a UI-graph export to it needs the live /object_info schema.
    transition_job(job, JobState.RUNNING)
    emitter.status(job, "preparing ComfyUI runtime")
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

    # object_info (the live /object_info schema) is needed to convert a UI-graph and, on every launch, to
    # normalize model-file names to ComfyUI's exact catalogued strings (a workflow's baked-in ckpt/lora
    # names are routinely bare or subfolder-relative and would fail /prompt validation). Fetch it once.
    object_info: dict[str, Any] | None = None
    try:
        object_info = _comfy_object_info(api_url)
    except Exception as exc:
        # A UI-graph cannot be submitted without the schema; an API-prompt graph can still try as-is.
        if is_ui_graph(workflow):
            raise
        log.warning("comfy_workflow: /object_info unavailable (%s); submitting graph without name normalization", exc)

    # A ComfyUI *UI-graph* export ({"nodes": [...], "links": [...]}, what Save produces and what nearly
    # every community workflow ships as) is rejected by /prompt (HTTP 500). Convert it to API-prompt
    # form using the live schema. This also makes the graph's model inputs bindable -- they become the
    # named `inputs` dict the slot logic reads -- so we can substitute a model even when the import-time
    # scan (which never sees /object_info) produced no bindings.
    if is_ui_graph(workflow):
        emitter.status(job, "converting workflow graph to ComfyUI prompt format")
        assert object_info is not None  # fetched above (and re-raised on failure) whenever is_ui_graph
        workflow = convert_ui_graph_to_api_prompt(workflow, object_info)
        if not slot_bindings:
            slot_bindings = _derive_checkpoint_slot_bindings(workflow)

    _apply_workflow_slot_bindings(workflow, slot_bindings, req, object_info)
    _apply_common_comfy_overrides(workflow, req, object_info)
    # Normalize every model-file input (baked-in AND just-substituted) to ComfyUI's exact catalogued name.
    _resolve_graph_model_names(workflow, object_info)

    # Debug: write the submitted (post-conversion, post-substitution) workflow graph next to the output
    # so a launch's graph -- including any model/lora slot substitution applied above -- is inspectable,
    # mirroring the native video path's debug dump. Best-effort; never blocks the launch.
    try:
        _write_native_prompt_debug_file(_native_prompt_debug_path(req, job.job_id), workflow)
    except Exception:
        pass

    emitter.status(job, "submitting prompt to ComfyUI")
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
        "metadata_write_deferred": False,
        **output_finalization_contract(output_path if 'output_path' in locals() else req.get("output"), metadata_output if 'metadata_output' in locals() else req.get("metadata_output"), original_output=str(req.get("original_output") or ""), media_type=output_media_type_for_metadata(req, output_path if 'output_path' in locals() else req.get("output")), metadata_write_status=str(metadata_payload.get("metadata_write_status") or "written"), metadata_write_error=metadata_payload.get("metadata_write_error")),
        **runtime_prep_metadata(req),
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
    video_cache_update = update_video_runtime_cache_from_result(req, payload)
    if video_cache_update:
        payload["video_runtime_cache_updated"] = True
        payload["video_runtime_cache"] = video_cache_update
    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload



def run_i2i(req: dict[str, Any], emitter: JobEmitter, job: JobRecord, active_job: ActiveJobHandle) -> dict[str, Any]:
    emitter.status(job, "loading pipeline")
    transition_job(job, JobState.STARTING)
    emitter.emit_job_update(job)
    runtime_prep = prepare_runtime_for_request(req, emitter, job)

    _, pipe, device, dtype, detected, cache_hit, model_swap_cleanup = get_or_load_pipelines(req["model"], req.get("model_family"))
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
        pipe=pipe,
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
        "active_adapters": active_adapter_names(pipe),
        **runtime_prep_metadata(req),
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
        runtime_failure = invalidate_video_runtime_cache_for_failure(job, code, error_text)
        fail_job(job, error_text, code=code, tb=tb, details=runtime_failure)
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


# ---------------------------------------------------------------------------
# Imported-workflow lifecycle: re-check / retry-install / delete.
# These operate on an ALREADY-imported profile folder (<slug>) under
# imported_workflows_root(), reusing the same scan + dependency-plan building
# blocks the importer uses, but against the LIVE comfy_root.
# ---------------------------------------------------------------------------

def _resolve_import_root(req: dict[str, Any]) -> Path | None:
    import_root = str(req.get("import_root") or "").strip()
    if not import_root:
        profile_path = str(req.get("profile_path") or "").strip()
        if profile_path:
            import_root = str(Path(profile_path).resolve().parent)
    return Path(import_root) if import_root else None


def _validate_models_against_object_info(model_report, api_url: str) -> dict[str, Any] | None:
    """Validate each extracted model literal against the LIVE /object_info loader lists, resolving the
    SAME way the launch path does (basename via _sv_choose_comfy_choice) so readiness PREDICTS launch.

    Returns {"missing", "ambiguous", "present"} or None if ComfyUI is unreachable (caller then falls
    back to the disk-based model plan). Semantics, deliberately fail-closed:
      - missing   = literal resolves to nothing installed (or its loader list is empty) -> would 400.
      - ambiguous = a BARE literal basename-matches installed models in >1 subfolder -> would render the
                    WRONG model. Surfaced as needs-review, never silently passed.
      - present   = resolves to exactly one installed entry.
    We never trust the worker's resolver as a black box that always says yes: a name absent from the
    live list is missing, full stop.
    """
    try:
        object_info = _comfy_object_info(api_url)
    except Exception:
        return None
    if not isinstance(object_info, dict) or not object_info:
        return None

    class_by_node = {n.node_id: n.class_type for n in getattr(model_report, "nodes", [])}
    base = lambda v: str(v).replace("\\", "/").rsplit("/", 1)[-1].lower()
    subdir = lambda v: str(v).replace("\\", "/").rsplit("/", 1)[0] if "/" in str(v).replace("\\", "/") else ""

    missing: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    present: list[dict[str, Any]] = []
    for ref in getattr(model_report, "model_references", []):
        cls = class_by_node.get(ref.node_id, "")
        key = ref.input_name
        val = str(ref.value or "").strip()
        if not val or not cls or cls not in object_info:
            # No loader class in the live schema -> a NODE problem (handled by the node check), not a
            # model-presence verdict. Skip rather than mislabel.
            continue
        choices = _sv_comfy_input_choices(object_info, cls, key)
        if not choices:
            missing.append({"value": val, "class_type": cls, "input": key,
                            "reason": f"{cls}.{key} has no installed options"})
            continue
        resolved = _sv_choose_comfy_choice(object_info, cls, key, val)
        basename_hits = [c for c in choices if base(c) == base(val)]
        if val not in choices and len({subdir(c) for c in basename_hits}) > 1:
            ambiguous.append({"value": val, "class_type": cls, "input": key,
                              "candidates": sorted(basename_hits)})
        elif resolved not in choices:
            missing.append({"value": val, "class_type": cls, "input": key,
                            "reason": f"not in {cls}.{key} ({len(choices)} installed)"})
        else:
            present.append({"value": val, "resolved": resolved, "class_type": cls})
    return {"missing": missing, "ambiguous": ambiguous, "present": present}


def _recheck_workflow_dependencies(
    import_root: Path,
    *,
    comfy_root: str,
    node_catalog: str,
    python_executable: str,
    model_cache_root: str,
    civitai_api_key: str | None,
    api_url: str | None = None,
):
    """Re-scan the imported workflow + rebuild node/model plans against the live comfy_root.
    Returns (report, node_plan, model_plan, live_models).

    Model literals come from the CONVERTED API-prompt graph (prompt_api.json = exactly what
    run_comfy_workflow submits at launch), because a raw UI-graph hides them in positional
    widgets_values and scan_workflow yields model_references=[] (the false-"Ready" root cause). We do
    NOT reimplement widgets_values mapping here. When api_url is given, model presence is validated
    against the live /object_info lists (see _validate_models_against_object_info)."""
    from workflow_scanner import load_workflow_source, scan_workflow
    from node_dependency_resolver import build_node_install_plan
    from model_dependency_resolver import build_model_install_plan

    workflow_json = import_root / "workflow.json"
    if not workflow_json.is_file():
        raise FileNotFoundError(f"workflow.json not found in import root: {import_root}")

    # Nodes: scan the raw graph (node detection is format-agnostic and unchanged).
    workflow_source, payload = load_workflow_source(str(workflow_json))
    report = scan_workflow(payload, source_kind=workflow_source.source_kind)

    # Models: if the raw scan found none (the UI-graph case), re-derive them from the compiled
    # API-prompt form, where MODEL_FIELD_MAP reads named inputs. api_report.nodes carry the class_types
    # the live /object_info validation needs. An API-prompt import (e.g. ltx-api-json) already has
    # model_references from the raw scan -> left untouched (the positive control).
    model_report = report
    api_prompt = import_root / "prompt_api.json"
    if not report.model_references and api_prompt.is_file():
        try:
            _, api_payload = load_workflow_source(str(api_prompt))
            api_report = scan_workflow(api_payload)
            if api_report.model_references:
                report.model_references = api_report.model_references
                model_report = api_report
        except Exception:
            pass

    node_plan = build_node_install_plan(
        report,
        comfy_root=comfy_root,
        node_catalog=node_catalog,
        python_executable=python_executable,
    )
    model_plan = build_model_install_plan(
        report,
        comfy_root=comfy_root,
        auto_materialize=False,
        cache_root=model_cache_root,
        civitai_api_key=civitai_api_key,
    )
    live_models = _validate_models_against_object_info(model_report, api_url) if api_url else None
    return report, node_plan, model_plan, live_models


def _write_recheck_into_profile(import_root: Path, comfy_root: str, node_plan, model_plan, applied: bool, live_models: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist the live re-check into the imported profile so the UI's
    loadWorkflowRecord reflects reality. The UI counts missing nodes from
    scan_report.json, so that file is the authoritative one to rewrite.

    When live_models is supplied it is the AUTHORITATIVE model signal (validated against live
    /object_info the way launch resolves); the disk-based model_plan is only the fallback used when
    ComfyUI was unreachable."""
    # Genuinely missing = anything not already installed/present.
    missing_nodes = sorted({dep.class_name for dep in node_plan.dependencies if dep.action != "already_installed"})
    node_counts = {
        "checked": len(node_plan.dependencies),
        "already_installed": sum(1 for dep in node_plan.dependencies if dep.action == "already_installed"),
        "installable": len(node_plan.install_actions),
        "unresolved": len(node_plan.unresolved_classes),
    }

    model_warnings: list[str] = []
    if live_models is not None:
        missing_models = live_models.get("missing", [])
        ambiguous_models = live_models.get("ambiguous", [])
        present_models = live_models.get("present", [])
        # Only genuine absence blocks as a "missing dependency"; ambiguity is a needs-review warning
        # (not a missing asset) so it surfaces as review, not as a download prompt.
        missing_assets = [str(m.get("value") or "") for m in missing_models]
        model_counts = {
            "checked": len(missing_models) + len(ambiguous_models) + len(present_models),
            "already_present": len(present_models),
            "missing": len(missing_models),
            "ambiguous": len(ambiguous_models),
        }
        for m in missing_models:
            model_warnings.append(f"missing model '{m.get('value')}' — {m.get('reason')}")
        for m in ambiguous_models:
            model_warnings.append(
                f"ambiguous model '{m.get('value')}' basename-matches multiple installed subfolders "
                f"{m.get('candidates')} — needs review (would render the wrong model)")
        models_ok = not missing_models and not ambiguous_models
    else:
        missing_assets = [str(a.get("source_value") or a.get("destination_path") or "") for a in model_plan.install_actions]
        model_counts = {
            "checked": len(model_plan.dependencies),
            "already_present": sum(1 for dep in model_plan.dependencies if dep.install_action == "already_present"),
            "missing": len(model_plan.install_actions),
        }
        models_ok = not model_plan.install_actions

    ready = not missing_nodes and models_ok

    verb = "Applied installs, then re-checked" if applied else "Re-checked"
    ambiguous_note = f", {model_counts.get('ambiguous', 0)} ambiguous" if model_counts.get("ambiguous") else ""
    summary = (
        f"{verb} against live ComfyUI: nodes {node_counts['already_installed']}/{node_counts['checked']} "
        f"already installed, {node_counts['installable']} installable, {node_counts['unresolved']} unresolved; "
        f"models {model_counts['already_present']}/{model_counts['checked']} present, {model_counts['missing']} missing{ambiguous_note}."
    )

    readiness_block = {
        "ok": ready,
        "summary": summary,
        "missing_node_classes": missing_nodes,
        "missing_runtime_assets": missing_assets,
        "errors": [],
        "warnings": list(node_plan.unresolved_classes) + model_warnings,
        "checked_at": utc_now_iso(),
        "checked_comfy_root": comfy_root,
        "node_counts": node_counts,
        "model_counts": model_counts,
    }

    # scan_report.json drives the UI's missing-node count + early readiness check.
    scan_path = import_root / "scan_report.json"
    if scan_path.is_file():
        try:
            scan_obj = json.loads(scan_path.read_text(encoding="utf-8"))
            if isinstance(scan_obj, dict):
                scan_obj["missing_custom_nodes"] = missing_nodes
                scan_path.write_text(json.dumps(scan_obj, indent=2), encoding="utf-8")
        except Exception:
            pass

    # profile.json: refresh the static missing list + the last_launch_readiness block.
    profile_path = import_root / "profile.json"
    if profile_path.is_file():
        try:
            profile_obj = json.loads(profile_path.read_text(encoding="utf-8"))
            if isinstance(profile_obj, dict):
                metadata = profile_obj.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                    profile_obj["metadata"] = metadata
                metadata["missing_custom_nodes"] = missing_nodes
                metadata["last_launch_readiness"] = readiness_block
                profile_path.write_text(json.dumps(profile_obj, indent=2), encoding="utf-8")
        except Exception:
            pass

    return {
        "ready": ready,
        "summary": summary,
        "missing_node_classes": missing_nodes,
        "missing_runtime_assets": missing_assets,
        "node_counts": node_counts,
        "model_counts": model_counts,
    }


def handle_check_workflow_launch_readiness_command(req: dict[str, Any]) -> dict[str, Any]:
    """Cheap re-check (NO install): re-scan an imported profile against the live
    ComfyUI and rewrite its stored readiness/missing-node set."""
    try:
        import_root = _resolve_import_root(req)
        if import_root is None or not import_root.is_dir():
            return {
                "type": "workflow_readiness_result",
                "ok": False,
                "action": "check_workflow_launch_readiness",
                "error": "check_workflow_launch_readiness requires a valid import_root or profile_path",
            }

        comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
        node_catalog = str(req.get("node_catalog") or starter_node_catalog_path()).strip()
        python_executable = str(req.get("python_executable") or sys.executable).strip()
        model_cache_root = str(req.get("model_cache_root") or (Path(__file__).resolve().parent.parent / "python" / ".cache" / "assets")).strip()
        civitai_api_key = str(req.get("civitai_api_key") or os.environ.get("CIVITAI_API_KEY") or "").strip() or None
        api_url = str(req.get("comfy_api_url") or os.environ.get("COMFY_API_URL") or "http://127.0.0.1:8188").rstrip("/")

        _, node_plan, model_plan, live_models = _recheck_workflow_dependencies(
            import_root,
            comfy_root=comfy_root,
            node_catalog=node_catalog,
            python_executable=python_executable,
            model_cache_root=model_cache_root,
            civitai_api_key=civitai_api_key,
            api_url=api_url,
        )
        result = _write_recheck_into_profile(import_root, comfy_root, node_plan, model_plan, applied=False, live_models=live_models)
        return {
            "type": "workflow_readiness_result",
            "ok": True,
            "action": "check_workflow_launch_readiness",
            "import_root": str(import_root),
            **result,
        }
    except Exception as exc:
        return {
            "type": "workflow_readiness_result",
            "ok": False,
            "action": "check_workflow_launch_readiness",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def handle_retry_workflow_dependencies_command(req: dict[str, Any]) -> dict[str, Any]:
    """Re-check against the live ComfyUI, then (if auto_apply_*) install ONLY the
    genuinely-missing-and-resolvable nodes/models, then re-check and persist."""
    try:
        from node_dependency_resolver import apply_node_install_plan
        from model_dependency_resolver import apply_model_install_plan

        import_root = _resolve_import_root(req)
        if import_root is None or not import_root.is_dir():
            return {
                "type": "workflow_dependency_retry_result",
                "ok": False,
                "action": "retry_workflow_dependencies",
                "error": "retry_workflow_dependencies requires a valid import_root or profile_path",
            }

        comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
        node_catalog = str(req.get("node_catalog") or starter_node_catalog_path()).strip()
        python_executable = str(req.get("python_executable") or sys.executable).strip()
        model_cache_root = str(req.get("model_cache_root") or (Path(__file__).resolve().parent.parent / "python" / ".cache" / "assets")).strip()
        civitai_api_key = str(req.get("civitai_api_key") or os.environ.get("CIVITAI_API_KEY") or "").strip() or None
        auto_apply_node_deps = bool(req.get("auto_apply_node_deps", False))
        auto_apply_model_deps = bool(req.get("auto_apply_model_deps", False))
        api_url = str(req.get("comfy_api_url") or os.environ.get("COMFY_API_URL") or "http://127.0.0.1:8188").rstrip("/")

        # 1) Live re-check FIRST.
        _, node_plan, model_plan, live_models = _recheck_workflow_dependencies(
            import_root,
            comfy_root=comfy_root,
            node_catalog=node_catalog,
            python_executable=python_executable,
            model_cache_root=model_cache_root,
            civitai_api_key=civitai_api_key,
            api_url=api_url,
        )

        apply_errors: list[str] = []
        applied = False
        # 2) Install ONLY install_actions. already_installed nodes are never in
        #    plan.install_actions, so they are skipped (not re-cloned).
        if auto_apply_node_deps and node_plan.install_actions:
            node_apply = apply_node_install_plan(node_plan, comfy_root=comfy_root, python_executable=python_executable)
            applied = True
            if not node_apply.ok:
                apply_errors.extend(node_apply.errors)
        if auto_apply_model_deps and model_plan.install_actions:
            model_apply = apply_model_install_plan(model_plan)
            applied = True
            if not model_apply.ok:
                apply_errors.extend(model_apply.errors)

        # 3) Re-check AFTER install to capture the post-install state, then persist.
        if applied:
            _, node_plan, model_plan, live_models = _recheck_workflow_dependencies(
                import_root,
                comfy_root=comfy_root,
                node_catalog=node_catalog,
                python_executable=python_executable,
                model_cache_root=model_cache_root,
                civitai_api_key=civitai_api_key,
                api_url=api_url,
            )
        result = _write_recheck_into_profile(import_root, comfy_root, node_plan, model_plan, applied=applied, live_models=live_models)
        return {
            "type": "workflow_dependency_retry_result",
            "ok": not apply_errors,
            "action": "retry_workflow_dependencies",
            "import_root": str(import_root),
            "applied": applied,
            "apply_errors": apply_errors,
            **result,
        }
    except Exception as exc:
        return {
            "type": "workflow_dependency_retry_result",
            "ok": False,
            "action": "retry_workflow_dependencies",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def handle_delete_workflow_profile_command(req: dict[str, Any]) -> dict[str, Any]:
    """Delete an imported workflow's <slug> folder, guarded against deleting
    anything that is not a direct child of imported_workflows_root()."""
    import shutil
    try:
        import_root = _resolve_import_root(req)
        if import_root is None:
            return {
                "type": "workflow_delete_result",
                "ok": False,
                "action": "delete_workflow_profile",
                "error": "delete_workflow_profile requires import_root or profile_path",
            }

        root = Path(imported_workflows_root()).resolve()
        target = import_root.resolve()

        # Safety: target must be a direct <slug> subfolder of the imported root,
        # never the root itself, a deeper path, or anything outside it.
        if target == root or target.parent != root or root not in target.parents:
            return {
                "type": "workflow_delete_result",
                "ok": False,
                "action": "delete_workflow_profile",
                "error": f"Refusing to delete '{target}': not a workflow folder directly under {root}",
            }

        if not target.is_dir():
            return {
                "type": "workflow_delete_result",
                "ok": True,
                "action": "delete_workflow_profile",
                "import_root": str(target),
                "already_absent": True,
            }

        shutil.rmtree(target)
        return {
            "type": "workflow_delete_result",
            "ok": True,
            "action": "delete_workflow_profile",
            "import_root": str(target),
            "deleted": True,
        }
    except Exception as exc:
        return {
            "type": "workflow_delete_result",
            "ok": False,
            "action": "delete_workflow_profile",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def _discovery_normpath(path: str) -> str:
    """Normalize a path for dedupe comparison (case-insensitive on Windows)."""
    try:
        resolved = str(Path(path).resolve())
    except Exception:
        resolved = str(path)
    return os.path.normcase(resolved)


def _sha256_file_bytes(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return None


def _imported_profile_identity_index(profiles_root: Path) -> dict[str, dict[str, Any]]:
    """Map sha256 -> imported-profile identity, built from Step 1's discovery keys.

    Reads existing profile.json files only; profiles without a
    discovery_source_sha256 (e.g. pre-Step-1 imports or in-memory sources) are
    skipped because they cannot be matched by content. WRITES NOTHING and never
    creates the directory.
    """
    index: dict[str, dict[str, Any]] = {}
    if not profiles_root.is_dir():
        return index
    for profile_path in sorted(profiles_root.glob("*/profile.json")):
        try:
            payload = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        sha = str(payload.get("discovery_source_sha256") or "").strip()
        if not sha or sha in index:
            continue
        index[sha] = {
            "profile_path": str(profile_path),
            "import_slug": profile_path.parent.name,
            "imported_source_path": payload.get("discovery_source_path"),
        }
    return index


def handle_discover_comfy_workflows_command(req: dict[str, Any] | None = None) -> dict[str, Any]:
    """List ComfyUI graph .json files and split them into discovered vs already-imported.

    Pure read + classify: recursively hashes every *.json under the workflows dir
    and cross-references each hash against existing imported profiles' Step-1
    discovery keys. WRITES NOTHING.
    """
    req = req or {}

    workflows_dir = str(req.get("workflows_dir") or "").strip()
    if not workflows_dir:
        comfy_root = str(req.get("comfy_root") or default_comfy_root()).strip()
        workflows_dir = str(Path(comfy_root) / "user" / "default" / "workflows")
    workflows_path = Path(workflows_dir)

    profiles_root = Path(str(req.get("destination_root") or imported_workflows_root()).strip())
    identity_index = _imported_profile_identity_index(profiles_root)

    discovered: list[dict[str, Any]] = []
    already_imported: list[dict[str, Any]] = []

    if workflows_path.is_dir():
        for source in sorted(workflows_path.rglob("*.json")):
            if not source.is_file():
                continue
            sha = _sha256_file_bytes(source)
            if sha is None:
                continue
            source_str = str(source.resolve())
            entry: dict[str, Any] = {
                "source_path": source_str,
                "sha256": sha,
                "filename": source.name,
                "already_imported": False,
            }
            match = identity_index.get(sha)
            if match is not None:
                imported_path = match.get("imported_source_path")
                path_changed = bool(
                    imported_path
                    and _discovery_normpath(str(imported_path)) != _discovery_normpath(source_str)
                )
                entry.update(
                    {
                        "already_imported": True,
                        "path_changed": path_changed,
                        "profile_path": match.get("profile_path"),
                        "import_slug": match.get("import_slug"),
                        "imported_source_path": imported_path,
                    }
                )
                already_imported.append(entry)
            else:
                discovered.append(entry)

    return {
        "type": "comfy_workflow_discovery",
        "ok": True,
        "action": "discover_comfy_workflows",
        "workflows_dir": str(workflows_path),
        "workflows_dir_exists": workflows_path.is_dir(),
        "profiles_root": str(profiles_root),
        "discovered": discovered,
        "already_imported": already_imported,
        "discovered_count": len(discovered),
        "already_imported_count": len(already_imported),
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


# Wrapper-family TeaCache nodes (WanVideoWrapper's WanVideoTeaCache, HunyuanVideoWrapper's
# HyVideoTeaCache) output TEACACHEARGS, NOT MODEL -- they belong to those wrappers' own sampler
# topology, not the native-core UNETLoader -> ModelSamplingSD3 -> KSamplerAdvanced graph the video
# builders emit. Inserting one into the model chain makes ComfyUI reject the WHOLE graph
# (return_type_mismatch: received TEACACHEARGS, expected MODEL -- verified live). The substring
# fallback below MUST skip them so the enable flag degrades to "no TeaCache" (a valid, unaccelerated
# graph) rather than a broken HTTP-400 graph. The normalized token "videoteacache" catches the
# *VideoTeaCache wrapper family (wan/hy and any future sibling); the explicit set is belt-and-suspenders.
_TEACACHE_WRAPPER_INCOMPATIBLE = ("wanvideoteacache", "hyvideoteacache")


def _spellvision_teacache_class(object_info: dict[str, Any]) -> str | None:
    # Explicit standalone model-wrapper nodes (MODEL in -> MODEL out) -- the compatible ones.
    for class_name in ("TeaCache", "TeaCacheForVidGen", "TeaCacheForImgGen"):
        if class_name in object_info:
            return class_name
    for class_name in object_info:
        normalized = str(class_name).lower().replace("_", "")
        if "teacache" not in normalized:
            continue
        if "videoteacache" in normalized or normalized in _TEACACHE_WRAPPER_INCOMPATIBLE:
            continue  # wrapper-topology node (TEACACHEARGS output) -- incompatible with the native graph
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

# --- TEST-ONLY: noop_slow command ----------------------------------------
# Exercises the queue / cancellation / progress paths of worker_service from
# pytest without requiring a real generation backend. Production code never
# emits this command. See tests/test_worker_queue.py.
def run_noop_slow(
    req: dict[str, Any],
    emitter: EventEmitter,
    job: JobRecord,
    active_job: ActiveJobHandle,
) -> None:
    try:
        duration_sec = float(req.get("duration_sec") or 0.5)
    except (TypeError, ValueError):
        duration_sec = 0.5
    try:
        steps = int(req.get("steps") or 5)
    except (TypeError, ValueError):
        steps = 5

    # Clamp to sane bounds. The upper bound on duration_sec protects against
    # a runaway test holding a worker thread for minutes.
    duration_sec = max(0.0, min(duration_sec, 30.0))
    steps = max(1, min(steps, 200))

    transition_job(job, JobState.STARTING)
    transition_job(job, JobState.RUNNING)
    update_job_progress(job, 0, steps, "noop_slow starting")
    emitter.emit_job_update(job)

    per_step = duration_sec / steps if steps > 0 else 0.0

    for i in range(1, steps + 1):
        raise_if_cancelled(active_job, emitter, f"noop_slow step {i}/{steps}")
        if per_step > 0:
            # cancel_event.wait acts as an interruptible sleep that returns
            # early when a cancel is requested. We re-check immediately after.
            active_job.cancel_event.wait(timeout=per_step)
            raise_if_cancelled(active_job, emitter, f"noop_slow step {i}/{steps}")
        update_job_progress(job, i, steps, f"noop_slow step {i}/{steps}")
        emitter.emit_job_update(job)

    job.result = JobResult(task_type="noop_slow")
    transition_job(job, JobState.COMPLETED)
    emitter.emit_job_update(job)
# --- END TEST-ONLY block --------------------------------------------------

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

        # Fail LOUDLY on encoding-corrupted prompt text (lone UTF-16 surrogates) before it can reach
        # the umt5 SentencePiece tokenizer ("TypeError: not a string") or silently mangle a render.
        # Control commands have no prompt fields, so they pass through untouched.
        prompt_encoding_error = first_unencodable_prompt_field(req)
        if prompt_encoding_error:
            fallback_job = JobRecord(
                job_id=f"job_{uuid.uuid4().hex[:12]}",
                command=str(req.get("command") or req.get("action") or "unknown"),
            )
            emitter.error(fallback_job, prompt_encoding_error, code="prompt_encoding_corruption")
            return

        command = canonical_command(req)  # C3: plain dispatch reads route through the single accessor
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
            emitter.emit(video_history_snapshot(_safe_int(req.get("limit"), 25)))
            return
        if command in {"video_family_contracts", "video_family_status"}:
            emitter.emit(video_family_contracts_snapshot())
            return
        if command in {"ltx_readiness_status", "ltx_runtime_readiness", "video_family_readiness", "video_family_readiness_status"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
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
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_readiness_snapshot(runtime_status=runtime_status))
            return
        if command in {"ltx_test_workflow_contract", "ltx_workflow_contract", "video_family_test_workflow_contract", "video_family_workflow_contract"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
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
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_test_workflow_contract_snapshot(runtime_status=runtime_status))
            return
        if command in {"ltx_t2v_smoke_test", "ltx_smoke_test_route", "video_family_smoke_test_route"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
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
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_t2v_smoke_test_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"ltx_workflow_materialization_dry_run", "ltx_materialize_workflow", "ltx_t2v_materialize_dry_run", "video_family_materialization_dry_run"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
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
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_workflow_materialization_dry_run_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"ltx_workflow_graph_inspection", "ltx_prompt_api_normalization_preview", "video_family_graph_inspection", "video_family_prompt_api_normalization_preview"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
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
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_workflow_graph_inspection_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"ltx_prompt_api_conversion_adapter", "ltx_prompt_api_export_adapter", "ltx_prompt_api_conversion_preview", "video_family_prompt_api_conversion_adapter"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
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
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_prompt_api_conversion_adapter_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"ltx_requeue_draft_gated_submission", "ltx_execute_requeue_draft", "video_family_ltx_requeue_gated_submission"}:
            runtime_status = handle_comfy_runtime_status_command({})
            emitter.emit(ltx_requeue_draft_gated_submission_snapshot(req, runtime_status=runtime_status))
            return

        if command in {"ltx_prompt_api_gated_submission", "ltx_prompt_api_submit", "ltx_submit_prompt_api", "ltx_prompt_api_submit_and_capture", "ltx_prompt_api_submit_wait", "video_family_prompt_api_gated_submission"}:
            family = normalize_video_family_id(req.get("family") or req.get("video_family") or "ltx")
            if family != "ltx":
                contract = video_family_contract(family)
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
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_prompt_api_gated_submission_snapshot(req, runtime_status=runtime_status))
            return
        if command in {"ltx_ui_queue_history_contract", "ltx_ui_registry_snapshot", "ltx_ui_results_contract", "video_family_ltx_ui_contract"}:
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(ltx_ui_queue_history_snapshot(
                runtime_status=runtime_status,
                limit=int(req.get("limit") or 20),
                include_queue=bool(req.get("include_queue", True)),
                include_history=bool(req.get("include_history", True)),
            ))
            return
        if command in {"ltx_registry_history", "ltx_history_registry", "ltx_recent_history", "video_family_ltx_history_registry"}:
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(read_recent_ltx_history(runtime_status=runtime_status, limit=int(req.get("limit") or 20)))
            return
        if command in {"ltx_registry_queue", "ltx_queue_registry", "ltx_recent_queue", "video_family_ltx_queue_registry"}:
            runtime_status = {}
            try:
                runtime_status = handle_comfy_runtime_status_command({})
            except Exception as exc:
                runtime_status = {"ok": False, "error": str(exc)}
            emitter.emit(read_recent_ltx_queue_events(runtime_status=runtime_status, limit=int(req.get("limit") or 20)))
            return
        if command in {"runtime_memory_status", "runtime_diagnostics", "unload_image_runtime", "unload_video_runtime", "unload_all_runtimes", "clear_cuda_cache"}:
            emitter.emit(handle_runtime_memory_control_command(req))
            return
        if command == "classify_models":
            emitter.emit(handle_classify_models_command(req))
            return
        if command == "resolve_component_stack":
            emitter.emit(handle_resolve_component_stack_command(req))
            return

        if command == "import_workflow":
            emitter.emit(handle_import_workflow_command(req))
            return
        if command == "list_workflow_profiles":
            emitter.emit(handle_list_workflow_profiles_command(req))
            return
        if command == "discover_comfy_workflows":
            emitter.emit(handle_discover_comfy_workflows_command(req))
            return
        if command == "check_workflow_launch_readiness":
            emitter.emit(handle_check_workflow_launch_readiness_command(req))
            return
        if command == "retry_workflow_dependencies":
            emitter.emit(handle_retry_workflow_dependencies_command(req))
            return
        if command == "delete_workflow_profile":
            emitter.emit(handle_delete_workflow_profile_command(req))
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
            command = canonical_command(req)  # C3: re-read after retry rebuilds req, through the same accessor

        job = create_job(req)
        emitter.emit_job_update(job)

        if command == "ping":
            transition_job(job, JobState.COMPLETED)
            job.result = JobResult(task_type="ping")
            emitter.emit_job_update(job)
            emitter.emit({"type": "result", "ok": True, "pong": True, "job_id": job.job_id, "state": job.state.value})
            return

        # COUPLING (C1): this allow-set must stay a subset of {"noop_slow"} u dispatch_generation's
        # handled commands. Anything admitted here that is NOT "noop_slow" falls through to
        # dispatch_generation below; if dispatch_generation doesn't handle it, it raises
        # "Unsupported generation command". Add a command here only after wiring it into dispatch_generation.
        if command not in {"t2i", "i2i", "t2v", "i2v", "comfy_workflow", "noop_slow"}:
            emitter.error(job, f"Unknown command: {command}", code="unknown_command")
            return

        active_job = ActiveJobHandle(job=job)
        register_active_job(active_job)

        try:
            if command == "noop_slow":
                run_noop_slow(req, emitter, job, active_job)
            else:
                dispatch_generation(command, req, emitter, job, active_job)  # C1: single generation dispatcher (adds the native-image fork the TCP path lacked)
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
    host = os.environ.get("SPELLVISION_WORKER_HOST", "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(os.environ.get("SPELLVISION_WORKER_PORT", "8765"))
    except ValueError:
        port = 8765
    with ThreadedTCPServer((host, port), WorkerTCPHandler) as server:
        print(f"[service] SpellVision worker service listening on {host}:{port}", flush=True)
        server.serve_forever()

if __name__ == "__main__":
    main()
