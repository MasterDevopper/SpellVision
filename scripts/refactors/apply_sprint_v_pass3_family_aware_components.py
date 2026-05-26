"""
Sprint V Pass 3: family-aware Components panel + WAN advanced row gating.

Extends updateVideoStackModeUi() so that WAN-specific rows (Wan Split,
High Steps, Low Steps, Split Step, High Shift, Low Shift, VAE Tiling,
plus the High Noise / Low Noise model combos) are hidden whenever the
resolved family is LTX, not just whenever the stack mode is non-dual.

Also calls updateVideoFamilyUi() from every place that already calls
updateVideoStackModeUi(), so a model selection change (which can flip
the Auto-resolved family) propagates correctly.

Together with Pass 2 this completes the family separation:

  Family resolved to LTX:
    - LTX Launch Options panel: visible
    - WAN Components rows (HighNoise / LowNoise): hidden
    - WAN Advanced rows (split, steps, shift, tiling): hidden
    - videoStackModeCombo (single/dual): still visible (it controls a WAN
      detail; users could theoretically be in LTX with manual overrides,
      and hiding it would orphan their config)

  Family resolved to WAN:
    - LTX Launch Options panel: hidden
    - WAN Components rows: visible if stack mode is dual-noise
    - WAN Advanced rows: visible if stack mode is dual-noise
"""
from pathlib import Path
path = Path("qt_ui/ImageGenerationPage.cpp")
text = path.read_text(encoding="utf-8")

# --- Insertion 1: extend updateVideoStackModeUi to consult family ---

needle1 = '''void ImageGenerationPage::updateVideoStackModeUi()
{
    if (!isVideoMode())
        return;

    const bool wanDualNoise = usesWanDualNoiseMode();

    if (videoHighNoiseRow_)
        videoHighNoiseRow_->setVisible(wanDualNoise);
    if (videoHighNoiseModelCombo_)
        videoHighNoiseModelCombo_->setVisible(wanDualNoise);
    if (videoLowNoiseRow_)
        videoLowNoiseRow_->setVisible(wanDualNoise);
    if (videoLowNoiseModelCombo_)
        videoLowNoiseModelCombo_->setVisible(wanDualNoise);

    for (QWidget *row : {wanSplitRow_, highNoiseStepsRow_, lowNoiseStepsRow_, splitStepRow_, highNoiseShiftRow_, lowNoiseShiftRow_, enableVaeTilingRow_})
    {
        if (row)
            row->setVisible(wanDualNoise);
    }'''

replacement1 = '''void ImageGenerationPage::updateVideoStackModeUi()
{
    if (!isVideoMode())
        return;

    // Sprint V Pass 3:
    // Family resolution gates WAN UI. Even if the stack mode combo would
    // technically allow dual-noise, an LTX family selection hides WAN
    // rows entirely so the user sees a coherent LTX-only surface.
    const bool familyIsWan = resolvedVideoFamilyToken() == QStringLiteral("wan");
    const bool wanDualNoise = usesWanDualNoiseMode() && familyIsWan;

    if (videoHighNoiseRow_)
        videoHighNoiseRow_->setVisible(wanDualNoise);
    if (videoHighNoiseModelCombo_)
        videoHighNoiseModelCombo_->setVisible(wanDualNoise);
    if (videoLowNoiseRow_)
        videoLowNoiseRow_->setVisible(wanDualNoise);
    if (videoLowNoiseModelCombo_)
        videoLowNoiseModelCombo_->setVisible(wanDualNoise);

    for (QWidget *row : {wanSplitRow_, highNoiseStepsRow_, lowNoiseStepsRow_, splitStepRow_, highNoiseShiftRow_, lowNoiseShiftRow_, enableVaeTilingRow_})
    {
        if (row)
            row->setVisible(wanDualNoise);
    }

    // The stack-mode row itself is only meaningful for WAN. Hide it when
    // family resolved to LTX so the right-rail Components panel doesn't
    // show a "Stack Mode: WAN dual-noise" choice that does nothing.
    if (videoStackModeRow_)
        videoStackModeRow_->setVisible(familyIsWan);
    if (videoStackModeCombo_)
        videoStackModeCombo_->setVisible(familyIsWan);'''

if needle1 not in text:
    raise SystemExit("Could not find updateVideoStackModeUi body in ImageGenerationPage.cpp")
text = text.replace(needle1, replacement1, 1)

# --- Insertion 2: call updateVideoFamilyUi alongside the existing
#     updateVideoStackModeUi() invocations, so family resolution stays
#     in sync when a model changes or a mode switches.
#
# We anchor on each of the existing calls that occur at the end of state
# changes. There are four such sites; we patch them all by handling the
# common pattern.

# Pattern: a trailing call to updateVideoStackModeUi(); on its own line.
# We DO NOT alter the call site inside updateVideoStackModeUi's connect
# (which is already correctly placed and was added in Pass 2).

import re
# Match only top-level (exactly 4 spaces of indent) standalone invocations.
# A negative lookbehind for a space ensures we don't catch 8-space-indented
# calls inside lambdas (e.g. the one added in Pass 2's connect block, which
# already pairs updateVideoFamilyUi() with updateVideoStackModeUi()).
pattern = re.compile(r'(?<=\n)(?<! )    updateVideoStackModeUi\(\);\r?\n')
# Find all standalone-line invocations
matches = list(pattern.finditer(text))
if not matches:
    raise SystemExit("Could not find any updateVideoStackModeUi() invocations to chain with updateVideoFamilyUi()")

# Replace each match with an "updateVideoFamilyUi(); updateVideoStackModeUi();" pair.
# Skip any occurrence that's already preceded by an updateVideoFamilyUi() call.
def replace_match(match):
    start = match.start()
    # Look back ~80 chars; if updateVideoFamilyUi already present, leave alone.
    preceding = text[max(0, start - 80):start]
    if "updateVideoFamilyUi();" in preceding:
        return match.group(0)
    return "    updateVideoFamilyUi();\n" + match.group(0)

new_text = pattern.sub(replace_match, text)
if new_text == text:
    raise SystemExit("Chaining updateVideoFamilyUi onto updateVideoStackModeUi sites produced no change")
text = new_text

path.write_text(text, encoding="utf-8")
print("Applied Sprint V Pass 3: WAN rows gated by family; family UI re-syncs on model/mode change.")
