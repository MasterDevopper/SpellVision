#!/usr/bin/env python3
"""
PASS 9.5: LoRA stack for chain stages
=====================================

Scope
-----
Adds a LORAS section to ChainConfigPanelWidget, sitting between the
MODEL row (Pass 9) and the existing 7 sampling controls. Lets the
user add, replace, and clear LoRAs on T2I / I2I / T2V / I2V stages.

Per Young's clarification (the V2V kind doesn't exist in the engine
today, and UltraShape is 3D-only and orthogonal to LoRA):
  - LoRA section visible on: T2I, I2I, T2V, I2V
  - LoRA section hidden on:  I2_3D, Audio
  - V2V deferred until the engine learns about it
  - UltraShape deferred to its own future pass

Reuses LoraStackController + ModelStackState from
spellvision::assets -- zero new infrastructure. Same pattern as
ImageGenerationPage's LoRA stack management.

Per-stage cache vector + display-resolver map live on the widget,
mirroring the model-fields pattern from Pass 9. applyConfigToControls
translates engine LoraEntry -> controller LoraStackEntry on stage
switch; harvestCurrentConfig translates back on Regenerate.

Atomic-across-files validation
------------------------------
This script implements the methodology fix from the Pass 9
retrospective: ALL anchors across BOTH files validate BEFORE EITHER
file is written. If any anchor mismatches, no file is modified and
no backup is created. The original Pass 9 script's "atomic within
a file, not across files" pattern left header and cpp inconsistent
when the cpp anchor failed; that can't happen here.

Files
-----
  qt_ui/chain/ChainConfigPanelWidget.h
  qt_ui/chain/ChainConfigPanelWidget.cpp

  Backups (written only on full success):
    qt_ui/chain/ChainConfigPanelWidget.h.pre_pass9_5.bak
    qt_ui/chain/ChainConfigPanelWidget.cpp.pre_pass9_5.bak

Idempotency
-----------
Marker-guarded by "// --- CHAIN STUDIO PASS 9.5:" in both files.
Re-run is a clean no-op for already-applied files.

Verification
------------
  1. .\\scripts\\dev\\run_ui.ps1
  2. Build should succeed; ChainConfigPanelWidget.cpp recompiles.
  3. Open Chain mode, + add stage -> T2I.
  4. Config panel: between MODEL and SAMPLER rows there's now a
     LORAS section with "No LoRAs in stack", [Add LoRA] [Clear].
  5. Click "Add LoRA" -> CatalogPickerDialog opens with the loras
     subdir (143+ LoRAs from D:/AI_ASSETS/models/loras).
  6. Pick one. Row appears in the stack with weight 1.00 and an
     enabled toggle. Summary updates: "1 in stack, 1 enabled".
  7. Click Regenerate. The harvested config carries the LoRA
     through to MainWindow::submitChainGenerationRequest, which
     forwards it into buildWorkerGenerationRequest's existing
     LoRA pathway (same as ImageGenerationPage already uses).
  8. Switch to a Locked stage (Pass 12 polish) or to a 3D stage
     after engine ever supports it: LORAS section hides.
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
HEADER_MARKER = "// --- CHAIN STUDIO PASS 9.5:"

HEADER_EDITS = [

# Edit H1: add QMap to the Qt include block + LoraStackController to
# the assets namespace forward decls. ModelStackState pulls in the
# LoraStackEntry struct definition.
(
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
class QVBoxLayout;

namespace spellvision::widgets
{
class ClickOnlyComboBox;
}""",

"""#include "chain/ChainModel.h"

// --- CHAIN STUDIO PASS 9.5: LoRA stack dependencies ---
#include "assets/ModelStackState.h"

#include <QJsonObject>
#include <QMap>
#include <QString>
#include <QVector>
#include <QWidget>

class QComboBox;
class QDoubleSpinBox;
class QFrame;
class QLabel;
class QPushButton;
class QSpinBox;
class QVBoxLayout;

namespace spellvision::widgets
{
class ClickOnlyComboBox;
}

// --- CHAIN STUDIO PASS 9.5: LoraStackController forward decl ---
namespace spellvision::assets
{
class LoraStackController;
}""",
),

