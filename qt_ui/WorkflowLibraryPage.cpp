#include "WorkflowLibraryPage.h"

#include <QAbstractItemView>
#include <QClipboard>
#include <QDesktopServices>
#include <QDir>
#include <QFileInfo>
#include <QFrame>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QJsonValue>
#include <QLabel>
#include <QListWidget>
#include <QListWidgetItem>
#include <QMessageBox>
#include <QPlainTextEdit>
#include <QProcess>
#include <QProcessEnvironment>
#include <QPushButton>
#include <QSplitter>
#include <QUrl>
#include <QVBoxLayout>

namespace
{
    QJsonObject parseLastJsonObjectFromStdout(const QString &allStdout, QString *errorText = nullptr)
    {
        QString lastJsonLine;
        const QStringList lines = allStdout.split('\n', Qt::SkipEmptyParts);
        for (auto it = lines.crbegin(); it != lines.crend(); ++it)
        {
            const QString candidate = it->trimmed();
            if (candidate.startsWith('{') && candidate.endsWith('}'))
            {
                lastJsonLine = candidate;
                break;
            }
        }

        if (lastJsonLine.isEmpty())
        {
            if (errorText)
                *errorText = QStringLiteral("Worker returned no JSON payload.");
            return {};
        }

        QJsonParseError parseError{};
        const QJsonDocument doc = QJsonDocument::fromJson(lastJsonLine.toUtf8(), &parseError);
        if (parseError.error != QJsonParseError::NoError || !doc.isObject())
        {
            if (errorText)
                *errorText = QStringLiteral("Worker returned invalid JSON: %1").arg(lastJsonLine);
            return {};
        }

        return doc.object();
    }

    QStringList uniqueStringsFromValue(const QJsonValue &value)
    {
        QStringList out;
        const QJsonArray array = value.toArray();
        for (const QJsonValue &entry : array)
        {
            const QString text = entry.toString().trimmed();
            if (!text.isEmpty() && !out.contains(text))
                out << text;
        }
        return out;
    }

    QString summarizeListLine(const QStringList &values, const QString &emptyFallback = QStringLiteral("none"))
    {
        if (values.isEmpty())
            return emptyFallback;
        return values.join(QStringLiteral(", "));
    }

    QString displayOrFallback(const QString &value, const QString &fallback = QStringLiteral("unknown"))
    {
        const QString trimmed = value.trimmed();
        return trimmed.isEmpty() ? fallback : trimmed;
    }

    QString directoryForOpen(const QString &path)
    {
        const QFileInfo info(path);
        if (info.isDir())
            return info.absoluteFilePath();
        if (info.exists())
            return info.absolutePath();
        return path;
    }
}

WorkflowLibraryPage::WorkflowLibraryPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("WorkflowLibraryPage"));
    buildUi();
}

void WorkflowLibraryPage::setProjectRoot(const QString &path)
{
    projectRoot_ = path.trimmed();
}

void WorkflowLibraryPage::setPythonExecutable(const QString &path)
{
    pythonExecutable_ = path.trimmed();
}

void WorkflowLibraryPage::setProfilesRoot(const QString &path)
{
    profilesRoot_ = path.trimmed();
}

