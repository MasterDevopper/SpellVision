"""
Sprint R Pass 3: width-computed splitter sizing + resize-aware recompute.

Two changes:

1. applyAdaptiveSplitterSizes() is rewritten to COMPUTE the three column
   widths from the splitter's actual available width instead of using
   frozen literals ({395, 850, 465} etc). The algorithm:

     - rails get a target width that scales with available width but is
       clamped to the per-tier [min, max] the rail scroll areas allow
       (those caps were widened for the Wide tier in Pass 2);
     - the canvas gets whatever remains, but is itself capped (Pass 1
       set centerContainer_->setMaximumWidth(1280));
     - any surplus beyond the canvas cap is absorbed entirely by the two
       rails (split 45/55, right rail denser) -- this is the "extra
       space to the rails" behavior chosen for ultrawide. The per-tier
       rail maxes are SOFT targets for the proportional phase only; past
       the canvas cap the rails grow freely (Pass 2's hard scroll-area
       caps sit far above anything reachable here).

   Compact mode keeps its existing right-rail-collapsed special case.

2. The Pass 28F guard in updateAdaptiveLayout() previously only re-seeded
   splitter sizes when the adaptive *tier* changed (Compact/Medium/Wide)
   or on first use. That is why resizing the window *within* the Wide
   tier -- e.g. 1920 -> 2560 -- did nothing: same tier, no recompute, so
   the canvas kept the frozen size and the surplus piled up unused.

   The guard now also recomputes when the splitter's available width has
   changed materially (> 24 px) since the last applied sizing, EXCEPT
   while a generation is active (busy_) -- the anti-breathing protection
   from Pass 28F/28G is preserved for that case, since generation status
   updates were the original source of the "breathing" bug.

A new member, lastSplitterComputeWidth_, tracks the width at which sizes
were last applied. It is added to the header by this same patch.
"""
from pathlib import Path

# --- Header: add the width-tracking member ---
hpath = Path("qt_ui/ImageGenerationPage.h")
htext = hpath.read_text(encoding="utf-8")

h_needle = '''    void updateVideoStackModeUi();'''
if h_needle not in htext:
    raise SystemExit("Could not find updateVideoStackModeUi declaration in header")

h_replacement = '''    void updateVideoStackModeUi();

    // Sprint R Pass 3: width at which applyAdaptiveSplitterSizes() last
    // ran, so updateAdaptiveLayout() can detect a material resize within
    // the same adaptive tier and recompute. -1 = never computed yet.
    int lastSplitterComputeWidth_ = -1;'''

htext = htext.replace(h_needle, h_replacement, 1)
hpath.write_text(htext, encoding="utf-8")

# --- Implementation: rewrite applyAdaptiveSplitterSizes ---
cpath = Path("qt_ui/ImageGenerationPage.cpp")
ctext = cpath.read_text(encoding="utf-8")

c_needle1 = '''void ImageGenerationPage::applyAdaptiveSplitterSizes(AdaptiveLayoutMode mode)
{
    if (!contentSplitter_)
        return;

    if (mode == AdaptiveLayoutMode::Compact)
    {
        if (rightScrollArea_ && rightScrollArea_->isVisible())
            contentSplitter_->setSizes({345, 690, 390});
        else
            contentSplitter_->setSizes({360, 900, 0});
        return;
    }

    if (mode == AdaptiveLayoutMode::Medium)
    {
        contentSplitter_->setSizes({385, 760, 425});
        return;
    }

    contentSplitter_->setSizes({395, 850, 465});
}'''

