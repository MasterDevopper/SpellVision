#include "InspirationPage.h"
#include <QPair>
#include <QList>

#include "EyePickStore.h"
#include "OutputCardModel.h"
#include "ThemeManager.h"
#include "assets/ModelCardDelegate.h"
#include "assets/ModelCardModel.h"
#include "assets/ModelCardView.h"
#include "assets/ModelThumbnailCache.h"

#include <QComboBox>
#include <QDialog>
#include <QDir>
#include <QEvent>
#include <QMouseEvent>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QItemSelectionModel>
#include <QIODevice>
#include <QJsonDocument>
#include <QJsonObject>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QPixmap>
#include <QPixmapCache>
#include <QPushButton>
#include <QSettings>
#include <QShowEvent>
#include <QSplitter>
#include <QTextEdit>
#include <QVBoxLayout>

InspirationPage::InspirationPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("InspirationPage"));
    setFocusPolicy(Qt::StrongFocus);
    buildUi();
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });
    // Deliberately NOT scanning here -- see galleryLoaded_ in the header.
}

void InspirationPage::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    // Fallback for any path that shows this page without going through switchToMode's refresh.
    if (!galleryLoaded_)
        refreshGallery();
}

void InspirationPage::setProjectRoot(const QString &root)
{
    projectRoot_ = root.trimmed();
    pickStore_.setProjectRoot(projectRoot_);
    pickStore_.load();
    restoreHuntFolders();
    refreshTeacherStill();
    if (galleryModel_)
        galleryModel_->setPickMarks(pickStore_.marks());
}

