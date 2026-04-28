from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_CPP = ROOT / "qt_ui" / "MainWindow.cpp"
MAIN_H = ROOT / "qt_ui" / "MainWindow.h"
CMAKE = ROOT / "CMakeLists.txt"


def replace_function_body(text: str, signature: str, new_body: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"Could not find function signature: {signature}")

    open_brace = text.find("{", start)
    if open_brace < 0:
        raise RuntimeError(f"Could not find opening brace for: {signature}")

    depth = 0
    for index in range(open_brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[:start] + new_body.rstrip() + "\n" + text[index + 1:]

    raise RuntimeError(f"Could not find closing brace for: {signature}")


def ensure_include(text: str, include_line: str, after: str) -> str:
    if include_line in text:
        return text
    if after not in text:
        raise RuntimeError(f"Could not find include anchor: {after}")
    return text.replace(after, after + "\n" + include_line, 1)


def patch_cmake(text: str) -> str:
    if "qt_ui/shell/BottomTelemetryPresenter.cpp" in text:
        return text

    insert = "    qt_ui/shell/BottomTelemetryPresenter.cpp\n    qt_ui/shell/BottomTelemetryPresenter.h"
    anchors = [
        "    qt_ui/shell/QueueUiPresenter.h",
        "    qt_ui/shell/MainWindowTrayController.h",
    ]
    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "\n" + insert, 1)

    raise RuntimeError("Could not find CMake shell helper anchor.")


def main() -> None:
    cpp = MAIN_CPP.read_text(encoding="utf-8")
    header = MAIN_H.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    cpp = ensure_include(
        cpp,
        '#include "shell/BottomTelemetryPresenter.h"',
        '#include "shell/QueueUiPresenter.h"',
    )

    build_body = r'''
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
}
'''

    sync_body = r'''
void MainWindow::syncBottomTelemetry()
{
    spellvision::shell::BottomTelemetryPresenter::SyncBindings bindings;
    bindings.queueManager = queueManager_;
    bindings.currentGenerationPage = generationPageForMode(currentModeId_);
    bindings.currentModeId = currentModeId_;
    bindings.pageContextText = pageContextForMode(currentModeId_);
    bindings.readyLabel = bottomReadyLabel_;
    bindings.pageLabel = bottomPageLabel_;
    bindings.runtimeLabel = bottomRuntimeLabel_;
    bindings.queueLabel = bottomQueueLabel_;
    bindings.vramLabel = bottomVramLabel_;
    bindings.modelLabel = bottomModelLabel_;
    bindings.loraLabel = bottomLoraLabel_;
    bindings.stateLabel = bottomStateLabel_;
    bindings.progressBar = bottomProgressBar_;

    spellvision::shell::BottomTelemetryPresenter::sync(bindings);
}
'''

    cpp = replace_function_body(cpp, "void MainWindow::buildBottomTelemetryBar()", build_body)
    cpp = replace_function_body(cpp, "void MainWindow::syncBottomTelemetry()", sync_body)

    cmake = patch_cmake(cmake)

    MAIN_CPP.write_text(cpp, encoding="utf-8")
    MAIN_H.write_text(header, encoding="utf-8")
    CMAKE.write_text(cmake, encoding="utf-8")

    print("Sprint 14C Pass 10 applied: BottomTelemetryPresenter wired into MainWindow.")


if __name__ == "__main__":
    main()
