r"""
SpellVision — Pass 7b-polish fixup: missing theme accessors + u8 literals.

Two distinct build errors from the polish pass:

(#1) C2039: 'background0Color' / 'background1Color' is not a member of
    'ThemeManager'. I assumed these public accessors existed (the user
    memory said they were patched in). Reading the actual ThemeManager.h
    shows they don't — only surface0/surface1/text*/border have public
    compat-layer wrappers. The private accessors background0()/background1()
    exist (ThemeManager.cpp:286, :298), they just aren't exposed.

(#2) C2308: concatenating mismatched strings. I used QStringLiteral(u8"...")
    to embed Unicode arrow chars. The u8 prefix makes them char8_t string
    literals (or char in pre-C++20), which QStringLiteral can't concatenate
    with its own internal char-16 buffer. The u8 prefix was reflexive and
    unnecessary — the source file is UTF-8 and Qt handles it natively.

Fix (#1) by adding background0Color()/background1Color() to ThemeManager.h
in the same Compatibility Layer section as the Pass 7b status colors. Same
inline-wrapper pattern. Strictly additive.

Fix (#2) by replacing the u8"\u..." literals in ChainRailWidget.cpp with
plain "..." literals carrying the arrow characters as raw UTF-8.

Three surgical edits across two files. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 7B POLISH FIXUP THEME AND U8"
THEME_BACKUP_SUFFIX = ".pre_pass7b_polish_fixup_theme.bak"
RAIL_BACKUP_SUFFIX  = ".pre_pass7b_polish_fixup_rail.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Anchor not found: {label}")
    if text.count(old) > 1:
        raise RuntimeError(f"Anchor not unique ({text.count(old)}x): {label}")
    return text.replace(old, new, 1)


# =============================================================================
# 1. ThemeManager.h — add background0Color / background1Color public wrappers
# =============================================================================
# Mirrors the Pass 7B status-color wrappers added just below borderToneColor.
# Insert immediately after the status-color block so all bg/surface/text/
# border/status accessors stay grouped in the compat-layer section.

THEME_ANCHOR = (
    "    QColor successColorPublic() const { return successColor(); }\n"
    "    QColor warningColorPublic() const { return warningColor(); }\n"
    "    QColor errorColorPublic()   const { return errorColor(); }\n"
)

THEME_REPLACEMENT = (
    "    QColor successColorPublic() const { return successColor(); }\n"
    "    QColor warningColorPublic() const { return warningColor(); }\n"
    "    QColor errorColorPublic()   const { return errorColor(); }\n"
    "\n"
    f"    // --- {MARKER} ---\n"
    "    // Background tier colors — one tier deeper than surface0/1.\n"
    "    // Used by ChainStudioPage as its page background so the\n"
    "    // surface1 cards (panels) actually contrast against the page.\n"
    "    // Hierarchy: background0 < background1 < surface0 < surface1.\n"
    "    QColor background0Color() const { return background0(); }\n"
    "    QColor background1Color() const { return background1(); }\n"
)


def patch_theme(project: Path) -> None:
    path = project / "qt_ui" / "ThemeManager.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if "background0Color()" in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, THEME_BACKUP_SUFFIX)
    text = replace_once(text, THEME_ANCHOR, THEME_REPLACEMENT,
                        "Pass 7b status-color block tail")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# =============================================================================
# 2. ChainRailWidget.cpp — drop u8 prefix on Unicode string literals
# =============================================================================
# Two sites — the I->3D kind label and the connector arrow. Both can be
# raw UTF-8 in the source string (the file is saved as UTF-8 and Qt
# treats QStringLiteral arguments as UTF-8 by default).

ARROW_3D_OLD = 'return QStringLiteral(u8"I\\u21923D");'
ARROW_3D_NEW = 'return QStringLiteral("I\\u2192" "3D");  // I->3D, split to avoid \\u + hex digit ambiguity'

CONNECTOR_OLD = 'auto *connector = new QLabel(QStringLiteral(u8"\\u2192"), content_);'
CONNECTOR_NEW = 'auto *connector = new QLabel(QStringLiteral("\\u2192"), content_);'


def patch_rail(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainRailWidget.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, RAIL_BACKUP_SUFFIX)
    text = replace_once(text, ARROW_3D_OLD, ARROW_3D_NEW, "I->3D kind label")
    text = replace_once(text, CONNECTOR_OLD, CONNECTOR_NEW, "connector arrow literal")
    # Marker comment for idempotency.
    text = text.replace(
        "namespace\n{\n",
        f"namespace\n{{\n// --- {MARKER} ---\n",
        1,
    )
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/ThemeManager.h")
    patch_theme(project)
    print()
    print("qt_ui/chain/ChainRailWidget.cpp")
    patch_rail(project)
    print()
    print(f"Done — {MARKER} applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
