#include "FirstRunDialog.h"
#include "LayoutPickerWidget.h"
#include "ModelsLibraryPaths.h"
#include "RuntimeProfile.h"
#include "../ThemeManager.h"
#include "../style/SvKit.h"

#include <QCheckBox>
#include <QComboBox>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QMetaObject>
#include <QPointer>
#include <QProcessEnvironment>
#include <QPushButton>
#include <QSettings>
#include <QStackedWidget>
#include <QStorageInfo>
#include <QStyle>
#include <QTimer>
#include <QThreadPool>
#include <QVBoxLayout>

namespace spellvision::shell
{
namespace kit = spellvision::kit;
namespace style = spellvision::style;
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
    const bool comfyListening = false;
    QString comfyDetail = QStringLiteral("Open Runtime Setup to configure or install ComfyUI.");
    if (comfyFolder && comfyStarting)
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
         workerStarting
             ? QStringLiteral("Starting protocol ping on %1:%2").arg(profile.workerHost).arg(profile.workerPort)
             : QStringLiteral("Protocol ping on %1:%2").arg(profile.workerHost).arg(profile.workerPort),
         false, true, workerStarting},
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

    const ThemeManager &theme = ThemeManager::instance();

    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(24, 24, 24, 20);
    layout->setSpacing(12);

    // Two pages rather than one flat body (spec 2.7). Only the BODY turns: the dialog's frame --
    // its margins, the suppression checkbox and the action row -- is shared, so the second page is
    // the same dialog with a different middle rather than a second window.
    pages_ = new QStackedWidget(this);
    pages_->setObjectName(QStringLiteral("FirstRunPages"));

    // --- page 0: the shell layout -------------------------------------------------------------
    auto *layoutPage = new QWidget(pages_);
    layoutPage->setObjectName(QStringLiteral("FirstRunLayoutPage"));
    auto *layoutColumn = new QVBoxLayout(layoutPage);
    layoutColumn->setContentsMargins(0, 0, 0, 0);
    layoutColumn->setSpacing(theme.spacing(ThemeManager::Spacing::Snug));

    auto *layoutEyebrow = new QLabel(QStringLiteral("STEP 1 OF 2 · SHELL LAYOUT"), layoutPage);
    layoutEyebrow->setObjectName(QStringLiteral("FirstRunEyebrow"));
    auto *layoutTitle = new QLabel(QStringLiteral("Choose the shape of the app"), layoutPage);
    layoutTitle->setObjectName(QStringLiteral("FirstRunTitle"));
    auto *layoutBody = new QLabel(
        QStringLiteral("All three keep every feature reachable; they differ in where the room goes. "
                       "Change it whenever you like in Settings — nothing is written until you continue."),
        layoutPage);
    layoutBody->setObjectName(QStringLiteral("FirstRunBody"));
    layoutBody->setWordWrap(true);

    layoutPicker_ = new LayoutPickerWidget(layoutPage);
    // Deferred, and this single line IS spec 2.7's "dismissal is never a trap". Settings keeps
    // Immediate, where a pick is the user's whole gesture; here the gesture is not finished until
    // one of the two exit actions runs commitLayoutChoice().
    layoutPicker_->setCommitMode(LayoutPickerWidget::CommitMode::Deferred);

    layoutColumn->addWidget(layoutEyebrow);
    layoutColumn->addWidget(layoutTitle);
    layoutColumn->addWidget(layoutBody);
    // Stretch 0, then a stretch of the column's OWN: page 0 is as tall as page 1's checklist (the
    // stack sizes to its tallest page, and the suppression checkbox retains its row), so this column
    // always has ~345 px of surplus to place. Given to the picker it went INTO the cards -- each card
    // grew to 534 px around 187 px of content (measured), and the description label's own stretch 1
    // (LayoutPickerWidget.cpp) split the void into a ~195 px band above it and a ~190 px band below.
    // Page 1 already ends with checklist->addStretch(1) for exactly this reason; the picker's other
    // host (SettingsPage.cpp) adds it at the default stretch 0 and renders correctly. The surplus
    // belongs BELOW the content on both pages, not inside a shared widget's children.
    layoutColumn->addWidget(layoutPicker_, 0);
    layoutColumn->addStretch(1);
    pages_->addWidget(layoutPage);

    // --- page 1: the environment checklist, unchanged in content ------------------------------
    auto *checklistPage = new QWidget(pages_);
    checklistPage->setObjectName(QStringLiteral("FirstRunChecklistPage"));
    auto *checklist = new QVBoxLayout(checklistPage);
    checklist->setContentsMargins(0, 0, 0, 0);
    checklist->setSpacing(theme.spacing(ThemeManager::Spacing::Snug));

    auto *eyebrow = new QLabel(QStringLiteral("FIRST-RUN CHECK"), checklistPage);
    eyebrow->setObjectName(QStringLiteral("FirstRunEyebrow"));
    auto *title = new QLabel(QStringLiteral("Make the runtime honest before you create"), checklistPage);
    title->setObjectName(QStringLiteral("FirstRunTitle"));
    auto *body = new QLabel(
        QStringLiteral("Point SpellVision at your model folder and, separately, where you want generated files. "
                       "This check does not download, install, or pick a house path for you."),
        checklistPage);
    body->setObjectName(QStringLiteral("FirstRunBody"));
    body->setWordWrap(true);

    auto makeFolderRow = [this, checklistPage](const QString &caption, QLabel **pathLabel, void (FirstRunDialog::*browse)()) {
        auto *row = new QFrame(checklistPage);
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
        auto *browseBtn = kit::button(style::Role::Secondary, QStringLiteral("Browse…"), QStringLiteral("SecondaryButton"), row);
        rowLayout->addWidget(copy, 1);
        rowLayout->addWidget(browseBtn, 0, Qt::AlignVCenter);
        connect(browseBtn, &QPushButton::clicked, this, browse);
        return row;
    };

    checklist->addWidget(eyebrow);
    checklist->addWidget(title);
    checklist->addWidget(body);
    checklist->addWidget(makeFolderRow(QStringLiteral("Model library folder"), &modelsPathLabel_, &FirstRunDialog::browseModelsRoot));
    {
        auto *driveRow = new QWidget(checklistPage);
        auto *driveLayout = new QHBoxLayout(driveRow);
        driveLayout->setContentsMargins(0, 0, 0, 0);
        driveLayout->setSpacing(theme.spacing(ThemeManager::Spacing::Snug));
        auto *driveCopy = new QLabel(QStringLiteral("Or pick the drive that will hold models. SpellVision creates AI_ASSETS/models on it. Removable drives are listed when they are plugged in."));
        driveCopy->setObjectName(QStringLiteral("FirstRunCheckDetail"));
        driveCopy->setWordWrap(true);
        modelsDriveCombo_ = new QComboBox(driveRow);
        modelsDriveCombo_->setMinimumContentsLength(10);
        modelsDriveCombo_->addItem(QStringLiteral("Choose a drive…"), QString());
        for (const QStorageInfo &vol : QStorageInfo::mountedVolumes())
        {
            if (!vol.isValid() || !vol.isReady() || vol.isReadOnly())
                continue;
            const QString root = QDir::fromNativeSeparators(vol.rootPath());
            QString label = QDir::toNativeSeparators(root);
            if (!vol.name().trimmed().isEmpty())
                label += QStringLiteral(" — %1").arg(vol.name().trimmed());
            modelsDriveCombo_->addItem(label, root);
        }
        auto *createBtn = kit::button(style::Role::Secondary, QStringLiteral("Create library on this drive"), QStringLiteral("SecondaryButton"), driveRow);
        auto *driveCol = new QVBoxLayout;
        driveCol->setContentsMargins(0, 0, 0, 0);
        driveCol->setSpacing(theme.spacing(ThemeManager::Spacing::Tight));
        driveCol->addWidget(driveCopy);
        auto *pickRow = new QHBoxLayout;
        pickRow->setContentsMargins(0, 0, 0, 0);
        pickRow->addWidget(modelsDriveCombo_, 1);
        pickRow->addWidget(createBtn, 0, Qt::AlignVCenter);
        driveCol->addLayout(pickRow);
        driveLayout->addLayout(driveCol, 1);
        connect(createBtn, &QPushButton::clicked, this, &FirstRunDialog::createModelsLibraryOnDrive);
        checklist->addWidget(driveRow);
    }
    checklist->addWidget(makeFolderRow(QStringLiteral("Generation output folder"), &outputPathLabel_, &FirstRunDialog::browseOutputFolder));
    refreshFolderLabels();
    checklist->addSpacing(4);
    checklist->addWidget(makeCheckRow(checks[0], checklistPage));
    checklist->addWidget(makeCheckRow(checks[1], checklistPage));
    checklist->addWidget(makeCheckRow(checks[2], checklistPage, &workerCheckDetail_, &workerCheckStatus_));
    checklist->addWidget(makeCheckRow(checks[3], checklistPage, &comfyCheckDetail_, &comfyCheckStatus_));
    checklist->addWidget(makeCheckRow(checks[4], checklistPage));
    checklist->addWidget(makeCheckRow({QStringLiteral("Model library"),
                                       modelsDetail,
                                       modelsReady, true},
                                      checklistPage, &modelsCheckDetail_, &modelsCheckStatus_));
    const bool outputReady = !outputFolder_.trimmed().isEmpty() && QDir(outputFolder_).exists();
    checklist->addWidget(makeCheckRow({QStringLiteral("Generation output"),
                                       outputReady ? QDir::toNativeSeparators(outputFolder_)
                                                   : QStringLiteral("Browse a folder for generated files."),
                                       outputReady, true},
                                      checklistPage, &outputCheckDetail_, &outputCheckStatus_));
    checklist->addStretch(1);
    pages_->addWidget(checklistPage);

    layout->addWidget(pages_, 1);

    const bool requiredReady = otherRequiredReady_ && modelsReady && outputReady;
    suppressCheck_ = new QCheckBox(QStringLiteral("Do not show this check again"), this);
    suppressCheck_->setChecked(requiredReady);
    // Hidden on page 0 but still occupying its row: without this the dialog is 33 px shorter on the
    // layout page and JUMPS when Next is pressed, which reads as the window flinching at the first
    // thing the user does in the app. QStackedLayout already keeps the two BODIES the same size (its
    // sizeHint is the maximum over its pages); the checkbox sits outside the stack, in the shared
    // frame, so it needed saying separately.
    QSizePolicy suppressPolicy = suppressCheck_->sizePolicy();
    suppressPolicy.setRetainSizeWhenHidden(true);
    suppressCheck_->setSizePolicy(suppressPolicy);
    layout->addWidget(suppressCheck_);

    auto *actions = new QHBoxLayout;
    actions->setSpacing(8);
    actions->addStretch(1);
    backButton_ = kit::button(style::Role::Secondary, QStringLiteral("Back"), QStringLiteral("SecondaryButton"), this);
    runtimeButton_ = kit::button(style::Role::Secondary, QStringLiteral("Open Runtime Setup"), QStringLiteral("SecondaryButton"), this);
    nextButton_ = kit::button(style::Role::Primary, QStringLiteral("Next"), QStringLiteral("PrimaryButton"), this);
    continueButton_ = kit::button(
        style::Role::Primary,
        requiredReady ? QStringLiteral("Start creating") : QStringLiteral("Continue in limited mode"),
        QStringLiteral("PrimaryButton"), this);
    continueButton_->setDefault(true);
    actions->addWidget(backButton_);
    actions->addWidget(runtimeButton_);
    actions->addWidget(nextButton_);
    actions->addWidget(continueButton_);
    layout->addLayout(actions);

    connect(nextButton_, &QPushButton::clicked, this, [this]() { showPage(Page::Checklist); });
    connect(backButton_, &QPushButton::clicked, this, [this]() { showPage(Page::Layout); });
    // Both exit actions commit, because both of them are the user FINISHING first run -- "Open
    // Runtime Setup" is a destination, not a cancellation, and a layout chosen on the way to the
    // runtime page would otherwise be silently dropped. Only closing the dialog (Esc, the window's
    // X, reject()) leaves the layout where it was, which is what spec 2.7 promises.
    connect(runtimeButton_, &QPushButton::clicked, this, [this]() {
        persistFolders();
        commitLayoutChoice();
        action_ = Action::OpenRuntime;
        accept();
    });
    connect(continueButton_, &QPushButton::clicked, this, [this]() {
        persistFolders();
        commitLayoutChoice();
        action_ = Action::Continue;
        accept();
    });

    showPage(Page::Layout);

    auto *tick = new QTimer(this);
    connect(tick, &QTimer::timeout, this, &FirstRunDialog::refreshChecks);
    tick->start(1500);
    startReachabilityProbes();
}

