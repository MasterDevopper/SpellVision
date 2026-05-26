r"""
SpellVision — Pass 7d.1 fixup: ClickOnlyComboBox include path.

Build error:
    ChainConfigPanelWidget.cpp(3,10): error C1083: Cannot open include
    file: 'ClickOnlyComboBox.h': No such file or directory

I wrote #include "ClickOnlyComboBox.h" but the file lives at
qt_ui/widgets/ClickOnlyComboBox.h. The rest of the project uses
    #include "widgets/ClickOnlyComboBox.h"
(see ImageGenerationPage.cpp:18). I had the widgets/ prefix correct
on the SectionCardWidgets include just two lines later but dropped it
here. Same class of bug as Pass 7b's missing chain/ChainModel.h —
include path not matching disk layout. Fix: add the widgets/ prefix.

One-line edit. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 7D1 FIXUP CLICKONLY INCLUDE"
BACKUP_SUFFIX = ".pre_pass7d1_fixup_include.bak"


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


OLD = '#include "ClickOnlyComboBox.h"\n'
NEW = f'// --- {MARKER} ---\n#include "widgets/ClickOnlyComboBox.h"\n'


def patch_canvas(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainConfigPanelWidget.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)
    text = replace_once(text, OLD, NEW, "ClickOnlyComboBox include line")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/chain/ChainConfigPanelWidget.cpp")
    patch_canvas(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
