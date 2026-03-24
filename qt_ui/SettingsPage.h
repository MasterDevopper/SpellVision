#pragma once

#include <QWidget>

class QCheckBox;
class QComboBox;
class QFrame;
class QLabel;
class QPushButton;
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

signals:
    void presetChanged(const QString &presetName);
    void usePresetAccentChanged(bool enabled);
    void chooseAccentColorRequested();
    void effectsWeightChanged(int value);
    void restoreDefaultsRequested();

private:
    QFrame *createSectionCard(const QString &title, const QString &subtitle);
    QLabel *createBodyLabel(const QString &text);
    void updateEffectsValueLabel(int value);
    void applyTheme();

private:
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
};
