from pathlib import Path
import re

presenter_path = Path("qt_ui/shell/BottomTelemetryPresenter.cpp")
main_cpp_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28p_real_bottom_telemetry_state.py")

presenter = presenter_path.read_text(encoding="utf-8")
main_cpp = main_cpp_path.read_text(encoding="utf-8")


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
# 1) BottomTelemetryPresenter: make telemetry mode-aware and active-state aware.
# ----------------------------------------------------------------------

if "#include <QStringList>" not in presenter:
    presenter = presenter.replace("#include <QStatusBar>", "#include <QStatusBar>\n#include <QStringList>", 1)

if "#include <QSizePolicy>" not in presenter:
    presenter = presenter.replace("#include <QProgressBar>", "#include <QProgressBar>\n#include <QSizePolicy>", 1)

helper = r'''
QString normalizedCommand(const QString &value)
{
    return value.trimmed().toLower();
}

QStringList acceptedCommandsForMode(const QString &modeId)
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

bool itemMatchesMode(const QueueItem &item, const QString &modeId)
{
    const QStringList accepted = acceptedCommandsForMode(modeId);
    if (accepted.isEmpty())
        return true;

    return accepted.contains(normalizedCommand(item.command));
}

bool itemIsActiveWork(const QueueItem &item)
{
    if (item.isTerminal())
        return false;

    return item.running ||
           item.state == QueueItemState::Queued ||
           item.state == QueueItemState::Preparing ||
           item.state == QueueItemState::Running;
}

bool modeIsImageWorkspace(const QString &modeId)
{
    const QString mode = modeId.trimmed().toLower();
    return mode == QStringLiteral("t2i") || mode == QStringLiteral("i2i");
}

'''

if "acceptedCommandsForMode" not in presenter:
    presenter = presenter.replace("QLabel *makeLabel", helper + "\nQLabel *makeLabel", 1)


build_replacement = r'''
void BottomTelemetryPresenter::build(const BuildBindings &bindings)
{
    if (!bindings.statusBar)
        return;

    auto *bar = bindings.statusBar;
    bar->setSizeGripEnabled(false);
    bar->setFixedHeight(34);
    bar->setMinimumHeight(34);
    bar->setMaximumHeight(34);

    auto *readyLabel = makeLabel(QStringLiteral("Ready"), bindings.owner);
    auto *pageLabel = makeLabel(QStringLiteral("Home"), bindings.owner);
    auto *runtimeLabel = makeLabel(QStringLiteral("Runtime: local"), bindings.owner);
    auto *queueLabel = makeLabel(QStringLiteral("Queue: 0"), bindings.owner);
    auto *vramLabel = makeLabel(QStringLiteral("VRAM: idle"), bindings.owner);
    auto *modelLabel = makeLabel(QStringLiteral("Model: none"), bindings.owner);
    auto *loraLabel = makeLabel(QStringLiteral("LoRA: none"), bindings.owner);
    auto *stateLabel = makeLabel(QStringLiteral("Idle"), bindings.owner);

    auto stabilizeLabel = [](QLabel *label, int width) {
        if (!label)
            return;

        label->setFixedWidth(width);
        label->setMinimumHeight(22);
        label->setMaximumHeight(22);
        label->setWordWrap(false);
        label->setTextInteractionFlags(Qt::NoTextInteraction);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    };

    stabilizeLabel(readyLabel, 64);
    stabilizeLabel(pageLabel, 150);
    stabilizeLabel(runtimeLabel, 150);
    stabilizeLabel(queueLabel, 104);
    stabilizeLabel(vramLabel, 118);
    stabilizeLabel(modelLabel, 210);
    stabilizeLabel(loraLabel, 150);
    stabilizeLabel(stateLabel, 96);

    auto *progressBar = new QProgressBar(bindings.owner);
    progressBar->setObjectName(QStringLiteral("BottomProgressBar"));
    progressBar->setRange(0, 100);
    progressBar->setValue(0);
    progressBar->setTextVisible(true);
    progressBar->setFormat(QStringLiteral("%p%"));
    progressBar->setFixedSize(154, 16);
    progressBar->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    progressBar->setStyleSheet(QStringLiteral(
        "QProgressBar#BottomProgressBar {"
        " border: 1px solid rgba(90,150,220,115);"
        " border-radius: 7px;"
        " background: rgba(6,12,24,190);"
        " color: rgba(220,235,255,230);"
        " font-size: 9px;"
        " text-align: center;"
        "}"
        "QProgressBar#BottomProgressBar::chunk {"
        " border-radius: 6px;"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        " stop:0 rgba(67,137,220,230),"
        " stop:1 rgba(142,92,210,230));"
        "}"
    ));

    assignLabel(bindings.readyLabel, readyLabel);
    assignLabel(bindings.pageLabel, pageLabel);
    assignLabel(bindings.runtimeLabel, runtimeLabel);
    assignLabel(bindings.queueLabel, queueLabel);
    assignLabel(bindings.vramLabel, vramLabel);
    assignLabel(bindings.modelLabel, modelLabel);
    assignLabel(bindings.loraLabel, loraLabel);
    assignLabel(bindings.stateLabel, stateLabel);
    assignProgress(bindings.progressBar, progressBar);

    bar->addWidget(readyLabel);
    bar->addWidget(pageLabel);
    bar->addPermanentWidget(runtimeLabel);
    bar->addPermanentWidget(queueLabel);
    bar->addPermanentWidget(vramLabel);
    bar->addPermanentWidget(modelLabel);
    bar->addPermanentWidget(loraLabel);
    bar->addPermanentWidget(stateLabel);
    bar->addPermanentWidget(progressBar);
}
'''

