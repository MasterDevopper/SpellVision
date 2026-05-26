"""
Spacing Tokens Phase 2, Patch 2/4: inter-card & root spacing migration.

(Note: the sprint is now 4 patches, not 5. The originally-planned
"zero-margin rows" patch was dropped -- literal 0 is already the
clearest form and does not get tokenized. Patch numbering here reflects
the 4-patch plan: 1 card padding [done], 2 inter-card/root [this],
3 control sub-grids, 4 preview/transport.)

Migrates the 6 structural spacing calls in ImageGenerationPage::buildUi
-- the page-edge margins and the spacing BETWEEN cards / rails, as
opposed to padding inside cards (Patch 1).

The 6 calls, 3 layouts:

  root (the page's outer QVBoxLayout):
    498  setContentsMargins(10, 8, 10, 10) -> (Snug, Tight, Snug, Snug)
         CHANGES: 10->12 on left/right/bottom (+2px page edge). The 8
         (top) is already on-scale -> Tight, pure rename.
    499  setSpacing(10)                    -> Snug
         CHANGES: 10->12 between the 3 columns (+2px).

  leftLayout (the left rail's container layout):
    518  setContentsMargins(0, 0, 4, 0)    -> (0, 0, Hairline, 0)
         Pure rename. 0 stays literal 0; 4 is on-scale -> Hairline.
    519  setSpacing(8)                     -> Tight
         Pure rename.

  rightLayout (the right rail's container layout):
    1190 setContentsMargins(4, 0, 0, 0)    -> (Hairline, 0, 0, 0)
         Pure rename. 4 -> Hairline, zeros stay literal.
    1191 setSpacing(12)                    -> Snug
         Pure rename.

Net visual change: only root's 10->12 values move anything -- the page
gains 2px of outer margin on three sides and 2px between columns. The
other 4 calls are pure vocabulary. Per the established convention,
literal 0 is left as 0 (clearest form; not on the spacing scale).

Each call is anchored on the unique `auto *<name> = new QVBoxLayout(...)`
line above it. Count assertion: exactly 6 substitutions or abort.
"""
from pathlib import Path
path = Path("qt_ui/ImageGenerationPage.cpp")
text = path.read_text(encoding="utf-8")

TM = "ThemeManager::instance()"
HAIR = f"{TM}.spacing(ThemeManager::Spacing::Hairline)"
TIGHT = f"{TM}.spacing(ThemeManager::Spacing::Tight)"
SNUG = f"{TM}.spacing(ThemeManager::Spacing::Snug)"

# (anchor, old_call, new_call, label)
migrations = [
    ("    auto *root = new QVBoxLayout(this);",
     "    root->setContentsMargins(10, 8, 10, 10);",
     f"    root->setContentsMargins({SNUG}, {TIGHT}, {SNUG}, {SNUG});",
     "root margins 10,8 -> Snug,Tight (+2px L/R/bottom)"),

    ("    root->setContentsMargins(10, 8, 10, 10);",
     "    root->setSpacing(10);",
     f"    root->setSpacing({SNUG});",
     "root spacing 10 -> Snug (+2px between columns)"),

    ("    auto *leftLayout = new QVBoxLayout(leftContainer);",
     "    leftLayout->setContentsMargins(0, 0, 4, 0);",
     f"    leftLayout->setContentsMargins(0, 0, {HAIR}, 0);",
     "leftLayout margins 0,0,4,0 -> Hairline (pure rename)"),

    ("    leftLayout->setContentsMargins(0, 0, 4, 0);",
     "    leftLayout->setSpacing(8);",
     f"    leftLayout->setSpacing({TIGHT});",
     "leftLayout spacing 8 -> Tight (pure rename)"),

    ("    auto *rightLayout = new QVBoxLayout(rightContainer);",
     "    rightLayout->setContentsMargins(4, 0, 0, 0);",
     f"    rightLayout->setContentsMargins({HAIR}, 0, 0, 0);",
     "rightLayout margins 4,0,0,0 -> Hairline (pure rename)"),

    ("    rightLayout->setContentsMargins(4, 0, 0, 0);",
     "    rightLayout->setSpacing(12);",
     f"    rightLayout->setSpacing({SNUG});",
     "rightLayout spacing 12 -> Snug (pure rename)"),
]

