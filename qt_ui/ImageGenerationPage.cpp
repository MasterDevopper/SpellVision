#include "ImageGenerationPage.h"

#include "ThemeManager.h"

#include <QAbstractItemView>
#include <QAbstractSpinBox>
#include <QComboBox>
#include <QCompleter>
#include <QDir>
#include <QDirIterator>
#include <QDoubleSpinBox>
#include <QDropEvent>
#include <QDragEnterEvent>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QMimeData>
#include <QPixmap>
#include <QPushButton>
#include <QResizeEvent>
#include <QScrollArea>
#include <QSettings>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QSplitter>
#include <QTextEdit>
#include <QToolButton>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>
#include <QWheelEvent>

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
    label->setObjectName(QStringLiteral("SectionTitle"));
    return label;
}

QLabel *createSectionBody(const QString &text, QWidget *parent = nullptr)
{
    auto *label = new QLabel(text, parent);
    label->setWordWrap(true);
    label->setObjectName(QStringLiteral("SectionBody"));
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

    const QFileInfo pathInfo(trimmed);
    return pathInfo.completeBaseName().trimmed().isEmpty() ? pathInfo.fileName() : pathInfo.completeBaseName().trimmed();
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

    QDirIterator it(targetDir, modelNameFilters(), QDir::Files, QDirIterator::Subdirectories);

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
        entries.push_back({compactCatalogDisplay(rootPath, absolutePath, needsDisambiguator), absolutePath});
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
    combo->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

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
    spin->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

void configureDoubleSpinBox(QDoubleSpinBox *spin)
{
    if (!spin)
        return;

    spin->setAccelerated(true);
    spin->setKeyboardTracking(false);
    spin->setButtonSymbols(QAbstractSpinBox::UpDownArrows);
    spin->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    spin->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

QWidget *makeCollapsibleSection(QVBoxLayout *parentLayout,
                                const QString &title,
                                QWidget *body,
                                bool expanded = true)
{
    auto *container = new QWidget;
    auto *layout = new QVBoxLayout(container);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(8);

    auto *toggle = new QToolButton(container);
    toggle->setText(title);
    toggle->setCheckable(true);
    toggle->setChecked(expanded);
    toggle->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
    toggle->setArrowType(expanded ? Qt::DownArrow : Qt::RightArrow);
    toggle->setObjectName(QStringLiteral("SecondaryActionButton"));

    body->setVisible(expanded);

    QObject::connect(toggle, &QToolButton::toggled, body, [body, toggle](bool checked) {
        body->setVisible(checked);
        toggle->setArrowType(checked ? Qt::DownArrow : Qt::RightArrow);
    });

    layout->addWidget(toggle);
    layout->addWidget(body);
    parentLayout->addWidget(container);
    return container;
}
} // namespace

ImageGenerationPage::ImageGenerationPage(Mode mode, QWidget *parent)
    : QWidget(parent),
      mode_(mode)
{
    uiRefreshTimer_ = new QTimer(this);
    uiRefreshTimer_->setSingleShot(true);
    connect(uiRefreshTimer_, &QTimer::timeout, this, [this]() {
        refreshPreview();
    });

    previewResizeTimer_ = new QTimer(this);
    previewResizeTimer_->setSingleShot(true);
    connect(previewResizeTimer_, &QTimer::timeout, this, [this]() { refreshPreview(); });

    buildUi();
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });
    reloadCatalogs();
    restoreSnapshot();
    updateAdaptiveLayout();
    schedulePreviewRefresh(busy_ ? 0 : 30);
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

    const QString resolvedLora = resolveLoraValue();
    payload.insert(QStringLiteral("lora"), resolvedLora);
    payload.insert(QStringLiteral("lora_summary"), resolvedLora);
    payload.insert(QStringLiteral("lora_scale"), loraWeightSpin_ ? loraWeightSpin_->value() : 1.0);

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
    root->setContentsMargins(10, 8, 10, 10);
    root->setSpacing(10);

    contentSplitter_ = new QSplitter(Qt::Horizontal, this);
    contentSplitter_->setChildrenCollapsible(false);
    contentSplitter_->setOpaqueResize(false);
    contentSplitter_->setHandleWidth(8);

    leftScrollArea_ = new QScrollArea(contentSplitter_);
    leftScrollArea_->setWidgetResizable(true);
    leftScrollArea_->setFrameShape(QFrame::NoFrame);
    leftScrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    leftScrollArea_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    leftScrollArea_->setMinimumWidth(340);
    leftScrollArea_->setMaximumWidth(460);
    leftScrollArea_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    auto *leftContainer = new QWidget(leftScrollArea_);
    auto *leftLayout = new QVBoxLayout(leftContainer);
    leftLayout->setContentsMargins(0, 0, 4, 0);
    leftLayout->setSpacing(12);
    leftLayout->setSizeConstraint(QLayout::SetMinAndMaxSize);

    auto *promptCard = createCard(QStringLiteral("PromptCard"));
    auto *promptLayout = new QVBoxLayout(promptCard);
    promptLayout->setContentsMargins(16, 16, 16, 16);
    promptLayout->setSpacing(10);

    presetCombo_ = new ClickOnlyComboBox(promptCard);
    presetCombo_->setEditable(false);
    presetCombo_->addItem(QStringLiteral("Balanced"), QStringLiteral("Balanced"));
    presetCombo_->addItem(QStringLiteral("Portrait Detail"), QStringLiteral("Portrait Detail"));
    presetCombo_->addItem(QStringLiteral("Stylized Concept"), QStringLiteral("Stylized Concept"));
    presetCombo_->addItem(QStringLiteral("Upscale / Repair"), QStringLiteral("Upscale / Repair"));
    presetCombo_->addItem(QStringLiteral("Custom"), QStringLiteral("Custom"));
    configureComboBox(presetCombo_);

    auto *presetRow = new QHBoxLayout;
    presetRow->setContentsMargins(0, 0, 0, 0);
    presetRow->setSpacing(8);
    presetRow->addWidget(createSectionTitle(QStringLiteral("Preset"), promptCard));
    presetRow->addStretch(1);
    auto *applyPresetButton = new QPushButton(QStringLiteral("Apply Preset"), promptCard);
    applyPresetButton->setObjectName(QStringLiteral("SecondaryActionButton"));
    applyPresetButton->setMinimumWidth(120);
    connect(applyPresetButton, &QPushButton::clicked, this, [this]() { applyPreset(presetCombo_->currentText()); });
    presetRow->addWidget(applyPresetButton);

    promptEdit_ = new QTextEdit(promptCard);
    promptEdit_->setPlaceholderText(QStringLiteral("Describe the subject, framing, lighting, materials, style cues, and production notes here…"));
    promptEdit_->setMinimumHeight(isVideoMode() ? 150 : 180);

    negativePromptEdit_ = new QTextEdit(promptCard);
    negativePromptEdit_->setPlaceholderText(QStringLiteral("Low quality, blurry, extra fingers, watermark, text, duplicate limbs…"));
    negativePromptEdit_->setMinimumHeight(104);

    promptLayout->addLayout(presetRow);
    promptLayout->addWidget(presetCombo_);
    promptLayout->addWidget(createSectionTitle(QStringLiteral("Prompt"), promptCard));
    promptLayout->addWidget(promptEdit_);
    promptLayout->addWidget(createSectionTitle(QStringLiteral("Negative Prompt"), promptCard));
    promptLayout->addWidget(negativePromptEdit_);
    leftLayout->addWidget(promptCard);

    inputCard_ = createCard(QStringLiteral("InputCard"));
    auto *inputLayout = new QVBoxLayout(inputCard_);
    inputLayout->setContentsMargins(16, 16, 16, 16);
    inputLayout->setSpacing(10);
    inputLayout->addWidget(createSectionTitle(isVideoMode() ? QStringLiteral("Input Keyframe") : QStringLiteral("Input Image"), inputCard_));

    auto *dropFrame = new DropTargetFrame(inputCard_);
    dropFrame->setObjectName(QStringLiteral("InputDropCard"));
    auto *dropLayout = new QVBoxLayout(dropFrame);
    dropLayout->setContentsMargins(14, 14, 14, 14);
    dropLayout->setSpacing(8);

    inputDropLabel_ = new QLabel(
        isVideoMode() ? QStringLiteral("Drop a still image or keyframe here, or click Browse to select one.")
                      : QStringLiteral("Drop an image here or click Browse to select a source image."),
        dropFrame);
    inputDropLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    inputDropLabel_->setWordWrap(true);
    dropLayout->addWidget(inputDropLabel_);

    inputImageEdit_ = new QLineEdit(inputCard_);
    inputImageEdit_->setPlaceholderText(isVideoMode() ? QStringLiteral("No keyframe selected") : QStringLiteral("No input image selected"));

    auto *inputButtons = new QHBoxLayout;
    inputButtons->setContentsMargins(0, 0, 0, 0);
    inputButtons->setSpacing(8);
    auto *browseButton = new QPushButton(QStringLiteral("Browse"), inputCard_);
    browseButton->setObjectName(QStringLiteral("SecondaryActionButton"));
    auto *clearInputButton = new QPushButton(QStringLiteral("Clear"), inputCard_);
    clearInputButton->setObjectName(QStringLiteral("TertiaryActionButton"));
    connect(browseButton, &QPushButton::clicked, this, [this]() {
        const QString filePath = QFileDialog::getOpenFileName(this,
                                                              QStringLiteral("Choose input image"),
                                                              QString(),
                                                              QStringLiteral("Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"));
        if (!filePath.isEmpty())
            setInputImagePath(filePath);
    });
    connect(clearInputButton, &QPushButton::clicked, this, [this]() { setInputImagePath(QString()); });
    inputButtons->addWidget(browseButton);
    inputButtons->addWidget(clearInputButton);
    inputButtons->addStretch(1);

    dropFrame->onFileDropped = [this](const QString &path) { setInputImagePath(path); };

    inputLayout->addWidget(dropFrame);
    inputLayout->addWidget(inputImageEdit_);
    inputLayout->addLayout(inputButtons);

    inputCard_->setVisible(isImageInputMode());
    leftLayout->addWidget(inputCard_);

    leftScrollArea_->setWidget(leftContainer);

    centerContainer_ = new QWidget(contentSplitter_);
    auto *centerLayout = new QVBoxLayout(centerContainer_);
    centerLayout->setContentsMargins(0, 0, 0, 0);
    centerLayout->setSpacing(0);

    auto *canvasCard = createCard(QStringLiteral("CanvasCard"));
    auto *canvasLayout = new QVBoxLayout(canvasCard);
    canvasLayout->setContentsMargins(16, 14, 16, 14);
    canvasLayout->setSpacing(8);

    previewLabel_ = new QLabel(canvasCard);
    previewLabel_->setObjectName(QStringLiteral("PreviewSurface"));
    previewLabel_->setAlignment(Qt::AlignCenter);
    previewLabel_->setMinimumSize(0, 0);
    previewLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    previewLabel_->setWordWrap(true);

    generateButton_ = new QPushButton(QStringLiteral("Generate"), canvasCard);
    generateButton_->setObjectName(QStringLiteral("PrimaryActionButton"));
    queueButton_ = new QPushButton(QStringLiteral("Queue"), canvasCard);
    queueButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    prepLatestForI2IButton_ = new QPushButton(QStringLiteral("Prep for I2I"), canvasCard);
    prepLatestForI2IButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    useLatestT2IButton_ = new QPushButton(QStringLiteral("Use Last Image"), canvasCard);
    useLatestT2IButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    savePresetButton_ = new QPushButton(QStringLiteral("Save Snapshot"), canvasCard);
    savePresetButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    clearButton_ = new QPushButton(QStringLiteral("Reset"), canvasCard);
    clearButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    toggleControlsButton_ = new QPushButton(QStringLiteral("Hide Controls"), canvasCard);
    toggleControlsButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    toggleControlsButton_->setVisible(false);

    connect(generateButton_, &QPushButton::clicked, this, [this]() { emit generateRequested(buildRequestPayload()); });
    connect(queueButton_, &QPushButton::clicked, this, [this]() { emit queueRequested(buildRequestPayload()); });
    connect(savePresetButton_, &QPushButton::clicked, this, [this]() { saveSnapshot(); });
    connect(clearButton_, &QPushButton::clicked, this, [this]() { clearForm(); });
    connect(toggleControlsButton_, &QPushButton::clicked, this, [this]() {
        rightControlsVisible_ = !rightControlsVisible_;
        updateAdaptiveLayout();
    });
    connect(prepLatestForI2IButton_, &QPushButton::clicked, this, &ImageGenerationPage::prepLatestForI2I);
    connect(useLatestT2IButton_, &QPushButton::clicked, this, &ImageGenerationPage::useLatestForI2I);

    auto *actionRow = new QHBoxLayout;
    actionRow->setContentsMargins(0, 0, 0, 0);
    actionRow->setSpacing(8);
    actionRow->addWidget(generateButton_);
    actionRow->addWidget(queueButton_);
    actionRow->addWidget(toggleControlsButton_);
    actionRow->addStretch(1);
    actionRow->addWidget(prepLatestForI2IButton_);
    actionRow->addWidget(useLatestT2IButton_);
    actionRow->addWidget(savePresetButton_);
    actionRow->addWidget(clearButton_);

    canvasLayout->addWidget(previewLabel_, 1);
    canvasLayout->addLayout(actionRow, 0);
    centerLayout->addWidget(canvasCard, 1);

    rightScrollArea_ = new QScrollArea(contentSplitter_);
    rightScrollArea_->setWidgetResizable(true);
    rightScrollArea_->setFrameShape(QFrame::NoFrame);
    rightScrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    rightScrollArea_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    rightScrollArea_->setMinimumWidth(340);
    rightScrollArea_->setMaximumWidth(460);
    rightScrollArea_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    auto *rightContainer = new QWidget(rightScrollArea_);
    auto *rightLayout = new QVBoxLayout(rightContainer);
    rightLayout->setContentsMargins(4, 0, 0, 0);
    rightLayout->setSpacing(12);

    stackCard_ = createCard(QStringLiteral("SettingsCard"));
    auto *stackCardLayout = new QVBoxLayout(stackCard_);
    stackCardLayout->setContentsMargins(16, 16, 16, 16);
    stackCardLayout->setSpacing(8);

    modelCombo_ = new ClickOnlyComboBox(stackCard_);
    modelCombo_->setEditable(true);
    modelCombo_->setInsertPolicy(QComboBox::NoInsert);
    modelCombo_->setPlaceholderText(QStringLiteral("Checkpoint path or repo id"));
    configureComboBox(modelCombo_);

    workflowCombo_ = new ClickOnlyComboBox(stackCard_);
    workflowCombo_->setEditable(false);
    workflowCombo_->addItem(QStringLiteral("Default Canvas"), QStringLiteral("Default Canvas"));
    workflowCombo_->addItem(QStringLiteral("Portrait Detail"), QStringLiteral("Portrait Detail"));
    workflowCombo_->addItem(QStringLiteral("Stylized Concept"), QStringLiteral("Stylized Concept"));
    workflowCombo_->addItem(QStringLiteral("Upscale / Repair"), QStringLiteral("Upscale / Repair"));
    configureComboBox(workflowCombo_);

    loraCombo_ = new ClickOnlyComboBox(stackCard_);
    loraCombo_->setEditable(true);
    loraCombo_->setInsertPolicy(QComboBox::NoInsert);
    loraCombo_->setPlaceholderText(QStringLiteral("Optional LoRA from loras/ or full file path"));
    configureComboBox(loraCombo_);

    loraWeightSpin_ = new QDoubleSpinBox(stackCard_);
    loraWeightSpin_->setDecimals(2);
    loraWeightSpin_->setSingleStep(0.05);
    loraWeightSpin_->setRange(0.0, 2.0);
    loraWeightSpin_->setValue(1.0);
    configureDoubleSpinBox(loraWeightSpin_);

    auto *stackForm = new QGridLayout;
    stackForm->setHorizontalSpacing(10);
    stackForm->setVerticalSpacing(8);
    stackForm->setColumnStretch(1, 1);

    int stackRow = 0;
    stackForm->addWidget(new QLabel(QStringLiteral("Model"), stackCard_), stackRow, 0);
    stackForm->addWidget(modelCombo_, stackRow, 1);
    ++stackRow;
    stackForm->addWidget(new QLabel(QStringLiteral("Workflow"), stackCard_), stackRow, 0);
    stackForm->addWidget(workflowCombo_, stackRow, 1);
    ++stackRow;
    stackForm->addWidget(new QLabel(QStringLiteral("LoRA"), stackCard_), stackRow, 0);
    stackForm->addWidget(loraCombo_, stackRow, 1);
    ++stackRow;
    stackForm->addWidget(new QLabel(QStringLiteral("LoRA Weight"), stackCard_), stackRow, 0);
    stackForm->addWidget(loraWeightSpin_, stackRow, 1);

    stackToolsLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    stackToolsLayout_->setContentsMargins(0, 0, 0, 0);
    stackToolsLayout_->setSpacing(8);
    openModelsButton_ = new QPushButton(QStringLiteral("Open Models"), stackCard_);
    openModelsButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    openModelsButton_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    openWorkflowsButton_ = new QPushButton(QStringLiteral("Open Workflows"), stackCard_);
    openWorkflowsButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    openWorkflowsButton_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    connect(openModelsButton_, &QPushButton::clicked, this, &ImageGenerationPage::openModelsRequested);
    connect(openWorkflowsButton_, &QPushButton::clicked, this, &ImageGenerationPage::openWorkflowsRequested);
    stackToolsLayout_->addWidget(openModelsButton_);
    stackToolsLayout_->addWidget(openWorkflowsButton_);

    stackCardLayout->addWidget(createSectionTitle(QStringLiteral("Model Stack"), stackCard_));
    stackCardLayout->addLayout(stackForm);
    stackCardLayout->addLayout(stackToolsLayout_);
    rightLayout->addWidget(stackCard_);

    settingsCard_ = createCard(QStringLiteral("OutputCard"));
    auto *settingsCardLayout = new QVBoxLayout(settingsCard_);
    settingsCardLayout->setContentsMargins(16, 16, 16, 16);
    settingsCardLayout->setSpacing(10);

    samplerCombo_ = new ClickOnlyComboBox(settingsCard_);
    samplerCombo_->addItem(QStringLiteral("euler"), QStringLiteral("euler"));
    samplerCombo_->addItem(QStringLiteral("euler_ancestral"), QStringLiteral("euler_ancestral"));
    samplerCombo_->addItem(QStringLiteral("heun"), QStringLiteral("heun"));
    samplerCombo_->addItem(QStringLiteral("dpmpp_2m"), QStringLiteral("dpmpp_2m"));
    samplerCombo_->addItem(QStringLiteral("dpmpp_sde"), QStringLiteral("dpmpp_sde"));
    samplerCombo_->addItem(QStringLiteral("uni_pc"), QStringLiteral("uni_pc"));
    configureComboBox(samplerCombo_);

    schedulerCombo_ = new ClickOnlyComboBox(settingsCard_);
    schedulerCombo_->addItem(QStringLiteral("normal"), QStringLiteral("normal"));
    schedulerCombo_->addItem(QStringLiteral("karras"), QStringLiteral("karras"));
    schedulerCombo_->addItem(QStringLiteral("sgm_uniform"), QStringLiteral("sgm_uniform"));
    configureComboBox(schedulerCombo_);

    stepsSpin_ = new QSpinBox(settingsCard_);
    stepsSpin_->setRange(1, 200);
    stepsSpin_->setValue(28);
    configureSpinBox(stepsSpin_);

    cfgSpin_ = new QDoubleSpinBox(settingsCard_);
    cfgSpin_->setDecimals(1);
    cfgSpin_->setSingleStep(0.5);
    cfgSpin_->setRange(1.0, 30.0);
    cfgSpin_->setValue(7.0);
    configureDoubleSpinBox(cfgSpin_);

    seedSpin_ = new QSpinBox(settingsCard_);
    seedSpin_->setRange(0, 999999999);
    seedSpin_->setSpecialValueText(QStringLiteral("Random"));
    seedSpin_->setValue(0);
    configureSpinBox(seedSpin_);

    widthSpin_ = new QSpinBox(settingsCard_);
    widthSpin_->setRange(64, 8192);
    widthSpin_->setSingleStep(64);
    widthSpin_->setValue(1024);
    configureSpinBox(widthSpin_);

    heightSpin_ = new QSpinBox(settingsCard_);
    heightSpin_->setRange(64, 8192);
    heightSpin_->setSingleStep(64);
    heightSpin_->setValue(1024);
    configureSpinBox(heightSpin_);

    batchSpin_ = new QSpinBox(settingsCard_);
    batchSpin_->setRange(1, 32);
    batchSpin_->setValue(1);
    configureSpinBox(batchSpin_);

    denoiseSpin_ = new QDoubleSpinBox(settingsCard_);
    denoiseSpin_->setDecimals(2);
    denoiseSpin_->setSingleStep(0.05);
    denoiseSpin_->setRange(0.0, 1.0);
    denoiseSpin_->setValue(0.45);
    configureDoubleSpinBox(denoiseSpin_);

    auto makeSettingsRow = [this](QWidget *parent, const QString &labelText, QWidget *field) -> QWidget * {
        auto *rowWidget = new QWidget(parent);
        auto *rowLayout = new QHBoxLayout(rowWidget);
        rowLayout->setContentsMargins(0, 0, 0, 0);
        rowLayout->setSpacing(10);

        auto *label = new QLabel(labelText, rowWidget);
        label->setMinimumWidth(92);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);

        field->setParent(rowWidget);
        field->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        rowLayout->addWidget(label);
        rowLayout->addWidget(field, 1);
        return rowWidget;
    };

    QWidget *samplerRow = makeSettingsRow(settingsCard_, QStringLiteral("Sampler"), samplerCombo_);
    QWidget *schedulerRow = makeSettingsRow(settingsCard_, QStringLiteral("Scheduler"), schedulerCombo_);
    QWidget *stepsRow = makeSettingsRow(settingsCard_, QStringLiteral("Steps"), stepsSpin_);
    QWidget *cfgRow = makeSettingsRow(settingsCard_, QStringLiteral("CFG"), cfgSpin_);
    QWidget *seedRow = makeSettingsRow(settingsCard_, QStringLiteral("Seed"), seedSpin_);
    QWidget *batchRow = makeSettingsRow(settingsCard_, QStringLiteral("Batch"), batchSpin_);
    QWidget *widthRow = makeSettingsRow(settingsCard_, QStringLiteral("Width"), widthSpin_);
    QWidget *heightRow = makeSettingsRow(settingsCard_, QStringLiteral("Height"), heightSpin_);

    denoiseRow_ = makeSettingsRow(settingsCard_, QStringLiteral("Denoise Strength"), denoiseSpin_);
    denoiseRow_->setVisible(usesStrengthControl());

    samplerSchedulerLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    samplerSchedulerLayout_->setContentsMargins(0, 0, 0, 0);
    samplerSchedulerLayout_->setSpacing(8);
    samplerSchedulerLayout_->addWidget(samplerRow);
    samplerSchedulerLayout_->addWidget(schedulerRow);

    stepsCfgLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    stepsCfgLayout_->setContentsMargins(0, 0, 0, 0);
    stepsCfgLayout_->setSpacing(8);
    stepsCfgLayout_->addWidget(stepsRow);
    stepsCfgLayout_->addWidget(cfgRow);

    seedBatchLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    seedBatchLayout_->setContentsMargins(0, 0, 0, 0);
    seedBatchLayout_->setSpacing(8);
    seedBatchLayout_->addWidget(seedRow);
    seedBatchLayout_->addWidget(batchRow);

    sizeLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    sizeLayout_->setContentsMargins(0, 0, 0, 0);
    sizeLayout_->setSpacing(8);
    sizeLayout_->addWidget(widthRow);
    sizeLayout_->addWidget(heightRow);

    outputPrefixEdit_ = new QLineEdit(settingsCard_);
    outputPrefixEdit_->setPlaceholderText(QStringLiteral("spellvision_render"));

    outputFolderLabel_ = new QLabel(QDir::toNativeSeparators(chooseComfyOutputPath()), settingsCard_);
    outputFolderLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    outputFolderLabel_->setWordWrap(true);

    modelsRootLabel_ = new QLabel(settingsCard_);
    modelsRootLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    modelsRootLabel_->setWordWrap(true);

    settingsCardLayout->addWidget(createSectionTitle(isVideoMode() ? QStringLiteral("Frames / Motion") : QStringLiteral("Generation Settings"), settingsCard_));
    settingsCardLayout->addLayout(samplerSchedulerLayout_);
    settingsCardLayout->addLayout(stepsCfgLayout_);
    settingsCardLayout->addLayout(seedBatchLayout_);
    settingsCardLayout->addLayout(sizeLayout_);
    settingsCardLayout->addWidget(denoiseRow_);
    settingsCardLayout->addWidget(new QLabel(QStringLiteral("Filename Prefix"), settingsCard_));
    settingsCardLayout->addWidget(outputPrefixEdit_);
    settingsCardLayout->addWidget(new QLabel(QStringLiteral("Output Folder"), settingsCard_));
    settingsCardLayout->addWidget(outputFolderLabel_);
    settingsCardLayout->addWidget(modelsRootLabel_);
    rightLayout->addWidget(settingsCard_);
    rightLayout->addStretch(1);

    rightScrollArea_->setWidget(rightContainer);

    contentSplitter_->addWidget(leftScrollArea_);
    contentSplitter_->addWidget(centerContainer_);
    contentSplitter_->addWidget(rightScrollArea_);
    contentSplitter_->setStretchFactor(0, 0);
    contentSplitter_->setStretchFactor(1, 1);
    contentSplitter_->setStretchFactor(2, 0);
    contentSplitter_->setSizes({380, 1020, 420});

    root->addWidget(contentSplitter_, 1);

    if (prepLatestForI2IButton_)
        prepLatestForI2IButton_->setVisible(mode_ == Mode::TextToImage);
    if (useLatestT2IButton_)
        useLatestT2IButton_->setVisible(mode_ == Mode::ImageToImage);

    const auto refreshers = [this]() { scheduleUiRefresh(); };

    connect(promptEdit_, &QTextEdit::textChanged, this, refreshers);
    connect(negativePromptEdit_, &QTextEdit::textChanged, this, refreshers);
    connect(modelCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(workflowCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(loraCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(loraWeightSpin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    connect(samplerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(schedulerCombo_, &QComboBox::currentTextChanged, this, refreshers);
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

    setWorkspaceTelemetry(QStringLiteral("Runtime: Managed ComfyUI"),
                          QStringLiteral("Queue: 0 running | 0 pending"),
                          QStringLiteral("Model: none"),
                          QStringLiteral("LoRA: none"),
                          0,
                          QStringLiteral("Idle"));

    updateAdaptiveLayout();
}

void ImageGenerationPage::reloadCatalogs()
{
    modelsRootDir_ = chooseModelsRootPath();

    if (modelsRootLabel_)
    {
        const QString rootText = QDir::toNativeSeparators(modelsRootDir_);
        modelsRootLabel_->setText(QStringLiteral("Assets: %1\nDropdowns show compact names; full paths stay available in tooltips.").arg(rootText));
    }

    populateComboFromCatalog(modelCombo_, scanCatalog(modelsRootDir_, QStringLiteral("checkpoints")), {QStringLiteral("sdxl")});

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
        if (loraCombo_)
            loraCombo_->setCurrentText(QString());
        if (loraWeightSpin_)
            loraWeightSpin_->setValue(1.0);
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
        if (loraCombo_)
            loraCombo_->setCurrentText(QString());
        if (loraWeightSpin_)
            loraWeightSpin_->setValue(1.0);
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
        if (loraCombo_)
            loraCombo_->setCurrentText(QString());
        if (loraWeightSpin_)
            loraWeightSpin_->setValue(1.0);
        if (!selectComboValue(samplerCombo_, QStringLiteral("uni_pc")))
            selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
        selectComboValue(schedulerCombo_, QStringLiteral("normal"));
        stepsSpin_->setValue(24);
        cfgSpin_->setValue(5.5);
        if (denoiseSpin_)
            denoiseSpin_->setValue(0.35);
    }
    else
    {
        promptEdit_->setPlainText(QStringLiteral("high quality image, clean composition, strong subject read, balanced lighting"));
        negativePromptEdit_->setPlainText(QStringLiteral("low quality, blurry, text, watermark"));
        if (modelCombo_ && modelCombo_->count() > 0)
            modelCombo_->setCurrentIndex(0);
        selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));
        if (loraCombo_)
            loraCombo_->setCurrentText(QString());
        if (loraWeightSpin_)
            loraWeightSpin_->setValue(1.0);
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
        stepsSpin_->setValue(28);
        cfgSpin_->setValue(7.0);
        widthSpin_->setValue(1024);
        heightSpin_->setValue(1024);
        if (denoiseSpin_)
            denoiseSpin_->setValue(0.45);
    }

    schedulePreviewRefresh(0);
}

void ImageGenerationPage::scheduleUiRefresh(int delayMs)
{
    if (!uiRefreshTimer_)
    {
        refreshPreview();
        return;
    }

    uiRefreshTimer_->start(qBound(0, delayMs, 250));
}

void ImageGenerationPage::schedulePreviewRefresh(int delayMs)
{
    if (!previewResizeTimer_)
    {
        refreshPreview();
        return;
    }

    previewResizeTimer_->start(qBound(0, delayMs, 250));
}

bool ImageGenerationPage::loadPreviewPixmapIfNeeded(const QString &path, bool forceReload)
{
    const QString normalizedPath = path.trimmed();
    if (normalizedPath.isEmpty())
        return false;

    const QFileInfo info(normalizedPath);
    if (!info.exists() || !info.isFile())
        return false;

    const qint64 modifiedMs = info.lastModified().toMSecsSinceEpoch();
    const qint64 fileSize = info.size();
    const bool sameSource = cachedPreviewSourcePath_ == normalizedPath;
    const bool fileUnchanged = sameSource &&
                               cachedPreviewLastModifiedMs_ == modifiedMs &&
                               cachedPreviewFileSize_ == fileSize;

    if (!forceReload && fileUnchanged && !cachedPreviewPixmap_.isNull())
        return true;

    QPixmap pixmap;
    if (!pixmap.load(normalizedPath))
        return false;

    cachedPreviewSourcePath_ = normalizedPath;
    cachedPreviewPixmap_ = pixmap;
    cachedPreviewLastModifiedMs_ = modifiedMs;
    cachedPreviewFileSize_ = fileSize;
    return true;
}

QString ImageGenerationPage::buildRenderedPreviewFingerprint(const QString &sourcePath,
                                                            const QString &summaryText,
                                                            const QSize &targetSize) const
{
    return QStringLiteral("%1|%2|%3x%4|%5|%6")
        .arg(sourcePath)
        .arg(summaryText)
        .arg(targetSize.width())
        .arg(targetSize.height())
        .arg(cachedPreviewLastModifiedMs_)
        .arg(cachedPreviewFileSize_);
}

void ImageGenerationPage::refreshPreview()
{
    if (!previewLabel_)
        return;

    auto showPixmap = [this](const QString &sourcePath, const QPixmap &pixmap, const QString &summaryText) {
        if (pixmap.isNull())
            return;

        QSize target = previewLabel_->contentsRect().size();
        if (target.width() < 64 || target.height() < 64)
            target = QSize(640, 480);

        const QString fingerprint = buildRenderedPreviewFingerprint(sourcePath, summaryText, target);
        if (lastRenderedPreviewFingerprint_ == fingerprint)
            return;

        lastRenderedPreviewFingerprint_ = fingerprint;
        lastPreviewTargetSize_ = target;

        previewLabel_->setText(QString());
        previewLabel_->setPixmap(pixmap.scaled(target, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    };

    if (!generatedPreviewPath_.trimmed().isEmpty() && QFileInfo::exists(generatedPreviewPath_))
    {
        if (cachedPreviewSourcePath_ != generatedPreviewPath_)
        {
            QPixmap pixmap;
            if (pixmap.load(generatedPreviewPath_))
            {
                cachedPreviewSourcePath_ = generatedPreviewPath_;
                cachedPreviewPixmap_ = pixmap;
            }
            else
            {
                previewLabel_->setPixmap(QPixmap());
                previewLabel_->setText(QStringLiteral("Loading latest output preview…"));
                schedulePreviewRefresh(120);
                return;
            }
        }

        if (!cachedPreviewPixmap_.isNull())
        {
            const QString summary = !generatedPreviewCaption_.trimmed().isEmpty()
                                        ? generatedPreviewCaption_.trimmed()
                                        : QStringLiteral("Latest result: %1\n%2 × %3")
                                              .arg(QFileInfo(generatedPreviewPath_).fileName())
                                              .arg(cachedPreviewPixmap_.width())
                                              .arg(cachedPreviewPixmap_.height());

            showPixmap(generatedPreviewPath_, cachedPreviewPixmap_, summary);
            return;
        }
    }

    if (isImageInputMode())
    {
        const QString path = inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString();
        if (!path.isEmpty() && QFileInfo::exists(path))
        {
            QPixmap pixmap;
            if (cachedPreviewSourcePath_ == path && !cachedPreviewPixmap_.isNull())
                pixmap = cachedPreviewPixmap_;
            else if (pixmap.load(path))
            {
                cachedPreviewSourcePath_ = path;
                cachedPreviewPixmap_ = pixmap;
            }

            if (!pixmap.isNull())
            {
                showPixmap(path,
                           pixmap,
                           QStringLiteral("%1: %2\nStrength: %3    Sampler: %4    Steps: %5")
                               .arg(isVideoMode() ? QStringLiteral("Keyframe") : QStringLiteral("Source image"))
                               .arg(QFileInfo(path).fileName())
                               .arg(denoiseSpin_ ? QString::number(denoiseSpin_->value(), 'f', 2) : QStringLiteral("n/a"))
                               .arg(comboDisplayValue(samplerCombo_))
                               .arg(stepsSpin_ ? stepsSpin_->value() : 0));
                return;
            }
        }
    }

    previewLabel_->setPixmap(QPixmap());
    lastPreviewTargetSize_ = QSize();
    lastRenderedPreviewFingerprint_.clear();

    if (generatedPreviewPath_.trimmed().isEmpty())
    {
        cachedPreviewSourcePath_.clear();
        cachedPreviewPixmap_ = QPixmap();
        cachedPreviewLastModifiedMs_ = -1;
        cachedPreviewFileSize_ = -1;
    }

    previewLabel_->setText(
        busy_ ? (busyMessage_.isEmpty() ? QStringLiteral("Generation in progress…") : busyMessage_)
              : (isImageInputMode()
                     ? QStringLiteral("No source image loaded yet.\n\nDrop an image into the Input Image card or browse for one to begin.")
                     : (isVideoMode()
                            ? QStringLiteral("Ready to create motion.\n\nBuild the prompt and motion stack on the left, then press Generate or Queue.")
                            : QStringLiteral("Your generated image will appear here.\n\nBuild the prompt and stack on the left, then generate."))));
}

void ImageGenerationPage::setInputImagePath(const QString &path)
{
    if (!inputImageEdit_ || !inputDropLabel_)
        return;

    generatedPreviewPath_.clear();
    generatedPreviewCaption_.clear();
    cachedPreviewSourcePath_.clear();
    cachedPreviewPixmap_ = QPixmap();
    cachedPreviewLastModifiedMs_ = -1;
    cachedPreviewFileSize_ = -1;
    lastRenderedPreviewFingerprint_.clear();

    inputImageEdit_->setText(path);
    inputDropLabel_->setText(path.isEmpty() ? QStringLiteral("Drop an image here or click Browse to select a source image.")
                                            : QStringLiteral("Current source image:\n%1").arg(path));
    schedulePreviewRefresh(0);
}

void ImageGenerationPage::setPreviewImage(const QString &imagePath, const QString &caption)
{
    const QString normalizedPath = imagePath.trimmed();

    generatedPreviewPath_.clear();
    generatedPreviewCaption_.clear();
    cachedPreviewSourcePath_.clear();
    cachedPreviewPixmap_ = QPixmap();
    cachedPreviewLastModifiedMs_ = -1;
    cachedPreviewFileSize_ = -1;
    lastRenderedPreviewFingerprint_.clear();

    if (normalizedPath.isEmpty())
    {
        busy_ = false;
        busyMessage_.clear();
        schedulePreviewRefresh(0);
        return;
    }

    generatedPreviewPath_ = normalizedPath;
    generatedPreviewCaption_ = caption.trimmed();
    busy_ = false;
    busyMessage_.clear();

    persistLatestGeneratedOutput(normalizedPath);
    schedulePreviewRefresh(0);
}

void ImageGenerationPage::setBusy(bool busy, const QString &message)
{
    busy_ = busy;
    busyMessage_ = message.trimmed();

    if (busy)
    {
        generatedPreviewPath_.clear();
        generatedPreviewCaption_.clear();
        cachedPreviewSourcePath_.clear();
        cachedPreviewPixmap_ = QPixmap();
    }

    if (generateButton_)
        generateButton_->setEnabled(!busy);
    if (queueButton_)
        queueButton_->setEnabled(!busy);
    if (savePresetButton_)
        savePresetButton_->setEnabled(!busy);
    if (clearButton_)
        clearButton_->setEnabled(!busy);

    schedulePreviewRefresh(busy ? 0 : 30);
}



int ImageGenerationPage::measuredContentWidth() const
{
    if (contentSplitter_)
        return contentSplitter_->contentsRect().width();

    return contentsRect().width();
}

int ImageGenerationPage::measuredRightRailWidth() const
{
    if (!rightScrollArea_)
        return 0;

    if (QWidget *viewport = rightScrollArea_->viewport())
        return std::max(0, viewport->contentsRect().width());

    return std::max(0, rightScrollArea_->contentsRect().width());
}

bool ImageGenerationPage::isCompactLayout() const
{
    return measuredContentWidth() < 1340;
}

bool ImageGenerationPage::isMediumLayout() const
{
    const int contentWidth = measuredContentWidth();
    return contentWidth >= 1340 && contentWidth < 1680;
}

ImageGenerationPage::AdaptiveLayoutMode ImageGenerationPage::currentAdaptiveLayoutMode() const
{
    if (isCompactLayout())
        return AdaptiveLayoutMode::Compact;
    if (isMediumLayout())
        return AdaptiveLayoutMode::Medium;
    return AdaptiveLayoutMode::Wide;
}

void ImageGenerationPage::setRightControlsVisible(bool visible)
{
    if (!rightScrollArea_)
        return;

    rightScrollArea_->setVisible(visible);
}

void ImageGenerationPage::applyRightPanelReflow(AdaptiveLayoutMode mode)
{
    const int railWidth = measuredRightRailWidth();
    const bool compactRail = (mode == AdaptiveLayoutMode::Compact) || railWidth < 360;
    const bool verticalActions = compactRail || railWidth < 410;

    if (stackToolsLayout_)
    {
        stackToolsLayout_->setDirection(verticalActions ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
        stackToolsLayout_->setSpacing(verticalActions ? 8 : 10);
    }

    auto applyPairDirection = [compactRail](QBoxLayout *layout) {
        if (!layout)
            return;
        layout->setDirection(compactRail ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
        layout->setSpacing(compactRail ? 8 : 10);
    };

    applyPairDirection(samplerSchedulerLayout_);
    applyPairDirection(stepsCfgLayout_);
    applyPairDirection(seedBatchLayout_);
    applyPairDirection(sizeLayout_);

    const int buttonHeight = verticalActions ? 42 : 40;
    if (openModelsButton_)
    {
        openModelsButton_->setMinimumHeight(buttonHeight);
        openModelsButton_->setMinimumWidth(0);
    }
    if (openWorkflowsButton_)
    {
        openWorkflowsButton_->setMinimumHeight(buttonHeight);
        openWorkflowsButton_->setMinimumWidth(0);
    }
}

void ImageGenerationPage::applyAdaptiveSplitterSizes(AdaptiveLayoutMode mode)
{
    if (!contentSplitter_)
        return;

    if (mode == AdaptiveLayoutMode::Compact)
    {
        if (rightScrollArea_ && rightScrollArea_->isVisible())
            contentSplitter_->setSizes({280, 820, 400});
        else
            contentSplitter_->setSizes({290, 1140, 0});
        return;
    }

    if (mode == AdaptiveLayoutMode::Medium)
    {
        contentSplitter_->setSizes({285, 900, 400});
        return;
    }

    contentSplitter_->setSizes({285, 1020, 390});
}

void ImageGenerationPage::updateAdaptiveLayout()
{
    const AdaptiveLayoutMode mode = currentAdaptiveLayoutMode();
    adaptiveCompact_ = mode == AdaptiveLayoutMode::Compact;

    if (mode != lastAdaptiveLayoutMode_)
    {
        if (mode == AdaptiveLayoutMode::Compact)
            rightControlsVisible_ = false;
        else if (lastAdaptiveLayoutMode_ == AdaptiveLayoutMode::Compact)
            rightControlsVisible_ = true;

        lastAdaptiveLayoutMode_ = mode;
    }

    if (leftScrollArea_)
    {
        if (mode == AdaptiveLayoutMode::Compact)
        {
            leftScrollArea_->setMinimumWidth(260);
            leftScrollArea_->setMaximumWidth(320);
        }
        else if (mode == AdaptiveLayoutMode::Medium)
        {
            leftScrollArea_->setMinimumWidth(270);
            leftScrollArea_->setMaximumWidth(330);
        }
        else
        {
            leftScrollArea_->setMinimumWidth(270);
            leftScrollArea_->setMaximumWidth(340);
        }
    }

    const bool showRightControls = (mode != AdaptiveLayoutMode::Compact) || rightControlsVisible_;
    setRightControlsVisible(showRightControls);

    if (rightScrollArea_)
    {
        if (mode == AdaptiveLayoutMode::Compact)
        {
            rightScrollArea_->setMinimumWidth(360);
            rightScrollArea_->setMaximumWidth(430);
        }
        else if (mode == AdaptiveLayoutMode::Medium)
        {
            rightScrollArea_->setMinimumWidth(370);
            rightScrollArea_->setMaximumWidth(440);
        }
        else
        {
            rightScrollArea_->setMinimumWidth(380);
            rightScrollArea_->setMaximumWidth(450);
        }
    }

    applyRightPanelReflow(mode);

    if (toggleControlsButton_)
    {
        toggleControlsButton_->setVisible(mode == AdaptiveLayoutMode::Compact);
        toggleControlsButton_->setText(showRightControls ? QStringLiteral("Hide Controls")
                                                         : QStringLiteral("Show Controls"));
    }

    if (promptEdit_)
    {
        promptEdit_->setMinimumHeight(mode == AdaptiveLayoutMode::Wide ? (isVideoMode() ? 140 : 170)
                                                                      : (isVideoMode() ? 128 : 150));
    }
    if (negativePromptEdit_)
        negativePromptEdit_->setMinimumHeight(mode == AdaptiveLayoutMode::Wide ? 100 : 88);

    applyAdaptiveSplitterSizes(mode);
}

void ImageGenerationPage::setWorkspaceTelemetry(const QString &runtime,
                                                const QString &queue,
                                                const QString &model,
                                                const QString &lora,
                                                int progressPercent,
                                                const QString &progressText)
{
    Q_UNUSED(runtime);
    Q_UNUSED(queue);
    Q_UNUSED(model);
    Q_UNUSED(lora);
    Q_UNUSED(progressPercent);
    Q_UNUSED(progressText);
}

void ImageGenerationPage::applyHomeStarter(const QString &title,
                                           const QString &subtitle,
                                           const QString &sourceLabel)
{
    QStringList lines;
    const QString trimmedTitle = title.trimmed();
    const QString trimmedSubtitle = subtitle.trimmed();
    const QString trimmedSource = sourceLabel.trimmed();

    if (!trimmedTitle.isEmpty())
        lines << trimmedTitle;
    if (!trimmedSubtitle.isEmpty())
        lines << trimmedSubtitle;

    const QString starterText = lines.join(QStringLiteral("\n")).trimmed();
    if (!starterText.isEmpty() && promptEdit_)
        promptEdit_->setPlainText(starterText);

    if (presetCombo_)
        selectComboValue(presetCombo_, QStringLiteral("Balanced"));

    if (workflowCombo_ && trimmedSource.contains(QStringLiteral("workflow"), Qt::CaseInsensitive))
        selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));

    if (inputImageEdit_ && isImageInputMode() && inputImageEdit_->text().trimmed().isEmpty())
        inputDropLabel_->setText(QStringLiteral("Starter selected from Home. Add a source image or keyframe to continue."));

    generatedPreviewCaption_.clear();
    busy_ = false;
    busyMessage_.clear();

    scheduleUiRefresh(0);
    schedulePreviewRefresh(0);
}


void ImageGenerationPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateAdaptiveLayout();
    schedulePreviewRefresh(60);
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
    if (loraWeightSpin_)
        loraWeightSpin_->setValue(1.0);
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

    schedulePreviewRefresh(0);
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
    settings.setValue(QStringLiteral("loraWeight"), loraWeightSpin_ ? loraWeightSpin_->value() : 1.0);
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
    if (loraWeightSpin_)
        loraWeightSpin_->setValue(settings.value(QStringLiteral("loraWeight"), 1.0).toDouble());
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

    const QString lowered = raw.toLower();
    if (lowered == QStringLiteral("(none)") || lowered == QStringLiteral("none") || lowered == QStringLiteral("no lora"))
        return QString();

    const auto it = loraPathByDisplay_.constFind(raw);
    if (it != loraPathByDisplay_.constEnd())
        return it.value();

    return raw;
}

void ImageGenerationPage::persistLatestGeneratedOutput(const QString &path)
{
    if (path.trimmed().isEmpty())
        return;

    QSettings s;
    s.setValue(QStringLiteral("workspace/last_generated_image_path"), path);
}

QString ImageGenerationPage::latestGeneratedOutputPath() const
{
    QSettings s;
    return s.value(QStringLiteral("workspace/last_generated_image_path")).toString();
}

void ImageGenerationPage::prepLatestForI2I()
{
    const QString latest = latestGeneratedOutputPath();
    if (latest.isEmpty())
        return;

    QSettings s;
    s.setValue(QStringLiteral("workspace/staged_i2i_input_path"), latest);
}

void ImageGenerationPage::useLatestForI2I()
{
    QSettings s;
    QString staged = s.value(QStringLiteral("workspace/staged_i2i_input_path")).toString();

    if (staged.isEmpty())
        staged = latestGeneratedOutputPath();

    if (!staged.isEmpty())
        setInputImagePath(staged);
}
