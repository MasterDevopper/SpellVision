"""One contact sheet from a list of plates, for the README's evidence folder.

`sheet(paths, labels, out, cols=6, cell=(300, 420))` lays the plates out row-major in a grid of
`cols` columns, each thumbnail fitted inside `cell` (aspect kept), with its label drawn beneath.
A missing or unreadable plate becomes an empty dark cell that still carries its label, so a sheet
never silently shifts the grid when one render failed -- the gap IS the evidence. The JPEG quality
steps down until the file is under `max_bytes` (2 MB, the evidence-folder rule).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

LABEL_H = 18
GROUND = (20, 20, 22)
INK = (230, 230, 230)
MISSING = (46, 46, 50)


def sheet(paths: list[Path | None], labels: list[str], out: Path, cols: int = 6,
          cell: tuple[int, int] = (300, 420), max_bytes: int = 2_000_000) -> Path:
    if len(paths) != len(labels):
        raise ValueError(f"{len(paths)} paths but {len(labels)} labels")
    if cols < 1 or not paths:
        raise ValueError("a sheet needs at least one column and one plate")
    rows = (len(paths) + cols - 1) // cols
    cw, ch = cell
    im = Image.new("RGB", (cols * cw, rows * (ch + LABEL_H)), GROUND)
    draw = ImageDraw.Draw(im)
    for i, (p, label) in enumerate(zip(paths, labels)):
        x, y = (i % cols) * cw, (i // cols) * (ch + LABEL_H)
        try:
            thumb = Image.open(p).convert("RGB") if p is not None else None
        except OSError:
            thumb = None
        if thumb is None:
            draw.rectangle([x + 2, y + 2, x + cw - 3, y + ch - 3], fill=MISSING)
        else:
            thumb.thumbnail((cw, ch))
            im.paste(thumb, (x + (cw - thumb.width) // 2, y + (ch - thumb.height) // 2))
        draw.text((x + 4, y + ch + 2), label[:60], fill=INK)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Quality steps down until the file fits the evidence-folder cap; a 6x6 sheet of 300x420 cells
    # lands near 400 KB at 85, so the loop rarely runs more than once.
    for quality in (85, 75, 65, 55, 45):
        im.save(out, "JPEG", quality=quality)
        if out.stat().st_size <= max_bytes:
            break
    return out


if __name__ == "__main__":  # pragma: no cover -- `sheet` is called from the read scripts
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("plates", nargs="+", help="png paths; label = parent dir + stem")
    ap.add_argument("--cols", type=int, default=6)
    a = ap.parse_args()
    ps = [Path(p) for p in a.plates]
    print(sheet(ps, [f"{p.parent.name}/{p.stem}" for p in ps], Path(a.out), cols=a.cols))
