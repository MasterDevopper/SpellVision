#!/usr/bin/env python3
"""
PASS 9 FIXUP: cpp-only re-apply with corrected includes anchor
==============================================================

Why this script exists
----------------------
Pass 9's first apply succeeded on ChainConfigPanelWidget.h but failed
on ChainConfigPanelWidget.cpp. The cpp edit #1 (includes block)
anchored on text that differed slightly from what's on disk:
  - The on-disk file has `widgets/ClickOnlyComboBox.h` (correct
    long-form path), my snapshot had `ClickOnlyComboBox.h`.
  - The on-disk file has a `// --- PASS 7D1 FIXUP CLICKONLY INCLUDE ---`
    marker comment that my snapshot lacked.

The other 6 cpp edits anchored on text that DOES match the on-disk
file -- they would have succeeded on the first run if not for the
all-or-nothing abort guard.

The header is already in "Pass 9 applied" state from the first run.
This script does NOT touch the header. It applies all 7 cpp edits
using corrected anchors.

Atomic-apply guarantee
----------------------
This script validates ALL 7 anchors against the file BEFORE writing
anything. If any one fails, no edit is applied and no backup is
written. (The original Pass 9 script had this guarantee WITHIN a
file but not ACROSS files -- a flaw being noted for Pass 10+
scripts: validate across all files first, write across all files
only if validation passes everywhere.)

Files
-----
  qt_ui/chain/ChainConfigPanelWidget.cpp

  Backup:
    qt_ui/chain/ChainConfigPanelWidget.cpp.pre_pass9_fixup.bak

Verification after applying
---------------------------
  1. Inspect the file:
       Select-String -Path qt_ui\\chain\\ChainConfigPanelWidget.cpp -Pattern "onBrowseCheckpointClicked" | Measure-Object | Select Count
     Expected: 2 (one connect call + one definition).
  2. .\\scripts\\dev\\run_ui.ps1
  3. Build should succeed.
  4. Open Chain mode, + add stage -> T2I, see new MODEL row, click
     Browse, pick a checkpoint, type prompt, click REGENERATE.
"""

from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

NL = "\r\n"

CPP_REL = "qt_ui/chain/ChainConfigPanelWidget.cpp"
CPP_MARKER = "// --- CHAIN STUDIO PASS 9:"

