#include "TrainPage.h"

#include "ThemeManager.h"
#include "shell/GpuMemoryProbe.h"
#include "style/SvKit.h"

#ifdef Q_OS_WIN
#include <windows.h>
#endif

#include <QComboBox>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QProcess>
#include <QProcessEnvironment>
#include <QPushButton>
#include <QSettings>
#include <QSpinBox>
#include <QTextEdit>
#include <QUrl>
#include <QVBoxLayout>

TrainPage::TrainPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("TrainPage"));
    buildUi();
    applyTheme();
    {
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        const QString saved = s.value(QStringLiteral("train/sohyaPath")).toString();
        if (pathEdit_)
            pathEdit_->setText(saved);
        const QString dataset = s.value(QStringLiteral("train/lastDatasetRoot")).toString();
        if (datasetEdit_ && datasetEdit_->text().trimmed().isEmpty() && !dataset.isEmpty())
            datasetEdit_->setText(QDir::toNativeSeparators(dataset));
    }
    probeTrainer();
    refreshHardwareDefaults();
    applyFamilyPreset();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });
}

void TrainPage::setProjectRoot(const QString &root)
{
    projectRoot_ = root.trimmed();
}

void TrainPage::updateDisclosure(bool advanced)
{
    advanced_ = advanced;
    if (advancedBlock_)
        advancedBlock_->setVisible(advanced);
}

QString TrainPage::defaultSohyaPath() const
{
    return QString();
}

QString TrainPage::lastDatasetRoot() const
{
    return datasetEdit_ ? datasetEdit_->text().trimmed() : QString();
}

