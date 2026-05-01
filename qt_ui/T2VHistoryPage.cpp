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
    connect(openVideoButton_, &QPushButton::clicked, this, &T2VHistoryPage::openSelectedVideo);
    connect(revealFolderButton_, &QPushButton::clicked, this, &T2VHistoryPage::revealSelectedVideo);
    connect(copyPromptButton_, &QPushButton::clicked, this, &T2VHistoryPage::copySelectedPrompt);
    connect(copyMetadataPathButton_, &QPushButton::clicked, this, &T2VHistoryPage::copySelectedMetadataPath);
    detailActions->addWidget(openVideoButton_);
    detailActions->addWidget(revealFolderButton_);

    auto *copyActions = new QHBoxLayout;
    copyActions->setSpacing(8);
    copyActions->addWidget(copyPromptButton_);
    copyActions->addWidget(copyMetadataPathButton_);

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
        summaryLabel_->setText(QStringLiteral("No persisted T2V outputs found yet. Generate a Wan T2V job to populate runtime/history/video_history_index.json."));
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
                                      ? QStringLiteral("No persisted T2V outputs found yet. Generate a Wan T2V job and refresh this page.")
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
}

void T2VHistoryPage::updateEmptyDetails()
{
    detailsTitleLabel_->setText(QStringLiteral("Select a video"));
    detailsStatusLabel_->setText(QStringLiteral("No selection"));
    detailsBodyLabel_->setText(QStringLiteral("Generate a Wan T2V job or refresh after existing history has been indexed. This browser reads runtime/history/video_history_index.json and does not depend on the live queue."));
    openVideoButton_->setEnabled(false);
    revealFolderButton_->setEnabled(false);
    copyPromptButton_->setEnabled(false);
    copyMetadataPathButton_->setEnabled(false);
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
