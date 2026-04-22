from __future__ import annotations

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPO_ROOT / "python"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


CORE_CODE = r'''

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


def _sv_core_wan_vae_name(object_info: dict[str, Any], stack: dict[str, Any]) -> str:
    explicit = str(stack.get("vae_path") or stack.get("vae") or "").strip()
    requested = _sv_basename(explicit)
    choices = _comfy_input_choices(object_info, "VAELoader", "vae_name")
    if not choices:
        return requested

    by_lower = {choice.lower(): choice for choice in choices}
    if requested:
        found = by_lower.get(requested.lower())
        if found:
            return found

    for preferred in ("wan2.2_vae.safetensors", "wan_2.1_vae.safetensors", "onTHEFLYWanAIWan21VideoModel_kijaiWan21VAE.safetensors"):
        found = by_lower.get(preferred.lower())
        if found:
            return found

    for choice in choices:
        lowered = choice.lower()
        if "wan" in lowered and "vae" in lowered:
            return choice

    return choices[0]


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


def _build_native_wan_core_video_prompt(req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str, job_id: str) -> dict[str, Any]:
    if command != "t2v":
        raise RuntimeError("The native WAN core adapter currently supports T2V only. Use a compiled I2V workflow for I2V until the I2V adapter is wired.")

    stack = _video_model_stack_from_request(req)
    primary_path = _first_stack_value(stack, ("primary_path", "transformer_path", "unet_path", "model_path")) or str(req.get("model") or "")
    if not primary_path:
        raise RuntimeError("The selected WAN video stack has no primary diffusion model path.")

    frames = int(req.get("frames") or req.get("num_frames") or req.get("frame_count") or 81)
    fps = int(req.get("fps") or req.get("frame_rate") or 16)
    steps = int(req.get("steps") or 30)
    width = int(req.get("width") or 832)
    height = int(req.get("height") or 480)
    cfg = float(req.get("cfg") or req.get("guidance_scale") or 5.0)
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
    _add_node(prompt, "4", unet_class, inputs)

    vae_class = _first_available_class(object_info, ("VAELoader",), label="WAN core VAE loading")
    allowed = _comfy_class_inputs(object_info, vae_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("vae_name", "vae", "model_name"), _sv_core_wan_vae_name(object_info, stack))
    _add_node(prompt, "5", vae_class, inputs)

    sampling_class = _first_available_class(object_info, ("ModelSamplingSD3",), label="WAN core model sampling config")
    allowed = _comfy_class_inputs(object_info, sampling_class)
    inputs = {}
    _set_if_allowed(inputs, allowed, ("model",), ["4", 0])
    _set_if_allowed(inputs, allowed, ("shift",), float(req.get("shift") or req.get("model_sampling_shift") or 5.0))
    _add_node(prompt, "6", sampling_class, inputs)

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
    _set_if_allowed(inputs, allowed, ("sampler_name", "sampler"), _sv_core_wan_choice(object_info, sampler_class, "sampler_name", req.get("video_sampler") or req.get("sampler"), ("dpmpp_2m", "dpm++_2m", "euler", "uni_pc", "unipc")))
    _set_if_allowed(inputs, allowed, ("scheduler", "scheduler_name"), _sv_core_wan_choice(object_info, sampler_class, "scheduler", req.get("video_scheduler") or req.get("scheduler"), ("sgm_uniform", "normal", "simple", "karras")))
    _set_if_allowed(inputs, allowed, ("positive",), ["2", 0])
    _set_if_allowed(inputs, allowed, ("negative",), ["3", 0])
    _set_if_allowed(inputs, allowed, ("latent_image", "samples"), ["7", 0])
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
    filename_prefix = str(Path(output_value).with_suffix(""))
    inputs = {}
    _set_if_allowed(inputs, allowed, ("video",), ["10", 0])
    _set_if_allowed(inputs, allowed, ("filename_prefix", "filename", "path"), filename_prefix)
    _set_if_allowed(inputs, allowed, ("format",), "mp4")
    _set_if_allowed(inputs, allowed, ("codec",), "h264")
    _add_node(prompt, "11", save_class, inputs)

    return prompt
'''


def patch_worker_service() -> None:
    path = PYTHON_ROOT / "worker_service.py"
    text = read(path)

    if "def _build_native_wan_core_video_prompt" not in text:
        marker = "def _build_native_wan_split_video_prompt"
        if marker not in text:
            raise SystemExit("Could not find _build_native_wan_split_video_prompt marker.")
        text = text.replace(marker, CORE_CODE + "\n\n" + marker, 1)

    route_pattern = re.compile(
        r'    if family_key\.startswith\("wan"\) and "WanVideoModelLoader" in object_info:\n'
        r'        req\["resolved_native_video_family"\] = "wan"\n'
        r'        return _build_native_wan_split_video_prompt\(\n'
        r'            req,\n'
        r'            object_info,\n'
        r'            command=command,\n'
        r'            family=family,\n'
        r'            job_id=job_id,\n'
        r'        \)\n'
    )
    replacement = '''    if family_key.startswith("wan"):
        req["resolved_native_video_family"] = "wan"
        if _should_use_native_wan_core_route(req, object_info) and "CLIPLoader" in object_info and "KSamplerAdvanced" in object_info:
            req["native_video_route"] = "wan_core"
            return _build_native_wan_core_video_prompt(
                req,
                object_info,
                command=command,
                family=family,
                job_id=job_id,
            )
        if "WanVideoModelLoader" in object_info:
            req["native_video_route"] = "wan_wrapper"
            return _build_native_wan_split_video_prompt(
                req,
                object_info,
                command=command,
                family=family,
                job_id=job_id,
            )
'''
    text, count = route_pattern.subn(replacement, text, count=1)
    if count == 0:
        if "_build_native_wan_core_video_prompt" not in text or "wan_core" not in text:
            raise SystemExit("Could not patch WAN route block. It may have drifted; inspect _build_native_split_video_prompt.")

    write(path, text)


def main() -> None:
    patch_worker_service()
    print("Applied Native WAN Core Route pass.")
    print("- WAN Auto now mirrors imported working Comfy graph: CLIPLoader(type='wan') + KSamplerAdvanced.")
    print("- WanVideoWrapper remains available only when explicitly selected as wrapper route.")


if __name__ == "__main__":
    main()
