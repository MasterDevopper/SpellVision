#include "studios/ComicStudioPage.h"

#include "DashboardGlassPanel.h"
#include "DurableJson.h"
#include "ThemeManager.h"
#include "assets/AssetCatalogScanner.h"
#include "assets/CatalogPickerDialog.h"
#include "generation/CockpitWidgetKit.h"
#include "generation/OutputPathHelpers.h"

#include <QCheckBox>
#include <QComboBox>
#include <QDateTime>
#include <QDir>
#include <QDoubleSpinBox>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QIcon>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QPainter>
#include <QPixmap>
#include <QProgressBar>
#include <QPushButton>
#include <QResizeEvent>
#include <QScrollArea>
#include <QSpinBox>
#include <QSplitter>
#include <QStackedWidget>
#include <QTextEdit>
#include <QVBoxLayout>

namespace spellvision::studios
{
namespace
{

QLabel *eyebrow(const QString &text, QWidget *parent)
{
    auto *l = new QLabel(text, parent);
    l->setObjectName(QStringLiteral("ComicEyebrow"));
    return l;
}

QLabel *fieldLabel(const QString &text, QWidget *parent)
{
    auto *l = new QLabel(text, parent);
    l->setObjectName(QStringLiteral("ComicFieldLabel"));
    return l;
}

struct LayoutSpec
{
    QString id;
    QString label;
    int cols = 2;
    int rows = 2;
    int panels = 4;
};

const QVector<LayoutSpec> &layouts()
{
    static const QVector<LayoutSpec> k = {
        {QStringLiteral("grid_2x2"), QStringLiteral("2×2 grid"), 2, 2, 4},
        {QStringLiteral("strip_3"), QStringLiteral("3-panel strip"), 3, 1, 3},
        {QStringLiteral("manga_6"), QStringLiteral("Manga 6-up"), 3, 2, 6},
        {QStringLiteral("splash_plus"), QStringLiteral("Splash + 3"), 2, 2, 4},
        {QStringLiteral("widescreen_4"), QStringLiteral("Widescreen 4"), 4, 1, 4},
        {QStringLiteral("nine_grid"), QStringLiteral("9-panel grid"), 3, 3, 9},
    };
    return k;
}

LayoutSpec findLayout(const QString &id)
{
    for (const auto &l : layouts())
        if (l.id == id)
            return l;
    return layouts().first();
}

} // namespace

ComicStudioPage::ComicStudioPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("ComicStudioPage"));
    applyLayoutPreset(QStringLiteral("grid_2x2"));
    buildUi();
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });
    refreshPanelInspector();
    refreshCanvas();
    refreshHeroMeta();
    // Initial reflow for default restore size (resizeEvent may not fire until first user resize).
    reflowForWidth(width() > 0 ? width() : 1280);
}

void ComicStudioPage::setProjectRoot(const QString &root)
{
    projectRoot_ = root;
    loadProject();
}

void ComicStudioPage::updateDisclosure(bool advanced)
{
    advanced_ = advanced;
    if (advancedBlock_)
        advancedBlock_->setVisible(advanced_);
}

void ComicStudioPage::setBusy(bool busy, const QString &message)
{
    busy_ = busy;
    if (progress_) {
        progress_->setVisible(busy);
        progress_->setRange(0, 0);
    }
    if (statusBanner_ && !message.isEmpty())
        statusBanner_->setText(message);
    if (genPanelBtn_)
        genPanelBtn_->setEnabled(!busy);
    if (genAllBtn_)
        genAllBtn_->setEnabled(!busy);
}

void ComicStudioPage::setPanelResult(int panelIndex, const QString &imagePath)
{
    if (panelIndex < 0 || panelIndex >= panels_.size()) {
        // If unknown, fill first incomplete.
        for (int i = 0; i < panels_.size(); ++i) {
            if (!panels_[i].done) {
                panelIndex = i;
                break;
            }
        }
    }
    if (panelIndex < 0 || panelIndex >= panels_.size())
        return;

    panels_[panelIndex].imagePath = imagePath;
    panels_[panelIndex].done = QFileInfo::exists(imagePath);
    rebuildPanelList();
    refreshCanvas();
    refreshPanelInspector();
    refreshHeroMeta();
    saveProject();
    setBusy(false, QStringLiteral("Panel %1 ready").arg(panelIndex + 1));
}

void ComicStudioPage::buildUi()
{
    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Card),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    root->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    root->addWidget(buildHero());

    mainSplit_ = new QSplitter(Qt::Horizontal, this);
    mainSplit_->setChildrenCollapsible(false);
    mainSplit_->setHandleWidth(8);
    leftColumn_ = buildLeftColumn();
    rightColumn_ = buildRightInspector();
    mainSplit_->addWidget(leftColumn_);
    mainSplit_->addWidget(buildCenterCanvas());
    mainSplit_->addWidget(rightColumn_);
    mainSplit_->setStretchFactor(0, 0);
    mainSplit_->setStretchFactor(1, 1);
    mainSplit_->setStretchFactor(2, 0);
    mainSplit_->setSizes({280, 520, 280});
    root->addWidget(mainSplit_, 1);
    root->addWidget(buildActionRow());
}

void ComicStudioPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    reflowForWidth(event ? event->size().width() : width());
}

void ComicStudioPage::reflowForWidth(int width)
{
    if (!mainSplit_ || !leftColumn_ || !rightColumn_)
        return;

    // Half-screen / restore: keep both rails usable without crushing the canvas.
    // Side columns shrink and scroll rather than vanishing.
    int leftBudget = 280;
    int rightBudget = 280;
    if (width < 1100) {
        leftBudget = 240;
        rightBudget = 240;
    } else if (width < 1400) {
        leftBudget = 260;
        rightBudget = 260;
    } else {
        leftBudget = 300;
        rightBudget = 300;
    }

    leftColumn_->setMinimumWidth(qMax(220, leftBudget - 20));
    leftColumn_->setMaximumWidth(leftBudget + 40);
    rightColumn_->setMinimumWidth(qMax(220, rightBudget - 20));
    rightColumn_->setMaximumWidth(rightBudget + 40);

    // Prefer canvas stretch; re-balance only when the window is truly narrow so we don't
    // fight user-dragged splitter handles on every resize at full screen.
    if (width < 1280) {
        const int canvas = qMax(280, width - leftBudget - rightBudget - 80);
        mainSplit_->setSizes({leftBudget, canvas, rightBudget});
    }
}

