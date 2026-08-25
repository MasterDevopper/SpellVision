#include "Gen3DPage.h"

#include "ThemeManager.h"
#include "widgets/DropTargetFrame.h"

#include <QComboBox>
#include <QDesktopServices>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QPushButton>
#include <QTextEdit>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>

Gen3DPage::Gen3DPage(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("Gen3DPage"));
    buildUi();
    applyTheme();
    probeComfyPath();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });
    // Re-probe Comfy a few times so a late-start runtime is detected.
    QTimer::singleShot(2000, this, [this]() { probeComfyPath(); });
}

void Gen3DPage::setProjectRoot(const QString &root)
{
    projectRoot_ = root.trimmed();
}

void Gen3DPage::setInputImage(const QString &path)
{
    if (primaryEdit_)
        primaryEdit_->setText(QDir::toNativeSeparators(path));
}

void Gen3DPage::updateDisclosure(bool advanced)
{
    advanced_ = advanced;
    if (resCombo_)
        resCombo_->setVisible(advanced);
}

void Gen3DPage::setBusy(bool busy, const QString &message)
{
    busy_ = busy;
    if (generateButton_)
        generateButton_->setEnabled(!busy && comfyReachable_);
    if (statusLabel_)
        statusLabel_->setText(message.isEmpty() ? (busy ? QStringLiteral("Running…") : QStringLiteral("Idle"))
                                                : message);
}

void Gen3DPage::setResultMesh(const QString &path, const QString &caption)
{
    if (resultLabel_)
        resultLabel_->setText(caption.isEmpty()
                                  ? QStringLiteral("Mesh: %1").arg(QDir::toNativeSeparators(path))
                                  : caption);
    appendLog(QStringLiteral("Result: %1").arg(path));
}

void Gen3DPage::setAvailableWorkflows(const QVector<QJsonObject> &profiles)
{
    workflowProfiles_ = profiles;
    if (!workflowCombo_)
        return;

    const QString previous = workflowCombo_->currentData().toString();
    workflowCombo_->blockSignals(true);
    workflowCombo_->clear();
    workflowCombo_->addItem(QStringLiteral("— Select a 3D workflow from Flows —"), QString());

    auto looks3d = [](const QJsonObject &p) -> bool {
        const QString hay =
            (p.value(QStringLiteral("profile_name")).toString() + QLatin1Char(' ')
             + p.value(QStringLiteral("display_name")).toString() + QLatin1Char(' ')
             + p.value(QStringLiteral("workflow_path")).toString() + QLatin1Char(' ')
             + p.value(QStringLiteral("source_workflow_path")).toString() + QLatin1Char(' ')
             + p.value(QStringLiteral("task_command")).toString() + QLatin1Char(' ')
             + p.value(QStringLiteral("media_type")).toString()
             + p.value(QStringLiteral("tags")).toVariant().toStringList().join(QLatin1Char(' ')))
                .toLower();
        return hay.contains(QStringLiteral("3d"))
               || hay.contains(QStringLiteral("trellis"))
               || hay.contains(QStringLiteral("pixal"))
               || hay.contains(QStringLiteral("hunyuan3d"))
               || hay.contains(QStringLiteral("i23d"))
               || hay.contains(QStringLiteral("mesh"))
               || hay.contains(QStringLiteral("glb"))
               || p.value(QStringLiteral("task_command")).toString().contains(QStringLiteral("i23d"), Qt::CaseInsensitive);
    };

    int preferred = -1;
    for (const QJsonObject &p : workflowProfiles_) {
        const QString path = p.value(QStringLiteral("workflow_path")).toString(
            p.value(QStringLiteral("source_workflow_path")).toString());
        if (path.isEmpty())
            continue;
        const bool is3d = looks3d(p);
        const QString name = p.value(QStringLiteral("display_name")).toString(
            p.value(QStringLiteral("profile_name")).toString(QFileInfo(path).fileName()));
        const QString label = is3d ? QStringLiteral("✦ %1").arg(name) : name;
        workflowCombo_->addItem(label, path);
        if (is3d && preferred < 0)
            preferred = workflowCombo_->count() - 1;
    }

    int restore = workflowCombo_->findData(previous);
    if (restore >= 0)
        workflowCombo_->setCurrentIndex(restore);
    else if (preferred >= 0)
        workflowCombo_->setCurrentIndex(preferred);
    else
        workflowCombo_->setCurrentIndex(0);
    workflowCombo_->blockSignals(false);

    if (toolLabel_ && workflowCombo_->count() <= 1) {
        toolLabel_->setText(
            toolLabel_->text()
            + QStringLiteral(" No imported workflows yet — open Flows and import a Trellis/Pixal/Hunyuan3D graph."));
    }
}