void WorkflowLibraryPage::buildUi()
{
    auto *rootLayout = new QVBoxLayout(this);
    rootLayout->setContentsMargins(18, 18, 18, 18);
    rootLayout->setSpacing(12);

    auto *headerRow = new QHBoxLayout;
    headerRow->setSpacing(10);

    auto *titleCol = new QVBoxLayout;
    titleCol->setSpacing(4);

    auto *title = new QLabel(QStringLiteral("Workflow Library"), this);
    title->setStyleSheet(QStringLiteral("font-size: 22px; font-weight: 800; color: #eef4ff;"));

    auto *subtitle = new QLabel(QStringLiteral("Browse imported workflow profiles, inspect dependencies, and queue launch handoffs without leaving the library."), this);
    subtitle->setWordWrap(true);
    subtitle->setStyleSheet(QStringLiteral("font-size: 12px; color: #9fb0ca;"));

    titleCol->addWidget(title);
    titleCol->addWidget(subtitle);

    refreshButton_ = new QPushButton(QStringLiteral("Refresh"), this);
    importButton_ = new QPushButton(QStringLiteral("Import Workflow"), this);
    openImportRootButton_ = new QPushButton(QStringLiteral("Open Import Folder"), this);

    headerRow->addLayout(titleCol, 1);
    headerRow->addWidget(refreshButton_);
    headerRow->addWidget(importButton_);
    headerRow->addWidget(openImportRootButton_);

    rootLayout->addLayout(headerRow);

    statusLabel_ = new QLabel(QStringLiteral("Ready."), this);
    statusLabel_->setStyleSheet(QStringLiteral("font-size: 11px; color: #8fb2ff;"));
    rootLayout->addWidget(statusLabel_);

    auto *splitter = new QSplitter(Qt::Horizontal, this);

    auto *listPane = new QFrame(splitter);
    auto *listLayout = new QVBoxLayout(listPane);
    listLayout->setContentsMargins(0, 0, 0, 0);
    listLayout->setSpacing(8);

    auto *listTitle = new QLabel(QStringLiteral("Imported Profiles"), listPane);
    listTitle->setStyleSheet(QStringLiteral("font-size: 14px; font-weight: 800; color: #eef4ff;"));

    profileList_ = new QListWidget(listPane);
    profileList_->setSelectionMode(QAbstractItemView::SingleSelection);
    profileList_->setUniformItemSizes(false);
    profileList_->setAlternatingRowColors(true);
    profileList_->setMinimumWidth(360);

    listLayout->addWidget(listTitle);
    listLayout->addWidget(profileList_, 1);

    auto *detailPane = new QFrame(splitter);
    auto *detailLayout = new QVBoxLayout(detailPane);
    detailLayout->setContentsMargins(0, 0, 0, 0);
    detailLayout->setSpacing(10);

    detailTitleLabel_ = new QLabel(QStringLiteral("No workflow selected"), detailPane);
    detailTitleLabel_->setStyleSheet(QStringLiteral("font-size: 18px; font-weight: 800; color: #eef4ff;"));

    detailSummaryLabel_ = new QLabel(QStringLiteral("Select an imported workflow to inspect its task type, paths, slot bindings, warnings, and dependency signals."), detailPane);
    detailSummaryLabel_->setWordWrap(true);
    detailSummaryLabel_->setStyleSheet(QStringLiteral("font-size: 12px; color: #9fb0ca;"));

    auto *detailActionRow = new QHBoxLayout;
    detailActionRow->setSpacing(8);

    launchSelectedButton_ = new QPushButton(QStringLiteral("Queue Workflow"), detailPane);
    openSelectedFolderButton_ = new QPushButton(QStringLiteral("Open Selected Folder"), detailPane);
    openSelectedScanReportButton_ = new QPushButton(QStringLiteral("View Scan Report"), detailPane);
    copyPathsButton_ = new QPushButton(QStringLiteral("Copy Paths"), detailPane);

    detailActionRow->addWidget(launchSelectedButton_);
    detailActionRow->addWidget(openSelectedFolderButton_);
    detailActionRow->addWidget(openSelectedScanReportButton_);
    detailActionRow->addWidget(copyPathsButton_);
    detailActionRow->addStretch(1);

    detailTextEdit_ = new QPlainTextEdit(detailPane);
    detailTextEdit_->setReadOnly(true);
    detailTextEdit_->setPlaceholderText(QStringLiteral("Workflow details will appear here."));
    detailTextEdit_->setMinimumHeight(380);

    detailLayout->addWidget(detailTitleLabel_);
    detailLayout->addWidget(detailSummaryLabel_);
    detailLayout->addLayout(detailActionRow);
    detailLayout->addWidget(detailTextEdit_, 1);

    splitter->addWidget(listPane);
    splitter->addWidget(detailPane);
    splitter->setStretchFactor(0, 0);
    splitter->setStretchFactor(1, 1);
    splitter->setSizes({390, 930});

    rootLayout->addWidget(splitter, 1);

    connect(refreshButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::refreshProfiles);
    connect(importButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::importWorkflowRequested);
    connect(openImportRootButton_, &QPushButton::clicked, this, [this]()
            {
        if (profilesRoot_.trimmed().isEmpty())
            return;
        QDesktopServices::openUrl(QUrl::fromLocalFile(directoryForOpen(profilesRoot_))); });

    connect(profileList_, &QListWidget::currentItemChanged, this, [this](QListWidgetItem *, QListWidgetItem *)
            { handleSelectionChanged(); });
    connect(profileList_, &QListWidget::itemDoubleClicked, this, [this](QListWidgetItem *)
            { handleLaunchSelectedWorkflow(); });
    connect(launchSelectedButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::handleLaunchSelectedWorkflow);
    connect(openSelectedFolderButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::handleOpenSelectedFolder);
    connect(openSelectedScanReportButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::handleOpenSelectedScanReport);
    connect(copyPathsButton_, &QPushButton::clicked, this, &WorkflowLibraryPage::handleCopyPaths);

    launchSelectedButton_->setEnabled(false);
    openSelectedFolderButton_->setEnabled(false);
    openSelectedScanReportButton_->setEnabled(false);
    copyPathsButton_->setEnabled(false);
}

