r"""
SpellVision — Pass 7c rescale-on-show fix.

Visible from the previous render:

(Fixed!) Image now loads and renders. findBrandImage() found SpellVision.jpg
         at qt_ui/icons/ and QPixmap successfully loaded it.

(Remaining bug) Image renders at small natural size in the upper area of
    a now-correctly-large canvas region. Cause: refresh() is called from
    the ChainCanvasWidget constructor, BEFORE the widget has real
    geometry (the layout hasn't been computed yet). imageHolder_->size()
    at that moment is the initial uncomputed size, so pixmap.scaled()
    targets a tiny area. The pixmap displays unscaled because that
    initial scale was small.

Fix: override showEvent() to call refresh() AFTER first show, when
the layout has computed real geometry. Also override resizeEvent() to
rescale when the window resizes. Both delegated to refresh() since
refresh() is idempotent and cheap.

This is a header + cpp change. Full-file rewrites of both. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER_HINT = "PASS 7C RESCALE ON SHOW"
HDR_BACKUP = ".pre_pass7c_rescale_hdr.bak"
CPP_BACKUP = ".pre_pass7c_rescale_cpp.bak"


CANVAS_H = r'''#pragma once

// SpellVision — Chain Studio canvas (Pass 7c).
//
// The dominant region of ChainStudioPage. Shows the selected stage's
// selected variation as full media (image only for Pass 7c; video
// rendering deferred to Pass 7d or 8 to avoid mixing the QMediaPlayer
// complexity into this pass). Beneath the media: a pager row with
// prev/next controls, a "variation N of M" indicator, and an inline
// "Lock variation" pill button.
//
// Per the v3 mockup:
//   [image — 84% of canvas height, square aspect ratio]
//   [pager: <  variation N of M  >    Lock pill]
//
// Pass 7c populates the canvas against the same STUB Chain data the
// rail uses. Real engine wiring in Pass 8.
//
// The widget reads from spellvision::chain::Stage / Variation; like
// the rail, it does not touch the engine, store, or watcher. Selection
// signals come INTO the widget via setSelectedStageId(); navigation
// signals come OUT via signals the page connects to engine calls.
//
// Empty state: when a stage has no variations yet (Draft), the canvas
// shows a single placeholder line ("No variations yet — click Regenerate
// to start") instead of an image. Pager controls hide; Lock disables.

#include "chain/ChainModel.h"

#include <QString>
#include <QWidget>

class QFrame;
class QHBoxLayout;
class QLabel;
class QPushButton;
class QResizeEvent;
class QShowEvent;
class QVBoxLayout;

namespace spellvision::chain
{

class ChainCanvasWidget : public QWidget
{
    Q_OBJECT

public:
    explicit ChainCanvasWidget(QWidget *parent = nullptr);

    void setChain(const Chain &chain);
    void setSelectedStageId(const QString &stageId);

signals:
    void variationSelectionChanged(QString stageId, int newVarIdx);
    void lockRequested(QString stageId);

protected:
    // --- PASS 7C RESCALE ON SHOW ---
    // First refresh runs from the constructor before the layout has
    // computed real geometry, so the pixmap scales to a tiny area.
    // Override showEvent to re-refresh once the widget is actually
    // sized, and resizeEvent to rescale on window resize. Both
    // delegate to refresh() which is idempotent and cheap.
    void showEvent(QShowEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;

private slots:
    void onPrevClicked();
    void onNextClicked();
    void onLockClicked();

private:
    void refresh();
    const Stage *currentStage() const;
    int currentVariationIdx() const;
    void renderImage(const QString &path);
    void setEmptyState(bool empty);

    Chain  chain_;
    QString selectedStageId_;

    QFrame      *imageHolder_  = nullptr;
    QLabel      *imageLabel_   = nullptr;
    QLabel      *emptyLabel_   = nullptr;
    QPushButton *prevButton_   = nullptr;
    QLabel      *pagerLabel_   = nullptr;
    QPushButton *nextButton_   = nullptr;
    QPushButton *lockButton_   = nullptr;
    QHBoxLayout *pagerRow_     = nullptr;
};

} // namespace spellvision::chain
'''


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
#include <QShowEvent>
#include <QSizePolicy>
#include <QVBoxLayout>

// --- ''' + MARKER_HINT + r''' ---
// Adds showEvent/resizeEvent overrides so the pixmap rescales once the
// widget actually has geometry. Previously refresh() ran only from the
// constructor when imageHolder_->size() was its initial uncomputed
// value, producing a tiny scaled pixmap.

namespace spellvision::chain
{

namespace
{

constexpr int kPagerButtonSide = 30;
constexpr int kLockMinWidth    = 80;
constexpr int kPagerHostHeight = 40;

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

    imageHolder_ = new QFrame(this);
    imageHolder_->setObjectName(QStringLiteral("ChainCanvasImageHolder"));
    imageHolder_->setStyleSheet(cardContainerStyle());
    imageHolder_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    auto *holderLayout = new QVBoxLayout(imageHolder_);
    holderLayout->setContentsMargins(0, 0, 0, 0);
    holderLayout->setSpacing(0);

    imageLabel_ = new QLabel(imageHolder_);
    imageLabel_->setAlignment(Qt::AlignCenter);
    imageLabel_->setScaledContents(false);
    // Pass 28E preview surface geometry lock (copied from
    // ImageGenerationPage.cpp:1037-1043). Pixmap content must not
    // drive sizeHint or it fights the layout.
    imageLabel_->setMinimumSize(0, 0);
    imageLabel_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Ignored);
    imageLabel_->setWordWrap(true);
    holderLayout->addWidget(imageLabel_, 1);

    emptyLabel_ = new QLabel(imageHolder_);
    emptyLabel_->setAlignment(Qt::AlignCenter);
    emptyLabel_->setStyleSheet(emptyLabelStyle());
    emptyLabel_->setText(QStringLiteral("No variations yet \u2014 click Regenerate to start"));
    emptyLabel_->setMinimumSize(0, 0);
    emptyLabel_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Ignored);
    emptyLabel_->hide();
    holderLayout->addWidget(emptyLabel_);

    root->addWidget(imageHolder_, 1);

    auto *pagerHost = new QWidget(this);
    pagerHost->setFixedHeight(kPagerHostHeight);
    pagerHost->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    pagerRow_ = new QHBoxLayout(pagerHost);
    pagerRow_->setContentsMargins(0, 0, 0, 0);
    pagerRow_->setSpacing(tm.spacing(ThemeManager::Spacing::Snug));
    pagerRow_->setAlignment(Qt::AlignCenter);

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

void ChainCanvasWidget::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    // First-render rescale: now that the widget has actual geometry,
    // re-run refresh() so renderImage() sees the real holder size.
    refresh();
}

void ChainCanvasWidget::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    // Rescale the displayed pixmap to fill the new size.
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
    // If holder hasn't been sized yet, defer — showEvent will retry.
    if (holderSize.width() < 32 || holderSize.height() < 32)
    {
        qDebug() << "[ChainCanvas] holder not yet sized, deferring scale";
        imageLabel_->setPixmap(pix);   // store the unscaled pixmap so it's there
        return;
    }

    const QSize target(holderSize.width() - 8,
                       holderSize.height() - 8);
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
             << "varCount:" << (s ? s->variations.size() : 0)
             << "prev:" << (prevButton_ ? prevButton_->size() : QSize())
             << "next:" << (nextButton_ ? nextButton_->size() : QSize())
             << "lock:" << (lockButton_ ? lockButton_->size() : QSize());

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

    for relpath, payload, backup_suffix in [
        (Path("qt_ui/chain/ChainCanvasWidget.h"), CANVAS_H, HDR_BACKUP),
        (Path("qt_ui/chain/ChainCanvasWidget.cpp"), CANVAS_CPP, CPP_BACKUP),
    ]:
        target = project / relpath
        if not target.exists():
            print(f"  Skipped (not found): {target}")
            continue
        backup = target.with_suffix(target.suffix + backup_suffix)
        if not backup.exists():
            backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  Backup written: {backup.name}")
        crlf = payload.replace("\r\n", "\n").replace("\n", "\r\n")
        target.write_bytes(crlf.encode("utf-8"))
        print(f"  Rewrote (CRLF): {target.name}")
        print()

    print(f"Done — {MARKER_HINT} applied.")
    print()
    print("Run: .\\scripts\\dev\\run_ui.ps1")
    print()
    print("Image should now scale up to fill the canvas region after the")
    print("first showEvent fires. If the pager buttons (>, LOCK) are still")
    print("missing, paste any [ChainCanvas] log lines from the run output")
    print("so we can see the actual button sizes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