QWidget *ComicStudioPage::buildHero()
{
    heroPanel_ = new DashboardGlassPanel(this);
    heroPanel_->setVariant(DashboardGlassPanel::Variant::Hero);
    heroPanel_->setCornerRadius(16);
    heroPanel_->setGlowStrength(1.0);

    auto *lay = new QVBoxLayout(heroPanel_);
    lay->setContentsMargins(20, 14, 20, 14);
    lay->setSpacing(6);

    auto *top = new QHBoxLayout;
    auto *titles = new QVBoxLayout;
    titles->setSpacing(2);
    titles->addWidget(eyebrow(QStringLiteral("CREATE  ·  COMIC STUDIO"), heroPanel_));
    heroTitle_ = new QLabel(QStringLiteral("Comic Studio"), heroPanel_);
    heroTitle_->setObjectName(QStringLiteral("ComicHeroTitle"));
    heroSubtitle_ = new QLabel(
        QStringLiteral("Script → panel grid → style-locked generations → page composite. "
                       "Keep character identity across beats."),
        heroPanel_);
    heroSubtitle_->setObjectName(QStringLiteral("ComicHeroSubtitle"));
    heroSubtitle_->setWordWrap(true);
    titles->addWidget(heroTitle_);
    titles->addWidget(heroSubtitle_);
    top->addLayout(titles, 1);

    auto *meta = new QVBoxLayout;
    meta->setAlignment(Qt::AlignRight | Qt::AlignTop);
    heroMeta_ = new QLabel(QStringLiteral("4 panels"), heroPanel_);
    heroMeta_->setObjectName(QStringLiteral("ComicHeroMeta"));
    heroMeta_->setAlignment(Qt::AlignRight);
    progress_ = new QProgressBar(heroPanel_);
    progress_->setObjectName(QStringLiteral("ComicProgress"));
    progress_->setFixedWidth(150);
    progress_->setFixedHeight(6);
    progress_->setTextVisible(false);
    progress_->setVisible(false);
    meta->addWidget(heroMeta_);
    meta->addWidget(progress_, 0, Qt::AlignRight);
    top->addLayout(meta);
    lay->addLayout(top);

    statusBanner_ = new QLabel(
        QStringLiteral("Write a short script, pick a layout, then generate panels. Character lock keeps faces consistent."),
        heroPanel_);
    statusBanner_->setObjectName(QStringLiteral("ComicStatusBanner"));
    statusBanner_->setWordWrap(true);
    lay->addWidget(statusBanner_);
    return heroPanel_;
}

QWidget *ComicStudioPage::buildLeftColumn()
{
    auto *panel = new DashboardGlassPanel(this);
    panel->setVariant(DashboardGlassPanel::Variant::Raised);
    panel->setCornerRadius(16);
    panel->setMinimumWidth(220);
    panel->setMaximumWidth(360);
    panel->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    // Scroll so Advanced Sampling stays reachable at half-height / restore sizes.
    auto *scroll = new QScrollArea(panel);
    scroll->setObjectName(QStringLiteral("ComicSideScroll"));
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    auto *body = new QWidget(scroll);
    body->setObjectName(QStringLiteral("ComicLeftBody"));
    auto *lay = new QVBoxLayout(body);
    lay->setContentsMargins(14, 14, 14, 14);
    lay->setSpacing(8);

    lay->addWidget(eyebrow(QStringLiteral("PAGE"), body));
    auto *sec = new QLabel(QStringLiteral("Script & layout"), body);
    sec->setObjectName(QStringLiteral("ComicSectionTitle"));
    lay->addWidget(sec);

    lay->addWidget(fieldLabel(QStringLiteral("Title"), body));
    titleEdit_ = new QLineEdit(QStringLiteral("Untitled Page"), body);
    lay->addWidget(titleEdit_);

    auto *row = new QHBoxLayout;
    layoutCombo_ = new QComboBox(body);
    for (const auto &l : layouts())
        layoutCombo_->addItem(l.label, l.id);
    connect(layoutCombo_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this](int) {
        applyLayoutPreset(layoutCombo_->currentData().toString());
    });
    styleCombo_ = new QComboBox(body);
    styleCombo_->addItems({
        QStringLiteral("Cinematic realist"),
        QStringLiteral("Franco-Belgian ligne claire"),
        QStringLiteral("Modern manga"),
        QStringLiteral("Noir ink"),
        QStringLiteral("Painterly graphic novel"),
        QStringLiteral("Western superhero")
    });
    row->addWidget(layoutCombo_, 1);
    row->addWidget(styleCombo_, 1);
    lay->addLayout(row);

    aspectCombo_ = new QComboBox(body);
    aspectCombo_->addItems({
        QStringLiteral("Panel 832×1216 (portrait)"),
        QStringLiteral("Panel 1024×1024 (square)"),
        QStringLiteral("Panel 1216×832 (landscape)")
    });
    lay->addWidget(aspectCombo_);

    lay->addWidget(fieldLabel(QStringLiteral("Model stack"), body));
    modelValueLabel_ = new QLabel(QStringLiteral("No model selected — required to generate"), body);
    modelValueLabel_->setObjectName(QStringLiteral("ComicMuted"));
    modelValueLabel_->setWordWrap(true);
    lay->addWidget(modelValueLabel_);
    auto *modelRow = new QHBoxLayout;
    pickModelBtn_ = new QPushButton(QStringLiteral("Choose model…"), body);
    pickModelBtn_->setObjectName(QStringLiteral("ComicSecondaryBtn"));
    connect(pickModelBtn_, &QPushButton::clicked, this, &ComicStudioPage::pickModel);
    modelRow->addWidget(pickModelBtn_, 1);
    lay->addLayout(modelRow);
    loraValueLabel_ = new QLabel(QStringLiteral("LoRA: None"), body);
    loraValueLabel_->setObjectName(QStringLiteral("ComicMuted"));
    loraValueLabel_->setWordWrap(true);
    lay->addWidget(loraValueLabel_);
    auto *loraRow = new QHBoxLayout;
    pickLoraBtn_ = new QPushButton(QStringLiteral("Add LoRA…"), body);
    pickLoraBtn_->setObjectName(QStringLiteral("ComicSecondaryBtn"));
    clearLoraBtn_ = new QPushButton(QStringLiteral("Clear"), body);
    connect(pickLoraBtn_, &QPushButton::clicked, this, &ComicStudioPage::pickLora);
    connect(clearLoraBtn_, &QPushButton::clicked, this, &ComicStudioPage::clearLora);
    loraRow->addWidget(pickLoraBtn_, 1);
    loraRow->addWidget(clearLoraBtn_, 0);
    lay->addLayout(loraRow);

    lay->addWidget(fieldLabel(QStringLiteral("Page script / beats"), body));
    scriptEdit_ = new QTextEdit(body);
    scriptEdit_->setPlaceholderText(
        QStringLiteral("1. Wide establishing — rain on neon alley\n"
                       "2. Medium — hero under streetlamp\n"
                       "3. Close — eyes narrow\n"
                       "4. Action — cloak flares as they leap"));
    scriptEdit_->setMinimumHeight(80);
    scriptEdit_->setMaximumHeight(140);
    lay->addWidget(scriptEdit_);

    autoScriptBtn_ = new QPushButton(QStringLiteral("Split script → panels"), body);
    autoScriptBtn_->setObjectName(QStringLiteral("ComicSecondaryBtn"));
    connect(autoScriptBtn_, &QPushButton::clicked, this, &ComicStudioPage::autoFillPromptsFromScript);
    lay->addWidget(autoScriptBtn_);

    lay->addWidget(fieldLabel(QStringLiteral("Global style scaffold"), body));
    globalStyleEdit_ = new QTextEdit(body);
    globalStyleEdit_->setMinimumHeight(48);
    globalStyleEdit_->setMaximumHeight(80);
    globalStyleEdit_->setPlainText(
        QStringLiteral("cohesive comic page, consistent character design, clean inking, "
                       "dramatic lighting, professional sequential art"));
    lay->addWidget(globalStyleEdit_);

    keepCharacterCheck_ = new QCheckBox(QStringLiteral("Lock character identity"), body);
    keepCharacterCheck_->setChecked(true);
    lay->addWidget(keepCharacterCheck_);
    characterLockEdit_ = new QLineEdit(body);
    characterLockEdit_->setPlaceholderText(QStringLiteral("same woman, silver undercut, scar on left brow…"));
    lay->addWidget(characterLockEdit_);

    panelCountSpin_ = new QSpinBox(body);
    panelCountSpin_->setRange(1, 12);
    panelCountSpin_->setValue(panels_.size());
    connect(panelCountSpin_, QOverload<int>::of(&QSpinBox::valueChanged), this, [this](int n) {
        while (panels_.size() < n) {
            ComicPanel p;
            p.index = panels_.size();
            p.title = QStringLiteral("Panel %1").arg(p.index + 1);
            p.camera = QStringLiteral("medium");
            panels_.push_back(p);
        }
        while (panels_.size() > n)
            panels_.pop_back();
        rebuildPanelList();
        refreshCanvas();
        refreshHeroMeta();
    });
    lay->addWidget(fieldLabel(QStringLiteral("Panel count"), body));
    lay->addWidget(panelCountSpin_);

    advancedBlock_ = new QWidget(body);
    auto *adv = new QVBoxLayout(advancedBlock_);
    adv->setContentsMargins(0, 6, 0, 0);
    adv->setSpacing(8);
    adv->addWidget(eyebrow(QStringLiteral("ADVANCED SAMPLING"), advancedBlock_));
    samplerHintCombo_ = new QComboBox(advancedBlock_);
    samplerHintCombo_->addItem(QStringLiteral("euler"), QStringLiteral("euler"));
    samplerHintCombo_->addItem(QStringLiteral("dpmpp_2m"), QStringLiteral("dpmpp_2m"));
    samplerHintCombo_->addItem(QStringLiteral("uni_pc"), QStringLiteral("uni_pc"));
    stepsSpin_ = new QSpinBox(advancedBlock_);
    stepsSpin_->setRange(4, 80);
    stepsSpin_->setValue(28);
    cfgSpin_ = new QDoubleSpinBox(advancedBlock_);
    cfgSpin_->setRange(1.0, 15.0);
    cfgSpin_->setSingleStep(0.5);
    cfgSpin_->setValue(5.0);
    randomSeedCheck_ = new QCheckBox(QStringLiteral("Random seed"), advancedBlock_);
    randomSeedCheck_->setChecked(true);
    seedEdit_ = new QLineEdit(QStringLiteral("0"), advancedBlock_);
    widthSpin_ = new QSpinBox(advancedBlock_);
    widthSpin_->setRange(512, 2048);
    widthSpin_->setSingleStep(64);
    widthSpin_->setValue(832);
    heightSpin_ = new QSpinBox(advancedBlock_);
    heightSpin_->setRange(512, 2048);
    heightSpin_->setSingleStep(64);
    heightSpin_->setValue(1216);

    auto *advHost = advancedBlock_;
    auto addStacked = [adv, advHost](const QString &label, QWidget *field) {
        auto *lab = new QLabel(label, advHost);
        lab->setObjectName(QStringLiteral("ComicFieldLabel"));
        field->setMinimumWidth(0);
        field->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        adv->addWidget(lab);
        adv->addWidget(field);
    };
    addStacked(QStringLiteral("Sampler"), samplerHintCombo_);
    addStacked(QStringLiteral("Steps"), stepsSpin_);
    addStacked(QStringLiteral("CFG"), cfgSpin_);
    addStacked(QStringLiteral("Seed"), seedEdit_);
    addStacked(QStringLiteral("Width"), widthSpin_);
    addStacked(QStringLiteral("Height"), heightSpin_);
    adv->addWidget(randomSeedCheck_);
    advancedBlock_->setVisible(false);
    lay->addWidget(advancedBlock_);
    lay->addStretch(1);

    scroll->setWidget(body);

    auto *panelLay = new QVBoxLayout(panel);
    panelLay->setContentsMargins(0, 0, 0, 0);
    panelLay->setSpacing(0);
    panelLay->addWidget(scroll, 1);
    return panel;
}

