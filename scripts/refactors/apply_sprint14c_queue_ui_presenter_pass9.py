from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
CPP = ROOT / "qt_ui" / "MainWindow.cpp"
H = ROOT / "qt_ui" / "MainWindow.h"
CMAKE = ROOT / "CMakeLists.txt"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def insert_once(text: str, needle: str, insertion: str, after: bool = True) -> tuple[str, bool]:
    if insertion.strip() in text:
        return text, False
    if needle not in text:
        return text, False
    replacement = needle + insertion if after else insertion + needle
    return text.replace(needle, replacement, 1), True


def find_function_span(text: str, signature: str) -> tuple[int, int] | None:
    start = text.find(signature)
    if start < 0:
        return None
    brace = text.find("{", start)
    if brace < 0:
        return None

    depth = 0
    in_string = False
    in_char = False
    escaped = False
    line_comment = False
    block_comment = False

    i = brace
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if line_comment:
            if ch == "\n":
                line_comment = False
            i += 1
            continue

        if block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
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
            line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_comment = True
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
                return start, i + 1
        i += 1

    return None


def replace_function_body(text: str, signature: str, body: str) -> tuple[str, bool]:
    span = find_function_span(text, signature)
    if not span:
        return text, False
    start, end = span
    replacement = signature + "\n{\n" + body.rstrip() + "\n}"
    if text[start:end] == replacement:
        return text, False
    return text[:start] + replacement + text[end:], True


def patch_cmake() -> bool:
    text = read(CMAKE)
    sources = [
        "    qt_ui/shell/QueueUiPresenter.cpp",
        "    qt_ui/shell/QueueUiPresenter.h",
    ]
    if "qt_ui/shell/QueueUiPresenter.cpp" in text:
        return False
    insertion = "\n" + "\n".join(sources)
    for anchor in [
        "    qt_ui/shell/MainWindowTrayController.h",
        "    qt_ui/shell/MainWindowTrayController.cpp",
        "    qt_ui/MainWindow.h",
    ]:
        if anchor in text:
            text = text.replace(anchor, anchor + insertion, 1)
            write(CMAKE, "\n".join(line.rstrip() for line in text.splitlines()) + "\n")
            return True
    raise RuntimeError("Could not find CMake anchor for QueueUiPresenter sources.")


def patch_header() -> list[str]:
    text = read(H)
    changes: list[str] = []
    # Pass 9 uses static presenter helpers, so no member is required.
    write(H, text)
    return changes


def patch_cpp() -> list[str]:
    text = read(CPP)
    changes: list[str] = []

    text, changed = insert_once(
        text,
        '#include "shell/MainWindowTrayController.h"',
        '\n#include "shell/QueueUiPresenter.h"',
        after=True,
    )
    if changed:
        changes.append("include QueueUiPresenter")

    old = "QString queueStateDisplay(QueueItemState state)"
    if old in text and "QueueUiPresenter::queueStateDisplay" not in text[:text.find(old)]:
        # Leave the legacy helper for now. It may still be used by details rendering.
        changes.append("left legacy queueStateDisplay in place for details safety")

    signature = "void MainWindow::updateActiveQueueStrip()"
    new_body = """
    spellvision::shell::QueueUiPresenter::updateActiveQueueStrip(
        queueManager_,
        activeQueueTitleLabel_,
        activeQueueSummaryLabel_);
"""
    text, changed = replace_function_body(text, signature, new_body)
    if changed:
        changes.append("delegate updateActiveQueueStrip")

    signature = "QString MainWindow::selectedQueueId() const"
    new_body = """
    return spellvision::shell::QueueUiPresenter::selectedQueueId(queueTableView_);
"""
    text, changed = replace_function_body(text, signature, new_body)
    if changed:
        changes.append("delegate selectedQueueId")

    # Replace the most common direct filter connects with the presenter helper.
    direct_filter_blocks = [
        "connect(queueSearchEdit_, &QLineEdit::textChanged, queueFilterProxyModel_, &QueueFilterProxyModel::setTextFilter);\n    connect(queueStateFilter_, &QComboBox::currentTextChanged, queueFilterProxyModel_, &QueueFilterProxyModel::setStateFilter);",
        "connect(queueSearchEdit_, &QLineEdit::textChanged, queueFilterProxyModel_, &QueueFilterProxyModel::setTextFilter);\r\n    connect(queueStateFilter_, &QComboBox::currentTextChanged, queueFilterProxyModel_, &QueueFilterProxyModel::setStateFilter);",
    ]
    replacement = "spellvision::shell::QueueUiPresenter::connectFilterControls(queueSearchEdit_, queueStateFilter_, queueFilterProxyModel_);"
    if replacement not in text:
        for block in direct_filter_blocks:
            if block in text:
                text = text.replace(block, replacement, 1)
                changes.append("delegate queue filter connects")
                break

    write(CPP, text)
    return changes


def main() -> None:
    changes = []
    if patch_cmake():
        changes.append("add QueueUiPresenter to CMake")
    changes.extend(patch_header())
    changes.extend(patch_cpp())

    if changes:
        print("Sprint 14C Pass 9 patch applied:")
        for change in changes:
            print(f" - {change}")
    else:
        print("Sprint 14C Pass 9 patch made no source changes; files may already be patched.")


if __name__ == "__main__":
    main()