presenter = replace_function(presenter, "void BottomTelemetryPresenter::build(const BuildBindings &bindings)", build_replacement)


sync_replacement = r'''
void BottomTelemetryPresenter::sync(const SyncBindings &bindings)
{
    const bool imageWorkspace = modeIsImageWorkspace(bindings.currentModeId);

    int visibleQueueCount = 0;
    const QueueItem *activeItem = nullptr;

    if (bindings.queueManager)
    {
        const QString activeQueueId = bindings.queueManager->activeQueueItemId();

        if (!activeQueueId.trimmed().isEmpty() && bindings.queueManager->contains(activeQueueId))
        {
            const QueueItem item = bindings.queueManager->itemById(activeQueueId);
            if (itemMatchesMode(item, bindings.currentModeId) && itemIsActiveWork(item))
            {
                const QVector<QueueItem> &items = bindings.queueManager->items();
                for (const QueueItem &candidate : items)
                {
                    if (candidate.id == item.id)
                    {
                        activeItem = &candidate;
                        break;
                    }
                }
            }
        }

        const QVector<QueueItem> &items = bindings.queueManager->items();
        for (const QueueItem &item : items)
        {
            if (!itemMatchesMode(item, bindings.currentModeId))
                continue;

            if (itemIsActiveWork(item))
            {
                activeItem = &item;
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

    const bool busy = activeItem != nullptr;
    const QString stateText = busy ? queueStateDisplay(activeItem->state) : QStringLiteral("Idle");

    int progressPercent = 0;
    if (busy)
    {
        progressPercent = activeItem->progressPercent();

        if (progressPercent <= 0 && activeItem->state == QueueItemState::Preparing)
            progressPercent = 5;

        if (progressPercent <= 0 && activeItem->state == QueueItemState::Running)
            progressPercent = 8;
    }

    if (bindings.readyLabel)
        bindings.readyLabel->setText(busy ? QStringLiteral("Busy") : QStringLiteral("Ready"));

    if (bindings.pageLabel)
    {
        const QString pageText = !bindings.pageContextText.trimmed().isEmpty()
                                     ? bindings.pageContextText.trimmed()
                                     : bindings.currentModeId.trimmed().toUpper();
        bindings.pageLabel->setText(pageText.isEmpty() ? QStringLiteral("Home") : pageText);
    }

    if (bindings.runtimeLabel)
        bindings.runtimeLabel->setText(QStringLiteral("Runtime: local"));

    if (bindings.queueLabel)
        bindings.queueLabel->setText(QStringLiteral("Queue: %1").arg(visibleQueueCount));

    // Pass 28P:
    // Until real GPU memory telemetry is wired from the worker, do not leave this
    // as the misleading permanent "n/a" placeholder. Show GPU activity state.
    if (bindings.vramLabel)
        bindings.vramLabel->setText(busy ? QStringLiteral("VRAM: active") : QStringLiteral("VRAM: idle"));

    const QString modelValue = bindings.currentGenerationPage ? bindings.currentGenerationPage->selectedModelValue() : QString();
    const QString loraValue = bindings.currentGenerationPage ? bindings.currentGenerationPage->selectedLoraValue() : QString();

    if (bindings.modelLabel)
        bindings.modelLabel->setText(QStringLiteral("Model: %1").arg(shortAssetName(modelValue)));

    if (bindings.loraLabel)
        bindings.loraLabel->setText(QStringLiteral("LoRA: %1").arg(shortAssetName(loraValue)));

    if (bindings.stateLabel)
        bindings.stateLabel->setText(busy ? stateText : QStringLiteral("Idle"));

    if (bindings.progressBar)
    {
        bindings.progressBar->setRange(0, 100);
        bindings.progressBar->setValue(progressPercent);
        bindings.progressBar->setTextVisible(true);
        bindings.progressBar->setFormat(busy ? QStringLiteral("%p%") : QStringLiteral(""));
    }
}
'''