void InspirationPage::buildUi()
{
    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(16, 14, 16, 14);
    root->setSpacing(10);

    auto *header = new QHBoxLayout();
    auto *titles = new QVBoxLayout();
    auto *eyebrow = new QLabel(QStringLiteral("INSPIRATION"), this);
    eyebrow->setObjectName(QStringLiteral("InspEyebrow"));
    heroTitle_ = new QLabel(QStringLiteral("Moodboard"), this);
    heroTitle_->setObjectName(QStringLiteral("InspTitle"));
    auto *sub = new QLabel(
        QStringLiteral("Browse recent outputs. KEEP / NO (K / N) grades them in-app. Export JSON for hunts."), this);
    sub->setObjectName(QStringLiteral("InspSub"));
    sub->setWordWrap(true);
    titles->addWidget(eyebrow);
    titles->addWidget(heroTitle_);
    titles->addWidget(sub);
    header->addLayout(titles, 1);

    filterEdit_ = new QLineEdit(this);
    filterEdit_->setObjectName(QStringLiteral("InspFilter"));
    filterEdit_->setPlaceholderText(QStringLiteral("Filter by name…"));
    filterEdit_->setClearButtonEnabled(true);
    filterEdit_->setMaximumWidth(220);
    pickFilterCombo_ = new QComboBox(this);
    pickFilterCombo_->setObjectName(QStringLiteral("InspPickFilter"));
    pickFilterCombo_->addItem(QStringLiteral("All"), QStringLiteral("all"));
    pickFilterCombo_->addItem(QStringLiteral("KEEP"), QStringLiteral("keep"));
    pickFilterCombo_->addItem(QStringLiteral("NO"), QStringLiteral("no"));
    pickFilterCombo_->addItem(QStringLiteral("Unmarked"), QStringLiteral("unmarked"));
    refreshButton_ = new QPushButton(QStringLiteral("Refresh"), this);
    exportPicksButton_ = new QPushButton(QStringLiteral("Export KEEP/NO"), this);
    addHuntFolderButton_ = new QPushButton(QStringLiteral("Add hunt folder"), this);
    clearHuntFoldersButton_ = new QPushButton(QStringLiteral("Clear hunt folders"), this);
    openHistoryButton_ = new QPushButton(QStringLiteral("Open History"), this);
    header->addWidget(filterEdit_, 0, Qt::AlignBottom);
    header->addWidget(pickFilterCombo_, 0, Qt::AlignBottom);
    header->addWidget(refreshButton_, 0, Qt::AlignBottom);
    header->addWidget(exportPicksButton_, 0, Qt::AlignBottom);
    header->addWidget(addHuntFolderButton_, 0, Qt::AlignBottom);
    header->addWidget(clearHuntFoldersButton_, 0, Qt::AlignBottom);
    header->addWidget(openHistoryButton_, 0, Qt::AlignBottom);
    root->addLayout(header);

    auto *split = new QSplitter(Qt::Horizontal, this);
    split->setObjectName(QStringLiteral("InspSplit"));
    split->setChildrenCollapsible(false);

    // Left: gallery
    auto *left = new QWidget(split);
    auto *leftLay = new QVBoxLayout(left);
    leftLay->setContentsMargins(0, 0, 0, 0);
    emptyHint_ = new QLabel(QStringLiteral("No outputs yet — generate on T2I, or Add hunt folder for OneDrive batches."), left);
    emptyHint_->setObjectName(QStringLiteral("InspEmpty"));
    emptyHint_->setAlignment(Qt::AlignCenter);
    emptyHint_->setWordWrap(true);

    thumbCache_ = new spellvision::assets::ModelThumbnailCache(this);
    galleryModel_ = new OutputCardModel(this);
    cardDelegate_ = new spellvision::assets::ModelCardDelegate(thumbCache_, this);
    galleryView_ = new spellvision::assets::ModelCardView(left);
    galleryView_->setModel(galleryModel_);
    galleryView_->setItemDelegate(cardDelegate_);
    QPixmapCache::setCacheLimit(64 * 1024);
    connect(thumbCache_, &spellvision::assets::ModelThumbnailCache::thumbnailReady,
            this, [this](const QString &key, int) {
                if (galleryModel_)
                    galleryModel_->noteThumbnailReady(key);
            });
    connect(galleryView_, &spellvision::assets::ModelCardView::inspectRequested,
            this, [this](const QModelIndex &idx) {
                if (galleryView_)
                    galleryView_->setCurrentIndex(idx);
                onSelectionChanged();
            });
    connect(galleryView_, &spellvision::assets::ModelCardView::loadRequested,
            this, [this](const QModelIndex &idx) {
                if (galleryView_)
                    galleryView_->setCurrentIndex(idx);
                onSelectionChanged();
                sendToI2I();
            });
    connect(galleryView_->selectionModel(), &QItemSelectionModel::currentChanged,
            this, [this](const QModelIndex &, const QModelIndex &) { onSelectionChanged(); });

    leftLay->addWidget(emptyHint_);
    leftLay->addWidget(galleryView_, 1);
    split->addWidget(left);

    // Right: prompt inspector
    auto *right = new QFrame(split);
    right->setObjectName(QStringLiteral("InspInspector"));
    auto *rightLay = new QVBoxLayout(right);
    rightLay->setContentsMargins(12, 12, 12, 12);
    rightLay->setSpacing(8);

    auto *teacherEyebrow = new QLabel(QStringLiteral("TEACHER"), right);
    teacherEyebrow->setObjectName(QStringLiteral("InspEyebrow"));
    teacherStillLabel_ = new QLabel(right);
    teacherStillLabel_->setObjectName(QStringLiteral("InspTeacherStill"));
    teacherStillLabel_->setMinimumHeight(180);
    teacherStillLabel_->setAlignment(Qt::AlignCenter);
    teacherStillLabel_->setScaledContents(false);
    teacherPathLabel_ = new QLabel(QStringLiteral("No teacher pinned."), right);
    teacherPathLabel_->setObjectName(QStringLiteral("InspMeta"));
    teacherPathLabel_->setWordWrap(true);
    pinTeacherButton_ = new QPushButton(QStringLiteral("Pin teacher…"), right);

    auto *inspEyebrow = new QLabel(QStringLiteral("SELECTED"), right);
    inspEyebrow->setObjectName(QStringLiteral("InspEyebrow"));
    selectedStillLabel_ = new QLabel(right);
    selectedStillLabel_->setObjectName(QStringLiteral("InspSelectedStill"));
    selectedStillLabel_->setMinimumHeight(420);
    selectedStillLabel_->setAlignment(Qt::AlignCenter);
    selectedStillLabel_->setScaledContents(false);
    selectedStillLabel_->setText(QStringLiteral("Select a card. Click the still to zoom."));
    selectedStillLabel_->installEventFilter(this);
    selectedStillLabel_->setCursor(Qt::PointingHandCursor);
    metaLabel_ = new QLabel(QStringLiteral("Select a card to load its prompt."), right);
    metaLabel_->setObjectName(QStringLiteral("InspMeta"));
    metaLabel_->setWordWrap(true);

    auto *promptLab = new QLabel(QStringLiteral("Prompt"), right);
    promptLab->setObjectName(QStringLiteral("InspFieldLabel"));
    promptEdit_ = new QTextEdit(right);
    promptEdit_->setObjectName(QStringLiteral("InspPrompt"));
    promptEdit_->setPlaceholderText(QStringLiteral("Prompt loads from the output sidecar when available…"));
    promptEdit_->setMinimumHeight(120);

    auto *negLab = new QLabel(QStringLiteral("Negative"), right);
    negLab->setObjectName(QStringLiteral("InspFieldLabel"));
    negativeEdit_ = new QTextEdit(right);
    negativeEdit_->setObjectName(QStringLiteral("InspNegative"));
    negativeEdit_->setPlaceholderText(QStringLiteral("Optional negative prompt…"));
    negativeEdit_->setMaximumHeight(80);

    auto *actions = new QHBoxLayout();
    sendT2IButton_ = new QPushButton(QStringLiteral("Send → T2I"), right);
    sendT2IButton_->setObjectName(QStringLiteral("PrimaryActionButton"));
    sendI2IButton_ = new QPushButton(QStringLiteral("Send → I2I"), right);
    keepButton_ = new QPushButton(QStringLiteral("KEEP (K)"), right);
    noButton_ = new QPushButton(QStringLiteral("NO (N)"), right);
    actions->addWidget(sendT2IButton_);
    actions->addWidget(sendI2IButton_);
    actions->addWidget(keepButton_);
    actions->addWidget(noButton_);
    actions->addStretch(1);

    rightLay->addWidget(teacherEyebrow);
    rightLay->addWidget(teacherStillLabel_);
    rightLay->addWidget(teacherPathLabel_);
    rightLay->addWidget(pinTeacherButton_);
    rightLay->addWidget(inspEyebrow);
    rightLay->addWidget(selectedStillLabel_);
    rightLay->addWidget(metaLabel_);
    rightLay->addWidget(promptLab);
    rightLay->addWidget(promptEdit_, 1);
    rightLay->addWidget(negLab);
    rightLay->addWidget(negativeEdit_);
    rightLay->addLayout(actions);
    rightLay->addStretch(0);
    split->addWidget(right);
    split->setStretchFactor(0, 3);
    split->setStretchFactor(1, 2);
    split->setSizes({720, 360});

    root->addWidget(split, 1);

    connect(refreshButton_, &QPushButton::clicked, this, &InspirationPage::refreshGallery);
    connect(exportPicksButton_, &QPushButton::clicked, this, &InspirationPage::exportPicks);
    connect(addHuntFolderButton_, &QPushButton::clicked, this, &InspirationPage::addHuntFolder);
    connect(clearHuntFoldersButton_, &QPushButton::clicked, this, &InspirationPage::clearHuntFolders);
    connect(pinTeacherButton_, &QPushButton::clicked, this, &InspirationPage::pinTeacherStill);
    connect(openHistoryButton_, &QPushButton::clicked, this, [this]() { emit openHistoryRequested(); });
    connect(sendT2IButton_, &QPushButton::clicked, this, &InspirationPage::sendToT2I);
    connect(sendI2IButton_, &QPushButton::clicked, this, &InspirationPage::sendToI2I);
    connect(keepButton_, &QPushButton::clicked, this, [this]() { applyPick(QStringLiteral("keep")); });
    connect(noButton_, &QPushButton::clicked, this, [this]() { applyPick(QStringLiteral("no")); });
    connect(pickFilterCombo_, &QComboBox::currentIndexChanged, this, [this]() { refreshGallery(); });
    connect(filterEdit_, &QLineEdit::textChanged, this, [this](const QString &text) {
        if (galleryModel_)
            galleryModel_->setNameNeedle(text);
        refreshGallery();
    });
}

