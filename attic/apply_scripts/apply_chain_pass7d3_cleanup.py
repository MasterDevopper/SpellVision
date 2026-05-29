r"""
SpellVision - Chain Studio Pass 7d.3 CLEANUP (full file overwrites).

After many diagnostic passes resolved the kind-picker menu bug, this
script strips ALL debug instrumentation from the chain widget cpp
files by overwriting them with canonical post-7d.3 versions.

KEEPS:
  - Real connect from addButton_ clicked to onAddStageClicked
  - The eventFilter for uploadBox_ (always intended)
  - addStageRequested(QPoint) signal with global pos
  - showAddStageMenu(window()) menu parent fix
  - Pass 7d.3 enablement (final stub stage is Locked)
  - validKindsForAdd / stageKindLabel logic

REMOVES:
  - addButton_->installEventFilter(this) and qDebug logging
  - The test lambda connect duplicating the real connect
  - The eventFilter branch for watched == addButton_
  - hitButton diagnostic logging
  - All qDebug lines in show/select/choose flows
  - The QDebug include (no longer needed)
  - All PASS 7D3 ... debug-only marker comments
"""

from __future__ import annotations
import sys
from pathlib import Path

MARKER = "PASS 7D3 CLEAN"


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def write_crlf(path: Path, payload: str) -> None:
    crlf = payload.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_bytes(crlf.encode("utf-8"))


