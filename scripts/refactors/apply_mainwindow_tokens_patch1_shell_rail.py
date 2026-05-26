"""
MainWindow Spacing Tokens, Patch 1/3: shell/rail region.

First of three region patches migrating MainWindow.cpp spacing literals
to ThemeManager tokens, mirroring the completed ImageGenerationPage
sprint. Region split: 1) shell/rail [this], 2) bottom-utility/queue,
3) details-panel cards.

Needle built from the LIVE file, confirmed via Select-String. The
shell/rail region has exactly one migrating pair -- the side-rail's
outer QVBoxLayout in createSideRail():

  layout->setContentsMargins(10, 14, 10, 14) -> (Snug, Card, Snug, Card)
       10 -> 12 (Snug) on left/right; 14 -> 16 (Card) on top/bottom.
  layout->setSpacing(10)                     -> Snug   (10 -> 12)

Both snap upward to the clean scale. Net visual: the rail's inner
padding gains 2px each side, and the gap between rail buttons goes
10 -> 12px.

NOT touched: shellLayout's setContentsMargins(0,0,0,0) + setSpacing(0)
earlier in buildShell() -- literal 0 stays literal 0 per the
established convention.

The generic name `layout` is reused for five different layouts across
MainWindow.cpp, so the needle is anchored on the unique 3-line block:
the `auto *layout = new QVBoxLayout(rail);` declaration (unique -- it is
the only `layout` bound to `rail`) plus the two calls below it.

ThemeManager.h is already included in MainWindow.cpp (ThemeManager::
instance() is used in buildShell's applyTheme lambda), so no new include
is needed.
"""
from pathlib import Path
path = Path("qt_ui/MainWindow.cpp")
text = path.read_text(encoding="utf-8")

SNUG = "ThemeManager::instance().spacing(ThemeManager::Spacing::Snug)"
CARD = "ThemeManager::instance().spacing(ThemeManager::Spacing::Card)"

# 3-line block: declaration anchor + the two migrating calls.
needle = (
    "    auto *layout = new QVBoxLayout(rail);\n"
    "    layout->setContentsMargins(10, 14, 10, 14);\n"
    "    layout->setSpacing(10);"
)
replacement = (
    "    auto *layout = new QVBoxLayout(rail);\n"
    f"    layout->setContentsMargins({SNUG}, {CARD}, {SNUG}, {CARD});\n"
    f"    layout->setSpacing({SNUG});"
)

applied = False
for nl in ("\r\n", "\n"):
    n = needle.replace("\n", nl)
    r = replacement.replace("\n", nl)
    if n in text:
        if text.count(n) != 1:
            raise SystemExit(
                f"Patch 1 anchor block appears {text.count(n)}x, need exactly 1. "
                "Aborting without write."
            )
        text = text.replace(n, r, 1)
        applied = True
        break

if not applied:
    raise SystemExit(
        "Patch 1 could not match the shell/rail layout block. No changes written. "
        "Re-run Select-String on the live file and compare."
    )

path.write_text(text, encoding="utf-8")
print("Applied MainWindow Spacing Tokens Patch 1/3: shell/rail region (1 layout pair) migrated to tokens.")
