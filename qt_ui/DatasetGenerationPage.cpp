#include "DatasetGenerationPage.h"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGridLayout>
#include <QLabel>
#include <QLineEdit>
#include <QTextEdit>
#include <QSpinBox>
#include <QPushButton>
#include <QCheckBox>
#include <QGroupBox>
#include <QScrollArea>
#include <QApplication>
#include <QTimer>

DatasetGenerationPage::DatasetGenerationPage(QWidget *parent)
    : QWidget(parent)
{
    buildUi();
}

void DatasetGenerationPage::buildUi()
{
    if (!parent())
        return;

    auto *mainLayout = new QVBoxLayout(this);
    
    // Dataset Generation Controls
    auto *controlsGroup = new QGroupBox(QStringLiteral("Dataset Generation Controls"));
    auto *controlsLayout = new QVBoxLayout(controlsGroup);
    
    // Prompts input
    auto *promptsGroup = new QGroupBox(QStringLiteral("Prompts"));
    auto *promptsLayout = new QVBoxLayout(promptsGroup);
    
    auto *promptsLabel = new QLabel(QStringLiteral("Enter prompts (one per line):"));
    datasetPromptsEdit_ = new QTextEdit();
    datasetPromptsEdit_->setPlaceholderText(QStringLiteral("Enter your prompts here, one per line\nExample:\nA beautiful landscape\nA futuristic city\nA cute animal"));
    datasetPromptsEdit_->setMinimumHeight(120);
    
    promptsLayout->addWidget(promptsLabel);
    promptsLayout->addWidget(datasetPromptsEdit_);
    
    controlsLayout->addWidget(promptsGroup);
    
    // Dataset settings
    auto *settingsGroup = new QGroupBox(QStringLiteral("Dataset Settings"));
    auto *settingsLayout = new QGridLayout(settingsGroup);
    
    // Output directory
    auto *outputLabel = new QLabel(QStringLiteral("Output Directory:"));
    datasetOutputEdit_ = new QLineEdit();
    datasetOutputEdit_->setText(QStringLiteral("./dataset_output"));
    
    settingsLayout->addWidget(outputLabel, 0, 0);
    settingsLayout->addWidget(datasetOutputEdit_, 0, 1);
    
    // Images per prompt
    auto *imagesPerPromptLabel = new QLabel(QStringLiteral("Images per Prompt:"));
    imagesPerPromptSpin_ = new QSpinBox();
    imagesPerPromptSpin_->setRange(1, 100);
    imagesPerPromptSpin_->setValue(5);
    
    settingsLayout->addWidget(imagesPerPromptLabel, 1, 0);
    settingsLayout->addWidget(imagesPerPromptSpin_, 1, 1);
    
    // Seed start
    auto *seedStartLabel = new QLabel(QStringLiteral("Seed Start:"));
    seedStartSpin_ = new QSpinBox();
    seedStartSpin_->setRange(0, 1000000);
    seedStartSpin_->setValue(42);
    
    settingsLayout->addWidget(seedStartLabel, 2, 0);
    settingsLayout->addWidget(seedStartSpin_, 2, 1);
    
    // Width
    auto *widthLabel = new QLabel(QStringLiteral("Width:"));
    datasetWidthSpin_ = new QSpinBox();
    datasetWidthSpin_->setRange(128, 2048);
    datasetWidthSpin_->setValue(512);
    
    settingsLayout->addWidget(widthLabel, 3, 0);
    settingsLayout->addWidget(datasetWidthSpin_, 3, 1);
    
    // Height
    auto *heightLabel = new QLabel(QStringLiteral("Height:"));
    datasetHeightSpin_ = new QSpinBox();
    datasetHeightSpin_->setRange(128, 2048);
    datasetHeightSpin_->setValue(512);
    
    settingsLayout->addWidget(heightLabel, 4, 0);
    settingsLayout->addWidget(datasetHeightSpin_, 4, 1);
    
    controlsLayout->addWidget(settingsGroup);
    
    // Options
    auto *optionsGroup = new QGroupBox(QStringLiteral("Options"));
    auto *optionsLayout = new QVBoxLayout(optionsGroup);
    
    shufflePromptsCheckBox_ = new QCheckBox(QStringLiteral("Shuffle Prompts"));
    shufflePromptsCheckBox_->setChecked(true);
    
    saveMetadataCheckBox_ = new QCheckBox(QStringLiteral("Save Metadata"));
    saveMetadataCheckBox_->setChecked(true);
    
    optionsLayout->addWidget(shufflePromptsCheckBox_);
    optionsLayout->addWidget(saveMetadataCheckBox_);
    
    controlsLayout->addWidget(optionsGroup);
    
    // Action buttons
    auto *buttonLayout = new QHBoxLayout();
    generateDatasetButton_ = new QPushButton(QStringLiteral("Generate Dataset"));
    previewDatasetButton_ = new QPushButton(QStringLiteral("Preview"));
    
    buttonLayout->addWidget(generateDatasetButton_);
    buttonLayout->addWidget(previewDatasetButton_);
    
    controlsLayout->addLayout(buttonLayout);
    
    // Preview area
    auto *previewGroup = new QGroupBox(QStringLiteral("Preview"));
    auto *previewLayout = new QVBoxLayout(previewGroup);
    
    datasetPreviewLabel_ = new QLabel(QStringLiteral("Dataset preview will appear here"));
    datasetPreviewLabel_->setAlignment(Qt::AlignCenter);
    datasetPreviewLabel_->setStyleSheet(QStringLiteral("background-color: #182030; border: 1px solid #2a3248; border-radius: 4px;"));
    datasetPreviewLabel_->setMinimumHeight(200);
    
    previewLayout->addWidget(datasetPreviewLabel_);
    
    datasetProgress_ = new QProgressBar();
    datasetProgress_->setMinimum(0);
    datasetProgress_->setMaximum(100);
    datasetProgress_->setValue(0);
    
    previewLayout->addWidget(datasetProgress_);
    
    // Main layout
    mainLayout->addWidget(controlsGroup);
    mainLayout->addWidget(previewGroup);
    
    // Connect signals
    if (generateDatasetButton_)
    {
        connect(generateDatasetButton_, &QPushButton::clicked, this, &DatasetGenerationPage::generateDataset);
    }
    
    if (previewDatasetButton_)
    {
        connect(previewDatasetButton_, &QPushButton::clicked, this, &DatasetGenerationPage::updateDatasetPreview);
    }
}

