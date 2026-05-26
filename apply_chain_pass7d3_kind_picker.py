r"""
SpellVision — Chain Studio Pass 7d.3: kind-picker menu.

The visual scaffold's last piece. Both the rail's "+ add stage" and
the dialog bar's "+ add stage" need to pop a small QMenu showing valid
StageKinds. Click a kind → emit addStageWithKindRequested(kind) →
page stub handler (Pass 8 wires engine.addStage(kind)).

Three coordinated edits, all full-file rewrites for the affected
files (header + cpp). CMake doesn't change.

KIND FILTERING — Pass 7d.3 logic:

  Empty chain OR DescribedText entry with no image-producing last stage
    → offer T2I, T2V
  UploadedImage entry OR last stage produced an image
    → offer I2I, I2V, I2_3D
  Audio is reserved (Pass 10 polish)

Implemented in a free function spellvision::chain::validKindsForAdd()
inside an anonymous namespace in ChainStudioPage.cpp — keeps the
business rule co-located with the page that uses it.

SIGNAL SHAPE CHANGE: addStageRequested() loses its empty arg and gains
a QPoint globalPos arg. Callers (rail, dialog bar) pass the button's
screen-coordinate top-left + button height so the menu pops directly
below the button. ChainStudioPage::onRailAddStageRequested(QPoint)
opens the menu at that position.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "CHAIN STUDIO PASS 7D3 KIND PICKER"
RAIL_H_BACKUP   = ".pre_pass7d3_rail_hdr.bak"
RAIL_CPP_BACKUP = ".pre_pass7d3_rail_cpp.bak"
BAR_H_BACKUP    = ".pre_pass7d3_bar_hdr.bak"
BAR_CPP_BACKUP  = ".pre_pass7d3_bar_cpp.bak"
PAGE_H_BACKUP   = ".pre_pass7d3_page_hdr.bak"
PAGE_CPP_BACKUP = ".pre_pass7d3_page_cpp.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def write_crlf(path: Path, payload: str) -> None:
    crlf = payload.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_bytes(crlf.encode("utf-8"))


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Anchor not found: {label}")
    if text.count(old) > 1:
        raise RuntimeError(f"Anchor not unique ({text.count(old)}x): {label}")
    return text.replace(old, new, 1)


# =============================================================================
# 1. ChainRailWidget.h — signal signature change
# =============================================================================
#
# Surgical edit to a single line in the header. The signal was:
#     void addStageRequested();
# becomes:
#     void addStageRequested(QPoint globalPos);

RAIL_H_OLD_SIG = "    void addStageRequested();\n"
RAIL_H_NEW_SIG = (
    f"    // --- {MARKER} ---\n"
    "    // Carries the global screen position of the + button's lower-\n"
    "    // left corner so the page can pop the kind-picker QMenu right\n"
    "    // below the button.\n"
    "    void addStageRequested(QPoint globalPos);\n"
)


def patch_rail_header(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainRailWidget.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, RAIL_H_BACKUP)
    # Ensure QPoint is forward-declared by adding the include if not present.
    if "#include <QPoint>" not in text:
        text = text.replace(
            "#include <QString>\n",
            "#include <QPoint>\n#include <QString>\n",
            1,
        )
    text = replace_once(text, RAIL_H_OLD_SIG, RAIL_H_NEW_SIG,
                        "addStageRequested signal in rail header")
    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")


# =============================================================================
# 2. ChainRailWidget.cpp — pass button geometry into emit
# =============================================================================
#
# Surgical edit. The add-button click handler currently emits the bare
# signal; we want it to emit with the button's bottom-left global pos.

RAIL_CPP_OLD_EMIT = "emit addStageRequested();"
RAIL_CPP_NEW_EMIT = (
    f"// --- {MARKER} ---\n"
    "        // Compute the button's bottom-left in global screen coords\n"
    "        // so the page can pop the kind-picker QMenu just below it.\n"
    "        const QPoint pos = addButton_\n"
    "            ? addButton_->mapToGlobal(QPoint(0, addButton_->height()))\n"
    "            : QCursor::pos();\n"
    "        emit addStageRequested(pos);"
)


def patch_rail_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainRailWidget.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, RAIL_CPP_BACKUP)
    # Add QCursor include if not present (mapToGlobal + QCursor::pos).
    if "#include <QCursor>" not in text:
        text = text.replace(
            "#include <QPushButton>\n",
            "#include <QCursor>\n#include <QPushButton>\n",
            1,
        )
    # The exact occurrence: there should be one emit. Replace with the
    # geometry-aware version. The new emit is indented to match its
    # original context (8 spaces).
    text = replace_once(text, RAIL_CPP_OLD_EMIT, RAIL_CPP_NEW_EMIT,
                        "addStageRequested emit in rail cpp")
    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")


# =============================================================================
# 3. ChainDialogBarWidget.h — signal signature change
# =============================================================================

BAR_H_OLD_SIG = "    void addStageRequested();\n"
BAR_H_NEW_SIG = (
    f"    // --- {MARKER} ---\n"
    "    // Carries the global screen position of the + button's lower-\n"
    "    // left corner so the page can pop the kind-picker QMenu right\n"
    "    // below the button.\n"
    "    void addStageRequested(QPoint globalPos);\n"
)


def patch_bar_header(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainDialogBarWidget.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, BAR_H_BACKUP)
    if "#include <QPoint>" not in text:
        text = text.replace(
            "#include <QString>\n",
            "#include <QPoint>\n#include <QString>\n",
            1,
        )
    text = replace_once(text, BAR_H_OLD_SIG, BAR_H_NEW_SIG,
                        "addStageRequested signal in dialog bar header")
    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")


# =============================================================================
# 4. ChainDialogBarWidget.cpp — pass button geometry into emit
# =============================================================================

BAR_CPP_OLD_FUNC = (
    "void ChainDialogBarWidget::onAddStageClicked()\n"
    "{\n"
    "    emit addStageRequested();\n"
    "}\n"
)

BAR_CPP_NEW_FUNC = (
    "void ChainDialogBarWidget::onAddStageClicked()\n"
    "{\n"
    f"    // --- {MARKER} ---\n"
    "    // Compute the button's bottom-left in global screen coords so\n"
    "    // the page can pop the kind-picker QMenu just below it.\n"
    "    const QPoint pos = addButton_\n"
    "        ? addButton_->mapToGlobal(QPoint(0, addButton_->height()))\n"
    "        : QCursor::pos();\n"
    "    emit addStageRequested(pos);\n"
    "}\n"
)


def patch_bar_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainDialogBarWidget.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, BAR_CPP_BACKUP)
    if "#include <QCursor>" not in text:
        text = text.replace(
            "#include <QPushButton>\n",
            "#include <QCursor>\n#include <QPushButton>\n",
            1,
        )
    text = replace_once(text, BAR_CPP_OLD_FUNC, BAR_CPP_NEW_FUNC,
                        "onAddStageClicked in dialog bar cpp")
    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")


# =============================================================================
# 5. ChainStudioPage.h — slot signature changes + new signal + helper
# =============================================================================

PAGE_H_OLD_SLOT = "    void onRailAddStageRequested();\n"
PAGE_H_NEW_SLOT = (
    f"    // --- {MARKER} ---\n"
    "    void onRailAddStageRequested(QPoint globalPos);\n"
    "    void showAddStageMenu(QPoint globalPos);\n"
    "    void onAddStageKindChosen(StageKind kind);\n"
)


def patch_page_header(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, PAGE_H_BACKUP)
    if "#include <QPoint>" not in text:
        text = text.replace(
            "#include <QString>\n",
            "#include <QPoint>\n#include <QString>\n",
            1,
        )
    text = replace_once(text, PAGE_H_OLD_SLOT, PAGE_H_NEW_SLOT,
                        "onRailAddStageRequested slot in page header")
    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")


# =============================================================================
# 6. ChainStudioPage.cpp — full rewrite with menu helper + filtered kinds
# =============================================================================

PAGE_CPP = r'''#include "chain/ChainStudioPage.h"

#include "ThemeManager.h"
// --- CHAIN STUDIO PASS 7B RAIL ---
#include "chain/ChainRailWidget.h"
// --- CHAIN STUDIO PASS 7C CANVAS ---
#include "chain/ChainCanvasWidget.h"
// --- CHAIN STUDIO PASS 7D1 CONFIG PANEL ---
#include "chain/ChainConfigPanelWidget.h"
// --- CHAIN STUDIO PASS 7D2 DIALOG BAR ---
#include "chain/ChainDialogBarWidget.h"
#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QDateTime>
#include <QUuid>

#include <QAction>
#include <QFrame>
#include <QHBoxLayout>
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

// --- ''' + MARKER + r''' ---
// Decide which stage kinds are valid as the NEXT stage given the
// current chain state. Pass 7d.3 wiring is purely visual:
//
//   - No image to feed forward (empty chain, or last stage was text-
//     only and has no completed variation) → T2I, T2V
//   - Image available (UploadedImage entry, OR last stage was image-
//     producing AND has a Locked or Completed variation) → I2I, I2V,
//     I2_3D
//
// Audio is reserved — disabled for now, surfaced in Pass 10 polish.
// Pass 8 will move this logic into the engine and consume engine
// state instead of stub state.

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
        // T2V, I2V produce video; I2_3D produces a 3D asset.
        // Pass 10 may permit "use a video keyframe as image input"
        // but for now treat only image-producing kinds as forward-
        // chainable to image-input stages.
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
    // Same handler as the rail's + button; both feed showAddStageMenu.
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
    stubChain_.stages.append(makeStub(StageKind::I2_3D, StageStatus::Draft,   0, 2));
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

// --- ''' + MARKER + r''' ---

void ChainStudioPage::onRailAddStageRequested(QPoint globalPos)
{
    // Single entry point for both + buttons (rail and dialog bar).
    showAddStageMenu(globalPos);
}

void ChainStudioPage::showAddStageMenu(QPoint globalPos)
{
    // Build a fresh QMenu each call — cheap, and keeps state simple.
    // Mirrors MainWindow.cpp's showTitleBarMenu / showLayoutMenu /
    // showSystemMenu pattern (stack-allocated QMenu, exec at pos).
    QMenu menu(this);

    const QVector<StageKind> kinds = validKindsForAdd(stubChain_);
    for (StageKind k : kinds)
    {
        QAction *action = menu.addAction(stageKindLabel(k));
        // Capture k by value into the lambda — connect routes through
        // the page's slot so Pass 8 can swap in engine.addStage(k).
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
    // Stub: Pass 8 will call engine.addStage(kind). For 7d.3 visual
    // review we acknowledge the click silently — the menu's presence
    // and the per-state filtering is what we're verifying.
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


def patch_page_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    backup_once(path, PAGE_CPP_BACKUP)
    write_crlf(path, PAGE_CPP)
    print(f"  Rewrote (CRLF): {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/chain/ChainRailWidget.h")
    patch_rail_header(project)
    print()
    print("qt_ui/chain/ChainRailWidget.cpp")
    patch_rail_cpp(project)
    print()
    print("qt_ui/chain/ChainDialogBarWidget.h")
    patch_bar_header(project)
    print()
    print("qt_ui/chain/ChainDialogBarWidget.cpp")
    patch_bar_cpp(project)
    print()
    print("qt_ui/chain/ChainStudioPage.h")
    patch_page_header(project)
    print()
    print("qt_ui/chain/ChainStudioPage.cpp")
    patch_page_cpp(project)
    print()
    print(f"Done — {MARKER} applied.")
    print()
    print("Run: .\\scripts\\dev\\run_ui.ps1")
    print()
    print("Verify: clicking either + button should pop a small menu of")
    print("kinds. With no image: T2I, T2V. After uploading an image to")
    print("the dialog bar: I2I, I2V, I→3D. Clicking a kind is a no-op")
    print("for now (Pass 8 wires engine.addStage).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
