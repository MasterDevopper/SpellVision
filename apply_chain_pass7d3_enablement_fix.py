r"""
SpellVision — Pass 7d.3 enablement fix.

ROOT CAUSE CONFIRMED via diagnostic:
  - addButton_ is disabled at click time (isEnabled=false)
  - Per Qt source (qabstractbutton.cpp), disabled buttons don't fire clicked
  - Disabled state set by ChainStudioPage::buildChainRail's canAdd logic:
      canAdd = stages.isEmpty() || stages.back().status == Locked
  - Our stub chain ends with I→3D in StageStatus::Draft → canAdd = false
  - The disabled stylesheet against dark bg made the button LOOK enabled

This isn't a Qt bug. The button correctly refuses clicks because the
business logic says "can't add a stage when the tail isn't locked".

FIX (two parts):

1. Change the stub chain's final stage to StageStatus::Locked so the
   demo state matches a chain where "+ add stage" is valid. This is
   what the kind-picker menu was designed to test.

2. Make the disabled state visually obvious (gray text, dashed border)
   so we don't hit this confusion again. (Already mostly correct in
   addBtnStyle's disabled branch, but verify against the actual page
   background.)

After this, clicking the now-enabled + add stage button will fire
clicked → onAddStageClicked → emit addStageRequested(pos) → page's
showAddStageMenu pops the kind-picker menu.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

MARKER = "PASS 7D3 ENABLEMENT FIX"


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    page_path = project / "qt_ui" / "chain" / "ChainStudioPage.cpp"
    if not page_path.exists():
        print(f"  Not found: {page_path}")
        return 1

    text = page_path.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"  Already patched: {page_path.name}")
        return 0

    backup_once(page_path, ".pre_pass7d3_enablement_fix.bak")

    # Change the third (I→3D) stage in buildStubChain from Draft → Locked.
    # Pattern: the three append() calls add stages in order T2I/I2V/I→3D.
    # The third one is "makeStub(StageKind::I2_3D, StageStatus::Draft, 0, 2)".
    # Change Draft → Locked AND varCount 0 → 1 (so lockedVarIdx is sensible).

    old = (
        "stubChain_.stages.append(makeStub(StageKind::I2_3D, StageStatus::Draft,   0, 2));"
    )
    new = (
        f"// --- {MARKER}: final stage must be Locked for + add stage to enable ---\r\n"
        "    stubChain_.stages.append(makeStub(StageKind::I2_3D, StageStatus::Locked,  1, 2));"
    )

    if old not in text:
        # Try CRLF-tolerant search
        # The line above has multiple spaces; let's be lenient
        pattern = re.compile(
            r"stubChain_\.stages\.append\(makeStub\(StageKind::I2_3D,\s*StageStatus::Draft,\s*0,\s*2\)\);"
        )
        m = pattern.search(text)
        if not m:
            raise RuntimeError("Cannot find I→3D stage append line in stub chain builder")
        text = text[:m.start()] + new + text[m.end():]
    else:
        text = text.replace(old, new, 1)

    page_path.write_text(text, encoding="utf-8")
    print(f"  Patched: {page_path.name}")
    print()
    print(f"Done — {MARKER} applied.")
    print()
    print("Now the stub chain ends with a Locked stage, so canAdd = true,")
    print("the + add stage button gets enabled, and clicking it should:")
    print("  - fire QPushButton::clicked")
    print("  - call onAddStageClicked")
    print("  - emit addStageRequested(pos)")
    print("  - call page's onRailAddStageRequested → showAddStageMenu")
    print("  - pop the kind-picker QMenu with I2I/I2V/I→3D options")
    print()
    print("Run: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
