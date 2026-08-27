#include "DatasetGenerationPage.h"

#include "ThemeManager.h"

#include <QCheckBox>
#include <QDesktopServices>
#include <QDir>
#include <QFrame>
#include <QGridLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QLineEdit>
#include <QProgressBar>
#include <QPushButton>
#include <QRandomGenerator>
#include <QSettings>
#include <QSpinBox>
#include <QTextEdit>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>

DatasetGenerationPage::DatasetGenerationPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("DatasetGenerationPage"));
    buildUi();
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });
}

void DatasetGenerationPage::setProjectRoot(const QString &root)
{
    projectRoot_ = root.trimmed();
    if (datasetOutputEdit_ && (datasetOutputEdit_->text().trimmed().isEmpty()
                               || datasetOutputEdit_->text() == QStringLiteral("./dataset_output"))) {
        datasetOutputEdit_->setText(defaultOutputRoot());
    }
}

void DatasetGenerationPage::setBusy(bool busy, const QString &message)
{
    if (generateDatasetButton_)
        generateDatasetButton_->setEnabled(!busy);
    if (previewDatasetButton_)
        previewDatasetButton_->setEnabled(!busy);
    if (statusLabel_ && !message.isEmpty())
        statusLabel_->setText(message);
    if (datasetProgress_ && busy)
        datasetProgress_->setRange(0, 0); // indeterminate while worker queues
    if (datasetProgress_ && !busy)
        datasetProgress_->setRange(0, 100);
}

void DatasetGenerationPage::applyQueueAck(const QJsonObject &ack)
{
    const bool ok = ack.value(QStringLiteral("ok")).toBool(false);
    const int queued = ack.value(QStringLiteral("queued_count")).toInt(0);
    const QString root = ack.value(QStringLiteral("dataset_root")).toString();
    if (datasetProgress_) {
        datasetProgress_->setRange(0, 100);
        datasetProgress_->setValue(ok ? 100 : 0);
    }
    if (datasetPreviewLabel_) {
        if (ok) {
            datasetPreviewLabel_->setText(
                QStringLiteral("Queued %1 image job(s).\nOutput: %2\nJobs run through the normal T2I queue.")
                    .arg(queued)
                    .arg(root.isEmpty() ? defaultOutputRoot() : root));
        } else {
            datasetPreviewLabel_->setText(
                QStringLiteral("Dataset enqueue failed: %1")
                    .arg(ack.value(QStringLiteral("error")).toString(QStringLiteral("unknown error"))));
        }
    }
    if (statusLabel_) {
        statusLabel_->setText(ok ? QStringLiteral("Queued %1 jobs").arg(queued)
                                 : QStringLiteral("Enqueue failed"));
    }
    setBusy(false);
}

QString DatasetGenerationPage::defaultOutputRoot() const
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString dest = settings.value(QStringLiteral("image_generation/output_folder")).toString().trimmed();
    if (!dest.isEmpty() && QDir(dest).exists())
        return dest;
    return QString();
}

