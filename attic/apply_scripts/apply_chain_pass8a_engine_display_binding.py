#!/usr/bin/env python3
"""
PASS 8A: engine display binding for ChainStudioPage
====================================================

What this script does
---------------------
Replaces the in-page `stubChain_` source-of-truth in `ChainStudioPage` with
a real `ChainEngine` instance. The engine is constructed bound to:
  - store    = nullptr   (no persistence yet, comes in pass 8c)
  - watcher  = nullptr   (no real worker integration yet, comes in pass 8c)
  - submitFn = rejecting lambda (returns false so any Regenerate click
               would emit submissionRejected -- which is why this pass
               also makes Regenerate a no-op until 8c)

Widgets continue to read state via setChain(engine_->chain()). The engine's
`chainMutated` signal is connected to a new `refreshAllWidgets()` slot, so
future mutations (8b) will fan out cleanly.

The previous mutation paths (lock/select/regenerate/prompt/upload/add-kind)
become Q_UNUSED stubs in 8a. Pass 8b will replace each body with
engine_->X(...) calls.

Side effects
------------
  - Removes the `buildStubChain()` method and its `findBrandImage` helper
    (both only used by the stub).
  - Removes <QDateTime> and <QUuid> includes (only used by stub generation).
  - Adds a forward decl for ChainEngine in the .h, and an include for it in
    the .cpp.

Idempotency
-----------
The script is marker-guarded. On re-run it detects the
"// --- CHAIN STUDIO PASS 8A:" marker and skips the write but still emits
a fresh backup if requested.

Output
------
  qt_ui/chain/ChainStudioPage.h    (rewritten)
  qt_ui/chain/ChainStudioPage.cpp  (rewritten)
  Backups:
    qt_ui/chain/ChainStudioPage.h.pre_pass8a.bak
    qt_ui/chain/ChainStudioPage.cpp.pre_pass8a.bak

Verification after applying
---------------------------
  1. .\\scripts\\dev\\run_ui.ps1
  2. Build should succeed.
  3. Chain Studio page should render empty: no rail nodes, blank canvas,
     blank config panel, "+ add stage" button enabled.
  4. Clicking "+ add stage" should pop the kind-picker menu with
     "T2I - text to image" and "T2V - text to video" (entry kinds for
     EntryKind::DescribedText).
  5. Clicking a kind does nothing visible (Q_UNUSED stub for 8b).
  6. No crashes.

If everything looks right, commit on top of track-b-scaffold.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Project root: parent of this script (so the script can sit in project root
# alongside the other apply_chain_*.py scripts).
PROJECT_ROOT = Path(__file__).resolve().parent

# CRLF for Windows-line-ending consistency with the rest of the codebase.
NL = "\r\n"

PAGE_H_REL  = "qt_ui/chain/ChainStudioPage.h"
PAGE_CPP_REL = "qt_ui/chain/ChainStudioPage.cpp"

MARKER = "// --- CHAIN STUDIO PASS 8A:"

# ---------------------------------------------------------------------------
# New ChainStudioPage.h
# ---------------------------------------------------------------------------

NEW_PAGE_H = r"""#pragma once

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
"""

# ---------------------------------------------------------------------------
# New ChainStudioPage.cpp
# ---------------------------------------------------------------------------

NEW_PAGE_CPP = r"""#include "chain/ChainStudioPage.h"

#include "ThemeManager.h"
#include "chain/ChainCanvasWidget.h"
#include "chain/ChainConfigPanelWidget.h"
#include "chain/ChainDialogBarWidget.h"
// --- CHAIN STUDIO PASS 8A: engine ownership ---
#include "chain/ChainEngine.h"
#include "chain/ChainRailWidget.h"

#include <QAction>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonObject>
#include <QLabel>
#include <QMenu>
#include <QSizePolicy>
#include <QVBoxLayout>

namespace spellvision::chain
{

namespace
{

constexpr int kChainRailHeight  = 64;
constexpr int kConfigPanelWidth = 318;

QString placeholderLabelStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "color: %1; "
        "font-size: 11px; "
        "letter-spacing: 0.6px; "
        "font-weight: 600;"
    ).arg(tm.textMutedColor().name());
}

// --- PASS 7D3 CLEAN: kind-picker helpers ---

bool lastStageProducesImage(const Chain &chain)
{
    if (chain.stages.isEmpty())
        return false;
    const Stage &last = chain.stages.back();
    switch (last.kind)
    {
        case StageKind::T2I:
        case StageKind::I2I:
            return last.status == StageStatus::Locked ||
                   last.status == StageStatus::Completed;
        case StageKind::T2V:
        case StageKind::I2V:
        case StageKind::I2_3D:
        case StageKind::Audio:
            return false;
    }
    return false;
}