QWidget *ComicStudioPage::buildCenterCanvas()
{
    auto *panel = new DashboardGlassPanel(this);
    panel->setVariant(DashboardGlassPanel::Variant::Standard);
    panel->setCornerRadius(16);

    auto *lay = new QVBoxLayout(panel);
    lay->setContentsMargins(14, 14, 14, 14);
    lay->setSpacing(8);
    lay->addWidget(eyebrow(QStringLiteral("PAGE CANVAS"), panel));
    auto *title = new QLabel(QStringLiteral("Panel board"), panel);
    title->setObjectName(QStringLiteral("ComicSectionTitle"));
    lay->addWidget(title);

    canvasHost_ = new QWidget(panel);
    canvasHost_->setObjectName(QStringLiteral("ComicCanvasHost"));
    auto *grid = new QGridLayout(canvasHost_);
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setSpacing(8);
    lay->addWidget(canvasHost_, 1);

    pagePreviewCaption_ = new QLabel(QStringLiteral("Click a panel plate to inspect · double-click generates"), panel);
    pagePreviewCaption_->setObjectName(QStringLiteral("ComicMuted"));
    lay->addWidget(pagePreviewCaption_);
    return panel;
}

QWidget *ComicStudioPage::buildRightInspector()
{
    auto *panel = new DashboardGlassPanel(this);
    panel->setVariant(DashboardGlassPanel::Variant::Raised);
    panel->setCornerRadius(16);
    panel->setMinimumWidth(220);
    panel->setMaximumWidth(380);
    panel->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    auto *scroll = new QScrollArea(panel);
    scroll->setObjectName(QStringLiteral("ComicSideScroll"));
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);

    auto *body = new QWidget(scroll);
    auto *lay = new QVBoxLayout(body);
    lay->setContentsMargins(14, 14, 14, 14);
    lay->setSpacing(8);

    lay->addWidget(eyebrow(QStringLiteral("PANELS"), body));
    auto *sec = new QLabel(QStringLiteral("Beat inspector"), body);
    sec->setObjectName(QStringLiteral("ComicSectionTitle"));
    lay->addWidget(sec);

    panelList_ = new QListWidget(body);
    panelList_->setObjectName(QStringLiteral("ComicPanelList"));
    panelList_->setMinimumHeight(80);
    panelList_->setMaximumHeight(140);
    connect(panelList_, &QListWidget::currentRowChanged, this, &ComicStudioPage::selectPanel);
    lay->addWidget(panelList_);

    lay->addWidget(fieldLabel(QStringLiteral("Title"), body));
    panelTitleEdit_ = new QLineEdit(body);
    connect(panelTitleEdit_, &QLineEdit::editingFinished, this, &ComicStudioPage::syncPanelFromInspector);
    lay->addWidget(panelTitleEdit_);

    lay->addWidget(fieldLabel(QStringLiteral("Beat"), body));
    panelBeatEdit_ = new QTextEdit(body);
    panelBeatEdit_->setMinimumHeight(40);
    panelBeatEdit_->setMaximumHeight(64);
    lay->addWidget(panelBeatEdit_);

    lay->addWidget(fieldLabel(QStringLiteral("Generation prompt"), body));
    panelPromptEdit_ = new QTextEdit(body);
    panelPromptEdit_->setMinimumHeight(60);
    panelPromptEdit_->setMaximumHeight(100);
    lay->addWidget(panelPromptEdit_);

    lay->addWidget(fieldLabel(QStringLiteral("Dialogue / caption"), body));
    panelDialogueEdit_ = new QTextEdit(body);
    panelDialogueEdit_->setMinimumHeight(36);
    panelDialogueEdit_->setMaximumHeight(52);
    panelCaptionEdit_ = new QTextEdit(body);
    panelCaptionEdit_->setMinimumHeight(32);
    panelCaptionEdit_->setMaximumHeight(48);
    lay->addWidget(panelDialogueEdit_);
    lay->addWidget(panelCaptionEdit_);

    lay->addWidget(fieldLabel(QStringLiteral("Camera"), body));
    panelCameraCombo_ = new QComboBox(body);
    panelCameraCombo_->addItems({
        QStringLiteral("wide"),
        QStringLiteral("medium"),
        QStringLiteral("close"),
        QStringLiteral("extreme-close"),
        QStringLiteral("low-angle"),
        QStringLiteral("birdseye")
    });
    lay->addWidget(panelCameraCombo_);

    panelPreview_ = new QLabel(QStringLiteral("No panel image"), body);
    panelPreview_->setObjectName(QStringLiteral("ComicPreview"));
    panelPreview_->setAlignment(Qt::AlignCenter);
    panelPreview_->setMinimumHeight(120);
    lay->addWidget(panelPreview_, 1);

    panelStatus_ = new QLabel(QStringLiteral("—"), body);
    panelStatus_->setObjectName(QStringLiteral("ComicMuted"));
    lay->addWidget(panelStatus_);

    scroll->setWidget(body);
    auto *panelLay = new QVBoxLayout(panel);
    panelLay->setContentsMargins(0, 0, 0, 0);
    panelLay->setSpacing(0);
    panelLay->addWidget(scroll, 1);

    rebuildPanelList();
    return panel;
}

