#include "VideoGenerationPage.h"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGridLayout>
#include <QLabel>
#include <QLineEdit>
#include <QTextEdit>
#include <QSpinBox>
#include <QDoubleSpinBox>
#include <QPushButton>
#include <QComboBox>
#include <QProgressBar>
#include <QGroupBox>
#include <QScrollArea>
#include <QApplication>
#include <QTimer>
#include <QJsonObject>

VideoGenerationPage::VideoGenerationPage(QWidget *parent)
    : QWidget(parent)
{
    buildUi();
}

void VideoGenerationPage::buildUi()
{
    if (!parent())
        return;

    auto *mainLayout = new QVBoxLayout(this);

    // Video Generation Controls
    auto *controlsGroup = new QGroupBox(QStringLiteral("Video Generation Controls"));
    auto *controlsLayout = new QVBoxLayout(controlsGroup);

    auto *videoSettingsLayout = new QGridLayout();

    // Model selection
    auto *modelLabel = new QLabel(QStringLiteral("Model:"));
    videoModelCombo_ = new QComboBox(this);
    videoModelCombo_->addItem(QStringLiteral("SDXL Video"));
    videoModelCombo_->addItem(QStringLiteral("LTX Video"));
    videoModelCombo_->addItem(QStringLiteral("CogVideoX"));
    videoModelCombo_->addItem(QStringLiteral("Hunyuan Video"));
    videoModelCombo_->addItem(QStringLiteral("Mochi Video"));

    videoSettingsLayout->addWidget(modelLabel, 0, 0);
    videoSettingsLayout->addWidget(videoModelCombo_, 0, 1);

    // FPS
    auto *fpsLabel = new QLabel(QStringLiteral("FPS:"));
    fpsSpin_ = new QSpinBox(this);
    fpsSpin_->setRange(1, 60);
    fpsSpin_->setValue(24);

    videoSettingsLayout->addWidget(fpsLabel, 1, 0);
    videoSettingsLayout->addWidget(fpsSpin_, 1, 1);

    // Number of frames
    auto *framesLabel = new QLabel(QStringLiteral("Frames:"));
    numFramesSpin_ = new QSpinBox(this);
    numFramesSpin_->setRange(1, 1000);
    numFramesSpin_->setValue(16);

    videoSettingsLayout->addWidget(framesLabel, 2, 0);
    videoSettingsLayout->addWidget(numFramesSpin_, 2, 1);

    // Width
    auto *widthLabel = new QLabel(QStringLiteral("Width:"));
    videoWidthSpin_ = new QSpinBox(this);
    videoWidthSpin_->setRange(128, 2048);
    videoWidthSpin_->setValue(512);

    videoSettingsLayout->addWidget(widthLabel, 3, 0);
    videoSettingsLayout->addWidget(videoWidthSpin_, 3, 1);

    // Height
    auto *heightLabel = new QLabel(QStringLiteral("Height:"));
    videoHeightSpin_ = new QSpinBox(this);
    videoHeightSpin_->setRange(128, 2048);
    videoHeightSpin_->setValue(512);

    videoSettingsLayout->addWidget(heightLabel, 4, 0);
    videoSettingsLayout->addWidget(videoHeightSpin_, 4, 1);

    // Strength
    auto *strengthLabel = new QLabel(QStringLiteral("Strength:"));
    videoStrengthSpin_ = new QDoubleSpinBox(this);
    videoStrengthSpin_->setRange(0.0, 1.0);
    videoStrengthSpin_->setSingleStep(0.1);
    videoStrengthSpin_->setValue(0.6);

    videoSettingsLayout->addWidget(strengthLabel, 5, 0);
    videoSettingsLayout->addWidget(videoStrengthSpin_, 5, 1);

    // Sampler
    auto *samplerLabel = new QLabel(QStringLiteral("Sampler:"));
    videoSamplerCombo_ = new QComboBox(this);
    videoSamplerCombo_->addItem(QStringLiteral("Euler"));
    videoSamplerCombo_->addItem(QStringLiteral("DPM++ 2M"));
    videoSamplerCombo_->addItem(QStringLiteral("DPM++ SDE"));
    videoSamplerCombo_->addItem(QStringLiteral("DDIM"));
    videoSamplerCombo_->addItem(QStringLiteral("UniPC"));

    videoSettingsLayout->addWidget(samplerLabel, 6, 0);
    videoSettingsLayout->addWidget(videoSamplerCombo_, 6, 1);

    controlsLayout->addLayout(videoSettingsLayout);

    // Prompt and negative prompt
    auto *promptGroup = new QGroupBox(QStringLiteral("Prompts"));
    auto *promptLayout = new QVBoxLayout(promptGroup);

    auto *promptLabel = new QLabel(QStringLiteral("Prompt:"));
    videoPromptEdit_ = new QLineEdit(this);
    videoPromptEdit_->setText(QStringLiteral("A beautiful animated scene"));

    promptLayout->addWidget(promptLabel);
    promptLayout->addWidget(videoPromptEdit_);

    auto *negativeLabel = new QLabel(QStringLiteral("Negative Prompt:"));
    videoNegativePromptEdit_ = new QTextEdit(this);
    videoNegativePromptEdit_->setPlaceholderText(QStringLiteral("Unwanted elements..."));
    videoNegativePromptEdit_->setMaximumHeight(80);

    promptLayout->addWidget(negativeLabel);
    promptLayout->addWidget(videoNegativePromptEdit_);

    controlsLayout->addWidget(promptGroup);

    // Action buttons
    auto *buttonLayout = new QHBoxLayout();
    generateVideoButton_ = new QPushButton(QStringLiteral("Generate Video"), this);
    previewVideoButton_ = new QPushButton(QStringLiteral("Preview"), this);

    buttonLayout->addWidget(generateVideoButton_);
    buttonLayout->addWidget(previewVideoButton_);

    controlsLayout->addLayout(buttonLayout);

    // Preview area
    auto *previewGroup = new QGroupBox(QStringLiteral("Preview"));
    auto *previewLayout = new QVBoxLayout(previewGroup);

    videoPreviewLabel_ = new QLabel(QStringLiteral("Video preview will appear here"), this);
    videoPreviewLabel_->setAlignment(Qt::AlignCenter);
    videoPreviewLabel_->setStyleSheet(QStringLiteral("background-color: #182030; border: 1px solid #2a3248; border-radius: 4px;"));
    videoPreviewLabel_->setMinimumHeight(300);

    previewLayout->addWidget(videoPreviewLabel_);

    videoProgress_ = new QProgressBar(this);
    videoProgress_->setMinimum(0);
    videoProgress_->setMaximum(100);
    videoProgress_->setValue(0);

    previewLayout->addWidget(videoProgress_);

    // Main layout
    mainLayout->addWidget(controlsGroup);
    mainLayout->addWidget(previewGroup);

    // Connect signals
    if (generateVideoButton_)
    {
        connect(generateVideoButton_, &QPushButton::clicked, this, [this]()
                {
            if (!videoPromptEdit_ || !videoNegativePromptEdit_)
                return;

            QJsonObject payload;
            payload["command"] = "video_generation";
            payload["prompt"] = videoPromptEdit_->text();
            payload["negative_prompt"] = videoNegativePromptEdit_->toPlainText();
            payload["model"] = videoModelCombo_ ? videoModelCombo_->currentText() : "";
            payload["fps"] = fpsSpin_ ? fpsSpin_->value() : 24;
            payload["num_frames"] = numFramesSpin_ ? numFramesSpin_->value() : 16;
            payload["width"] = videoWidthSpin_ ? videoWidthSpin_->value() : 512;
            payload["height"] = videoHeightSpin_ ? videoHeightSpin_->value() : 512;
            payload["strength"] = videoStrengthSpin_ ? videoStrengthSpin_->value() : 0.6;
            payload["sampler"] = videoSamplerCombo_ ? videoSamplerCombo_->currentText() : "";
            
            emit generateRequested(payload); });
    }

    if (previewVideoButton_)
    {
        connect(previewVideoButton_, &QPushButton::clicked, this, [this]()
                {
            if (!videoPreviewLabel_ || !videoProgress_)
                return;
                
            videoPreviewLabel_->setText(QStringLiteral("Previewing video generation..."));
            videoProgress_->setValue(30);
            // Simulate preview
            QTimer::singleShot(2000, this, [this]() {
                if (videoProgress_)
                    videoProgress_->setValue(100);
                if (videoPreviewLabel_)
                    videoPreviewLabel_->setText(QStringLiteral("Video preview ready"));
            }); });
    }
}

void VideoGenerationPage::refreshPreview()
{
    // Implementation for refreshing preview
}

void VideoGenerationPage::updateVideoSettings()
{
    // Implementation for updating video settings
}