void WorkflowLibraryPage::refreshProfiles()
{
    if (refreshProcess_)
        return;
    startRefreshProcess();
}

void WorkflowLibraryPage::startRefreshProcess()
{
    const QString projectRoot = projectRoot_.trimmed();
    const QString pythonExecutable = pythonExecutable_.trimmed().isEmpty() ? QStringLiteral("python") : pythonExecutable_.trimmed();

    if (projectRoot.isEmpty())
    {
        statusLabel_->setText(QStringLiteral("Project root is not configured."));
        return;
    }

    const QString workerClient = QDir(projectRoot).filePath(QStringLiteral("python/worker_client.py"));
    if (!QFileInfo::exists(workerClient))
    {
        statusLabel_->setText(QStringLiteral("worker_client.py was not found."));
        return;
    }

    refreshButton_->setEnabled(false);
    statusLabel_->setText(QStringLiteral("Refreshing workflow library…"));

    auto *process = new QProcess(this);
    refreshProcess_ = process;

    process->setProgram(pythonExecutable);
    process->setArguments({workerClient});
    process->setWorkingDirectory(projectRoot);

    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    const QString cacheRoot = QDir(projectRoot).filePath(QStringLiteral("hf_cache"));
    env.insert(QStringLiteral("HF_HOME"), cacheRoot);
    env.insert(QStringLiteral("HUGGINGFACE_HUB_CACHE"), cacheRoot);
    process->setProcessEnvironment(env);

    const QByteArray requestBytes =
        QJsonDocument(QJsonObject{{QStringLiteral("command"), QStringLiteral("list_workflow_profiles")}})
            .toJson(QJsonDocument::Compact) +
        "\n";

    connect(process, &QProcess::started, this, [process, requestBytes]()
            {
        process->write(requestBytes);
        process->closeWriteChannel(); });

    connect(process, &QProcess::errorOccurred, this, [this, process](QProcess::ProcessError)
            {
        if (refreshProcess_ != process)
        {
            process->deleteLater();
            return;
        }

        const QString stderrText = QString::fromUtf8(process->readAllStandardError()).trimmed();
        refreshProcess_ = nullptr;
        process->deleteLater();

        refreshButton_->setEnabled(true);
        statusLabel_->setText(stderrText.isEmpty()
                                  ? QStringLiteral("Failed to refresh workflow library.")
                                  : QStringLiteral("Refresh failed: %1").arg(stderrText)); });

    connect(process,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this,
            [this, process](int exitCode, QProcess::ExitStatus exitStatus)
            {
                if (refreshProcess_ != process)
                {
                    process->deleteLater();
                    return;
                }

                const QString stderrText = QString::fromUtf8(process->readAllStandardError()).trimmed();
                const QString stdoutText = QString::fromUtf8(process->readAllStandardOutput()).trimmed();

                refreshProcess_ = nullptr;
                process->deleteLater();
                refreshButton_->setEnabled(true);

                if (exitStatus != QProcess::NormalExit || exitCode != 0)
                {
                    statusLabel_->setText(stderrText.isEmpty()
                                              ? QStringLiteral("Workflow library refresh exited with code %1.").arg(exitCode)
                                              : QStringLiteral("Workflow library refresh failed: %1").arg(stderrText));
                    return;
                }

                QString parseErrorText;
                const QJsonObject response = parseLastJsonObjectFromStdout(stdoutText, &parseErrorText);
                if (response.isEmpty())
                {
                    statusLabel_->setText(parseErrorText.isEmpty()
                                              ? QStringLiteral("Workflow library refresh returned no usable JSON.")
                                              : parseErrorText);
                    return;
                }

                const bool ok = response.value(QStringLiteral("ok")).toBool(false);
                if (!ok)
                {
                    statusLabel_->setText(displayOrFallback(response.value(QStringLiteral("error")).toString(),
                                                            QStringLiteral("Workflow library refresh failed.")));
                    return;
                }

                const QJsonArray profiles = response.value(QStringLiteral("profiles")).toArray();
                const QString root = response.value(QStringLiteral("profiles_root")).toString().trimmed();
                if (!root.isEmpty())
                    profilesRoot_ = root;

                populateProfiles(profiles);
                statusLabel_->setText(QStringLiteral("%1 workflow profile(s) loaded.").arg(profiles.size()));
            });

    process->start();
}

