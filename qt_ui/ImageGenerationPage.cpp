#include "ImageGenerationPage.h"

#include "ThemeManager.h"

#include <QAbstractItemView>
#include <QAbstractSpinBox>
#include <QComboBox>
#include <QCompleter>
#include <QDoubleSpinBox>
#include <QDropEvent>
#include <QDragEnterEvent>
#include <QDir>
#include <QDirIterator>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonDocument>
#include <QLabel>
#include <QLineEdit>
#include <QMimeData>
#include <QPixmap>
#include <QPushButton>
#include <QProgressBar>
#include <QResizeEvent>
#include <QScrollArea>
#include <QSettings>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QSplitter>
#include <QTextEdit>
#include <QToolButton>
#include <QUrl>
#include <QVBoxLayout>
#include <QWheelEvent>
#include <QtGlobal>

#include <algorithm>
#include <functional>

namespace
{
    struct CatalogEntry
    {
        QString display;
        QString value;
    };

    class DropTargetFrame final : public QFrame
    {
    public:
        explicit DropTargetFrame(QWidget *parent = nullptr)
            : QFrame(parent)
        {
            setAcceptDrops(true);
        }

        std::function<void(const QString &)> onFileDropped;

    protected:
        void dragEnterEvent(QDragEnterEvent *event) override
        {
            if (!event)
                return;

            const QMimeData *mimeData = event->mimeData();
            if (!mimeData || !mimeData->hasUrls())
            {
                event->ignore();
                return;
            }

            const QList<QUrl> urls = mimeData->urls();
            if (urls.isEmpty() || !urls.first().isLocalFile())
            {
                event->ignore();
                return;
            }

            event->acceptProposedAction();
        }

        void dropEvent(QDropEvent *event) override
        {
            if (!event)
                return;

            const QMimeData *mimeData = event->mimeData();
            if (!mimeData || !mimeData->hasUrls())
            {
                event->ignore();
                return;
            }

            const QList<QUrl> urls = mimeData->urls();
            if (urls.isEmpty() || !urls.first().isLocalFile())
            {
                event->ignore();
                return;
            }

            const QString localPath = urls.first().toLocalFile();
            if (onFileDropped)
                onFileDropped(localPath);

            event->acceptProposedAction();
        }
    };


    class ClickOnlyComboBox final : public QComboBox
    {
    public:
        explicit ClickOnlyComboBox(QWidget *parent = nullptr)
            : QComboBox(parent)
        {
            setFocusPolicy(Qt::StrongFocus);
        }

    protected:
        void wheelEvent(QWheelEvent *event) override
        {
            if (view() && view()->isVisible())
            {
                QComboBox::wheelEvent(event);
                return;
            }

            if (event)
                event->ignore();
        }
    };

    QFrame *createCard(const QString &objectName = QString())
    {
        auto *frame = new QFrame;
        frame->setObjectName(objectName);
        frame->setFrameShape(QFrame::NoFrame);
        return frame;
    }

    QLabel *createSectionTitle(const QString &text, QWidget *parent = nullptr)
    {
        auto *label = new QLabel(text, parent);
        label->setStyleSheet(QStringLiteral("font-size: 16px; font-weight: 700; color: #f4f7fb;"));
        return label;
    }

    QLabel *createSectionBody(const QString &text, QWidget *parent = nullptr)
    {
        auto *label = new QLabel(text, parent);
        label->setWordWrap(true);
        label->setStyleSheet(QStringLiteral("font-size: 12px; color: #9fb0ca;"));
        return label;
    }

    QString comboStoredValue(const QComboBox *combo)
    {
        if (!combo)
            return QString();

        const QString dataValue = combo->currentData(Qt::UserRole).toString().trimmed();
        if (!dataValue.isEmpty())
            return dataValue;

        return combo->currentText().trimmed();
    }

    QString comboDisplayValue(const QComboBox *combo)
    {
        return combo ? combo->currentText().trimmed() : QString();
    }

    QString compactCatalogDisplay(const QString &rootPath, const QString &absolutePath, bool addDisambiguator)
    {
        Q_UNUSED(rootPath);

        const QFileInfo info(absolutePath);
        const QString baseName = info.completeBaseName().trimmed().isEmpty()
            ? info.fileName()
            : info.completeBaseName().trimmed();

        if (!addDisambiguator)
            return baseName;

        const QString parentName = info.dir().dirName().trimmed();
        if (parentName.isEmpty())
            return baseName;

        return QStringLiteral("%1 • %2").arg(baseName, parentName);
    }

    QString shortDisplayFromValue(const QString &value)
    {
        const QString trimmed = value.trimmed();
        if (trimmed.isEmpty())
            return QStringLiteral("none");

        const QFileInfo info(trimmed);
        if (info.exists())
        {
            const QString baseName = info.completeBaseName().trimmed();
            if (!baseName.isEmpty())
                return baseName;
        }

        if (!trimmed.contains(QChar('/')) && !trimmed.contains(QChar('\\')))
            return trimmed;

        return QFileInfo(trimmed).completeBaseName().trimmed().isEmpty()
            ? QFileInfo(trimmed).fileName()
            : QFileInfo(trimmed).completeBaseName().trimmed();
    }

    QString chooseModelsRootPath()
    {
        const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_MODELS")).trimmed();
        if (!envPath.isEmpty() && QDir(envPath).exists())
            return QDir::fromNativeSeparators(QDir(envPath).absolutePath());

        const QString preferred = QStringLiteral("D:/AI_ASSETS/models");
        if (QDir(preferred).exists())
            return preferred;

        const QString alternate = QStringLiteral("D:\\AI_ASSETS\\models");
        if (QDir(alternate).exists())
            return QDir::fromNativeSeparators(QDir(alternate).absolutePath());

        return preferred;
    }

    QString chooseComfyOutputPath()
    {
        const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_COMFY")).trimmed();
        if (!envPath.isEmpty() && QDir(envPath).exists())
            return QDir(QDir::fromNativeSeparators(QDir(envPath).absolutePath())).filePath(QStringLiteral("output"));

        const QString preferred = QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI");
        if (QDir(preferred).exists())
            return QDir(preferred).filePath(QStringLiteral("output"));

        return QDir::fromNativeSeparators(QDir(preferred).filePath(QStringLiteral("output")));
    }

    QStringList modelNameFilters()
    {
        return {
            QStringLiteral("*.safetensors"),
            QStringLiteral("*.ckpt"),
            QStringLiteral("*.pt"),
            QStringLiteral("*.pth"),
            QStringLiteral("*.bin")};
    }

