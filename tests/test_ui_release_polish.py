"""The v1.0 UI must-fix list, pinned so it cannot quietly reopen.

Per-page UI audit, 2026-09-01. Zero dead controls were found on any page; the defects were in
layout, disclosure, error presentation and the absence of a version story. Each fix is small; each
of these is the property that keeps it fixed. Where a property can be stated tree-wide it is --
"worker stderr is never a dialog body" holds for every page, not the four sites that had it.

The responsive matrix (tests/cpp/test_responsive_matrix.cpp) is the mechanised half for layout;
this file asserts the matrix knows the two pages it did not, and everything the matrix cannot see.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from sweeps import sources  # noqa: E402

QT = ROOT / "qt_ui"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


# --- F: a traceback is never the body of a dialog -------------------------------------------------

_TR_WITH_STDERR = re.compile(r'tr\("[^"]*Worker stderr[^"]*"')
_DIALOG_WITH_STDERR = re.compile(r"QMessageBox::(?:warning|critical|information|question)\((?:[^;]|\n){0,900}?stderrText", re.MULTILINE)


def test_no_translated_string_in_the_tree_embeds_worker_stderr() -> None:
    hits = [sources.relative(p) for p in sources.cpp_sources() if _TR_WITH_STDERR.search(p.read_text(encoding="utf-8", errors="replace"))]
    assert not hits, f"raw worker stderr is again part of a user-facing string: {hits}"


def test_no_static_dialog_in_the_tree_takes_stderr_as_body() -> None:
    """The static QMessageBox helpers have no detailed-text slot, so stderr passed to one can only
    land in the body. showWorkerFailure puts it behind Show Details."""
    hits = []
    for p in sources.cpp_sources():
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in _DIALOG_WITH_STDERR.finditer(text):
            hits.append(f"{sources.relative(p)}:{text.count(chr(10), 0, m.start()) + 1}")
    assert not hits, f"stderr reaches a dialog body at: {hits}"


def test_the_helper_puts_stderr_behind_show_details() -> None:
    """One helper, in shell/, because the tree-wide rule above found sites in two files. A page-
    private copy would fix one page and leave the other to grow its own."""
    body = _read("qt_ui/shell/WorkerFailureDialog.cpp")
    start = body.index("void showWorkerFailure(")
    fn = body[start:body.index("\n}\n", start)]
    assert "setDetailedText(" in fn
    assert "setText(body)" in fn
    # The page's method is a delegate, not a second implementation.
    page = _read("qt_ui/WorkflowLibraryPage.cpp")
    start = page.index("void WorkflowLibraryPage::showWorkerFailure(")
    delegate = page[start:page.index("\n}\n", start)]
    assert "spellvision::shell::showWorkerFailure(this, title, body, stderrText)" in delegate
    assert "setDetailedText(" not in delegate


# --- A: the Runtime page owns a scroll region, and the matrix watches it ---------------------------

def test_the_runtime_page_owns_exactly_one_scroll_region() -> None:
    body = _read("qt_ui/ManagerPage.cpp")
    assert body.count("new QScrollArea(") == 1, "CLAUDE.md section 2: exactly one, never nested, never none"


def test_the_matrix_covers_workflows_and_runtime() -> None:
    body = _read("tests/cpp/test_responsive_matrix.cpp")
    for surface, ctor in (("Workflows library", "new WorkflowLibraryPage("), ("Runtime page", "new ManagerPage(")):
        assert f'{{"{surface}", ' in body, f"{surface} is not a matrix surface"
        assert ctor in body, f"{surface} has no constructor in the matrix factory"


def test_the_generate_clause_is_declared_per_surface_not_assumed() -> None:
    """Workflows' Import button carries PrimaryActionButton and is hidden by default; asserting
    "Generate reachable" against it would fail the page for the wrong reason."""
    body = _read("tests/cpp/test_responsive_matrix.cpp")
    assert "bool hasGenerate;" in body
    assert 'hasGenerate ? page->findChild<QPushButton *>' in body


# --- B: the Workflows action row wraps -------------------------------------------------------------

def test_the_workflows_actions_are_two_rows() -> None:
    body = _read("qt_ui/WorkflowLibraryPage.cpp")
    assert "auto *primaryActions = new QHBoxLayout();" in body
    assert "auto *secondaryActions = new QHBoxLayout();" in body
    assert "detailButtons->addLayout(primaryActions);" in body
    # Delete keeps the far-right seat on its own row.
    sec = body[body.index("auto *secondaryActions"):body.index("detailButtons->addLayout(primaryActions)")]
    assert sec.index("addStretch(1)") < sec.index("addWidget(deleteWorkflowButton_)")


# --- C: developer tools are gated once ------------------------------------------------------------

def test_the_hunt_list_button_is_a_dev_tool() -> None:
    body = _read("qt_ui/ImageGenerationPage.cpp")
    assert "queueHuntListButton_->setVisible(spellvision::shell::ShellNavigationController::devToolsVisible())" in body


def test_dev_tool_visibility_is_one_env_read() -> None:
    """The hidden modes and the hunt tool read the same predicate. A second
    qEnvironmentVariableIsEmpty("SPELLVISION_SHOW_ALL_MODES") anywhere is a second resolver."""
    hits = []
    for p in sources.cpp_sources():
        text = p.read_text(encoding="utf-8", errors="replace")
        n = text.count('"SPELLVISION_SHOW_ALL_MODES"')
        if n:
            hits.append((sources.relative(p), n))
    assert hits == [("qt_ui/shell/ShellNavigationController.cpp", 1)], hits


# --- E: the product has a version ------------------------------------------------------------------

def test_the_version_is_declared_once_in_cmake() -> None:
    cmake = _read("CMakeLists.txt")
    assert re.search(r"^project\(SpellVision VERSION \d+\.\d+\.\d+ LANGUAGES CXX\)", cmake, re.MULTILINE)
    assert 'SPELLVISION_VERSION="${PROJECT_VERSION}"' in cmake


def test_main_publishes_the_version_to_qt() -> None:
    assert "QCoreApplication::setApplicationVersion(QStringLiteral(SPELLVISION_VERSION))" in _read("qt_ui/main.cpp")


def test_no_second_version_literal_exists_in_the_ui() -> None:
    """The version is spelled in CMake. A literal like "1.0.0" in a .cpp is the one that drifts."""
    cmake = _read("CMakeLists.txt")
    declared = re.search(r"project\(SpellVision VERSION (\d+\.\d+\.\d+)", cmake).group(1)
    hits = [sources.relative(p) for p in sources.cpp_sources()
            if f'"{declared}"' in p.read_text(encoding="utf-8", errors="replace")
            or f'"v{declared}"' in p.read_text(encoding="utf-8", errors="replace")]
    assert not hits, f"the version literal {declared!r} is spelled again in: {hits}"


def test_settings_offers_about_and_check_for_updates() -> None:
    h = _read("qt_ui/SettingsPage.h")
    c = _read("qt_ui/SettingsPage.cpp")
    assert "void checkForUpdatesRequested();" in h
    assert "void showUpdateCheckResult(const QString &status, const QString &releaseUrl);" in h
    assert 'QStringLiteral("Check for updates")' in c
    assert "spellvision::shell::appVersion()" in c


def test_the_update_check_only_reports_and_never_installs() -> None:
    """Doc 28: unattended mutation is post-1.0. The check may open a page; it may not write."""
    body = _read("qt_ui/MainWindow.cpp")
    start = body.index("void MainWindow::checkForAppUpdates()")
    fn = body[start:body.index("\n}\n", start)]
    assert "latestReleaseApiUrl()" in fn
    # Code tokens, not words: the first version of this matched "download" inside the comment
    # that explains nothing is downloaded, which is the opposite of a finding.
    code_only = "\n".join(line for line in fn.splitlines() if not line.strip().startswith("//"))
    for forbidden in ("QProcess", "QFile(", "QSaveFile", "startDetached(", "QDir::mkpath(", "->write(", ".exe\"", ".msi\""):
        assert forbidden not in code_only, f"the update check touches {forbidden!r}; it must only report"


def test_the_system_menu_has_about() -> None:
    body = _read("qt_ui/MainWindow.cpp")
    start = body.index("void MainWindow::showSystemMenu(")
    fn = body[start:body.index("\n}\n", start)]
    assert 'QStringLiteral("About SpellVision")' in fn
    assert "QMessageBox::about(" in fn
