#include "studios/CharacterStudioPage.h"
#include "studios/ConceptReferencePacks.h"

#include "DashboardGlassPanel.h"
#include "DurableJson.h"
#include "ThemeManager.h"
#include "assets/AssetCatalogScanner.h"
#include "assets/CatalogPickerDialog.h"
#include "assets/FamilyLicense.h"
#include "generation/OutputPathHelpers.h"

#include <QCheckBox>
#include <QComboBox>
#include <QDateTime>
#include <QDoubleSpinBox>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QPixmap>
#include <QPlainTextEdit>
#include <QProcess>
#include <QtGlobal>
#include <QProcessEnvironment>
#include <QProgressBar>
#include <QPushButton>
#include <QResizeEvent>
#include <QScrollArea>
#include <QSettings>
#include <QSizePolicy>
#include <QSplitter>
#include <QStackedWidget>
#include <QAbstractItemView>
#include <QTextEdit>
#include <QTimer>
#include <QVariant>
#include <QVBoxLayout>

namespace spellvision::studios
{
namespace
{

QLabel *makeEyebrow(const QString &text, QWidget *parent)
{
    auto *l = new QLabel(text, parent);
    l->setObjectName(QStringLiteral("CharStudioEyebrow"));
    return l;
}

QLabel *makeFieldLabel(const QString &text, QWidget *parent)
{
    auto *l = new QLabel(text, parent);
    l->setObjectName(QStringLiteral("CharStudioFieldLabel"));
    return l;
}

QString garmentSlug(QString value)
{
    value = value.trimmed().toLower();
    QString out;
    bool dashPending = false;
    for (const QChar ch : value) {
        if (ch.isLetterOrNumber()) {
            out.append(ch);
            dashPending = false;
        } else if (!out.isEmpty() && !dashPending) {
            out.append(QLatin1Char('-'));
            dashPending = true;
        }
    }
    while (out.endsWith(QLatin1Char('-')))
        out.chop(1);
    return out.isEmpty() ? QStringLiteral("garment") : out;
}

void configureStudioCombo(QComboBox *combo)
{
    if (!combo)
        return;
    combo->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    combo->setMinimumContentsLength(10);
    combo->setMinimumWidth(0);
    combo->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    if (combo->view())
        combo->view()->setTextElideMode(Qt::ElideMiddle);
}

} // namespace

CharacterStudioPage::CharacterStudioPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("CharacterStudioPage"));

    stages_ = {
        {StageId::Concept, QStringLiteral("concept"), QStringLiteral("0 · Concept lock"),
         QStringLiteral("Hero plate"), QStringLiteral("Lock a clean front before the pack. Style lives here."), StageStatus::Ready},
        {StageId::MultiView, QStringLiteral("multiview"), QStringLiteral("1 · Plates + pack"),
         QStringLiteral("Face + clothes turnaround"), QStringLiteral("Author the character pack. Body is the mesh you choose."), StageStatus::Locked},
        {StageId::BaseMesh, QStringLiteral("basemesh"), QStringLiteral("2 · Adjunct Gen3D"),
         QStringLiteral("Props only — not the body"), QStringLiteral("TRELLIS/UltraShape never replace the chosen body mesh. Import a prop or skip."), StageStatus::Locked},
        {StageId::Refine, QStringLiteral("refine"), QStringLiteral("3 · Adjunct refine"),
         QStringLiteral("Prop detail only"), QStringLiteral("Optional adjunct. Not character identity."), StageStatus::Locked},
        {StageId::GameReady, QStringLiteral("gameready"), QStringLiteral("4 · Adjunct game-ready"),
         QStringLiteral("Prop retopo / UV"), QStringLiteral("Not a second body cage. Body stays the mesh you selected."), StageStatus::Locked},
        {StageId::Garments, QStringLiteral("garments"), QStringLiteral("5 · Clothes plates"),
         QStringLiteral("Separable wearables"), QStringLiteral("Stills for SpellBound garment cook. T4 tunic is live bind, not reconstructed clothes."), StageStatus::Locked},
        {StageId::Compose, QStringLiteral("compose"), QStringLiteral("6 · Fit notes"),
         QStringLiteral("On, not glued"), QStringLiteral("Record fit notes. Drape cook stays Degraded."), StageStatus::Locked},
        {StageId::Hair, QStringLiteral("hair"), QStringLiteral("7 · Hair notes"),
         QStringLiteral("Scalp slot empty"), QStringLiteral("hair.wear.scalp is empty. No groom cook. Record style only."), StageStatus::Locked},
        {StageId::Export, QStringLiteral("export"), QStringLiteral("8 · Create contract"),
         QStringLiteral("Path B package"), QStringLiteral("Writes jarvis_pack + character_create.json. Not MikkT/FBX cook."), StageStatus::Locked},
    };

    buildUi();
    recomputeStageStatuses();
    refreshStageRail();
    refreshWorkspace();
    refreshActionRow();
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });

    // Restore last project name if any.
    QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString last = s.value(QStringLiteral("characterStudio/lastProject")).toString();
    if (!last.isEmpty()) {
        projectName_ = last;
        if (characterNameEdit_)
            characterNameEdit_->setText(projectName_);
    }
    loadProjectState();
    selectStage(0);
    reflowForWidth(width() > 0 ? width() : 1280);
}

void CharacterStudioPage::setProjectRoot(const QString &root)
{
    projectRoot_ = root;
    loadProjectState();
    refreshWorkspace();
}

void CharacterStudioPage::updateDisclosure(bool advanced)
{
    advanced_ = advanced;
    if (advancedConceptBlock_)
        advancedConceptBlock_->setVisible(advanced_);
    if (advancedMeshBlock_)
        advancedMeshBlock_->setVisible(advanced_);
    refreshActionRow();
}

void CharacterStudioPage::setBusy(bool busy, const QString &message)
{
    busy_ = busy;
    if (progress_) {
        progress_->setVisible(busy);
        progress_->setRange(0, 0);
    }
    if (statusBanner_ && !message.isEmpty())
        statusBanner_->setText(message);
    if (primaryActionBtn_)
        primaryActionBtn_->setEnabled(!busy);
    if (secondaryActionBtn_)
        secondaryActionBtn_->setEnabled(!busy);
    if (completeLookBtn_)
        completeLookBtn_->setEnabled(!busy);
}

void CharacterStudioPage::setPreviewImage(const QString &path, const QString &caption)
{
    if (path.isEmpty())
        return;

    // Normalize Windows paths; worker may return mixed separators.
    QString resolved = QDir::fromNativeSeparators(path.trimmed());
    if (!QFileInfo::exists(resolved)) {
        const QString alt = QDir::toNativeSeparators(resolved);
        if (QFileInfo::exists(alt))
            resolved = alt;
        else if (!projectRoot_.isEmpty()) {
            const QString joined = QDir(projectRoot_).filePath(resolved);
            if (QFileInfo::exists(joined))
                resolved = joined;
        }
    }

    // Route completed generations into the Concept stage artifact (generations always
    // target Concept / MultiView plates even if the user clicked another stage mid-run).
    const int conceptIdx = static_cast<int>(StageId::Concept);
    auto &stage = stages_[conceptIdx];
    stage.artifactPath = resolved;
    stage.status = StageStatus::Done;
    stage.note = caption.isEmpty() ? QStringLiteral("Artifact received") : caption;
    currentStage_ = conceptIdx;
    if (stageList_)
        stageList_->setCurrentRow(conceptIdx);
    if (stageStack_)
        stageStack_->setCurrentIndex(conceptIdx);

    if (conceptPreview_) {
        QPixmap px;
        if (!px.load(resolved))
            px = QPixmap(QDir::toNativeSeparators(resolved));
        if (!px.isNull()) {
            // Fill the allotted preview plate; prefer the live widget size, with a strong floor.
            QSize target = conceptPreview_->size();
            if (target.width() < 320 || target.height() < 400)
                target = QSize(qMax(320, target.width()), qMax(400, target.height()));
            // Grow toward the panel if layout has already expanded.
            if (conceptPreview_->width() > target.width())
                target.setWidth(conceptPreview_->width());
            if (conceptPreview_->height() > target.height())
                target.setHeight(conceptPreview_->height());
            conceptPreview_->setMinimumSize(280, 360);
            conceptPreview_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
            conceptPreview_->setAlignment(Qt::AlignCenter);
            conceptPreview_->setPixmap(px.scaled(target, Qt::KeepAspectRatio, Qt::SmoothTransformation));
            conceptPreview_->setProperty("svFullResPath", resolved);
        } else if (conceptPreviewCaption_) {
            conceptPreviewCaption_->setText(QStringLiteral("Could not load image: %1").arg(QFileInfo(resolved).fileName()));
        }
        if (conceptPreviewCaption_ && !px.isNull())
            conceptPreviewCaption_->setText(QFileInfo(resolved).fileName());
    }
    if (meshArtifactLabel_ && (stages_[currentStage_].id == StageId::BaseMesh
                               || stages_[currentStage_].id == StageId::Refine
                               || stages_[currentStage_].id == StageId::GameReady))
        meshArtifactLabel_->setText(resolved);

    recomputeStageStatuses();
    refreshStageRail();
    refreshWorkspace();
    refreshActionRow();
    refreshStatusBanner();
    saveProjectState();
    if (statusBanner_)
        statusBanner_->setText(QStringLiteral("Concept image ready — lock it or regenerate."));
}

void CharacterStudioPage::acceptConceptReference(const QString &imagePath, const QString &prompt)
{
    const QString path = imagePath.trimmed();
    if (path.isEmpty() || !QFileInfo::exists(path))
        return;

    // Land on Concept stage with locked hero from Concept Reference Lab.
    currentStage_ = static_cast<int>(StageId::Concept);
    if (stageList_)
        stageList_->setCurrentRow(currentStage_);

    if (conceptPromptEdit_ && !prompt.trimmed().isEmpty())
        conceptPromptEdit_->setPlainText(prompt.trimmed());

    // Apply multi-view adherence packs (SFW character body hero).
    const auto pack = buildConceptPromptPack(ConceptAssetType::CharacterBody,
                                             ConceptContentMode::Sfw,
                                             ConceptViewMode::HeroFront);
    if (negativePromptEdit_)
        negativePromptEdit_->setPlainText(pack.negativeScaffold);

    if (referencePathEdit_)
        referencePathEdit_->setText(path);

    auto &s = stages_[static_cast<int>(StageId::Concept)];
    s.artifactPath = path;
    s.status = StageStatus::Done;
    s.note = QStringLiteral("Imported from Concept Reference Lab");

    if (conceptPreview_) {
        QPixmap px(path);
        if (!px.isNull())
            conceptPreview_->setPixmap(px.scaled(conceptPreview_->size().isEmpty()
                                                     ? QSize(280, 360)
                                                     : conceptPreview_->size(),
                                                 Qt::KeepAspectRatio, Qt::SmoothTransformation));
        if (conceptPreviewCaption_)
            conceptPreviewCaption_->setText(QFileInfo(path).fileName());
    }

    recomputeStageStatuses();
    refreshStageRail();
    refreshWorkspace();
    refreshActionRow();
    refreshStatusBanner();
    saveProjectState();
    if (statusBanner_)
        statusBanner_->setText(
            QStringLiteral("Concept reference imported and locked. Continue to plates + pack."));
}

void CharacterStudioPage::buildUi()
{
    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Card),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    root->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    root->addWidget(buildHeroStrip());

    mainSplit_ = new QSplitter(Qt::Horizontal, this);
    mainSplit_->setObjectName(QStringLiteral("CharStudioSplit"));
    mainSplit_->setChildrenCollapsible(false);
    stageRail_ = buildStageRail();
    mainSplit_->addWidget(stageRail_);
    mainSplit_->addWidget(buildWorkspace());
    mainSplit_->setStretchFactor(0, 0);
    mainSplit_->setStretchFactor(1, 1);
    mainSplit_->setSizes({240, 900});
    root->addWidget(mainSplit_, 1);

    root->addWidget(buildActionRow());
}

void CharacterStudioPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    reflowForWidth(event ? event->size().width() : width());
    relayoutConceptPreview();
}

void CharacterStudioPage::reflowForWidth(int width)
{
    if (!mainSplit_ || !stageRail_)
        return;

    // Half-screen / restore: stage rail shrinks instead of crushing the workspace.
    int railBudget = 240;
    if (width < 1100)
        railBudget = 200;
    else if (width < 1400)
        railBudget = 220;
    else
        railBudget = 260;

    stageRail_->setMinimumWidth(qMax(160, railBudget - 20));
    stageRail_->setMaximumWidth(railBudget + 40);

    if (width < 1280) {
        const int workspace = qMax(320, width - railBudget - 48);
        mainSplit_->setSizes({railBudget, workspace});
    }
}

QWidget *CharacterStudioPage::buildHeroStrip()
{
    heroPanel_ = new DashboardGlassPanel(this);
    heroPanel_->setVariant(DashboardGlassPanel::Variant::Hero);
    heroPanel_->setCornerRadius(16);
    heroPanel_->setGlowStrength(1.05);
    heroPanel_->setMinimumHeight(108);

    auto *lay = new QVBoxLayout(heroPanel_);
    lay->setContentsMargins(20, 14, 20, 14);
    lay->setSpacing(6);

    auto *top = new QHBoxLayout;
    top->setSpacing(12);

    auto *titles = new QVBoxLayout;
    titles->setSpacing(2);
    auto *eyebrow = makeEyebrow(QStringLiteral("CREATE  ·  CHARACTER STUDIO"), heroPanel_);
    heroTitle_ = new QLabel(QStringLiteral("Character Studio"), heroPanel_);
    heroTitle_->setObjectName(QStringLiteral("CharStudioHeroTitle"));
    heroSubtitle_ = new QLabel(
        QStringLiteral("Concept → plates → character pack → JSON create contract. "
                       "Clothes/hair/rig stay Degraded lanes. Gen3D is props only."),
        heroPanel_);
    heroSubtitle_->setObjectName(QStringLiteral("CharStudioHeroSubtitle"));
    heroSubtitle_->setWordWrap(true);
    titles->addWidget(eyebrow);
    titles->addWidget(heroTitle_);
    titles->addWidget(heroSubtitle_);

    auto *metaCol = new QVBoxLayout;
    metaCol->setAlignment(Qt::AlignRight | Qt::AlignTop);
    heroMeta_ = new QLabel(QStringLiteral("Concept + plates"), heroPanel_);
    heroMeta_->setObjectName(QStringLiteral("CharStudioHeroMeta"));
    heroMeta_->setAlignment(Qt::AlignRight);
    progress_ = new QProgressBar(heroPanel_);
    progress_->setObjectName(QStringLiteral("CharStudioProgress"));
    progress_->setFixedWidth(160);
    progress_->setFixedHeight(6);
    progress_->setTextVisible(false);
    progress_->setVisible(false);
    metaCol->addWidget(heroMeta_);
    metaCol->addWidget(progress_, 0, Qt::AlignRight);

    top->addLayout(titles, 1);
    top->addLayout(metaCol, 0);
    lay->addLayout(top);

    statusBanner_ = new QLabel(
        QStringLiteral("Stage 0 is yours — lock a clean, upright, evenly-lit hero image. Everything downstream inherits it."),
        heroPanel_);
    statusBanner_->setObjectName(QStringLiteral("CharStudioStatusBanner"));
    statusBanner_->setWordWrap(true);
    lay->addWidget(statusBanner_);

    return heroPanel_;
}

