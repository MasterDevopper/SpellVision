import json
import os
import socketserver
import threading
import time
import traceback
from typing import Any
import warnings
from datetime import datetime

warnings.filterwarnings("ignore", message="A matching Triton is not available*")
warnings.filterwarnings("ignore", category=FutureWarning, module="diffusers")

import torch
from PIL import Image
from diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion_img2img import StableDiffusionImg2ImgPipeline
from diffusers.pipelines.auto_pipeline import AutoPipelineForText2Image
from diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion import StableDiffusionPipeline
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
    "active_lora": "",
    "active_lora_scale": 1.0,
}
CACHE_LOCK = threading.Lock()


def is_local_file(path: str) -> bool:
    return os.path.isfile(path)


def is_local_dir(path: str) -> bool:
    return os.path.isdir(path)


def torch_dtype_and_device():
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


def optimize_pipeline(pipe, device: str):
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
            print("[service] xformers enabled", flush=True)
    except Exception:
        print("[service] xformers unavailable; using default attention", flush=True)

    return pipe


def unload_lora_if_possible(pipe):
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


def maybe_apply_lora_to_pipe(pipe, lora_path: str, lora_scale: float) -> bool:
    unload_lora_if_possible(pipe)

    if not lora_path:
        return False

    if not os.path.exists(lora_path):
        raise FileNotFoundError(f"LoRA file not found: {lora_path}")

    try:
        import peft  # noqa: F401
    except Exception as e:
        raise RuntimeError("LoRA support requires 'peft' in the venv.") from e

    pipe.load_lora_weights(lora_path)

    try:
        pipe.fuse_lora(lora_scale=lora_scale)
    except Exception:
        pass

    return True


def apply_lora_to_cached_pipelines(lora_path: str, lora_scale: float) -> bool:
    pipe = MODEL_CACHE["pipe"]
    img2img_pipe = MODEL_CACHE["img2img_pipe"]

    if pipe is None or img2img_pipe is None:
        return False

    used_t2i = maybe_apply_lora_to_pipe(pipe, lora_path, lora_scale)
    used_i2i = maybe_apply_lora_to_pipe(img2img_pipe, lora_path, lora_scale)

    MODEL_CACHE["active_lora"] = lora_path or ""
    MODEL_CACHE["active_lora_scale"] = lora_scale

    return used_t2i or used_i2i


def ensure_requested_lora(lora_path: str, lora_scale: float) -> bool:
    current_lora = MODEL_CACHE.get("active_lora", "")
    current_scale = MODEL_CACHE.get("active_lora_scale", 1.0)

    if current_lora == (lora_path or "") and float(current_scale) == float(lora_scale):
        return bool(lora_path)

    return apply_lora_to_cached_pipelines(lora_path, lora_scale)


def build_pipelines(model_name_or_path: str):
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


def get_or_load_pipelines(model_name_or_path: str):
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
        MODEL_CACHE["active_lora"] = ""
        MODEL_CACHE["active_lora_scale"] = 1.0

        return t2i_pipe, i2i_pipe, device, dtype, detected, False


