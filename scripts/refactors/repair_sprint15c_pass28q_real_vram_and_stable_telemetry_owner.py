from pathlib import Path

h_path = Path("qt_ui/MainWindow.h")
cpp_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28q_real_vram_and_stable_telemetry_owner.py")

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")


def replace_function(text: str, signature: str, replacement: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"Could not find function signature: {signature}")

    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"Could not find opening brace for: {signature}")

    depth = 0
    end = None
    in_string = False
    in_char = False
    escaped = False

    for index in range(brace, len(text)):
        ch = text[index]

        if escaped:
            escaped = False
            continue

        if ch == "\\":
            escaped = True
            continue

        if ch == '"' and not in_char:
            in_string = not in_string
            continue

        if ch == "'" and not in_string:
            in_char = not in_char
            continue

        if in_string or in_char:
            continue

        if ch == "{":
            depth += 1
            continue

        if ch == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    if end is None:
        raise SystemExit(f"Could not find closing brace for: {signature}")

    return text[:start] + replacement.rstrip() + "\n" + text[end:]


# ----------------------------------------------------------------------
# 1) Header additions.
# ----------------------------------------------------------------------

if "void startVramTelemetryPolling();" not in h:
    marker = "    void syncBottomTelemetry();\n"
    if marker not in h:
        raise SystemExit("Could not find syncBottomTelemetry declaration.")
    h = h.replace(
        marker,
        marker + "    void startVramTelemetryPolling();\n    void pollVramTelemetry();\n",
        1,
    )

if "QTimer *vramTelemetryTimer_" not in h:
    marker = "    QProgressBar *bottomProgressBar_ = nullptr;\n"
    if marker not in h:
        raise SystemExit("Could not find bottomProgressBar_ member.")
    h = h.replace(
        marker,
        marker + "    QTimer *vramTelemetryTimer_ = nullptr;\n    QString lastVramTelemetryText_ = QStringLiteral(\"VRAM: checking\");\n",
        1,
    )

h_path.write_text(h, encoding="utf-8")


# ----------------------------------------------------------------------
# 2) Includes.
# ----------------------------------------------------------------------

for include in [
    "#include <QProcess>",
    "#include <QTimer>",
    "#include <QLabel>",
    "#include <QSizePolicy>",
]:
    if include not in cpp:
        anchor = "#include <QPushButton>"
        if anchor in cpp:
            cpp = cpp.replace(anchor, include + "\n" + anchor, 1)
        else:
            cpp = include + "\n" + cpp


# ----------------------------------------------------------------------
# 3) Local telemetry helpers.
# ----------------------------------------------------------------------

helper = r'''
QString pass28qQueueStateText(QueueItemState state)
{
    switch (state)
    {
    case QueueItemState::Queued:
        return QStringLiteral("Queued");
    case QueueItemState::Preparing:
        return QStringLiteral("Preparing");
    case QueueItemState::Running:
        return QStringLiteral("Running");
    case QueueItemState::Completed:
        return QStringLiteral("Completed");
    case QueueItemState::Failed:
        return QStringLiteral("Failed");
    case QueueItemState::Cancelled:
        return QStringLiteral("Cancelled");
    case QueueItemState::Skipped:
        return QStringLiteral("Skipped");
    case QueueItemState::Unknown:
    default:
        return QStringLiteral("Unknown");
    }
}

QStringList pass28qAcceptedCommandsForMode(const QString &modeId)
{
    const QString mode = modeId.trimmed().toLower();

    if (mode == QStringLiteral("t2i"))
        return {QStringLiteral("t2i"), QStringLiteral("txt2img"), QStringLiteral("text_to_image")};

    if (mode == QStringLiteral("i2i"))
        return {QStringLiteral("i2i"), QStringLiteral("img2img"), QStringLiteral("image_to_image")};

    if (mode == QStringLiteral("t2v"))
        return {QStringLiteral("t2v"), QStringLiteral("text_to_video")};

    if (mode == QStringLiteral("i2v"))
        return {QStringLiteral("i2v"), QStringLiteral("image_to_video")};

    return {};
}

bool pass28qItemMatchesMode(const QueueItem &item, const QString &modeId)
{
    const QStringList accepted = pass28qAcceptedCommandsForMode(modeId);
    if (accepted.isEmpty())
        return true;

    return accepted.contains(item.command.trimmed().toLower());
}

bool pass28qItemIsActive(const QueueItem &item)
{
    if (item.isTerminal())
        return false;

    return item.running ||
           item.state == QueueItemState::Queued ||
           item.state == QueueItemState::Preparing ||
           item.state == QueueItemState::Running;
}

bool pass28qModeIsImage(const QString &modeId)
{
    const QString mode = modeId.trimmed().toLower();
    return mode == QStringLiteral("t2i") || mode == QStringLiteral("i2i");
}

QString pass28qFormatVramText(double usedMb, double totalMb)
{
    if (usedMb < 0.0 || totalMb <= 0.0)
        return QStringLiteral("VRAM: unavailable");

    const double usedGb = usedMb / 1024.0;
    const double totalGb = totalMb / 1024.0;

    return QStringLiteral("VRAM: %1/%2 GB")
        .arg(usedGb, 0, 'f', 1)
        .arg(totalGb, 0, 'f', 0);
}
'''

