"""
SpellVision — Sprint MOCKUP Pass 1 FIXUP 3

Fixup 2 didn't clear the "Could not parse stylesheet" warnings and the
chip variants still aren't visually differentiated. After more digging,
the two remaining suspects are:

1. `border: none` (AiTimingRow) and `border: 0px` (AiDetailsToggle) are
   incomplete border shorthands. Qt's QSS parser expects the full
   `width style color` triple; partial forms can fail. Replace with
   explicit property forms (`border-top: ...` alone, or
   `border-style: none`).

2. `[chipState="..."]` attribute selectors aren't being applied even
   though the matching readiness attribute selectors work. The
   difference: readiness widgets get explicit `repolishWidget()` calls,
   chips are created fresh per update with no repolish. The safer path
   is to skip attribute selectors entirely for chips — give chips
   distinct object names ("AiChipSet" / "AiChipAuto") and let Qt match
   them at first polish, no property-change choreography required.

This fixup:
  - ThemeManager.cpp:
    - Replaces "QLabel#AiChip[chipState=...]" rules with standalone
      "#AiChipSet" / "#AiChipAuto" rules (full property sets, not
      relying on inheritance from #AiChip).
    - Replaces "border: none" on AiTimingRow with just the border-top
      declaration (other sides default to nothing).
    - Replaces "border: 0px" on AiDetailsToggle with "border-style: none"
      which Qt's parser handles unambiguously.
  - ImageGenerationPage.cpp:
    - In the chip creation lambda, swaps
      `setObjectName("AiChip") + setProperty("chipState", ...)`
      for `setObjectName(isSet ? "AiChipSet" : "AiChipAuto")`.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "SPRINT MOCKUP PASS 1 FIXUP 3"
BACKUP_SUFFIX = ".pre_sprint_mockup_pass1_fixup3.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def apply_replacements(text: str, replacements: list[tuple[str, str, str]]) -> str:
    for old, new, label in replacements:
        if old not in text:
            raise RuntimeError(f"Anchor not found: {label}\n  Looking for: {old!r}")
        text = text.replace(old, new, 1)
    return text


# ---------------------------------------------------------------------------
# ThemeManager.cpp
# ---------------------------------------------------------------------------

THEME_REPLACEMENTS = [
    # 1. AiChip variants: ditch attribute selectors, use distinct object names.
    (
        '"QLabel#AiChip[chipState=\\"set\\"] { background: %43; border-color: %44; color: %13; }"',
        '"QLabel#AiChipSet { background: %43; border: 1px solid %44; border-radius: 12px; padding: 2px 10px; color: %13; font-size: 11px; min-height: 18px; }"',
        "AiChip set-variant rule"
    ),
    (
        '"QLabel#AiChip[chipState=\\"auto\\"] { border-style: dashed; color: %14; }"',
        '"QLabel#AiChipAuto { background: %17; border: 1px dashed %18; border-radius: 12px; padding: 2px 10px; color: %14; font-size: 11px; min-height: 18px; }"',
        "AiChip auto-variant rule"
    ),
    # 2. AiTimingRow: drop the incomplete `border: none` shorthand.
    (
        '"QFrame#AiTimingRow { background: transparent; border: none; border-top: 1px solid %29; }"',
        '"QFrame#AiTimingRow { background: transparent; border-top: 1px solid %29; }"',
        "AiTimingRow rule"
    ),
    # 3. AiDetailsToggle: switch `border: 0px` to `border-style: none`.
    (
        '"QToolButton#AiDetailsToggle { background: transparent; border: 0px; padding: 4px 0px; color: %45; font-size: 11px; min-height: 18px; font-weight: 600; }"',
        '"QToolButton#AiDetailsToggle { background: transparent; border-style: none; padding: 4px 0px; color: %45; font-size: 11px; min-height: 18px; font-weight: 600; }"',
        "AiDetailsToggle rule"
    ),
]


def patch_theme_manager(project: Path) -> None:
    path = project / "qt_ui" / "ThemeManager.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return

    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return

    backup_once(path)
    text = apply_replacements(text, THEME_REPLACEMENTS)
    # Stamp the marker for idempotency.
    text = text.replace(
        '// SPRINT MOCKUP PASS 1 FIXUP 2',
        f'// SPRINT MOCKUP PASS 1 FIXUP 2 + {MARKER}',
        1,
    )
    write_text(path, text)
    print(f"  Patched: {path.name}")


# ---------------------------------------------------------------------------
# ImageGenerationPage.cpp
# ---------------------------------------------------------------------------

# The chip-creation lambda currently has TWO lines we need to rewrite:
#   chip->setObjectName(QStringLiteral("AiChip"));
#   chip->setProperty("chipState", isSet ? QStringLiteral("set") : QStringLiteral("auto"));
#
# Replace the pair with a single dynamic-objectName call that picks
# AiChipSet or AiChipAuto. Drop the setProperty entirely (no longer
# needed since we're not using attribute selectors).

CPP_OLD = (
    '        chip->setObjectName(QStringLiteral("AiChip"));\n'
    '        chip->setProperty("chipState", isSet ? QStringLiteral("set") : QStringLiteral("auto"));\n'
)

CPP_NEW = (
    '        // --- FIXUP 3: distinct object names, no attribute selector ---\n'
    '        chip->setObjectName(isSet ? QStringLiteral("AiChipSet") : QStringLiteral("AiChipAuto"));\n'
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

    if CPP_OLD not in text:
        raise RuntimeError(
            "ImageGenerationPage.cpp does not contain the expected chip-creation "
            "lines. Has fixup 2 been applied? Run "
            "apply_sprint_mockup_pass1_fixup2.py first."
        )

    backup_once(path)
    text = text.replace(CPP_OLD, CPP_NEW, 1)
    # Stamp the marker for idempotency.
    text = text.replace(
        '// SPRINT MOCKUP PASS 1 FIXUP 2',
        f'// SPRINT MOCKUP PASS 1 FIXUP 2 + {MARKER}',
        1,
    )
    write_text(path, text)
    print(f"  Patched: {path.name}")


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------

def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()

    print("ThemeManager.cpp")
    patch_theme_manager(project)
    print()
    print("ImageGenerationPage.cpp")
    patch_image_generation_cpp(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next: rebuild with .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
