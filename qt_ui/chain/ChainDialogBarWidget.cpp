#include "chain/ChainDialogBarWidget.h"

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
    // --- PASS 7D3 CLEAN ---
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

    uploadGlyph_ = new QLabel(QStringLiteral("⤒"), uploadBox_);
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
        QStringLiteral("◆  Describe — prompt, style cues, framing notes…"));
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
    // --- PASS 7D3 CLEAN ---
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
