#include "ImageGenerationPage.h"

#include "ThemeManager.h"

#include <QAbstractItemView>
#include <QAbstractSpinBox>
#include <QComboBox>
#include <QListWidget>
#include <QDialogButtonBox>
#include <QDialog>
#include <QCheckBox>
#include <QCompleter>
#include <QDateTime>
#include <QDir>
#include <QDirIterator>
#include <QDoubleSpinBox>
#include <QCheckBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDropEvent>
#include <QFile>
#include <QDragEnterEvent>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonObject>
#include <QJsonDocument>
#include <QJsonArray>
#include <QLabel>
#include <QListWidget>
#include <QLineEdit>
#include <QMimeData>
#include <QMessageBox>
#include <QPixmap>
#include <QRegularExpression>
#include <QPushButton>
#include <QResizeEvent>
#include <QScrollArea>
#include <QScrollBar>
#include <QSettings>
#include <QSet>
#include <QSizePolicy>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QStandardPaths>
#include <QSplitter>
#include <QStyle>
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
    QString modality = QStringLiteral("unknown");
    QString family = QStringLiteral("Unknown");
    QString compatibilityNote = QStringLiteral("Unclassified asset");
    int confidence = 0;
};

struct AssetClassification
{
    QString modality = QStringLiteral("unknown");
    QString family = QStringLiteral("Unknown");
    QString compatibilityNote = QStringLiteral("No compatibility signal detected.");
    int confidence = 0;
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

class CatalogPickerDialog final : public QDialog
{
public:
    CatalogPickerDialog(const QString &title,
                        const QVector<CatalogEntry> &entries,
                        const QString &currentValue,
                        const QString &recentSettingsKey,
                        QWidget *parent = nullptr)
        : QDialog(parent), entries_(entries), recentSettingsKey_(recentSettingsKey)
    {
        setWindowTitle(title);
        resize(860, 620);

        auto *layout = new QVBoxLayout(this);
        layout->setContentsMargins(14, 14, 14, 14);
        layout->setSpacing(10);

        auto *header = new QVBoxLayout;
        header->setContentsMargins(0, 0, 0, 0);
        header->setSpacing(6);

        searchEdit_ = new QLineEdit(this);
        searchEdit_->setPlaceholderText(QStringLiteral("Search by name, folder, file path, or family keyword"));
        header->addWidget(searchEdit_);

        auto *toolbar = new QHBoxLayout;
        toolbar->setContentsMargins(0, 0, 0, 0);
        toolbar->setSpacing(8);

        recentOnlyCheck_ = new QCheckBox(QStringLiteral("Recent only"), this);
        resultsLabel_ = new QLabel(this);
        resultsLabel_->setObjectName(QStringLiteral("ImageGenHint"));
        toolbar->addWidget(recentOnlyCheck_);
        toolbar->addStretch(1);
        toolbar->addWidget(resultsLabel_);
        header->addLayout(toolbar);
        layout->addLayout(header);

        splitter_ = new QSplitter(Qt::Horizontal, this);

        listWidget_ = new QListWidget(splitter_);
        listWidget_->setSelectionMode(QAbstractItemView::SingleSelection);
        listWidget_->setAlternatingRowColors(true);

        auto *detailPane = new QWidget(splitter_);
        auto *detailLayout = new QVBoxLayout(detailPane);
        detailLayout->setContentsMargins(0, 0, 0, 0);
        detailLayout->setSpacing(8);

        detailTitleLabel_ = new QLabel(QStringLiteral("Select an asset"), detailPane);
        detailTitleLabel_->setObjectName(QStringLiteral("SectionTitle"));
        detailMetaLabel_ = new QLabel(QStringLiteral("Search and browse by recognition instead of recalling file names."), detailPane);
        detailMetaLabel_->setObjectName(QStringLiteral("SectionBody"));
        detailMetaLabel_->setWordWrap(true);
        detailPathLabel_ = new QLabel(detailPane);
        detailPathLabel_->setObjectName(QStringLiteral("ImageGenHint"));
        detailPathLabel_->setWordWrap(true);

        detailLayout->addWidget(detailTitleLabel_);
        detailLayout->addWidget(detailMetaLabel_);
        detailLayout->addWidget(detailPathLabel_);
        detailLayout->addStretch(1);

        splitter_->addWidget(listWidget_);
        splitter_->addWidget(detailPane);
        splitter_->setStretchFactor(0, 1);
        splitter_->setStretchFactor(1, 0);
        splitter_->setSizes({520, 260});
        layout->addWidget(splitter_, 1);

        auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
        layout->addWidget(buttons);

        QObject::connect(searchEdit_, &QLineEdit::textChanged, this, [this](const QString &) { rebuild(); });
        QObject::connect(recentOnlyCheck_, &QCheckBox::toggled, this, [this](bool) { rebuild(); });
        QObject::connect(listWidget_, &QListWidget::currentItemChanged, this, [this](QListWidgetItem *current, QListWidgetItem *) { updateDetails(current); });
        QObject::connect(listWidget_, &QListWidget::itemDoubleClicked, this, [this](QListWidgetItem *) { accept(); });
        QObject::connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
        QObject::connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);

        const QStringList rawRecent = QSettings().value(recentSettingsKey_).toStringList();
        for (const QString &value : rawRecent)
        {
            const QString trimmed = value.trimmed();
            if (!trimmed.isEmpty() && !recentValues_.contains(trimmed))
                recentValues_.push_back(trimmed);
        }

        currentValue_ = currentValue.trimmed();
        rebuild();

        if (!currentValue_.isEmpty())
        {
            for (int row = 0; row < listWidget_->count(); ++row)
            {
                QListWidgetItem *item = listWidget_->item(row);
                if (item && item->data(Qt::UserRole).toString().compare(currentValue_, Qt::CaseInsensitive) == 0)
                {
                    listWidget_->setCurrentRow(row);
                    break;
                }
            }
        }

        if (listWidget_->currentRow() < 0 && listWidget_->count() > 0)
            listWidget_->setCurrentRow(0);
    }

    QString selectedValue() const
    {
        const QListWidgetItem *item = listWidget_ ? listWidget_->currentItem() : nullptr;
        return item ? item->data(Qt::UserRole).toString() : QString();
    }

    QString selectedDisplay() const
    {
        const QListWidgetItem *item = listWidget_ ? listWidget_->currentItem() : nullptr;
        return item ? item->data(Qt::UserRole + 1).toString() : QString();
    }

private:
    void rebuild()
    {
        const QString needle = searchEdit_ ? searchEdit_->text().trimmed().toLower() : QString();
        const bool recentOnly = recentOnlyCheck_ && recentOnlyCheck_->isChecked();
        listWidget_->clear();

        QVector<CatalogEntry> sorted = entries_;
        std::sort(sorted.begin(), sorted.end(), [this](const CatalogEntry &lhs, const CatalogEntry &rhs) {
            const int lhsRecent = recentRank(lhs.value);
            const int rhsRecent = recentRank(rhs.value);
            const bool lhsCurrent = !currentValue_.isEmpty() && lhs.value.compare(currentValue_, Qt::CaseInsensitive) == 0;
            const bool rhsCurrent = !currentValue_.isEmpty() && rhs.value.compare(currentValue_, Qt::CaseInsensitive) == 0;
            if (lhsCurrent != rhsCurrent)
                return lhsCurrent;
            if ((lhsRecent >= 0) != (rhsRecent >= 0))
                return lhsRecent >= 0;
            if (lhsRecent >= 0 && rhsRecent >= 0 && lhsRecent != rhsRecent)
                return lhsRecent < rhsRecent;
            return QString::compare(lhs.display, rhs.display, Qt::CaseInsensitive) < 0;
        });

        int visibleCount = 0;
        for (const CatalogEntry &entry : sorted)
        {
            const QString trimmedValue = entry.value.trimmed();
            const bool isRecent = recentRank(trimmedValue) >= 0;
            if (recentOnly && !isRecent)
                continue;

            const QString haystack = QStringLiteral("%1 %2 %3 %4 %5").arg(entry.display, trimmedValue, entry.modality, entry.family, entry.compatibilityNote).toLower();
            if (!needle.isEmpty() && !haystack.contains(needle))
                continue;

            QString display = entry.display;
            if (display.trimmed().isEmpty())
                display = QFileInfo(trimmedValue).completeBaseName();
            if (display.trimmed().isEmpty())
                display = trimmedValue;

            const QFileInfo info(trimmedValue);
            QString secondary;
            if (info.exists())
            {
                secondary = info.dir().dirName();
                if (!secondary.isEmpty())
                    display = QStringLiteral("%1  •  %2").arg(display, secondary);
            }

            auto *item = new QListWidgetItem(display, listWidget_);
            item->setData(Qt::UserRole, trimmedValue);
            item->setData(Qt::UserRole + 1, entry.display);
            item->setData(Qt::UserRole + 2, isRecent);
            item->setData(Qt::UserRole + 3, entry.modality);
            item->setData(Qt::UserRole + 4, entry.family);
            item->setData(Qt::UserRole + 5, entry.compatibilityNote);
            item->setData(Qt::UserRole + 6, entry.confidence);
            item->setToolTip(trimmedValue);
            ++visibleCount;
        }

        if (resultsLabel_)
            resultsLabel_->setText(QStringLiteral("%1 result%2").arg(visibleCount).arg(visibleCount == 1 ? QString() : QStringLiteral("s")));
    }

    int recentRank(const QString &value) const
    {
        for (int index = 0; index < recentValues_.size(); ++index)
        {
            if (recentValues_.at(index).compare(value, Qt::CaseInsensitive) == 0)
                return index;
        }
        return -1;
    }

    void updateDetails(QListWidgetItem *item)
    {
        if (!item)
        {
            detailTitleLabel_->setText(QStringLiteral("Select an asset"));
            detailMetaLabel_->setText(QStringLiteral("Search and browse by recognition instead of recalling file names."));
            detailPathLabel_->clear();
            return;
        }

        const QString value = item->data(Qt::UserRole).toString();
        const QString display = item->data(Qt::UserRole + 1).toString();
        const bool isRecent = item->data(Qt::UserRole + 2).toBool();
        const QString modality = item->data(Qt::UserRole + 3).toString().trimmed();
        const QString family = item->data(Qt::UserRole + 4).toString().trimmed();
        const QString note = item->data(Qt::UserRole + 5).toString().trimmed();
        const int confidence = item->data(Qt::UserRole + 6).toInt();
        const QFileInfo info(value);

        detailTitleLabel_->setText(display.trimmed().isEmpty() ? value : display);

        QStringList meta;
        if (isRecent)
            meta << QStringLiteral("Recent selection");
        if (!modality.isEmpty())
            meta << QStringLiteral("Modality: %1").arg(modality);
        if (!family.isEmpty())
            meta << family;
        if (confidence > 0)
            meta << QStringLiteral("Confidence: %1%").arg(confidence);
        if (!note.isEmpty())
            meta << note;
        if (info.exists())
        {
            meta << QStringLiteral("File");
            if (!info.suffix().trimmed().isEmpty())
                meta << QStringLiteral(".%1").arg(info.suffix().toLower());
            const qint64 sizeMb = info.size() / (1024 * 1024);
            if (sizeMb > 0)
                meta << QStringLiteral("%1 MB").arg(sizeMb);
            const QString folder = info.dir().dirName().trimmed();
            if (!folder.isEmpty())
                meta << QStringLiteral("Folder: %1").arg(folder);
        }
        else if (!value.trimmed().isEmpty())
        {
            meta << QStringLiteral("External or unresolved path");
        }
        detailMetaLabel_->setText(meta.join(QStringLiteral(" · ")));
        detailPathLabel_->setText(value);
        detailPathLabel_->setToolTip(value);
    }

    QVector<CatalogEntry> entries_;
    QStringList recentValues_;
    QString recentSettingsKey_;
    QString currentValue_;
    QLineEdit *searchEdit_ = nullptr;
    QCheckBox *recentOnlyCheck_ = nullptr;
    QLabel *resultsLabel_ = nullptr;
    QSplitter *splitter_ = nullptr;
    QListWidget *listWidget_ = nullptr;
    QLabel *detailTitleLabel_ = nullptr;
    QLabel *detailMetaLabel_ = nullptr;
    QLabel *detailPathLabel_ = nullptr;
};

void persistRecentSelection(const QString &settingsKey, const QString &value)
{
    const QString trimmed = value.trimmed();
    if (settingsKey.trimmed().isEmpty() || trimmed.isEmpty())
        return;

    QSettings settings;
    QStringList values = settings.value(settingsKey).toStringList();
    values.removeAll(trimmed);
    values.prepend(trimmed);
    while (values.size() > 12)
        values.removeLast();
    settings.setValue(settingsKey, values);
}

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

bool isImageAssetPath(const QString &path)
{
    const QString suffix = QFileInfo(path.trimmed()).suffix().toLower();
    return QStringList{QStringLiteral("png"),
                       QStringLiteral("jpg"),
                       QStringLiteral("jpeg"),
                       QStringLiteral("webp"),
                       QStringLiteral("bmp"),
                       QStringLiteral("gif")}.contains(suffix);
}

bool isVideoAssetPath(const QString &path)
{
    const QString suffix = QFileInfo(path.trimmed()).suffix().toLower();
    return QStringList{QStringLiteral("mp4"),
                       QStringLiteral("webm"),
                       QStringLiteral("mov"),
                       QStringLiteral("mkv"),
                       QStringLiteral("avi"),
                       QStringLiteral("gif")}.contains(suffix);
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
        QStringLiteral("*.bin"),
        QStringLiteral("*.gguf")};
}

bool containsTokenish(const QString &haystack, const QString &token)
{
    const QString pattern = QStringLiteral("(^|[^a-z0-9])%1([^a-z0-9]|$)")
                                .arg(QRegularExpression::escape(token.toLower()));
    return QRegularExpression(pattern).match(haystack.toLower()).hasMatch();
}

bool containsAnyLiteral(const QString &haystack, const QStringList &needles)
{
    const QString lower = haystack.toLower();
    for (const QString &needle : needles)
    {
        if (!needle.trimmed().isEmpty() && lower.contains(needle.toLower()))
            return true;
    }
    return false;
}

