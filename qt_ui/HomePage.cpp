#include "HomePage.h"

#include "HomeDashboardPage.h"
#include "HomeDashboardSettings.h"
#include "ThemeManager.h"

#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QDirIterator>
#include <QFileInfo>
#include <QFrame>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSettings>
#include <QScrollArea>
#include <QShowEvent>
#include <QVBoxLayout>

#include <algorithm>

namespace
{
QString firstNonEmpty(const QString &a,
                      const QString &b = QString(),
                      const QString &c = QString(),
                      const QString &fallback = QString())
{
    for (const QString &candidate : {a, b, c, fallback})
    {
        const QString trimmed = candidate.trimmed();
        if (!trimmed.isEmpty())
            return trimmed;
    }
    return QString();
}

QString resolveProjectRoot()
{
    const QStringList starts = {
        QCoreApplication::applicationDirPath(),
        QDir::currentPath(),
    };

    for (const QString &start : starts)
    {
        QDir dir(start);
        for (int depth = 0; depth < 8; ++depth)
        {
            if (QFileInfo::exists(dir.filePath(QStringLiteral("python/worker_client.py"))))
                return dir.absolutePath();
            if (!dir.cdUp())
                break;
        }
    }

    return QDir::currentPath();
}

QString importedWorkflowsRoot(const QString &projectRoot)
{
    return QDir(projectRoot).filePath(QStringLiteral("runtime/imported_workflows"));
}

QString outputsRoot(const QString &projectRoot)
{
    return QDir(projectRoot).filePath(QStringLiteral("output"));
}

QString normalizedModeId(QString modeId)
{
    modeId = modeId.trimmed().toLower();

    if (modeId == QStringLiteral("t2i") || modeId == QStringLiteral("text_to_image") || modeId == QStringLiteral("text-to-image"))
        return QStringLiteral("t2i");
    if (modeId == QStringLiteral("i2i") || modeId == QStringLiteral("image_to_image") || modeId == QStringLiteral("image-to-image"))
        return QStringLiteral("i2i");
    if (modeId == QStringLiteral("t2v") || modeId == QStringLiteral("text_to_video") || modeId == QStringLiteral("text-to-video"))
        return QStringLiteral("t2v");
    if (modeId == QStringLiteral("i2v") || modeId == QStringLiteral("image_to_video") || modeId == QStringLiteral("image-to-video"))
        return QStringLiteral("i2v");

    return QString();
}

QString displayModeName(const QString &modeId)
{
    const QString normalized = normalizedModeId(modeId);
    if (normalized == QStringLiteral("t2i"))
        return QStringLiteral("Text to Image");
    if (normalized == QStringLiteral("i2i"))
        return QStringLiteral("Image to Image");
    if (normalized == QStringLiteral("t2v"))
        return QStringLiteral("Text to Video");
    if (normalized == QStringLiteral("i2v"))
        return QStringLiteral("Image to Video");
    return QStringLiteral("Generation");
}

QString prettifyFileStem(QString stem)
{
    stem.replace(QLatin1Char('_'), QLatin1Char(' '));
    stem.replace(QLatin1Char('-'), QLatin1Char(' '));
    stem = stem.simplified();
    if (stem.isEmpty())
        return QStringLiteral("Untitled");
    return stem;
}

QJsonObject readJsonObjectFromFile(const QString &path)
{
    const QFile file(path);
    if (!file.exists())
        return {};

    QFile openFile(path);
    if (!openFile.open(QIODevice::ReadOnly))
        return {};

    const QJsonDocument doc = QJsonDocument::fromJson(openFile.readAll());
    if (!doc.isObject())
        return {};
    return doc.object();
}

QString inferModeFromWorkflowProfile(const QJsonObject &profile)
{
    const QString directTask = normalizedModeId(firstNonEmpty(profile.value(QStringLiteral("task_command")).toString(),
                                                              profile.value(QStringLiteral("workflow_task_command")).toString(),
                                                              profile.value(QStringLiteral("task_type")).toString()));
    if (!directTask.isEmpty())
        return directTask;

    const QString mediaType = profile.value(QStringLiteral("media_type")).toString().trimmed().toLower();
    if (mediaType == QStringLiteral("video"))
        return QStringLiteral("t2v");
    if (mediaType == QStringLiteral("image"))
        return QStringLiteral("t2i");

    const QString workflowPath = firstNonEmpty(profile.value(QStringLiteral("workflow_path")).toString(),
                                               profile.value(QStringLiteral("workflow_source")).toString(),
                                               profile.value(QStringLiteral("name")).toString(),
                                               profile.value(QStringLiteral("profile_name")).toString()).toLower();

    for (const QString &candidate : {QStringLiteral("i2v"), QStringLiteral("t2v"), QStringLiteral("i2i"), QStringLiteral("t2i")})
    {
        if (workflowPath.contains(candidate))
            return candidate;
    }

    return QStringLiteral("t2i");
}

QString inferModeFromOutput(const QString &path, const QJsonObject &metadata)
{
    const QString metaTask = normalizedModeId(firstNonEmpty(metadata.value(QStringLiteral("task_type")).toString(),
                                                            metadata.value(QStringLiteral("task_command")).toString(),
                                                            metadata.value(QStringLiteral("workflow_task_command")).toString()));
    if (!metaTask.isEmpty())
        return metaTask;

    const QString lowerPath = QDir::fromNativeSeparators(path).toLower();
    for (const QString &candidate : {QStringLiteral("i2v"), QStringLiteral("t2v"), QStringLiteral("i2i"), QStringLiteral("t2i")})
    {
        if (lowerPath.contains(QStringLiteral("/%1/").arg(candidate)))
            return candidate;
    }

    if (lowerPath.contains(QStringLiteral("/workflows/")))
    {
        const QString mediaType = metadata.value(QStringLiteral("workflow_media_type")).toString().trimmed().toLower();
        if (mediaType == QStringLiteral("video"))
            return QStringLiteral("t2v");
        if (mediaType == QStringLiteral("image"))
            return QStringLiteral("t2i");
    }

    return QStringLiteral("t2i");
}

HomeStarterPreview defaultStarterPreview()
{
    HomeStarterPreview preview;
    preview.modeId = QStringLiteral("t2i");
    return preview;
}

QVector<HomeWorkflowCard> fallbackWorkflowCards()
{
    return {
        {QStringLiteral("RECENT WORKFLOW"),
         QStringLiteral("Stylized Portraits"),
         QStringLiteral("Portrait starter with polished composition and lighting cues."),
         QStringLiteral("t2i"),
         QStringLiteral("Workflow"),
         QStringLiteral("Preview in Hero"),
         0.18},
        {QStringLiteral("IMPORTED WORKFLOW"),
         QStringLiteral("Fantasy Art Generator"),
         QStringLiteral("Broad fantasy preset that primes the hero without leaving Home."),
         QStringLiteral("t2i"),
         QStringLiteral("Workflow"),
         QStringLiteral("Preview in Hero"),
         0.52}
    };
}

QVector<HomeRecentOutputCard> fallbackRecentOutputCards()
{
    return {
        {QStringLiteral("Character Portrait"),
         QStringLiteral("Send this still back into I2I for refinement."),
         QStringLiteral("i2i"),
         QStringLiteral("history"),
         0.08},
        {QStringLiteral("Open Landscape"),
         QStringLiteral("Route the world concept into T2V or open it for review."),
         QStringLiteral("t2v"),
         QStringLiteral("history"),
         0.32},
        {QStringLiteral("Motion Test"),
         QStringLiteral("Inspect the sequence and reopen the motion workspace."),
         QStringLiteral("i2v"),
         QStringLiteral("history"),
         0.58}
    };
}

QVector<HomeFavoriteCard> fallbackFavoriteCards()
{
    return {
        {QStringLiteral("FAVORITE"),
         QStringLiteral("Portrait Armor"),
         QStringLiteral("Character concept starter with cinematic edge lighting."),
         QStringLiteral("t2i"),
         QStringLiteral("Favorite"),
         QStringLiteral("Preview in Hero"),
         0.10},
        {QStringLiteral("FAVORITE"),
         QStringLiteral("Open Landscape"),
         QStringLiteral("Environment mood starter for wide world concepts."),
         QStringLiteral("t2v"),
         QStringLiteral("Favorite"),
         QStringLiteral("Preview in Hero"),
         0.35},
        {QStringLiteral("FAVORITE"),
         QStringLiteral("Sci-Fi City"),
         QStringLiteral("Urban neon starting point for future-world sequences."),
         QStringLiteral("t2v"),
         QStringLiteral("Favorite"),
         QStringLiteral("Preview in Hero"),
         0.64}
    };
}

qreal cardPhaseForIndex(int index)
{
    static const qreal phases[] = {0.08, 0.18, 0.32, 0.52, 0.64, 0.78};
    return phases[index % (sizeof(phases) / sizeof(phases[0]))];
}

QVector<HomeWorkflowCard> loadWorkflowCardsFromDisk(const QString &projectRoot)
{
    const QString rootPath = importedWorkflowsRoot(projectRoot);
    if (!QDir(rootPath).exists())
        return {};

    QStringList profilePaths;
    QDirIterator it(rootPath, {QStringLiteral("profile.json")}, QDir::Files, QDirIterator::Subdirectories);
    while (it.hasNext())
        profilePaths.push_back(QDir::fromNativeSeparators(it.next()));

    std::sort(profilePaths.begin(), profilePaths.end(), [](const QString &lhs, const QString &rhs) {
        return QFileInfo(lhs).lastModified() > QFileInfo(rhs).lastModified();
    });

    QVector<HomeWorkflowCard> cards;
    const int maxCards = 3;
    for (const QString &profilePath : profilePaths)
    {
        const QJsonObject profile = readJsonObjectFromFile(profilePath);
        if (profile.isEmpty())
            continue;

        HomeWorkflowCard card;
        const QString modeId = inferModeFromWorkflowProfile(profile);
        const QString name = firstNonEmpty(profile.value(QStringLiteral("profile_name")).toString(),
                                           profile.value(QStringLiteral("name")).toString(),
                                           QFileInfo(profilePath).dir().dirName(),
                                           QStringLiteral("Imported Workflow"));

        const QString task = firstNonEmpty(profile.value(QStringLiteral("task_command")).toString(),
                                           profile.value(QStringLiteral("workflow_task_command")).toString(),
                                           profile.value(QStringLiteral("task_type")).toString(),
                                           QStringLiteral("workflow"));
        const QString backend = firstNonEmpty(profile.value(QStringLiteral("backend_kind")).toString(),
                                              QStringLiteral("comfy_workflow"));
        const QString mediaType = profile.value(QStringLiteral("media_type")).toString().trimmed();
        const int missingNodes = profile.value(QStringLiteral("metadata")).toObject()
                                     .value(QStringLiteral("missing_custom_nodes")).toArray().size();

        QStringList bodyParts;
        bodyParts << QStringLiteral("%1 • %2").arg(displayModeName(modeId), task);
        if (!mediaType.isEmpty())
            bodyParts << QStringLiteral("media: %1").arg(mediaType);
        if (!backend.isEmpty())
            bodyParts << QStringLiteral("backend: %1").arg(backend);
        if (missingNodes > 0)
            bodyParts << QStringLiteral("%1 missing node%2").arg(missingNodes).arg(missingNodes == 1 ? QString() : QStringLiteral("s"));

        card.eyebrow = cards.isEmpty() ? QStringLiteral("RECENT WORKFLOW") : QStringLiteral("IMPORTED WORKFLOW");
        card.title = name;
        card.body = bodyParts.join(QStringLiteral(" · "));
        card.modeId = modeId;
        card.sourceLabel = QStringLiteral("Workflow");
        card.actionLabel = QStringLiteral("Preview in Hero");
        card.phase = cardPhaseForIndex(cards.size());
        cards.push_back(card);

        if (cards.size() >= maxCards)
            break;
    }

    return cards;
}

QJsonObject loadSidecarMetadata(const QString &mediaPath)
{
    const QFileInfo info(mediaPath);
    const QString metadataPath = info.dir().filePath(info.completeBaseName() + QStringLiteral(".json"));
    return readJsonObjectFromFile(metadataPath);
}

bool isOutputMediaFile(const QFileInfo &info)
{
    const QString suffix = info.suffix().trimmed().toLower();
    static const QStringList allowed = {
        QStringLiteral("png"),
        QStringLiteral("jpg"),
        QStringLiteral("jpeg"),
        QStringLiteral("webp"),
        QStringLiteral("bmp"),
        QStringLiteral("gif"),
        QStringLiteral("mp4"),
        QStringLiteral("mov"),
        QStringLiteral("webm"),
        QStringLiteral("mkv"),
    };
    return allowed.contains(suffix);
}

QVector<HomeRecentOutputCard> loadRecentOutputsFromDisk(const QString &projectRoot)
{
    const QString rootPath = outputsRoot(projectRoot);
    if (!QDir(rootPath).exists())
        return {};

    QStringList mediaPaths;
    QDirIterator it(rootPath, QDir::Files, QDirIterator::Subdirectories);
    while (it.hasNext())
    {
        const QString path = QDir::fromNativeSeparators(it.next());
        const QFileInfo info(path);
        if (!isOutputMediaFile(info))
            continue;
        mediaPaths.push_back(path);
    }

    std::sort(mediaPaths.begin(), mediaPaths.end(), [](const QString &lhs, const QString &rhs) {
        return QFileInfo(lhs).lastModified() > QFileInfo(rhs).lastModified();
    });

    QVector<HomeRecentOutputCard> cards;
    const int maxCards = 3;
    for (const QString &mediaPath : mediaPaths)
    {
        const QFileInfo info(mediaPath);
        const QJsonObject metadata = loadSidecarMetadata(mediaPath);
        const QString modeId = inferModeFromOutput(mediaPath, metadata);
        const QString relativeDir = QDir(projectRoot).relativeFilePath(info.absolutePath());
        const QString workflowName = metadata.value(QStringLiteral("workflow_profile_name")).toString().trimmed();

        QStringList bodyParts;
        if (!workflowName.isEmpty())
            bodyParts << workflowName;
        bodyParts << QStringLiteral("%1 result").arg(displayModeName(modeId));
        bodyParts << QDir::toNativeSeparators(relativeDir);
        bodyParts << info.lastModified().toString(QStringLiteral("MMM d · h:mm ap"));

        HomeRecentOutputCard card;
        card.title = prettifyFileStem(info.completeBaseName());
        card.body = bodyParts.join(QStringLiteral(" · "));
        card.routeModeId = modeId;
        card.openManagerId = QStringLiteral("history");
        card.phase = cardPhaseForIndex(cards.size());
        cards.push_back(card);

        if (cards.size() >= maxCards)
            break;
    }

    return cards;
}

QVector<HomeFavoriteCard> loadFavoritesFromSettings(QSettings &settings)
{
    QString jsonText = settings.value(QStringLiteral("ui/home_dashboard/favorites_json")).toString().trimmed();
    if (jsonText.isEmpty())
        jsonText = settings.value(QStringLiteral("ui/home/favorites_json")).toString().trimmed();

    if (jsonText.isEmpty())
        return {};

    const QJsonDocument doc = QJsonDocument::fromJson(jsonText.toUtf8());
    if (!doc.isArray())
        return {};

    QVector<HomeFavoriteCard> cards;
    const QJsonArray array = doc.array();
    for (int i = 0; i < array.size(); ++i)
    {
        if (!array.at(i).isObject())
            continue;

        const QJsonObject obj = array.at(i).toObject();
        HomeFavoriteCard card;
        card.eyebrow = firstNonEmpty(obj.value(QStringLiteral("eyebrow")).toString(), QStringLiteral("FAVORITE"));
        card.title = obj.value(QStringLiteral("title")).toString().trimmed();
        card.body = obj.value(QStringLiteral("body")).toString().trimmed();
        card.modeId = normalizedModeId(obj.value(QStringLiteral("modeId")).toString());
        card.sourceLabel = firstNonEmpty(obj.value(QStringLiteral("sourceLabel")).toString(), QStringLiteral("Favorite"));
        card.actionLabel = firstNonEmpty(obj.value(QStringLiteral("actionLabel")).toString(), QStringLiteral("Preview in Hero"));
        card.phase = obj.value(QStringLiteral("phase")).toDouble(cardPhaseForIndex(cards.size()));

        if (card.title.isEmpty() || card.modeId.isEmpty())
            continue;
        if (card.body.isEmpty())
            card.body = QStringLiteral("%1 starter").arg(displayModeName(card.modeId));

        cards.push_back(card);
    }

    return cards;
}

HomeStarterPreview loadHeroPreviewFromSettings(QSettings &settings)
{
    QString jsonText = settings.value(QStringLiteral("ui/home_dashboard/hero_preview_json")).toString().trimmed();
    if (jsonText.isEmpty())
        jsonText = settings.value(QStringLiteral("ui/home/hero_preview_json")).toString().trimmed();

    if (jsonText.isEmpty())
        return {};

    const QJsonDocument doc = QJsonDocument::fromJson(jsonText.toUtf8());
    if (!doc.isObject())
        return {};

    const QJsonObject obj = doc.object();
    HomeStarterPreview preview;
    preview.title = obj.value(QStringLiteral("title")).toString().trimmed();
    preview.subtitle = obj.value(QStringLiteral("subtitle")).toString().trimmed();
    preview.modeId = normalizedModeId(obj.value(QStringLiteral("modeId")).toString());
    preview.sourceLabel = obj.value(QStringLiteral("sourceLabel")).toString().trimmed();
    return preview;
}

HomeFavoriteCard favoriteFromWorkflowCard(const HomeWorkflowCard &workflow, int index)
{
    HomeFavoriteCard favorite;
    favorite.eyebrow = QStringLiteral("WORKFLOW");
    favorite.title = workflow.title;
    favorite.body = workflow.body;
    favorite.modeId = workflow.modeId;
    favorite.sourceLabel = firstNonEmpty(workflow.sourceLabel, QStringLiteral("Workflow"));
    favorite.actionLabel = firstNonEmpty(workflow.actionLabel, QStringLiteral("Preview in Hero"));
    favorite.phase = cardPhaseForIndex(index);
    return favorite;
}

HomeStarterPreview starterPreviewFromFavorite(const HomeFavoriteCard &favorite)
{
    HomeStarterPreview preview;
    preview.title = favorite.title;
    preview.subtitle = favorite.body;
    preview.modeId = favorite.modeId;
    preview.sourceLabel = favorite.sourceLabel;
    return preview;
}

HomeStarterPreview starterPreviewFromWorkflow(const HomeWorkflowCard &workflow)
{
    HomeStarterPreview preview;
    preview.title = workflow.title;
    preview.subtitle = workflow.body;
    preview.modeId = workflow.modeId;
    preview.sourceLabel = workflow.sourceLabel;
    return preview;
}

} // namespace

