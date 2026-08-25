#include "studios/ConceptReferencePage.h"
#include "DashboardGlassPanel.h"
#include "DurableJson.h"
#include "ThemeManager.h"
#include "assets/AssetCatalogScanner.h"
#include "assets/CatalogPickerDialog.h"
#include "generation/OutputPathHelpers.h"
#include <QAbstractButton>
#include <QButtonGroup>
#include <QJsonArray>
#include <QShowEvent>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QPixmap>
#include <QProgressBar>
#include <QPushButton>
#include <QResizeEvent>
#include <QScrollArea>
#include <QSettings>
#include <QSizePolicy>
#include <QSplitter>
#include <QTextEdit>
#include <QToolButton>
#include <QVBoxLayout>
namespace spellvision::studios
{
namespace
{
QLabel *makeEyebrow(const QString &text, QWidget *parent)
{
    auto *l = new QLabel(text, parent);
    l->setObjectName(QStringLiteral("ConceptRefEyebrow"));
    return l;
}
QLabel *makeFieldLabel(const QString &text, QWidget *parent)
{
    auto *l = new QLabel(text, parent);
    l->setObjectName(QStringLiteral("ConceptRefFieldLabel"));
    return l;
}
QToolButton *makeChip(const QString &text, QWidget *parent, bool checkable = true)
{
    auto *b = new QToolButton(parent);
    b->setObjectName(QStringLiteral("ConceptRefChip"));
    b->setText(text);
    b->setCheckable(checkable);
    b->setCursor(Qt::PointingHandCursor);
    b->setToolButtonStyle(Qt::ToolButtonTextOnly);
    b->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
    b->setMinimumHeight(30);
    return b;
}
} // namespace

ConceptReferencePage::ConceptReferencePage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("ConceptReferencePage"));
    buildUi();
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });
    QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString last = s.value(QStringLiteral("conceptReference/lastProject")).toString();
    if (!last.isEmpty()) {
        projectName_ = last;
        if (projectNameEdit_)
            projectNameEdit_->setText(projectName_);
    }
    loadProject();
    refreshPackUi();
    applyPackToEditors(true);
    reflowForWidth(width() > 0 ? width() : 1280);
}

void ConceptReferencePage::setProjectRoot(const QString &root)
{
    projectRoot_ = root;
    loadProject();
}

void ConceptReferencePage::updateDisclosure(bool advanced)
{
    advanced_ = advanced;
    if (advancedBlock_)
        advancedBlock_->setVisible(advanced_);
}

void ConceptReferencePage::setBusy(bool busy, const QString &message)
{
    busy_ = busy;
    if (progress_)
        progress_->setVisible(busy);
    if (generateBtn_)
        generateBtn_->setEnabled(!busy);
    if (turnaroundBtn_)
        turnaroundBtn_->setEnabled(!busy);
    if (actionHint_)
        actionHint_->setText(message.isEmpty() ? (busy ? QStringLiteral("Working…") : QStringLiteral("Ready"))
                                               : message);
    if (statusBanner_ && !message.isEmpty())
        statusBanner_->setText(message);
}

void ConceptReferencePage::setPreviewImage(const QString &path, const QString &caption)
{
    lastOutputPath_ = QDir::fromNativeSeparators(path.trimmed());
    if (!previewLabel_)
        return;
    QString resolved = lastOutputPath_;
    if (!resolved.isEmpty() && !QFileInfo::exists(resolved)) {
        // Worker may return relative / mixed separators.
        const QString alt = QDir::toNativeSeparators(resolved);
        if (QFileInfo::exists(alt))
            resolved = alt;
        else if (!projectRoot_.isEmpty()) {
            const QString joined = QDir(projectRoot_).filePath(resolved);
            if (QFileInfo::exists(joined))
                resolved = joined;
        }
    }
    lastOutputPath_ = resolved;
    if (lastOutputPath_.isEmpty() || !QFileInfo::exists(lastOutputPath_)) {
        previewLabel_->clear();
        previewLabel_->setText(QStringLiteral("No reference yet"));
        if (previewCaption_)
            previewCaption_->setText(caption.isEmpty() ? QStringLiteral("—") : caption);
        return;
    }
    QPixmap pm;
    if (!pm.load(lastOutputPath_)) {
        // Retry via native separators (Windows path edge cases).
        pm.load(QDir::toNativeSeparators(lastOutputPath_));
    }
    if (pm.isNull()) {
        previewLabel_->clear();
        previewLabel_->setText(QStringLiteral("Preview unavailable\n%1")
                                   .arg(QFileInfo(lastOutputPath_).fileName()));
        if (previewCaption_)
            previewCaption_->setText(lastOutputPath_);
        setBusy(false, QStringLiteral("Output saved but preview failed to decode."));
        return;
    }
    const int pw = qMax(280, previewLabel_->width());
    const int ph = qMax(320, previewLabel_->height());
    previewLabel_->setPixmap(pm.scaled(pw, ph, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    previewLabel_->setText(QString());
    if (previewCaption_)
        previewCaption_->setText(caption.isEmpty() ? QFileInfo(lastOutputPath_).fileName() : caption);
    setBusy(false, QStringLiteral("Reference ready — lock or send to Character Studio."));
}

void ConceptReferencePage::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    if (!catalogLoaded_)
        refreshModelCatalog();
}

void ConceptReferencePage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    reflowForWidth(event ? event->size().width() : width());
}

void ConceptReferencePage::reflowForWidth(int width)
{
    if (!mainSplit_ || !leftColumn_ || !rightColumn_)
        return;
    int leftBudget = 420;
    int rightBudget = 320;
    if (width < 1100) {
        leftBudget = 300;
        rightBudget = 240;
    } else if (width < 1400) {
        leftBudget = 360;
        rightBudget = 280;
    }
    leftColumn_->setMinimumWidth(qMax(260, leftBudget - 40));
    leftColumn_->setMaximumWidth(leftBudget + 60);
    rightColumn_->setMinimumWidth(qMax(220, rightBudget - 30));
    rightColumn_->setMaximumWidth(rightBudget + 80);
    if (width < 1280) {
        const int canvas = qMax(280, width - leftBudget - rightBudget - 80);
        mainSplit_->setSizes({leftBudget, canvas, rightBudget});
    }
}