void InspirationPage::applyTheme()
{
    const auto &theme = ThemeManager::instance();
    using C = ThemeManager::Color;
    using T = ThemeManager::Type;
    setStyleSheet(QStringLiteral(
                      "#InspirationPage { background: transparent; }"
                      "QLabel#InspEyebrow { @caption@ letter-spacing: 0.12em; color: @acc@; }"
                      "QLabel#InspTitle { @display@ color: @hi@; }"
                      "QLabel#InspSub, QLabel#InspMeta, QLabel#InspEmpty { @body@ color: @mid@; }"
                      "QLabel#InspFieldLabel { @caption@ color: @mid@; }"
                      "QFrame#InspInspector {"
                      " background: @s1@; border: 1px solid @bd@; border-radius: 10px; }"
                      "QTextEdit, QLineEdit {"
                      " background: @s0@; color: @hi@; border: 1px solid @bd@;"
                      " border-radius: 6px; padding: 8px; }"
                      "QPushButton#PrimaryActionButton {"
                      " background: @acc@; color: white; border: none; border-radius: 8px;"
                      " padding: 10px 14px; font-weight: 700; }"
                      "QPushButton {"
                      " background: rgba(255,255,255,0.03); color: @hi@;"
                      " border: 1px solid @bd@; border-radius: 6px; padding: 8px 12px; }")
                      .replace(QLatin1String("@display@"), theme.fontCss(T::Display))
                      .replace(QLatin1String("@body@"), theme.fontCss(T::Body))
                      .replace(QLatin1String("@caption@"), theme.fontCss(T::Caption))
                      .replace(QLatin1String("@hi@"), theme.css(C::TextHi))
                      .replace(QLatin1String("@mid@"), theme.css(C::TextMid))
                      .replace(QLatin1String("@s1@"), theme.css(C::Surface1))
                      .replace(QLatin1String("@s0@"), theme.css(C::Surface0))
                      .replace(QLatin1String("@bd@"), theme.css(C::Border))
                      .replace(QLatin1String("@acc@"), theme.css(C::Accent)));
}

