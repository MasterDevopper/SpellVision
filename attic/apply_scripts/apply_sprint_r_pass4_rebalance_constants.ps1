$patch = @'
"""
Sprint R Pass 4: rebalance the computed splitter constants.

Sprint R Pass 1-3 fixed the ultrawide void in the RIGHT DIRECTION but the
numbers were over-tuned toward the rails. On a 2560px display the result
was canvas 605 / 1280 / 675 -- the canvas, capped at 1280, became a tall
narrow column with the preview floating in a mostly-empty field. The
horizontal void just became a vertical one.

This pass rebalances three constant clusters so the canvas keeps the
lion's share (it IS the workspace) while the rails get *enough*, not
*greedy*:

  - Canvas cap:     1280 -> 1600   (both the centerContainer hard max
                                    and the canvasCap used in computed
                                    sizing)
  - Rail percents:  22%/26% -> 16%/18%   (proportional-phase targets)
  - Wide soft max:  560/620 -> 460/500
  - Medium soft max: 420/470 -> 400/440

Resulting splits after this pass:
  1920px -> 380 / 1130 / 410   (canvas 58%)
  2560px -> 449 / 1600 / 511   (canvas 62%)
  3440px -> 856 / 1600 / 984   (canvas 46%, rails wide but not ugly)

The overflow-redistribution logic (rails absorb everything past the
canvas cap, 45/55 split) is UNCHANGED -- only the constants move.

This patch edits text written by Sprint R Pass 1 and Pass 3, so it must
run AFTER those. If a needle does not match, those passes were not
applied (or were applied differently) -- nothing is written in that case.
"""
from pathlib import Path
path = Path("qt_ui/ImageGenerationPage.cpp")
text = path.read_text(encoding="utf-8")

replacements = []

# --- 1. centerContainer hard max: 1280 -> 1600 (written by Pass 1) ---
replacements.append((
    "centerContainer_->setMaximumWidth(1280);",
    "centerContainer_->setMaximumWidth(1600);",
    "Pass 1 centerContainer hard max",
))

# --- 2. Medium-tier constants (written by Pass 3) ---
replacements.append((
    """        leftMin = 360; leftMax = 420;
        rightMin = 390; rightMax = 470;
        canvasCap = 1280;""",
    """        leftMin = 360; leftMax = 400;
        rightMin = 390; rightMax = 440;
        canvasCap = 1600;""",
    "Pass 3 Medium-tier constants",
))

# --- 3. Wide-tier constants (written by Pass 3) ---
replacements.append((
    """        // These maxes match the Pass 2 rail scroll-area caps.
        leftMin = 380; leftMax = 560;
        rightMin = 410; rightMax = 620;
        canvasCap = 1280;""",
    """        // Soft targets for the proportional phase; rails still absorb
        // overflow past the canvas cap without a hard ceiling here.
        leftMin = 380; leftMax = 460;
        rightMin = 410; rightMax = 500;
        canvasCap = 1600;""",
    "Pass 3 Wide-tier constants",
))

# --- 4. Rail proportional percentages (written by Pass 3) ---
replacements.append((
    """    int leftW = qBound(leftMin, available * 22 / 100, leftMax);
    int rightW = qBound(rightMin, available * 26 / 100, rightMax);""",
    """    int leftW = qBound(leftMin, available * 16 / 100, leftMax);
    int rightW = qBound(rightMin, available * 18 / 100, rightMax);""",
    "Pass 3 rail proportional percentages",
))

missing = [label for old, new, label in replacements if old not in text]
if missing:
    raise SystemExit(
        "Sprint R Pass 4 could not find: " + "; ".join(missing) +
        ". Ensure Sprint R Pass 1 and Pass 3 were applied first."
    )

for old, new, label in replacements:
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Applied Sprint R Pass 4: splitter constants rebalanced (canvas cap 1600, rails 16/18%).")
'@
Set-Content .\scripts\refactors\apply_sprint_r_pass4_rebalance_constants.py $patch -Encoding UTF8
.\.venv\Scripts\python.exe .\scripts\refactors\apply_sprint_r_pass4_rebalance_constants.py
