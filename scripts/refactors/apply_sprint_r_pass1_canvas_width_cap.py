"""
Sprint R Pass 1: cap the center canvas width.

At ultrawide/fullscreen the QSplitter stretch factors (0 / 1 / 0) dump
ALL surplus width into the center column, producing a vast empty canvas
with the rails pinned narrow. Per the chosen design direction ("cap
canvas, give extra space to the rails"), this pass caps the center
container at a comfortable maximum so the canvas stops growing past a
readable size. Pass 3 redistributes the freed width into the rails.

The cap (1280 px) is generous enough for image previews at 1024x1024
plus card chrome, and for video previews at typical T2V/I2V resolutions,
without leaving a barren field at 2560px+ displays.
"""
from pathlib import Path
path = Path("qt_ui/ImageGenerationPage.cpp")
text = path.read_text(encoding="utf-8")

needle = '''    centerContainer_ = new QWidget(contentSplitter_);
    auto *centerLayout = new QVBoxLayout(centerContainer_);
    centerLayout->setContentsMargins(0, 0, 0, 0);
    centerLayout->setSpacing(0);'''

replacement = '''    centerContainer_ = new QWidget(contentSplitter_);
    // Sprint R Pass 1:
    // Cap the canvas width. Without this, QSplitter's stretch factors
    // (0 / 1 / 0) hand every surplus pixel at ultrawide/fullscreen to the
    // center column, leaving a barren preview field while the rails stay
    // pinned narrow. 1280 px comfortably fits a 1024x1024 image preview
    // plus card chrome and typical video preview sizes. Pass 3's computed
    // splitter sizing redistributes anything beyond this into the rails.
    centerContainer_->setMaximumWidth(1280);
    auto *centerLayout = new QVBoxLayout(centerContainer_);
    centerLayout->setContentsMargins(0, 0, 0, 0);
    centerLayout->setSpacing(0);'''

if needle not in text:
    raise SystemExit("Could not find centerContainer_ creation point in ImageGenerationPage.cpp")
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")
print("Applied Sprint R Pass 1: center canvas capped at 1280px.")