void InspirationPage::refreshGallery()
{
    if (!galleryModel_)
        return;
    galleryLoaded_ = true;
    pickStore_.load();
    if (pickFilterCombo_)
        galleryModel_->setPickFilter(pickFilterCombo_->currentData().toString());
    galleryModel_->setPickMarks(pickStore_.marks());
    const int n = galleryModel_->reload();
    if (emptyHint_)
        emptyHint_->setVisible(n == 0);
    if (galleryView_)
        galleryView_->setVisible(n > 0);
    if (heroTitle_)
        heroTitle_->setText(n > 0 ? QStringLiteral("Moodboard · %1").arg(n)
                                  : QStringLiteral("Moodboard"));
}

void InspirationPage::onSelectionChanged()
{
    if (!galleryView_ || !galleryModel_)
        return;
    const QModelIndex idx = galleryView_->currentIndex();
    const auto *out = galleryModel_->outputAt(idx.row());
    if (!out) {
        selectedPath_.clear();
        selectedModeId_.clear();
        if (metaLabel_)
            metaLabel_->setText(QStringLiteral("Select a card to load its prompt."));
        refreshSelectedStill();
        return;
    }
    selectedPath_ = out->path;
    selectedModeId_ = out->modeId;
    if (metaLabel_) {
        const QString mark = pickStore_.markFor(out->path);
        const QString grade = mark.isEmpty() ? QStringLiteral("unmarked") : mark.toUpper();
        metaLabel_->setText(QStringLiteral("%1\n%2\n%3\nGrade: %4")
                                .arg(out->fullName, out->subtitle,
                                     QDir::toNativeSeparators(out->path), grade));
    }
    const QJsonObject meta = loadSidecarForPath(out->path);
    if (promptEdit_) {
        const QString p = meta.value(QStringLiteral("prompt")).toString();
        promptEdit_->setPlainText(p.isEmpty()
                                      ? QStringLiteral("(no prompt sidecar — type one to send)")
                                      : p);
        if (p.isEmpty())
            promptEdit_->selectAll();
    }
    if (negativeEdit_)
        negativeEdit_->setPlainText(meta.value(QStringLiteral("negative_prompt")).toString());
    refreshSelectedStill();
}

