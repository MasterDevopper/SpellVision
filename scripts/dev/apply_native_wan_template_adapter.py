from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "python" / "worker_service.py"

if not WORKER.exists():
    raise SystemExit(f"worker_service.py not found at {WORKER}")

text = WORKER.read_text(encoding="utf-8")


def replace_once(haystack: str, old: str, new: str, label: str) -> str:
    if old not in haystack:
        raise SystemExit(f"Could not find {label}; patch not applied.")
    return haystack.replace(old, new, 1)


# Keep empty negative prompt text valid for text encoder nodes.
text = re.sub(
    r'def _set_if_allowed\(inputs: dict\[str, Any\], allowed: set\[str\], aliases: tuple\[str, \.\.\.\], value: Any\) -> bool:\n'
    r'    if value in \(None, ""\):\n'
    r'        return False\n'
    r'    for name in aliases:\n'
    r'        if name in allowed:\n'
    r'            inputs\[name\] = value\n'
    r'            return True\n'
    r'    return False\n',
    '''def _set_if_allowed(inputs: dict[str, Any], allowed: set[str], aliases: tuple[str, ...], value: Any) -> bool:
    if value is None:
        return False
    for name in aliases:
        if name in allowed:
            inputs[name] = value
            return True
    return False
''',
    text,
    count=1,
)

# Improve default extraction for modern Comfy schemas like ["COMBO", {"default": "auto", "options": [...]}].
input_default_pattern = re.compile(
    r'def _input_default_choice\(object_info: dict\[str, Any\], class_name: str, input_name: str, fallback: Any = None\) -> Any:\n'
    r'.*?\n\n\ndef _clip_loader_type_for_family',
    re.DOTALL,
)
input_default_replacement = '''def _input_default_choice(object_info: dict[str, Any], class_name: str, input_name: str, fallback: Any = None) -> Any:
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



def _clip_loader_type_for_family'''
text, count = input_default_pattern.subn(input_default_replacement, text, count=1)
if count != 1:
    raise SystemExit("Could not replace _input_default_choice; patch not applied.")

# Make local validator allow empty strings for text prompt inputs.
if "def _required_input_allows_empty" not in text:
    marker = "def _validate_comfy_prompt_against_object_info"
    helper = '''def _required_input_allows_empty(class_type: str, input_name: str) -> bool:
    class_key = str(class_type or "").strip().lower()
    input_key = str(input_name or "").strip().lower()

    if input_key in {"text", "prompt", "positive_prompt", "negative_prompt"}:
        if "textencode" in class_key or "textencode" in class_key.replace("_", ""):
            return True
        if "wanvideotextencode" in class_key:
            return True

    return False


'''
    text = text.replace(marker, helper + marker, 1)

text = text.replace(
    '''            value = inputs.get(input_name)
            if value is None or value == "":
                issues.append(f"node {node_id} ({class_type}): required input {input_name!r} is empty")
                continue
''',
    '''            value = inputs.get(input_name)
            if value is None:
                issues.append(f"node {node_id} ({class_type}): required input {input_name!r} is empty")
                continue
            if value == "" and not _required_input_allows_empty(class_type, input_name):
                issues.append(f"node {node_id} ({class_type}): required input {input_name!r} is empty")
                continue
''',
    1,
)

wan_helpers = r'''

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
    fps = int(req.get("fps") or req.get("frame_rate") or 16)
    steps = int(req.get("steps") or 30)
    cfg = float(req.get("cfg") or req.get("cfg_scale") or 6.0)
    shift = float(req.get("sampling_shift") or req.get("shift") or 5.0)
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
    _set_if_allowed(inputs, allowed, ("force_offload",), True)
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
    _set_if_allowed(inputs, allowed, ("scheduler",), str(req.get("scheduler") or "unipc"))
    _set_if_allowed(inputs, allowed, ("riflex_freq_index",), int(req.get("riflex_freq_index") or 0))
    _set_if_allowed(inputs, allowed, ("denoise_strength",), float(req.get("denoise") or req.get("denoise_strength") or 1.0))
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

    return prompt
'''

if "def _build_native_wan_split_video_prompt" not in text:
    marker = "def _build_native_split_video_prompt"
    if marker not in text:
        raise SystemExit("Could not find _build_native_split_video_prompt marker.")
    text = text.replace(marker, wan_helpers + "\n\n" + marker, 1)

# Dispatch WAN split-stack generation to the WAN wrapper template.
dispatch_needle = '''def _build_native_split_video_prompt(
    req: dict[str, Any],
    object_info: dict[str, Any],
    *,
    command: str,
    family: str,
    job_id: str,
) -> dict[str, Any]:
'''
dispatch_replacement = dispatch_needle + '''    family_key = str(family or "").strip().lower().replace("-", "_")
    if family_key.startswith("wan") and "WanVideoModelLoader" in object_info:
        return _build_native_wan_split_video_prompt(
            req,
            object_info,
            command=command,
            family=family,
            job_id=job_id,
        )

'''
if "return _build_native_wan_split_video_prompt" not in text:
    text = replace_once(text, dispatch_needle, dispatch_replacement, "WAN dispatch insertion point")

WORKER.write_text(text, encoding="utf-8")
print("Native WAN template adapter patch applied to python/worker_service.py")
print("- WAN split-stack T2V now uses WanVideoModelLoader / LoadWanVideoT5TextEncoder / WanVideoVAELoader / WanVideoSampler / WanVideoDecode / CreateVideo / SaveVideo")
print("- Generic native split-stack template is still retained for non-WAN families")
