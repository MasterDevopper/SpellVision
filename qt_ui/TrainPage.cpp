#include "TrainPage.h"

#include "ThemeManager.h"

#include <QDesktopServices>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QProcess>
#include <QPushButton>
#include <QSettings>
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
    }
    probeTrainer();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });
}

void TrainPage::setProjectRoot(const QString &root)
{
    projectRoot_ = root.trimmed();
}

QString TrainPage::defaultSohyaPath() const
{
    return QString();
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
        QStringLiteral("This is not an in-app training studio. Browse to a trainer entry "
                       "(main.py / .exe) you already have, then Launch. Dataset generates "
                       "images; this page only starts the external trainer."),
        this);
    sub->setObjectName(QStringLiteral("TrainSub"));
    sub->setWordWrap(true);
    root->addWidget(eyebrow);
    root->addWidget(title);
    root->addWidget(sub);

    auto *card = new QFrame(this);
    card->setObjectName(QStringLiteral("TrainCard"));
    auto *form = new QVBoxLayout(card);
    form->setContentsMargins(12, 12, 12, 12);
    form->setSpacing(8);
    form->addWidget(new QLabel(QStringLiteral("Trainer entry (main.py / .exe)"), card));
    auto *row = new QHBoxLayout;
    pathEdit_ = new QLineEdit(card);
    pathEdit_->setPlaceholderText(QStringLiteral("Path to trainer main.py or .exe…"));
    browseButton_ = new QPushButton(QStringLiteral("Browse"), card);
    row->addWidget(pathEdit_, 1);
    row->addWidget(browseButton_);
    form->addLayout(row);
    statusLabel_ = new QLabel(card);
    statusLabel_->setObjectName(QStringLiteral("TrainStatus"));
    statusLabel_->setWordWrap(true);
    form->addWidget(statusLabel_);
    root->addWidget(card);

    auto *actions = new QHBoxLayout;
    launchButton_ = new QPushButton(QStringLiteral("Launch trainer"), this);
    launchButton_->setObjectName(QStringLiteral("PrimaryActionButton"));
    datasetButton_ = new QPushButton(QStringLiteral("Open Dataset generator"), this);
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
    connect(launchButton_, &QPushButton::clicked, this, &TrainPage::launchTrainer);
    connect(datasetButton_, &QPushButton::clicked, this, &TrainPage::openDataset);
    connect(pathEdit_, &QLineEdit::textChanged, this, [this](const QString &) { probeTrainer(); });
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
                      "QLabel#TrainSub, QLabel#TrainStatus { @body@ color: @mid@; }"
                      "QFrame#TrainCard {"
                      " background: @s1@; border: 1px solid @bd@; border-radius: 10px; }"
                      "QTextEdit, QLineEdit {"
                      " background: @s0@; color: @hi@; border: 1px solid @bd@;"
                      " border-radius: 6px; padding: 6px; }"
                      "QPushButton#PrimaryActionButton {"
                      " background: @acc@; color: white; border: none; border-radius: 8px;"
                      " padding: 10px 16px; font-weight: 700; }"
                      "QPushButton {"
                      " background: rgba(255,255,255,0.03); color: @hi@;"
                      " border: 1px solid @bd@; border-radius: 6px; padding: 8px 12px; }")
                      .replace(QLatin1String("@display@"), theme.fontCss(T::Display))
                      .replace(QLatin1String("@body@"), theme.fontCss(T::Body))
                      .replace(QLatin1String("@caption@"), theme.fontCss(T::Caption))
                      .replace(QLatin1String("@hi@"), theme.css(C::TextHi))
                      .replace(QLatin1String("@mid@"), theme.css(C::TextMid))
                      .replace(QLatin1String("@s1@"), theme.css(C::Surface1))
                      .replace(QLatin1String("@s0@"), theme.css(C::Surface0))
                      .replace(QLatin1String("@bd@"), theme.css(C::Border))
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

    if (process_) {
        process_->kill();
        process_->deleteLater();
        process_ = nullptr;
    }

    process_ = new QProcess(this);
    process_->setProcessChannelMode(QProcess::MergedChannels);
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