presenter = replace_function(presenter, "void BottomTelemetryPresenter::sync(const SyncBindings &bindings)", sync_replacement)

presenter_path.write_text(presenter, encoding="utf-8")


# ----------------------------------------------------------------------
# 2) MainWindow local overrides: stop re-shrinking progress to an 8px line,
#    and stop forcing VRAM back toward n/a.
# ----------------------------------------------------------------------

main_cpp = main_cpp.replace("stabilizeLabel(bottomVramLabel_, 90);", "stabilizeLabel(bottomVramLabel_, 118);")
main_cpp = main_cpp.replace("stabilizeLabel(bottomStateLabel_, 84);", "stabilizeLabel(bottomStateLabel_, 96);")
main_cpp = main_cpp.replace("bottomProgressBar_->setFixedWidth(120);", "bottomProgressBar_->setFixedWidth(154);")
main_cpp = main_cpp.replace("bottomProgressBar_->setFixedHeight(8);", "bottomProgressBar_->setFixedHeight(16);")
main_cpp = main_cpp.replace("bottomProgressBar_->setFixedWidth(150);", "bottomProgressBar_->setFixedWidth(154);")
main_cpp = main_cpp.replace("statusBar()->setFixedHeight(30);", "statusBar()->setFixedHeight(34);")
main_cpp = main_cpp.replace("statusBar()->setMinimumHeight(30);", "statusBar()->setMinimumHeight(34);")
main_cpp = main_cpp.replace("statusBar()->setMaximumHeight(30);", "statusBar()->setMaximumHeight(34);")

if "Pass 28P progress polish" not in main_cpp:
    marker = '''    if (bottomProgressBar_)
    {'''
    replacement = '''    if (bottomProgressBar_)
    {
        // Pass 28P progress polish:
        // The bottom progress indicator should read as a compact progress pill,
        // not a primitive 8px line.
        bottomProgressBar_->setTextVisible(true);
        bottomProgressBar_->setFormat(QStringLiteral("%p%"));
        bottomProgressBar_->setStyleSheet(QStringLiteral(
            "QProgressBar#BottomProgressBar {"
            " border: 1px solid rgba(90,150,220,115);"
            " border-radius: 7px;"
            " background: rgba(6,12,24,190);"
            " color: rgba(220,235,255,230);"
            " font-size: 9px;"
            " text-align: center;"
            "}"
            "QProgressBar#BottomProgressBar::chunk {"
            " border-radius: 6px;"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            " stop:0 rgba(67,137,220,230),"
            " stop:1 rgba(142,92,210,230));"
            "}"
        ));'''
    main_cpp = main_cpp.replace(marker, replacement, 1)

# Remove the fallback that reintroduces "VRAM: n/a" when text is empty.
main_cpp = main_cpp.replace(
    '''    if (bottomVramLabel_ && bottomVramLabel_->text().trimmed().isEmpty())
        bottomVramLabel_->setText(QStringLiteral("VRAM: n/a"));

''',
    ""
)

main_cpp_path.write_text(main_cpp, encoding="utf-8")

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 28P: real busy state, non-N/A VRAM activity label, polished progress pill.")