QWidget *CharacterStudioPage::buildStageRail()
{
    auto *panel = new DashboardGlassPanel(this);
    panel->setVariant(DashboardGlassPanel::Variant::Raised);
    panel->setCornerRadius(16);
    panel->setMinimumWidth(180);
    panel->setMaximumWidth(280);
    panel->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    auto *lay = new QVBoxLayout(panel);
    lay->setContentsMargins(12, 14, 12, 14);
    lay->setSpacing(8);

    lay->addWidget(makeEyebrow(QStringLiteral("PIPELINE"), panel));
    auto *title = new QLabel(QStringLiteral("Stages"), panel);
    title->setObjectName(QStringLiteral("CharStudioSectionTitle"));
    lay->addWidget(title);

    stageList_ = new QListWidget(panel);
    stageList_->setObjectName(QStringLiteral("CharStudioStageList"));
    stageList_->setSpacing(4);
    stageList_->setUniformItemSizes(false);
    stageList_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    for (const auto &s : stages_) {
        auto *item = new QListWidgetItem(QStringLiteral("%1\n%2").arg(s.title, s.subtitle));
        item->setData(Qt::UserRole, static_cast<int>(s.id));
        stageList_->addItem(item);
    }
    for (int i = 0; i < stageList_->count(); ++i) {
        const auto id = static_cast<StageId>(stageList_->item(i)->data(Qt::UserRole).toInt());
        if (id == StageId::BaseMesh || id == StageId::Refine || id == StageId::GameReady)
            stageList_->item(i)->setHidden(true);
    }
    connect(stageList_, &QListWidget::currentRowChanged, this, &CharacterStudioPage::selectStage);
    lay->addWidget(stageList_, 1);

    return panel;
}

QWidget *CharacterStudioPage::buildWorkspace()
{
    auto *panel = new DashboardGlassPanel(this);
    panel->setVariant(DashboardGlassPanel::Variant::Standard);
    panel->setCornerRadius(16);
    panel->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    auto *scroll = new QScrollArea(panel);
    scroll->setObjectName(QStringLiteral("CharStudioWorkspaceScroll"));
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);

    stageStack_ = new QStackedWidget(scroll);
    stageStack_->setObjectName(QStringLiteral("CharStudioStack"));
    for (int i = 0; i < static_cast<int>(StageId::Count); ++i)
        stageStack_->addWidget(buildStagePage(static_cast<StageId>(i)));
    scroll->setWidget(stageStack_);

    auto *lay = new QVBoxLayout(panel);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->setSpacing(0);
    lay->addWidget(scroll, 1);
    return panel;
}