HomePage::HomePage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("HomePage"));

    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);
    outer->setSpacing(0);

    scrollArea_ = new QScrollArea(this);
    scrollArea_->setWidgetResizable(true);
    scrollArea_->setFrameShape(QFrame::NoFrame);
    scrollArea_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    outer->addWidget(scrollArea_);

    dashboardPage_ = new HomeDashboardPage(scrollArea_);
    scrollArea_->setWidget(dashboardPage_);

    dashboardSettings_ = new HomeDashboardSettings(this);
    loadDashboardConfig();

    connect(dashboardPage_, &HomeDashboardPage::modeRequested, this, &HomePage::modeRequested);
    connect(dashboardPage_, &HomeDashboardPage::managerRequested, this, &HomePage::managerRequested);
    connect(dashboardPage_, &HomeDashboardPage::launchRequested, this, &HomePage::launchRequested);
    connect(dashboardPage_, &HomeDashboardPage::configEdited, this, [this](const HomeDashboardConfig &config) {
        config_ = config;
        if (dashboardSettings_)
            dashboardSettings_->save(config_);
        emit dashboardConfigChanged(config_);
    });

    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &HomePage::applyTheme);

    refreshAppDataSources(true);
}

void HomePage::setRuntimeSummary(const QString &runtimeName,
                                 int runningCount,
                                 int pendingCount,
                                 int errorCount,
                                 const QString &vramText,
                                 const QString &modelText,
                                 const QString &loraText,
                                 const QString &progressText,
                                 int progressPercent)
{
    if (!dashboardPage_)
        return;

    HomeRuntimeSummary summary;
    summary.runtimeName = runtimeName;
    summary.runningCount = runningCount;
    summary.pendingCount = pendingCount;
    summary.errorCount = errorCount;
    summary.vramText = vramText;
    summary.modelText = modelText;
    summary.loraText = loraText;
    summary.progressText = progressText;
    summary.progressPercent = progressPercent;
    dashboardPage_->setRuntimeSummary(summary);
}

