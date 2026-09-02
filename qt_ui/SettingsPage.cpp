#include "SettingsPage.h"
#include "shell/AppVersion.h"
#include <QUrl>
#include <QDesktopServices>
#include "ThemeManager.h"
#include "shell/SecureCredentialStore.h"

#include <QCheckBox>
#include <QComboBox>
#include <QFrame>
#include <QHBoxLayout>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIODevice>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QScrollArea>
#include <QSettings>
#include <QStandardPaths>
#include <QSignalBlocker>
#include <QSlider>
#include <QVBoxLayout>

namespace
{
QString dashboardPresetLabel(HomeDashboardPreset preset)
{
    switch (preset)
    {
    case HomeDashboardPreset::CinematicStudio: return QStringLiteral("Cinematic Studio");
    case HomeDashboardPreset::ProductiveCompact: return QStringLiteral("Productive Compact");
    case HomeDashboardPreset::MotionWorkspace: return QStringLiteral("Motion Workspace");
    case HomeDashboardPreset::ModelOps: return QStringLiteral("Model Ops");
    case HomeDashboardPreset::Minimal: return QStringLiteral("Minimal");
    }

    return QStringLiteral("Cinematic Studio");
}

QString dashboardDensityLabel(HomeDashboardDensity density)
{
    switch (density)
    {
    case HomeDashboardDensity::Compact: return QStringLiteral("Compact");
    case HomeDashboardDensity::Comfortable: return QStringLiteral("Comfortable");
    case HomeDashboardDensity::Cinematic: return QStringLiteral("Cinematic");
    }

    return QStringLiteral("Comfortable");
}

QString moduleDisplayName(const QString &moduleId)
{
    if (moduleId == HomeDashboardIds::HeroLauncher)
        return QStringLiteral("Hero Launcher");
    if (moduleId == HomeDashboardIds::WorkflowLauncher)
        return QStringLiteral("Workflow Launcher");
    if (moduleId == HomeDashboardIds::RecentOutputs)
        return QStringLiteral("Recent Outputs");
    if (moduleId == HomeDashboardIds::Favorites)
        return QStringLiteral("Favorites Rail");
    if (moduleId == HomeDashboardIds::ActiveModels)
        return QStringLiteral("Active Models");

    return moduleId;
}
}

