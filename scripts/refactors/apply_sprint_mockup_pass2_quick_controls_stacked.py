"""
SpellVision — Sprint MOCKUP Pass 1 CLEANUP + Pass 2: Quick Controls
stacked-label field cells.

Pass 1 left a small piece of dead code; Pass 2 swaps the Quick Controls
field cells from "label-left of field" to "label-stacked above field"
to match the target mockup.

CLEANUP (Pass 1 leftover)
-------------------------
ThemeManager.cpp had a QLabel#AiChip base rule. Pass 1 fixup 3 moved
all chips to distinct object names (AiChipSet / AiChipAuto), so the
base rule was never matched again. Delete it.

PASS 2 — Quick Controls stacked-label cells
-------------------------------------------
The Quick Controls card had each control rendered via the
`makeSettingsRow` lambda (label LEFT of field, ~62px label width).
That doesn't match the mockup's `field-label / input` stack.

This pass adds a sibling `makeStackedField` lambda alongside
makeSettingsRow (label ABOVE field, full width) and swaps the 12
Quick Controls call sites to it. Other cards (Output/Queue, Advanced,
LTX Launch Options) keep `makeSettingsRow` for now — they'll be
visited in Pass 3 when their cards get promoted to disclosures.

The card title also updates from "Generation Quick Controls" /
"Core generation controls stay here." to "Generation Controls" /
"Core generation controls." (matching the mockup's title; the longer
"Core controls stay visible. The rest collapses." sub goes in once
Pass 3 actually makes the rest collapse).

WHAT THIS DOESN'T TOUCH
-----------------------
- The adaptive responsive layout in `applyAdaptiveSplitterSizes()` is
  unchanged. Width|Height and Steps|CFG still pair side-by-side in
  wide mode via `configureAdaptivePair`. Other rows stack vertically
  via `configureStackedGroup`. The new stacked-label cells slot into
  this without changes.
- The `*Row` variables (aspectRow, samplerRow, etc.) keep their names
  even though they're now "stacked cells" semantically. Renaming
  isn't worth the churn.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "SPRINT MOCKUP PASS 2 QUICK CONTROLS STACKED"
CLEANUP_MARKER = "SPRINT MOCKUP PASS 1 CLEANUP"
BACKUP_SUFFIX = ".pre_sprint_mockup_pass2.bak"


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
# ThemeManager.cpp
#   - remove dead QLabel#AiChip base rule
#   - add QLabel#StackedFieldLabel rule
# ---------------------------------------------------------------------------

THEME_DEAD_AICHIP = (
    '        "QLabel#AiChip { background: %17; border: 1px solid %18; border-radius: 12px; padding: 2px 10px; color: %15; font-size: 11px; min-height: 18px; }"\n'
)

THEME_STACKED_LABEL_ANCHOR = (
    '        "QLabel#CompactFieldLabel { color: %14; font-size: 10px; font-weight: 800; background: transparent; }"\n'
)

THEME_STACKED_LABEL_INSERT = (
    f'        // --- {MARKER}: stacked-label field cells ---\n'
    '        "QLabel#StackedFieldLabel { color: %14; font-size: 11px; font-weight: 700; background: transparent; padding-bottom: 2px; }"\n'
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

    backup_once(path)

    # 1. Cleanup — remove dead AiChip base rule
    if THEME_DEAD_AICHIP in text:
        text = text.replace(THEME_DEAD_AICHIP, "", 1)
        print(f"  Removed dead AiChip base rule")

    # 2. Add the stacked-label selector
    if THEME_STACKED_LABEL_ANCHOR not in text:
        raise RuntimeError("Could not find CompactFieldLabel anchor in ThemeManager.cpp")
    text = text.replace(
        THEME_STACKED_LABEL_ANCHOR,
        THEME_STACKED_LABEL_ANCHOR + THEME_STACKED_LABEL_INSERT,
        1,
    )

    write_text(path, text)
    print(f"  Patched: {path.name}")


# ---------------------------------------------------------------------------
# ImageGenerationPage.cpp
#   - add makeStackedField lambda after makeSettingsRow
#   - swap quickControlsCard call sites to makeStackedField
#   - update card title + subtitle
# ---------------------------------------------------------------------------

LAMBDA_ANCHOR = '''    auto makeSettingsRow = [this](QWidget *parent, const QString &labelText, QWidget *field) -> QWidget * {
        auto *rowWidget = new QWidget(parent);
        rowWidget->setMinimumHeight(30);
        auto *rowLayout = new QHBoxLayout(rowWidget);
        rowLayout->setContentsMargins(0, 0, 0, 0);
        rowLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

        auto *label = new QLabel(labelText, rowWidget);
        label->setMinimumWidth(62);
        label->setMaximumWidth(78);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
        label->setObjectName(QStringLiteral("CompactFieldLabel"));
        label->setToolTip(labelText);

        field->setParent(rowWidget);
        field->setMinimumWidth(qMax(field->minimumWidth(), 120));
        field->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        rowLayout->addWidget(label);
        rowLayout->addWidget(field, 1);
        return rowWidget;
    };
'''

LAMBDA_INSERT = f'''
    // --- {MARKER}: label-above-field stacked cells (mockup pattern) ---
    auto makeStackedField = [this](QWidget *parent, const QString &labelText, QWidget *field) -> QWidget * {{
        auto *cellWidget = new QWidget(parent);
        cellWidget->setMinimumHeight(48);
        auto *cellLayout = new QVBoxLayout(cellWidget);
        cellLayout->setContentsMargins(0, 0, 0, 0);
        cellLayout->setSpacing(2);

        auto *label = new QLabel(labelText, cellWidget);
        label->setObjectName(QStringLiteral("StackedFieldLabel"));
        label->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        label->setToolTip(labelText);

        field->setParent(cellWidget);
        field->setMinimumWidth(qMax(field->minimumWidth(), 110));
        field->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        cellLayout->addWidget(label);
        cellLayout->addWidget(field);
        return cellWidget;
    }};
'''

# Quick Controls call-site rewrites — all 12 swap from makeSettingsRow
# to makeStackedField. Other cards (Output/Queue, Advanced, LTX) keep
# makeSettingsRow.
QUICK_CONTROLS_CALL_REWRITES = [
    ('QWidget *aspectRow = makeSettingsRow(quickControlsCard',
     'QWidget *aspectRow = makeStackedField(quickControlsCard'),
    ('QWidget *samplerRow = makeSettingsRow(quickControlsCard',
     'QWidget *samplerRow = makeStackedField(quickControlsCard'),
    ('QWidget *schedulerRow = makeSettingsRow(quickControlsCard',
     'QWidget *schedulerRow = makeStackedField(quickControlsCard'),
    ('QWidget *videoSamplerRow = makeSettingsRow(quickControlsCard',
     'QWidget *videoSamplerRow = makeStackedField(quickControlsCard'),
    ('QWidget *videoSchedulerRow = makeSettingsRow(quickControlsCard',
     'QWidget *videoSchedulerRow = makeStackedField(quickControlsCard'),
    ('QWidget *stepsRow = makeSettingsRow(quickControlsCard',
     'QWidget *stepsRow = makeStackedField(quickControlsCard'),
    ('QWidget *cfgRow = makeSettingsRow(quickControlsCard',
     'QWidget *cfgRow = makeStackedField(quickControlsCard'),
    ('QWidget *seedRow = makeSettingsRow(quickControlsCard',
     'QWidget *seedRow = makeStackedField(quickControlsCard'),
    ('QWidget *widthRow = makeSettingsRow(quickControlsCard',
     'QWidget *widthRow = makeStackedField(quickControlsCard'),
    ('QWidget *heightRow = makeSettingsRow(quickControlsCard',
     'QWidget *heightRow = makeStackedField(quickControlsCard'),
    ('QWidget *framesRow = makeSettingsRow(quickControlsCard',
     'QWidget *framesRow = makeStackedField(quickControlsCard'),
    ('QWidget *fpsRow = makeSettingsRow(quickControlsCard',
     'QWidget *fpsRow = makeStackedField(quickControlsCard'),
]

TITLE_OLD = (
    'quickControlsLayout->addWidget(createSectionTitle(QStringLiteral("Generation Quick Controls"), quickControlsCard));'
)
TITLE_NEW = (
    'quickControlsLayout->addWidget(createSectionTitle(QStringLiteral("Generation Controls"), quickControlsCard));'
)

SUBTITLE_OLD = (
    'auto *quickControlsHint = createSectionBody(QStringLiteral("Core generation controls stay here."), quickControlsCard);'
)
SUBTITLE_NEW = (
    'auto *quickControlsHint = createSectionBody(QStringLiteral("Core generation controls."), quickControlsCard);'
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

    # 1. Add makeStackedField lambda right after makeSettingsRow
    if LAMBDA_ANCHOR not in text:
        raise RuntimeError("Could not find makeSettingsRow lambda anchor in ImageGenerationPage.cpp")
    text = text.replace(LAMBDA_ANCHOR, LAMBDA_ANCHOR + LAMBDA_INSERT, 1)

    # 2. Swap 12 call sites for Quick Controls
    for old, new in QUICK_CONTROLS_CALL_REWRITES:
        if old not in text:
            raise RuntimeError(f"Could not find call-site anchor: {old!r}")
        text = text.replace(old, new, 1)

    # 3. Update card title
    if TITLE_OLD not in text:
        raise RuntimeError("Could not find Quick Controls title anchor")
    text = text.replace(TITLE_OLD, TITLE_NEW, 1)

    # 4. Update card subtitle
    if SUBTITLE_OLD not in text:
        raise RuntimeError("Could not find Quick Controls subtitle anchor")
    text = text.replace(SUBTITLE_OLD, SUBTITLE_NEW, 1)

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