    QVector<CatalogEntry> scanCatalog(const QString &rootPath, const QString &subDir)
    {
        QVector<CatalogEntry> entries;
        if (rootPath.trimmed().isEmpty())
            return entries;

        const QString targetDir = QDir(rootPath).filePath(subDir);
        if (!QDir(targetDir).exists())
            return entries;

        QStringList absolutePaths;
        QHash<QString, int> baseNameCounts;

        QDirIterator it(targetDir,
                        modelNameFilters(),
                        QDir::Files,
                        QDirIterator::Subdirectories);

        while (it.hasNext())
        {
            const QString absolutePath = QDir::fromNativeSeparators(it.next());
            absolutePaths.push_back(absolutePath);

            const QFileInfo info(absolutePath);
            const QString baseKey = info.completeBaseName().trimmed().toLower();
            baseNameCounts[baseKey] += 1;
        }

        for (const QString &absolutePath : absolutePaths)
        {
            const QFileInfo info(absolutePath);
            const QString baseKey = info.completeBaseName().trimmed().toLower();
            const bool needsDisambiguator = baseNameCounts.value(baseKey) > 1;
            const QString display = compactCatalogDisplay(rootPath, absolutePath, needsDisambiguator);
            entries.push_back({display, absolutePath});
        }

        std::sort(entries.begin(), entries.end(), [](const CatalogEntry &lhs, const CatalogEntry &rhs) {
            return QString::compare(lhs.display, rhs.display, Qt::CaseInsensitive) < 0;
        });

        return entries;
    }

    void populateComboFromCatalog(QComboBox *combo,
                                  const QVector<CatalogEntry> &entries,
                                  const QStringList &fallbackItems = {})
    {
        if (!combo)
            return;

        const QString priorValue = comboStoredValue(combo);
        const QSignalBlocker blocker(combo);
        combo->clear();

        for (const CatalogEntry &entry : entries)
            combo->addItem(entry.display, entry.value);

        if (combo->count() == 0)
        {
            for (const QString &fallback : fallbackItems)
                combo->addItem(fallback, fallback);
        }

        if (!priorValue.isEmpty())
        {
            for (int index = 0; index < combo->count(); ++index)
            {
                if (combo->itemData(index, Qt::UserRole).toString().compare(priorValue, Qt::CaseInsensitive) == 0 ||
                    combo->itemText(index).compare(priorValue, Qt::CaseInsensitive) == 0)
                {
                    combo->setCurrentIndex(index);
                    return;
                }
            }

            if (combo->isEditable())
                combo->setEditText(priorValue);
        }
        else if (combo->count() > 0)
        {
            combo->setCurrentIndex(0);
        }
    }

    bool selectComboByContains(QComboBox *combo, const QStringList &needles)
    {
        if (!combo)
            return false;

        for (int index = 0; index < combo->count(); ++index)
        {
            const QString haystack = (combo->itemText(index) + QStringLiteral(" ") + combo->itemData(index, Qt::UserRole).toString()).toLower();
            for (const QString &needle : needles)
            {
                if (!needle.trimmed().isEmpty() && haystack.contains(needle.toLower()))
                {
                    combo->setCurrentIndex(index);
                    return true;
                }
            }
        }

        return false;
    }

    void configureComboBox(QComboBox *combo)
    {
        if (!combo)
            return;

        combo->setFocusPolicy(Qt::StrongFocus);
        combo->setMaxVisibleItems(18);
        combo->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);

        if (combo->view())
        {
            combo->view()->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
            combo->view()->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
            combo->view()->setTextElideMode(Qt::ElideMiddle);
        }
    }

    void configureSpinBox(QSpinBox *spin)
    {
        if (!spin)
            return;

        spin->setAccelerated(true);
        spin->setKeyboardTracking(false);
        spin->setButtonSymbols(QAbstractSpinBox::UpDownArrows);
        spin->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    }

    void configureDoubleSpinBox(QDoubleSpinBox *spin)
    {
        if (!spin)
            return;

        spin->setAccelerated(true);
        spin->setKeyboardTracking(false);
        spin->setButtonSymbols(QAbstractSpinBox::UpDownArrows);
        spin->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    }
}

ImageGenerationPage::ImageGenerationPage(Mode mode, QWidget *parent)
    : QWidget(parent),
      mode_(mode)
{
    buildUi();
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });
    reloadCatalogs();
    restoreSnapshot();
    refreshStackSummary();
    refreshPreview();
}

QJsonObject ImageGenerationPage::buildRequestPayload() const
{
    QJsonObject payload;
    payload.insert(QStringLiteral("mode"), modeKey());
    payload.insert(QStringLiteral("prompt"), promptEdit_ ? promptEdit_->toPlainText().trimmed() : QString());
    payload.insert(QStringLiteral("negative_prompt"), negativePromptEdit_ ? negativePromptEdit_->toPlainText().trimmed() : QString());
    payload.insert(QStringLiteral("preset"), currentComboValue(presetCombo_));
    payload.insert(QStringLiteral("model"), currentComboValue(modelCombo_));
    payload.insert(QStringLiteral("workflow_profile"), currentComboValue(workflowCombo_));
    payload.insert(QStringLiteral("lora_summary"), resolveLoraValue());
    payload.insert(QStringLiteral("sampler"), currentComboValue(samplerCombo_));
    payload.insert(QStringLiteral("scheduler"), currentComboValue(schedulerCombo_));
    payload.insert(QStringLiteral("steps"), stepsSpin_ ? stepsSpin_->value() : 0);
    const double cfgValue = cfgSpin_ ? cfgSpin_->value() : 0.0;
    payload.insert(QStringLiteral("cfg_scale"), cfgValue);
    payload.insert(QStringLiteral("cfg"), cfgValue);
    payload.insert(QStringLiteral("seed"), seedSpin_ ? seedSpin_->value() : 0);
    payload.insert(QStringLiteral("width"), widthSpin_ ? widthSpin_->value() : 0);
    payload.insert(QStringLiteral("height"), heightSpin_ ? heightSpin_->value() : 0);
    payload.insert(QStringLiteral("batch_count"), batchSpin_ ? batchSpin_->value() : 1);
    payload.insert(QStringLiteral("output_prefix"), outputPrefixEdit_ ? outputPrefixEdit_->text().trimmed() : QString());
    payload.insert(QStringLiteral("output_folder"), outputFolderLabel_ ? outputFolderLabel_->text() : QString());
    payload.insert(QStringLiteral("models_root"), modelsRootDir_);

    if (isImageInputMode())
    {
        payload.insert(QStringLiteral("input_image"), inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString());
        const double strengthValue = denoiseSpin_ ? denoiseSpin_->value() : 0.0;
        payload.insert(QStringLiteral("denoise_strength"), strengthValue);
        payload.insert(QStringLiteral("strength"), strengthValue);
    }

    return payload;
}


void ImageGenerationPage::applyTheme()
{
    setStyleSheet(ThemeManager::instance().imageGenerationStyleSheet());
}

