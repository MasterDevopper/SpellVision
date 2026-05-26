#!/usr/bin/env python3
"""
PASS 8C.2: ChainConfigPanelWidget::harvestCurrentConfig API
===========================================================

What this script does
---------------------
Adds a public method harvestCurrentConfig() to ChainConfigPanelWidget
that reads the 7 user-editable controls (sampler, scheduler, steps,
cfg, seed, width, height) and returns a StageConfig populated with:
- The currentStage()->config as the baseline (preserving prompt,
  negativePrompt, model fields, LoRA stack, workflow paths, video-
  specific fields, etc. -- anything the panel doesn't expose for
  editing)
- The 7 control values overwritten with the user's current widget
  state

Why this is the right shape
---------------------------
Option A from the design discussion: harvest-on-Regenerate (not
live binding). The user's edits live in the widget until Regenerate
fires; harvestCurrentConfig() is what Regenerate's handler calls to
get the final config to push into the engine via setStageConfig()
right before regenerate().

Returning a default-constructed StageConfig when no stage is selected
is intentional: the caller is responsible for not regenerating a
stage that doesn't exist, but if they do, the engine will reject and
nothing bad happens.

What this script DOES NOT do
----------------------------
- Does not call harvestCurrentConfig from anywhere -- pure surface
  addition (Pass 8c.3 wires the first caller in ChainStudioPage's
  onConfigRegenerateRequested body).
- Does not change applyConfigToControls or any other panel method.
- Does not modify ChainStudioPage.

Files
-----
  qt_ui/chain/ChainConfigPanelWidget.h
  qt_ui/chain/ChainConfigPanelWidget.cpp

  Backups:
    qt_ui/chain/ChainConfigPanelWidget.h.pre_pass8c2.bak
    qt_ui/chain/ChainConfigPanelWidget.cpp.pre_pass8c2.bak

Idempotency
-----------
Marker-guarded by "// --- CHAIN STUDIO PASS 8C.2:" in both files.
Re-run is a clean no-op.

Verification after applying
---------------------------
  1. .\\scripts\\dev\\run_ui.ps1
  2. Build should succeed -- ChainConfigPanelWidget.cpp recompiles,
     mocs_compilation_Debug.cpp does NOT (new method is plain public,
     not a slot, but Q_OBJECT classes regenerate MOC on header change
     anyway -- so MOC might also recompile).
  3. Chain studio behaves IDENTICALLY to Pass 8c.1 -- no callers of
     harvestCurrentConfig yet.
  4. Click + add stage -> T2I -> config panel populates.
  5. Click Regenerate -> still no-op (Pass 8c.3 wires it).
"""

from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

NL = "\r\n"

# ---------------------------------------------------------------
# ChainConfigPanelWidget.h edits
# ---------------------------------------------------------------

HEADER_REL = "qt_ui/chain/ChainConfigPanelWidget.h"
HEADER_MARKER = "// --- CHAIN STUDIO PASS 8C.2:"

# Edit H1: add the harvestCurrentConfig() public method declaration
# right after setSelectedStageId, keeping the public API surface
# clustered. Comment explains what the method does and what it does
# NOT do (it doesn't push to engine; the caller does).
HEADER_EDITS = [
(
"""    // Switch which stage's config the panel shows. Same selection
    // mechanism the rail and canvas use.
    void setSelectedStageId(const QString &stageId);

signals:""",

"""    // Switch which stage's config the panel shows. Same selection
    // mechanism the rail and canvas use.
    void setSelectedStageId(const QString &stageId);

    // --- CHAIN STUDIO PASS 8C.2: panel -> config harvest API ---
    // Returns a StageConfig built from currentStage()->config (so all
    // fields the panel does NOT expose for editing -- prompt, model,
    // LoRA stack, workflow paths, video-specific fields -- pass through
    // unchanged) with the 7 user-editable control values overlaid:
    // sampler, scheduler, steps, cfg, seed, width, height.
    //
    // Returns a default-constructed StageConfig if no stage is
    // currently selected. The caller is expected to push the result
    // into ChainEngine::setStageConfig(stageId, harvested) before
    // calling ChainEngine::regenerate(stageId).
    //
    // This method does NOT modify the engine. It does NOT modify the
    // panel's internal Chain copy. It just packages widget state for
    // the caller.
    StageConfig harvestCurrentConfig() const;

signals:""",
),
]

# ---------------------------------------------------------------
# ChainConfigPanelWidget.cpp edits
# ---------------------------------------------------------------

CPP_REL = "qt_ui/chain/ChainConfigPanelWidget.cpp"
CPP_MARKER = "// --- CHAIN STUDIO PASS 8C.2:"

