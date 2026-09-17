#include "ModelInspectorPanel.h"

#include "ModelKindTabs.h"

#include "../ThemeManager.h"
#include "../style/SvKit.h"
#include "../style/SvStyle.h"
#include "../widgets/ElidingLabel.h"

#include <QClipboard>
#include <QDesktopServices>
#include <QFileDialog>
#include <QFileInfo>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QPixmap>
#include <QPushButton>
#include <QUrl>
#include <QVBoxLayout>

namespace spellvision::assets
{

namespace
{
using spellvision::kit::setRole;

constexpr int kGalleryTiles = 6; // `download_previews` fetches at most six
constexpr int kTileHeight = 84;
constexpr int kDescriptionCollapsed = 320;

// Order matters: this is what the inspector reads top to bottom, and it is the order the cockpit
// cares about rather than the alphabetical order the sidecar's JSON object happens to be in.
const char *kFieldOrder[] = {"steps", "cfg", "guidance", "sampler", "scheduler", "shift",
                             "clip_skip", "width", "height", "frames", "fps", "lora_strength",
                             "prompt_prefix"};

QString fieldLabel(const QString &field)
{
    if (field == QStringLiteral("cfg"))
        return QStringLiteral("CFG");
    if (field == QStringLiteral("clip_skip"))
        return QStringLiteral("Clip skip");
    if (field == QStringLiteral("lora_strength"))
        return QStringLiteral("LoRA strength");
    if (field == QStringLiteral("prompt_prefix"))
        return QStringLiteral("Prompt prefix");
    if (field == QStringLiteral("fps"))
        return QStringLiteral("FPS");
    QString label = field;
    label.replace(QLatin1Char('_'), QLatin1Char(' '));
    label[0] = label[0].toUpper();
    return label;
}
} // namespace

ModelInspectorPanel::ModelInspectorPanel(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("ModelInspectorPanel"));

    ThemeManager &theme = ThemeManager::instance();
    const int snug = theme.spacing(ThemeManager::Spacing::Snug);
    const int tight = theme.spacing(ThemeManager::Spacing::Tight);
    const int hair = theme.spacing(ThemeManager::Spacing::Hairline);

    auto *column = new QVBoxLayout(this);
    column->setContentsMargins(0, 0, 0, 0);
    column->setSpacing(hair);

    headlineLabel_ = new QLabel(this);
    headlineLabel_->setObjectName(QStringLiteral("ModelsDetailsText"));
    headlineLabel_->setWordWrap(true);
    headlineLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    column->addWidget(headlineLabel_);

    subtitleLabel_ = new QLabel(this);
    subtitleLabel_->setObjectName(QStringLiteral("ModelsMeta"));
    subtitleLabel_->setWordWrap(true);
    subtitleLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    column->addWidget(subtitleLabel_);

    // --- gallery strip ---
    galleryRow_ = new QWidget(this);
    galleryRow_->setObjectName(QStringLiteral("ModelsGalleryStrip"));
    auto *strip = new QHBoxLayout(galleryRow_);
    strip->setContentsMargins(0, 0, 0, 0);
    strip->setSpacing(tight);
    for (int index = 0; index < kGalleryTiles; ++index)
    {
        auto *tile = new QLabel(galleryRow_);
        tile->setObjectName(QStringLiteral("ModelsGalleryTile"));
        tile->setFixedHeight(kTileHeight);
        tile->setAlignment(Qt::AlignCenter);
        tile->setScaledContents(false);
        tile->hide();
        galleryTiles_.push_back(tile);
        strip->addWidget(tile);
    }
    strip->addStretch(1);
    column->addWidget(galleryRow_);

    // --- description ---
    descriptionLabel_ = new QLabel(this);
    descriptionLabel_->setObjectName(QStringLiteral("ModelsMeta"));
    descriptionLabel_->setWordWrap(true);
    descriptionLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    column->addWidget(descriptionLabel_);

    descriptionToggle_ = new QPushButton(QStringLiteral("More"), this);
    descriptionToggle_->setObjectName(QStringLiteral("ModelsActionButton"));
    descriptionToggle_->setCursor(Qt::PointingHandCursor);
    setRole(descriptionToggle_, spellvision::style::Role::Tertiary);
    descriptionToggle_->hide();
    connect(descriptionToggle_, &QPushButton::clicked, this, [this]() {
        descriptionExpanded_ = !descriptionExpanded_;
        rebuild();
    });

