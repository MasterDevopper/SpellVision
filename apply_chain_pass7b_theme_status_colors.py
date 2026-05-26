r"""
SpellVision — Chain Studio Pass 7b (theme piggyback): expose status colors.

ThemeManager.h declares successColor/warningColor/errorColor in the
PRIVATE section (lines 123-125, after the private: marker on 105).
ChainRailWidget needs them for status-dot rendering on stage chips.

Mirrors the precedent established in the user memory for
background0Color/background1Color — those were exposed as PUBLIC
compat-layer wrappers returning the private value. Same pattern here:
three inline public wrappers in the existing Compatibility Layer
section.

Strictly additive — does not move the private declarations, does not
change any existing accessor, does not touch any other file.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 7B THEME EXPOSE STATUS COLORS"
BACKUP_SUFFIX = ".pre_pass7b_theme.bak"


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


# Anchor on the existing compat-layer block's tail. The line right
# after `QColor borderToneColor() const { return borderColor(); }` is
# the natural insertion point — same section, same wrapper style.
ANCHOR = (
    "    QColor borderToneColor() const { return borderColor(); }\n"
    "\n"
    "signals:\n"
)

REPLACEMENT = (
    "    QColor borderToneColor() const { return borderColor(); }\n"
    "\n"
    f"    // --- {MARKER} ---\n"
    "    // Status colors exposed via compat-layer wrappers. Required\n"
    "    // by ChainRailWidget's status dots; same pattern that already\n"
    "    // exposes surface0/surface1/text*/border.\n"
    "    QColor successColorPublic() const { return successColor(); }\n"
    "    QColor warningColorPublic() const { return warningColor(); }\n"
    "    QColor errorColorPublic()   const { return errorColor(); }\n"
    "\n"
    "signals:\n"
)


def patch_header(project: Path) -> None:
    path = project / "qt_ui" / "ThemeManager.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)
    text = replace_once(text, ANCHOR, REPLACEMENT, "compat-layer tail")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/ThemeManager.h")
    patch_header(project)
    print()
    print(f"Done — {MARKER} applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