void FirstRunDialog::showPage(Page page)
{
    if (!pages_)
        return;
    pages_->setCurrentIndex(static_cast<int>(page));

    // The action row carries both pages' buttons and shows the pair that belongs to the page on
    // screen. The suppression checkbox belongs to the checklist -- it suppresses the CHECK, and
    // offering it beside the layout cards would read as "do not ask me about layouts again".
    const bool onLayout = page == Page::Layout;
    if (backButton_)
        backButton_->setVisible(!onLayout);
    if (runtimeButton_)
        runtimeButton_->setVisible(!onLayout);
    if (nextButton_)
        nextButton_->setVisible(onLayout);
    if (continueButton_)
        continueButton_->setVisible(!onLayout);
    if (suppressCheck_)
        suppressCheck_->setVisible(!onLayout);

    QPushButton *primary = onLayout ? nextButton_ : continueButton_;
    if (primary)
    {
        primary->setDefault(true);
        primary->setFocus(Qt::OtherFocusReason);
    }
}

void FirstRunDialog::commitLayoutChoice()
{
    // A no-op unless the picker is Deferred and the user moved it off what ShellLayout already
    // holds -- setLayoutByIndex is silent on a no-op set, so accepting without touching a card
    // writes nothing and leaves the default in place.
    if (layoutPicker_)
        layoutPicker_->commitSelection();
}

