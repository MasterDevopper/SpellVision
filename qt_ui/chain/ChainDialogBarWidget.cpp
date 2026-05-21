#include "chain/ChainDialogBarWidget.h"

#include "ThemeManager.h"

#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QEvent>
#include <QMouseEvent>
#include <QPixmap>
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

// Style strings. Distilled from v3 mockup CSS:
//   .upload  → uploadEmptyStyle
//   .upload.has → uploadLoadedStyle
//   .dbar    → dbarStyle (applied to promptEdit_)
//   .addbtn  → addBtnStyle

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
    // v3 mockup uses a diagonal gradient over panel1; emulate with
    // surface1 plus a solid accent border to differentiate from empty.
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
    const auto &tm = ThemeManager::instance();
    if (!enabled)
    {
        // Disabled variant — muted, like the rail's disabled add button.
        return QStringLiteral(
            "QPushButton { "
            "  background: %1; "
            "  border: 1px dashed %2; "
            "  border-radius: %3px; "
            "  color: %2; "
            "  font-size: 13px; "
            "  font-weight: 800; "
            "  padding: 0 12px; "
            "}"
        ).arg(tm.background0Color().name(),
              tm.textMutedColor().name(),
              QString::number(tm.radiusControl()));
    }
    // Enabled variant — v3 mockup uses an accent gradient; emulate
    // with a solid accent fill + dark text.
    return QStringLiteral(
        "QPushButton { "
        "  background: %1; "
        "  border: none; "
        "  border-radius: %2px; "
        "  color: %3; "
        "  font-size: 13px; "
        "  font-weight: 800; "
        "  padding: 0 12px; "
        "}"
        "QPushButton:hover { background: %4; }"
        "QPushButton:pressed { background: %5; }"
    ).arg(tm.accentColor().name(),
          QString::number(tm.radiusControl()),
          tm.background0Color().name(),
          tm.accentColor().lighter(110).name(),
          tm.accentColor().darker(110).name());
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

    // We stack two visual layers inside the upload box: the
    // empty-state glyph+caption pair, and (when loaded) a thumbnail
    // QLabel. The stacked layout lets us toggle visibility in
    // refresh() without re-creating widgets.
    auto *uploadStack = new QVBoxLayout(uploadBox_);
    uploadStack->setContentsMargins(0, 0, 0, 0);
    uploadStack->setSpacing(2);
    uploadStack->setAlignment(Qt::AlignCenter);

    uploadGlyph_ = new QLabel(QStringLiteral("\u2912"), uploadBox_);   // ⤒
    uploadGlyph_->setAlignment(Qt::AlignCenter);
    uploadGlyph_->setStyleSheet(uploadGlyphStyle());
    uploadGlyph_->setAttribute(Qt::WA_TransparentForMouseEvents);

    uploadCaption_ = new QLabel(QStringLiteral("IMG"), uploadBox_);
    uploadCaption_->setAlignment(Qt::AlignCenter);
    uploadCaption_->setStyleSheet(uploadCaptionStyle(false));
    uploadCaption_->setAttribute(Qt::WA_TransparentForMouseEvents);

    uploadStack->addWidget(uploadGlyph_, 0, Qt::AlignCenter);
    uploadStack->addWidget(uploadCaption_, 0, Qt::AlignCenter);

    // Thumbnail label sits underneath the same stack. It's hidden by
    // default; when shown it covers the glyph+caption.
    uploadThumb_ = new QLabel(uploadBox_);
    uploadThumb_->setAlignment(Qt::AlignCenter);
    uploadThumb_->setScaledContents(false);
    uploadThumb_->setStyleSheet(QStringLiteral(
        "QLabel { background: transparent; border: none; border-radius: 5px; }"));
    uploadThumb_->setGeometry(2, 2, kUploadBoxSide - 4, kUploadBoxSide - 4);
    // Click-through: events bypass the thumb so the upload box's
    // installed event filter (below) sees the press/release.
    uploadThumb_->setAttribute(Qt::WA_TransparentForMouseEvents);
    uploadThumb_->hide();

    // QFrame doesn't have a `clicked` signal, so install an event
    // filter on uploadBox_ that fires onUploadBoxClicked on mouse
    // release. Simpler than a transparent overlay button (which would
    // need careful z-ordering with the thumbnail label).
    uploadBox_->installEventFilter(this);

    row->addWidget(uploadBox_);

    // ---- Dialog bar (prompt input) ----
    promptEdit_ = new QLineEdit(this);
    promptEdit_->setObjectName(QStringLiteral("ChainDialogPromptEdit"));
    promptEdit_->setPlaceholderText(
        QStringLiteral("\u25C6  Describe \u2014 prompt, style cues, framing notes\u2026"));
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
    // ---- Upload state ----
    const bool hasImage = (chain_.entryKind == EntryKind::UploadedImage) &&
                          !chain_.sourceImagePath.isEmpty() &&
                          QFileInfo::exists(chain_.sourceImagePath);
    if (hasImage)
        applyUploadLoadedVisual(chain_.sourceImagePath);
    else
        applyUploadEmptyVisual();

    // ---- Prompt input ----
    // Prompt lives on stage 0 (the chain's entry stage). If no stages
    // exist yet, leave the field at whatever the user has typed.
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

    // ---- Add button enabled state ----
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
    // Fallback if pixmap load failed: revert to empty visual.
    applyUploadEmptyVisual();
}

void ChainDialogBarWidget::onUploadBoxClicked()
{
    // Open at the user's Pictures folder by default (consistent with
    // ImageGenerationPage's QFileDialog convention).
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
    emit addStageRequested();
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