QWidget *ComicStudioPage::buildActionRow()
{
    auto *row = new DashboardGlassPanel(this);
    row->setVariant(DashboardGlassPanel::Variant::Utility);
    row->setCornerRadius(14);
    row->setFixedHeight(64);

    auto *lay = new QHBoxLayout(row);
    lay->setContentsMargins(14, 10, 14, 10);
    lay->setSpacing(10);

    actionHint_ = new QLabel(QStringLiteral("Ready to compose"), row);
    actionHint_->setObjectName(QStringLiteral("ComicMuted"));
    lay->addWidget(actionHint_, 1);

    openT2IBtn_ = new QPushButton(QStringLiteral("Open T2I"), row);
    openT2IBtn_->setObjectName(QStringLiteral("ComicSecondaryBtn"));
    connect(openT2IBtn_, &QPushButton::clicked, this, &ComicStudioPage::openSelectedInT2I);
    lay->addWidget(openT2IBtn_);

    saveBtn_ = new QPushButton(QStringLiteral("Save"), row);
    saveBtn_->setObjectName(QStringLiteral("ComicSecondaryBtn"));
    connect(saveBtn_, &QPushButton::clicked, this, &ComicStudioPage::saveProject);
    lay->addWidget(saveBtn_);

    exportBtn_ = new QPushButton(QStringLiteral("Export page"), row);
    exportBtn_->setObjectName(QStringLiteral("ComicSecondaryBtn"));
    connect(exportBtn_, &QPushButton::clicked, this, &ComicStudioPage::exportPage);
    lay->addWidget(exportBtn_);

    genAllBtn_ = new QPushButton(QStringLiteral("Generate all"), row);
    genAllBtn_->setObjectName(QStringLiteral("ComicSecondaryBtn"));
    connect(genAllBtn_, &QPushButton::clicked, this, &ComicStudioPage::generateAllPanels);
    lay->addWidget(genAllBtn_);

    genPanelBtn_ = new QPushButton(QStringLiteral("Generate panel"), row);
    genPanelBtn_->setObjectName(QStringLiteral("ComicPrimaryBtn"));
    connect(genPanelBtn_, &QPushButton::clicked, this, &ComicStudioPage::generateSelectedPanel);
    lay->addWidget(genPanelBtn_);

    return row;
}

void ComicStudioPage::applyLayoutPreset(const QString &presetId)
{
    const LayoutSpec spec = findLayout(presetId);
    layoutId_ = spec.id;
    const int n = spec.panels;
    panels_.clear();
    panels_.reserve(n);
    for (int i = 0; i < n; ++i) {
        ComicPanel p;
        p.index = i;
        p.title = QStringLiteral("Panel %1").arg(i + 1);
        p.camera = (i == 0) ? QStringLiteral("wide")
                            : (i == n - 1 ? QStringLiteral("close") : QStringLiteral("medium"));
        panels_.push_back(p);
    }
    if (panelCountSpin_)
        panelCountSpin_->setValue(n);
    selectedPanel_ = 0;
    rebuildPanelList();
    refreshCanvas();
    refreshHeroMeta();
}

void ComicStudioPage::rebuildPanelList()
{
    if (!panelList_)
        return;
    panelList_->blockSignals(true);
    panelList_->clear();
    for (const auto &p : panels_) {
        const QString mark = p.done ? QStringLiteral("●") : QStringLiteral("○");
        panelList_->addItem(QStringLiteral("%1  %2  ·  %3").arg(mark, p.title, p.camera));
    }
    if (selectedPanel_ >= 0 && selectedPanel_ < panels_.size())
        panelList_->setCurrentRow(selectedPanel_);
    panelList_->blockSignals(false);
}

void ComicStudioPage::selectPanel(int index)
{
    syncPanelFromInspector();
    if (index < 0 || index >= panels_.size())
        return;
    selectedPanel_ = index;
    refreshPanelInspector();
    refreshCanvas();
}

