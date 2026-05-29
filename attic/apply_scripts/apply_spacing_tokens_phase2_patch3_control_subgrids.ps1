$patch = @'
"""
Spacing Tokens Phase 2, Patch 3/4: control sub-grid spacing migration.

Migrates the 5 setSpacing calls on the in-card control sub-grids in
ImageGenerationPage::buildUi -- the paired-control rows in the
Generation Quick Controls card (sampler/scheduler, steps/cfg,
seed/batch, width/height) plus the generic rowLayout.

Needles built from the LIVE file (post Patch 1 + Patch 2), confirmed via
Select-String. All 5 target lines are still in literal form -- Patches 1
and 2 did not touch the control sub-grids.

The 5 setSpacing calls:

  1528  rowLayout->setSpacing(7)                -> Tight   (7->8,  +1px)
  1608  samplerSchedulerLayout_->setSpacing(6)  -> Tight   (6->8,  +2px)
  1617  stepsCfgLayout_->setSpacing(6)          -> Tight   (6->8,  +2px)
  1623  seedBatchLayout_->setSpacing(6)         -> Tight   (6->8,  +2px)
  1630  sizeLayout_->setSpacing(6)              -> Tight   (6->8,  +2px)

Net visual change: the four paired-control grids in Generation Quick
Controls gain 2px of vertical gap between their stacked rows; rowLayout
gains 1px. All snaps move toward the clean scale (6 and 7 were both
off-scale; Tight = 8 is the nearest scale value).

NOT in this patch: the 5 companion setContentsMargins(0, 0, 0, 0) calls
on these same layouts. Per the established convention, literal 0 stays
literal 0 -- it is already the clearest form and is not on the spacing
scale. Patch 3 therefore touches only the 5 setSpacing lines.

Each call is anchored on the unique `<name> = new QBoxLayout(...)` or
`new QHBoxLayout(...)` line above it (rowLayout uses QHBoxLayout; the
four sub-grids use QBoxLayout). The setContentsMargins line sits between
the anchor and the setSpacing line, so each needle spans 3 lines:
anchor + margins line + spacing line, with only the spacing line
changing. Count assertion: exactly 5 substitutions or abort.
"""
from pathlib import Path
path = Path("qt_ui/ImageGenerationPage.cpp")
text = path.read_text(encoding="utf-8")

TIGHT = "ThemeManager::instance().spacing(ThemeManager::Spacing::Tight)"

# Each entry: (anchor_line, margins_line, old_spacing_line, new_spacing_line, label)
# The 3-line needle (anchor + margins + spacing) is unique per call
# because the anchor `= new ...Layout` line names the specific layout.
migrations = [
    ("        auto *rowLayout = new QHBoxLayout(rowWidget);",
     "        rowLayout->setContentsMargins(0, 0, 0, 0);",
     "        rowLayout->setSpacing(7);",
     f"        rowLayout->setSpacing({TIGHT});",
     "rowLayout 7 -> Tight (+1px)"),

    ("    samplerSchedulerLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);",
     "    samplerSchedulerLayout_->setContentsMargins(0, 0, 0, 0);",
     "    samplerSchedulerLayout_->setSpacing(6);",
     f"    samplerSchedulerLayout_->setSpacing({TIGHT});",
     "samplerSchedulerLayout_ 6 -> Tight (+2px)"),

    ("    stepsCfgLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);",
     "    stepsCfgLayout_->setContentsMargins(0, 0, 0, 0);",
     "    stepsCfgLayout_->setSpacing(6);",
     f"    stepsCfgLayout_->setSpacing({TIGHT});",
     "stepsCfgLayout_ 6 -> Tight (+2px)"),

    ("    seedBatchLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);",
     "    seedBatchLayout_->setContentsMargins(0, 0, 0, 0);",
     "    seedBatchLayout_->setSpacing(6);",
     f"    seedBatchLayout_->setSpacing({TIGHT});",
     "seedBatchLayout_ 6 -> Tight (+2px)"),

    ("    sizeLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);",
     "    sizeLayout_->setContentsMargins(0, 0, 0, 0);",
     "    sizeLayout_->setSpacing(6);",
     f"    sizeLayout_->setSpacing({TIGHT});",
     "sizeLayout_ 6 -> Tight (+2px)"),
]

applied = 0
problems = []
for anchor, margins, old_spacing, new_spacing, label in migrations:
    matched = False
    for nl in ("\r\n", "\n"):
        needle = anchor + nl + margins + nl + old_spacing
        replacement = anchor + nl + margins + nl + new_spacing
        if needle in text:
            text = text.replace(needle, replacement, 1)
            applied += 1
            matched = True
            break
    if not matched:
        problems.append(label)

if problems:
    raise SystemExit(
        "Patch 3 could not match these calls: " + "; ".join(problems)
        + ". No changes written. Re-run Select-String on the live file and "
        "compare -- the file may have drifted from the mapped version."
    )

if applied != 5:
    raise SystemExit(
        f"Patch 3 expected 5 substitutions but made {applied}. "
        "Aborting without write as a safety measure."
    )

path.write_text(text, encoding="utf-8")
print(f"Applied Spacing Tokens Phase 2 Patch 3/4: {applied} control sub-grid spacing calls migrated to tokens.")
'@
Set-Content .\scripts\refactors\apply_spacing_tokens_phase2_patch3_control_subgrids.py $patch -Encoding UTF8
.\.venv\Scripts\python.exe .\scripts\refactors\apply_spacing_tokens_phase2_patch3_control_subgrids.py