QVector<StageKind> validKindsForAdd(const Chain &chain)
{
    const bool haveImage =
        (chain.entryKind == EntryKind::UploadedImage &&
         !chain.sourceImagePath.isEmpty()) ||
        lastStageProducesImage(chain);

    if (haveImage)
        return { StageKind::I2I, StageKind::I2V, StageKind::I2_3D };
    return { StageKind::T2I, StageKind::T2V };
}

QString stageKindLabel(StageKind k)
{
    switch (k)
    {
        case StageKind::T2I:   return QStringLiteral("T2I  \u2014  text to image");
        case StageKind::T2V:   return QStringLiteral("T2V  \u2014  text to video");
        case StageKind::I2I:   return QStringLiteral("I2I  \u2014  image to image");
        case StageKind::I2V:   return QStringLiteral("I2V  \u2014  image to video");
        case StageKind::I2_3D: return QStringLiteral("I\u2192" "3D  \u2014  image to 3D");
        case StageKind::Audio: return QStringLiteral("Audio");
    }
    return QStringLiteral("?");
}

} // anonymous namespace

ChainStudioPage::ChainStudioPage(QWidget *parent)
    : QWidget(parent)
{
    const auto &tm = ThemeManager::instance();
    setAutoFillBackground(true);
    QPalette pal = palette();
    pal.setColor(QPalette::Window, tm.background1Color());
    setPalette(pal);

    // --- CHAIN STUDIO PASS 8A: engine ownership ---
    // Construct the engine BEFORE the build* helpers run so they can
    // read engine_->chain() instead of the old stubChain_.
    //
    // bind() is called with null store + null watcher + a rejecting
    // submitFn. This is "display-only" wiring: the engine holds the
    // chain in memory, but cannot persist or actually submit. Pass 8b
    // wires real mutations through engine_-> methods; Pass 8c wires
    // the real submitFn, store, and watcher to connect into
    // QueueManager / worker_service.
    //
    // newChain(DescribedText) seeds an empty chain. The first stage
    // (T2I or T2V) will be added by the user via the "+ add stage"
    // kind-picker in Pass 8b. This pass shows an empty page.
    engine_ = new ChainEngine(this);
    auto rejectingSubmitFn = [](const QJsonObject &, const QString &) {
        return false;
    };
    engine_->bind(nullptr, nullptr, rejectingSubmitFn);
    engine_->newChain(EntryKind::DescribedText);

    connect(engine_, &ChainEngine::chainMutated,
            this, &ChainStudioPage::refreshAllWidgets);

    auto *root = new QVBoxLayout(this);
    const int outerVert = tm.spacing(ThemeManager::Spacing::Snug);
    const int outerHorz = tm.spacing(ThemeManager::Spacing::Card);
    root->setContentsMargins(outerHorz, outerVert, outerHorz, outerVert);
    root->setSpacing(tm.spacing(ThemeManager::Spacing::Snug));

    topStrip_  = buildTopStrip();
    chainRail_ = buildChainRail();

    auto *mainRow = new QHBoxLayout;
    mainRow->setContentsMargins(0, 0, 0, 0);
    mainRow->setSpacing(tm.spacing(ThemeManager::Spacing::Snug));

    canvas_ = buildCanvas();
    configPanel_ = buildConfigPanel();

    mainRow->addWidget(canvas_, 1);
    mainRow->addWidget(configPanel_, 0);

    root->addWidget(topStrip_);
    root->addWidget(chainRail_);
    root->addLayout(mainRow, 1);
}

QWidget *ChainStudioPage::buildTopStrip()
{
    dialogBarWidget_ = new ChainDialogBarWidget(this);

    connect(dialogBarWidget_, &ChainDialogBarWidget::inputImageSelected,
            this, &ChainStudioPage::onDialogInputImageSelected);
    connect(dialogBarWidget_, &ChainDialogBarWidget::promptChanged,
            this, &ChainStudioPage::onDialogPromptChanged);
    connect(dialogBarWidget_, &ChainDialogBarWidget::addStageRequested,
            this, &ChainStudioPage::onRailAddStageRequested);

    // --- CHAIN STUDIO PASS 8A: read from engine ---
    dialogBarWidget_->setChain(engine_->chain());
    dialogBarWidget_->setCanAddStage(engine_->canAddStage());

    return dialogBarWidget_;
}

QWidget *ChainStudioPage::buildChainRail()
{
    auto *rail = new ChainRailWidget(this);
    rail->setFixedHeight(kChainRailHeight);
    rail->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    connect(rail, &ChainRailWidget::stageSelected,
            this, &ChainStudioPage::onRailStageSelected);
    connect(rail, &ChainRailWidget::addStageRequested,
            this, &ChainStudioPage::onRailAddStageRequested);

    // --- CHAIN STUDIO PASS 8A: read from engine ---
    rail->setChain(engine_->chain());
    if (!engine_->chain().stages.isEmpty())
    {
        selectedStageId_ = engine_->chain().stages.first().id;
        rail->setSelectedStageId(selectedStageId_);
    }
    rail->setCanAddStage(engine_->canAddStage());

    return rail;
}