SettingsPage::SettingsPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("SettingsPage"));

    auto *outerLayout = new QVBoxLayout(this);
    outerLayout->setContentsMargins(0, 0, 0, 0);
    outerLayout->setSpacing(0);

    scrollArea_ = new QScrollArea(this);
    scrollArea_->setWidgetResizable(true);
    scrollArea_->setFrameShape(QFrame::NoFrame);
    scrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    outerLayout->addWidget(scrollArea_);

    contentWidget_ = new QWidget(scrollArea_);
    scrollArea_->setWidget(contentWidget_);

    rootLayout_ = new QVBoxLayout(contentWidget_);
    rootLayout_->setContentsMargins(18, 14, 18, 18);
    rootLayout_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    auto *titleLabel = new QLabel(QStringLiteral("Appearance & Home Dashboard"), contentWidget_);
    titleLabel->setObjectName(QStringLiteral("SettingsTitle"));

    auto *subtitleLabel = new QLabel(
        QStringLiteral("Tune the SpellVision surface language, then shape Home into a choose-your-own-adventure dashboard with presets, density, and module visibility."),
        contentWidget_);
    subtitleLabel->setObjectName(QStringLiteral("SettingsSubtitle"));
    subtitleLabel->setWordWrap(true);

    rootLayout_->addWidget(titleLabel);
    rootLayout_->addWidget(subtitleLabel);

    auto *workspaceCard = createSectionCard(
        QStringLiteral("Workspace Mode"),
        QStringLiteral("Simple shows intent-level controls; Advanced reveals the raw knobs in place. This is the same control as the Simple / Advanced toggle in the title bar -- they stay in sync, and your last choice is remembered next launch."));
    auto *workspaceLayout = qobject_cast<QVBoxLayout *>(workspaceCard->layout());

    disclosureModeCombo_ = new QComboBox(workspaceCard);
    disclosureModeCombo_->addItem(QStringLiteral("Simple"), false);
    disclosureModeCombo_->addItem(QStringLiteral("Advanced"), true);
    workspaceLayout->addWidget(disclosureModeCombo_);

    commercialUseCheck_ = new QCheckBox(QStringLiteral("I'm using SpellVision for commercial work"), workspaceCard);
    QSettings commercialSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    commercialUseCheck_->setChecked(commercialSettings.value(QStringLiteral("usage/commercialUse"), true).toBool());
    QObject::connect(commercialUseCheck_, &QCheckBox::toggled, workspaceCard, [](bool on) {
        QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        settings.setValue(QStringLiteral("usage/commercialUse"), on);
    });
    workspaceLayout->addWidget(commercialUseCheck_);
    rootLayout_->addWidget(workspaceCard);

    auto *credentialCard = createSectionCard(
        QStringLiteral("API keys"),
        QStringLiteral("Saved encrypted for this Windows user (DPAPI). Keys are never shown again after save, never written to git, and never stored in QSettings."));
    auto *credentialLayout = qobject_cast<QVBoxLayout *>(credentialCard->layout());
    hfTokenEdit_ = new QLineEdit(credentialCard);
    hfTokenEdit_->setEchoMode(QLineEdit::Password);
    hfTokenEdit_->setPlaceholderText(QStringLiteral("Hugging Face token"));
    hfTokenStatusLabel_ = new QLabel(credentialCard);
    hfTokenSaveButton_ = new QPushButton(QStringLiteral("Save"), credentialCard);
    hfTokenClearButton_ = new QPushButton(QStringLiteral("Clear"), credentialCard);
    auto *hfRow = new QHBoxLayout;
    hfRow->addWidget(hfTokenEdit_, 1);
    hfRow->addWidget(hfTokenSaveButton_);
    hfRow->addWidget(hfTokenClearButton_);
    credentialLayout->addLayout(hfRow);
    credentialLayout->addWidget(hfTokenStatusLabel_);
    civitaiKeyEdit_ = new QLineEdit(credentialCard);
    civitaiKeyEdit_->setEchoMode(QLineEdit::Password);
    civitaiKeyEdit_->setPlaceholderText(QStringLiteral("Civitai API key"));
    civitaiKeyStatusLabel_ = new QLabel(credentialCard);
    civitaiKeySaveButton_ = new QPushButton(QStringLiteral("Save"), credentialCard);
    civitaiKeyClearButton_ = new QPushButton(QStringLiteral("Clear"), credentialCard);
    auto *civitaiRow = new QHBoxLayout;
    civitaiRow->addWidget(civitaiKeyEdit_, 1);
    civitaiRow->addWidget(civitaiKeySaveButton_);
    civitaiRow->addWidget(civitaiKeyClearButton_);
    credentialLayout->addLayout(civitaiRow);
    credentialLayout->addWidget(civitaiKeyStatusLabel_);
    const auto refreshTokenStatus = [this]() {
        const bool hf = SecureCredentialStore::hasCredential(QStringLiteral("hf_token"));
        const bool civitai = SecureCredentialStore::hasCredential(QStringLiteral("civitai_api_key"));
        hfTokenStatusLabel_->setText(hf ? QStringLiteral("Hugging Face token encrypted on this account.") : QStringLiteral("No Hugging Face token saved."));
        civitaiKeyStatusLabel_->setText(civitai ? QStringLiteral("Civitai key encrypted on this account.") : QStringLiteral("No Civitai key saved."));
        hfTokenEdit_->setPlaceholderText(hf ? QStringLiteral("saved — paste to replace") : QStringLiteral("Hugging Face token"));
        civitaiKeyEdit_->setPlaceholderText(civitai ? QStringLiteral("saved — paste to replace") : QStringLiteral("Civitai API key"));
    };
    refreshTokenStatus();
    QObject::connect(hfTokenSaveButton_, &QPushButton::clicked, credentialCard, [this, refreshTokenStatus]() {
        const QString token = hfTokenEdit_->text().trimmed();
        if (token.isEmpty())
            return;
        SecureCredentialStore::setCredential(QStringLiteral("hf_token"), token);
        hfTokenEdit_->clear();
        refreshTokenStatus();
    });
    QObject::connect(hfTokenClearButton_, &QPushButton::clicked, credentialCard, [this, refreshTokenStatus]() {
        SecureCredentialStore::clearCredential(QStringLiteral("hf_token"));
        hfTokenEdit_->clear();
        refreshTokenStatus();
    });
    QObject::connect(civitaiKeySaveButton_, &QPushButton::clicked, credentialCard, [this, refreshTokenStatus]() {
        const QString token = civitaiKeyEdit_->text().trimmed();
        if (token.isEmpty())
            return;
        SecureCredentialStore::setCredential(QStringLiteral("civitai_api_key"), token);
        civitaiKeyEdit_->clear();
        refreshTokenStatus();
    });
    QObject::connect(civitaiKeyClearButton_, &QPushButton::clicked, credentialCard, [this, refreshTokenStatus]() {
        SecureCredentialStore::clearCredential(QStringLiteral("civitai_api_key"));
        civitaiKeyEdit_->clear();
        refreshTokenStatus();
    });
    rootLayout_->addWidget(credentialCard);

    auto *aboutCard = createSectionCard(
        QStringLiteral("About & updates"),
        QStringLiteral("Which SpellVision this is, and whether a newer one exists. Checking asks GitHub for the latest release; nothing is downloaded or installed from here."));
    auto *aboutLayout = qobject_cast<QVBoxLayout *>(aboutCard->layout());
    versionLabel_ = new QLabel(QStringLiteral("SpellVision %1").arg(spellvision::shell::appVersion()), aboutCard);
    versionLabel_->setObjectName(QStringLiteral("SettingsVersionLabel"));
    aboutLayout->addWidget(versionLabel_);
    auto *updateRow = new QHBoxLayout;
    checkUpdatesButton_ = new QPushButton(QStringLiteral("Check for updates"), aboutCard);
    checkUpdatesButton_->setObjectName(QStringLiteral("SettingsCheckUpdates"));
    openReleaseButton_ = new QPushButton(QStringLiteral("Open release page"), aboutCard);
    openReleaseButton_->setObjectName(QStringLiteral("SettingsOpenRelease"));
    openReleaseButton_->setEnabled(false);
    updateRow->addWidget(checkUpdatesButton_);
    updateRow->addWidget(openReleaseButton_);
    updateRow->addStretch(1);
    aboutLayout->addLayout(updateRow);
    updateStatusLabel_ = new QLabel(QStringLiteral("Not checked yet."), aboutCard);
    updateStatusLabel_->setObjectName(QStringLiteral("SettingsUpdateStatus"));
    updateStatusLabel_->setWordWrap(true);
    aboutLayout->addWidget(updateStatusLabel_);
    QObject::connect(checkUpdatesButton_, &QPushButton::clicked, this, [this]() {
        checkUpdatesButton_->setEnabled(false);
        updateStatusLabel_->setText(QStringLiteral("Checking..."));
        emit checkForUpdatesRequested();
    });
    QObject::connect(openReleaseButton_, &QPushButton::clicked, this, [this]() {
        const QString url = latestReleaseUrl_.isEmpty() ? spellvision::shell::releasesPageUrl() : latestReleaseUrl_;
        QDesktopServices::openUrl(QUrl(url));
    });
    rootLayout_->addWidget(aboutCard);

    auto *themeCard = createSectionCard(
        QStringLiteral("Theme Presets"),
        QStringLiteral("Arcane Glass, Obsidian Studio, Neon Forge, and Ivory Holograph are stored in settings and can be switched at any time."));
    auto *themeLayout = qobject_cast<QVBoxLayout *>(themeCard->layout());

    themePresetCombo_ = new QComboBox(themeCard);
    themePresetCombo_->addItems(ThemeManager::instance().presetNames());

    currentPresetValue_ = new QLabel(QStringLiteral("Current preset: Arcane Glass"), themeCard);
    currentPresetValue_->setObjectName(QStringLiteral("SettingsValueChip"));

    themeLayout->addWidget(themePresetCombo_);
    themeLayout->addWidget(currentPresetValue_);
    rootLayout_->addWidget(themeCard);

    auto *styleCard = createSectionCard(
        QStringLiteral("Surface Style"),
        QStringLiteral("What panels are made of, independent of their colours. The preset picks the "
                       "palette; the style picks the material, so every style works with every "
                       "preset. Matte is also the cheapest to draw."));
    auto *styleLayout = qobject_cast<QVBoxLayout *>(styleCard->layout());

    surfaceStyleCombo_ = new QComboBox(styleCard);
    surfaceStyleCombo_->addItems(ThemeManager::instance().styleNames());
    // Set before connecting, so initialising the combo does not fire a change and re-save.
    surfaceStyleCombo_->setCurrentIndex(static_cast<int>(ThemeManager::instance().style()));

    surfaceStyleDescLabel_ = new QLabel(
        ThemeManager::instance().styleDescription(ThemeManager::instance().style()), styleCard);
    surfaceStyleDescLabel_->setObjectName(QStringLiteral("SettingsValueChip"));
    surfaceStyleDescLabel_->setWordWrap(true);

    styleLayout->addWidget(surfaceStyleCombo_);
    styleLayout->addWidget(surfaceStyleDescLabel_);
    rootLayout_->addWidget(styleCard);

    auto *accentCard = createSectionCard(
        QStringLiteral("Accent Color"),
        QStringLiteral("Leave preset accent on for curated color matching, or choose your own accent color for a custom identity."));
    auto *accentLayout = qobject_cast<QVBoxLayout *>(accentCard->layout());

    usePresetAccentCheck_ = new QCheckBox(QStringLiteral("Use preset accent color"), accentCard);
    usePresetAccentCheck_->setChecked(true);

    auto *accentButtonRow = new QHBoxLayout;
    accentButtonRow->setContentsMargins(0, 0, 0, 0);
    accentButtonRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

    chooseAccentButton_ = new QPushButton(QStringLiteral("Choose Accent Color"), accentCard);
    presetAccentPreview_ = new QLabel(QStringLiteral("Preset Accent"), accentCard);
    presetAccentPreview_->setObjectName(QStringLiteral("AccentPreview"));
    presetAccentPreview_->setAlignment(Qt::AlignCenter);

    accentButtonRow->addWidget(chooseAccentButton_, 0);
    accentButtonRow->addWidget(presetAccentPreview_, 1);

    accentLayout->addWidget(usePresetAccentCheck_);
    accentLayout->addLayout(accentButtonRow);
    rootLayout_->addWidget(accentCard);

    auto *effectsCard = createSectionCard(
        QStringLiteral("Effects Intensity"),
        QStringLiteral("This adjusts glow, border energy, gradient richness, and glass weight while keeping the UI tasteful."));
    auto *effectsLayout = qobject_cast<QVBoxLayout *>(effectsCard->layout());

    auto *effectsSliderRow = new QHBoxLayout;
    effectsSliderRow->setContentsMargins(0, 0, 0, 0);
    effectsSliderRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    effectsSlider_ = new QSlider(Qt::Horizontal, effectsCard);
    effectsSlider_->setRange(0, 100);
    effectsSlider_->setValue(68);

    effectsValueLabel_ = new QLabel(QStringLiteral("68%"), effectsCard);
    effectsValueLabel_->setObjectName(QStringLiteral("EffectsValue"));

    effectsSliderRow->addWidget(effectsSlider_, 1);
    effectsSliderRow->addWidget(effectsValueLabel_, 0);

    restoreDefaultsButton_ = new QPushButton(QStringLiteral("Restore Default Theme"), effectsCard);

    auto *restoreButtonRow = new QHBoxLayout;
    restoreButtonRow->setContentsMargins(0, 0, 0, 0);
    restoreButtonRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    restoreButtonRow->addStretch(1);
    restoreButtonRow->addWidget(restoreDefaultsButton_);

    effectsLayout->addLayout(effectsSliderRow);
    effectsLayout->addLayout(restoreButtonRow);
    rootLayout_->addWidget(effectsCard);

    auto *animationCard = createSectionCard(
        QStringLiteral("Animation Quality"),
        QStringLiteral("How much motion and visual flourish the UI shows. Lower tiers cost less CPU/GPU -- drop to Minimal on weak hardware or on battery. Applies to the progress bar today, and to glass and other animated surfaces as they adopt it. Independent of the theme."));
    auto *animationLayout = qobject_cast<QVBoxLayout *>(animationCard->layout());

    animationQualityCombo_ = new QComboBox(animationCard);
    animationQualityCombo_->addItems(ThemeManager::instance().animationQualityNames());
    // Set the current tier BEFORE the change-signal is connected (below), so init doesn't fire it.
    animationQualityCombo_->setCurrentIndex(static_cast<int>(ThemeManager::instance().animationQuality()));

    animationQualityDescLabel_ = new QLabel(
        ThemeManager::instance().animationQualityDescription(ThemeManager::instance().animationQuality()),
        animationCard);
    animationQualityDescLabel_->setObjectName(QStringLiteral("SettingsValueChip"));
    animationQualityDescLabel_->setWordWrap(true);

    animationLayout->addWidget(animationQualityCombo_);
    animationLayout->addWidget(animationQualityDescLabel_);
    rootLayout_->addWidget(animationCard);

    auto *dashboardCard = createSectionCard(
        QStringLiteral("Home Dashboard"),
        QStringLiteral("Choose a starting layout, set density, toggle modules, then jump into Home customize mode to move and resize the dashboard."));
    auto *dashboardLayout = qobject_cast<QVBoxLayout *>(dashboardCard->layout());

    auto *presetRow = new QHBoxLayout;
    presetRow->setContentsMargins(0, 0, 0, 0);
    presetRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    auto *presetColumn = new QVBoxLayout;
    presetColumn->setContentsMargins(0, 0, 0, 0);
    presetColumn->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    presetColumn->addWidget(createBodyLabel(QStringLiteral("Layout preset")));

    dashboardPresetCombo_ = new QComboBox(dashboardCard);
    dashboardPresetCombo_->addItem(dashboardPresetLabel(HomeDashboardPreset::CinematicStudio), static_cast<int>(HomeDashboardPreset::CinematicStudio));
    dashboardPresetCombo_->addItem(dashboardPresetLabel(HomeDashboardPreset::ProductiveCompact), static_cast<int>(HomeDashboardPreset::ProductiveCompact));
    dashboardPresetCombo_->addItem(dashboardPresetLabel(HomeDashboardPreset::MotionWorkspace), static_cast<int>(HomeDashboardPreset::MotionWorkspace));
    dashboardPresetCombo_->addItem(dashboardPresetLabel(HomeDashboardPreset::ModelOps), static_cast<int>(HomeDashboardPreset::ModelOps));
    dashboardPresetCombo_->addItem(dashboardPresetLabel(HomeDashboardPreset::Minimal), static_cast<int>(HomeDashboardPreset::Minimal));
    presetColumn->addWidget(dashboardPresetCombo_);

    auto *densityColumn = new QVBoxLayout;
    densityColumn->setContentsMargins(0, 0, 0, 0);
    densityColumn->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    densityColumn->addWidget(createBodyLabel(QStringLiteral("Density")));

    dashboardDensityCombo_ = new QComboBox(dashboardCard);
    dashboardDensityCombo_->addItem(dashboardDensityLabel(HomeDashboardDensity::Compact), static_cast<int>(HomeDashboardDensity::Compact));
    dashboardDensityCombo_->addItem(dashboardDensityLabel(HomeDashboardDensity::Comfortable), static_cast<int>(HomeDashboardDensity::Comfortable));
    dashboardDensityCombo_->addItem(dashboardDensityLabel(HomeDashboardDensity::Cinematic), static_cast<int>(HomeDashboardDensity::Cinematic));
    densityColumn->addWidget(dashboardDensityCombo_);

    presetRow->addLayout(presetColumn, 1);
    presetRow->addLayout(densityColumn, 1);
    dashboardLayout->addLayout(presetRow);

    dashboardLayout->addWidget(createBodyLabel(QStringLiteral("Visible modules")));

    auto *moduleChecksHost = new QWidget(dashboardCard);
    auto *moduleChecksLayout = new QHBoxLayout(moduleChecksHost);
    moduleChecksLayout->setContentsMargins(0, 0, 0, 0);
    moduleChecksLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Card));

    auto *leftColumn = new QVBoxLayout;
    leftColumn->setContentsMargins(0, 0, 0, 0);
    leftColumn->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    auto *rightColumn = new QVBoxLayout;
    rightColumn->setContentsMargins(0, 0, 0, 0);
    rightColumn->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

    const QString moduleIds[] = {
        HomeDashboardIds::HeroLauncher,
        HomeDashboardIds::WorkflowLauncher,
        HomeDashboardIds::RecentOutputs,
        HomeDashboardIds::Favorites,
        HomeDashboardIds::ActiveModels
    };

    for (int i = 0; i < 5; ++i)
    {
        auto *check = new QCheckBox(moduleDisplayName(moduleIds[i]), moduleChecksHost);
        dashboardModuleChecks_.insert(moduleIds[i], check);
        if (i < 3)
            leftColumn->addWidget(check);
        else
            rightColumn->addWidget(check);
    }
    leftColumn->addStretch(1);
    rightColumn->addStretch(1);
    moduleChecksLayout->addLayout(leftColumn, 1);
    moduleChecksLayout->addLayout(rightColumn, 1);
    dashboardLayout->addWidget(moduleChecksHost);

    auto *dashboardActions = new QHBoxLayout;
    dashboardActions->setContentsMargins(0, 0, 0, 0);
    dashboardActions->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

    resetDashboardLayoutButton_ = new QPushButton(QStringLiteral("Reset Home Layout"), dashboardCard);
    customizeHomeButton_ = new QPushButton(QStringLiteral("Customize on Home"), dashboardCard);

    dashboardActions->addWidget(resetDashboardLayoutButton_, 0);
    dashboardActions->addWidget(customizeHomeButton_, 0);
    dashboardActions->addStretch(1);
    dashboardLayout->addLayout(dashboardActions);

    previewCard_ = new QFrame(contentWidget_);
    previewCard_->setObjectName(QStringLiteral("SettingsPreviewPanel"));
    auto *previewLayout = new QVBoxLayout(previewCard_);
    previewLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    previewLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    previewTitleLabel_ = new QLabel(QStringLiteral("Live Theme Preview"), previewCard_);
    previewTitleLabel_->setObjectName(QStringLiteral("SettingsPreviewHeader"));
    previewBodyLabel_ = new QLabel(QStringLiteral("Accent, depth, and control contrast update instantly when the preset changes."), previewCard_);
    previewBodyLabel_->setObjectName(QStringLiteral("SettingsPreviewBody"));
    previewBodyLabel_->setWordWrap(true);

    auto *chipRow = new QHBoxLayout;
    chipRow->setContentsMargins(0, 0, 0, 0);
    chipRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    previewChipActive_ = new QLabel(QStringLiteral("Active"), previewCard_);
    previewChipIdle_ = new QLabel(QStringLiteral("Secondary"), previewCard_);
    chipRow->addWidget(previewChipActive_, 0);
    chipRow->addWidget(previewChipIdle_, 0);
    chipRow->addStretch(1);

    auto *buttonRow = new QHBoxLayout;
    buttonRow->setContentsMargins(0, 0, 0, 0);
    buttonRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
    previewPrimaryButton_ = new QPushButton(QStringLiteral("Primary Action"), previewCard_);
    previewSecondaryButton_ = new QPushButton(QStringLiteral("Secondary"), previewCard_);
    buttonRow->addWidget(previewPrimaryButton_, 0);
    buttonRow->addWidget(previewSecondaryButton_, 0);
    buttonRow->addStretch(1);

    previewLayout->addWidget(previewTitleLabel_);
    previewLayout->addWidget(previewBodyLabel_);
    previewLayout->addLayout(chipRow);
    previewLayout->addLayout(buttonRow);
    rootLayout_->addWidget(dashboardCard);
    rootLayout_->addWidget(previewCard_);
    rootLayout_->addStretch(1);

    connect(themePresetCombo_, &QComboBox::currentTextChanged, this, [this](const QString &text) {
        setCurrentPresetSummary(QStringLiteral("Current preset: %1").arg(text));
        emit presetChanged(text);
    });
    connect(usePresetAccentCheck_, &QCheckBox::toggled, this, &SettingsPage::usePresetAccentChanged);
    connect(chooseAccentButton_, &QPushButton::clicked, this, &SettingsPage::chooseAccentColorRequested);
    connect(effectsSlider_, &QSlider::valueChanged, this, [this](int value) {
        updateEffectsValueLabel(value);
        emit effectsWeightChanged(value);
    });
    connect(restoreDefaultsButton_, &QPushButton::clicked, this, &SettingsPage::restoreDefaultsRequested);

    // Animation quality drives ThemeManager directly (a global setting, not theme-specific);
    // consumers react to animationQualityChanged. Update the per-tier explanation inline.
    connect(animationQualityCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this, [this](int index) {
        auto &theme = ThemeManager::instance();
        theme.setAnimationQualityByIndex(index);
        if (animationQualityDescLabel_)
            animationQualityDescLabel_->setText(
                theme.animationQualityDescription(static_cast<ThemeManager::AnimationQuality>(index)));
    });

    // Surface style is a theme mutation (it rewrites the material tokens), so it goes through
    // setStyleByIndex and every subscriber repaints off the existing themeChanged signal.
    connect(surfaceStyleCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this, [this](int index) {
        auto &theme = ThemeManager::instance();
        theme.setStyleByIndex(index);
        if (surfaceStyleDescLabel_)
            surfaceStyleDescLabel_->setText(theme.styleDescription(static_cast<ThemeManager::Style>(index)));
    });

    // User-only: activated fires on interaction, not on the programmatic setCurrentIndex in
    // setDisclosureMode -- so reflecting the title-bar toggle here never loops back.
    connect(disclosureModeCombo_, qOverload<int>(&QComboBox::activated), this, [this](int index) {
        emit disclosureModeChangeRequested(disclosureModeCombo_->itemData(index).toBool());
    });

    connect(dashboardPresetCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this, [this](int) {
        if (updatingHomeDashboardUi_)
            return;
        updateHomeDashboardPreset(selectedHomeDashboardPreset());
        emitHomeDashboardConfigChanged();
    });
    connect(dashboardDensityCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this, [this](int) {
        if (updatingHomeDashboardUi_)
            return;
        updateHomeDashboardDensity(selectedHomeDashboardDensity());
        emitHomeDashboardConfigChanged();
    });

    for (auto it = dashboardModuleChecks_.begin(); it != dashboardModuleChecks_.end(); ++it)
    {
        const QString moduleId = it.key();
        connect(it.value(), &QCheckBox::toggled, this, [this, moduleId](bool checked) {
            if (updatingHomeDashboardUi_)
                return;
            setModuleVisibility(moduleId, checked);
            emitHomeDashboardConfigChanged();
        });
    }

    connect(resetDashboardLayoutButton_, &QPushButton::clicked, this, [this]() {
        if (updatingHomeDashboardUi_)
            return;

        homeDashboardState_ = defaultHomeDashboardConfig(selectedHomeDashboardPreset());
        homeDashboardState_.density = selectedHomeDashboardDensity();
        syncHomeDashboardUi();
        emitHomeDashboardConfigChanged();
    });
    connect(customizeHomeButton_, &QPushButton::clicked, this, &SettingsPage::homeDashboardCustomizeRequested);

    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &SettingsPage::applyTheme);

    setHomeDashboardConfig(homeDashboardState_);
}

