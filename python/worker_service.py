import inspect
import json
import os
import socketserver
import threading
import time
import traceback
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

warnings.filterwarnings("ignore", message="A matching Triton is not available*")
warnings.filterwarnings("ignore", category=FutureWarning, module="diffusers")

import torch
from PIL import Image
from diffusers.pipelines.auto_pipeline import AutoPipelineForText2Image
from diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion import StableDiffusionPipeline
from diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion_img2img import StableDiffusionImg2ImgPipeline
from diffusers.pipelines.stable_diffusion_xl.pipeline_stable_diffusion_xl import StableDiffusionXLPipeline
from diffusers.pipelines.stable_diffusion_xl.pipeline_stable_diffusion_xl_img2img import StableDiffusionXLImg2ImgPipeline

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
}
CACHE_LOCK = threading.Lock()


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


def reset_lora_state(pipe: Any) -> None:
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


def maybe_load_lora(pipe: Any, lora_path: str, lora_scale: float) -> bool:
    reset_lora_state(pipe)

    if not lora_path:
        return False

    if not os.path.exists(lora_path):
        raise FileNotFoundError(f"LoRA file not found: {lora_path}")

    try:
        import peft  # noqa: F401
    except Exception as exc:
        raise RuntimeError("LoRA support requires 'peft' in the venv.") from exc

    pipe.load_lora_weights(lora_path)

    try:
        pipe.fuse_lora(lora_scale=lora_scale)
    except Exception:
        pass

    return True


def build_pipelines(model_name_or_path: str) -> tuple[Any, Any, str, str, str]:
    dtype, device = torch_dtype_and_device()
    detected = detect_pipeline_type(model_name_or_path)

    if is_local_file(model_name_or_path):
        try:
            t2i_pipe = StableDiffusionXLPipeline.from_single_file(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=model_name_or_path.lower().endswith(".safetensors"),
            )
            i2i_pipe = StableDiffusionXLImg2ImgPipeline.from_single_file(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=model_name_or_path.lower().endswith(".safetensors"),
            )
            detected = "sdxl"
        except Exception:
            t2i_pipe = StableDiffusionPipeline.from_single_file(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=model_name_or_path.lower().endswith(".safetensors"),
            )
            i2i_pipe = StableDiffusionImg2ImgPipeline.from_single_file(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=model_name_or_path.lower().endswith(".safetensors"),
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


def get_or_load_pipelines(model_name_or_path: str) -> tuple[Any, Any, str, str, str, bool]:
    with CACHE_LOCK:
        if MODEL_CACHE["key"] == model_name_or_path and MODEL_CACHE["pipe"] is not None:
            return (
                MODEL_CACHE["pipe"],
                MODEL_CACHE["img2img_pipe"],
                MODEL_CACHE["device"],
                MODEL_CACHE["dtype"],
                MODEL_CACHE["detected"],
                True,
            )

        t2i_pipe, i2i_pipe, device, dtype, detected = build_pipelines(model_name_or_path)
        MODEL_CACHE["key"] = model_name_or_path
        MODEL_CACHE["pipe"] = t2i_pipe
        MODEL_CACHE["img2img_pipe"] = i2i_pipe
        MODEL_CACHE["device"] = device
        MODEL_CACHE["dtype"] = dtype
        MODEL_CACHE["detected"] = detected

        return t2i_pipe, i2i_pipe, device, dtype, detected, False


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
) -> None:
    data = {
        "task_type": req.get("task_type", req.get("command", "unknown")),
        "generator": "spellvision_worker_service",
        "backend": backend_name,
        "detected_pipeline": detected_pipeline,
        "timestamp": datetime.now().isoformat(),
        "prompt": req["prompt"],
        "negative_prompt": req.get("negative_prompt", ""),
        "model": req["model"],
        "lora_path": req.get("lora", ""),
        "lora_scale": req.get("lora_scale", 1.0),
        "lora_used": lora_used,
        "width": req.get("width"),
        "height": req.get("height"),
        "steps": req["steps"],
        "cfg": req["cfg"],
        "seed": req["seed"],
        "device": device,
        "dtype": dtype,
        "image_path": image_path,
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
    }
    os.makedirs(os.path.dirname(metadata_output), exist_ok=True)
    with open(metadata_output, "w", encoding="utf-8") as file_obj:
        json.dump(data, file_obj, indent=2)



def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        }


