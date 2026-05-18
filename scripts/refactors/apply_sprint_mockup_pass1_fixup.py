"""
SpellVision — Sprint MOCKUP Pass 1 FIXUP

Post-application fixes for Pass 1:

1. ThemeManager.cpp
   QToolButton#AiDetailsToggle: remove `text-align: left`. Qt's QSS parser
   only accepts text-align on QPushButton and QProgressBar; on
   QToolButton it triggers a "Could not parse stylesheet" warning and the
   ENTIRE rule is dropped, which causes the toggle to fall back to the
   gradient QPushButton/QToolButton baseline. Without it, the rule
   applies and the toggle gets the flat accent-colored link treatment.

   Workaround for alignment: set Qt::AlignLeft on the button's icon-text
   layout via setStyleSheet won't work, but the QToolButton's default
   ToolButtonStyle of TextOnly already left-aligns the text inside the
   button rect. Combined with no padding, that's already mockup-correct.

2. ImageGenerationPage.cpp
   updateAssetIntelligenceUi: the right-aligned sub was being filled
   with "Select a checkpoint to generate." while the readiness text was
   already showing the same string. Make the sub empty when not ready
   (the headline already carries the block reason).

Idempotent. Re-running is a no-op once the FIXUP marker is present in
each file.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "SPRINT MOCKUP PASS 1 FIXUP"
BACKUP_SUFFIX = ".pre_sprint_mockup_pass1_fixup.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


# ---------------------------------------------------------------------------
# 1. ThemeManager.cpp — strip `text-align: left` from AiDetailsToggle
# ---------------------------------------------------------------------------

THEME_OLD = (
    '"QToolButton#AiDetailsToggle { background: transparent; border: none; '
    'padding: 4px 0; color: %45; font-size: 11px; min-height: 18px; '
    'text-align: left; font-weight: 600; }"'
)

THEME_NEW = (
    '"QToolButton#AiDetailsToggle { background: transparent; border: none; '
    'padding: 4px 0; color: %45; font-size: 11px; min-height: 18px; '
    'font-weight: 600; }"'
    f'  // {MARKER}: text-align stripped (unsupported on QToolButton)'
)


def patch_theme_manager(project: Path) -> None:
    path = project / "qt_ui" / "ThemeManager.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return

    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return

    if THEME_OLD not in text:
        raise RuntimeError(
            "ThemeManager.cpp does not contain the expected AiDetailsToggle rule. "
            "Has Sprint MOCKUP Pass 1 been applied? "
            "Run apply_sprint_mockup_pass1_asset_intelligence.py first."
        )

    backup_once(path)
    text = text.replace(THEME_OLD, THEME_NEW, 1)
    write_text(path, text)
    print(f"  Patched: {path.name}")


# ---------------------------------------------------------------------------
# 2. ImageGenerationPage.cpp — empty sub when not ready
# ---------------------------------------------------------------------------

CPP_OLD = (
    '        if (aiReadinessSub_)\n'
    '        {\n'
    '            QString sub;\n'
    '            if (selectedModelPath_.trimmed().isEmpty())\n'
    '            {\n'
    '                sub = QStringLiteral("Select a checkpoint to generate.");\n'
    '            }\n'
    '            else if (isVideoMode())\n'
    '            {\n'
    '                const QString backendLabel = hasVideoWorkflowBinding()\n'
    '                    ? QStringLiteral("imported workflow")\n'
    '                    : QStringLiteral("native");\n'
    '                sub = QStringLiteral("%1 \\u00B7 %2").arg(modelFamily, backendLabel);\n'
    '            }\n'
    '            else\n'
    '            {\n'
    '                sub = modelFamily;\n'
    '            }\n'
    '            aiReadinessSub_->setText(sub);\n'
    '        }\n'
)

CPP_NEW = (
    '        if (aiReadinessSub_)\n'
    '        {\n'
    f'            // --- {MARKER}: empty sub when not ready ---\n'
    '            // The headline already shows the block reason; leaving the\n'
    '            // sub empty avoids a duplicate-text overlap in the pill.\n'
    '            QString sub;\n'
    '            if (!ready)\n'
    '            {\n'
    '                sub.clear();\n'
    '            }\n'
    '            else if (isVideoMode())\n'
    '            {\n'
    '                const QString backendLabel = hasVideoWorkflowBinding()\n'
    '                    ? QStringLiteral("imported workflow")\n'
    '                    : QStringLiteral("native");\n'
    '                sub = QStringLiteral("%1 \\u00B7 %2").arg(modelFamily, backendLabel);\n'
    '            }\n'
    '            else\n'
    '            {\n'
    '                sub = modelFamily;\n'
    '            }\n'
    '            aiReadinessSub_->setText(sub);\n'
    f'            // --- END {MARKER} ---\n'
    '        }\n'
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
            "ImageGenerationPage.cpp does not contain the expected sub-text block. "
            "Has Sprint MOCKUP Pass 1 been applied? "
            "Run apply_sprint_mockup_pass1_asset_intelligence.py first."
        )

    backup_once(path)
    text = text.replace(CPP_OLD, CPP_NEW, 1)
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