void DatasetGenerationPage::buildUi()
{
    auto *mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(16, 16, 16, 16);
    mainLayout->setSpacing(12);

    auto *hero = new QLabel(QStringLiteral("Dataset Generator"), this);
    hero->setObjectName(QStringLiteral("DatasetHeroTitle"));
    auto *sub = new QLabel(
        QStringLiteral("Expand prompts into many T2I jobs. Requires a checkpoint (uses current T2I model if set)."),
        this);
    sub->setObjectName(QStringLiteral("DatasetHeroSub"));
    sub->setWordWrap(true);
    mainLayout->addWidget(hero);
    mainLayout->addWidget(sub);

    auto *controlsGroup = new QGroupBox(QStringLiteral("Dataset Generation Controls"), this);
    controlsGroup->setObjectName(QStringLiteral("DatasetCard"));
    auto *controlsLayout = new QVBoxLayout(controlsGroup);

    auto *promptsGroup = new QGroupBox(QStringLiteral("Prompts"), controlsGroup);
    auto *promptsLayout = new QVBoxLayout(promptsGroup);
    auto *promptsLabel = new QLabel(QStringLiteral("Enter prompts (one per line):"), promptsGroup);
    datasetPromptsEdit_ = new QTextEdit(promptsGroup);
    datasetPromptsEdit_->setPlaceholderText(
        QStringLiteral("A beautiful landscape at golden hour\n"
                       "A futuristic city skyline, neon rain\n"
                       "A product hero shot on white seamless"));
    datasetPromptsEdit_->setMinimumHeight(120);
    promptsLayout->addWidget(promptsLabel);
    promptsLayout->addWidget(datasetPromptsEdit_);
    controlsLayout->addWidget(promptsGroup);

    auto *settingsGroup = new QGroupBox(QStringLiteral("Dataset Settings"), controlsGroup);
    auto *settingsLayout = new QGridLayout(settingsGroup);

    datasetOutputEdit_ = new QLineEdit(settingsGroup);
    datasetOutputEdit_->setPlaceholderText(QStringLiteral("Not set — browse dest in first-run or T2I"));
    const QString dest = defaultOutputRoot();
    if (!dest.isEmpty())
        datasetOutputEdit_->setText(dest);
    settingsLayout->addWidget(new QLabel(QStringLiteral("Output Directory:"), settingsGroup), 0, 0);
    settingsLayout->addWidget(datasetOutputEdit_, 0, 1);

    imagesPerPromptSpin_ = new QSpinBox(settingsGroup);
    imagesPerPromptSpin_->setRange(1, 100);
    imagesPerPromptSpin_->setValue(4);
    settingsLayout->addWidget(new QLabel(QStringLiteral("Images per Prompt:"), settingsGroup), 1, 0);
    settingsLayout->addWidget(imagesPerPromptSpin_, 1, 1);

    seedStartSpin_ = new QSpinBox(settingsGroup);
    seedStartSpin_->setRange(0, 2000000000);
    seedStartSpin_->setValue(0);
    settingsLayout->addWidget(new QLabel(QStringLiteral("Seed Start:"), settingsGroup), 2, 0);
    settingsLayout->addWidget(seedStartSpin_, 2, 1);

    datasetWidthSpin_ = new QSpinBox(settingsGroup);
    datasetWidthSpin_->setRange(0, 2048);
    datasetWidthSpin_->setSingleStep(64);
    datasetWidthSpin_->setSpecialValueText(QStringLiteral("—"));
    datasetWidthSpin_->setValue(0);
    settingsLayout->addWidget(new QLabel(QStringLiteral("Width:"), settingsGroup), 3, 0);
    settingsLayout->addWidget(datasetWidthSpin_, 3, 1);

    datasetHeightSpin_ = new QSpinBox(settingsGroup);
    datasetHeightSpin_->setRange(0, 2048);
    datasetHeightSpin_->setSingleStep(64);
    datasetHeightSpin_->setSpecialValueText(QStringLiteral("—"));
    datasetHeightSpin_->setValue(0);
    settingsLayout->addWidget(new QLabel(QStringLiteral("Height:"), settingsGroup), 4, 0);
    settingsLayout->addWidget(datasetHeightSpin_, 4, 1);

    controlsLayout->addWidget(settingsGroup);

    auto *optionsGroup = new QGroupBox(QStringLiteral("Options"), controlsGroup);
    auto *optionsLayout = new QVBoxLayout(optionsGroup);
    shufflePromptsCheckBox_ = new QCheckBox(QStringLiteral("Shuffle Prompts"), optionsGroup);
    shufflePromptsCheckBox_->setChecked(false);
    saveMetadataCheckBox_ = new QCheckBox(QStringLiteral("Save Metadata sidecars"), optionsGroup);
    saveMetadataCheckBox_->setChecked(true);
    optionsLayout->addWidget(shufflePromptsCheckBox_);
    optionsLayout->addWidget(saveMetadataCheckBox_);
    controlsLayout->addWidget(optionsGroup);

    auto *buttonLayout = new QHBoxLayout();
    generateDatasetButton_ = new QPushButton(QStringLiteral("Generate Dataset"), controlsGroup);
    generateDatasetButton_->setObjectName(QStringLiteral("PrimaryActionButton"));
    previewDatasetButton_ = new QPushButton(QStringLiteral("Count Jobs"), controlsGroup);
    openOutputButton_ = new QPushButton(QStringLiteral("Open Output"), controlsGroup);
    buttonLayout->addWidget(generateDatasetButton_);
    buttonLayout->addWidget(previewDatasetButton_);
    buttonLayout->addWidget(openOutputButton_);
    buttonLayout->addStretch(1);
    controlsLayout->addLayout(buttonLayout);

    auto *previewGroup = new QGroupBox(QStringLiteral("Status"), this);
    previewGroup->setObjectName(QStringLiteral("DatasetCard"));
    auto *previewLayout = new QVBoxLayout(previewGroup);
    datasetPreviewLabel_ = new QLabel(QStringLiteral("Ready — enter prompts and Generate."), previewGroup);
    datasetPreviewLabel_->setObjectName(QStringLiteral("DatasetPreview"));
    datasetPreviewLabel_->setAlignment(Qt::AlignLeft | Qt::AlignTop);
    datasetPreviewLabel_->setWordWrap(true);
    datasetPreviewLabel_->setMinimumHeight(120);
    datasetProgress_ = new QProgressBar(previewGroup);
    datasetProgress_->setRange(0, 100);
    datasetProgress_->setValue(0);
    statusLabel_ = new QLabel(QStringLiteral("Idle"), previewGroup);
    statusLabel_->setObjectName(QStringLiteral("DatasetStatus"));
    previewLayout->addWidget(datasetPreviewLabel_);
    previewLayout->addWidget(datasetProgress_);
    previewLayout->addWidget(statusLabel_);

    mainLayout->addWidget(controlsGroup);
    mainLayout->addWidget(previewGroup, 1);

    connect(generateDatasetButton_, &QPushButton::clicked, this, &DatasetGenerationPage::generateDataset);
    connect(previewDatasetButton_, &QPushButton::clicked, this, &DatasetGenerationPage::updateDatasetPreview);
    connect(openOutputButton_, &QPushButton::clicked, this, [this]() {
        const QString root = datasetOutputEdit_ ? datasetOutputEdit_->text().trimmed() : defaultOutputRoot();
        if (!root.isEmpty()) {
            QDir().mkpath(root);
            QDesktopServices::openUrl(QUrl::fromLocalFile(root));
        }
    });
}

