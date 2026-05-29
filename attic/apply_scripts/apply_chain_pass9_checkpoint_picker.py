#!/usr/bin/env python3
"""
PASS 9: Checkpoint picker for chain stages
==========================================

What this script does
---------------------
Adds a MODEL row to the top of ChainConfigPanelWidget's body. After
this commit, chain stages have a "Browse" button that opens the
existing CatalogPickerDialog (the same one ImageGenerationPage uses),
the user picks a checkpoint, and the harvested StageConfig populates
the model/modelDisplay/modelFamily/modelModality/modelRole fields
the worker pipeline needs.

This is the UNBLOCKER. After Pass 9 lands, clicking Regenerate on a
chain stage with a model selected produces an actual image.

Architectural choices
---------------------
- Reuse the existing CatalogPickerDialog, AssetCatalogScanner, and
  chooseModelsRootPath from spellvision::assets / spellvision::generation.
  Zero new infrastructure -- pure consumption of existing surfaces.
- Catalog choice is per-stage-kind:
    T2I, I2I  -> scanImageModelCatalog
    T2V, I2V  -> scanVideoModelStackCatalog
    I2_3D, Audio -> disabled (engine doesn't run them)
- Scan fresh on every picker open. Cost is small (~50ms directory
  walk) and avoids cache-invalidation bugs.
- Selected model state lives in private members on the widget,
  mirroring how the 7 spinbox/combobox controls hold their state.
  applyConfigToControls writes to them on stage-switch;
  harvestCurrentConfig reads them out on Regenerate.
- LoRA stack management deferred to Pass 9.5 / 10. Pass 9 only does
  the checkpoint, since that's enough to unblock generation.

What this script DOES NOT do
----------------------------
- No changes to MainWindow, ChainStudioPage, or any engine code.
- No changes to ChainModel / StageConfig (the model fields already
  exist there, populated since Track A).
- No LoRA UI.
- No 3D / Audio support.
- No persistence of selection across app restarts (would require
  the ChainStore wiring -- separate pass).

Files
-----
  qt_ui/chain/ChainConfigPanelWidget.h
  qt_ui/chain/ChainConfigPanelWidget.cpp

  Backups:
    qt_ui/chain/ChainConfigPanelWidget.h.pre_pass9.bak
    qt_ui/chain/ChainConfigPanelWidget.cpp.pre_pass9.bak

Idempotency
-----------
Marker-guarded by "// --- CHAIN STUDIO PASS 9:" in both files.
Re-run is a clean no-op.

Verification after applying
---------------------------
  1. .\\scripts\\dev\\run_ui.ps1
  2. Build should succeed -- ChainConfigPanelWidget.cpp recompiles.
  3. Open Chain mode. + add stage -> T2I.
  4. Config panel now shows MODEL row at top:
       "No checkpoint selected"
       [ Browse ]
  5. Click Browse -> CatalogPickerDialog opens with all checkpoints
     from D:\\AI_ASSETS\\models\\checkpoints (or wherever
     chooseModelsRootPath resolves on this machine).
  6. Pick one (e.g. IoxsPerfectEvilDoll_v10). Dialog closes. The
     MODEL row updates: short name on top, full path underneath.
  7. Type a prompt in the dialog bar (top of page).
  8. Click REGENERATE. THIS TIME IT SHOULD ACTUALLY GENERATE:
     - Stage status flips Idle -> Queued -> Generating.
     - Bottom telemetry switches to Submitting -> Running.
     - VRAM climbs, image generates (30s-2min).
     - When done, canvas displays the result. Status: Completed.
  9. Switch to an I2I or T2V stage if you want to test those
     catalogs; the picker title and contents change accordingly.
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
HEADER_MARKER = "// --- CHAIN STUDIO PASS 9:"

HEADER_EDITS = [

# Edit H1: include QJsonObject for the selectedVideoStack metadata
# field, and add the QPushButton forward declaration.
(
"""#include "chain/ChainModel.h"

#include <QString>
#include <QWidget>

class QComboBox;
class QDoubleSpinBox;
class QFrame;
class QLabel;
class QPushButton;
class QSpinBox;
class QVBoxLayout;""",

"""#include "chain/ChainModel.h"

#include <QJsonObject>
#include <QString>
#include <QWidget>

class QComboBox;
class QDoubleSpinBox;
class QFrame;
class QLabel;
class QPushButton;
class QSpinBox;
class QVBoxLayout;""",
),

# Edit H2: add the new private slot onBrowseCheckpointClicked() and
# the helper updateModelRowFromCache() alongside the existing
# private slots and helpers.
(
"""private slots:
    void onRegenerateClicked();

private:
    // Resync header + body controls from the current selection. Safe
    // to call repeatedly; never reconstructs widgets.
    void refresh();""",

"""private slots:
    void onRegenerateClicked();
    // --- CHAIN STUDIO PASS 9: model picker slot ---
    void onBrowseCheckpointClicked();

