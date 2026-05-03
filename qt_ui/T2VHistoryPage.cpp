#include "T2VHistoryPage.h"

#include "ThemeManager.h"

#include <QAbstractItemView>
#include <QApplication>
#include <QClipboard>
#include <QComboBox>
#include <QDateTime>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QSaveFile>
#include <QProcess>
#include <QTimer>
#include <QTableView>
#include <QItemSelectionModel>
#include <QAbstractItemModel>
#include <QCoreApplication>
#include <QMessageBox>
#include <QGuiApplication>
#include <QtGlobal>
#include <QSet>
#include <QProcessEnvironment>
#include <QFileInfo>
#include <QFrame>
#include <QHeaderView>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QJsonValue>
#include <QIODevice>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QUrl>
#include <QVBoxLayout>
#include <QHBoxLayout>

namespace
{

QJsonObject firstObjectFromArray(const QJsonArray &array)
{
    for (const QJsonValue &value : array)
    {
        if (value.isObject())
            return value.toObject();
    }

    return {};
}

QString stringFromObjectPath(const QJsonObject &object, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QString value = object.value(key).toString();
        if (!value.isEmpty())
            return value;
    }

    return {};
}

qint64 int64FromObjectPath(const QJsonObject &object, const QStringList &keys, qint64 fallback = 0)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = object.value(key);
        if (value.isDouble())
            return static_cast<qint64>(value.toDouble());
    }

    return fallback;
}

QString latestLtxRequeueUiContractPath()
{
    const QString root = QDir(QStringLiteral("D:/AI_ASSETS/comfy_runtime/spellvision_registry/ui")).absolutePath();
    QDir().mkpath(root);
    return QDir(root).filePath(QStringLiteral("latest_ltx_requeue_queue_preview_contract.json"));
}



bool rowContainsNeedle(const QAbstractItemModel *model, int row, const QStringList &needles)
{
    if (!model || row < 0)
        return false;

    for (int column = 0; column < model->columnCount(); ++column)
    {
        const QString value = model->index(row, column).data(Qt::DisplayRole).toString();

        for (const QString &needle : needles)
        {
            if (needle.isEmpty())
                continue;

            if (value.contains(needle, Qt::CaseInsensitive))
                return true;
        }
    }

    return false;
}

QString fileNameFromPathText(const QString &pathText)
{
    if (pathText.isEmpty())
        return {};

    return QFileInfo(pathText).fileName();
}



QString spellVisionRepoRootForWorkerClient()
{
    const QString current = QDir::currentPath();
    if (QFileInfo::exists(QDir(current).filePath(QStringLiteral("python/worker_client.py"))))
        return current;

    QDir appDir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 8; ++i)
    {
        if (QFileInfo::exists(appDir.filePath(QStringLiteral("python/worker_client.py"))))
            return appDir.absolutePath();

        if (!appDir.cdUp())
            break;
    }

    return current;
}

QString spellVisionPythonExecutable(const QString &repoRoot)
{
#ifdef Q_OS_WIN
    const QString venvPython = QDir(repoRoot).filePath(QStringLiteral(".venv/Scripts/python.exe"));
#else
    const QString venvPython = QDir(repoRoot).filePath(QStringLiteral(".venv/bin/python"));
#endif

    if (QFileInfo::exists(venvPython))
        return venvPython;

    return QStringLiteral("python");
}

QJsonObject parseLastJsonObjectFromProcessOutput(const QByteArray &output, QString *errorMessage = nullptr)
{
    const QList<QByteArray> lines = output.split('\n');

    for (int i = lines.size() - 1; i >= 0; --i)
    {
        const QByteArray trimmed = lines.at(i).trimmed();
        if (trimmed.isEmpty())
            continue;

        QJsonParseError parseError;
        const QJsonDocument document = QJsonDocument::fromJson(trimmed, &parseError);
        if (parseError.error == QJsonParseError::NoError && document.isObject())
            return document.object();
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(output, &parseError);
    if (parseError.error == QJsonParseError::NoError && document.isObject())
        return document.object();

    if (errorMessage)
        *errorMessage = QStringLiteral("Could not parse worker response JSON.");

    return {};
}

QString safeRequeueSlug(QString value)
{
    value = value.trimmed();
    if (value.isEmpty())
        value = QStringLiteral("ltx-history-requeue");

    value.replace(QRegularExpression(QStringLiteral("[^A-Za-z0-9_\\-]+")), QStringLiteral("_"));
    value = value.left(96);

    if (value.isEmpty())
        value = QStringLiteral("ltx-history-requeue");

    return value;
}

QString ltxRequeueDraftRoot()
{
    const QProcessEnvironment env = QProcessEnvironment::systemEnvironment();

    const QString explicitPath = env.value(QStringLiteral("SPELLVISION_LTX_REQUEUE_ROOT")).trimmed();
    if (!explicitPath.isEmpty())
        return QDir::fromNativeSeparators(explicitPath);

    const QString runtimeRoot = env.value(QStringLiteral("SPELLVISION_COMFY_RUNTIME_ROOT")).trimmed();
    if (!runtimeRoot.isEmpty())
    {
        return QDir(QDir::fromNativeSeparators(runtimeRoot))
            .filePath(QStringLiteral("spellvision_registry/requeue/ltx"));
    }

    const QString assetRoot = env.value(QStringLiteral("SPELLVISION_ASSET_ROOT")).trimmed();
    if (!assetRoot.isEmpty())
    {
        return QDir(QDir::fromNativeSeparators(assetRoot))
            .filePath(QStringLiteral("comfy_runtime/spellvision_registry/requeue/ltx"));
    }

    return QStringLiteral("D:/AI_ASSETS/comfy_runtime/spellvision_registry/requeue/ltx");
}

QString requeuePromptIdFromRuntimeSummary(const QString &runtimeSummary)
{
    const QString marker = QStringLiteral("requeue-ready");
    const int markerIndex = runtimeSummary.indexOf(marker, 0, Qt::CaseInsensitive);
    if (markerIndex < 0)
        return QString();

    const QString tail = runtimeSummary.mid(markerIndex + marker.size()).trimmed();
    const QString cleaned = tail;
    const QRegularExpression uuidRegex(QStringLiteral("([0-9a-fA-F]{8}\\-[0-9a-fA-F]{4}\\-[0-9a-fA-F]{4}\\-[0-9a-fA-F]{4}\\-[0-9a-fA-F]{12})"));
    const QRegularExpressionMatch match = uuidRegex.match(cleaned);
    if (match.hasMatch())
        return match.captured(1);

    return QString();
}
QString firstRegistryString(const QJsonObject &obj, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QString value = obj.value(key).toString().trimmed();
        if (!value.isEmpty())
            return value;
    }
    return QString();
}

QJsonObject firstRegistryObject(const QJsonObject &obj, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = obj.value(key);
        if (value.isObject())
            return value.toObject();
    }
    return {};
}

QJsonArray firstRegistryArray(const QJsonObject &obj, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = obj.value(key);
        if (value.isArray())
            return value.toArray();
    }
    return {};
}

QString ltxRegistryHistoryPath()
{
    const QProcessEnvironment env = QProcessEnvironment::systemEnvironment();

    const QString explicitPath = env.value(QStringLiteral("SPELLVISION_LTX_HISTORY_RECORDS_JSONL")).trimmed();
    if (!explicitPath.isEmpty())
        return QDir::fromNativeSeparators(explicitPath);

    const QString runtimeRoot = env.value(QStringLiteral("SPELLVISION_COMFY_RUNTIME_ROOT")).trimmed();
    if (!runtimeRoot.isEmpty())
    {
        return QDir(QDir::fromNativeSeparators(runtimeRoot))
            .filePath(QStringLiteral("spellvision_registry/history/records.jsonl"));
    }

    const QString assetRoot = env.value(QStringLiteral("SPELLVISION_ASSET_ROOT")).trimmed();
    if (!assetRoot.isEmpty())
    {
        return QDir(QDir::fromNativeSeparators(assetRoot))
            .filePath(QStringLiteral("comfy_runtime/spellvision_registry/history/records.jsonl"));
    }

    return QStringLiteral("D:/AI_ASSETS/comfy_runtime/spellvision_registry/history/records.jsonl");
}

QString registryOutputPathFromRecord(const QJsonObject &record)
{
    const QString direct = firstRegistryString(record, {
        QStringLiteral("primary_output_path"),
        QStringLiteral("output_path"),
        QStringLiteral("video_path"),
        QStringLiteral("path"),
    });
    if (!direct.isEmpty())
        return direct;

    const QJsonObject primary = firstRegistryObject(record, {
        QStringLiteral("primary_output"),
        QStringLiteral("primary"),
    });

    const QString primaryPath = firstRegistryString(primary, {
        QStringLiteral("path"),
        QStringLiteral("preview_path"),
        QStringLiteral("output_path"),
    });
    if (!primaryPath.isEmpty())
        return primaryPath;

    const QJsonArray outputs = firstRegistryArray(record, {
        QStringLiteral("outputs"),
        QStringLiteral("ui_outputs"),
    });

    for (const QJsonValue &value : outputs)
    {
        if (!value.isObject())
            continue;

        const QJsonObject output = value.toObject();
        const QString role = output.value(QStringLiteral("role")).toString().trimmed().toLower();
        if (role != QStringLiteral("full"))
            continue;

        const QString path = firstRegistryString(output, {
            QStringLiteral("path"),
            QStringLiteral("preview_path"),
            QStringLiteral("output_path"),
        });
        if (!path.isEmpty())
            return path;
    }

    for (const QJsonValue &value : outputs)
    {
        if (!value.isObject())
            continue;

        const QJsonObject output = value.toObject();
        const QString path = firstRegistryString(output, {
            QStringLiteral("path"),
            QStringLiteral("preview_path"),
            QStringLiteral("output_path"),
        });
        if (!path.isEmpty())
            return path;
    }

    return QString();
}

