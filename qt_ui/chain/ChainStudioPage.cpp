#include "chain/ChainStudioPage.h"

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