def save_metadata(req, image_path: str, metadata_output: str, backend_name: str, device: str, dtype: str, detected_pipeline: str, lora_used: bool, elapsed: float, steps_per_sec: float):
    data = {
        "task_type": req["task_type"],
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
    with open(metadata_output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def run_t2i(req):
    pipe, _, device, dtype, detected, cache_hit = get_or_load_pipelines(req["model"])

    lora_path = req.get("lora", "")
    lora_scale = float(req.get("lora_scale", 1.0))
    lora_used = ensure_requested_lora(lora_path, lora_scale)

    if device == "cuda":
        generator = torch.Generator(device="cuda").manual_seed(int(req["seed"]))
    else:
        generator = torch.Generator().manual_seed(int(req["seed"]))

    kwargs = {
        "prompt": req["prompt"],
        "num_inference_steps": int(req["steps"]),
        "guidance_scale": float(req["cfg"]),
        "generator": generator,
        "width": int(req["width"]),
        "height": int(req["height"]),
    }
    if req.get("negative_prompt"):
        kwargs["negative_prompt"] = req["negative_prompt"]

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start

    image = result.images[0]
    image.save(req["output"], "PNG")

    steps_per_sec = req["steps"] / elapsed if elapsed > 0 else 0.0

    save_metadata(
        req,
        req["output"],
        req["metadata_output"],
        pipe.__class__.__name__,
        device,
        dtype,
        detected,
        lora_used,
        elapsed,
        steps_per_sec,
    )

    return {
        "ok": True,
        "cache_hit": cache_hit,
        "output": req["output"],
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cuda_allocated_gb": round(torch.cuda.memory_allocated() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "cuda_reserved_gb": round(torch.cuda.memory_reserved() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "active_lora": MODEL_CACHE.get("active_lora", ""),
        "active_lora_scale": MODEL_CACHE.get("active_lora_scale", 1.0),
    }


def run_i2i(req):
    _, pipe, device, dtype, detected, cache_hit = get_or_load_pipelines(req["model"])

    lora_path = req.get("lora", "")
    lora_scale = float(req.get("lora_scale", 1.0))
    lora_used = ensure_requested_lora(lora_path, lora_scale)

    if device == "cuda":
        generator = torch.Generator(device="cuda").manual_seed(int(req["seed"]))
    else:
        generator = torch.Generator().manual_seed(int(req["seed"]))

    image = Image.open(req["input_image"]).convert("RGB")

    kwargs = {
        "prompt": req["prompt"],
        "image": image,
        "strength": float(req.get("strength", 0.6)),
        "num_inference_steps": int(req["steps"]),
        "guidance_scale": float(req["cfg"]),
        "generator": generator,
    }
    if req.get("negative_prompt"):
        kwargs["negative_prompt"] = req["negative_prompt"]

    start = time.perf_counter()
    result = pipe(**kwargs)
    elapsed = time.perf_counter() - start

    out = result.images[0]
    out.save(req["output"], "PNG")

    steps_per_sec = req["steps"] / elapsed if elapsed > 0 else 0.0

    save_metadata(
        req,
        req["output"],
        req["metadata_output"],
        pipe.__class__.__name__,
        device,
        dtype,
        detected,
        lora_used,
        elapsed,
        steps_per_sec,
    )

    return {
        "ok": True,
        "cache_hit": cache_hit,
        "output": req["output"],
        "generation_time_sec": round(elapsed, 2),
        "steps_per_sec": round(steps_per_sec, 2),
        "cuda_allocated_gb": round(torch.cuda.memory_allocated() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "cuda_reserved_gb": round(torch.cuda.memory_reserved() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0,
        "active_lora": MODEL_CACHE.get("active_lora", ""),
        "active_lora_scale": MODEL_CACHE.get("active_lora_scale", 1.0),
    }


class WorkerTCPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline().decode("utf-8").strip()
        if not line:
            return
        try:
            req = json.loads(line)

            if req.get("command") == "ping":
                resp = {
                    "ok": True,
                    "pong": True,
                    "model_loaded": bool(MODEL_CACHE.get("pipe") is not None),
                    "active_model": MODEL_CACHE.get("key"),
                    "active_lora": MODEL_CACHE.get("active_lora", ""),
                }
            elif req.get("command") == "t2i":
                resp = run_t2i(req)
            elif req.get("command") == "i2i":
                resp = run_i2i(req)
            else:
                resp = {"ok": False, "error": f"Unknown command: {req.get('command')}"}
        except Exception as e:
            resp = {
                "ok": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

        self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))


def main():
    host = "127.0.0.1"
    port = 8765
    with socketserver.ThreadingTCPServer((host, port), WorkerTCPHandler) as server:
        print(f"[service] SpellVision worker service listening on {host}:{port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()