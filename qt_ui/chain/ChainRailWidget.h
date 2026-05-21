#pragma once

// SpellVision — Chain Studio rail (Pass 7b).
//
// The thin horizontal status display that sits below the top strip in
// ChainStudioPage. Renders a row of stage chips, connectors between
// them, and a trailing "+ add stage" placeholder. Per the v3 mockup:
//
//   [node][conn][node][conn][node]...[+ add stage]
//
// Two widgets in this file because they are tightly coupled and small:
//
//   ChainRailNodeWidget   — one stage chip (148x46 outer, with thumb,
//                            kind label, status dot, variation count,
//                            optional progress bar)
//   ChainRailWidget       — the horizontal container that lays out
//                            nodes + connectors + the add button,
//                            owns selection state, and exposes the
//                            signal Track B passes 7c/7d listen to
//
// Pass 7b populates the rail against STUB chain data (a hardcoded
// Chain struct in ChainStudioPage). Pass 8 swaps the stub for the
// real engine and binds to chainMutated / stageStatusChanged so the
// rail updates live during generation.
//
// The widget reads from spellvision::chain::Chain / Stage / Variation
// — the model defined in Pass 1's ChainModel.h. It does NOT touch the
// engine, store, or watcher; it's a pure renderer + click-to-select
// surface. That separation is what makes Pass 8's wiring trivial.

#include "chain/ChainModel.h"

#include <QPoint>
#include <QString>
#include <QVector>
#include <QWidget>

class QHBoxLayout;
class QLabel;
class QPushButton;
class QScrollArea;

namespace spellvision::chain
{

// ---------------------------------------------------------------------------
// ChainRailNodeWidget — one stage chip
// ---------------------------------------------------------------------------

class ChainRailNodeWidget : public QWidget
{
    Q_OBJECT

public:
    explicit ChainRailNodeWidget(QWidget *parent = nullptr);

    // Replace this node's display from a Stage + the index it sits
    // at in the chain. Re-renders all child widgets in place — does
    // not re-create them, so connect-once signal wiring survives.
    void setStage(const Stage &stage);

    // Mark this node as the rail's current selection (border tint).
    void setSelected(bool selected);

    // The stage id this node currently represents. "" if setStage
    // hasn't been called yet.
    QString stageId() const { return stageId_; }

signals:
    // Emitted when the user clicks anywhere on this node. Carries
    // the stage id so the rail container doesn't need a per-node
    // lookup.
    void clicked(const QString &stageId);

protected:
    void mousePressEvent(QMouseEvent *event) override;

private:
    void rebuildStyle();

    QString    stageId_;
    StageKind  kind_      = StageKind::T2I;
    StageStatus status_   = StageStatus::Draft;
    int        varCount_  = 0;
    bool       selected_  = false;

    QLabel *thumb_      = nullptr;  // colored swatch for now; real
                                    // thumbnail wiring lands in 7c/8
    QLabel *kindLabel_  = nullptr;
    // --- PASS 7B POLISH STRUCTURAL VISUAL: status dot + text split into two children ---
    QLabel *statusDot_  = nullptr;  // colored circle
    QLabel *statusText_ = nullptr;  // "Locked" / "Idle" / etc.
    QLabel *varRow_     = nullptr;  // "3 variations"
};

// ---------------------------------------------------------------------------
// ChainRailWidget — horizontal container managing the row
// ---------------------------------------------------------------------------

class ChainRailWidget : public QWidget
{
    Q_OBJECT

public:
    explicit ChainRailWidget(QWidget *parent = nullptr);

    // Lay out one node per stage in chain.stages, with connectors
    // between them. The trailing "+ add stage" placeholder's enabled
    // state should be set separately via setCanAddStage() — keeping
    // it decoupled lets the page use ChainEngine::canAddStage()
    // without ChainRailWidget needing an engine reference.
    void setChain(const Chain &chain);

    // Visually highlight the node matching stageId. Pass "" to clear
    // selection. Safe to call before setChain — the highlight is
    // applied on the next setChain that contains a matching id.
    void setSelectedStageId(const QString &stageId);

    // Enable/disable the trailing + button. Page should call this
    // after setChain() based on ChainEngine::canAddStage().
    void setCanAddStage(bool canAdd);

signals:
    // Emitted when the user clicks a node. The page reacts by
    // updating its selectedStageId (and downstream: canvas + config).
    void stageSelected(const QString &stageId);

    // Emitted when the user clicks the + button. The page reacts by
    // showing a kind-picker menu and (if a kind is chosen) calling
    // ChainEngine::addStage. Pass 7b emits this; Pass 7d wires the
    // picker menu; Pass 8 wires the engine call.
    // --- CHAIN STUDIO PASS 7D3 KIND PICKER ---
    // Carries the global screen position of the + button's lower-
    // left corner so the page can pop the kind-picker QMenu right
    // below the button.
    void addStageRequested(QPoint globalPos);

private:
    // Tear down current node/connector widgets and rebuild from the
    // last-set chain. Selection is preserved across rebuilds.
    void rebuild();

    Chain chain_;
    QString selectedStageId_;
    bool canAddStage_ = true;

    QScrollArea *scroll_      = nullptr;
    QWidget     *content_     = nullptr;
    QHBoxLayout *contentRow_  = nullptr;
    QPushButton *addButton_   = nullptr;
};

} // namespace spellvision::chain