if "pass28qFormatVramText" not in cpp:
    if "namespace\n{\n" not in cpp:
        raise SystemExit("Could not find anonymous namespace start.")
    cpp = cpp.replace("namespace\n{\n", "namespace\n{\n" + helper + "\n", 1)


# ----------------------------------------------------------------------
# 4) Build bar: fixed geometry + start VRAM polling.
# ----------------------------------------------------------------------

build_replacement = r'''
void MainWindow::buildBottomTelemetryBar()
{
    spellvision::shell::BottomTelemetryPresenter::BuildBindings bindings;
    bindings.owner = this;
    bindings.statusBar = statusBar();
    bindings.readyLabel = &bottomReadyLabel_;
    bindings.pageLabel = &bottomPageLabel_;
    bindings.runtimeLabel = &bottomRuntimeLabel_;
    bindings.queueLabel = &bottomQueueLabel_;
    bindings.vramLabel = &bottomVramLabel_;
    bindings.modelLabel = &bottomModelLabel_;
    bindings.loraLabel = &bottomLoraLabel_;
    bindings.stateLabel = &bottomStateLabel_;
    bindings.progressBar = &bottomProgressBar_;

    spellvision::shell::BottomTelemetryPresenter::build(bindings);

    // Pass 28Q:
    // Bottom telemetry is now rendered as fixed cells owned by MainWindow.
    // The presenter creates widgets; MainWindow owns live values.
    if (statusBar())
    {
        statusBar()->setSizeGripEnabled(false);
        statusBar()->setFixedHeight(36);
        statusBar()->setMinimumHeight(36);
        statusBar()->setMaximumHeight(36);
    }

    auto stabilizeLabel = [](QLabel *label, int width) {
        if (!label)
            return;

        label->setFixedWidth(width);
        label->setMinimumHeight(24);
        label->setMaximumHeight(24);
        label->setWordWrap(false);
        label->setTextInteractionFlags(Qt::NoTextInteraction);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    };

    stabilizeLabel(bottomReadyLabel_, 64);
    stabilizeLabel(bottomPageLabel_, 150);
    stabilizeLabel(bottomRuntimeLabel_, 150);
    stabilizeLabel(bottomQueueLabel_, 104);
    stabilizeLabel(bottomVramLabel_, 170);
    stabilizeLabel(bottomModelLabel_, 210);
    stabilizeLabel(bottomLoraLabel_, 150);
    stabilizeLabel(bottomStateLabel_, 96);

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setObjectName(QStringLiteral("BottomProgressBar"));
        bottomProgressBar_->setRange(0, 100);
        bottomProgressBar_->setValue(0);
        bottomProgressBar_->setTextVisible(true);
        bottomProgressBar_->setFormat(QStringLiteral(""));
        bottomProgressBar_->setFixedSize(164, 18);
        bottomProgressBar_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
        bottomProgressBar_->setStyleSheet(QStringLiteral(
            "QProgressBar#BottomProgressBar {"
            " border: 1px solid rgba(90,150,220,120);"
            " border-radius: 8px;"
            " background: rgba(6,12,24,190);"
            " color: rgba(220,235,255,235);"
            " font-size: 9px;"
            " text-align: center;"
            "}"
            "QProgressBar#BottomProgressBar::chunk {"
            " border-radius: 7px;"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            " stop:0 rgba(67,137,220,230),"
            " stop:1 rgba(142,92,210,230));"
            "}"
        ));
    }

    startVramTelemetryPolling();
    syncBottomTelemetry();
}
'''

