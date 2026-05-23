#pragma once

// SpellVision -- Chain Studio page (Pass 8a: engine display binding).
//
// Track B's page. This is the visible page that lives in the shell rail
// between Home and T2I. The v3 fixed-workspace mockup is implemented here.
//
// PASS 8A CHANGE (in this pass):
//   - Owns a ChainEngine instance instead of a local stubChain_ Chain.
//   - Widgets read state via engine_->chain() and engine_->canAddStage().
//   - Engine's chainMutated signal -> refreshAllWidgets() slot.
//   - All user-facing mutation handlers (lock, select, regenerate, prompt,
//     upload, add-stage-kind) are Q_UNUSED stubs. Pass 8b will replace
//     each body with engine_-> calls.
//   - Engine bind: store=nullptr, watcher=nullptr, submitFn=rejecting.
//     The engine holds state in memory only -- no persistence, no real
//     submission. Pass 8c will wire the real submitFn / store / watcher.
//
// Before 8a: page mutated a local stubChain_ on every UI interaction;
// the engine class existed but was never instantiated.
// After 8a:  page builds an empty Chain via engine_->newChain(...) and
// displays it. UI interactions are inert until 8b lands.

// --- PASS 7B FIXUP CHAINMODEL INCLUDE ---
#include "chain/ChainModel.h"

#include <QWidget>

class QLabel;

namespace spellvision::chain
{

// --- CHAIN STUDIO PASS 7C CANVAS: forward-declare ChainCanvasWidget ---
class ChainCanvasWidget;
// --- CHAIN STUDIO PASS 7D1 CONFIG PANEL: forward-declare ChainConfigPanelWidget ---
class ChainConfigPanelWidget;
// --- CHAIN STUDIO PASS 7D2 DIALOG BAR: forward-declare ChainDialogBarWidget ---
class ChainDialogBarWidget;
// --- CHAIN STUDIO PASS 8A: forward-declare ChainEngine ---
class ChainEngine;

class ChainStudioPage : public QWidget
{
    Q_OBJECT

public:
    explicit ChainStudioPage(QWidget *parent = nullptr);

private:
    // Build the outer column + the four regions. Each helper returns
    // the QWidget for that region so the constructor stays a clean
    // assembly call rather than a 200-line block.
    QWidget *buildTopStrip();
    QWidget *buildChainRail();
    QWidget *buildCanvas();
    QWidget *buildConfigPanel();

    // Apply ThemeManager-driven styling to a placeholder region.
    void applyPlaceholderStyle(QWidget *region, const QString &debugLabel);

    // Region pointers kept on the instance for later passes (8b will
    // route mutations through engine_; 8c will hook up worker signals).
    QWidget *topStrip_     = nullptr;
    QWidget *chainRail_    = nullptr;
    QWidget *canvas_       = nullptr;
    QWidget *configPanel_  = nullptr;

    // --- CHAIN STUDIO PASS 8A: engine ownership ---
    // The engine owns the canonical Chain. Widgets read via
    // engine_->chain(); mutations go through engine_ methods (wired
    // in Pass 8b). The engine's chainMutated signal triggers
    // refreshAllWidgets(), which fans state out to every widget.
    //
    // The engine is parented to `this` so Qt object ownership
    // handles lifecycle. bind() is called once with null store/
    // watcher and a rejecting submitFn for Pass 8a's display-only
    // wiring.
    ChainEngine *engine_ = nullptr;

    // UI-only selection state. The engine has a chain_.selectedStageId
    // field too, but page selection is driven independently by user
    // clicks on the rail; we don't push it into the engine.
    QString selectedStageId_;

    // Push engine_->chain() out to every widget. Called from the
    // engine's chainMutated signal AND from rail selection changes
    // (which don't mutate the engine but still need widgets to see
    // the new selectedStageId_).
    void refreshAllWidgets();

    // --- rail interaction handlers ---
    void onRailStageSelected(const QString &stageId);
    // --- CHAIN STUDIO PASS 7D3 RECOVERY ---
    void onRailAddStageRequested(QPoint globalPos);
    void showAddStageMenu(QPoint globalPos);
    void onAddStageKindChosen(StageKind kind);

    // --- CHAIN STUDIO PASS 7C CANVAS ---
    ChainCanvasWidget *canvasWidget_ = nullptr;
    void onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx);
    void onCanvasLockRequested(const QString &stageId);

    // --- CHAIN STUDIO PASS 7D1 CONFIG PANEL ---
    ChainConfigPanelWidget *configPanelWidget_ = nullptr;
    void onConfigRegenerateRequested(const QString &stageId);

    // --- CHAIN STUDIO PASS 7D2 DIALOG BAR ---
    ChainDialogBarWidget *dialogBarWidget_ = nullptr;
    void onDialogInputImageSelected(const QString &path);
    void onDialogPromptChanged(const QString &text);
};

} // namespace spellvision::chain