void ComicStudioPage::refreshPanelInspector()
{
    if (selectedPanel_ < 0 || selectedPanel_ >= panels_.size())
        return;
    const ComicPanel &p = panels_[selectedPanel_];
    if (panelTitleEdit_)
        panelTitleEdit_->setText(p.title);
    if (panelBeatEdit_)
        panelBeatEdit_->setPlainText(p.beat);
    if (panelPromptEdit_)
        panelPromptEdit_->setPlainText(p.prompt);
    if (panelDialogueEdit_)
        panelDialogueEdit_->setPlainText(p.dialogue);
    if (panelCaptionEdit_)
        panelCaptionEdit_->setPlainText(p.caption);
    if (panelCameraCombo_) {
        const int idx = panelCameraCombo_->findText(p.camera);
        panelCameraCombo_->setCurrentIndex(idx >= 0 ? idx : 1);
    }
    if (panelPreview_) {
        if (!p.imagePath.isEmpty() && QFileInfo::exists(p.imagePath)) {
            QPixmap px(p.imagePath);
            panelPreview_->setPixmap(px.scaled(panelPreview_->size().boundedTo(QSize(320, 240)),
                                               Qt::KeepAspectRatio, Qt::SmoothTransformation));
        } else {
            panelPreview_->setPixmap(QPixmap());
            panelPreview_->setText(QStringLiteral("No panel image"));
        }
    }
    if (panelStatus_)
        panelStatus_->setText(p.done ? QStringLiteral("Done · %1").arg(p.imagePath)
                                     : QStringLiteral("Not generated"));
}

void ComicStudioPage::refreshCanvas()
{
    if (!canvasHost_)
        return;

    // Rebuild grid cells.
    if (auto *old = canvasHost_->layout()) {
        QLayoutItem *child;
        while ((child = old->takeAt(0)) != nullptr) {
            if (child->widget())
                child->widget()->deleteLater();
            delete child;
        }
        delete old;
    }
    canvasCells_.clear();

    auto *grid = new QGridLayout(canvasHost_);
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setSpacing(10);

    const int cols = colsForLayout();

    for (int i = 0; i < panels_.size(); ++i) {
        const ComicPanel &p = panels_[i];
        auto *clickCell = new QPushButton(canvasHost_);
        clickCell->setObjectName(QStringLiteral("ComicCanvasHit"));
        clickCell->setMinimumSize(150, 180);
        clickCell->setCheckable(true);
        clickCell->setChecked(i == selectedPanel_);
        clickCell->setCursor(Qt::PointingHandCursor);

        if (!p.imagePath.isEmpty() && QFileInfo::exists(p.imagePath)) {
            clickCell->setIcon(QIcon(p.imagePath));
            clickCell->setIconSize(QSize(200, 260));
            clickCell->setText(QString());
            clickCell->setToolTip(p.title + QLatin1Char('\n') + p.imagePath);
        } else {
            const QString beatHint = p.beat.trimmed().isEmpty()
                                         ? QStringLiteral("empty beat — write script & split")
                                         : p.beat.left(72);
            clickCell->setText(QStringLiteral("%1\n%2\n\n%3")
                                   .arg(p.title, p.camera, beatHint));
            clickCell->setToolTip(QStringLiteral("Click to inspect · Generate panel when ready"));
        }

        connect(clickCell, &QPushButton::clicked, this, [this, i]() { selectPanel(i); });
        grid->addWidget(clickCell, i / cols, i % cols);

        // Keep a dummy entry so size matches (preview thumb path unused now).
        auto *marker = new QLabel(canvasHost_);
        marker->hide();
        canvasCells_.push_back(marker);
    }
}

void ComicStudioPage::refreshHeroMeta()
{
    int done = 0;
    for (const auto &p : panels_)
        if (p.done)
            ++done;
    if (heroMeta_)
        heroMeta_->setText(QStringLiteral("%1/%2 panels · %3")
                               .arg(done)
                               .arg(panels_.size())
                               .arg(findLayout(layoutId_).label));
    if (pagePreviewCaption_)
        pagePreviewCaption_->setText(
            QStringLiteral("%1 · style: %2")
                .arg(titleEdit_ ? titleEdit_->text() : QStringLiteral("Page"),
                     styleCombo_ ? styleCombo_->currentText() : QString()));
}

void ComicStudioPage::syncPanelFromInspector()
{
    if (selectedPanel_ < 0 || selectedPanel_ >= panels_.size())
        return;
    ComicPanel &p = panels_[selectedPanel_];
    if (panelTitleEdit_)
        p.title = panelTitleEdit_->text().trimmed().isEmpty() ? p.title : panelTitleEdit_->text().trimmed();
    if (panelBeatEdit_)
        p.beat = panelBeatEdit_->toPlainText().trimmed();
    if (panelPromptEdit_)
        p.prompt = panelPromptEdit_->toPlainText().trimmed();
    if (panelDialogueEdit_)
        p.dialogue = panelDialogueEdit_->toPlainText().trimmed();
    if (panelCaptionEdit_)
        p.caption = panelCaptionEdit_->toPlainText().trimmed();
    if (panelCameraCombo_)
        p.camera = panelCameraCombo_->currentText();
}

void ComicStudioPage::autoFillPromptsFromScript()
{
    if (!scriptEdit_)
        return;
    const QStringList lines = scriptEdit_->toPlainText().split(QLatin1Char('\n'), Qt::SkipEmptyParts);
    if (lines.isEmpty())
        return;

    // Resize panels to script lines if needed.
    if (panelCountSpin_ && lines.size() != panels_.size())
        panelCountSpin_->setValue(qBound(1, lines.size(), 12));

    for (int i = 0; i < panels_.size() && i < lines.size(); ++i) {
        QString beat = lines[i].trimmed();
        // Strip leading numbering "1." / "1)"
        if (beat.size() > 2 && beat[0].isDigit()) {
            const int dot = beat.indexOf(QLatin1Char('.'));
            const int par = beat.indexOf(QLatin1Char(')'));
            const int cut = (dot > 0 && dot < 4) ? dot : ((par > 0 && par < 4) ? par : -1);
            if (cut > 0)
                beat = beat.mid(cut + 1).trimmed();
        }
        panels_[i].beat = beat;
        panels_[i].title = QStringLiteral("Panel %1").arg(i + 1);
        panels_[i].prompt = QStringLiteral("%1, %2, %3, %4 sequential art panel")
                                .arg(beat, cameraDirective(panels_[i].camera), styleScaffold(),
                                     keepCharacterCheck_ && keepCharacterCheck_->isChecked()
                                             && characterLockEdit_ && !characterLockEdit_->text().trimmed().isEmpty()
                                         ? characterLockEdit_->text().trimmed()
                                         : QStringLiteral("consistent cast"));
    }
    rebuildPanelList();
    refreshPanelInspector();
    refreshCanvas();
    if (statusBanner_)
        statusBanner_->setText(QStringLiteral("Script split across %1 panels. Review prompts, then generate.").arg(panels_.size()));
}

void ComicStudioPage::generateSelectedPanel()
{
    if (selectedPanel_ < 0 || selectedPanel_ >= panels_.size())
        return;
    if (selectedModelPath_.trimmed().isEmpty()) {
        if (statusBanner_)
            statusBanner_->setText(QStringLiteral("Choose a checkpoint first (Model stack on the left)."));
        return;
    }
    syncPanelFromInspector();
    ComicPanel &p = panels_[selectedPanel_];
    if (p.prompt.trimmed().isEmpty()) {
        // Synthesize from beat.
        if (p.beat.trimmed().isEmpty()) {
            if (statusBanner_)
                statusBanner_->setText(QStringLiteral("Add a beat or prompt for this panel first."));
            return;
        }
        p.prompt = QStringLiteral("%1, %2, %3")
                       .arg(p.beat, cameraDirective(p.camera), styleScaffold());
        if (keepCharacterCheck_ && keepCharacterCheck_->isChecked() && characterLockEdit_
            && !characterLockEdit_->text().trimmed().isEmpty())
            p.prompt += QStringLiteral(", ") + characterLockEdit_->text().trimmed();
        refreshPanelInspector();
    }

    const QJsonObject payload = buildPanelPayload(p);
    setBusy(true, QStringLiteral("Generating %1…").arg(p.title));
    // Stash selected index in payload for MainWindow routing back.
    QJsonObject tagged = payload;
    tagged.insert(QStringLiteral("_comic_panel_index"), selectedPanel_);
    tagged.insert(QStringLiteral("_comic_project"), projectName_);
    emit generateRequested(QStringLiteral("t2i"), tagged, false);
}