void ConceptReferencePage::buildUi()
{
    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Card),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    root->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
    // --- Hero ---
    heroPanel_ = new DashboardGlassPanel(this);
    heroPanel_->setVariant(DashboardGlassPanel::Variant::Hero);
    heroPanel_->setCornerRadius(16);
    heroPanel_->setGlowStrength(1.05);
    auto *heroLay = new QVBoxLayout(heroPanel_);
    heroLay->setContentsMargins(18, 14, 18, 14);
    heroLay->setSpacing(6);
    auto *heroTop = new QHBoxLayout;
    auto *titles = new QVBoxLayout;
    titles->setSpacing(2);
    titles->addWidget(makeEyebrow(QStringLiteral("CONCEPT REFERENCE"), heroPanel_));
    heroTitle_ = new QLabel(QStringLiteral("Multi-view ready concept art"), heroPanel_);
    heroTitle_->setObjectName(QStringLiteral("ConceptRefHeroTitle"));
    heroSubtitle_ = new QLabel(
        QStringLiteral("Lighting, background, and angle packs for multi-view adherence — body, clothing, building, or prop."),
        heroPanel_);
    heroSubtitle_->setObjectName(QStringLiteral("ConceptRefHeroSubtitle"));
    heroSubtitle_->setWordWrap(true);
    titles->addWidget(heroTitle_);
    titles->addWidget(heroSubtitle_);
    heroTop->addLayout(titles, 1);
    progress_ = new QProgressBar(heroPanel_);
    progress_->setObjectName(QStringLiteral("ConceptRefProgress"));
    progress_->setFixedWidth(140);
    progress_->setFixedHeight(6);
    progress_->setTextVisible(false);
    progress_->setRange(0, 0);
    progress_->setVisible(false);
    heroTop->addWidget(progress_, 0, Qt::AlignTop);
    heroLay->addLayout(heroTop);
    statusBanner_ = new QLabel(
        QStringLiteral("Select a checkpoint, pick asset type + view, Apply pack, then Generate."),
        heroPanel_);
    statusBanner_->setObjectName(QStringLiteral("ConceptRefStatusBanner"));
    statusBanner_->setWordWrap(true);
    heroLay->addWidget(statusBanner_);
    root->addWidget(heroPanel_);
    // --- Split ---
    mainSplit_ = new QSplitter(Qt::Horizontal, this);
    mainSplit_->setChildrenCollapsible(false);
    // LEFT: controls
    leftColumn_ = new DashboardGlassPanel(this);
    static_cast<DashboardGlassPanel *>(leftColumn_)->setVariant(DashboardGlassPanel::Variant::Raised);
    static_cast<DashboardGlassPanel *>(leftColumn_)->setCornerRadius(14);
    auto *leftScroll = new QScrollArea(leftColumn_);
    leftScroll->setObjectName(QStringLiteral("ConceptRefSideScroll"));
    leftScroll->setWidgetResizable(true);
    leftScroll->setFrameShape(QFrame::NoFrame);
    leftScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    auto *leftBody = new QWidget(leftScroll);
    auto *leftLay = new QVBoxLayout(leftBody);
    leftLay->setContentsMargins(14, 14, 14, 14);
    leftLay->setSpacing(10);
    leftLay->addWidget(makeEyebrow(QStringLiteral("PROJECT"), leftBody));
    leftLay->addWidget(makeFieldLabel(QStringLiteral("Name"), leftBody));
    projectNameEdit_ = new QLineEdit(projectName_, leftBody);
    projectNameEdit_->setPlaceholderText(QStringLiteral("concept_ref_01"));
    connect(projectNameEdit_, &QLineEdit::editingFinished, this, [this]() {
        projectName_ = projectNameEdit_->text().trimmed().isEmpty()
                           ? QStringLiteral("concept_ref_01")
                           : projectNameEdit_->text().trimmed();
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        s.setValue(QStringLiteral("conceptReference/lastProject"), projectName_);
    });
    leftLay->addWidget(projectNameEdit_);
    leftLay->addWidget(makeEyebrow(QStringLiteral("MODEL STACK"), leftBody));
    leftLay->addWidget(makeFieldLabel(QStringLiteral("Checkpoint"), leftBody));
    modelValueLabel_ = new QLabel(QStringLiteral("No model selected"), leftBody);
    modelValueLabel_->setObjectName(QStringLiteral("ConceptRefModelValue"));
    modelValueLabel_->setWordWrap(true);
    leftLay->addWidget(modelValueLabel_);
    auto *modelRow = new QHBoxLayout;
    modelRow->setSpacing(6);
    pickModelBtn_ = new QPushButton(QStringLiteral("Choose model…"), leftBody);
    pickModelBtn_->setObjectName(QStringLiteral("ConceptRefSecondaryBtn"));
    refreshModelsBtn_ = new QPushButton(QStringLiteral("Refresh"), leftBody);
    refreshModelsBtn_->setObjectName(QStringLiteral("ConceptRefSecondaryBtn"));
    connect(pickModelBtn_, &QPushButton::clicked, this, &ConceptReferencePage::pickModel);
    connect(refreshModelsBtn_, &QPushButton::clicked, this, &ConceptReferencePage::refreshModelCatalog);
    modelRow->addWidget(pickModelBtn_, 1);
    modelRow->addWidget(refreshModelsBtn_, 0);
    leftLay->addLayout(modelRow);
    leftLay->addWidget(makeFieldLabel(QStringLiteral("LoRA (optional)"), leftBody));
    loraValueLabel_ = new QLabel(QStringLiteral("None"), leftBody);
    loraValueLabel_->setObjectName(QStringLiteral("ConceptRefModelValue"));
    loraValueLabel_->setWordWrap(true);
    leftLay->addWidget(loraValueLabel_);
    auto *loraRow = new QHBoxLayout;
    loraRow->setSpacing(6);
    pickLoraBtn_ = new QPushButton(QStringLiteral("Add LoRA…"), leftBody);
    pickLoraBtn_->setObjectName(QStringLiteral("ConceptRefSecondaryBtn"));
    clearLoraBtn_ = new QPushButton(QStringLiteral("Clear"), leftBody);
    clearLoraBtn_->setObjectName(QStringLiteral("ConceptRefSecondaryBtn"));
    connect(pickLoraBtn_, &QPushButton::clicked, this, &ConceptReferencePage::pickLora);
    connect(clearLoraBtn_, &QPushButton::clicked, this, &ConceptReferencePage::clearLora);
    loraRow->addWidget(pickLoraBtn_, 1);
    loraRow->addWidget(clearLoraBtn_, 0);
    leftLay->addLayout(loraRow);
    leftLay->addWidget(makeEyebrow(QStringLiteral("ASSET TYPE"), leftBody));
    auto *assetRow = new QHBoxLayout;
    assetRow->setSpacing(6);
    assetTypeGroup_ = new QButtonGroup(this);
    assetTypeGroup_->setExclusive(true);
    const struct {
        ConceptAssetType type;
        const char *label;
    } assets[] = {
        {ConceptAssetType::CharacterBody, "Character body"},
        {ConceptAssetType::Clothing, "Clothing"},
        {ConceptAssetType::Building, "Building"},
        {ConceptAssetType::Prop, "Prop"},
    };
    for (const auto &a : assets) {
        auto *chip = makeChip(QString::fromUtf8(a.label), leftBody);
        chip->setProperty("assetType", static_cast<int>(a.type));
        assetTypeGroup_->addButton(chip, static_cast<int>(a.type));
        assetRow->addWidget(chip);
        if (a.type == ConceptAssetType::CharacterBody)
            chip->setChecked(true);
    }
    assetRow->addStretch(1);
    leftLay->addLayout(assetRow);
    connect(assetTypeGroup_, &QButtonGroup::idClicked, this, [this](int id) {
        assetType_ = static_cast<ConceptAssetType>(id);
        refreshPackUi();
        applyPackToEditors(false);
    });
    leftLay->addWidget(makeEyebrow(QStringLiteral("CONTENT MODE"), leftBody));
    auto *contentRow = new QHBoxLayout;
    contentRow->setSpacing(6);
    contentModeGroup_ = new QButtonGroup(this);
    contentModeGroup_->setExclusive(true);
    auto *sfwChip = makeChip(QStringLiteral("SFW body"), leftBody);
    sfwChip->setToolTip(QStringLiteral(
        "Anatomically correct proportions and massing, smooth genital region without genitals — "
        "best for game characters that will wear clothing."));
    auto *nsfwChip = makeChip(QStringLiteral("NSFW anatomy"), leftBody);
    nsfwChip->setToolTip(QStringLiteral(
        "Allow full anatomical detail when you need unclothed body fidelity."));
    contentModeGroup_->addButton(sfwChip, static_cast<int>(ConceptContentMode::Sfw));
    contentModeGroup_->addButton(nsfwChip, static_cast<int>(ConceptContentMode::Nsfw));
    sfwChip->setChecked(true);
    contentRow->addWidget(sfwChip);
    contentRow->addWidget(nsfwChip);
    contentRow->addStretch(1);
    leftLay->addLayout(contentRow);
    connect(contentModeGroup_, &QButtonGroup::idClicked, this, [this](int id) {
        contentMode_ = static_cast<ConceptContentMode>(id);
        refreshPackUi();
        applyPackToEditors(false);
    });
    leftLay->addWidget(makeEyebrow(QStringLiteral("VIEW / ANGLE"), leftBody));
    auto *viewGrid = new QGridLayout;
    viewGrid->setHorizontalSpacing(6);
    viewGrid->setVerticalSpacing(6);
    viewModeGroup_ = new QButtonGroup(this);
    viewModeGroup_->setExclusive(true);
    const ConceptViewMode views[] = {
        ConceptViewMode::HeroFront,
        ConceptViewMode::TurnaroundSheet,
        ConceptViewMode::AngleFront,
        ConceptViewMode::AngleBack,
        ConceptViewMode::AngleLeft,
        ConceptViewMode::AngleRight,
        ConceptViewMode::AngleThreeQuarter,
    };
    int vi = 0;
    for (ConceptViewMode v : views) {
        auto *chip = makeChip(conceptViewModeLabel(v), leftBody);
        viewModeGroup_->addButton(chip, static_cast<int>(v));
        viewGrid->addWidget(chip, vi / 2, vi % 2);
        if (v == ConceptViewMode::HeroFront)
            chip->setChecked(true);
        ++vi;
    }
    leftLay->addLayout(viewGrid);
    connect(viewModeGroup_, &QButtonGroup::idClicked, this, [this](int id) {
        viewMode_ = static_cast<ConceptViewMode>(id);
        refreshPackUi();
        applyPackToEditors(false);
    });
    applyPackBtn_ = new QPushButton(QStringLiteral("Apply pack → prompts"), leftBody);
    applyPackBtn_->setObjectName(QStringLiteral("ConceptRefSecondaryBtn"));
    applyPackBtn_->setToolTip(QStringLiteral("Overwrite positive/negative editors with the current pack scaffolds."));
    connect(applyPackBtn_, &QPushButton::clicked, this, [this]() { applyPackToEditors(true); });
    leftLay->addWidget(applyPackBtn_);
    packSummaryLabel_ = new QLabel(leftBody);
    packSummaryLabel_->setObjectName(QStringLiteral("ConceptRefMuted"));
    packSummaryLabel_->setWordWrap(true);
    leftLay->addWidget(packSummaryLabel_);
    leftLay->addWidget(makeFieldLabel(QStringLiteral("Subject (your idea)"), leftBody));
    subjectEdit_ = new QTextEdit(leftBody);
    subjectEdit_->setObjectName(QStringLiteral("ConceptRefSubject"));
    subjectEdit_->setFixedHeight(72);
    subjectEdit_->setPlaceholderText(QStringLiteral("Describe the subject only — packs add lighting/bg/angle…"));
    leftLay->addWidget(subjectEdit_);
    leftLay->addWidget(makeFieldLabel(QStringLiteral("Positive prompt (pack + subject)"), leftBody));
    positiveEdit_ = new QTextEdit(leftBody);
    positiveEdit_->setObjectName(QStringLiteral("ConceptRefPositive"));
    positiveEdit_->setMinimumHeight(110);
    leftLay->addWidget(positiveEdit_);
    leftLay->addWidget(makeFieldLabel(QStringLiteral("Negative prompt (always-on adherence)"), leftBody));
    negativeEdit_ = new QTextEdit(leftBody);
    negativeEdit_->setObjectName(QStringLiteral("ConceptRefNegative"));
    negativeEdit_->setMinimumHeight(90);
    leftLay->addWidget(negativeEdit_);
    advancedBlock_ = new QWidget(leftBody);
    auto *advLay = new QVBoxLayout(advancedBlock_);
    advLay->setContentsMargins(0, 4, 0, 0);
    advLay->setSpacing(6);
    advLay->addWidget(makeEyebrow(QStringLiteral("ADVANCED SAMPLING"), advancedBlock_));
    auto *seedRow = new QHBoxLayout;
    seedEdit_ = new QLineEdit(QStringLiteral("42"), advancedBlock_);
    stepsEdit_ = new QLineEdit(QStringLiteral("30"), advancedBlock_);
    cfgEdit_ = new QLineEdit(QStringLiteral("4.5"), advancedBlock_);
    seedEdit_->setPlaceholderText(QStringLiteral("seed"));
    stepsEdit_->setPlaceholderText(QStringLiteral("steps"));
    cfgEdit_->setPlaceholderText(QStringLiteral("cfg"));
    seedRow->addWidget(seedEdit_, 1);
    seedRow->addWidget(stepsEdit_, 1);
    seedRow->addWidget(cfgEdit_, 1);
    advLay->addLayout(seedRow);
    advancedBlock_->setVisible(false);
    leftLay->addWidget(advancedBlock_);
    checklistLabel_ = new QLabel(leftBody);
    checklistLabel_->setObjectName(QStringLiteral("ConceptRefChecklist"));
    checklistLabel_->setWordWrap(true);
    checklistLabel_->setTextFormat(Qt::RichText);
    leftLay->addWidget(checklistLabel_);
    leftLay->addStretch(1);
    leftScroll->setWidget(leftBody);
    auto *leftShell = new QVBoxLayout(leftColumn_);
    leftShell->setContentsMargins(0, 0, 0, 0);
    leftShell->addWidget(leftScroll);
    // CENTER: preview
    auto *center = new DashboardGlassPanel(this);
    center->setVariant(DashboardGlassPanel::Variant::Standard);
    center->setCornerRadius(14);
    auto *centerLay = new QVBoxLayout(center);
    centerLay->setContentsMargins(16, 16, 16, 16);
    centerLay->setSpacing(8);
    centerLay->addWidget(makeEyebrow(QStringLiteral("PREVIEW"), center));
    previewLabel_ = new QLabel(QStringLiteral("Ready when you are.\nApply a pack, then Generate."), center);
    previewLabel_->setObjectName(QStringLiteral("ConceptRefPreview"));
    previewLabel_->setAlignment(Qt::AlignCenter);
    previewLabel_->setMinimumSize(280, 360);
    previewLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    centerLay->addWidget(previewLabel_, 1);
    previewCaption_ = new QLabel(QStringLiteral("—"), center);
    previewCaption_->setObjectName(QStringLiteral("ConceptRefMuted"));
    previewCaption_->setAlignment(Qt::AlignCenter);
    centerLay->addWidget(previewCaption_);
    // RIGHT: actions + tips
    rightColumn_ = new DashboardGlassPanel(this);
    static_cast<DashboardGlassPanel *>(rightColumn_)->setVariant(DashboardGlassPanel::Variant::Inset);
    static_cast<DashboardGlassPanel *>(rightColumn_)->setCornerRadius(14);
    auto *rightScroll = new QScrollArea(rightColumn_);
    rightScroll->setObjectName(QStringLiteral("ConceptRefSideScroll"));
    rightScroll->setWidgetResizable(true);
    rightScroll->setFrameShape(QFrame::NoFrame);
    rightScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    auto *rightBody = new QWidget(rightScroll);
    auto *rightLay = new QVBoxLayout(rightBody);
    rightLay->setContentsMargins(14, 14, 14, 14);
    rightLay->setSpacing(10);
    rightLay->addWidget(makeEyebrow(QStringLiteral("ACTIONS"), rightBody));
    generateBtn_ = new QPushButton(QStringLiteral("Generate reference"), rightBody);
    generateBtn_->setObjectName(QStringLiteral("ConceptRefPrimaryBtn"));
    connect(generateBtn_, &QPushButton::clicked, this, &ConceptReferencePage::generateReference);
    rightLay->addWidget(generateBtn_);
    turnaroundBtn_ = new QPushButton(QStringLiteral("Generate turnaround sheet"), rightBody);
    turnaroundBtn_->setObjectName(QStringLiteral("ConceptRefSecondaryBtn"));
    turnaroundBtn_->setToolTip(QStringLiteral("Force turnaround multi-view sheet scaffold regardless of angle chip."));
    connect(turnaroundBtn_, &QPushButton::clicked, this, &ConceptReferencePage::generateTurnaround);
    rightLay->addWidget(turnaroundBtn_);
    lockBtn_ = new QPushButton(QStringLiteral("Lock as hero reference"), rightBody);
    lockBtn_->setObjectName(QStringLiteral("ConceptRefSecondaryBtn"));
    connect(lockBtn_, &QPushButton::clicked, this, &ConceptReferencePage::lockReference);
    rightLay->addWidget(lockBtn_);
    toCharacterBtn_ = new QPushButton(QStringLiteral("Send to Character Studio"), rightBody);
    toCharacterBtn_->setObjectName(QStringLiteral("ConceptRefSecondaryBtn"));
    connect(toCharacterBtn_, &QPushButton::clicked, this, &ConceptReferencePage::sendToCharacter);
    rightLay->addWidget(toCharacterBtn_);
    openT2IBtn_ = new QPushButton(QStringLiteral("Open T2I cockpit"), rightBody);
    openT2IBtn_->setObjectName(QStringLiteral("ConceptRefSecondaryBtn"));
    connect(openT2IBtn_, &QPushButton::clicked, this, &ConceptReferencePage::openInT2I);
    rightLay->addWidget(openT2IBtn_);
    saveBtn_ = new QPushButton(QStringLiteral("Save project"), rightBody);
    saveBtn_->setObjectName(QStringLiteral("ConceptRefSecondaryBtn"));
    connect(saveBtn_, &QPushButton::clicked, this, &ConceptReferencePage::saveProject);
    rightLay->addWidget(saveBtn_);
    actionHint_ = new QLabel(QStringLiteral("Ready"), rightBody);
    actionHint_->setObjectName(QStringLiteral("ConceptRefMuted"));
    actionHint_->setWordWrap(true);
    rightLay->addWidget(actionHint_);
    auto *why = new QLabel(
        QStringLiteral(
            "<b>SFW body</b> — anatomical massing, no genitals (game-safe under clothing).<br/>"
            "<b>NSFW</b> — full anatomical detail when needed.<br/>"
            "Packs enforce even light + empty plates for multi-view lock."),
        rightBody);
    why->setObjectName(QStringLiteral("ConceptRefMuted"));
    why->setWordWrap(true);
    why->setTextFormat(Qt::RichText);
    rightLay->addWidget(why);
    rightLay->addStretch(1);
    rightScroll->setWidget(rightBody);
    auto *rightShell = new QVBoxLayout(rightColumn_);
    rightShell->setContentsMargins(0, 0, 0, 0);
    rightShell->addWidget(rightScroll);
    mainSplit_->addWidget(leftColumn_);
    mainSplit_->addWidget(center);
    mainSplit_->addWidget(rightColumn_);
    mainSplit_->setStretchFactor(0, 0);
    mainSplit_->setStretchFactor(1, 1);
    mainSplit_->setStretchFactor(2, 0);
    mainSplit_->setSizes({400, 520, 300});
    root->addWidget(mainSplit_, 1);
}