# Edit C1: insert harvestCurrentConfig implementation immediately
# AFTER applyConfigToControls. The two are mirror images of each
# other (one writes the controls from a config, the other reads
# config from the controls) and pairing them keeps the file
# navigable.
CPP_EDITS = [
(
"""void ChainConfigPanelWidget::applyConfigToControls(const StageConfig &config)
{
    // Block signals while updating to prevent edit-signal cascades.
    // (Pass 7d.1 doesn't yet connect editing signals, but doing this
    // now means Pass 8 can wire them without thinking about loops.)
    const auto blockOn = [](QObject *o) { if (o) o->blockSignals(true); };
    const auto blockOff = [](QObject *o) { if (o) o->blockSignals(false); };

    for (QObject *o : QList<QObject *>{samplerCombo_, schedulerCombo_,
                                       stepsSpin_, cfgSpin_, seedSpin_,
                                       widthSpin_, heightSpin_})
        blockOn(o);

    if (samplerCombo_ != nullptr)
    {
        const QString s = config.imageSampler.isEmpty()
            ? QStringLiteral("dpmpp_2m") : config.imageSampler;
        const int idx = samplerCombo_->findData(s);
        samplerCombo_->setCurrentIndex(idx >= 0 ? idx : 0);
    }
    if (schedulerCombo_ != nullptr)
    {
        const QString s = config.imageScheduler.isEmpty()
            ? QStringLiteral("karras") : config.imageScheduler;
        const int idx = schedulerCombo_->findData(s);
        schedulerCombo_->setCurrentIndex(idx >= 0 ? idx : 0);
    }
    if (stepsSpin_ != nullptr)
        stepsSpin_->setValue(config.steps > 0 ? config.steps : 20);
    if (cfgSpin_ != nullptr)
        cfgSpin_->setValue(config.cfg > 0.0 ? config.cfg : 7.0);
    if (seedSpin_ != nullptr)
        seedSpin_->setValue(config.seed);
    if (widthSpin_ != nullptr)
        widthSpin_->setValue(config.width > 0 ? config.width : 1024);
    if (heightSpin_ != nullptr)
        heightSpin_->setValue(config.height > 0 ? config.height : 1024);

    for (QObject *o : QList<QObject *>{samplerCombo_, schedulerCombo_,
                                       stepsSpin_, cfgSpin_, seedSpin_,
                                       widthSpin_, heightSpin_})
        blockOff(o);
}""",

"""void ChainConfigPanelWidget::applyConfigToControls(const StageConfig &config)
{
    // Block signals while updating to prevent edit-signal cascades.
    // (Pass 7d.1 doesn't yet connect editing signals, but doing this
    // now means Pass 8 can wire them without thinking about loops.)
    const auto blockOn = [](QObject *o) { if (o) o->blockSignals(true); };
    const auto blockOff = [](QObject *o) { if (o) o->blockSignals(false); };

    for (QObject *o : QList<QObject *>{samplerCombo_, schedulerCombo_,
                                       stepsSpin_, cfgSpin_, seedSpin_,
                                       widthSpin_, heightSpin_})
        blockOn(o);

    if (samplerCombo_ != nullptr)
    {
        const QString s = config.imageSampler.isEmpty()
            ? QStringLiteral("dpmpp_2m") : config.imageSampler;
        const int idx = samplerCombo_->findData(s);
        samplerCombo_->setCurrentIndex(idx >= 0 ? idx : 0);
    }
    if (schedulerCombo_ != nullptr)
    {
        const QString s = config.imageScheduler.isEmpty()
            ? QStringLiteral("karras") : config.imageScheduler;
        const int idx = schedulerCombo_->findData(s);
        schedulerCombo_->setCurrentIndex(idx >= 0 ? idx : 0);
    }
    if (stepsSpin_ != nullptr)
        stepsSpin_->setValue(config.steps > 0 ? config.steps : 20);
    if (cfgSpin_ != nullptr)
        cfgSpin_->setValue(config.cfg > 0.0 ? config.cfg : 7.0);
    if (seedSpin_ != nullptr)
        seedSpin_->setValue(config.seed);
    if (widthSpin_ != nullptr)
        widthSpin_->setValue(config.width > 0 ? config.width : 1024);
    if (heightSpin_ != nullptr)
        heightSpin_->setValue(config.height > 0 ? config.height : 1024);

    for (QObject *o : QList<QObject *>{samplerCombo_, schedulerCombo_,
                                       stepsSpin_, cfgSpin_, seedSpin_,
                                       widthSpin_, heightSpin_})
        blockOff(o);
}

// --- CHAIN STUDIO PASS 8C.2: panel -> config harvest ---
// Mirror image of applyConfigToControls above. Reads the 7 controls,
// overlays them onto currentStage()->config, returns the result.
//
// Why start from currentStage()->config rather than a fresh default?
// Because StageConfig has ~20 fields (prompt, negativePrompt, model,
// modelDisplay, modelFamily, modelModality, modelRole,
// selectedVideoStack, workflow* paths, ltx* fields, loras, video
// sampler/scheduler, frames, fps, etc.) and the panel only exposes 7
// of them. Starting from the existing config preserves the other
// ~13 untouched -- they came from setStageConfig or from the engine's
// default seed, and the user has no UI to edit them.
StageConfig ChainConfigPanelWidget::harvestCurrentConfig() const
{
    const Stage *s = currentStage();
    StageConfig harvested = (s != nullptr) ? s->config : StageConfig{};

    if (samplerCombo_ != nullptr)
    {
        const QString val = samplerCombo_->currentData().toString();
        if (!val.isEmpty())
            harvested.imageSampler = val;
    }
    if (schedulerCombo_ != nullptr)
    {
        const QString val = schedulerCombo_->currentData().toString();
        if (!val.isEmpty())
            harvested.imageScheduler = val;
    }
    if (stepsSpin_ != nullptr)
        harvested.steps = stepsSpin_->value();
    if (cfgSpin_ != nullptr)
        harvested.cfg = cfgSpin_->value();
    if (seedSpin_ != nullptr)
        harvested.seed = seedSpin_->value();
    if (widthSpin_ != nullptr)
        harvested.width = widthSpin_->value();
    if (heightSpin_ != nullptr)
        harvested.height = heightSpin_->value();

    return harvested;
}""",
),
]


