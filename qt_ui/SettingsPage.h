#pragma once

#include "HomeDashboardTypes.h"

#include <QMap>
#include <QWidget>

class QCheckBox;
class QComboBox;
class QFrame;
class QLabel;
class QPushButton;
class QScrollArea;
class QSlider;
class QVBoxLayout;

class SettingsPage : public QWidget
{
    Q_OBJECT

public:
    explicit SettingsPage(QWidget *parent = nullptr);

    QString currentPreset() const;
    void setCurrentPreset(const QString &presetName);

    bool usePresetAccent() const;
    void setUsePresetAccent(bool usePresetAccent);

    int effectsWeight() const;
    void setEffectsWeight(int value);

    void setPresetAccentPreviewCss(const QString &css);
    void setCurrentPresetSummary(const QString &text);
    void refreshThemePreview();

    void setHomeDashboardConfig(const HomeDashboardConfig &config);
    HomeDashboardConfig homeDashboardConfig() const;

signals:
    void presetChanged(const QString &presetName);
    void usePresetAccentChanged(bool enabled);
    void chooseAccentColorRequested();
    void effectsWeightChanged(int value);
    void restoreDefaultsRequested();

    void homeDashboardConfigChanged(const HomeDashboardConfig &config);
    void homeDashboardCustomizeRequested();

private:
    QFrame *createSectionCard(const QString &title, const QString &subtitle);
    QLabel *createBodyLabel(const QString &text);
    void updateEffectsValueLabel(int value);
    void applyTheme();

    void syncHomeDashboardUi();
    void emitHomeDashboardConfigChanged();
    HomeDashboardPreset selectedHomeDashboardPreset() const;
    HomeDashboardDensity selectedHomeDashboardDensity() const;
    void updateHomeDashboardPreset(HomeDashboardPreset preset);
    void updateHomeDashboardDensity(HomeDashboardDensity density);
    void setModuleVisibility(const QString &moduleId, bool visible);

private:
    QScrollArea *scrollArea_ = nullptr;
    QWidget *contentWidget_ = nullptr;
    QVBoxLayout *rootLayout_ = nullptr;

    QComboBox *themePresetCombo_ = nullptr;
    QLabel *currentPresetValue_ = nullptr;

    QCheckBox *usePresetAccentCheck_ = nullptr;
    QPushButton *chooseAccentButton_ = nullptr;
    QLabel *presetAccentPreview_ = nullptr;

    QSlider *effectsSlider_ = nullptr;
    QLabel *effectsValueLabel_ = nullptr;
    QPushButton *restoreDefaultsButton_ = nullptr;

    QFrame *previewCard_ = nullptr;
    QLabel *previewTitleLabel_ = nullptr;
    QLabel *previewBodyLabel_ = nullptr;
    QLabel *previewChipActive_ = nullptr;
    QLabel *previewChipIdle_ = nullptr;
    QPushButton *previewPrimaryButton_ = nullptr;
    QPushButton *previewSecondaryButton_ = nullptr;

    QComboBox *dashboardPresetCombo_ = nullptr;
    QComboBox *dashboardDensityCombo_ = nullptr;
    QMap<QString, QCheckBox *> dashboardModuleChecks_;
    QPushButton *resetDashboardLayoutButton_ = nullptr;
    QPushButton *customizeHomeButton_ = nullptr;

    HomeDashboardConfig homeDashboardState_ = defaultHomeDashboardConfig(HomeDashboardPreset::CinematicStudio);
    bool updatingHomeDashboardUi_ = false;
};