DIALOG_BAR_CPP = '''#include "chain/ChainDialogBarWidget.h"

#include "ThemeManager.h"

#include <QCursor>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QEvent>
#include <QMouseEvent>
#include <QPixmap>
#include <QPoint>
#include <QPushButton>
#include <QSizePolicy>
#include <QStandardPaths>
#include <QVBoxLayout>

namespace spellvision::chain
{

namespace
{

constexpr int kBarHeight       = 56;
constexpr int kUploadBoxSide   = 56;
constexpr int kAddButtonMinW   = 104;

QString uploadEmptyStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QFrame#ChainDialogUploadBox { "
        "  background: %1; "
        "  border: 1px dashed %2; "
        "  border-radius: %3px; "
        "}"
        "QFrame#ChainDialogUploadBox:hover { border-color: %4; }"
    ).arg(tm.background0Color().name(),
          tm.borderToneColor().name(),
          QString::number(tm.radiusControl()),
          tm.accentColor().name());
}

QString uploadLoadedStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QFrame#ChainDialogUploadBox { "
        "  background: %1; "
        "  border: 1px solid %2; "
        "  border-radius: %3px; "
        "}"
        "QFrame#ChainDialogUploadBox:hover { border-color: %4; }"
    ).arg(tm.surface1Color().name(),
          tm.accentColor().name(),
          QString::number(tm.radiusControl()),
          tm.accentColor().lighter(130).name());
}

QString uploadGlyphStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QLabel { color: %1; font-size: 18px; background: transparent; "
        "border: none; }"
    ).arg(tm.accentColor().name());
}

QString uploadCaptionStyle(bool loaded)
{
    const auto &tm = ThemeManager::instance();
    const QColor color = loaded ? tm.accentColor() : tm.textMutedColor();
    return QStringLiteral(
        "QLabel { color: %1; font-size: 8px; font-weight: 700; "
        "letter-spacing: 0.4px; background: transparent; border: none; }"
    ).arg(color.name());
}

QString dbarStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QLineEdit { "
        "  background: %1; "
        "  border: 1px solid %2; "
        "  border-radius: %3px; "
        "  padding: 0 16px; "
        "  color: %4; "
        "  font-size: 13px; "
        "}"
        "QLineEdit:focus { border-color: %5; }"
    ).arg(tm.background0Color().name(),
          tm.borderToneColor().name(),
          QString::number(tm.radiusControl()),
          tm.textPrimaryColor().name(),
          tm.accentColor().name());
}

QString addBtnStyle(bool enabled)
{
    // --- ''' + MARKER + ''' ---
    // Minimal stylesheet (no padding, no :pressed pseudo). Earlier
    // attempts with border:none + padding interfered with QPushButton
    // hit-testing on Windows in some configurations.
    const auto &tm = ThemeManager::instance();
    if (!enabled)
    {
        return QStringLiteral(
            "QPushButton { "
            "  background-color: %1; "
            "  color: %2; "
            "  border-width: 0px; "
            "  border-radius: %3px; "
            "  font-size: 13px; "
            "  font-weight: 800; "
            "}"
        ).arg(tm.background0Color().name(),
              tm.textMutedColor().name(),
              QString::number(tm.radiusControl()));
    }
    return QStringLiteral(
        "QPushButton { "
        "  background-color: %1; "
        "  color: %2; "
        "  border-width: 0px; "
        "  border-radius: %3px; "
        "  font-size: 13px; "
        "  font-weight: 800; "
        "}"
        "QPushButton:hover { background-color: %4; }"
    ).arg(tm.accentColor().name(),
          tm.background0Color().name(),
          QString::number(tm.radiusControl()),
          tm.accentColor().lighter(110).name());
}

} // anonymous namespace

ChainDialogBarWidget::ChainDialogBarWidget(QWidget *parent)
    : QWidget(parent)
{
    setFixedHeight(kBarHeight);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    const auto &tm = ThemeManager::instance();
    auto *row = new QHBoxLayout(this);
    row->setContentsMargins(0, 0, 0, 0);
    row->setSpacing(tm.spacing(ThemeManager::Spacing::Snug));

    // ---- Upload box ----
    uploadBox_ = new QFrame(this);
    uploadBox_->setObjectName(QStringLiteral("ChainDialogUploadBox"));
    uploadBox_->setFixedSize(kUploadBoxSide, kUploadBoxSide);
    uploadBox_->setCursor(Qt::PointingHandCursor);
    uploadBox_->setStyleSheet(uploadEmptyStyle());

    auto *uploadStack = new QVBoxLayout(uploadBox_);
    uploadStack->setContentsMargins(0, 0, 0, 0);
    uploadStack->setSpacing(2);
    uploadStack->setAlignment(Qt::AlignCenter);

    uploadGlyph_ = new QLabel(QStringLiteral("UNICODE_ARROW_GLYPH"), uploadBox_);
    uploadGlyph_->setAlignment(Qt::AlignCenter);
    uploadGlyph_->setStyleSheet(uploadGlyphStyle());
    uploadGlyph_->setAttribute(Qt::WA_TransparentForMouseEvents);

    uploadCaption_ = new QLabel(QStringLiteral("IMG"), uploadBox_);
    uploadCaption_->setAlignment(Qt::AlignCenter);
    uploadCaption_->setStyleSheet(uploadCaptionStyle(false));
    uploadCaption_->setAttribute(Qt::WA_TransparentForMouseEvents);

    uploadStack->addWidget(uploadGlyph_, 0, Qt::AlignCenter);
    uploadStack->addWidget(uploadCaption_, 0, Qt::AlignCenter);

    uploadThumb_ = new QLabel(uploadBox_);
    uploadThumb_->setAlignment(Qt::AlignCenter);
    uploadThumb_->setScaledContents(false);
    uploadThumb_->setStyleSheet(QStringLiteral(
        "QLabel { background: transparent; border: none; border-radius: 5px; }"));
    uploadThumb_->setGeometry(2, 2, kUploadBoxSide - 4, kUploadBoxSide - 4);
    uploadThumb_->setAttribute(Qt::WA_TransparentForMouseEvents);
    uploadThumb_->hide();

    // QFrame has no clicked signal; eventFilter on uploadBox_ catches
    // MouseButtonRelease and calls onUploadBoxClicked.
    uploadBox_->installEventFilter(this);

    row->addWidget(uploadBox_);

    // ---- Dialog bar (prompt input) ----
    promptEdit_ = new QLineEdit(this);
    promptEdit_->setObjectName(QStringLiteral("ChainDialogPromptEdit"));
    promptEdit_->setPlaceholderText(
        QStringLiteral("UNICODE_DIAMOND  Describe UNICODE_DASH prompt, style cues, framing notesUNICODE_ELLIPSIS"));
    promptEdit_->setStyleSheet(dbarStyle());
    promptEdit_->setClearButtonEnabled(false);
    connect(promptEdit_, &QLineEdit::textChanged,
            this, &ChainDialogBarWidget::promptChanged);
    row->addWidget(promptEdit_, 1);

    // ---- Add-stage button ----
    addButton_ = new QPushButton(this);
    addButton_->setMinimumWidth(kAddButtonMinW);
    addButton_->setFixedHeight(kBarHeight);
    addButton_->setCursor(Qt::PointingHandCursor);
    addButton_->setText(QStringLiteral("+  add stage"));
    addButton_->setStyleSheet(addBtnStyle(true));
    connect(addButton_, &QPushButton::clicked,
            this, &ChainDialogBarWidget::onAddStageClicked);
    row->addWidget(addButton_);

    refresh();
}

void ChainDialogBarWidget::setChain(const Chain &chain)
{
    chain_ = chain;
    refresh();
}

void ChainDialogBarWidget::setCanAddStage(bool canAdd)
{
    if (canAddStage_ == canAdd)
        return;
    canAddStage_ = canAdd;
    if (addButton_ != nullptr)
    {
        addButton_->setEnabled(canAdd);
        addButton_->setStyleSheet(addBtnStyle(canAdd));
    }
}

void ChainDialogBarWidget::refresh()
{
    const bool hasImage = (chain_.entryKind == EntryKind::UploadedImage) &&
                          !chain_.sourceImagePath.isEmpty() &&
                          QFileInfo::exists(chain_.sourceImagePath);
    if (hasImage)
        applyUploadLoadedVisual(chain_.sourceImagePath);
    else
        applyUploadEmptyVisual();

    if (promptEdit_ != nullptr && !chain_.stages.isEmpty())
    {
        const QString prompt = chain_.stages.first().config.prompt;
        if (prompt != promptEdit_->text())
        {
            promptEdit_->blockSignals(true);
            promptEdit_->setText(prompt);
            promptEdit_->blockSignals(false);
        }
    }

    if (addButton_ != nullptr)
    {
        addButton_->setEnabled(canAddStage_);
        addButton_->setStyleSheet(addBtnStyle(canAddStage_));
    }
}

void ChainDialogBarWidget::applyUploadEmptyVisual()
{
    if (uploadBox_ != nullptr)
        uploadBox_->setStyleSheet(uploadEmptyStyle());
    if (uploadGlyph_ != nullptr)
        uploadGlyph_->show();
    if (uploadCaption_ != nullptr)
    {
        uploadCaption_->show();
        uploadCaption_->setStyleSheet(uploadCaptionStyle(false));
    }
    if (uploadThumb_ != nullptr)
    {
        uploadThumb_->hide();
        uploadThumb_->clear();
    }
}

void ChainDialogBarWidget::applyUploadLoadedVisual(const QString &thumbPath)
{
    if (uploadBox_ != nullptr)
        uploadBox_->setStyleSheet(uploadLoadedStyle());
    if (uploadThumb_ != nullptr)
    {
        QPixmap pix(thumbPath);
        if (!pix.isNull())
        {
            const QSize target(kUploadBoxSide - 4, kUploadBoxSide - 4);
            uploadThumb_->setPixmap(
                pix.scaled(target, Qt::KeepAspectRatioByExpanding,
                           Qt::SmoothTransformation));
            uploadThumb_->show();
            uploadThumb_->raise();
            if (uploadGlyph_ != nullptr)
                uploadGlyph_->hide();
            if (uploadCaption_ != nullptr)
                uploadCaption_->hide();
            return;
        }
    }
    applyUploadEmptyVisual();
}

void ChainDialogBarWidget::onUploadBoxClicked()
{
    const QString startDir = QStandardPaths::writableLocation(
        QStandardPaths::PicturesLocation);
    const QString filter = QStringLiteral(
        "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*.*)");
    const QString path = QFileDialog::getOpenFileName(
        this, QStringLiteral("Choose entry image"), startDir, filter);
    if (path.isEmpty())
        return;
    emit inputImageSelected(path);
}

void ChainDialogBarWidget::onAddStageClicked()
{
    // --- ''' + MARKER + ''' ---
    // Emit with the button's bottom-left global pos so the page can
    // pop the kind-picker QMenu just below the button.
    const QPoint pos = addButton_
        ? addButton_->mapToGlobal(QPoint(0, addButton_->height()))
        : QCursor::pos();
    emit addStageRequested(pos);
}

bool ChainDialogBarWidget::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == uploadBox_ &&
        event->type() == QEvent::MouseButtonRelease)
    {
        auto *me = static_cast<QMouseEvent *>(event);
        if (me->button() == Qt::LeftButton &&
            uploadBox_->rect().contains(me->position().toPoint()))
        {
            onUploadBoxClicked();
            return true;
        }
    }
    return QWidget::eventFilter(watched, event);
}

} // namespace spellvision::chain
'''