QString registryMetadataPathFromRecord(const QJsonObject &record)
{
    const QString direct = firstRegistryString(record, {
        QStringLiteral("primary_metadata_path"),
        QStringLiteral("metadata_path"),
        QStringLiteral("metadata_output"),
    });
    if (!direct.isEmpty())
        return direct;

    const QJsonObject primary = firstRegistryObject(record, {
        QStringLiteral("primary_output"),
        QStringLiteral("primary"),
    });

    const QString primaryMetadata = firstRegistryString(primary, {
        QStringLiteral("metadata_path"),
        QStringLiteral("primary_metadata_path"),
        QStringLiteral("metadata_output"),
    });
    if (!primaryMetadata.isEmpty())
        return primaryMetadata;

    const QJsonArray outputs = firstRegistryArray(record, {
        QStringLiteral("outputs"),
        QStringLiteral("ui_outputs"),
    });

    for (const QJsonValue &value : outputs)
    {
        if (!value.isObject())
            continue;

        const QJsonObject output = value.toObject();
        const QString metadata = firstRegistryString(output, {
            QStringLiteral("metadata_path"),
            QStringLiteral("primary_metadata_path"),
            QStringLiteral("metadata_output"),
        });
        if (!metadata.isEmpty())
            return metadata;
    }

    const QString outputPath = registryOutputPathFromRecord(record);
    return outputPath.isEmpty() ? QString() : QStringLiteral("%1.spellvision.json").arg(outputPath);
}

QString compactPromptPreview(const QString &prompt)
{
    const QString compact = prompt.simplified();
    if (compact.size() <= 260)
        return compact;
    return compact.left(257) + QStringLiteral("...");
}

int registryIntValue(const QJsonObject &record, const QStringList &keys, int fallback = 0)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = record.value(key);
        if (value.isDouble())
            return value.toInt();
        if (value.isString())
        {
            bool ok = false;
            const int parsed = value.toString().trimmed().toInt(&ok);
            if (ok)
                return parsed;
        }
    }
    return fallback;
}

double registryDoubleValue(const QJsonObject &record, const QStringList &keys, double fallback = 0.0)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = record.value(key);
        if (value.isDouble())
            return value.toDouble();
        if (value.isString())
        {
            bool ok = false;
            const double parsed = value.toString().trimmed().toDouble(&ok);
            if (ok)
                return parsed;
        }
    }
    return fallback;
}

QString ltxResolutionLabel(const QJsonObject &record)
{
    const int width = registryIntValue(record, {QStringLiteral("width"), QStringLiteral("video_width")});
    const int height = registryIntValue(record, {QStringLiteral("height"), QStringLiteral("video_height")});

    if (width > 0 && height > 0)
        return QStringLiteral("%1x%2").arg(width).arg(height);

    return QStringLiteral("unknown");
}

QString ltxDurationLabel(const QJsonObject &record)
{
    const int frames = registryIntValue(record, {QStringLiteral("frames"), QStringLiteral("frame_count")});
    const double fps = registryDoubleValue(record, {QStringLiteral("fps"), QStringLiteral("frame_rate")});

    if (frames > 0 && fps > 0.0)
    {
        const double seconds = static_cast<double>(frames) / fps;
        return QStringLiteral("%1 frames @ %2 fps (%3s)")
            .arg(frames)
            .arg(QString::number(fps, 'f', fps == static_cast<int>(fps) ? 0 : 2))
            .arg(QString::number(seconds, 'f', 1));
    }

    if (frames > 0)
        return QStringLiteral("%1 frames").arg(frames);

    return QStringLiteral("LTX");
}

QString ltxFinishedLabel(const QJsonObject &record)
{
    const QString rawTimestamp = firstRegistryString(record, {
        QStringLiteral("registered_at"),
        QStringLiteral("created_at"),
        QStringLiteral("finished_at"),
        QStringLiteral("completed_at"),
    });

    if (rawTimestamp.isEmpty())
        return QStringLiteral("unknown");

    QDateTime parsed = QDateTime::fromString(rawTimestamp, Qt::ISODateWithMs);
    if (!parsed.isValid())
        parsed = QDateTime::fromString(rawTimestamp, Qt::ISODate);

    if (parsed.isValid())
        return parsed.toLocalTime().toString(QStringLiteral("MMM d, h:mm AP"));

    return rawTimestamp;
}

QString ltxRuntimeSummary(const QJsonObject &record)
{
    const QString promptId = firstRegistryString(record, {
        QStringLiteral("registry_prompt_id"),
        QStringLiteral("prompt_id"),
    });

    if (!promptId.isEmpty())
        return QStringLiteral("LTX registry • comfy_prompt_api • requeue-ready • %1").arg(promptId);

    return QStringLiteral("LTX registry • comfy_prompt_api • requeue-ready");
}


QString jsonText(const QJsonObject &obj, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QString value = obj.value(key).toString().trimmed();
        if (!value.isEmpty())
            return value;
    }
    return QString();
}

qint64 jsonInt64(const QJsonObject &obj, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = obj.value(key);
        if (value.isDouble())
            return static_cast<qint64>(value.toDouble());
    }
    return 0;
}

QString jsonStringList(const QJsonObject &obj, const QString &key)
{
    const QJsonValue value = obj.value(key);
    if (value.isArray())
    {
        QStringList parts;
        const QJsonArray array = value.toArray();
        for (const QJsonValue &entry : array)
        {
            const QString text = entry.toString().trimmed();
            if (!text.isEmpty())
                parts << text;
        }
        return parts.join(QStringLiteral("; "));
    }
    return value.toString().trimmed();
}

QTableWidgetItem *tableItem(const QString &text)
{
    auto *item = new QTableWidgetItem(text);
    item->setFlags(item->flags() & ~Qt::ItemIsEditable);
    return item;
}
}