QString SettingsPage::currentPreset() const
{
    return themePresetCombo_ ? themePresetCombo_->currentText() : QString();
}

void SettingsPage::setCurrentPreset(const QString &presetName)
{
    if (!themePresetCombo_)
        return;

    const QSignalBlocker blocker(themePresetCombo_);
    const int index = themePresetCombo_->findText(presetName);
    if (index >= 0)
        themePresetCombo_->setCurrentIndex(index);

    setCurrentPresetSummary(QStringLiteral("Current preset: %1").arg(currentPreset()));
}

bool SettingsPage::usePresetAccent() const
{
    return usePresetAccentCheck_ ? usePresetAccentCheck_->isChecked() : true;
}

void SettingsPage::setUsePresetAccent(bool usePresetAccent)
{
    if (!usePresetAccentCheck_)
        return;
    const QSignalBlocker blocker(usePresetAccentCheck_);
    usePresetAccentCheck_->setChecked(usePresetAccent);
}

int SettingsPage::effectsWeight() const
{
    return effectsSlider_ ? effectsSlider_->value() : 0;
}

void SettingsPage::setEffectsWeight(int value)
{
    if (!effectsSlider_)
        return;

    const QSignalBlocker blocker(effectsSlider_);
    effectsSlider_->setValue(value);
    updateEffectsValueLabel(value);
}

