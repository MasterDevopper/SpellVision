#include "chain/ChainCanvasWidget.h"

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

// --- PASS 7C RESCALE ON SHOW ---
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
        "QLabel { color: %1; font-size: 12px; font-weight: 600; }"
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
