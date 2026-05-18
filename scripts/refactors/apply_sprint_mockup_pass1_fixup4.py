"""
SpellVision — Sprint MOCKUP Pass 1 FIXUP 4 (the actual root cause)

After staring at the patched ThemeManager.cpp, the real bug is finally
visible: the original Pass 1 patch REPLACED the last .arg() in the
chain instead of inserting after it.

The QSS uses placeholders %1 through %45 (45 placeholders).
The current .arg() chain has only 44 calls:
  - Lines 637-668: 32 calls (originally 33, one lost)
  - Lines 678-689: 12 new color-slot calls

QString::arg() substitutes the lowest-numbered remaining placeholder on
each call. With 44 args for 45 placeholders, every substitution from
%33 onward shifts by one, and %45 is left as literal "%45" in the
output QSS string.

%45 is used in QToolButton#AiDetailsToggle's `color: %45;`. Qt's QSS
parser sees `color: %45` (not a valid CSS color token) and emits
"Could not parse stylesheet" on the whole rule, which is why the
toggle falls back to the gradient base style.

This fixup adds ONE LINE — the original arg that fed %33 — back to
the chain at the correct position (between the existing args and the
new color-slot args).

After this fixup, all 45 placeholders get the value they were meant
to have, AiDetailsToggle renders flat-accent, the chip variants from
fixup 3 should also display correctly, and the parse warnings clear.

Why the previous three fixups didn't fix it:
  - Fixup 1 (text-align removed) — irrelevant property
  - Fixup 2 (is -> chipState rename, letter-spacing dropped) — the
    `is` property might still have been a latent concern, but neither
    change touched the actual missing-arg problem
  - Fixup 3 (object-name variants, border cleanup) — the chip and
    border changes are defensively good but again not the root cause

All three previous fixups are HARMLESS — they're defensive cleanups
that stay in place. Fixup 4 finally addresses the real parse failure.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "SPRINT MOCKUP PASS 1 FIXUP 4"
BACKUP_SUFFIX = ".pre_sprint_mockup_pass1_fixup4.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


# ---------------------------------------------------------------------------
# ThemeManager.cpp — restore the missing %33 arg
# ---------------------------------------------------------------------------

# Insert AFTER the line that currently feeds %32 (was the original 32nd
# arg) and BEFORE the comment block that introduces the 12 new color
# slots (which now correctly start at %34 instead of being shifted into
# %33).

ANCHOR = (
    '        .arg(rgba(withAlpha(mix(inputSurface(), background0(), 0.42), 1.0), 1.0))\n'
    '        // --- SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: new color slots (34-45) ---\n'
)

# Note: no trailing semicolon on the inserted .arg() — the chain
# continues. The terminating `);` stays on the last (12th) new arg.
REPLACEMENT = (
    '        .arg(rgba(withAlpha(mix(inputSurface(), background0(), 0.42), 1.0), 1.0))\n'
    f'        // --- {MARKER}: restore missing %33 arg (was lost when Pass 1 replaced instead of inserted) ---\n'
    '        .arg(rgba(withAlpha(mix(panel0, background0(), 0.20), 1.0), 1.0))\n'
    '        // --- SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: new color slots (34-45) ---\n'
)


def patch_theme_manager(project: Path) -> None:
    path = project / "qt_ui" / "ThemeManager.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return

    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return

    if ANCHOR not in text:
        raise RuntimeError(
            "Could not find the .arg-chain insertion anchor. The Pass 1 patches "
            "may have been hand-edited or the file may already differ from "
            "what fixup 4 expects."
        )

    backup_once(path)
    text = text.replace(ANCHOR, REPLACEMENT, 1)
    write_text(path, text)
    print(f"  Patched: {path.name}")


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------

def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()

    print("ThemeManager.cpp")
    patch_theme_manager(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next: rebuild with .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