QJsonObject InspirationPage::loadSidecarForPath(const QString &mediaPath) const
{
    const QFileInfo fi(mediaPath);
    const QString sidecar = fi.absolutePath() + QLatin1Char('/') + fi.completeBaseName() + QStringLiteral(".json");
    QFile f(sidecar);
    if (f.open(QIODevice::ReadOnly))
        return QJsonDocument::fromJson(f.readAll()).object();

    QJsonObject fallback;
    const QString promptTxt = fi.absolutePath() + QStringLiteral("/prompt.txt");
    QFile promptFile(promptTxt);
    if (promptFile.open(QIODevice::ReadOnly))
        fallback.insert(QStringLiteral("prompt"), QString::fromUtf8(promptFile.readAll()).trimmed());
    return fallback;
}

void InspirationPage::addHuntFolder()
{
    const QString chosen = QFileDialog::getExistingDirectory(this, QStringLiteral("Add hunt folder"));
    if (chosen.trimmed().isEmpty() || !galleryModel_)
        return;
    QStringList roots = galleryModel_->extraRoots();
    roots.push_back(chosen);
    galleryModel_->setExtraRoots(roots);
    persistHuntFolders();
    refreshGallery();
}

void InspirationPage::clearHuntFolders()
{
    if (!galleryModel_)
        return;
    galleryModel_->setExtraRoots({});
    persistHuntFolders();
    refreshGallery();
}

void InspirationPage::persistHuntFolders()
{
    QSettings settings;
    settings.setValue(QStringLiteral("inspiration/extra_roots"),
                      galleryModel_ ? galleryModel_->extraRoots() : QStringList());
}

void InspirationPage::restoreHuntFolders()
{
    if (!galleryModel_)
        return;
    QSettings settings;
    galleryModel_->setExtraRoots(settings.value(QStringLiteral("inspiration/extra_roots")).toStringList());
}

QJsonObject InspirationPage::recipeDraft() const
{
    // What made the picture, in the names the cockpit reads. The prompt fields on this page are
    // authoritative -- the user may have edited them -- so they are set by the callers, not here.
    // Everything else comes from the render's own sidecar, which build_metadata_payload writes
    // beside every output; a KEEP that only carried its prompt was half a recipe.
    QJsonObject draft;
    if (selectedPath_.isEmpty())
        return draft;
    const QJsonObject meta = loadSidecarForPath(selectedPath_);
    if (meta.isEmpty())
        return draft;

    // sidecar key -> draft key. Same name where applyWorkflowDraft already uses the sidecar's.
    static const QList<QPair<QString, QString>> kRecipeKeys = {
        {QStringLiteral("model"), QStringLiteral("checkpoint")},
        {QStringLiteral("model_display"), QStringLiteral("checkpoint_display")},
        {QStringLiteral("sampler"), QStringLiteral("sampler")},
        {QStringLiteral("scheduler"), QStringLiteral("scheduler")},
        {QStringLiteral("steps"), QStringLiteral("steps")},
        {QStringLiteral("cfg"), QStringLiteral("cfg")},
        {QStringLiteral("seed"), QStringLiteral("seed")},
        {QStringLiteral("width"), QStringLiteral("width")},
        {QStringLiteral("height"), QStringLiteral("height")},
        {QStringLiteral("strength"), QStringLiteral("strength")},
        {QStringLiteral("frames"), QStringLiteral("frames")},
        {QStringLiteral("media_type"), QStringLiteral("media_type")},
        {QStringLiteral("workflow_path"), QStringLiteral("source_workflow_path")},
        {QStringLiteral("workflow_profile_path"), QStringLiteral("source_profile_path")},
        {QStringLiteral("workflow_profile_name"), QStringLiteral("source_name")},
    };
    for (const auto &pair : kRecipeKeys)
    {
        const QJsonValue value = meta.value(pair.first);
        if (value.isUndefined() || value.isNull())
            continue;
        if (value.isString() && value.toString().trimmed().isEmpty())
            continue;
        draft.insert(pair.second, value);
    }
    return draft;
}