void Gen3DPage::buildUi()
{
    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(16, 14, 16, 14);
    root->setSpacing(10);

    auto *eyebrow = new QLabel(QStringLiteral("3D GENERATION"), this);
    eyebrow->setObjectName(QStringLiteral("G3Eyebrow"));
    auto *title = new QLabel(QStringLiteral("Image → Mesh (ComfyUI)"), this);
    title->setObjectName(QStringLiteral("G3Title"));
    auto *sub = new QLabel(
        QStringLiteral("Runs through ComfyUI only — never a standalone GPU process. "
                       "There is no in-page mesh viewer. If a workflow writes a .glb, "
                       "watch History / the mesh folder. Import the graph in Flows first."),
        this);
    sub->setObjectName(QStringLiteral("G3Sub"));
    sub->setWordWrap(true);
    root->addWidget(eyebrow);
    root->addWidget(title);
    root->addWidget(sub);

    toolLabel_ = new QLabel(this);
    toolLabel_->setObjectName(QStringLiteral("G3Tools"));
    toolLabel_->setWordWrap(true);
    root->addWidget(toolLabel_);

    auto *card = new QFrame(this);
    card->setObjectName(QStringLiteral("G3Card"));
    auto *form = new QGridLayout(card);
    form->setContentsMargins(12, 12, 12, 12);
    form->setHorizontalSpacing(10);
    form->setVerticalSpacing(8);

    form->addWidget(new QLabel(QStringLiteral("Primary image"), card), 0, 0);
    auto *inputRow = new QHBoxLayout();
    primaryEdit_ = new QLineEdit(card);
    primaryEdit_->setPlaceholderText(QStringLiteral("Drop or browse a concept / reference PNG…"));
    browseButton_ = new QPushButton(QStringLiteral("Browse"), card);
    inputRow->addWidget(primaryEdit_, 1);
    inputRow->addWidget(browseButton_);
    form->addLayout(inputRow, 0, 1);

    auto *drop = new spellvision::widgets::DropTargetFrame(card);
    drop->setObjectName(QStringLiteral("G3Drop"));
    drop->setMinimumHeight(64);
    auto *dropLab = new QLabel(QStringLiteral("Drop primary image here"), drop);
    dropLab->setAlignment(Qt::AlignCenter);
    auto *dropLay = new QVBoxLayout(drop);
    dropLay->addWidget(dropLab);
    drop->onFileDropped = [this](const QString &path) {
        if (!path.isEmpty())
            setInputImage(path);
    };
    form->addWidget(drop, 1, 0, 1, 2);

    form->addWidget(new QLabel(QStringLiteral("Backend"), card), 2, 0);
    backendCombo_ = new QComboBox(card);
    backendCombo_->addItem(QStringLiteral("Pixal3D (single image → mesh)"), int(Backend::Pixal3D));
    backendCombo_->addItem(QStringLiteral("TRELLIS.2 (multi-view angles)"), int(Backend::Trellis2));
    connect(backendCombo_, QOverload<int>::of(&QComboBox::currentIndexChanged), this,
            [this](int) { onBackendChanged(); });
    form->addWidget(backendCombo_, 2, 1);

    form->addWidget(new QLabel(QStringLiteral("Comfy workflow"), card), 3, 0);
    workflowCombo_ = new QComboBox(card);
    workflowCombo_->addItem(QStringLiteral("— Select a 3D workflow from Flows —"), QString());
    workflowCombo_->setToolTip(
        QStringLiteral("i23d requires a Comfy workflow binding. Import Trellis/Pixal/Hunyuan3D graphs in Flows, "
                       "then pick them here. Generate will not start a standalone GPU process."));
    form->addWidget(workflowCombo_, 3, 1);

    form->addWidget(new QLabel(QStringLiteral("Output tag"), card), 4, 0);
    outTagEdit_ = new QLineEdit(card);
    outTagEdit_->setText(QStringLiteral("sv3d"));
    form->addWidget(outTagEdit_, 4, 1);

    form->addWidget(new QLabel(QStringLiteral("Target res (Advanced)"), card), 5, 0);
    resCombo_ = new QComboBox(card);
    resCombo_->addItem(QStringLiteral("1024"), 1024);
    resCombo_->addItem(QStringLiteral("1280"), 1280);
    resCombo_->addItem(QStringLiteral("1536"), 1536);
    resCombo_->setCurrentIndex(2);
    resCombo_->setVisible(false);
    form->addWidget(resCombo_, 5, 1);

    // TRELLIS multi-view block
    multiViewBlock_ = new QWidget(card);
    auto *mv = new QVBoxLayout(multiViewBlock_);
    mv->setContentsMargins(0, 6, 0, 0);
    mv->setSpacing(6);
    mv->addWidget(new QLabel(QStringLiteral("Multi-view plates (TRELLIS.2)"), multiViewBlock_));
    angleList_ = new QListWidget(multiViewBlock_);
    angleList_->setMinimumHeight(90);
    mv->addWidget(angleList_);
    auto *angleRow = new QHBoxLayout;
    angleCombo_ = new QComboBox(multiViewBlock_);
    angleCombo_->addItem(QStringLiteral("Front"), QStringLiteral("front"));
    angleCombo_->addItem(QStringLiteral("Back"), QStringLiteral("back"));
    angleCombo_->addItem(QStringLiteral("Left"), QStringLiteral("left"));
    angleCombo_->addItem(QStringLiteral("Right"), QStringLiteral("right"));
    angleCombo_->addItem(QStringLiteral("Three-quarter"), QStringLiteral("three_quarter"));
    angleCombo_->addItem(QStringLiteral("Top"), QStringLiteral("top"));
    addAngleButton_ = new QPushButton(QStringLiteral("Add image…"), multiViewBlock_);
    removeAngleButton_ = new QPushButton(QStringLiteral("Remove"), multiViewBlock_);
    connect(addAngleButton_, &QPushButton::clicked, this, &Gen3DPage::addAngleImage);
    connect(removeAngleButton_, &QPushButton::clicked, this, &Gen3DPage::removeSelectedAngle);
    angleRow->addWidget(angleCombo_, 1);
    angleRow->addWidget(addAngleButton_);
    angleRow->addWidget(removeAngleButton_);
    mv->addLayout(angleRow);
    multiViewBlock_->setVisible(false);
    form->addWidget(multiViewBlock_, 6, 0, 1, 2);

    root->addWidget(card);

    auto *actions = new QHBoxLayout();
    generateButton_ = new QPushButton(QStringLiteral("Generate via ComfyUI"), this);
    generateButton_->setObjectName(QStringLiteral("PrimaryActionButton"));
    openOutButton_ = new QPushButton(QStringLiteral("Open mesh folder"), this);
    openFlowsButton_ = new QPushButton(QStringLiteral("Open Flows"), this);
    actions->addWidget(generateButton_);
    actions->addWidget(openOutButton_);
    actions->addWidget(openFlowsButton_);
    actions->addStretch(1);
    root->addLayout(actions);

    statusLabel_ = new QLabel(QStringLiteral("Idle"), this);
    statusLabel_->setObjectName(QStringLiteral("G3Status"));
    resultLabel_ = new QLabel(QStringLiteral("No mesh viewer in this page. Queued jobs do not appear here."), this);
    resultLabel_->setObjectName(QStringLiteral("G3Result"));
    resultLabel_->setWordWrap(true);
    root->addWidget(statusLabel_);
    root->addWidget(resultLabel_);

    logEdit_ = new QTextEdit(this);
    logEdit_->setObjectName(QStringLiteral("G3Log"));
    logEdit_->setReadOnly(true);
    logEdit_->setMinimumHeight(140);
    logEdit_->setPlaceholderText(QStringLiteral("Comfy / worker log…"));
    root->addWidget(logEdit_, 1);

    connect(browseButton_, &QPushButton::clicked, this, &Gen3DPage::browsePrimary);
    connect(generateButton_, &QPushButton::clicked, this, &Gen3DPage::runGenerate);
    connect(openOutButton_, &QPushButton::clicked, this, [this]() {
        const QString dir = defaultOutDir();
        QDir().mkpath(dir);
        QDesktopServices::openUrl(QUrl::fromLocalFile(dir));
    });
    connect(openFlowsButton_, &QPushButton::clicked, this, [this]() {
        emit openWorkflowsRequested();
        emit navigateRequested(QStringLiteral("workflows"));
    });

    onBackendChanged();
}

