#include "DatasetGenerationPage.h"

#include "ThemeManager.h"
#include "style/SvKit.h"

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

void DatasetGenerationPage::updateDisclosure(bool advanced)
{
    if (advancedBlock_)
        advancedBlock_->setVisible(advanced);
    // The caption sits OUTSIDE advancedBlock_ and stays visible in both modes: revealing the spins
    // does not relocate it, and hiding them does not take the sentence away with them.
    updateCanvasCaption();
}

void DatasetGenerationPage::setInheritedCanvas(int width, int height)
{
    inheritedWidth_ = width;
    inheritedHeight_ = height;
    updateCanvasCaption();
}

void DatasetGenerationPage::updateCanvasCaption()
{
    if (!canvasCaptionLabel_)
        return;
    const int stated = datasetWidthSpin_ ? datasetWidthSpin_->value() : 0;
    const int statedHeight = datasetHeightSpin_ ? datasetHeightSpin_->value() : 0;
    if (stated >= 64 && statedHeight >= 64) {
        canvasCaptionLabel_->setText(
            QStringLiteral("Canvas: %1 × %2").arg(stated).arg(statedHeight));
        return;
    }
    if (inheritedWidth_ >= 64 && inheritedHeight_ >= 64) {
        // Saying it is the point. The shell substitutes this canvas into the request on its way to
        // the worker, and a substitution the user was never shown is the hidden output-changing
        // state this codebase spent a hardening pass removing.
        canvasCaptionLabel_->setText(QStringLiteral("Canvas: %1 × %2, from Text to Image")
                                         .arg(inheritedWidth_)
                                         .arg(inheritedHeight_));
        return;
    }
    canvasCaptionLabel_->setText(
        QStringLiteral("Canvas: not set — set one on Text to Image, or turn on Advanced here."));
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
    datasetPromptsEdit_->setAcceptDrops(false);
    datasetPromptsEdit_->setPlaceholderText(
        QStringLiteral("A futuristic city skyline, neon rain\n"
                       "A product hero shot on white seamless"));
    // Placeholder is not a prompt — generateDataset() reads toPlainText(). Live 2026-09-10
    // Generate said "Add at least one prompt" while the box showed the golden-hour sample.
    datasetPromptsEdit_->setPlainText(QStringLiteral("A beautiful landscape at golden hour"));
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

    advancedBlock_ = new QWidget(settingsGroup);
    auto *advLayout = new QGridLayout(advancedBlock_);
    seedStartSpin_ = new QSpinBox(advancedBlock_);
    seedStartSpin_->setRange(0, 2000000000);
    seedStartSpin_->setValue(0);
    advLayout->addWidget(new QLabel(QStringLiteral("Seed Start:"), advancedBlock_), 0, 0);
    advLayout->addWidget(seedStartSpin_, 0, 1);

    datasetWidthSpin_ = new QSpinBox(advancedBlock_);
    datasetWidthSpin_->setRange(0, 2048);
    datasetWidthSpin_->setSingleStep(64);
    datasetWidthSpin_->setSpecialValueText(QStringLiteral("—"));
    // NO initial value, deliberately, and this is the whole of the fix. The control was already
    // BUILT to say "unstated" -- minimum 0 with an em-dash special value -- and generateDataset
    // already refuses a canvas below 64 with "Choose a canvas size to generate.", exactly as it
    // refuses a missing output folder. A hardcoded 1024 used to sit on this line and on the height
    // line below; it overrode all of that and stated a house canvas as though the user had picked
    // it, so the refusal could never fire and every dataset rendered 1024x1024 by default rather
    // than by decision.
    //
    // The absence is written as an absence rather than as an explicit zero call because two tests
    // hold these two lines from opposite sides -- one greps the file for the 1024 literal, the
    // other for an explicit zero on these spins -- and a QSpinBox constructed with a minimum of 0
    // already sits at 0. Do not "tidy" either spelling back in.
    advLayout->addWidget(new QLabel(QStringLiteral("Width:"), advancedBlock_), 1, 0);
    advLayout->addWidget(datasetWidthSpin_, 1, 1);

    datasetHeightSpin_ = new QSpinBox(advancedBlock_);
    datasetHeightSpin_->setRange(0, 2048);
    datasetHeightSpin_->setSingleStep(64);
    datasetHeightSpin_->setSpecialValueText(QStringLiteral("—"));
    // Unstated, same as width above.
    advLayout->addWidget(new QLabel(QStringLiteral("Height:"), advancedBlock_), 2, 0);
    advLayout->addWidget(datasetHeightSpin_, 2, 1);
    advancedBlock_->setVisible(false);
    settingsLayout->addWidget(advancedBlock_, 2, 0, 1, 2);

    // Read-only, in the Simple half of the form. Not a knob -- a Simple user cannot type a canvas
    // here, and is not being asked to. It reports the size the images will actually come out at,
    // which is the cockpit's canvas whenever this page has not been given one of its own.
    canvasCaptionLabel_ = new QLabel(settingsGroup);
    canvasCaptionLabel_->setObjectName(QStringLiteral("DatasetCanvasCaption"));
    canvasCaptionLabel_->setWordWrap(true);
    canvasCaptionLabel_->setTextInteractionFlags(Qt::NoTextInteraction);
    settingsLayout->addWidget(canvasCaptionLabel_, 3, 0, 1, 2);
    updateCanvasCaption();

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
    spellvision::kit::setRole(generateDatasetButton_, spellvision::style::Role::Primary);
    previewDatasetButton_ = new QPushButton(QStringLiteral("Count Jobs"), controlsGroup);
    // No object name, so no name-map fallback either: a role or it renders undecorated.
    spellvision::kit::setRole(previewDatasetButton_, spellvision::style::Role::Secondary);
    openOutputButton_ = new QPushButton(QStringLiteral("Open Output"), controlsGroup);
    spellvision::kit::setRole(openOutputButton_, spellvision::style::Role::Secondary);
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

    connect(datasetWidthSpin_, &QSpinBox::valueChanged, this, [this]() { updateCanvasCaption(); });
    connect(datasetHeightSpin_, &QSpinBox::valueChanged, this, [this]() { updateCanvasCaption(); });
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
                      // A group box is NOT a type SvStyle draws (it is not a QFrame, so it
                      // cannot carry a surface), so this one rule still paints -- with the
                      // material's card radius rather than a literal. The card-name half of the
                      // old selector is gone: naming a card is what a surface property is for,
                      // and the group boxes inside it were drawn by the same rule anyway.
                      "QGroupBox {"
                      " background: @s1@; border: 1px solid @bd@; border-radius: @rcard@;"
                      " margin-top: 10px; padding-top: 8px; color: @hi@; }"
                      "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: @mid@; }"
                      "QLabel#DatasetPreview { background: @s0@; border: 1px solid @bd@; border-radius: @rctl@;"
                      " padding: 12px; color: @mid@; }"
                      "QLabel#DatasetStatus { @caption@ color: @mute@; }"
                      "QLabel#DatasetCanvasCaption { @caption@ color: @mid@; }"
                      // Generate is Role::Primary, the other two Role::Secondary, and the fields
                      // are the style's field panel. Spacing is all a sheet may say about them.
                      "QPushButton { padding: 8px 12px; min-height: 30px; }"
                      "QTextEdit, QLineEdit, QSpinBox { padding: 6px; }")
                      .replace(QLatin1String("@display@"), theme.fontCss(T::Display))
                      .replace(QLatin1String("@body@"), theme.fontCss(T::Body))
                      .replace(QLatin1String("@caption@"), theme.fontCss(T::Caption))
                      .replace(QLatin1String("@hi@"), theme.css(C::TextHi))
                      .replace(QLatin1String("@mid@"), theme.css(C::TextMid))
                      .replace(QLatin1String("@mute@"), theme.css(C::TextLo))
                      .replace(QLatin1String("@s0@"), theme.css(C::Surface0))
                      .replace(QLatin1String("@s1@"), theme.css(C::Surface1))
                      .replace(QLatin1String("@bd@"), theme.css(C::Border))
                      .replace(QLatin1String("@rcard@"), QString::number(theme.radiusCard()) + QStringLiteral("px"))
                      .replace(QLatin1String("@rctl@"), QString::number(theme.radiusControl()) + QStringLiteral("px")));
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
    {
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        s.setValue(QStringLiteral("train/lastDatasetRoot"), dest);
    }
    const int width = datasetWidthSpin_ ? datasetWidthSpin_->value() : 0;
    const int height = datasetHeightSpin_ ? datasetHeightSpin_->value() : 0;
    // Unset here is not the same as unknown. The width/height spins live in the Advanced block, so
    // in Simple they are always unset -- and refusing on that alone left a Simple user reading
    // "choose a canvas" beside no canvas control at all. The refusal belongs to the case where
    // NOTHING states a canvas: not this page, and not the cockpit it inherits from.
    const bool inherits = inheritedWidth_ >= 64 && inheritedHeight_ >= 64;
    if ((width < 64 || height < 64) && !inherits) {
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
    // Sent AS STATED, including 0 for an unset spin. The inherited canvas is deliberately not
    // copied in here: the shell's mergeDatasetRequestFromCockpit substitutes it, and a page that
    // also applied the rule would be a second copy of it to drift against.
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
        // A preview queues nothing, so there is no progress to report. The bar used to be parked at
        // 40 here, which was harmless only while the style suppressed every percentage label and
        // became a claim the moment that label came back: "40 %" beside "Preview only -- not
        // queued". An empty groove is the honest reading of a job that has not started.
        datasetProgress_->setRange(0, 100);
        datasetProgress_->setValue(0);
    }
    if (statusLabel_)
        statusLabel_->setText(QStringLiteral("Preview only — not queued"));
}