def create_job(req: dict[str, Any]) -> JobRecord:
    return JobRecord(
        job_id=req.get("job_id") or f"job_{uuid.uuid4().hex[:12]}",
        command=str(req.get("command", "unknown")),
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



class EventEmitter:
    def __init__(self, handler: socketserver.StreamRequestHandler):
        self.handler = handler
        self.lock = threading.Lock()

    def emit(self, payload: dict[str, Any]) -> None:
        with self.lock:
            self.handler.wfile.write((json.dumps(payload) + "\n").encode("utf-8"))
            self.handler.wfile.flush()

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
    emitter: EventEmitter,
    job: JobRecord,
) -> None:
    total_steps = int(req["steps"])
    signature = inspect.signature(pipe.__call__)

    def step_end_callback(_pipe: Any, step_index: int, _timestep: Any, callback_kwargs: dict[str, Any]) -> dict[str, Any]:
        emitter.progress(job, step_index + 1, total_steps, f"running step {step_index + 1}/{total_steps}")
        return callback_kwargs

    def legacy_callback(step: int, _timestep: Any, _latents: Any) -> None:
        emitter.progress(job, step + 1, total_steps, f"running step {step + 1}/{total_steps}")

    if "callback_on_step_end" in signature.parameters:
        kwargs["callback_on_step_end"] = step_end_callback
    elif "callback" in signature.parameters:
        kwargs["callback"] = legacy_callback
        kwargs["callback_steps"] = 1


def run_t2i(req: dict[str, Any], emitter: EventEmitter, job: JobRecord) -> dict[str, Any]:
    emitter.status(job, "loading pipeline")
    transition_job(job, JobState.STARTING)
    emitter.emit_job_update(job)

    pipe, _, device, dtype, detected, cache_hit = get_or_load_pipelines(req["model"])

    lora_used = False
    if req.get("lora"):
        emitter.status(job, "loading lora")
        lora_used = maybe_load_lora(pipe, req["lora"], float(req.get("lora_scale", 1.0)))
    else:
        reset_lora_state(pipe)

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
    attach_progress_callback(pipe, kwargs, req, emitter, job)

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "running pipeline")

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start

    image = result.images[0]
    image.save(req["output"], "PNG")

    steps_per_sec = int(req["steps"]) / elapsed if elapsed > 0 else 0.0

    save_metadata(
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
    }

    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


def run_i2i(req: dict[str, Any], emitter: EventEmitter, job: JobRecord) -> dict[str, Any]:
    emitter.status(job, "loading pipeline")
    transition_job(job, JobState.STARTING)
    emitter.emit_job_update(job)

    _, pipe, device, dtype, detected, cache_hit = get_or_load_pipelines(req["model"])

    lora_used = False
    if req.get("lora"):
        emitter.status(job, "loading lora")
        lora_used = maybe_load_lora(pipe, req["lora"], float(req.get("lora_scale", 1.0)))
    else:
        reset_lora_state(pipe)

    if device == "cuda":
        generator = torch.Generator(device="cuda").manual_seed(int(req["seed"]))
    else:
        generator = torch.Generator().manual_seed(int(req["seed"]))

    input_image = Image.open(req["input_image"]).convert("RGB")

    kwargs = build_generation_kwargs(
        req,
        generator,
        {
            "image": input_image,
            "strength": float(req.get("strength", 0.6)),
        },
    )
    attach_progress_callback(pipe, kwargs, req, emitter, job)

    transition_job(job, JobState.RUNNING)
    emitter.status(job, "running pipeline")

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start

    image = result.images[0]
    image.save(req["output"], "PNG")

    steps_per_sec = int(req["steps"]) / elapsed if elapsed > 0 else 0.0

    save_metadata(
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
    }

    complete_job(job, payload)
    emitter.emit_job_update(job)
    return payload


class WorkerTCPHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        emitter = EventEmitter(self)
        line = self.rfile.readline().decode("utf-8").strip()
        if not line:
            return

        job = JobRecord(job_id=f"job_{uuid.uuid4().hex[:12]}", command="unknown")

        try:
            req = json.loads(line)
            job = create_job(req)
            emitter.emit_job_update(job)

            if req.get("command") == "ping":
                transition_job(job, JobState.COMPLETED)
                job.result = JobResult(task_type="ping")
                emitter.emit_job_update(job)
                emitter.emit({"type": "result", "ok": True, "pong": True, "job_id": job.job_id, "state": job.state.value})
                return

            if req.get("command") == "t2i":
                run_t2i(req, emitter, job)
                emitter.result(job)
                return

            if req.get("command") == "i2i":
                run_i2i(req, emitter, job)
                emitter.result(job)
                return

            emitter.error(job, f"Unknown command: {req.get('command')}", code="unknown_command")
        except Exception as exc:
            emitter.error(job, str(exc), traceback.format_exc())


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