void ComicStudioPage::generateAllPanels()
{
    if (selectedModelPath_.trimmed().isEmpty()) {
        if (statusBanner_)
            statusBanner_->setText(QStringLiteral("Choose a checkpoint first (Model stack on the left)."));
        return;
    }
    syncPanelFromInspector();
    // Ensure prompts exist.
    for (auto &p : panels_) {
        if (p.prompt.trimmed().isEmpty() && !p.beat.trimmed().isEmpty()) {
            p.prompt = QStringLiteral("%1, %2, %3")
                           .arg(p.beat, cameraDirective(p.camera), styleScaffold());
            if (keepCharacterCheck_ && keepCharacterCheck_->isChecked() && characterLockEdit_
                && !characterLockEdit_->text().trimmed().isEmpty())
                p.prompt += QStringLiteral(", ") + characterLockEdit_->text().trimmed();
        }
    }
    int queued = 0;
    for (int i = 0; i < panels_.size(); ++i) {
        if (panels_[i].done)
            continue;
        if (panels_[i].prompt.trimmed().isEmpty())
            continue;
        QJsonObject tagged = buildPanelPayload(panels_[i]);
        tagged.insert(QStringLiteral("_comic_panel_index"), i);
        tagged.insert(QStringLiteral("_comic_project"), projectName_);
        emit generateRequested(QStringLiteral("t2i"), tagged, false);
        ++queued;
    }
    if (queued == 0) {
        if (statusBanner_)
            statusBanner_->setText(QStringLiteral("All panels already generated, or prompts are empty."));
    } else {
        setBusy(true, QStringLiteral("Queued %1 panel%2…")
                          .arg(queued)
                          .arg(queued == 1 ? QString() : QStringLiteral("s")));
        if (actionHint_)
            actionHint_->setText(QStringLiteral("Queued %1 incomplete panel%2 — previews route by job id.")
                                     .arg(queued)
                                     .arg(queued == 1 ? QString() : QStringLiteral("s")));
        rebuildPanelList();
        refreshPanelInspector();
    }
}

void ComicStudioPage::openSelectedInT2I()
{
    emit navigateRequested(QStringLiteral("t2i"));
}

void ComicStudioPage::exportPage()
{
    syncPanelFromInspector();
    const QString dir = QDir(projectsDir()).filePath(projectName_ + QStringLiteral("/export"));
    QDir().mkpath(dir);

    // Composite a simple page image from available panels.
    const int cols = colsForLayout();
    const int rows = rowsForLayout();
    const int cellW = 512;
    const int cellH = 640;
    const int gap = 16;
    const int pageW = cols * cellW + (cols + 1) * gap;
    const int pageH = rows * cellH + (rows + 1) * gap + 48;

    QPixmap page(pageW, pageH);
    page.fill(QColor(QStringLiteral("#0b0d14")));
    QPainter painter(&page);
    painter.setRenderHint(QPainter::SmoothPixmapTransform, true);
    painter.setPen(QColor(QStringLiteral("#e8e6f2")));
    painter.setFont(ThemeManager::instance().font(ThemeManager::Type::Title));
    painter.drawText(QRect(gap, 8, pageW - 2 * gap, 32),
                     Qt::AlignLeft | Qt::AlignVCenter,
                     titleEdit_ ? titleEdit_->text() : QStringLiteral("Comic page"));

    for (int i = 0; i < panels_.size(); ++i) {
        const int r = i / cols;
        const int c = i % cols;
        const QRect rect(gap + c * (cellW + gap), 48 + gap + r * (cellH + gap), cellW, cellH);
        painter.fillRect(rect, QColor(QStringLiteral("#141824")));
        painter.setPen(QPen(QColor(QStringLiteral("#3a3f55")), 2));
        painter.drawRect(rect.adjusted(0, 0, -1, -1));
        if (!panels_[i].imagePath.isEmpty() && QFileInfo::exists(panels_[i].imagePath)) {
            QPixmap px(panels_[i].imagePath);
            painter.drawPixmap(rect.adjusted(4, 4, -4, -4),
                               px.scaled(rect.size() - QSize(8, 8), Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation));
        } else {
            painter.setPen(QColor(QStringLiteral("#8b90a5")));
            painter.drawText(rect, Qt::AlignCenter, panels_[i].title);
        }
        if (!panels_[i].dialogue.isEmpty()) {
            painter.fillRect(QRect(rect.left() + 12, rect.bottom() - 56, rect.width() - 24, 40),
                             QColor(255, 255, 255, 220));
            painter.setPen(Qt::black);
            painter.setFont(ThemeManager::instance().font(ThemeManager::Type::Body));
            painter.drawText(QRect(rect.left() + 16, rect.bottom() - 52, rect.width() - 32, 32),
                             Qt::AlignCenter | Qt::TextWordWrap, panels_[i].dialogue);
        }
    }
    painter.end();

    const QString outImg = QDir(dir).filePath(QStringLiteral("page.png"));
    page.save(outImg, "PNG");

    QJsonObject manifest;
    manifest.insert(QStringLiteral("title"), titleEdit_ ? titleEdit_->text() : QString());
    manifest.insert(QStringLiteral("layout"), layoutId_);
    manifest.insert(QStringLiteral("style"), styleCombo_ ? styleCombo_->currentText() : QString());
    manifest.insert(QStringLiteral("page_image"), outImg);
    QJsonArray arr;
    for (const auto &p : panels_) {
        QJsonObject o;
        o.insert(QStringLiteral("index"), p.index);
        o.insert(QStringLiteral("title"), p.title);
        o.insert(QStringLiteral("beat"), p.beat);
        o.insert(QStringLiteral("prompt"), p.prompt);
        o.insert(QStringLiteral("dialogue"), p.dialogue);
        o.insert(QStringLiteral("caption"), p.caption);
        o.insert(QStringLiteral("camera"), p.camera);
        o.insert(QStringLiteral("image"), p.imagePath);
        arr.append(o);
    }
    manifest.insert(QStringLiteral("panels"), arr);

    if (!writeJsonAtomically(QDir(dir).filePath(QStringLiteral("page_manifest.json")),
                             QJsonDocument(manifest))) {
        if (statusBanner_)
            statusBanner_->setText(QStringLiteral("Export failed: page manifest could not be safely written."));
        return;
    }

    saveProject();
    if (statusBanner_)
        statusBanner_->setText(QStringLiteral("Exported page → %1").arg(outImg));
    if (actionHint_)
        actionHint_->setText(QStringLiteral("Export complete"));
}

