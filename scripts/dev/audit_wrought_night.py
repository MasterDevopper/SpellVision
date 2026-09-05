"""The morning read of a Wrought night run: sheets, drift ranking, captions, and a summary.

The night run leaves one JSON record per frame. This turns nine hundred of them into what the
owner actually needs at breakfast: a contact sheet per race to judge, the frames most likely to
have drifted photoreal pulled to the front, a caption file beside every frame so the keepers are
already a training set, and one table saying how the run went.

WHY DRIFT IS RANKED AND NOT GATED. `face_fine_over_meso` -- pore-scale texture over form-scale
texture on the face -- separated three photograph probes (0.545..0.660) from every locked plate
(<= 0.501) and put the early orc batch that reads as documentary skin at 0.82..0.94. But that is
four locked plates with a face large enough to measure. A threshold set from four is the trap this
gate keeps recording, so the number RANKS and the owner's eye decides; once a hundred frames carry
a verdict, `--calibrate` on the keepers gives the threshold a real sample.

CAPTIONS ARE CONTENT, NOT STYLE. Doc 43: "wrought style, [subject], [materials], [pose], [light]
-- content, not style prose." The style is what the LoRA learns from the pixels; captioning it
would teach the trigger to mean the words rather than the look. So the caption is rebuilt from the
frame's variation record, never copied from the prompt, and the 002-lead sentence never appears.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrought_variants as variants  # noqa: E402

TRIGGER = "wrought style"
SHEET_COLS, CELL_W, CAP_H, PAD = 5, 380, 26, 6


def _font(size: int):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size)
    except OSError:
        return ImageFont.load_default()


def records_for(root: Path) -> dict[str, list[dict]]:
    """race -> records, from every `<race>_woman/` (or `<race>_man/`) directory under root."""
    out: dict[str, list[dict]] = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        race = d.name.rsplit("_", 1)[0] if d.name.endswith(("_woman", "_man")) else d.name
        for j in sorted(d.glob("[0-9][0-9][0-9].json")):
            rec = json.loads(j.read_text(encoding="utf-8"))
            rec["_png"] = j.with_suffix(".png")
            rec["_root"] = root.name
            if rec["_png"].exists():
                out.setdefault(race, []).append(rec)
    return out


def caption_for(race: str, rec: dict) -> str:
    """Doc 43's caption shape, rebuilt from the variation -- content only, trigger first."""
    v = rec["variation"]
    parts = [TRIGGER, f"a single {race.replace('_', ' ')} {v['sex']}", v.get("lineage", ""),
             v.get("skin", ""), v.get("face", ""), v.get("eyes", ""),
             v["build"], v["age"], v["hair"], v["expression"] + " expression",
             f"wearing {v['clothing']}, {v['condition']}", v.get("marks", ""), v["framing"],
             v["light"]]
    return ", ".join(p for p in parts if p)


