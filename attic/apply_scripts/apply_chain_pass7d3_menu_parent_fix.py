r"""
SpellVision — Pass 7d.3 menu parent fix.

DIAGNOSTIC CONFIRMS click flow now works end-to-end through showAddStageMenu.
The remaining issue is the QMenu refusing to popup with:

  QWidgetWindow(0x..., name="ChainStudioPageClassWindow") must be a top level window.

ROOT CAUSE per Qt docs / forum:
  QMenu internally calls setTransientParent on its parent widget's window.
  If the parent isn't a top-level window (i.e., it's embedded in something
  larger, like our ChainStudioPage embedded inside MainWindow's central
  widget stack), Qt prints this warning and the popup fails.

FIX:
  Construct QMenu with `window()` instead of `this`. QWidget::window()
  returns the ancestor top-level widget (the MainWindow), which IS a
  proper top-level window.

This single-line change in showAddStageMenu should make the kind-picker
QMenu pop correctly below the + add stage button.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

MARKER = "PASS 7D3 MENU PARENT FIX"


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    path = project / "qt_ui" / "chain" / "ChainStudioPage.cpp"
    if not path.exists():
        print(f"  Not found: {path}")
        return 1

    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return 0

    backup_once(path, ".pre_pass7d3_menu_parent_fix.bak")

    # Change `QMenu menu(this);` inside showAddStageMenu to
    # `QMenu menu(window());`. Use a regex to tolerate any whitespace
    # variations and CRLF.
    pattern = re.compile(r"QMenu menu\(this\);")
    if not pattern.search(text):
        # Already fixed or different form?
        if "QMenu menu(window())" in text:
            print("  Already in correct form")
            return 0
        raise RuntimeError("Cannot find QMenu construction in showAddStageMenu")

    replacement = (
        f"// --- {MARKER}: menu must be parented to top-level window per Qt docs ---\r\n"
        "    QMenu menu(window());"
    )
    text = pattern.sub(replacement, text, count=1)

    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")
    print()
    print(f"Done — {MARKER} applied.")
    print()
    print("Run: .\\scripts\\dev\\run_ui.ps1")
    print()
    print("Click the + add stage button. The kind-picker menu should now")
    print("pop below the button with two options (T2I and T2V).")
    print()
    print("Expected log lines:")
    print("  ... (all the previous click flow) ...")
    print("  [ChainStudio] about to menu.exec, actions: 2")
    print("  (NO 'must be a top level window' warning this time)")
    print("  [ChainStudio] menu.exec returned, picked: '<chosen action>' or '<nullptr>'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