# Edit H2: add the new private slots after Pass 9's
# onBrowseCheckpointClicked + the new helper after
# updateModelRowFromCache.
(
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

"""private slots:
    void onRegenerateClicked();
    // --- CHAIN STUDIO PASS 9: model picker slot ---
    void onBrowseCheckpointClicked();
    // --- CHAIN STUDIO PASS 9.5: LoRA stack slots ---
    void onAddLoraClicked();
    void onClearLorasClicked();
    void onReplaceLora(int index);

private:
    // Resync header + body controls from the current selection. Safe
    // to call repeatedly; never reconstructs widgets.
    void refresh();

    // --- CHAIN STUDIO PASS 9: model picker helpers ---
    // Refresh the MODEL row UI from the lastPickedModel* cache (which
    // applyConfigToControls populates when the stage selection
    // changes). Called whenever the cache is mutated.
    void updateModelRowFromCache();

    // --- CHAIN STUDIO PASS 9.5: LoRA stack helpers ---
    // Rebuild loraStack_ (controller cache) from the current stage's
    // config.loras vector. Called on stage switch. Also rebuilds the
    // display-resolver map by scanning the LoRA catalog so the
    // controller can show readable names for already-stacked entries.
    void rebuildLoraCacheFromStage();""",
),

# Edit H3: add the new member widgets + state alongside the model
# cache members and before the spinbox/combo bank.
(
"""    // --- CHAIN STUDIO PASS 9: per-stage model selection cache ---
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

    spellvision::widgets::ClickOnlyComboBox *samplerCombo_   = nullptr;""",

"""    // --- CHAIN STUDIO PASS 9: per-stage model selection cache ---
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

    // --- CHAIN STUDIO PASS 9.5: LoRA stack widgets + state ---
    // The whole assembly wrapped in loraSection_ so it can be hidden
    // on stages that don't accept LoRAs (I2_3D, Audio) and shown only
    // on T2I / I2I / T2V / I2V.
    QWidget     *loraSection_         = nullptr;
    QLabel      *loraSummaryLabel_    = nullptr;
    QWidget     *loraContainer_       = nullptr;  // controller renders rows here
    QVBoxLayout *loraContainerLayout_ = nullptr;
    QPushButton *addLoraButton_       = nullptr;
    QPushButton *clearLoraButton_     = nullptr;

    // The controller owns per-row UI and mutates loraStack_ in place.
    // We translate engine LoraEntry <-> controller LoraStackEntry at
    // apply/harvest time; the structs are field-identical.
    spellvision::assets::LoraStackController *loraController_ = nullptr;
    QVector<spellvision::assets::LoraStackEntry> loraStack_;

    // Value -> display lookup, populated each time we scan the LoRA
    // catalog (lazily, in onAddLoraClicked and rebuildLoraCacheFromStage).
    // Lets the controller's displayResolver turn a value-only entry
    // (e.g. one loaded from a saved StageConfig) into a readable name.
    QMap<QString, QString> loraDisplayByValue_;

    spellvision::widgets::ClickOnlyComboBox *samplerCombo_   = nullptr;""",
),
]

# ---------------------------------------------------------------
# ChainConfigPanelWidget.cpp edits
# ---------------------------------------------------------------

CPP_REL = "qt_ui/chain/ChainConfigPanelWidget.cpp"
CPP_MARKER = "// --- CHAIN STUDIO PASS 9.5:"