T2VHistoryPage::T2VHistoryPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("T2VHistoryPage"));

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(16, 10, 16, 16);
    root->setSpacing(12);

    auto *hero = new QFrame(this);
    hero->setObjectName(QStringLiteral("HistoryHeroCard"));
    auto *heroLayout = new QVBoxLayout(hero);
    heroLayout->setContentsMargins(20, 16, 20, 16);
    heroLayout->setSpacing(8);

    auto *eyebrow = new QLabel(QStringLiteral("Video History"), hero);
    eyebrow->setObjectName(QStringLiteral("HistoryEyebrow"));

    auto *title = new QLabel(QStringLiteral("T2V History Browser"), hero);
    title->setObjectName(QStringLiteral("HistoryTitle"));

    auto *subtitle = new QLabel(QStringLiteral("Review persisted Wan T2V outputs from the local history index. Select a row to inspect the prompt, stack, runtime, output contract, and metadata state."), hero);
    subtitle->setObjectName(QStringLiteral("HistorySubtitle"));
    subtitle->setWordWrap(true);

    auto *filters = new QHBoxLayout;
    filters->setSpacing(8);

    searchEdit_ = new QLineEdit(hero);
    searchEdit_->setObjectName(QStringLiteral("HistorySearch"));
    searchEdit_->setPlaceholderText(QStringLiteral("Search prompt, stack, model, path..."));
    connect(searchEdit_, &QLineEdit::textChanged, this, &T2VHistoryPage::applyFilters);

    contractFilterCombo_ = new QComboBox(hero);
    contractFilterCombo_->setObjectName(QStringLiteral("HistoryFilterCombo"));
    contractFilterCombo_->addItems({QStringLiteral("All"), QStringLiteral("OK"), QStringLiteral("Needs Review")});
    connect(contractFilterCombo_, &QComboBox::currentTextChanged, this, &T2VHistoryPage::applyFilters);

    filters->addWidget(searchEdit_, 1);
    filters->addWidget(contractFilterCombo_, 0);

    auto *actions = new QHBoxLayout;
    actions->setSpacing(8);
    summaryLabel_ = new QLabel(QStringLiteral("No video history loaded yet."), hero);
    summaryLabel_->setObjectName(QStringLiteral("HistorySummary"));
    summaryLabel_->setWordWrap(true);

    refreshButton_ = new QPushButton(QStringLiteral("Refresh"), hero);
    refreshButton_->setObjectName(QStringLiteral("HistoryActionButton"));
    connect(refreshButton_, &QPushButton::clicked, this, &T2VHistoryPage::refreshHistory);

    actions->addWidget(summaryLabel_, 1);
    actions->addWidget(refreshButton_, 0, Qt::AlignRight);

    heroLayout->addWidget(eyebrow);
    heroLayout->addWidget(title);
    heroLayout->addWidget(subtitle);
    heroLayout->addLayout(filters);
    heroLayout->addLayout(actions);
    root->addWidget(hero);

    auto *content = new QFrame(this);
    content->setObjectName(QStringLiteral("HistoryContentCard"));
    auto *contentLayout = new QHBoxLayout(content);
    contentLayout->setContentsMargins(14, 14, 14, 14);
    contentLayout->setSpacing(14);

    table_ = new QTableWidget(content);
    table_->setObjectName(QStringLiteral("HistoryTable"));
    table_->setColumnCount(6);
    table_->setHorizontalHeaderLabels({QStringLiteral("Finished"),
                                       QStringLiteral("Prompt"),
                                       QStringLiteral("Duration"),
                                       QStringLiteral("Resolution"),
                                       QStringLiteral("Stack"),
                                       QStringLiteral("Contract")});
    table_->verticalHeader()->setVisible(false);
    table_->horizontalHeader()->setStretchLastSection(false);
    table_->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    table_->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    table_->horizontalHeader()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    table_->horizontalHeader()->setSectionResizeMode(3, QHeaderView::ResizeToContents);
    table_->horizontalHeader()->setSectionResizeMode(4, QHeaderView::ResizeToContents);
    table_->horizontalHeader()->setSectionResizeMode(5, QHeaderView::ResizeToContents);
    table_->setSelectionBehavior(QAbstractItemView::SelectRows);
    table_->setSelectionMode(QAbstractItemView::SingleSelection);
    table_->setAlternatingRowColors(true);
    table_->setShowGrid(false);
    connect(table_, &QTableWidget::itemSelectionChanged, this, &T2VHistoryPage::handleSelectionChanged);

    emptyStateLabel_ = new QLabel(QStringLiteral("No T2V history entries match the current filters."), content);
    emptyStateLabel_->setObjectName(QStringLiteral("HistoryEmptyState"));
    emptyStateLabel_->setAlignment(Qt::AlignCenter);
    emptyStateLabel_->setWordWrap(true);
    emptyStateLabel_->hide();

    auto *tableStack = new QVBoxLayout;
    tableStack->setContentsMargins(0, 0, 0, 0);
    tableStack->setSpacing(8);
    tableStack->addWidget(table_);
    tableStack->addWidget(emptyStateLabel_);

    auto *details = new QFrame(content);
    details->setObjectName(QStringLiteral("HistoryDetailsCard"));
    details->setMinimumWidth(330);
    auto *detailsLayout = new QVBoxLayout(details);
    detailsLayout->setContentsMargins(14, 14, 14, 14);
    detailsLayout->setSpacing(8);

    detailsTitleLabel_ = new QLabel(QStringLiteral("Select a video"), details);
    detailsTitleLabel_->setObjectName(QStringLiteral("HistoryDetailsTitle"));
    detailsTitleLabel_->setWordWrap(true);

    detailsStatusLabel_ = new QLabel(QStringLiteral("No selection"), details);
    detailsStatusLabel_->setObjectName(QStringLiteral("HistoryDetailsStatus"));
    detailsStatusLabel_->setWordWrap(true);

    detailsBodyLabel_ = new QLabel(QStringLiteral("Choose a completed T2V result to inspect its prompt preview, Wan low/high stack, runtime reuse mode, and final output contract."), details);
    detailsBodyLabel_->setObjectName(QStringLiteral("HistoryDetailsBody"));
    detailsBodyLabel_->setWordWrap(true);
    detailsBodyLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);

    auto *detailActions = new QHBoxLayout;
    detailActions->setSpacing(8);
    openVideoButton_ = new QPushButton(QStringLiteral("Open Video"), details);
    openVideoButton_->setObjectName(QStringLiteral("HistoryActionButton"));
    revealFolderButton_ = new QPushButton(QStringLiteral("Reveal Folder"), details);
    revealFolderButton_->setObjectName(QStringLiteral("HistoryActionButton"));
    copyPromptButton_ = new QPushButton(QStringLiteral("Copy Prompt"), details);
    copyPromptButton_->setObjectName(QStringLiteral("HistoryActionButton"));
    copyMetadataPathButton_ = new QPushButton(QStringLiteral("Copy Metadata Path"), details);
    copyMetadataPathButton_->setObjectName(QStringLiteral("HistoryActionButton"));
    requeueButton_ = new QPushButton(QStringLiteral("Prepare Requeue"), details);
    requeueButton_->setObjectName(QStringLiteral("HistoryActionButton"));
    validateRequeueButton_ = new QPushButton(QStringLiteral("Validate Requeue"), details);
    validateRequeueButton_->setObjectName(QStringLiteral("HistoryActionButton"));
    submitRequeueButton_ = new QPushButton(QStringLiteral("Submit Requeue"), details);
    submitRequeueButton_->setObjectName(QStringLiteral("HistoryActionButton"));
    submitRequeueButton_->setEnabled(false);
    connect(openVideoButton_, &QPushButton::clicked, this, &T2VHistoryPage::openSelectedVideo);
    connect(revealFolderButton_, &QPushButton::clicked, this, &T2VHistoryPage::revealSelectedVideo);
    connect(copyPromptButton_, &QPushButton::clicked, this, &T2VHistoryPage::copySelectedPrompt);
    connect(copyMetadataPathButton_, &QPushButton::clicked, this, &T2VHistoryPage::copySelectedMetadataPath);
    connect(requeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::prepareSelectedLtxRequeueDraft);
    connect(validateRequeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::validateSelectedLtxRequeueDraft);
    connect(submitRequeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::submitSelectedLtxRequeueDraft);
    detailActions->addWidget(openVideoButton_);
    detailActions->addWidget(revealFolderButton_);

    auto *copyActions = new QHBoxLayout;
    copyActions->setSpacing(8);
    copyActions->addWidget(copyPromptButton_);
    copyActions->addWidget(copyMetadataPathButton_);
    copyActions->addWidget(requeueButton_);
    copyActions->addWidget(validateRequeueButton_);
    copyActions->addWidget(submitRequeueButton_);

    detailsLayout->addWidget(detailsTitleLabel_);
    detailsLayout->addWidget(detailsStatusLabel_);
    detailsLayout->addWidget(detailsBodyLabel_, 1);
    detailsLayout->addLayout(detailActions);
    detailsLayout->addLayout(copyActions);

    contentLayout->addLayout(tableStack, 3);
    contentLayout->addWidget(details, 2);
    root->addWidget(content, 1);

    updateEmptyDetails();
    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &T2VHistoryPage::applyTheme);
}

void T2VHistoryPage::setProjectRoot(const QString &projectRoot)
{
    projectRoot_ = projectRoot;
    refreshHistory();
}

void T2VHistoryPage::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    refreshHistory();
}

QString T2VHistoryPage::historyIndexPath() const
{
    if (projectRoot_.trimmed().isEmpty())
        return QString();
    return QDir(projectRoot_).filePath(QStringLiteral("runtime/history/video_history_index.json"));
}


QList<T2VHistoryPage::VideoHistoryItem> T2VHistoryPage::loadLtxRegistryHistoryItems() const
{
    QList<VideoHistoryItem> loaded;

    const QString path = ltxRegistryHistoryPath();
    if (path.trimmed().isEmpty())
        return loaded;

    QFile file(path);
    if (!file.exists() || !file.open(QIODevice::ReadOnly | QIODevice::Text))
        return loaded;

    while (!file.atEnd())
    {
        const QByteArray line = file.readLine().trimmed();
        if (line.isEmpty())
            continue;

        QJsonParseError parseError;
        const QJsonDocument document = QJsonDocument::fromJson(line, &parseError);
        if (parseError.error != QJsonParseError::NoError || !document.isObject())
            continue;

        const QJsonObject record = document.object();
        const QString family = record.value(QStringLiteral("family")).toString().trimmed().toLower();
        const QString taskType = record.value(QStringLiteral("task_type")).toString().trimmed().toLower();

        if (!family.isEmpty() && family != QStringLiteral("ltx"))
            continue;
        if (!taskType.isEmpty() && taskType != QStringLiteral("t2v"))
            continue;

        const QString outputPath = QDir::fromNativeSeparators(registryOutputPathFromRecord(record));
        if (outputPath.isEmpty())
            continue;

        const QString metadataPath = QDir::fromNativeSeparators(registryMetadataPathFromRecord(record));
        const QFileInfo outputInfo(outputPath);
        const QFileInfo metadataInfo(metadataPath);

        VideoHistoryItem item;
        item.promptPreview = compactPromptPreview(firstRegistryString(record, {
            QStringLiteral("prompt"),
            QStringLiteral("summary"),
            QStringLiteral("title"),
        }));
        item.lowModelName = firstRegistryString(record, {
            QStringLiteral("model"),
            QStringLiteral("video_primary_model_name"),
        });
        item.highModelName = QStringLiteral("LTX Prompt API");
        item.stackSummary = item.lowModelName.isEmpty()
                                ? QStringLiteral("LTX Prompt API")
                                : QStringLiteral("LTX • %1").arg(item.lowModelName);
        item.outputPath = outputPath;
        item.metadataPath = metadataPath;
        item.durationLabel = ltxDurationLabel(record);
        item.resolution = ltxResolutionLabel(record);
        item.runtimeSummary = ltxRuntimeSummary(record);
        item.outputExists = outputInfo.exists() && outputInfo.isFile();
        item.metadataExists = metadataInfo.exists() && metadataInfo.isFile();
        item.outputFileSizeBytes = item.outputExists ? outputInfo.size() : 0;
        item.metadataStatus = item.metadataExists ? QStringLiteral("Metadata written") : QStringLiteral("Metadata missing");
        item.outputContractOk = item.outputExists && item.metadataExists;
        item.outputContractStatus = item.outputContractOk ? QStringLiteral("OK") : QStringLiteral("Needs review");

        QStringList warnings;
        if (!item.outputExists)
            warnings << QStringLiteral("Output missing");
        if (!item.metadataExists)
            warnings << QStringLiteral("Metadata missing");
        item.outputContractWarnings = warnings.join(QStringLiteral("; "));

        loaded.prepend(item);
    }

    return loaded;
}

