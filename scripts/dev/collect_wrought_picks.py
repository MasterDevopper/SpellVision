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
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_wrought_night import caption_for  # noqa: E402
import json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("picks", help="text file of race/NNN lines")
    parser.add_argument("--roots", nargs="+",
                        default=[str(REPO / "runtime/wrought_night"), str(REPO / "runtime/wrought_night_b")])
    parser.add_argument("--out", default=str(REPO / "runtime/style/datasets/wrought_night_v1/train"))
    parser.add_argument("--sex", default="woman")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    roots = [Path(r) for r in args.roots]

    picks = [ln.split("#", 1)[0].strip() for ln in Path(args.picks).read_text(encoding="utf-8").splitlines()]
    picks = [p for p in picks if p]
    copied, missing = 0, []
    for pick in picks:
        # Two forms. `race/NNN` searches the roots in order -- ambiguous for a race split across
        # both roots with overlapping indices (human), so the picker exports the unambiguous
        # `<root>/<race>_woman/NNN` instead, which is a path relative to runtime/.
        if "_woman/" in pick or "_man/" in pick:
            parts = pick.replace("\\", "/").split("/")
            root_name, race_dir, idx = parts[-3], parts[-2], parts[-1]
            race = race_dir.rsplit("_", 1)[0]
            idx = f"{int(Path(idx).stem):03d}"
            src = next((r / race_dir / f"{idx}.png" for r in roots
                        if r.name == root_name and (r / race_dir / f"{idx}.png").exists()), None)
        else:
            race, _, idx = pick.partition("/")
            idx = f"{int(idx):03d}"
            src = next((r / f"{race}_{args.sex}" / f"{idx}.png" for r in roots
                        if (r / f"{race}_{args.sex}" / f"{idx}.png").exists()), None)
        if src is None:
            missing.append(pick)
            continue
        record = json.loads(src.with_suffix(".json").read_text(encoding="utf-8"))
        # Root in the stem, so the two human halves cannot overwrite each other in one flat dir.
        dst = out / f"{src.parent.parent.name}_{race}_{idx}.png"
        shutil.copy2(src, dst)
        dst.with_suffix(".txt").write_text(caption_for(race, record) + "\n", encoding="utf-8")
        copied += 1

    print(f"{copied} frames -> {out}")
    if missing:
        print(f"{len(missing)} picks not found: {', '.join(missing[:10])}{' …' if len(missing) > 10 else ''}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