CPP_EDITS = [

# Edit C1: add includes -- LoraStackController, QFileInfo (for filename
# fallback in displayResolver), QFileDialog (no -- not needed, picker
# does that). Inserted after Pass 9's includes block.
(
"""// --- CHAIN STUDIO PASS 9: model picker dependencies ---
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

"""// --- CHAIN STUDIO PASS 9: model picker dependencies ---
#include "assets/AssetCatalogScanner.h"
#include "assets/CatalogPickerDialog.h"
#include "generation/OutputPathHelpers.h"

// --- CHAIN STUDIO PASS 9.5: LoRA stack dependencies ---
#include "assets/LoraStackController.h"

// --- PASS 7D1 FIXUP CLICKONLY INCLUDE ---
#include "widgets/ClickOnlyComboBox.h"
#include "ThemeManager.h"
#include "widgets/SectionCardWidgets.h"

#include <QAbstractSpinBox>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QScrollArea>
#include <QSizePolicy>
#include <QSpinBox>
#include <QVBoxLayout>""",
),

# Edit C2: add the anonymous-namespace LoraEntry <-> LoraStackEntry
# translation helpers. Insert before the `} // namespace { ... }`
# closer of the existing anonymous namespace. The existing anon ns
# starts with `configureComboBoxLocal` -- I'll piggyback on a stable
# anchor inside it.
(
"""// --- duplicated from ImageGenerationPage.cpp:298-340 ---
// These helpers aren't in a shared header yet. Pass 10 polish can
// promote them to widgets/SectionCardWidgets.h alongside createCard
// etc., at which point we delete these local copies.

void configureComboBoxLocal(QComboBox *combo)""",

"""// --- duplicated from ImageGenerationPage.cpp:298-340 ---
// These helpers aren't in a shared header yet. Pass 10 polish can
// promote them to widgets/SectionCardWidgets.h alongside createCard
// etc., at which point we delete these local copies.

// --- CHAIN STUDIO PASS 9.5: engine <-> controller LoRA translators ---
// engine's LoraEntry and controller's LoraStackEntry have the same 4
// fields with the same types; this is a field-by-field memcpy in
// spirit. Kept as free functions so the type translation is local to
// this TU and doesn't pollute the chain or assets namespaces.
spellvision::assets::LoraStackEntry toLoraStackEntry(
    const spellvision::chain::LoraEntry &e)
{
    return {e.display, e.value, e.weight, e.enabled};
}

spellvision::chain::LoraEntry toEngineLoraEntry(
    const spellvision::assets::LoraStackEntry &e)
{
    return {e.display, e.value, e.weight, e.enabled};
}

void configureComboBoxLocal(QComboBox *combo)""",
),

# Edit C3: insert LORAS section construction in the constructor,
# after the MODEL row is added (`bodyLayout->addWidget(modelRow_);`)
# and before the "---- The seven controls ----" comment.
(
"""        modelRowLayout->addWidget(modelInnerRow);
    }
    bodyLayout->addWidget(modelRow_);

    // ---- The seven controls ----
    samplerCombo_ = new ClickOnlyComboBox(bodyHolder_);""",

"""        modelRowLayout->addWidget(modelInnerRow);
    }
    bodyLayout->addWidget(modelRow_);

    // --- CHAIN STUDIO PASS 9.5: LORAS section ---
    // Section structure:
    //   [ LORAS — caption ]
    //   [ summary label: "No LoRAs in stack" / "N in stack, M enabled" ]
    //   [ container — controller renders rows here, one per LoRA ]
    //   [ [Add LoRA]  [Clear Stack] ]
    // The whole thing wrapped in loraSection_ so refresh() can hide
    // it on stages that don't accept LoRAs (I2_3D / Audio).
    loraSection_ = new QWidget(bodyHolder_);
    {
        auto *sectionLayout = new QVBoxLayout(loraSection_);
        sectionLayout->setContentsMargins(0, 0, 0, 0);
        sectionLayout->setSpacing(4);

        auto *caption = new QLabel(QStringLiteral("LoRAs"), loraSection_);
        caption->setStyleSheet(QStringLiteral(
            "QLabel { color: %1; font-size: 10px; font-weight: 700; "
            "letter-spacing: 0.6px; text-transform: uppercase; }"
        ).arg(tm.textMutedColor().name()));
        sectionLayout->addWidget(caption);

        loraSummaryLabel_ = new QLabel(QStringLiteral("No LoRAs in stack"),
                                       loraSection_);
        loraSummaryLabel_->setWordWrap(true);
        loraSummaryLabel_->setStyleSheet(QStringLiteral(
            "QLabel { color: %1; font-size: 11px; }"
        ).arg(tm.textSecondaryColor().name()));
        sectionLayout->addWidget(loraSummaryLabel_);

        loraContainer_ = new QWidget(loraSection_);
        loraContainerLayout_ = new QVBoxLayout(loraContainer_);
        loraContainerLayout_->setContentsMargins(0, 0, 0, 0);
        loraContainerLayout_->setSpacing(4);
        sectionLayout->addWidget(loraContainer_);

        auto *buttonRow = new QWidget(loraSection_);
        auto *buttonRowLayout = new QHBoxLayout(buttonRow);
        buttonRowLayout->setContentsMargins(0, 0, 0, 0);
        buttonRowLayout->setSpacing(tm.spacing(ThemeManager::Spacing::Tight));

        addLoraButton_ = new QPushButton(QStringLiteral("Add LoRA"), buttonRow);
        addLoraButton_->setCursor(Qt::PointingHandCursor);
        connect(addLoraButton_, &QPushButton::clicked,
                this, &ChainConfigPanelWidget::onAddLoraClicked);
        buttonRowLayout->addWidget(addLoraButton_);

        clearLoraButton_ = new QPushButton(QStringLiteral("Clear"), buttonRow);
        clearLoraButton_->setCursor(Qt::PointingHandCursor);
        connect(clearLoraButton_, &QPushButton::clicked,
                this, &ChainConfigPanelWidget::onClearLorasClicked);
        buttonRowLayout->addWidget(clearLoraButton_);
        buttonRowLayout->addStretch(1);

        sectionLayout->addWidget(buttonRow);
    }
    bodyLayout->addWidget(loraSection_);

    // Construct the controller and bind it to our cache vector +
    // section widgets. The controller owns per-row UI; we own the
    // cache vector lifetime and the Add/Clear button connections.
    loraController_ = new spellvision::assets::LoraStackController(this);
    spellvision::assets::LoraStackBindings loraBindings;
    loraBindings.container    = loraContainer_;
    loraBindings.layout       = loraContainerLayout_;
    loraBindings.summaryLabel = loraSummaryLabel_;
    loraBindings.clearButton  = clearLoraButton_;
    loraController_->bind(&loraStack_, loraBindings);
    loraController_->setDisplayResolver([this](const QString &value) -> QString {
        auto it = loraDisplayByValue_.constFind(value);
        if (it != loraDisplayByValue_.constEnd() && !it.value().isEmpty())
            return it.value();
        return QFileInfo(value).fileName();
    });
    loraController_->setChangedCallback([]() {
        // Cache vector has changed; controller already rebuilt rows
        // and refreshed summary label. Engine push happens only at
        // Regenerate (Option A: harvest-on-Regenerate, no live binding).
    });
    loraController_->setReplaceRequestedCallback([this](int index) {
        onReplaceLora(index);
    });

    // ---- The seven controls ----
    samplerCombo_ = new ClickOnlyComboBox(bodyHolder_);""",
),

# Edit C4: setEmptyState gains loraSection_ in its hide/show set, BUT
# only as the "no stage selected" gate. The per-kind gate happens in
# refresh() (Edit C8) so this just handles the "no selection" case.
(
"""    // --- CHAIN STUDIO PASS 9: MODEL row visibility ---
    if (modelRow_ != nullptr)
        modelRow_->setVisible(!empty);
    if (regenerateButton_ != nullptr)
        regenerateButton_->setEnabled(!empty);
}""",

"""    // --- CHAIN STUDIO PASS 9: MODEL row visibility ---
    if (modelRow_ != nullptr)
        modelRow_->setVisible(!empty);
    // --- CHAIN STUDIO PASS 9.5: LORAS section visibility ---
    // setEmptyState only handles the "no stage selected" hide. The
    // per-kind hide (I2_3D / Audio) happens in refresh() since those
    // require currentStage() and a kind switch.
    if (loraSection_ != nullptr)
        loraSection_->setVisible(!empty);
    if (regenerateButton_ != nullptr)
        regenerateButton_->setEnabled(!empty);
}""",
),

# Edit C5: applyConfigToControls populates the LoRA cache from the
# incoming stage's config.loras and asks the controller to rebuild.
# Inserted after the Pass 9 model-field cache copy block.
(
"""    // --- CHAIN STUDIO PASS 9: copy model fields into per-stage cache ---
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

"""    // --- CHAIN STUDIO PASS 9: copy model fields into per-stage cache ---
    // No signals to block here; these are plain QString members. The
    // updateModelRowFromCache() call refreshes the MODEL row label.
    lastPickedModelValue_    = config.model;
    lastPickedModelDisplay_  = config.modelDisplay;
    lastPickedModelFamily_   = config.modelFamily;
    lastPickedModelModality_ = config.modelModality;
    lastPickedModelRole_     = config.modelRole;
    lastPickedModelMetadata_ = config.selectedVideoStack;
    updateModelRowFromCache();

    // --- CHAIN STUDIO PASS 9.5: refresh LoRA cache from stage ---
    // rebuildLoraCacheFromStage() reads currentStage()->config.loras
    // (the same Chain we just synced via setChain or setSelectedStageId)
    // and translates engine LoraEntry -> controller LoraStackEntry,
    // then asks the controller to rebuild rows. Safe to call here
    // because currentStage() is now the same stage `config` came from.
    rebuildLoraCacheFromStage();
}""",
),

# Edit C6: harvestCurrentConfig writes the LoRA cache back into
# harvested.loras. Inserted after the Pass 9 model-field harvest block.
(
"""    // --- CHAIN STUDIO PASS 9: harvest model fields from cache ---
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

"""    // --- CHAIN STUDIO PASS 9: harvest model fields from cache ---
    // These were populated by applyConfigToControls on stage switch
    // and by onBrowseCheckpointClicked on user pick. No null guards
    // needed since they are plain members, not pointer widgets.
    harvested.model              = lastPickedModelValue_;
    harvested.modelDisplay       = lastPickedModelDisplay_;
    harvested.modelFamily        = lastPickedModelFamily_;
    harvested.modelModality      = lastPickedModelModality_;
    harvested.modelRole          = lastPickedModelRole_;
    harvested.selectedVideoStack = lastPickedModelMetadata_;

    // --- CHAIN STUDIO PASS 9.5: harvest LoRA stack from cache ---
    // Translate controller LoraStackEntry -> engine LoraEntry. The
    // structs are field-identical; toEngineLoraEntry is a 1-liner.
    harvested.loras.clear();
    harvested.loras.reserve(loraStack_.size());
    for (const auto &e : loraStack_)
        harvested.loras.append(toEngineLoraEntry(e));

    return harvested;
}""",
),