void DatasetGenerationPage::generateDataset()
{
    if (!datasetPromptsEdit_ || !datasetOutputEdit_)
        return;

    QJsonObject payload;
    payload["command"] = "generate_dataset";
    payload["prompts"] = datasetPromptsEdit_->toPlainText();
    payload["output_root"] = datasetOutputEdit_->text();
    payload["images_per_prompt"] = imagesPerPromptSpin_ ? imagesPerPromptSpin_->value() : 5;
    payload["seed_start"] = seedStartSpin_ ? seedStartSpin_->value() : 42;
    payload["width"] = datasetWidthSpin_ ? datasetWidthSpin_->value() : 512;
    payload["height"] = datasetHeightSpin_ ? datasetHeightSpin_->value() : 512;
    payload["shuffle_prompts"] = shufflePromptsCheckBox_ ? shufflePromptsCheckBox_->isChecked() : true;
    payload["save_metadata"] = saveMetadataCheckBox_ ? saveMetadataCheckBox_->isChecked() : true;
    
    emit generateDatasetRequested(payload);
    
    // Show progress
    if (datasetProgress_)
    {
        datasetProgress_->setValue(0);
        if (datasetPreviewLabel_)
            datasetPreviewLabel_->setText(QStringLiteral("Generating dataset..."));
    }
    
    // Simulate progress
    if (datasetProgress_)
    {
        QTimer::singleShot(1000, this, [this]() {
            if (datasetProgress_)
                datasetProgress_->setValue(50);
            if (datasetPreviewLabel_)
                datasetPreviewLabel_->setText(QStringLiteral("Processing..."));
        });
        
        QTimer::singleShot(2000, this, [this]() {
            if (datasetProgress_)
                datasetProgress_->setValue(100);
            if (datasetPreviewLabel_)
                datasetPreviewLabel_->setText(QStringLiteral("Dataset generation complete!"));
        });
    }
}

void DatasetGenerationPage::updateDatasetPreview()
{
    if (!datasetPreviewLabel_ || !datasetProgress_)
        return;

    datasetPreviewLabel_->setText(QStringLiteral("Previewing dataset generation..."));
    datasetProgress_->setValue(30);
    
    // Simulate preview
    QTimer::singleShot(2000, this, [this]() {
        if (datasetProgress_)
            datasetProgress_->setValue(100);
        if (datasetPreviewLabel_)
            datasetPreviewLabel_->setText(QStringLiteral("Dataset preview ready"));
    });
}