void ConceptReferencePage::refreshPackUi()
{
    // SFW/NSFW only meaningful for character body — still allowed elsewhere (no-op content strings).
    const bool body = currentAssetType() == ConceptAssetType::CharacterBody;
    if (contentModeGroup_) {
        for (QAbstractButton *b : contentModeGroup_->buttons())
            b->setEnabled(body);
    }
    const auto pack = buildConceptPromptPack(currentAssetType(), currentContentMode(), currentViewMode());
    if (subjectEdit_)
        subjectEdit_->setPlaceholderText(pack.subjectHint);
    if (checklistLabel_)
        checklistLabel_->setText(pack.checklistHtml);
    if (packSummaryLabel_) {
        packSummaryLabel_->setText(
            QStringLiteral("%1 · %2 · %3")
                .arg(conceptAssetTypeLabel(currentAssetType()),
                     currentContentMode() == ConceptContentMode::Sfw ? QStringLiteral("SFW")
                                                                     : QStringLiteral("NSFW"),
                     conceptViewModeLabel(currentViewMode())));
    }
}

void ConceptReferencePage::applyPackToEditors(bool overwriteUser)
{
    const auto pack = buildConceptPromptPack(currentAssetType(), currentContentMode(), currentViewMode());
    const QString subject = subjectEdit_ ? subjectEdit_->toPlainText().trimmed() : QString();
    if (positiveEdit_) {
        if (overwriteUser || positiveEdit_->toPlainText().trimmed().isEmpty())
            positiveEdit_->setPlainText(composeConceptPositivePrompt(subject, pack));
        else if (!subject.isEmpty()) {
            // Refresh scaffold while keeping subject prefix if user already edited.
            positiveEdit_->setPlainText(composeConceptPositivePrompt(subject, pack));
        }
    }
    if (negativeEdit_ && (overwriteUser || negativeEdit_->toPlainText().trimmed().isEmpty()))
        negativeEdit_->setPlainText(pack.negativeScaffold);
    if (statusBanner_) {
        statusBanner_->setText(
            QStringLiteral("Pack applied: %1 / %2 / %3 — generate when ready.")
                .arg(conceptAssetTypeLabel(currentAssetType()),
                     currentContentMode() == ConceptContentMode::Sfw ? QStringLiteral("SFW")
                                                                     : QStringLiteral("NSFW"),
                     conceptViewModeLabel(currentViewMode())));
    }
}