void TrainPage::buildUi()
{
    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(16, 14, 16, 14);
    root->setSpacing(10);

    auto *eyebrow = new QLabel(QStringLiteral("TRAIN"), this);
    eyebrow->setObjectName(QStringLiteral("TrainEyebrow"));
    auto *title = new QLabel(QStringLiteral("External trainer launcher"), this);
    title->setObjectName(QStringLiteral("TrainTitle"));
    auto *sub = new QLabel(
        QStringLiteral("This is not an in-app training studio. Pick a family, point at the last "
                       "Dataset folder, then Launch a trainer entry (main.py / .exe) you already "
                       "have. Rank/batch are hardware-smart; Advanced reveals them in place."),
        this);
    sub->setObjectName(QStringLiteral("TrainSub"));
    sub->setWordWrap(true);
    root->addWidget(eyebrow);
    root->addWidget(title);
    root->addWidget(sub);

    auto *card = new QFrame(this);
    card->setObjectName(QStringLiteral("TrainCard"));
    spellvision::kit::setSurface(card, spellvision::style::Surface::Panel);
    auto *form = new QVBoxLayout(card);
    form->setContentsMargins(12, 12, 12, 12);
    form->setSpacing(8);

    form->addWidget(new QLabel(QStringLiteral("Family (recipe)"), card));
    familyCombo_ = new QComboBox(card);
    familyCombo_->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    familyCombo_->setMinimumContentsLength(10);
    familyCombo_->addItem(QStringLiteral("Krea 2"), QStringLiteral("krea2"));
    familyCombo_->addItem(QStringLiteral("SDXL"), QStringLiteral("sdxl"));
    familyCombo_->addItem(QStringLiteral("Flux"), QStringLiteral("flux"));
    familyCombo_->addItem(QStringLiteral("Wan"), QStringLiteral("wan"));
    familyCombo_->addItem(QStringLiteral("LTX"), QStringLiteral("ltx"));
    form->addWidget(familyCombo_);

    form->addWidget(new QLabel(QStringLiteral("Dataset folder (last Dataset generate)"), card));
    auto *datasetRow = new QHBoxLayout;
    datasetEdit_ = new QLineEdit(card);
    datasetEdit_->setPlaceholderText(QStringLiteral("Not set — generate a dataset or Browse…"));
    datasetBrowseButton_ = new QPushButton(QStringLiteral("Browse"), card);
    spellvision::kit::setRole(datasetBrowseButton_, spellvision::style::Role::Secondary);
    datasetRow->addWidget(datasetEdit_, 1);
    datasetRow->addWidget(datasetBrowseButton_);
    form->addLayout(datasetRow);

    form->addWidget(new QLabel(QStringLiteral("Trainer entry (main.py / .exe)"), card));
    auto *row = new QHBoxLayout;
    pathEdit_ = new QLineEdit(card);
    pathEdit_->setPlaceholderText(QStringLiteral("Path to trainer main.py or .exe…"));
    browseButton_ = new QPushButton(QStringLiteral("Browse"), card);
    spellvision::kit::setRole(browseButton_, spellvision::style::Role::Secondary);
    row->addWidget(pathEdit_, 1);
    row->addWidget(browseButton_);
    form->addLayout(row);

    advancedBlock_ = new QWidget(card);
    auto *adv = new QVBoxLayout(advancedBlock_);
    adv->addWidget(new QLabel(QStringLiteral("LoRA rank"), advancedBlock_));
    rankSpin_ = new QSpinBox(advancedBlock_);
    rankSpin_->setRange(4, 128);
    rankSpin_->setSingleStep(4);
    rankSpin_->setValue(8);
    adv->addWidget(rankSpin_);
    adv->addWidget(new QLabel(QStringLiteral("Batch size"), advancedBlock_));
    batchSpin_ = new QSpinBox(advancedBlock_);
    batchSpin_->setRange(1, 8);
    batchSpin_->setValue(1);
    adv->addWidget(batchSpin_);
    advancedBlock_->setVisible(false);
    form->addWidget(advancedBlock_);

    statusLabel_ = new QLabel(card);
    statusLabel_->setObjectName(QStringLiteral("TrainStatus"));
    statusLabel_->setWordWrap(true);
    form->addWidget(statusLabel_);
    hardwareDefaultsLabel_ = new QLabel(card);
    hardwareDefaultsLabel_->setObjectName(QStringLiteral("TrainHardwareDefaults"));
    hardwareDefaultsLabel_->setWordWrap(true);
    form->addWidget(hardwareDefaultsLabel_);
    root->addWidget(card);

    auto *actions = new QHBoxLayout;
    launchButton_ = new QPushButton(QStringLiteral("Launch trainer"), this);
    launchButton_->setObjectName(QStringLiteral("PrimaryActionButton"));
    spellvision::kit::setRole(launchButton_, spellvision::style::Role::Primary);
    datasetButton_ = new QPushButton(QStringLiteral("Open Dataset generator"), this);
    spellvision::kit::setRole(datasetButton_, spellvision::style::Role::Secondary);
    actions->addWidget(launchButton_);
    actions->addWidget(datasetButton_);
    actions->addStretch(1);
    root->addLayout(actions);

    logEdit_ = new QTextEdit(this);
    logEdit_->setObjectName(QStringLiteral("TrainLog"));
    logEdit_->setReadOnly(true);
    logEdit_->setMinimumHeight(160);
    logEdit_->setPlaceholderText(QStringLiteral("Launch log…"));
    root->addWidget(logEdit_, 1);

    connect(browseButton_, &QPushButton::clicked, this, &TrainPage::browseTrainer);
    connect(datasetBrowseButton_, &QPushButton::clicked, this, &TrainPage::browseDataset);
    connect(launchButton_, &QPushButton::clicked, this, &TrainPage::launchTrainer);
    connect(datasetButton_, &QPushButton::clicked, this, &TrainPage::openDataset);
    connect(pathEdit_, &QLineEdit::textChanged, this, [this](const QString &) { probeTrainer(); });
    connect(familyCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this,
            [this](int) { applyFamilyPreset(); });
}

void TrainPage::applyTheme()
{
    const auto &theme = ThemeManager::instance();
    using C = ThemeManager::Color;
    using T = ThemeManager::Type;
    setStyleSheet(QStringLiteral(
                      "#TrainPage { background: transparent; }"
                      "QLabel#TrainEyebrow { @caption@ letter-spacing: 0.12em; color: @acc@; }"
                      "QLabel#TrainTitle { @display@ color: @hi@; }"
                      "QLabel#TrainSub, QLabel#TrainStatus, QLabel#TrainHardwareDefaults { @body@ color: @mid@; }"
                      "QTextEdit, QLineEdit, QComboBox, QSpinBox { padding: 6px; }"
                      "QPushButton { padding: 8px 12px; min-height: 30px; }")
                      .replace(QLatin1String("@display@"), theme.fontCss(T::Display))
                      .replace(QLatin1String("@body@"), theme.fontCss(T::Body))
                      .replace(QLatin1String("@caption@"), theme.fontCss(T::Caption))
                      .replace(QLatin1String("@hi@"), theme.css(C::TextHi))
                      .replace(QLatin1String("@mid@"), theme.css(C::TextMid))
                      .replace(QLatin1String("@acc@"), theme.css(C::Accent)));
}

