"""
SpellVision — Sprint MOCKUP Pass 4b: Advanced toggle + Batch/Prefix leak.

Two bugs visible after Pass 4:

1. ADVANCED "Open" TOGGLE MISSING
   The Advanced collapse block (now correctly matching "AdvancedCard"
   after Pass 4) gates the toggle with:
       advancedToggleButton_->setVisible(advancedCard->isVisible());
   Every other disclosure card uses a plain setVisible(true). During
   the adaptive layout pass advancedCard->isVisible() is unreliable
   (false if the card or an ancestor hasn't been shown yet), so the
   Advanced toggle never appears (screenshots: Advanced header has no
   Open button, unlike Sampler & Scheduler / LTX). Fix: setVisible(true)
   to match the sibling cards.

2. BATCH / PREFIX AREA BROKEN (OutputQueueCard body leak)
   OutputQueueCard collapses to 58px via setMaximumHeight but never
   hides its body widgets — the exact same leak Pass 4 fixed for the
   other three cards. The clipped body (Batch row, Prefix row, Output
   Folder title + label) bleeds out under the header as a cramped,
   overlapping sliver. OutputQueueCard was simply out of Pass 4's
   scope.
   Its body widgets already carry distinct object names:
     - "OutputQueueBodyRow"   (Batch row, Prefix row)
     - "OutputQueueBodyLabel" (Output Folder title)
     - "OutputQueueBodyHint"  (Output Folder value label)
   so we gate by walking the card's direct children and hiding any
   whose objectName starts with "OutputQueueBody" when collapsed.
   The header (outputQueueHeader) has no such prefix so it stays.

Order: apply after Pass 4.
Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "SPRINT MOCKUP PASS 4B TOGGLE AND BATCH FIX"
BACKUP_SUFFIX = ".pre_sprint_mockup_pass4b.bak"


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


# ---------------------------------------------------------------------------
# 1. Advanced toggle visibility — match sibling cards (plain setVisible(true))
# ---------------------------------------------------------------------------

ADV_TOGGLE_OLD = (
    '            advancedToggleButton_->setVisible(advancedCard->isVisible());\n'
)
ADV_TOGGLE_NEW = (
    f'            advancedToggleButton_->setVisible(true);  // {MARKER}: was advancedCard->isVisible() (unreliable mid-layout)\n'
)


# ---------------------------------------------------------------------------
# 2. OutputQueueCard body gating — hide OutputQueueBody* children when
#    collapsed. Extend the existing collapse block.
# ---------------------------------------------------------------------------

OQ_BLOCK_OLD = (
    '        outputQueueCard->setToolTip(collapseOutput\n'
    '            ? QStringLiteral("Output / Queue is collapsed to protect prompt and canvas space. Click Open to expand.")\n'
    '            : QStringLiteral("Output / Queue details."));\n'
    '        if (outputQueueToggleButton_)\n'
)

OQ_BLOCK_NEW = (
    '        outputQueueCard->setToolTip(collapseOutput\n'
    '            ? QStringLiteral("Output / Queue is collapsed to protect prompt and canvas space. Click Open to expand.")\n'
    '            : QStringLiteral("Output / Queue details."));\n'
    f'        // --- {MARKER}: hide OutputQueue body widgets when collapsed ---\n'
    '        const QList<QWidget *> oqKids = outputQueueCard->findChildren<QWidget *>(\n'
    '            QString(), Qt::FindDirectChildrenOnly);\n'
    '        for (QWidget *kid : oqKids)\n'
    '        {\n'
    '            if (kid->objectName().startsWith(QStringLiteral("OutputQueueBody")))\n'
    '                kid->setVisible(!collapseOutput);\n'
    '        }\n'
    '        if (outputQueueToggleButton_)\n'
)


def patch_image_generation_cpp(project: Path) -> None:
    path = project / "qt_ui" / "ImageGenerationPage.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)

    text = replace_once(text, ADV_TOGGLE_OLD, ADV_TOGGLE_NEW,
                        "Advanced toggle visibility gate")
    text = replace_once(text, OQ_BLOCK_OLD, OQ_BLOCK_NEW,
                        "OutputQueue collapse block (body gating)")

    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("ImageGenerationPage.cpp")
    patch_image_generation_cpp(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next: rebuild with .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