void T2VHistoryPage::mergeLtxRegistryHistoryItems(QList<VideoHistoryItem> &items) const
{
    const QList<VideoHistoryItem> ltxItems = loadLtxRegistryHistoryItems();
    if (ltxItems.isEmpty())
        return;

    QSet<QString> knownOutputPaths;
    for (const VideoHistoryItem &item : items)
    {
        const QString path = QDir::fromNativeSeparators(item.outputPath).trimmed().toLower();
        if (!path.isEmpty())
            knownOutputPaths.insert(path);
    }

    QList<VideoHistoryItem> merged;
    for (const VideoHistoryItem &item : ltxItems)
    {
        const QString path = QDir::fromNativeSeparators(item.outputPath).trimmed().toLower();
        if (path.isEmpty() || knownOutputPaths.contains(path))
            continue;

        knownOutputPaths.insert(path);
        merged.append(item);
    }

    if (merged.isEmpty())
        return;

    for (int i = merged.size() - 1; i >= 0; --i)
        items.prepend(merged.at(i));
}


QList<T2VHistoryPage::VideoHistoryItem> T2VHistoryPage::loadHistoryItems()
{
    QList<VideoHistoryItem> loaded;
    loadErrorText_.clear();
    const QString path = historyIndexPath();
    if (path.isEmpty())
    {
        loadErrorText_ = QStringLiteral("Project root is not set yet.");
        return loaded;
    }

    QFile file(path);
    if (!file.exists())
    {
        loadErrorText_ = QStringLiteral("History index does not exist yet: %1").arg(QDir::toNativeSeparators(path));
        return loaded;
    }
    if (!file.open(QIODevice::ReadOnly))
    {
        loadErrorText_ = QStringLiteral("Unable to read history index: %1").arg(QDir::toNativeSeparators(path));
        return loaded;
    }

    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
    {
        loadErrorText_ = QStringLiteral("History index parse error: %1").arg(parseError.errorString());
        return loaded;
    }

    const QJsonArray items = doc.object().value(QStringLiteral("items")).toArray();
    for (int i = items.size() - 1; i >= 0; --i)
    {
        const QJsonObject obj = items.at(i).toObject();
        if (obj.isEmpty())
            continue;

        VideoHistoryItem item;
        item.historyId = jsonText(obj, {QStringLiteral("history_id"), QStringLiteral("job_id")});
        item.jobId = obj.value(QStringLiteral("job_id")).toString().trimmed();
        item.command = jsonText(obj, {QStringLiteral("command"), QStringLiteral("task_type"), QStringLiteral("video_request_kind")});
        item.promptPreview = jsonText(obj, {QStringLiteral("prompt_preview"), QStringLiteral("prompt")});
        item.outputPath = jsonText(obj, {QStringLiteral("final_video_path"), QStringLiteral("final_output_path"), QStringLiteral("output_video"), QStringLiteral("video_path"), QStringLiteral("output")});
        item.metadataPath = jsonText(obj, {QStringLiteral("final_metadata_path"), QStringLiteral("metadata_output"), QStringLiteral("video_metadata_output")});
        item.finishedAt = jsonText(obj, {QStringLiteral("finished_at"), QStringLiteral("updated_at"), QStringLiteral("output_finalized_at")});
        item.durationLabel = obj.value(QStringLiteral("video_duration_label")).toString().trimmed();
        item.resolution = obj.value(QStringLiteral("video_resolution")).toString().trimmed();
        item.stackSummary = obj.value(QStringLiteral("video_model_stack_summary")).toString().trimmed();
        item.lowModelName = obj.value(QStringLiteral("video_low_model_name")).toString().trimmed();
        item.highModelName = obj.value(QStringLiteral("video_high_model_name")).toString().trimmed();
        item.outputExists = obj.value(QStringLiteral("output_exists")).toBool(false);
        item.metadataExists = obj.value(QStringLiteral("metadata_exists")).toBool(false);
        item.outputContractOk = obj.value(QStringLiteral("output_contract_ok")).toBool(false);
        item.outputFileSizeBytes = jsonInt64(obj, {QStringLiteral("output_file_size_bytes")});
        item.metadataStatus = obj.value(QStringLiteral("metadata_write_status")).toString().trimmed();
        item.outputContractWarnings = jsonStringList(obj, QStringLiteral("output_contract_warnings"));
        item.outputContractStatus = item.outputContractOk ? QStringLiteral("OK") : QStringLiteral("Needs review");
        if (obj.value(QStringLiteral("video_runtime_reused")).toBool(false))
            item.runtimeSummary = QStringLiteral("Video Warm Reuse");
        else if (obj.value(QStringLiteral("image_cache_unloaded_before_video")).toBool(false))
            item.runtimeSummary = QStringLiteral("Image → Video Cleanup");
        else if (obj.value(QStringLiteral("runtime_previous")).toString().compare(QStringLiteral("cold"), Qt::CaseInsensitive) == 0)
            item.runtimeSummary = QStringLiteral("Cold Start");
        else
            item.runtimeSummary = obj.value(QStringLiteral("runtime_transition")).toString().trimmed();

        if (item.outputPath.isEmpty())
            continue;
        loaded.append(item);
    }
    return loaded;
}

void T2VHistoryPage::refreshHistory()
{
    items_ = loadHistoryItems();
    mergeLtxRegistryHistoryItems(items_);
    applyFilters();
}

QString T2VHistoryPage::activeContractFilter() const
{
    return contractFilterCombo_ ? contractFilterCombo_->currentText().trimmed() : QStringLiteral("All");
}

bool T2VHistoryPage::itemMatchesFilters(const VideoHistoryItem &item) const
{
    const QString filter = activeContractFilter();
    if (filter == QStringLiteral("OK") && !item.outputContractOk)
        return false;
    if (filter == QStringLiteral("Needs Review") && item.outputContractOk)
        return false;

    const QString needle = searchEdit_ ? searchEdit_->text().trimmed().toLower() : QString();
    if (needle.isEmpty())
        return true;

    const QString haystack = QStringList{item.promptPreview,
                                         item.stackSummary,
                                         item.lowModelName,
                                         item.highModelName,
                                         item.runtimeSummary,
                                         item.outputPath,
                                         item.metadataPath,
                                         item.outputContractWarnings}
                                 .join(QStringLiteral(" "))
                                 .toLower();
    return haystack.contains(needle);
}

void T2VHistoryPage::applyFilters()
{
    visibleItemIndexes_.clear();
    for (int i = 0; i < items_.size(); ++i)
    {
        if (itemMatchesFilters(items_.at(i)))
            visibleItemIndexes_.append(i);
    }

    populateTable();

    if (!loadErrorText_.isEmpty())
    {
        summaryLabel_->setText(loadErrorText_);
        updateEmptyDetails();
        return;
    }

    if (items_.isEmpty())
    {
        summaryLabel_->setText(QStringLiteral("No persisted T2V outputs found yet. Generate a Wan or LTX T2V job to populate runtime/history/video_history_index.json."));
        updateEmptyDetails();
        return;
    }

    const QString suffix = (visibleItemIndexes_.size() == items_.size())
                               ? QStringLiteral("loaded")
                               : QStringLiteral("shown after filters");
    summaryLabel_->setText(QStringLiteral("%1 of %2 persisted video%3 %4 from runtime/history/video_history_index.json.")
                               .arg(visibleItemIndexes_.size())
                               .arg(items_.size())
                               .arg(items_.size() == 1 ? QString() : QStringLiteral("s"))
                               .arg(suffix));

    if (visibleItemIndexes_.isEmpty())
    {
        updateEmptyDetails();
        return;
    }
    table_->selectRow(0);
}