void TrainPage::probeTrainer()
{
    const QString path = pathEdit_ ? pathEdit_->text().trimmed() : QString();
    if (path.isEmpty()) {
        if (statusLabel_)
            statusLabel_->setText(QStringLiteral("No trainer path — Browse to a main.py or .exe."));
        if (launchButton_)
            launchButton_->setEnabled(false);
        return;
    }
    const bool ok = QFileInfo::exists(path);
    if (statusLabel_) {
        statusLabel_->setText(ok
                                  ? QStringLiteral("Ready: %1").arg(QDir::toNativeSeparators(path))
                                  : QStringLiteral("Path not found: %1").arg(path));
    }
    if (launchButton_)
        launchButton_->setEnabled(ok);
}

void TrainPage::refreshHardwareDefaults()
{
    if (!hardwareDefaultsLabel_)
        return;

    const GpuMemoryProbe::Reading gpu = GpuMemoryProbe::instance().read();
    const int gpuCount = gpu.valid ? 1 : 0;
    double ramGb = 0.0;
#ifdef Q_OS_WIN
    MEMORYSTATUSEX status;
    status.dwLength = sizeof(status);
    if (GlobalMemoryStatusEx(&status))
        ramGb = static_cast<double>(status.ullTotalPhys) / (1024.0 * 1024.0 * 1024.0);
#endif
    const double vramGb = gpu.valid ? (gpu.totalMb / 1024.0) : 0.0;
    const int rank = vramGb >= 24.0 ? 16 : 8;
    const int batch = vramGb >= 24.0 ? 2 : 1;
    if (rankSpin_)
        rankSpin_->setValue(rank);
    if (batchSpin_)
        batchSpin_->setValue(batch);

    QString text;
    if (!gpu.valid)
        text = QStringLiteral("VRAM unknown — LoRA rank/batch withheld. No house checkpoint. No house LoRA.");
    else
        text = QStringLiteral(
                   "This machine: %1 GB VRAM, %2 GB RAM, %3 GPU. "
                   "Single-GPU LoRA preset for krea2 / sdxl / flux / wan / ltx: batch %4, rank %5. "
                   "Multi-GPU / PAIR: cluster not joined — fail-closed. "
                   "No house checkpoint. No house LoRA.")
                   .arg(vramGb, 0, 'f', 0)
                   .arg(ramGb, 0, 'f', 0)
                   .arg(gpuCount)
                   .arg(batch)
                   .arg(rank);
    hardwareDefaultsLabel_->setText(text);
}

void TrainPage::applyFamilyPreset()
{
    // Rank/batch come from this machine, not a second UI per family. Changing family
    // re-applies the hardware preset so Simple stays OP; Advanced can then edit in place.
    refreshHardwareDefaults();
}

