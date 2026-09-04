"""Pad and centre a rendered view so it satisfies the reference-sheet framing rules.

`check_reference_sheet.py` says whether a set meets
`CHARACTER_IMAGE_INPUT_SPEC_2026-08-07.md`. This fixes the two failures that are FRAMING rather than
generation, and it exists because of what those two cost to chase in the sampler.

MARGIN IS A POST-PROCESS, NOT A PROMPT. The spec wants a 5-10% margin so the fuse never cuts a limb.
Asking a diffusion model for whitespace is unreliable and costs ~200 s an attempt: measured on the
orc-002 regeneration, "wide framing with generous empty margin on all sides, clear empty space above
the head and below the feet" plus a wider canvas moved the horizontal margins from 0.0% to 13%, and
left the vertical ones at 3.7% top and 1.3% bottom -- still failing. Padding the canvas afterwards
satisfies the same constraint exactly, in milliseconds, without touching a pixel of the subject.

The same applies to centring, which is the other rule the existing hand-made orc set failed (spread
0.079 against a 0.060 limit). Both are arithmetic on the mask's bounding box.

WHAT THIS DOES NOT DO, deliberately: it never scales, crops or rotates the subject. Padding is the
only safe operation here -- a resize would change the measured proportions the sheet exists to carry,
which is the one thing downstream actually reads.

The mask comes from `check_reference_sheet.subject_mask`, imported rather than reimplemented. That
function carries three hard-won corrections (no luminance thresholding, per-edge background
references, cast-shadow exclusion); a second copy here would have none of them, and would disagree
with the checker about where the subject is -- which is exactly the class of defect the padding is
meant to end.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_reference_sheet import subject_mask  # noqa: E402

TARGET_MARGIN = 0.08  # inside the spec's 5-10% band, with room for the checker's 5% floor


def prepare(path: Path, out: Path, margin: float = TARGET_MARGIN) -> dict:
    image = Image.open(path).convert("RGB")
    rgb = np.asarray(image)
    height, width, _ = rgb.shape

    mask = subject_mask(rgb)
    if not mask.any():
        raise SystemExit(f"{path}: no subject found; padding would be meaningless")

    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    top, bottom = int(rows[0]), int(rows[-1])
    left, right = int(cols[0]), int(cols[-1])
    subject_h, subject_w = bottom - top + 1, right - left + 1

    # The final canvas has to be big enough that the subject occupies at most (1 - 2*margin) of it.
    final_h = int(round(subject_h / (1.0 - 2.0 * margin)))
    final_w = int(round(subject_w / (1.0 - 2.0 * margin)))
    final_h = max(final_h, height)
    final_w = max(final_w, width)

    # Centre the SUBJECT, not the old canvas: an off-centre render is the other failure being fixed.
    offset_x = (final_w - subject_w) // 2 - left
    offset_y = (final_h - subject_h) // 2 - top

    # Fill with the background the image already has, so the pad is invisible and stays maskable.
    background = np.median(rgb[~mask], axis=0).astype(np.uint8) if (~mask).any() else np.uint8([255, 255, 255])
    canvas = np.empty((final_h, final_w, 3), dtype=np.uint8)
    canvas[:, :] = background

    # Where the original lands on the new canvas, clipped to it.
    dst_x0, dst_y0 = max(0, offset_x), max(0, offset_y)
    src_x0, src_y0 = max(0, -offset_x), max(0, -offset_y)
    copy_w = min(width - src_x0, final_w - dst_x0)
    copy_h = min(height - src_y0, final_h - dst_y0)
    canvas[dst_y0:dst_y0 + copy_h, dst_x0:dst_x0 + copy_w] = \
        rgb[src_y0:src_y0 + copy_h, src_x0:src_x0 + copy_w]

    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(canvas).save(out)
    return {
        "src": str(path), "out": str(out),
        "from": f"{width}x{height}", "to": f"{final_w}x{final_h}",
        "subject": f"{subject_w}x{subject_h}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="image files, or a directory of them")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--margin", type=float, default=TARGET_MARGIN)
    args = parser.parse_args()

    files: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(q for q in p.iterdir()
                                if q.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}))
        elif p.is_file():
            files.append(p)
    if not files:
        print("no images found", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    for f in files:
        info = prepare(f, out_dir / f"{f.stem}.png", args.margin)
        print(f"{f.name}: {info['from']} -> {info['to']}  (subject {info['subject']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