void T2VHistoryPage::populateTable()
{
    table_->setRowCount(0);
    table_->setRowCount(visibleItemIndexes_.size());
    for (int row = 0; row < visibleItemIndexes_.size(); ++row)
    {
        const VideoHistoryItem &item = items_.at(visibleItemIndexes_.at(row));
        table_->setItem(row, 0, tableItem(formatFinishedAt(item.finishedAt)));
        table_->setItem(row, 1, tableItem(compactText(item.promptPreview, 90)));
        table_->setItem(row, 2, tableItem(item.durationLabel.isEmpty() ? QStringLiteral("unknown") : item.durationLabel));
        table_->setItem(row, 3, tableItem(item.resolution.isEmpty() ? QStringLiteral("unknown") : item.resolution));
        table_->setItem(row, 4, tableItem(!item.stackSummary.isEmpty() ? compactText(item.stackSummary, 44) : QStringLiteral("Wan stack")));
        table_->setItem(row, 5, tableItem(item.outputContractStatus));
    }
    const bool empty = visibleItemIndexes_.isEmpty();
    table_->setVisible(!empty);
    emptyStateLabel_->setVisible(empty);
    if (empty)
    {
        emptyStateLabel_->setText(items_.isEmpty()
                                      ? QStringLiteral("No persisted T2V outputs found yet. Generate a Wan or LTX T2V job and refresh this page.")
                                      : QStringLiteral("No T2V history entries match the current search/filter."));
    }
}

void T2VHistoryPage::handleSelectionChanged()
{
    const VideoHistoryItem *item = selectedItem();
    if (!item)
    {
        updateEmptyDetails();
        return;
    }
    updateDetailsForItem(*item);
}

int T2VHistoryPage::selectedRow() const
{
    const auto ranges = table_->selectedRanges();
    if (ranges.isEmpty())
        return -1;
    return ranges.first().topRow();
}

const T2VHistoryPage::VideoHistoryItem *T2VHistoryPage::selectedItem() const
{
    const int row = selectedRow();
    if (row < 0 || row >= visibleItemIndexes_.size())
        return nullptr;
    const int itemIndex = visibleItemIndexes_.at(row);
    if (itemIndex < 0 || itemIndex >= items_.size())
        return nullptr;
    return &items_.at(itemIndex);
}

void T2VHistoryPage::updateDetailsForItem(const VideoHistoryItem &item)
{
    const QFileInfo outputInfo(item.outputPath);
    const QFileInfo metadataInfo(item.metadataPath);
    detailsTitleLabel_->setText(item.durationLabel.isEmpty()
                                    ? QStringLiteral("Completed T2V output")
                                    : QStringLiteral("Completed T2V • %1").arg(item.durationLabel));
    QString status = QStringLiteral("%1 • %2 • %3")
                         .arg(item.outputContractOk ? QStringLiteral("Contract OK") : QStringLiteral("Contract needs review"),
                              item.outputExists ? QStringLiteral("Output exists") : QStringLiteral("Output missing"),
                              item.metadataExists ? QStringLiteral("Metadata written") : QStringLiteral("Metadata missing"));
    if (!item.outputContractWarnings.isEmpty())
        status += QStringLiteral(" • %1").arg(item.outputContractWarnings);
    detailsStatusLabel_->setText(status);

    QStringList body;
    body << QStringLiteral("Prompt: %1").arg(item.promptPreview.isEmpty() ? QStringLiteral("unknown") : item.promptPreview);
    body << QStringLiteral("Resolution: %1").arg(item.resolution.isEmpty() ? QStringLiteral("unknown") : item.resolution);
    body << QStringLiteral("Stack: %1").arg(!item.stackSummary.isEmpty() ? item.stackSummary : QStringLiteral("low=%1 • high=%2").arg(item.lowModelName, item.highModelName));
    if (!item.runtimeSummary.isEmpty())
        body << QStringLiteral("Runtime mode: %1").arg(item.runtimeSummary);
    body << QStringLiteral("Contract: %1").arg(item.outputContractOk ? QStringLiteral("OK") : QStringLiteral("Needs review"));
    if (!item.outputContractWarnings.isEmpty())
        body << QStringLiteral("Contract warnings: %1").arg(item.outputContractWarnings);
    if (!item.metadataStatus.isEmpty())
        body << QStringLiteral("Metadata status: %1").arg(item.metadataStatus);
    body << QStringLiteral("Output size: %1").arg(formatFileSize(item.outputFileSizeBytes));
    body << QStringLiteral("Output: %1").arg(QDir::toNativeSeparators(outputInfo.absoluteFilePath()));
    if (!item.metadataPath.isEmpty())
        body << QStringLiteral("Metadata: %1").arg(QDir::toNativeSeparators(metadataInfo.absoluteFilePath()));
    body << QStringLiteral("Finished: %1").arg(formatFinishedAt(item.finishedAt));
    detailsBodyLabel_->setText(body.join(QStringLiteral("\n")));

    openVideoButton_->setEnabled(item.outputExists && outputInfo.exists());
    revealFolderButton_->setEnabled(!item.outputPath.isEmpty());
    copyPromptButton_->setEnabled(!item.promptPreview.isEmpty());
    copyMetadataPathButton_->setEnabled(!item.metadataPath.isEmpty());
    const bool selectedItemIsLtx = item.runtimeSummary.contains(QStringLiteral("LTX registry"), Qt::CaseInsensitive)
        || item.stackSummary.contains(QStringLiteral("LTX"), Qt::CaseInsensitive)
        || item.lowModelName.contains(QStringLiteral("ltx"), Qt::CaseInsensitive);
    requeueButton_->setEnabled(selectedItemIsLtx);
    validateRequeueButton_->setEnabled(selectedItemIsLtx);
    validatedRequeueDraftPath_.clear();
    submitRequeueButton_->setEnabled(false);
}

void T2VHistoryPage::updateEmptyDetails()
{
    detailsTitleLabel_->setText(QStringLiteral("Select a video"));
    detailsStatusLabel_->setText(QStringLiteral("No selection"));
    detailsBodyLabel_->setText(QStringLiteral("Generate a Wan or LTX T2V job or refresh after existing history has been indexed. This browser reads runtime/history/video_history_index.json and does not depend on the live queue."));
    openVideoButton_->setEnabled(false);
    revealFolderButton_->setEnabled(false);
    copyPromptButton_->setEnabled(false);
    copyMetadataPathButton_->setEnabled(false);
    requeueButton_->setEnabled(false);
    validateRequeueButton_->setEnabled(false);
}

void T2VHistoryPage::openSelectedVideo()
{
    const VideoHistoryItem *item = selectedItem();
    if (!item)
        return;

    const QFileInfo info(item->outputPath);
    if (!info.exists())
        return;

    QDesktopServices::openUrl(QUrl::fromLocalFile(info.absoluteFilePath()));
}

void T2VHistoryPage::revealSelectedVideo()
{
    const VideoHistoryItem *item = selectedItem();
    if (!item)
        return;

    const QFileInfo info(item->outputPath);
    const QDir dir = info.exists() ? info.absoluteDir() : QFileInfo(item->outputPath).absoluteDir();
    if (!dir.exists())
        return;

    QDesktopServices::openUrl(QUrl::fromLocalFile(dir.absolutePath()));
}


void T2VHistoryPage::copySelectedPrompt()
{
    const VideoHistoryItem *item = selectedItem();
    if (!item || item->promptPreview.isEmpty())
        return;
    QApplication::clipboard()->setText(item->promptPreview);
}

void T2VHistoryPage::copySelectedMetadataPath()
{
    const VideoHistoryItem *item = selectedItem();
    if (!item || item->metadataPath.isEmpty())
        return;
    QApplication::clipboard()->setText(QDir::toNativeSeparators(item->metadataPath));
}

QString T2VHistoryPage::formatFileSize(qint64 bytes) const
{
    if (bytes <= 0)
        return QStringLiteral("unknown");
    if (bytes < 1024)
        return QStringLiteral("%1 B").arg(bytes);
    const double kb = static_cast<double>(bytes) / 1024.0;
    if (kb < 1024.0)
        return QStringLiteral("%1 KB").arg(kb, 0, 'f', 1);
    const double mb = kb / 1024.0;
    return QStringLiteral("%1 MB").arg(mb, 0, 'f', 1);
}

QString T2VHistoryPage::formatFinishedAt(const QString &isoText) const
{
    if (isoText.trimmed().isEmpty())
        return QStringLiteral("unknown");

    QDateTime dt = QDateTime::fromString(isoText, Qt::ISODateWithMs);
    if (!dt.isValid())
        dt = QDateTime::fromString(isoText, Qt::ISODate);
    if (!dt.isValid())
        return isoText;
    return dt.toLocalTime().toString(QStringLiteral("MMM d, h:mm AP"));
}

QString T2VHistoryPage::compactText(const QString &text, int maxChars) const
{
    const QString compact = text.simplified();
    if (compact.size() <= maxChars)
        return compact;
    return compact.left(qMax(0, maxChars - 3)) + QStringLiteral("...");
}

