"""Can the native reference path turn a Lane-A skin plate into a flat-lit F/B/L/R sheet that keeps
the person? Twenty plates, measured, before any LoRA or node pack is downloaded (owner decision 6).

The sheet is a BUILD DOCUMENT: it is checked against CHARACTER_IMAGE_INPUT_SPEC (A-pose, plain
ground, flat light, >=1024 px, one figure, consistent scale) by check_reference_sheet.py, and it does
NOT carry the Wrought look -- the pipeline doc records that the look lives in the lighting law and
cannot survive the sheet. Owner decision 7: if the path cannot re-light to flat, a directional-soft
key that is flat enough for 3D is accepted; both are run and reported side by side.

The set actually CHECKED is the PADDED one, not the raw render. `prepare_reference_sheet.py` states
why in its own first line -- "Pad and centre a rendered view so it satisfies the reference-sheet
framing rules" -- and its docstring measures the alternative: chasing margin through the prompt cost
~200s/attempt and still left the vertical margins failing. Margin is a post-process, not a prompt, so
`run_sheet` pads every rendered view through `prepare_reference_sheet.prepare` before handing the set
to `check_set`. Pass `pad=False` (CLI `--no-pad`) to check the raw, unpadded render instead.
`prepare_reference_sheet.prepare` raises when its mask shatters -- a dark-ground side view does that
to `check_reference_sheet.subject_mask` the same way that module's own docstring predicts -- and one
bad view must not take the whole plate batch down with it: `run_sheet` catches that per view, falls
back to the RAW render for it (recorded in `pad_errors`), and lets the checker fail that view on its
own margin/background rules instead.

Identity is measured, not eyeballed: face MAE/NCC between the skin plate and the RAW front view (the
padding is a framing fix, not a face-identity variable), and between front and back for scale via the
checker's cross-view rule.

A sheet counts as fully passing only via `sheet_verdict`: all four views must have rendered, every
per-image rule must hold, and cross_view must be non-empty and entirely ok. A missing view or an
empty cross-view list (which check_reference_sheet.check_set returns for fewer than two usable
reports) must never read as a pass by vacuous truth.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_reference_sheet  # noqa: E402
import wrought_comfy as wc  # noqa: E402
import wrought_measures as measures  # noqa: E402
from check_reference_sheet import check_set  # noqa: E402
from generate_reference_sheet import NEGATIVE as PLATE_NEGATIVE, VIEW_WIDTH, VIEWS  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
H = 1728
VIEW_ORDER = ("front", "back", "left", "right")
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
# phrase is stripped once here and only the flat path puts it back, alongside "key light" (a token
# the base never carried at all). "dramatic shadows" and "vignette" are NOT restated -- the base
# already has them, and repeating a token already present is dead weight in the negative.
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
        return _BASE_NEGATIVE + ", dark background, key light"
    return _BASE_NEGATIVE


def sheet_verdict(files: dict[str, Path], report: dict) -> bool:
    """True only when the WHOLE sheet passes -- a partial or vacuously-empty set never does.

    Guards against two ways `run_sheet` could otherwise over-report: a view that failed to render
    just drops out of `files`, so a naive fold over what remains can call three good views a full
    pass; and `check_reference_sheet.cross_view_findings` returns an EMPTY list for fewer than two
    usable reports, which is vacuously `all(ok for ok in [])` -- true -- unless emptiness itself is
    checked for.
    """
    if not all(view in files for view in VIEW_ORDER):
        return False
    images = report.get("images", [])
    if len(images) != 4:
        return False
    if not all(finding["ok"] for image in images for finding in image["findings"]):
        return False
    cross = report.get("cross_view", [])
    return bool(cross) and all(finding["ok"] for finding in cross)


def run_sheet(endpoint: wc.Endpoint, skin_plate: Path, out_dir: Path, light: str, seed: int,
              pad: bool = True) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    ref = endpoint.upload_reference(skin_plate)   # <=1 MP; the graph carries the official reference LoRA by default (measured 2026-09-06)
    stem = f"{skin_plate.parent.name}_{skin_plate.stem}_{light}"
    files: dict[str, Path] = {}
    t0 = time.time()
    for i, view in enumerate(VIEW_ORDER):
        target = out_dir / f"{stem}_{view}.png"
        graph = wc.reference_edit_graph(sheet_prompt(view, light), sheet_negative(light), seed + i,
                                        f"wsheet_{stem}_{view}", VIEW_WIDTH[view], H, ref)
        if wc.render(endpoint, graph, target):
            files[view] = target

    # Margin is a post-process (prepare_reference_sheet.py's own first line), not a prompt: the
    # set check_set actually grades is the padded one, never the raw render.
    checked: dict[str, Path] = files
    pad_errors: dict[str, str] = {}
    if pad and files:
        checked = {}
        for view, path in files.items():
            try:
                info = prepare_reference_sheet.prepare(path, out_dir / "padded" / path.name)
                checked[view] = Path(info["out"])
            except Exception as exc:
                # A view the pad step cannot mask (a dark-ground side view shatters
                # check_reference_sheet.subject_mask the same way its own docstring predicts) must
                # not take the whole batch down. Fall back to the RAW render for this view -- the
                # checker then fails IT on its own margin/background rules, so sheet_verdict still
                # reports the sheet as not fully passing; only the run must survive, not the score.
                pad_errors[view] = str(exc)[:200]
                checked[view] = path

    report = check_set([checked[v] for v in VIEW_ORDER if v in checked]) if checked else {}
    identity = measures.face_identity(skin_plate, files["front"]) if "front" in files else {}
    per_image = {Path(r["path"]).stem.rsplit("_", 1)[-1]: sum(f["ok"] for f in r["findings"]) / max(len(r["findings"]), 1)
                 for r in report.get("images", [])}
    cross = report.get("cross_view", [])
    result = {"plate": str(skin_plate), "light": light, "seed": seed, "seconds": round(time.time() - t0, 1),
              "files": {k: v.name for k, v in files.items()}, "per_image_pass_fraction": per_image,
              "cross_view_ok": bool(cross) and all(f["ok"] for f in cross),
              "fully_passing": sheet_verdict(files, report),
              "pad_errors": pad_errors, "checked": {k: str(v) for k, v in checked.items()},
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
    parser.add_argument("--no-pad", action="store_true",
                        help="check the raw render; skip the prepare_reference_sheet padding step")
    args = parser.parse_args()
    plates = sorted({Path(p) for raw in args.plates for p in (glob.glob(raw) or [raw])})[: args.n]
    endpoint = wc.Endpoint(args.api)
    pad = not args.no_pad
    rows = []
    for i, plate in enumerate(plates):
        r = run_sheet(endpoint, plate, Path(args.out), args.light, args.seed + 10 * i, pad=pad)
        rows.append(r)
        ident = r["identity"]
        print(f"{plate.name:22s} views ok {sum(v >= 0.99 for v in r['per_image_pass_fraction'].values())}/4 "
              f"cross {'ok' if r['cross_view_ok'] else 'FAIL'} mae {ident.get('mae')} ncc {ident.get('ncc')} "
              f"{r['seconds']}s", flush=True)
    ncc_values = [r["identity"].get("ncc") for r in rows if r["identity"].get("ncc") is not None]
    summary = {"light": args.light, "n": len(rows),
               "sheets_fully_passing": sum(r["fully_passing"] for r in rows),
               "median_ncc": sorted(ncc_values)[len(ncc_values) // 2] if ncc_values else None,
               "unmeasured_identity": len(rows) - len(ncc_values)}
    (Path(args.out) / f"_summary_{args.light}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