# Edit C7: setControlsEditable enables/disables Add/Clear LoRA buttons.
(
"""    // --- CHAIN STUDIO PASS 9: Browse button follows lock state ---
    // Locked stages should not be re-pointed at a different model;
    // unlock the stage first.
    if (modelBrowseButton_ != nullptr)
        modelBrowseButton_->setEnabled(editable);
}""",

"""    // --- CHAIN STUDIO PASS 9: Browse button follows lock state ---
    // Locked stages should not be re-pointed at a different model;
    // unlock the stage first.
    if (modelBrowseButton_ != nullptr)
        modelBrowseButton_->setEnabled(editable);
    // --- CHAIN STUDIO PASS 9.5: LoRA buttons follow lock state ---
    if (addLoraButton_ != nullptr)
        addLoraButton_->setEnabled(editable);
    if (clearLoraButton_ != nullptr)
        clearLoraButton_->setEnabled(editable);
}""",
),

# Edit C8: refresh() — per-kind LORA section visibility gate.
# Insert right before the setControlsEditable call near the bottom
# of refresh().
(
"""    applyConfigToControls(s->config);

    // Lock disables editing; everything else allows it. Generating /
    // Queued probably shouldn't be edited mid-flight, but the engine's
    // canGenerate / lifecycle is the source of truth for "can I run a
    // new generation" — config edits during Generating are harmless
    // since they only apply on the next regenerate.
    const bool editable = (s->status != StageStatus::Locked);
    setControlsEditable(editable);""",

"""    applyConfigToControls(s->config);

    // --- CHAIN STUDIO PASS 9.5: per-kind LORAS visibility ---
    // LoRAs only meaningfully apply to image/video-producing stages.
    // UltraShape (3D-only) is its own future section. Audio gets
    // neither today.
    const bool kindAllowsLora =
        s->kind == StageKind::T2I ||
        s->kind == StageKind::I2I ||
        s->kind == StageKind::T2V ||
        s->kind == StageKind::I2V;
    if (loraSection_ != nullptr)
        loraSection_->setVisible(kindAllowsLora);

    // Lock disables editing; everything else allows it. Generating /
    // Queued probably shouldn't be edited mid-flight, but the engine's
    // canGenerate / lifecycle is the source of truth for "can I run a
    // new generation" — config edits during Generating are harmless
    // since they only apply on the next regenerate.
    const bool editable = (s->status != StageStatus::Locked);
    setControlsEditable(editable);""",
),