    // --- trigger words ---
    triggersLabel_ = new QLabel(this);
    triggersLabel_->setObjectName(QStringLiteral("ModelsDetailsText"));
    triggersLabel_->setWordWrap(true);
    triggersLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    copyTriggersButton_ = new QPushButton(QStringLiteral("Copy trigger words"), this);
    copyTriggersButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    copyTriggersButton_->setCursor(Qt::PointingHandCursor);
    setRole(copyTriggersButton_, spellvision::style::Role::Secondary);
    connect(copyTriggersButton_, &QPushButton::clicked, this, [this]() {
        if (!intel_.triggerWords.isEmpty())
            QGuiApplication::clipboard()->setText(intel_.triggerWords.join(QStringLiteral(", ")));
    });

    auto *triggersRow = new QHBoxLayout();
    triggersRow->setContentsMargins(0, 0, 0, 0);
    triggersRow->setSpacing(tight);
    triggersRow->addWidget(triggersLabel_, 1);
    triggersRow->addWidget(descriptionToggle_, 0, Qt::AlignTop);
    triggersRow->addWidget(copyTriggersButton_, 0, Qt::AlignTop);
    column->addLayout(triggersRow);

    licenceLabel_ = new QLabel(this);
    licenceLabel_->setObjectName(QStringLiteral("ModelsMeta"));
    licenceLabel_->setWordWrap(true);
    column->addWidget(licenceLabel_);

    recommendedLabel_ = new QLabel(this);
    recommendedLabel_->setObjectName(QStringLiteral("ModelsDetailsText"));
    recommendedLabel_->setWordWrap(true);
    recommendedLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    column->addWidget(recommendedLabel_);

    // --- actions ---
    applyButton_ = new QPushButton(QStringLiteral("Apply to this mode"), this);
    applyButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    applyButton_->setCursor(Qt::PointingHandCursor);
    setRole(applyButton_, spellvision::style::Role::Secondary);
    connect(applyButton_, &QPushButton::clicked, this, [this]() {
        if (!weightPath_.isEmpty())
            emit applyRecommendedRequested(weightPath_, recommendedAsJson());
    });

    usePictureButton_ = new QPushButton(QStringLiteral("Use my picture…"), this);
    usePictureButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    usePictureButton_->setCursor(Qt::PointingHandCursor);
    setRole(usePictureButton_, spellvision::style::Role::Secondary);
    usePictureButton_->setToolTip(QStringLiteral(
        "Replace this model's picture with one of your own. The file itself is not touched, and a "
        "later metadata refresh will not overwrite your choice."));
    connect(usePictureButton_, &QPushButton::clicked, this, [this]() {
        if (weightPath_.isEmpty())
            return;
        // Start in the weight's own folder. The worker refuses a picture outside the model roots,
        // so opening anywhere else invites a refusal the user did not need to see.
        const QString chosen = QFileDialog::getOpenFileName(
            this, QStringLiteral("Use my picture for this model"),
            QFileInfo(weightPath_).absolutePath(),
            QStringLiteral("Images (*.png *.jpg *.jpeg *.webp *.bmp)"));
        if (!chosen.trimmed().isEmpty())
            requestUserPicture(chosen);
    });

    refreshButton_ = new QPushButton(QStringLiteral("Refresh metadata"), this);
    refreshButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    refreshButton_->setCursor(Qt::PointingHandCursor);
    setRole(refreshButton_, spellvision::style::Role::Secondary);
    connect(refreshButton_, &QPushButton::clicked, this, &ModelInspectorPanel::requestRefresh);

    openSiteButton_ = new QPushButton(QStringLiteral("Open on site"), this);
    openSiteButton_->setObjectName(QStringLiteral("ModelsActionButton"));
    openSiteButton_->setCursor(Qt::PointingHandCursor);
    setRole(openSiteButton_, spellvision::style::Role::Secondary);
    connect(openSiteButton_, &QPushButton::clicked, this, [this]() {
        const QString url = intel_.primarySource().url;
        if (!url.isEmpty())
            QDesktopServices::openUrl(QUrl(url));
    });

    // ONE status line, and it is an ElidingLabel rather than a second ErrorPillLabel: a page can
    // hold only one unnamed pill before a findChild in an existing test starts picking the wrong
    // one.
    statusLabel_ = new spellvision::widgets::ElidingLabel(this);
    statusLabel_->setObjectName(QStringLiteral("ModelsInspectorStatus"));