cpp = replace_function(cpp, "void MainWindow::buildBottomTelemetryBar()", build_replacement)


# ----------------------------------------------------------------------
# 5) MainWindow-owned telemetry sync. No BottomTelemetryPresenter::sync fight.
# ----------------------------------------------------------------------

sync_replacement = r'''
void MainWindow::syncBottomTelemetry()
{
    const bool imageWorkspace = pass28qModeIsImage(currentModeId_);

    const QueueItem *activeItem = nullptr;
    int visibleQueueCount = 0;
    int activeProgress = 0;

    if (queueManager_)
    {
        const QVector<QueueItem> &items = queueManager_->items();

        for (const QueueItem &item : items)
        {
            if (!pass28qItemMatchesMode(item, currentModeId_))
                continue;

            if (pass28qItemIsActive(item))
            {
                activeItem = &item;
                activeProgress = qMax(activeProgress, item.progressPercent());

                if (activeProgress <= 0 && item.state == QueueItemState::Preparing)
                    activeProgress = 5;

                if (activeProgress <= 0 && item.state == QueueItemState::Running)
                    activeProgress = 8;

                continue;
            }

            if (imageWorkspace)
            {
                if (item.isTerminal())
                    ++visibleQueueCount;
            }
            else
            {
                ++visibleQueueCount;
            }
        }
    }

    if (queueTableView_ && queueTableView_->model())
        visibleQueueCount = queueTableView_->model()->rowCount();

    const bool busy = activeItem != nullptr;

    auto setLabelText = [](QLabel *label, const QString &text) {
        if (!label)
            return;

        if (label->text() != text)
            label->setText(text);
    };

    setLabelText(bottomReadyLabel_, busy ? QStringLiteral("Busy") : QStringLiteral("Ready"));
    setLabelText(bottomPageLabel_, pageContextForMode(currentModeId_));
    setLabelText(bottomRuntimeLabel_, QStringLiteral("Runtime: local"));
    setLabelText(bottomQueueLabel_, QStringLiteral("Queue: %1").arg(visibleQueueCount));
    setLabelText(bottomVramLabel_, lastVramTelemetryText_.trimmed().isEmpty()
        ? QStringLiteral("VRAM: checking")
        : lastVramTelemetryText_);

    ImageGenerationPage *page = generationPageForMode(currentModeId_);
    const QString modelValue = page ? page->selectedModelValue() : QString();
    const QString loraValue = page ? page->selectedLoraValue() : QString();

    setLabelText(bottomModelLabel_, QStringLiteral("Model: %1").arg(
        spellvision::shell::BottomTelemetryPresenter::shortAssetName(modelValue)));
    setLabelText(bottomLoraLabel_, QStringLiteral("LoRA: %1").arg(
        spellvision::shell::BottomTelemetryPresenter::shortAssetName(loraValue)));
    setLabelText(bottomStateLabel_, busy ? pass28qQueueStateText(activeItem->state) : QStringLiteral("Idle"));

    auto stabilizeLabel = [](QLabel *label, int width) {
        if (!label)
            return;

        label->setFixedWidth(width);
        label->setMinimumHeight(24);
        label->setMaximumHeight(24);
        label->setWordWrap(false);
        label->setTextInteractionFlags(Qt::NoTextInteraction);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    };

    stabilizeLabel(bottomReadyLabel_, 64);
    stabilizeLabel(bottomPageLabel_, 150);
    stabilizeLabel(bottomRuntimeLabel_, 150);
    stabilizeLabel(bottomQueueLabel_, 104);
    stabilizeLabel(bottomVramLabel_, 170);
    stabilizeLabel(bottomModelLabel_, 210);
    stabilizeLabel(bottomLoraLabel_, 150);
    stabilizeLabel(bottomStateLabel_, 96);

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setRange(0, 100);
        bottomProgressBar_->setValue(busy ? qBound(0, activeProgress, 100) : 0);
        bottomProgressBar_->setTextVisible(true);
        bottomProgressBar_->setFormat(busy ? QStringLiteral("%p%") : QStringLiteral(""));
        bottomProgressBar_->setFixedSize(164, 18);
        bottomProgressBar_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    }
}
'''