QWidget *ChainStudioPage::buildCanvas()
{
    canvasWidget_ = new ChainCanvasWidget(this);
    canvasWidget_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    connect(canvasWidget_, &ChainCanvasWidget::variationSelectionChanged,
            this, &ChainStudioPage::onCanvasVariationSelectionChanged);
    connect(canvasWidget_, &ChainCanvasWidget::lockRequested,
            this, &ChainStudioPage::onCanvasLockRequested);

    // --- CHAIN STUDIO PASS 8A: read from engine ---
    canvasWidget_->setChain(engine_->chain());
    canvasWidget_->setSelectedStageId(selectedStageId_);

    return canvasWidget_;
}

QWidget *ChainStudioPage::buildConfigPanel()
{
    configPanelWidget_ = new ChainConfigPanelWidget(this);
    configPanelWidget_->setFixedWidth(kConfigPanelWidth);
    configPanelWidget_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);

    connect(configPanelWidget_, &ChainConfigPanelWidget::regenerateRequested,
            this, &ChainStudioPage::onConfigRegenerateRequested);

    // --- CHAIN STUDIO PASS 8A: read from engine ---
    configPanelWidget_->setChain(engine_->chain());
    configPanelWidget_->setSelectedStageId(selectedStageId_);

    return configPanelWidget_;
}

void ChainStudioPage::applyPlaceholderStyle(QWidget *region, const QString &debugLabel)
{
    if (region == nullptr)
        return;

    const auto &tm = ThemeManager::instance();

    region->setStyleSheet(QStringLiteral(
        "QFrame { "
        "  background: %1; "
        "  border: 1px solid %2; "
        "  border-radius: %3px; "
        "}"
    ).arg(tm.surface1Color().name(),
          tm.borderToneColor().name(),
          QString::number(tm.radiusCard())));

    auto *layout = new QVBoxLayout(region);
    const int innerPad = tm.spacing(ThemeManager::Spacing::Snug);
    layout->setContentsMargins(innerPad, tm.spacing(ThemeManager::Spacing::Tight),
                               innerPad, tm.spacing(ThemeManager::Spacing::Tight));
    layout->setSpacing(0);
    layout->addStretch(1);

    auto *label = new QLabel(debugLabel, region);
    label->setStyleSheet(placeholderLabelStyle());
    label->setAlignment(Qt::AlignCenter);
    label->setWordWrap(true);
    layout->addWidget(label, 0, Qt::AlignCenter);

    layout->addStretch(1);
}

// --- CHAIN STUDIO PASS 8A: fan engine state out to every widget ---
void ChainStudioPage::refreshAllWidgets()
{
    if (engine_ == nullptr)
        return;
    const Chain &chain = engine_->chain();
    const bool canAdd = engine_->canAddStage();

    if (auto *rail = qobject_cast<ChainRailWidget *>(chainRail_))
    {
        rail->setChain(chain);
        rail->setSelectedStageId(selectedStageId_);
        rail->setCanAddStage(canAdd);
    }
    if (canvasWidget_ != nullptr)
    {
        canvasWidget_->setChain(chain);
        canvasWidget_->setSelectedStageId(selectedStageId_);
    }
    if (configPanelWidget_ != nullptr)
    {
        configPanelWidget_->setChain(chain);
        configPanelWidget_->setSelectedStageId(selectedStageId_);
    }
    if (dialogBarWidget_ != nullptr)
    {
        dialogBarWidget_->setChain(chain);
        dialogBarWidget_->setCanAddStage(canAdd);
    }
}

void ChainStudioPage::onRailStageSelected(const QString &stageId)
{
    if (stageId == selectedStageId_)
        return;
    selectedStageId_ = stageId;
    // Selection change doesn't mutate the engine, so chainMutated
    // won't fire on its own -- push the new selection out manually.
    refreshAllWidgets();
}

void ChainStudioPage::onRailAddStageRequested(QPoint globalPos)
{
    showAddStageMenu(globalPos);
}