QWidget *CharacterStudioPage::buildStagePage(StageId id)
{
    auto *page = new QWidget;
    auto *lay = new QVBoxLayout(page);
    lay->setContentsMargins(4, 4, 4, 4);
    lay->setSpacing(10);

    const int idx = static_cast<int>(id);
    auto *head = new QLabel(stages_[idx].title, page);
    head->setObjectName(QStringLiteral("CharStudioSectionTitle"));
    auto *detail = new QLabel(stages_[idx].detail, page);
    detail->setObjectName(QStringLiteral("CharStudioMuted"));
    detail->setWordWrap(true);
    lay->addWidget(head);
    lay->addWidget(detail);

    if (id == StageId::Concept) {
        auto *row = new QHBoxLayout;
        row->setSpacing(14);

        auto *formHost = new QWidget(page);
        auto *form = new QVBoxLayout(formHost);
        form->setContentsMargins(0, 0, 0, 0);
        form->setSpacing(8);

        form->addWidget(makeFieldLabel(QStringLiteral("Character name"), formHost));
        characterNameEdit_ = new QLineEdit(projectName_, formHost);
        characterNameEdit_->setPlaceholderText(QStringLiteral("e.g. kael_ashward"));
        connect(characterNameEdit_, &QLineEdit::editingFinished, this, [this]() {
            const QString n = characterNameEdit_->text().trimmed();
            if (!n.isEmpty()) {
                projectName_ = n;
                QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
                s.setValue(QStringLiteral("characterStudio/lastProject"), projectName_);
            }
        });
        form->addWidget(characterNameEdit_);

        form->addWidget(makeFieldLabel(QStringLiteral("Concept prompt"), formHost));
        conceptPromptEdit_ = new QTextEdit(formHost);
        conceptPromptEdit_->setPlaceholderText(
            QStringLiteral("Stylized-realistic humanoid warrior, clean white background, "
                           "neutral A-pose, even studio lighting, full body, game character concept…"));
        conceptPromptEdit_->setFixedHeight(110);
        form->addWidget(conceptPromptEdit_);

        form->addWidget(makeFieldLabel(QStringLiteral("Content mode"), formHost));
        contentModeCombo_ = new QComboBox(formHost);
        contentModeCombo_->addItem(QStringLiteral("SFW body"), static_cast<int>(ConceptContentMode::Sfw));
        contentModeCombo_->addItem(QStringLiteral("NSFW anatomy"), static_cast<int>(ConceptContentMode::Nsfw));
        contentModeCombo_->setCurrentIndex(0);
        contentModeCombo_->setToolTip(
            QStringLiteral("SFW = game-safe body without genitals. NSFW = full anatomical detail when you need it."));
        form->addWidget(contentModeCombo_);

        auto *presetRow = new QHBoxLayout;
        stylePresetCombo_ = new QComboBox(formHost);
        stylePresetCombo_->addItems({
            QStringLiteral("Stylized Realistic"),
            QStringLiteral("Painterly Fantasy"),
            QStringLiteral("Hard-Surface Sci-Fi"),
            QStringLiteral("Anime-leaning"),
            QStringLiteral("Realistic Scan-like")
        });
        poseCombo_ = new QComboBox(formHost);
        poseCombo_->addItems({
            QStringLiteral("A-pose (preferred)"),
            QStringLiteral("T-pose"),
            QStringLiteral("Neutral standing"),
            QStringLiteral("Three-quarter hero")
        });
        aspectCombo_ = new QComboBox(formHost);
        aspectCombo_->addItems({
            QStringLiteral("Portrait 832×1216"),
            QStringLiteral("Square 1024×1024"),
            QStringLiteral("Tall 768×1344")
        });
        presetRow->addWidget(stylePresetCombo_, 1);
        presetRow->addWidget(poseCombo_, 1);
        presetRow->addWidget(aspectCombo_, 1);
        form->addLayout(presetRow);

        form->addWidget(makeFieldLabel(QStringLiteral("Model stack"), formHost));
        modelValueLabel_ = new QLabel(QStringLiteral("No model selected — required to generate"), formHost);
        modelValueLabel_->setObjectName(QStringLiteral("CharStudioMuted"));
        modelValueLabel_->setWordWrap(true);
        form->addWidget(modelValueLabel_);
        licenseNoteLabel_ = new QLabel(formHost);
        licenseNoteLabel_->setObjectName(QStringLiteral("CharStudioMuted"));
        licenseNoteLabel_->setWordWrap(true);
        licenseNoteLabel_->setVisible(false);
        form->addWidget(licenseNoteLabel_);
        auto *modelRow = new QHBoxLayout;
        pickModelBtn_ = new QPushButton(QStringLiteral("Choose model…"), formHost);
        pickModelBtn_->setObjectName(QStringLiteral("CharStudioSecondaryBtn"));
        connect(pickModelBtn_, &QPushButton::clicked, this, &CharacterStudioPage::pickModel);
        modelRow->addWidget(pickModelBtn_, 1);
        form->addLayout(modelRow);
        loraValueLabel_ = new QLabel(QStringLiteral("LoRA: None"), formHost);
        loraValueLabel_->setObjectName(QStringLiteral("CharStudioMuted"));
        loraValueLabel_->setWordWrap(true);
        form->addWidget(loraValueLabel_);
        auto *loraRow = new QHBoxLayout;
        pickLoraBtn_ = new QPushButton(QStringLiteral("Add LoRA…"), formHost);
        pickLoraBtn_->setObjectName(QStringLiteral("CharStudioSecondaryBtn"));
        clearLoraBtn_ = new QPushButton(QStringLiteral("Clear"), formHost);
        connect(pickLoraBtn_, &QPushButton::clicked, this, &CharacterStudioPage::pickLora);
        connect(clearLoraBtn_, &QPushButton::clicked, this, &CharacterStudioPage::clearLora);
        loraRow->addWidget(pickLoraBtn_, 1);
        loraRow->addWidget(clearLoraBtn_, 0);
        form->addLayout(loraRow);

        form->addWidget(makeFieldLabel(QStringLiteral("Reference image (optional)"), formHost));
        auto *refRow = new QHBoxLayout;
        referencePathEdit_ = new QLineEdit(formHost);
        referencePathEdit_->setPlaceholderText(QStringLiteral("Drop or browse a reference…"));
        auto *browseRef = new QPushButton(QStringLiteral("Browse"), formHost);
        connect(browseRef, &QPushButton::clicked, this, &CharacterStudioPage::browseReferenceImage);
        refRow->addWidget(referencePathEdit_, 1);
        refRow->addWidget(browseRef);
        form->addLayout(refRow);

        advancedConceptBlock_ = new QWidget(formHost);
        auto *adv = new QVBoxLayout(advancedConceptBlock_);
        adv->setContentsMargins(0, 6, 0, 0);
        adv->setSpacing(6);
        form->addWidget(makeFieldLabel(QStringLiteral("Negative prompt"), advancedConceptBlock_));
        negativePromptEdit_ = new QTextEdit(advancedConceptBlock_);
        negativePromptEdit_->setPlaceholderText(QStringLiteral("busy background, cropped, extra limbs, blurry, lowres…"));
        negativePromptEdit_->setFixedHeight(56);
        negativePromptEdit_->setPlainText(
            buildConceptPromptPack(ConceptAssetType::CharacterBody,
                                   currentContentMode(),
                                   ConceptViewMode::HeroFront)
                .negativeScaffold);
        adv->addWidget(negativePromptEdit_);
        auto *seedRow = new QHBoxLayout;
        seedLockCheck_ = new QCheckBox(QStringLiteral("Seed lock"), advancedConceptBlock_);
        seedEdit_ = new QLineEdit(QStringLiteral("42"), advancedConceptBlock_);
        seedEdit_->setFixedWidth(100);
        houseStyleLoraCheck_ = new QCheckBox(QStringLiteral("Apply style LoRA"), advancedConceptBlock_);
        houseStyleLoraCheck_->setChecked(false);
        houseStyleLoraCheck_->setToolTip(
            QStringLiteral("Uses the LoRA path below when you have chosen one."));
        seedRow->addWidget(seedLockCheck_);
        seedRow->addWidget(seedEdit_);
        seedRow->addWidget(houseStyleLoraCheck_, 1);
        adv->addLayout(seedRow);

        houseLoraPathLabel_ = new QLabel(QStringLiteral("Style LoRA: not configured"), advancedConceptBlock_);
        houseLoraPathLabel_->setObjectName(QStringLiteral("CharStudioMuted"));
        houseLoraPathLabel_->setWordWrap(true);
        adv->addWidget(houseLoraPathLabel_);
        auto *houseRow = new QHBoxLayout;
        pickHouseLoraBtn_ = new QPushButton(QStringLiteral("Choose LoRA…"), advancedConceptBlock_);
        clearHouseLoraBtn_ = new QPushButton(QStringLiteral("Clear"), advancedConceptBlock_);
        connect(pickHouseLoraBtn_, &QPushButton::clicked, this, &CharacterStudioPage::pickHouseLora);
        connect(clearHouseLoraBtn_, &QPushButton::clicked, this, &CharacterStudioPage::clearHouseLora);
        houseRow->addWidget(pickHouseLoraBtn_, 1);
        houseRow->addWidget(clearHouseLoraBtn_, 0);
        adv->addLayout(houseRow);

        // Reference adherence (IP-Adapter-style strength via denoise when ref is used)
        refDenoiseSpin_ = new QDoubleSpinBox(advancedConceptBlock_);
        refDenoiseSpin_->setRange(0.15, 0.95);
        refDenoiseSpin_->setSingleStep(0.05);
        refDenoiseSpin_->setDecimals(2);
        refDenoiseSpin_->setValue(0.62);
        refDenoiseSpin_->setToolTip(
            QStringLiteral("When a reference image is set, generation uses I2I. Higher = freer pose/style "
                           "(less stuck on the photo). Lower = stick closer to the reference."));
        adv->addWidget(new QLabel(QStringLiteral("Reference freedom (I2I denoise)"), advancedConceptBlock_));
        adv->addWidget(refDenoiseSpin_);

        // Restore house LoRA path
        {
            QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
            houseLoraPath_ = s.value(QStringLiteral("characterStudio/houseLoraPath")).toString();
            houseLoraDisplay_ = s.value(QStringLiteral("characterStudio/houseLoraDisplay")).toString();
            houseStyleLoraCheck_->setChecked(
                s.value(QStringLiteral("characterStudio/houseLoraEnabled"), false).toBool()
                && !houseLoraPath_.isEmpty());
            refreshHouseLoraLabel();
        }

        advancedConceptBlock_->setVisible(false);
        form->addWidget(advancedConceptBlock_);

        form->addStretch(1);
        row->addWidget(formHost, 3);

        auto *prevHost = new DashboardGlassPanel(page);
        prevHost->setVariant(DashboardGlassPanel::Variant::Inset);
        prevHost->setCornerRadius(14);
        auto *prevLay = new QVBoxLayout(prevHost);
        prevLay->setContentsMargins(12, 12, 12, 12);
        prevLay->addWidget(makeEyebrow(QStringLiteral("HERO PREVIEW"), prevHost));
        conceptPreview_ = new QLabel(QStringLiteral("No concept locked yet"), prevHost);
        conceptPreview_->setObjectName(QStringLiteral("CharStudioPreview"));
        conceptPreview_->setAlignment(Qt::AlignCenter);
        conceptPreview_->setMinimumSize(240, 320);
        conceptPreview_->setScaledContents(false);
        prevLay->addWidget(conceptPreview_, 1);
        conceptPreviewCaption_ = new QLabel(QStringLiteral("—"), prevHost);
        conceptPreviewCaption_->setObjectName(QStringLiteral("CharStudioMuted"));
        conceptPreviewCaption_->setAlignment(Qt::AlignCenter);
        prevLay->addWidget(conceptPreviewCaption_);
        completeLookBtn_ = new QPushButton(QStringLiteral("Complete look (head to toe)"), prevHost);
        completeLookBtn_->setObjectName(QStringLiteral("CharStudioSecondaryBtn"));
        completeLookBtn_->setToolTip(
            QStringLiteral("If the still is cropped, recreate the rest from what is present. "
                           "768×1344, Utopic Quants. Not a 14517 cook."));
        connect(completeLookBtn_, &QPushButton::clicked, this, &CharacterStudioPage::completeLookFromPresent);
        prevLay->addWidget(completeLookBtn_);
        row->addWidget(prevHost, 2);

        lay->addLayout(row, 1);
    } else if (id == StageId::MultiView) {
        lay->addWidget(makeFieldLabel(QStringLiteral("View count"), page));
        viewCountCombo_ = new QComboBox(page);
        viewCountCombo_->addItems({QStringLiteral("4 views"), QStringLiteral("8 views"), QStringLiteral("16 views (TRELLIS max)")});
        viewCountCombo_->setCurrentIndex(2);
        viewCountCombo_->setMinimumWidth(0);
        viewCountCombo_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        lay->addWidget(viewCountCombo_);
        multiViewSummary_ = new QLabel(
            QStringLiteral("Generates guided multi-view prompts from the locked hero. Review back/occluded views before mesh."),
            page);
        multiViewSummary_->setObjectName(QStringLiteral("CharStudioMuted"));
        multiViewSummary_->setWordWrap(true);
        lay->addWidget(multiViewSummary_);

        auto *packTitle = new QLabel(QStringLiteral("Jarvis character pack"), page);
        packTitle->setObjectName(QStringLiteral("CharStudioSectionTitle"));
        lay->addWidget(packTitle);
        auto *packContract = new QLabel(
            QStringLiteral("Author the small evidence pack used by SpellBound: a face close-up, a clothed T/A-pose turn, "
                           "and named pieces. Body is the mesh you choose; clothes stay separate. This does not claim "
                           "VL, sewing, Wrought transfer, bind/cook, or Stage proof are complete."),
            page);
        packContract->setObjectName(QStringLiteral("CharStudioMuted"));
        packContract->setWordWrap(true);
        lay->addWidget(packContract);

        auto addPackSlot = [this, page, lay](const QString &label,
                                             const QString &placeholder,
                                             QLineEdit *&target) {
            lay->addWidget(makeFieldLabel(label, page));
            auto *row = new QHBoxLayout;
            target = new QLineEdit(page);
            target->setPlaceholderText(placeholder);
            target->setMinimumWidth(0);
            auto *browse = new QPushButton(QStringLiteral("Browse"), page);
            connect(browse, &QPushButton::clicked, this,
                    [this, target, label]() { browseJarvisPackImage(target, label); });
            connect(target, &QLineEdit::textChanged, this,
                    [this]() { refreshJarvisPackReadiness(); });
            row->addWidget(target, 1);
            row->addWidget(browse);
            lay->addLayout(row);
        };
        addPackSlot(QStringLiteral("Face · front (required)"),
                    QStringLiteral("Identity / eyes / hairline"), packFaceFrontEdit_);
        addPackSlot(QStringLiteral("Face · 3/4 (optional)"),
                    QStringLiteral("Optional identity support"), packFace3qEdit_);
        addPackSlot(QStringLiteral("Clothes · front (required)"),
                    QStringLiteral("T- or A-pose on white"), packClothesFrontEdit_);
        addPackSlot(QStringLiteral("Clothes · side (side or back required)"),
                    QStringLiteral("Same pose, different pixels"), packClothesSideEdit_);
        addPackSlot(QStringLiteral("Clothes · back (side or back required)"),
                    QStringLiteral("Cloaks, straps, hair layers"), packClothesBackEdit_);
        addPackSlot(QStringLiteral("Clothes · 3/4 (optional)"),
                    QStringLiteral("Optional layer/read support"), packClothes3qEdit_);

        lay->addWidget(makeFieldLabel(QStringLiteral("Piece list (required, comma-separated)"), page));
        packPiecesEdit_ = new QLineEdit(page);
        packPiecesEdit_->setPlaceholderText(QStringLiteral("hat, pauldron, belt, catsuit, boots, cloak"));
        lay->addWidget(packPiecesEdit_);
        lay->addWidget(makeFieldLabel(QStringLiteral("Named palette (required, comma-separated)"), page));
        packPaletteEdit_ = new QLineEdit(page);
        packPaletteEdit_->setPlaceholderText(QStringLiteral("bone, charcoal, dried-blood, tarnished-brass"));
        lay->addWidget(packPaletteEdit_);
        connect(packPiecesEdit_, &QLineEdit::textChanged, this,
                [this]() { refreshJarvisPackReadiness(); });
        connect(packPaletteEdit_, &QLineEdit::textChanged, this,
                [this]() { refreshJarvisPackReadiness(); });

        jarvisPackReadinessLabel_ = new QLabel(page);
        jarvisPackReadinessLabel_->setObjectName(QStringLiteral("CharStudioStatusBanner"));
        jarvisPackReadinessLabel_->setWordWrap(true);
        lay->addWidget(jarvisPackReadinessLabel_);
        buildJarvisPackBtn_ = new QPushButton(QStringLiteral("Build Jarvis pack"), page);
        buildJarvisPackBtn_->setObjectName(QStringLiteral("CharStudioSecondaryBtn"));
        connect(buildJarvisPackBtn_, &QPushButton::clicked, this, &CharacterStudioPage::buildJarvisPack);
        lay->addWidget(buildJarvisPackBtn_, 0, Qt::AlignLeft);
        refreshJarvisPackReadiness();
        lay->addStretch(1);
    } else if (id == StageId::BaseMesh || id == StageId::Refine || id == StageId::GameReady) {
        meshBackendCombo_ = meshBackendCombo_ ? meshBackendCombo_ : new QComboBox(page);
        if (id == StageId::BaseMesh) {
            meshBackendCombo_->clear();
            meshBackendCombo_->addItems({
                QStringLiteral("Refuse — Pixal/TRELLIS is not the body"),
                QStringLiteral("Comfy Gen3D adjunct (props only)"),
                QStringLiteral("Import existing prop mesh…")
            });
            meshBackendCombo_->setCurrentIndex(2);
            detailTargetCombo_ = new QComboBox(page);
            detailTargetCombo_->addItems({
                QStringLiteral("Game prop (~200k)"),
                QStringLiteral("Hero character (~1M)"),
                QStringLiteral("Sculpt density (max)")
            });
            detailTargetCombo_->setCurrentIndex(1);
            runUltraShapeCheck_ = new QCheckBox(QStringLiteral("Chain UltraShape refine after generate"), page);
            runUltraShapeCheck_->setChecked(true);
            generateLodsCheck_ = new QCheckBox(QStringLiteral("Build LOD chain"), page);
            generateLodsCheck_->setChecked(true);
            bakeMapsCheck_ = new QCheckBox(QStringLiteral("Bake normal / AO / curvature"), page);
            bakeMapsCheck_->setChecked(true);

            auto *meshForm = new QVBoxLayout;
            meshForm->setContentsMargins(0, 0, 0, 0);
            meshForm->setSpacing(6);
            meshForm->addWidget(makeFieldLabel(QStringLiteral("Backend"), page));
            meshBackendCombo_->setMinimumWidth(0);
            meshBackendCombo_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
            meshForm->addWidget(meshBackendCombo_);
            meshForm->addWidget(makeFieldLabel(QStringLiteral("Detail target"), page));
            detailTargetCombo_->setMinimumWidth(0);
            detailTargetCombo_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
            meshForm->addWidget(detailTargetCombo_);
            lay->addLayout(meshForm);
            lay->addWidget(runUltraShapeCheck_);

            advancedMeshBlock_ = new QWidget(page);
            auto *adv = new QVBoxLayout(advancedMeshBlock_);
            adv->setContentsMargins(0, 4, 0, 0);
            adv->addWidget(generateLodsCheck_);
            adv->addWidget(bakeMapsCheck_);
            advancedMeshBlock_->setVisible(false);
            lay->addWidget(advancedMeshBlock_);
        }

        if (!meshToolStatus_) {
            meshToolStatus_ = new QLabel(page);
            meshToolStatus_->setObjectName(QStringLiteral("CharStudioStatusBanner"));
            meshToolStatus_->setWordWrap(true);
        }
        // Reparent-safe: only add once per page instance — create per-page label copy for display
        auto *toolStatus = new QLabel(page);
        toolStatus->setObjectName(QStringLiteral("CharStudioStatusBanner"));
        toolStatus->setWordWrap(true);
        toolStatus->setObjectName(QStringLiteral("CharStudioMeshToolStatus"));
        // Keep a pointer only for the first mesh page; others read via refresh
        if (id == StageId::BaseMesh)
            meshToolStatus_ = toolStatus;
        else
            toolStatus->setText(QStringLiteral("Same adjunct import path as Base mesh. Not a body cook."));

        lay->addWidget(toolStatus);

        auto *art = new QLabel(QStringLiteral("No mesh artifact yet"), page);
        art->setObjectName(QStringLiteral("CharStudioMuted"));
        art->setWordWrap(true);
        if (id == StageId::BaseMesh)
            meshArtifactLabel_ = art;
        lay->addWidget(art);

        auto *browseArt = new QPushButton(QStringLiteral("Attach existing artifact…"), page);
        connect(browseArt, &QPushButton::clicked, this, &CharacterStudioPage::browseArtifactForStage);
        lay->addWidget(browseArt, 0, Qt::AlignLeft);
        lay->addStretch(1);
    } else if (id == StageId::Garments) {
        lay->addWidget(makeFieldLabel(QStringLiteral("Garment / prop list (one per line)"), page));
        garmentListEdit_ = new QTextEdit(page);
        garmentListEdit_->setPlaceholderText(QStringLiteral("leather coat\nplate pauldrons\nlongsword\nboots"));
        garmentListEdit_->setFixedHeight(120);
        lay->addWidget(garmentListEdit_);
        garmentRegimeCombo_ = new QComboBox(page);
        garmentRegimeCombo_->addItems({
            QStringLiteral("cloth"),
            QStringLiteral("cloth (stiff)"),
            QStringLiteral("rigid"),
            QStringLiteral("rod"),
            QStringLiteral("static (weapon)")
        });
        lay->addWidget(makeFieldLabel(QStringLiteral("Default regime tag"), page));
        garmentRegimeCombo_->setMinimumWidth(0);
        garmentRegimeCombo_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        configureStudioCombo(garmentRegimeCombo_);
        lay->addWidget(garmentRegimeCombo_);
        auto *hint = new QLabel(
            QStringLiteral("Queue clothes-only plates (dummy=none product sheet). "
                           "Shrink-wrap onto the body mesh you selected uses dummy=whbs. "
                           "Cook stays Degraded — stills, not a wearable."),
            page);
        hint->setObjectName(QStringLiteral("CharStudioMuted"));
        hint->setWordWrap(true);
        lay->addWidget(hint);
        lay->addStretch(1);
    } else if (id == StageId::Compose || id == StageId::Hair) {
        auto *hint = new QLabel(
            id == StageId::Compose
                ? QStringLiteral("Fit notes only. Shrink-wrap is a scaffold onto the body mesh you selected. Drape cook is not in this build.")
                : QStringLiteral("Hair notes only. Scalp slot stays empty. No groom cook in this build."),
            page);
        hint->setObjectName(QStringLiteral("CharStudioMuted"));
        hint->setWordWrap(true);
        lay->addWidget(hint);
        auto *notes = new QPlainTextEdit(page);
        notes->setPlaceholderText(QStringLiteral("Notes stay notes — they do not mark this stage complete."));
        notes->setMinimumHeight(120);
        connect(notes, &QPlainTextEdit::textChanged, this, [this, id, notes]() {
            stages_[static_cast<int>(id)].note = notes->toPlainText().trimmed();
            saveProjectState();
        });
        lay->addWidget(notes);
        lay->addStretch(1);
    } else if (id == StageId::Export) {
        exportFormatCombo_ = new QComboBox(page);
        exportFormatCombo_->addItems({QStringLiteral("JSON create contract (Path B)")});
        writeLicenseSidecarCheck_ = new QCheckBox(QStringLiteral("Write per-asset license sidecar"), page);
        writeLicenseSidecarCheck_->setChecked(true);
        lay->addWidget(makeFieldLabel(QStringLiteral("Format"), page));
        exportFormatCombo_->setMinimumWidth(0);
        exportFormatCombo_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        lay->addWidget(exportFormatCombo_);
        lay->addWidget(writeLicenseSidecarCheck_);
        exportSummary_ = new QLabel(QStringLiteral("Export summary will appear here."), page);
        exportSummary_->setObjectName(QStringLiteral("CharStudioMuted"));
        exportSummary_->setWordWrap(true);
        lay->addWidget(exportSummary_);
        lay->addStretch(1);
    }

    return page;
}

