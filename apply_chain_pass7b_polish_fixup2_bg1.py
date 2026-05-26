r"""
SpellVision — Pass 7b-polish fixup #2: page bg one tier brighter.

Pass 7b-polish swapped the page background from surface0 -> background0
to give cards more contrast against the page. The screenshot showed
the cards' borders are now too subtle against the very dark background0
(#070b12 in ArcaneGlass), so the page reads slightly washed-out.

Per the project's named-by-role color hierarchy:
    background0 < background1 < surface0 < surface1
background1 (#101624) is the literal "page background tier", whereas
background0 (#070b12) is the absolute darkest, intended for under-
overlays etc. The original surface0 was one tier too high; background0
overshot in the other direction. background1 is the named-correct
middle ground.

One-line change. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 7B POLISH FIXUP 2 BACKGROUND1"
BACKUP_SUFFIX = ".pre_pass7b_polish_fixup2.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Anchor not found: {label}")
    if text.count(old) > 1:
        raise RuntimeError(f"Anchor not unique ({text.count(old)}x): {label}")
    return text.replace(old, new, 1)


OLD = "    pal.setColor(QPalette::Window, tm.background0Color());\n"
NEW = f"    pal.setColor(QPalette::Window, tm.background1Color());  // {MARKER}\n"


def patch_page(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)
    text = replace_once(text, OLD, NEW, "page bg palette assignment")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/chain/ChainStudioPage.cpp")
    patch_page(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
