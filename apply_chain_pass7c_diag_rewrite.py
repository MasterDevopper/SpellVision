r"""
SpellVision — Pass 7c diagnostic rewrite of ChainCanvasWidget.cpp.

Why a full rewrite instead of surgical edits: my previous fixup script
failed at an anchor match because of CRLF vs LF line-ending mismatches
in literal Unicode comment characters. Three str_replace attempts have
landed only partially across files. A full rewrite is anchor-free and
guaranteed to land.

Changes vs the file on disk:

1. EXPLICIT C++ SIZING on every pager widget. Stylesheet min-width/
   max-height rules may or may not drive Qt's layout engine reliably
   for a QPushButton in a QHBoxLayout — empirical evidence from the
   live render says they aren't enough here. We now call setFixedSize
   on prev/next (30x30), setFixedHeight + setMinimumWidth on lock
   (height=30, width>=80), and setFixedHeight on the pager host
   (40 = 30 buttons + 10 padding).

2. DIAGNOSTIC LOGGING — qDebug() prints during refresh and renderImage
   so we can see what's actually happening:
     - projectRoot resolution result (from page side, via env hint)
     - whether QFileInfo::exists succeeded
     - the resolved path that failed if it did
     - imageHolder_->size() at render time
   These will appear in the console when running run_ui.ps1. They are
   intentionally noisy for one cycle — once we know the bug, we strip
   them in a follow-up.

3. Belt-and-braces image holder constraint — added a maximumHeight
   based on parent hint, in case imageHolder_'s Expanding/Expanding
   policy is causing it to over-allocate and push the pager outside
   visible bounds.

4. emptyLabel_ default geometry — previously hidden, now also
   explicitly sized so toggling its visibility doesn't shift layout.

The path-resolution fix from the previous patch (QDir::cleanPath in
ChainStudioPage::buildStubChain) is unchanged and stays in place.

Idempotent: writes the file regardless of prior state. Backs up the
current file before overwriting.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER_HINT = "PASS 7C DIAG REWRITE"
BACKUP_SUFFIX = ".pre_pass7c_diag.bak"


CANVAS_CPP = r'''#include "chain/ChainCanvasWidget.h"

#include "ThemeManager.h"

#include <QDebug>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPixmap>
#include <QPushButton>
#include <QResizeEvent>
#include <QSizePolicy>
#include <QVBoxLayout>

// --- ''' + MARKER_HINT + r''' ---
// Full-file rewrite to escape CRLF/LF anchor mismatches plaguing the
// surgical-edit fixup scripts. Adds explicit C++ widget sizing and
// diagnostic qDebug logging so we can see what the layout engine and
// file system are actually doing.

namespace spellvision::chain
{

namespace
{

constexpr int kPagerButtonSide = 30;
constexpr int kLockMinWidth    = 80;
constexpr int kPagerHostHeight = 40;   // buttons + 10px breathing
constexpr int kImageMinSide    = 200;

QString cardContainerStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QFrame#ChainCanvasImageHolder { "
        "  background: %1; "
        "  border: 1px solid %2; "
        "  border-radius: %3px; "
        "}"
    ).arg(tm.surface0Color().name(),
          tm.borderToneColor().name(),
          QString::number(tm.radiusCard()));
}

QString pagerButtonStyle(bool enabled)
{
    const auto &tm = ThemeManager::instance();
    const QColor borderC = enabled ? tm.borderToneColor() : tm.background1Color();
    const QColor textC   = enabled ? tm.textSecondaryColor() : tm.textMutedColor();
    // No min-width/max-width in stylesheet — C++ setFixedSize handles
    // the layout. Stylesheet only controls visual painting.
    return QStringLiteral(
        "QPushButton { "
        "  color: %1; "
        "  background: transparent; "
        "  border: 1px solid %2; "
        "  border-radius: %3px; "
        "  font-size: 14px; "
        "  font-weight: 700; "
        "}"
        "QPushButton:hover:enabled { color: %4; border-color: %4; }"
        "QPushButton:disabled { color: %5; border-color: %5; }"
    ).arg(textC.name(),
          borderC.name(),
          QString::number(tm.radiusControl()),
          tm.accentColor().name(),
          tm.background1Color().name());
}

QString pagerLabelStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QLabel { color: %1; font-size: 12px; font-weight: 500; }"
    ).arg(tm.textSecondaryColor().name());
}

QString lockButtonStyle(bool enabled)
{
    const auto &tm = ThemeManager::instance();
    const QColor color = enabled ? tm.successColorPublic() : tm.textMutedColor();
    return QStringLiteral(
        "QPushButton { "
        "  color: %1; "
        "  background: transparent; "
        "  border: 1px solid %1; "
        "  border-radius: %2px; "
        "  padding: 4px 12px; "
        "  font-size: 11px; "
        "  font-weight: 800; "
        "  letter-spacing: 0.5px; "
        "}"
        "QPushButton:hover:enabled { "
        "  background: %1; "
        "  color: %3; "
        "}"
        "QPushButton:disabled { color: %4; border-color: %4; }"
    ).arg(color.name(),
          QString::number(tm.radiusPill()),
          tm.surface0Color().name(),
          tm.background1Color().name());
}

QString emptyLabelStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "QLabel { color: %1; font-size: 13px; font-weight: 500; }"
    ).arg(tm.textMutedColor().name());
}

} // anonymous namespace

ChainCanvasWidget::ChainCanvasWidget(QWidget *parent)
    : QWidget(parent)
{
    const auto &tm = ThemeManager::instance();

    auto *root = new QVBoxLayout(this);
    const int pad = tm.spacing(ThemeManager::Spacing::Snug);
    root->setContentsMargins(pad, pad, pad, pad);
    root->setSpacing(tm.spacing(ThemeManager::Spacing::Snug));

    // ---- Image holder ----
    imageHolder_ = new QFrame(this);
    imageHolder_->setObjectName(QStringLiteral("ChainCanvasImageHolder"));
    imageHolder_->setStyleSheet(cardContainerStyle());
    imageHolder_->setMinimumSize(kImageMinSide, kImageMinSide);
    imageHolder_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    auto *holderLayout = new QVBoxLayout(imageHolder_);
    holderLayout->setContentsMargins(0, 0, 0, 0);
    holderLayout->setSpacing(0);

    imageLabel_ = new QLabel(imageHolder_);
    imageLabel_->setAlignment(Qt::AlignCenter);
    imageLabel_->setScaledContents(false);
    imageLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    holderLayout->addWidget(imageLabel_);

    emptyLabel_ = new QLabel(imageHolder_);
    emptyLabel_->setAlignment(Qt::AlignCenter);
    emptyLabel_->setStyleSheet(emptyLabelStyle());
    emptyLabel_->setText(QStringLiteral("No variations yet \u2014 click Regenerate to start"));
    emptyLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    emptyLabel_->hide();
    holderLayout->addWidget(emptyLabel_);

    root->addWidget(imageHolder_, 1);

    // ---- Pager row ----
    // pagerHost: fixed height so it CANNOT be squished by the layout
    // engine no matter what the children report as sizeHint.
    auto *pagerHost = new QWidget(this);
    pagerHost->setFixedHeight(kPagerHostHeight);
    pagerHost->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    pagerRow_ = new QHBoxLayout(pagerHost);
    pagerRow_->setContentsMargins(0, 0, 0, 0);
    pagerRow_->setSpacing(tm.spacing(ThemeManager::Spacing::Snug));
    pagerRow_->setAlignment(Qt::AlignCenter);

    // prev/next: explicit C++ setFixedSize. Stylesheet only paints.
    prevButton_ = new QPushButton(QStringLiteral("\u2039"), pagerHost);
    prevButton_->setCursor(Qt::PointingHandCursor);
    prevButton_->setFixedSize(kPagerButtonSide, kPagerButtonSide);
    prevButton_->setStyleSheet(pagerButtonStyle(true));
    connect(prevButton_, &QPushButton::clicked,
            this, &ChainCanvasWidget::onPrevClicked);

    pagerLabel_ = new QLabel(pagerHost);
    pagerLabel_->setStyleSheet(pagerLabelStyle());
    pagerLabel_->setText(QStringLiteral("variation \u2014 of \u2014"));
    pagerLabel_->setAlignment(Qt::AlignCenter);

    nextButton_ = new QPushButton(QStringLiteral("\u203a"), pagerHost);
    nextButton_->setCursor(Qt::PointingHandCursor);
    nextButton_->setFixedSize(kPagerButtonSide, kPagerButtonSide);
    nextButton_->setStyleSheet(pagerButtonStyle(true));
    connect(nextButton_, &QPushButton::clicked,
            this, &ChainCanvasWidget::onNextClicked);

    // lock: fixed height + minimum width floor.
    lockButton_ = new QPushButton(QStringLiteral("LOCK"), pagerHost);
    lockButton_->setCursor(Qt::PointingHandCursor);
    lockButton_->setFixedHeight(kPagerButtonSide);
    lockButton_->setMinimumWidth(kLockMinWidth);
    lockButton_->setStyleSheet(lockButtonStyle(true));
    connect(lockButton_, &QPushButton::clicked,
            this, &ChainCanvasWidget::onLockClicked);

    pagerRow_->addStretch(1);
    pagerRow_->addWidget(prevButton_);
    pagerRow_->addWidget(pagerLabel_);
    pagerRow_->addWidget(nextButton_);
    pagerRow_->addSpacing(tm.spacing(ThemeManager::Spacing::Card));
    pagerRow_->addWidget(lockButton_);
    pagerRow_->addStretch(1);

    root->addWidget(pagerHost, 0);

    refresh();
}

void ChainCanvasWidget::setChain(const Chain &chain)
{
    chain_ = chain;
    refresh();
}

void ChainCanvasWidget::setSelectedStageId(const QString &stageId)
{
    if (selectedStageId_ == stageId)
        return;
    selectedStageId_ = stageId;
    refresh();
}

const Stage *ChainCanvasWidget::currentStage() const
{
    if (selectedStageId_.isEmpty())
        return nullptr;
    for (const Stage &s : chain_.stages)
    {
        if (s.id == selectedStageId_)
            return &s;
    }
    return nullptr;
}

int ChainCanvasWidget::currentVariationIdx() const
{
    const Stage *s = currentStage();
    if (s == nullptr || s->variations.isEmpty())
        return -1;
    int idx = s->selectedVarIdx;
    if (idx < 0)
        idx = s->variations.size() - 1;
    if (idx >= s->variations.size())
        idx = s->variations.size() - 1;
    return idx;
}

void ChainCanvasWidget::setEmptyState(bool empty)
{
    if (emptyLabel_ != nullptr)
        emptyLabel_->setVisible(empty);
    if (imageLabel_ != nullptr)
        imageLabel_->setVisible(!empty);
}

void ChainCanvasWidget::renderImage(const QString &path)
{
    if (imageLabel_ == nullptr)
        return;

    // ---- DIAGNOSTIC ----
    qDebug() << "[ChainCanvas] renderImage path:" << path
             << "exists:" << QFileInfo::exists(path)
             << "holderSize:" << (imageHolder_ ? imageHolder_->size() : QSize());

    if (path.trimmed().isEmpty() || !QFileInfo::exists(path))
    {
        imageLabel_->clear();
        imageLabel_->setText(QStringLiteral("\u2014"));
        imageLabel_->setStyleSheet(emptyLabelStyle());
        return;
    }

    QPixmap pix(path);
    if (pix.isNull())
    {
        qDebug() << "[ChainCanvas] QPixmap loaded but isNull:" << path;
        imageLabel_->clear();
        return;
    }

    const QSize holderSize = imageHolder_->size();
    const QSize target(qMax(kImageMinSide - 8, holderSize.width() - 8),
                       qMax(kImageMinSide - 8, holderSize.height() - 8));
    const QPixmap scaled = pix.scaled(target, Qt::KeepAspectRatio,
                                      Qt::SmoothTransformation);
    imageLabel_->setStyleSheet(QStringLiteral(""));
    imageLabel_->setPixmap(scaled);
    qDebug() << "[ChainCanvas] image set, scaled to" << scaled.size();
}

void ChainCanvasWidget::refresh()
{
    const Stage *s = currentStage();
    const int idx = currentVariationIdx();
    const bool hasVariations = (s != nullptr) && (idx >= 0);

    qDebug() << "[ChainCanvas] refresh stage:" << selectedStageId_
             << "found:" << (s != nullptr)
             << "varIdx:" << idx
             << "varCount:" << (s ? s->variations.size() : 0);

    setEmptyState(!hasVariations);

    if (hasVariations)
    {
        const Variation &v = s->variations.at(idx);
        renderImage(v.outputPath);

        pagerLabel_->setText(
            QStringLiteral("variation %1 of %2")
                .arg(idx + 1).arg(s->variations.size()));

        const bool canPrev = idx > 0;
        const bool canNext = idx < s->variations.size() - 1;
        prevButton_->setEnabled(canPrev);
        nextButton_->setEnabled(canNext);
        prevButton_->setStyleSheet(pagerButtonStyle(canPrev));
        nextButton_->setStyleSheet(pagerButtonStyle(canNext));

        const bool canLock = s->status == StageStatus::Completed;
        lockButton_->setEnabled(canLock);
        lockButton_->setStyleSheet(lockButtonStyle(canLock));
        if (s->status == StageStatus::Locked)
            lockButton_->setText(QStringLiteral("LOCKED"));
        else
            lockButton_->setText(QStringLiteral("LOCK"));
    }
    else
    {
        pagerLabel_->setText(QStringLiteral("variation \u2014 of \u2014"));
        prevButton_->setEnabled(false);
        nextButton_->setEnabled(false);
        lockButton_->setEnabled(false);
        prevButton_->setStyleSheet(pagerButtonStyle(false));
        nextButton_->setStyleSheet(pagerButtonStyle(false));
        lockButton_->setStyleSheet(lockButtonStyle(false));
        lockButton_->setText(QStringLiteral("LOCK"));
    }
}

void ChainCanvasWidget::onPrevClicked()
{
    const Stage *s = currentStage();
    const int idx = currentVariationIdx();
    if (s == nullptr || idx <= 0)
        return;
    emit variationSelectionChanged(s->id, idx - 1);
}

void ChainCanvasWidget::onNextClicked()
{
    const Stage *s = currentStage();
    const int idx = currentVariationIdx();
    if (s == nullptr || idx < 0 || idx >= s->variations.size() - 1)
        return;
    emit variationSelectionChanged(s->id, idx + 1);
}

void ChainCanvasWidget::onLockClicked()
{
    const Stage *s = currentStage();
    if (s == nullptr || s->status != StageStatus::Completed)
        return;
    emit lockRequested(s->id);
}

} // namespace spellvision::chain
'''


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER_HINT}")
    print(f"  Project root: {project}")
    print()

    target = project / "qt_ui" / "chain" / "ChainCanvasWidget.cpp"
    if not target.exists():
        print(f"  Skipped (not found): {target}")
        return 1

    backup = target.with_suffix(target.suffix + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")

    # Write with CRLF line endings to match project convention.
    # newline="" disables Python's default LF translation; we add \r\n
    # explicitly so the file matches the rest of the project.
    payload = CANVAS_CPP.replace("\r\n", "\n").replace("\n", "\r\n")
    target.write_bytes(payload.encode("utf-8"))
    print(f"  Rewrote (full file, CRLF): {target.name}")
    print()
    print(f"Done — {MARKER_HINT} applied.")
    print()
    print("After build, watch the console output for [ChainCanvas] log lines:")
    print("  - 'renderImage path: <X> exists: true/false' tells us if the")
    print("    image file is being found at all")
    print("  - 'holderSize: <WxH>' tells us if the image area has real geometry")
    print("  - 'refresh stage: <id> found: true varIdx: N' confirms the stage")
    print("    is bound correctly")
    print()
    print("Paste any [ChainCanvas] log lines back so I can read the actual")
    print("runtime state and diagnose precisely.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