void SettingsPage::setDisclosureMode(bool advanced)
{
    if (!disclosureModeCombo_)
        return;

    // QSignalBlocker (belt-and-suspenders alongside the activated-only connect) so reflecting the
    // title-bar toggle never re-emits disclosureModeChangeRequested.
    const QSignalBlocker blocker(disclosureModeCombo_);
    const int index = disclosureModeCombo_->findData(advanced);
    if (index >= 0)
        disclosureModeCombo_->setCurrentIndex(index);
}

void SettingsPage::setPresetAccentPreviewCss(const QString &css)
{
    if (!presetAccentPreview_)
        return;

    presetAccentPreview_->setStyleSheet(css);
}

void SettingsPage::setCurrentPresetSummary(const QString &text)
{
    if (currentPresetValue_)
        currentPresetValue_->setText(text);
}

void SettingsPage::refreshThemePreview()
{
    applyTheme();
}

void SettingsPage::setHomeDashboardConfig(const HomeDashboardConfig &config)
{
    homeDashboardState_ = isValidHomeDashboardConfig(config)
        ? config
        : defaultHomeDashboardConfig(HomeDashboardPreset::CinematicStudio);
    syncHomeDashboardUi();
}

HomeDashboardConfig SettingsPage::homeDashboardConfig() const
{
    return homeDashboardState_;
}

