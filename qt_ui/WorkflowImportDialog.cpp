#include "WorkflowImportDialog.h"

#include <QCheckBox>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QDesktopServices>
#include <QLabel>
#include <QUrl>
#include <QLineEdit>
#include <QListWidget>
#include <QProcess>
#include <QProcessEnvironment>
#include <QPushButton>
#include <QTextEdit>
#include <QVBoxLayout>

WorkflowImportDialog::WorkflowImportDialog(const QString &projectRoot,
                                           const QString &pythonExecutable,
                                           QWidget *parent)
    : QDialog(parent),
      m_projectRoot(projectRoot),
      m_pythonExecutable(pythonExecutable)
{
    setWindowTitle("Import Comfy Workflow");
    resize(980, 720);

    auto *layout = new QVBoxLayout(this);

    auto *formWidget = new QWidget(this);
    auto *form = new QFormLayout(formWidget);

    sourcePathEdit = new QLineEdit(this);
    browseButton = new QPushButton("Browse...", this);
    connect(browseButton, &QPushButton::clicked, this, &WorkflowImportDialog::browseWorkflowSource);

    auto *sourceRow = new QWidget(this);
    auto *sourceRowLayout = new QHBoxLayout(sourceRow);
    sourceRowLayout->setContentsMargins(0, 0, 0, 0);
    sourceRowLayout->addWidget(sourcePathEdit, 1);
    sourceRowLayout->addWidget(browseButton);

    profileNameEdit = new QLineEdit(this);
    profileNameEdit->setPlaceholderText("Optional display name");

    autoInstallNodesCheck = new QCheckBox("Auto-install missing custom nodes", this);
    autoInstallModelsCheck = new QCheckBox("Auto-install missing models", this);

    form->addRow("Workflow Source", sourceRow);
    form->addRow("Profile Name", profileNameEdit);
    form->addRow("", autoInstallNodesCheck);
    form->addRow("", autoInstallModelsCheck);

    auto *buttonRow = new QWidget(this);
    auto *buttonLayout = new QHBoxLayout(buttonRow);
    buttonLayout->setContentsMargins(0, 0, 0, 0);

    importButton = new QPushButton("Import Workflow", this);
    refreshProfilesButton = new QPushButton("Refresh Profiles", this);
    openFolderButton = new QPushButton("Open Profile Folder", this);
    openFolderButton->setEnabled(false);

    connect(importButton, &QPushButton::clicked, this, &WorkflowImportDialog::importWorkflow);
    connect(refreshProfilesButton, &QPushButton::clicked, this, &WorkflowImportDialog::refreshProfiles);
    connect(openFolderButton, &QPushButton::clicked, this, &WorkflowImportDialog::openSelectedProfileFolder);

    buttonLayout->addWidget(importButton);
    buttonLayout->addWidget(refreshProfilesButton);
    buttonLayout->addWidget(openFolderButton);
    buttonLayout->addStretch();

    auto *bodyWidget = new QWidget(this);
    auto *bodyLayout = new QHBoxLayout(bodyWidget);
    bodyLayout->setContentsMargins(0, 0, 0, 0);

    auto *leftColumn = new QWidget(this);
    auto *leftLayout = new QVBoxLayout(leftColumn);
    leftLayout->setContentsMargins(0, 0, 0, 0);
    leftLayout->addWidget(new QLabel("Imported Profiles", this));

    profilesList = new QListWidget(this);
    connect(profilesList, &QListWidget::itemSelectionChanged, this, &WorkflowImportDialog::onProfileSelectionChanged);
    leftLayout->addWidget(profilesList, 1);

    auto *rightColumn = new QWidget(this);
    auto *rightLayout = new QVBoxLayout(rightColumn);
    rightLayout->setContentsMargins(0, 0, 0, 0);
    rightLayout->addWidget(new QLabel("Details", this));

    detailsPanel = new QTextEdit(this);
    detailsPanel->setReadOnly(true);
    detailsPanel->setStyleSheet("font-family: Consolas, monospace; font-size: 12px;");
    detailsPanel->setPlainText("Import a workflow to inspect scan results, dependencies, and generated profile data.");
    rightLayout->addWidget(detailsPanel, 3);

    rightLayout->addWidget(new QLabel("Importer Log", this));
    logPanel = new QTextEdit(this);
    logPanel->setReadOnly(true);
    logPanel->setStyleSheet("font-family: Consolas, monospace; font-size: 12px;");
    rightLayout->addWidget(logPanel, 2);

    bodyLayout->addWidget(leftColumn, 1);
    bodyLayout->addWidget(rightColumn, 2);

    layout->addWidget(formWidget);
    layout->addWidget(buttonRow);
    layout->addWidget(bodyWidget, 1);

    refreshProfiles();
}

void WorkflowImportDialog::browseWorkflowSource()
{
    const QString path = QFileDialog::getOpenFileName(
        this,
        "Select Comfy Workflow",
        m_projectRoot,
        "Comfy Workflows (*.json *.png *.webp);;All Files (*.*)");
    if (!path.isEmpty())
        sourcePathEdit->setText(path);
}

void WorkflowImportDialog::importWorkflow()
{
    const QString source = sourcePathEdit->text().trimmed();
    if (source.isEmpty())
    {
        appendLog("Select a workflow file first.");
        return;
    }

    QJsonObject payload;
    payload["command"] = "import_workflow";
    payload["source"] = source;
    if (!profileNameEdit->text().trimmed().isEmpty())
        payload["profile_name"] = profileNameEdit->text().trimmed();
    payload["auto_apply_node_deps"] = autoInstallNodesCheck->isChecked();
    payload["auto_apply_model_deps"] = autoInstallModelsCheck->isChecked();
    payload["python_executable"] = m_pythonExecutable;

    const QString result = sendWorkerRequest(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));
    renderImportResult(result);
    refreshProfiles();
    emit profilesChanged();
}