    auto *actions = new QHBoxLayout();
    actions->setContentsMargins(0, 0, 0, 0);
    actions->setSpacing(tight);
    actions->addWidget(applyButton_);
    actions->addWidget(usePictureButton_);
    actions->addWidget(refreshButton_);
    actions->addWidget(openSiteButton_);
    actions->addWidget(statusLabel_, 1);
    column->addLayout(actions);
    column->addSpacing(hair);

    Q_UNUSED(snug);
    clear();
}

void ModelInspectorPanel::setModelRoots(const QStringList &roots)
{
    modelRoots_ = roots;
}

void ModelInspectorPanel::clear()
{
    weightPath_.clear();
    fileName_.clear();
    intel_ = ModelIntel{};
    descriptionExpanded_ = false;
    setStatus(QString(), false);
    rebuild();
}

void ModelInspectorPanel::showModel(const QString &weightPath, const QString &fileName)
{
    if (weightPath.trimmed().isEmpty())
    {
        clear();
        return;
    }
    weightPath_ = weightPath;
    fileName_ = fileName.isEmpty() ? QFileInfo(weightPath).fileName() : fileName;
    descriptionExpanded_ = false;
    setStatus(QString(), false);
    reloadFromDisk();
}

void ModelInspectorPanel::reloadFromDisk()
{
    intel_ = readModelIntel(weightPath_);
    rebuild();
}

void ModelInspectorPanel::setStatus(const QString &text, bool isError)
{
    if (!statusLabel_)
        return;
    statusLabel_->setFullText(text);
    statusLabel_->setProperty("svState", isError ? QStringLiteral("error") : QString());
    statusLabel_->setVisible(!text.isEmpty());
}