cpp = replace_function(cpp, "void MainWindow::syncBottomTelemetry()", sync_replacement)


# ----------------------------------------------------------------------
# 6) Async NVIDIA VRAM polling through nvidia-smi.
# ----------------------------------------------------------------------

vram_functions = r'''
void MainWindow::startVramTelemetryPolling()
{
    if (vramTelemetryTimer_)
        return;

    vramTelemetryTimer_ = new QTimer(this);
    vramTelemetryTimer_->setInterval(2000);

    connect(vramTelemetryTimer_, &QTimer::timeout, this, &MainWindow::pollVramTelemetry);

    pollVramTelemetry();
    vramTelemetryTimer_->start();
}

void MainWindow::pollVramTelemetry()
{
    if (property("svVramTelemetryInFlight").toBool())
        return;

    setProperty("svVramTelemetryInFlight", true);

    auto *process = new QProcess(this);
    process->setProgram(QStringLiteral("nvidia-smi"));
    process->setArguments({
        QStringLiteral("--query-gpu=memory.used,memory.total"),
        QStringLiteral("--format=csv,noheader,nounits")
    });

    connect(process, &QProcess::errorOccurred, this, [this, process](QProcess::ProcessError) {
        if (process->property("svHandled").toBool())
            return;

        process->setProperty("svHandled", true);
        setProperty("svVramTelemetryInFlight", false);

        lastVramTelemetryText_ = QStringLiteral("VRAM: unavailable");
        syncBottomTelemetry();

        process->deleteLater();
    });

    connect(process, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, [this, process](int exitCode, QProcess::ExitStatus status) {
        if (process->property("svHandled").toBool())
            return;

        process->setProperty("svHandled", true);
        setProperty("svVramTelemetryInFlight", false);

        QString nextText = QStringLiteral("VRAM: unavailable");

        if (status == QProcess::NormalExit && exitCode == 0)
        {
            const QString output = QString::fromLocal8Bit(process->readAllStandardOutput()).trimmed();
            const QString firstLine = output.split(QRegularExpression(QStringLiteral("[\\r\\n]+")), Qt::SkipEmptyParts).value(0).trimmed();
            const QStringList parts = firstLine.split(QStringLiteral(","), Qt::SkipEmptyParts);

            if (parts.size() >= 2)
            {
                bool usedOk = false;
                bool totalOk = false;

                const double usedMb = parts.at(0).trimmed().toDouble(&usedOk);
                const double totalMb = parts.at(1).trimmed().toDouble(&totalOk);

                if (usedOk && totalOk)
                    nextText = pass28qFormatVramText(usedMb, totalMb);
            }
        }

        if (lastVramTelemetryText_ != nextText)
        {
            lastVramTelemetryText_ = nextText;
            syncBottomTelemetry();
        }

        process->deleteLater();
    });

    process->start();
}
'''

if "void MainWindow::startVramTelemetryPolling()" not in cpp:
    insert_before = "void MainWindow::syncBottomTelemetry()"
    index = cpp.find(insert_before)
    if index < 0:
        raise SystemExit("Could not find syncBottomTelemetry insertion point.")
    cpp = cpp[:index] + vram_functions + "\n\n" + cpp[index:]


# Need QRegularExpression for parsing nvidia-smi line endings.
if "#include <QRegularExpression>" not in cpp:
    cpp = cpp.replace("#include <QProcess>", "#include <QProcess>\n#include <QRegularExpression>", 1)


cpp_path.write_text(cpp, encoding="utf-8")

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 28Q: real nvidia-smi VRAM telemetry and single stable telemetry owner.")
