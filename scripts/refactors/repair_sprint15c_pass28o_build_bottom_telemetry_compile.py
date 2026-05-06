from pathlib import Path

path = Path("qt_ui/MainWindow.cpp")
text = path.read_text(encoding="utf-8")

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


if "#include <QLabel>" not in text:
    text = text.replace("#include <QKeySequence>", "#include <QKeySequence>\n#include <QLabel>", 1)

if "#include <QSizePolicy>" not in text:
    text = text.replace("#include <QShortcut>", "#include <QShortcut>\n#include <QSizePolicy>", 1)

replacement = r'''
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

    // Pass 28O repair:
    // Keep bottom telemetry cells fixed so frequent queue/status text updates
    // cannot resize the status bar or push neighboring cells.
    if (statusBar())
    {
        statusBar()->setSizeGripEnabled(false);
        statusBar()->setFixedHeight(30);
        statusBar()->setMinimumHeight(30);
        statusBar()->setMaximumHeight(30);
    }

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

    stabilizeLabel(bottomReadyLabel_, 64);
    stabilizeLabel(bottomPageLabel_, 150);
    stabilizeLabel(bottomRuntimeLabel_, 150);
    stabilizeLabel(bottomQueueLabel_, 104);
    stabilizeLabel(bottomVramLabel_, 90);
    stabilizeLabel(bottomModelLabel_, 210);
    stabilizeLabel(bottomLoraLabel_, 150);
    stabilizeLabel(bottomStateLabel_, 84);

    if (bottomProgressBar_)
    {
        bottomProgressBar_->setFixedWidth(120);
        bottomProgressBar_->setFixedHeight(8);
        bottomProgressBar_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    }
}
'''

text = replace_function(text, "void MainWindow::buildBottomTelemetryBar()", replacement)
path.write_text(text, encoding="utf-8")

print("Repaired corrupted Pass 28O buildBottomTelemetryBar().")