QFrame *SettingsPage::createSectionCard(const QString &title, const QString &subtitle)
{
    auto *card = new QFrame(contentWidget_);
    card->setObjectName(QStringLiteral("SettingsCard"));

    auto *layout = new QVBoxLayout(card);
    layout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    auto *titleLabel = new QLabel(title, card);
    titleLabel->setObjectName(QStringLiteral("SettingsSectionTitle"));

    auto *subtitleLabel = createBodyLabel(subtitle);
    subtitleLabel->setParent(card);

    layout->addWidget(titleLabel);
    layout->addWidget(subtitleLabel);

    return card;
}

QLabel *SettingsPage::createBodyLabel(const QString &text)
{
    auto *label = new QLabel(text);
    label->setObjectName(QStringLiteral("SettingsBody"));
    label->setWordWrap(true);
    return label;
}

void SettingsPage::updateEffectsValueLabel(int value)
{
    if (effectsValueLabel_)
        effectsValueLabel_->setText(QStringLiteral("%1%").arg(value));
}

void SettingsPage::applyTheme()
{
    auto &theme = ThemeManager::instance();
    setStyleSheet(theme.settingsStyleSheet());
    setCurrentPreset(theme.presetName());
    setUsePresetAccent(theme.usePresetAccent());
    setEffectsWeight(theme.effectsWeight());
    setCurrentPresetSummary(QStringLiteral("Current preset: %1").arg(theme.presetName()));
    setPresetAccentPreviewCss(theme.accentGradientStyle() + QStringLiteral("color:%1; font-weight:700;").arg(theme.textPrimaryColor().name()));

    if (previewCard_)
        previewCard_->setStyleSheet(theme.settingsPreviewCardStyle());
    if (previewChipActive_)
        previewChipActive_->setStyleSheet(theme.settingsPreviewChipStyle(true));
    if (previewChipIdle_)
        previewChipIdle_->setStyleSheet(theme.settingsPreviewChipStyle(false));
    if (previewPrimaryButton_)
        previewPrimaryButton_->setStyleSheet(theme.settingsPreviewButtonStyle(true));
    if (previewSecondaryButton_)
        previewSecondaryButton_->setStyleSheet(theme.settingsPreviewButtonStyle(false));
    if (chooseAccentButton_)
        chooseAccentButton_->setEnabled(!theme.usePresetAccent());
}

