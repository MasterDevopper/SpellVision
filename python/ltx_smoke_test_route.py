from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ltx_workflow_contract import ltx_test_workflow_contract_snapshot


@dataclass(frozen=True)
class LtxSmokeTestRoute:
    type: str = "ltx_t2v_smoke_test"
    ok: bool = True
    family: str = "ltx"
    display_name: str = "LTX-Video"
    validation_status: str = "experimental"
    production_ready: bool = False
    gate: str = "experimental_ready_to_test_required"
    gate_passed: bool = False
    readiness: str = "unknown"
    ready_to_test: bool = False
    generation_enabled: bool = False
    submitted: bool = False
    submission_status: str = "not_submitted"
    execution_mode: str = "contract_only"
    prompt: str = ""
    negative_prompt: str = ""
    width: int = 512
    height: int = 320
    frames: int = 33
    fps: int = 8
    duration_seconds: float = 0.0
    seed: int = 0
    cfg: float = 1.0
    steps: int = 8
    sampler: str = "euler"
    scheduler: str = "linear_quadratic"
    workflow_name: str = ""
    workflow_path: str = ""
    workflow_source: str = ""
    workflow_profile_id: str = ""
    request_metadata: dict[str, Any] = field(default_factory=dict)
    smoke_request: dict[str, Any] = field(default_factory=dict)
    output_contract: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    contract: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return fallback
    return parsed if parsed > 0 else fallback


def _safe_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return fallback
    return parsed if parsed > 0 else fallback


def _stable_seed(prompt: str, salt: str = "spellvision-ltx-smoke") -> int:
    digest = hashlib.sha256(f"{salt}|{prompt}".encode("utf-8", errors="replace")).hexdigest()
    return int(digest[:12], 16) % 2_147_483_647


def _path_exists(path: str) -> bool:
    try:
        return bool(path and Path(path).exists())
    except Exception:
        return False


