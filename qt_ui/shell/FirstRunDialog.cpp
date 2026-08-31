#include "FirstRunDialog.h"
#include "RuntimeProfile.h"

#include <QCheckBox>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QProcessEnvironment>
#include <QPushButton>
#include <QSettings>
#include <QStorageInfo>
#include <QStyle>
#include <QTcpSocket>
#include <QTimer>
#include <QVBoxLayout>

namespace spellvision::shell
{
namespace
{
struct SetupCheck
{
    QString name;
    QString detail;
    bool ready = false;
    bool required = true;
    bool starting = false;
};

void applyStatusBadge(QLabel *status, bool ready, bool required, bool starting)
{
    if (!status)
        return;
    QString statusName = QStringLiteral("FirstRunStatusOptional");
    QString statusText = QStringLiteral("OPTIONAL");
    if (ready)
    {
        statusName = QStringLiteral("FirstRunStatusReady");
        statusText = QStringLiteral("READY");
    }
    else if (starting)
    {
        statusName = QStringLiteral("FirstRunStatusOptional");
        statusText = QStringLiteral("STARTING");
    }
    else if (required)
    {
        statusName = QStringLiteral("FirstRunStatusMissing");
        statusText = QStringLiteral("NEEDS SETUP");
    }
    status->setObjectName(statusName);
    status->setText(statusText);
    status->style()->unpolish(status);
    status->style()->polish(status);
}

QFrame *makeCheckRow(const SetupCheck &check, QWidget *parent, QLabel **detailOut = nullptr, QLabel **statusOut = nullptr)
{
    auto *row = new QFrame(parent);
    row->setObjectName(QStringLiteral("FirstRunCheckRow"));
    auto *layout = new QHBoxLayout(row);
    layout->setContentsMargins(12, 9, 12, 9);
    layout->setSpacing(12);

    auto *copy = new QWidget(row);
    auto *copyLayout = new QVBoxLayout(copy);
    copyLayout->setContentsMargins(0, 0, 0, 0);
    copyLayout->setSpacing(2);

    auto *name = new QLabel(check.name, copy);
    name->setObjectName(QStringLiteral("FirstRunCheckName"));
    auto *detail = new QLabel(check.detail, copy);
    detail->setObjectName(QStringLiteral("FirstRunCheckDetail"));
    detail->setWordWrap(true);
    copyLayout->addWidget(name);
    copyLayout->addWidget(detail);

    auto *status = new QLabel(row);
    applyStatusBadge(status, check.ready, check.required, check.starting);
    status->setAlignment(Qt::AlignCenter);
    status->setMinimumWidth(92);

    layout->addWidget(copy, 1);
    layout->addWidget(status, 0, Qt::AlignVCenter);
    if (detailOut)
        *detailOut = detail;
    if (statusOut)
        *statusOut = status;
    return row;
}

bool workerIsReachable(const spellvision::shell::RuntimeProfile &profile)
{
    return probeWorkerProtocol(profile.workerHost, profile.workerPort, 350);
}
} // namespace

FirstRunDialog::FirstRunDialog(const QString &projectRoot, bool workerStarting, bool comfyStarting, QWidget *parent)
    : QDialog(parent)
{
    setObjectName(QStringLiteral("FirstRunDialog"));
    setWindowTitle(QStringLiteral("Set up SpellVision"));
    setModal(true);
    setMinimumWidth(620);
    setMaximumWidth(760);

    const QString root = QDir::cleanPath(projectRoot);
    profile_ = RuntimeProfile::load(root);
    {
        QSettings destSettings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        outputFolder_ = destSettings.value(QStringLiteral("image_generation/output_folder")).toString().trimmed();
        if (!outputFolder_.isEmpty() && !QDir(outputFolder_).exists())
            outputFolder_.clear();
    }
    const RuntimeProfile &profile = profile_;
    const bool hasApiKey = !qgetenv("BFL_API_KEY").trimmed().isEmpty();

    const bool comfyFolder = profile.comfyRootReady();
    const bool comfyListening = probeComfyProtocol(profile.comfyHost, profile.comfyPort, 350);
    QString comfyDetail = QStringLiteral("Open Runtime Setup to configure or install ComfyUI.");
    if (comfyFolder && comfyListening)
        comfyDetail = profile.comfyRoot + QStringLiteral(" · listening on %1").arg(profile.comfyPort);
    else if (comfyFolder && comfyStarting)
        comfyDetail = profile.comfyRoot + QStringLiteral(" · starting, waiting for %1").arg(profile.comfyPort);
    else if (comfyFolder)
        comfyDetail = profile.comfyRoot + QStringLiteral(" · folder present, %1 not answering").arg(profile.comfyPort);

    QString modelsDetail = QStringLiteral("Configure a model root before local generation.");
    bool modelsReady = profile.modelsRootReady();
    if (modelsReady)
    {
        modelsDetail = profile.modelsRoot;
        const QStorageInfo storage(profile.modelsRoot);
        if (storage.isValid())
        {
            const double freeGb = static_cast<double>(storage.bytesAvailable()) / (1024.0 * 1024.0 * 1024.0);
            modelsDetail += QStringLiteral(" · %1 GB free").arg(freeGb, 0, 'f', 1);
            if (freeGb < 2.0)
                modelsDetail += QStringLiteral(" — too small for new official downloads");
        }
    }

    workerStarting_ = workerStarting;
    comfyStarting_ = comfyStarting;

    const QList<SetupCheck> checks = {
        {QStringLiteral("Python runtime"),
         profile.workerPythonReady() ? profile.workerPython : QStringLiteral("Repair or create the project .venv before local generation."),
         profile.workerPythonReady(), true},
        {QStringLiteral("SpellVision worker"),
         profile.workerScriptReady() ? profile.workerScript : QStringLiteral("python/worker_service.py was not found under the project root."),
         profile.workerScriptReady(), true},
        {QStringLiteral("Worker connection"),
         workerStarting && !workerIsReachable(profile)
             ? QStringLiteral("Starting protocol ping on %1:%2").arg(profile.workerHost).arg(profile.workerPort)
             : QStringLiteral("Protocol ping on %1:%2").arg(profile.workerHost).arg(profile.workerPort),
         workerIsReachable(profile), true, workerStarting && !workerIsReachable(profile)},
        {QStringLiteral("ComfyUI runtime"),
         comfyDetail,
         comfyFolder && comfyListening, true, comfyFolder && comfyStarting && !comfyListening},
        {QStringLiteral("FLUX.3 hosted preview"),
         hasApiKey ? QStringLiteral("BFL_API_KEY is available to this process.")
                   : QStringLiteral("Requires a paid BFL account and BFL_API_KEY; local generation is unaffected."),
         hasApiKey, false},
    };

    otherRequiredReady_ = true;
    for (const SetupCheck &check : checks)
    {
        if (check.required && !check.ready && !check.starting)
            otherRequiredReady_ = false;
    }

    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(24, 24, 24, 20);
    layout->setSpacing(12);

    auto *eyebrow = new QLabel(QStringLiteral("FIRST-RUN CHECK"), this);
    eyebrow->setObjectName(QStringLiteral("FirstRunEyebrow"));
    auto *title = new QLabel(QStringLiteral("Make the runtime honest before you create"), this);
    title->setObjectName(QStringLiteral("FirstRunTitle"));
    auto *body = new QLabel(
        QStringLiteral("Point SpellVision at your model folder and, separately, where you want generated files. "
                       "This check does not download, install, or pick a house path for you."),
        this);
    body->setObjectName(QStringLiteral("FirstRunBody"));
    body->setWordWrap(true);

    auto makeFolderRow = [this](const QString &caption, QLabel **pathLabel, void (FirstRunDialog::*browse)()) {
        auto *row = new QFrame(this);
        row->setObjectName(QStringLiteral("FirstRunCheckRow"));
        auto *rowLayout = new QHBoxLayout(row);
        rowLayout->setContentsMargins(12, 9, 12, 9);
        rowLayout->setSpacing(12);
        auto *copy = new QWidget(row);
        auto *copyLayout = new QVBoxLayout(copy);
        copyLayout->setContentsMargins(0, 0, 0, 0);
        copyLayout->setSpacing(2);
        auto *name = new QLabel(caption, copy);
        name->setObjectName(QStringLiteral("FirstRunCheckName"));
        *pathLabel = new QLabel(copy);
        (*pathLabel)->setObjectName(QStringLiteral("FirstRunCheckDetail"));
        (*pathLabel)->setWordWrap(true);
        copyLayout->addWidget(name);
        copyLayout->addWidget(*pathLabel);
        auto *browseBtn = new QPushButton(QStringLiteral("Browse…"), row);
        browseBtn->setObjectName(QStringLiteral("SecondaryButton"));
        rowLayout->addWidget(copy, 1);
        rowLayout->addWidget(browseBtn, 0, Qt::AlignVCenter);
        connect(browseBtn, &QPushButton::clicked, this, browse);
        return row;
    };

    layout->addWidget(eyebrow);
    layout->addWidget(title);
    layout->addWidget(body);
    layout->addWidget(makeFolderRow(QStringLiteral("Model library folder"), &modelsPathLabel_, &FirstRunDialog::browseModelsRoot));
    layout->addWidget(makeFolderRow(QStringLiteral("Generation output folder"), &outputPathLabel_, &FirstRunDialog::browseOutputFolder));
    refreshFolderLabels();
    layout->addSpacing(4);
    layout->addWidget(makeCheckRow(checks[0], this));
    layout->addWidget(makeCheckRow(checks[1], this));
    layout->addWidget(makeCheckRow(checks[2], this, &workerCheckDetail_, &workerCheckStatus_));
    layout->addWidget(makeCheckRow(checks[3], this, &comfyCheckDetail_, &comfyCheckStatus_));
    layout->addWidget(makeCheckRow(checks[4], this));
    layout->addWidget(makeCheckRow({QStringLiteral("Model library"),
                                    modelsDetail,
                                    modelsReady, true},
                                   this, &modelsCheckDetail_, &modelsCheckStatus_));
    const bool outputReady = !outputFolder_.trimmed().isEmpty() && QDir(outputFolder_).exists();
    layout->addWidget(makeCheckRow({QStringLiteral("Generation output"),
                                    outputReady ? QDir::toNativeSeparators(outputFolder_)
                                                : QStringLiteral("Browse a folder for generated files."),
                                    outputReady, true},
                                   this, &outputCheckDetail_, &outputCheckStatus_));

    const bool requiredReady = otherRequiredReady_ && modelsReady && outputReady;
    suppressCheck_ = new QCheckBox(QStringLiteral("Do not show this check again"), this);
    suppressCheck_->setChecked(requiredReady);
    layout->addWidget(suppressCheck_);

    auto *actions = new QHBoxLayout;
    actions->setSpacing(8);
    actions->addStretch(1);
    auto *runtimeButton = new QPushButton(QStringLiteral("Open Runtime Setup"), this);
    runtimeButton->setObjectName(QStringLiteral("SecondaryButton"));
    continueButton_ = new QPushButton(
        requiredReady ? QStringLiteral("Start creating") : QStringLiteral("Continue in limited mode"),
        this);
    continueButton_->setObjectName(QStringLiteral("PrimaryButton"));
    continueButton_->setDefault(true);
    actions->addWidget(runtimeButton);
    actions->addWidget(continueButton_);
    layout->addLayout(actions);

    connect(runtimeButton, &QPushButton::clicked, this, [this]() {
        persistFolders();
        action_ = Action::OpenRuntime;
        accept();
    });
    connect(continueButton_, &QPushButton::clicked, this, [this]() {
        persistFolders();
        action_ = Action::Continue;
        accept();
    });

    auto *tick = new QTimer(this);
    connect(tick, &QTimer::timeout, this, &FirstRunDialog::refreshChecks);
    tick->start(1500);
}

void FirstRunDialog::browseModelsRoot()
{
    const QString chosen = QFileDialog::getExistingDirectory(
        this, QStringLiteral("Model library folder"), profile_.modelsRoot);
    if (chosen.trimmed().isEmpty())
        return;
    profile_.modelsRoot = QDir::fromNativeSeparators(QDir(chosen).absolutePath());
    persistFolders();
    refreshFolderLabels();
    refreshChecks();
}

void FirstRunDialog::browseOutputFolder()
{
    const QString chosen = QFileDialog::getExistingDirectory(
        this, QStringLiteral("Generation output folder"), outputFolder_);
    if (chosen.trimmed().isEmpty())
        return;
    outputFolder_ = QDir::fromNativeSeparators(QDir(chosen).absolutePath());
    persistFolders();
    refreshFolderLabels();
    refreshChecks();
}

void FirstRunDialog::refreshFolderLabels()
{
    if (modelsPathLabel_)
        modelsPathLabel_->setText(profile_.modelsRoot.trimmed().isEmpty()
                                      ? QStringLiteral("Not set — browse to the folder that holds your models.")
                                      : QDir::toNativeSeparators(profile_.modelsRoot));
    if (outputPathLabel_)
        outputPathLabel_->setText(outputFolder_.trimmed().isEmpty()
                                      ? QStringLiteral("Not set — browse to where generated files should go.")
                                      : QDir::toNativeSeparators(outputFolder_));
}

void FirstRunDialog::refreshChecks()
{
    const bool modelsReady = profile_.modelsRootReady();
    if (modelsCheckDetail_)
    {
        if (modelsReady)
        {
            QString detail = profile_.modelsRoot;
            const QStorageInfo storage(profile_.modelsRoot);
            if (storage.isValid())
            {
                const double freeGb = static_cast<double>(storage.bytesAvailable()) / (1024.0 * 1024.0 * 1024.0);
                detail += QStringLiteral(" · %1 GB free").arg(freeGb, 0, 'f', 1);
                if (freeGb < 2.0)
                    detail += QStringLiteral(" — too small for new official downloads");
            }
            modelsCheckDetail_->setText(detail);
        }
        else
        {
            modelsCheckDetail_->setText(QStringLiteral("Configure a model root before local generation."));
        }
    }
    applyStatusBadge(modelsCheckStatus_, modelsReady, true, false);

    const bool outputReady = !outputFolder_.trimmed().isEmpty() && QDir(outputFolder_).exists();
    if (outputCheckDetail_)
        outputCheckDetail_->setText(outputReady
                                        ? QDir::toNativeSeparators(outputFolder_)
                                        : QStringLiteral("Browse a folder for generated files."));
    applyStatusBadge(outputCheckStatus_, outputReady, true, false);

    const bool workerReady = workerIsReachable(profile_);
    const bool workerStarting = workerStarting_ && !workerReady;
    if (workerCheckDetail_)
        workerCheckDetail_->setText(workerStarting
                                        ? QStringLiteral("Starting protocol ping on %1:%2")
                                              .arg(profile_.workerHost)
                                              .arg(profile_.workerPort)
                                        : QStringLiteral("Protocol ping on %1:%2")
                                              .arg(profile_.workerHost)
                                              .arg(profile_.workerPort));
    applyStatusBadge(workerCheckStatus_, workerReady, true, workerStarting);

    const bool comfyFolder = profile_.comfyRootReady();
    const bool comfyListening = probeComfyProtocol(profile_.comfyHost, profile_.comfyPort, 350);
    const bool comfyStarting = comfyStarting_ && comfyFolder && !comfyListening;
    if (comfyCheckDetail_)
    {
        QString comfyDetail = QStringLiteral("Open Runtime Setup to configure or install ComfyUI.");
        if (comfyFolder && comfyListening)
            comfyDetail = profile_.comfyRoot + QStringLiteral(" · listening on %1").arg(profile_.comfyPort);
        else if (comfyFolder && comfyStarting)
            comfyDetail = profile_.comfyRoot + QStringLiteral(" · starting, waiting for %1").arg(profile_.comfyPort);
        else if (comfyFolder)
            comfyDetail = profile_.comfyRoot + QStringLiteral(" · folder present, %1 not answering").arg(profile_.comfyPort);
        comfyCheckDetail_->setText(comfyDetail);
    }
    applyStatusBadge(comfyCheckStatus_, comfyFolder && comfyListening, true, comfyStarting);

    otherRequiredReady_ = profile_.workerPythonReady() && profile_.workerScriptReady()
                          && (workerReady || workerStarting)
                          && ((comfyFolder && comfyListening) || comfyStarting);

    const bool requiredReady = otherRequiredReady_ && modelsReady && outputReady;
    if (continueButton_)
        continueButton_->setText(requiredReady ? QStringLiteral("Start creating")
                                               : QStringLiteral("Continue in limited mode"));
}

void FirstRunDialog::persistFolders()
{
    profile_.save();
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    if (!outputFolder_.trimmed().isEmpty())
        settings.setValue(QStringLiteral("image_generation/output_folder"), outputFolder_);
}

FirstRunDialog::Action FirstRunDialog::action() const
{
    return action_;
}

bool FirstRunDialog::suppressFuturePrompts() const
{
    return suppressCheck_ && suppressCheck_->isChecked();
}

} // namespace spellvision::shell