void WorkflowLibraryPage::populateProfiles(const QJsonArray &profiles)
{
    const QString previousSelection = selectedProfilePath_;

    profileList_->blockSignals(true);
    profileList_->clear();

    int selectedRow = -1;
    int row = 0;

    for (const QJsonValue &value : profiles)
    {
        const QJsonObject profile = value.toObject();
        const QString name = displayOrFallback(profile.value(QStringLiteral("name")).toString(),
                                               displayOrFallback(profile.value(QStringLiteral("profile_name")).toString(),
                                                                 QStringLiteral("Imported Workflow")));
        const QString task = displayOrFallback(profile.value(QStringLiteral("task_command")).toString());
        const QString media = displayOrFallback(profile.value(QStringLiteral("media_type")).toString());
        const QString backend = displayOrFallback(profile.value(QStringLiteral("backend_kind")).toString());

        const QJsonObject metadata = profile.value(QStringLiteral("metadata")).toObject();
        const int missingCustomNodes = metadata.value(QStringLiteral("missing_custom_nodes")).toArray().size();
        const int warningCount = uniqueStringsFromValue(profile.value(QStringLiteral("warnings"))).size();

        QStringList lines;
        lines << name;
        lines << QStringLiteral("%1 • %2 • %3").arg(task, media, backend);
        lines << QStringLiteral("%1 warning(s) • %2 custom node(s)").arg(warningCount).arg(missingCustomNodes);

        auto *item = new QListWidgetItem(lines.join(QStringLiteral("\n")), profileList_);
        item->setData(Qt::UserRole, QJsonDocument(profile).toJson(QJsonDocument::Compact));
        item->setData(Qt::UserRole + 1, profile.value(QStringLiteral("profile_path")).toString());

        if (item->data(Qt::UserRole + 1).toString() == previousSelection)
            selectedRow = row;
        ++row;
    }

    profileList_->blockSignals(false);

    if (profileList_->count() == 0)
    {
        selectedProfilePath_.clear();
        renderSelectedProfile();
        return;
    }

    if (selectedRow >= 0)
        profileList_->setCurrentRow(selectedRow);
    else
        profileList_->setCurrentRow(0);

    renderSelectedProfile();
}

