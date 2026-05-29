$patch = @'
"""
Spacing Tokens Phase 2, Patch 1/5: card-content padding migration.

Migrates the ~10 card-content setContentsMargins calls in
ImageGenerationPage::buildUi to consume ThemeManager spacing tokens
instead of literal pixel values. These are the calls that define each
card's internal padding -- the most visible spacing on the page.

Scope of THIS patch (card padding only):
  - 7 calls already at 12,12,12,12  -> Spacing::Snug   (pure rename, 0px change)
  - 2 calls at 10,10,10,10          -> Spacing::Snug   (+2px each side: snap)
  - 1 call  at 16,16,16,16          -> Spacing::Card   (pure rename, 0px change)
  - 1 call  at 16,14,16,14          -> Spacing::Card   (+2px top/bottom: fixes
                                                        asymmetric padding)

Not in this patch: zero-margin rows (Patch 2), inter-card/root spacing
(Patch 3), control sub-grids (Patch 4), preview/transport (Patch 5),
and the 3 conditional ternary calls (left literal for now).

Each card-padding call shares identical setContentsMargins text with
others, so every needle is anchored on the UNIQUE `auto *<name>Layout =
new ...` line directly above it. A substitution count assertion at the
end aborts the write if anything other than exactly 10 replacements
landed.

ThemeManager.h is already #included and ThemeManager::instance() is
already used in buildUi, so no new includes are needed.
"""
from pathlib import Path
path = Path("qt_ui/ImageGenerationPage.cpp")
text = path.read_text(encoding="utf-8")

# Each entry: (anchor_line, old_margins_call, new_token_call)
# The anchor line makes the two-line needle unique even when the
# setContentsMargins text is identical across cards.
TM = "ThemeManager::instance()"
SNUG = f"{TM}.spacing(ThemeManager::Spacing::Snug)"
CARD = f"{TM}.spacing(ThemeManager::Spacing::Card)"

migrations = [
    # (unique anchor, old call, new call, label)
    ("    auto *familyLayout = new QVBoxLayout(videoFamilyCard_);",
     "        familyLayout->setContentsMargins(12, 12, 12, 12);",
     f"        familyLayout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});",
     "familyLayout 12->Snug"),

    ("    auto *promptLayout = new QVBoxLayout(promptCard);",
     "    promptLayout->setContentsMargins(12, 12, 12, 12);",
     f"    promptLayout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});",
     "promptLayout 12->Snug"),

    ("    auto *inputLayout = new QVBoxLayout(inputCard_);",
     "    inputLayout->setContentsMargins(12, 12, 12, 12);",
     f"    inputLayout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});",
     "inputLayout 12->Snug"),

    ("    auto *quickControlsLayout = new QVBoxLayout(quickControlsCard);",
     "    quickControlsLayout->setContentsMargins(12, 12, 12, 12);",
     f"    quickControlsLayout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});",
     "quickControlsLayout 12->Snug"),

    ("    auto *ltxLaunchLayout = new QVBoxLayout(ltxLaunchOptionsPanel_);",
     "    ltxLaunchLayout->setContentsMargins(10, 10, 10, 10);",
     f"    ltxLaunchLayout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});",
     "ltxLaunchLayout 10->Snug (+2px snap)"),

    ("    auto *outputQueueLayout = new QVBoxLayout(outputQueueCard);",
     "    outputQueueLayout->setContentsMargins(12, 12, 12, 12);",
     f"    outputQueueLayout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});",
     "outputQueueLayout 12->Snug"),

    ("    auto *advancedLayout = new QVBoxLayout(advancedCard);",
     "    advancedLayout->setContentsMargins(12, 12, 12, 12);",
     f"    advancedLayout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});",
     "advancedLayout 12->Snug"),

    ("    auto *canvasLayout = new QVBoxLayout(canvasCard);",
     "    canvasLayout->setContentsMargins(16, 14, 16, 14);",
     f"    canvasLayout->setContentsMargins({CARD}, {CARD}, {CARD}, {CARD});",
     "canvasLayout 16,14->Card (fixes asymmetric pad)"),

    ("    auto *stackCardLayout = new QVBoxLayout(stackCard_);",
     "    stackCardLayout->setContentsMargins(16, 16, 16, 16);",
     f"    stackCardLayout->setContentsMargins({CARD}, {CARD}, {CARD}, {CARD});",
     "stackCardLayout 16->Card"),

    ("    auto *settingsCardLayout = new QVBoxLayout(settingsCard_);",
     "    settingsCardLayout->setContentsMargins(12, 12, 12, 12);",
     f"    settingsCardLayout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});",
     "settingsCardLayout 12->Snug"),
]

applied = 0
problems = []
for anchor, old_call, new_call, label in migrations:
    needle = anchor + "\r\n" + old_call
    replacement = anchor + "\r\n" + new_call
    if needle in text:
        text = text.replace(needle, replacement, 1)
        applied += 1
    else:
        # Try LF-only line endings as a fallback before declaring failure.
        needle_lf = anchor + "\n" + old_call
        replacement_lf = anchor + "\n" + new_call
        if needle_lf in text:
            text = text.replace(needle_lf, replacement_lf, 1)
            applied += 1
        else:
            problems.append(label)

if problems:
    raise SystemExit(
        "Patch 1 could not match these card-padding calls: "
        + "; ".join(problems)
        + ". No changes written. The file may differ from the mapped version."
    )

if applied != 10:
    raise SystemExit(
        f"Patch 1 expected 10 substitutions but made {applied}. "
        "Aborting without write as a safety measure."
    )

path.write_text(text, encoding="utf-8")
print(f"Applied Spacing Tokens Phase 2 Patch 1/5: {applied} card-padding calls migrated to tokens.")
'@
Set-Content .\scripts\refactors\apply_spacing_tokens_phase2_patch1_card_padding.py $patch -Encoding UTF8
.\.venv\Scripts\python.exe .\scripts\refactors\apply_spacing_tokens_phase2_patch1_card_padding.py