void WorkflowImportDialog::refreshProfiles()
{
    QJsonObject payload;
    payload["command"] = "list_workflow_profiles";
    const QString result = sendWorkerRequest(QString::fromUtf8(QJsonDocument(payload).toJson(QJsonDocument::Compact)));
    renderProfilesResult(result);
}

void WorkflowImportDialog::onProfileSelectionChanged()
{
    auto *item = profilesList->currentItem();
    if (!item)
        return;
    const QString payload = item->data(Qt::UserRole).toString();
    detailsPanel->setPlainText(payload);
    if (openFolderButton)
        openFolderButton->setEnabled(!item->data(Qt::UserRole + 1).toString().isEmpty());
}

void WorkflowImportDialog::openSelectedProfileFolder()
{
    auto *item = profilesList ? profilesList->currentItem() : nullptr;
    if (!item)
        return;
    const QString importRoot = item->data(Qt::UserRole + 1).toString();
    if (importRoot.isEmpty())
        return;
    QDesktopServices::openUrl(QUrl::fromLocalFile(importRoot));
}


QString WorkflowImportDialog::sendWorkerRequest(const QString &jsonPayload)
{
    QProcess process(this);
    process.setProgram(m_pythonExecutable);
    process.setArguments({QDir(m_projectRoot).filePath("python/worker_client.py")});
    process.setWorkingDirectory(m_projectRoot);

    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    const QString cacheRoot = QDir(m_projectRoot).filePath("hf_cache");
    env.insert("HF_HOME", cacheRoot);
    env.insert("HUGGINGFACE_HUB_CACHE", cacheRoot);
    process.setProcessEnvironment(env);

    process.start();
    if (!process.waitForStarted(10000))
        return R"({"ok":false,"error":"worker_client failed to start"})";

    process.write(jsonPayload.toUtf8());
    process.write("\n");
    process.closeWriteChannel();
    process.waitForFinished(600000);

    QString stdoutText = QString::fromUtf8(process.readAllStandardOutput()).trimmed();
    if (stdoutText.contains('\n'))
        stdoutText = stdoutText.section('\n', -1);

    const QString stderrText = QString::fromUtf8(process.readAllStandardError()).trimmed();
    if (!stderrText.isEmpty())
        appendLog(stderrText);

    return stdoutText;
}

void WorkflowImportDialog::appendLog(const QString &text)
{
    if (text.trimmed().isEmpty())
        return;
    logPanel->append(text.trimmed());
}

void WorkflowImportDialog::renderImportResult(const QString &jsonText)
{
    QJsonParseError parseError{};
    const QJsonDocument doc = QJsonDocument::fromJson(jsonText.toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
    {
        detailsPanel->setPlainText(jsonText);
        appendLog("Import returned non-JSON payload.");
        return;
    }

    QJsonObject obj = doc.object();
    const QString messageType = obj.value("type").toString();
    if ((messageType == "client_warning" || messageType == "client_error") &&
        obj.value("raw").isObject())
    {
        obj = obj.value("raw").toObject();
    }

    detailsPanel->setPlainText(QString::fromUtf8(QJsonDocument(obj).toJson(QJsonDocument::Indented)));

    const bool ok = obj.value("ok").toBool(false);
    appendLog(ok ? "Workflow import completed." : "Workflow import failed.");

    const QJsonArray warnings = obj.value("warnings").toArray();
    for (const QJsonValue &value : warnings)
        appendLog(QString("[warning] %1").arg(value.toString()));

    const QJsonArray errors = obj.value("errors").toArray();
    for (const QJsonValue &value : errors)
        appendLog(QString("[error] %1").arg(value.toString()));

    if (obj.contains("error"))
        appendLog(QString("[error] %1").arg(obj.value("error").toString()));
}

void WorkflowImportDialog::renderProfilesResult(const QString &jsonText)
{
    QJsonParseError parseError{};
    const QJsonDocument doc = QJsonDocument::fromJson(jsonText.toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject())
    {
        appendLog("Profile refresh returned non-JSON payload.");
        return;
    }

    QJsonObject obj = doc.object();
    const QString messageType = obj.value("type").toString();
    if ((messageType == "client_warning" || messageType == "client_error") &&
        obj.value("raw").isObject())
    {
        obj = obj.value("raw").toObject();
    }

    const QJsonArray profiles = obj.value("profiles").toArray();

    profilesList->clear();
    for (const QJsonValue &value : profiles)
    {
        const QJsonObject profile = value.toObject();
        const QString name = profile.value("name").toString(profile.value("profile_name").toString("Imported Workflow"));
        const QString task = profile.value("task_command").toString("unknown");
        const QString backend = profile.value("backend_kind").toString("comfy_workflow");
        const QString importRoot = profile.value("import_root").toString();
        const QString shortId = QFileInfo(importRoot).fileName();

        auto *item = new QListWidgetItem(QString("%1 [%2 | %3] • %4").arg(name, task, backend, shortId), profilesList);
        item->setData(Qt::UserRole, QString::fromUtf8(QJsonDocument(profile).toJson(QJsonDocument::Indented)));
        item->setData(Qt::UserRole + 1, importRoot);
    }

    appendLog(QString("Loaded %1 workflow profile(s).").arg(profiles.size()));
}