void Gen3DPage::applyTheme()
{
    const auto &theme = ThemeManager::instance();
    using C = ThemeManager::Color;
    using T = ThemeManager::Type;
    setStyleSheet(QStringLiteral(
                      "#Gen3DPage { background: transparent; }"
                      "QLabel#G3Eyebrow { @caption@ letter-spacing: 0.12em; color: @acc@; }"
                      "QLabel#G3Title { @display@ color: @hi@; }"
                      "QLabel#G3Sub, QLabel#G3Tools, QLabel#G3Status, QLabel#G3Result { @body@ color: @mid@; }"
                      "QFrame#G3Card, QFrame#G3Drop {"
                      " background: @s1@; border: 1px solid @bd@; border-radius: 10px; }"
                      "QTextEdit, QLineEdit, QComboBox, QListWidget {"
                      " background: rgba(10,11,18,0.55); color: @hi@; border: 1px solid @bd@;"
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
                      .replace(QLatin1String("@bd@"), theme.css(C::Border))
                      .replace(QLatin1String("@acc@"), theme.css(C::Accent)));
}

void Gen3DPage::probeComfyPath()
{
    // Lightweight HTTP probe — does not start heavy 3D models.
    auto *nam = new QNetworkAccessManager(this);
    QNetworkRequest req(QUrl(QStringLiteral("http://127.0.0.1:8188/system_stats")));
    req.setHeader(QNetworkRequest::UserAgentHeader, QStringLiteral("SpellVision-Gen3D"));
    QNetworkReply *reply = nam->get(req);
    connect(reply, &QNetworkReply::finished, this, [this, reply, nam]() {
        comfyReachable_ = (reply->error() == QNetworkReply::NoError);
        reply->deleteLater();
        nam->deleteLater();
        if (toolLabel_) {
            if (comfyReachable_) {
                toolLabel_->setText(
                    QStringLiteral("ComfyUI online (:8188). Generation uses Comfy graph execution only. "
                                   "Import a Trellis/Pixal3D workflow in Flows if one is not ready yet. "
                                   "Standalone spike processes are disabled."));
            } else {
                toolLabel_->setText(
                    QStringLiteral("ComfyUI not reachable on :8188. Restart SpellVision so it can start or adopt Comfy, "
                                   "or open Runtime and wait until the port answers. "
                                   "External Pixal/Trellis CLI is intentionally disabled to protect system stability."));
            }
        }
        if (generateButton_)
            generateButton_->setEnabled(comfyReachable_ && !busy_);
    });
}

void Gen3DPage::onBackendChanged()
{
    const bool trellis = currentBackend() == Backend::Trellis2;
    if (multiViewBlock_)
        multiViewBlock_->setVisible(trellis);
    if (statusLabel_) {
        statusLabel_->setText(trellis
                                  ? QStringLiteral("TRELLIS.2 — add front/side/back plates for best structure")
                                  : QStringLiteral("Pixal3D — single image path"));
    }
}

void Gen3DPage::browsePrimary()
{
    const QString path = QFileDialog::getOpenFileName(
        this, QStringLiteral("Select primary image"), projectRoot_,
        QStringLiteral("Images (*.png *.jpg *.jpeg *.webp)"));
    if (!path.isEmpty())
        setInputImage(path);
}

void Gen3DPage::addAngleImage()
{
    const QString path = QFileDialog::getOpenFileName(
        this, QStringLiteral("Add angled view"), projectRoot_,
        QStringLiteral("Images (*.png *.jpg *.jpeg *.webp)"));
    if (path.isEmpty())
        return;
    AngleSlot s;
    s.path = path;
    s.angle = angleCombo_ ? angleCombo_->currentData().toString() : QStringLiteral("front");
    angleSlots_.push_back(s);
    rebuildAngleList();
}

void Gen3DPage::removeSelectedAngle()
{
    if (!angleList_)
        return;
    const int row = angleList_->currentRow();
    if (row < 0 || row >= angleSlots_.size())
        return;
    angleSlots_.removeAt(row);
    rebuildAngleList();
}

void Gen3DPage::rebuildAngleList()
{
    if (!angleList_)
        return;
    angleList_->clear();
    for (const AngleSlot &s : angleSlots_) {
        angleList_->addItem(QStringLiteral("[%1] %2")
                                .arg(s.angle, QFileInfo(s.path).fileName()));
    }
}

Gen3DPage::Backend Gen3DPage::currentBackend() const
{
    if (!backendCombo_)
        return Backend::Pixal3D;
    return static_cast<Backend>(backendCombo_->currentData().toInt());
}

QString Gen3DPage::defaultOutDir() const
{
    if (!projectRoot_.isEmpty())
        return QDir(projectRoot_).filePath(QStringLiteral("runtime/meshes"));
    return QDir::temp().filePath(QStringLiteral("spellvision_meshes"));
}

void Gen3DPage::appendLog(const QString &line)
{
    if (logEdit_)
        logEdit_->append(line.trimmed());
}

QJsonObject Gen3DPage::buildComfyRequest() const
{
    QJsonObject req;
    req.insert(QStringLiteral("command"), QStringLiteral("enqueue"));
    // Prefer comfy_workflow when a graph is bound; worker still accepts i23d.
    const QString workflowPath = workflowCombo_ ? workflowCombo_->currentData().toString().trimmed() : QString();
    if (!workflowPath.isEmpty()) {
        req.insert(QStringLiteral("task_command"), QStringLiteral("comfy_workflow"));
        req.insert(QStringLiteral("workflow_path"), workflowPath);
        req.insert(QStringLiteral("source_workflow_path"), workflowPath);
        req.insert(QStringLiteral("queue_display_command"), QStringLiteral("i23d"));
    } else {
        req.insert(QStringLiteral("task_command"), QStringLiteral("i23d"));
    }
    req.insert(QStringLiteral("mode"), QStringLiteral("i23d"));
    req.insert(QStringLiteral("backend"),
               currentBackend() == Backend::Trellis2 ? QStringLiteral("trellis2")
                                                     : QStringLiteral("pixal3d"));
    req.insert(QStringLiteral("output_prefix"),
               outTagEdit_ ? outTagEdit_->text().trimmed() : QStringLiteral("sv3d"));
    req.insert(QStringLiteral("output_folder"), defaultOutDir());
    req.insert(QStringLiteral("width"), resCombo_ ? resCombo_->currentData().toInt() : 1536);
    req.insert(QStringLiteral("height"), resCombo_ ? resCombo_->currentData().toInt() : 1536);

    const QString primary = primaryEdit_ ? primaryEdit_->text().trimmed() : QString();
    req.insert(QStringLiteral("input_image"), primary);
    req.insert(QStringLiteral("image"), primary);
    // Common Comfy slot names used by image-to-3D graphs.
    req.insert(QStringLiteral("positive_prompt"),
               QStringLiteral("high quality game asset, clean topology friendly mesh"));
    req.insert(QStringLiteral("negative_prompt"),
               QStringLiteral("blurry, low quality, deformed"));

    QJsonArray views;
    // Always include primary as front if not already listed.
    bool hasFront = false;
    for (const AngleSlot &s : angleSlots_) {
        QJsonObject v;
        v.insert(QStringLiteral("path"), s.path);
        v.insert(QStringLiteral("angle"), s.angle);
        // Comfy LoadImage / multi-view node wiring keys (adapter maps these).
        v.insert(QStringLiteral("comfy_slot"), QStringLiteral("view_%1").arg(s.angle));
        views.append(v);
        if (s.angle == QStringLiteral("front"))
            hasFront = true;
    }
    if (!primary.isEmpty() && !hasFront) {
        QJsonObject v;
        v.insert(QStringLiteral("path"), primary);
        v.insert(QStringLiteral("angle"), QStringLiteral("front"));
        v.insert(QStringLiteral("comfy_slot"), QStringLiteral("view_front"));
        views.prepend(v);
    }
    req.insert(QStringLiteral("multi_view_images"), views);
    req.insert(QStringLiteral("execution_engine"), QStringLiteral("comfyui"));
    req.insert(QStringLiteral("forbid_external_process"), true);
    return req;
}

void Gen3DPage::runGenerate()
{
    if (busy_)
        return;
    if (!comfyReachable_) {
        appendLog(QStringLiteral("Blocked: ComfyUI offline. Start Comfy first — no external 3D process will run."));
        if (statusLabel_)
            statusLabel_->setText(QStringLiteral("ComfyUI offline"));
        return;
    }

    const QString primary = primaryEdit_ ? primaryEdit_->text().trimmed() : QString();
    if (primary.isEmpty() || !QFileInfo::exists(primary)) {
        appendLog(QStringLiteral("Blocked: primary image required."));
        return;
    }

    const QString workflowPath = workflowCombo_ ? workflowCombo_->currentData().toString().trimmed() : QString();
    if (workflowPath.isEmpty()) {
        appendLog(QStringLiteral(
            "Blocked: pick a Comfy workflow (import Trellis/Pixal/Hunyuan3D in Flows first). "
            "Standalone spike processes stay disabled."));
        if (statusLabel_)
            statusLabel_->setText(QStringLiteral("Workflow required"));
        return;
    }

    if (currentBackend() == Backend::Trellis2 && angleSlots_.isEmpty()) {
        appendLog(QStringLiteral("Tip: TRELLIS.2 works better with 2–4 angled plates (front/side/back). "
                                 "Proceeding with primary as front-only."));
    }

    const QJsonObject req = buildComfyRequest();
    appendLog(QStringLiteral("Submitting via ComfyUI (workflow=%1, backend=%2, views=%3)…")
                  .arg(QFileInfo(workflowPath).fileName(),
                       req.value(QStringLiteral("backend")).toString())
                  .arg(req.value(QStringLiteral("multi_view_images")).toArray().size()));
    setBusy(true, QStringLiteral("Queued on ComfyUI…"));
    emit comfyGenerateRequested(req);
}