void InspirationPage::sendToT2I()
{
    QJsonObject draft = recipeDraft();
    draft.insert(QStringLiteral("prompt"),
                 promptEdit_ ? promptEdit_->toPlainText().trimmed() : QString());
    draft.insert(QStringLiteral("negative_prompt"),
                 negativeEdit_ ? negativeEdit_->toPlainText().trimmed() : QString());
    emit sendToGenerationRequested(QStringLiteral("t2i"), draft);
    emit navigateRequested(QStringLiteral("t2i"));
}

void InspirationPage::sendToI2I()
{
    QJsonObject draft = recipeDraft();
    draft.insert(QStringLiteral("prompt"),
                 promptEdit_ ? promptEdit_->toPlainText().trimmed() : QString());
    draft.insert(QStringLiteral("negative_prompt"),
                 negativeEdit_ ? negativeEdit_->toPlainText().trimmed() : QString());
    if (!selectedPath_.isEmpty())
        draft.insert(QStringLiteral("input_image"), selectedPath_);
    emit sendToGenerationRequested(QStringLiteral("i2i"), draft);
    emit navigateRequested(QStringLiteral("i2i"));
}

void InspirationPage::useAsHomeStarter()
{
    // Reserved — Home can listen later.
}

void InspirationPage::applyPick(const QString &mark)
{
    if (selectedPath_.isEmpty())
        return;
    pickStore_.setMark(selectedPath_, mark);
    pickStore_.save();
    if (galleryModel_)
        galleryModel_->setPickMarks(pickStore_.marks());
    onSelectionChanged();
    advanceSelection();
}

void InspirationPage::advanceSelection()
{
    if (!galleryView_ || !galleryModel_)
        return;
    const int row = galleryView_->currentIndex().row();
    const int next = row + 1;
    if (next >= 0 && next < galleryModel_->rowCount())
        galleryView_->setCurrentIndex(galleryModel_->index(next, 0));
}

void InspirationPage::exportPicks()
{
    const QString dest = QFileDialog::getSaveFileName(
        this,
        QStringLiteral("Export KEEP/NO"),
        QDir(projectRoot_).filePath(QStringLiteral("runtime/eye_picks.json")),
        QStringLiteral("JSON (*.json)"));
    if (!dest.trimmed().isEmpty())
        pickStore_.exportTo(dest);
}

void InspirationPage::pinTeacherStill()
{
    const QString chosen = QFileDialog::getOpenFileName(
        this,
        QStringLiteral("Pin teacher still"),
        teacherStillPath_.isEmpty() ? projectRoot_ : teacherStillPath_,
        QStringLiteral("Images (*.png *.jpg *.jpeg *.webp)"));
    if (chosen.trimmed().isEmpty())
        return;
    teacherStillPath_ = QDir::fromNativeSeparators(chosen);
    QSettings settings;
    settings.setValue(QStringLiteral("inspiration/teacher_still"), teacherStillPath_);
    refreshTeacherStill();
}

void InspirationPage::refreshTeacherStill()
{
    QSettings settings;
    teacherStillPath_ = settings.value(QStringLiteral("inspiration/teacher_still")).toString().trimmed();
    if (teacherPathLabel_)
        teacherPathLabel_->setText(teacherStillPath_.isEmpty()
                                       ? QStringLiteral("No teacher pinned.")
                                       : QDir::toNativeSeparators(teacherStillPath_));
    if (!teacherStillLabel_)
        return;
    if (teacherStillPath_.isEmpty() || !QFileInfo::exists(teacherStillPath_))
    {
        teacherStillLabel_->setPixmap({});
        teacherStillLabel_->setText(QStringLiteral("Pin a teacher still to compare."));
        return;
    }
    QPixmap pix(teacherStillPath_);
    if (pix.isNull())
    {
        teacherStillLabel_->setText(QStringLiteral("Could not load teacher still."));
        return;
    }
    teacherStillLabel_->setText(QString());
    teacherStillLabel_->setPixmap(pix.scaled(teacherStillLabel_->width() > 40 ? teacherStillLabel_->width() : 280,
                                             220,
                                             Qt::KeepAspectRatio,
                                             Qt::SmoothTransformation));
}

