"""Turn the owner's picks into a training set: copy each kept frame and its caption into one flat
directory the trainer can read.

The owner judges on the audit sheets and writes picks as `race/NNN` lines (one per line, `#`
comments allowed) -- for example `orc/017` or `dark_elf/042`. Both night roots are searched, so a
pick does not need to say which box rendered it. Frames land as `<race>_<NNN>.png` with the
matching `.txt` caption beside them, which is the stem-pairing musubi-tuner's dataset config uses.

WHY A COPY AND NOT A LIST. The trainer wants one image directory; the night run left nine race
directories across two roots. Copying is a few hundred megabytes and makes the training set a
thing that can be looked at, zipped and reproduced -- the JSON record beside each source frame
stays where it was, so provenance is one `race/NNN` away.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_wrought_night import caption_for  # noqa: E402
import json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("picks", help="text file of race/NNN lines")
    parser.add_argument("--roots", nargs="+",
                        default=[str(REPO / "runtime/wrought_night"), str(REPO / "runtime/wrought_night_b"),
                                 str(REPO / "runtime/wrought_v2"), str(REPO / "runtime/wrought_v2_b")])
    parser.add_argument("--out", default=None,
                        help="where the training set lands; default runtime/style/datasets/wrought_v2/"
                             "train_<today, YYYY-MM-DD> -- a dated dir so a previous training "
                             "snapshot is never silently overwritten (DIRECTION_V2 section 5)")
    parser.add_argument("--sex", default="woman")
    args = parser.parse_args()

    out = (Path(args.out) if args.out else
           REPO / "runtime/style/datasets/wrought_v2" / f"train_{date.today().isoformat()}")
    out.mkdir(parents=True, exist_ok=True)
    roots = [Path(r) for r in args.roots]

    picks = [ln.split("#", 1)[0].strip() for ln in Path(args.picks).read_text(encoding="utf-8").splitlines()]
    picks = [p for p in picks if p]
    copied, missing = 0, []
    for pick in picks:
        # Two forms. `race/NNN` searches the roots in order -- ambiguous for a race split across
        # both roots with overlapping indices (human), so the picker exports the unambiguous
        # `<root>/<dir>/<stem>` instead, a path relative to runtime/. `<dir>` is `<race>_woman` /
        # `<race>_man` (v1, and a v2 Lane A identity) or a v2 Lane B `<race>_<kind>` directory
        # (`dwarf_outfit`, `dwarf_weapon`, `dwarf_fit`...) -- neither of the last three ends in
        # `_woman`/`_man`, so the form is told apart by segment count, not by dir suffix. `<stem>`
        # is a bare index (v1: `007`) or `NNN_<which>` (v2: `007_skin` / `007_suit` / `003_outfit` /
        # `003_fit` / `003_weapon`...) -- one JSON record backs two PNGs for Lane A (skin + suit),
        # so the stem, not the index alone, addresses which frame this pick names.
        norm = pick.replace("\\", "/")
        if norm.count("/") >= 2:
            parts = norm.split("/")
            root_name, race_dir, stem = parts[-3], parts[-2], Path(parts[-1]).stem
            race = race_dir.rsplit("_", 1)[0]
            index, _, which = stem.partition("_")
            src = next((r / race_dir / f"{stem}.png" for r in roots
                        if r.name == root_name and (r / race_dir / f"{stem}.png").exists()), None)
            if src is None:
                src = next((r / race_dir / f"{int(index):03d}.png" for r in roots
                            if r.name == root_name and (r / race_dir / f"{int(index):03d}.png").exists()), None)
            record_path = src.parent / f"{int(index):03d}.json" if src else None
            dst_stem = f"{src.parent.parent.name}_{race_dir}_{stem}" if src else None
        else:
            race, _, idx = pick.partition("/")
            which = ""
            stem = f"{int(idx):03d}"
            src = next((r / f"{race}_{args.sex}" / f"{stem}.png" for r in roots
                        if (r / f"{race}_{args.sex}" / f"{stem}.png").exists()), None)
            record_path = src.with_suffix(".json") if src else None
            # Root in the stem, so the two human halves cannot overwrite each other in one flat dir.
            dst_stem = f"{src.parent.parent.name}_{race}_{stem}" if src else None
        if src is None:
            missing.append(pick)
            continue
        record = json.loads(record_path.read_text(encoding="utf-8"))
        dst = out / f"{dst_stem}.png"
        shutil.copy2(src, dst)
        dst.with_suffix(".txt").write_text(caption_for(race, record, which) + "\n", encoding="utf-8")
        copied += 1

    print(f"{copied} frames -> {out}")
    if missing:
        print(f"{len(missing)} picks not found: {', '.join(missing[:10])}{' …' if len(missing) > 10 else ''}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
