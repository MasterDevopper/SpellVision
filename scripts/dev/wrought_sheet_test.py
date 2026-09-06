"""Can the native reference path turn a Lane-A skin plate into a flat-lit F/B/L/R sheet that keeps
the person? Twenty plates, measured, before any LoRA or node pack is downloaded (owner decision 6).

The sheet is a BUILD DOCUMENT: it is checked against CHARACTER_IMAGE_INPUT_SPEC (A-pose, plain
ground, flat light, >=1024 px, one figure, consistent scale) by check_reference_sheet.py, and it does
NOT carry the Wrought look -- the pipeline doc records that the look lives in the lighting law and
cannot survive the sheet. Owner decision 7: if the path cannot re-light to flat, a directional-soft
key that is flat enough for 3D is accepted; both are run and reported side by side.

Identity is measured, not eyeballed: face MAE/NCC between the skin plate and the front view, and
between front and back for scale via the checker's cross-view rule.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrought_comfy as wc  # noqa: E402
import wrought_measures as measures  # noqa: E402
from check_reference_sheet import check_set  # noqa: E402
from generate_reference_sheet import NEGATIVE as PLATE_NEGATIVE, VIEW_WIDTH, VIEWS  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
H = 1728
SHEET_LIGHT = {
    # No "no key light" clause here: a negation still puts the token "key light" in the POSITIVE
    # prompt, which is exactly the class of bug generate_reference_sheet.py's own docstring names
    # (item 1 -- a negated "flat lighting" fought the sampler instead of steering it). The concept
    # is refused where negation belongs: in `sheet_negative`, under `flat`.
    "flat": "even soft frontal studio lighting, no harsh shadows",
    "soft": "soft directional light from the upper left with gentle fill, low contrast, no hard shadow",
}
# `PLATE_NEGATIVE` already carries "dark background" unconditionally (it sits in the shared
# framing/wardrobe clause, alongside "dramatic shadows, rim light, vignette"). Measured
# 2026-09-06 rather than assumed -- a bare concatenation would leave "dark background" in the
# negative under BOTH lights, which defeats the point of a soft-light fallback. So the shared
# phrase is stripped once here and only the flat path puts it back (with its two companions
# restated for emphasis, same as the original clause).
_BASE_NEGATIVE = PLATE_NEGATIVE.replace("dark background, ", "")


def sheet_prompt(view: str, light: str) -> str:
    return ", ".join([
        "one single figure alone, the same woman as the reference, identical face, hair, skin and build",
        "wearing the same plain matte mid-grey sports bra and fitted shorts, barefoot",
        "neutral A-pose with the arms held away from the sides, feet shoulder width apart",
        VIEWS[view], SHEET_LIGHT[light],
        "plain seamless light grey studio backdrop, orthographic character reference sheet",
        "whole figure with generous empty margin on all sides, hands well inside the frame",
    ])


def sheet_negative(light: str) -> str:
    if light == "flat":
        return _BASE_NEGATIVE + ", dark background, dramatic shadows, key light, vignette"
    return _BASE_NEGATIVE


def run_sheet(endpoint: wc.Endpoint, skin_plate: Path, out_dir: Path, light: str, seed: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    ref = endpoint.upload_reference(skin_plate)   # <=1 MP; the graph carries the official reference LoRA by default (measured 2026-09-06)
    stem = f"{skin_plate.parent.name}_{skin_plate.stem}_{light}"
    files: dict[str, Path] = {}
    t0 = time.time()
    for i, view in enumerate(("front", "back", "left", "right")):
        target = out_dir / f"{stem}_{view}.png"
        graph = wc.reference_edit_graph(sheet_prompt(view, light), sheet_negative(light), seed + i,
                                        f"wsheet_{stem}_{view}", VIEW_WIDTH[view], H, ref)
        if wc.render(endpoint, graph, target):
            files[view] = target
    report = check_set([files[v] for v in ("front", "back", "left", "right") if v in files]) if files else {}
    identity = measures.face_identity(skin_plate, files["front"]) if "front" in files else {}
    per_image = {Path(r["path"]).stem.rsplit("_", 1)[-1]: sum(f["ok"] for f in r["findings"]) / max(len(r["findings"]), 1)
                 for r in report.get("images", [])}
    result = {"plate": str(skin_plate), "light": light, "seed": seed, "seconds": round(time.time() - t0, 1),
              "files": {k: v.name for k, v in files.items()}, "per_image_pass_fraction": per_image,
              "cross_view_ok": all(f["ok"] for f in report.get("cross_view", [])) if report else False,
              "identity": identity, "report": report}
    (out_dir / f"{stem}_sheet.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plates", nargs="+", required=True, help="skin plates or globs")
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--light", choices=list(SHEET_LIGHT), default="flat")
    parser.add_argument("--out", default=str(REPO / "runtime/wrought_sheet_test"))
    parser.add_argument("--api", default="http://127.0.0.1:8188")
    parser.add_argument("--seed", type=int, default=31000)
    args = parser.parse_args()
    plates = sorted({Path(p) for raw in args.plates for p in (glob.glob(raw) or [raw])})[: args.n]
    endpoint = wc.Endpoint(args.api)
    rows = []
    for i, plate in enumerate(plates):
        r = run_sheet(endpoint, plate, Path(args.out), args.light, args.seed + 10 * i)
        rows.append(r)
        ident = r["identity"]
        print(f"{plate.name:22s} views ok {sum(v >= 0.99 for v in r['per_image_pass_fraction'].values())}/4 "
              f"cross {'ok' if r['cross_view_ok'] else 'FAIL'} mae {ident.get('mae')} ncc {ident.get('ncc')} "
              f"{r['seconds']}s", flush=True)
    summary = {"light": args.light, "n": len(rows),
               "sheets_fully_passing": sum(all(v >= 0.99 for v in r["per_image_pass_fraction"].values())
                                           and r["cross_view_ok"] for r in rows),
               "median_ncc": sorted(r["identity"].get("ncc") or 0 for r in rows)[len(rows) // 2] if rows else None}
    (Path(args.out) / f"_summary_{args.light}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
