r"""
SpellVision — Pass 7b fixup: ChainStudioPage.h missing ChainModel.h include.

Build error cascade (~17 errors all rooted in one cause):
    ChainStudioPage.h(73,11): error C3646: 'stubChain_': unknown
        override specifier
    ChainStudioPage.h(73,5):  error C4430: missing type specifier
    ChainStudioPage.cpp(118,20+): error C2065: 'stubChain_': undeclared
        identifier  (x12)
    ChainStudioPage.cpp(126,16): error C2737: 'canAdd': const object
        must be initialized

Cause: Pass 7b added the member `Chain stubChain_;` to ChainStudioPage.h
but didn't add `#include "chain/ChainModel.h"`. Chain is held by value
so a forward-decl isn't sufficient — the compiler needs the full type
definition. MSVC's C3646 ("unknown override specifier") is its way of
saying "I don't know what 'Chain' is, so I'm guessing it must be one
of the contextual keywords like override/final" — a misleading message
that points at the wrong line.

The .cpp builds fine because its own #include block transitively pulls
in ChainModel.h via ChainRailWidget.h. The header was the gap.

Fix: one #include line near the top of ChainStudioPage.h. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 7B FIXUP CHAINMODEL INCLUDE"
BACKUP_SUFFIX = ".pre_pass7b_fixup.bak"


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


# Anchor on the existing #include <QWidget> line; add ChainModel.h
# above it so chain types are visible before any class declarations.
ANCHOR = (
    '#include <QWidget>\n'
    '\n'
    'class QLabel;\n'
)

REPLACEMENT = (
    f'// --- {MARKER} ---\n'
    '#include "chain/ChainModel.h"\n'
    '\n'
    '#include <QWidget>\n'
    '\n'
    'class QLabel;\n'
)


def patch_header(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)
    text = replace_once(text, ANCHOR, REPLACEMENT, "ChainStudioPage.h include block")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/chain/ChainStudioPage.h")
    patch_header(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