# Edit C9: append new method bodies (onAddLoraClicked,
# onClearLorasClicked, onReplaceLora, rebuildLoraCacheFromStage)
# right before the closing namespace brace.
(
"""void ChainConfigPanelWidget::onRegenerateClicked()
{
    if (selectedStageId_.isEmpty())
        return;
    emit regenerateRequested(selectedStageId_);
}

} // namespace spellvision::chain""",

"""void ChainConfigPanelWidget::onRegenerateClicked()
{
    if (selectedStageId_.isEmpty())
        return;
    emit regenerateRequested(selectedStageId_);
}

// --- CHAIN STUDIO PASS 9.5: Add LoRA handler ---
// Scan the loras/ subdirectory under the models root, populate the
// value->display map, open the CatalogPickerDialog, and on accept
// ask the controller to add the picked LoRA. The controller's
// changedCallback fires automatically; we don't need to do anything
// else here.
void ChainConfigPanelWidget::onAddLoraClicked()
{
    using spellvision::assets::CatalogEntry;
    using spellvision::assets::CatalogPickerDialog;
    using spellvision::assets::persistRecentSelection;
    using spellvision::assets::scanCatalog;
    using spellvision::generation::chooseModelsRootPath;

    if (loraController_ == nullptr)
        return;

    const QString modelsRoot = chooseModelsRootPath();
    const QVector<CatalogEntry> entries =
        scanCatalog(modelsRoot, QStringLiteral("loras"));

    // Refresh the display-resolver map so any already-stacked entries
    // (loaded from a saved StageConfig that we don't have full catalog
    // metadata for) can resolve their display names too.
    for (const CatalogEntry &entry : entries)
        loraDisplayByValue_.insert(entry.value, entry.display);

    const QString recentKey = QStringLiteral("chain_studio/recent_loras");
    CatalogPickerDialog dialog(QStringLiteral("Choose LoRA"), entries,
                               /*currentValue=*/QString(),
                               recentKey, this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    const QString value   = dialog.selectedValue();
    const QString display = dialog.selectedDisplay();
    if (value.trimmed().isEmpty())
        return;

    loraController_->addOrUpdate(value, display);
    persistRecentSelection(recentKey, value);
}

// --- CHAIN STUDIO PASS 9.5: Clear handler ---
// Wraps controller->clear() so we have a stable connect target.
// (The Add/Clear button row's clearButton_ is also bound directly
// via the LoraStackBindings, but that path may try to clear via the
// bound clearButton_ raw click signal; routing through this method
// is the more explicit pattern.)
void ChainConfigPanelWidget::onClearLorasClicked()
{
    if (loraController_ != nullptr)
        loraController_->clear();
}

// --- CHAIN STUDIO PASS 9.5: Replace handler ---
// Fires when the user clicks an existing LoRA row in the stack. The
// controller passes the row index; we open the same picker dialog
// pre-selected to that row's current value, and on accept ask the
// controller to replace at that index.
void ChainConfigPanelWidget::onReplaceLora(int index)
{
    using spellvision::assets::CatalogEntry;
    using spellvision::assets::CatalogPickerDialog;
    using spellvision::assets::persistRecentSelection;
    using spellvision::assets::scanCatalog;
    using spellvision::generation::chooseModelsRootPath;

    if (loraController_ == nullptr)
        return;
    if (index < 0 || index >= loraStack_.size())
        return;

    const QString modelsRoot = chooseModelsRootPath();
    const QVector<CatalogEntry> entries =
        scanCatalog(modelsRoot, QStringLiteral("loras"));

    for (const CatalogEntry &entry : entries)
        loraDisplayByValue_.insert(entry.value, entry.display);

    const QString currentValue = loraStack_.at(index).value;
    const QString recentKey = QStringLiteral("chain_studio/recent_loras");
    CatalogPickerDialog dialog(QStringLiteral("Replace LoRA"), entries,
                               currentValue, recentKey, this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    const QString value   = dialog.selectedValue();
    const QString display = dialog.selectedDisplay();
    if (value.trimmed().isEmpty())
        return;

    loraController_->replaceAt(index, value, display);
    persistRecentSelection(recentKey, value);
}

// --- CHAIN STUDIO PASS 9.5: Rebuild LoRA cache from current stage ---
// Called from applyConfigToControls. Translates currentStage()->
// config.loras (engine LoraEntry vector) into loraStack_ (controller
// LoraStackEntry vector), then asks the controller to rebuild rows.
//
// Also refreshes loraDisplayByValue_ by scanning the catalog, so any
// LoRAs loaded from a saved StageConfig (where we may not have a
// display name) can still resolve to a readable label.
void ChainConfigPanelWidget::rebuildLoraCacheFromStage()
{
    using spellvision::assets::CatalogEntry;
    using spellvision::assets::scanCatalog;
    using spellvision::generation::chooseModelsRootPath;

    if (loraController_ == nullptr)
        return;

    loraStack_.clear();

    const Stage *s = currentStage();
    if (s != nullptr)
    {
        loraStack_.reserve(s->config.loras.size());
        for (const LoraEntry &e : s->config.loras)
            loraStack_.append(toLoraStackEntry(e));
    }

    // Lazy catalog scan to backfill displays. Cheap; well under 100ms
    // on typical SSDs. Pass 11+ may cache this if profiling complains.
    const QVector<CatalogEntry> entries =
        scanCatalog(chooseModelsRootPath(), QStringLiteral("loras"));
    for (const CatalogEntry &entry : entries)
        loraDisplayByValue_.insert(entry.value, entry.display);

    loraController_->rebuild();
}

} // namespace spellvision::chain""",
),

]


