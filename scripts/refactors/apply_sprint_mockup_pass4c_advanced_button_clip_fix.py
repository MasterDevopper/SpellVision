"""
SpellVision — Sprint MOCKUP Pass 4c: Advanced "Open" button clip fix.

Symptom
-------
The Advanced card's "Open" toggle renders only ~1/4 visible (clipped
at the top), while Sampler & Scheduler / Output / Queue / LTX all show
their full "Open" button. The button works (clicking opens Advanced);
it's purely a visual clip.

Root cause
----------
All five disclosure cards collapse to the same 58px maxHeight. The
other four, when collapsed, ALSO hide their body hint label, so their
collapsed content is just the header strip (~26px button + title +
margins) which fits in 58px.

Advanced is the odd one out: Pass 4's skip-list keeps AdvancedBodyHint
VISIBLE even when collapsed:

    if (kn == "AdvancedHeader" || kn == "AdvancedBodyHint")
        continue;            // <-- hint stays shown when collapsed

So the collapsed Advanced card has to fit header + 24px hint + 8px
spacing + margins into 58px. It overflows, and the 58px clamp slices
the header where the vertically-centered toggle button sits -> the
button is clipped.

Fix
---
Make Advanced behave exactly like its four siblings: hide
AdvancedBodyHint when collapsed too. Collapsed Advanced becomes a
clean header-only strip that fits 58px, so the "Open" button renders
full-height. The hint reappears when expanded.

This is a one-line change: drop AdvancedBodyHint from the keep-list
so it gets hidden along with the rest of the body when collapsed.
AdvancedHeader stays in the keep-list so the header (title + button)
is always visible.

Order: apply after Pass 4b.
Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "SPRINT MOCKUP PASS 4C ADVANCED BUTTON CLIP FIX"
BACKUP_SUFFIX = ".pre_sprint_mockup_pass4c.bak"


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


# The Advanced gating loop currently keeps BOTH AdvancedHeader and
# AdvancedBodyHint visible when collapsed. Drop AdvancedBodyHint from
# the keep-list so it is hidden when collapsed, matching the four
# sibling cards (whose collapsed state is header-only).

ADV_KEEP_OLD = (
    '            const QString kn = kid->objectName();\n'
    '            if (kn == QStringLiteral("AdvancedHeader") || kn == QStringLiteral("AdvancedBodyHint"))\n'
    '                continue;\n'
    '            kid->setVisible(!collapseAdvanced);\n'
)

ADV_KEEP_NEW = (
    '            const QString kn = kid->objectName();\n'
    f'            // --- {MARKER}: only the header survives collapse ---\n'
    '            // (was: AdvancedHeader || AdvancedBodyHint — keeping the\n'
    '            //  hint visible overflowed the 58px clamp and clipped the\n'
    '            //  toggle button. Siblings hide their hint when collapsed.)\n'
    '            if (kn == QStringLiteral("AdvancedHeader"))\n'
    '                continue;\n'
    '            kid->setVisible(!collapseAdvanced);\n'
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
    text = replace_once(text, ADV_KEEP_OLD, ADV_KEEP_NEW,
                        "Advanced collapse keep-list")
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
