"""G-graph structure gate for the Wan 2.2 A14B dual-expert (MoE) T2V builder.

Builds the dual-noise prompt from a SYNTHETIC wan_dual_noise stack (two fake expert paths) + an
object_info stub, and asserts the MoE TOPOLOGY without a render: exactly two UNETLoader (two distinct
expert paths), two ModelSamplingSD3 (shift 5.0), two chained KSamplerAdvanced with the correct
step-split and the high->low latent handoff, both text-encodes feeding both samplers, a 2.1 VAE, and
the low->decode->create->save tail. A green graph proves STRUCTURE only -- per the banked principle a
coherent image-following render is the real acceptance (Tier 2 smoke, run manually at the milestone).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import worker_service as ws  # noqa: E402


HIGH = "D:/AI_ASSETS/models/diffusion_models/wan22_t2v_high_noise_14B_fp8_scaled.safetensors"
LOW = "D:/AI_ASSETS/models/diffusion_models/wan22_t2v_low_noise_14B_fp8_scaled.safetensors"


def _combo(*choices):
    return [list(choices), {}]


# object_info stub: each class declares the input names the builder sets; COMBO inputs carry choices
# where resolution matters (weight_dtype "default", a 2.1 VAE present, euler/simple).
OBJECT_INFO = {
    "CLIPLoader": {"input": {"required": {
        "clip_name": _combo("umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
        "type": _combo("wan", "sdxl"),
        "device": _combo("default"),
    }}},
    "CLIPTextEncode": {"input": {"required": {"clip": ["CLIP"], "text": ["STRING", {}]}}},
    "UNETLoader": {"input": {"required": {
        "unet_name": _combo(os.path.basename(HIGH), os.path.basename(LOW)),
        "weight_dtype": _combo("default", "fp8_e4m3fn"),
    }}},
    "VAELoader": {"input": {"required": {"vae_name": _combo("wan2.2_vae.safetensors", "wan_2.1_vae.safetensors")}}},
    "ModelSamplingSD3": {"input": {"required": {"model": ["MODEL"], "shift": ["FLOAT", {"default": 5.0}]}}},
    "EmptyHunyuanLatentVideo": {"input": {"required": {
        "width": ["INT", {}], "height": ["INT", {}], "length": ["INT", {}], "batch_size": ["INT", {}],
    }}},
    "KSamplerAdvanced": {"input": {"required": {
        "model": ["MODEL"], "add_noise": _combo("enable", "disable"), "noise_seed": ["INT", {}],
        "steps": ["INT", {}], "cfg": ["FLOAT", {}], "sampler_name": _combo("euler", "dpmpp_2m"),
        "scheduler": _combo("simple", "normal", "sgm_uniform"), "positive": ["CONDITIONING"], "negative": ["CONDITIONING"],
        "latent_image": ["LATENT"], "start_at_step": ["INT", {}], "end_at_step": ["INT", {}],
        "return_with_leftover_noise": _combo("enable", "disable"),
    }}},
    "VAEDecode": {"input": {"required": {"samples": ["LATENT"], "vae": ["VAE"]}}},
    "CreateVideo": {"input": {"required": {"images": ["IMAGE"], "fps": ["INT", {}]}}},
    "SaveVideo": {"input": {"required": {
        "video": ["VIDEO"], "filename_prefix": ["STRING", {}], "format": _combo("mp4"), "codec": _combo("h264"),
    }}},
    "LoraLoaderModelOnly": {"input": {"required": {
        "model": ["MODEL"],
        "lora_name": _combo("wan22_high_noise_lora.safetensors", "wan22_low_noise_lora.safetensors", "my_style_lora.safetensors"),
        "strength_model": ["FLOAT", {"default": 1.0}],
    }}},
}

STEPS = 20
SPLIT = STEPS // 2  # 10

HIGH_LORA = "D:/AI_ASSETS/models/loras/wan22_high_noise_lora.safetensors"   # -> high expert only
LOW_LORA = "D:/AI_ASSETS/models/loras/wan22_low_noise_lora.safetensors"     # -> low expert only
CONTENT_LORA = "D:/AI_ASSETS/models/loras/my_style_lora.safetensors"        # -> both experts


def _dual_noise_req(**overrides):
    stack = {
        "stack_kind": "wan_dual_noise",
        "high_noise_path": HIGH,
        "low_noise_path": LOW,
        "text_encoder_path": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    }
    req = {
        "command": "t2v",
        "native_video_stack_kind": "wan_dual_noise",
        "video_model_stack": stack,
        "prompt": "a calm ocean wave rolling to shore",
        "negative_prompt": "blurry",
        "steps": STEPS, "cfg": 3.5, "width": 832, "height": 480, "frames": 81, "fps": 16, "seed": 42,
    }
    req.update(overrides)
    return req


def _build(**overrides):
    return ws._build_native_wan_dual_noise_video_prompt(
        _dual_noise_req(**overrides), OBJECT_INFO, command="t2v", family="wan", job_id="jtest",
    )


def _nodes_of(prompt, cls):
    return {nid: node for nid, node in prompt.items() if node.get("class_type") == cls}


def test_dual_noise_graph_structure():
    prompt = _build()

    # --- exactly two UNETLoader, two distinct expert paths ---
    unets = _nodes_of(prompt, "UNETLoader")
    assert len(unets) == 2, f"expected 2 UNETLoader, got {len(unets)}: {list(unets)}"
    unet_names = {n["inputs"].get("unet_name") for n in unets.values()}
    assert unet_names == {os.path.basename(HIGH), os.path.basename(LOW)}, f"expert paths not distinct/correct: {unet_names}"
    for n in unets.values():
        assert n["inputs"].get("weight_dtype") == "default", f"UNETLoader weight_dtype must be 'default', got {n['inputs'].get('weight_dtype')}"

    # --- two ModelSamplingSD3, shift 5.0, each wrapping a distinct UNET ---
    ms = _nodes_of(prompt, "ModelSamplingSD3")
    assert len(ms) == 2, f"expected 2 ModelSamplingSD3, got {len(ms)}"
    assert all(float(n["inputs"].get("shift")) == 5.0 for n in ms.values()), "ModelSamplingSD3 shift must be 5.0"
    ms_unet_refs = {n["inputs"]["model"][0] for n in ms.values()}
    assert ms_unet_refs == set(unets.keys()), "each ModelSamplingSD3 must wrap a distinct UNETLoader"

    # --- two KSamplerAdvanced; identify high (start=0) vs low (start=split) ---
    samplers = _nodes_of(prompt, "KSamplerAdvanced")
    assert len(samplers) == 2, f"expected 2 KSamplerAdvanced, got {len(samplers)}"
    high = next((nid for nid, n in samplers.items() if n["inputs"].get("start_at_step") == 0), None)
    low = next((nid for nid, n in samplers.items() if n["inputs"].get("start_at_step") == SPLIT), None)
    assert high is not None and low is not None, f"could not identify high/low samplers by start_at_step: {samplers}"
    h, l = samplers[high]["inputs"], samplers[low]["inputs"]

    # --- the step split: high [0, split) with leftover noise -> low [split, steps] ---
    assert h["end_at_step"] == SPLIT, f"high end_at_step must be split ({SPLIT}), got {h['end_at_step']}"
    assert l["start_at_step"] == SPLIT, f"low start_at_step must be split ({SPLIT}), got {l['start_at_step']}"
    assert l["end_at_step"] == STEPS, f"low end_at_step must be steps ({STEPS}), got {l['end_at_step']}"
    assert h["add_noise"] == "enable" and h["return_with_leftover_noise"] == "enable", "high sampler must add noise + return leftover"
    assert l["add_noise"] == "disable" and l["return_with_leftover_noise"] == "disable", "low sampler must not add noise + not return leftover"

    # --- THE MoE HANDOFF: low latent_image = HIGH sampler output; high latent_image = empty latent ---
    latent = _nodes_of(prompt, "EmptyHunyuanLatentVideo")
    assert len(latent) == 1, "expected one EmptyHunyuanLatentVideo"
    latent_id = next(iter(latent))
    assert h["latent_image"] == [latent_id, 0], f"high sampler must read the empty latent, got {h['latent_image']}"
    assert l["latent_image"] == [high, 0], f"low sampler must read the HIGH sampler output {high}, got {l['latent_image']}"

    # --- each sampler takes its OWN expert's model chain (distinct ModelSamplingSD3) ---
    assert h["model"][0] != l["model"][0], "the two samplers must take different ModelSamplingSD3 (distinct experts)"
    assert {h["model"][0], l["model"][0]} == set(ms.keys())

    # --- both text-encodes feed BOTH samplers ---
    encodes = _nodes_of(prompt, "CLIPTextEncode")
    assert len(encodes) == 2, f"expected 2 CLIPTextEncode, got {len(encodes)}"
    assert h["positive"] == l["positive"], "both samplers must share the same positive encode"
    assert h["negative"] == l["negative"], "both samplers must share the same negative encode"
    assert h["positive"][0] in encodes and h["negative"][0] in encodes, "sampler pos/neg must reference CLIPTextEncode nodes"
    assert h["positive"][0] != h["negative"][0], "positive and negative must be distinct encodes"

    # --- VAE = a 2.1 VAE (the A14B dual-noise fix, not the 2.2 the filename probe would pick) ---
    vae = _nodes_of(prompt, "VAELoader")
    assert len(vae) == 1
    vae_name = next(iter(vae.values()))["inputs"].get("vae_name")
    assert "2.1" in str(vae_name), f"dual-noise VAE must be a 2.1 VAE, got {vae_name!r}"

    # --- tail: low -> VAEDecode -> CreateVideo -> SaveVideo ---
    decode = _nodes_of(prompt, "VAEDecode")
    create = _nodes_of(prompt, "CreateVideo")
    save = _nodes_of(prompt, "SaveVideo")
    assert len(decode) == 1 and len(create) == 1 and len(save) == 1
    decode_id = next(iter(decode))
    create_id = next(iter(create))
    assert next(iter(decode.values()))["inputs"]["samples"] == [low, 0], "VAEDecode must read the LOW sampler output"
    assert next(iter(create.values()))["inputs"]["images"] == [decode_id, 0], "CreateVideo must read VAEDecode"
    assert next(iter(save.values()))["inputs"]["video"] == [create_id, 0], "SaveVideo must read CreateVideo"


def test_dual_noise_overrides_explicit_2_2_vae():
    """THE REGRESSION GATE for the 48-vs-16 decode crash. A real frontend sends a FULLY-POPULATED
    stack including an explicit VAE (it defaults to wan2.2_vae for a "2.2" model). The dual-noise
    builder must OVERRIDE that explicit 2.2 VAE with the architecturally-required 16-ch 2.1 VAE --
    the 48-ch 2.2 VAE crashes VAEDecode on the 16-ch latent the 14B experts produce. The original
    structure test missed this because it sent NO explicit VAE; this one mimics the frontend."""
    prompt = _build(video_model_stack={
        "stack_kind": "wan_dual_noise",
        "high_noise_path": HIGH,
        "low_noise_path": LOW,
        "text_encoder_path": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "vae": "wan2.2_vae.safetensors",                                   # the frontend's (wrong) explicit VAE
        "vae_path": "D:/AI_ASSETS/models/vae/wan2.2_vae.safetensors",
    })
    vae = _nodes_of(prompt, "VAELoader")
    vae_name = str(next(iter(vae.values()))["inputs"].get("vae_name"))
    assert "2.1" in vae_name, f"dual-noise must OVERRIDE the explicit 2.2 VAE with a 2.1 VAE, got {vae_name!r}"
    assert "2.2" not in vae_name, f"dual-noise must NOT emit the 2.2 VAE (48-ch -> decode crash), got {vae_name!r}"


def test_single_model_wan_still_honors_explicit_vae():
    """The dual-noise VAE fix must NOT change single-model Wan: 'explicit wins' still holds. An explicit
    2.2 VAE overrides even a 2.1-marked primary here (the exact opposite of the dual-noise override) --
    proving the fix is scoped to the dual-noise builder and the resolver rule is untouched for others."""
    req = {
        "command": "t2v",
        "video_model_stack": {
            "primary_path": "D:/AI_ASSETS/models/diffusion_models/wan2.1_t2v_14B.safetensors",  # 2.1-marked -> probe would pick 2.1
            "vae": "wan2.2_vae.safetensors",  # ...but the explicit VAE must win
        },
        "prompt": "x", "negative_prompt": "",
        "steps": 20, "cfg": 3.5, "width": 832, "height": 480, "frames": 81, "fps": 16, "seed": 1,
    }
    prompt = ws._build_native_wan_core_video_prompt(req, OBJECT_INFO, command="t2v", family="wan", job_id="jtest")
    vae = _nodes_of(prompt, "VAELoader")
    vae_name = str(next(iter(vae.values()))["inputs"].get("vae_name"))
    assert vae_name == "wan2.2_vae.safetensors", f"single-model Wan must HONOR the explicit VAE (explicit wins), got {vae_name!r}"


def test_dual_noise_missing_high_expert_raises():
    req = _dual_noise_req()
    req["video_model_stack"] = {k: v for k, v in req["video_model_stack"].items() if "high" not in k}
    with pytest.raises(RuntimeError, match="HIGH-noise expert"):
        ws._build_native_wan_dual_noise_video_prompt(req, OBJECT_INFO, command="t2v", family="wan", job_id="jtest")


def test_dual_noise_missing_low_expert_raises():
    req = _dual_noise_req()
    req["video_model_stack"] = {k: v for k, v in req["video_model_stack"].items() if "low" not in k}
    with pytest.raises(RuntimeError, match="LOW-noise expert"):
        ws._build_native_wan_dual_noise_video_prompt(req, OBJECT_INFO, command="t2v", family="wan", job_id="jtest")


def test_dual_noise_i2v_refused():
    with pytest.raises(RuntimeError, match="T2V only"):
        ws._build_native_wan_dual_noise_video_prompt(_dual_noise_req(command="i2v"), OBJECT_INFO, command="i2v", family="wan", job_id="jtest")


def test_steps_overridable_split_tracks():
    # split = steps//2 must track an overridden step count (reachable LoRA path: steps=4 -> split=2).
    prompt = _build(steps=4)
    samplers = _nodes_of(prompt, "KSamplerAdvanced")
    highs = [n["inputs"] for n in samplers.values() if n["inputs"]["start_at_step"] == 0]
    assert highs and highs[0]["end_at_step"] == 2, "steps=4 must yield split=2"


# --------------------------------------------------------------------------- LoRA chaining

def _trace_model_chain(prompt, start_ref):
    """Walk model refs backward from start_ref (a ModelSamplingSD3.model input) through the LoRA chain
    to the UNETLoader. Returns (unet_id, [(lora_id, lora_node), ...] in UNET->ModelSamplingSD3 order)."""
    ref = start_ref
    chain = []
    for _ in range(64):
        nid = ref[0]
        node = prompt[nid]
        ct = node.get("class_type")
        if ct == "LoraLoaderModelOnly":
            chain.append((nid, node))
            ref = node["inputs"]["model"]
        elif ct == "UNETLoader":
            return nid, list(reversed(chain))
        else:
            raise AssertionError(f"unexpected node in model chain: {nid} {ct}")
    raise AssertionError("model chain did not terminate at a UNETLoader (cycle?)")


def _high_low_ms(prompt):
    """Return (high_ms_id, low_ms_id): the ModelSamplingSD3 feeding the high (start=0) / low samplers."""
    samplers = _nodes_of(prompt, "KSamplerAdvanced")
    high = next(n for n in samplers.values() if n["inputs"]["start_at_step"] == 0)
    low = next(n for n in samplers.values() if n["inputs"]["start_at_step"] != 0)
    return high["inputs"]["model"][0], low["inputs"]["model"][0]


def test_lora_chain_routing_and_threading():
    """high_noise LoRA -> high chain, low_noise LoRA -> low chain, content LoRA -> BOTH; each chain sits
    between its UNETLoader and its ModelSamplingSD3, threaded node-to-node, strengths preserved."""
    prompt = _build(lora_stack=[
        {"name": HIGH_LORA, "display": "hi", "strength": 1.5, "enabled": True},
        {"name": LOW_LORA, "display": "lo", "strength": 0.8, "enabled": True},
        {"name": CONTENT_LORA, "display": "style", "strength": 0.6, "enabled": True},
    ])
    high_ms, low_ms = _high_low_ms(prompt)

    # HIGH expert chain: [high LoRA, content LoRA], between UNET "4" and its ModelSamplingSD3
    unet_h, chain_h = _trace_model_chain(prompt, prompt[high_ms]["inputs"]["model"])
    assert unet_h == "4", f"high chain must terminate at the high UNETLoader (4), got {unet_h}"
    names_h = [n["inputs"]["lora_name"] for _id, n in chain_h]
    assert names_h == ["wan22_high_noise_lora.safetensors", "my_style_lora.safetensors"], f"high routing wrong: {names_h}"
    assert [n["inputs"]["strength_model"] for _id, n in chain_h] == [1.5, 0.6], "high strengths not preserved"

    # LOW expert chain: [low LoRA, content LoRA], between UNET "12" and its ModelSamplingSD3
    unet_l, chain_l = _trace_model_chain(prompt, prompt[low_ms]["inputs"]["model"])
    assert unet_l == "12", f"low chain must terminate at the low UNETLoader (12), got {unet_l}"
    names_l = [n["inputs"]["lora_name"] for _id, n in chain_l]
    assert names_l == ["wan22_low_noise_lora.safetensors", "my_style_lora.safetensors"], f"low routing wrong: {names_l}"
    assert [n["inputs"]["strength_model"] for _id, n in chain_l] == [0.8, 0.6], "low strengths not preserved"

    # THREADING (the anti-vacuity target): the 2nd node reads the 1st node's OUTPUT, not the UNETLoader.
    first_h, second_h = chain_h[0][0], chain_h[1][0]
    assert prompt[second_h]["inputs"]["model"] == [first_h, 0], (
        f"chain mis-threaded: 2nd LoRA reads {prompt[second_h]['inputs']['model']}, expected [{first_h!r}, 0]"
    )
    assert prompt[chain_h[0][0]]["inputs"]["model"] == ["4", 0], "first high LoRA must read the UNETLoader"


def test_lora_disabled_entry_excluded():
    prompt = _build(lora_stack=[
        {"name": CONTENT_LORA, "display": "on", "strength": 1.0, "enabled": True},
        {"name": HIGH_LORA, "display": "off", "strength": 1.0, "enabled": False},
    ])
    names = {n["inputs"]["lora_name"] for n in _nodes_of(prompt, "LoraLoaderModelOnly").values()}
    assert "wan22_high_noise_lora.safetensors" not in names, "disabled LoRA must not appear in the graph"
    assert names == {"my_style_lora.safetensors"}, f"only the enabled content LoRA should appear, got {names}"


def test_no_lora_emits_no_lora_nodes_and_ms_reads_unet():
    """No lora_stack -> zero LoraLoaderModelOnly nodes, and each ModelSamplingSD3 reads its UNETLoader
    directly (the no-LoRA path is byte-identical to the pre-LoRA structure)."""
    prompt = _build()  # no lora_stack
    assert _nodes_of(prompt, "LoraLoaderModelOnly") == {}, "no LoRA nodes when the stack is empty"
    high_ms, low_ms = _high_low_ms(prompt)
    assert prompt[high_ms]["inputs"]["model"] == ["4", 0], "high ModelSamplingSD3 must read UNET 4 directly"
    assert prompt[low_ms]["inputs"]["model"] == ["12", 0], "low ModelSamplingSD3 must read UNET 12 directly"


def test_per_expert_shift_wiring():
    prompt = _build(high_noise_shift=3.0, low_noise_shift=8.0)
    high_ms, low_ms = _high_low_ms(prompt)
    assert float(prompt[high_ms]["inputs"]["shift"]) == 3.0, "high_noise_shift must land on the high ModelSamplingSD3"
    assert float(prompt[low_ms]["inputs"]["shift"]) == 8.0, "low_noise_shift must land on the low ModelSamplingSD3"


def test_pairing_guard_mismatched_variant_raises():
    # t2v high + i2v low = off-model pairing -> hard error naming the mismatch.
    with pytest.raises(RuntimeError, match="expert mismatch"):
        _build(video_model_stack={
            "stack_kind": "wan_dual_noise",
            "high_noise_path": "D:/AI_ASSETS/models/diffusion_models/wan22_t2v_high_noise_14B_fp8_scaled.safetensors",
            "low_noise_path": "D:/AI_ASSETS/models/diffusion_models/wan22_i2v_low_noise_14B_fp8_scaled.safetensors",
        })


# --------------------------------------------------------------------------- operating-point table (Phase 1)

def test_omitted_steps_resolves_from_quality_table():
    """Integration: a request that OMITS steps resolves from the wan/quality operating point (28,
    split 14) THROUGH the builder -- proving the operating-point table is actually consulted, not the
    inline literal (which would give 20)."""
    req = _dual_noise_req()
    del req["steps"]  # no steps -> resolver fills from wan/quality default (28)
    prompt = ws._build_native_wan_dual_noise_video_prompt(req, OBJECT_INFO, command="t2v", family="wan", job_id="jtest")
    samplers = _nodes_of(prompt, "KSamplerAdvanced")
    high = next(n["inputs"] for n in samplers.values() if n["inputs"]["start_at_step"] == 0)
    assert high["steps"] == 28, f"omitted steps must resolve to the quality table's 28, got {high['steps']}"
    assert high["end_at_step"] == 14, f"split must be 28//2=14, got {high['end_at_step']}"


# --------------------------------------------------------------------------- Phase 2a builder-level gates
# The literal safety net SURVIVES each routed builder, so these prove the TABLE is consulted BEFORE it
# (corrupting the table changes the builder output -> not shadowed by the literal).

def test_native_video_kwargs_lifts_diffusers_defaults():
    # pure function; wan_diffusers default = steps 30 / cfg 5.0.
    kw = ws._native_video_kwargs({"prompt": "x"}, "t2v")
    assert kw["num_inference_steps"] == 30, f"omitted steps -> wan_diffusers table 30, got {kw['num_inference_steps']}"
    assert kw["guidance_scale"] == 5.0, f"omitted cfg -> wan_diffusers table 5.0, got {kw['guidance_scale']}"


def _wan_core_req():
    return {
        "command": "t2v",
        "video_model_stack": {
            "primary_path": "D:/AI_ASSETS/models/diffusion_models/wan2.2_t2v_14B.safetensors",
        },
        "prompt": "a wave", "negative_prompt": "",
        "width": 832, "height": 480, "frames": 81, "fps": 16, "seed": 1,
        # NOTE: no steps / cfg / sampler / scheduler / shift -> must come from the wan_core table.
    }


def test_wan_core_lifts_defaults_through_builder():
    prompt = ws._build_native_wan_core_video_prompt(_wan_core_req(), OBJECT_INFO, command="t2v", family="wan", job_id="jtest")
    sampler = next(n["inputs"] for n in _nodes_of(prompt, "KSamplerAdvanced").values())
    ms = next(n["inputs"] for n in _nodes_of(prompt, "ModelSamplingSD3").values())
    assert sampler["steps"] == 30, f"omitted steps -> wan_core table 30, got {sampler['steps']}"
    assert sampler["cfg"] == 5.0, f"omitted cfg -> wan_core table 5.0, got {sampler['cfg']}"
    assert sampler["sampler_name"] == "dpmpp_2m", f"omitted sampler -> wan_core table dpmpp_2m, got {sampler['sampler_name']}"
    assert sampler["scheduler"] == "sgm_uniform", f"omitted scheduler -> wan_core table sgm_uniform, got {sampler['scheduler']}"
    assert float(ms["shift"]) == 5.0, f"omitted shift -> wan_core table 5.0, got {ms['shift']}"
