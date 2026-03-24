#pragma once

#include <QWidget>
#include <QJsonObject>

class QComboBox;
class QSpinBox;
class QDoubleSpinBox;
class QLineEdit;
class QTextEdit;
class QPushButton;
class QLabel;
class QProgressBar;
class QGroupBox;

class VideoGenerationPage : public QWidget
{
    Q_OBJECT

public:
    explicit VideoGenerationPage(QWidget *parent = nullptr);

signals:
    void generateRequested(const QJsonObject &payload);

private:
    void buildUi();
    void refreshPreview();
    void updateVideoSettings();

    // UI elements
    QComboBox *videoModelCombo_ = nullptr;
    QSpinBox *fpsSpin_ = nullptr;
    QSpinBox *numFramesSpin_ = nullptr;
    QSpinBox *videoWidthSpin_ = nullptr;
    QSpinBox *videoHeightSpin_ = nullptr;
    QDoubleSpinBox *videoStrengthSpin_ = nullptr;
    QComboBox *videoSamplerCombo_ = nullptr;
    QLineEdit *videoPromptEdit_ = nullptr;
    QTextEdit *videoNegativePromptEdit_ = nullptr;
    QPushButton *generateVideoButton_ = nullptr;
    QPushButton *previewVideoButton_ = nullptr;
    QLabel *videoPreviewLabel_ = nullptr;
    QProgressBar *videoProgress_ = nullptr;
};