def ltx_t2v_smoke_test_snapshot(req: dict[str, Any] | None = None, runtime_status: dict[str, Any] | None = None) -> dict[str, Any]:
    req = req or {}
    runtime_status = runtime_status or {}
    contract = ltx_test_workflow_contract_snapshot(runtime_status=runtime_status)

    readiness = str(contract.get("readiness") or "unknown")
    ready_to_test = bool(contract.get("ready_to_test", False))
    generation_enabled = bool(contract.get("generation_enabled", False))
    gate_passed = bool(ready_to_test and generation_enabled and not contract.get("missing_assets"))

    prompt = str(req.get("prompt") or "a quiet magical library with floating violet light particles, cinematic, soft motion").strip()
    negative_prompt = str(req.get("negative_prompt") or "").strip()
    width = _safe_int(req.get("width"), 512)
    height = _safe_int(req.get("height"), 320)
    frames = _safe_int(req.get("frames") or req.get("num_frames"), 33)
    fps = _safe_int(req.get("fps"), 8)
    seed = _safe_int(req.get("seed"), _stable_seed(prompt))
    settings = contract.get("recommended_settings") if isinstance(contract.get("recommended_settings"), dict) else {}
    cfg = _safe_float(req.get("cfg") or req.get("guidance_scale"), _safe_float(settings.get("cfg"), 1.0))
    steps = _safe_int(req.get("steps"), _safe_int(settings.get("steps"), 8))
    sampler = str(req.get("sampler") or settings.get("sampler") or "euler").strip()
    scheduler = str(req.get("scheduler") or settings.get("scheduler") or "linear_quadratic").strip()
    duration_seconds = round(float(frames) / float(fps), 3) if frames > 0 and fps > 0 else 0.0

    request_metadata = dict(contract.get("request_metadata") or {})
    request_metadata.update({
        "video_family": "ltx",
        "video_request_kind": "t2v",
        "video_width": width,
        "video_height": height,
        "video_resolution": f"{width}x{height}",
        "video_frames": frames,
        "video_frame_count": frames,
        "video_fps": fps,
        "video_duration_seconds": duration_seconds,
        "video_duration_label": f"{frames} frames @ {fps} fps ({duration_seconds:.1f}s)",
        "video_has_input_image": False,
        "video_input_image": "",
        "video_input_name": "",
        "smoke_test": True,
        "smoke_test_route": "ltx_t2v_smoke_test",
        "smoke_test_checked_at": _utc_now_iso(),
    })

    workflow_path = str(contract.get("workflow_path") or "")
    smoke_request = {
        "command": "comfy_workflow",
        "task_command": "t2v",
        "video_family": "ltx",
        "workflow_profile_id": contract.get("workflow_profile_id"),
        "workflow_profile_name": contract.get("workflow_profile_name"),
        "workflow_profile_path": workflow_path,
        "workflow_source": contract.get("workflow_source"),
        "workflow_name": contract.get("workflow_name"),
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "frames": frames,
        "fps": fps,
        "seed": seed,
        "cfg": cfg,
        "steps": steps,
        "sampler": sampler,
        "scheduler": scheduler,
        "video_model_stack": {
            "family": "ltx",
            "stack_kind": contract.get("stack_kind"),
            "stack_mode": contract.get("stack_mode"),
            "stack_ready": gate_passed,
            "primary": request_metadata.get("video_primary_model"),
            "text_encoder": request_metadata.get("video_text_encoder"),
            "text_projection": request_metadata.get("video_text_projection"),
            "vae": request_metadata.get("video_vae"),
            "audio_vae": request_metadata.get("video_audio_vae"),
        },
        **request_metadata,
    }

    submit_requested = bool(req.get("submit") or req.get("execute") or req.get("submit_to_comfy"))
    submitted = False
    execution_mode = "contract_only"
    submission_status = "ready_for_next_pass"
    notes = [
        "LTX smoke-test route is gated by the LTX workflow contract.",
        "This pass builds the smoke request and metadata contract without disturbing the Wan production path.",
    ]

    if not gate_passed:
        submission_status = "blocked_by_gate"
        notes.append("LTX smoke test is blocked until readiness is ready_to_test and required assets are present.")
    elif submit_requested:
        submission_status = "submission_deferred_to_next_pass"
        execution_mode = "deferred_submit"
        notes.append("Submit was requested, but this pass intentionally defers Comfy prompt mutation/submission to the next route-wiring pass.")
    else:
        notes.append("Use this route to inspect the exact tiny LTX T2V payload before enabling submission.")

    diagnostics = {
        "checked_at": _utc_now_iso(),
        "workflow_path_exists": _path_exists(workflow_path),
        "contract_ready_to_test": ready_to_test,
        "contract_generation_enabled": generation_enabled,
        "missing_assets": list(contract.get("missing_assets") or []),
        "comfy_running": bool((contract.get("readiness_snapshot") or {}).get("comfy_running", False)),
        "comfy_healthy": bool((contract.get("readiness_snapshot") or {}).get("comfy_healthy", False)),
        "comfy_endpoint_alive": bool((contract.get("readiness_snapshot") or {}).get("comfy_endpoint_alive", False)),
    }

    output_contract = {
        "expected_media_type": "video",
        "expected_extensions": [".mp4", ".webm", ".mov"],
        "metadata_family": "ltx",
        "metadata_task_type": "t2v",
        "requires_finalization_contract": True,
    }

    return LtxSmokeTestRoute(
        gate_passed=gate_passed,
        readiness=readiness,
        ready_to_test=ready_to_test,
        generation_enabled=generation_enabled,
        submitted=submitted,
        submission_status=submission_status,
        execution_mode=execution_mode,
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        frames=frames,
        fps=fps,
        duration_seconds=duration_seconds,
        seed=seed,
        cfg=cfg,
        steps=steps,
        sampler=sampler,
        scheduler=scheduler,
        workflow_name=str(contract.get("workflow_name") or ""),
        workflow_path=workflow_path,
        workflow_source=str(contract.get("workflow_source") or ""),
        workflow_profile_id=str(contract.get("workflow_profile_id") or ""),
        request_metadata=request_metadata,
        smoke_request=smoke_request,
        output_contract=output_contract,
        diagnostics=diagnostics,
        contract=contract,
        notes=notes,
    ).to_payload()