void HomePage::setDashboardConfig(const HomeDashboardConfig &config)
{
    if (!dashboardPage_)
        return;

    config_ = isValidHomeDashboardConfig(config)
                  ? config
                  : defaultHomeDashboardConfig(HomeDashboardPreset::CinematicStudio);
    dashboardPage_->setConfig(config_);

    if (dashboardSettings_)
        dashboardSettings_->save(config_);

    emit dashboardConfigChanged(config_);
}

HomeDashboardConfig HomePage::dashboardConfig() const
{
    return config_;
}

void HomePage::setCustomizeMode(bool enabled)
{
    if (!dashboardPage_)
        return;
    dashboardPage_->setCustomizeMode(enabled);
}

bool HomePage::isCustomizeMode() const
{
    return dashboardPage_ && dashboardPage_->isCustomizeMode();
}

void HomePage::setHeroStarterPreview(const HomeStarterPreview &preview)
{
    if (dashboardPage_)
        dashboardPage_->setHeroStarterPreview(preview);
}

void HomePage::setWorkflowCards(const QVector<HomeWorkflowCard> &cards)
{
    if (dashboardPage_)
        dashboardPage_->setWorkflowCards(cards);
}

void HomePage::setRecentOutputCards(const QVector<HomeRecentOutputCard> &cards)
{
    if (dashboardPage_)
        dashboardPage_->setRecentOutputCards(cards);
}