void ImageGenerationPage::buildUi()
{
    setObjectName(QStringLiteral("ImageGenerationPage"));
    setAcceptDrops(isImageInputMode());

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(12, 8, 12, 12);
    root->setSpacing(10);


    auto *contentSplitter = new QSplitter(Qt::Horizontal, this);
    contentSplitter->setChildrenCollapsible(false);
    contentSplitter->setOpaqueResize(false);
    contentSplitter->setHandleWidth(8);

    auto *leftScroll = new QScrollArea(contentSplitter);
    leftScroll->setWidgetResizable(true);
    leftScroll->setFrameShape(QFrame::NoFrame);
    leftScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    leftScroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    leftScroll->setMinimumWidth(300);
    leftScroll->setMaximumWidth(374);

    auto *leftContainer = new QWidget(leftScroll);
    auto *leftLayout = new QVBoxLayout(leftContainer);
    leftLayout->setContentsMargins(0, 0, 4, 0);
    leftLayout->setSpacing(14);
    leftLayout->setSizeConstraint(QLayout::SetMinAndMaxSize);

    auto *promptCard = createCard(QStringLiteral("ImageGenCard"));
    auto *promptLayout = new QVBoxLayout(promptCard);
    promptLayout->setContentsMargins(16, 14, 16, 14);
    promptLayout->setSpacing(8);
    promptLayout->addWidget(createSectionTitle(QStringLiteral("Prompt Builder"), promptCard));
    promptLayout->addWidget(createSectionBody(isVideoMode() ? QStringLiteral("The video modes keep the same guided shell now so timeline and shot tooling can slot in later without rebuilding the page.") : QStringLiteral("Keep the heavy diagnostics in the shell when you need them. The main workspace should stay focused on the prompt and the image."), promptCard));

    presetCombo_ = new ClickOnlyComboBox(promptCard);
    presetCombo_->setEditable(false);
    presetCombo_->addItem(QStringLiteral("Balanced"), QStringLiteral("Balanced"));
    presetCombo_->addItem(QStringLiteral("Portrait Detail"), QStringLiteral("Portrait Detail"));
    presetCombo_->addItem(QStringLiteral("Stylized Concept"), QStringLiteral("Stylized Concept"));
    presetCombo_->addItem(QStringLiteral("Upscale / Repair"), QStringLiteral("Upscale / Repair"));
    presetCombo_->addItem(QStringLiteral("Custom"), QStringLiteral("Custom"));
    configureComboBox(presetCombo_);

    auto *presetRow = new QHBoxLayout;
    presetRow->setSpacing(8);
    auto *applyPresetButton = new QPushButton(QStringLiteral("Apply Preset"), promptCard);
    applyPresetButton->setMaximumWidth(88);
    connect(applyPresetButton, &QPushButton::clicked, this, [this]() { applyPreset(presetCombo_->currentText()); });
    presetRow->addWidget(new QLabel(QStringLiteral("Preset"), promptCard));
    presetRow->addWidget(presetCombo_, 1);
    presetRow->addWidget(applyPresetButton);
    promptLayout->addLayout(presetRow);

    promptEdit_ = new QTextEdit(promptCard);
    promptEdit_->setPlaceholderText(QStringLiteral("Describe the subject, framing, camera, lighting, materials, style cues, and any production notes here…"));
    promptEdit_->setMinimumHeight(110);

    negativePromptEdit_ = new QTextEdit(promptCard);
    negativePromptEdit_->setPlaceholderText(QStringLiteral("Low quality, blurry, extra fingers, watermark, text, duplicate limbs…"));
    negativePromptEdit_->setMinimumHeight(72);

    promptLayout->addWidget(createSectionTitle(QStringLiteral("Prompt"), promptCard));
    promptLayout->addWidget(promptEdit_);
    promptLayout->addWidget(createSectionTitle(QStringLiteral("Negative Prompt"), promptCard));
    promptLayout->addWidget(negativePromptEdit_);

    leftLayout->addWidget(promptCard);

    inputCard_ = createCard(QStringLiteral("ImageGenCard"));
    auto *inputLayout = new QVBoxLayout(inputCard_);
    inputLayout->setContentsMargins(16, 14, 16, 14);
    inputLayout->setSpacing(8);
    inputLayout->addWidget(createSectionTitle(isVideoMode() ? QStringLiteral("Input Keyframe") : QStringLiteral("Input Image"), inputCard_));
    inputLayout->addWidget(createSectionBody(isVideoMode() ? QStringLiteral("Drop a still image or keyframe here. Until motion output exists, the canvas mirrors this source image as the starting point.") : QStringLiteral("Drop a source image here or browse for one. Until you generate a new result, the canvas will mirror this source image."), inputCard_));

    auto *dropFrame = new DropTargetFrame(inputCard_);
    dropFrame->setObjectName(QStringLiteral("ImageGenCard"));
    auto *dropLayout = new QVBoxLayout(dropFrame);
    dropLayout->setContentsMargins(14, 14, 14, 14);
    dropLayout->setSpacing(8);
    inputDropLabel_ = new QLabel(isVideoMode() ? QStringLiteral("Drop a still image or keyframe here, or click Browse to select one.") : QStringLiteral("Drop an image here or click Browse to select a source image."), dropFrame);
    inputDropLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    inputDropLabel_->setWordWrap(true);
    dropLayout->addWidget(inputDropLabel_);

    inputImageEdit_ = new QLineEdit(inputCard_);
    inputImageEdit_->setPlaceholderText(isVideoMode() ? QStringLiteral("No keyframe selected") : QStringLiteral("No input image selected"));

    auto *inputButtonRow = new QHBoxLayout;
    auto *browseButton = new QPushButton(QStringLiteral("Browse"), inputCard_);
    auto *clearInputButton = new QPushButton(QStringLiteral("Clear"), inputCard_);
    connect(browseButton, &QPushButton::clicked, this, [this]() {
        const QString filePath = QFileDialog::getOpenFileName(
            this,
            QStringLiteral("Choose input image"),
            QString(),
            QStringLiteral("Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"));
        if (!filePath.isEmpty())
            setInputImagePath(filePath);
    });
    connect(clearInputButton, &QPushButton::clicked, this, [this]() { setInputImagePath(QString()); });
    inputButtonRow->addWidget(browseButton);
    inputButtonRow->addWidget(clearInputButton);
    inputButtonRow->addStretch(1);

    dropFrame->onFileDropped = [this](const QString &path) { setInputImagePath(path); };

    inputLayout->addWidget(dropFrame);
    inputLayout->addWidget(inputImageEdit_);
    inputLayout->addLayout(inputButtonRow);
    inputCard_->setVisible(isImageInputMode());
    leftLayout->addWidget(inputCard_);

    auto *settingsCard = createCard(QStringLiteral("ImageGenCard"));
    auto *settingsLayout = new QVBoxLayout(settingsCard);
    settingsLayout->setContentsMargins(16, 14, 16, 14);
    settingsLayout->setSpacing(8);
    settingsLayout->addWidget(createSectionTitle(isVideoMode() ? QStringLiteral("Frames / Motion") : QStringLiteral("Generation Settings"), settingsCard));

    auto *form = new QGridLayout;
    form->setHorizontalSpacing(10);
    form->setVerticalSpacing(8);

    modelCombo_ = new ClickOnlyComboBox(settingsCard);
    modelCombo_->setEditable(true);
    modelCombo_->setInsertPolicy(QComboBox::NoInsert);
    modelCombo_->setPlaceholderText(QStringLiteral("Checkpoint path or repo id"));
    modelCombo_->setMinimumContentsLength(12);
    configureComboBox(modelCombo_);

    workflowCombo_ = new ClickOnlyComboBox(settingsCard);
    workflowCombo_->setEditable(false);
    workflowCombo_->addItem(QStringLiteral("Default Canvas"), QStringLiteral("Default Canvas"));
    workflowCombo_->addItem(QStringLiteral("Portrait Detail"), QStringLiteral("Portrait Detail"));
    workflowCombo_->addItem(QStringLiteral("Stylized Concept"), QStringLiteral("Stylized Concept"));
    workflowCombo_->addItem(QStringLiteral("Upscale / Repair"), QStringLiteral("Upscale / Repair"));
    workflowCombo_->setMinimumContentsLength(10);
    configureComboBox(workflowCombo_);

    loraCombo_ = new ClickOnlyComboBox(settingsCard);
    loraCombo_->setEditable(true);
    loraCombo_->setInsertPolicy(QComboBox::NoInsert);
    loraCombo_->setPlaceholderText(QStringLiteral("Optional single LoRA from loras/ or full file path"));
    loraCombo_->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    loraCombo_->setMinimumContentsLength(11);
    configureComboBox(loraCombo_);

    samplerCombo_ = new ClickOnlyComboBox(settingsCard);
    samplerCombo_->addItem(QStringLiteral("euler"), QStringLiteral("euler"));
    samplerCombo_->addItem(QStringLiteral("euler_ancestral"), QStringLiteral("euler_ancestral"));
    samplerCombo_->addItem(QStringLiteral("heun"), QStringLiteral("heun"));
    samplerCombo_->addItem(QStringLiteral("dpmpp_2m"), QStringLiteral("dpmpp_2m"));
    samplerCombo_->addItem(QStringLiteral("dpmpp_sde"), QStringLiteral("dpmpp_sde"));
    samplerCombo_->addItem(QStringLiteral("uni_pc"), QStringLiteral("uni_pc"));
    configureComboBox(samplerCombo_);

    schedulerCombo_ = new ClickOnlyComboBox(settingsCard);
    schedulerCombo_->addItem(QStringLiteral("normal"), QStringLiteral("normal"));
    schedulerCombo_->addItem(QStringLiteral("karras"), QStringLiteral("karras"));
    schedulerCombo_->addItem(QStringLiteral("sgm_uniform"), QStringLiteral("sgm_uniform"));
    configureComboBox(schedulerCombo_);

    stepsSpin_ = new QSpinBox(settingsCard);
    stepsSpin_->setRange(1, 200);
    stepsSpin_->setSingleStep(1);
    stepsSpin_->setValue(28);
    configureSpinBox(stepsSpin_);

    cfgSpin_ = new QDoubleSpinBox(settingsCard);
    cfgSpin_->setDecimals(1);
    cfgSpin_->setSingleStep(0.5);
    cfgSpin_->setRange(1.0, 30.0);
    cfgSpin_->setValue(7.0);
    configureDoubleSpinBox(cfgSpin_);

    seedSpin_ = new QSpinBox(settingsCard);
    seedSpin_->setRange(0, 999999999);
    seedSpin_->setSpecialValueText(QStringLiteral("Random"));
    seedSpin_->setSingleStep(1);
    seedSpin_->setValue(0);
    configureSpinBox(seedSpin_);

    widthSpin_ = new QSpinBox(settingsCard);
    widthSpin_->setRange(64, 8192);
    widthSpin_->setSingleStep(64);
    widthSpin_->setValue(1024);
    configureSpinBox(widthSpin_);

    heightSpin_ = new QSpinBox(settingsCard);
    heightSpin_->setRange(64, 8192);
    heightSpin_->setSingleStep(64);
    heightSpin_->setValue(1024);
    configureSpinBox(heightSpin_);

    batchSpin_ = new QSpinBox(settingsCard);
    batchSpin_->setRange(1, 32);
    batchSpin_->setSingleStep(1);
    batchSpin_->setValue(1);
    configureSpinBox(batchSpin_);

    denoiseSpin_ = new QDoubleSpinBox(settingsCard);
    denoiseSpin_->setDecimals(2);
    denoiseSpin_->setSingleStep(0.05);
    denoiseSpin_->setRange(0.0, 1.0);
    denoiseSpin_->setValue(0.45);
    configureDoubleSpinBox(denoiseSpin_);

    int row = 0;
    form->setColumnStretch(1, 1);
    form->setColumnStretch(3, 1);

    form->addWidget(new QLabel(QStringLiteral("Model"), settingsCard), row, 0);
    form->addWidget(modelCombo_, row, 1);
    form->addWidget(new QLabel(QStringLiteral("Workflow"), settingsCard), row, 2);
    form->addWidget(workflowCombo_, row, 3);
    ++row;

    form->addWidget(new QLabel(QStringLiteral("LoRA"), settingsCard), row, 0);
    form->addWidget(loraCombo_, row, 1, 1, 3);
    ++row;

    form->addWidget(new QLabel(QStringLiteral("Sampler"), settingsCard), row, 0);
    form->addWidget(samplerCombo_, row, 1);
    form->addWidget(new QLabel(QStringLiteral("Scheduler"), settingsCard), row, 2);
    form->addWidget(schedulerCombo_, row, 3);
    ++row;

    form->addWidget(new QLabel(QStringLiteral("Steps"), settingsCard), row, 0);
    form->addWidget(stepsSpin_, row, 1);
    form->addWidget(new QLabel(QStringLiteral("CFG"), settingsCard), row, 2);
    form->addWidget(cfgSpin_, row, 3);
    ++row;

    form->addWidget(new QLabel(QStringLiteral("Seed"), settingsCard), row, 0);
    form->addWidget(seedSpin_, row, 1);
    form->addWidget(new QLabel(QStringLiteral("Batch"), settingsCard), row, 2);
    form->addWidget(batchSpin_, row, 3);
    ++row;

    form->addWidget(new QLabel(QStringLiteral("Width"), settingsCard), row, 0);
    form->addWidget(widthSpin_, row, 1);
    form->addWidget(new QLabel(QStringLiteral("Height"), settingsCard), row, 2);
    form->addWidget(heightSpin_, row, 3);
    ++row;

    denoiseRow_ = new QWidget(settingsCard);
    auto *denoiseRowLayout = new QHBoxLayout(denoiseRow_);
    denoiseRowLayout->setContentsMargins(0, 0, 0, 0);
    denoiseRowLayout->setSpacing(10);
    denoiseRowLayout->addWidget(new QLabel(QStringLiteral("Denoise Strength"), denoiseRow_));
    denoiseRowLayout->addWidget(denoiseSpin_);
    denoiseRowLayout->addStretch(1);
    denoiseRow_->setVisible(usesStrengthControl());

    settingsLayout->addLayout(form);
    settingsLayout->addWidget(denoiseRow_);

    modelsRootLabel_ = new QLabel(settingsCard);
    modelsRootLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    modelsRootLabel_->setWordWrap(true);
    settingsLayout->addWidget(modelsRootLabel_);

    leftLayout->addWidget(settingsCard);

    auto *outputCard = createCard(QStringLiteral("ImageGenCard"));
    auto *outputLayout = new QVBoxLayout(outputCard);
    outputLayout->setContentsMargins(16, 14, 16, 14);
    outputLayout->setSpacing(8);
    outputLayout->addWidget(createSectionTitle(isVideoMode() ? QStringLiteral("Output / Queue") : QStringLiteral("Output & Stack"), outputCard));

    outputPrefixEdit_ = new QLineEdit(outputCard);
    outputPrefixEdit_->setPlaceholderText(QStringLiteral("spellvision_render"));

    outputFolderLabel_ = new QLabel(QDir::toNativeSeparators(chooseComfyOutputPath()), outputCard);
    outputFolderLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    outputFolderLabel_->setWordWrap(true);

    stackSummaryLabel_ = new QLabel(outputCard);
    stackSummaryLabel_->setObjectName(QStringLiteral("StackSummary"));
    stackSummaryLabel_->setWordWrap(true);

    auto *quickToolsRow = new QHBoxLayout;
    auto *openModelsButton = new QPushButton(QStringLiteral("Open Models"), outputCard);
    auto *openWorkflowsButton = new QPushButton(QStringLiteral("Open Workflows"), outputCard);
    connect(openModelsButton, &QPushButton::clicked, this, &ImageGenerationPage::openModelsRequested);
    connect(openWorkflowsButton, &QPushButton::clicked, this, &ImageGenerationPage::openWorkflowsRequested);
    quickToolsRow->addWidget(openModelsButton);
    quickToolsRow->addWidget(openWorkflowsButton);

    outputLayout->addWidget(new QLabel(QStringLiteral("Filename Prefix"), outputCard));
    outputLayout->addWidget(outputPrefixEdit_);
    outputLayout->addWidget(new QLabel(QStringLiteral("Output Folder"), outputCard));
    outputLayout->addWidget(outputFolderLabel_);
    outputLayout->addWidget(createSectionBody(QStringLiteral("Queue and logs stay available from View. Right-side telemetry and details remain visible for generation feedback."), outputCard));
    outputLayout->addWidget(stackSummaryLabel_);
    outputLayout->addLayout(quickToolsRow);

    leftLayout->addWidget(outputCard);
    leftLayout->addStretch(1);

    leftScroll->setWidget(leftContainer);

    auto *rightContainer = new QWidget(contentSplitter);
    auto *rightLayout = new QVBoxLayout(rightContainer);
    rightLayout->setContentsMargins(0, 0, 0, 0);
    rightLayout->setSpacing(12);

    auto *canvasCard = createCard(QStringLiteral("ImageGenCard"));
    auto *canvasLayout = new QVBoxLayout(canvasCard);
    canvasLayout->setContentsMargins(18, 16, 18, 16);
    canvasLayout->setSpacing(12);

    auto *canvasTopRow = new QHBoxLayout;
    auto *canvasTitle = createSectionTitle(isVideoMode() ? QStringLiteral("Preview / Output") : QStringLiteral("Canvas"), canvasCard);
    auto *canvasHint = createSectionBody(isVideoMode() ? QStringLiteral("This shell reserves the center for preview, frame strips, and output review as video tooling lands. Use docks only when you need queue or diagnostic context.") : QStringLiteral("The generated image stays front-and-center here. Use View to reopen shell docks only when you need diagnostics or queue controls."), canvasCard);
    canvasTopRow->addWidget(canvasTitle, 0, Qt::AlignVCenter);
    canvasTopRow->addStretch(1);

    canvasLayout->addLayout(canvasTopRow);
    canvasLayout->addWidget(canvasHint);

    previewLabel_ = new QLabel(canvasCard);
    previewLabel_->setObjectName(QStringLiteral("PreviewSurface"));
    previewLabel_->setAlignment(Qt::AlignCenter);
    previewLabel_->setMinimumHeight(720);
    previewLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    previewLabel_->setWordWrap(true);

    previewSummaryLabel_ = new QLabel(canvasCard);
    previewSummaryLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    previewSummaryLabel_->setWordWrap(true);

    auto *actionRow = new QHBoxLayout;
    actionRow->setSpacing(10);
    generateButton_ = new QPushButton(QStringLiteral("Generate"), canvasCard);
    generateButton_->setObjectName(QStringLiteral("PrimaryActionButton"));
    queueButton_ = new QPushButton(QStringLiteral("Queue"), canvasCard);
    savePresetButton_ = new QPushButton(QStringLiteral("Save Snapshot"), canvasCard);
    clearButton_ = new QPushButton(QStringLiteral("Reset"), canvasCard);

    connect(generateButton_, &QPushButton::clicked, this, [this]() { emit generateRequested(buildRequestPayload()); });
    connect(queueButton_, &QPushButton::clicked, this, [this]() { emit queueRequested(buildRequestPayload()); });
    connect(savePresetButton_, &QPushButton::clicked, this, [this]() { saveSnapshot(); });
    connect(clearButton_, &QPushButton::clicked, this, [this]() { clearForm(); });

    actionRow->addWidget(generateButton_);
    actionRow->addWidget(queueButton_);
    actionRow->addStretch(1);
    actionRow->addWidget(savePresetButton_);
    actionRow->addWidget(clearButton_);

    canvasLayout->addWidget(previewLabel_, 1);
    canvasLayout->addWidget(previewSummaryLabel_);
    canvasLayout->addLayout(actionRow);

    rightLayout->addWidget(canvasCard, 1);

    contentSplitter->addWidget(leftScroll);
    contentSplitter->addWidget(rightContainer);
    contentSplitter->setStretchFactor(0, 1);
    contentSplitter->setStretchFactor(1, 3);
    contentSplitter->setSizes({332, 1568});

    root->addWidget(contentSplitter, 1);

    const auto refreshers = [this]() {
        refreshStackSummary();
        refreshPreview();
    };

    connect(promptEdit_, &QTextEdit::textChanged, this, refreshers);
    connect(negativePromptEdit_, &QTextEdit::textChanged, this, refreshers);
    connect(modelCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(workflowCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(loraCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(samplerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(schedulerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(modelCombo_, &QComboBox::currentTextChanged, this, [this]() {
        if (modelCombo_)
            modelCombo_->setToolTip(currentComboValue(modelCombo_));
    });
    connect(loraCombo_, &QComboBox::currentTextChanged, this, [this]() {
        if (loraCombo_)
            loraCombo_->setToolTip(resolveLoraValue());
    });
    connect(workflowCombo_, &QComboBox::currentTextChanged, this, [this]() {
        if (workflowCombo_)
            workflowCombo_->setToolTip(currentComboValue(workflowCombo_));
    });
    connect(stepsSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(cfgSpin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    connect(seedSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(widthSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(heightSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(batchSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(outputPrefixEdit_, &QLineEdit::textChanged, this, refreshers);
    if (denoiseSpin_)
        connect(denoiseSpin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    if (inputImageEdit_)
        connect(inputImageEdit_, &QLineEdit::textChanged, this, refreshers);

    setWorkspaceTelemetry(QStringLiteral("Runtime: Managed ComfyUI"),
                          QStringLiteral("Queue: 0 running | 0 pending"),
                          QStringLiteral("Model: none"),
                          QStringLiteral("LoRA: none"),
                          0,
                          QStringLiteral("Idle"));
}



void ImageGenerationPage::reloadCatalogs()
{
    modelsRootDir_ = chooseModelsRootPath();

    if (modelsRootLabel_)
    {
        const QString rootText = QDir::toNativeSeparators(modelsRootDir_);
        modelsRootLabel_->setText(QStringLiteral("Assets: %1\nDropdowns show compact names; full paths stay available in tooltips.")
                                      .arg(rootText));
    }

    populateComboFromCatalog(
        modelCombo_,
        scanCatalog(modelsRootDir_, QStringLiteral("checkpoints")),
        {QStringLiteral("sdxl")});

    loraPathByDisplay_.clear();
    QVector<CatalogEntry> loras = scanCatalog(modelsRootDir_, QStringLiteral("loras"));

    if (loraCombo_)
    {
        const QString priorValue = currentComboValue(loraCombo_);
        const QSignalBlocker blocker(loraCombo_);
        loraCombo_->clear();
        loraCombo_->addItem(QStringLiteral("(none)"), QString());

        QStringList loraDisplays;
        loraDisplays.reserve(loras.size());

        for (const CatalogEntry &entry : loras)
        {
            loraCombo_->addItem(entry.display, entry.value);
            loraPathByDisplay_.insert(entry.display, entry.value);
            loraDisplays.push_back(entry.display);
        }

        auto *completer = new QCompleter(loraDisplays, loraCombo_);
        completer->setCaseSensitivity(Qt::CaseInsensitive);
        completer->setFilterMode(Qt::MatchContains);
        completer->setCompletionMode(QCompleter::PopupCompletion);
        loraCombo_->setCompleter(completer);

        if (!priorValue.trimmed().isEmpty())
        {
            if (!selectComboValue(loraCombo_, priorValue))
                loraCombo_->setCurrentText(priorValue);
        }
        else
        {
            loraCombo_->setCurrentIndex(0);
        }

        loraCombo_->setToolTip(resolveLoraValue());
    }

    if (modelCombo_)
        modelCombo_->setToolTip(currentComboValue(modelCombo_));
    if (workflowCombo_)
        workflowCombo_->setToolTip(currentComboValue(workflowCombo_));
}

void ImageGenerationPage::applyPreset(const QString &presetName)
{
    if (presetName == QStringLiteral("Portrait Detail"))
    {
        promptEdit_->setPlainText(QStringLiteral("portrait of a confident fantasy heroine, detailed face, studio rim lighting, shallow depth of field, high micro-detail"));
        negativePromptEdit_->setPlainText(QStringLiteral("blurry, low quality, extra fingers, malformed hands, watermark, text"));
        selectComboByContains(modelCombo_, {QStringLiteral("sdxl"), QStringLiteral("xl")});
        selectComboValue(workflowCombo_, QStringLiteral("Portrait Detail"));
        if (loraCombo_) loraCombo_->setCurrentText(QString());
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
        stepsSpin_->setValue(35);
        cfgSpin_->setValue(6.5);
        widthSpin_->setValue(1024);
        heightSpin_->setValue(1344);
    }
    else if (presetName == QStringLiteral("Stylized Concept"))
    {
        promptEdit_->setPlainText(QStringLiteral("stylized concept art, dynamic pose, cinematic lighting, strong silhouette, clean material read, production concept render"));
        negativePromptEdit_->setPlainText(QStringLiteral("muddy colors, blurry, oversaturated, low detail, duplicate limbs"));
        selectComboByContains(modelCombo_, {QStringLiteral("flux"), QStringLiteral("sdxl"), QStringLiteral("xl")});
        selectComboValue(workflowCombo_, QStringLiteral("Stylized Concept"));
        if (loraCombo_) loraCombo_->setCurrentText(QString());
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_sde"));
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
        stepsSpin_->setValue(30);
        cfgSpin_->setValue(5.0);
        widthSpin_->setValue(1216);
        heightSpin_->setValue(832);
    }
    else if (presetName == QStringLiteral("Upscale / Repair"))
    {
        promptEdit_->setPlainText(QStringLiteral("restore detail, clean edges, improve texture fidelity, maintain original composition, crisp focus"));
        negativePromptEdit_->setPlainText(QStringLiteral("new objects, warped anatomy, duplicated features, heavy noise, blur"));
        selectComboByContains(modelCombo_, {QStringLiteral("juggernaut"), QStringLiteral("sdxl"), QStringLiteral("xl")});
        selectComboValue(workflowCombo_, QStringLiteral("Upscale / Repair"));
        if (loraCombo_) loraCombo_->setCurrentText(QString());
        if (!selectComboValue(samplerCombo_, QStringLiteral("uni_pc")))
            selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
        selectComboValue(schedulerCombo_, QStringLiteral("normal"));
        stepsSpin_->setValue(24);
        cfgSpin_->setValue(5.5);
        if (denoiseSpin_)
            denoiseSpin_->setValue(0.35);
    }
    else if (presetName == QStringLiteral("Balanced"))
    {
        promptEdit_->setPlainText(QStringLiteral("high quality image, clean composition, strong subject read, balanced lighting"));
        negativePromptEdit_->setPlainText(QStringLiteral("low quality, blurry, text, watermark"));
        if (modelCombo_ && modelCombo_->count() > 0)
            modelCombo_->setCurrentIndex(0);
        selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));
        if (loraCombo_) loraCombo_->setCurrentText(QString());
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
        stepsSpin_->setValue(28);
        cfgSpin_->setValue(7.0);
        widthSpin_->setValue(1024);
        heightSpin_->setValue(1024);
        if (denoiseSpin_)
            denoiseSpin_->setValue(0.45);
    }

    refreshStackSummary();
    refreshPreview();
}


void ImageGenerationPage::refreshPreview()
{
    if (!previewLabel_ || !previewSummaryLabel_)
        return;

    auto showPixmap = [this](const QPixmap &pixmap, const QString &summaryText) {
        if (pixmap.isNull())
            return;

        previewLabel_->setText(QString());
        const QSize target = previewLabel_->contentsRect().size().expandedTo(QSize(700, 520));
        previewLabel_->setPixmap(pixmap.scaled(target, Qt::KeepAspectRatio, Qt::SmoothTransformation));
        previewSummaryLabel_->setText(summaryText);
    };

    if (!generatedPreviewPath_.trimmed().isEmpty() && QFileInfo::exists(generatedPreviewPath_))
    {
        const QPixmap pixmap(generatedPreviewPath_);
        if (!pixmap.isNull())
        {
            const QString summary = !generatedPreviewCaption_.trimmed().isEmpty()
                ? generatedPreviewCaption_.trimmed()
                : QStringLiteral("Latest result: %1\n%2 × %3")
                      .arg(QFileInfo(generatedPreviewPath_).fileName())
                      .arg(pixmap.width())
                      .arg(pixmap.height());
            showPixmap(pixmap, summary);
            return;
        }
    }

    if (isImageInputMode())
    {
        const QString path = inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString();
        if (!path.isEmpty() && QFileInfo::exists(path))
        {
            const QPixmap pixmap(path);
            if (!pixmap.isNull())
            {
                showPixmap(
                    pixmap,
                    QStringLiteral("%1: %2\nStrength: %3    Sampler: %4    Steps: %5").arg(isVideoMode() ? QStringLiteral("Keyframe") : QStringLiteral("Source image"))
                        .arg(QFileInfo(path).fileName())
                        .arg(denoiseSpin_ ? QString::number(denoiseSpin_->value(), 'f', 2) : QStringLiteral("n/a"))
                        .arg(comboDisplayValue(samplerCombo_))
                        .arg(stepsSpin_ ? stepsSpin_->value() : 0));
                return;
            }
        }
    }

    previewLabel_->setPixmap(QPixmap());
    previewLabel_->setText(busy_
        ? (busyMessage_.isEmpty()
               ? QStringLiteral("Generation in progress…")
               : busyMessage_)
        : (isImageInputMode()
               ? QStringLiteral("No source image or generated output yet.\n\nDrop an image into the Input Image card or browse for one.")
               : (isVideoMode() ? QStringLiteral("Your preview timeline and generated output will appear here.\n\nBuild the prompt and motion stack on the left, then generate.") : QStringLiteral("Your generated image will appear here.\n\nBuild the prompt and stack on the left, then generate."))));

    const QString promptSummary = promptEdit_ && !promptEdit_->toPlainText().trimmed().isEmpty()
        ? promptEdit_->toPlainText().trimmed().left(180)
        : QStringLiteral("No prompt entered yet.");

    previewSummaryLabel_->setText(QStringLiteral("Prompt: %1\nResolution: %2 × %3    Batch: %4")
                                      .arg(promptSummary)
                                      .arg(widthSpin_ ? widthSpin_->value() : 0)
                                      .arg(heightSpin_ ? heightSpin_->value() : 0)
                                      .arg(batchSpin_ ? batchSpin_->value() : 1));
}


void ImageGenerationPage::refreshStackSummary()
{
    if (!stackSummaryLabel_)
        return;

    const QString denoiseText = usesStrengthControl() && denoiseSpin_
        ? QStringLiteral("\nDenoise Strength: %1").arg(QString::number(denoiseSpin_->value(), 'f', 2))
        : QString();

    stackSummaryLabel_->setText(
        QStringLiteral("%1: %2\nWorkflow: %3\nLoRA: %4\nSampler: %5 / %6\nSteps: %7    CFG: %8    Seed: %9%10").arg(isVideoMode() ? QStringLiteral("Model / Motion") : QStringLiteral("Model"))
            .arg(shortDisplayFromValue(currentComboValue(modelCombo_)))
            .arg(comboDisplayValue(workflowCombo_).isEmpty() ? QStringLiteral("none") : comboDisplayValue(workflowCombo_))
            .arg(shortDisplayFromValue(resolveLoraValue()))
            .arg(comboDisplayValue(samplerCombo_).isEmpty() ? QStringLiteral("none") : comboDisplayValue(samplerCombo_))
            .arg(comboDisplayValue(schedulerCombo_).isEmpty() ? QStringLiteral("none") : comboDisplayValue(schedulerCombo_))
            .arg(stepsSpin_ ? stepsSpin_->value() : 0)
            .arg(cfgSpin_ ? QString::number(cfgSpin_->value(), 'f', 1) : QStringLiteral("0.0"))
            .arg(seedSpin_ ? (seedSpin_->value() == 0 ? QStringLiteral("random") : QString::number(seedSpin_->value())) : QStringLiteral("random"))
            .arg(denoiseText));
}

void ImageGenerationPage::setInputImagePath(const QString &path)
{
    if (!inputImageEdit_ || !inputDropLabel_)
        return;

    generatedPreviewPath_.clear();
    generatedPreviewCaption_.clear();

    inputImageEdit_->setText(path);
    inputDropLabel_->setText(path.isEmpty()
        ? QStringLiteral("Drop an image here or click Browse to select a source image.")
        : QStringLiteral("Current source image:\n%1").arg(path));
    refreshPreview();
}


void ImageGenerationPage::setPreviewImage(const QString &imagePath, const QString &caption)
{
    generatedPreviewPath_ = imagePath.trimmed();
    generatedPreviewCaption_ = caption.trimmed();
    busy_ = false;
    busyMessage_.clear();
    refreshPreview();
}

void ImageGenerationPage::setBusy(bool busy, const QString &message)
{
    busy_ = busy;
    busyMessage_ = message.trimmed();

    if (generateButton_)
        generateButton_->setEnabled(!busy);
    if (queueButton_)
        queueButton_->setEnabled(!busy);
    if (savePresetButton_)
        savePresetButton_->setEnabled(!busy);
    if (clearButton_)
        clearButton_->setEnabled(!busy);

    refreshPreview();
}


void ImageGenerationPage::setWorkspaceTelemetry(const QString &runtime,
                                                const QString &queue,
                                                const QString &model,
                                                const QString &lora,
                                                int progressPercent,
                                                const QString &progressText)
{
    if (headerRuntimeLabel_)
        headerRuntimeLabel_->setText(runtime.trimmed().isEmpty() ? QStringLiteral("Runtime: Managed ComfyUI") : runtime.trimmed());
    if (headerQueueLabel_)
        headerQueueLabel_->setText(queue.trimmed().isEmpty() ? QStringLiteral("Queue: 0 running | 0 pending") : queue.trimmed());
    if (headerModelLabel_)
        headerModelLabel_->setText(model.trimmed().isEmpty() ? QStringLiteral("Model: none") : model.trimmed());
    if (headerLoraLabel_)
        headerLoraLabel_->setText(lora.trimmed().isEmpty() ? QStringLiteral("LoRA: none") : lora.trimmed());

    const QString normalizedProgressText = progressText.trimmed().isEmpty() ? QStringLiteral("Idle") : progressText.trimmed();

    if (headerProgressBar_)
    {
        headerProgressBar_->setValue(qBound(0, progressPercent, 100));
        headerProgressBar_->setFormat(QStringLiteral("%1   %2%").arg(normalizedProgressText, QString::number(qBound(0, progressPercent, 100))));
        headerProgressBar_->setToolTip(normalizedProgressText);
    }
    if (headerProgressTextLabel_)
        headerProgressTextLabel_->setText(normalizedProgressText);
}

void ImageGenerationPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    refreshPreview();
}


void ImageGenerationPage::clearForm()
{
    if (presetCombo_)
        presetCombo_->setCurrentText(QStringLiteral("Balanced"));

    if (promptEdit_)
        promptEdit_->clear();
    if (negativePromptEdit_)
        negativePromptEdit_->clear();
    if (inputImageEdit_)
        inputImageEdit_->clear();
    if (modelCombo_)
    {
        if (modelCombo_->count() > 0)
            modelCombo_->setCurrentIndex(0);
        else
            modelCombo_->setEditText(QString());
    }
    if (workflowCombo_)
        selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));
    if (loraCombo_)
        loraCombo_->setCurrentText(QString());
    if (samplerCombo_)
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
    if (schedulerCombo_)
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
    if (stepsSpin_)
        stepsSpin_->setValue(28);
    if (cfgSpin_)
        cfgSpin_->setValue(7.0);
    if (seedSpin_)
        seedSpin_->setValue(0);
    if (widthSpin_)
        widthSpin_->setValue(1024);
    if (heightSpin_)
        heightSpin_->setValue(1024);
    if (batchSpin_)
        batchSpin_->setValue(1);
    if (denoiseSpin_)
        denoiseSpin_->setValue(0.45);
    if (outputPrefixEdit_)
        outputPrefixEdit_->clear();

    generatedPreviewPath_.clear();
    generatedPreviewCaption_.clear();
    busy_ = false;
    busyMessage_.clear();

    setInputImagePath(QString());
    if (generateButton_)
        generateButton_->setEnabled(true);
    if (queueButton_)
        queueButton_->setEnabled(true);
    if (savePresetButton_)
        savePresetButton_->setEnabled(true);
    if (clearButton_)
        clearButton_->setEnabled(true);
    refreshStackSummary();
    refreshPreview();
}

void ImageGenerationPage::saveSnapshot() const
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString group = QStringLiteral("ImageGenerationPage/%1").arg(modeKey());

    settings.beginGroup(group);
    settings.setValue(QStringLiteral("preset"), currentComboValue(presetCombo_));
    settings.setValue(QStringLiteral("prompt"), promptEdit_ ? promptEdit_->toPlainText() : QString());
    settings.setValue(QStringLiteral("negativePrompt"), negativePromptEdit_ ? negativePromptEdit_->toPlainText() : QString());
    settings.setValue(QStringLiteral("inputImage"), inputImageEdit_ ? inputImageEdit_->text() : QString());
    settings.setValue(QStringLiteral("model"), currentComboValue(modelCombo_));
    settings.setValue(QStringLiteral("workflow"), currentComboValue(workflowCombo_));
    settings.setValue(QStringLiteral("loraSummary"), resolveLoraValue());
    settings.setValue(QStringLiteral("loraDisplay"), loraCombo_ ? comboDisplayValue(loraCombo_) : QString());
    settings.setValue(QStringLiteral("sampler"), currentComboValue(samplerCombo_));
    settings.setValue(QStringLiteral("scheduler"), currentComboValue(schedulerCombo_));
    settings.setValue(QStringLiteral("steps"), stepsSpin_ ? stepsSpin_->value() : 28);
    settings.setValue(QStringLiteral("cfg"), cfgSpin_ ? cfgSpin_->value() : 7.0);
    settings.setValue(QStringLiteral("seed"), seedSpin_ ? seedSpin_->value() : 0);
    settings.setValue(QStringLiteral("width"), widthSpin_ ? widthSpin_->value() : 1024);
    settings.setValue(QStringLiteral("height"), heightSpin_ ? heightSpin_->value() : 1024);
    settings.setValue(QStringLiteral("batch"), batchSpin_ ? batchSpin_->value() : 1);
    settings.setValue(QStringLiteral("denoise"), denoiseSpin_ ? denoiseSpin_->value() : 0.45);
    settings.setValue(QStringLiteral("outputPrefix"), outputPrefixEdit_ ? outputPrefixEdit_->text() : QString());
    settings.endGroup();
}

void ImageGenerationPage::restoreSnapshot()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString group = QStringLiteral("ImageGenerationPage/%1").arg(modeKey());
    settings.beginGroup(group);

    if (presetCombo_)
        selectComboValue(presetCombo_, settings.value(QStringLiteral("preset"), QStringLiteral("Balanced")).toString());
    if (promptEdit_)
        promptEdit_->setPlainText(settings.value(QStringLiteral("prompt")).toString());
    if (negativePromptEdit_)
        negativePromptEdit_->setPlainText(settings.value(QStringLiteral("negativePrompt")).toString());
    if (modelCombo_)
        selectComboValue(modelCombo_, settings.value(QStringLiteral("model")).toString());
    if (workflowCombo_)
        selectComboValue(workflowCombo_, settings.value(QStringLiteral("workflow"), QStringLiteral("Default Canvas")).toString());
    if (loraCombo_)
    {
        const QString loraDisplay = settings.value(QStringLiteral("loraDisplay")).toString();
        const QString loraValue = settings.value(QStringLiteral("loraSummary")).toString();
        selectComboValue(loraCombo_, !loraDisplay.isEmpty() ? loraDisplay : loraValue);
    }
    if (samplerCombo_)
        selectComboValue(samplerCombo_, settings.value(QStringLiteral("sampler"), QStringLiteral("dpmpp_2m")).toString());
    if (schedulerCombo_)
        selectComboValue(schedulerCombo_, settings.value(QStringLiteral("scheduler"), QStringLiteral("karras")).toString());
    if (stepsSpin_)
        stepsSpin_->setValue(settings.value(QStringLiteral("steps"), 28).toInt());
    if (cfgSpin_)
        cfgSpin_->setValue(settings.value(QStringLiteral("cfg"), 7.0).toDouble());
    if (seedSpin_)
        seedSpin_->setValue(settings.value(QStringLiteral("seed"), 0).toInt());
    if (widthSpin_)
        widthSpin_->setValue(settings.value(QStringLiteral("width"), 1024).toInt());
    if (heightSpin_)
        heightSpin_->setValue(settings.value(QStringLiteral("height"), 1024).toInt());
    if (batchSpin_)
        batchSpin_->setValue(settings.value(QStringLiteral("batch"), 1).toInt());
    if (denoiseSpin_)
        denoiseSpin_->setValue(settings.value(QStringLiteral("denoise"), 0.45).toDouble());
    if (outputPrefixEdit_)
        outputPrefixEdit_->setText(settings.value(QStringLiteral("outputPrefix")).toString());

    setInputImagePath(settings.value(QStringLiteral("inputImage")).toString());
    settings.endGroup();
}

QString ImageGenerationPage::modeKey() const
{
    switch (mode_)
    {
    case Mode::TextToImage:
        return QStringLiteral("t2i");
    case Mode::ImageToImage:
        return QStringLiteral("i2i");
    case Mode::TextToVideo:
        return QStringLiteral("t2v");
    case Mode::ImageToVideo:
        return QStringLiteral("i2v");
    }
    return QStringLiteral("t2i");
}

QString ImageGenerationPage::modeTitle() const
{
    switch (mode_)
    {
    case Mode::TextToImage:
        return QStringLiteral("Text to Image");
    case Mode::ImageToImage:
        return QStringLiteral("Image to Image");
    case Mode::TextToVideo:
        return QStringLiteral("Text to Video");
    case Mode::ImageToVideo:
        return QStringLiteral("Image to Video");
    }
    return QStringLiteral("Text to Image");
}

bool ImageGenerationPage::isImageInputMode() const
{
    return mode_ == Mode::ImageToImage || mode_ == Mode::ImageToVideo;
}

bool ImageGenerationPage::isVideoMode() const
{
    return mode_ == Mode::TextToVideo || mode_ == Mode::ImageToVideo;
}

bool ImageGenerationPage::usesStrengthControl() const
{
    return isImageInputMode();
}

QString ImageGenerationPage::currentComboValue(const QComboBox *combo) const
{
    return comboStoredValue(combo);
}

bool ImageGenerationPage::selectComboValue(QComboBox *combo, const QString &value)
{
    if (!combo)
        return false;

    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return false;

    for (int index = 0; index < combo->count(); ++index)
    {
        if (combo->itemData(index, Qt::UserRole).toString().compare(trimmed, Qt::CaseInsensitive) == 0 ||
            combo->itemText(index).compare(trimmed, Qt::CaseInsensitive) == 0)
        {
            combo->setCurrentIndex(index);
            return true;
        }
    }

    if (combo->isEditable())
    {
        combo->setEditText(trimmed);
        return true;
    }

    return false;
}

QString ImageGenerationPage::resolveLoraValue() const
{
    const QString raw = loraCombo_ ? currentComboValue(loraCombo_).trimmed() : QString();
    if (raw.isEmpty())
        return QString();

    const auto it = loraPathByDisplay_.constFind(raw);
    if (it != loraPathByDisplay_.constEnd())
        return it.value();

    return raw;
}
