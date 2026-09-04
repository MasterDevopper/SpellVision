"""Contact sheets for judging a generated race batch, and a tally that reads back the verdict.

A hundred frames per race is too many to judge in a folder and far too many to judge one at a time.
These are numbered grids: the owner reads off the numbers that fail, and `--reject` writes them into
the batch summary so the labels live beside the images rather than in a chat log.

WHY THE LABELS MATTER MORE THAN THE IMAGES. The gate's thresholds currently rest on seventeen
character plates and have been wrong four separate times, each because that sample encoded a
property of its own subject as a law of the style -- a saturation floor that rejected desaturated
steel, a black-pixel ceiling that rejected a dark-furred boar, a skin gloss rule applied to a
polished helmet, a shadow floor applied to an unlit hall. An owner-labelled set spanning nine races
is the first sample wide enough to re-derive those thresholds against something other than one kind
of picture.

The gate's own verdict is printed under each cell, so the sheet doubles as a record of where the
machine and the owner disagree. Those disagreements are the useful rows: a frame the gate passed and
the owner rejects is a criterion that is too loose, and the reverse is one fitted too tight.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CELL = 320          # thumbnail width
COLS = 5
LABEL_H = 34


def _font(size: int = 15):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def sheets(batch: Path, out: Path, per_sheet: int = 25) -> list[Path]:
    records = {}
    summary = batch / "_summary.json"
    if summary.is_file():
        for record in json.loads(summary.read_text(encoding="utf-8")).get("records", []):
            records[record["index"]] = record

    images = sorted(p for p in batch.glob("[0-9][0-9][0-9].png"))
    if not images:
        raise SystemExit(f"no frames in {batch}")

    out.mkdir(parents=True, exist_ok=True)
    font = _font()
    written = []
    for start in range(0, len(images), per_sheet):
        chunk = images[start:start + per_sheet]
        rows = (len(chunk) + COLS - 1) // COLS
        # Cell height follows the first image's aspect so a portrait batch does not letterbox.
        with Image.open(chunk[0]) as probe:
            cell_h = int(CELL * probe.height / probe.width)
        sheet = Image.new("RGB", (COLS * CELL, rows * (cell_h + LABEL_H)), (24, 24, 28))
        draw = ImageDraw.Draw(sheet)

        for position, path in enumerate(chunk):
            column, row = position % COLS, position // COLS
            x, y = column * CELL, row * (cell_h + LABEL_H)
            with Image.open(path) as image:
                sheet.paste(image.convert("RGB").resize((CELL, cell_h), Image.LANCZOS), (x, y))
            index = int(path.stem)
            record = records.get(index, {})
            gate = record.get("gate", "?")
            variation = record.get("variation", {})
            note = f"{variation.get('sex','')[:1]}/{variation.get('framing','')[:10]}"
            # The number is what the owner reads back, so it is the loudest thing on the cell.
            draw.text((x + 6, y + cell_h + 4), f"{index:03d}", font=_font(19),
                      fill=(255, 255, 255))
            draw.text((x + 44, y + cell_h + 8), gate, font=font,
                      fill=(120, 220, 160) if gate == "WROUGHT" else (230, 150, 90))
            draw.text((x + 44 + 92, y + cell_h + 8), note, font=font, fill=(150, 150, 160))

        target = out / f"{batch.name}_sheet{start // per_sheet + 1:02d}.png"
        sheet.save(target)
        written.append(target)
    return written


def record_rejects(batch: Path, rejected: list[int]) -> dict:
    """Write the owner's verdict beside the images, and report where the gate disagreed."""
    summary_path = batch / "_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rejects = set(rejected)

    false_pass, false_fail = [], []
    for record in summary.get("records", []):
        owner = "REJECT" if record["index"] in rejects else "KEEP"
        record["owner"] = owner
        if record["gate"] == "WROUGHT" and owner == "REJECT":
            false_pass.append(record["index"])     # criterion too loose
        if record["gate"] == "OFF-STYLE" and owner == "KEEP":
            false_fail.append(record["index"])     # criterion fitted too tight
    summary["owner_rejected"] = sorted(rejects)
    summary["gate_false_pass"] = false_pass
    summary["gate_false_fail"] = false_fail
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", help="a race directory under runtime/wrought_dataset")
    parser.add_argument("--out", default=None)
    parser.add_argument("--per-sheet", type=int, default=25)
    parser.add_argument("--reject", default="",
                        help="comma/space separated frame numbers the owner rejects, e.g. "
                             "'3,17,42' -- recorded into _summary.json with the gate disagreements")
    args = parser.parse_args()

    batch = Path(args.batch)
    if args.reject.strip():
        numbers = [int(n) for n in args.reject.replace(",", " ").split()]
        summary = record_rejects(batch, numbers)
        kept = summary["count"] - len(summary["owner_rejected"])
        print(f"{batch.name}: {kept}/{summary['count']} kept by the owner")
        print(f"  gate passed but owner rejected (too loose): {summary['gate_false_pass']}")
        print(f"  gate rejected but owner kept (too tight):    {summary['gate_false_fail']}")
        return 0

    out = Path(args.out) if args.out else batch / "_review"
    for path in sheets(batch, out, args.per_sheet):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