void ModelInspectorPanel::rebuild()
{
    const bool hasModel = !weightPath_.isEmpty();

    headlineLabel_->setText(hasModel ? headlineText() : QStringLiteral("Select a model to view details."));

    QStringList subtitle;
    if (hasModel)
    {
        // The FILE, always. The headline may be the site's title; this is where a user checks
        // which file that title points at.
        subtitle << fileName_;
        if (!intel_.kind.isEmpty())
            subtitle << ModelKindTabs::kindLabel(intel_.kind);
        if (!intel_.family.isEmpty())
            subtitle << intel_.family;
        if (!intel_.quantisation.isEmpty())
            subtitle << intel_.quantisation;
        if (!intel_.creator.isEmpty())
            subtitle << QStringLiteral("by %1").arg(intel_.creator);
        const QString caption = identificationCaption(intel_.identification());
        if (!caption.isEmpty())
            subtitle << caption;
    }
    subtitleLabel_->setText(subtitle.join(QStringLiteral("   ·   ")));
    subtitleLabel_->setVisible(hasModel);

    // --- gallery ---
    int shown = 0;
    for (int index = 0; index < galleryTiles_.size(); ++index)
    {
        QLabel *tile = galleryTiles_.at(index);
        if (index >= intel_.images.size())
        {
            tile->clear();
            tile->setProperty("imagePath", QString());
            tile->hide();
            continue;
        }
        const ModelIntelImage &image = intel_.images.at(index);
        QPixmap pixmap;
        if (!image.localPath.isEmpty())
            pixmap.load(image.localPath);
        if (pixmap.isNull())
        {
            // The sidecar names a picture that is not on disk (a previews folder the user moved,
            // a half-finished refresh). The tile stays out rather than showing an empty box.
            tile->clear();
            tile->setProperty("imagePath", QString());
            tile->hide();
            continue;
        }
        if (previewShouldBlur(image.nsfwLevel, nsfwPreviewCeiling()))
        {
            const QPixmap tiny = pixmap.scaled(QSize(8, 8), Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
            pixmap = tiny.scaledToHeight(kTileHeight, Qt::SmoothTransformation);
        }
        tile->setPixmap(pixmap.scaledToHeight(kTileHeight, Qt::SmoothTransformation));
        tile->setProperty("imagePath", image.localPath);
        tile->setToolTip(image.originUrl.isEmpty() ? image.localPath : image.originUrl);
        tile->show();
        ++shown;
    }
    galleryRow_->setVisible(shown > 0);

    // --- description ---
    const QString description = plainTextFromHtml(intel_.descriptionHtml);
    const bool longDescription = description.size() > kDescriptionCollapsed;
    descriptionLabel_->setText(
        (longDescription && !descriptionExpanded_)
            ? description.left(kDescriptionCollapsed) + QStringLiteral("…")
            : description);
    descriptionLabel_->setVisible(!description.isEmpty());
    descriptionToggle_->setVisible(longDescription);
    descriptionToggle_->setText(descriptionExpanded_ ? QStringLiteral("Less") : QStringLiteral("More"));

    // --- trigger words ---
    const bool hasTriggers = !intel_.triggerWords.isEmpty();
    triggersLabel_->setText(hasTriggers
        ? QStringLiteral("Triggers: %1").arg(intel_.triggerWords.join(QStringLiteral(", ")))
        : QString());
    triggersLabel_->setVisible(hasTriggers);
    copyTriggersButton_->setVisible(hasTriggers);

    licenceLabel_->setText(licenceText());
    licenceLabel_->setVisible(hasModel);

    const QStringList lines = recommendedLines();
    recommendedLabel_->setText(lines.isEmpty()
        ? QStringLiteral("No published settings for this model.")
        : QStringLiteral("Recommended settings\n%1").arg(lines.join(QLatin1Char('\n'))));
    recommendedLabel_->setVisible(hasModel);

    applyButton_->setEnabled(hasModel && !lines.isEmpty());
    usePictureButton_->setEnabled(hasModel);
    refreshButton_->setEnabled(hasModel);
    openSiteButton_->setVisible(canOpenOnSite());
}

QString ModelInspectorPanel::headlineText() const
{
    if (weightPath_.isEmpty())
        return QString();
    return intel_.displayName.isEmpty() ? fileName_ : intel_.displayName;
}

QString ModelInspectorPanel::descriptionText() const
{
    return descriptionLabel_ ? descriptionLabel_->text() : QString();
}

QString ModelInspectorPanel::licenceText() const
{
    if (weightPath_.isEmpty())
        return QString();
    if (!intel_.licenseName.isEmpty())
        return QStringLiteral("Licence: %1").arg(intel_.licenseName);
    if (intel_.identification() == ModelIdentification::Identified)
    {
        // The site knows this weight and published no licence. Saying "the site did not say"
        // rather than nothing is the difference between an unanswered question and one nobody
        // asked — and for a library that may ship commercially, the difference matters.
        return QStringLiteral("Licence: not stated by the site");
    }
    return QStringLiteral("Licence: unknown — this model has not been identified");
}

QStringList ModelInspectorPanel::triggerWords() const
{
    return intel_.triggerWords;
}

int ModelInspectorPanel::galleryCount() const
{
    int shown = 0;
    for (const QLabel *tile : galleryTiles_)
    {
        if (tile->isVisibleTo(const_cast<ModelInspectorPanel *>(this)) && tile->pixmap().isNull() == false)
            ++shown;
    }
    return shown;
}

QString ModelInspectorPanel::galleryImageAt(int index) const
{
    if (index < 0 || index >= galleryTiles_.size())
        return QString();
    return galleryTiles_.at(index)->property("imagePath").toString();
}

QString ModelInspectorPanel::coverPath() const
{
    return intel_.coverPath();
}

QStringList ModelInspectorPanel::recommendedLines() const
{
    QStringList lines;
    QStringList seen;
    auto append = [&](const ModelIntelRecommendation &entry) {
        if (entry.field.isEmpty() || seen.contains(entry.field))
            return;
        seen << entry.field;
        lines << QStringLiteral("%1: %2   (%3)")
                     .arg(fieldLabel(entry.field), entry.value, entry.caption());
    };
    for (const char *field : kFieldOrder)
    {
        const ModelIntelRecommendation entry = intel_.recommendationFor(QString::fromLatin1(field));
        if (!entry.field.isEmpty())
            append(entry);
    }
    // Anything the sidecar carries that this build has no opinion about the order of still shows.
    // A newer worker adding a field must not make it invisible here.
    for (const ModelIntelRecommendation &entry : intel_.recommended)
        append(entry);
    return lines;
}

QStringList ModelInspectorPanel::provenanceCaptions() const
{
    QStringList captions;
    for (const ModelIntelRecommendation &entry : intel_.recommended)
        captions << entry.caption();
    return captions;
}

QString ModelInspectorPanel::statusText() const
{
    return statusLabel_ ? statusLabel_->fullText() : QString();
}

bool ModelInspectorPanel::canOpenOnSite() const
{
    return !intel_.primarySource().url.isEmpty();
}

QJsonObject ModelInspectorPanel::recommendedAsJson() const
{
    QJsonObject settings;
    for (const ModelIntelRecommendation &entry : intel_.recommended)
    {
        QJsonObject one;
        one.insert(QStringLiteral("value"), entry.value);
        one.insert(QStringLiteral("provenance"), entry.provenance);
        one.insert(QStringLiteral("confidence"), entry.confidence);
        settings.insert(entry.field, one);
    }
    return settings;
}

void ModelInspectorPanel::requestUserPicture(const QString &picturePath)
{
    if (weightPath_.isEmpty() || picturePath.trimmed().isEmpty())
        return;

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("model_intel_set_user"));
    request.insert(QStringLiteral("path"), weightPath_);
    request.insert(QStringLiteral("picture"), picturePath.trimmed());
    // The worker bounds `path` AND `picture` by the roots the REQUEST names, and a request naming
    // none gets no location check at all. Sending them is what makes the documented containment
    // true for this caller -- and what makes the refusal below reachable rather than theoretical.
    QJsonArray roots;
    for (const QString &root : modelRoots_)
    {
        if (!root.trimmed().isEmpty())
            roots.append(root.trimmed());
    }
    if (!roots.isEmpty())
        request.insert(QStringLiteral("roots"), roots);

    setStatus(QStringLiteral("Setting your picture…"), false);
    emit workerRequested(request);
}

