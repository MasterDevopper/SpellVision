"""
Spacing Tokens Phase 2, Patch 4/4: preview/transport spacing migration.

FINAL patch of the ImageGenerationPage spacing-token sprint. Migrates the
preview-area and video-transport spacing calls.

Needles built from the LIVE file (post Patches 1-3), confirmed via two
Select-String passes. The preview/transport set turned out smaller than
the original migration-map estimate: 8 spacing lines total, of which
only 4 need migrating --

  949  canvasLayout->setSpacing(8)            -> Tight  (pure rename, 0px)
  976  previewVideoLayout->setSpacing(6)      -> Tight  (6->8, +2px)
  992  previewTransportLayout->setContentsMargins(8, 6, 8, 6)
                                              -> (Tight, Tight, Tight, Tight)
                                                 (6->8 top/bottom: fixes
                                                  asymmetric padding)
  993  previewTransportLayout->setSpacing(8)  -> Tight  (pure rename, 0px)

Excluded, by design:
  - 948  canvasLayout->setContentsMargins(...) -- already migrated to
    Spacing::Card in Patch 1; not touched here.
  - 957/958  previewImageLayout margins(0,0,0,0) + spacing(0)  -- literal
    0 stays literal 0 per the established convention.
  - 975  previewVideoLayout->setContentsMargins(0,0,0,0)  -- literal 0.

Net visual change: previewVideoLayout gains 2px between its stacked
elements; the video transport bar's vertical padding goes 6->8 to match
its horizontal padding (was 8,6,8,6 -- asymmetric; now 8,8,8,8). The two
canvasLayout/previewTransportLayout setSpacing calls were already 8, so
those are pure vocabulary with zero pixel change.

Each call anchored on the unique `auto *<name> = new ...Layout(...)`
line above it, except canvasLayout->setSpacing which anchors on the
(already-migrated, Patch 1) canvasLayout->setContentsMargins line
directly above it. Count assertion: exactly 4 substitutions or abort.

After this patch lands and builds clean, the ImageGenerationPage
spacing-token migration is COMPLETE: all non-conditional spacing calls
in buildUi consume ThemeManager tokens; the 3 adaptive-mode ternary
calls remain literal by design.
"""
from pathlib import Path
path = Path("qt_ui/ImageGenerationPage.cpp")
text = path.read_text(encoding="utf-8")

TIGHT = "ThemeManager::instance().spacing(ThemeManager::Spacing::Tight)"

# canvasLayout->setSpacing: anchor on the already-migrated (Patch 1)
# canvasLayout->setContentsMargins line. That line is long; we match it
# by its stable, unique prefix + the setSpacing line below it. To stay
# robust against the long Card-token margins line, we anchor instead on
# the setSpacing line's own uniqueness: `canvasLayout->setSpacing(8);`
# appears exactly once in the file. Same for previewTransportLayout's
# setSpacing(8) -- but that one is NOT unique on its own text if other
# layouts also use setSpacing(8). So we anchor each on the `= new` decl
# where one exists, and handle canvasLayout->setSpacing specially.

applied = 0
problems = []

def try_apply(needle, replacement, label):
    global text, applied
    for nl in ("\r\n", "\n"):
        n = needle.replace("\n", nl)
        r = replacement.replace("\n", nl)
        if n in text:
            text = text.replace(n, r, 1)
            applied += 1
            return True
    return False

# 1. canvasLayout->setSpacing(8) -> Tight.
#    `canvasLayout->setSpacing(8);` -- check uniqueness, then replace.
canvas_old = "    canvasLayout->setSpacing(8);"
canvas_new = f"    canvasLayout->setSpacing({TIGHT});"
if text.count(canvas_old) == 1:
    text = text.replace(canvas_old, canvas_new, 1)
    applied += 1
else:
    problems.append(f"canvasLayout->setSpacing (found {text.count(canvas_old)}x, need 1)")

# 2. previewVideoLayout->setSpacing(6) -> Tight.
#    Anchored on its `= new QVBoxLayout` decl + the margins line between.
if not try_apply(
    "    auto *previewVideoLayout = new QVBoxLayout(previewVideoPage_);\n"
    "    previewVideoLayout->setContentsMargins(0, 0, 0, 0);\n"
    "    previewVideoLayout->setSpacing(6);",
    "    auto *previewVideoLayout = new QVBoxLayout(previewVideoPage_);\n"
    "    previewVideoLayout->setContentsMargins(0, 0, 0, 0);\n"
    f"    previewVideoLayout->setSpacing({TIGHT});",
    "previewVideoLayout->setSpacing 6 -> Tight"):
    problems.append("previewVideoLayout->setSpacing 6 -> Tight")

# 3 + 4. previewTransportLayout margins (8,6,8,6) -> Tight x4, AND
#        previewTransportLayout->setSpacing(8) -> Tight.
#        Both anchored together on the `= new QHBoxLayout` decl so the
#        3-line block is unique and both lines migrate in one go.
if not try_apply(
    "    auto *previewTransportLayout = new QHBoxLayout(previewVideoTransportBar_);\n"
    "    previewTransportLayout->setContentsMargins(8, 6, 8, 6);\n"
    "    previewTransportLayout->setSpacing(8);",
    "    auto *previewTransportLayout = new QHBoxLayout(previewVideoTransportBar_);\n"
    f"    previewTransportLayout->setContentsMargins({TIGHT}, {TIGHT}, {TIGHT}, {TIGHT});\n"
    f"    previewTransportLayout->setSpacing({TIGHT});",
    "previewTransportLayout margins+spacing -> Tight"):
    problems.append("previewTransportLayout margins+spacing -> Tight")
else:
    # that single block replacement covered 2 logical calls
    applied += 1  # count the second logical call

if problems:
    raise SystemExit(
        "Patch 4 could not match these calls: " + "; ".join(problems)
        + ". No changes written. Re-run Select-String on the live file and compare."
    )

if applied != 4:
    raise SystemExit(
        f"Patch 4 expected 4 substitutions but counted {applied}. "
        "Aborting without write as a safety measure."
    )

path.write_text(text, encoding="utf-8")
print(f"Applied Spacing Tokens Phase 2 Patch 4/4: {applied} preview/transport spacing calls migrated to tokens.")
print("ImageGenerationPage spacing-token migration COMPLETE.")