private:
    // Resync header + body controls from the current selection. Safe
    // to call repeatedly; never reconstructs widgets.
    void refresh();

    // --- CHAIN STUDIO PASS 9: model picker helpers ---
    // Refresh the MODEL row UI from the lastPickedModel* cache (which
    // applyConfigToControls populates when the stage selection
    // changes). Called whenever the cache is mutated.
    void updateModelRowFromCache();""",
),

# Edit H3: add the new MODEL row widget members and the per-stage
# selection-state cache. The cache mirrors how the 7 spinbox/combo
# controls hold their own state; applyConfigToControls writes the
# cache from incoming config, harvestCurrentConfig reads it out.
(
"""    // ---- body (the seven controls) ----
    QFrame *bodyHolder_     = nullptr;
    QLabel *emptyLabel_     = nullptr;

    spellvision::widgets::ClickOnlyComboBox *samplerCombo_   = nullptr;
    spellvision::widgets::ClickOnlyComboBox *schedulerCombo_ = nullptr;
    QSpinBox                                *stepsSpin_      = nullptr;
    QDoubleSpinBox                          *cfgSpin_        = nullptr;
    QSpinBox                                *seedSpin_       = nullptr;
    QSpinBox                                *widthSpin_      = nullptr;
    QSpinBox                                *heightSpin_     = nullptr;""",

"""    // ---- body (the seven controls) ----
    QFrame *bodyHolder_     = nullptr;
    QLabel *emptyLabel_     = nullptr;

    // --- CHAIN STUDIO PASS 9: MODEL row widgets ---
    // The row container itself (so setEmptyState can hide it).
    QWidget     *modelRow_           = nullptr;
    QLabel      *selectedModelLabel_ = nullptr;
    QPushButton *modelBrowseButton_  = nullptr;

    // --- CHAIN STUDIO PASS 9: per-stage model selection cache ---
    // Mirrors the spinbox/combobox pattern: applyConfigToControls
    // copies the incoming stage config's model fields here on stage
    // switch, harvestCurrentConfig copies them back to the harvested
    // StageConfig. Between those, the user mutates the cache by
    // clicking Browse and picking from the catalog dialog.
    QString     lastPickedModelValue_;
    QString     lastPickedModelDisplay_;
    QString     lastPickedModelFamily_;
    QString     lastPickedModelModality_;
    QString     lastPickedModelRole_;
    QJsonObject lastPickedModelMetadata_;

    spellvision::widgets::ClickOnlyComboBox *samplerCombo_   = nullptr;
    spellvision::widgets::ClickOnlyComboBox *schedulerCombo_ = nullptr;
    QSpinBox                                *stepsSpin_      = nullptr;
    QDoubleSpinBox                          *cfgSpin_        = nullptr;
    QSpinBox                                *seedSpin_       = nullptr;
    QSpinBox                                *widthSpin_      = nullptr;
    QSpinBox                                *heightSpin_     = nullptr;""",
),
]

# ---------------------------------------------------------------
# ChainConfigPanelWidget.cpp edits
# ---------------------------------------------------------------

CPP_REL = "qt_ui/chain/ChainConfigPanelWidget.cpp"
CPP_MARKER = "// --- CHAIN STUDIO PASS 9:"

CPP_EDITS = [

# Edit C1: add includes for the model picker, scanner, and
# OutputPathHelpers (for chooseModelsRootPath).
(
"""#include "chain/ChainConfigPanelWidget.h"

#include "ClickOnlyComboBox.h"
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

#include "ClickOnlyComboBox.h"
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

# Edit C2: build the MODEL row in the constructor, between the
# emptyLabel_ insertion and the first control (samplerCombo_). The
# row uses a horizontal layout: stacked label-block on the left
# (caption "MODEL" + multi-line value), Browse button on the right.
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

# Edit C3: setEmptyState gains the modelRow_ in its hide/show set.
# Without this, the model row stays visible when no stage is selected,
# which would look broken next to the centered empty-state label.
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

# Edit C4: applyConfigToControls writes the incoming config's model
# fields into the per-stage cache and refreshes the MODEL row UI.
# Goes right after the heightSpin_ block; before the blockOff loop
# would be cleanest, but the cache mutations don't emit signals so
# either side of the blockOff is fine.
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

# Edit C5: setControlsEditable enables/disables the Browse button
# alongside the existing 7 controls.
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

# Edit C6: harvestCurrentConfig reads the cached model fields back
# out into the harvested StageConfig. Inserted alongside the existing
# 7 control harvests, just before the return.
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

# Edit C7: append the new methods (onBrowseCheckpointClicked,
# updateModelRowFromCache) at the END of the file, just before the
# closing namespace brace. Keeps the patch localized.
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
    print("Applying PASS 9: Checkpoint picker for chain stages")
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
    h_changed = apply_edits(h_path, HEADER_EDITS, HEADER_MARKER, ".pre_pass9.bak")
    print()

    if not h_changed:
        print(CPP_REL)
        cpp_changed = apply_edits(cpp_path, CPP_EDITS, CPP_MARKER, ".pre_pass9.bak")
        print()
        if not cpp_changed:
            print("Done -- PASS 9 was already applied (no-op).")
            return 0
        else:
            print("Warning: header already had marker but cpp did not.")
            print("Cpp has now been updated; investigate if unexpected.")
            return 0

    print(CPP_REL)
    cpp_changed = apply_edits(cpp_path, CPP_EDITS, CPP_MARKER, ".pre_pass9.bak")
    print()

    if not cpp_changed:
        print("ERROR: header edit succeeded but cpp edit failed.")
        print("       Restore ChainConfigPanelWidget.h.pre_pass9.bak and investigate.")
        return 2

    print("Done -- PASS 9 applied.")
    print()
    print("Verify:")
    print("  1. .\\scripts\\dev\\run_ui.ps1")
    print("  2. Build should succeed -- ChainConfigPanelWidget.cpp recompiles.")
    print("  3. Open Chain mode. + add stage -> T2I.")
    print("  4. Config panel: new MODEL row at top with 'Browse' button.")
    print("  5. Click Browse -> CatalogPickerDialog opens.")
    print("  6. Pick a checkpoint -> MODEL row updates with name + path.")
    print("  7. Type a prompt in the dialog bar. Click REGENERATE.")
    print("  8. EXPECTED: the stage actually generates an image. The")
    print("     chain studio loop is closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