void T2VHistoryPage::applyTheme()
{
    const auto &theme = ThemeManager::instance();
    const bool ivory = theme.preset() == ThemeManager::Preset::IvoryHolograph;
    const QString titleColor = ivory ? QStringLiteral("#132033") : QStringLiteral("#f5f8ff");
    const QString bodyColor = ivory ? QStringLiteral("#5d7087") : QStringLiteral("#9fb4d2");
    const QString cardBg = ivory ? QStringLiteral("rgba(255,255,255,0.86)") : QStringLiteral("rgba(10,15,26,0.94)");
    const QString tableBg = ivory ? QStringLiteral("rgba(255,255,255,0.78)") : QStringLiteral("rgba(8,12,22,0.88)");

    setStyleSheet(QStringLiteral(
        "#T2VHistoryPage { background: transparent; }"
        "QFrame#HistoryHeroCard, QFrame#HistoryContentCard, QFrame#HistoryDetailsCard {"
        " background: %1; border: 1px solid rgba(126,146,190,0.24); border-radius: 20px; }"
        "QLabel#HistoryEyebrow { color: #8fb2ff; font-size: 11px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; }"
        "QLabel#HistoryTitle { color: %2; font-size: 28px; font-weight: 850; }"
        "QLabel#HistorySubtitle, QLabel#HistorySummary, QLabel#HistoryDetailsBody { color: %3; font-size: 12px; }"
        "QLabel#HistoryDetailsTitle { color: %2; font-size: 18px; font-weight: 800; }"
        "QLabel#HistoryDetailsStatus { color: #8fb2ff; font-size: 11px; font-weight: 700; }"
        "QLineEdit#HistorySearch, QComboBox#HistoryFilterCombo { background: rgba(5,10,18,0.64); color: %2; border: 1px solid rgba(126,146,190,0.24); border-radius: 10px; padding: 7px 10px; }"
        "QLabel#HistoryEmptyState { color: %3; font-size: 13px; padding: 40px; border: 1px dashed rgba(126,146,190,0.28); border-radius: 14px; }"
        "QTableWidget#HistoryTable { background: %4; color: %2; border: 1px solid rgba(126,146,190,0.20); border-radius: 14px; gridline-color: transparent; selection-background-color: rgba(92,154,255,0.32); }"
        "QHeaderView::section { background: rgba(92,154,255,0.14); color: %3; border: none; padding: 8px; font-weight: 800; }"
        "QPushButton#HistoryActionButton { background: rgba(92,154,255,0.18); color: %2; border: 1px solid rgba(126,146,190,0.32); border-radius: 12px; padding: 8px 12px; font-weight: 700; }"
        "QPushButton#HistoryActionButton:hover { background: rgba(92,154,255,0.30); }"
        "QPushButton#HistoryActionButton:disabled { color: rgba(159,180,210,0.45); background: rgba(80,90,110,0.12); }")
                      .arg(cardBg, titleColor, bodyColor, tableBg));
}




void T2VHistoryPage::validateSelectedLtxRequeueDraft()
{
    const VideoHistoryItem *item = selectedItem();
    if (!item)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Validate Requeue"),
                                 QStringLiteral("Select an LTX history row first."));
        return;
    }

    const bool isLtx = item->runtimeSummary.contains(QStringLiteral("LTX registry"), Qt::CaseInsensitive)
        || item->stackSummary.contains(QStringLiteral("LTX"), Qt::CaseInsensitive)
        || item->lowModelName.contains(QStringLiteral("ltx"), Qt::CaseInsensitive);

    if (!isLtx)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Validate Requeue"),
                                 QStringLiteral("This action is currently enabled for LTX registry history rows only."));
        return;
    }

    const QString promptId = requeuePromptIdFromRuntimeSummary(item->runtimeSummary);
    const QString slug = safeRequeueSlug(promptId.isEmpty() ? item->promptPreview.left(80) : promptId);
    const QString draftPath = QDir(ltxRequeueDraftRoot()).filePath(QStringLiteral("%1.requeue.json").arg(slug));
    if (!QFileInfo::exists(draftPath))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Validate Requeue"),
                                 QStringLiteral("No requeue draft exists yet for this item.\n\nClick Prepare Requeue first, then click Validate Requeue."));
        return;
    }

    const QString repoRoot = spellVisionRepoRootForWorkerClient();
    const QString pythonExe = spellVisionPythonExecutable(repoRoot);
    const QString workerClient = QDir(repoRoot).filePath(QStringLiteral("python/worker_client.py"));

    if (!QFileInfo::exists(workerClient))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Validate Requeue"),
                             QStringLiteral("Could not find worker_client.py from:\n%1").arg(repoRoot));
        return;
    }

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("ltx_requeue_draft_gated_submission"));
    request.insert(QStringLiteral("draft_path"), QDir::toNativeSeparators(draftPath));
    request.insert(QStringLiteral("dry_run"), true);
    request.insert(QStringLiteral("submit_to_comfy"), false);

    QProcess process;
    process.setWorkingDirectory(repoRoot);
    process.setProgram(pythonExe);
    process.setArguments({workerClient});
    process.start();

    if (!process.waitForStarted(10000))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Validate Requeue"),
                             QStringLiteral("Could not start worker client:\n%1").arg(pythonExe));
        return;
    }

    process.write(QJsonDocument(request).toJson(QJsonDocument::Compact));
    process.closeWriteChannel();

    if (!process.waitForFinished(60000))
    {
        process.kill();
        QMessageBox::warning(this,
                             QStringLiteral("Validate Requeue"),
                             QStringLiteral("Timed out waiting for requeue validation."));
        return;
    }

    const QByteArray standardOutput = process.readAllStandardOutput();
    const QByteArray standardError = process.readAllStandardError();

    QString parseError;
    const QJsonObject response = parseLastJsonObjectFromProcessOutput(standardOutput, &parseError);
    if (response.isEmpty())
    {
        QMessageBox::warning(this,
                             QStringLiteral("Validate Requeue"),
                             QStringLiteral("%1\n\nstderr:\n%2\n\nstdout:\n%3")
                                 .arg(parseError, QString::fromUtf8(standardError), QString::fromUtf8(standardOutput)));
        return;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const bool canSubmit = response.value(QStringLiteral("can_submit")).toBool(false);
    const QString status = response.value(QStringLiteral("submission_status")).toString(QStringLiteral("unknown"));
    const QString mode = response.value(QStringLiteral("execution_mode")).toString(QStringLiteral("dry_run"));
    const QString error = response.value(QStringLiteral("error")).toString();

    if (!ok || !canSubmit)
    {
        const QJsonArray reasons = response.value(QStringLiteral("blocked_submit_reasons")).toArray();
        QStringList reasonText;
        for (const QJsonValue &value : reasons)
            reasonText << value.toString();

        QMessageBox::warning(this,
                             QStringLiteral("Validate Requeue"),
                             QStringLiteral("Requeue validation did not pass.\n\nStatus: %1\nMode: %2\nReasons: %3\nError: %4")
                                 .arg(status, mode, reasonText.join(QStringLiteral(", ")), error));
        return;
    }

    validatedRequeueDraftPath_ = draftPath;
    submitRequeueButton_->setEnabled(true);

    QMessageBox::information(this,
                             QStringLiteral("Requeue Validation Passed"),
                             QStringLiteral("LTX requeue draft is ready for gated submission.\n\nStatus: %1\nMode: %2\nDraft:\n%3")
                                 .arg(status, mode, draftPath));
}