QWidget *CharacterStudioPage::buildActionRow()
{
    auto *row = new DashboardGlassPanel(this);
    row->setVariant(DashboardGlassPanel::Variant::Utility);
    row->setCornerRadius(14);
    row->setFixedHeight(64);

    auto *lay = new QHBoxLayout(row);
    lay->setContentsMargins(14, 10, 14, 10);
    lay->setSpacing(10);

    actionHint_ = new QLabel(QStringLiteral("Ready"), row);
    actionHint_->setObjectName(QStringLiteral("CharStudioMuted"));
    lay->addWidget(actionHint_, 1);

    openT2IBtn_ = new QPushButton(QStringLiteral("Open in T2I"), row);
    openT2IBtn_->setObjectName(QStringLiteral("CharStudioSecondaryBtn"));
    connect(openT2IBtn_, &QPushButton::clicked, this, &CharacterStudioPage::openConceptInT2I);
    lay->addWidget(openT2IBtn_);

    saveProjectBtn_ = new QPushButton(QStringLiteral("Save"), row);
    saveProjectBtn_->setObjectName(QStringLiteral("CharStudioSecondaryBtn"));
    connect(saveProjectBtn_, &QPushButton::clicked, this, &CharacterStudioPage::saveProjectState);
    lay->addWidget(saveProjectBtn_);

    secondaryActionBtn_ = new QPushButton(QStringLiteral("Secondary"), row);
    secondaryActionBtn_->setObjectName(QStringLiteral("CharStudioSecondaryBtn"));
    connect(secondaryActionBtn_, &QPushButton::clicked, this, [this]() {
        if (currentStage_ == static_cast<int>(StageId::Concept))
            lockConcept();
        else if (currentStage_ == static_cast<int>(StageId::MultiView))
            generateMultiViewPrompts();
        else if (currentStage_ == static_cast<int>(StageId::Export))
            createFullCharacter();
        else if (currentStage_ < static_cast<int>(StageId::Count) - 1)
            selectStage(currentStage_ + 1);
    });
    lay->addWidget(secondaryActionBtn_);

    primaryActionBtn_ = new QPushButton(QStringLiteral("Run stage"), row);
    primaryActionBtn_->setObjectName(QStringLiteral("CharStudioPrimaryBtn"));
    connect(primaryActionBtn_, &QPushButton::clicked, this, &CharacterStudioPage::runCurrentStage);
    lay->addWidget(primaryActionBtn_);

    return row;
}

void CharacterStudioPage::selectStage(int index)
{
    if (index < 0 || index >= stages_.size())
        return;
    currentStage_ = index;
    if (stageStack_)
        stageStack_->setCurrentIndex(index);
    if (stageList_ && stageList_->currentRow() != index)
        stageList_->setCurrentRow(index);
    refreshStatusBanner();
    refreshActionRow();
    refreshWorkspace();
}

void CharacterStudioPage::refreshStageRail()
{
    if (!stageList_)
        return;
    for (int i = 0; i < stages_.size(); ++i) {
        auto *item = stageList_->item(i);
        if (!item)
            continue;
        const auto &s = stages_[i];
        item->setText(QStringLiteral("%1  [%2]\n%3")
                          .arg(s.title, stageStatusLabel(s.status), s.subtitle));
        item->setToolTip(s.detail + (s.note.isEmpty() ? QString() : QStringLiteral("\n") + s.note));
    }
}

void CharacterStudioPage::refreshWorkspace()
{
    if (meshToolStatus_) {
        QStringList bits;
        bits << QStringLiteral("Adjunct only — not character identity");
        bits << (hasPixalEnv_ ? QStringLiteral("external 3D env present") : QStringLiteral("no external 3D env"));
        bits << (hasBlender_ ? QStringLiteral("Blender present") : QStringLiteral("Blender missing"));
        if (!spikeRoot_.isEmpty())
            bits << QStringLiteral("spike: %1").arg(spikeRoot_);
        meshToolStatus_->setText(bits.join(QStringLiteral("  ·  ")));
    }
    if (exportSummary_) {
        int done = 0;
        int total = 0;
        for (const auto &s : stages_) {
            if (s.id == StageId::BaseMesh || s.id == StageId::Refine || s.id == StageId::GameReady)
                continue;
            ++total;
            if (s.status == StageStatus::Done)
                ++done;
        }
        exportSummary_->setText(
            QStringLiteral("%1 / %2 stages complete. Format: %3. License sidecar: %4.")
                .arg(done)
                .arg(total)
                .arg(exportFormatCombo_ ? exportFormatCombo_->currentText() : QStringLiteral("JSON create contract (Path B)"))
                .arg(writeLicenseSidecarCheck_ && writeLicenseSidecarCheck_->isChecked() ? QStringLiteral("yes") : QStringLiteral("no")));
    }
    refreshStatusBanner();
}

void CharacterStudioPage::refreshStatusBanner()
{
    if (!statusBanner_ || currentStage_ < 0 || currentStage_ >= stages_.size())
        return;
    const auto &s = stages_[currentStage_];
    QString msg = s.detail;
    if (!s.note.isEmpty())
        msg += QStringLiteral("  —  ") + s.note;
    if (!s.artifactPath.isEmpty())
        msg += QStringLiteral("  ·  ") + s.artifactPath;
    statusBanner_->setText(msg);
    if (heroMeta_)
        heroMeta_->setText(QStringLiteral("%1 · %2").arg(s.title, stageStatusLabel(s.status)));
}

void CharacterStudioPage::refreshActionRow()
{
    if (!primaryActionBtn_ || !secondaryActionBtn_ || !actionHint_)
        return;

    switch (static_cast<StageId>(currentStage_)) {
    case StageId::Concept:
        primaryActionBtn_->setText(QStringLiteral("Generate concept"));
        secondaryActionBtn_->setText(QStringLiteral("Lock concept"));
        actionHint_->setText(QStringLiteral("Generate a batch, pick the closest, then lock. Seed-lock once identity is close."));
        break;
    case StageId::MultiView:
        primaryActionBtn_->setText(QStringLiteral("Create character"));
        secondaryActionBtn_->setText(QStringLiteral("Build multi-view set"));
        actionHint_->setText(QStringLiteral("Path B: character pack + JSON create contract. Multi-view is extra plates, not a new body."));
        break;
    case StageId::BaseMesh:
        primaryActionBtn_->setText(QStringLiteral("Import prop mesh"));
        secondaryActionBtn_->setText(QStringLiteral("Skip adjunct"));
        actionHint_->setText(QStringLiteral("Adjunct only — not character identity. Pixal/TRELLIS cannot be the body."));
        break;
    case StageId::Refine:
        primaryActionBtn_->setText(QStringLiteral("Skip adjunct refine"));
        secondaryActionBtn_->setText(QStringLiteral("Next stage"));
        actionHint_->setText(QStringLiteral("Optional prop refine only. Not character identity."));
        break;
    case StageId::GameReady:
        primaryActionBtn_->setText(QStringLiteral("Skip adjunct bake"));
        secondaryActionBtn_->setText(QStringLiteral("Next stage"));
        actionHint_->setText(QStringLiteral("This stage does not replace the body mesh you selected."));
        break;
    case StageId::Garments:
        primaryActionBtn_->setText(QStringLiteral("Queue garment concepts"));
        secondaryActionBtn_->setText(QStringLiteral("Next stage"));
        actionHint_->setText(QStringLiteral("Clothes-only plates (dummy=none). Wrap later uses dummy=whbs. Cook still Degraded."));
        break;
    case StageId::Compose:
        primaryActionBtn_->setText(QStringLiteral("Shrink-wrap to body"));
        secondaryActionBtn_->setText(QStringLiteral("Next stage"));
        actionHint_->setText(QStringLiteral("Projects a garment shell onto the body mesh you selected. Cook still Degraded."));
        break;
    case StageId::Hair:
        primaryActionBtn_->setText(QStringLiteral("Record hair notes"));
        secondaryActionBtn_->setText(QStringLiteral("Next stage"));
        actionHint_->setText(QStringLiteral("Scalp slot stays empty. This is not a groom cook."));
        break;
    case StageId::Export:
        primaryActionBtn_->setText(QStringLiteral("Export create contract"));
        secondaryActionBtn_->setText(QStringLiteral("Create character"));
        actionHint_->setText(QStringLiteral("Writes jarvis_pack + character_create.json. Cook stays incomplete."));
        break;
    default:
        break;
    }
}

void CharacterStudioPage::recomputeStageStatuses()
{
    // Unlock linearly based on prior Done, with honest Blocked when tools missing.
    for (int i = 0; i < stages_.size(); ++i) {
        auto &s = stages_[i];
        if (s.status == StageStatus::Done || s.status == StageStatus::Running)
            continue;
        if (i == 0) {
            s.status = StageStatus::Ready;
            continue;
        }
        if (s.id == StageId::BaseMesh || s.id == StageId::Refine || s.id == StageId::GameReady) {
            s.status = (stages_[static_cast<int>(StageId::MultiView)].status == StageStatus::Done)
                           ? StageStatus::Done
                           : StageStatus::Locked;
            continue;
        }
        if (s.id == StageId::Compose || s.id == StageId::Hair) {
            if (s.status == StageStatus::Done || s.status == StageStatus::Running)
                continue;
            s.status = (stages_[static_cast<int>(StageId::Garments)].status == StageStatus::Done)
                           ? StageStatus::Ready
                           : StageStatus::Locked;
            continue;
        }
        if (s.id == StageId::Export) {
            if (s.status == StageStatus::Done || s.status == StageStatus::Running)
                continue;
            s.status = (stages_[static_cast<int>(StageId::Garments)].status == StageStatus::Done)
                           ? StageStatus::Ready
                           : StageStatus::Locked;
            continue;
        }
        if (stages_[i - 1].status == StageStatus::Done) {
            s.status = StageStatus::Ready;
            if ((s.id == StageId::BaseMesh || s.id == StageId::Refine || s.id == StageId::GameReady)
                && !hasPixalEnv_ && s.artifactPath.isEmpty()) {
                s.status = StageStatus::Warning;
                if (s.note.isEmpty())
                    s.note = QStringLiteral("External 3D toolchain incomplete — you can still attach artifacts.");
            }
        } else if (s.status != StageStatus::Warning) {
            s.status = StageStatus::Locked;
        }
    }
}