# All 7 cpp edits, anchors updated to match the on-disk text exactly.
# Only edit #1 changes from the original Pass 9 script; the rest are
# identical (their original anchors already matched).
CPP_EDITS = [

# Edit C1 (CORRECTED): use the actual on-disk include header layout,
# preserving the "// --- PASS 7D1 FIXUP CLICKONLY INCLUDE ---" marker
# comment that lives between the local-include block and the Qt
# headers.
(
"""#include "chain/ChainConfigPanelWidget.h"

// --- PASS 7D1 FIXUP CLICKONLY INCLUDE ---
#include "widgets/ClickOnlyComboBox.h"
#include "ThemeManager.h"
#include "widgets/SectionCardWidgets.h"

#include <QAbstractSpinBox>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QScrollArea>
#include <QSizePolicy>
#include <QSpinBox>
#include <QVBoxLayout>""",

"""#include "chain/ChainConfigPanelWidget.h"

// --- CHAIN STUDIO PASS 9: model picker dependencies ---
#include "assets/AssetCatalogScanner.h"
#include "assets/CatalogPickerDialog.h"
#include "generation/OutputPathHelpers.h"

// --- PASS 7D1 FIXUP CLICKONLY INCLUDE ---
#include "widgets/ClickOnlyComboBox.h"
#include "ThemeManager.h"
#include "widgets/SectionCardWidgets.h"

#include <QAbstractSpinBox>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QScrollArea>
#include <QSizePolicy>
#include <QSpinBox>
#include <QVBoxLayout>""",
),

# Edit C2: MODEL row construction (unchanged from original Pass 9).
(
"""    // Empty-state label sits inside the body, shown when no stage is
    // selected or selection is unresolvable.
    emptyLabel_ = new QLabel(
        QStringLiteral("Select a stage from the rail above to view its configuration."),
        bodyHolder_);
    emptyLabel_->setStyleSheet(emptyLabelStyle());
    emptyLabel_->setAlignment(Qt::AlignCenter);
    emptyLabel_->setWordWrap(true);
    bodyLayout->addWidget(emptyLabel_);

    // ---- The seven controls ----
    samplerCombo_ = new ClickOnlyComboBox(bodyHolder_);""",

"""    // Empty-state label sits inside the body, shown when no stage is
    // selected or selection is unresolvable.
    emptyLabel_ = new QLabel(
        QStringLiteral("Select a stage from the rail above to view its configuration."),
        bodyHolder_);
    emptyLabel_->setStyleSheet(emptyLabelStyle());
    emptyLabel_->setAlignment(Qt::AlignCenter);
    emptyLabel_->setWordWrap(true);
    bodyLayout->addWidget(emptyLabel_);

    // --- CHAIN STUDIO PASS 9: MODEL row ---
    // Layout: caption "MODEL" sits above a horizontal row that has the
    // selected-model label (multi-line: display name on top, path
    // underneath) on the left and the Browse button on the right.
    // The whole assembly is wrapped in modelRow_ so setEmptyState can
    // hide it alongside the other control rows.
    modelRow_ = new QWidget(bodyHolder_);
    {
        auto *modelRowLayout = new QVBoxLayout(modelRow_);
        modelRowLayout->setContentsMargins(0, 0, 0, 0);
        modelRowLayout->setSpacing(4);

        auto *caption = new QLabel(QStringLiteral("Model"), modelRow_);
        caption->setStyleSheet(QStringLiteral(
            "QLabel { color: %1; font-size: 10px; font-weight: 700; "
            "letter-spacing: 0.6px; text-transform: uppercase; }"
        ).arg(tm.textMutedColor().name()));
        modelRowLayout->addWidget(caption);

        auto *modelInnerRow = new QWidget(modelRow_);
        auto *modelInnerLayout = new QHBoxLayout(modelInnerRow);
        modelInnerLayout->setContentsMargins(0, 0, 0, 0);
        modelInnerLayout->setSpacing(tm.spacing(ThemeManager::Spacing::Tight));

        selectedModelLabel_ = new QLabel(
            QStringLiteral("No checkpoint selected"),
            modelInnerRow);
        selectedModelLabel_->setWordWrap(true);
        selectedModelLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
        selectedModelLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
        selectedModelLabel_->setStyleSheet(QStringLiteral(
            "QLabel { color: %1; font-size: 11px; }"
        ).arg(tm.textPrimaryColor().name()));
        modelInnerLayout->addWidget(selectedModelLabel_, 1);

        modelBrowseButton_ = new QPushButton(QStringLiteral("Browse"), modelInnerRow);
        modelBrowseButton_->setCursor(Qt::PointingHandCursor);
        modelBrowseButton_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
        // Connect once at construction; the slot reads the current
        // stage's kind to choose the right catalog.
        connect(modelBrowseButton_, &QPushButton::clicked,
                this, &ChainConfigPanelWidget::onBrowseCheckpointClicked);
        modelInnerLayout->addWidget(modelBrowseButton_, 0);

        modelRowLayout->addWidget(modelInnerRow);
    }
    bodyLayout->addWidget(modelRow_);

    // ---- The seven controls ----
    samplerCombo_ = new ClickOnlyComboBox(bodyHolder_);""",
),

# Edit C3: setEmptyState includes modelRow_ in its hide/show set.
(
"""void ChainConfigPanelWidget::setEmptyState(bool empty)
{
    if (emptyLabel_ != nullptr)
        emptyLabel_->setVisible(empty);
    // The seven controls live under labeled holders which are siblings
    // of emptyLabel_ in bodyHolder_'s layout. Hide/show them all.
    for (auto *spin : {stepsSpin_, seedSpin_, widthSpin_, heightSpin_})
    {
        if (spin != nullptr && spin->parentWidget() != nullptr)
            spin->parentWidget()->setVisible(!empty);
    }
    if (cfgSpin_ != nullptr && cfgSpin_->parentWidget() != nullptr)
        cfgSpin_->parentWidget()->setVisible(!empty);
    for (auto *combo : {samplerCombo_, schedulerCombo_})
    {
        if (combo != nullptr && combo->parentWidget() != nullptr)
            combo->parentWidget()->setVisible(!empty);
    }
    if (regenerateButton_ != nullptr)
        regenerateButton_->setEnabled(!empty);
}""",

"""void ChainConfigPanelWidget::setEmptyState(bool empty)
{
    if (emptyLabel_ != nullptr)
        emptyLabel_->setVisible(empty);
    // The seven controls live under labeled holders which are siblings
    // of emptyLabel_ in bodyHolder_'s layout. Hide/show them all.
    for (auto *spin : {stepsSpin_, seedSpin_, widthSpin_, heightSpin_})
    {
        if (spin != nullptr && spin->parentWidget() != nullptr)
            spin->parentWidget()->setVisible(!empty);
    }
    if (cfgSpin_ != nullptr && cfgSpin_->parentWidget() != nullptr)
        cfgSpin_->parentWidget()->setVisible(!empty);
    for (auto *combo : {samplerCombo_, schedulerCombo_})
    {
        if (combo != nullptr && combo->parentWidget() != nullptr)
            combo->parentWidget()->setVisible(!empty);
    }
    // --- CHAIN STUDIO PASS 9: MODEL row visibility ---
    if (modelRow_ != nullptr)
        modelRow_->setVisible(!empty);
    if (regenerateButton_ != nullptr)
        regenerateButton_->setEnabled(!empty);
}""",
),

# Edit C4: applyConfigToControls writes model fields into cache.
(
"""    if (widthSpin_ != nullptr)
        widthSpin_->setValue(config.width > 0 ? config.width : 1024);
    if (heightSpin_ != nullptr)
        heightSpin_->setValue(config.height > 0 ? config.height : 1024);

    for (QObject *o : QList<QObject *>{samplerCombo_, schedulerCombo_,
                                       stepsSpin_, cfgSpin_, seedSpin_,
                                       widthSpin_, heightSpin_})
        blockOff(o);
}""",

"""    if (widthSpin_ != nullptr)
        widthSpin_->setValue(config.width > 0 ? config.width : 1024);
    if (heightSpin_ != nullptr)
        heightSpin_->setValue(config.height > 0 ? config.height : 1024);

    for (QObject *o : QList<QObject *>{samplerCombo_, schedulerCombo_,
                                       stepsSpin_, cfgSpin_, seedSpin_,
                                       widthSpin_, heightSpin_})
        blockOff(o);

    // --- CHAIN STUDIO PASS 9: copy model fields into per-stage cache ---
    // No signals to block here; these are plain QString members. The
    // updateModelRowFromCache() call refreshes the MODEL row label.
    lastPickedModelValue_    = config.model;
    lastPickedModelDisplay_  = config.modelDisplay;
    lastPickedModelFamily_   = config.modelFamily;
    lastPickedModelModality_ = config.modelModality;
    lastPickedModelRole_     = config.modelRole;
    lastPickedModelMetadata_ = config.selectedVideoStack;
    updateModelRowFromCache();
}""",
),

# Edit C5: setControlsEditable enables/disables Browse button.
(
"""void ChainConfigPanelWidget::setControlsEditable(bool editable)
{
    for (QWidget *w : QList<QWidget *>{samplerCombo_, schedulerCombo_,
                                       stepsSpin_, cfgSpin_, seedSpin_,
                                       widthSpin_, heightSpin_})
    {
        if (w != nullptr)
            w->setEnabled(editable);
    }
}""",

"""void ChainConfigPanelWidget::setControlsEditable(bool editable)
{
    for (QWidget *w : QList<QWidget *>{samplerCombo_, schedulerCombo_,
                                       stepsSpin_, cfgSpin_, seedSpin_,
                                       widthSpin_, heightSpin_})
    {
        if (w != nullptr)
            w->setEnabled(editable);
    }
    // --- CHAIN STUDIO PASS 9: Browse button follows lock state ---
    // Locked stages should not be re-pointed at a different model;
    // unlock the stage first.
    if (modelBrowseButton_ != nullptr)
        modelBrowseButton_->setEnabled(editable);
}""",
),

# Edit C6: harvestCurrentConfig reads model fields from cache.
(
"""    if (widthSpin_ != nullptr)
        harvested.width = widthSpin_->value();
    if (heightSpin_ != nullptr)
        harvested.height = heightSpin_->value();

    return harvested;
}""",

"""    if (widthSpin_ != nullptr)
        harvested.width = widthSpin_->value();
    if (heightSpin_ != nullptr)
        harvested.height = heightSpin_->value();

    // --- CHAIN STUDIO PASS 9: harvest model fields from cache ---
    // These were populated by applyConfigToControls on stage switch
    // and by onBrowseCheckpointClicked on user pick. No null guards
    // needed since they are plain members, not pointer widgets.
    harvested.model              = lastPickedModelValue_;
    harvested.modelDisplay       = lastPickedModelDisplay_;
    harvested.modelFamily        = lastPickedModelFamily_;
    harvested.modelModality      = lastPickedModelModality_;
    harvested.modelRole          = lastPickedModelRole_;
    harvested.selectedVideoStack = lastPickedModelMetadata_;

    return harvested;
}""",
),

# Edit C7: prepend new method definitions BEFORE harvestCurrentConfig.
(
"""StageConfig ChainConfigPanelWidget::harvestCurrentConfig() const
{""",

"""// --- CHAIN STUDIO PASS 9: Browse handler ---
// Opens CatalogPickerDialog with the catalog matching the current
// stage's kind. Image stages get scanImageModelCatalog; video stages
// get scanVideoModelStackCatalog. I2_3D / Audio are not supported.
//
// On accept, the picker's selectedValue / selectedDisplay (plus the
// matching CatalogEntry's family / modality / role / metadata fields)
// land in the per-stage cache, and updateModelRowFromCache refreshes
// the MODEL row UI. The harvested config flows into the engine only
// when the user clicks Regenerate.
void ChainConfigPanelWidget::onBrowseCheckpointClicked()
{
    using spellvision::assets::CatalogEntry;
    using spellvision::assets::CatalogPickerDialog;
    using spellvision::assets::persistRecentSelection;
    using spellvision::assets::scanImageModelCatalog;
    using spellvision::assets::scanVideoModelStackCatalog;
    using spellvision::generation::chooseModelsRootPath;

    const Stage *s = currentStage();
    if (s == nullptr)
        return;

    const QString modelsRoot = chooseModelsRootPath();

    QVector<CatalogEntry> entries;
    QString dialogTitle;
    QString recentKey;

    switch (s->kind)
    {
        case StageKind::T2I:
        case StageKind::I2I:
            entries     = scanImageModelCatalog(modelsRoot);
            dialogTitle = QStringLiteral("Choose Checkpoint");
            recentKey   = QStringLiteral("chain_studio/recent_checkpoints");
            break;
        case StageKind::T2V:
        case StageKind::I2V:
            entries     = scanVideoModelStackCatalog(modelsRoot);
            dialogTitle = QStringLiteral("Choose Video Model Stack");
            recentKey   = QStringLiteral("chain_studio/recent_video_model_stacks");
            break;
        case StageKind::I2_3D:
        case StageKind::Audio:
            // Engine refuses to execute these (per isExecutable in
            // ChainModel.h). No catalog scan, no dialog -- the Browse
            // button click is a silent no-op for these kinds. Pass 10
            // polish can disable the button proactively when these
            // kinds are selected.
            return;
    }

    CatalogPickerDialog dialog(dialogTitle, entries, lastPickedModelValue_,
                               recentKey, this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    const QString chosenValue   = dialog.selectedValue();
    const QString chosenDisplay = dialog.selectedDisplay();

    // Look up the matching CatalogEntry to capture family / modality /
    // role / metadata. (CatalogPickerDialog only returns value and
    // display; the rest we resolve here from the scan results.)
    QString family;
    QString modality;
    QString role;
    QJsonObject metadata;
    for (const CatalogEntry &entry : entries)
    {
        if (entry.value == chosenValue)
        {
            family   = entry.family;
            modality = entry.modality;
            role     = entry.role;
            metadata = entry.metadata;
            break;
        }
    }

    lastPickedModelValue_    = chosenValue;
    lastPickedModelDisplay_  = chosenDisplay;
    lastPickedModelFamily_   = family;
    lastPickedModelModality_ = modality;
    lastPickedModelRole_     = role;
    lastPickedModelMetadata_ = metadata;

    persistRecentSelection(recentKey, chosenValue);
    updateModelRowFromCache();
}

// --- CHAIN STUDIO PASS 9: refresh the MODEL row label ---
// Reads lastPickedModelValue_ / Display and rebuilds the label text.
// Mirrors ImageGenerationPage::refreshSelectedModelUi's format:
// "<display>\\n<path>" if both are set, just the value if display is
// empty, or a placeholder string when nothing is selected.
void ChainConfigPanelWidget::updateModelRowFromCache()
{
    if (selectedModelLabel_ == nullptr)
        return;

    if (lastPickedModelValue_.trimmed().isEmpty())
    {
        selectedModelLabel_->setText(QStringLiteral("No checkpoint selected"));
        return;
    }

    if (lastPickedModelDisplay_.trimmed().isEmpty())
    {
        selectedModelLabel_->setText(lastPickedModelValue_);
        return;
    }

    selectedModelLabel_->setText(
        QStringLiteral("%1\\n%2").arg(lastPickedModelDisplay_, lastPickedModelValue_));
}

StageConfig ChainConfigPanelWidget::harvestCurrentConfig() const
{""",
),

]


