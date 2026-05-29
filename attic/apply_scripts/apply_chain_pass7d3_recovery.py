r"""
SpellVision — Chain Studio Pass 7d.3 RECOVERY.

After several anchor-based attempts at Pass 7d.3 failed in partial
or confusing ways, this script implements 7d.3 cleanly via FULL FILE
REWRITES for all three affected cpp files, plus minimal surgical
header edits.

WHAT 7D.3 NEEDS TO DO:

1. ChainRailWidget signal: change addStageRequested() to addStageRequested(QPoint).
   Header: replace the signal declaration.
   Cpp: replace the passthrough connect with a lambda that computes
   button bottom-left global pos and emits with that QPoint.

2. ChainDialogBarWidget signal: same shape change.
   Header: replace signal declaration.
   Cpp: change emit addStageRequested() to compute pos and emit with QPoint.

3. ChainStudioPage:
   Header: change onRailAddStageRequested() to (QPoint), add showAddStageMenu
   and onAddStageKindChosen helpers.
   Cpp: full rewrite that includes the kind-picker menu helper, valid kinds
   filtering, and updated stub-chain mutation flow.

CURRENT DISK STATE (verified by uploaded files):
- All three files are at post-Pass-7d.2 state, NOT post-7d.3.
- The 7d.3 apply script's edits never landed (or were reverted).
- The dialog bar cpp has a stray '--- PASS 7D3 DIAGNOSTIC V2 ---' qDebug
  line that we'll preserve in the rewrite for the click flow trace.

This script accepts the disk-state-as-uploaded and replaces it with
post-7d.3 versions. No anchor matching - direct overwrites with backups.
Idempotent via marker check.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "CHAIN STUDIO PASS 7D3 RECOVERY"


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def write_crlf(path: Path, payload: str) -> None:
    crlf = payload.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_bytes(crlf.encode("utf-8"))


# =============================================================================
# ChainRailWidget.h — surgical signal signature change
# =============================================================================

def patch_rail_header(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainRailWidget.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, ".pre_pass7d3_recovery_rail_hdr.bak")

    # Ensure QPoint include
    if "#include <QPoint>" not in text:
        if "#include <QString>\r\n" in text:
            text = text.replace(
                "#include <QString>\r\n",
                "#include <QPoint>\r\n#include <QString>\r\n",
                1,
            )
        elif "#include <QString>\n" in text:
            text = text.replace(
                "#include <QString>\n",
                "#include <QPoint>\n#include <QString>\n",
                1,
            )

    # Replace signal — accept both CRLF and LF, with or without leading
    # comment block from any previous attempt.
    candidates = [
        "    void addStageRequested();\r\n",
        "    void addStageRequested();\n",
        # In case a previous attempt left a partial patch:
        "    void addStageRequested(QPoint globalPos);\r\n",
        "    void addStageRequested(QPoint globalPos);\n",
    ]
    new_sig_crlf = (
        f"    // --- {MARKER} ---\r\n"
        "    // Signal carries the button's bottom-left in global screen\r\n"
        "    // coords so the page can pop the kind-picker QMenu below it.\r\n"
        "    void addStageRequested(QPoint globalPos);\r\n"
    )
    new_sig_lf = new_sig_crlf.replace("\r\n", "\n")

    found = False
    for cand in candidates:
        if cand in text:
            new = new_sig_crlf if "\r\n" in cand else new_sig_lf
            text = text.replace(cand, new, 1)
            found = True
            break
    if not found:
        raise RuntimeError("Couldn't find addStageRequested signal declaration in rail header")

    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")


# =============================================================================
# ChainRailWidget.cpp — surgical connect rewrite to lambda
# =============================================================================

def patch_rail_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainRailWidget.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, ".pre_pass7d3_recovery_rail_cpp.bak")

    # Ensure QCursor include
    if "#include <QCursor>" not in text:
        if "#include <QPushButton>\r\n" in text:
            text = text.replace(
                "#include <QPushButton>\r\n",
                "#include <QCursor>\r\n#include <QPushButton>\r\n",
                1,
            )
        elif "#include <QPushButton>\n" in text:
            text = text.replace(
                "#include <QPushButton>\n",
                "#include <QCursor>\n#include <QPushButton>\n",
                1,
            )

    # Find and replace the connect block. Accept both CRLF and LF.
    # Use the 2-line form verified in the uploaded file.
    new_block_crlf = (
        f"    // --- {MARKER} ---\r\n"
        "    // Was a passthrough connect; now a lambda computes the button's\r\n"
        "    // bottom-left in global screen coords and emits with QPoint.\r\n"
        "    connect(addButton_, &QPushButton::clicked, this, [this]() {\r\n"
        "        const QPoint pos = addButton_\r\n"
        "            ? addButton_->mapToGlobal(QPoint(0, addButton_->height()))\r\n"
        "            : QCursor::pos();\r\n"
        "        emit addStageRequested(pos);\r\n"
        "    });\r\n"
    )
    new_block_lf = new_block_crlf.replace("\r\n", "\n")

    old_candidates = [
        # Passthrough form
        "    connect(addButton_, &QPushButton::clicked,\r\n"
        "            this, &ChainRailWidget::addStageRequested);\r\n",
        "    connect(addButton_, &QPushButton::clicked,\n"
        "            this, &ChainRailWidget::addStageRequested);\n",
        # Just in case the fixup somehow already landed in part
        "    connect(addButton_, &QPushButton::clicked, this, [this]() {\r\n",
        "    connect(addButton_, &QPushButton::clicked, this, [this]() {\n",
    ]

    found = False
    for cand in old_candidates[:2]:
        if cand in text:
            new = new_block_crlf if "\r\n" in cand else new_block_lf
            text = text.replace(cand, new, 1)
            found = True
            break
    if not found:
        # If the file already has a lambda form (3rd/4th candidate), assume
        # idempotent and skip.
        for cand in old_candidates[2:]:
            if cand in text:
                print(f"  Skipped (already lambda form): {path.name}")
                return
        raise RuntimeError("Couldn't find the addButton_ connect in rail cpp")

    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")


# =============================================================================
# ChainDialogBarWidget.h — surgical signal signature change
# =============================================================================

def patch_bar_header(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainDialogBarWidget.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, ".pre_pass7d3_recovery_bar_hdr.bak")

    if "#include <QPoint>" not in text:
        if "#include <QString>\r\n" in text:
            text = text.replace(
                "#include <QString>\r\n",
                "#include <QPoint>\r\n#include <QString>\r\n",
                1,
            )
        elif "#include <QString>\n" in text:
            text = text.replace(
                "#include <QString>\n",
                "#include <QPoint>\n#include <QString>\n",
                1,
            )

    candidates = [
        "    void addStageRequested();\r\n",
        "    void addStageRequested();\n",
        "    void addStageRequested(QPoint globalPos);\r\n",
        "    void addStageRequested(QPoint globalPos);\n",
    ]
    new_sig_crlf = (
        f"    // --- {MARKER} ---\r\n"
        "    void addStageRequested(QPoint globalPos);\r\n"
    )
    new_sig_lf = new_sig_crlf.replace("\r\n", "\n")

    found = False
    for cand in candidates:
        if cand in text:
            new = new_sig_crlf if "\r\n" in cand else new_sig_lf
            text = text.replace(cand, new, 1)
            found = True
            break
    if not found:
        raise RuntimeError("Couldn't find addStageRequested signal in dialog bar header")

    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")


# =============================================================================
# ChainDialogBarWidget.cpp — full file rewrite preserving existing structure
# =============================================================================
#
# The cpp is mostly already correct from Pass 7d.2. We need to:
#   1. Ensure QCursor + QDebug includes
#   2. Replace onAddStageClicked body to compute pos and emit with QPoint
#
# Surgical edit of just that function — much safer than full rewrite.

def patch_bar_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainDialogBarWidget.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, ".pre_pass7d3_recovery_bar_cpp.bak")

    # Ensure QCursor include
    if "#include <QCursor>" not in text:
        if "#include <QPushButton>\r\n" in text:
            text = text.replace(
                "#include <QPushButton>\r\n",
                "#include <QCursor>\r\n#include <QPushButton>\r\n",
                1,
            )
        elif "#include <QPushButton>\n" in text:
            text = text.replace(
                "#include <QPushButton>\n",
                "#include <QCursor>\n#include <QPushButton>\n",
                1,
            )

    # Ensure QDebug include (qDebug may already be transitively included
    # but being explicit is safer)
    if "#include <QDebug>" not in text:
        # Insert after QCursor (which we just added) or after QEvent
        if "#include <QCursor>\r\n" in text:
            text = text.replace(
                "#include <QCursor>\r\n",
                "#include <QCursor>\r\n#include <QDebug>\r\n",
                1,
            )
        elif "#include <QCursor>\n" in text:
            text = text.replace(
                "#include <QCursor>\n",
                "#include <QCursor>\n#include <QDebug>\n",
                1,
            )

    # Find onAddStageClicked function and replace its body using regex
    # so we don't depend on exact whitespace/comments.
    import re
    pattern = re.compile(
        r"(void ChainDialogBarWidget::onAddStageClicked\(\)\s*\{)"
        r"[^}]*"
        r"(\})",
        flags=re.DOTALL,
    )
    new_body = (
        r"\1\r\n"
        f"    // --- {MARKER} ---\r\n"
        "    qDebug() << \"[ChainStudio] DialogBar::onAddStageClicked fired\";\r\n"
        "    const QPoint pos = addButton_\r\n"
        "        ? addButton_->mapToGlobal(QPoint(0, addButton_->height()))\r\n"
        "        : QCursor::pos();\r\n"
        "    qDebug() << \"[ChainStudio] DialogBar emit pos:\" << pos;\r\n"
        "    emit addStageRequested(pos);\r\n"
        r"\2"
    )
    new_text, count = pattern.subn(new_body, text, count=1)
    if count != 1:
        raise RuntimeError(f"Couldn't match onAddStageClicked body (count={count})")

    path.write_text(new_text, encoding="utf-8")
    print(f"  Patched: {path.name}")


# =============================================================================
# ChainStudioPage.h — surgical: change slot signature + add helpers
# =============================================================================

def patch_page_header(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, ".pre_pass7d3_recovery_page_hdr.bak")

    if "#include <QPoint>" not in text:
        if "#include <QString>\r\n" in text:
            text = text.replace(
                "#include <QString>\r\n",
                "#include <QPoint>\r\n#include <QString>\r\n",
                1,
            )
        elif "#include <QString>\n" in text:
            text = text.replace(
                "#include <QString>\n",
                "#include <QPoint>\n#include <QString>\n",
                1,
            )

    # Find and replace the slot declaration. The actual declaration in
    # the page header — Pass 7d.2 left it as:
    #   void onRailAddStageRequested();
    # We want to change to (QPoint) and add two helpers.
    candidates = [
        "    void onRailAddStageRequested();\r\n",
        "    void onRailAddStageRequested();\n",
        "    void onRailAddStageRequested(QPoint globalPos);\r\n",
        "    void onRailAddStageRequested(QPoint globalPos);\n",
    ]
    new_decl_crlf = (
        f"    // --- {MARKER} ---\r\n"
        "    void onRailAddStageRequested(QPoint globalPos);\r\n"
        "    void showAddStageMenu(QPoint globalPos);\r\n"
        "    void onAddStageKindChosen(StageKind kind);\r\n"
    )
    new_decl_lf = new_decl_crlf.replace("\r\n", "\n")

    found = False
    for cand in candidates:
        if cand in text:
            new = new_decl_crlf if "\r\n" in cand else new_decl_lf
            text = text.replace(cand, new, 1)
            found = True
            break
    if not found:
        raise RuntimeError("Couldn't find onRailAddStageRequested slot in page header")

    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")


# =============================================================================
# ChainStudioPage.cpp — full file rewrite (the page is the central piece)
# =============================================================================

PAGE_CPP = '''#include "chain/ChainStudioPage.h"

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
#include <QDebug>
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

// --- ''' + MARKER + ''' ---

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
        case StageKind::T2I:   return QStringLiteral("T2I  \\u2014  text to image");
        case StageKind::T2V:   return QStringLiteral("T2V  \\u2014  text to video");
        case StageKind::I2I:   return QStringLiteral("I2I  \\u2014  image to image");
        case StageKind::I2V:   return QStringLiteral("I2V  \\u2014  image to video");
        case StageKind::I2_3D: return QStringLiteral("I\\u2192" "3D  \\u2014  image to 3D");
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

void ChainStudioPage::onRailAddStageRequested(QPoint globalPos)
{
    qDebug() << "[ChainStudio] Page::onRailAddStageRequested pos:" << globalPos;
    showAddStageMenu(globalPos);
}

void ChainStudioPage::showAddStageMenu(QPoint globalPos)
{
    qDebug() << "[ChainStudio] Page::showAddStageMenu pos:" << globalPos
             << "stubChain stages:" << stubChain_.stages.size()
             << "entryKind:" << static_cast<int>(stubChain_.entryKind);

    QMenu menu(this);

    const QVector<StageKind> kinds = validKindsForAdd(stubChain_);
    qDebug() << "[ChainStudio] valid kinds:" << kinds.size();
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

    qDebug() << "[ChainStudio] about to menu.exec, actions:" << menu.actions().size();
    QAction *picked = menu.exec(globalPos);
    qDebug() << "[ChainStudio] menu.exec returned, picked:"
             << (picked ? picked->text() : QStringLiteral("<nullptr>"));
}

void ChainStudioPage::onAddStageKindChosen(StageKind kind)
{
    qDebug() << "[ChainStudio] onAddStageKindChosen:" << static_cast<int>(kind);
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
    backup_once(path, ".pre_pass7d3_recovery_page_cpp.bak")
    # Fix the escaped unicode sequences in the page CPP (we used \\u
    # in the Python string literal to avoid Python interpreting them).
    page = PAGE_CPP.replace("\\u2014", "\u2014").replace("\\u2192", "\u2192")
    write_crlf(path, page)
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
    print("Build should clear. Clicking + add stage should pop a menu")
    print("with T2I / T2V kinds. Paste any [ChainStudio] log lines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