c_replacement1 = '''void ImageGenerationPage::applyAdaptiveSplitterSizes(AdaptiveLayoutMode mode)
{
    if (!contentSplitter_)
        return;

    // Sprint R Pass 3:
    // Compute column widths from the splitter's actual available width
    // instead of frozen literals. This is what makes the layout respond
    // correctly to window resize at ultrawide/fullscreen.

    const int available = contentSplitter_->contentsRect().width();

    // Defensive: if the splitter has not been laid out yet (width 0 or
    // negative), fall back to the previous fixed seed for this tier so
    // the very first paint is still reasonable.
    if (available <= 0)
    {
        if (mode == AdaptiveLayoutMode::Compact)
            contentSplitter_->setSizes({345, 690, 390});
        else if (mode == AdaptiveLayoutMode::Medium)
            contentSplitter_->setSizes({385, 760, 425});
        else
            contentSplitter_->setSizes({395, 850, 465});
        lastSplitterComputeWidth_ = available;
        return;
    }

    // Compact mode keeps its existing behavior: if the right rail is
    // collapsed it gets 0 width and the canvas absorbs it.
    if (mode == AdaptiveLayoutMode::Compact)
    {
        const bool rightVisible = rightScrollArea_ && rightScrollArea_->isVisible();
        if (rightVisible)
        {
            // Proportional-ish but clamped to the Compact rail caps.
            const int leftW = qBound(330, available * 28 / 100, 390);
            const int rightW = qBound(360, available * 30 / 100, 440);
            const int centerW = qMax(320, available - leftW - rightW);
            contentSplitter_->setSizes({leftW, centerW, rightW});
        }
        else
        {
            const int leftW = qBound(330, available * 30 / 100, 390);
            const int centerW = qMax(320, available - leftW);
            contentSplitter_->setSizes({leftW, centerW, 0});
        }
        lastSplitterComputeWidth_ = available;
        return;
    }

    // Medium and Wide: rails clamped to their per-tier caps, canvas takes
    // the remainder up to its own maximum (set in Pass 1), and any
    // surplus beyond that is split evenly back into the rails.
    int leftMin, leftMax, rightMin, rightMax, canvasCap;
    if (mode == AdaptiveLayoutMode::Medium)
    {
        leftMin = 360; leftMax = 420;
        rightMin = 390; rightMax = 470;
        canvasCap = 1280;
    }
    else // Wide
    {
        // These maxes match the Pass 2 rail scroll-area caps.
        leftMin = 380; leftMax = 560;
        rightMin = 410; rightMax = 620;
        canvasCap = 1280;
    }

    // Start with a proportional target for each rail, clamped to caps.
    int leftW = qBound(leftMin, available * 22 / 100, leftMax);
    int rightW = qBound(rightMin, available * 26 / 100, rightMax);
    int centerW = available - leftW - rightW;

    // Canvas exceeds its cap: the rails absorb ALL of the overflow. The
    // leftMax / rightMax above are SOFT targets for the proportional
    // phase only -- past the canvas cap the rails keep growing without a
    // hard ceiling (the scroll-area hard caps from Pass 2 sit far above
    // anything reachable here, so they never fight this). Split 45/55:
    // the right rail is denser (Model Stack + Asset Intelligence) so it
    // gets the slightly larger share. This is the "extra space to the
    // rails" behavior chosen for ultrawide.
    if (centerW > canvasCap)
    {
        const int overflow = centerW - canvasCap;
        centerW = canvasCap;
        const int toLeft = overflow * 45 / 100;
        const int toRight = overflow - toLeft;
        leftW += toLeft;
        rightW += toRight;
    }
    else if (centerW < 320)
    {
        // Pathologically narrow: shrink rails toward their minimums so
        // the canvas keeps a usable floor.
        int deficit = 320 - centerW;
        centerW = 320;
        const int leftShrink = qMin(leftW - leftMin, deficit / 2);
        const int rightShrink = qMin(rightW - rightMin, deficit - leftShrink);
        leftW -= leftShrink;
        rightW -= rightShrink;
    }

    contentSplitter_->setSizes({leftW, centerW, rightW});
    lastSplitterComputeWidth_ = available;
}'''

if c_needle1 not in ctext:
    raise SystemExit("Could not find applyAdaptiveSplitterSizes body in ImageGenerationPage.cpp")
ctext = ctext.replace(c_needle1, c_replacement1, 1)

# --- Implementation: make the Pass 28F guard resize-aware ---

c_needle2 = '''    // Pass 28F:
    // Do not reset splitter sizes on every resizeEvent/layout pass. The previous
    // behavior reapplied hard splitter sizes continuously, which caused the
    // visible workspace to breathe while generation status updates were flowing.
    // Only seed splitter geometry on first use or when the adaptive mode changes.
    bool splitterNeedsInitialSizes = true;
    if (contentSplitter_)
    {
        const QList<int> sizes = contentSplitter_->sizes();
        int total = 0;
        for (int size : sizes)
            total += size;
        splitterNeedsInitialSizes = sizes.isEmpty() || total <= 0;
    }

    if (adaptiveModeChanged || splitterNeedsInitialSizes)
        applyAdaptiveSplitterSizes(mode);
}'''

c_replacement2 = '''    // Pass 28F + Sprint R Pass 3:
    // Pass 28F's rule still holds during generation: do not reapply
    // splitter sizes on every internal layout pass, because generation
    // status updates were causing the visible workspace to "breathe."
    // BUT outside of generation we DO want to respond to genuine window
    // resizes -- including resizes WITHIN the same adaptive tier, which
    // Pass 28F's tier-only check ignored. That tier-only check is exactly
    // why dragging from 1920 -> 2560 (both Wide) did nothing.
    bool splitterNeedsInitialSizes = true;
    bool splitterWidthChanged = false;
    if (contentSplitter_)
    {
        const QList<int> sizes = contentSplitter_->sizes();
        int total = 0;
        for (int size : sizes)
            total += size;
        splitterNeedsInitialSizes = sizes.isEmpty() || total <= 0;

        // Material width change since the last computed sizing?
        const int availableNow = contentSplitter_->contentsRect().width();
        if (lastSplitterComputeWidth_ >= 0 && availableNow > 0)
        {
            const int delta = availableNow - lastSplitterComputeWidth_;
            splitterWidthChanged = (delta > 24) || (delta < -24);
        }
    }

    // Recompute when: the tier changed, the splitter has never been
    // seeded, OR (the window was materially resized AND we are not mid
    // generation). The busy_ guard preserves the anti-breathing fix.
    const bool resizeDrivenRecompute = splitterWidthChanged && !busy_;
    if (adaptiveModeChanged || splitterNeedsInitialSizes || resizeDrivenRecompute)
        applyAdaptiveSplitterSizes(mode);
}'''

if c_needle2 not in ctext:
    raise SystemExit("Could not find Pass 28F splitter guard in ImageGenerationPage.cpp")
ctext = ctext.replace(c_needle2, c_replacement2, 1)

cpath.write_text(ctext, encoding="utf-8")
print("Applied Sprint R Pass 3: width-computed splitter sizing + resize-aware recompute.")
