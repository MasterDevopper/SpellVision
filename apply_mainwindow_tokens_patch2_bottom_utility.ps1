$patch = @'
"""
MainWindow Spacing Tokens, Patch 2/3: bottom-utility/queue region.

Second of three region patches. Needles built from the LIVE file,
confirmed via two Select-String passes (named layouts + generic
`layout` declarations in the 1840-2410 range).

Region contents -- six layout blocks, of which 7 individual calls
migrate:

  1859-1861  layout (BottomUtilityRoot QVBoxLayout)
       setContentsMargins(0,0,0,0) + setSpacing(0)
       -> NEITHER migrates. literal 0 stays literal 0. (block left
          entirely untouched; listed here for completeness.)

  1864-1866  headerLayout (QHBoxLayout on bottomUtilityHeaderBar_)
       setContentsMargins(8,4,8,4) -> (Tight, Hairline, Tight, Hairline)
            pure rename: 8->Tight, 4->Hairline, both on-scale.
       setSpacing(6)                -> Tight   (6 -> 8 snap)

  1909-1911  expandedLayout (QHBoxLayout on queueExpandedContent_)
       setContentsMargins(8,4,8,8) -> (Tight, Hairline, Tight, Tight)
            pure rename: 8->Tight, 4->Hairline.
       setSpacing(8)                -> Tight   (pure rename)

  2361-2363  layout (QueuePaneRoot QVBoxLayout)
       setContentsMargins(0,0,0,0)  -> stays literal 0 (untouched)
       setSpacing(10)               -> Snug    (10 -> 12 snap)

  2367-2369  activeLayout (QVBoxLayout on activeStrip)
       setContentsMargins(8,6,8,6) -> (Tight, Tight, Tight, Tight)
            6 -> 8 snap on top/bottom; fixes asymmetric padding.
       setSpacing(3)                -> stays literal 3. off-scale and
            deliberately tight (activeStrip is a fixed 78px-high strip);
            same treatment as the adaptive ternary calls in
            ImageGenerationPage -- not snapped.

  2402-2404  filtersLayout (QHBoxLayout)
       setContentsMargins(0,0,0,0)  -> stays literal 0 (untouched)
       setSpacing(6)                -> Tight   (6 -> 8 snap)

Total: 7 calls migrate. 2 pure renames, 5 snaps (four 6->8, one
10->12). The two literal-0 blocks and the deliberate setSpacing(3)
are left exactly as-is.

Anchoring: the two generic `layout` blocks both begin with
`auto *layout = new QVBoxLayout(root);` -- NOT unique on that line
alone. But the full 3-line block differs (one is 0,0,0,0 + spacing(0);
the other is 0,0,0,0 + spacing(10)), so each 3-line needle is unique.
The QueuePaneRoot block is the only one of the two that migrates (its
spacing(10)); the BottomUtilityRoot block is not touched at all.

Count assertion: exactly 5 block replacements (headerLayout,
expandedLayout, QueuePaneRoot-layout, activeLayout, filtersLayout) ->
covering 7 logical call changes. Aborts if any block fails to match.
"""
from pathlib import Path
path = Path("qt_ui/MainWindow.cpp")
text = path.read_text(encoding="utf-8")

TM = "ThemeManager::instance()"
HAIR = f"{TM}.spacing(ThemeManager::Spacing::Hairline)"
TIGHT = f"{TM}.spacing(ThemeManager::Spacing::Tight)"
SNUG = f"{TM}.spacing(ThemeManager::Spacing::Snug)"

# Each entry: (label, needle_block, replacement_block)
blocks = [
    (
        "headerLayout",
        "    auto *headerLayout = new QHBoxLayout(bottomUtilityHeaderBar_);\n"
        "    headerLayout->setContentsMargins(8, 4, 8, 4);\n"
        "    headerLayout->setSpacing(6);",
        "    auto *headerLayout = new QHBoxLayout(bottomUtilityHeaderBar_);\n"
        f"    headerLayout->setContentsMargins({TIGHT}, {HAIR}, {TIGHT}, {HAIR});\n"
        f"    headerLayout->setSpacing({TIGHT});",
    ),
    (
        "expandedLayout",
        "    auto *expandedLayout = new QHBoxLayout(queueExpandedContent_);\n"
        "    expandedLayout->setContentsMargins(8, 4, 8, 8);\n"
        "    expandedLayout->setSpacing(8);",
        "    auto *expandedLayout = new QHBoxLayout(queueExpandedContent_);\n"
        f"    expandedLayout->setContentsMargins({TIGHT}, {HAIR}, {TIGHT}, {TIGHT});\n"
        f"    expandedLayout->setSpacing({TIGHT});",
    ),
    (
        "QueuePaneRoot layout (setSpacing 10 -> Snug)",
        "    auto *layout = new QVBoxLayout(root);\n"
        "    layout->setContentsMargins(0, 0, 0, 0);\n"
        "    layout->setSpacing(10);",
        "    auto *layout = new QVBoxLayout(root);\n"
        "    layout->setContentsMargins(0, 0, 0, 0);\n"
        f"    layout->setSpacing({SNUG});",
    ),
    (
        "activeLayout",
        "    auto *activeLayout = new QVBoxLayout(activeStrip);\n"
        "    activeLayout->setContentsMargins(8, 6, 8, 6);\n"
        "    activeLayout->setSpacing(3);",
        "    auto *activeLayout = new QVBoxLayout(activeStrip);\n"
        f"    activeLayout->setContentsMargins({TIGHT}, {TIGHT}, {TIGHT}, {TIGHT});\n"
        "    activeLayout->setSpacing(3);",
    ),
    (
        "filtersLayout",
        "    auto *filtersLayout = new QHBoxLayout;\n"
        "    filtersLayout->setContentsMargins(0, 0, 0, 0);\n"
        "    filtersLayout->setSpacing(6);",
        "    auto *filtersLayout = new QHBoxLayout;\n"
        "    filtersLayout->setContentsMargins(0, 0, 0, 0);\n"
        f"    filtersLayout->setSpacing({TIGHT});",
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
                matched = True  # treat as handled-with-error
                break
            text = text.replace(n, r, 1)
            applied += 1
            matched = True
            break
    if not matched:
        problems.append(f"{label} (no match)")

if problems:
    raise SystemExit(
        "Patch 2 had problems: " + "; ".join(problems)
        + ". No changes written (or partial -- see count). Re-run Select-String "
        "on the live file and compare."
    )

if applied != 5:
    raise SystemExit(
        f"Patch 2 expected 5 block replacements but made {applied}. "
        "Aborting without write as a safety measure."
    )

path.write_text(text, encoding="utf-8")
print(f"Applied MainWindow Spacing Tokens Patch 2/3: bottom-utility/queue region "
      f"({applied} blocks, 7 logical calls) migrated to tokens.")
'@
Set-Content .\scripts\refactors\apply_mainwindow_tokens_patch2_bottom_utility.py $patch -Encoding UTF8
.\.venv\Scripts\python.exe .\scripts\refactors\apply_mainwindow_tokens_patch2_bottom_utility.py