void DatasetGenerationPage::applyTheme()
{
    const auto &theme = ThemeManager::instance();
    using C = ThemeManager::Color;
    using T = ThemeManager::Type;
    setStyleSheet(QStringLiteral(
                      "#DatasetGenerationPage { background: transparent; }"
                      "QLabel#DatasetHeroTitle { @display@ color: @hi@; }"
                      "QLabel#DatasetHeroSub { @body@ color: @mid@; }"
                      "QGroupBox#DatasetCard, QGroupBox {"
                      " background: @s1@; border: 1px solid @bd@; border-radius: 10px;"
                      " margin-top: 10px; padding-top: 8px; color: @hi@; }"
                      "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: @mid@; }"
                      "QLabel#DatasetPreview { background: @s0@; border: 1px solid @bd@; border-radius: 8px;"
                      " padding: 12px; color: @mid@; }"
                      "QLabel#DatasetStatus { @caption@ color: @mute@; }"
                      "QPushButton#PrimaryActionButton {"
                      " background: @acc@; color: white; border: none; border-radius: 8px;"
                      " padding: 10px 16px; font-weight: 700; }"
                      "QPushButton { background: rgba(255,255,255,0.03); color: @hi@;"
                      " border: 1px solid @bd@; border-radius: 6px; padding: 8px 12px; }"
                      "QTextEdit, QLineEdit, QSpinBox {"
                      " background: @s0@; color: @hi@; border: 1px solid @bd@;"
                      " border-radius: 6px; padding: 6px; }")
                      .replace(QLatin1String("@display@"), theme.fontCss(T::Display))
                      .replace(QLatin1String("@body@"), theme.fontCss(T::Body))
                      .replace(QLatin1String("@caption@"), theme.fontCss(T::Caption))
                      .replace(QLatin1String("@hi@"), theme.css(C::TextHi))
                      .replace(QLatin1String("@mid@"), theme.css(C::TextMid))
                      .replace(QLatin1String("@mute@"), theme.css(C::TextLo))
                      .replace(QLatin1String("@s0@"), theme.css(C::Surface0))
                      .replace(QLatin1String("@s1@"), theme.css(C::Surface1))
                      .replace(QLatin1String("@bd@"), theme.css(C::Border))
                      .replace(QLatin1String("@acc@"), theme.css(C::Accent)));
}

