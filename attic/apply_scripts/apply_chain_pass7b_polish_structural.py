r"""
SpellVision — Chain Studio Pass 7b-polish: structural visual fixups.

Four issues caught from the first visible render of ChainStudioPage:

(#1) Chain rail has no container chrome — nodes and connectors float
     while the other three regions are clearly bounded cards.
(#2) Status row text is squished — the rich-text bullet
     (&#9679; at font-size:13px inside a 10px label) breaks QLabel's
     line-height calculation, and the info column's addStretch(1)
     pushes content up instead of distributing it across 46px.
(#4) "+ add stage" button doesn't visually disable when canAddStage is
     false — opacity in Qt stylesheet doesn't apply per-pseudo-class
     reliably; need explicit color changes for QPushButton:disabled.
(#5) Page background is one tier too elevated. Used surface0 (#141b2a
     in NeonForge) but pages should use background0 (#070b12). The
     hierarchy is bg0 < bg1 < surface0 < surface1; cards (surface1)
     barely contrast against a surface0 page bg.

This patch is purely cosmetic — no behavior change, no new symbols.
Four surgical edits across three files:

1. ChainStudioPage.cpp — switch page background from surface0Color()
   to background0Color().
2. ChainRailWidget.cpp — wrap the scroll content in a styled container
   frame (rail-as-card, surface1/border/radiusCard); drop per-node
   borders in favor of selected-state-only accent ring; replace the
   rich-text bullet status row with a proper composite (real circle
   QLabel + text QLabel in a horizontal sublayout); strengthen the
   add button's disabled state with explicit color overrides.
3. (No engine or theme changes — all visual.)

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PASS 7B POLISH STRUCTURAL VISUAL"
PAGE_BACKUP_SUFFIX = ".pre_pass7b_polish_page.bak"
RAIL_BACKUP_SUFFIX = ".pre_pass7b_polish_rail.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Anchor not found: {label}")
    if text.count(old) > 1:
        raise RuntimeError(f"Anchor not unique ({text.count(old)}x): {label}")
    return text.replace(old, new, 1)


# =============================================================================
# 1. ChainStudioPage.cpp — page background
# =============================================================================
# surface0 -> background0. Aligns with the project's hierarchy:
#   bg0  = page bg
#   bg1  = page-level frame (we don't use this layer)
#   sfc0 = panel surface
#   sfc1 = elevated card  (what our four regions use)

PAGE_OLD = (
    '    setAutoFillBackground(true);\n'
    '    QPalette pal = palette();\n'
    '    pal.setColor(QPalette::Window, tm.surface0Color());\n'
    '    setPalette(pal);\n'
)

PAGE_NEW = (
    f'    // --- {MARKER}: page bg one tier deeper ---\n'
    '    setAutoFillBackground(true);\n'
    '    QPalette pal = palette();\n'
    '    pal.setColor(QPalette::Window, tm.background0Color());\n'
    '    setPalette(pal);\n'
)


def patch_page(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, PAGE_BACKUP_SUFFIX)
    text = replace_once(text, PAGE_OLD, PAGE_NEW, "page background palette")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# =============================================================================
# 2. ChainRailWidget.cpp — three structural fixes in one file
# =============================================================================
#
# Strategy: instead of trying to surgically str-replace four separate
# sections, rewrite the file in full from this script. Pass 7b's rail
# is small enough (~270 lines) that a full rewrite is cleaner than
# four overlapping anchors, and the diff against the .bak is what
# captures the change for review.

RAIL_REWRITE = r'''#include "chain/ChainRailWidget.h"

#include "ThemeManager.h"

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QMouseEvent>
#include <QPushButton>
#include <QScrollArea>
#include <QSizePolicy>
#include <QVBoxLayout>

// --- ''' + MARKER + r''' ---
// Rewrite addresses three visible issues from the first render:
//   - Rail had no container chrome (nodes floated)
//   - Status row's rich-text bullet broke QLabel line-height
//   - Add button's disabled state was visually identical to enabled
// See apply_chain_pass7b_polish_structural.py for the full rationale.

namespace spellvision::chain
{

namespace
{

constexpr int kNodeWidth      = 148;
constexpr int kNodeHeight     = 46;
constexpr int kThumbSide      = 46;
constexpr int kConnectorWidth = 30;
constexpr int kAddBtnWidth    = 118;
constexpr int kStatusDot      = 8;   // bumped from 6 — was hard to see

// Node base style. With the container card chrome added below, the
// per-node border is now redundant for unselected nodes — they just
// fill with a slightly elevated surface tone. Selected nodes get an
// accent ring as the only visible border.
QString nodeBaseStyle(bool selected)
{
    const auto &tm = ThemeManager::instance();
    if (selected)
    {
        return QStringLiteral(
            "QWidget#ChainRailNodeRoot { "
            "  background: %1; "
            "  border: 1px solid %2; "
            "  border-radius: %3px; "
            "}"
        ).arg(tm.surface0Color().name(),
              tm.accentColor().name(),
              QString::number(tm.radiusControl()));
    }
    return QStringLiteral(
        "QWidget#ChainRailNodeRoot { "
        "  background: %1; "
        "  border: 1px solid transparent; "
        "  border-radius: %2px; "
        "}"
    ).arg(tm.surface0Color().name(),
          QString::number(tm.radiusControl()));
}

QString thumbStyle(StageStatus status)
{
    const auto &tm = ThemeManager::instance();
    QColor base = tm.background1Color();
    if (status == StageStatus::Completed || status == StageStatus::Locked)
        base = base.lighter(125);
    return QStringLiteral(
        "QLabel { "
        "  background: %1; "
        "  border-radius: %2px; "
        "}"
    ).arg(base.name(), QString::number(tm.radiusControl()));
}

QColor statusColorFor(StageStatus status)
{
    const auto &tm = ThemeManager::instance();
    switch (status)
    {
        case StageStatus::Locked:     return tm.successColorPublic();
        case StageStatus::Queued:
        case StageStatus::Generating: return tm.warningColorPublic();
        case StageStatus::Failed:     return tm.errorColorPublic();
        case StageStatus::Completed:  return tm.accentColor();
        case StageStatus::Draft:      return tm.textMutedColor();
    }
    return tm.textMutedColor();
}

QString statusDotStyle(const QColor &color)
{
    return QStringLiteral(
        "QLabel { "
        "  background: %1; "
        "  border-radius: %2px; "
        "  min-width: %3px; max-width: %3px; "
        "  min-height: %3px; max-height: %3px; "
        "}"
    ).arg(color.name(),
          QString::number(kStatusDot / 2),
          QString::number(kStatusDot));
}

QString statusLabelText(StageStatus status)
{
    switch (status)
    {
        case StageStatus::Draft:      return QStringLiteral("Idle");
        case StageStatus::Queued:     return QStringLiteral("Queued");
        case StageStatus::Generating: return QStringLiteral("Generating");
        case StageStatus::Completed:  return QStringLiteral("Completed");
        case StageStatus::Failed:     return QStringLiteral("Failed");
        case StageStatus::Locked:     return QStringLiteral("Locked");
    }
    return QStringLiteral("Idle");
}

QString kindLabelText(StageKind kind)
{
    switch (kind)
    {
        case StageKind::T2I:   return QStringLiteral("T2I");
        case StageKind::T2V:   return QStringLiteral("T2V");
        case StageKind::I2I:   return QStringLiteral("I2I");
        case StageKind::I2V:   return QStringLiteral("I2V");
        case StageKind::I2_3D: return QStringLiteral(u8"I\u21923D");
        case StageKind::Audio: return QStringLiteral("AUDIO");
    }
    return QStringLiteral("?");
}

} // anonymous namespace

// ---------------------------------------------------------------------------
// ChainRailNodeWidget
// ---------------------------------------------------------------------------

ChainRailNodeWidget::ChainRailNodeWidget(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("ChainRailNodeRoot"));
    setFixedSize(kNodeWidth, kNodeHeight);
    setCursor(Qt::PointingHandCursor);

    const auto &tm = ThemeManager::instance();

    auto *row = new QHBoxLayout(this);
    row->setContentsMargins(0, 0, 0, 0);
    row->setSpacing(tm.spacing(ThemeManager::Spacing::Tight));

    thumb_ = new QLabel(this);
    thumb_->setFixedSize(kThumbSide, kThumbSide);
    row->addWidget(thumb_);

    // Info column — three rows, evenly distributed across 46px so the
    // node feels balanced top-to-bottom. No addStretch — explicit
    // spacing distribution.
    auto *info = new QVBoxLayout;
    info->setContentsMargins(0, 4, tm.spacing(ThemeManager::Spacing::Tight), 4);
    info->setSpacing(2);

    kindLabel_ = new QLabel(this);
    kindLabel_->setStyleSheet(QStringLiteral(
        "QLabel { color: %1; font-size: 12px; font-weight: 800; }"
    ).arg(tm.accentColor().name()));
    info->addWidget(kindLabel_);

    // Status row is a real composite — a circle QLabel + text QLabel
    // in a horizontal sublayout. Replaces the rich-text bullet that
    // broke vertical alignment.
    auto *statusRow = new QHBoxLayout;
    statusRow->setContentsMargins(0, 0, 0, 0);
    statusRow->setSpacing(4);

    statusDot_ = new QLabel(this);
    statusDot_->setFixedSize(kStatusDot, kStatusDot);
    statusRow->addWidget(statusDot_, 0, Qt::AlignVCenter);

    statusText_ = new QLabel(this);
    statusText_->setStyleSheet(QStringLiteral(
        "QLabel { color: %1; font-size: 10px; }"
    ).arg(tm.textSecondaryColor().name()));
    statusRow->addWidget(statusText_, 1, Qt::AlignVCenter);

    info->addLayout(statusRow);

    varRow_ = new QLabel(this);
    varRow_->setStyleSheet(QStringLiteral(
        "QLabel { color: %1; font-size: 9px; }"
    ).arg(tm.textMutedColor().name()));
    info->addWidget(varRow_);

    row->addLayout(info, 1);

    rebuildStyle();
}

void ChainRailNodeWidget::setStage(const Stage &stage)
{
    stageId_  = stage.id;
    kind_     = stage.kind;
    status_   = stage.status;
    varCount_ = stage.variations.size();

    if (kindLabel_ != nullptr)
        kindLabel_->setText(kindLabelText(kind_));

    if (statusDot_ != nullptr)
        statusDot_->setStyleSheet(statusDotStyle(statusColorFor(status_)));

    if (statusText_ != nullptr)
        statusText_->setText(statusLabelText(status_));

    if (varRow_ != nullptr)
    {
        if (varCount_ == 0)
            varRow_->setText(QStringLiteral("no variations"));
        else if (varCount_ == 1)
            varRow_->setText(QStringLiteral("1 variation"));
        else
            varRow_->setText(QString::number(varCount_) +
                             QStringLiteral(" variations"));
    }

    if (thumb_ != nullptr)
        thumb_->setStyleSheet(thumbStyle(status_));
}

void ChainRailNodeWidget::setSelected(bool selected)
{
    if (selected_ == selected)
        return;
    selected_ = selected;
    rebuildStyle();
}

void ChainRailNodeWidget::mousePressEvent(QMouseEvent *event)
{
    if (event->button() == Qt::LeftButton && !stageId_.isEmpty())
        emit clicked(stageId_);
    QWidget::mousePressEvent(event);
}

void ChainRailNodeWidget::rebuildStyle()
{
    setStyleSheet(nodeBaseStyle(selected_));
}

// ---------------------------------------------------------------------------
// ChainRailWidget
// ---------------------------------------------------------------------------

ChainRailWidget::ChainRailWidget(QWidget *parent)
    : QWidget(parent)
{
    const auto &tm = ThemeManager::instance();

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    // Container card — gives the rail the same chrome the other three
    // page regions have. Fixes the "nodes floating in space" problem.
    auto *card = new QFrame(this);
    card->setObjectName(QStringLiteral("ChainRailCardRoot"));
    card->setStyleSheet(QStringLiteral(
        "QFrame#ChainRailCardRoot { "
        "  background: %1; "
        "  border: 1px solid %2; "
        "  border-radius: %3px; "
        "}"
    ).arg(tm.surface1Color().name(),
          tm.borderToneColor().name(),
          QString::number(tm.radiusCard())));

    auto *cardLayout = new QVBoxLayout(card);
    const int pad = tm.spacing(ThemeManager::Spacing::Tight);
    cardLayout->setContentsMargins(pad, pad, pad, pad);
    cardLayout->setSpacing(0);

    scroll_ = new QScrollArea(card);
    scroll_->setWidgetResizable(true);
    scroll_->setFrameShape(QFrame::NoFrame);
    scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll_->setStyleSheet(QStringLiteral("QScrollArea { background: transparent; }"));

    content_ = new QWidget;
    content_->setStyleSheet(QStringLiteral("QWidget { background: transparent; }"));
    contentRow_ = new QHBoxLayout(content_);
    contentRow_->setContentsMargins(0, 0, 0, 0);
    contentRow_->setSpacing(0);
    contentRow_->setAlignment(Qt::AlignLeft);

    scroll_->setWidget(content_);
    cardLayout->addWidget(scroll_);

    root->addWidget(card);

    // Add button — explicit disabled colors so the state is legible.
    // Qt stylesheet's opacity rule isn't reliable per-pseudo-class, so
    // we hard-code the disabled appearance.
    addButton_ = new QPushButton(QStringLiteral("+\nadd stage"), this);
    addButton_->setCursor(Qt::PointingHandCursor);
    addButton_->setFixedWidth(kAddBtnWidth);
    addButton_->setFixedHeight(kNodeHeight);
    addButton_->setStyleSheet(QStringLiteral(
        "QPushButton { "
        "  color: %1; "
        "  background: transparent; "
        "  border: 1px dashed %2; "
        "  border-radius: %3px; "
        "  font-size: 9px; "
        "  font-weight: 500; "
        "}"
        "QPushButton:hover:enabled { color: %4; border-color: %4; }"
        "QPushButton:disabled { color: %5; border-color: %5; }"
    ).arg(tm.textMutedColor().name(),
          tm.borderToneColor().name(),
          QString::number(tm.radiusControl()),
          tm.accentColor().name(),
          tm.background1Color().name()));   // disabled = dim against rail card
    connect(addButton_, &QPushButton::clicked,
            this, &ChainRailWidget::addStageRequested);

    rebuild();
}

void ChainRailWidget::setChain(const Chain &chain)
{
    chain_ = chain;
    rebuild();
}

void ChainRailWidget::setSelectedStageId(const QString &stageId)
{
    if (selectedStageId_ == stageId)
        return;
    selectedStageId_ = stageId;
    for (int i = 0; i < contentRow_->count(); ++i)
    {
        if (auto *node = qobject_cast<ChainRailNodeWidget *>(
                contentRow_->itemAt(i)->widget()))
        {
            node->setSelected(node->stageId() == selectedStageId_);
        }
    }
}

void ChainRailWidget::setCanAddStage(bool canAdd)
{
    canAddStage_ = canAdd;
    if (addButton_ != nullptr)
        addButton_->setEnabled(canAdd);
}

void ChainRailWidget::rebuild()
{
    while (QLayoutItem *item = contentRow_->takeAt(0))
    {
        if (auto *w = item->widget())
        {
            if (w == addButton_)
                w->setParent(nullptr);
            else
                w->deleteLater();
        }
        delete item;
    }

    const auto &tm = ThemeManager::instance();

    for (int i = 0; i < chain_.stages.size(); ++i)
    {
        auto *node = new ChainRailNodeWidget(content_);
        node->setStage(chain_.stages.at(i));
        node->setSelected(node->stageId() == selectedStageId_);
        connect(node, &ChainRailNodeWidget::clicked,
                this, &ChainRailWidget::stageSelected);

        if (i > 0)
        {
            auto *connector = new QLabel(QStringLiteral(u8"\u2192"), content_);
            connector->setFixedWidth(kConnectorWidth);
            connector->setAlignment(Qt::AlignCenter);
            const bool nextLive =
                chain_.stages.at(i - 1).status == StageStatus::Locked;
            connector->setStyleSheet(QStringLiteral(
                "QLabel { color: %1; font-size: 16px; font-weight: 600; }"
            ).arg(nextLive
                ? tm.accentColor().name()
                : tm.textMutedColor().name()));
            contentRow_->addWidget(connector);
        }

        contentRow_->addWidget(node);
    }

    if (!chain_.stages.isEmpty())
        contentRow_->addSpacing(kConnectorWidth / 2);

    addButton_->setParent(content_);
    addButton_->setEnabled(canAddStage_);
    contentRow_->addWidget(addButton_);

    contentRow_->addStretch(1);
}

} // namespace spellvision::chain
'''


def patch_rail(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainRailWidget.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, RAIL_BACKUP_SUFFIX)
    write_text(path, RAIL_REWRITE)
    print(f"  Patched (full rewrite): {path.name}")


# =============================================================================
# 3. ChainRailWidget.h — add the new statusDot_ / statusText_ members
# =============================================================================
# The header still declares statusRow_ as a single QLabel; the rewrite
# above splits it into two children. One additive edit to the header.

HDR_BACKUP_SUFFIX = ".pre_pass7b_polish_hdr.bak"

HDR_OLD = (
    '    QLabel *thumb_     = nullptr;  // colored swatch for now; real\n'
    '                                   // thumbnail wiring lands in 7c/8\n'
    '    QLabel *kindLabel_ = nullptr;\n'
    '    QLabel *statusRow_ = nullptr;  // "● Locked" / "○ Idle" / etc.\n'
    '    QLabel *varRow_    = nullptr;  // "3 variations"\n'
)

HDR_NEW = (
    '    QLabel *thumb_      = nullptr;  // colored swatch for now; real\n'
    '                                    // thumbnail wiring lands in 7c/8\n'
    '    QLabel *kindLabel_  = nullptr;\n'
    f'    // --- {MARKER}: status dot + text split into two children ---\n'
    '    QLabel *statusDot_  = nullptr;  // colored circle\n'
    '    QLabel *statusText_ = nullptr;  // "Locked" / "Idle" / etc.\n'
    '    QLabel *varRow_     = nullptr;  // "3 variations"\n'
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
    backup_once(path, HDR_BACKUP_SUFFIX)
    text = replace_once(text, HDR_OLD, HDR_NEW, "node member declarations")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("qt_ui/chain/ChainStudioPage.cpp")
    patch_page(project)
    print()
    print("qt_ui/chain/ChainRailWidget.h")
    patch_rail_header(project)
    print()
    print("qt_ui/chain/ChainRailWidget.cpp")
    patch_rail(project)
    print()
    print(f"Done — {MARKER} applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