void SettingsPage::syncHomeDashboardUi()
{
    updatingHomeDashboardUi_ = true;

    if (dashboardPresetCombo_)
    {
        const int index = dashboardPresetCombo_->findData(static_cast<int>(homeDashboardState_.preset));
        if (index >= 0)
            dashboardPresetCombo_->setCurrentIndex(index);
    }

    if (dashboardDensityCombo_)
    {
        const int index = dashboardDensityCombo_->findData(static_cast<int>(homeDashboardState_.density));
        if (index >= 0)
            dashboardDensityCombo_->setCurrentIndex(index);
    }

    for (auto it = dashboardModuleChecks_.begin(); it != dashboardModuleChecks_.end(); ++it)
    {
        bool visible = false;
        for (const HomeModulePlacement &placement : homeDashboardState_.placements)
        {
            if (placement.moduleId == it.key())
            {
                visible = placement.visible;
                break;
            }
        }

        const QSignalBlocker blocker(it.value());
        it.value()->setChecked(visible);
    }

    updatingHomeDashboardUi_ = false;
}

void SettingsPage::emitHomeDashboardConfigChanged()
{
    if (!isValidHomeDashboardConfig(homeDashboardState_))
        homeDashboardState_ = defaultHomeDashboardConfig(HomeDashboardPreset::CinematicStudio);

    emit homeDashboardConfigChanged(homeDashboardState_);
}

