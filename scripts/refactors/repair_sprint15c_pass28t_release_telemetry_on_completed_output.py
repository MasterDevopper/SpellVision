from pathlib import Path

cpp_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28t_release_telemetry_on_completed_output.py")

text = cpp_path.read_text(encoding="utf-8")


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
# 1) Capture completed-row baseline when a job is submitted.
# ----------------------------------------------------------------------

old_submit = '''    setProperty("svTelemetryPhaseRank", 1);
    setProperty("svTelemetryProgressTarget", 3);
    setProperty("svTelemetryJobActive", true);

    if (bottomProgressBar_)'''

new_submit = '''    setProperty("svTelemetryPhaseRank", 1);
    setProperty("svTelemetryProgressTarget", 3);
    setProperty("svTelemetryJobActive", true);
    setProperty("svTelemetryCompletionPulse", false);

    // Pass 28T:
    // The image queue tray is a completed-jobs ledger. Capture the visible
    // completed-row count at submission so telemetry can detect the new output
    // even if the worker's active queue row disappears or goes stale.
    const int completedRowsAtSubmit =
        (queueTableView_ && queueTableView_->model()) ? queueTableView_->model()->rowCount() : 0;
    setProperty("svTelemetryCompletedRowsAtSubmit", completedRowsAtSubmit);

    if (bottomProgressBar_)'''

if "svTelemetryCompletedRowsAtSubmit" not in text:
    if old_submit not in text:
        raise SystemExit("Could not find Pass 28S submit telemetry baseline block.")
    text = text.replace(old_submit, new_submit, 1)


# ----------------------------------------------------------------------
# 2) Reset completion metadata when the existing release hooks run.
# ----------------------------------------------------------------------

text = text.replace(
    '''            setProperty("svTelemetryProgressTarget", 0);
            setProperty("svTelemetryJobActive", false);
            syncBottomTelemetry();''',
    '''            setProperty("svTelemetryProgressTarget", 0);
            setProperty("svTelemetryJobActive", false);
            setProperty("svTelemetryCompletionPulse", false);
            setProperty("svTelemetryCompletedRowsAtSubmit", 0);
            syncBottomTelemetry();'''
)


# ----------------------------------------------------------------------
# 3) Replace syncBottomTelemetry with completion pulse + release behavior.
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

    const bool explicitBusy =
        property("svTelemetryBusy").toBool() &&
        property("svTelemetryBusyMode").toString() == currentModeId_;

    const int completedRowsAtSubmit = property("svTelemetryCompletedRowsAtSubmit").toInt();

    const bool completedOutputObserved =
        explicitBusy &&
        imageWorkspace &&
        completedRowsAtSubmit >= 0 &&
        visibleQueueCount > completedRowsAtSubmit;

    // Pass 28T:
    // If a new completed image row appears after submission, completion wins
    // over any stale active row that may still say Running/89%.
    if (completedOutputObserved)
        activeItem = nullptr;

    const bool completionPulse = property("svTelemetryCompletionPulse").toBool();
    bool busy = activeItem != nullptr || explicitBusy || completionPulse;

    if (completedOutputObserved && !completionPulse)
    {
        setProperty("svTelemetryCompletionPulse", true);
        setProperty("svTelemetryBusy", false);
        setProperty("svTelemetryBusyState", QStringLiteral("Completed"));
        setProperty("svTelemetryPhaseRank", 0);
        setProperty("svTelemetryProgressTarget", 100);

        if (bottomProgressBar_)
        {
            bottomProgressBar_->setFormat(QStringLiteral("%p%"));
        }

        QTimer::singleShot(900, this, [this]() {
            setProperty("svTelemetryBusy", false);
            setProperty("svTelemetryBusyState", QStringLiteral("Idle"));
            setProperty("svTelemetryPhaseRank", 0);
            setProperty("svTelemetryProgressTarget", 0);
            setProperty("svTelemetryJobActive", false);
            setProperty("svTelemetryCompletionPulse", false);
            setProperty("svTelemetryCompletedRowsAtSubmit", 0);
            syncBottomTelemetry();
        });
    }

    const QString explicitBusyState = property("svTelemetryBusyState").toString().trimmed();

    const int observedRank = activeItem
        ? pass28sTelemetryRankFromState(activeItem->state)
        : (busy ? pass28sTelemetryRankFromText(explicitBusyState) : 0);

    int displayedRank = property("svTelemetryPhaseRank").toInt();

    if (busy && !completedOutputObserved && !completionPulse)
        displayedRank = qMax(displayedRank, observedRank);
    else if (!busy)
        displayedRank = 0;

    setProperty("svTelemetryPhaseRank", displayedRank);

    QString stateText = QStringLiteral("Idle");

    if (completedOutputObserved || completionPulse)
        stateText = QStringLiteral("Completed");
    else if (busy)
        stateText = pass28sTelemetryStateFromRank(displayedRank, explicitBusyState);

    int targetProgress = activeProgress;

    if (completedOutputObserved || completionPulse)
    {
        targetProgress = 100;
    }
    else if (busy)
    {
        targetProgress = qMax(targetProgress, pass28sMinimumProgressForRank(displayedRank));

        const int previousTarget = property("svTelemetryProgressTarget").toInt();
        targetProgress = qMax(targetProgress, previousTarget);
        targetProgress = qBound(0, targetProgress, 99);
    }
    else
    {
        targetProgress = 0;
    }

    setProperty("svTelemetryProgressTarget", targetProgress);

    auto setLabelText = [](QLabel *label, const QString &text) {
        if (!label)
            return;

        if (label->text() != text)
            label->setText(text);
    };

    setLabelText(bottomReadyLabel_, (busy || completionPulse || completedOutputObserved) ? QStringLiteral("Busy") : QStringLiteral("Ready"));
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
    setLabelText(bottomStateLabel_, stateText);

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
        bottomProgressBar_->setTextVisible(true);
        bottomProgressBar_->setFormat((busy || completionPulse || completedOutputObserved) ? QStringLiteral("%p%") : QStringLiteral(""));
        bottomProgressBar_->setFixedSize(164, 18);
        bottomProgressBar_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);

        const int currentValue = bottomProgressBar_->value();
        const int currentTarget = bottomProgressBar_->property("svProgressAnimationTarget").toInt();

        if (currentTarget != targetProgress)
        {
            if (auto *oldAnimation = bottomProgressBar_->findChild<QPropertyAnimation *>(QStringLiteral("TelemetryProgressAnimation")))
            {
                oldAnimation->stop();
                oldAnimation->deleteLater();
            }

            bottomProgressBar_->setProperty("svProgressAnimationTarget", targetProgress);

            auto *animation = new QPropertyAnimation(bottomProgressBar_, "value", bottomProgressBar_);
            animation->setObjectName(QStringLiteral("TelemetryProgressAnimation"));
            animation->setDuration((busy || completionPulse || completedOutputObserved) ? 260 : 180);
            animation->setEasingCurve(QEasingCurve::OutCubic);
            animation->setStartValue(currentValue);
            animation->setEndValue(targetProgress);
            animation->start(QAbstractAnimation::DeleteWhenStopped);
        }
    }
}
'''

text = replace_function(text, "void MainWindow::syncBottomTelemetry()", sync_replacement)

cpp_path.write_text(text, encoding="utf-8")
script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 28T: telemetry releases on completed output and pulses to 100%.")