void CharacterStudioPage::runCurrentStage()
{
    switch (static_cast<StageId>(currentStage_)) {
    case StageId::Concept:
        generateConcept();
        break;
    case StageId::MultiView:
        createFullCharacter();
        break;
    case StageId::BaseMesh:
        if (meshBackendCombo_)
            meshBackendCombo_->setCurrentIndex(2);
        runMeshPipeline(StageId::BaseMesh);
        break;
    case StageId::Refine:
    case StageId::GameReady:
        stages_[currentStage_].status = StageStatus::Warning;
        stages_[currentStage_].note = QStringLiteral("Adjunct skipped — body stays the mesh you selected");
        recomputeStageStatuses();
        refreshStageRail();
        refreshActionRow();
        saveProjectState();
        break;
    case StageId::Garments: {
        const QString list = garmentListEdit_ ? garmentListEdit_->toPlainText() : QString();
        const QStringList items = list.split(QLatin1Char('\n'), Qt::SkipEmptyParts);
        if (items.isEmpty()) {
            setStageNote(StageId::Garments, QStringLiteral("Add at least one garment/prop line."));
            refreshStatusBanner();
            return;
        }
        if (selectedModelPath_.trimmed().isEmpty()) {
            setStageNote(StageId::Garments, QStringLiteral("Choose a checkpoint first (Model stack on Concept)."));
            refreshStatusBanner();
            return;
        }
        const QString firstGarment = items.first().trimmed();
        QJsonArray remaining;
        for (int i = 1; i < items.size(); ++i)
            remaining.append(items.at(i).trimmed());
        const QString slug = garmentSlug(firstGarment);
        const QString dest = QDir(currentProjectDir()).filePath(QStringLiteral("garments/%1").arg(slug));
        QDir().mkpath(dest);
        lastClothesOnlyDest_ = dest;

        QJsonArray views;
        views.append(QStringLiteral("front"));
        views.append(QStringLiteral("side"));
        views.append(QStringLiteral("back"));

        QJsonObject payload;
        payload.insert(QStringLiteral("command"), QStringLiteral("clothes_only"));
        payload.insert(QStringLiteral("task_command"), QStringLiteral("clothes_only"));
        payload.insert(QStringLiteral("garment"), firstGarment);
        payload.insert(QStringLiteral("garment_text"), firstGarment);
        payload.insert(QStringLiteral("views"), views);
        payload.insert(QStringLiteral("dummy"), QStringLiteral("none"));
        payload.insert(QStringLiteral("wrap_dummy"), QStringLiteral("whbs"));
        payload.insert(QStringLiteral("queue"), remaining);
        payload.insert(QStringLiteral("character_id"), projectName_);
        payload.insert(QStringLiteral("dest"), dest);
        payload.insert(QStringLiteral("prompt"), firstGarment);
        payload.insert(QStringLiteral("negative_prompt"),
                       QStringLiteral("person, mannequin, busy background, text, watermark, second face"));
        payload.insert(QStringLiteral("width"), 1024);
        payload.insert(QStringLiteral("height"), 1024);
        payload.insert(QStringLiteral("steps"), 52);
        payload.insert(QStringLiteral("cfg"), 3.5);
        payload.insert(QStringLiteral("seed"), 7);
        payload.insert(QStringLiteral("output_prefix"),
                       QStringLiteral("character_%1_clothes_%2").arg(projectName_, slug));
        payload.insert(QStringLiteral("output_folder"), dest);
        payload.insert(QStringLiteral("model"), selectedModelPath_.trimmed());
        payload.insert(QStringLiteral("model_display"),
                       selectedModelDisplay_.isEmpty() ? QFileInfo(selectedModelPath_).fileName()
                                                       : selectedModelDisplay_);
        if (!selectedLoraPath_.trimmed().isEmpty()) {
            QJsonArray loras;
            QJsonObject l;
            l.insert(QStringLiteral("path"), selectedLoraPath_.trimmed());
            l.insert(QStringLiteral("name"),
                     selectedLoraDisplay_.isEmpty() ? QFileInfo(selectedLoraPath_).fileName()
                                                    : selectedLoraDisplay_);
            l.insert(QStringLiteral("weight"), 1.0);
            l.insert(QStringLiteral("enabled"), true);
            loras.append(l);
            payload.insert(QStringLiteral("loras"), loras);
        }
        stages_[static_cast<int>(StageId::Garments)].status = StageStatus::Running;
        stages_[static_cast<int>(StageId::Garments)].artifactPath = dest;
        stages_[static_cast<int>(StageId::Garments)].note =
            QStringLiteral("Clothes plates queued — shrink-wrap scaffold, cook still Degraded.");
        refreshStageRail();
        setBusy(true, QStringLiteral("Clothes plates queued — shrink-wrap scaffold, cook still Degraded."));
        if (statusBanner_)
            statusBanner_->setText(QStringLiteral("Clothes plates queued — shrink-wrap scaffold, cook still Degraded."));
        saveProjectState();
        emit generateRequested(QStringLiteral("t2i"), payload, false);
        for (int i = 1; i < items.size(); ++i) {
            QJsonObject queued = payload;
            const QString extra = items.at(i).trimmed();
            const QString extraSlug = garmentSlug(extra);
            const QString extraDest = QDir(currentProjectDir()).filePath(QStringLiteral("garments/%1").arg(extraSlug));
            queued.insert(QStringLiteral("garment"), extra);
            queued.insert(QStringLiteral("garment_text"), extra);
            queued.insert(QStringLiteral("prompt"), extra);
            queued.insert(QStringLiteral("dest"), extraDest);
            queued.insert(QStringLiteral("output_folder"), extraDest);
            queued.insert(QStringLiteral("output_prefix"),
                           QStringLiteral("character_%1_clothes_%2").arg(projectName_, extraSlug));
            queued.insert(QStringLiteral("queue"), QJsonArray());
            emit generateRequested(QStringLiteral("t2i"), queued, true);
        }
        break;
    }
    case StageId::Compose: {
        QString plates = lastClothesOnlyDest_.trimmed();
        if (plates.isEmpty()) {
            const QDir garments(QDir(currentProjectDir()).filePath(QStringLiteral("garments")));
            const QStringList slugs = garments.entryList(QDir::Dirs | QDir::NoDotAndDotDot);
            for (const QString &slug : slugs) {
                if (QFileInfo::exists(garments.filePath(slug + QStringLiteral("/front.png")))) {
                    plates = garments.filePath(slug);
                    break;
                }
            }
        }
        if (plates.isEmpty()) {
            setStageNote(StageId::Compose, QStringLiteral("Queue clothes-only plates on Garments first."));
            refreshStatusBanner();
            return;
        }
        QSettings bodySettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        QString bodyGlb = bodySettings.value(QStringLiteral("characterStudio/bodyGlb")).toString().trimmed();
        if (bodyGlb.isEmpty() || !QFileInfo::exists(bodyGlb)) {
            bodyGlb = QFileDialog::getOpenFileName(this,
                                                   QStringLiteral("Choose body GLB"),
                                                   QString(),
                                                   QStringLiteral("GLB (*.glb)"));
            bodyGlb = QDir::fromNativeSeparators(bodyGlb.trimmed());
            if (bodyGlb.isEmpty() || !QFileInfo::exists(bodyGlb)) {
                setStageNote(StageId::Compose,
                             QStringLiteral("No body GLB chosen. Wrap does not assume a house path."));
                refreshStatusBanner();
                return;
            }
            bodySettings.setValue(QStringLiteral("characterStudio/bodyGlb"), bodyGlb);
        }
        QJsonObject payload;
        payload.insert(QStringLiteral("command"), QStringLiteral("garment_shrinkwrap"));
        payload.insert(QStringLiteral("task_command"), QStringLiteral("garment_shrinkwrap"));
        payload.insert(QStringLiteral("plates_dir"), plates);
        payload.insert(QStringLiteral("dest"), plates);
        payload.insert(QStringLiteral("character_id"), projectName_);
        payload.insert(QStringLiteral("run_blender"), true);
        payload.insert(QStringLiteral("body"), bodyGlb);
        payload.insert(QStringLiteral("prompt"), QStringLiteral("shrinkwrap scaffold"));
        payload.insert(QStringLiteral("width"), 768);
        payload.insert(QStringLiteral("height"), 1344);
        payload.insert(QStringLiteral("model"), selectedModelPath_.trimmed());
        payload.insert(QStringLiteral("output_prefix"),
                       QStringLiteral("character_%1_wrap").arg(projectName_));
        payload.insert(QStringLiteral("output_folder"), plates);
        stages_[static_cast<int>(StageId::Compose)].status = StageStatus::Running;
        stages_[static_cast<int>(StageId::Compose)].artifactPath = plates;
        stages_[static_cast<int>(StageId::Compose)].note =
            QStringLiteral("Shrink-wrap scaffold queued onto the selected body mesh — cook still Degraded.");
        refreshStageRail();
        setBusy(true, QStringLiteral("Shrink-wrap scaffold onto selected body mesh…"));
        saveProjectState();
        emit generateRequested(QStringLiteral("t2i"), payload, false);
        break;
    }
    case StageId::Hair: {
        writeCreateContract(QDir(currentProjectDir()).filePath(QStringLiteral("jarvis_pack")));
        stages_[currentStage_].status = StageStatus::Warning;
        stages_[currentStage_].note = (static_cast<StageId>(currentStage_) == StageId::Hair)
                                          ? QStringLiteral("Hair notes recorded; scalp slot empty; cook false")
                                          : QStringLiteral("Fit notes recorded; garment cook still Degraded");
        recomputeStageStatuses();
        refreshStageRail();
        refreshActionRow();
        saveProjectState();
        break;
    }
    case StageId::Export:
        exportCharacterPackage();
        break;
    default:
        break;
    }
}

void CharacterStudioPage::generateConcept()
{
    if (selectedModelPath_.trimmed().isEmpty()) {
        setStageNote(StageId::Concept, QStringLiteral("Choose a checkpoint first (Model stack)."));
        refreshStatusBanner();
        if (statusBanner_)
            statusBanner_->setText(QStringLiteral("Choose a checkpoint on this page before generating."));
        return;
    }
    const QJsonObject payload = buildConceptPayload();
    if (payload.value(QStringLiteral("prompt")).toString().trimmed().isEmpty()) {
        setStageNote(StageId::Concept, QStringLiteral("Write a concept prompt first."));
        refreshStatusBanner();
        return;
    }
    stages_[static_cast<int>(StageId::Concept)].status = StageStatus::Running;
    refreshStageRail();
    setBusy(true, QStringLiteral("Generating concept…"));
    emit generateRequested(QStringLiteral("t2i"), payload, false);
}

QString CharacterStudioPage::lookCompleteSourcePath() const
{
    if (conceptPreview_) {
        const QString preview = conceptPreview_->property("svFullResPath").toString().trimmed();
        if (!preview.isEmpty() && QFileInfo::exists(preview))
            return preview;
    }
    const QString artifact = stages_[static_cast<int>(StageId::Concept)].artifactPath.trimmed();
    if (!artifact.isEmpty() && QFileInfo::exists(artifact))
        return artifact;
    if (referencePathEdit_) {
        const QString ref = referencePathEdit_->text().trimmed();
        if (!ref.isEmpty() && QFileInfo::exists(ref))
            return ref;
    }
    return {};
}

void CharacterStudioPage::completeLookFromPresent()
{
    const QString source = lookCompleteSourcePath();
    if (source.isEmpty()) {
        setStageNote(StageId::Concept,
                     QStringLiteral("Attach a cropped still (reference or preview) before Complete look."));
        refreshStatusBanner();
        return;
    }
    if (selectedModelPath_.trimmed().isEmpty()) {
        setStageNote(StageId::Concept, QStringLiteral("Choose a checkpoint first (Model stack)."));
        refreshStatusBanner();
        return;
    }
    const QString dest = QDir(currentProjectDir()).filePath(QStringLiteral("look_complete"));
    QDir().mkpath(dest);
    QJsonObject payload;
    payload.insert(QStringLiteral("command"), QStringLiteral("look_complete"));
    payload.insert(QStringLiteral("task_command"), QStringLiteral("look_complete"));
    payload.insert(QStringLiteral("input_image"), source);
    payload.insert(QStringLiteral("method"), QStringLiteral("t2i_identity"));
    payload.insert(QStringLiteral("target"), QStringLiteral("full_body_768x1344"));
    payload.insert(QStringLiteral("dest"), dest);
    payload.insert(QStringLiteral("output_folder"), dest);
    payload.insert(QStringLiteral("character_id"), projectName_);
    payload.insert(QStringLiteral("prompt"),
                   QStringLiteral("full body, entire figure, head to toe, feet visible"));
    payload.insert(QStringLiteral("negative_prompt"),
                   QStringLiteral("close-up, cropped, bust shot, missing feet, second face"));
    payload.insert(QStringLiteral("width"), 768);
    payload.insert(QStringLiteral("height"), 1344);
    payload.insert(QStringLiteral("steps"), 52);
    payload.insert(QStringLiteral("cfg"), 3.5);
    payload.insert(QStringLiteral("model"), selectedModelPath_.trimmed());
    payload.insert(QStringLiteral("model_display"),
                   selectedModelDisplay_.isEmpty() ? QFileInfo(selectedModelPath_).fileName()
                                                   : selectedModelDisplay_);
    payload.insert(QStringLiteral("output_prefix"),
                   QStringLiteral("character_%1_look_complete").arg(projectName_));
    stages_[static_cast<int>(StageId::Concept)].status = StageStatus::Running;
    stages_[static_cast<int>(StageId::Concept)].note =
        QStringLiteral("Look-complete queued — recreate missing body from what is present.");
    refreshStageRail();
    setBusy(true, QStringLiteral("Completing look from what is present…"));
    saveProjectState();
    emit generateRequested(QStringLiteral("t2i"), payload, false);
}

void CharacterStudioPage::lockConcept()
{
    auto &s = stages_[static_cast<int>(StageId::Concept)];
    if (s.artifactPath.isEmpty() && conceptPreview_ && conceptPreview_->pixmap(Qt::ReturnByValue).isNull()) {
        // Allow lock from reference path.
        if (referencePathEdit_ && QFileInfo::exists(referencePathEdit_->text().trimmed())) {
            s.artifactPath = referencePathEdit_->text().trimmed();
        } else {
            setStageNote(StageId::Concept, QStringLiteral("Generate or attach a hero image before locking."));
            refreshStatusBanner();
            return;
        }
    }
    s.status = StageStatus::Done;
    s.note = QStringLiteral("Concept locked");
    recomputeStageStatuses();
    refreshStageRail();
    refreshActionRow();
    saveProjectState();
    if (statusBanner_)
        statusBanner_->setText(QStringLiteral("Concept locked. Continue to plates + pack."));
}

void CharacterStudioPage::openConceptInT2I()
{
    emit navigateRequested(QStringLiteral("t2i"));
}

void CharacterStudioPage::generateMultiViewPrompts()
{
    if (stages_[static_cast<int>(StageId::Concept)].status != StageStatus::Done) {
        setStageNote(StageId::MultiView, QStringLiteral("Lock the concept first."));
        refreshStatusBanner();
        return;
    }
    if (selectedModelPath_.trimmed().isEmpty()) {
        setStageNote(StageId::MultiView, QStringLiteral("Choose a checkpoint first (Model stack on Concept)."));
        refreshStatusBanner();
        return;
    }
    const int views = viewCountCombo_ ? (viewCountCombo_->currentIndex() == 0 ? 4
                                              : viewCountCombo_->currentIndex() == 1 ? 8
                                                                                      : 16)
                                      : 16;
    const QString base = conceptPromptEdit_ ? conceptPromptEdit_->toPlainText().trimmed()
                                            : QStringLiteral("character");
    const auto pack = buildConceptPromptPack(ConceptAssetType::CharacterBody,
                                             currentContentMode(),
                                             ConceptViewMode::TurnaroundSheet);
    // Seed a multi-view sheet request (single image grid) — practical path until dedicated multi-view family.
    QJsonObject payload;
    payload.insert(QStringLiteral("prompt"), composeConceptPositivePrompt(base, pack));
    payload.insert(QStringLiteral("negative_prompt"),
                   negativePromptEdit_ && !negativePromptEdit_->toPlainText().trimmed().isEmpty()
                       ? negativePromptEdit_->toPlainText().trimmed()
                       : pack.negativeScaffold);
    payload.insert(QStringLiteral("width"), conceptDefaultWidth(ConceptViewMode::TurnaroundSheet));
    payload.insert(QStringLiteral("height"), conceptDefaultHeight(ConceptViewMode::TurnaroundSheet));
    payload.insert(QStringLiteral("steps"), 30);
    payload.insert(QStringLiteral("cfg"), 4.5);
    payload.insert(QStringLiteral("seed"),
                   seedLockCheck_ && seedLockCheck_->isChecked() && seedEdit_
                       ? seedEdit_->text().toInt()
                       : 11);
    payload.insert(QStringLiteral("output_prefix"),
                   QStringLiteral("character_%1_multiview").arg(projectName_));
    payload.insert(QStringLiteral("model"), selectedModelPath_.trimmed());
    payload.insert(QStringLiteral("model_display"),
                   selectedModelDisplay_.isEmpty() ? QFileInfo(selectedModelPath_).fileName()
                                                   : selectedModelDisplay_);
    if (!selectedLoraPath_.trimmed().isEmpty()) {
        QJsonArray loras;
        QJsonObject l;
        l.insert(QStringLiteral("path"), selectedLoraPath_.trimmed());
        l.insert(QStringLiteral("name"),
                 selectedLoraDisplay_.isEmpty() ? QFileInfo(selectedLoraPath_).fileName()
                                                : selectedLoraDisplay_);
        l.insert(QStringLiteral("weight"), 1.0);
        l.insert(QStringLiteral("enabled"), true);
        loras.append(l);
        payload.insert(QStringLiteral("loras"), loras);
    }
    if (!stages_[0].artifactPath.isEmpty()) {
        payload.insert(QStringLiteral("input_image"), stages_[0].artifactPath);
        stages_[static_cast<int>(StageId::MultiView)].status = StageStatus::Running;
        refreshStageRail();
        setBusy(true, QStringLiteral("Building multi-view sheet via I2I…"));
        emit generateRequested(QStringLiteral("i2i"), payload, false);
    } else {
        stages_[static_cast<int>(StageId::MultiView)].status = StageStatus::Running;
        refreshStageRail();
        setBusy(true, QStringLiteral("Building multi-view sheet via T2I…"));
        emit generateRequested(QStringLiteral("t2i"), payload, false);
    }
    if (multiViewSummary_)
        multiViewSummary_->setText(QStringLiteral("Queued %1-view sheet from locked concept.").arg(views));
}

