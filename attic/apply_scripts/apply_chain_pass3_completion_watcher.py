r"""
SpellVision — Chain Studio Pass 3: register ChainCompletionWatcher.

Adds the two new files (ChainCompletionWatcher.h/.cpp) to the existing
Chain Studio block in CMakeLists.txt. Per the Pass 2 lesson, the CMake
registration is now part of the same pass as the new files, not a
separate followup.

Idempotent.

After applying:
    .\scripts\dev\run_ui.ps1
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "CHAIN STUDIO PASS 3 CMAKE REGISTRATION"
BACKUP_SUFFIX = ".pre_chain_pass3_cmake.bak"


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


# Anchor on the trailing line of the Pass 1+2 block (ChainStore.cpp).
# Appending the new files keeps the chain/ entries grouped together.
ANCHOR = (
    "    qt_ui/chain/ChainModel.h\n"
    "    qt_ui/chain/ChainStore.h\n"
    "    qt_ui/chain/ChainStore.cpp\n"
)

REPLACEMENT = (
    "    qt_ui/chain/ChainModel.h\n"
    "    qt_ui/chain/ChainStore.h\n"
    "    qt_ui/chain/ChainStore.cpp\n"
    f"    # --- {MARKER} ---\n"
    "    qt_ui/chain/ChainCompletionWatcher.h\n"
    "    qt_ui/chain/ChainCompletionWatcher.cpp\n"
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
    text = replace_once(text, ANCHOR, REPLACEMENT, "Chain Studio source group")
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
    print("Next: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
