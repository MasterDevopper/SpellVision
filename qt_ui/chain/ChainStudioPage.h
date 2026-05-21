#pragma once

// SpellVision — Chain Studio page (Pass 7a: scaffold).
//
// Track B begins here. This is the visible page that replaces HomePage
// in the shell rail. The v3 fixed-workspace mockup lives here.
//
// Pass 7a scope (THIS PASS):
//   - Outer column layout (full-bleed, 14/16 padding per v3 mockup)
//   - Pinned top strip placeholder (56px tall)
//   - Thin horizontal chain rail placeholder
//   - Main 1fr / 318px split: canvas region + config panel region
//   - All four regions are visible, themed via ThemeManager tokens,
//     LABELED with what will go inside them. No actual widgets, no
//     real chain data binding, no engine wiring.
//
// Later passes (NOT in 7a):
//   - 7b: populate the rail with stage chips (against stub Chain data)
//   - 7c: canvas + variation pager (against stub variations)
//   - 7d: config panel + dialog bar + + picker
//   - 8 : wire to real ChainEngine, including the one-line
//         MainWindow::buildWorkerGenerationRequest forward of
//         queue_item_id flagged in Pass 4b
//   - 9 : full shell routing audit (the Pass 7a routing nudge is
//         minimal — Pass 9 settles it properly)
//   - 10: polish + edge cases
//
// Why this incremental cut: the v3 mockup is too dense for a single
// page-creation pass. Cutting along structural seams (shell -> rail
// -> canvas -> config) means each sub-pass is small, compilable, and
// visually reviewable in isolation.

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
    // Uses panel0 background, stroke border, body radius — same
    // tokens existing pages use, so the scaffold sits cleanly in
    // the shell's visual language.
    void applyPlaceholderStyle(QWidget *region, const QString &debugLabel);

    // Region pointers kept on the instance for later passes (7b-7d
    // will populate them; 8 will bind them to engine signals).
    QWidget *topStrip_     = nullptr;
    QWidget *chainRail_    = nullptr;
    QWidget *canvas_       = nullptr;
    QWidget *configPanel_  = nullptr;

    // --- CHAIN STUDIO PASS 7B RAIL ---
    // Stub chain used while Track B is built against placeholder
    // data. Pass 8 will replace this with a live ChainEngine
    // reference and bind to engine signals.
    Chain stubChain_;
    QString selectedStageId_;
    void buildStubChain();
    void onRailStageSelected(const QString &stageId);
    void onRailAddStageRequested();

    // --- CHAIN STUDIO PASS 7C CANVAS ---
    // Cached pointer to the canvas widget so the rail's selection
    // handler can route to it. Pass 8 will replace this with a
    // proper engine-driven signal flow.
    ChainCanvasWidget *canvasWidget_ = nullptr;
    void onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx);
    void onCanvasLockRequested(const QString &stageId);

    // --- CHAIN STUDIO PASS 7D1 CONFIG PANEL ---
    // Cached pointer to the config panel so the rail's selection
    // handler can route to it. Pass 8 will harvest the panel's
    // edited config when Regenerate is clicked and route to
    // engine.regenerate(stageId, config).
    ChainConfigPanelWidget *configPanelWidget_ = nullptr;
    void onConfigRegenerateRequested(const QString &stageId);

    // --- CHAIN STUDIO PASS 7D2 DIALOG BAR ---
    // Cached pointer to the top dialog bar. The bar emits image
    // selection, prompt edits, and add-stage requests. Pass 8
    // wires them to engine mutations.
    ChainDialogBarWidget *dialogBarWidget_ = nullptr;
    void onDialogInputImageSelected(const QString &path);
    void onDialogPromptChanged(const QString &text);
};

} // namespace spellvision::chain