# IMPORTANT: two pairs here use the OLD form of a preceding line as the
# anchor for the next call (e.g. root's margins line anchors root's
# spacing line). So substitutions must run in order, and once the
# margins line is rewritten, the spacing line's anchor is gone. To keep
# anchors stable we match each (anchor + old_call) as a single block in
# the ORIGINAL order, but because replacing call N changes the text that
# call N+1 anchors on, we instead anchor every call on its own
# `auto *... = new` declaration OR on the still-original text. To avoid
# that fragility entirely, we match the full 2-line block per call where
# the anchor is the line *above*, and we process in file order so the
# anchor line is always still in its original form when we reach it.
#
# Concretely: call 1 anchors on `auto *root = new` (never changes).
# call 2 anchors on root's *margins* line -- which call 1 just rewrote.
# So call 2's anchor must be the NEW margins line. We handle this by
# threading the replacement: after call 1, the margins line is the new
# token form, so call 2's needle uses that. Build needles dynamically.

applied = 0
problems = []

# Process with awareness that an earlier replacement may have changed
# the anchor text of a later call. We rebuild each needle against the
# CURRENT text state.
def try_apply(anchor, old_call, new_call, label):
    global text, applied
    for nl in ("\r\n", "\n"):
        needle = anchor + nl + old_call
        replacement = anchor + nl + new_call
        if needle in text:
            text = text.replace(needle, replacement, 1)
            applied += 1
            return True
    return False

# Call 1: root margins. Anchor = `auto *root = new` (stable).
if not try_apply(*migrations[0][:3], migrations[0][3]):
    problems.append(migrations[0][3])

# Call 2: root spacing. Its original anchor was the OLD margins line,
# which call 1 just rewrote. Re-anchor on the NEW margins line.
new_root_margins = f"    root->setContentsMargins({SNUG}, {TIGHT}, {SNUG}, {SNUG});"
if not try_apply(new_root_margins,
                 "    root->setSpacing(10);",
                 f"    root->setSpacing({SNUG});",
                 migrations[1][3]):
    problems.append(migrations[1][3])

# Call 3: leftLayout margins. Anchor = `auto *leftLayout = new` (stable).
if not try_apply(*migrations[2][:3], migrations[2][3]):
    problems.append(migrations[2][3])

# Call 4: leftLayout spacing. Original anchor = OLD leftLayout margins
# line, just rewritten. Re-anchor on the NEW one.
new_left_margins = f"    leftLayout->setContentsMargins(0, 0, {HAIR}, 0);"
if not try_apply(new_left_margins,
                 "    leftLayout->setSpacing(8);",
                 f"    leftLayout->setSpacing({TIGHT});",
                 migrations[3][3]):
    problems.append(migrations[3][3])

# Call 5: rightLayout margins. Anchor = `auto *rightLayout = new` (stable).
if not try_apply(*migrations[4][:3], migrations[4][3]):
    problems.append(migrations[4][3])

# Call 6: rightLayout spacing. Re-anchor on NEW rightLayout margins line.
new_right_margins = f"    rightLayout->setContentsMargins({HAIR}, 0, 0, 0);"
if not try_apply(new_right_margins,
                 "    rightLayout->setSpacing(12);",
                 f"    rightLayout->setSpacing({SNUG});",
                 migrations[5][3]):
    problems.append(migrations[5][3])

if problems:
    raise SystemExit(
        "Patch 2 could not match these calls: " + "; ".join(problems)
        + ". No changes written. The file may differ from the mapped version."
    )

if applied != 6:
    raise SystemExit(
        f"Patch 2 expected 6 substitutions but made {applied}. "
        "Aborting without write as a safety measure."
    )

path.write_text(text, encoding="utf-8")
print(f"Applied Spacing Tokens Phase 2 Patch 2/4: {applied} inter-card/root spacing calls migrated to tokens.")
