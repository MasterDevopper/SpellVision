from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
MAIN_CPP = ROOT / "qt_ui" / "MainWindow.cpp"
MAIN_H = ROOT / "qt_ui" / "MainWindow.h"


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing expected file: {path}")
    return path.read_text(encoding="utf-8")


def write_if_changed(path: Path, text: str) -> bool:
    old = read(path)
    if old == text:
        return False
    path.write_text(text, encoding="utf-8", newline="")
    return True


def find_function_body(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"Could not find function signature: {signature}")

    brace_open = text.find("{", start)
    if brace_open < 0:
        raise RuntimeError(f"Could not find opening brace for: {signature}")

    depth = 0
    in_string = False
    in_char = False
    escaped = False
    in_line_comment = False
    in_block_comment = False

    for i in range(brace_open, len(text)):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
            continue

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if in_char:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_char = False
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "'":
            in_char = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1

    raise RuntimeError(f"Could not find closing brace for: {signature}")


def replace_function(text: str, signature: str, replacement: str) -> str:
    start, end = find_function_body(text, signature)
    return text[:start] + replacement.rstrip() + "\n" + text[end:]


def patch_main_h(text: str) -> str:
    if "class WorkerQueueController" not in text:
        marker = "class WorkflowLibraryPage;\n"
        replacement = marker + "\nnamespace spellvision::workers\n{\nclass WorkerQueueController;\n}\n"
        if marker not in text:
            raise RuntimeError("Could not find WorkflowLibraryPage forward declaration anchor in MainWindow.h")
        text = text.replace(marker, replacement, 1)

    old_member = "    QTimer *workerQueuePollTimer_ = nullptr;"
    new_member = "    spellvision::workers::WorkerQueueController *workerQueueController_ = nullptr;"
    if old_member in text:
        text = text.replace(old_member, new_member, 1)
    elif new_member not in text:
        raise RuntimeError("Could not find workerQueuePollTimer_ member or existing workerQueueController_ member in MainWindow.h")

    return text


def patch_main_cpp(text: str) -> str:
    if '#include "workers/WorkerQueueController.h"' not in text:
        anchor = '#include "workers/WorkerProcessController.h"\n'
        if anchor in text:
            text = text.replace(anchor, anchor + '#include "workers/WorkerQueueController.h"\n', 1)
        else:
            fallback = '#include "WorkflowLibraryPage.h"\n'
            if fallback not in text:
                raise RuntimeError("Could not find include anchor in MainWindow.cpp")
            text = text.replace(fallback, fallback + '#include "workers/WorkerQueueController.h"\n', 1)

    old_timer_block = '''    workerQueuePollTimer_ = new QTimer(this);
    workerQueuePollTimer_->setInterval(1800);
    connect(workerQueuePollTimer_, &QTimer::timeout, this, &MainWindow::pollWorkerQueueStatus);
    workerQueuePollTimer_->start();'''

    new_controller_block = '''    workerQueueController_ = new spellvision::workers::WorkerQueueController(this);
    spellvision::workers::WorkerQueueController::Bindings queueBindings;
    queueBindings.queueManager = queueManager_;
    queueBindings.sendRequest = [this](const QJsonObject &request, QString *stderrText, bool *startedOk) {
        return sendWorkerRequest(request, stderrText, startedOk);
    };
    queueBindings.appendLogLine = [this](const QString &text) {
        appendLogLine(text);
    };
    queueBindings.afterQueueSnapshotApplied = [this]() {
        syncGenerationPreviewsFromQueue();
        syncBottomTelemetry();
    };
    workerQueueController_->bind(queueBindings);
    workerQueueController_->startPolling(1800);'''

    if old_timer_block in text:
        text = text.replace(old_timer_block, new_controller_block, 1)
    elif "workerQueueController_ = new spellvision::workers::WorkerQueueController(this);" not in text:
        raise RuntimeError("Could not find old workerQueuePollTimer_ constructor block in MainWindow.cpp")

    poll_sig = "void MainWindow::pollWorkerQueueStatus()"
    poll_replacement = '''void MainWindow::pollWorkerQueueStatus()
{
    if (workerQueueController_)
        workerQueueController_->pollOnce();
}'''
    text = replace_function(text, poll_sig, poll_replacement)

    apply_sig = "void MainWindow::applyWorkerQueueResponse(const QJsonObject &response)"
    apply_replacement = '''void MainWindow::applyWorkerQueueResponse(const QJsonObject &response)
{
    if (workerQueueController_)
        workerQueueController_->applyWorkerQueueResponse(response);
}'''
    text = replace_function(text, apply_sig, apply_replacement)

    return text


def main() -> None:
    main_h = read(MAIN_H)
    main_cpp = read(MAIN_CPP)

    patched_h = patch_main_h(main_h)
    patched_cpp = patch_main_cpp(main_cpp)

    changed_h = write_if_changed(MAIN_H, patched_h)
    changed_cpp = write_if_changed(MAIN_CPP, patched_cpp)

    print("Sprint 14C Pass 6 worker queue controller wiring complete.")
    print(f"MainWindow.h changed: {changed_h}")
    print(f"MainWindow.cpp changed: {changed_cpp}")


if __name__ == "__main__":
    main()
