from pathlib import Path

cpp_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28s_monotonic_state_smooth_progress.py")

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
# 1) Include animation support.
# ----------------------------------------------------------------------

if "#include <QPropertyAnimation>" not in text:
    text = text.replace("#include <QProcess>", "#include <QProcess>\n#include <QPropertyAnimation>", 1)

if "#include <QEasingCurve>" not in text:
    text = text.replace("#include <QDateTime>", "#include <QDateTime>\n#include <QEasingCurve>", 1)


# ----------------------------------------------------------------------
# 2) Add monotonic state/progress helpers.
# ----------------------------------------------------------------------

helpers = r'''
int pass28sTelemetryRankFromState(QueueItemState state)
{
    switch (state)
    {
    case QueueItemState::Queued:
        return 1;
    case QueueItemState::Preparing:
        return 2;
    case QueueItemState::Running:
        return 3;
    case QueueItemState::Completed:
    case QueueItemState::Failed:
    case QueueItemState::Cancelled:
    case QueueItemState::Skipped:
    case QueueItemState::Unknown:
    default:
        return 0;
    }
}

int pass28sTelemetryRankFromText(const QString &stateText)
{
    const QString state = stateText.trimmed().toLower();

    if (state == QStringLiteral("running"))
        return 3;

    if (state == QStringLiteral("preparing"))
        return 2;

    if (state == QStringLiteral("queued") ||
        state == QStringLiteral("queueing") ||
        state == QStringLiteral("submitting"))
        return 1;

    return 0;
}

QString pass28sTelemetryStateFromRank(int rank, const QString &fallback = QString())
{
    if (rank >= 3)
        return QStringLiteral("Running");

    if (rank == 2)
        return QStringLiteral("Preparing");

    if (rank == 1)
    {
        const QString normalized = fallback.trimmed();
        return normalized.isEmpty() ? QStringLiteral("Submitting") : normalized;
    }

    return QStringLiteral("Idle");
}

int pass28sMinimumProgressForRank(int rank)
{
    if (rank >= 3)
        return 12;

    if (rank == 2)
        return 7;

    if (rank == 1)
        return 3;

    return 0;
}

'''

if "pass28sTelemetryRankFromState" not in text:
    marker = "QString pass28qQueueStateText(QueueItemState state)"
    index = text.find(marker)
    if index < 0:
        raise SystemExit("Could not find pass28qQueueStateText helper insertion point.")
    text = text[:index] + helpers + "\n" + text[index:]


# ----------------------------------------------------------------------
# 3) Strengthen explicit busy latch at submission.
# ----------------------------------------------------------------------

old_submit = '''    setProperty("svTelemetryBusy", true);
    setProperty("svTelemetryBusyMode", modeId);
    setProperty("svTelemetryBusyState", enqueueOnly ? QStringLiteral("Queued") : QStringLiteral("Submitting"));
    syncBottomTelemetry();'''

new_submit = '''    setProperty("svTelemetryBusy", true);
    setProperty("svTelemetryBusyMode", modeId);
    setProperty("svTelemetryBusyState", enqueueOnly ? QStringLiteral("Queued") : QStringLiteral("Submitting"));

    // Pass 28S:
    // Start every new job from a clean telemetry state. From here, state can
    // advance Submitting -> Preparing -> Running, but it must not regress if a
    // queue snapshot temporarily omits the active row.
    setProperty("svTelemetryPhaseRank", 1);
    setProperty("svTelemetryProgressTarget", 3);
    setProperty("svTelemetryJobActive", true);

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setValue(0);
        bottomProgressBar_->setFormat(QStringLiteral("%p%"));
    }

    syncBottomTelemetry();'''

if "Pass 28S:" not in text[text.find("Pass 28R explicit busy latch"):text.find("page->setBusy(true", text.find("Pass 28R explicit busy latch"))]:
    if old_submit not in text:
        raise SystemExit("Could not find explicit busy latch submit block.")
    text = text.replace(old_submit, new_submit, 1)


# ----------------------------------------------------------------------
# 4) Reset monotonic state when generation is truly finished.
# ----------------------------------------------------------------------

if "svTelemetryPhaseRank" in text:
    text = text.replace(
        '''            setProperty("svTelemetryBusy", false);
            setProperty("svTelemetryBusyState", QStringLiteral("Idle"));
            syncBottomTelemetry();''',
        '''            setProperty("svTelemetryBusy", false);
            setProperty("svTelemetryBusyState", QStringLiteral("Idle"));
            setProperty("svTelemetryPhaseRank", 0);
            setProperty("svTelemetryProgressTarget", 0);
            setProperty("svTelemetryJobActive", false);
            syncBottomTelemetry();'''
    )


# ----------------------------------------------------------------------
# 5) Replace syncBottomTelemetry with monotonic state and animated progress.
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

    const bool busy = activeItem != nullptr || explicitBusy;

    const QString explicitBusyState = property("svTelemetryBusyState").toString().trimmed();

    const int observedRank = activeItem
        ? pass28sTelemetryRankFromState(activeItem->state)
        : (busy ? pass28sTelemetryRankFromText(explicitBusyState) : 0);

    int displayedRank = property("svTelemetryPhaseRank").toInt();

    if (busy)
        displayedRank = qMax(displayedRank, observedRank);
    else
        displayedRank = 0;

    setProperty("svTelemetryPhaseRank", displayedRank);

    const QString stateText = busy
        ? pass28sTelemetryStateFromRank(displayedRank, explicitBusyState)
        : QStringLiteral("Idle");

    int targetProgress = activeProgress;

    if (busy)
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
        bottomProgressBar_->setFormat(busy ? QStringLiteral("%p%") : QStringLiteral(""));
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
            animation->setDuration(busy ? 260 : 180);
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

print("Applied Pass 28S: telemetry state is monotonic and progress animates toward real queue progress.")