void ComicStudioPage::saveProject()
{
    syncPanelFromInspector();
    QDir().mkpath(QDir(projectsDir()).filePath(projectName_));
    QJsonObject root;
    root.insert(QStringLiteral("name"), projectName_);
    root.insert(QStringLiteral("title"), titleEdit_ ? titleEdit_->text() : QString());
    root.insert(QStringLiteral("layout"), layoutId_);
    root.insert(QStringLiteral("style"), styleCombo_ ? styleCombo_->currentIndex() : 0);
    root.insert(QStringLiteral("script"), scriptEdit_ ? scriptEdit_->toPlainText() : QString());
    root.insert(QStringLiteral("global_style"), globalStyleEdit_ ? globalStyleEdit_->toPlainText() : QString());
    root.insert(QStringLiteral("character_lock"), characterLockEdit_ ? characterLockEdit_->text() : QString());
    root.insert(QStringLiteral("model"), selectedModelPath_);
    root.insert(QStringLiteral("model_display"), selectedModelDisplay_);
    root.insert(QStringLiteral("lora"), selectedLoraPath_);
    root.insert(QStringLiteral("lora_display"), selectedLoraDisplay_);
    QJsonArray arr;
    for (const auto &p : panels_) {
        QJsonObject o;
        o.insert(QStringLiteral("index"), p.index);
        o.insert(QStringLiteral("title"), p.title);
        o.insert(QStringLiteral("beat"), p.beat);
        o.insert(QStringLiteral("prompt"), p.prompt);
        o.insert(QStringLiteral("dialogue"), p.dialogue);
        o.insert(QStringLiteral("caption"), p.caption);
        o.insert(QStringLiteral("camera"), p.camera);
        o.insert(QStringLiteral("image"), p.imagePath);
        o.insert(QStringLiteral("done"), p.done);
        arr.append(o);
    }
    root.insert(QStringLiteral("panels"), arr);
    if (!writeJsonAtomically(
            QDir(projectsDir()).filePath(projectName_ + QStringLiteral("/project.json")),
            QJsonDocument(root))
        && actionHint_)
        actionHint_->setText(QStringLiteral("Save failed: project.json was not replaced"));
}

void ComicStudioPage::loadProject()
{
    QFile f(QDir(projectsDir()).filePath(projectName_ + QStringLiteral("/project.json")));
    if (!f.exists() || !f.open(QIODevice::ReadOnly))
        return;
    const auto doc = QJsonDocument::fromJson(f.readAll());
    f.close();
    if (!doc.isObject())
        return;
    const QJsonObject root = doc.object();
    if (titleEdit_)
        titleEdit_->setText(root.value(QStringLiteral("title")).toString());
    layoutId_ = root.value(QStringLiteral("layout")).toString(layoutId_);
    if (layoutCombo_) {
        const int idx = layoutCombo_->findData(layoutId_);
        if (idx >= 0)
            layoutCombo_->setCurrentIndex(idx);
    }
    if (styleCombo_)
        styleCombo_->setCurrentIndex(root.value(QStringLiteral("style")).toInt());
    if (scriptEdit_)
        scriptEdit_->setPlainText(root.value(QStringLiteral("script")).toString());
    if (globalStyleEdit_)
        globalStyleEdit_->setPlainText(root.value(QStringLiteral("global_style")).toString());
    if (characterLockEdit_)
        characterLockEdit_->setText(root.value(QStringLiteral("character_lock")).toString());
    selectedModelPath_ = root.value(QStringLiteral("model")).toString();
    selectedModelDisplay_ = root.value(QStringLiteral("model_display")).toString();
    selectedLoraPath_ = root.value(QStringLiteral("lora")).toString();
    selectedLoraDisplay_ = root.value(QStringLiteral("lora_display")).toString();
    refreshModelStackLabels();

    const QJsonArray arr = root.value(QStringLiteral("panels")).toArray();
    if (!arr.isEmpty()) {
        panels_.clear();
        for (const QJsonValue &v : arr) {
            const QJsonObject o = v.toObject();
            ComicPanel p;
            p.index = o.value(QStringLiteral("index")).toInt();
            p.title = o.value(QStringLiteral("title")).toString();
            p.beat = o.value(QStringLiteral("beat")).toString();
            p.prompt = o.value(QStringLiteral("prompt")).toString();
            p.dialogue = o.value(QStringLiteral("dialogue")).toString();
            p.caption = o.value(QStringLiteral("caption")).toString();
            p.camera = o.value(QStringLiteral("camera")).toString(QStringLiteral("medium"));
            p.imagePath = o.value(QStringLiteral("image")).toString();
            p.done = o.value(QStringLiteral("done")).toBool() || QFileInfo::exists(p.imagePath);
            panels_.push_back(p);
        }
        if (panelCountSpin_)
            panelCountSpin_->setValue(panels_.size());
    }
    rebuildPanelList();
    refreshCanvas();
    refreshPanelInspector();
    refreshHeroMeta();
}

QJsonObject ComicStudioPage::buildPanelPayload(const ComicPanel &panel) const
{
    int w = 832, h = 1216;
    if (advanced_ && widthSpin_ && heightSpin_) {
        w = widthSpin_->value();
        h = heightSpin_->value();
    } else if (aspectCombo_) {
        if (aspectCombo_->currentIndex() == 1) {
            w = 1024;
            h = 1024;
        } else if (aspectCombo_->currentIndex() == 2) {
            w = 1216;
            h = 832;
        }
    }

    int seed = 0;
    if (advanced_ && randomSeedCheck_ && !randomSeedCheck_->isChecked() && seedEdit_)
        seed = seedEdit_->text().toInt();
    else
        seed = static_cast<int>((QDateTime::currentMSecsSinceEpoch() + panel.index * 9973) & 0x7fffffff);

    const int steps = (advanced_ && stepsSpin_) ? stepsSpin_->value() : 28;
    const double cfg = (advanced_ && cfgSpin_) ? cfgSpin_->value() : 5.0;

    QString prompt = panel.prompt;
    if (!prompt.contains(styleScaffold().left(12)))
        prompt += QStringLiteral(", ") + styleScaffold();

    QJsonObject payload;
    payload.insert(QStringLiteral("prompt"), prompt);
    payload.insert(QStringLiteral("negative_prompt"),
                   QStringLiteral("collage, multiple panels, speech bubble artifacts, watermark, text overlay, "
                                  "blurry, lowres, extra fingers, deformed face, inconsistent outfit"));
    payload.insert(QStringLiteral("width"), w);
    payload.insert(QStringLiteral("height"), h);
    payload.insert(QStringLiteral("steps"), steps);
    payload.insert(QStringLiteral("cfg"), cfg);
    payload.insert(QStringLiteral("seed"), seed);
    if (advanced_ && samplerHintCombo_)
        payload.insert(QStringLiteral("sampler"),
                       spellvision::generation::comboStoredValue(samplerHintCombo_));
    payload.insert(QStringLiteral("output_prefix"),
                   QStringLiteral("comic_%1_p%2").arg(projectName_).arg(panel.index + 1, 2, 10, QLatin1Char('0')));
    if (!selectedModelPath_.trimmed().isEmpty()) {
        payload.insert(QStringLiteral("model"), selectedModelPath_.trimmed());
        payload.insert(QStringLiteral("model_display"),
                       selectedModelDisplay_.isEmpty() ? QFileInfo(selectedModelPath_).fileName()
                                                       : selectedModelDisplay_);
    }
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
    return payload;
}