QJsonObject T2VHistoryPage::buildLtxRequeueQueuePreviewContract(const QJsonObject &response) const
{
    const QJsonObject spellvisionResult = response.value(QStringLiteral("spellvision_result")).toObject();
    const QJsonObject queueEvent = response.value(QStringLiteral("queue_result_event")).toObject();
    const QJsonObject historyRecord = response.value(QStringLiteral("history_record")).toObject();
    const QJsonObject primaryOutput = response.value(QStringLiteral("primary_output")).toObject();

    QJsonObject resultPrimaryOutput = spellvisionResult.value(QStringLiteral("primary_output")).toObject();
    if (resultPrimaryOutput.isEmpty())
        resultPrimaryOutput = primaryOutput;

    const QJsonArray uiOutputs = response.value(QStringLiteral("ui_outputs")).toArray();
    const QJsonObject firstUiOutput = firstObjectFromArray(uiOutputs);

    QJsonObject output = resultPrimaryOutput;
    if (output.isEmpty())
        output = firstUiOutput;

    const QString promptId = response.value(QStringLiteral("prompt_id")).toString();
    const QString outputPath = stringFromObjectPath(output, {
        QStringLiteral("path"),
        QStringLiteral("preview_path"),
        QStringLiteral("uri"),
    });

    const QString metadataPath = stringFromObjectPath(output, {
        QStringLiteral("metadata_path"),
        QStringLiteral("primary_metadata_path"),
    });

    const QString filename = stringFromObjectPath(output, {
        QStringLiteral("filename"),
    });

    QJsonObject contract;
    contract.insert(QStringLiteral("type"), QStringLiteral("spellvision_ltx_requeue_queue_preview_contract"));
    contract.insert(QStringLiteral("schema_version"), 1);
    contract.insert(QStringLiteral("created_at"), QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs));
    contract.insert(QStringLiteral("family"), QStringLiteral("ltx"));
    contract.insert(QStringLiteral("task_type"), QStringLiteral("t2v"));
    contract.insert(QStringLiteral("backend"), QStringLiteral("comfy_prompt_api"));
    contract.insert(QStringLiteral("source"), QStringLiteral("history_requeue_submit"));
    contract.insert(QStringLiteral("prompt_id"), promptId);
    contract.insert(QStringLiteral("state"), response.value(QStringLiteral("submission_status")).toString(QStringLiteral("submitted")));
    contract.insert(QStringLiteral("execution_mode"), response.value(QStringLiteral("execution_mode")).toString(QStringLiteral("submit")));
    contract.insert(QStringLiteral("submitted"), response.value(QStringLiteral("submitted")).toBool(false));
    contract.insert(QStringLiteral("completed"), response.value(QStringLiteral("result_completed")).toBool(false));
    contract.insert(QStringLiteral("queue_ready"), spellvisionResult.value(QStringLiteral("queue_ready")).toBool(!queueEvent.isEmpty()));
    contract.insert(QStringLiteral("history_ready"), spellvisionResult.value(QStringLiteral("history_ready")).toBool(!historyRecord.isEmpty()));
    contract.insert(QStringLiteral("preview_ready"), spellvisionResult.value(QStringLiteral("preview_ready")).toBool(!outputPath.isEmpty()));
    contract.insert(QStringLiteral("primary_output_path"), outputPath);
    contract.insert(QStringLiteral("primary_metadata_path"), metadataPath);
    contract.insert(QStringLiteral("primary_filename"), filename);
    contract.insert(QStringLiteral("output_count"), spellvisionResult.value(QStringLiteral("output_count")).toInt(uiOutputs.size()));
    contract.insert(QStringLiteral("size_bytes"), static_cast<double>(int64FromObjectPath(output, {QStringLiteral("size_bytes")})));
    contract.insert(QStringLiteral("openable"), output.value(QStringLiteral("openable")).toBool(QFileInfo::exists(outputPath)));
    contract.insert(QStringLiteral("animated"), output.value(QStringLiteral("animated")).toBool(true));
    contract.insert(QStringLiteral("send_to_mode"), output.value(QStringLiteral("send_to_mode")).toString(QStringLiteral("t2v")));

    QJsonObject preview;
    preview.insert(QStringLiteral("kind"), output.value(QStringLiteral("kind")).toString(QStringLiteral("video")));
    preview.insert(QStringLiteral("role"), output.value(QStringLiteral("role")).toString(QStringLiteral("full")));
    preview.insert(QStringLiteral("label"), output.value(QStringLiteral("label")).toString(QStringLiteral("LTX Full")));
    preview.insert(QStringLiteral("path"), outputPath);
    preview.insert(QStringLiteral("metadata_path"), metadataPath);
    preview.insert(QStringLiteral("filename"), filename);
    preview.insert(QStringLiteral("exists"), QFileInfo::exists(outputPath));
    preview.insert(QStringLiteral("openable"), output.value(QStringLiteral("openable")).toBool(QFileInfo::exists(outputPath)));
    contract.insert(QStringLiteral("preview"), preview);

    QJsonObject queue;
    queue.insert(QStringLiteral("type"), QStringLiteral("spellvision_queue_result_event"));
    queue.insert(QStringLiteral("prompt_id"), promptId);
    queue.insert(QStringLiteral("state"), queueEvent.value(QStringLiteral("state")).toString(QStringLiteral("completed")));
    queue.insert(QStringLiteral("title"), queueEvent.value(QStringLiteral("title")).toString(QStringLiteral("LTX requeue generation")));
    queue.insert(QStringLiteral("summary"), queueEvent.value(QStringLiteral("summary")).toString(QStringLiteral("LTX requeue output captured")));
    queue.insert(QStringLiteral("primary_output_path"), outputPath);
    queue.insert(QStringLiteral("primary_metadata_path"), metadataPath);
    contract.insert(QStringLiteral("queue"), queue);

    QJsonObject history;
    history.insert(QStringLiteral("type"), QStringLiteral("spellvision_history_record"));
    history.insert(QStringLiteral("prompt_id"), promptId);
    history.insert(QStringLiteral("prompt"), historyRecord.value(QStringLiteral("prompt")).toString());
    history.insert(QStringLiteral("model"), historyRecord.value(QStringLiteral("model")).toString());
    history.insert(QStringLiteral("primary_output_path"), outputPath);
    history.insert(QStringLiteral("primary_metadata_path"), metadataPath);
    contract.insert(QStringLiteral("history"), history);

    contract.insert(QStringLiteral("raw_response_type"), response.value(QStringLiteral("type")).toString());

    return contract;
}

void T2VHistoryPage::persistLatestLtxRequeueQueuePreviewContract(const QJsonObject &contract) const
{
    const QString path = latestLtxRequeueUiContractPath();
    QSaveFile file(path);

    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return;

    file.write(QJsonDocument(contract).toJson(QJsonDocument::Indented));
    file.commit();
}


