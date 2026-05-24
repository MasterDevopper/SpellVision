#include "chain/ChainStudioPage.h"

#include "ThemeManager.h"
#include "chain/ChainCanvasWidget.h"
// --- CHAIN STUDIO PASS 8C.3: completion watcher + main window ---
#include "chain/ChainCompletionWatcher.h"
#include "chain/ChainConfigPanelWidget.h"
#include "chain/ChainDialogBarWidget.h"
// --- CHAIN STUDIO PASS 8A: engine ownership ---
#include "chain/ChainEngine.h"
#include "chain/ChainRailWidget.h"
#include "MainWindow.h"

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

    // --- CHAIN STUDIO PASS 8C.3: engine + watcher + real submitFn ---
    // Pass 8a constructed the engine with a rejecting submitFn and
    // null watcher (display-only). Pass 8c.3 replaces both:
    //
    //   - watcher_ binds to MainWindow's QueueManager and observes
    //     queue snapshots, firing variation*-signals that the engine
    //     subscribes to via bind().
    //   - submitFn captures a MainWindow* and forwards each
    //     (payload, engineId) pair into
    //     MainWindow::submitChainGenerationRequest, which mirrors the
    //     existing submitGenerationRequest pipeline.
    //
    // Parent resolution: at construct time, qobject_cast<MainWindow*>
    // on the parent QWidget gives us the typed handle. window() would
    // not work because the page hasn't been added to a top-level
    // window yet. If the cast fails (unexpected -- would imply the
    // page was reparented or constructed standalone for testing), we
    // fall back to the Pass 8a rejecting submitFn so the page stays
    // functional for display.
    engine_ = new ChainEngine(this);
    watcher_ = new ChainCompletionWatcher(this);

    MainWindow *mw = qobject_cast<MainWindow *>(parent);
    if (mw != nullptr && mw->queueManager() != nullptr)
    {
        watcher_->bind(mw->queueManager(), nullptr);

        auto realSubmitFn = [mw](const QJsonObject &payload,
                                 const QString &engineId) -> bool
        {
            // ChainEngine::draftFromConfig stamps draft.mode =
            // toString(StageKind) which the GenerationRequestBuilder
            // emits as payload["mode"]. That is exactly the lowercase
            // task command MainWindow expects as modeId.
            const QString modeId = payload.value(QStringLiteral("mode")).toString();
            return mw->submitChainGenerationRequest(modeId, payload, engineId);
        };
        engine_->bind(nullptr, watcher_, realSubmitFn);
    }
    else
    {
        // Defensive fallback: no MainWindow available means no queue
        // and no submission path. Keep the engine bound to the same
        // rejecting stub as Pass 8a so the page renders but
        // submissions are inert.
        auto rejectingSubmitFn = [](const QJsonObject &, const QString &) {
            return false;
        };
        engine_->bind(nullptr, nullptr, rejectingSubmitFn);
    }

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

// --- CHAIN STUDIO PASS 8B: mutation handlers wired to engine ---
// Five of six mutation handlers now route through engine_-> calls.
// Each engine call may emit chainMutated, which fires
// refreshAllWidgets() and fans state out to all four widgets.
//
// The sixth, onConfigRegenerateRequested, STAYS as a Q_UNUSED stub
// because the currently-bound submitFn returns false unconditionally
// -- calling engine_->regenerate now would emit submissionRejected
// and mark the stage Failed. Pass 8c wires the real submitFn into
// MainWindow's worker pipeline and replaces this body in lockstep.

void ChainStudioPage::onAddStageKindChosen(StageKind kind)
{
    // Engine validates and returns "" on rejection (kind mismatched
    // entry, or predecessor not Locked). On success the chainMutated
    // signal already fired during addStage() -- our refresh below
    // additionally pushes the new selection out.
    const QString newStageId = engine_->addStage(kind);
    if (newStageId.isEmpty())
        return;
    selectedStageId_ = newStageId;
    refreshAllWidgets();
}

void ChainStudioPage::onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx)
{
    // Engine emits chainMutated on success -> refreshAllWidgets()
    // fires automatically. Out-of-range idx is silently ignored by
    // the engine; we don't need to surface that.
    engine_->selectVariation(stageId, newVarIdx);
}

void ChainStudioPage::onCanvasLockRequested(const QString &stageId)
{
    // Engine validates (must be Completed, must have selectedVarIdx
    // >= 0); rejection is silent and the chain stays unchanged. On
    // success the engine emits chainMutated -> refreshAllWidgets().
    engine_->lock(stageId);
}

void ChainStudioPage::onConfigRegenerateRequested(const QString &stageId)
{
    // --- CHAIN STUDIO PASS 8C.3: harvest-then-regenerate ---
    // The config panel widget edits are NOT live-bound to the engine
    // (Option A from design): the user's spinbox/combobox changes
    // live in the widget until Regenerate fires. Here we harvest the
    // user's current widget state, push it into the engine's stage
    // config, and ONLY THEN call regenerate so the engine builds the
    // payload from the harvested values.
    if (configPanelWidget_ != nullptr)
    {
        const StageConfig harvested = configPanelWidget_->harvestCurrentConfig();
        engine_->setStageConfig(stageId, harvested);
    }

    // regenerate() emits stageStatusChanged(Queued) -> chainMutated
    // -> refreshAllWidgets, then synchronously calls the bound
    // submitFn. If submitFn returns false (rejected at any gate),
    // the engine fires submissionRejected and the stage transitions
    // to Failed. If true, the engine tracks engineId via the
    // watcher; later the watcher fires variationCompleted which the
    // engine handles by appending the real Variation and emitting
    // chainMutated again.
    engine_->regenerate(stageId);
}

void ChainStudioPage::onDialogInputImageSelected(const QString &path)
{
    // If the chain already has stages, refuse the upload silently
    // for now -- swapping entry image on a non-empty chain would
    // need to wipe everything (engine has no incremental "swap
    // source image" API), and a silent wipe would be a UX trap.
    // Pass 10 polish: confirm-dialog or toast before reset.
    if (!engine_->chain().stages.isEmpty())
        return;

    // Empty chain -- safe to re-seed with UploadedImage entry. The
    // kind-picker menu will switch to offering I2I / I2V / I2_3D.
    engine_->newChain(EntryKind::UploadedImage, path);
}

void ChainStudioPage::onDialogPromptChanged(const QString &text)
{
    // The top dialog bar drives the FIRST stage's prompt (per v3
    // mockup). If there is no first stage yet the user is still in
    // "describe what you want to make" mode -- the text input
    // accepts text freely; we just can't push it anywhere until a
    // stage exists.
    if (engine_->chain().stages.isEmpty())
        return;

    // Engine rejects setStageConfig on Locked stages, but the entry
    // stage is rarely Locked during prompt editing. Harvest the
    // existing config so we only mutate the prompt field.
    const QString firstStageId = engine_->chain().stages.first().id;
    StageConfig newConfig = engine_->chain().stages.first().config;
    newConfig.prompt = text;
    engine_->setStageConfig(firstStageId, newConfig);
}

} // namespace spellvision::chain