def already_applied(text: str, marker: str) -> bool:
    return marker in text


def write_with_crlf(path: Path, body_lf: str) -> None:
    text = body_lf.replace("\r\n", "\n").replace("\n", NL)
    path.write_bytes(text.encode("utf-8"))


def main() -> int:
    print("Applying PASS 9 FIXUP: cpp-only re-apply")
    print(f"  Project root: {PROJECT_ROOT}")
    print()

    cpp_path = PROJECT_ROOT / CPP_REL
    if not cpp_path.exists():
        print(f"ERROR: {CPP_REL} does not exist at {cpp_path}")
        return 1

    raw = cpp_path.read_bytes().decode("utf-8")
    body = raw.replace("\r\n", "\n")

    if already_applied(body, CPP_MARKER):
        print(f"  Already applied (marker present): {cpp_path.name}")
        print("  No-op.")
        return 0

    # === ATOMIC VALIDATION ===
    # Validate EVERY anchor before writing anything. This is the
    # guarantee the original Pass 9 script had within a file but not
    # across files. Here it doesn't matter since we only touch one
    # file, but the pattern is the right one for Pass 10+ multi-file
    # scripts.
    print(f"  Validating {len(CPP_EDITS)} anchors against {cpp_path.name}...")
    for i, (anchor, _replacement) in enumerate(CPP_EDITS, 1):
        count = body.count(anchor)
        if count != 1:
            print(f"  ERROR: edit #{i} anchor matches {count} times "
                  f"(expected exactly 1).")
            preview = anchor.split("\n")[0][:80]
            print(f"  First line of anchor: {preview!r}")
            print()
            print("  No file written. Investigate the on-disk text.")
            return 2
    print(f"  All {len(CPP_EDITS)} anchors validated.")

    # === APPLY ===
    for anchor, replacement in CPP_EDITS:
        body = body.replace(anchor, replacement, 1)

    if CPP_MARKER not in body:
        print(f"  ERROR: post-edit body does not contain MARKER {CPP_MARKER!r}.")
        return 3

    # Write backup, then CRLF-normalized body.
    backup = cpp_path.with_suffix(cpp_path.suffix + ".pre_pass9_fixup.bak")
    backup.write_bytes(raw.encode("utf-8"))
    print(f"  Backup written: {backup.name}")

    write_with_crlf(cpp_path, body)
    print(f"  Rewrote: {cpp_path.name}")
    print()

    print("Done -- PASS 9 FIXUP applied.")
    print()
    print("Verify:")
    print("  Select-String -Path qt_ui\\chain\\ChainConfigPanelWidget.cpp -Pattern 'onBrowseCheckpointClicked' | Measure-Object | Select Count")
    print("    Expected: 2")
    print("  Then: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