def normalize_lf(text: str) -> str:
    return text.replace("\r\n", "\n")


def write_with_crlf(path: Path, body_lf: str) -> None:
    text = body_lf.replace("\r\n", "\n").replace("\n", NL)
    path.write_bytes(text.encode("utf-8"))


def validate_file(path: Path, edits, marker):
    """
    Returns one of:
      ("skip", None, None)            — already applied, marker present
      ("ok", new_body, raw_bytes)     — all anchors matched, in-memory new body ready
      ("error", err_message, None)    — at least one anchor mismatched; no changes ready
    Reads file, normalizes line endings to LF for matching, applies edits
    in memory (no write yet).
    """
    if not path.exists():
        return ("error", f"file does not exist: {path}", None)

    raw_bytes = path.read_bytes()
    raw_text = raw_bytes.decode("utf-8")
    body = normalize_lf(raw_text)

    if marker in body:
        return ("skip", None, None)

    # validate every anchor matches exactly once
    for i, (anchor, _replacement) in enumerate(edits, 1):
        count = body.count(anchor)
        if count != 1:
            preview = anchor.split("\n")[0][:80]
            return ("error",
                    f"{path.name} edit #{i} anchor matches {count} times "
                    f"(expected 1). First line: {preview!r}",
                    None)

    # apply in memory
    for anchor, replacement in edits:
        body = body.replace(anchor, replacement, 1)

    if marker not in body:
        return ("error",
                f"{path.name}: post-edit body missing marker {marker!r}",
                None)

    return ("ok", body, raw_bytes)