void CharacterStudioPage::browseJarvisPackImage(QLineEdit *target, const QString &slotTitle)
{
    if (!target)
        return;
    const QString path = QFileDialog::getOpenFileName(
        this, slotTitle, currentProjectDir(),
        QStringLiteral("Images (*.png *.jpg *.jpeg *.webp *.bmp)"));
    if (!path.isEmpty())
        target->setText(QDir::fromNativeSeparators(path));
}

void CharacterStudioPage::refreshJarvisPackReadiness()
{
    if (!jarvisPackReadinessLabel_)
        return;

    QStringList missing;
    const auto hasFile = [](QLineEdit *edit) {
        return edit && QFileInfo(edit->text().trimmed()).isFile();
    };
    if (!hasFile(packFaceFrontEdit_))
        missing << QStringLiteral("face front");
    if (!hasFile(packClothesFrontEdit_))
        missing << QStringLiteral("clothes front");
    if (!hasFile(packClothesSideEdit_) && !hasFile(packClothesBackEdit_))
        missing << QStringLiteral("clothes side or back");
    if (!packPiecesEdit_ || packPiecesEdit_->text().trimmed().isEmpty())
        missing << QStringLiteral("piece list");
    if (!packPaletteEdit_ || packPaletteEdit_->text().trimmed().isEmpty())
        missing << QStringLiteral("named palette");

    const bool building = jarvisPackProcess_ && jarvisPackProcess_->state() != QProcess::NotRunning;
    if (!missing.isEmpty()) {
        jarvisPackReadinessLabel_->setText(
            QStringLiteral("Pack needs: %1. No nude plates are required or requested.")
                .arg(missing.join(QStringLiteral(", "))));
    } else {
        const bool optimal = hasFile(packFace3qEdit_) && hasFile(packClothesSideEdit_)
                             && hasFile(packClothesBackEdit_) && hasFile(packClothes3qEdit_);
        jarvisPackReadinessLabel_->setText(
            optimal
                ? QStringLiteral("Optimal seven-file pack selected. Build validates hashes before writing it.")
                : QStringLiteral("Minimum pack selected. Build validates that required views contain different bytes."));
    }
    if (buildJarvisPackBtn_)
        buildJarvisPackBtn_->setEnabled(missing.isEmpty() && !building);
}

void CharacterStudioPage::buildJarvisPack()
{
    refreshJarvisPackReadiness();
    if (!buildJarvisPackBtn_ || !buildJarvisPackBtn_->isEnabled())
        return;

    const QString python = QDir(projectRoot_).filePath(QStringLiteral(".venv/Scripts/python.exe"));
    const QString script = QDir(projectRoot_).filePath(QStringLiteral("python/character_pack.py"));
    if (!QFileInfo(python).isFile() || !QFileInfo(script).isFile()) {
        jarvisPackReadinessLabel_->setText(
            QStringLiteral("Pack builder unavailable: project Python or python/character_pack.py is missing."));
        return;
    }

    QJsonObject images;
    const auto addImage = [&images](const QString &key, QLineEdit *edit) {
        if (edit && !edit->text().trimmed().isEmpty())
            images.insert(key, edit->text().trimmed());
    };
    addImage(QStringLiteral("face_front"), packFaceFrontEdit_);
    addImage(QStringLiteral("face_3q"), packFace3qEdit_);
    addImage(QStringLiteral("clothes_front"), packClothesFrontEdit_);
    addImage(QStringLiteral("clothes_side"), packClothesSideEdit_);
    addImage(QStringLiteral("clothes_back"), packClothesBackEdit_);
    addImage(QStringLiteral("clothes_3q"), packClothes3qEdit_);

    QJsonObject request;
    request.insert(QStringLiteral("pack_id"), projectName_);
    request.insert(QStringLiteral("output_dir"),
                   QDir(currentProjectDir()).filePath(QStringLiteral("jarvis_pack")));
    request.insert(QStringLiteral("images"), images);
    request.insert(QStringLiteral("pieces"), packPiecesEdit_->text().trimmed());
    request.insert(QStringLiteral("palette"), packPaletteEdit_->text().trimmed());
    request.insert(QStringLiteral("pose"), poseCombo_ ? poseCombo_->currentText()
                                                       : QStringLiteral("T- or A-pose, white ground"));

    const QString requestPath = QDir(currentProjectDir()).filePath(QStringLiteral("jarvis_pack_request.json"));
    if (!writeJsonAtomically(requestPath, QJsonDocument(request))) {
        jarvisPackReadinessLabel_->setText(QStringLiteral("Could not write the pack request file."));
        return;
    }
    saveProjectState();

    jarvisPackProcess_ = new QProcess(this);
    jarvisPackProcess_->setWorkingDirectory(projectRoot_);
    QProcessEnvironment packEnvironment = QProcessEnvironment::systemEnvironment();
    packEnvironment.insert(QStringLiteral("PYTHONNOUSERSITE"), QStringLiteral("1"));
    packEnvironment.remove(QStringLiteral("PYTHONPATH"));
    packEnvironment.remove(QStringLiteral("PYTHONHOME"));
    packEnvironment.insert(QStringLiteral("VIRTUAL_ENV"), QFileInfo(python).dir().absolutePath() + QStringLiteral("/.."));
    jarvisPackProcess_->setProcessEnvironment(packEnvironment);
    buildJarvisPackBtn_->setEnabled(false);
    jarvisPackReadinessLabel_->setText(
        QStringLiteral("Validating hashes and authoring the pack… no generation or cook is running."));
    setBusy(true, QStringLiteral("Authoring Jarvis reference pack…"));
    connect(jarvisPackProcess_, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this](int exitCode, QProcess::ExitStatus exitStatus) {
                QProcess *process = jarvisPackProcess_;
                jarvisPackProcess_ = nullptr;
                const QByteArray output = process ? process->readAllStandardOutput() : QByteArray();
                const QByteArray errors = process ? process->readAllStandardError() : QByteArray();
                QJsonObject result;
                const QList<QByteArray> lines = output.split('\n');
                for (auto it = lines.crbegin(); it != lines.crend(); ++it) {
                    const QJsonDocument doc = QJsonDocument::fromJson(it->trimmed());
                    if (doc.isObject()) {
                        result = doc.object();
                        break;
                    }
                }

                if (exitStatus == QProcess::NormalExit && exitCode == 0
                    && result.value(QStringLiteral("ok")).toBool()) {
                    const QString outputDir = result.value(QStringLiteral("output_dir")).toString();
                    const bool optimal = result.value(QStringLiteral("optimal")).toBool();
                    jarvisPackReadinessLabel_->setText(
                        QStringLiteral("%1 pack ready at %2. Evidence authored only: Jarvis still needs VL, "
                                       "per-piece mesh reconstruction, Wrought transfer, bind/cook, and Stage proof.")
                            .arg(optimal ? QStringLiteral("Optimal") : QStringLiteral("Minimum"), outputDir));
                    setStageNote(StageId::MultiView,
                                 QStringLiteral("Jarvis pack authored; downstream concept-to-style remains incomplete."));
                } else {
                    QString reason = result.value(QStringLiteral("error")).toString().trimmed();
                    if (reason.isEmpty())
                        reason = QString::fromUtf8(errors).trimmed();
                    if (reason.isEmpty())
                        reason = QStringLiteral("pack builder exited without a result");
                    jarvisPackReadinessLabel_->setText(QStringLiteral("Pack refused: %1").arg(reason));
                }
                if (process)
                    process->deleteLater();
                setBusy(false, QStringLiteral("Jarvis pack authoring finished"));
                refreshStageRail();
                if (buildJarvisPackBtn_)
                    buildJarvisPackBtn_->setEnabled(true);
            });
    jarvisPackProcess_->start(python, {script, QStringLiteral("--request"), requestPath});
    if (!jarvisPackProcess_->waitForStarted(3000)) {
        jarvisPackReadinessLabel_->setText(QStringLiteral("Pack builder failed to start."));
        jarvisPackProcess_->deleteLater();
        jarvisPackProcess_ = nullptr;
        setBusy(false, QStringLiteral("Jarvis pack authoring could not start"));
        buildJarvisPackBtn_->setEnabled(true);
    }
}

void CharacterStudioPage::writeCreateContract(const QString &packDir)
{
    const QString python = QDir(projectRoot_).filePath(QStringLiteral(".venv/Scripts/python.exe"));
    const QString script = QDir(projectRoot_).filePath(QStringLiteral("python/character_create.py"));
    const QString outPath = QDir(currentProjectDir()).filePath(QStringLiteral("character_create.json"));
    QJsonObject request;
    request.insert(QStringLiteral("project"), projectName_);
    request.insert(QStringLiteral("output"), outPath);
    request.insert(QStringLiteral("identity_path"), QStringLiteral("B"));
    if (!packDir.isEmpty())
        request.insert(QStringLiteral("pack_dir"), packDir);
    const QString requestPath = QDir(currentProjectDir()).filePath(QStringLiteral("character_create_request.json"));
    const bool requestWritten = writeJsonAtomically(requestPath, QJsonDocument(request));

    if (requestWritten && QFileInfo(python).isFile() && QFileInfo(script).isFile()) {
        QProcess proc;
        proc.setWorkingDirectory(projectRoot_);
        QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
        env.insert(QStringLiteral("PYTHONNOUSERSITE"), QStringLiteral("1"));
        env.remove(QStringLiteral("PYTHONPATH"));
        proc.setProcessEnvironment(env);
        proc.start(python, {script, QStringLiteral("--request"), requestPath});
        if (proc.waitForFinished(15000) && proc.exitCode() == 0)
            return;
    }

    QJsonObject contract;
    contract.insert(QStringLiteral("contract"), QStringLiteral("spellbound.character-studio-create.v1"));
    contract.insert(QStringLiteral("project"), projectName_);
    contract.insert(QStringLiteral("identity_path"), QStringLiteral("B"));
    contract.insert(QStringLiteral("studio_create_facilitated"), true);
    contract.insert(QStringLiteral("create_complete"), false);
    QSettings bodySettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString bodyGlb = bodySettings.value(QStringLiteral("characterStudio/bodyGlb")).toString().trimmed();
    QJsonObject body;
    body.insert(QStringLiteral("source"), bodyGlb);
    body.insert(QStringLiteral("user_selected"), !bodyGlb.isEmpty());
    contract.insert(QStringLiteral("body"), body);
    contract.insert(QStringLiteral("pack_dir"), packDir);
    contract.insert(QStringLiteral("pixal_identity"), false);
    contract.insert(QStringLiteral("validated"), true);
    contract.insert(QStringLiteral("concept_to_style_complete"), false);
    contract.insert(QStringLiteral("blocked_on"),
                    QJsonArray{QStringLiteral("concept_to_style"), QStringLiteral("stills_to_mesh"),
                               QStringLiteral("hair_create"), QStringLiteral("rig_author"),
                               QStringLiteral("vl_unwired")});
    writeJsonAtomically(outPath, QJsonDocument(contract));
}

void CharacterStudioPage::createFullCharacter()
{
    auto &concept = stages_[static_cast<int>(StageId::Concept)];
    if (concept.status != StageStatus::Done && concept.artifactPath.isEmpty()) {
        setStageNote(StageId::MultiView, QStringLiteral("Lock a concept plate first."));
        refreshStatusBanner();
        return;
    }

    refreshJarvisPackReadiness();
    const QString packDir = QDir(currentProjectDir()).filePath(QStringLiteral("jarvis_pack"));
    const bool packSlotsReady = buildJarvisPackBtn_ && buildJarvisPackBtn_->isEnabled();
    if (packSlotsReady)
        buildJarvisPack();
    writeCreateContract(packDir);

    stages_[static_cast<int>(StageId::MultiView)].status = StageStatus::Done;
    stages_[static_cast<int>(StageId::MultiView)].artifactPath = packDir;
    stages_[static_cast<int>(StageId::MultiView)].note =
        QStringLiteral("Path B create facilitated: plates + JSON create contract. Cook not complete.");
    stages_[static_cast<int>(StageId::Export)].artifactPath =
        QDir(currentProjectDir()).filePath(QStringLiteral("character_create.json"));
    recomputeStageStatuses();
    refreshStageRail();
    refreshActionRow();
    saveProjectState();
    setBusy(false, QStringLiteral("Character create contract written (Path B, cook incomplete)"));
}

void CharacterStudioPage::runMeshPipeline(StageId id)
{
    const int idx = static_cast<int>(id);
    // Import path only. Pixal/TRELLIS is never character identity.
    if (!meshBackendCombo_ || meshBackendCombo_->currentIndex() != 2) {
        stages_[idx].status = StageStatus::Warning;
        setStageNote(id,
                     QStringLiteral("Body mesh is the one you selected. "
                                    "Choose Import existing mesh for a prop, or Create character."));
        refreshStageRail();
        refreshStatusBanner();
        return;
    }
    browseArtifactForStage();
    return;
}