void InspirationPage::refreshSelectedStill()
{
    if (!selectedStillLabel_)
        return;
    if (selectedPath_.isEmpty() || !QFileInfo::exists(selectedPath_))
    {
        selectedStillLabel_->setPixmap({});
        selectedStillLabel_->setText(QStringLiteral("Select a card. Click the still to zoom."));
        if (lightboxImage_)
            lightboxImage_->setPixmap({});
        return;
    }
    QPixmap pix(selectedPath_);
    if (pix.isNull())
    {
        selectedStillLabel_->setText(QStringLiteral("Could not load still."));
        return;
    }
    selectedStillLabel_->setText(QString());
    const int w = selectedStillLabel_->width() > 80 ? selectedStillLabel_->width() : 420;
    selectedStillLabel_->setPixmap(pix.scaled(w, 420, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    if (lightboxImage_ && lightbox_ && lightbox_->isVisible())
    {
        const QSize box = lightbox_->size() - QSize(32, 32);
        lightboxImage_->setPixmap(pix.scaled(box.width() > 40 ? box.width() : 800,
                                             box.height() > 40 ? box.height() : 800,
                                             Qt::KeepAspectRatio,
                                             Qt::SmoothTransformation));
        lightbox_->setWindowTitle(QFileInfo(selectedPath_).fileName());
    }
}

void InspirationPage::openSelectedLightbox()
{
    if (selectedPath_.isEmpty())
        return;
    if (!lightbox_)
    {
        lightbox_ = new QDialog(this);
        lightbox_->setObjectName(QStringLiteral("InspLightbox"));
        lightbox_->setWindowTitle(QStringLiteral("Selected still"));
        lightbox_->resize(900, 900);
        lightbox_->setMinimumSize(480, 480);
        auto *lay = new QVBoxLayout(lightbox_);
        lay->setContentsMargins(12, 12, 12, 12);
        lightboxImage_ = new QLabel(lightbox_);
        lightboxImage_->setAlignment(Qt::AlignCenter);
        lightboxImage_->setMinimumSize(420, 420);
        lay->addWidget(lightboxImage_, 1);
        lightbox_->installEventFilter(this);
    }
    refreshSelectedStill();
    lightbox_->show();
    lightbox_->raise();
    lightbox_->activateWindow();
}

bool InspirationPage::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == selectedStillLabel_ && event && event->type() == QEvent::MouseButtonRelease)
    {
        openSelectedLightbox();
        return true;
    }
    if (watched == lightbox_ && event && event->type() == QEvent::KeyPress)
    {
        auto *key = static_cast<QKeyEvent *>(event);
        if (!key->modifiers())
        {
            if (key->key() == Qt::Key_K)
            {
                applyPick(QStringLiteral("keep"));
                refreshSelectedStill();
                return true;
            }
            if (key->key() == Qt::Key_N)
            {
                applyPick(QStringLiteral("no"));
                refreshSelectedStill();
                return true;
            }
            if (key->key() == Qt::Key_Escape)
            {
                lightbox_->hide();
                return true;
            }
            if (key->key() == Qt::Key_Left || key->key() == Qt::Key_Right)
            {
                if (galleryView_ && galleryModel_)
                {
                    const int row = galleryView_->currentIndex().row();
                    const int next = key->key() == Qt::Key_Right
                                         ? qMin(row + 1, galleryModel_->rowCount() - 1)
                                         : qMax(row - 1, 0);
                    if (next >= 0)
                        galleryView_->setCurrentIndex(galleryModel_->index(next, 0));
                }
                refreshSelectedStill();
                return true;
            }
        }
    }
    return QWidget::eventFilter(watched, event);
}

void InspirationPage::keyPressEvent(QKeyEvent *event)
{
    if (event && !event->modifiers() && event->key() == Qt::Key_K)
    {
        applyPick(QStringLiteral("keep"));
        return;
    }
    if (event && !event->modifiers() && event->key() == Qt::Key_N)
    {
        applyPick(QStringLiteral("no"));
        return;
    }
    QWidget::keyPressEvent(event);
}
