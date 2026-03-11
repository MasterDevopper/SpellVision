import argparse
import json
import os
import sys
import time
import traceback
import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="diffusers")
warnings.filterwarnings("ignore", message="A matching Triton is not available*")
from datetime import datetime

import torch
from PIL import Image

from diffusers.pipelines.auto_pipeline import AutoPipelineForText2Image
from diffusers.pipelines.stable_diffusion.pipeline_stable_diffusion import StableDiffusionPipeline
from diffusers.pipelines.stable_diffusion_xl.pipeline_stable_diffusion_xl import StableDiffusionXLPipeline

try:
    from diffusers.pipelines.stable_diffusion_3.pipeline_stable_diffusion_3 import StableDiffusion3Pipeline
except Exception:
    StableDiffusion3Pipeline = None

try:
    from diffusers.pipelines.flux.pipeline_flux import FluxPipeline
except Exception:
    FluxPipeline = None


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
            print("[worker] xformers enabled")
    except Exception:
        print("[worker] xformers unavailable; continuing with default attention")

    return pipe


def load_pipeline(model_name_or_path: str):
    dtype, device = torch_dtype_and_device()
    detected = detect_pipeline_type(model_name_or_path)

    print(f"[worker] loading model: {model_name_or_path}")
    print(f"[worker] detected_pipeline={detected}")
    print(f"[worker] device={device}, dtype={dtype}")

    pipe = None

    if is_local_file(model_name_or_path):
        first_error = None

        try:
            print("[worker] trying StableDiffusionXLPipeline.from_single_file(...)")
            pipe = StableDiffusionXLPipeline.from_single_file(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=model_name_or_path.lower().endswith(".safetensors"),
            )
        except Exception as e:
            first_error = e
            print(f"[worker] SDXL single-file load failed: {e}")

        if pipe is None:
            try:
                print("[worker] trying StableDiffusionPipeline.from_single_file(...)")
                pipe = StableDiffusionPipeline.from_single_file(
                    model_name_or_path,
                    torch_dtype=dtype,
                    use_safetensors=model_name_or_path.lower().endswith(".safetensors"),
                )
            except Exception as e:
                print(f"[worker] SD single-file load failed: {e}")
                raise RuntimeError("Failed to load single-file checkpoint.") from e if first_error is None else e

    elif is_local_dir(model_name_or_path):
        if detected == "flux" and FluxPipeline is not None:
            pipe = FluxPipeline.from_pretrained(model_name_or_path, torch_dtype=dtype)
        elif detected == "sd3" and StableDiffusion3Pipeline is not None:
            pipe = StableDiffusion3Pipeline.from_pretrained(model_name_or_path, torch_dtype=dtype)
        elif detected == "sdxl":
            pipe = StableDiffusionXLPipeline.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
            )
        else:
            pipe = AutoPipelineForText2Image.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
            )
    else:
        if detected == "flux" and FluxPipeline is not None:
            pipe = FluxPipeline.from_pretrained(model_name_or_path, torch_dtype=dtype)
        elif detected == "sd3" and StableDiffusion3Pipeline is not None:
            pipe = StableDiffusion3Pipeline.from_pretrained(model_name_or_path, torch_dtype=dtype)
        elif detected == "sdxl":
            pipe = StableDiffusionXLPipeline.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
                variant="fp16" if device == "cuda" else None,
            )
        else:
            pipe = AutoPipelineForText2Image.from_pretrained(
                model_name_or_path,
                torch_dtype=dtype,
                use_safetensors=True,
            )

    pipe = pipe.to(device)
    pipe = optimize_pipeline(pipe, device)

    return pipe, device, str(dtype), detected