ConceptAssetType ConceptReferencePage::currentAssetType() const
{
    if (assetTypeGroup_ && assetTypeGroup_->checkedId() >= 0)
        return static_cast<ConceptAssetType>(assetTypeGroup_->checkedId());
    return assetType_;
}

ConceptContentMode ConceptReferencePage::currentContentMode() const
{
    if (contentModeGroup_ && contentModeGroup_->checkedId() >= 0)
        return static_cast<ConceptContentMode>(contentModeGroup_->checkedId());
    return contentMode_;
}

ConceptViewMode ConceptReferencePage::currentViewMode() const
{
    if (viewModeGroup_ && viewModeGroup_->checkedId() >= 0)
        return static_cast<ConceptViewMode>(viewModeGroup_->checkedId());
    return viewMode_;
}

QJsonObject ConceptReferencePage::buildPayload(ConceptViewMode view) const
{
    const auto pack = buildConceptPromptPack(currentAssetType(), currentContentMode(), view);
    QString positive = positiveEdit_ ? positiveEdit_->toPlainText().trimmed() : QString();
    QString negative = negativeEdit_ ? negativeEdit_->toPlainText().trimmed() : QString();
    const QString subject = subjectEdit_ ? subjectEdit_->toPlainText().trimmed() : QString();
    // If user is on a different view chip but we forced turnaround, rebuild positives.
    if (view != currentViewMode() || positive.isEmpty())
        positive = composeConceptPositivePrompt(subject, pack);
    if (negative.isEmpty())
        negative = pack.negativeScaffold;
    int steps = 30;
    double cfg = 4.5;
    int seed = 42;
    if (stepsEdit_)
        steps = qBound(8, stepsEdit_->text().toInt(), 60);
    if (cfgEdit_)
        cfg = qBound(1.0, cfgEdit_->text().toDouble(), 12.0);
    if (seedEdit_)
        seed = seedEdit_->text().toInt();
    QJsonObject payload;
    payload.insert(QStringLiteral("prompt"), positive);
    payload.insert(QStringLiteral("negative_prompt"), negative);
    payload.insert(QStringLiteral("width"), conceptDefaultWidth(view));
    payload.insert(QStringLiteral("height"), conceptDefaultHeight(view));
    payload.insert(QStringLiteral("steps"), steps);
    payload.insert(QStringLiteral("cfg"), cfg);
    payload.insert(QStringLiteral("seed"), seed);
    payload.insert(QStringLiteral("output_prefix"),
                   QStringLiteral("concept_ref_%1_%2")
                       .arg(conceptAssetTypeId(currentAssetType()), projectName_));
    const QString model = selectedModelValue();
    if (!model.isEmpty()) {
        payload.insert(QStringLiteral("model"), model);
        payload.insert(QStringLiteral("model_display"), selectedModelDisplay());
    }
    const QString lora = selectedLoraValue();
    if (!lora.isEmpty()) {
        QJsonArray loras;
        QJsonObject l;
        l.insert(QStringLiteral("path"), lora);
        l.insert(QStringLiteral("name"), selectedLoraDisplay_.isEmpty()
                                             ? QFileInfo(lora).fileName()
                                             : selectedLoraDisplay_);
        l.insert(QStringLiteral("strength"), 0.85);
        loras.append(l);
        payload.insert(QStringLiteral("loras"), loras);
    }
    // Prefer I2I when locking further angles from a locked hero.
    if (!lockedImagePath_.isEmpty() && QFileInfo::exists(lockedImagePath_)
        && view != ConceptViewMode::HeroFront) {
        payload.insert(QStringLiteral("input_image"), lockedImagePath_);
    }
    return payload;
}