def main() -> int:
    print("Applying PASS 9.5: LoRA stack for chain stages")
    print(f"  Project root: {PROJECT_ROOT}")
    print("  (atomic-across-files: validate BOTH, then write BOTH)")
    print()

    h_path   = PROJECT_ROOT / HEADER_REL
    cpp_path = PROJECT_ROOT / CPP_REL

    # === PHASE 1: validate everything ===
    print("Phase 1: validating all anchors across all files...")
    print(f"  {HEADER_REL}")
    h_status, h_body, h_raw = validate_file(h_path, HEADER_EDITS, HEADER_MARKER)
    print(f"  {CPP_REL}")
    c_status, c_body, c_raw = validate_file(cpp_path, CPP_EDITS, CPP_MARKER)
    print()

    # If either file errored, abort with no writes.
    if h_status == "error":
        print(f"  ERROR: {h_body}")
        print("  No files written.")
        return 2
    if c_status == "error":
        print(f"  ERROR: {c_body}")
        print("  No files written.")
        return 2

    # Both skipped: clean idempotent no-op.
    if h_status == "skip" and c_status == "skip":
        print("Done -- PASS 9.5 was already applied (no-op).")
        return 0

    # Mixed states are surprising but recoverable: write whichever isn't
    # already applied. Document what we're doing.
    if h_status == "skip" and c_status == "ok":
        print("  Note: header already had marker; only cpp needs writing.")
    elif h_status == "ok" and c_status == "skip":
        print("  Note: cpp already had marker; only header needs writing.")
    else:
        print("  Both files need writing.")

    # === PHASE 2: write everything that needs writing ===
    print()
    print("Phase 2: writing validated files...")

    if h_status == "ok":
        backup_h = h_path.with_suffix(h_path.suffix + ".pre_pass9_5.bak")
        backup_h.write_bytes(h_raw)
        print(f"  Backup: {backup_h.name}")
        write_with_crlf(h_path, h_body)
        print(f"  Rewrote: {h_path.name}")

    if c_status == "ok":
        backup_c = cpp_path.with_suffix(cpp_path.suffix + ".pre_pass9_5.bak")
        backup_c.write_bytes(c_raw)
        print(f"  Backup: {backup_c.name}")
        write_with_crlf(cpp_path, c_body)
        print(f"  Rewrote: {cpp_path.name}")

    print()
    print("Done -- PASS 9.5 applied.")
    print()
    print("Verify:")
    print("  1. .\\scripts\\dev\\run_ui.ps1")
    print("  2. Build should succeed; ChainConfigPanelWidget.cpp recompiles.")
    print("  3. Open Chain mode, + add stage -> T2I.")
    print("  4. Config panel: new LORAS section between MODEL and SAMPLER.")
    print("  5. Click 'Add LoRA' -> picker opens with loras subdir.")
    print("  6. Pick a LoRA, see it appear in the stack with weight 1.00.")
    print("  7. Click Regenerate -> image generates with the LoRA applied.")
    print("  8. (Sanity) Try a video stage if you have video stacks: LORAS")
    print("     still visible. 3D / Audio kinds would hide it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
