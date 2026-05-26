r"""
SpellVision — Pass 7c proper fix: reuse existing patterns.

After three rounds of guessing at canvas bugs, the diagnostic rewrite
gave us real runtime data:
    path: "<...>/SpellVision.jpg" exists: false
    holderSize: QSize(200, 200)   <-- stuck at minimum, not stretching

Both bugs trace to the same root cause: I invented patterns instead of
reusing what the project already had working.

ROOT CAUSE 1 — image file path:
    Brand images are at qt_ui/icons/SpellVision.{jpg,jpeg,png}, NOT at
    the project root. MainWindow.cpp already has loadBrandPixmap() which
    walks up 7 directory levels looking for the brand at any of the
    conventional paths. I should use that, not invent my own resolution.

ROOT CAUSE 2 — image holder not stretching:
    ImageGenerationPage.cpp:1037-1043 has the exact pattern needed,
    documented with this comment:

        // Pass 28E preview surface geometry lock:
        // Generated image pixmap dimensions must not become the QLabel
        // size hint that resizes the splitter/window. The layout owns
        // the canvas size; refreshPreview() scales the pixmap into the
        // existing canvas.
        previewLabel_->setMinimumSize(0, 0);
        previewLabel_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Ignored);

    My canvas had setMinimumSize(200, 200) + Expanding/Expanding instead.
    The QLabel's pixmap content was driving sizeHint, fighting the
    intended geometry, causing the holder to lock at minimum size and
    the pager to clip.

This rewrite:

(a) Removes my hand-rolled path resolution from ChainStudioPage::
    buildStubChain. Stub variations now use a small helper that
    duplicates the brandIconCandidates pattern (since extracting a
    shared helper is a bigger refactor than this pass should attempt;
    Pass 10 polish can promote to a shared util).

(b) Rewrites ChainCanvasWidget.cpp to apply the Pass 28E preview
    pattern verbatim: minimumSize(0,0) + Ignored/Ignored on the image
    label, with the manual scale in renderImage() owning the actual
    pixmap size.

(c) Keeps the explicit C++ setFixedSize on pager buttons that the
    previous diag rewrite added — that part was correct.

(d) Adds one more diagnostic line logging pager button geometry on
    refresh, so if next/LOCK are still missing we'll know exactly
    where they ended up.

Full file rewrite for both files (CRLF, no anchor matching). Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER_HINT = "PASS 7C PROPER FIX"
PAGE_BACKUP = ".pre_pass7c_proper_page.bak"
CANVAS_BACKUP = ".pre_pass7c_proper_canvas.bak"


PAGE_CPP = r'''#include "chain/ChainStudioPage.h"

#include "ThemeManager.h"
// --- CHAIN STUDIO PASS 7B RAIL ---
#include "chain/ChainRailWidget.h"
// --- CHAIN STUDIO PASS 7C CANVAS ---
#include "chain/ChainCanvasWidget.h"
#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QDateTime>
#include <QUuid>

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QSizePolicy>
#include <QVBoxLayout>

namespace spellvision::chain
{

namespace
{

constexpr int kTopStripHeight   = 56;
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

// --- ''' + MARKER_HINT + r''' ---
// Find any brand image in qt_ui/icons/ — same search pattern as
// MainWindow.cpp's brandIconCandidates() (lines 414-442). We duplicate
// rather than extract because pulling a shared helper is a Pass 10
// concern, and this duplication is small (3 names x 7 depth levels).
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
    auto *strip = new QFrame(this);
    strip->setFixedHeight(kTopStripHeight);
    strip->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    applyPlaceholderStyle(strip,
        QStringLiteral("TOP STRIP \u2014 upload box + dialog bar + + button (Pass 7d)"));
    return strip;
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
    auto *panel = new QFrame(this);
    panel->setFixedWidth(kConfigPanelWidth);
    panel->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);
    applyPlaceholderStyle(panel,
        QStringLiteral("CONFIG PANEL \u2014 selected stage's settings (Pass 7d)"));
    return panel;
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
    // --- ''' + MARKER_HINT + r''' ---
    // Use the project's existing brand-icon search pattern (mirrors
    // MainWindow.cpp's brandIconCandidates / loadBrandPixmap) to find
    // SpellVision.{jpg,jpeg,png} wherever they actually live, instead
    // of inventing path math that assumed the project root.
    const QString brand1 = findBrandImage(QStringLiteral("SpellVision"));
    const QString brand2 = findBrandImage(QStringLiteral("SpellVision2"));
    QStringList stubImages;
    if (!brand1.isEmpty()) stubImages << brand1;
    if (!brand2.isEmpty()) stubImages << brand2;
    if (stubImages.isEmpty())
        stubImages << QString();   // fallback to empty-state in canvas

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
}

void ChainStudioPage::onRailAddStageRequested()
{
    // Pass 7d will show a kind-picker menu here.
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
        }
        if (canvasWidget_ != nullptr)
            canvasWidget_->setChain(stubChain_);
        return;
    }
}

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
#include <QSizePolicy>
#include <QVBoxLayout>

// --- ''' + MARKER_HINT + r''' ---
// Adopts ImageGenerationPage.cpp:1037-1043's proven preview pattern:
//   imageLabel_->setMinimumSize(0, 0);
//   imageLabel_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Ignored);
// The "Pass 28E preview surface geometry lock" comment there explains
// why: pixmap content cannot drive sizeHint or it fights the layout.
// My earlier setMinimumSize(200,200) + Expanding/Expanding was the bug.
//
// Keeps the explicit C++ setFixedSize on pager buttons (correct from
// the diag rewrite). Diagnostic qDebug() retained for one more cycle
// so we can verify pager geometry on screen.

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

    // ---- Image holder — adopts the Pass 28E preview pattern ----
    imageHolder_ = new QFrame(this);
    imageHolder_->setObjectName(QStringLiteral("ChainCanvasImageHolder"));
    imageHolder_->setStyleSheet(cardContainerStyle());
    // CRITICAL: do NOT setMinimumSize on the holder — let the layout
    // own the geometry. The holder gets all remaining vertical space
    // via root->addWidget(..., stretch=1) below.
    imageHolder_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    auto *holderLayout = new QVBoxLayout(imageHolder_);
    holderLayout->setContentsMargins(0, 0, 0, 0);
    holderLayout->setSpacing(0);

    imageLabel_ = new QLabel(imageHolder_);
    imageLabel_->setAlignment(Qt::AlignCenter);
    imageLabel_->setScaledContents(false);
    // --- Pass 28E preview surface geometry lock (copied from
    // ImageGenerationPage.cpp:1037-1043) ---
    // Generated image pixmap dimensions must not become the QLabel
    // size hint that resizes the splitter/window. The layout owns the
    // canvas size; renderImage() scales the pixmap into the existing
    // canvas geometry.
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

    root->addWidget(imageHolder_, 1);   // takes all remaining height

    // ---- Pager row — fixed height, explicit C++ sizing on buttons ----
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
    const QSize target(qMax(64, holderSize.width() - 8),
                       qMax(64, holderSize.height() - 8));
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
        (Path("qt_ui/chain/ChainStudioPage.cpp"), PAGE_CPP, PAGE_BACKUP),
        (Path("qt_ui/chain/ChainCanvasWidget.cpp"), CANVAS_CPP, CANVAS_BACKUP),
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
    print("If the image still doesn't render, paste the [ChainCanvas] log")
    print("lines. The geometry log will show actual button sizes — if any")
    print("button is 0x0, that's the diagnostic. If the image holder is")
    print("now larger than 200x200, the Pass 28E pattern took effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
