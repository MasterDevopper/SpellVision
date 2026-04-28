from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_CPP = ROOT / "qt_ui" / "MainWindow.cpp"
CMAKE = ROOT / "CMakeLists.txt"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def add_include(text: str) -> str:
    include = '#include "workflows/WorkflowLaunchController.h"'
    if include in text:
        return text

    anchor = '#include "WorkflowLibraryPage.h"'
    if anchor in text:
        return text.replace(anchor, anchor + "\n" + include, 1)

    fallback = '#include "workers/WorkerSubmissionPolicy.h"'
    if fallback in text:
        return text.replace(fallback, fallback + "\n" + include, 1)

    raise RuntimeError("Could not find include anchor in MainWindow.cpp")


def find_function(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"Could not find function signature: {signature}")

    brace = text.find("{", start)
    if brace < 0:
        raise RuntimeError(f"Could not find opening brace for: {signature}")

    depth = 0
    in_string = False
    in_char = False
    escape = False
    in_line_comment = False
    in_block_comment = False

    for index in range(brace, len(text)):
        ch = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
            continue

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if in_char:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
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
                return start, index + 1

    raise RuntimeError(f"Could not find closing brace for: {signature}")


def patch_open_workflow_draft(text: str) -> str:
    signature = "void MainWindow::openWorkflowDraft(const QJsonObject &draft)"
    start, end = find_function(text, signature)

    replacement = r'''void MainWindow::openWorkflowDraft(const QJsonObject &draft)
{
    const QString modeId = spellvision::workflows::WorkflowLaunchController::resolveDraftModeId(
        draft,
        [this](const QString &candidate) { return generationPageForMode(candidate) != nullptr; });

    ImageGenerationPage *page = generationPageForMode(modeId);
    if (!page)
    {
        QMessageBox::warning(this,
                             QStringLiteral("Workflow Draft"),
                             QStringLiteral("This workflow cannot be opened as an editable draft in the current build."));
        return;
    }

    page->applyWorkflowDraft(draft);
    switchToMode(modeId);

    appendLogLine(spellvision::workflows::WorkflowLaunchController::draftOpenedLogLine(draft, modeId));

    if (!page->workflowDraftCanSubmit())
        appendLogLine(spellvision::workflows::WorkflowLaunchController::draftRequiresReviewLogLine(modeId));
}'''

    return text[:start] + replacement + text[end:]


def patch_cmake(text: str) -> str:
    sources = [
        "    qt_ui/workflows/WorkflowLaunchController.cpp",
        "    qt_ui/workflows/WorkflowLaunchController.h",
    ]
    if "qt_ui/workflows/WorkflowLaunchController.cpp" in text:
        return text

    insert = "\n".join(sources)
    anchors = [
        "    qt_ui/shell/BottomTelemetryPresenter.h",
        "    qt_ui/shell/QueueUiPresenter.h",
        "    qt_ui/shell/MainWindowTrayController.h",
        "    qt_ui/workers/WorkerSubmissionPolicy.h",
    ]
    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "\n" + insert, 1)

    raise RuntimeError("Could not find CMake source anchor for WorkflowLaunchController")


def main() -> None:
    main_cpp = read(MAIN_CPP)
    main_cpp = add_include(main_cpp)
    main_cpp = patch_open_workflow_draft(main_cpp)
    write(MAIN_CPP, main_cpp)

    cmake = read(CMAKE)
    cmake = patch_cmake(cmake)
    cmake = "\n".join(line.rstrip() for line in cmake.splitlines()) + "\n"
    write(CMAKE, cmake)

    print("Sprint 14C Pass 11 workflow launch controller patch applied.")


if __name__ == "__main__":
    main()
