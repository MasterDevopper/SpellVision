from pathlib import Path

cpp_path = Path("qt_ui/MainWindow.cpp")
script_path = Path("scripts/refactors/repair_sprint15c_pass28r_single_container_telemetry_bar.py")

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


for include in [
    "#include <QFrame>",
    "#include <QHBoxLayout>",
    "#include <QStatusBar>",
    "#include <QSizePolicy>",
]:
    if include not in text:
        anchor = "#include <QGridLayout>"
        if anchor in text:
            text = text.replace(anchor, include + "\n" + anchor, 1)
        else:
            text = include + "\n" + text


build_replacement = r'''
void MainWindow::buildBottomTelemetryBar()
{
    // Pass 28R:
    // QStatusBar shifts normal widgets and permanent widgets independently.
    // Use one fixed telemetry container so label updates cannot make the bar
    // jump left/right while generation and VRAM polling are active.
    QStatusBar *bar = statusBar();
    if (!bar)
        return;

    bar->clearMessage();
    bar->setSizeGripEnabled(false);
    bar->setFixedHeight(38);
    bar->setMinimumHeight(38);
    bar->setMaximumHeight(38);

    auto *container = new QFrame(bar);
    container->setObjectName(QStringLiteral("BottomTelemetryContainer"));
    container->setFrameShape(QFrame::NoFrame);
    container->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    container->setMinimumHeight(30);
    container->setMaximumHeight(30);

    auto *layout = new QHBoxLayout(container);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);

    auto makeTelemetryLabel = [container](const QString &objectName,
                                          const QString &text,
                                          int width,
                                          Qt::Alignment alignment = Qt::AlignCenter) {
        auto *label = new QLabel(text, container);
        label->setObjectName(objectName);
        label->setFixedWidth(width);
        label->setMinimumHeight(24);
        label->setMaximumHeight(24);
        label->setAlignment(alignment);
        label->setWordWrap(false);
        label->setTextInteractionFlags(Qt::NoTextInteraction);
        label->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
        return label;
    };

    auto addSeparator = [container, layout]() {
        auto *separator = new QFrame(container);
        separator->setObjectName(QStringLiteral("BottomTelemetrySeparator"));
        separator->setFrameShape(QFrame::VLine);
        separator->setFixedWidth(1);
        separator->setMinimumHeight(22);
        separator->setMaximumHeight(22);
        separator->setStyleSheet(QStringLiteral(
            "QFrame#BottomTelemetrySeparator {"
            " background: rgba(135,165,220,115);"
            " border: none;"
            "}"
        ));
        layout->addWidget(separator);
    };

    bottomReadyLabel_ = makeTelemetryLabel(QStringLiteral("BottomReadyLabel"), QStringLiteral("Ready"), 64);
    bottomPageLabel_ = makeTelemetryLabel(QStringLiteral("BottomPageLabel"), QStringLiteral("Home"), 150, Qt::AlignLeft | Qt::AlignVCenter);
    bottomRuntimeLabel_ = makeTelemetryLabel(QStringLiteral("BottomRuntimeLabel"), QStringLiteral("Runtime: local"), 150);
    bottomQueueLabel_ = makeTelemetryLabel(QStringLiteral("BottomQueueLabel"), QStringLiteral("Queue: 0"), 104);
    bottomVramLabel_ = makeTelemetryLabel(QStringLiteral("BottomVramLabel"), QStringLiteral("VRAM: checking"), 170);
    bottomModelLabel_ = makeTelemetryLabel(QStringLiteral("BottomModelLabel"), QStringLiteral("Model: none"), 210);
    bottomLoraLabel_ = makeTelemetryLabel(QStringLiteral("BottomLoraLabel"), QStringLiteral("LoRA: none"), 150);
    bottomStateLabel_ = makeTelemetryLabel(QStringLiteral("BottomStateLabel"), QStringLiteral("Idle"), 96);

    bottomProgressBar_ = new QProgressBar(container);
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

    layout->addWidget(bottomReadyLabel_);
    addSeparator();
    layout->addWidget(bottomPageLabel_);
    layout->addStretch(1);
    layout->addWidget(bottomRuntimeLabel_);
    addSeparator();
    layout->addWidget(bottomQueueLabel_);
    addSeparator();
    layout->addWidget(bottomVramLabel_);
    addSeparator();
    layout->addWidget(bottomModelLabel_);
    addSeparator();
    layout->addWidget(bottomLoraLabel_);
    addSeparator();
    layout->addWidget(bottomStateLabel_);
    addSeparator();
    layout->addWidget(bottomProgressBar_);

    bar->addWidget(container, 1);

    startVramTelemetryPolling();
    syncBottomTelemetry();
}
'''