PAGE_CPP = '''#include "chain/ChainStudioPage.h"

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

// --- ''' + MARKER + ''': kind-picker helpers ---

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
        case StageKind::T2I:   return QStringLiteral("T2I  UNICODE_DASH  text to image");
        case StageKind::T2V:   return QStringLiteral("T2V  UNICODE_DASH  text to video");
        case StageKind::I2I:   return QStringLiteral("I2I  UNICODE_DASH  image to image");
        case StageKind::I2V:   return QStringLiteral("I2V  UNICODE_DASH  image to video");
        case StageKind::I2_3D: return QStringLiteral("IUNICODE_RARROW" "3D  UNICODE_DASH  image to 3D");
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
    // --- ''' + MARKER + ''' ---
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
    // --- ''' + MARKER + ''' ---
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
'''


def resolve_unicode_placeholders(payload: str) -> str:
    """Replace placeholder tokens with actual unicode characters.

    We use placeholder tokens like UNICODE_DASH instead of putting the
    real Unicode characters or escape sequences in the embedded source
    string, to avoid any issues with Python parsing or C++ compilation
    of Unicode-in-source.
    """
    replacements = {
        "UNICODE_ARROW_GLYPH": "\u2912",   # arrow with double horizontal stroke
        "UNICODE_DIAMOND":     "\u25C6",   # black diamond
        "UNICODE_DASH":        "\u2014",   # em dash
        "UNICODE_ELLIPSIS":    "\u2026",   # horizontal ellipsis
        "UNICODE_RARROW":      "\u2192",   # right arrow
    }
    for token, char in replacements.items():
        payload = payload.replace(token, char)
    return payload


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()

    bar_path = project / "qt_ui" / "chain" / "ChainDialogBarWidget.cpp"
    page_path = project / "qt_ui" / "chain" / "ChainStudioPage.cpp"

    print("qt_ui/chain/ChainDialogBarWidget.cpp")
    if bar_path.exists():
        existing = bar_path.read_text(encoding="utf-8")
        if f"// --- {MARKER}" in existing:
            print(f"  Already cleaned: {bar_path.name}")
        else:
            backup_once(bar_path, ".pre_pass7d3_cleanup.bak")
            write_crlf(bar_path, resolve_unicode_placeholders(DIALOG_BAR_CPP))
            print(f"  Rewrote: {bar_path.name}")
    else:
        print(f"  Not found: {bar_path}")

    print()

    print("qt_ui/chain/ChainStudioPage.cpp")
    if page_path.exists():
        existing = page_path.read_text(encoding="utf-8")
        if f"// --- {MARKER}" in existing:
            print(f"  Already cleaned: {page_path.name}")
        else:
            backup_once(page_path, ".pre_pass7d3_cleanup.bak")
            write_crlf(page_path, resolve_unicode_placeholders(PAGE_CPP))
            print(f"  Rewrote: {page_path.name}")
    else:
        print(f"  Not found: {page_path}")

    print()
    print(f"Done - {MARKER} applied.")
    print()
    print("Verify:")
    print("  1. .\\scripts\\dev\\run_ui.ps1")
    print("  2. Console should be quiet (no [ChainStudio] log lines)")
    print("  3. Click + add stage button -> kind-picker menu still pops")
    print("  4. Stage visuals still render correctly")
    print()
    print("If everything works, commit Track B's visual scaffold to git.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
