#include "T2VHistoryPage.h"

#include "ThemeManager.h"

#include <QAbstractItemView>
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
    connect(openVideoButton_, &QPushButton::clicked, this, &T2VHistoryPage::openSelectedVideo);
    connect(revealFolderButton_, &QPushButton::clicked, this, &T2VHistoryPage::revealSelectedVideo);
    detailActions->addWidget(openVideoButton_);
    detailActions->addWidget(revealFolderButton_);

    detailsLayout->addWidget(detailsTitleLabel_);
    detailsLayout->addWidget(detailsStatusLabel_);
    detailsLayout->addWidget(detailsBodyLabel_, 1);
    detailsLayout->addLayout(detailActions);

    contentLayout->addWidget(table_, 3);
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

QList<T2VHistoryPage::VideoHistoryItem> T2VHistoryPage::loadHistoryItems() const
{
    QList<VideoHistoryItem> loaded;
    const QString path = historyIndexPath();
    if (path.isEmpty())
        return loaded;

    QFile file(path);
    if (!file.exists() || !file.open(QIODevice::ReadOnly))
        return loaded;

    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
        return loaded;

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
    populateTable();

    if (items_.isEmpty())
    {
        summaryLabel_->setText(QStringLiteral("No persisted T2V outputs found yet. Generate a Wan T2V job to populate runtime/history/video_history_index.json."));
        updateEmptyDetails();
        return;
    }

    summaryLabel_->setText(QStringLiteral("%1 persisted video%2 loaded from runtime/history/video_history_index.json.")
                               .arg(items_.size())
                               .arg(items_.size() == 1 ? QString() : QStringLiteral("s")));
    table_->selectRow(0);
}

void T2VHistoryPage::populateTable()
{
    table_->setRowCount(0);
    table_->setRowCount(items_.size());
    for (int row = 0; row < items_.size(); ++row)
    {
        const VideoHistoryItem &item = items_.at(row);
        table_->setItem(row, 0, tableItem(formatFinishedAt(item.finishedAt)));
        table_->setItem(row, 1, tableItem(compactText(item.promptPreview, 90)));
        table_->setItem(row, 2, tableItem(item.durationLabel.isEmpty() ? QStringLiteral("unknown") : item.durationLabel));
        table_->setItem(row, 3, tableItem(item.resolution.isEmpty() ? QStringLiteral("unknown") : item.resolution));
        table_->setItem(row, 4, tableItem(!item.stackSummary.isEmpty() ? compactText(item.stackSummary, 44) : QStringLiteral("Wan stack")));
        table_->setItem(row, 5, tableItem(item.outputContractStatus));
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
    if (row < 0 || row >= items_.size())
        return nullptr;
    return &items_.at(row);
}

void T2VHistoryPage::updateDetailsForItem(const VideoHistoryItem &item)
{
    const QFileInfo outputInfo(item.outputPath);
    const QFileInfo metadataInfo(item.metadataPath);
    detailsTitleLabel_->setText(item.durationLabel.isEmpty()
                                    ? QStringLiteral("Completed T2V output")
                                    : QStringLiteral("Completed T2V • %1").arg(item.durationLabel));
    detailsStatusLabel_->setText(QStringLiteral("%1 • %2 • %3")
                                     .arg(item.outputContractOk ? QStringLiteral("Contract OK") : QStringLiteral("Contract needs review"),
                                          item.outputExists ? QStringLiteral("Output exists") : QStringLiteral("Output missing"),
                                          item.metadataExists ? QStringLiteral("Metadata written") : QStringLiteral("Metadata missing")));

    QStringList body;
    body << QStringLiteral("Prompt: %1").arg(item.promptPreview.isEmpty() ? QStringLiteral("unknown") : item.promptPreview);
    body << QStringLiteral("Resolution: %1").arg(item.resolution.isEmpty() ? QStringLiteral("unknown") : item.resolution);
    body << QStringLiteral("Stack: %1").arg(!item.stackSummary.isEmpty() ? item.stackSummary : QStringLiteral("low=%1 • high=%2").arg(item.lowModelName, item.highModelName));
    if (!item.runtimeSummary.isEmpty())
        body << QStringLiteral("Runtime mode: %1").arg(item.runtimeSummary);
    body << QStringLiteral("Output size: %1").arg(formatFileSize(item.outputFileSizeBytes));
    body << QStringLiteral("Output: %1").arg(QDir::toNativeSeparators(outputInfo.absoluteFilePath()));
    if (!item.metadataPath.isEmpty())
        body << QStringLiteral("Metadata: %1").arg(QDir::toNativeSeparators(metadataInfo.absoluteFilePath()));
    body << QStringLiteral("Finished: %1").arg(formatFinishedAt(item.finishedAt));
    detailsBodyLabel_->setText(body.join(QStringLiteral("\n")));

    openVideoButton_->setEnabled(item.outputExists && outputInfo.exists());
    revealFolderButton_->setEnabled(!item.outputPath.isEmpty());
}

void T2VHistoryPage::updateEmptyDetails()
{
    detailsTitleLabel_->setText(QStringLiteral("Select a video"));
    detailsStatusLabel_->setText(QStringLiteral("No selection"));
    detailsBodyLabel_->setText(QStringLiteral("Generate a Wan T2V job or refresh after existing history has been indexed. This browser reads runtime/history/video_history_index.json and does not depend on the live queue."));
    openVideoButton_->setEnabled(false);
    revealFolderButton_->setEnabled(false);
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
        "QTableWidget#HistoryTable { background: %4; color: %2; border: 1px solid rgba(126,146,190,0.20); border-radius: 14px; gridline-color: transparent; selection-background-color: rgba(92,154,255,0.32); }"
        "QHeaderView::section { background: rgba(92,154,255,0.14); color: %3; border: none; padding: 8px; font-weight: 800; }"
        "QPushButton#HistoryActionButton { background: rgba(92,154,255,0.18); color: %2; border: 1px solid rgba(126,146,190,0.32); border-radius: 12px; padding: 8px 12px; font-weight: 700; }"
        "QPushButton#HistoryActionButton:hover { background: rgba(92,154,255,0.30); }"
        "QPushButton#HistoryActionButton:disabled { color: rgba(159,180,210,0.45); background: rgba(80,90,110,0.12); }")
                      .arg(cardBg, titleColor, bodyColor, tableBg));
}