def sheet(recs: list[dict], out: Path, title: str, sort_key=None) -> None:
    recs = sorted(recs, key=sort_key) if sort_key else recs
    if not recs:
        return
    font, small = _font(18), _font(15)
    sample = Image.open(recs[0]["_png"])
    cell_h = int(CELL_W * sample.height / sample.width)
    rows = (len(recs) + SHEET_COLS - 1) // SHEET_COLS
    img = Image.new("RGB", (SHEET_COLS * (CELL_W + PAD) + PAD, 34 + rows * (cell_h + CAP_H) + PAD),
                    (18, 18, 20))
    draw = ImageDraw.Draw(img)
    draw.text((PAD + 2, 8), title, font=font, fill=(238, 238, 242))
    for i, rec in enumerate(recs):
        x = PAD + (i % SHEET_COLS) * (CELL_W + PAD)
        y = 34 + (i // SHEET_COLS) * (cell_h + CAP_H)
        frame = Image.open(rec["_png"]).convert("RGB")
        # a portrait canvas and a figure canvas have different aspect; fit, don't stretch
        scale = min(CELL_W / frame.width, cell_h / frame.height)
        frame = frame.resize((max(1, int(frame.width * scale)), max(1, int(frame.height * scale))))
        img.paste(frame, (x + (CELL_W - frame.width) // 2, y + (cell_h - frame.height) // 2))
        m = rec.get("metrics", {})
        face = m.get("face_fine_over_meso")
        gate = rec.get("gate", "?")
        colour = (150, 230, 160) if gate == "WROUGHT" else (225, 165, 120)
        label = f"{rec['index']:03d}  {gate}  face {face if face is not None else '-'}"
        draw.text((x + 3, y + cell_h + 4), label, font=small, fill=colour)
    img.save(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", help="e.g. runtime/wrought_night runtime/wrought_night_b")
    parser.add_argument("--out", default=None, help="where sheets and the summary go; "
                                                     "default <first root>/_audit")
    parser.add_argument("--captions", action="store_true",
                        help="write <index>.txt beside every frame (content caption, trigger first)")
    parser.add_argument("--drift-top", type=int, default=20,
                        help="how many highest-face-texture frames per race go on the drift sheet")
    args = parser.parse_args()

    roots = [Path(r) for r in args.roots]
    out = Path(args.out) if args.out else roots[0] / "_audit"
    out.mkdir(parents=True, exist_ok=True)

    merged: dict[str, list[dict]] = {}
    for root in roots:
        for race, recs in records_for(root).items():
            merged.setdefault(race, []).extend(recs)

    lines = ["# Wrought night run -- audit", "",
             "| race | frames | gate pass | face measured | face p50 | face p90 | > 0.60 | "
             "0.50-0.60 | figure/portrait | top tiers |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    total = passed = 0
    for race, recs in sorted(merged.items()):
        recs.sort(key=lambda r: (r["_root"], r["index"]))
        faces = [r["metrics"].get("face_fine_over_meso") for r in recs]
        faces = sorted(f for f in faces if f is not None)
        p50 = faces[len(faces) // 2] if faces else None
        p90 = faces[int(len(faces) * 0.9)] if faces else None
        hot = sum(1 for f in faces if f > 0.60)
        warm = sum(1 for f in faces if 0.50 < f <= 0.60)
        ok = sum(1 for r in recs if r.get("gate") == "WROUGHT")
        canvases = Counter("portrait" if r.get("canvas", [0, 0])[1] == 1024 else "figure" for r in recs)
        tiers = Counter(r["variation"].get("tier", "?") for r in recs).most_common(3)
        total += len(recs); passed += ok
        lines.append(f"| {race} | {len(recs)} | {ok} | {len(faces)} | "
                     f"{p50 if p50 is not None else '-'} | {p90 if p90 is not None else '-'} | "
                     f"{hot} | {warm} | {canvases['figure']}/{canvases['portrait']} | "
                     f"{', '.join(f'{t} {n}' for t, n in tiers)} |")

        # the full sheet, in pages of 20, for judging
        for page, start in enumerate(range(0, len(recs), SHEET_COLS * 4)):
            chunk = recs[start:start + SHEET_COLS * 4]
            sheet(chunk, out / f"{race}_p{page + 1:02d}.png",
                  f"{race}  frames {chunk[0]['index']:03d}-{chunk[-1]['index']:03d}  "
                  f"({chunk[0]['_root']})")
        # the drift sheet: highest face texture first
        with_face = [r for r in recs if r["metrics"].get("face_fine_over_meso") is not None]
        sheet(with_face[:], out / f"{race}_drift_top{args.drift_top}.png",
              f"{race}  highest face texture first (photograph probes measured 0.545-0.660; "
              f"locked plates <= 0.501)",
              sort_key=lambda r: -r["metrics"]["face_fine_over_meso"])
        if args.captions:
            for r in recs:
                r["_png"].with_suffix(".txt").write_text(caption_for(race, r) + "\n", encoding="utf-8")

    lines += ["", f"**{total} frames, {passed} through the gate ({passed * 100 // max(total, 1)}%).**",
              "",
              "Sheets: `<race>_pNN.png` (all frames, 20 a page, index order) and "
              "`<race>_drift_topN.png` (highest face texture first -- look here for photoreal).",
              "Gate verdicts are the calibrated Wrought criteria; face texture is advisory and "
              "unthresholded until a labelled set exists.",
              "Captions (`--captions`): `<index>.txt` beside each frame, trigger first, content only."]
    (out / "_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nsheets -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
