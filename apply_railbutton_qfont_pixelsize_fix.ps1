$patch = @'
"""
QFont::setPointSize(-1) warning fix attempt: explicit pixel-size on rail buttons.

THE WARNING
-----------
On hovering the left-rail buttons (T2V, etc.) the console logs
"QFont::setPointSize: Point size <= 0 (-1), must be greater than 0"
~22 times. Exhaustive search of qt_ui found NO setPointSize / QFont /
setFont / QSvgRenderer anywhere in SpellVision code -- the call is
inside Qt itself. The likely path: ThemeManager's shell stylesheet sets
"QToolButton#SideRailButton { font-size: 12px; }" (a PIXEL size). When
Qt recomputes the button style on :hover, an internal code path reads
the font's pointSize(), gets -1 (the "point size not set" sentinel,
because the size was set in pixels), and round-trips it through
setPointSize() -- emitting the warning. Benign, but noisy.

THE ATTEMPT
-----------
Give each rail button's QFont an explicit pixel size IN C++, at
construction, before the stylesheet is ever applied. If the font
carries a valid pixelSize() from the start, Qt's hover-recompute has a
real value to read instead of the -1 sentinel, and the internal
setPointSize(-1) path should not be hit.

12px is chosen to MATCH the existing stylesheet rule
("QToolButton#SideRailButton { ... font-size: 12px; ... }" in
ThemeManager.cpp) -- so this changes NOTHING visually; the buttons were
already rendering at 12px via the stylesheet. This only ensures the
C++-side font object agrees, pre-empting the mismatch.

This is a ONE-SHOT attempt. If the warning persists after this, the
agreed call is to park it as a benign Qt-internal quirk -- no second
attempt, no message-handler filter.

Two edits, both in MainWindow.cpp:
  1. Add #include <QFont> (currently absent; QToolButton is included).
  2. In createRailButton, after setCursor(...) and before return,
     set an explicit-pixel-size font on the button.
"""
from pathlib import Path
path = Path("qt_ui/MainWindow.cpp")
text = path.read_text(encoding="utf-8")

# --- Edit 1: add #include <QFont>, grouped next to #include <QToolButton> ---
inc_needle = "#include <QToolButton>"
inc_replacement = "#include <QFont>\r\n#include <QToolButton>"

if inc_needle not in text:
    raise SystemExit("Could not find #include <QToolButton> in MainWindow.cpp")
# Guard: don't double-add if QFont is somehow already there
if "#include <QFont>" in text:
    print("Note: #include <QFont> already present, skipping include edit.")
else:
    text = text.replace(inc_needle, inc_replacement, 1)

# --- Edit 2: explicit pixel-size font in createRailButton ---
# Anchor on the unique 2-line tail of the function: setCursor + return.
fn_needle = (
    "        button->setCursor(Qt::PointingHandCursor);\r\n"
    "        return button;"
)
fn_replacement = (
    "        button->setCursor(Qt::PointingHandCursor);\r\n"
    "\r\n"
    "        // Pre-empt the Qt-internal \"QFont::setPointSize: Point size <= 0\"\r\n"
    "        // warning that fires on rail-button :hover recompute. The shell\r\n"
    "        // stylesheet sets font-size: 12px (a PIXEL size) on\r\n"
    "        // QToolButton#SideRailButton; giving the button's QFont an explicit\r\n"
    "        // pixelSize here means Qt's hover restyle reads a valid size instead\r\n"
    "        // of the -1 \"unset point size\" sentinel. 12px matches the stylesheet,\r\n"
    "        // so this is visually a no-op.\r\n"
    "        QFont railButtonFont = button->font();\r\n"
    "        railButtonFont.setPixelSize(12);\r\n"
    "        button->setFont(railButtonFont);\r\n"
    "\r\n"
    "        return button;"
)

if fn_needle not in text:
    # Fallback to LF in case the working copy isn't CRLF
    fn_needle_lf = fn_needle.replace("\r\n", "\n")
    fn_replacement_lf = fn_replacement.replace("\r\n", "\n")
    if fn_needle_lf in text:
        text = text.replace(fn_needle_lf, fn_replacement_lf, 1)
    else:
        raise SystemExit(
            "Could not find the createRailButton setCursor/return anchor. "
            "No changes written."
        )
else:
    text = text.replace(fn_needle, fn_replacement, 1)

path.write_text(text, encoding="utf-8")
print("Applied QFont pixel-size fix attempt: #include <QFont> added, rail buttons given explicit 12px pixel size.")
'@
Set-Content .\scripts\refactors\apply_railbutton_qfont_pixelsize_fix.py $patch -Encoding UTF8
.\.venv\Scripts\python.exe .\scripts\refactors\apply_railbutton_qfont_pixelsize_fix.py