AssetClassification classifyCatalogAsset(const QString &absolutePath,
                                          const QString &display,
                                          const QString &subDir,
                                          const QString &assetKind)
{
    const QString haystack = QStringLiteral("%1 %2 %3")
                                 .arg(display, absolutePath, subDir)
                                 .replace(QStringLiteral("\\"), QStringLiteral("/"))
                                 .toLower();

    auto classified = [](const QString &modality,
                         const QString &family,
                         const QString &note,
                         int confidence) {
        AssetClassification out;
        out.modality = modality;
        out.family = family;
        out.compatibilityNote = note;
        out.confidence = confidence;
        return out;
    };

    const bool isLora = assetKind.compare(QStringLiteral("lora"), Qt::CaseInsensitive) == 0;
    const QString kindPrefix = isLora ? QStringLiteral("LoRA") : QStringLiteral("model");

    if (containsAnyLiteral(haystack, {QStringLiteral("wan2"), QStringLiteral("wan_"), QStringLiteral("wan-")}) ||
        containsTokenish(haystack, QStringLiteral("wan")))
    {
        return classified(QStringLiteral("video"), QStringLiteral("WAN video family"),
                          QStringLiteral("%1 name/path matches WAN video signals.").arg(kindPrefix), 96);
    }

    if (containsAnyLiteral(haystack, {QStringLiteral("ltx-video"), QStringLiteral("ltxv"), QStringLiteral("ltx_"), QStringLiteral("ltx-")}) ||
        containsTokenish(haystack, QStringLiteral("ltx")))
    {
        return classified(QStringLiteral("video"), QStringLiteral("LTX video family"),
                          QStringLiteral("%1 name/path matches LTX video signals.").arg(kindPrefix), 94);
    }

    if (containsAnyLiteral(haystack, {QStringLiteral("hunyuanvideo"), QStringLiteral("hunyuan-video"), QStringLiteral("hunyuan_video"), QStringLiteral("hyvideo")}))
    {
        return classified(QStringLiteral("video"), QStringLiteral("Hunyuan Video family"),
                          QStringLiteral("%1 name/path matches Hunyuan Video signals.").arg(kindPrefix), 94);
    }

    if (containsAnyLiteral(haystack, {QStringLiteral("cogvideox"), QStringLiteral("cogvideo"), QStringLiteral("cog-video")}))
    {
        return classified(QStringLiteral("video"), QStringLiteral("CogVideoX family"),
                          QStringLiteral("%1 name/path matches CogVideoX video signals.").arg(kindPrefix), 92);
    }

    if (containsAnyLiteral(haystack, {QStringLiteral("mochi"), QStringLiteral("animatediff"), QStringLiteral("stable-video"), QStringLiteral("svd"), QStringLiteral("pyramid-flow"), QStringLiteral("skyreels")}))
    {
        return classified(QStringLiteral("video"), QStringLiteral("Video generation family"),
                          QStringLiteral("%1 name/path matches known video generation signals.").arg(kindPrefix), 88);
    }

    if (containsAnyLiteral(haystack, {QStringLiteral("pony"), QStringLiteral("illustrious"), QStringLiteral("sdxl"), QStringLiteral("stable-diffusion-xl"), QStringLiteral("juggernaut"), QStringLiteral("realvis"), QStringLiteral("dreamshaper")}))
    {
        QString family = QStringLiteral("Image generation family");
        if (haystack.contains(QStringLiteral("pony")))
            family = QStringLiteral("Pony image family");
        else if (haystack.contains(QStringLiteral("illustrious")))
            family = QStringLiteral("Illustrious image family");
        else if (haystack.contains(QStringLiteral("sdxl")) || haystack.contains(QStringLiteral("stable-diffusion-xl")))
            family = QStringLiteral("SDXL / XL image family");

        return classified(QStringLiteral("image"), family,
                          QStringLiteral("%1 name/path matches image checkpoint signals.").arg(kindPrefix), 90);
    }

    if (containsAnyLiteral(haystack, {QStringLiteral("z-image"), QStringLiteral("zimage"), QStringLiteral("qwen-image"), QStringLiteral("qwen_image"), QStringLiteral("flux"), QStringLiteral("sd3"), QStringLiteral("sd-3"), QStringLiteral("sd15"), QStringLiteral("sd1.5")}))
    {
        QString family = QStringLiteral("Image generation family");
        if (haystack.contains(QStringLiteral("flux")))
            family = QStringLiteral("Flux image family");
        else if (haystack.contains(QStringLiteral("z-image")) || haystack.contains(QStringLiteral("zimage")))
            family = QStringLiteral("Z-Image family");
        else if (haystack.contains(QStringLiteral("qwen-image")) || haystack.contains(QStringLiteral("qwen_image")))
            family = QStringLiteral("Qwen Image family");

        return classified(QStringLiteral("image"), family,
                          QStringLiteral("%1 name/path matches modern image model signals.").arg(kindPrefix), 88);
    }

    if (subDir.contains(QStringLiteral("video"), Qt::CaseInsensitive))
    {
        return classified(QStringLiteral("video"), QStringLiteral("Video generation family"),
                          QStringLiteral("%1 is stored under a video-oriented model folder.").arg(kindPrefix), 70);
    }

    if (subDir.contains(QStringLiteral("checkpoints"), Qt::CaseInsensitive) && !isLora)
    {
        return classified(QStringLiteral("image"), QStringLiteral("Image checkpoint family"),
                          QStringLiteral("Checkpoint folder fallback; visible on image pages by default."), 52);
    }

    return classified(QStringLiteral("unknown"), QStringLiteral("Unknown family"),
                      QStringLiteral("No reliable modality signal detected; hidden on video pages unless compatibility override is enabled."), 0);
}

bool assetAllowedForMode(const QString &modality, bool videoMode, bool showIncompatible)
{
    const QString normalized = modality.trimmed().toLower();
    if (showIncompatible)
        return true;
    if (normalized == QStringLiteral("mixed"))
        return true;
    if (normalized == QStringLiteral("unknown"))
        return !videoMode;
    return videoMode ? normalized == QStringLiteral("video") : normalized == QStringLiteral("image");
}

QString assetModeFilterLabel(bool videoMode, bool showIncompatible)
{
    if (showIncompatible)
        return QStringLiteral("showing all known, unknown, and incompatible assets");
    return videoMode
               ? QStringLiteral("showing video-compatible assets only")
               : QStringLiteral("showing image-compatible assets; unknown checkpoints remain visible");
}

QVector<CatalogEntry> filterCatalogEntriesForMode(const QMap<QString, QString> &displayByValue,
                                                  const QMap<QString, QString> &modalityByValue,
                                                  const QMap<QString, QString> &familyByValue,
                                                  const QMap<QString, QString> &noteByValue,
                                                  const QMap<QString, int> &confidenceByValue,
                                                  bool videoMode,
                                                  bool showIncompatible)
{
    QVector<CatalogEntry> entries;
    entries.reserve(displayByValue.size());

    for (auto it = displayByValue.constBegin(); it != displayByValue.constEnd(); ++it)
    {
        const QString value = it.key();
        const QString modality = modalityByValue.value(value, QStringLiteral("unknown"));
        if (!assetAllowedForMode(modality, videoMode, showIncompatible))
            continue;

        CatalogEntry entry;
        entry.display = it.value();
        entry.value = value;
        entry.modality = modality;
        entry.family = familyByValue.value(value, QStringLiteral("Unknown family"));
        entry.compatibilityNote = noteByValue.value(value, QStringLiteral("No compatibility note available."));
        entry.confidence = confidenceByValue.value(value, 0);
        entries.push_back(entry);
    }

    std::sort(entries.begin(), entries.end(), [](const CatalogEntry &lhs, const CatalogEntry &rhs) {
        if (lhs.modality != rhs.modality)
            return lhs.modality < rhs.modality;
        if (lhs.family != rhs.family)
            return QString::compare(lhs.family, rhs.family, Qt::CaseInsensitive) < 0;
        return QString::compare(lhs.display, rhs.display, Qt::CaseInsensitive) < 0;
    });

    return entries;
}

QVector<CatalogEntry> scanCatalog(const QString &rootPath, const QString &subDir, const QString &assetKind = QStringLiteral("model"))
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
        CatalogEntry entry;
        entry.display = compactCatalogDisplay(rootPath, absolutePath, needsDisambiguator);
        entry.value = absolutePath;
        const AssetClassification classification = classifyCatalogAsset(absolutePath, entry.display, subDir, assetKind);
        entry.modality = classification.modality;
        entry.family = classification.family;
        entry.compatibilityNote = classification.compatibilityNote;
        entry.confidence = classification.confidence;
        entries.push_back(entry);

    }

    std::sort(entries.begin(), entries.end(), [](const CatalogEntry &lhs, const CatalogEntry &rhs) {
        return QString::compare(lhs.display, rhs.display, Qt::CaseInsensitive) < 0;
    });

    return entries;
}

QVector<CatalogEntry> scanCatalogGroup(const QString &rootPath,
                                       const QStringList &subDirs,
                                       const QString &assetKind = QStringLiteral("model"))
{
    QVector<CatalogEntry> merged;
    QSet<QString> seen;

    for (const QString &subDir : subDirs)
    {
        const QVector<CatalogEntry> entries = scanCatalog(rootPath, subDir, assetKind);
        for (const CatalogEntry &entry : entries)
        {
            const QString key = entry.value.trimmed().toLower();
            if (key.isEmpty() || seen.contains(key))
                continue;
            seen.insert(key);
            merged.push_back(entry);
        }
    }

    std::sort(merged.begin(), merged.end(), [](const CatalogEntry &lhs, const CatalogEntry &rhs) {
        if (lhs.modality != rhs.modality)
            return lhs.modality < rhs.modality;
        if (lhs.family != rhs.family)
            return QString::compare(lhs.family, rhs.family, Qt::CaseInsensitive) < 0;
        return QString::compare(lhs.display, rhs.display, Qt::CaseInsensitive) < 0;
    });

    return merged;
}


QString resolveCatalogValueByCandidates(const QVector<CatalogEntry> &entries, const QStringList &candidates)
{
    for (const QString &candidate : candidates)
    {
        const QString trimmed = candidate.trimmed();
        if (trimmed.isEmpty())
            continue;

        for (const CatalogEntry &entry : entries)
        {
            if (entry.value.compare(trimmed, Qt::CaseInsensitive) == 0 ||
                entry.display.compare(trimmed, Qt::CaseInsensitive) == 0)
            {
                return entry.value;
            }
        }
    }

    for (const QString &candidate : candidates)
    {
        const QString needle = candidate.trimmed().toLower();
        if (needle.isEmpty())
            continue;

        for (const CatalogEntry &entry : entries)
        {
            const QString haystack = QStringLiteral("%1 %2 %3")
                                         .arg(entry.display, entry.value, shortDisplayFromValue(entry.value))
                                         .toLower();
            if (haystack.contains(needle))
                return entry.value;
        }
    }

    return QString();
}

QString serializeLoraStack(const QVector<ImageGenerationPage::LoraStackEntry> &stack)
{
    QJsonArray array;
    for (const auto &entry : stack)
    {
        QJsonObject obj;
        obj.insert(QStringLiteral("display"), entry.display);
        obj.insert(QStringLiteral("value"), entry.value);
        obj.insert(QStringLiteral("weight"), entry.weight);
        obj.insert(QStringLiteral("enabled"), entry.enabled);
        array.append(obj);
    }
    return QString::fromUtf8(QJsonDocument(array).toJson(QJsonDocument::Compact));
}