QJsonObject WorkflowLibraryPage::currentProfile() const
{
    QListWidgetItem *item = profileList_ ? profileList_->currentItem() : nullptr;
    if (!item)
        return {};

    QJsonParseError parseError{};
    const QJsonDocument doc = QJsonDocument::fromJson(item->data(Qt::UserRole).toByteArray(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
        return {};
    return doc.object();
}

void WorkflowLibraryPage::handleSelectionChanged()
{
    QListWidgetItem *item = profileList_ ? profileList_->currentItem() : nullptr;
    selectedProfilePath_ = item ? item->data(Qt::UserRole + 1).toString() : QString();
    renderSelectedProfile();
}

void WorkflowLibraryPage::handleLaunchSelectedWorkflow()
{
    const QJsonObject profile = currentProfile();
    if (profile.isEmpty())
        return;

    statusLabel_->setText(QStringLiteral("Workflow launch requested…"));
    emit launchWorkflowRequested(profile);
}

void WorkflowLibraryPage::renderSelectedProfile()
{
    const QJsonObject profile = currentProfile();
    if (profile.isEmpty())
    {
        detailTitleLabel_->setText(QStringLiteral("No workflow selected"));
        detailSummaryLabel_->setText(QStringLiteral("Select an imported workflow to inspect task type, paths, slot bindings, warnings, and dependency signals."));
        detailTextEdit_->setPlainText(QStringLiteral("No imported workflow is currently selected."));
        launchSelectedButton_->setEnabled(false);
        openSelectedFolderButton_->setEnabled(false);
        openSelectedScanReportButton_->setEnabled(false);
        copyPathsButton_->setEnabled(false);
        return;
    }

    const QString profileName = displayOrFallback(profile.value(QStringLiteral("profile_name")).toString(),
                                                  displayOrFallback(profile.value(QStringLiteral("name")).toString(),
                                                                    QStringLiteral("Imported Workflow")));
    const QString task = displayOrFallback(profile.value(QStringLiteral("task_command")).toString());
    const QString media = displayOrFallback(profile.value(QStringLiteral("media_type")).toString());
    const QString backend = displayOrFallback(profile.value(QStringLiteral("backend_kind")).toString());
    const QString workflowPath = profile.value(QStringLiteral("workflow_path")).toString().trimmed().isEmpty()
                                     ? profile.value(QStringLiteral("workflow_source")).toString().trimmed()
                                     : profile.value(QStringLiteral("workflow_path")).toString().trimmed();
    const QString profilePath = profile.value(QStringLiteral("profile_path")).toString().trimmed();
    const QString importRoot = profile.value(QStringLiteral("import_root")).toString().trimmed();
    const QString importSlug = profile.value(QStringLiteral("import_slug")).toString().trimmed();

    const QJsonObject metadata = profile.value(QStringLiteral("metadata")).toObject();
    const QString graphFormat = displayOrFallback(metadata.value(QStringLiteral("graph_format")).toString(), QStringLiteral("unknown"));
    const int nodeCount = metadata.value(QStringLiteral("node_count")).toInt(0);
    const QJsonArray missingCustomNodes = metadata.value(QStringLiteral("missing_custom_nodes")).toArray();
    const QJsonArray modelReferences = metadata.value(QStringLiteral("model_references")).toArray();
    const QString scanReportId = metadata.value(QStringLiteral("scan_report_id")).toString().trimmed();

    const QStringList tags = uniqueStringsFromValue(profile.value(QStringLiteral("tags")));
    const QStringList modelHints = uniqueStringsFromValue(profile.value(QStringLiteral("model_family_hints")));
    const QStringList warnings = uniqueStringsFromValue(profile.value(QStringLiteral("warnings")));

    detailTitleLabel_->setText(profileName);
    detailSummaryLabel_->setText(QStringLiteral("%1 • %2 • %3 • %4 custom node(s) • %5 warning(s)")
                                     .arg(task, media, backend)
                                     .arg(missingCustomNodes.size())
                                     .arg(warnings.size()));

    QStringList detailLines;
    detailLines << QStringLiteral("Profile")
                << QStringLiteral("  Name: %1").arg(profileName)
                << QStringLiteral("  Import Slug: %1").arg(displayOrFallback(importSlug, QStringLiteral("none")))
                << QStringLiteral("  Task Command: %1").arg(task)
                << QStringLiteral("  Media Type: %1").arg(media)
                << QStringLiteral("  Backend Kind: %1").arg(backend)
                << QStringLiteral("")
                << QStringLiteral("Paths")
                << QStringLiteral("  Import Root: %1").arg(displayOrFallback(importRoot, QStringLiteral("none")))
                << QStringLiteral("  Workflow Path: %1").arg(displayOrFallback(workflowPath, QStringLiteral("none")))
                << QStringLiteral("  Profile Path: %1").arg(displayOrFallback(profilePath, QStringLiteral("none")))
                << QStringLiteral("  Scan Report Path: %1").arg(importRoot.isEmpty() ? QStringLiteral("unknown") : QDir(importRoot).filePath(QStringLiteral("scan_report.json")))
                << QStringLiteral("")
                << QStringLiteral("Metadata")
                << QStringLiteral("  Graph Format: %1").arg(graphFormat)
                << QStringLiteral("  Node Count: %1").arg(nodeCount)
                << QStringLiteral("  Scan Report ID: %1").arg(displayOrFallback(scanReportId, QStringLiteral("none")))
                << QStringLiteral("")
                << QStringLiteral("Tags")
                << QStringLiteral("  %1").arg(summarizeListLine(tags))
                << QStringLiteral("")
                << QStringLiteral("Model Family Hints")
                << QStringLiteral("  %1").arg(summarizeListLine(modelHints))
                << QStringLiteral("")
                << QStringLiteral("Missing Custom Nodes");

    if (missingCustomNodes.isEmpty())
    {
        detailLines << QStringLiteral("  none");
    }
    else
    {
        for (const QJsonValue &value : missingCustomNodes)
            detailLines << QStringLiteral("  - %1").arg(value.toString());
    }

    detailLines << QStringLiteral("")
                << QStringLiteral("Model References")
                << QStringLiteral("  Count: %1").arg(modelReferences.size());

    for (const QJsonValue &value : modelReferences)
    {
        const QJsonObject ref = value.toObject();
        detailLines << QStringLiteral("  - [%1] %2 (node %3 / %4)")
                           .arg(displayOrFallback(ref.value(QStringLiteral("kind")).toString()),
                                displayOrFallback(ref.value(QStringLiteral("value")).toString()),
                                displayOrFallback(ref.value(QStringLiteral("node_id")).toString()),
                                displayOrFallback(ref.value(QStringLiteral("input_name")).toString()));
    }

    const QJsonObject slotBindings = profile.value(QStringLiteral("slot_bindings")).toObject();
    detailLines << QStringLiteral("")
                << QStringLiteral("Slot Bindings");

    if (slotBindings.isEmpty())
    {
        detailLines << QStringLiteral("  none");
    }
    else
    {
        QStringList keys = slotBindings.keys();
        keys.sort();
        for (const QString &key : keys)
        {
            const QJsonObject binding = slotBindings.value(key).toObject();
            detailLines << QStringLiteral("  - %1 → node %2 / %3")
                               .arg(key,
                                    displayOrFallback(binding.value(QStringLiteral("node_id")).toString()),
                                    displayOrFallback(binding.value(QStringLiteral("input_name")).toString()));
            detailLines << QStringLiteral("      path: %1").arg(displayOrFallback(binding.value(QStringLiteral("path")).toString(), QStringLiteral("none")));
            detailLines << QStringLiteral("      confidence: %1").arg(QString::number(binding.value(QStringLiteral("confidence")).toDouble(0.0), 'f', 2));
            if (!binding.value(QStringLiteral("note")).toString().trimmed().isEmpty())
                detailLines << QStringLiteral("      note: %1").arg(binding.value(QStringLiteral("note")).toString().trimmed());
        }
    }

    detailLines << QStringLiteral("")
                << QStringLiteral("Warnings");

    if (warnings.isEmpty())
    {
        detailLines << QStringLiteral("  none");
    }
    else
    {
        for (const QString &warning : warnings)
            detailLines << QStringLiteral("  - %1").arg(warning);
    }

    detailTextEdit_->setPlainText(detailLines.join(QStringLiteral("\n")));

    const bool launchable = !profilePath.isEmpty() || !workflowPath.isEmpty();
    const bool hasSelection = !importRoot.isEmpty() || !profilePath.isEmpty();

    launchSelectedButton_->setEnabled(launchable);
    openSelectedFolderButton_->setEnabled(hasSelection);
    openSelectedScanReportButton_->setEnabled(!importRoot.isEmpty());
    copyPathsButton_->setEnabled(hasSelection);
}

void WorkflowLibraryPage::handleOpenSelectedFolder()
{
    const QJsonObject profile = currentProfile();
    if (profile.isEmpty())
        return;

    const QString importRoot = profile.value(QStringLiteral("import_root")).toString().trimmed();
    const QString profilePath = profile.value(QStringLiteral("profile_path")).toString().trimmed();
    const QString target = !importRoot.isEmpty() ? importRoot : profilePath;
    if (target.isEmpty())
        return;

    QDesktopServices::openUrl(QUrl::fromLocalFile(directoryForOpen(target)));
}

void WorkflowLibraryPage::handleOpenSelectedScanReport()
{
    const QJsonObject profile = currentProfile();
    if (profile.isEmpty())
        return;

    const QString importRoot = profile.value(QStringLiteral("import_root")).toString().trimmed();
    if (importRoot.isEmpty())
        return;

    const QString scanReportPath = QDir(importRoot).filePath(QStringLiteral("scan_report.json"));
    if (!QFileInfo::exists(scanReportPath))
    {
        QMessageBox::information(this,
                                 QStringLiteral("Workflow Library"),
                                 QStringLiteral("scan_report.json was not found for the selected workflow."));
        return;
    }

    QDesktopServices::openUrl(QUrl::fromLocalFile(scanReportPath));
}

void WorkflowLibraryPage::handleCopyPaths()
{
    const QJsonObject profile = currentProfile();
    if (profile.isEmpty())
        return;

    QStringList lines;
    lines << QStringLiteral("Import Root: %1").arg(profile.value(QStringLiteral("import_root")).toString().trimmed());
    lines << QStringLiteral("Workflow Path: %1").arg(profile.value(QStringLiteral("workflow_path")).toString().trimmed().isEmpty() ? profile.value(QStringLiteral("workflow_source")).toString().trimmed() : profile.value(QStringLiteral("workflow_path")).toString().trimmed());
    lines << QStringLiteral("Profile Path: %1").arg(profile.value(QStringLiteral("profile_path")).toString().trimmed());

    const QString importRoot = profile.value(QStringLiteral("import_root")).toString().trimmed();
    if (!importRoot.isEmpty())
        lines << QStringLiteral("Scan Report Path: %1").arg(QDir(importRoot).filePath(QStringLiteral("scan_report.json")));

    if (QClipboard *clipboard = QGuiApplication::clipboard())
        clipboard->setText(lines.join(QStringLiteral("\n")));

    statusLabel_->setText(QStringLiteral("Paths copied to clipboard."));
}