from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
MAIN_CPP = ROOT / "qt_ui" / "MainWindow.cpp"

INCLUDE_WORKER = '#include "workers/WorkerProcessController.h"'
INCLUDE_EVENT_LOOP = '#include <QEventLoop>'

NEW_FUNCTION = r'''QJsonObject MainWindow::sendWorkerRequest(const QJsonObject &request, QString *stderrText, bool *startedOk) const
{
    if (stderrText)
        stderrText->clear();
    if (startedOk)
        *startedOk = false;

    const QString projectRoot = resolveProjectRoot();
    const QString pythonExecutable = resolvePythonExecutable();
    const QString workerClient = QDir(projectRoot).filePath(QStringLiteral("python/worker_client.py"));

    spellvision::workers::WorkerProcessController controller;
    spellvision::workers::WorkerProcessController::CommandRequest command;
    command.program = pythonExecutable;
    command.arguments = {workerClient};
    command.workingDirectory = projectRoot;
    command.environment = QProcessEnvironment::systemEnvironment();
    command.payload = request;
    command.closeWriteChannelAfterPayload = true;

    QJsonObject lastJsonMessage;
    QStringList stderrLines;
    QStringList processErrors;
    bool finished = false;
    bool timedOut = false;
    int exitCode = -1;
    QProcess::ExitStatus exitStatus = QProcess::NormalExit;

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    connect(&controller, &spellvision::workers::WorkerProcessController::stderrLineReceived,
            &loop, [&stderrLines](const QString &line) {
                if (!line.trimmed().isEmpty())
                    stderrLines << line.trimmed();
            });

    connect(&controller, &spellvision::workers::WorkerProcessController::jsonMessageReceived,
            &loop, [&lastJsonMessage](const QJsonObject &message) {
                if (!message.isEmpty())
                    lastJsonMessage = message;
            });

    connect(&controller, &spellvision::workers::WorkerProcessController::processError,
            &loop, [&processErrors](const QString &message) {
                if (!message.trimmed().isEmpty())
                    processErrors << message.trimmed();
            });

    connect(&controller,
            &spellvision::workers::WorkerProcessController::processFinished,
            &loop,
            [&loop, &finished, &exitCode, &exitStatus](int code, QProcess::ExitStatus status) {
                finished = true;
                exitCode = code;
                exitStatus = status;
                loop.quit();
            });

    connect(&timeoutTimer, &QTimer::timeout, &loop, [&controller, &loop, &timedOut, &processErrors]() {
        timedOut = true;
        processErrors << QStringLiteral("Worker process timed out while waiting for a response.");
        controller.kill();
        loop.quit();
    });

    const bool started = controller.start(command);
    if (startedOk)
        *startedOk = started;

    if (!started)
    {
        if (stderrText)
            *stderrText = processErrors.join(QChar('\n'));
        return {};
    }

    if (controller.isRunning())
    {
        timeoutTimer.start(120000);
        loop.exec();
        timeoutTimer.stop();
    }

    if (stderrText)
    {
        QStringList diagnostics = stderrLines;
        diagnostics.append(processErrors);
        diagnostics.removeAll(QString());
        *stderrText = diagnostics.join(QChar('\n'));
    }

    if (timedOut)
        return lastJsonMessage;

    if (finished && exitStatus != QProcess::NormalExit)
        return lastJsonMessage;

    if (finished && exitCode != 0 && lastJsonMessage.isEmpty())
        return {};

    return lastJsonMessage;
}
'''


def add_include_once(text: str, include_line: str, after_candidates: list[str]) -> str:
    if include_line in text:
        return text
    for candidate in after_candidates:
        if candidate in text:
            return text.replace(candidate, candidate + "\n" + include_line, 1)
    # Fallback: place before first Qt include if no preferred anchor exists.
    marker = "#include <"
    idx = text.find(marker)
    if idx >= 0:
        return text[:idx] + include_line + "\n" + text[idx:]
    return include_line + "\n" + text


def find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    i = open_index
    in_line_comment = False
    in_block_comment = False
    in_string = False
    in_char = False
    escaped = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if in_char:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_char = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue

        if ch == "'":
            in_char = True
            i += 1
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i

        i += 1

    raise RuntimeError("Could not find matching closing brace for sendWorkerRequest().")


def replace_send_worker_request(text: str) -> str:
    marker = "QJsonObject MainWindow::sendWorkerRequest"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError("Could not find MainWindow::sendWorkerRequest().")

    open_brace = text.find("{", start)
    if open_brace < 0:
        raise RuntimeError("Could not find opening brace for MainWindow::sendWorkerRequest().")

    close_brace = find_matching_brace(text, open_brace)
    end = close_brace + 1

    # Preserve spacing between functions.
    if end < len(text) and text[end:end + 2] == "\r\n":
        end += 2
    elif end < len(text) and text[end:end + 1] == "\n":
        end += 1

    return text[:start] + NEW_FUNCTION + "\n" + text[end:]


def main() -> None:
    if not MAIN_CPP.exists():
        raise SystemExit(f"Missing file: {MAIN_CPP}")

    text = MAIN_CPP.read_text(encoding="utf-8")
    text = add_include_once(
        text,
        INCLUDE_WORKER,
        [
            '#include "WorkflowLibraryPage.h"',
            '#include "WorkerResponseParser.h"',
        ],
    )
    text = add_include_once(
        text,
        INCLUDE_EVENT_LOOP,
        [
            '#include <QDir>',
            '#include <QCoreApplication>',
        ],
    )
    text = replace_send_worker_request(text)
    MAIN_CPP.write_text(text, encoding="utf-8", newline="")
    print("Applied Sprint 14C Pass 4 WorkerProcessController wiring to qt_ui/MainWindow.cpp")


if __name__ == "__main__":
    main()