QVector<ImageGenerationPage::LoraStackEntry> deserializeLoraStack(const QString &json)
{
    QVector<ImageGenerationPage::LoraStackEntry> stack;
    const QJsonDocument doc = QJsonDocument::fromJson(json.toUtf8());
    if (!doc.isArray())
        return stack;

    for (const QJsonValue &value : doc.array())
    {
        if (!value.isObject())
            continue;
        const QJsonObject obj = value.toObject();
        ImageGenerationPage::LoraStackEntry entry;
        entry.display = obj.value(QStringLiteral("display")).toString().trimmed();
        entry.value = obj.value(QStringLiteral("value")).toString().trimmed();
        entry.weight = obj.value(QStringLiteral("weight")).toDouble(1.0);
        entry.enabled = obj.value(QStringLiteral("enabled")).toBool(true);
        if (!entry.value.isEmpty())
            stack.push_back(entry);
    }

    return stack;
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

void repolishWidget(QWidget *widget)
{
    if (!widget)
        return;

    if (QStyle *style = widget->style())
    {
        style->unpolish(widget);
        style->polish(widget);
    }
    widget->update();
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
        updateAssetIntelligenceUi();
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
    updatePrimaryActionAvailability();
    schedulePreviewRefresh(busy_ ? 0 : 30);

    QTimer::singleShot(0, this, [this]() {
        if (leftScrollArea_ && leftScrollArea_->verticalScrollBar())
            leftScrollArea_->verticalScrollBar()->setValue(0);
    });
}

QJsonObject ImageGenerationPage::buildRequestPayload() const
{
    QJsonObject payload;
    payload.insert(QStringLiteral("mode"), modeKey());
    payload.insert(QStringLiteral("prompt"), promptEdit_ ? promptEdit_->toPlainText().trimmed() : QString());
    payload.insert(QStringLiteral("negative_prompt"), negativePromptEdit_ ? negativePromptEdit_->toPlainText().trimmed() : QString());
    payload.insert(QStringLiteral("preset"), currentComboValue(presetCombo_));
    payload.insert(QStringLiteral("model"), selectedModelValue());
    payload.insert(QStringLiteral("model_display"), selectedModelDisplay_);
    payload.insert(QStringLiteral("model_modality"), modelModalityByValue_.value(selectedModelPath_, QStringLiteral("unknown")));
    payload.insert(QStringLiteral("model_family"), modelFamilyByValue_.value(selectedModelPath_, QStringLiteral("unknown")));
    payload.insert(QStringLiteral("workflow_profile"), currentComboValue(workflowCombo_));
    payload.insert(QStringLiteral("workflow_draft_source"), workflowDraftSource_);
    payload.insert(QStringLiteral("workflow_profile_path"), workflowDraftProfilePath_);
    payload.insert(QStringLiteral("workflow_path"), workflowDraftWorkflowPath_);
    payload.insert(QStringLiteral("compiled_prompt_path"), workflowDraftCompiledPromptPath_);
    payload.insert(QStringLiteral("workflow_backend"), workflowDraftBackend_);
    payload.insert(QStringLiteral("workflow_media_type"), workflowDraftMediaType_);

    QJsonArray loraArray;
    QString primaryLora;
    QString primaryLoraDisplay;
    double primaryLoraWeight = 1.0;
    for (const LoraStackEntry &entry : loraStack_)
    {
        QJsonObject item;
        item.insert(QStringLiteral("name"), entry.value);
        item.insert(QStringLiteral("display"), entry.display);
        item.insert(QStringLiteral("strength"), entry.weight);
        item.insert(QStringLiteral("enabled"), entry.enabled);
        loraArray.append(item);

        if (primaryLora.isEmpty() && entry.enabled && !entry.value.trimmed().isEmpty())
        {
            primaryLora = entry.value.trimmed();
            primaryLoraDisplay = entry.display.trimmed();
            primaryLoraWeight = entry.weight;
        }
    }

    payload.insert(QStringLiteral("loras"), loraArray);
    payload.insert(QStringLiteral("lora_stack"), loraArray);
    payload.insert(QStringLiteral("lora"), primaryLora);
    payload.insert(QStringLiteral("lora_display"), primaryLoraDisplay);
    payload.insert(QStringLiteral("lora_summary"), primaryLora);
    payload.insert(QStringLiteral("lora_stack_summary"), loraStackSummaryLabel_ ? loraStackSummaryLabel_->text() : QString());
    payload.insert(QStringLiteral("lora_scale"), primaryLoraWeight);

    payload.insert(QStringLiteral("sampler"), currentComboValue(samplerCombo_));
    payload.insert(QStringLiteral("scheduler"), currentComboValue(schedulerCombo_));
    payload.insert(QStringLiteral("steps"), stepsSpin_ ? stepsSpin_->value() : 0);

    const double cfgValue = cfgSpin_ ? cfgSpin_->value() : 0.0;
    payload.insert(QStringLiteral("cfg_scale"), cfgValue);
    payload.insert(QStringLiteral("cfg"), cfgValue);

    payload.insert(QStringLiteral("seed"), seedSpin_ ? seedSpin_->value() : 0);
    payload.insert(QStringLiteral("width"), widthSpin_ ? widthSpin_->value() : 0);
    payload.insert(QStringLiteral("height"), heightSpin_ ? heightSpin_->value() : 0);

    if (isVideoMode())
    {
        const int frames = frameCountSpin_ ? frameCountSpin_->value() : 81;
        const int fps = fpsSpin_ ? fpsSpin_->value() : 16;
        payload.insert(QStringLiteral("frames"), frames);
        payload.insert(QStringLiteral("num_frames"), frames);
        payload.insert(QStringLiteral("frame_count"), frames);
        payload.insert(QStringLiteral("fps"), fps);
        payload.insert(QStringLiteral("duration_seconds"), fps > 0 ? static_cast<double>(frames) / static_cast<double>(fps) : 0.0);
    }

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
    leftScrollArea_->setObjectName(QStringLiteral("LeftRailScrollArea"));
    leftScrollArea_->setWidgetResizable(true);
    leftScrollArea_->setFrameShape(QFrame::NoFrame);
    leftScrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    leftScrollArea_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    leftScrollArea_->setMinimumWidth(360);
    leftScrollArea_->setMaximumWidth(470);
    leftScrollArea_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    auto *leftContainer = new QWidget(leftScrollArea_);
    auto *leftLayout = new QVBoxLayout(leftContainer);
    leftLayout->setContentsMargins(0, 0, 4, 0);
    leftLayout->setSpacing(8);
    leftLayout->setSizeConstraint(QLayout::SetMinAndMaxSize);

    auto *promptCard = createCard(QStringLiteral("PromptCard"));
    auto *promptLayout = new QVBoxLayout(promptCard);
    promptLayout->setContentsMargins(12, 12, 12, 12);
    promptLayout->setSpacing(8);

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
    applyPresetButton->setMinimumWidth(104);
    connect(applyPresetButton, &QPushButton::clicked, this, [this]() { applyPreset(presetCombo_->currentText()); });
    presetRow->addWidget(applyPresetButton);

    promptEdit_ = new QTextEdit(promptCard);
    promptEdit_->setPlaceholderText(QStringLiteral("Describe the subject, framing, lighting, materials, style cues, and production notes here…"));
    promptEdit_->setMinimumHeight(isVideoMode() ? 126 : 148);
    promptEdit_->setMaximumHeight(isVideoMode() ? 144 : 166);
    promptEdit_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    negativePromptEdit_ = new QTextEdit(promptCard);
    negativePromptEdit_->setPlaceholderText(QStringLiteral("Low quality, blurry, extra fingers, watermark, text, duplicate limbs…"));
    negativePromptEdit_->setMinimumHeight(82);
    negativePromptEdit_->setMaximumHeight(100);
    negativePromptEdit_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    promptLayout->addLayout(presetRow);
    promptLayout->addWidget(presetCombo_);
    promptLayout->addWidget(createSectionTitle(QStringLiteral("Prompt"), promptCard));
    promptLayout->addWidget(promptEdit_);
    promptLayout->addWidget(createSectionTitle(QStringLiteral("Negative Prompt"), promptCard));
    promptLayout->addWidget(negativePromptEdit_);
    promptCard->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Maximum);
    leftLayout->addWidget(promptCard);

    inputCard_ = createCard(QStringLiteral("InputCard"));
    auto *inputLayout = new QVBoxLayout(inputCard_);
    inputLayout->setContentsMargins(12, 12, 12, 12);
    inputLayout->setSpacing(8);
    inputLayout->addWidget(createSectionTitle(isVideoMode() ? QStringLiteral("Input Keyframe") : QStringLiteral("Input Image"), inputCard_));

    auto *dropFrame = new DropTargetFrame(inputCard_);
    dropFrame->setObjectName(QStringLiteral("InputDropCard"));
    auto *dropLayout = new QVBoxLayout(dropFrame);
    dropLayout->setContentsMargins(10, 10, 10, 10);
    dropLayout->setSpacing(6);

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

    auto *quickControlsCard = createCard(QStringLiteral("QuickControlsCard"));
    auto *quickControlsLayout = new QVBoxLayout(quickControlsCard);
    quickControlsLayout->setContentsMargins(12, 12, 12, 12);
    quickControlsLayout->setSpacing(8);
    quickControlsLayout->addWidget(createSectionTitle(QStringLiteral("Generation Quick Controls"), quickControlsCard));
    auto *quickControlsHint = createSectionBody(QStringLiteral("Core generation controls stay here."), quickControlsCard);
    quickControlsHint->setMaximumHeight(22);
    quickControlsLayout->addWidget(quickControlsHint);
    leftLayout->addWidget(quickControlsCard);

    auto *outputQueueCard = createCard(QStringLiteral("OutputQueueCard"));
    auto *outputQueueLayout = new QVBoxLayout(outputQueueCard);
    outputQueueLayout->setContentsMargins(12, 12, 12, 12);
    outputQueueLayout->setSpacing(8);
    auto *outputQueueHeader = new QWidget(outputQueueCard);
    auto *outputQueueHeaderLayout = new QHBoxLayout(outputQueueHeader);
    outputQueueHeaderLayout->setContentsMargins(0, 0, 0, 0);
    outputQueueHeaderLayout->setSpacing(8);
    outputQueueHeaderLayout->addWidget(createSectionTitle(QStringLiteral("Output / Queue"), outputQueueCard), 1);
    outputQueueToggleButton_ = new QToolButton(outputQueueCard);
    outputQueueToggleButton_->setObjectName(QStringLiteral("InspectorSectionToggle"));
    outputQueueToggleButton_->setToolButtonStyle(Qt::ToolButtonTextOnly);
    outputQueueToggleButton_->setText(QStringLiteral("Open"));
    outputQueueToggleButton_->setMinimumWidth(72);
    outputQueueToggleButton_->setMinimumHeight(26);
    outputQueueToggleButton_->setFixedHeight(26);
    outputQueueToggleButton_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    outputQueueToggleButton_->setVisible(false);
    outputQueueHeaderLayout->addWidget(outputQueueToggleButton_, 0, Qt::AlignRight | Qt::AlignVCenter);
    outputQueueLayout->addWidget(outputQueueHeader);
    connect(outputQueueToggleButton_, &QToolButton::clicked, this, [this](bool) {
        outputQueueForceOpen_ = !outputQueueForceOpen_;

        updateAdaptiveLayout();

        if (!outputQueueForceOpen_ || !leftScrollArea_)
            return;

        QTimer::singleShot(0, this, [this]() {
            QWidget *card = findChild<QWidget *>(QStringLiteral("OutputQueueCard"));
            if (!card || !leftScrollArea_)
                return;
            leftScrollArea_->ensureWidgetVisible(card, 4, 8);
        });
    });
    leftLayout->addWidget(outputQueueCard);

    auto *advancedCard = createCard(QStringLiteral("AdvancedCard"));
    auto *advancedLayout = new QVBoxLayout(advancedCard);
    advancedLayout->setContentsMargins(12, 12, 12, 12);
    advancedLayout->setSpacing(8);
    auto *advancedHeader = new QWidget(advancedCard);
    auto *advancedHeaderLayout = new QHBoxLayout(advancedHeader);
    advancedHeaderLayout->setContentsMargins(0, 0, 0, 0);
    advancedHeaderLayout->setSpacing(8);
    advancedHeaderLayout->addWidget(createSectionTitle(QStringLiteral("Advanced"), advancedCard), 1);
    advancedToggleButton_ = new QToolButton(advancedCard);
    advancedToggleButton_->setObjectName(QStringLiteral("InspectorSectionToggle"));
    advancedToggleButton_->setToolButtonStyle(Qt::ToolButtonTextOnly);
    advancedToggleButton_->setText(QStringLiteral("Open"));
    advancedToggleButton_->setMinimumWidth(72);
    advancedToggleButton_->setMinimumHeight(26);
    advancedToggleButton_->setFixedHeight(26);
    advancedToggleButton_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    advancedHeaderLayout->addWidget(advancedToggleButton_, 0, Qt::AlignRight | Qt::AlignVCenter);
    advancedLayout->addWidget(advancedHeader);
    connect(advancedToggleButton_, &QToolButton::clicked, this, [this](bool) {
        advancedForceOpen_ = !advancedForceOpen_;

        updateAdaptiveLayout();

        if (!advancedForceOpen_ || !leftScrollArea_)
            return;

        QTimer::singleShot(0, this, [this]() {
            QWidget *card = findChild<QWidget *>(QStringLiteral("AdvancedCard"));
            if (!card || !leftScrollArea_)
                return;
            leftScrollArea_->ensureWidgetVisible(card, 4, 8);
        });
    });
    auto *advancedHint = createSectionBody(QStringLiteral("Mode-specific controls."), advancedCard);
    advancedHint->setObjectName(QStringLiteral("AdvancedBodyHint"));
    advancedHint->setMaximumHeight(24);
    advancedLayout->addWidget(advancedHint);
    leftLayout->addWidget(advancedCard);
    leftLayout->addStretch(1);

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
    previewLabel_->setProperty("emptyState", true);
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

    readinessHintLabel_ = new QLabel(canvasCard);
    readinessHintLabel_->setObjectName(QStringLiteral("ReadinessHint"));
    readinessHintLabel_->setWordWrap(false);
    readinessHintLabel_->setMaximumWidth(280);
    readinessHintLabel_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
    readinessHintLabel_->setVisible(false);

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
    actionRow->addWidget(readinessHintLabel_, 0, Qt::AlignVCenter);
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

    auto *checkpointValueCard = new QFrame(stackCard_);
    checkpointValueCard->setObjectName(QStringLiteral("InputDropCard"));
    auto *checkpointValueLayout = new QHBoxLayout(checkpointValueCard);
    checkpointValueLayout->setContentsMargins(12, 10, 12, 10);
    checkpointValueLayout->setSpacing(8);

    selectedModelLabel_ = new QLabel(QStringLiteral("No checkpoint selected"), checkpointValueCard);
    selectedModelLabel_->setObjectName(QStringLiteral("SectionBody"));
    selectedModelLabel_->setWordWrap(true);
    checkpointValueLayout->addWidget(selectedModelLabel_, 1);

    browseModelButton_ = new QPushButton(QStringLiteral("Browse"), stackCard_);
    browseModelButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    clearModelButton_ = new QPushButton(QStringLiteral("Clear"), stackCard_);
    clearModelButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    connect(browseModelButton_, &QPushButton::clicked, this, &ImageGenerationPage::showCheckpointPicker);
    connect(clearModelButton_, &QPushButton::clicked, this, [this]() { setSelectedModel(QString(), QString()); });

    workflowCombo_ = new ClickOnlyComboBox(stackCard_);
    workflowCombo_->setEditable(false);
    workflowCombo_->addItem(QStringLiteral("Default Canvas"), QStringLiteral("Default Canvas"));
    workflowCombo_->addItem(QStringLiteral("Portrait Detail"), QStringLiteral("Portrait Detail"));
    workflowCombo_->addItem(QStringLiteral("Stylized Concept"), QStringLiteral("Stylized Concept"));
    workflowCombo_->addItem(QStringLiteral("Upscale / Repair"), QStringLiteral("Upscale / Repair"));
    configureComboBox(workflowCombo_);

    loraStackContainer_ = new QWidget(stackCard_);
    loraStackLayout_ = new QVBoxLayout(loraStackContainer_);
    loraStackLayout_->setContentsMargins(0, 0, 0, 0);
    loraStackLayout_->setSpacing(8);

    loraStackSummaryLabel_ = new QLabel(QStringLiteral("No LoRAs in stack"), stackCard_);
    loraStackSummaryLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    loraStackSummaryLabel_->setWordWrap(true);

    addLoraButton_ = new QPushButton(QStringLiteral("Add LoRA"), stackCard_);
    addLoraButton_->setObjectName(QStringLiteral("SecondaryActionButton"));
    clearLorasButton_ = new QPushButton(QStringLiteral("Clear Stack"), stackCard_);
    clearLorasButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    connect(addLoraButton_, &QPushButton::clicked, this, &ImageGenerationPage::showLoraPicker);
    connect(clearLorasButton_, &QPushButton::clicked, this, [this]() { loraStack_.clear(); rebuildLoraStackUi(); scheduleUiRefresh(0); });

    auto *stackForm = new QGridLayout;
    stackForm->setHorizontalSpacing(10);
    stackForm->setVerticalSpacing(8);
    stackForm->setColumnStretch(1, 1);

    int stackRow = 0;
    stackForm->addWidget(new QLabel(QStringLiteral("Checkpoint"), stackCard_), stackRow, 0);
    stackForm->addWidget(checkpointValueCard, stackRow, 1);
    ++stackRow;
    auto *checkpointActions = new QWidget(stackCard_);
    auto *checkpointActionsLayout = new QHBoxLayout(checkpointActions);
    checkpointActionsLayout->setContentsMargins(0, 0, 0, 0);
    checkpointActionsLayout->setSpacing(8);
    checkpointActionsLayout->addWidget(browseModelButton_);
    checkpointActionsLayout->addWidget(clearModelButton_);
    checkpointActionsLayout->addStretch(1);
    stackForm->addWidget(checkpointActions, stackRow, 1);
    ++stackRow;
    stackForm->addWidget(new QLabel(QStringLiteral("Workflow"), stackCard_), stackRow, 0);
    stackForm->addWidget(workflowCombo_, stackRow, 1);
    ++stackRow;
    stackForm->addWidget(new QLabel(QStringLiteral("LoRA Stack"), stackCard_), stackRow, 0, Qt::AlignTop);
    stackForm->addWidget(loraStackContainer_, stackRow, 1);
    ++stackRow;
    auto *loraActions = new QWidget(stackCard_);
    auto *loraActionsLayout = new QHBoxLayout(loraActions);
    loraActionsLayout->setContentsMargins(0, 0, 0, 0);
    loraActionsLayout->setSpacing(8);
    loraActionsLayout->addWidget(addLoraButton_);
    loraActionsLayout->addWidget(clearLorasButton_);
    loraActionsLayout->addStretch(1);
    stackForm->addWidget(loraActions, stackRow, 1);
    ++stackRow;
    stackForm->addWidget(new QLabel(QStringLiteral("Stack Summary"), stackCard_), stackRow, 0, Qt::AlignTop);
    stackForm->addWidget(loraStackSummaryLabel_, stackRow, 1);
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

    auto *modelStackHeader = new QWidget(stackCard_);
    auto *modelStackHeaderLayout = new QHBoxLayout(modelStackHeader);
    modelStackHeaderLayout->setContentsMargins(0, 0, 0, 0);
    modelStackHeaderLayout->setSpacing(8);
    modelStackHeaderLayout->addWidget(createSectionTitle(QStringLiteral("Model Stack"), stackCard_), 1);
    showIncompatibleAssetsCheck_ = new QCheckBox(QStringLiteral("Show all"), stackCard_);
    showIncompatibleAssetsCheck_->setObjectName(QStringLiteral("ImageGenHint"));
    showIncompatibleAssetsCheck_->setToolTip(QStringLiteral("Show unknown or cross-modality assets. Keep this off for normal image/video filtering."));
    connect(showIncompatibleAssetsCheck_, &QCheckBox::toggled, this, [this](bool) {
        refreshSelectedModelUi();
        rebuildLoraStackUi();
        updateAssetIntelligenceUi();
    });
    modelStackHeaderLayout->addWidget(showIncompatibleAssetsCheck_, 0, Qt::AlignRight | Qt::AlignVCenter);
    stackCardLayout->addWidget(modelStackHeader);
    stackCardLayout->addLayout(stackForm);
    stackCardLayout->addLayout(stackToolsLayout_);
    rightLayout->addWidget(stackCard_);

    settingsCard_ = createCard(QStringLiteral("OutputCard"));
    auto *settingsCardLayout = new QVBoxLayout(settingsCard_);
    settingsCardLayout->setContentsMargins(12, 12, 12, 12);
    settingsCardLayout->setSpacing(8);

    samplerCombo_ = new ClickOnlyComboBox(quickControlsCard);
    samplerCombo_->addItem(QStringLiteral("euler"), QStringLiteral("euler"));
    samplerCombo_->addItem(QStringLiteral("euler_ancestral"), QStringLiteral("euler_ancestral"));
    samplerCombo_->addItem(QStringLiteral("heun"), QStringLiteral("heun"));
    samplerCombo_->addItem(QStringLiteral("dpmpp_2m"), QStringLiteral("dpmpp_2m"));
    samplerCombo_->addItem(QStringLiteral("dpmpp_sde"), QStringLiteral("dpmpp_sde"));
    samplerCombo_->addItem(QStringLiteral("uni_pc"), QStringLiteral("uni_pc"));
    configureComboBox(samplerCombo_);

    schedulerCombo_ = new ClickOnlyComboBox(quickControlsCard);
    schedulerCombo_->addItem(QStringLiteral("normal"), QStringLiteral("normal"));
    schedulerCombo_->addItem(QStringLiteral("karras"), QStringLiteral("karras"));
    schedulerCombo_->addItem(QStringLiteral("sgm_uniform"), QStringLiteral("sgm_uniform"));
    configureComboBox(schedulerCombo_);

    stepsSpin_ = new QSpinBox(quickControlsCard);
    stepsSpin_->setRange(1, 200);
    stepsSpin_->setValue(28);
    configureSpinBox(stepsSpin_);

    cfgSpin_ = new QDoubleSpinBox(quickControlsCard);
    cfgSpin_->setDecimals(1);
    cfgSpin_->setSingleStep(0.5);
    cfgSpin_->setRange(1.0, 30.0);
    cfgSpin_->setValue(7.0);
    configureDoubleSpinBox(cfgSpin_);

    seedSpin_ = new QSpinBox(quickControlsCard);
    seedSpin_->setRange(0, 999999999);
    seedSpin_->setSpecialValueText(QStringLiteral("Random"));
    seedSpin_->setValue(0);
    configureSpinBox(seedSpin_);

    widthSpin_ = new QSpinBox(quickControlsCard);
    widthSpin_->setRange(64, 8192);
    widthSpin_->setSingleStep(64);
    widthSpin_->setValue(isVideoMode() ? 832 : 1024);
    configureSpinBox(widthSpin_);

    heightSpin_ = new QSpinBox(quickControlsCard);
    heightSpin_->setRange(64, 8192);
    heightSpin_->setSingleStep(64);
    heightSpin_->setValue(isVideoMode() ? 480 : 1024);
    configureSpinBox(heightSpin_);

    frameCountSpin_ = new QSpinBox(quickControlsCard);
    frameCountSpin_->setRange(1, 2400);
    frameCountSpin_->setSingleStep(8);
    frameCountSpin_->setValue(81);
    frameCountSpin_->setToolTip(QStringLiteral("Total frames requested from the video workflow."));
    configureSpinBox(frameCountSpin_);

    fpsSpin_ = new QSpinBox(quickControlsCard);
    fpsSpin_->setRange(1, 120);
    fpsSpin_->setValue(16);
    fpsSpin_->setToolTip(QStringLiteral("Playback frames per second for the generated clip."));
    configureSpinBox(fpsSpin_);

    batchSpin_ = new QSpinBox(outputQueueCard);
    batchSpin_->setRange(1, 32);
    batchSpin_->setValue(1);
    configureSpinBox(batchSpin_);

    denoiseSpin_ = new QDoubleSpinBox(advancedCard);
    denoiseSpin_->setDecimals(2);
    denoiseSpin_->setSingleStep(0.05);
    denoiseSpin_->setRange(0.0, 1.0);
    denoiseSpin_->setValue(0.45);
    configureDoubleSpinBox(denoiseSpin_);

    auto makeSettingsRow = [this](QWidget *parent, const QString &labelText, QWidget *field) -> QWidget * {
        auto *rowWidget = new QWidget(parent);
        rowWidget->setMinimumHeight(30);
        auto *rowLayout = new QHBoxLayout(rowWidget);
        rowLayout->setContentsMargins(0, 0, 0, 0);
        rowLayout->setSpacing(7);

        auto *label = new QLabel(labelText, rowWidget);
        label->setMinimumWidth(62);
        label->setMaximumWidth(78);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Preferred);
        label->setObjectName(QStringLiteral("CompactFieldLabel"));
        label->setToolTip(labelText);

        field->setParent(rowWidget);
        field->setMinimumWidth(qMax(field->minimumWidth(), 120));
        field->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        rowLayout->addWidget(label);
        rowLayout->addWidget(field, 1);
        return rowWidget;
    };

    auto *aspectPresetCombo = new ClickOnlyComboBox(quickControlsCard);
    aspectPresetCombo->addItem(QStringLiteral("Custom"), QString());
    aspectPresetCombo->addItem(QStringLiteral("Square 1:1"), QStringLiteral("1024x1024"));
    aspectPresetCombo->addItem(QStringLiteral("Portrait 3:4"), QStringLiteral("1024x1344"));
    aspectPresetCombo->addItem(QStringLiteral("Landscape 3:2"), QStringLiteral("1216x832"));
    aspectPresetCombo->addItem(QStringLiteral("Wide 16:9"), QStringLiteral("1344x768"));
    configureComboBox(aspectPresetCombo);
    connect(aspectPresetCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this, aspectPresetCombo](int index) {
        const QString value = aspectPresetCombo->itemData(index, Qt::UserRole).toString();
        if (value.isEmpty() || !widthSpin_ || !heightSpin_)
            return;

        const QStringList parts = value.split(QLatin1Char('x'));
        if (parts.size() != 2)
            return;

        widthSpin_->setValue(parts.at(0).toInt());
        heightSpin_->setValue(parts.at(1).toInt());
    });

    QWidget *aspectRow = makeSettingsRow(quickControlsCard, QStringLiteral("Aspect"), aspectPresetCombo);
    QWidget *samplerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Sampler"), samplerCombo_);
    QWidget *schedulerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Scheduler"), schedulerCombo_);
    QWidget *stepsRow = makeSettingsRow(quickControlsCard, QStringLiteral("Steps"), stepsSpin_);
    QWidget *cfgRow = makeSettingsRow(quickControlsCard, QStringLiteral("CFG"), cfgSpin_);
    QWidget *seedRow = makeSettingsRow(quickControlsCard, QStringLiteral("Seed"), seedSpin_);
    QWidget *widthRow = makeSettingsRow(quickControlsCard, QStringLiteral("Width"), widthSpin_);
    QWidget *heightRow = makeSettingsRow(quickControlsCard, QStringLiteral("Height"), heightSpin_);
    QWidget *framesRow = makeSettingsRow(quickControlsCard, QStringLiteral("Frames"), frameCountSpin_);
    QWidget *fpsRow = makeSettingsRow(quickControlsCard, QStringLiteral("FPS"), fpsSpin_);
    framesRow->setVisible(isVideoMode());
    fpsRow->setVisible(isVideoMode());
    QWidget *batchRow = makeSettingsRow(outputQueueCard, QStringLiteral("Batch"), batchSpin_);
    batchRow->setObjectName(QStringLiteral("OutputQueueBodyRow"));

    denoiseRow_ = makeSettingsRow(advancedCard, QStringLiteral("Denoise"), denoiseSpin_);
    denoiseRow_->setObjectName(QStringLiteral("AdvancedBodyRow"));
    denoiseRow_->setVisible(usesStrengthControl());

    samplerSchedulerLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    samplerSchedulerLayout_->setContentsMargins(0, 0, 0, 0);
    samplerSchedulerLayout_->setSpacing(6);
    samplerSchedulerLayout_->addWidget(aspectRow);
    samplerSchedulerLayout_->addWidget(samplerRow);
    samplerSchedulerLayout_->addWidget(schedulerRow);

    stepsCfgLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    stepsCfgLayout_->setContentsMargins(0, 0, 0, 0);
    stepsCfgLayout_->setSpacing(6);
    stepsCfgLayout_->addWidget(stepsRow);
    stepsCfgLayout_->addWidget(cfgRow);

    seedBatchLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    seedBatchLayout_->setContentsMargins(0, 0, 0, 0);
    seedBatchLayout_->setSpacing(6);
    seedBatchLayout_->addWidget(seedRow);
    seedBatchLayout_->addWidget(framesRow);
    seedBatchLayout_->addWidget(fpsRow);

    sizeLayout_ = new QBoxLayout(QBoxLayout::TopToBottom);
    sizeLayout_->setContentsMargins(0, 0, 0, 0);
    sizeLayout_->setSpacing(6);
    sizeLayout_->addWidget(widthRow);
    sizeLayout_->addWidget(heightRow);

    outputPrefixEdit_ = new QLineEdit(outputQueueCard);
    outputPrefixEdit_->setPlaceholderText(QStringLiteral("spellvision_render"));

    outputFolderLabel_ = new QLabel(QDir::toNativeSeparators(chooseComfyOutputPath()), outputQueueCard);
    outputFolderLabel_->setObjectName(QStringLiteral("OutputQueueBodyHint"));
    outputFolderLabel_->setWordWrap(true);

    modelsRootLabel_ = new QLabel(settingsCard_);
    modelsRootLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    modelsRootLabel_->setWordWrap(true);
    modelsRootLabel_->setTextFormat(Qt::RichText);
    modelsRootLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);

    quickControlsLayout->addLayout(samplerSchedulerLayout_);
    quickControlsLayout->addLayout(sizeLayout_);
    quickControlsLayout->addLayout(stepsCfgLayout_);
    quickControlsLayout->addLayout(seedBatchLayout_);

    auto *prefixRow = makeSettingsRow(outputQueueCard, QStringLiteral("Prefix"), outputPrefixEdit_);
    prefixRow->setObjectName(QStringLiteral("OutputQueueBodyRow"));
    auto *outputFolderTitle = new QLabel(QStringLiteral("Output Folder"), outputQueueCard);
    outputFolderTitle->setObjectName(QStringLiteral("OutputQueueBodyLabel"));

    outputQueueLayout->addWidget(batchRow);
    outputQueueLayout->addWidget(prefixRow);
    outputQueueLayout->addWidget(outputFolderTitle);
    outputQueueLayout->addWidget(outputFolderLabel_);

    advancedLayout->addWidget(denoiseRow_);
    if (!usesStrengthControl())
        advancedCard->setVisible(false);

    settingsCardLayout->addWidget(createSectionTitle(QStringLiteral("Asset Intelligence"), settingsCard_));
    auto *assetHint = createSectionBody(QStringLiteral("Live model, LoRA, workflow, and draft readiness."), settingsCard_);
    assetHint->setMaximumHeight(36);
    settingsCardLayout->addWidget(assetHint);
    modelsRootLabel_->setObjectName(QStringLiteral("AssetIntelligenceBody"));
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
    contentSplitter_->setSizes({395, 880, 465});

    root->addWidget(contentSplitter_, 1);

    if (prepLatestForI2IButton_)
        prepLatestForI2IButton_->setVisible(mode_ == Mode::TextToImage);
    if (useLatestT2IButton_)
    {
        useLatestT2IButton_->setVisible(isImageInputMode());
        useLatestT2IButton_->setToolTip(isVideoMode()
                                           ? QStringLiteral("Use the latest generated still image as the I2V keyframe.")
                                           : QStringLiteral("Use the latest generated still image as the I2I source."));
    }

    const auto refreshers = [this]() { scheduleUiRefresh(); };

    connect(promptEdit_, &QTextEdit::textChanged, this, refreshers);
    connect(negativePromptEdit_, &QTextEdit::textChanged, this, refreshers);
    connect(workflowCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(samplerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(schedulerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(stepsSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(cfgSpin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    connect(seedSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(widthSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(heightSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    if (frameCountSpin_)
        connect(frameCountSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    if (fpsSpin_)
        connect(fpsSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(batchSpin_, qOverload<int>(&QSpinBox::valueChanged), this, refreshers);
    connect(outputPrefixEdit_, &QLineEdit::textChanged, this, refreshers);
    if (denoiseSpin_)
        connect(denoiseSpin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    if (inputImageEdit_)
        connect(inputImageEdit_, &QLineEdit::textChanged, this, refreshers);

    connect(workflowCombo_, &QComboBox::currentTextChanged, this, [this]() {
        if (workflowCombo_)
            workflowCombo_->setToolTip(currentComboValue(workflowCombo_));
    });

    refreshSelectedModelUi();
    rebuildLoraStackUi();

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

    updateAssetIntelligenceUi();

    const QStringList modelSubDirs = isVideoMode()
        ? QStringList{QStringLiteral("checkpoints"),
                      QStringLiteral("diffusion_models"),
                      QStringLiteral("unet"),
                      QStringLiteral("video"),
                      QStringLiteral("wan"),
                      QStringLiteral("ltx"),
                      QStringLiteral("hunyuan_video")}
        : QStringList{QStringLiteral("checkpoints")};

    const QVector<CatalogEntry> modelAssets = scanCatalogGroup(modelsRootDir_, modelSubDirs, QStringLiteral("model"));
    modelDisplayByValue_.clear();
    modelModalityByValue_.clear();
    modelFamilyByValue_.clear();
    modelCompatibilityNoteByValue_.clear();
    modelConfidenceByValue_.clear();

    for (const CatalogEntry &entry : modelAssets)
    {
        modelDisplayByValue_.insert(entry.value, entry.display);
        modelModalityByValue_.insert(entry.value, entry.modality);
        modelFamilyByValue_.insert(entry.value, entry.family);
        modelCompatibilityNoteByValue_.insert(entry.value, entry.compatibilityNote);
        modelConfidenceByValue_.insert(entry.value, entry.confidence);
    }

    const bool showIncompatible = showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked();
    const QVector<CatalogEntry> compatibleModels = filterCatalogEntriesForMode(modelDisplayByValue_,
                                                                               modelModalityByValue_,
                                                                               modelFamilyByValue_,
                                                                               modelCompatibilityNoteByValue_,
                                                                               modelConfidenceByValue_,
                                                                               isVideoMode(),
                                                                               showIncompatible);

    const QString priorModel = selectedModelPath_;
    if (!priorModel.trimmed().isEmpty() &&
        modelDisplayByValue_.contains(priorModel) &&
        assetAllowedForMode(modelModalityByValue_.value(priorModel, QStringLiteral("unknown")), isVideoMode(), showIncompatible))
    {
        setSelectedModel(priorModel, resolveSelectedModelDisplay(priorModel));
    }
    else if (!compatibleModels.isEmpty())
    {
        setSelectedModel(compatibleModels.first().value, compatibleModels.first().display);
    }
    else
    {
        setSelectedModel(QString(), QString());
    }

    const QVector<CatalogEntry> loras = scanCatalog(modelsRootDir_, QStringLiteral("loras"), QStringLiteral("lora"));
    loraDisplayByValue_.clear();
    loraModalityByValue_.clear();
    loraFamilyByValue_.clear();
    loraCompatibilityNoteByValue_.clear();
    loraConfidenceByValue_.clear();

    for (const CatalogEntry &entry : loras)
    {
        loraDisplayByValue_.insert(entry.value, entry.display);
        loraModalityByValue_.insert(entry.value, entry.modality);
        loraFamilyByValue_.insert(entry.value, entry.family);
        loraCompatibilityNoteByValue_.insert(entry.value, entry.compatibilityNote);
        loraConfidenceByValue_.insert(entry.value, entry.confidence);
    }

    for (LoraStackEntry &entry : loraStack_)
    {
        if (entry.display.trimmed().isEmpty())
            entry.display = resolveLoraDisplay(entry.value);
    }

    refreshSelectedModelUi();
    rebuildLoraStackUi();

    if (workflowCombo_)
        workflowCombo_->setToolTip(currentComboValue(workflowCombo_));
}

void ImageGenerationPage::applyPreset(const QString &presetName)
{
    if (isVideoMode())
    {
        if (presetName == QStringLiteral("Portrait Detail"))
        {
            promptEdit_->setPlainText(QStringLiteral("cinematic character motion, subtle camera movement, expressive face, clean animation, coherent lighting, detailed environment"));
            negativePromptEdit_->setPlainText(QStringLiteral("flicker, morphing anatomy, broken hands, jitter, low quality, blurry, text, watermark"));
        }
        else if (presetName == QStringLiteral("Stylized Concept"))
        {
            promptEdit_->setPlainText(QStringLiteral("stylized cinematic shot, elegant motion, strong silhouette, clean temporal coherence, dramatic lighting, production concept animation"));
            negativePromptEdit_->setPlainText(QStringLiteral("muddy colors, frame flicker, unstable subject, duplicate limbs, heavy blur, low detail"));
        }
        else if (presetName == QStringLiteral("Upscale / Repair"))
        {
            promptEdit_->setPlainText(QStringLiteral("stabilize motion, restore details, preserve composition, improve temporal consistency, clean edges"));
            negativePromptEdit_->setPlainText(QStringLiteral("new objects, warped anatomy, heavy flicker, jitter, ghosting, blur"));
        }
        else
        {
            promptEdit_->setPlainText(QStringLiteral("cinematic animated scene, clean motion, strong subject read, consistent lighting, high quality video"));
            negativePromptEdit_->setPlainText(QStringLiteral("flicker, jitter, low quality, blurry, text, watermark, warped anatomy"));
        }

        trySetSelectedModelByCandidate({QStringLiteral("wan"), QStringLiteral("ltx"), QStringLiteral("hunyuan"), QStringLiteral("video"), QStringLiteral("sdxl")});
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
        if (stepsSpin_)
            stepsSpin_->setValue(30);
        if (cfgSpin_)
            cfgSpin_->setValue(5.0);
        if (widthSpin_)
            widthSpin_->setValue(832);
        if (heightSpin_)
            heightSpin_->setValue(480);
        if (frameCountSpin_)
            frameCountSpin_->setValue(81);
        if (fpsSpin_)
            fpsSpin_->setValue(16);
        if (denoiseSpin_)
            denoiseSpin_->setValue(0.55);

        schedulePreviewRefresh(0);
        scheduleUiRefresh(0);
        return;
    }
    if (presetName == QStringLiteral("Portrait Detail"))
    {
        promptEdit_->setPlainText(QStringLiteral("portrait of a confident fantasy heroine, detailed face, studio rim lighting, shallow depth of field, high micro-detail"));
        negativePromptEdit_->setPlainText(QStringLiteral("blurry, low quality, extra fingers, malformed hands, watermark, text"));
        trySetSelectedModelByCandidate({QStringLiteral("sdxl"), QStringLiteral("xl")});
        selectComboValue(workflowCombo_, QStringLiteral("Portrait Detail"));
        loraStack_.clear();
        rebuildLoraStackUi();
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
        trySetSelectedModelByCandidate({QStringLiteral("flux"), QStringLiteral("sdxl"), QStringLiteral("xl")});
        selectComboValue(workflowCombo_, QStringLiteral("Stylized Concept"));
        loraStack_.clear();
        rebuildLoraStackUi();
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
        trySetSelectedModelByCandidate({QStringLiteral("juggernaut"), QStringLiteral("sdxl"), QStringLiteral("xl")});
        selectComboValue(workflowCombo_, QStringLiteral("Upscale / Repair"));
        loraStack_.clear();
        rebuildLoraStackUi();
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
        {
            const bool showIncompatible = showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked();
            const QVector<CatalogEntry> compatibleModels = filterCatalogEntriesForMode(modelDisplayByValue_,
                                                                                       modelModalityByValue_,
                                                                                       modelFamilyByValue_,
                                                                                       modelCompatibilityNoteByValue_,
                                                                                       modelConfidenceByValue_,
                                                                                       isVideoMode(),
                                                                                       showIncompatible);
            if (!compatibleModels.isEmpty())
                setSelectedModel(compatibleModels.first().value, compatibleModels.first().display);
        }
        selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));
        loraStack_.clear();
        rebuildLoraStackUi();
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

void ImageGenerationPage::updatePreviewEmptyStateSizing()
{
    if (!previewLabel_)
        return;

    const bool hasRenderedPreview = !generatedPreviewPath_.trimmed().isEmpty() && QFileInfo::exists(generatedPreviewPath_.trimmed());
    const bool hasInputPreview = isImageInputMode() && inputImageEdit_ && !inputImageEdit_->text().trimmed().isEmpty();
    const bool emptyState = !busy_ && !hasRenderedPreview && !hasInputPreview;

    if (previewLabel_->property("emptyState").toBool() != emptyState)
        previewLabel_->setProperty("emptyState", emptyState);

    if (emptyState)
    {
        const AdaptiveLayoutMode mode = currentAdaptiveLayoutMode();
        // Empty/readiness states should still feel like the main preview surface.
        // Keep the instructional copy, but do not cap the preview label into a small
        // floating island inside the canvas card. The preview surface owns the
        // available center canvas whether it is empty, waiting for a checkpoint,
        // or showing a generated result.
        previewLabel_->setMinimumHeight(mode == AdaptiveLayoutMode::Compact ? 340 : 420);
        previewLabel_->setMaximumHeight(QWIDGETSIZE_MAX);
    }
    else
    {
        previewLabel_->setMinimumHeight(0);
        previewLabel_->setMaximumHeight(QWIDGETSIZE_MAX);
    }

    repolishWidget(previewLabel_);
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

        if (previewLabel_->property("emptyState").toBool())
        {
            previewLabel_->setProperty("emptyState", false);
            repolishWidget(previewLabel_);
        }
        previewLabel_->setText(QString());
        previewLabel_->setPixmap(pixmap.scaled(target, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    };

    if (!generatedPreviewPath_.trimmed().isEmpty() && QFileInfo::exists(generatedPreviewPath_))
    {
        if (isVideoAssetPath(generatedPreviewPath_) && !isImageAssetPath(generatedPreviewPath_))
        {
            previewLabel_->setPixmap(QPixmap());
            cachedPreviewSourcePath_.clear();
            cachedPreviewPixmap_ = QPixmap();
            lastRenderedPreviewFingerprint_ = QStringLiteral("video:%1:%2").arg(generatedPreviewPath_, generatedPreviewCaption_);
            if (previewLabel_->property("emptyState").toBool())
            {
                previewLabel_->setProperty("emptyState", false);
                repolishWidget(previewLabel_);
            }

            const QFileInfo info(generatedPreviewPath_);
            const QString summary = generatedPreviewCaption_.trimmed().isEmpty()
                                        ? QStringLiteral("Video output ready.\n\n%1").arg(info.fileName())
                                        : QStringLiteral("%1\n\n%2").arg(generatedPreviewCaption_.trimmed(), info.fileName());
            previewLabel_->setText(summary);
            return;
        }

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

    updatePreviewEmptyStateSizing();

    if (previewLabel_->property("emptyState").toBool())
    {
        const QString reason = readinessBlockReason();
        previewLabel_->setText(
            isImageInputMode()
                ? QStringLiteral("No source image loaded yet.\n\nDrop or browse an input image from the left rail.")
                : (reason.isEmpty()
                       ? QStringLiteral("Canvas ready.\n\nGenerate or queue from the focused canvas when your prompt is set.")
                       : QStringLiteral("Ready for setup.\n\n%1").arg(reason)));
        return;
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
    inputDropLabel_->setText(path.isEmpty()
                                 ? (isVideoMode() ? QStringLiteral("Drop a keyframe here or click Browse to select one.")
                                                  : QStringLiteral("Drop an image here or click Browse to select a source image."))
                                 : QStringLiteral("Current source image:\n%1").arg(path));
    updatePrimaryActionAvailability();
    updatePreviewEmptyStateSizing();
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

    updatePrimaryActionAvailability();
    updatePreviewEmptyStateSizing();
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
    const bool compactRail = (mode == AdaptiveLayoutMode::Compact) || railWidth < 380;
    const bool verticalActions = compactRail || railWidth < 430;

    if (stackToolsLayout_)
    {
        stackToolsLayout_->setDirection(verticalActions ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
        stackToolsLayout_->setSpacing(verticalActions ? 6 : 8);
    }

    const int buttonHeight = verticalActions ? 38 : 36;
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
            contentSplitter_->setSizes({345, 690, 390});
        else
            contentSplitter_->setSizes({360, 900, 0});
        return;
    }

    if (mode == AdaptiveLayoutMode::Medium)
    {
        contentSplitter_->setSizes({385, 760, 425});
        return;
    }

    contentSplitter_->setSizes({395, 850, 465});
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
        QTimer::singleShot(0, this, [this]() {
            if (leftScrollArea_ && leftScrollArea_->verticalScrollBar())
                leftScrollArea_->verticalScrollBar()->setValue(0);
        });
    }

    if (leftScrollArea_)
    {
        if (mode == AdaptiveLayoutMode::Compact)
        {
            leftScrollArea_->setMinimumWidth(330);
            leftScrollArea_->setMaximumWidth(390);
        }
        else if (mode == AdaptiveLayoutMode::Medium)
        {
            leftScrollArea_->setMinimumWidth(360);
            leftScrollArea_->setMaximumWidth(420);
        }
        else
        {
            leftScrollArea_->setMinimumWidth(380);
            leftScrollArea_->setMaximumWidth(440);
        }
    }

    const bool showRightControls = (mode != AdaptiveLayoutMode::Compact) || rightControlsVisible_;
    setRightControlsVisible(showRightControls);

    if (rightScrollArea_)
    {
        if (mode == AdaptiveLayoutMode::Compact)
        {
            rightScrollArea_->setMinimumWidth(360);
            rightScrollArea_->setMaximumWidth(440);
        }
        else if (mode == AdaptiveLayoutMode::Medium)
        {
            rightScrollArea_->setMinimumWidth(390);
            rightScrollArea_->setMaximumWidth(470);
        }
        else
        {
            rightScrollArea_->setMinimumWidth(410);
            rightScrollArea_->setMaximumWidth(500);
        }
    }

    applyRightPanelReflow(mode);

    const int leftRailWidth = leftScrollArea_ ? leftScrollArea_->viewport()->width() : 0;
    const int leftRailHeight = leftScrollArea_ ? leftScrollArea_->viewport()->height() : height();
    const bool narrowLeftRail = (mode == AdaptiveLayoutMode::Compact) || leftRailWidth < 390;
    const bool wideLeftRail = (mode == AdaptiveLayoutMode::Wide) && leftRailWidth >= 410;
    const bool constrainedLeftHeight = leftRailHeight > 0 && leftRailHeight < 900;
    const bool veryConstrainedLeftHeight = leftRailHeight > 0 && leftRailHeight < 780;
    const bool shortGenerationRail = leftRailHeight > 0 && leftRailHeight < 960;
    Q_UNUSED(veryConstrainedLeftHeight);
    Q_UNUSED(shortGenerationRail);

    auto configureStackedGroup = [narrowLeftRail](QBoxLayout *layout) {
        if (!layout)
            return;
        layout->setDirection(QBoxLayout::TopToBottom);
        layout->setSpacing(narrowLeftRail ? 3 : 4);
    };
    auto configureAdaptivePair = [wideLeftRail, constrainedLeftHeight](QBoxLayout *layout) {
        if (!layout)
            return;
        const bool useTwoColumns = wideLeftRail && !constrainedLeftHeight;
        layout->setDirection(useTwoColumns ? QBoxLayout::LeftToRight : QBoxLayout::TopToBottom);
        layout->setSpacing(useTwoColumns ? 8 : 3);
    };

    configureStackedGroup(samplerSchedulerLayout_);
    configureAdaptivePair(sizeLayout_);
    configureAdaptivePair(stepsCfgLayout_);
    configureStackedGroup(seedBatchLayout_);

    if (QFrame *quickControlsCard = findChild<QFrame *>(QStringLiteral("QuickControlsCard")))
        quickControlsCard->setToolTip(QStringLiteral("High-frequency generation controls stay prioritized in the left inspector."));

    if (QFrame *outputQueueCard = findChild<QFrame *>(QStringLiteral("OutputQueueCard")))
    {
        const bool outputAutoCollapsed = true;
        const bool collapseOutput = outputAutoCollapsed && !outputQueueForceOpen_;
        outputQueueCard->setMaximumHeight(collapseOutput ? 58 : QWIDGETSIZE_MAX);
        outputQueueCard->setToolTip(collapseOutput
            ? QStringLiteral("Output / Queue is collapsed to protect prompt space. Click Open to edit batch, prefix, and output folder.")
            : QString());

        const auto bodyRows = outputQueueCard->findChildren<QWidget *>(QStringLiteral("OutputQueueBodyRow"));
        for (QWidget *body : bodyRows)
            body->setVisible(!collapseOutput);

        if (QWidget *label = outputQueueCard->findChild<QWidget *>(QStringLiteral("OutputQueueBodyLabel")))
            label->setVisible(!collapseOutput);
        if (QWidget *hint = outputQueueCard->findChild<QWidget *>(QStringLiteral("OutputQueueBodyHint")))
            hint->setVisible(!collapseOutput);

        if (outputQueueToggleButton_)
        {
            outputQueueToggleButton_->setVisible(true);
            outputQueueToggleButton_->setMinimumWidth(collapseOutput ? 72 : 74);
            outputQueueToggleButton_->setText(collapseOutput ? QStringLiteral("Open") : QStringLiteral("Close"));
            outputQueueToggleButton_->setToolTip(collapseOutput
                ? QStringLiteral("Open Output / Queue controls.")
                : QStringLiteral("Close Output / Queue controls and return space to the rail."));
        }
    }

    if (QFrame *advancedCard = findChild<QFrame *>(QStringLiteral("AdvancedCard")))
    {
        const bool advancedAutoCollapsed = true;
        const bool collapseAdvanced = advancedAutoCollapsed && !advancedForceOpen_;
        advancedCard->setMaximumHeight(collapseAdvanced ? 58 : QWIDGETSIZE_MAX);
        advancedCard->setToolTip(collapseAdvanced
            ? QStringLiteral("Advanced controls are collapsed by default to protect prompt space. Click Open to edit mode-specific controls.")
            : QString());

        const auto bodyRows = advancedCard->findChildren<QWidget *>(QStringLiteral("AdvancedBodyRow"));
        for (QWidget *body : bodyRows)
            body->setVisible(!collapseAdvanced);
        if (QWidget *hint = advancedCard->findChild<QWidget *>(QStringLiteral("AdvancedBodyHint")))
            hint->setVisible(!collapseAdvanced);

        if (advancedToggleButton_)
        {
            advancedToggleButton_->setVisible(advancedCard->isVisible());
            advancedToggleButton_->setMinimumWidth(collapseAdvanced ? 72 : 74);
            advancedToggleButton_->setText(collapseAdvanced ? QStringLiteral("Open") : QStringLiteral("Close"));
            advancedToggleButton_->setToolTip(collapseAdvanced
                ? QStringLiteral("Open Advanced controls.")
                : QStringLiteral("Close Advanced controls and return space to the rail."));
        }
    }

    if (toggleControlsButton_)
    {
        toggleControlsButton_->setVisible(mode == AdaptiveLayoutMode::Compact);
        toggleControlsButton_->setText(showRightControls ? QStringLiteral("Hide Controls")
                                                         : QStringLiteral("Show Controls"));
    }

    if (promptEdit_)
    {
        const bool shortRail = leftRailHeight > 0 && leftRailHeight < 760;
        const int promptMin = shortRail ? (isVideoMode() ? 110 : 128)
                                        : (mode == AdaptiveLayoutMode::Wide ? (isVideoMode() ? 132 : 156)
                                                                           : (isVideoMode() ? 118 : 140));
        promptEdit_->setMinimumHeight(promptMin);
        promptEdit_->setMaximumHeight(promptMin + 18);
    }
    if (negativePromptEdit_)
    {
        const bool shortRail = leftRailHeight > 0 && leftRailHeight < 760;
        const int negativeMin = shortRail ? 68 : (mode == AdaptiveLayoutMode::Wide ? 84 : 76);
        negativePromptEdit_->setMinimumHeight(negativeMin);
        negativePromptEdit_->setMaximumHeight(negativeMin + 16);
    }

    updatePreviewEmptyStateSizing();
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
    workflowDraftSource_.clear();
    workflowDraftWarnings_.clear();
    workflowDraftBlocking_ = false;
    updateDraftCompatibilityUi();
    updatePrimaryActionAvailability();

    scheduleUiRefresh(0);
    schedulePreviewRefresh(0);
}


QString ImageGenerationPage::selectedModelValue() const
{
    return selectedModelPath_.trimmed();
}

QString ImageGenerationPage::selectedLoraValue() const
{
    return resolveLoraValue();
}

bool ImageGenerationPage::workflowDraftCanSubmit() const
{
    return !workflowDraftBlocking_;
}

void ImageGenerationPage::applyWorkflowDraft(const QJsonObject &draft)
{
    workflowDraftSource_ = draft.value(QStringLiteral("source_name")).toString().trimmed();
    workflowDraftProfilePath_ = draft.value(QStringLiteral("source_profile_path")).toString().trimmed();
    workflowDraftWorkflowPath_ = draft.value(QStringLiteral("source_workflow_path")).toString().trimmed();
    workflowDraftCompiledPromptPath_ = draft.value(QStringLiteral("compiled_prompt_path")).toString().trimmed();
    workflowDraftBackend_ = draft.value(QStringLiteral("backend")).toString().trimmed();
    workflowDraftMediaType_ = draft.value(QStringLiteral("media_type")).toString().trimmed();
    workflowDraftWarnings_.clear();
    workflowDraftBlocking_ = false;

    if (promptEdit_)
        promptEdit_->setPlainText(draft.value(QStringLiteral("prompt")).toString());
    if (negativePromptEdit_)
        negativePromptEdit_->setPlainText(draft.value(QStringLiteral("negative_prompt")).toString());

    if (presetCombo_)
        selectComboValue(presetCombo_, QStringLiteral("Custom"));

    const QString checkpoint = draft.value(QStringLiteral("checkpoint")).toString().trimmed();
    const QString checkpointDisplay = draft.value(QStringLiteral("checkpoint_display")).toString().trimmed();
    bool checkpointMatched = checkpoint.isEmpty();
    if (!checkpoint.isEmpty())
        checkpointMatched = trySetSelectedModelByCandidate({checkpoint, checkpointDisplay, shortDisplayFromValue(checkpoint)});

    const QString sampler = draft.value(QStringLiteral("sampler")).toString().trimmed();
    if (!sampler.isEmpty())
    {
        if (!selectComboValue(samplerCombo_, sampler))
            selectComboByContains(samplerCombo_, {sampler});
    }

    const QString scheduler = draft.value(QStringLiteral("scheduler")).toString().trimmed();
    if (!scheduler.isEmpty())
    {
        if (!selectComboValue(schedulerCombo_, scheduler))
            selectComboByContains(schedulerCombo_, {scheduler});
    }

    const int steps = draft.value(QStringLiteral("steps")).toInt(0);
    if (steps > 0 && stepsSpin_)
        stepsSpin_->setValue(steps);

    const double cfg = draft.value(QStringLiteral("cfg")).toDouble(0.0);
    if (cfg > 0.0 && cfgSpin_)
        cfgSpin_->setValue(cfg);

    const qlonglong seed = draft.value(QStringLiteral("seed")).toVariant().toLongLong();
    if (seed > 0 && seedSpin_)
        seedSpin_->setValue(static_cast<int>(qMin<qlonglong>(seed, 999999999LL)));

    const int width = draft.value(QStringLiteral("width")).toInt(0);
    if (width > 0 && widthSpin_)
        widthSpin_->setValue(width);

    const int height = draft.value(QStringLiteral("height")).toInt(0);
    if (height > 0 && heightSpin_)
        heightSpin_->setValue(height);

    const int frames = draft.value(QStringLiteral("frames")).toInt(draft.value(QStringLiteral("num_frames")).toInt(0));
    if (frames > 0 && frameCountSpin_)
        frameCountSpin_->setValue(frames);

    const int fps = draft.value(QStringLiteral("fps")).toInt(0);
    if (fps > 0 && fpsSpin_)
        fpsSpin_->setValue(fps);

    if (isImageInputMode())
    {
        const QString inputImage = draft.value(QStringLiteral("input_image")).toString().trimmed();
        if (!inputImage.isEmpty())
            setInputImagePath(inputImage);
    }

    loraStack_.clear();
    const QJsonArray loraStack = draft.value(QStringLiteral("lora_stack")).toArray();
    int matchedLoras = 0;
    for (const QJsonValue &value : loraStack)
    {
        if (!value.isObject())
            continue;
        const QJsonObject obj = value.toObject();
        const QString loraName = obj.value(QStringLiteral("name")).toString().trimmed();
        const QString loraDisplay = obj.value(QStringLiteral("display")).toString().trimmed();
        const double loraStrength = obj.value(QStringLiteral("strength")).toDouble(1.0);
        const bool enabled = obj.value(QStringLiteral("enabled")).toBool(true);
        if (tryAddLoraByCandidate({loraName, loraDisplay, shortDisplayFromValue(loraName)}, loraStrength, enabled))
            ++matchedLoras;
        else if (!loraName.isEmpty())
            workflowDraftWarnings_.push_back(QStringLiteral("Imported LoRA could not be matched in the current LoRA catalog: %1").arg(loraName));
    }

    const bool videoWorkflowDraft = isVideoMode() &&
                                    (!workflowDraftProfilePath_.trimmed().isEmpty() ||
                                     !workflowDraftWorkflowPath_.trimmed().isEmpty() ||
                                     !workflowDraftCompiledPromptPath_.trimmed().isEmpty() ||
                                     workflowDraftMediaType_.compare(QStringLiteral("video"), Qt::CaseInsensitive) == 0);

    if (!checkpointMatched)
    {
        if (!videoWorkflowDraft)
            workflowDraftBlocking_ = true;
        workflowDraftWarnings_.push_back(QStringLiteral("Imported checkpoint could not be matched in the current model catalog: %1").arg(checkpoint));
    }

    if (matchedLoras == 0 && !loraStack.isEmpty() && !videoWorkflowDraft)
        workflowDraftBlocking_ = true;

    const bool safeToSubmit = draft.value(QStringLiteral("safe_to_submit")).toBool(true);
    const QJsonArray draftWarnings = draft.value(QStringLiteral("warnings")).toArray();
    for (const QJsonValue &warning : draftWarnings)
    {
        const QString text = warning.toString().trimmed();
        if (!text.isEmpty())
            workflowDraftWarnings_.push_back(text);
    }
    if (!safeToSubmit)
        workflowDraftBlocking_ = true;

    rebuildLoraStackUi();
    updateDraftCompatibilityUi();
    updatePrimaryActionAvailability();
    scheduleUiRefresh(0);
    schedulePreviewRefresh(0);
}

void ImageGenerationPage::updateAssetIntelligenceUi()
{
    if (!modelsRootLabel_)
        return;

    const QString modelDisplay = selectedModelPath_.trimmed().isEmpty()
        ? QStringLiteral("none selected")
        : (selectedModelDisplay_.trimmed().isEmpty() ? shortDisplayFromValue(selectedModelPath_) : selectedModelDisplay_.trimmed());

    const QString modelModality = selectedModelPath_.trimmed().isEmpty()
        ? (isVideoMode() ? QStringLiteral("video mode") : QStringLiteral("image mode"))
        : modelModalityByValue_.value(selectedModelPath_, QStringLiteral("unknown"));
    const QString modelFamily = selectedModelPath_.trimmed().isEmpty()
        ? QStringLiteral("none")
        : modelFamilyByValue_.value(selectedModelPath_, QStringLiteral("Unknown family"));
    const QString modelCompatibility = selectedModelPath_.trimmed().isEmpty()
        ? assetModeFilterLabel(isVideoMode(), showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked())
        : modelCompatibilityNoteByValue_.value(selectedModelPath_, QStringLiteral("No compatibility note available."));
    const int modelConfidence = selectedModelPath_.trimmed().isEmpty()
        ? 0
        : modelConfidenceByValue_.value(selectedModelPath_, 0);

    int enabledLoras = 0;
    for (const LoraStackEntry &entry : loraStack_)
    {
        if (entry.enabled)
            ++enabledLoras;
    }

    const QString workflowName = workflowCombo_ ? currentComboValue(workflowCombo_) : QStringLiteral("Default Canvas");
    const QString draftState = workflowDraftSource_.trimmed().isEmpty()
        ? QStringLiteral("none")
        : (workflowDraftBlocking_ ? QStringLiteral("review required") : QStringLiteral("ready"));
    const QString warningState = workflowDraftWarnings_.isEmpty()
        ? QStringLiteral("none")
        : QStringLiteral("%1 review note%2").arg(workflowDraftWarnings_.size()).arg(workflowDraftWarnings_.size() == 1 ? QString() : QStringLiteral("s"));
    const QString rootText = modelsRootDir_.trimmed().isEmpty()
        ? QStringLiteral("not configured")
        : QDir::toNativeSeparators(modelsRootDir_);
    const QString blockReason = readinessBlockReason();
    const bool ready = blockReason.isEmpty();
    const QString readiness = ready ? QStringLiteral("ready") : blockReason;

    auto row = [ready](const QString &label, const QString &value, bool readinessRow = false) {
        const QString valueClass = readinessRow ? (ready ? QStringLiteral("v good") : QStringLiteral("v bad")) : QStringLiteral("v");
        return QStringLiteral("<tr><td class='k'>%1</td><td class='%2'>%3</td></tr>")
            .arg(label.toHtmlEscaped(), valueClass, value.toHtmlEscaped());
    };

    QString html;
    html += QStringLiteral("<style>"
                           "table{border-collapse:collapse;width:100%;}"
                           "td{padding:2px 0;vertical-align:top;}"
                           ".k{opacity:.74;font-weight:800;white-space:nowrap;padding-right:12px;}"
                           ".v{font-weight:650;}"
                           ".good{color:#9ff5ca;}"
                           ".bad{color:#ffd1dc;}"
                           "</style>");
    html += QStringLiteral("<table>");
    html += row(isVideoMode() ? QStringLiteral("Video Asset") : QStringLiteral("Checkpoint"), modelDisplay);
    html += row(QStringLiteral("Modality"), modelModality);
    html += row(QStringLiteral("Family"), modelFamily);
    html += row(QStringLiteral("Filter"), assetModeFilterLabel(isVideoMode(), showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked()));
    if (modelConfidence > 0)
        html += row(QStringLiteral("Confidence"), QStringLiteral("%1%").arg(modelConfidence));
    html += row(QStringLiteral("Compatibility"), modelCompatibility);
    html += row(QStringLiteral("LoRAs"), QStringLiteral("%1 stack / %2 enabled").arg(loraStack_.size()).arg(enabledLoras));
    html += row(QStringLiteral("Workflow"), workflowName.trimmed().isEmpty() ? QStringLiteral("Default Canvas") : workflowName);
    if (isVideoMode())
    {
        const int frames = frameCountSpin_ ? frameCountSpin_->value() : 0;
        const int fps = fpsSpin_ ? fpsSpin_->value() : 0;
        const double seconds = fps > 0 ? static_cast<double>(frames) / static_cast<double>(fps) : 0.0;
        html += row(QStringLiteral("Timing"), QStringLiteral("%1 frames @ %2 fps (%3s)").arg(frames).arg(fps).arg(QString::number(seconds, 'f', 1)));
    }
    html += row(QStringLiteral("Draft"), draftState);
    html += row(QStringLiteral("Review"), warningState);
    html += row(QStringLiteral("Readiness"), readiness, true);
    html += row(QStringLiteral("Assets"), rootText);
    html += QStringLiteral("</table>");

    QStringList plain;
    plain << QStringLiteral("%1: %2").arg(isVideoMode() ? QStringLiteral("Video Asset") : QStringLiteral("Checkpoint"), modelDisplay);
    plain << QStringLiteral("Modality: %1").arg(modelModality);
    plain << QStringLiteral("Family: %1").arg(modelFamily);
    plain << QStringLiteral("Filter: %1").arg(assetModeFilterLabel(isVideoMode(), showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked()));
    if (modelConfidence > 0)
        plain << QStringLiteral("Confidence: %1%").arg(modelConfidence);
    plain << QStringLiteral("Compatibility: %1").arg(modelCompatibility);
    plain << QStringLiteral("LoRAs: %1 in stack / %2 enabled").arg(loraStack_.size()).arg(enabledLoras);
    plain << QStringLiteral("Workflow: %1").arg(workflowName.trimmed().isEmpty() ? QStringLiteral("Default Canvas") : workflowName);
    if (isVideoMode())
    {
        const int frames = frameCountSpin_ ? frameCountSpin_->value() : 0;
        const int fps = fpsSpin_ ? fpsSpin_->value() : 0;
        const double seconds = fps > 0 ? static_cast<double>(frames) / static_cast<double>(fps) : 0.0;
        plain << QStringLiteral("Timing: %1 frames @ %2 fps (%3s)").arg(frames).arg(fps).arg(QString::number(seconds, 'f', 1));
    }
    plain << QStringLiteral("Draft: %1").arg(draftState);
    plain << QStringLiteral("Review: %1").arg(warningState);
    plain << QStringLiteral("Readiness: %1").arg(readiness);
    plain << QStringLiteral("Assets: %1").arg(rootText);

    modelsRootLabel_->setText(html);
    modelsRootLabel_->setToolTip(plain.join(QStringLiteral("\n")));
}

void ImageGenerationPage::updateDraftCompatibilityUi()
{
    QStringList lines;
    if (!workflowDraftSource_.isEmpty())
        lines << QStringLiteral("Loaded from workflow: %1").arg(workflowDraftSource_);
    for (const QString &warning : workflowDraftWarnings_)
    {
        if (!warning.trimmed().isEmpty())
            lines << warning.trimmed();
    }
    const QString tooltip = lines.join(QStringLiteral("\n"));

    if (!tooltip.isEmpty())
    {
        if (generateButton_)
            generateButton_->setToolTip(tooltip);
        if (queueButton_)
            queueButton_->setToolTip(tooltip);
        if (openWorkflowsButton_)
            openWorkflowsButton_->setToolTip(tooltip);
    }

    updateAssetIntelligenceUi();
}

bool ImageGenerationPage::hasReadyModelSelection() const
{
    if (isVideoMode() && hasVideoWorkflowBinding())
        return true;

    return !selectedModelValue().trimmed().isEmpty();
}

bool ImageGenerationPage::hasRequiredGenerationInput() const
{
    if (!isImageInputMode())
        return true;

    return inputImageEdit_ && !inputImageEdit_->text().trimmed().isEmpty();
}

bool ImageGenerationPage::hasVideoWorkflowBinding() const
{
    if (!isVideoMode())
        return true;

    if (!workflowDraftProfilePath_.trimmed().isEmpty())
        return true;
    if (!workflowDraftWorkflowPath_.trimmed().isEmpty())
        return true;
    if (!workflowDraftCompiledPromptPath_.trimmed().isEmpty())
        return true;

    return false;
}

QString ImageGenerationPage::readinessBlockReason() const
{
    if (busy_)
        return busyMessage_.isEmpty() ? QStringLiteral("Generation in progress.") : busyMessage_;

    if (isVideoMode() && !hasVideoWorkflowBinding())
        return QStringLiteral("Open a video workflow draft from Workflows before generating.");

    if (!hasReadyModelSelection())
        return QStringLiteral("Select a checkpoint to generate.");

    if (!hasRequiredGenerationInput())
        return isVideoMode()
                   ? QStringLiteral("Add an input keyframe to generate.")
                   : QStringLiteral("Add an input image to generate.");

    if (workflowDraftBlocking_)
        return QStringLiteral("Resolve workflow draft review items.");

    return QString();
}

void ImageGenerationPage::applyActionReadinessStyle(QPushButton *button, bool enabled, const QString &tooltip)
{
    if (!button)
        return;

    const bool blocked = !enabled;
    if (button->property("readinessBlocked").toBool() != blocked)
        button->setProperty("readinessBlocked", blocked);

    button->setEnabled(enabled);
    button->setToolTip(tooltip);
    repolishWidget(button);
}

void ImageGenerationPage::updatePrimaryActionAvailability()
{
    const QString blockReason = readinessBlockReason();
    const bool enabled = blockReason.isEmpty();

    applyActionReadinessStyle(generateButton_, enabled,
                              enabled ? QStringLiteral("Generate with the current prompt and model stack.")
                                      : blockReason);
    applyActionReadinessStyle(queueButton_, enabled,
                              enabled ? QStringLiteral("Add this job to the queue.")
                                      : blockReason);

    if (readinessHintLabel_)
    {
        readinessHintLabel_->setText(enabled ? QString() : blockReason);
        readinessHintLabel_->setToolTip(enabled ? QString() : blockReason);
        readinessHintLabel_->setVisible(!enabled && !blockReason.trimmed().isEmpty());
    }

    updateAssetIntelligenceUi();
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

    {
        const bool showIncompatible = showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked();
        const QVector<CatalogEntry> compatibleModels = filterCatalogEntriesForMode(modelDisplayByValue_,
                                                                                   modelModalityByValue_,
                                                                                   modelFamilyByValue_,
                                                                                   modelCompatibilityNoteByValue_,
                                                                                   modelConfidenceByValue_,
                                                                                   isVideoMode(),
                                                                                   showIncompatible);
        if (!compatibleModels.isEmpty())
            setSelectedModel(compatibleModels.first().value, compatibleModels.first().display);
        else
            setSelectedModel(QString(), QString());
    }

    if (workflowCombo_)
        selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));
    loraStack_.clear();
    rebuildLoraStackUi();
    if (samplerCombo_)
        selectComboValue(samplerCombo_, QStringLiteral("dpmpp_2m"));
    if (schedulerCombo_)
        selectComboValue(schedulerCombo_, QStringLiteral("karras"));
    if (stepsSpin_)
        stepsSpin_->setValue(isVideoMode() ? 30 : 28);
    if (cfgSpin_)
        cfgSpin_->setValue(isVideoMode() ? 5.0 : 7.0);
    if (seedSpin_)
        seedSpin_->setValue(0);
    if (widthSpin_)
        widthSpin_->setValue(isVideoMode() ? 832 : 1024);
    if (heightSpin_)
        heightSpin_->setValue(isVideoMode() ? 480 : 1024);
    if (frameCountSpin_)
        frameCountSpin_->setValue(81);
    if (fpsSpin_)
        fpsSpin_->setValue(16);
    if (batchSpin_)
        batchSpin_->setValue(1);
    if (denoiseSpin_)
        denoiseSpin_->setValue(0.45);
    if (outputPrefixEdit_)
        outputPrefixEdit_->clear();

    workflowDraftSource_.clear();
    workflowDraftProfilePath_.clear();
    workflowDraftWorkflowPath_.clear();
    workflowDraftCompiledPromptPath_.clear();
    workflowDraftBackend_.clear();
    workflowDraftMediaType_.clear();
    workflowDraftWarnings_.clear();
    workflowDraftBlocking_ = false;

    generatedPreviewPath_.clear();
    generatedPreviewCaption_.clear();
    busy_ = false;
    busyMessage_.clear();

    setInputImagePath(QString());

    updatePrimaryActionAvailability();
    if (savePresetButton_)
        savePresetButton_->setEnabled(true);
    if (clearButton_)
        clearButton_->setEnabled(true);

    updateAssetIntelligenceUi();
    schedulePreviewRefresh(0);
}

void ImageGenerationPage::saveSnapshot()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QString group = QStringLiteral("ImageGenerationPage/%1").arg(modeKey());

    settings.beginGroup(group);
    settings.setValue(QStringLiteral("preset"), currentComboValue(presetCombo_));
    settings.setValue(QStringLiteral("prompt"), promptEdit_ ? promptEdit_->toPlainText() : QString());
    settings.setValue(QStringLiteral("negativePrompt"), negativePromptEdit_ ? negativePromptEdit_->toPlainText() : QString());
    settings.setValue(QStringLiteral("inputImage"), inputImageEdit_ ? inputImageEdit_->text() : QString());
    settings.setValue(QStringLiteral("model"), selectedModelValue());
    settings.setValue(QStringLiteral("modelDisplay"), selectedModelDisplay_);
    settings.setValue(QStringLiteral("workflow"), currentComboValue(workflowCombo_));
    settings.setValue(QStringLiteral("loraStackJson"), serializeLoraStack(loraStack_));
    settings.setValue(QStringLiteral("sampler"), currentComboValue(samplerCombo_));
    settings.setValue(QStringLiteral("scheduler"), currentComboValue(schedulerCombo_));
    settings.setValue(QStringLiteral("steps"), stepsSpin_ ? stepsSpin_->value() : 28);
    settings.setValue(QStringLiteral("cfg"), cfgSpin_ ? cfgSpin_->value() : 7.0);
    settings.setValue(QStringLiteral("seed"), seedSpin_ ? seedSpin_->value() : 0);
    settings.setValue(QStringLiteral("width"), widthSpin_ ? widthSpin_->value() : 1024);
    settings.setValue(QStringLiteral("height"), heightSpin_ ? heightSpin_->value() : 1024);
    settings.setValue(QStringLiteral("frames"), frameCountSpin_ ? frameCountSpin_->value() : 81);
    settings.setValue(QStringLiteral("fps"), fpsSpin_ ? fpsSpin_->value() : 16);
    settings.setValue(QStringLiteral("batch"), batchSpin_ ? batchSpin_->value() : 1);
    settings.setValue(QStringLiteral("denoise"), denoiseSpin_ ? denoiseSpin_->value() : 0.45);
    settings.setValue(QStringLiteral("outputPrefix"), outputPrefixEdit_ ? outputPrefixEdit_->text() : QString());
    settings.endGroup();
    settings.sync();

    QString sourcePath = generatedPreviewPath_.trimmed();
    if (sourcePath.isEmpty() && isImageInputMode() && inputImageEdit_)
        sourcePath = inputImageEdit_->text().trimmed();

    if (sourcePath.isEmpty() || !QFileInfo::exists(sourcePath))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Save Snapshot"),
                                 QStringLiteral("Generation settings were saved. No rendered output is available to copy yet."));
        return;
    }

    QFileInfo sourceInfo(sourcePath);
    QString extension = sourceInfo.suffix().trimmed().toLower();
    const QStringList supportedSnapshotExtensions = {QStringLiteral("png"),
                                                     QStringLiteral("jpg"),
                                                     QStringLiteral("jpeg"),
                                                     QStringLiteral("webp"),
                                                     QStringLiteral("bmp"),
                                                     QStringLiteral("gif"),
                                                     QStringLiteral("mp4"),
                                                     QStringLiteral("webm"),
                                                     QStringLiteral("mov"),
                                                     QStringLiteral("mkv")};
    if (!supportedSnapshotExtensions.contains(extension))
        extension = isVideoMode() ? QStringLiteral("mp4") : QStringLiteral("png");

    QString picturesRoot = QStandardPaths::writableLocation(QStandardPaths::PicturesLocation);
    if (picturesRoot.trimmed().isEmpty())
        picturesRoot = QDir::homePath();

    QDir snapshotDir(QDir(picturesRoot).filePath(QStringLiteral("SpellVision/Snapshots")));
    snapshotDir.mkpath(QStringLiteral("."));

    const QString defaultName = QStringLiteral("%1_snapshot_%2.%3")
                                    .arg(modeKey(),
                                         QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd_HHmmss")),
                                         extension);
    QString savePath = QFileDialog::getSaveFileName(this,
                                                    QStringLiteral("Save SpellVision Snapshot"),
                                                    snapshotDir.filePath(defaultName),
                                                    isVideoMode()
                                                        ? QStringLiteral("Video / Animated Outputs (*.mp4 *.webm *.mov *.mkv *.gif);;All Files (*)")
                                                        : QStringLiteral("Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All Files (*)"));
    if (savePath.trimmed().isEmpty())
        return;

    if (QFileInfo(savePath).suffix().trimmed().isEmpty())
        savePath += QStringLiteral(".") + extension;

    QFileInfo targetInfo(savePath);
    const QString canonicalSource = sourceInfo.canonicalFilePath();
    const QString canonicalTarget = targetInfo.exists() ? targetInfo.canonicalFilePath() : targetInfo.absoluteFilePath();
    if (!canonicalSource.isEmpty() && canonicalSource == canonicalTarget)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Save Snapshot"),
                                 QStringLiteral("Snapshot already exists at this location."));
        return;
    }

    if (QFileInfo::exists(savePath) && !QFile::remove(savePath))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Save Snapshot"),
                             QStringLiteral("Could not replace the existing file:\n%1").arg(savePath));
        return;
    }

    bool saved = QFile::copy(sourcePath, savePath);
    if (!saved && !cachedPreviewPixmap_.isNull())
        saved = cachedPreviewPixmap_.save(savePath);

    if (!saved)
    {
        QMessageBox::warning(this,
                             QStringLiteral("Save Snapshot"),
                             QStringLiteral("Could not save the snapshot:\n%1").arg(savePath));
        return;
    }

    QSettings workspaceSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    workspaceSettings.setValue(QStringLiteral("workspace/last_saved_snapshot_path"), savePath);
    workspaceSettings.sync();

    QMessageBox::information(this,
                             QStringLiteral("Save Snapshot"),
                             QStringLiteral("Snapshot saved:\n%1").arg(savePath));
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
    setSelectedModel(settings.value(QStringLiteral("model")).toString(),
                     settings.value(QStringLiteral("modelDisplay")).toString());
    if (workflowCombo_)
        selectComboValue(workflowCombo_, settings.value(QStringLiteral("workflow"), QStringLiteral("Default Canvas")).toString());
    loraStack_ = deserializeLoraStack(settings.value(QStringLiteral("loraStackJson")).toString());
    rebuildLoraStackUi();
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
        widthSpin_->setValue(settings.value(QStringLiteral("width"), isVideoMode() ? 832 : 1024).toInt());
    if (heightSpin_)
        heightSpin_->setValue(settings.value(QStringLiteral("height"), isVideoMode() ? 480 : 1024).toInt());
    if (frameCountSpin_)
        frameCountSpin_->setValue(settings.value(QStringLiteral("frames"), 81).toInt());
    if (fpsSpin_)
        fpsSpin_->setValue(settings.value(QStringLiteral("fps"), 16).toInt());
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
    for (const LoraStackEntry &entry : loraStack_)
    {
        if (entry.enabled && !entry.value.trimmed().isEmpty())
            return entry.value.trimmed();
    }
    return QString();
}

void ImageGenerationPage::showCheckpointPicker()
{
    const bool showIncompatible = showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked();
    const QVector<CatalogEntry> checkpoints = filterCatalogEntriesForMode(modelDisplayByValue_,
                                                                          modelModalityByValue_,
                                                                          modelFamilyByValue_,
                                                                          modelCompatibilityNoteByValue_,
                                                                          modelConfidenceByValue_,
                                                                          isVideoMode(),
                                                                          showIncompatible);

    CatalogPickerDialog dialog(isVideoMode() ? QStringLiteral("Choose Video Model Asset") : QStringLiteral("Choose Image Checkpoint"),
                               checkpoints,
                               selectedModelPath_,
                               isVideoMode() ? QStringLiteral("image_generation/recent_video_models") : QStringLiteral("image_generation/recent_checkpoints"),
                               this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    setSelectedModel(dialog.selectedValue(), dialog.selectedDisplay());
    persistRecentSelection(isVideoMode() ? QStringLiteral("image_generation/recent_video_models") : QStringLiteral("image_generation/recent_checkpoints"), dialog.selectedValue());
    scheduleUiRefresh(0);
}

void ImageGenerationPage::showLoraPicker()
{
    const bool showIncompatible = showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked();
    const QVector<CatalogEntry> loras = filterCatalogEntriesForMode(loraDisplayByValue_,
                                                                    loraModalityByValue_,
                                                                    loraFamilyByValue_,
                                                                    loraCompatibilityNoteByValue_,
                                                                    loraConfidenceByValue_,
                                                                    isVideoMode(),
                                                                    showIncompatible);

    CatalogPickerDialog dialog(isVideoMode() ? QStringLiteral("Add Video LoRA to Stack") : QStringLiteral("Add Image LoRA to Stack"),
                               loras,
                               QString(),
                               isVideoMode() ? QStringLiteral("image_generation/recent_video_loras") : QStringLiteral("image_generation/recent_loras"),
                               this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    addLoraToStack(dialog.selectedValue(), dialog.selectedDisplay(), 1.0, true);
    persistRecentSelection(isVideoMode() ? QStringLiteral("image_generation/recent_video_loras") : QStringLiteral("image_generation/recent_loras"), dialog.selectedValue());
    scheduleUiRefresh(0);
}

void ImageGenerationPage::setSelectedModel(const QString &value, const QString &display)
{
    selectedModelPath_ = value.trimmed();
    selectedModelDisplay_ = display.trimmed().isEmpty() ? resolveSelectedModelDisplay(selectedModelPath_) : display.trimmed();
    refreshSelectedModelUi();
    updatePrimaryActionAvailability();
}

void ImageGenerationPage::refreshSelectedModelUi()
{
    if (selectedModelLabel_)
    {
        if (selectedModelPath_.trimmed().isEmpty())
        {
            selectedModelLabel_->setText(isVideoMode() ? QStringLiteral("No video model asset selected") : QStringLiteral("No image checkpoint selected"));
            selectedModelLabel_->setToolTip(assetModeFilterLabel(isVideoMode(), showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked()));
        }
        else
        {
            const QString display = selectedModelDisplay_.isEmpty() ? shortDisplayFromValue(selectedModelPath_) : selectedModelDisplay_;
            const QString modality = modelModalityByValue_.value(selectedModelPath_, QStringLiteral("unknown"));
            const QString family = modelFamilyByValue_.value(selectedModelPath_, QStringLiteral("Unknown family"));
            const QString note = modelCompatibilityNoteByValue_.value(selectedModelPath_, QStringLiteral("No compatibility note available."));
            const int confidence = modelConfidenceByValue_.value(selectedModelPath_, 0);
            selectedModelLabel_->setText(QStringLiteral("%1\n%2 • %3 • %4%\n%5")
                                             .arg(display, modality, family)
                                             .arg(confidence)
                                             .arg(selectedModelPath_));
            selectedModelLabel_->setToolTip(QStringLiteral("%1\n%2\n%3")
                                                .arg(selectedModelPath_, assetModeFilterLabel(isVideoMode(), showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked()), note));
        }
    }

    if (clearModelButton_)
        clearModelButton_->setEnabled(!selectedModelPath_.trimmed().isEmpty());

    updateAssetIntelligenceUi();
}

QString ImageGenerationPage::resolveSelectedModelDisplay(const QString &value) const
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return QString();

    const auto it = modelDisplayByValue_.constFind(trimmed);
    if (it != modelDisplayByValue_.constEnd())
        return it.value();

    return shortDisplayFromValue(trimmed);
}

QString ImageGenerationPage::resolveLoraDisplay(const QString &value) const
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return QString();

    const auto it = loraDisplayByValue_.constFind(trimmed);
    if (it != loraDisplayByValue_.constEnd())
        return it.value();

    return shortDisplayFromValue(trimmed);
}

bool ImageGenerationPage::trySetSelectedModelByCandidate(const QStringList &candidates)
{
    const bool showIncompatible = showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked();
    const QVector<CatalogEntry> compatible = filterCatalogEntriesForMode(modelDisplayByValue_,
                                                                         modelModalityByValue_,
                                                                         modelFamilyByValue_,
                                                                         modelCompatibilityNoteByValue_,
                                                                         modelConfidenceByValue_,
                                                                         isVideoMode(),
                                                                         showIncompatible);

    QString match = resolveCatalogValueByCandidates(compatible, candidates);
    if (match.isEmpty() && showIncompatible)
    {
        const QVector<CatalogEntry> allAssets = filterCatalogEntriesForMode(modelDisplayByValue_,
                                                                            modelModalityByValue_,
                                                                            modelFamilyByValue_,
                                                                            modelCompatibilityNoteByValue_,
                                                                            modelConfidenceByValue_,
                                                                            isVideoMode(),
                                                                            true);
        match = resolveCatalogValueByCandidates(allAssets, candidates);
    }

    if (match.isEmpty())
        return false;

    setSelectedModel(match, resolveSelectedModelDisplay(match));
    return true;
}

bool ImageGenerationPage::tryAddLoraByCandidate(const QStringList &candidates, double weight, bool enabled)
{
    const bool showIncompatible = showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked();
    const QVector<CatalogEntry> compatible = filterCatalogEntriesForMode(loraDisplayByValue_,
                                                                         loraModalityByValue_,
                                                                         loraFamilyByValue_,
                                                                         loraCompatibilityNoteByValue_,
                                                                         loraConfidenceByValue_,
                                                                         isVideoMode(),
                                                                         showIncompatible);

    QString match = resolveCatalogValueByCandidates(compatible, candidates);
    if (match.isEmpty() && showIncompatible)
    {
        const QVector<CatalogEntry> allAssets = filterCatalogEntriesForMode(loraDisplayByValue_,
                                                                            loraModalityByValue_,
                                                                            loraFamilyByValue_,
                                                                            loraCompatibilityNoteByValue_,
                                                                            loraConfidenceByValue_,
                                                                            isVideoMode(),
                                                                            true);
        match = resolveCatalogValueByCandidates(allAssets, candidates);
    }

    if (match.isEmpty())
        return false;

    addLoraToStack(match, resolveLoraDisplay(match), weight, enabled);
    return true;
}

void ImageGenerationPage::addLoraToStack(const QString &value, const QString &display, double weight, bool enabled)
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return;

    for (LoraStackEntry &entry : loraStack_)
    {
        if (entry.value.compare(trimmed, Qt::CaseInsensitive) == 0)
        {
            entry.weight = weight;
            entry.enabled = enabled;
            if (entry.display.trimmed().isEmpty())
                entry.display = display.trimmed();
            persistRecentSelection(isVideoMode() ? QStringLiteral("image_generation/recent_video_loras") : QStringLiteral("image_generation/recent_loras"), trimmed);
            rebuildLoraStackUi();
            return;
        }
    }

    LoraStackEntry entry;
    entry.value = trimmed;
    entry.display = display.trimmed().isEmpty() ? resolveLoraDisplay(trimmed) : display.trimmed();
    entry.weight = weight;
    entry.enabled = enabled;
    loraStack_.push_back(entry);
    persistRecentSelection(isVideoMode() ? QStringLiteral("image_generation/recent_video_loras") : QStringLiteral("image_generation/recent_loras"), trimmed);
    rebuildLoraStackUi();
}

void ImageGenerationPage::rebuildLoraStackUi()
{
    if (!loraStackLayout_)
        return;

    while (QLayoutItem *item = loraStackLayout_->takeAt(0))
    {
        if (QWidget *widget = item->widget())
            widget->deleteLater();
        delete item;
    }

    int enabledCount = 0;
    for (int index = 0; index < loraStack_.size(); ++index)
    {
        LoraStackEntry &entry = loraStack_[index];
        if (entry.display.trimmed().isEmpty())
            entry.display = resolveLoraDisplay(entry.value);
        if (entry.enabled)
            ++enabledCount;

        auto *row = new QFrame(loraStackContainer_);
        row->setObjectName(QStringLiteral("InputDropCard"));
        auto *rowLayout = new QVBoxLayout(row);
        rowLayout->setContentsMargins(10, 10, 10, 10);
        rowLayout->setSpacing(8);

        auto *topRow = new QHBoxLayout;
        topRow->setContentsMargins(0, 0, 0, 0);
        topRow->setSpacing(8);
        auto *enabledBox = new QCheckBox(QStringLiteral("Enabled"), row);
        enabledBox->setChecked(entry.enabled);
        const QString loraModality = loraModalityByValue_.value(entry.value, QStringLiteral("unknown"));
        const QString loraFamily = loraFamilyByValue_.value(entry.value, QStringLiteral("Unknown family"));
        auto *title = new QLabel(QStringLiteral("%1\n%2 • %3\n%4").arg(entry.display, loraModality, loraFamily, entry.value), row);
        title->setObjectName(QStringLiteral("SectionBody"));
        title->setWordWrap(true);
        auto *editButton = new QPushButton(QStringLiteral("Change"), row);
        editButton->setObjectName(QStringLiteral("TertiaryActionButton"));
        auto *upButton = new QPushButton(QStringLiteral("Up"), row);
        upButton->setObjectName(QStringLiteral("TertiaryActionButton"));
        auto *downButton = new QPushButton(QStringLiteral("Down"), row);
        downButton->setObjectName(QStringLiteral("TertiaryActionButton"));
        auto *removeButton = new QPushButton(QStringLiteral("Remove"), row);
        removeButton->setObjectName(QStringLiteral("TertiaryActionButton"));

        topRow->addWidget(enabledBox);
        topRow->addWidget(title, 1);
        topRow->addWidget(editButton);
        topRow->addWidget(upButton);
        topRow->addWidget(downButton);
        topRow->addWidget(removeButton);
        rowLayout->addLayout(topRow);

        auto *weightRow = new QHBoxLayout;
        weightRow->setContentsMargins(0, 0, 0, 0);
        weightRow->setSpacing(8);
        auto *weightLabel = new QLabel(QStringLiteral("Weight"), row);
        auto *weightSpin = new QDoubleSpinBox(row);
        weightSpin->setDecimals(2);
        weightSpin->setSingleStep(0.05);
        weightSpin->setRange(0.0, 2.0);
        weightSpin->setValue(entry.weight);
        configureDoubleSpinBox(weightSpin);
        weightRow->addWidget(weightLabel);
        weightRow->addWidget(weightSpin, 1);
        rowLayout->addLayout(weightRow);

        QObject::connect(enabledBox, &QCheckBox::toggled, this, [this, index](bool checked) {
            if (index < 0 || index >= loraStack_.size())
                return;
            loraStack_[index].enabled = checked;
            rebuildLoraStackUi();
            scheduleUiRefresh(0);
        });
        QObject::connect(weightSpin, qOverload<double>(&QDoubleSpinBox::valueChanged), this, [this, index](double value) {
            if (index < 0 || index >= loraStack_.size())
                return;
            loraStack_[index].weight = value;
            scheduleUiRefresh(0);
        });
        QObject::connect(editButton, &QPushButton::clicked, this, [this, index]() {
            if (index < 0 || index >= loraStack_.size())
                return;

            const bool showIncompatible = showIncompatibleAssetsCheck_ && showIncompatibleAssetsCheck_->isChecked();
            const QVector<CatalogEntry> loras = filterCatalogEntriesForMode(loraDisplayByValue_,
                                                                            loraModalityByValue_,
                                                                            loraFamilyByValue_,
                                                                            loraCompatibilityNoteByValue_,
                                                                            loraConfidenceByValue_,
                                                                            isVideoMode(),
                                                                            showIncompatible);

            CatalogPickerDialog dialog(isVideoMode() ? QStringLiteral("Replace Video LoRA") : QStringLiteral("Replace Image LoRA"),
                                       loras,
                                       loraStack_[index].value,
                                       isVideoMode() ? QStringLiteral("image_generation/recent_video_loras") : QStringLiteral("image_generation/recent_loras"),
                                       this);
            if (dialog.exec() != QDialog::Accepted)
                return;

            loraStack_[index].value = dialog.selectedValue().trimmed();
            loraStack_[index].display = dialog.selectedDisplay().trimmed().isEmpty() ? resolveLoraDisplay(loraStack_[index].value) : dialog.selectedDisplay().trimmed();
            persistRecentSelection(isVideoMode() ? QStringLiteral("image_generation/recent_video_loras") : QStringLiteral("image_generation/recent_loras"), loraStack_[index].value);
            rebuildLoraStackUi();
            scheduleUiRefresh(0);
        });
        QObject::connect(removeButton, &QPushButton::clicked, this, [this, index]() {
            if (index < 0 || index >= loraStack_.size())
                return;
            loraStack_.removeAt(index);
            rebuildLoraStackUi();
            scheduleUiRefresh(0);
        });
        QObject::connect(upButton, &QPushButton::clicked, this, [this, index]() {
            if (index <= 0 || index >= loraStack_.size())
                return;
            loraStack_.swapItemsAt(index, index - 1);
            rebuildLoraStackUi();
            scheduleUiRefresh(0);
        });
        QObject::connect(downButton, &QPushButton::clicked, this, [this, index]() {
            if (index < 0 || index >= loraStack_.size() - 1)
                return;
            loraStack_.swapItemsAt(index, index + 1);
            rebuildLoraStackUi();
            scheduleUiRefresh(0);
        });

        loraStackLayout_->addWidget(row);
    }

    if (loraStack_.isEmpty())
    {
        auto *empty = new QLabel(QStringLiteral("No LoRAs selected. Add one or more LoRAs to build a reusable stack."), loraStackContainer_);
        empty->setObjectName(QStringLiteral("ImageGenHint"));
        empty->setWordWrap(true);
        loraStackLayout_->addWidget(empty);
    }

    loraStackLayout_->addStretch(1);

    if (loraStackSummaryLabel_)
    {
        if (loraStack_.isEmpty())
        {
            loraStackSummaryLabel_->setText(QStringLiteral("No LoRAs in stack"));
        }
        else
        {
            const LoraStackEntry &first = loraStack_.first();
            loraStackSummaryLabel_->setText(QStringLiteral("%1 in stack • %2 enabled • first: %3 @ %4")
                                                .arg(loraStack_.size())
                                                .arg(enabledCount)
                                                .arg(first.display)
                                                .arg(QString::number(first.weight, 'f', 2)));
        }
    }

    if (clearLorasButton_)
        clearLorasButton_->setEnabled(!loraStack_.isEmpty());

    updateAssetIntelligenceUi();
}

void ImageGenerationPage::persistLatestGeneratedOutput(const QString &path)
{
    const QString normalizedPath = path.trimmed();
    if (normalizedPath.isEmpty())
        return;

    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    if (isImageAssetPath(normalizedPath))
        settings.setValue(QStringLiteral("workspace/last_generated_image_path"), normalizedPath);
    if (isVideoAssetPath(normalizedPath))
        settings.setValue(QStringLiteral("workspace/last_generated_video_path"), normalizedPath);
    settings.sync();
}

QString ImageGenerationPage::latestGeneratedOutputPath() const
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    return settings.value(QStringLiteral("workspace/last_generated_image_path")).toString().trimmed();
}

void ImageGenerationPage::prepLatestForI2I()
{
    QString latest = generatedPreviewPath_.trimmed();
    if (latest.isEmpty())
        latest = latestGeneratedOutputPath();

    if (latest.isEmpty() || !QFileInfo::exists(latest))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Prep for I2I"),
                                 QStringLiteral("No generated image is available yet. Generate or queue a T2I image first."));
        return;
    }

    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    settings.setValue(QStringLiteral("workspace/staged_i2i_input_path"), latest);
    settings.sync();

    if (prepLatestForI2IButton_)
    {
        prepLatestForI2IButton_->setText(QStringLiteral("Prepped"));
        QTimer::singleShot(1300, this, [this]() {
            if (prepLatestForI2IButton_)
                prepLatestForI2IButton_->setText(QStringLiteral("Prep for I2I"));
        });
    }

    emit prepForI2IRequested(latest);
}

void ImageGenerationPage::useLatestForI2I()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    QString staged = settings.value(QStringLiteral("workspace/staged_i2i_input_path")).toString().trimmed();

    if (staged.isEmpty())
        staged = latestGeneratedOutputPath();

    if (staged.isEmpty() || !QFileInfo::exists(staged))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Use Last Image"),
                                 QStringLiteral("No staged or generated image is available yet."));
        return;
    }

    useImageAsInput(staged);
}

void ImageGenerationPage::useImageAsInput(const QString &path)
{
    const QString normalizedPath = path.trimmed();
    if (normalizedPath.isEmpty() || !QFileInfo::exists(normalizedPath))
        return;

    setInputImagePath(normalizedPath);
    updatePrimaryActionAvailability();
    scheduleUiRefresh(0);
    schedulePreviewRefresh(0);
}