void CharacterStudioPage::exportCharacterPackage()
{
    const QString outDir = QDir(currentProjectDir()).filePath(QStringLiteral("export"));
    QDir().mkpath(outDir);

    QJsonObject manifest;
    manifest.insert(QStringLiteral("project"), projectName_);
    manifest.insert(QStringLiteral("format"),
                    exportFormatCombo_ ? exportFormatCombo_->currentText() : QStringLiteral("JSON create contract (Path B)"));
    QJsonObject arts;
    for (const auto &s : stages_) {
        if (!s.artifactPath.isEmpty())
            arts.insert(s.key, s.artifactPath);
    }
    manifest.insert(QStringLiteral("artifacts"), arts);
    writeCreateContract(QDir(currentProjectDir()).filePath(QStringLiteral("jarvis_pack")));
    const QString createPath = QDir(currentProjectDir()).filePath(QStringLiteral("character_create.json"));
    if (QFileInfo::exists(createPath)) {
        const QString dest = QDir(outDir).filePath(QStringLiteral("character_create.json"));
        QFile::remove(dest);
        QFile::copy(createPath, dest);
    }

    manifest.insert(QStringLiteral("identity_path"), QStringLiteral("B"));
    manifest.insert(QStringLiteral("create_complete"), false);
    manifest.insert(QStringLiteral("engine_notes"),
                    QStringLiteral("Path B: selected body mesh + sliders + character pack. Not TRELLIS identity. Not MikkT/FBX cook."));

    const QString manifestPath = QDir(outDir).filePath(QStringLiteral("character_manifest.json"));
    if (!writeJsonAtomically(manifestPath, QJsonDocument(manifest))) {
        if (actionHint_)
            actionHint_->setText(QStringLiteral("Export failed: could not safely write character_manifest.json"));
        return;
    }

    if (writeLicenseSidecarCheck_ && writeLicenseSidecarCheck_->isChecked()) {
        QJsonObject lic;
        lic.insert(QStringLiteral("note"),
                   QStringLiteral("Record which model produced each component and its license for downstream shipping."));
        lic.insert(QStringLiteral("components"), QJsonArray{
                                                     QJsonObject{{QStringLiteral("stage"), QStringLiteral("identity")},
                                                                 {QStringLiteral("model"), QStringLiteral("user-selected body mesh")},
                                                                 {QStringLiteral("license"), QStringLiteral("engine freeze")}},
                                                     QJsonObject{{QStringLiteral("stage"), QStringLiteral("adjunct_gen3d")},
                                                                 {QStringLiteral("model"), QStringLiteral("TRELLIS / UltraShape — props only")},
                                                                 {QStringLiteral("license"), QStringLiteral("not body identity; UltraShape is Hunyuan Community not Apache")}},
                                                 });
        if (!writeJsonAtomically(QDir(outDir).filePath(QStringLiteral("license_sidecar.json")),
                                 QJsonDocument(lic))) {
            if (actionHint_)
                actionHint_->setText(QStringLiteral("Export failed: could not safely write license_sidecar.json"));
            return;
        }
    }

    // Copy known mesh artifacts into export folder when present.
    for (const auto &s : stages_) {
        if (s.artifactPath.isEmpty())
            continue;
        const QFileInfo fi(s.artifactPath);
        if (!fi.exists())
            continue;
        const QString dest = QDir(outDir).filePath(s.key + QLatin1Char('_') + fi.fileName());
        QFile::remove(dest);
        QFile::copy(s.artifactPath, dest);
    }

    stages_[static_cast<int>(StageId::Export)].status = StageStatus::Done;
    stages_[static_cast<int>(StageId::Export)].artifactPath = outDir;
    stages_[static_cast<int>(StageId::Export)].note = QStringLiteral("Package written");
    if (exportSummary_)
        exportSummary_->setText(QStringLiteral("Exported to %1").arg(outDir));
    recomputeStageStatuses();
    refreshStageRail();
    refreshWorkspace();
    saveProjectState();
    setBusy(false, QStringLiteral("JSON create contract written"));
}

void CharacterStudioPage::browseReferenceImage()
{
    const QString path = QFileDialog::getOpenFileName(
        this, QStringLiteral("Reference image"), projectRoot_,
        QStringLiteral("Images (*.png *.jpg *.jpeg *.webp *.bmp)"));
    if (!path.isEmpty() && referencePathEdit_)
        referencePathEdit_->setText(path);
}

