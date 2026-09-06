"""Sweep denoise x mode over EXISTING Lane-A skin plates through `wrought_comfy.img2img_graph`,
and MEASURE every output with the silhouette measure -- the pick is made from the record and the
sheet this writes, not from a look at one render.

Task 15D: Task 15B's re-measure found 0 of 54 skin/suit pairs inside the 8 px silhouette bar
(the native reference-edit suit plate rebuilds the body from the model's prior). img2img starts
the sampler from the skin plate's own VAE-encoded latent instead, so the body silhouette survives
by construction; the open question is how much denoise still gives the "new surface" the suit
plate needs (a compression suit, not the drawn wardrobe) without falling back to a near-copy of
the skin plate. This script renders the grid and measures it; it never decides the answer.

This script never submits anywhere but `--api` (default the local endpoint) and never writes
anywhere but `--out`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_wrought_dataset as g  # noqa: E402
import wrought_comfy as wc  # noqa: E402
import wrought_measures as measures  # noqa: E402
import wrought_variants as variants  # noqa: E402
from wrought_evidence_sheet import sheet  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def run(endpoint: "wc.Endpoint", skins: list[Path], out: Path, denoise: list[float],
        modes: list[str], steps: int = 52, cfg: float = 3.5) -> list[dict]:
    """Render every (skin, mode, denoise) combination and measure it. Returns the same list of
    records written to `<out>/_probe.json`; a render that fails is recorded with `ok=False`, never
    skipped, so a bad cell is as visible in the record as it is in the sheet.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    sheet_paths: list[Path | None] = []
    sheet_labels: list[str] = []
    for skin in skins:
        skin = Path(skin)
        stem = skin.stem.removesuffix("_skin")
        pair = json.loads((skin.parent / f"{stem}.json").read_text(encoding="utf-8"))
        suit_prompt = pair["prompts"]["suit"]
        seed = pair["seed"] + 500_000
        negative = ", ".join([g.WROUGHT_NEG, variants.negative_for("woman"), variants.SUIT_NEGATIVE])
        init_name = endpoint.upload(skin)
        ref_name = endpoint.upload_reference(skin) if "reference" in modes else None

        sheet_paths.append(skin)
        sheet_labels.append("skin")
        for mode in modes:
            for d in denoise:
                tag = f"{mode}_d{int(d * 100):02d}"
                prefix = f"wsp_{stem}_{tag}"
                target = out / f"{skin.parent.name}__{stem}_{tag}.png"
                graph = wc.img2img_graph(suit_prompt, negative, seed, prefix, init_name, d,
                                         steps=steps, cfg=cfg,
                                         reference_name=ref_name if mode == "reference" else None)
                ok = wc.render(endpoint, graph, target)
                silhouette = measures.silhouette_delta(skin, target) if ok else None
                identity = measures.face_identity(skin, target) if ok else None
                rows.append({"skin": str(skin), "mode": mode, "denoise": d, "file": target.name,
                            "silhouette": silhouette, "identity": identity, "ok": ok})
                sil, ident = silhouette or {}, identity or {}
                print(f"{target.name}  waist d {sil.get('waist_delta_px', '-')}  "
                      f"hip d {sil.get('hip_delta_px', '-')}  height d {sil.get('height_delta_px', '-')}  "
                      f"ncc {ident.get('ncc', '-')}", flush=True)
                sheet_paths.append(target if ok else None)
                sheet_labels.append(f"{mode} d{d} hipΔ{sil.get('hip_delta_px', '-')}")

    (out / "_probe.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    sheet(sheet_paths, sheet_labels, out / "_sheet.jpg", cols=1 + len(modes) * len(denoise))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skins", nargs="+", required=True, help="existing Lane-A skin plate PNGs")
    parser.add_argument("--out", required=True)
    parser.add_argument("--denoise", type=float, nargs="+", default=[0.6, 0.7, 0.8])
    parser.add_argument("--modes", nargs="+", choices=["plain", "reference"], default=["plain", "reference"])
    parser.add_argument("--api", default=wc.Endpoint().api)
    parser.add_argument("--steps", type=int, default=52)
    parser.add_argument("--cfg", type=float, default=3.5)
    args = parser.parse_args()

    endpoint = wc.Endpoint(args.api)
    skins = [Path(p) for p in args.skins]
    rows = run(endpoint, skins, Path(args.out), args.denoise, args.modes, args.steps, args.cfg)
    passed = sum(r["ok"] for r in rows)
    print(f"{passed}/{len(rows)} renders ok -- wrote {Path(args.out) / '_probe.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