void TrainPage::writeRecipeSidecar() const
{
    const QString destRoot = lastDatasetRoot();
    if (destRoot.isEmpty())
        return;
    QDir().mkpath(destRoot);
    QJsonObject recipe;
    recipe.insert(QStringLiteral("family"),
                  familyCombo_ ? familyCombo_->currentData().toString() : QString());
    recipe.insert(QStringLiteral("rank"), rankSpin_ ? rankSpin_->value() : 0);
    recipe.insert(QStringLiteral("batch"), batchSpin_ ? batchSpin_->value() : 0);
    recipe.insert(QStringLiteral("dataset"), destRoot);
    recipe.insert(QStringLiteral("cluster_joined"), false);
    const QString path = QDir(destRoot).filePath(QStringLiteral("train_recipe.json"));
    QFile f(path);
    if (!f.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return;
    f.write(QJsonDocument(recipe).toJson(QJsonDocument::Indented));
}

void TrainPage::browseTrainer()
{
    const QString path = QFileDialog::getOpenFileName(
        this, QStringLiteral("Select trainer entry"), projectRoot_,
        QStringLiteral("Python/Executable (*.py *.exe);;All files (*.*)"));
    if (path.isEmpty() || !pathEdit_)
        return;
    pathEdit_->setText(QDir::toNativeSeparators(path));
    QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    s.setValue(QStringLiteral("train/sohyaPath"), pathEdit_->text());
    probeTrainer();
}

void TrainPage::browseDataset()
{
    const QString start = lastDatasetRoot().isEmpty() ? projectRoot_ : lastDatasetRoot();
    const QString path = QFileDialog::getExistingDirectory(this, QStringLiteral("Select dataset folder"), start);
    if (path.isEmpty() || !datasetEdit_)
        return;
    datasetEdit_->setText(QDir::toNativeSeparators(path));
    QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    s.setValue(QStringLiteral("train/lastDatasetRoot"), datasetEdit_->text());
}

void TrainPage::appendLog(const QString &line)
{
    if (logEdit_)
        logEdit_->append(line.trimmed());
}

void TrainPage::launchTrainer()
{
    const QString path = pathEdit_ ? pathEdit_->text().trimmed() : QString();
    if (path.isEmpty() || !QFileInfo::exists(path)) {
        appendLog(QStringLiteral("Blocked: trainer path missing."));
        return;
    }

    QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    s.setValue(QStringLiteral("train/sohyaPath"), path);
    if (!lastDatasetRoot().isEmpty())
        s.setValue(QStringLiteral("train/lastDatasetRoot"), lastDatasetRoot());

    writeRecipeSidecar();
    const QString family = familyCombo_ ? familyCombo_->currentData().toString() : QString();
    appendLog(QStringLiteral("Recipe: family=%1 rank=%2 batch=%3 dataset=%4 cluster=fail-closed")
                  .arg(family)
                  .arg(rankSpin_ ? rankSpin_->value() : 0)
                  .arg(batchSpin_ ? batchSpin_->value() : 0)
                  .arg(lastDatasetRoot().isEmpty() ? QStringLiteral("(none)") : lastDatasetRoot()));

    if (process_) {
        process_->kill();
        process_->deleteLater();
        process_ = nullptr;
    }

    process_ = new QProcess(this);
    process_->setProcessChannelMode(QProcess::MergedChannels);
    QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
    environment.remove(QStringLiteral("PYTHONPATH"));
    environment.remove(QStringLiteral("PYTHONHOME"));
    environment.insert(QStringLiteral("PYTHONNOUSERSITE"), QStringLiteral("1"));
    process_->setProcessEnvironment(environment);
    connect(process_, &QProcess::readyReadStandardOutput, this, [this]() {
        if (process_)
            appendLog(QString::fromUtf8(process_->readAllStandardOutput()));
    });
    connect(process_, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this](int code, QProcess::ExitStatus) {
                appendLog(QStringLiteral("Trainer exited (%1)").arg(code));
            });

    const QFileInfo fi(path);
    if (fi.suffix().compare(QStringLiteral("py"), Qt::CaseInsensitive) == 0) {
        // Prefer trainer venv if present beside main.py, else SpellVision venv, else system python.
        QString python = QDir(fi.absolutePath()).filePath(QStringLiteral(".venv/Scripts/python.exe"));
        if (!QFileInfo::exists(python) && !projectRoot_.isEmpty())
            python = QDir(projectRoot_).filePath(QStringLiteral(".venv/Scripts/python.exe"));
        if (!QFileInfo::exists(python))
            python = QStringLiteral("python");
        process_->setWorkingDirectory(fi.absolutePath());
        appendLog(QStringLiteral("Launching: %1 %2").arg(python, path));
        process_->start(python, {path});
    } else {
        process_->setWorkingDirectory(fi.absolutePath());
        appendLog(QStringLiteral("Launching: %1").arg(path));
        process_->start(path, {});
    }

    if (!process_->waitForStarted(4000)) {
        appendLog(QStringLiteral("Failed to start trainer process."));
        process_->deleteLater();
        process_ = nullptr;
        return;
    }
    appendLog(QStringLiteral("Trainer started (PID %1). Configure house LoRA in Character → Advanced when training finishes.")
                  .arg(process_->processId()));
}

void TrainPage::openDataset()
{
    emit openDatasetRequested();
    emit navigateRequested(QStringLiteral("dataset"));
}