void ChainStudioPage::showAddStageMenu(QPoint globalPos)
{
    // --- PASS 7D3 CLEAN ---
    // QMenu's parent must be a top-level window per Qt docs (otherwise
    // Qt logs "must be a top level window" and the popup misbehaves).
    // window() returns the ancestor top-level widget (MainWindow).
    QMenu menu(window());

    // --- CHAIN STUDIO PASS 8A: read from engine ---
    const QVector<StageKind> kinds = validKindsForAdd(engine_->chain());
    for (StageKind k : kinds)
    {
        QAction *action = menu.addAction(stageKindLabel(k));
        connect(action, &QAction::triggered, this,
                [this, k]() { onAddStageKindChosen(k); });
    }

    if (kinds.isEmpty())
    {
        QAction *noKinds = menu.addAction(QStringLiteral("No valid kinds"));
        noKinds->setEnabled(false);
    }

    menu.exec(globalPos);
}

// --- CHAIN STUDIO PASS 8A: mutation handlers are Q_UNUSED stubs ---
// Pass 8b will replace each body with engine_-> calls. Each Q_UNUSED
// silences a "-Wunused-parameter" warning; the engine_ pointer is
// already in scope when those bodies land.

void ChainStudioPage::onAddStageKindChosen(StageKind kind)
{
    // Pass 8b: engine_->addStage(kind).
    Q_UNUSED(kind);
}

void ChainStudioPage::onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx)
{
    // Pass 8b: engine_->selectVariation(stageId, newVarIdx).
    Q_UNUSED(stageId);
    Q_UNUSED(newVarIdx);
}

void ChainStudioPage::onCanvasLockRequested(const QString &stageId)
{
    // Pass 8b: engine_->lock(stageId).
    Q_UNUSED(stageId);
}

void ChainStudioPage::onConfigRegenerateRequested(const QString &stageId)
{
    // Pass 8c: engine_->regenerate(stageId) with the real SubmitFn.
    // Currently the bound submitFn returns false unconditionally, so
    // calling regenerate now would emit submissionRejected without
    // doing anything useful. Better to no-op until 8c lands.
    Q_UNUSED(stageId);
}

void ChainStudioPage::onDialogInputImageSelected(const QString &path)
{
    // Pass 8b: this needs design discussion. UX-wise, setting the
    // entry image on a chain that already has stages would either
    // require unlocking everything or starting a fresh chain. The
    // engine API offers newChain(EntryKind::UploadedImage, path)
    // for the latter; setStageConfig() does not touch chain-level
    // sourceImagePath.
    Q_UNUSED(path);
}

void ChainStudioPage::onDialogPromptChanged(const QString &text)
{
    // Pass 8b: harvest first-stage config, set .prompt = text, call
    // engine_->setStageConfig(firstStageId, newConfig). Falls
    // through silently if there is no first stage yet.
    Q_UNUSED(text);
}

} // namespace spellvision::chain
"""


def write_with_crlf(path: Path, body: str) -> None:
    """Write `body` to `path` with CRLF line endings, no trailing newline duplication."""
    # The body uses literal \n; normalize to CRLF.
    text = body.replace("\r\n", "\n").replace("\n", NL)
    # Ensure exactly one trailing newline.
    if not text.endswith(NL):
        text += NL
    path.write_bytes(text.encode("utf-8"))


def already_applied(path: Path) -> bool:
    try:
        return MARKER in path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False


def apply_one(rel: str, new_body: str) -> bool:
    """
    Write the new body to the file at PROJECT_ROOT/rel, saving a .bak
    backup of the existing content. Returns True if a write happened,
    False if already applied (idempotent re-run).
    """
    path = PROJECT_ROOT / rel
    if not path.exists():
        print(f"  ERROR: {rel} does not exist at {path}")
        return False

    if already_applied(path):
        print(f"  Already applied (marker present): {rel}")
        return False

    backup = path.with_suffix(path.suffix + ".pre_pass8a.bak")
    backup.write_bytes(path.read_bytes())
    print(f"  Backup written: {backup.name}")

    write_with_crlf(path, new_body)
    print(f"  Rewrote: {rel}")
    return True


def main() -> int:
    print("Applying PASS 8A: engine display binding")
    print(f"  Project root: {PROJECT_ROOT}")
    print()

    print(PAGE_H_REL)
    h_changed = apply_one(PAGE_H_REL, NEW_PAGE_H)
    print()
    print(PAGE_CPP_REL)
    cpp_changed = apply_one(PAGE_CPP_REL, NEW_PAGE_CPP)
    print()

    if h_changed or cpp_changed:
        print("Done -- PASS 8A applied.")
    else:
        print("Done -- PASS 8A was already applied (no-op).")

    print()
    print("Verify:")
    print("  1. .\\scripts\\dev\\run_ui.ps1")
    print("  2. Build should succeed.")
    print("  3. Chain Studio page should render EMPTY: no rail nodes,")
    print("     blank canvas, blank config panel, '+' enabled.")
    print("  4. Click '+ add stage' -> kind-picker menu with T2I / T2V.")
    print("  5. Clicking a kind does nothing visible (8b will wire it).")
    print("  6. No crashes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