text = replace_function(text, "void MainWindow::buildBottomTelemetryBar()", build_replacement)


# Explicit busy latch: queue polling can be late/missing active ids, so latch Busy
# when generation is submitted and release it on terminal preview recovery.
submit_marker = '''    page->setBusy(true, enqueueOnly ? QStringLiteral("Queueing request…") : QStringLiteral("Submitting generation…"));'''
submit_replacement = '''    // Pass 28R explicit busy latch:
    // Telemetry should say Busy immediately after user submission, even before
    // queue polling publishes an active row.
    setProperty("svTelemetryBusy", true);
    setProperty("svTelemetryBusyMode", modeId);
    setProperty("svTelemetryBusyState", enqueueOnly ? QStringLiteral("Queued") : QStringLiteral("Submitting"));
    syncBottomTelemetry();

    page->setBusy(true, enqueueOnly ? QStringLiteral("Queueing request…") : QStringLiteral("Submitting generation…"));'''

if "Pass 28R explicit busy latch" not in text:
    if submit_marker not in text:
        raise SystemExit("Could not find submitGenerationRequest busy marker.")
    text = text.replace(submit_marker, submit_replacement, 1)


# Release the busy latch whenever MainWindow marks the generation page ready.
if "Pass 28R release telemetry busy latch" not in text:
    text = text.replace(
        '''            page->setBusy(false, QStringLiteral("Ready"));''',
        '''            // Pass 28R release telemetry busy latch.
            setProperty("svTelemetryBusy", false);
            setProperty("svTelemetryBusyState", QStringLiteral("Idle"));
            syncBottomTelemetry();
            page->setBusy(false, QStringLiteral("Ready"));''',
        1,
    )

    text = text.replace(
        '''            page->setBusy(false, message);''',
        '''            // Pass 28R release telemetry busy latch.
            setProperty("svTelemetryBusy", false);
            setProperty("svTelemetryBusyState", QStringLiteral("Idle"));
            syncBottomTelemetry();
            page->setBusy(false, message);''',
        1,
    )


# Patch syncBottomTelemetry to respect the explicit busy latch if queue active item
# is not visible yet.
old_busy = '''    const bool busy = activeItem != nullptr;'''
new_busy = '''    const bool explicitBusy =
        property("svTelemetryBusy").toBool() &&
        property("svTelemetryBusyMode").toString() == currentModeId_;

    const bool busy = activeItem != nullptr || explicitBusy;'''

if old_busy in text and "const bool explicitBusy =" not in text:
    text = text.replace(old_busy, new_busy, 1)

old_state = '''    setLabelText(bottomStateLabel_, busy ? pass28qQueueStateText(activeItem->state) : QStringLiteral("Idle"));'''
new_state = '''    const QString explicitBusyState = property("svTelemetryBusyState").toString().trimmed();
    setLabelText(bottomStateLabel_, activeItem
        ? pass28qQueueStateText(activeItem->state)
        : (busy && !explicitBusyState.isEmpty() ? explicitBusyState : QStringLiteral("Idle")));'''

if old_state in text:
    text = text.replace(old_state, new_state, 1)

old_progress = '''        bottomProgressBar_->setValue(busy ? qBound(0, activeProgress, 100) : 0);'''
new_progress = '''        int displayProgress = activeProgress;
        if (busy && displayProgress <= 0)
            displayProgress = 3;

        bottomProgressBar_->setValue(busy ? qBound(0, displayProgress, 100) : 0);'''

if old_progress in text:
    text = text.replace(old_progress, new_progress, 1)


cpp_path.write_text(text, encoding="utf-8")
script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 28R: single-container telemetry bar and explicit Busy latch.")