def maybe_load_lora(pipe, lora_path: str, lora_scale: float):
    if not lora_path:
        return False

    if not os.path.exists(lora_path):
        raise FileNotFoundError(f"LoRA file not found: {lora_path}")

    try:
        import peft  # noqa: F401
    except Exception as e:
        raise RuntimeError(
            "LoRA support requires the 'peft' package in your .venv. Install it with: pip install peft"
        ) from e

    print(f"[worker] loading LoRA: {lora_path} (scale={lora_scale})")
    pipe.load_lora_weights(lora_path)

    try:
        pipe.fuse_lora(lora_scale=lora_scale)
        print("[worker] fused LoRA")
    except Exception as e:
        print(f"[worker] fuse_lora failed or unavailable: {e}")

    return True


def save_metadata(args, image_path: str, metadata_output: str, backend_name: str, device: str, dtype: str, detected_pipeline: str, lora_used: bool):
    metadata = {
        "task_type": "t2i",
        "generator": "spellvision_diffusers_worker",
        "backend": backend_name,
        "detected_pipeline": detected_pipeline,
        "timestamp": datetime.now().isoformat(),
        "prompt": args.prompt,
        "negative_prompt": args.negative_prompt,
        "model": args.model,
        "lora_path": args.lora if args.lora else "",
        "lora_scale": args.lora_scale,
        "lora_used": lora_used,
        "width": args.width,
        "height": args.height,
        "steps": args.steps,
        "cfg": args.cfg,
        "seed": args.seed,
        "device": device,
        "dtype": dtype,
        "image_path": image_path,
    }

    os.makedirs(os.path.dirname(metadata_output), exist_ok=True)
    with open(metadata_output, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"[worker] wrote metadata {metadata_output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--model", required=True)
    parser.add_argument("--lora", default="")
    parser.add_argument("--lora-scale", type=float, default=1.0)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--cfg", type=float, default=7.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata-output", required=True)
    args = parser.parse_args()

    try:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)

        print("[worker] starting real T2I render")
        print(f"[worker] prompt={args.prompt}")
        print(
            f"[worker] model={args.model}, size={args.width}x{args.height}, "
            f"steps={args.steps}, cfg={args.cfg}, seed={args.seed}"
        )

        pipe, device, dtype, detected = load_pipeline(args.model)
        lora_used = maybe_load_lora(pipe, args.lora, args.lora_scale)

        if device == "cuda":
            generator = torch.Generator(device="cuda").manual_seed(args.seed)
        else:
            generator = torch.Generator().manual_seed(args.seed)

        run_kwargs = {
            "prompt": args.prompt,
            "width": args.width,
            "height": args.height,
            "num_inference_steps": args.steps,
            "guidance_scale": args.cfg,
            "generator": generator,
        }

        if args.negative_prompt.strip():
            run_kwargs["negative_prompt"] = args.negative_prompt

        print("[worker] running pipeline...")
        start_time = time.perf_counter()
        result = pipe(**run_kwargs)
        end_time = time.perf_counter()

        image = result.images[0]
        elapsed = end_time - start_time
        steps_per_sec = (args.steps / elapsed) if elapsed > 0 else 0.0

        if not isinstance(image, Image.Image):
            raise RuntimeError("Pipeline did not return a PIL image.")

        image.save(args.output, "PNG")
        print(f"[worker] wrote image {args.output}")
        print(f"[worker] generation_time_sec={elapsed:.2f}")
        print(f"[worker] steps_per_sec={steps_per_sec:.2f}")

        if torch.cuda.is_available():
            allocated_gb = torch.cuda.memory_allocated() / (1024 ** 3)
            reserved_gb = torch.cuda.memory_reserved() / (1024 ** 3)
            print(f"[worker] cuda_allocated_gb={allocated_gb:.2f}")
            print(f"[worker] cuda_reserved_gb={reserved_gb:.2f}")

        save_metadata(
            args=args,
            image_path=args.output,
            metadata_output=args.metadata_output,
            backend_name=pipe.__class__.__name__,
            device=device,
            dtype=dtype,
            detected_pipeline=detected,
            lora_used=lora_used,
        )

        print("[worker] generation complete")

    except Exception as e:
        print(f"[worker] ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()