int FirstRunDialog::currentPageIndex() const
{
    return pages_ ? pages_->currentIndex() : -1;
}

void FirstRunDialog::browseModelsRoot()
{
    const QString chosen = QFileDialog::getExistingDirectory(
        this, QStringLiteral("Model library folder"), profile_.modelsRoot);
    if (chosen.trimmed().isEmpty())
        return;
    profile_.modelsRoot = resolveModelsLibraryRoot(QDir::fromNativeSeparators(QDir(chosen).absolutePath()));
    persistFolders();
    refreshFolderLabels();
    refreshChecks();
}

void FirstRunDialog::createModelsLibraryOnDrive()
{
    if (!modelsDriveCombo_)
        return;
    const QString volume = modelsDriveCombo_->currentData().toString().trimmed();
    const QString path = proposedModelsLibraryOnVolume(volume);
    if (path.isEmpty())
        return;
    if (!QDir().mkpath(path))
        return;
    profile_.modelsRoot = path;
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

    applyProbeResults(lastWorkerReady_, lastComfyListening_);
    startReachabilityProbes();
}

void FirstRunDialog::startReachabilityProbes()
{
    if (probeInFlight_)
        return;
    probeInFlight_ = true;

    const QString workerHost = profile_.workerHost;
    const quint16 workerPort = profile_.workerPort;
    const QString comfyHost = profile_.comfyHost;
    const quint16 comfyPort = profile_.comfyPort;
    QPointer<FirstRunDialog> self(this);
    QThreadPool::globalInstance()->start([self, workerHost, workerPort, comfyHost, comfyPort]() {
        const bool workerReady = probeWorkerProtocol(workerHost, workerPort, 350);
        const bool comfyListening = probeComfyProtocol(comfyHost, comfyPort, 350);
        if (!self)
            return;
        QMetaObject::invokeMethod(self.data(), [self, workerReady, comfyListening]() {
            if (!self)
                return;
            self->probeInFlight_ = false;
            self->applyProbeResults(workerReady, comfyListening);
        }, Qt::QueuedConnection);
    });
}

void FirstRunDialog::applyProbeResults(bool workerReady, bool comfyListening)
{
    lastWorkerReady_ = workerReady;
    lastComfyListening_ = comfyListening;

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

    const bool modelsReady = profile_.modelsRootReady();
    const bool outputReady = !outputFolder_.trimmed().isEmpty() && QDir(outputFolder_).exists();
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
