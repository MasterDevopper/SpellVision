from pathlib import Path
import re

ROOT = Path.cwd()
MAIN_CPP = ROOT / "qt_ui" / "MainWindow.cpp"
CMAKE = ROOT / "CMakeLists.txt"

INCLUDE_LINE = '#include "shell/MainWindowTrayController.h"\n'

NEW_BODY = '''void MainWindow::buildPersistentDocks()
{
    spellvision::shell::MainWindowTrayController::Bindings trayBindings;
    trayBindings.owner = this;
    trayBindings.createBottomUtilityWidget = [this]() { return createBottomUtilityWidget(); };
    trayBindings.hideNativeDockTitleBar = [this](QDockWidget *dock) { hideNativeDockTitleBar(dock); };
    trayBindings.updateDockChrome = [this]() { updateDockChrome(); };
    trayBindings.queueDock = &queueDock_;
    trayBindings.detailsDock = &detailsDock_;
    trayBindings.logsDock = &logsDock_;

    spellvision::shell::MainWindowTrayController::buildPersistentDocks(trayBindings);
}
'''

CMAKE_LINES = [
    "    qt_ui/shell/MainWindowTrayController.cpp",
    "    qt_ui/shell/MainWindowTrayController.h",
]


def add_include(text: str) -> str:
    if INCLUDE_LINE.strip() in text:
        return text
    anchor = '#include "WorkflowLibraryPage.h"\n'
    if anchor not in text:
        raise RuntimeError("Could not find WorkflowLibraryPage include anchor in MainWindow.cpp")
    return text.replace(anchor, anchor + INCLUDE_LINE, 1)


def find_function_bounds(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"Could not find function signature: {signature}")

    brace = text.find("{", start)
    if brace < 0:
        raise RuntimeError(f"Could not find opening brace for: {signature}")

    depth = 0
    i = brace
    in_string = False
    in_char = False
    escape = False
    in_line_comment = False
    in_block_comment = False

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
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if in_char:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
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
                end = i + 1
                while end < len(text) and text[end] in " \t\r\n":
                    end += 1
                return start, end

        i += 1

    raise RuntimeError(f"Could not find closing brace for: {signature}")


def replace_build_persistent_docks(text: str) -> str:
    signature = "void MainWindow::buildPersistentDocks()"
    start, end = find_function_bounds(text, signature)
    return text[:start] + NEW_BODY + "\n" + text[end:]


def patch_cmake(text: str) -> str:
    if "qt_ui/shell/MainWindowTrayController.cpp" in text:
        return text

    insert = "\n".join(CMAKE_LINES)
    anchors = [
        r"^(\s*qt_ui/workers/WorkerSubmissionPolicy\.h\s*)$",
        r"^(\s*qt_ui/workers/WorkerQueueController\.h\s*)$",
        r"^(\s*qt_ui/MainWindow\.h\s*)$",
    ]
    for pattern in anchors:
        if re.search(pattern, text, flags=re.MULTILINE):
            return re.sub(pattern, r"\1\n" + insert, text, count=1, flags=re.MULTILINE)
    raise RuntimeError("Could not find a CMake source anchor. Add MainWindowTrayController manually.")


def main() -> None:
    main_cpp = MAIN_CPP.read_text(encoding="utf-8")
    main_cpp = add_include(main_cpp)
    main_cpp = replace_build_persistent_docks(main_cpp)
    MAIN_CPP.write_text(main_cpp, encoding="utf-8", newline="")

    cmake = CMAKE.read_text(encoding="utf-8")
    cmake = patch_cmake(cmake)
    CMAKE.write_text(cmake, encoding="utf-8", newline="")

    print("Applied Sprint 14C Pass 8 MainWindow tray controller wiring.")


if __name__ == "__main__":
    main()
