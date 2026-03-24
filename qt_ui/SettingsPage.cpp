#include "SettingsPage.h"

#include "ThemeManager.h"

#include <QCheckBox>
#include <QComboBox>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QSignalBlocker>
#include <QSlider>
#include <QVBoxLayout>

SettingsPage::SettingsPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("SettingsPage"));

    rootLayout_ = new QVBoxLayout(this);
    rootLayout_->setContentsMargins(18, 14, 18, 18);
    rootLayout_->setSpacing(12);

    auto *titleLabel = new QLabel(QStringLiteral("Appearance Settings"), this);
    titleLabel->setObjectName(QStringLiteral("SettingsTitle"));

    auto *subtitleLabel = new QLabel(
        QStringLiteral("Choose between four premium theme presets, then tune accent color and effect intensity without breaking the overall visual direction."),
        this);
    subtitleLabel->setObjectName(QStringLiteral("SettingsSubtitle"));
    subtitleLabel->setWordWrap(true);

    rootLayout_->addWidget(titleLabel);
    rootLayout_->addWidget(subtitleLabel);

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

    auto *accentCard = createSectionCard(
        QStringLiteral("Accent Color"),
        QStringLiteral("Leave preset accent on for curated color matching, or choose your own accent color for a custom identity."));
    auto *accentLayout = qobject_cast<QVBoxLayout *>(accentCard->layout());

    usePresetAccentCheck_ = new QCheckBox(QStringLiteral("Use preset accent color"), accentCard);
    usePresetAccentCheck_->setChecked(true);

    auto *accentButtonRow = new QHBoxLayout;
    accentButtonRow->setContentsMargins(0, 0, 0, 0);
    accentButtonRow->setSpacing(8);

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
    effectsSliderRow->setSpacing(12);

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
    restoreButtonRow->setSpacing(8);
    restoreButtonRow->addStretch(1);
    restoreButtonRow->addWidget(restoreDefaultsButton_);

    effectsLayout->addLayout(effectsSliderRow);
    effectsLayout->addLayout(restoreButtonRow);
    rootLayout_->addWidget(effectsCard);

    previewCard_ = new QFrame(this);
    previewCard_->setObjectName(QStringLiteral("SettingsPreviewPanel"));
    auto *previewLayout = new QVBoxLayout(previewCard_);
    previewLayout->setContentsMargins(14, 14, 14, 14);
    previewLayout->setSpacing(10);

    previewTitleLabel_ = new QLabel(QStringLiteral("Live Theme Preview"), previewCard_);
    previewTitleLabel_->setObjectName(QStringLiteral("SettingsPreviewHeader"));
    previewBodyLabel_ = new QLabel(QStringLiteral("Accent, depth, and control contrast update instantly when the preset changes."), previewCard_);
    previewBodyLabel_->setObjectName(QStringLiteral("SettingsPreviewBody"));
    previewBodyLabel_->setWordWrap(true);

    auto *chipRow = new QHBoxLayout;
    chipRow->setContentsMargins(0, 0, 0, 0);
    chipRow->setSpacing(8);
    previewChipActive_ = new QLabel(QStringLiteral("Active"), previewCard_);
    previewChipIdle_ = new QLabel(QStringLiteral("Secondary"), previewCard_);
    chipRow->addWidget(previewChipActive_, 0);
    chipRow->addWidget(previewChipIdle_, 0);
    chipRow->addStretch(1);

    auto *buttonRow = new QHBoxLayout;
    buttonRow->setContentsMargins(0, 0, 0, 0);
    buttonRow->setSpacing(8);
    previewPrimaryButton_ = new QPushButton(QStringLiteral("Primary Action"), previewCard_);
    previewSecondaryButton_ = new QPushButton(QStringLiteral("Secondary"), previewCard_);
    buttonRow->addWidget(previewPrimaryButton_, 0);
    buttonRow->addWidget(previewSecondaryButton_, 0);
    buttonRow->addStretch(1);

    previewLayout->addWidget(previewTitleLabel_);
    previewLayout->addWidget(previewBodyLabel_);
    previewLayout->addLayout(chipRow);
    previewLayout->addLayout(buttonRow);
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

    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &SettingsPage::applyTheme);
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

QFrame *SettingsPage::createSectionCard(const QString &title, const QString &subtitle)
{
    auto *card = new QFrame(this);
    card->setObjectName(QStringLiteral("SettingsCard"));

    auto *layout = new QVBoxLayout(card);
    layout->setContentsMargins(14, 14, 14, 14);
    layout->setSpacing(10);

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
