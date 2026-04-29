from pathlib import Path
import re
import sys

ROOT = Path.cwd()
main_cpp = ROOT / "qt_ui" / "MainWindow.cpp"
cmake_path = ROOT / "CMakeLists.txt"

if not main_cpp.exists():
    raise SystemExit("qt_ui/MainWindow.cpp not found")
if not cmake_path.exists():
    raise SystemExit("CMakeLists.txt not found")

text = main_cpp.read_text(encoding="utf-8")

include_line = '#include "shell/ShellNavigationController.h"\n'
if include_line not in text:
    anchor = '#include "shell/QueueUiPresenter.h"\n'
    if anchor in text:
        text = text.replace(anchor, anchor + include_line, 1)
    else:
        text = text.replace('#include "shell/MainWindowTrayController.h"\n',
                            '#include "shell/MainWindowTrayController.h"\n' + include_line, 1)

rail_pattern = re.compile(
    r'\n\s*const struct RailButtonSpec\s*\n\s*\{\s*\n'
    r'\s*QString modeId;\s*\n'
    r'\s*QString text;\s*\n'
    r'\s*QString toolTip;\s*\n'
    r'\s*\}\s*specs\[\]\s*=\s*\{.*?\};',
    re.DOTALL,
)
rail_replacement = '\n    const auto specs = spellvision::shell::ShellNavigationController::railButtonSpecs();'
text, rail_count = rail_pattern.subn(rail_replacement, text, count=1)
if rail_count == 0 and "ShellNavigationController::railButtonSpecs()" not in text:
    raise SystemExit("Could not replace createSideRail rail specs")

page_context_pattern = re.compile(
    r'QString MainWindow::pageContextForMode\(const QString &modeId\) const\s*\{.*?\n\}',
    re.DOTALL,
)
page_context_replacement = """QString MainWindow::pageContextForMode(const QString &modeId) const
{
    return spellvision::shell::ShellNavigationController::pageContextForMode(modeId);
}"""
text, page_context_count = page_context_pattern.subn(page_context_replacement, text, count=1)
if page_context_count == 0 and "ShellNavigationController::pageContextForMode" not in text:
    print("warning: pageContextForMode body was not replaced", file=sys.stderr)

update_button_pattern = re.compile(
    r'void MainWindow::updateModeButtonState\(const QString &modeId\)\s*\{.*?\n\}',
    re.DOTALL,
)
update_button_replacement = """void MainWindow::updateModeButtonState(const QString &modeId)
{
    spellvision::shell::ShellNavigationController::updateModeButtonState(modeButtons_, modeId);
}"""
text, update_button_count = update_button_pattern.subn(update_button_replacement, text, count=1)
if update_button_count == 0 and "ShellNavigationController::updateModeButtonState" not in text:
    print("warning: updateModeButtonState body was not replaced", file=sys.stderr)

main_cpp.write_text(text, encoding="utf-8", newline="\n")

cmake = cmake_path.read_text(encoding="utf-8")
sources = [
    "    qt_ui/shell/ShellNavigationController.cpp",
    "    qt_ui/shell/ShellNavigationController.h",
]
if "qt_ui/shell/ShellNavigationController.cpp" not in cmake:
    insert = "\n".join(sources)
    anchors = [
        r"(?m)^(\s*qt_ui/shell/QueueUiPresenter\.h\s*)$",
        r"(?m)^(\s*qt_ui/shell/BottomTelemetryPresenter\.h\s*)$",
        r"(?m)^(\s*qt_ui/shell/MainWindowTrayController\.h\s*)$",
    ]
    for anchor in anchors:
        if re.search(anchor, cmake):
            cmake = re.sub(anchor, r"\1\n" + insert, cmake, count=1)
            break
    else:
        raise SystemExit("Could not find shell source anchor in CMakeLists.txt")

cmake_path.write_text(cmake, encoding="utf-8", newline="\n")

print("Applied Sprint 14C Pass 12 ShellNavigationController wiring.")