void T2VHistoryPage::focusLatestLtxRequeueOutputAfterRefresh()
{
    if (pendingLtxRequeuePromptId_.isEmpty() && pendingLtxRequeuePrimaryOutputPath_.isEmpty())
        return;

    QStringList needles;
    needles << pendingLtxRequeuePromptId_;
    needles << pendingLtxRequeuePrimaryOutputPath_;
    needles << fileNameFromPathText(pendingLtxRequeuePrimaryOutputPath_);

    for (QTableWidget *table : findChildren<QTableWidget *>())
    {
        if (!table)
            continue;

        for (int row = 0; row < table->rowCount(); ++row)
        {
            bool matched = false;
            for (int column = 0; column < table->columnCount() && !matched; ++column)
            {
                const QTableWidgetItem *item = table->item(row, column);
                if (!item)
                    continue;

                const QString value = item->text();
                for (const QString &needle : needles)
                {
                    if (!needle.isEmpty() && value.contains(needle, Qt::CaseInsensitive))
                    {
                        matched = true;
                        break;
                    }
                }
            }

            if (!matched)
                continue;

            table->setCurrentCell(row, 0);
            table->selectRow(row);
            table->scrollToItem(table->item(row, 0), QAbstractItemView::PositionAtCenter);
            pendingLtxRequeuePromptId_.clear();
            pendingLtxRequeuePrimaryOutputPath_.clear();
            pendingLtxRequeuePreviewContract_ = QJsonObject();
            return;
        }
    }

    for (QTableView *view : findChildren<QTableView *>())
    {
        if (!view || !view->model())
            continue;

        QAbstractItemModel *model = view->model();
        for (int row = 0; row < model->rowCount(); ++row)
        {
            if (!rowContainsNeedle(model, row, needles))
                continue;

            const QModelIndex index = model->index(row, 0);
            view->setCurrentIndex(index);
            if (view->selectionModel())
                view->selectionModel()->select(index, QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
            view->scrollTo(index, QAbstractItemView::PositionAtCenter);
            pendingLtxRequeuePromptId_.clear();
            pendingLtxRequeuePrimaryOutputPath_.clear();
            pendingLtxRequeuePreviewContract_ = QJsonObject();
            return;
        }
    }
}


void T2VHistoryPage::scheduleRefreshAfterLtxRequeueSubmit(const QJsonObject &response)
{
    const QString promptId = response.value(QStringLiteral("prompt_id")).toString();

    QString primaryOutputPath;
    const QJsonObject primaryOutput = response.value(QStringLiteral("primary_output")).toObject();
    if (!primaryOutput.isEmpty())
        primaryOutputPath = primaryOutput.value(QStringLiteral("path")).toString();

    if (primaryOutputPath.isEmpty())
    {
        const QJsonObject spellvisionResult = response.value(QStringLiteral("spellvision_result")).toObject();
        const QJsonObject resultPrimaryOutput = spellvisionResult.value(QStringLiteral("primary_output")).toObject();
        primaryOutputPath = resultPrimaryOutput.value(QStringLiteral("path")).toString();
    }

    pendingLtxRequeuePromptId_ = promptId;
    pendingLtxRequeuePrimaryOutputPath_ = primaryOutputPath;
    pendingLtxRequeuePreviewContract_ = buildLtxRequeueQueuePreviewContract(response);

    persistLatestLtxRequeueQueuePreviewContract(pendingLtxRequeuePreviewContract_);

    emit ltxRequeueSubmitted(promptId, primaryOutputPath);
    emit ltxRequeuePreviewContractReady(pendingLtxRequeuePreviewContract_);

    auto clickRefreshButton = [this]()
    {
        const QList<QPushButton *> buttons = findChildren<QPushButton *>();
        for (QPushButton *button : buttons)
        {
            if (!button)
                continue;

            if (button->text().compare(QStringLiteral("Refresh"), Qt::CaseInsensitive) == 0)
            {
                button->click();
                return;
            }
        }
    };

    QTimer::singleShot(250, this, clickRefreshButton);
    QTimer::singleShot(1500, this, clickRefreshButton);
    QTimer::singleShot(2200, this, &T2VHistoryPage::focusLatestLtxRequeueOutputAfterRefresh);
    QTimer::singleShot(3200, this, &T2VHistoryPage::focusLatestLtxRequeueOutputAfterRefresh);
}


void T2VHistoryPage::submitSelectedLtxRequeueDraft()
{
    const VideoHistoryItem *item = selectedItem();
    if (!item)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Submit Requeue"),
                                 QStringLiteral("Select an LTX history row first."));
        return;
    }

    const bool isLtx = item->runtimeSummary.contains(QStringLiteral("LTX registry"), Qt::CaseInsensitive)
        || item->stackSummary.contains(QStringLiteral("LTX"), Qt::CaseInsensitive)
        || item->lowModelName.contains(QStringLiteral("ltx"), Qt::CaseInsensitive);

    if (!isLtx)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Submit Requeue"),
                                 QStringLiteral("This action is currently enabled for LTX registry history rows only."));
        return;
    }

    const QString promptId = requeuePromptIdFromRuntimeSummary(item->runtimeSummary);
    const QString slug = safeRequeueSlug(promptId.isEmpty() ? item->promptPreview.left(80) : promptId);
    const QString draftPath = QDir(ltxRequeueDraftRoot()).filePath(QStringLiteral("%1.requeue.json").arg(slug));

    if (!QFileInfo::exists(draftPath))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Submit Requeue"),
                                 QStringLiteral("No requeue draft exists yet for this item.\n\nClick Prepare Requeue first."));
        return;
    }

    if (validatedRequeueDraftPath_ != draftPath)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Submit Requeue"),
                                 QStringLiteral("Validate this requeue draft before submitting it.\n\nClick Validate Requeue first."));
        return;
    }

    const QMessageBox::StandardButton choice = QMessageBox::question(
        this,
        QStringLiteral("Submit LTX Requeue"),
        QStringLiteral("Submit this LTX requeue draft to Comfy now?\n\nThis can start a GPU-heavy video generation job.\n\nDraft:\n%1")
            .arg(draftPath),
        QMessageBox::Yes | QMessageBox::No,
        QMessageBox::No);

    if (choice != QMessageBox::Yes)
        return;

    const QString repoRoot = spellVisionRepoRootForWorkerClient();
    const QString pythonExe = spellVisionPythonExecutable(repoRoot);
    const QString workerClient = QDir(repoRoot).filePath(QStringLiteral("python/worker_client.py"));

    if (!QFileInfo::exists(workerClient))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Submit Requeue"),
                             QStringLiteral("Could not find worker_client.py from:\n%1").arg(repoRoot));
        return;
    }

    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("ltx_requeue_draft_gated_submission"));
    request.insert(QStringLiteral("draft_path"), QDir::toNativeSeparators(draftPath));
    request.insert(QStringLiteral("dry_run"), false);
    request.insert(QStringLiteral("submit_to_comfy"), true);
    request.insert(QStringLiteral("wait_for_result"), false);
    request.insert(QStringLiteral("capture_metadata"), true);

    QProcess process;
    process.setWorkingDirectory(repoRoot);
    process.setProgram(pythonExe);
    process.setArguments({workerClient});
    process.start();

    if (!process.waitForStarted(10000))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Submit Requeue"),
                             QStringLiteral("Could not start worker client:\n%1").arg(pythonExe));
        return;
    }

    process.write(QJsonDocument(request).toJson(QJsonDocument::Compact));
    process.closeWriteChannel();

    if (!process.waitForFinished(120000))
    {
        process.kill();
        QMessageBox::warning(this,
                             QStringLiteral("Submit Requeue"),
                             QStringLiteral("Timed out waiting for requeue submission response."));
        return;
    }

    const QByteArray standardOutput = process.readAllStandardOutput();
    const QByteArray standardError = process.readAllStandardError();

    QString parseError;
    const QJsonObject response = parseLastJsonObjectFromProcessOutput(standardOutput, &parseError);
    if (response.isEmpty())
    {
        QMessageBox::warning(this,
                             QStringLiteral("Submit Requeue"),
                             QStringLiteral("%1\n\nstderr:\n%2\n\nstdout:\n%3")
                                 .arg(parseError, QString::fromUtf8(standardError), QString::fromUtf8(standardOutput)));
        return;
    }

    const bool ok = response.value(QStringLiteral("ok")).toBool(false);
    const bool submitted = response.value(QStringLiteral("submitted")).toBool(false);
    const QString status = response.value(QStringLiteral("submission_status")).toString(QStringLiteral("unknown"));
    const QString mode = response.value(QStringLiteral("execution_mode")).toString(QStringLiteral("submit"));
    const QString promptIdResult = response.value(QStringLiteral("prompt_id")).toString();
    const QString error = response.value(QStringLiteral("error")).toString(response.value(QStringLiteral("submit_error")).toString());

    if (!ok || !submitted)
    {
        const QJsonArray reasons = response.value(QStringLiteral("blocked_submit_reasons")).toArray();
        QStringList reasonText;
        for (const QJsonValue &value : reasons)
            reasonText << value.toString();

        QMessageBox::warning(this,
                             QStringLiteral("Submit Requeue"),
                             QStringLiteral("Requeue submission did not start.\n\nStatus: %1\nMode: %2\nReasons: %3\nError: %4")
                                 .arg(status, mode, reasonText.join(QStringLiteral(", ")), error));
        return;
    }

    scheduleRefreshAfterLtxRequeueSubmit(response);

    QMessageBox::information(this,
                             QStringLiteral("Requeue Submitted"),
                             QStringLiteral("LTX requeue was submitted to Comfy.\n\nStatus: %1\nMode: %2\nPrompt ID: %3\n\nHistory and queue views are refreshing. The latest requeue output will be selected when it appears, and a queue/preview contract has been published.")
                                 .arg(status, mode, promptIdResult));
}


void T2VHistoryPage::prepareSelectedLtxRequeueDraft()
{
    const VideoHistoryItem *item = selectedItem();
    if (!item)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Prepare Requeue"),
                                 QStringLiteral("Select an LTX history row first."));
        return;
    }

    const bool isLtx = item->runtimeSummary.contains(QStringLiteral("LTX registry"), Qt::CaseInsensitive)
        || item->stackSummary.contains(QStringLiteral("LTX"), Qt::CaseInsensitive)
        || item->lowModelName.contains(QStringLiteral("ltx"), Qt::CaseInsensitive);

    if (!isLtx)
    {
        QMessageBox::information(this,
                                 QStringLiteral("Prepare Requeue"),
                                 QStringLiteral("This action is currently enabled for LTX registry history rows only."));
        return;
    }

    const QString promptId = requeuePromptIdFromRuntimeSummary(item->runtimeSummary);
    const QString draftRoot = ltxRequeueDraftRoot();
    QDir().mkpath(draftRoot);

    const QString slug = safeRequeueSlug(promptId.isEmpty() ? item->promptPreview.left(80) : promptId);
    const QString draftPath = QDir(draftRoot).filePath(QStringLiteral("%1.requeue.json").arg(slug));

    QJsonObject draft;
    draft.insert(QStringLiteral("type"), QStringLiteral("spellvision_ltx_history_requeue_draft"));
    draft.insert(QStringLiteral("schema_version"), 1);
    draft.insert(QStringLiteral("family"), QStringLiteral("ltx"));
    draft.insert(QStringLiteral("task_type"), QStringLiteral("t2v"));
    draft.insert(QStringLiteral("backend"), QStringLiteral("comfy_prompt_api"));
    draft.insert(QStringLiteral("source"), QStringLiteral("T2VHistoryPage"));
    draft.insert(QStringLiteral("registry_prompt_id"), promptId);
    draft.insert(QStringLiteral("prompt"), item->promptPreview);
    draft.insert(QStringLiteral("model"), item->lowModelName);
    draft.insert(QStringLiteral("stack_summary"), item->stackSummary);
    draft.insert(QStringLiteral("duration"), item->durationLabel);
    draft.insert(QStringLiteral("resolution"), item->resolution);
    draft.insert(QStringLiteral("runtime_summary"), item->runtimeSummary);
    draft.insert(QStringLiteral("source_output_path"), item->outputPath);
    draft.insert(QStringLiteral("source_metadata_path"), item->metadataPath);
    draft.insert(QStringLiteral("safe_to_requeue"), true);
    draft.insert(QStringLiteral("submit_immediately"), false);
    draft.insert(QStringLiteral("next_command_hint"), QStringLiteral("ltx_prompt_api_gated_submission"));
    draft.insert(QStringLiteral("note"), QStringLiteral("This is a safe requeue draft. A later pass can turn this into one-click submission after confirming model/workflow readiness."));

    QFile outFile(draftPath);
    if (!outFile.open(QIODevice::WriteOnly | QIODevice::Truncate))
    {
        QMessageBox::warning(this,
                             QStringLiteral("Prepare Requeue"),
                             QStringLiteral("Could not write requeue draft:\n%1").arg(draftPath));
        return;
    }

    outFile.write(QJsonDocument(draft).toJson(QJsonDocument::Indented));
    outFile.close();

    if (QClipboard *clipboard = QGuiApplication::clipboard())
        clipboard->setText(draftPath);

    QMessageBox::information(this,
                             QStringLiteral("LTX Requeue Draft Ready"),
                             QStringLiteral("Created a safe LTX requeue draft and copied its path to the clipboard.\n\n%1").arg(draftPath));
}


