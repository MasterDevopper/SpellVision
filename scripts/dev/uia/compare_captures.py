"""Fraction of differing pixels between two captures. Used to prove a change is visible.

    compare_captures.py A.png B.png [--crop-bottom N] [--bbox]

`--crop-bottom N` drops the last N rows before comparing, and it exists because the capture rig
saves a FIXED 1600x1000 screen region rather than the window. The app's window is shorter than
that, so the bottom rows of every shot are whatever sits behind it -- on this machine, the Windows
taskbar, whose clock changes between runs. Two captures of an UNTOUCHED tree taken days apart read
0.0276 against each other on that strip alone, which is three times the 0.0100 gate the programme
uses to prove two things differ. A comparison against a capture from another session is therefore
measuring the clock unless those rows are dropped. `--crop-bottom 40` covers it here.

The honest alternative, and the better one where it is possible, is to capture a `-before` prefix
in the SAME session as the `-after` and compare those: the rig is deterministic within a session
(a repeat capture of an unchanged tree reads 0 pixels of 1,600,000).

`--bbox` additionally prints the bounding box of the differing region. A number on its own says two
images differ; the box says WHERE, which is what turns a mystery into a defect. It is how a missing
rail gradient was found in this wave -- the fraction was a plausible 0.0119 and the box was exactly
the rail's 64 px column, which named the bug on sight.
"""
import sys

from PIL import Image, ImageChops


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = [a for a in argv[1:] if a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2

    crop_bottom = 0
    for flag in flags:
        if flag.startswith("--crop-bottom"):
            _, _, value = flag.partition("=")
            if not value:
                index = argv.index(flag)
                value = argv[index + 1] if index + 1 < len(argv) else "0"
            crop_bottom = int(value)

    a = Image.open(args[0]).convert("RGB")
    b = Image.open(args[1]).convert("RGB")
    if a.size != b.size:
        print(f"size mismatch {a.size} vs {b.size}")
        return 2

    if crop_bottom:
        height = a.height - crop_bottom
        if height <= 0:
            print(f"--crop-bottom {crop_bottom} leaves nothing of a {a.height} row image")
            return 2
        box = (0, 0, a.width, height)
        a = a.crop(box)
        b = b.crop(box)

    diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 8 else 0)
    changed = sum(1 for v in diff.getdata() if v)
    print(f"{changed / (diff.width * diff.height):.4f}")

    if "--bbox" in flags:
        bbox = diff.getbbox()
        print(f"bbox {bbox}" if bbox else "bbox none (identical)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