QString ConceptReferencePage::selectedModelValue() const
{
    return selectedModelPath_.trimmed();
}

QString ConceptReferencePage::selectedModelDisplay() const
{
    if (!selectedModelDisplay_.trimmed().isEmpty())
        return selectedModelDisplay_.trimmed();
    if (!selectedModelPath_.isEmpty())
        return QFileInfo(selectedModelPath_).fileName();
    return {};
}

QString ConceptReferencePage::selectedLoraValue() const
{
    return selectedLoraPath_.trimmed();
}

void ConceptReferencePage::refreshModelCatalog()
{
    catalogLoaded_ = true;
    // Labels only — pickers scan live on open so the list stays fresh.
    if (modelValueLabel_) {
        modelValueLabel_->setText(selectedModelPath_.isEmpty()
                                      ? QStringLiteral("No model selected — required to generate")
                                      : selectedModelDisplay());
    }
    if (loraValueLabel_) {
        loraValueLabel_->setText(selectedLoraPath_.isEmpty()
                                     ? QStringLiteral("None")
                                     : selectedLoraDisplay_);
    }
}

void ConceptReferencePage::pickModel()
{
    using namespace spellvision::assets;
    using spellvision::generation::chooseModelsRootPath;
    const QString root = chooseModelsRootPath();
    const QVector<CatalogEntry> entries = scanImageModelCatalog(root);
    if (entries.isEmpty()) {
        setBusy(false, QStringLiteral("No checkpoints found under models root."));
        return;
    }
    CatalogPickerDialog dlg(QStringLiteral("Choose checkpoint"), entries, selectedModelPath_,
                            QStringLiteral("conceptReference/recentModels"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    selectedModelPath_ = dlg.selectedValue();
    selectedModelDisplay_ = dlg.selectedDisplay();
    persistRecentSelection(QStringLiteral("conceptReference/recentModels"), selectedModelPath_);
    refreshModelCatalog();
    saveProject();
}

void ConceptReferencePage::pickLora()
{
    using namespace spellvision::assets;
    using spellvision::generation::chooseModelsRootPath;
    const QString root = chooseModelsRootPath();
    const QVector<CatalogEntry> entries = scanCatalog(root, QStringLiteral("loras"));
    if (entries.isEmpty()) {
        setBusy(false, QStringLiteral("No LoRAs found under models/loras."));
        return;
    }
    CatalogPickerDialog dlg(QStringLiteral("Choose LoRA"), entries, selectedLoraPath_,
                            QStringLiteral("conceptReference/recentLoras"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    selectedLoraPath_ = dlg.selectedValue();
    selectedLoraDisplay_ = dlg.selectedDisplay();
    persistRecentSelection(QStringLiteral("conceptReference/recentLoras"), selectedLoraPath_);
    refreshModelCatalog();
    saveProject();
}

void ConceptReferencePage::clearLora()
{
    selectedLoraPath_.clear();
    selectedLoraDisplay_.clear();
    refreshModelCatalog();
    saveProject();
}

void ConceptReferencePage::generateReference()
{
    // Ensure pack is present
    if (positiveEdit_ && positiveEdit_->toPlainText().trimmed().isEmpty())
        applyPackToEditors(true);
    if (selectedModelValue().isEmpty()) {
        setBusy(false, QStringLiteral("Choose a checkpoint first (Model stack)."));
        return;
    }
    const ConceptViewMode view = currentViewMode();
    QJsonObject payload = buildPayload(view);
    if (payload.value(QStringLiteral("prompt")).toString().trimmed().isEmpty()) {
        setBusy(false, QStringLiteral("Add a subject or apply a pack first."));
        return;
    }
    const bool hasInput = payload.contains(QStringLiteral("input_image"));
    setBusy(true, hasInput ? QStringLiteral("Generating angle via I2I from locked hero…")
                           : QStringLiteral("Generating multi-view-ready reference…"));
    emit generateRequested(hasInput ? QStringLiteral("i2i") : QStringLiteral("t2i"), payload, false);
    saveProject();
}

void ConceptReferencePage::generateTurnaround()
{
    if (selectedModelValue().isEmpty()) {
        setBusy(false, QStringLiteral("Choose a checkpoint first (Model stack)."));
        return;
    }
    if (subjectEdit_ && subjectEdit_->toPlainText().trimmed().isEmpty()
        && positiveEdit_ && positiveEdit_->toPlainText().trimmed().isEmpty()) {
        setBusy(false, QStringLiteral("Describe the subject first."));
        return;
    }
    // Select turnaround chip visually
    if (viewModeGroup_) {
        if (QAbstractButton *b = viewModeGroup_->button(static_cast<int>(ConceptViewMode::TurnaroundSheet)))
            b->setChecked(true);
        viewMode_ = ConceptViewMode::TurnaroundSheet;
        refreshPackUi();
        applyPackToEditors(true);
    }
    QJsonObject payload = buildPayload(ConceptViewMode::TurnaroundSheet);
    const bool hasInput = payload.contains(QStringLiteral("input_image"));
    setBusy(true, QStringLiteral("Generating turnaround sheet…"));
    emit generateRequested(hasInput ? QStringLiteral("i2i") : QStringLiteral("t2i"), payload, false);
    saveProject();
}

void ConceptReferencePage::lockReference()
{
    if (lastOutputPath_.isEmpty() || !QFileInfo::exists(lastOutputPath_)) {
        setBusy(false, QStringLiteral("Generate a reference first, then lock."));
        return;
    }
    lockedImagePath_ = lastOutputPath_;
    if (statusBanner_)
        statusBanner_->setText(
            QStringLiteral("Hero locked: %1 — further angles will I2I from this identity.")
                .arg(QFileInfo(lockedImagePath_).fileName()));
    if (actionHint_)
        actionHint_->setText(QStringLiteral("Locked. Pick angle chips to stay on-identity."));
    saveProject();
}

void ConceptReferencePage::openInT2I()
{
    emit navigateRequested(QStringLiteral("t2i"));
}

void ConceptReferencePage::sendToCharacter()
{
    const QString path = !lockedImagePath_.isEmpty() ? lockedImagePath_ : lastOutputPath_;
    const QString prompt = subjectEdit_ ? subjectEdit_->toPlainText().trimmed()
                                        : (positiveEdit_ ? positiveEdit_->toPlainText().trimmed() : QString());
    if (path.isEmpty() || !QFileInfo::exists(path)) {
        setBusy(false, QStringLiteral("Lock or generate a reference before sending."));
        return;
    }
    emit sendToCharacterStudioRequested(path, prompt);
    emit navigateRequested(QStringLiteral("character"));
}

QString ConceptReferencePage::projectsDir() const
{
    const QString root = projectRoot_.isEmpty() ? QDir::currentPath() : projectRoot_;
    return QDir(root).filePath(QStringLiteral("runtime/concept_references"));
}

void ConceptReferencePage::saveProject()
{
    QDir().mkpath(projectsDir());
    QJsonObject o;
    o.insert(QStringLiteral("name"), projectName_);
    o.insert(QStringLiteral("asset_type"), conceptAssetTypeId(currentAssetType()));
    o.insert(QStringLiteral("content_mode"),
             currentContentMode() == ConceptContentMode::Sfw ? QStringLiteral("sfw")
                                                             : QStringLiteral("nsfw"));
    o.insert(QStringLiteral("view_mode"), static_cast<int>(currentViewMode()));
    o.insert(QStringLiteral("subject"), subjectEdit_ ? subjectEdit_->toPlainText() : QString());
    o.insert(QStringLiteral("positive"), positiveEdit_ ? positiveEdit_->toPlainText() : QString());
    o.insert(QStringLiteral("negative"), negativeEdit_ ? negativeEdit_->toPlainText() : QString());
    o.insert(QStringLiteral("locked_image"), lockedImagePath_);
    o.insert(QStringLiteral("last_output"), lastOutputPath_);
    o.insert(QStringLiteral("model"), selectedModelPath_);
    o.insert(QStringLiteral("model_display"), selectedModelDisplay_);
    o.insert(QStringLiteral("lora"), selectedLoraPath_);
    o.insert(QStringLiteral("lora_display"), selectedLoraDisplay_);
    o.insert(QStringLiteral("updated_at"), QDateTime::currentDateTimeUtc().toString(Qt::ISODate));
    const QString path = QDir(projectsDir()).filePath(projectName_ + QStringLiteral(".json"));
    const bool saved = writeJsonAtomically(path, QJsonDocument(o));
    if (actionHint_)
        actionHint_->setText(saved
                                 ? QStringLiteral("Saved %1").arg(QFileInfo(path).fileName())
                                 : QStringLiteral("Save failed: project file was not replaced"));
}

void ConceptReferencePage::loadProject()
{
    const QString path = QDir(projectsDir()).filePath(projectName_ + QStringLiteral(".json"));
    QFile f(path);
    if (!f.exists() || !f.open(QIODevice::ReadOnly))
        return;
    const QJsonObject o = QJsonDocument::fromJson(f.readAll()).object();
    f.close();
    if (subjectEdit_)
        subjectEdit_->setPlainText(o.value(QStringLiteral("subject")).toString());
    if (positiveEdit_)
        positiveEdit_->setPlainText(o.value(QStringLiteral("positive")).toString());
    if (negativeEdit_)
        negativeEdit_->setPlainText(o.value(QStringLiteral("negative")).toString());
    lockedImagePath_ = o.value(QStringLiteral("locked_image")).toString();
    lastOutputPath_ = o.value(QStringLiteral("last_output")).toString();
    selectedModelPath_ = o.value(QStringLiteral("model")).toString();
    selectedModelDisplay_ = o.value(QStringLiteral("model_display")).toString();
    selectedLoraPath_ = o.value(QStringLiteral("lora")).toString();
    selectedLoraDisplay_ = o.value(QStringLiteral("lora_display")).toString();
    refreshModelCatalog();
    if (!lastOutputPath_.isEmpty())
        setPreviewImage(lastOutputPath_, QStringLiteral("Restored"));
    const QString asset = o.value(QStringLiteral("asset_type")).toString();
    ConceptAssetType at = ConceptAssetType::CharacterBody;
    if (asset == QStringLiteral("clothing"))
        at = ConceptAssetType::Clothing;
    else if (asset == QStringLiteral("building"))
        at = ConceptAssetType::Building;
    else if (asset == QStringLiteral("prop"))
        at = ConceptAssetType::Prop;
    if (assetTypeGroup_) {
        if (QAbstractButton *b = assetTypeGroup_->button(static_cast<int>(at)))
            b->setChecked(true);
    }
    assetType_ = at;
    const bool nsfw = o.value(QStringLiteral("content_mode")).toString() == QStringLiteral("nsfw");
    contentMode_ = nsfw ? ConceptContentMode::Nsfw : ConceptContentMode::Sfw;
    if (contentModeGroup_) {
        if (QAbstractButton *b = contentModeGroup_->button(static_cast<int>(contentMode_)))
            b->setChecked(true);
    }
    refreshPackUi();
}

void ConceptReferencePage::applyTheme()
{
    const auto &theme = ThemeManager::instance();
    using C = ThemeManager::Color;
    QString css = QStringLiteral(
        "#ConceptReferencePage { background: transparent; }"
        "QLabel#ConceptRefEyebrow { color: @acc@; @caption@ letter-spacing: 0.12em; text-transform: uppercase; }"
        "QLabel#ConceptRefHeroTitle { color: @hi@; @heading@ }"
        "QLabel#ConceptRefHeroSubtitle, QLabel#ConceptRefMuted, QLabel#ConceptRefStatusBanner,"
        "QLabel#ConceptRefChecklist, QLabel#ConceptRefFieldLabel { color: @mid@; @body@ background: transparent; }"
        "QLabel#ConceptRefFieldLabel { @label@ color: @hi@; }"
                "QLabel#ConceptRefModelValue { color: @mid@; @detail@ background: @s0@; border: 1px solid @bd@; border-radius: 8px; padding: 6px 8px; }"
                "QLabel#ConceptRefPreview {"
                " background: @s0@; color: @mid@; border: 1px dashed @bd@; border-radius: 12px; @body@ }"
        "QTextEdit, QLineEdit {"
        " background: @s0@; color: @hi@; border: 1px solid @bd@; border-radius: 10px; padding: 8px; @body@ }"
        "QTextEdit:focus, QLineEdit:focus { border-color: @acc@; }"
        "QToolButton#ConceptRefChip {"
        " background: @sub@; color: @mid@; border: 1px solid @bd@; border-radius: 9px;"
        " padding: 6px 10px; @label@ }"
        "QToolButton#ConceptRefChip:hover { border-color: @acc@; color: @hi@; }"
        "QToolButton#ConceptRefChip:checked {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 @acc@, stop:1 @acc2@);"
        " color: white; border: 1px solid @accH@; font-weight: 700; }"
        "QPushButton#ConceptRefPrimaryBtn {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 @acc@, stop:1 @acc2@);"
        " color: white; border: 1px solid @accH@; border-radius: 10px;"
        " min-height: 38px; padding: 8px 14px; font-weight: 800; @label@ }"
        "QPushButton#ConceptRefPrimaryBtn:hover { border-color: @hi@; }"
        "QPushButton#ConceptRefPrimaryBtn:disabled { color: @dis@; background: @s0@; border-color: @bds@; }"
        "QPushButton#ConceptRefSecondaryBtn {"
        " background: @sub@; color: @hi@; border: 1px solid @bd@; border-radius: 10px;"
        " min-height: 34px; padding: 7px 12px; @label@ }"
        "QPushButton#ConceptRefSecondaryBtn:hover { border-color: @acc@; background: @glow@; }"
        "QScrollArea#ConceptRefSideScroll { background: transparent; border: none; }"
        "QProgressBar#ConceptRefProgress { border: none; background: @bds@; border-radius: 3px; }"
        "QProgressBar#ConceptRefProgress::chunk { background: @acc@; border-radius: 3px; }");
    const auto put = [&](const char *tok, const QString &val) {
        css.replace(QLatin1String(tok), val);
    };
    put("@s0@", theme.css(C::Surface0));
    put("@hi@", theme.css(C::TextHi));
    put("@mid@", theme.css(C::TextMid));
    put("@dis@", theme.css(C::TextDisabled));
    put("@acc@", theme.css(C::Accent));
    put("@acc2@", theme.css(C::AccentSecondary));
    put("@accH@", theme.css(C::AccentHover));
    put("@bd@", theme.css(C::BorderStrong));
    put("@bds@", theme.css(C::BorderSubtle));
    put("@sub@", theme.css(C::AccentSubtle));
    put("@glow@", theme.css(C::AccentGlow));
    put("@heading@", theme.fontCss(ThemeManager::Type::Heading));
    put("@body@", theme.fontCss(ThemeManager::Type::Body));
    put("@label@", theme.fontCss(ThemeManager::Type::Label));
    put("@caption@", theme.fontCss(ThemeManager::Type::Caption));
    put("@detail@", theme.fontCss(ThemeManager::Type::Detail));
    setStyleSheet(css);
}
} // namespace spellvision::studios
