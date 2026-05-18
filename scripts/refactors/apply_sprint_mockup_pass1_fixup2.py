"""
SpellVision — Sprint MOCKUP Pass 1 FIXUP 2

Pass 1's fixup removed `text-align: left` but the "Could not parse
stylesheet" warnings persisted and the AiDetailsToggle still falls
back to the gradient base style. After looking at the generated QSS,
two more suspects stand out:

1. `[is="set"]` / `[is="auto"]` attribute selectors. `is` collides
   with CSS Selectors Level 4's `:is(...)` pseudo-class function.
   Qt's QSS parser likely treats `is` as a special token and bails
   on the surrounding rule. Symptom: the AiChip variant rules don't
   apply -- all chips render with the solid base border, none dashed.
2. `letter-spacing: 1px`. Not listed in Qt's official QSS reference.
   Inconsistent acceptance across Qt versions. Safer to drop.
3. `border: none` for AiDetailsToggle. Accepted by Qt but some parser
   paths can stumble; `border: 0px` is bulletproof and equivalent.

This fixup:
  - Renames the dynamic property `is` -> `chipState` in both the QSS
    selectors AND the setProperty() call.
  - Drops `letter-spacing` from AiGroupLabel and AiTimingKey rules.
  - Switches `border: none` -> `border: 0px` for AiDetailsToggle.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "SPRINT MOCKUP PASS 1 FIXUP 2"
BACKUP_SUFFIX = ".pre_sprint_mockup_pass1_fixup2.bak"


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
    """Each replacement is (old, new, label). Raises if `old` not found."""
    for old, new, label in replacements:
        if old not in text:
            raise RuntimeError(f"Anchor not found: {label}\n  Looking for: {old!r}")
        text = text.replace(old, new, 1)
    return text


# ---------------------------------------------------------------------------
# 1. ThemeManager.cpp
# ---------------------------------------------------------------------------

THEME_REPLACEMENTS = [
    # AiChip[is="set"] -> AiChip[chipState="set"]
    (
        '"QLabel#AiChip[is=\\"set\\"] { background: %43; border-color: %44; color: %13; }"',
        '"QLabel#AiChip[chipState=\\"set\\"] { background: %43; border-color: %44; color: %13; }"',
        "AiChip[is=\"set\"] selector"
    ),
    # AiChip[is="auto"] -> AiChip[chipState="auto"]
    (
        '"QLabel#AiChip[is=\\"auto\\"] { border-style: dashed; color: %14; }"',
        '"QLabel#AiChip[chipState=\\"auto\\"] { border-style: dashed; color: %14; }"',
        "AiChip[is=\"auto\"] selector"
    ),
    # AiGroupLabel: drop letter-spacing
    (
        '"QLabel#AiGroupLabel { font-size: 10px; color: %14; background: transparent; font-weight: 800; letter-spacing: 1px; }"',
        '"QLabel#AiGroupLabel { font-size: 10px; color: %14; background: transparent; font-weight: 800; }"',
        "AiGroupLabel rule"
    ),
    # AiTimingKey: drop letter-spacing
    (
        '"QLabel#AiTimingKey { font-size: 10px; color: %14; background: transparent; font-weight: 800; letter-spacing: 1px; }"',
        '"QLabel#AiTimingKey { font-size: 10px; color: %14; background: transparent; font-weight: 800; }"',
        "AiTimingKey rule"
    ),
    # AiDetailsToggle: border: none -> border: 0px
    (
        '"QToolButton#AiDetailsToggle { background: transparent; border: none; padding: 4px 0; color: %45; font-size: 11px; min-height: 18px; font-weight: 600; }"',
        '"QToolButton#AiDetailsToggle { background: transparent; border: 0px; padding: 4px 0px; color: %45; font-size: 11px; min-height: 18px; font-weight: 600; }"',
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
    # Stamp the marker so idempotency works.
    text = text.replace(
        '// --- END SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE ---',
        f'// --- END SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE ---  // {MARKER}',
        1,
    )
    write_text(path, text)
    print(f"  Patched: {path.name}")


# ---------------------------------------------------------------------------
# 2. ImageGenerationPage.cpp
# ---------------------------------------------------------------------------

CPP_REPLACEMENTS = [
    (
        'chip->setProperty("is", isSet ? QStringLiteral("set") : QStringLiteral("auto"));',
        'chip->setProperty("chipState", isSet ? QStringLiteral("set") : QStringLiteral("auto"));',
        "chip setProperty"
    ),
]


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
    text = apply_replacements(text, CPP_REPLACEMENTS)
    # Stamp the marker so idempotency works.
    text = text.replace(
        '// --- END SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: structured population ---',
        f'// --- END SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE: structured population ---  // {MARKER}',
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
