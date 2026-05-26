"""
MainWindow Spacing Tokens, Patch 3/3: details-panel cards (FINAL region).

Last of three region patches. Needles built from the LIVE file,
confirmed via two Select-String passes. Completes the MainWindow.cpp
spacing-token migration.

Region contents -- five layout blocks, all migrate, 10 calls total:

  2471-2473  layout (DetailsPane root QVBoxLayout)
       setContentsMargins(12,12,12,12) -> (Snug, Snug, Snug, Snug)
       setSpacing(12)                   -> Snug   (pure rename)

  2476-2478  summaryLayout (QVBoxLayout on DetailsSummaryCard)
       setContentsMargins(12,12,12,12) -> (Snug, Snug, Snug, Snug)
       setSpacing(8)                    -> Tight  (pure rename)

  2519-2521  actionLayout (QVBoxLayout on DetailsActionCard)
       setContentsMargins(12,12,12,12) -> (Snug, Snug, Snug, Snug)
       setSpacing(8)                    -> Tight  (pure rename)

  2551-2553  layout (LogsPane root QVBoxLayout)
       setContentsMargins(12,12,12,12) -> (Snug, Snug, Snug, Snug)
       setSpacing(10)                   -> Snug   (10 -> 12 snap)

  2556-2558  cardLayout (QVBoxLayout on ExecutionLogCard)
       setContentsMargins(12,12,12,12) -> (Snug, Snug, Snug, Snug)
       setSpacing(8)                    -> Tight  (pure rename)

Total: 10 calls migrate. 8 pure renames (12->Snug margins, 12->Snug and
8->Tight spacing), 2 snaps (the LogsPane root's 10->12). Net visual is
near-invisible -- almost everything was already on-scale; only the
LogsPane root's inter-card spacing nudges +2px.

Anchoring: the two generic `layout` blocks BOTH have
`auto *layout = new QVBoxLayout(root);` + `setContentsMargins(12,12,12,12)`
-- identical on those two lines. They are disambiguated by the third
line: DetailsPane root ends in setSpacing(12), LogsPane root ends in
setSpacing(10). So each full 3-line needle is unique. (Same technique as
Patch 2's two generic `layout` blocks.)

Count assertion: exactly 5 block replacements or abort.

After this patch builds clean, MainWindow.cpp spacing-token migration is
COMPLETE -- and together with the finished ImageGenerationPage sprint,
the two largest "every page invents its own margins" files both now
consume the ThemeManager token scale.
"""
from pathlib import Path
path = Path("qt_ui/MainWindow.cpp")
text = path.read_text(encoding="utf-8")

SNUG = "ThemeManager::instance().spacing(ThemeManager::Spacing::Snug)"
TIGHT = "ThemeManager::instance().spacing(ThemeManager::Spacing::Tight)"

# (label, needle_block, replacement_block)
blocks = [
    (
        "DetailsPane root layout (setSpacing 12)",
        "    auto *layout = new QVBoxLayout(root);\n"
        "    layout->setContentsMargins(12, 12, 12, 12);\n"
        "    layout->setSpacing(12);",
        "    auto *layout = new QVBoxLayout(root);\n"
        f"    layout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});\n"
        f"    layout->setSpacing({SNUG});",
    ),
    (
        "summaryLayout",
        "    auto *summaryLayout = new QVBoxLayout(summaryCard);\n"
        "    summaryLayout->setContentsMargins(12, 12, 12, 12);\n"
        "    summaryLayout->setSpacing(8);",
        "    auto *summaryLayout = new QVBoxLayout(summaryCard);\n"
        f"    summaryLayout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});\n"
        f"    summaryLayout->setSpacing({TIGHT});",
    ),
    (
        "actionLayout",
        "    auto *actionLayout = new QVBoxLayout(actionCard);\n"
        "    actionLayout->setContentsMargins(12, 12, 12, 12);\n"
        "    actionLayout->setSpacing(8);",
        "    auto *actionLayout = new QVBoxLayout(actionCard);\n"
        f"    actionLayout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});\n"
        f"    actionLayout->setSpacing({TIGHT});",
    ),
    (
        "LogsPane root layout (setSpacing 10 -> Snug)",
        "    auto *layout = new QVBoxLayout(root);\n"
        "    layout->setContentsMargins(12, 12, 12, 12);\n"
        "    layout->setSpacing(10);",
        "    auto *layout = new QVBoxLayout(root);\n"
        f"    layout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});\n"
        f"    layout->setSpacing({SNUG});",
    ),
    (
        "cardLayout",
        "    auto *cardLayout = new QVBoxLayout(card);\n"
        "    cardLayout->setContentsMargins(12, 12, 12, 12);\n"
        "    cardLayout->setSpacing(8);",
        "    auto *cardLayout = new QVBoxLayout(card);\n"
        f"    cardLayout->setContentsMargins({SNUG}, {SNUG}, {SNUG}, {SNUG});\n"
        f"    cardLayout->setSpacing({TIGHT});",
    ),
]

applied = 0
problems = []
for label, needle, replacement in blocks:
    matched = False
    for nl in ("\r\n", "\n"):
        n = needle.replace("\n", nl)
        r = replacement.replace("\n", nl)
        if n in text:
            cnt = text.count(n)
            if cnt != 1:
                problems.append(f"{label} (block appears {cnt}x, need 1)")
                matched = True
                break
            text = text.replace(n, r, 1)
            applied += 1
            matched = True
            break
    if not matched:
        problems.append(f"{label} (no match)")

if problems:
    raise SystemExit(
        "Patch 3 had problems: " + "; ".join(problems)
        + ". No changes written (or partial -- check count). Re-run Select-String "
        "on the live file and compare."
    )

if applied != 5:
    raise SystemExit(
        f"Patch 3 expected 5 block replacements but made {applied}. "
        "Aborting without write as a safety measure."
    )

path.write_text(text, encoding="utf-8")
print(f"Applied MainWindow Spacing Tokens Patch 3/3: details-panel cards "
      f"({applied} blocks, 10 logical calls) migrated to tokens.")
print("MainWindow.cpp spacing-token migration COMPLETE.")