void CharacterStudioPage::browseArtifactForStage()
{
    const QString path = QFileDialog::getOpenFileName(
        this, QStringLiteral("Attach artifact"), currentProjectDir(),
        QStringLiteral("Assets (*.png *.jpg *.jpeg *.webp *.glb *.gltf *.fbx *.obj);;All (*.*)"));
    if (path.isEmpty())
        return;
    auto &s = stages_[currentStage_];
    s.artifactPath = path;
    s.status = StageStatus::Done;
    s.note = QStringLiteral("Attached manually");
    if (currentStage_ == 0 && conceptPreview_) {
        QPixmap px(path);
        if (!px.isNull())
            conceptPreview_->setPixmap(px.scaled(280, 360, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    }
    recomputeStageStatuses();
    refreshStageRail();
    refreshWorkspace();
    saveProjectState();
}

ConceptContentMode CharacterStudioPage::currentContentMode() const
{
    if (!contentModeCombo_)
        return ConceptContentMode::Sfw;
    const QVariant data = contentModeCombo_->currentData();
    if (!data.isValid())
        return ConceptContentMode::Sfw;
    return static_cast<ConceptContentMode>(data.toInt());
}

QJsonObject CharacterStudioPage::buildConceptPayload() const
{
    const auto pack = buildConceptPromptPack(ConceptAssetType::CharacterBody,
                                             currentContentMode(),
                                             ConceptViewMode::HeroFront);
    QString subject = conceptPromptEdit_ ? conceptPromptEdit_->toPlainText().trimmed() : QString();
    const QString style = stylePresetCombo_ ? stylePresetCombo_->currentText() : QString();
    const QString pose = poseCombo_ ? poseCombo_->currentText() : QString();
    if (!subject.isEmpty() && !style.isEmpty())
        subject += QStringLiteral(", %1").arg(style);
    if (!subject.isEmpty() && !pose.isEmpty())
        subject += QStringLiteral(", %1").arg(pose);

    const QString prompt = composeConceptPositivePrompt(subject, pack);
    QString negative = negativePromptEdit_ ? negativePromptEdit_->toPlainText().trimmed() : QString();
    if (negative.isEmpty())
        negative = pack.negativeScaffold;

    int w = conceptDefaultWidth(ConceptViewMode::HeroFront);
    int h = conceptDefaultHeight(ConceptViewMode::HeroFront);
    if (aspectCombo_) {
        if (aspectCombo_->currentIndex() == 1) {
            w = 1024;
            h = 1024;
        } else if (aspectCombo_->currentIndex() == 2) {
            w = 768;
            h = 1344;
        }
    }

    QJsonObject payload;
    // Emphasize selected pose over reference photo when both are present.
    QString finalPrompt = prompt;
    if (referencePathEdit_ && !referencePathEdit_->text().trimmed().isEmpty() && !pose.isEmpty()) {
        finalPrompt = QStringLiteral("follow pose directive closely: %1, %2").arg(pose, prompt);
    }
    payload.insert(QStringLiteral("prompt"), finalPrompt);
    payload.insert(QStringLiteral("negative_prompt"), negative);
    payload.insert(QStringLiteral("width"), w);
    payload.insert(QStringLiteral("height"), h);
    payload.insert(QStringLiteral("steps"), 30);
    payload.insert(QStringLiteral("cfg"), 5.0);
    const int seed = (seedLockCheck_ && seedLockCheck_->isChecked() && seedEdit_)
                         ? seedEdit_->text().toInt()
                         : static_cast<int>(QDateTime::currentMSecsSinceEpoch() & 0x7fffffff);
    payload.insert(QStringLiteral("seed"), seed);
    payload.insert(QStringLiteral("output_prefix"),
                   QStringLiteral("character_%1_concept").arg(projectName_));
    if (!selectedModelPath_.trimmed().isEmpty()) {
        payload.insert(QStringLiteral("model"), selectedModelPath_.trimmed());
        payload.insert(QStringLiteral("model_display"),
                       selectedModelDisplay_.isEmpty() ? QFileInfo(selectedModelPath_).fileName()
                                                       : selectedModelDisplay_);
    }
    QJsonArray loras;
    if (!selectedLoraPath_.trimmed().isEmpty()) {
        QJsonObject l;
        l.insert(QStringLiteral("path"), selectedLoraPath_.trimmed());
        l.insert(QStringLiteral("name"),
                 selectedLoraDisplay_.isEmpty() ? QFileInfo(selectedLoraPath_).fileName()
                                                : selectedLoraDisplay_);
        l.insert(QStringLiteral("weight"), 1.0);
        l.insert(QStringLiteral("enabled"), true);
        loras.append(l);
    }
    // House-style LoRA: optional second adapter when configured + enabled.
    if (houseStyleLoraCheck_ && houseStyleLoraCheck_->isChecked() && !houseLoraPath_.trimmed().isEmpty()) {
        QJsonObject h;
        h.insert(QStringLiteral("path"), houseLoraPath_.trimmed());
        h.insert(QStringLiteral("name"),
                 houseLoraDisplay_.isEmpty() ? QFileInfo(houseLoraPath_).fileName() : houseLoraDisplay_);
        h.insert(QStringLiteral("weight"), 0.85);
        h.insert(QStringLiteral("enabled"), true);
        loras.append(h);
    }
    if (!loras.isEmpty())
        payload.insert(QStringLiteral("loras"), loras);
    if (referencePathEdit_ && !referencePathEdit_->text().trimmed().isEmpty()) {
        payload.insert(QStringLiteral("input_image"), referencePathEdit_->text().trimmed());
        // Higher denoise = freer pose (less photo lock). Default 0.62.
        const double denoise = refDenoiseSpin_ ? refDenoiseSpin_->value() : 0.62;
        payload.insert(QStringLiteral("denoise_strength"), denoise);
        payload.insert(QStringLiteral("strength"), denoise);
        // Soft IP-Adapter-style weight for future worker path; denoise is the live lever.
        payload.insert(QStringLiteral("ipadapter_weight"), qBound(0.15, 1.0 - denoise + 0.15, 0.85));
        payload.insert(QStringLiteral("reference_mode"), QStringLiteral("pose_flexible"));
    }
    return payload;
}

void CharacterStudioPage::refreshHouseLoraLabel()
{
    if (!houseLoraPathLabel_)
        return;
    if (houseLoraPath_.isEmpty()) {
        houseLoraPathLabel_->setText(
            QStringLiteral("Style LoRA: not configured"));
    } else {
        houseLoraPathLabel_->setText(
            QStringLiteral("Style LoRA: %1")
                .arg(houseLoraDisplay_.isEmpty() ? QFileInfo(houseLoraPath_).fileName() : houseLoraDisplay_));
    }
}

void CharacterStudioPage::pickHouseLora()
{
    using namespace spellvision::assets;
    using spellvision::generation::chooseModelsRootPath;
    const QString root = chooseModelsRootPath();
    const QVector<CatalogEntry> entries = scanCatalog(root, QStringLiteral("loras"));
    if (entries.isEmpty()) {
        if (statusBanner_)
            statusBanner_->setText(QStringLiteral("No LoRAs found under models/loras."));
        return;
    }
    CatalogPickerDialog dlg(QStringLiteral("Choose style LoRA"), entries, houseLoraPath_,
                            QStringLiteral("characterStudio/recentHouseLoras"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    houseLoraPath_ = dlg.selectedValue();
    houseLoraDisplay_ = dlg.selectedDisplay();
    if (houseStyleLoraCheck_)
        houseStyleLoraCheck_->setChecked(true);
    QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    s.setValue(QStringLiteral("characterStudio/houseLoraPath"), houseLoraPath_);
    s.setValue(QStringLiteral("characterStudio/houseLoraDisplay"), houseLoraDisplay_);
    s.setValue(QStringLiteral("characterStudio/houseLoraEnabled"), true);
    persistRecentSelection(QStringLiteral("characterStudio/recentHouseLoras"), houseLoraPath_);
    refreshHouseLoraLabel();
}

void CharacterStudioPage::clearHouseLora()
{
    houseLoraPath_.clear();
    houseLoraDisplay_.clear();
    if (houseStyleLoraCheck_)
        houseStyleLoraCheck_->setChecked(false);
    QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    s.remove(QStringLiteral("characterStudio/houseLoraPath"));
    s.remove(QStringLiteral("characterStudio/houseLoraDisplay"));
    s.setValue(QStringLiteral("characterStudio/houseLoraEnabled"), false);
    refreshHouseLoraLabel();
}

void CharacterStudioPage::relayoutConceptPreview()
{
    if (!conceptPreview_)
        return;
    const QString path = conceptPreview_->property("svFullResPath").toString();
    if (path.isEmpty() || !QFileInfo::exists(path))
        return;
    QPixmap px;
    if (!px.load(path))
        return;
    QSize target = conceptPreview_->size();
    if (target.width() < 200 || target.height() < 200)
        return;
    conceptPreview_->setPixmap(px.scaled(target, Qt::KeepAspectRatio, Qt::SmoothTransformation));
}

void CharacterStudioPage::refreshModelStackLabels()
{
    if (modelValueLabel_) {
        modelValueLabel_->setText(selectedModelPath_.isEmpty()
                                      ? QStringLiteral("No model selected — required to generate")
                                      : (selectedModelDisplay_.isEmpty()
                                             ? QFileInfo(selectedModelPath_).fileName()
                                             : selectedModelDisplay_));
    }
    if (licenseNoteLabel_) {
        const QString badge = spellvision::assets::familyLicenseBadgeText(QString(), selectedModelPath_);
        licenseNoteLabel_->setVisible(!badge.isEmpty());
        licenseNoteLabel_->setText(badge.isEmpty() ? QString() : badge);
    }
    if (loraValueLabel_) {
        loraValueLabel_->setText(selectedLoraPath_.isEmpty()
                                     ? QStringLiteral("LoRA: None")
                                     : QStringLiteral("LoRA: %1").arg(
                                           selectedLoraDisplay_.isEmpty()
                                               ? QFileInfo(selectedLoraPath_).fileName()
                                               : selectedLoraDisplay_));
    }
}

void CharacterStudioPage::pickModel()
{
    using namespace spellvision::assets;
    using spellvision::generation::chooseModelsRootPath;
    const QString root = chooseModelsRootPath();
    const QVector<CatalogEntry> entries = scanImageModelCatalog(root);
    if (entries.isEmpty()) {
        if (statusBanner_)
            statusBanner_->setText(QStringLiteral("No checkpoints found under models root."));
        return;
    }
    CatalogPickerDialog dlg(QStringLiteral("Choose checkpoint"), entries, selectedModelPath_,
                            QStringLiteral("characterStudio/recentModels"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    selectedModelPath_ = dlg.selectedValue();
    selectedModelDisplay_ = dlg.selectedDisplay();
    persistRecentSelection(QStringLiteral("characterStudio/recentModels"), selectedModelPath_);
    refreshModelStackLabels();
    saveProjectState();
}

void CharacterStudioPage::pickLora()
{
    using namespace spellvision::assets;
    using spellvision::generation::chooseModelsRootPath;
    const QString root = chooseModelsRootPath();
    const QVector<CatalogEntry> entries = scanCatalog(root, QStringLiteral("loras"));
    if (entries.isEmpty()) {
        if (statusBanner_)
            statusBanner_->setText(QStringLiteral("No LoRAs found under models/loras."));
        return;
    }
    CatalogPickerDialog dlg(QStringLiteral("Choose LoRA"), entries, selectedLoraPath_,
                            QStringLiteral("characterStudio/recentLoras"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    selectedLoraPath_ = dlg.selectedValue();
    selectedLoraDisplay_ = dlg.selectedDisplay();
    persistRecentSelection(QStringLiteral("characterStudio/recentLoras"), selectedLoraPath_);
    refreshModelStackLabels();
    saveProjectState();
}

void CharacterStudioPage::clearLora()
{
    selectedLoraPath_.clear();
    selectedLoraDisplay_.clear();
    refreshModelStackLabels();
    saveProjectState();
}

QString CharacterStudioPage::projectsDir() const
{
    const QString root = projectRoot_.isEmpty()
                             ? QDir::currentPath()
                             : projectRoot_;
    return QDir(root).filePath(QStringLiteral("runtime/characters"));
}

QString CharacterStudioPage::currentProjectDir() const
{
    const QString dir = QDir(projectsDir()).filePath(projectName_);
    QDir().mkpath(dir);
    return dir;
}

void CharacterStudioPage::saveProjectState()
{
    QDir().mkpath(currentProjectDir());
    QJsonObject root;
    root.insert(QStringLiteral("name"), projectName_);
    root.insert(QStringLiteral("prompt"), conceptPromptEdit_ ? conceptPromptEdit_->toPlainText() : QString());
    root.insert(QStringLiteral("negative"), negativePromptEdit_ ? negativePromptEdit_->toPlainText() : QString());
    root.insert(QStringLiteral("content_mode"), static_cast<int>(currentContentMode()));
    root.insert(QStringLiteral("reference"), referencePathEdit_ ? referencePathEdit_->text() : QString());
    root.insert(QStringLiteral("garments"), garmentListEdit_ ? garmentListEdit_->toPlainText() : QString());
    root.insert(QStringLiteral("last_clothes_only_dest"), lastClothesOnlyDest_);
    root.insert(QStringLiteral("model"), selectedModelPath_);
    root.insert(QStringLiteral("model_display"), selectedModelDisplay_);
    root.insert(QStringLiteral("lora"), selectedLoraPath_);
    root.insert(QStringLiteral("lora_display"), selectedLoraDisplay_);
    QJsonObject jarvisPack;
    const auto savePackField = [&jarvisPack](const QString &key, QLineEdit *edit) {
        jarvisPack.insert(key, edit ? edit->text().trimmed() : QString());
    };
    savePackField(QStringLiteral("face_front"), packFaceFrontEdit_);
    savePackField(QStringLiteral("face_3q"), packFace3qEdit_);
    savePackField(QStringLiteral("clothes_front"), packClothesFrontEdit_);
    savePackField(QStringLiteral("clothes_side"), packClothesSideEdit_);
    savePackField(QStringLiteral("clothes_back"), packClothesBackEdit_);
    savePackField(QStringLiteral("clothes_3q"), packClothes3qEdit_);
    savePackField(QStringLiteral("pieces"), packPiecesEdit_);
    savePackField(QStringLiteral("palette"), packPaletteEdit_);
    root.insert(QStringLiteral("jarvis_pack"), jarvisPack);
    QJsonArray arr;
    for (const auto &s : stages_) {
        QJsonObject o;
        o.insert(QStringLiteral("key"), s.key);
        o.insert(QStringLiteral("status"), static_cast<int>(s.status));
        o.insert(QStringLiteral("artifact"), s.artifactPath);
        o.insert(QStringLiteral("note"), s.note);
        arr.append(o);
    }
    root.insert(QStringLiteral("stages"), arr);
    const bool saved = writeJsonAtomically(
        QDir(currentProjectDir()).filePath(QStringLiteral("project.json")), QJsonDocument(root));
    if (actionHint_)
        actionHint_->setText(saved
                                 ? QStringLiteral("Saved %1").arg(currentProjectDir())
                                 : QStringLiteral("Save failed: project.json was not replaced"));
}

void CharacterStudioPage::loadProjectState()
{
    const QString path = QDir(currentProjectDir()).filePath(QStringLiteral("project.json"));
    QFile f(path);
    if (!f.exists() || !f.open(QIODevice::ReadOnly))
        return;
    const auto doc = QJsonDocument::fromJson(f.readAll());
    f.close();
    if (!doc.isObject())
        return;
    const QJsonObject root = doc.object();
    if (conceptPromptEdit_)
        conceptPromptEdit_->setPlainText(root.value(QStringLiteral("prompt")).toString());
    if (negativePromptEdit_)
        negativePromptEdit_->setPlainText(root.value(QStringLiteral("negative")).toString());
    if (contentModeCombo_ && root.contains(QStringLiteral("content_mode"))) {
        const int mode = root.value(QStringLiteral("content_mode")).toInt(0);
        const int idx = contentModeCombo_->findData(mode);
        if (idx >= 0)
            contentModeCombo_->setCurrentIndex(idx);
    }
    if (referencePathEdit_)
        referencePathEdit_->setText(root.value(QStringLiteral("reference")).toString());
    if (garmentListEdit_)
        garmentListEdit_->setPlainText(root.value(QStringLiteral("garments")).toString());
    lastClothesOnlyDest_ = root.value(QStringLiteral("last_clothes_only_dest")).toString();
    selectedModelPath_ = root.value(QStringLiteral("model")).toString();
    selectedModelDisplay_ = root.value(QStringLiteral("model_display")).toString();
    selectedLoraPath_ = root.value(QStringLiteral("lora")).toString();
    selectedLoraDisplay_ = root.value(QStringLiteral("lora_display")).toString();
    refreshModelStackLabels();
    const QJsonObject jarvisPack = root.value(QStringLiteral("jarvis_pack")).toObject();
    const auto loadPackField = [&jarvisPack](const QString &key, QLineEdit *edit) {
        if (edit)
            edit->setText(jarvisPack.value(key).toString());
    };
    loadPackField(QStringLiteral("face_front"), packFaceFrontEdit_);
    loadPackField(QStringLiteral("face_3q"), packFace3qEdit_);
    loadPackField(QStringLiteral("clothes_front"), packClothesFrontEdit_);
    loadPackField(QStringLiteral("clothes_side"), packClothesSideEdit_);
    loadPackField(QStringLiteral("clothes_back"), packClothesBackEdit_);
    loadPackField(QStringLiteral("clothes_3q"), packClothes3qEdit_);
    loadPackField(QStringLiteral("pieces"), packPiecesEdit_);
    loadPackField(QStringLiteral("palette"), packPaletteEdit_);
    refreshJarvisPackReadiness();
    const QJsonArray arr = root.value(QStringLiteral("stages")).toArray();
    for (const QJsonValue &v : arr) {
        const QJsonObject o = v.toObject();
        const QString key = o.value(QStringLiteral("key")).toString();
        for (auto &s : stages_) {
            if (s.key != key)
                continue;
            s.status = static_cast<StageStatus>(o.value(QStringLiteral("status")).toInt());
            s.artifactPath = o.value(QStringLiteral("artifact")).toString();
            s.note = o.value(QStringLiteral("note")).toString();
            if (s.id == StageId::Concept && !s.artifactPath.isEmpty() && conceptPreview_) {
                QPixmap px(s.artifactPath);
                if (!px.isNull())
                    conceptPreview_->setPixmap(px.scaled(280, 360, Qt::KeepAspectRatio, Qt::SmoothTransformation));
                if (conceptPreviewCaption_)
                    conceptPreviewCaption_->setText(QFileInfo(s.artifactPath).fileName());
            }
        }
    }
    recomputeStageStatuses();
    refreshStageRail();
}

void CharacterStudioPage::probeExternalTools()
{
    spikeRoot_.clear();
    pixalPython_.clear();
    blenderPath_.clear();
    hasPixalEnv_ = false;
    hasUltraShape_ = false;
    hasBlender_ = false;
}

void CharacterStudioPage::setStageNote(StageId id, const QString &note)
{
    stages_[static_cast<int>(id)].note = note;
}

QString CharacterStudioPage::stageStatusLabel(StageStatus s) const
{
    switch (s) {
    case StageStatus::Locked: return QStringLiteral("locked");
    case StageStatus::Ready: return QStringLiteral("ready");
    case StageStatus::Running: return QStringLiteral("running");
    case StageStatus::Done: return QStringLiteral("done");
    case StageStatus::Warning: return QStringLiteral("warn");
    case StageStatus::Blocked: return QStringLiteral("blocked");
    }
    return QStringLiteral("?");
}

QString CharacterStudioPage::stageStatusCss(StageStatus) const
{
    return {};
}

void CharacterStudioPage::applyTheme()
{
    const auto &theme = ThemeManager::instance();
    using C = ThemeManager::Color;
    // Use @tokens@ — QString::arg only supports %1..%9 reliably; %10+ becomes "%1"+"0".
    QString css = QStringLiteral(
        "#CharacterStudioPage { background: transparent; }"
        "QLabel#CharStudioEyebrow { @micro@ letter-spacing: 0.14em; color: @accent@; }"
        "QLabel#CharStudioHeroTitle { @display@ color: @textHi@; }"
        "QLabel#CharStudioHeroSubtitle { @body@ color: @textMid@; }"
        "QLabel#CharStudioHeroMeta { @label@ color: @accentHover@; }"
        "QLabel#CharStudioSectionTitle { @heading@ color: @textHi@; }"
        "QLabel#CharStudioFieldLabel { @label@ color: @textMid@; }"
        "QLabel#CharStudioMuted { @body@ color: @textMid@; }"
        "QLabel#CharStudioStatusBanner {"
        " @body@ color: @textMid@; background: @glassFill@; border: 1px solid @border@;"
        " border-radius: 10px; padding: 8px 10px; }"
        "QLabel#CharStudioPreview {"
        " background: @surface0@; border: 1px solid @border@; border-radius: 12px; color: @textMid@; }"
        "QListWidget#CharStudioStageList {"
        " background: transparent; border: none; outline: none; color: @textHi@; @body@ }"
        "QListWidget#CharStudioStageList::item {"
        " background: @surface1@; border: 1px solid @border@; border-radius: 10px;"
        " padding: 8px; margin: 2px 0; }"
        "QListWidget#CharStudioStageList::item:selected {"
        " background: @accentSubtle@; border: 1px solid @accent@; }"
        "QListWidget#CharStudioStageList::item:hover { border-color: @accentHover@; }"
        "QTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {"
        " background: @surface0@; color: @textHi@; border: 1px solid @border@; border-radius: 8px;"
        " padding: 6px 8px; @body@ selection-background-color: @accent@; }"
        "QTextEdit:focus, QLineEdit:focus, QComboBox:focus { border-color: @accent@; }"
        "QPushButton#CharStudioPrimaryBtn {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 @accent@, stop:1 @accentSecondary@);"
        " color: white; border: 1px solid @accentHover@; border-radius: 10px;"
        " padding: 8px 16px; @label@ }"
        "QPushButton#CharStudioPrimaryBtn:hover { background: @accentHover@; }"
        "QPushButton#CharStudioPrimaryBtn:disabled { background: @surface2@; color: @textDisabled@; border-color: @border@; }"
        "QPushButton#CharStudioSecondaryBtn {"
        " background: @surface1@; color: @textHi@; border: 1px solid @border@; border-radius: 10px;"
        " padding: 8px 14px; @label@ }"
        "QPushButton#CharStudioSecondaryBtn:hover { border-color: @accent@; color: @accent@; }"
        "QProgressBar#CharStudioProgress {"
        " background: @surface0@; border: none; border-radius: 3px; }"
        "QProgressBar#CharStudioProgress::chunk {"
        " background: @accent@; border-radius: 3px; }"
        "QCheckBox { color: @textMid@; @body@ spacing: 8px; }"
        "QScrollArea { background: transparent; border: none; }"
        "QLabel { color: @textMid@; }");

    const auto put = [&](const char *token, const QString &value) {
        css.replace(QLatin1String(token), value);
    };
    put("@micro@", theme.fontCss(ThemeManager::Type::Micro));
    put("@display@", theme.fontCss(ThemeManager::Type::Display));
    put("@heading@", theme.fontCss(ThemeManager::Type::Heading));
    put("@body@", theme.fontCss(ThemeManager::Type::Body));
    put("@label@", theme.fontCss(ThemeManager::Type::Label));
    put("@accent@", theme.css(C::Accent));
    put("@accentHover@", theme.css(C::AccentHover));
    put("@accentSecondary@", theme.css(C::AccentSecondary));
    put("@accentSubtle@", theme.css(C::AccentSubtle));
    put("@textHi@", theme.css(C::TextHi));
    put("@textMid@", theme.css(C::TextMid));
    put("@textDisabled@", theme.css(C::TextDisabled));
    put("@border@", theme.css(C::Border));
    put("@surface0@", theme.css(C::Surface0));
    put("@surface1@", theme.css(C::Surface1));
    put("@surface2@", theme.css(C::Surface2));
    put("@glassFill@", theme.css(C::GlassFill));

    setStyleSheet(css);
    if (heroPanel_)
        heroPanel_->update();
}

} // namespace spellvision::studios