void DatasetGenerationPage::generateDataset()
{
    if (!datasetPromptsEdit_ || !datasetOutputEdit_)
        return;

    QString promptsText = datasetPromptsEdit_->toPlainText();
    QStringList lines = promptsText.split(QLatin1Char('\n'), Qt::SkipEmptyParts);
    for (QString &line : lines)
        line = line.trimmed();
    lines.removeAll(QString());
    if (lines.isEmpty()) {
        if (datasetPreviewLabel_)
            datasetPreviewLabel_->setText(QStringLiteral("Add at least one prompt."));
        return;
    }

    const QString dest = datasetOutputEdit_->text().trimmed();
    if (dest.isEmpty()) {
        if (datasetPreviewLabel_)
            datasetPreviewLabel_->setText(QStringLiteral("Choose an output folder to generate."));
        return;
    }
    const int width = datasetWidthSpin_ ? datasetWidthSpin_->value() : 0;
    const int height = datasetHeightSpin_ ? datasetHeightSpin_->value() : 0;
    if (width < 64 || height < 64) {
        if (datasetPreviewLabel_)
            datasetPreviewLabel_->setText(QStringLiteral("Choose a canvas size to generate."));
        return;
    }

    if (shufflePromptsCheckBox_ && shufflePromptsCheckBox_->isChecked()) {
        // Simple Fisher–Yates without bringing <random> into the header path.
        for (int i = lines.size() - 1; i > 0; --i) {
            const int j = QRandomGenerator::global()->bounded(i + 1);
            lines.swapItemsAt(i, j);
        }
        promptsText = lines.join(QLatin1Char('\n'));
    }

    QJsonObject payload;
    payload.insert(QStringLiteral("command"), QStringLiteral("generate_dataset"));
    payload.insert(QStringLiteral("prompts"), promptsText);
    payload.insert(QStringLiteral("output_root"), datasetOutputEdit_->text().trimmed());
    payload.insert(QStringLiteral("images_per_prompt"),
                   imagesPerPromptSpin_ ? imagesPerPromptSpin_->value() : 4);
    payload.insert(QStringLiteral("seed_start"), seedStartSpin_ ? seedStartSpin_->value() : 0);
    payload.insert(QStringLiteral("width"), width);
    payload.insert(QStringLiteral("height"), height);
    payload.insert(QStringLiteral("save_metadata"),
                   saveMetadataCheckBox_ ? saveMetadataCheckBox_->isChecked() : true);

    setBusy(true, QStringLiteral("Enqueueing…"));
    if (datasetPreviewLabel_)
        datasetPreviewLabel_->setText(QStringLiteral("Sending generate_dataset to worker…"));
    emit generateDatasetRequested(payload);
}

void DatasetGenerationPage::updateDatasetPreview()
{
    if (!datasetPromptsEdit_)
        return;
    QStringList lines = datasetPromptsEdit_->toPlainText().split(QLatin1Char('\n'), Qt::SkipEmptyParts);
    int prompts = 0;
    for (const QString &line : lines) {
        if (!line.trimmed().isEmpty())
            ++prompts;
    }
    const int per = imagesPerPromptSpin_ ? imagesPerPromptSpin_->value() : 4;
    const int total = prompts * per;
    if (datasetPreviewLabel_) {
        datasetPreviewLabel_->setText(
            QStringLiteral("%1 prompt(s) × %2 image(s) = %3 T2I queue job(s).\nOutput: %4")
                .arg(prompts)
                .arg(per)
                .arg(total)
                .arg(datasetOutputEdit_ ? datasetOutputEdit_->text() : defaultOutputRoot()));
    }
    if (datasetProgress_) {
        datasetProgress_->setRange(0, 100);
        datasetProgress_->setValue(prompts > 0 ? 40 : 0);
    }
    if (statusLabel_)
        statusLabel_->setText(QStringLiteral("Preview only — not queued"));
}