def already_applied(text: str, marker: str) -> bool:
    return marker in text


def write_with_crlf(path: Path, body_lf: str) -> None:
    text = body_lf.replace("\r\n", "\n").replace("\n", NL)
    path.write_bytes(text.encode("utf-8"))


def apply_edits(path: Path, edits, marker, backup_suffix) -> bool:
    raw = path.read_bytes().decode("utf-8")
    body = raw.replace("\r\n", "\n")

    if already_applied(body, marker):
        print(f"  Already applied (marker present): {path.name}")
        return False

    for i, (anchor, _replacement) in enumerate(edits, 1):
        count = body.count(anchor)
        if count != 1:
            print(f"  ERROR: edit #{i} anchor matches {count} times "
                  f"(expected exactly 1).")
            preview = anchor.split("\n")[0][:80]
            print(f"  First line of anchor: {preview!r}")
            return False

    for anchor, replacement in edits:
        body = body.replace(anchor, replacement, 1)

    if marker not in body:
        print(f"  ERROR: post-edit body does not contain MARKER {marker!r}.")
        return False

    backup = path.with_suffix(path.suffix + backup_suffix)
    backup.write_bytes(raw.encode("utf-8"))
    print(f"  Backup written: {backup.name}")

    write_with_crlf(path, body)
    print(f"  Rewrote: {path.name}")
    return True


def main() -> int:
    print("Applying PASS 8C.2: ChainConfigPanelWidget::harvestCurrentConfig")
    print(f"  Project root: {PROJECT_ROOT}")
    print()

    h_path = PROJECT_ROOT / HEADER_REL
    cpp_path = PROJECT_ROOT / CPP_REL

    if not h_path.exists():
        print(f"ERROR: {HEADER_REL} does not exist at {h_path}")
        return 1
    if not cpp_path.exists():
        print(f"ERROR: {CPP_REL} does not exist at {cpp_path}")
        return 1

    print(HEADER_REL)
    h_changed = apply_edits(h_path, HEADER_EDITS, HEADER_MARKER, ".pre_pass8c2.bak")
    print()

    if not h_changed:
        print(CPP_REL)
        cpp_changed = apply_edits(cpp_path, CPP_EDITS, CPP_MARKER, ".pre_pass8c2.bak")
        print()
        if not cpp_changed:
            print("Done -- PASS 8C.2 was already applied (no-op).")
            return 0
        else:
            print("Warning: header already had marker but cpp did not.")
            print("Cpp has now been updated; investigate if unexpected.")
            return 0

    print(CPP_REL)
    cpp_changed = apply_edits(cpp_path, CPP_EDITS, CPP_MARKER, ".pre_pass8c2.bak")
    print()

    if not cpp_changed:
        print("ERROR: header edit succeeded but cpp edit failed.")
        print("       Restore ChainConfigPanelWidget.h.pre_pass8c2.bak and investigate.")
        return 2

    print("Done -- PASS 8C.2 applied.")
    print()
    print("Verify:")
    print("  1. .\\scripts\\dev\\run_ui.ps1")
    print("  2. Build should succeed -- ChainConfigPanelWidget.cpp recompiles.")
    print("  3. Chain studio behaves identically to Pass 8c.1.")
    print("  4. + add stage -> T2I -> config panel populates as before.")
    print("  5. Click Regenerate -- still no-op (Pass 8c.3 wires the caller).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
