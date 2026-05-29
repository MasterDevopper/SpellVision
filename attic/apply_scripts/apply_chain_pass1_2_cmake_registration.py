r"""
SpellVision — Chain Studio Pass 1+2: register new files in CMakeLists.txt.

Adds the three new chain/ files to the qt_add_executable(SpellVision ...)
source list so CMake compiles them and regenerates compile_commands.json
(which fixes the VS Code IntelliSense "cannot open source file QDateTime"
errors as a side effect — those are IntelliSense complaints from files
not being in the build graph yet, not real compile failures).

Anchors on the last two source lines so insertion order matches the
existing per-page grouping (utility/chrome at the bottom). Idempotent.

After applying:
    1. Run .\scripts\dev\run_ui.ps1  (this triggers cmake configure,
       which regenerates compile_commands.json and IntelliSense picks
       up the new files automatically).
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "CHAIN STUDIO PASS 1+2 CMAKE REGISTRATION"
BACKUP_SUFFIX = ".pre_chain_cmake.bak"


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


# Anchor on the last two source lines + closing paren. Inserting the new
# block above the closing paren keeps existing file ordering intact.
ANCHOR = (
    "    qt_ui/ModelManagerPage.h\n"
    "    qt_ui/ModelManagerPage.cpp\n"
    ")\n"
)

REPLACEMENT = (
    "    qt_ui/ModelManagerPage.h\n"
    "    qt_ui/ModelManagerPage.cpp\n"
    "\n"
    f"    # --- {MARKER} ---\n"
    "    qt_ui/chain/ChainModel.h\n"
    "    qt_ui/chain/ChainStore.h\n"
    "    qt_ui/chain/ChainStore.cpp\n"
    ")\n"
)


def patch_cmake(project: Path) -> None:
    path = project / "CMakeLists.txt"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)
    text = replace_once(text, ANCHOR, REPLACEMENT, "qt_add_executable source list tail")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("CMakeLists.txt")
    patch_cmake(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next: .\\scripts\\dev\\run_ui.ps1  (regenerates compile_commands.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
