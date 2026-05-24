#pragma once

// SpellVision — Chain Studio config panel (Pass 7d.1).
//
// The right-side 318px column of ChainStudioPage. Shows the SELECTED
// stage's configuration: sampler, scheduler, steps, CFG, seed, width,
// height. Driven by setSelectedStageId() — same selection input the
// rail and canvas already use.
//
// Per the v3 mockup:
//
//   [ cfg-h: title + subtitle ]            <-- header, top-section
//   [ cfg-body: scrollable controls ]      <-- the seven controls
//   [ cfg-foot: Regenerate button ]        <-- bottom-section
//
// Editability: when the selected stage's status is Locked, the
// controls are disabled (display-only). For Draft / Completed /
// Failed they're editable. (Generating/Queued probably also disabled,
// but that's a Pass 10 polish detail.)
//
// Pass 7d.1 emits NO signals back to the page — edits update an
// internal copy of the stage config that Pass 8 will harvest when
// Regenerate is clicked, at which point engine.regenerate() will
// receive the modified config. For 7d.1 the Regenerate footer button
// is wired as a stub.
//
// Reuses: spellvision::widgets::{createCard, createSectionTitle,
// ClickOnlyComboBox}. The configureComboBox / configureSpinBox /
// configureDoubleSpinBox helpers are duplicated locally in the .cpp
// (anonymous namespace) since they aren't in a shared header yet
// (Pass 10 polish can promote them).

#include "chain/ChainModel.h"

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
}

namespace spellvision::chain
{

class ChainConfigPanelWidget : public QWidget
{
    Q_OBJECT

public:
    explicit ChainConfigPanelWidget(QWidget *parent = nullptr);

    // Bind to the source chain. Re-renders with the currently
    // selected stage (or empty state if no selection).
    void setChain(const Chain &chain);

    // Switch which stage's config the panel shows. Same selection
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

signals:
    // Footer Regenerate button clicked. Pass 8 wires this to
    // engine.regenerate(stageId) (with the modified StageConfig
    // harvested via takeEditedConfig()).
    void regenerateRequested(QString stageId);

private slots:
    void onRegenerateClicked();

private:
    // Resync header + body controls from the current selection. Safe
    // to call repeatedly; never reconstructs widgets.
    void refresh();

    // Locate the currently selected stage. Returns nullptr if not
    // found or selectedStageId_ is empty.
    const Stage *currentStage() const;

    // Apply the seven control values from the given config; updates
    // the controls without firing edit signals (uses blockSignals).
    void applyConfigToControls(const StageConfig &config);

    // Enable/disable all body controls based on stage status. Locked
    // stages are display-only.
    void setControlsEditable(bool editable);

    // Toggle the empty-state vs config-state visual.
    void setEmptyState(bool empty);

    Chain   chain_;
    QString selectedStageId_;

    // ---- header ----
    QLabel *headerTitle_    = nullptr;
    QLabel *headerSubtitle_ = nullptr;

    // ---- body (the seven controls) ----
    QFrame *bodyHolder_     = nullptr;
    QLabel *emptyLabel_     = nullptr;

    spellvision::widgets::ClickOnlyComboBox *samplerCombo_   = nullptr;
    spellvision::widgets::ClickOnlyComboBox *schedulerCombo_ = nullptr;
    QSpinBox                                *stepsSpin_      = nullptr;
    QDoubleSpinBox                          *cfgSpin_        = nullptr;
    QSpinBox                                *seedSpin_       = nullptr;
    QSpinBox                                *widthSpin_      = nullptr;
    QSpinBox                                *heightSpin_     = nullptr;

    // ---- footer ----
    QPushButton *regenerateButton_ = nullptr;
};

} // namespace spellvision::chain