HomeDashboardPreset SettingsPage::selectedHomeDashboardPreset() const
{
    if (!dashboardPresetCombo_)
        return HomeDashboardPreset::CinematicStudio;
    return static_cast<HomeDashboardPreset>(dashboardPresetCombo_->currentData().toInt());
}

HomeDashboardDensity SettingsPage::selectedHomeDashboardDensity() const
{
    if (!dashboardDensityCombo_)
        return HomeDashboardDensity::Comfortable;
    return static_cast<HomeDashboardDensity>(dashboardDensityCombo_->currentData().toInt());
}

void SettingsPage::updateHomeDashboardPreset(HomeDashboardPreset preset)
{
    const HomeDashboardDensity density = selectedHomeDashboardDensity();
    homeDashboardState_ = defaultHomeDashboardConfig(preset);
    homeDashboardState_.density = density;
    syncHomeDashboardUi();
}

void SettingsPage::updateHomeDashboardDensity(HomeDashboardDensity density)
{
    homeDashboardState_.density = density;
}

void SettingsPage::setModuleVisibility(const QString &moduleId, bool visible)
{
    for (HomeModulePlacement &placement : homeDashboardState_.placements)
    {
        if (placement.moduleId == moduleId)
        {
            placement.visible = visible;
            return;
        }
    }

    if (!isKnownHomeModuleId(moduleId))
        return;

    const HomeDashboardConfig defaults = defaultHomeDashboardConfig(homeDashboardState_.preset);
    for (const HomeModulePlacement &placement : defaults.placements)
    {
        if (placement.moduleId != moduleId)
            continue;

        HomeModulePlacement restored = placement;
        restored.visible = visible;
        homeDashboardState_.placements.append(restored);
        return;
    }
}

void SettingsPage::showUpdateCheckResult(const QString &status, const QString &releaseUrl)
{
    if (updateStatusLabel_)
        updateStatusLabel_->setText(status);
    latestReleaseUrl_ = releaseUrl.trimmed();
    if (openReleaseButton_)
        openReleaseButton_->setEnabled(!latestReleaseUrl_.isEmpty());
    if (checkUpdatesButton_)
        checkUpdatesButton_->setEnabled(true);
}
