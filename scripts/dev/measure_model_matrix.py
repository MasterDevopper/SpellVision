"""Every krea2 variant at 52 and 30 steps, one prompt, one seed. Time, gate, and a file to look at.

Decides what a 900-frame dataset run uses. Identical prompt/seed/resolution throughout, and all on
ONE box: cross-GPU determinism is not guaranteed, so a quality comparison split across two cards
would compare the cards as well as the models.

The turbo variant is distilled and is NOT comparable at 52/30 steps with cfg 3.5 -- that config is
wrong for it rather than unflattering. It gets its intended row as well, and both are reported, so
"turbo looked bad" cannot be recorded from a config it was never meant to run.
"""
import json, sys, time, urllib.request, importlib.util
from pathlib import Path
REPO = Path("C:/Users/xXste/Code_Projects/SpellVision")
sys.path.insert(0, str(REPO / "python")); sys.path.insert(0, str(REPO / "scripts/dev"))
from comfy_prompt_client import _http_get_json
from check_wrought import measure, verdict
spec = importlib.util.spec_from_file_location("gd", REPO / "scripts/dev/generate_wrought_dataset.py")
gd = importlib.util.module_from_spec(spec); spec.loader.exec_module(gd)

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8188"
gd.API = API
OUT = Path("C:/tmp/model_matrix"); OUT.mkdir(exist_ok=True)
SEED, W, H = 2200, 832, 1216

# One subject, fixed: an orc woman in practical armour, full body. Enough material variety
# (iron, leather, fur, cloth, skin) that a model's material read is visible.
info = gd.culture("orc")
SUBJECT = ("a single orc woman, broad and muscular, in their prime, wearing practical armour over "
           "layered cloth, full body standing head to toe, key light from the upper left, "
           f"materials of this culture: {info['materials']}, {info['surface'].lower()} surfaces, "
           f"{info['ornament'].lower()} ornament, palette of {info['palette']}")
POSITIVE = f"{SUBJECT}, {gd.WROUGHT_STYLE}"

MODELS = [
    "loxsUtopicWorldKrea2_v10BF16.safetensors",
    "loxsUtopicWorldKrea2_v10Quants.safetensors",
    "loxsUtopicWorldKrea2_v20BF16.safetensors",
    "loxsUtopicWorldKrea2_v20Quants.safetensors",
    "loxsUtopicWorldKrea2_v20Quants_nvfp4.safetensors",
    "krea2_raw_fp8_scaled.safetensors",
]
RUNS = [(m, s, 3.5) for m in MODELS for s in (52, 30)]
RUNS += [("krea2_turbo_fp8_scaled.safetensors", s, 3.5) for s in (52, 30)]
RUNS += [("krea2_turbo_fp8_scaled.safetensors", 8, 1.0)]   # its intended config

rows = []
for unet, steps, cfg in RUNS:
    tag = f"{unet.replace('.safetensors','').replace('loxsUtopicWorld','')}_{steps}s"
    if cfg != 3.5:
        tag += f"_cfg{cfg}"
    g = gd.build_graph(POSITIVE, SEED, f"mx_{tag}", W, H)
    g["1"]["inputs"]["unet_name"] = unet
    g["8"]["inputs"]["steps"] = steps
    g["8"]["inputs"]["cfg"] = cfg
    t0 = time.perf_counter()
    body = json.dumps({"prompt": g, "client_id": "mx"}).encode()
    rq = urllib.request.Request(f"{API}/prompt", data=body, headers={"Content-Type": "application/json"})
    try:
        pid = json.loads(urllib.request.urlopen(rq, timeout=120).read())["prompt_id"]
    except Exception as exc:
        print(f"  {tag:44s} REJECTED {exc}"); sys.stdout.flush(); continue
    files = gd.wait_for(pid, 2400)
    secs = round(time.perf_counter() - t0, 1)
    if not files:
        print(f"  {tag:44s} FAILED after {secs}s"); sys.stdout.flush(); continue
    dst = OUT / f"{tag}.png"; dst.write_bytes(gd.fetch(files[0]))
    row = measure(dst); checks = verdict(row)
    rec = {"model": unet, "steps": steps, "cfg": cfg, "seconds": secs,
           "gate": "WROUGHT" if all(o for _, o, _ in checks) else "OFF-STYLE",
           "failed": [k for k, o, _ in checks if not o],
           "detail_mid": row["detail_mid"], "saturation_p50": row["saturation_p50"],
           "material_floor": row["material_floor"], "file": str(dst)}
    rows.append(rec)
    print(f"  {tag:44s} {secs:6.1f}s  {rec['gate']:9s} detail {row['detail_mid']:.4f} "
          f"floor {row['material_floor']:.3f}")
    sys.stdout.flush()

(OUT / "matrix.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
print(f"\nwrote {OUT/'matrix.json'}")