void ComicStudioPage::refreshModelStackLabels()
{
    if (modelValueLabel_) {
        modelValueLabel_->setText(selectedModelPath_.isEmpty()
                                      ? QStringLiteral("No model selected — required to generate")
                                      : (selectedModelDisplay_.isEmpty()
                                             ? QFileInfo(selectedModelPath_).fileName()
                                             : selectedModelDisplay_));
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

void ComicStudioPage::pickModel()
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
                            QStringLiteral("comicStudio/recentModels"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    selectedModelPath_ = dlg.selectedValue();
    selectedModelDisplay_ = dlg.selectedDisplay();
    persistRecentSelection(QStringLiteral("comicStudio/recentModels"), selectedModelPath_);
    refreshModelStackLabels();
    saveProject();
}

void ComicStudioPage::pickLora()
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
                            QStringLiteral("comicStudio/recentLoras"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    selectedLoraPath_ = dlg.selectedValue();
    selectedLoraDisplay_ = dlg.selectedDisplay();
    persistRecentSelection(QStringLiteral("comicStudio/recentLoras"), selectedLoraPath_);
    refreshModelStackLabels();
    saveProject();
}

void ComicStudioPage::clearLora()
{
    selectedLoraPath_.clear();
    selectedLoraDisplay_.clear();
    refreshModelStackLabels();
    saveProject();
}

QString ComicStudioPage::projectsDir() const
{
    const QString root = projectRoot_.isEmpty() ? QDir::currentPath() : projectRoot_;
    return QDir(root).filePath(QStringLiteral("runtime/comics"));
}

QString ComicStudioPage::styleScaffold() const
{
    QString s = globalStyleEdit_ ? globalStyleEdit_->toPlainText().trimmed() : QString();
    if (styleCombo_)
        s = styleCombo_->currentText() + QStringLiteral(", ") + s;
    return s;
}

QString ComicStudioPage::cameraDirective(const QString &camera) const
{
    if (camera == QStringLiteral("wide"))
        return QStringLiteral("wide establishing shot");
    if (camera == QStringLiteral("close"))
        return QStringLiteral("close-up shot");
    if (camera == QStringLiteral("extreme-close"))
        return QStringLiteral("extreme close-up");
    if (camera == QStringLiteral("low-angle"))
        return QStringLiteral("dramatic low angle");
    if (camera == QStringLiteral("birdseye"))
        return QStringLiteral("bird's eye view");
    return QStringLiteral("medium shot");
}

int ComicStudioPage::colsForLayout() const
{
    return findLayout(layoutId_).cols;
}

int ComicStudioPage::rowsForLayout() const
{
    return findLayout(layoutId_).rows;
}

void ComicStudioPage::applyTheme()
{
    const auto &theme = ThemeManager::instance();
    using C = ThemeManager::Color;
    // Use @tokens@ — QString::arg only supports %1..%9 reliably; %10+ becomes "%1"+"0".
    QString css = QStringLiteral(
        "#ComicStudioPage { background: transparent; }"
        "QLabel#ComicEyebrow { @micro@ letter-spacing: 0.14em; color: @accent@; }"
        "QLabel#ComicHeroTitle { @display@ color: @textHi@; }"
        "QLabel#ComicHeroSubtitle { @body@ color: @textMid@; }"
        "QLabel#ComicHeroMeta { @label@ color: @accentHover@; }"
        "QLabel#ComicSectionTitle { @heading@ color: @textHi@; }"
        "QLabel#ComicFieldLabel { @label@ color: @textMid@; }"
        "QLabel#ComicMuted { @body@ color: @textMid@; }"
        "QLabel#ComicStatusBanner {"
        " @body@ color: @textMid@; background: @glassFill@; border: 1px solid @border@;"
        " border-radius: 10px; padding: 8px 10px; }"
        "QLabel#ComicPreview, QLabel#ComicCanvasCell {"
        " background: @surface0@; border: 1px solid @border@; border-radius: 12px; color: @textMid@; }"
        "QListWidget#ComicPanelList {"
        " background: transparent; border: none; color: @textHi@; @body@ outline: none; }"
        "QListWidget#ComicPanelList::item {"
        " background: @surface1@; border: 1px solid @border@; border-radius: 8px; padding: 6px; margin: 2px 0; }"
        "QListWidget#ComicPanelList::item:selected { background: @accentSubtle@; border-color: @accent@; }"
        "QListWidget#ComicPanelList::item:hover { border-color: @accentHover@; }"
        "QTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {"
        " background: @surface0@; color: @textHi@; border: 1px solid @border@; border-radius: 8px;"
        " padding: 6px 8px; @body@ selection-background-color: @accent@; }"
        "QTextEdit:focus, QLineEdit:focus, QComboBox:focus { border-color: @accent@; }"
        "QPushButton#ComicPrimaryBtn {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 @accent@, stop:1 @accentSecondary@);"
        " color: white; border: 1px solid @accentHover@; border-radius: 10px; padding: 8px 16px; @label@ }"
        "QPushButton#ComicPrimaryBtn:hover { background: @accentHover@; }"
        "QPushButton#ComicPrimaryBtn:disabled { background: @surface2@; color: @textDisabled@; border-color: @border@; }"
        "QPushButton#ComicSecondaryBtn {"
        " background: @surface1@; color: @textHi@; border: 1px solid @border@; border-radius: 10px; padding: 8px 14px; @label@ }"
        "QPushButton#ComicSecondaryBtn:hover { border-color: @accent@; color: @accent@; }"
        "QPushButton#ComicCanvasHit {"
        " background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 @surface1@, stop:1 @surface0@);"
        " color: @textMid@; border: 1px solid @border@; border-radius: 14px;"
        " padding: 12px; text-align: center; @body@ }"
        "QPushButton#ComicCanvasHit:checked {"
        " border: 2px solid @accent@; color: @textHi@; background: @accentSubtle@; }"
        "QPushButton#ComicCanvasHit:hover { border-color: @accentHover@; color: @textHi@; }"
        "QProgressBar#ComicProgress { background: @surface0@; border: none; border-radius: 3px; }"
        "QProgressBar#ComicProgress::chunk { background: @accent@; border-radius: 3px; }"
        "QCheckBox { color: @textMid@; @body@ spacing: 8px; }"
        "QScrollArea#ComicSideScroll { background: transparent; border: none; }"
        "QScrollArea#ComicSideScroll > QWidget > QWidget { background: transparent; }"
        "QFormLayout, QLabel { color: @textMid@; }");

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
    refreshCanvas();
}

} // namespace spellvision::studios
