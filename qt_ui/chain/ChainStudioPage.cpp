#include "chain/ChainStudioPage.h"

#include "ThemeManager.h"
#include "chain/ChainRailWidget.h"
#include "chain/ChainCanvasWidget.h"
#include "chain/ChainConfigPanelWidget.h"
#include "chain/ChainDialogBarWidget.h"

#include <QAction>
#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QDateTime>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QMenu>
#include <QSizePolicy>
#include <QUuid>
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

QString findBrandImage(const QString &basename)
{
    const QStringList starts = {
        QCoreApplication::applicationDirPath(),
        QDir::currentPath()
    };
    const QStringList suffixes = {
        QStringLiteral(".jpg"),
        QStringLiteral(".jpeg"),
        QStringLiteral(".png"),
    };
    const QStringList relPrefixes = {
        QStringLiteral("qt_ui/icons/"),
        QStringLiteral("icons/"),
        QStringLiteral(""),
    };
    for (const QString &start : starts)
    {
        QDir dir(start);
        for (int depth = 0; depth < 7; ++depth)
        {
            for (const QString &prefix : relPrefixes)
            {
                for (const QString &suffix : suffixes)
                {
                    const QString candidate = dir.filePath(prefix + basename + suffix);
                    if (QFileInfo::exists(candidate))
                        return QDir::cleanPath(candidate);
                }
            }
            if (!dir.cdUp())
                break;
        }
    }
    return QString();
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
        case StageKind::T2I:   return QStringLiteral("T2I  —  text to image");
        case StageKind::T2V:   return QStringLiteral("T2V  —  text to video");
        case StageKind::I2I:   return QStringLiteral("I2I  —  image to image");
        case StageKind::I2V:   return QStringLiteral("I2V  —  image to video");
        case StageKind::I2_3D: return QStringLiteral("I→" "3D  —  image to 3D");
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

    buildStubChain();
    rail->setChain(stubChain_);
    if (!stubChain_.stages.isEmpty())
    {
        selectedStageId_ = stubChain_.stages.first().id;
        rail->setSelectedStageId(selectedStageId_);
    }
    const bool canAdd = stubChain_.stages.isEmpty() ||
        stubChain_.stages.back().status == StageStatus::Locked;
    rail->setCanAddStage(canAdd);

    if (dialogBarWidget_ != nullptr)
    {
        dialogBarWidget_->setChain(stubChain_);
        dialogBarWidget_->setCanAddStage(canAdd);
    }

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

    canvasWidget_->setChain(stubChain_);
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

    configPanelWidget_->setChain(stubChain_);
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

void ChainStudioPage::buildStubChain()
{
    const QString brand1 = findBrandImage(QStringLiteral("SpellVision"));
    const QString brand2 = findBrandImage(QStringLiteral("SpellVision2"));
    QStringList stubImages;
    if (!brand1.isEmpty()) stubImages << brand1;
    if (!brand2.isEmpty()) stubImages << brand2;
    if (stubImages.isEmpty())
        stubImages << QString();

    stubChain_ = Chain{};
    stubChain_.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
    stubChain_.createdAt = QDateTime::currentDateTimeUtc();
    stubChain_.updatedAt = stubChain_.createdAt;
    stubChain_.entryKind = EntryKind::DescribedText;

    auto makeStub = [&stubImages](StageKind k, StageStatus s, int varCount, int idx) {
        Stage stage;
        stage.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
        stage.index = idx;
        stage.kind = k;
        stage.status = s;
        stage.config.stageKind = k;
        stage.config.imageSampler   = QStringLiteral("dpmpp_2m");
        stage.config.imageScheduler = QStringLiteral("karras");
        stage.config.steps          = (idx == 0) ? 25 : 30;
        stage.config.cfg            = 7.5;
        stage.config.seed           = (idx == 0) ? 42 : -1;
        stage.config.width          = 1024;
        stage.config.height         = 1024;
        if (idx == 0)
            stage.config.prompt = QStringLiteral(
                "chisato hasegawa, semi-realism, dramatic rim light, full body");
        for (int i = 0; i < varCount; ++i)
        {
            Variation v;
            v.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
            v.createdAt = QDateTime::currentDateTimeUtc();
            v.outputPath = stubImages.at(i % stubImages.size());
            stage.variations.append(v);
        }
        if (varCount > 0)
            stage.selectedVarIdx = varCount - 1;
        if (s == StageStatus::Locked && varCount > 0)
            stage.lockedVarIdx = varCount - 1;
        return stage;
    };

    stubChain_.stages.append(makeStub(StageKind::T2I, StageStatus::Locked,    3, 0));
    stubChain_.stages.append(makeStub(StageKind::I2V, StageStatus::Completed, 2, 1));
    // --- PASS 7D3 CLEAN ---
    // Final stage Locked so canAdd is true and + add stage enables.
    // Per Qt source, disabled buttons don't emit clicked, so an
    // enabled-looking-but-disabled button would be a click trap.
    stubChain_.stages.append(makeStub(StageKind::I2_3D, StageStatus::Locked,  1, 2));
}

void ChainStudioPage::onRailStageSelected(const QString &stageId)
{
    if (stageId == selectedStageId_)
        return;
    selectedStageId_ = stageId;
    if (auto *rail = qobject_cast<ChainRailWidget *>(chainRail_))
        rail->setSelectedStageId(stageId);
    if (canvasWidget_ != nullptr)
        canvasWidget_->setSelectedStageId(stageId);
    if (configPanelWidget_ != nullptr)
        configPanelWidget_->setSelectedStageId(stageId);
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

    const QVector<StageKind> kinds = validKindsForAdd(stubChain_);
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

void ChainStudioPage::onAddStageKindChosen(StageKind kind)
{
    // Pass 8 will replace this with engine.addStage(kind).
    Q_UNUSED(kind);
}

void ChainStudioPage::onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx)
{
    for (auto &stage : stubChain_.stages)
    {
        if (stage.id != stageId)
            continue;
        if (newVarIdx < 0 || newVarIdx >= stage.variations.size())
            return;
        stage.selectedVarIdx = newVarIdx;
        if (canvasWidget_ != nullptr)
            canvasWidget_->setChain(stubChain_);
        return;
    }
}

void ChainStudioPage::onCanvasLockRequested(const QString &stageId)
{
    for (auto &stage : stubChain_.stages)
    {
        if (stage.id != stageId)
            continue;
        if (stage.status != StageStatus::Completed)
            return;
        stage.status = StageStatus::Locked;
        stage.lockedVarIdx = stage.selectedVarIdx;
        if (auto *rail = qobject_cast<ChainRailWidget *>(chainRail_))
        {
            rail->setChain(stubChain_);
            rail->setSelectedStageId(selectedStageId_);
            const bool canAdd = stubChain_.stages.isEmpty() ||
                stubChain_.stages.back().status == StageStatus::Locked;
            rail->setCanAddStage(canAdd);
            if (dialogBarWidget_ != nullptr)
                dialogBarWidget_->setCanAddStage(canAdd);
        }
        if (canvasWidget_ != nullptr)
            canvasWidget_->setChain(stubChain_);
        if (configPanelWidget_ != nullptr)
            configPanelWidget_->setChain(stubChain_);
        if (dialogBarWidget_ != nullptr)
            dialogBarWidget_->setChain(stubChain_);
        return;
    }
}

void ChainStudioPage::onConfigRegenerateRequested(const QString &stageId)
{
    Q_UNUSED(stageId);
}

void ChainStudioPage::onDialogInputImageSelected(const QString &path)
{
    stubChain_.entryKind = EntryKind::UploadedImage;
    stubChain_.sourceImagePath = path;
    if (dialogBarWidget_ != nullptr)
        dialogBarWidget_->setChain(stubChain_);
}

void ChainStudioPage::onDialogPromptChanged(const QString &text)
{
    if (stubChain_.stages.isEmpty())
        return;
    stubChain_.stages.first().config.prompt = text;
    if (configPanelWidget_ != nullptr)
        configPanelWidget_->setChain(stubChain_);
}

} // namespace spellvision::chain