void HomePage::setFavoriteCards(const QVector<HomeFavoriteCard> &cards)
{
    if (dashboardPage_)
        dashboardPage_->setFavoriteCards(cards);
}

void HomePage::resetDashboardContentToDefaults()
{
    if (dashboardPage_)
        dashboardPage_->resetContentToDefaults();
}

void HomePage::refreshAppDataSources(bool refreshHeroPreview)
{
    if (!dashboardPage_)
        return;

    const QString projectRoot = resolveProjectRoot();
    QSettings settings;

    QVector<HomeWorkflowCard> workflowCards = loadWorkflowCardsFromDisk(projectRoot);
    QVector<HomeRecentOutputCard> recentOutputCards = loadRecentOutputsFromDisk(projectRoot);
    QVector<HomeFavoriteCard> favoriteCards = loadFavoritesFromSettings(settings);

    if (workflowCards.isEmpty())
        workflowCards = fallbackWorkflowCards();
    if (recentOutputCards.isEmpty())
        recentOutputCards = fallbackRecentOutputCards();

    if (favoriteCards.isEmpty())
    {
        for (int index = 0; index < workflowCards.size() && favoriteCards.size() < 3; ++index)
            favoriteCards.push_back(favoriteFromWorkflowCard(workflowCards[index], index));
    }
    if (favoriteCards.isEmpty())
        favoriteCards = fallbackFavoriteCards();

    setWorkflowCards(workflowCards);
    setRecentOutputCards(recentOutputCards);
    setFavoriteCards(favoriteCards);

    if (refreshHeroPreview || !appDataInitialized_)
    {
        HomeStarterPreview heroPreview = loadHeroPreviewFromSettings(settings);
        if (heroPreview.modeId.trimmed().isEmpty())
        {
            if (!favoriteCards.isEmpty())
                heroPreview = starterPreviewFromFavorite(favoriteCards.first());
            else if (!workflowCards.isEmpty())
                heroPreview = starterPreviewFromWorkflow(workflowCards.first());
            else
                heroPreview = defaultStarterPreview();
        }

        setHeroStarterPreview(heroPreview);
    }

    appDataInitialized_ = true;
}

void HomePage::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    refreshAppDataSources(false);
}

void HomePage::loadDashboardConfig()
{
    if (!dashboardSettings_ || !dashboardPage_)
        return;

    config_ = dashboardSettings_->load();
    dashboardPage_->setConfig(config_);
}

void HomePage::applyTheme()
{
    setStyleSheet(ThemeManager::instance().homePageStyleSheet());
}
