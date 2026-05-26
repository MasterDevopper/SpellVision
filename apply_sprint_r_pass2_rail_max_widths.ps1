$patch = @'
"""
Sprint R Pass 2: raise rail max-widths so they can absorb freed width.

With the canvas now capped (Pass 1), the rails need permission to grow
into the space the canvas no longer takes. Today the Wide tier caps the
left rail at 440 px and the right rail at 500 px, so even when there is
surplus width the rails refuse it and the splitter is forced to leave a
gap or over-feed the (now-capped) center.

This pass raises ONLY the Wide-tier hard maximums (left 440 -> 1400,
right 500 -> 1500). These are SAFETY CEILINGS -- Pass 3 uses lower soft
targets (560 / 620) for proportional sizing, then lets the rails absorb
canvas overflow past those at ultrawide. The hard cap must exceed the
largest width Pass 3 can compute or the scroll area fights setSizes(). Compact and Medium tiers are untouched -- they are not where
the ultrawide problem occurs, and widening them would hurt the
narrow-window layouts that currently work. The minimums are also
unchanged so nothing collapses.

Wider rails directly improve the LTX path fields and the Asset
Intelligence rows, both of which currently truncate.
"""
from pathlib import Path
path = Path("qt_ui/ImageGenerationPage.cpp")
text = path.read_text(encoding="utf-8")

# --- Left rail Wide-tier max ---
needle_left = '''        else
        {
            leftScrollArea_->setMinimumWidth(380);
            leftScrollArea_->setMaximumWidth(440);
        }
    }'''

replacement_left = '''        else
        {
            // Sprint R Pass 2: Wide-tier left rail hard max raised 440 -> 1400.
            // This is a safety ceiling only -- Pass 3's computed sizing uses
            // a 560px SOFT target for the proportional phase, then lets the
            // rail absorb canvas overflow past that at ultrawide. The hard
            // cap must stay above the largest width Pass 3 can compute
            // (~1200 at 4K) or the scroll area would fight setSizes().
            leftScrollArea_->setMinimumWidth(380);
            leftScrollArea_->setMaximumWidth(1400);
        }
    }'''

if needle_left not in text:
    raise SystemExit("Could not find left rail Wide-tier max-width block")
text = text.replace(needle_left, replacement_left, 1)

# --- Right rail Wide-tier max ---
needle_right = '''        else
        {
            rightScrollArea_->setMinimumWidth(410);
            rightScrollArea_->setMaximumWidth(500);
        }
    }'''

replacement_right = '''        else
        {
            // Sprint R Pass 2: Wide-tier right rail hard max raised 500 -> 1500.
            // Safety ceiling only; Pass 3 uses a 620px SOFT target then lets
            // the rail absorb overflow at ultrawide (up to ~1380 at 4K).
            rightScrollArea_->setMinimumWidth(410);
            rightScrollArea_->setMaximumWidth(1500);
        }
    }'''

if needle_right not in text:
    raise SystemExit("Could not find right rail Wide-tier max-width block")
text = text.replace(needle_right, replacement_right, 1)

path.write_text(text, encoding="utf-8")
print("Applied Sprint R Pass 2: Wide-tier rail max-widths raised (left 560, right 620).")
'@
Set-Content .\scripts\refactors\apply_sprint_r_pass2_rail_max_widths.py $patch -Encoding UTF8
.\.venv\Scripts\python.exe .\scripts\refactors\apply_sprint_r_pass2_rail_max_widths.py
