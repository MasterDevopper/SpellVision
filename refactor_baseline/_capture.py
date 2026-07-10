"""Family-plugin refactor BASELINE capture (STEP-0 scoping pass, Part C).

Builds the submitted native prompt graph for every registered family via the CURRENT
code, deterministically (fixed request), and writes refactor_baseline/<family>.json.
This is the behavior-preservation contract: the eventual per-family extraction must
reproduce these graphs structurally-identically. Graph construction ONLY -- no render.

Run:  .venv/Scripts/python.exe refactor_baseline/_capture.py
"""
import json, os, sys, traceback
sys.path.insert(0, r"C:\Users\xXste\Code_Projects\SpellVision\python")
import worker_service as ws

BASE = "http://127.0.0.1:8188"
OUT = os.path.dirname(os.path.abspath(__file__))

# Fixed, deterministic request knobs shared by all families (per-family builders may
# override cfg/steps by design -- that IS the captured behavior).
FIX = dict(prompt="a lighthouse on a rocky coast at dawn, detailed",
           negative_prompt="low quality, blurry",
           width=1024, height=1024, seed=12345, cfg=6.5, steps=30)

IMAGE_FAMILIES = {
    "flux":    r"D:/AI_ASSETS/models/checkpoints/flux/fluxmania_kreamania.safetensors",
    "pixart":  r"D:/AI_ASSETS/models/checkpoints/pixart/pixartSigma1024px_1024pxV04.safetensors",
    "lumina":  r"D:/AI_ASSETS/models/checkpoints/lumina/lumina_2.safetensors",
    "z_image": r"D:/AI_ASSETS/models/diffusion_models/z-image/z_image_turbo_bf16.safetensors",
    "anima":   r"D:/AI_ASSETS/models/diffusion_models/anima/anima-base-v1.0.safetensors",
}
WAN_MODEL = r"D:/AI_ASSETS/models/diffusion_models/wan2.1_i2v_480p_14B_fp16.safetensors"

def dump(name, graph, note=""):
    path = os.path.join(OUT, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, sort_keys=True)
    ncls = sorted({v.get("class_type") for v in graph.values() if isinstance(v, dict)})
    print(f"  [OK]   {name:9s} -> {name}.json  ({len(graph)} nodes: {', '.join(ncls)}){note}")

def note(name, why):
    print(f"  [SKIP] {name:9s} -- {why}")

print("=== object_info (live ComfyUI) ===")
oi = ws._comfy_object_info(BASE)
print(f"  {len(oi)} node classes available\n")

print("=== IMAGE families (native-image path) ===")
for fam, model in IMAGE_FAMILIES.items():
    try:
        if not os.path.exists(model):
            note(fam, f"model not on disk: {model}"); continue
        req = dict(FIX); req.update(command="t2i", model=model, output=os.path.join(OUT, f"{fam}.png"))
        resolved = ws._resolve_native_image_stack(req, oi, fam)
        missing = [s.component for s in resolved.missing_required()]
        if missing:
            note(fam, f"stack incomplete, missing {missing}"); continue
        g = ws._build_native_image_prompt(fam, req, oi, f"baseline_{fam}", resolved)
        dump(fam, g)
    except Exception as exc:
        note(fam, f"build error: {exc}")
        traceback.print_exc()

print("\n=== VIDEO family: wan (native split-stack path, core route) ===")
try:
    if not os.path.exists(WAN_MODEL):
        note("wan", f"model not on disk: {WAN_MODEL}")
    else:
        req = dict(FIX)
        req.update(command="t2v", model=WAN_MODEL, num_frames=33, length=33,
                   output=os.path.join(OUT, "wan.mp4"),
                   resolved_native_video_family="wan", video_family="wan", model_family="wan",
                   video_model_stack={
                       "text_encoder": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                       "vae": "wan_2.1_vae.safetensors",
                       "clip_vision": "clip_vision_h.safetensors",
                   })
        g = ws._build_native_split_video_prompt(req, oi, command="t2v", family="wan", job_id="baseline_wan")
        dump("wan", g, note=f"  route={req.get('native_video_route')}")
except Exception as exc:
    note("wan", f"build error: {exc}")
    traceback.print_exc()

print("\n=== VIDEO family: hunyuan (native t2v, SamplerCustomAdvanced chain) ===")
HUNYUAN_MODEL = r"D:/AI_ASSETS/models/diffusion_models/hunyuan_video_t2v_720p_bf16.safetensors"
try:
    if not os.path.exists(HUNYUAN_MODEL):
        note("hunyuan", f"model not on disk: {HUNYUAN_MODEL}")
    else:
        req = dict(FIX)
        req.update(command="t2v", model=HUNYUAN_MODEL, width=848, height=480, length=61, num_frames=61,
                   fps=24, output=os.path.join(OUT, "hunyuan.mp4"),
                   resolved_native_video_family="hunyuan_video", video_family="hunyuan_video",
                   model_family="hunyuan_video")
        g = ws._build_native_split_video_prompt(req, oi, command="t2v", family="hunyuan_video", job_id="baseline_hunyuan")
        dump("hunyuan", g, note=f"  route={req.get('native_video_route')}")
except Exception as exc:
    note("hunyuan", f"build error: {exc}")
    traceback.print_exc()

print("\n=== baseline files written to refactor_baseline/ ===")
for f in sorted(os.listdir(OUT)):
    if f.endswith(".json"):
        print(f"  {f}  ({os.path.getsize(os.path.join(OUT, f))} bytes)")