void ModelInspectorPanel::requestRefresh()
{
    if (weightPath_.isEmpty())
        return;
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("model_intel_refresh"));
    QJsonArray roots;
    for (const QString &root : modelRoots_)
    {
        if (!root.trimmed().isEmpty())
            roots.append(root.trimmed());
    }
    // `roots` is required by the command. Falling back to the weight's own folder keeps the button
    // working on a library whose roots the page has not pushed yet, and narrows the walk to the
    // one directory rather than silently re-hashing terabytes.
    if (roots.isEmpty())
        roots.append(QFileInfo(weightPath_).absolutePath());
    request.insert(QStringLiteral("roots"), roots);
    request.insert(QStringLiteral("files"), QJsonArray{weightPath_});
    setStatus(QStringLiteral("Refreshing metadata…"), false);
    emit workerRequested(request);
}

void ModelInspectorPanel::applyWorkerReply(const QJsonObject &reply)
{
    const QString type = reply.value(QStringLiteral("type")).toString();
    if (type != QStringLiteral("model_intel_set_user") && type != QStringLiteral("model_intel_refresh")
        && type != QStringLiteral("model_intel"))
    {
        return;
    }

    if (!reply.value(QStringLiteral("ok")).toBool(false))
    {
        // The containment refusal lands here. It is a designed answer, not a crash, and a user
        // who picked a file outside their model roots needs to be told which rule stopped them --
        // otherwise the cover simply does not change and the app looks broken.
        const QString error = reply.value(QStringLiteral("error")).toString();
        setStatus(error.isEmpty() ? QStringLiteral("The worker refused that request.") : error, true);
        return;
    }

    if (type == QStringLiteral("model_intel_set_user"))
    {
        const QStringList changed = [&]() {
            QStringList out;
            for (const QJsonValue &value : reply.value(QStringLiteral("changed")).toArray())
                out << value.toString();
            return out;
        }();
        reloadFromDisk();
        setStatus(changed.contains(QStringLiteral("picture"))
                      ? QStringLiteral("Your picture is now this model's cover.")
                      : QStringLiteral("Saved."),
                  false);
        return;
    }

    if (type == QStringLiteral("model_intel_refresh"))
    {
        reloadFromDisk();
        setStatus(QStringLiteral("Metadata refreshed."), false);
        return;
    }

    // `model_intel` carries the sidecar in the reply, so there is no need to go back to disk.
    const QJsonObject payload = reply.value(QStringLiteral("sidecar")).toObject();
    if (payload.isEmpty())
    {
        reloadFromDisk();
        return;
    }
    intel_ = parseModelIntelDocument(QJsonDocument(payload).toJson(QJsonDocument::Compact),
                                     modelIntelSidecarPath(weightPath_));
    rebuild();
}

} // namespace spellvision::assets
