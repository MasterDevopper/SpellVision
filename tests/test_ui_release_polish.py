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


def test_pages_built_ahead_of_their_first_visit_are_parked_hidden() -> None:
    """A page is homed in the stack on first visit. Until then it is a plain child of MainWindow,
    and a child that exists before show() is SHOWN with it -- at (0,0), 100x30, painted over the
    title bar. Seen live 2026-09-02 as the breadcrumb reading "nage" for "Text to Image": the
    "arcs" beside the badge were WorkflowLibraryPage's buttons. The build parks every page the stack
    does not yet hold."""
    main = _read("qt_ui/MainWindow.cpp")
    park = re.search(
        r"findChildren<QWidget \*>\(QString\(\), Qt::FindDirectChildrenOnly\)[^}]*"
        r"endsWith\(QStringLiteral\(\"Page\"\)\)[^}]*indexOf\(page\) < 0[^}]*page->hide\(\);",
        main,
    )
    assert park is not None, "buildPages must hide every page the stack does not yet hold"
    # And the homing step still exists: switchToMode adds a parked page before showing it.
    assert "if (target && pageStack_->indexOf(target) < 0)" in main
    assert "pageStack_->addWidget(target);" in main


# --- 2026-09-02, the cheap-correctness lane: a value the UI did not choose the length of ----------

_ELIDE_CALL = re.compile(r"\belidedText\s*\(")
# Elision sites that are NOT widget text, keyed by site and valued by a REASON, which is the
# repo's exemption convention (tests/sweeps/exemptions.py): adding one costs a reviewer reading a
# sentence, and a boolean would not.
#
# A heuristic was tried first and abandoned honestly: "the nearest column-0 function definition"
# names a file-scope helper for a delegate's indented paint(), and "a QPainter within 1500
# characters" misses both real painters because the QPainter is a parameter 50 lines up. Two known
# sites do not need a classifier.
_ELISION_EXEMPT = {
    "qt_ui/assets/ModelCardDelegate.cpp:191": "delegate paint: elides into the QRect it is handed, and has no widget to measure",
    "qt_ui/CommandPaletteDialog.cpp:105": "delegate paint: same -- the row is a rect in a view, not a widget",
}


def _strip_line_comments(text: str) -> str:
    """A comment saying what the code must NOT do is not the code doing it. The first version of the
    bottom-bar rule below flagged its own explanatory comment -- the same trap this file already
    records for the update check, where "download" matched inside the sentence explaining that
    nothing is downloaded."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))


def _paints_into_a_rect(text: str, offset: int) -> bool:
    return "QPainter" in text[max(0, offset - _PAINTER_SCOPE_WINDOW):offset]


def test_widget_text_elides_through_one_helper() -> None:
    """Three implementations of "does this text fit" disagreed: applyTelemetryText reserved 6px,
    ErrorPillLabel 24px plus a glyph, and a third was about to be written for the video caption and
    the LoRA name. They now share widgets/ElidingLabel.h::elideForWidget.

    PAINTED elision is a different question and stays exempt: a delegate has a QRect, not a widget,
    so it cannot ask a widget for its width. The exemption is the enclosing function being a paint
    routine -- measured, both of the two current sites are, and the count is pinned so a fourth
    implementation cannot arrive quietly."""
    widget_side = []
    seen_exempt = set()
    for path in sources.cpp_sources():
        rel = sources.relative(path)
        if rel.endswith("widgets/ElidingLabel.cpp"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _ELIDE_CALL.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            site = f"{rel}:{line}"
            if site in _ELISION_EXEMPT:
                seen_exempt.add(site)
            else:
                widget_side.append(site)
    assert not widget_side, f"a second elision implementation for widget text: {widget_side}"
    # An exemption that no longer matches anything is a stale reason nobody will re-read.
    assert seen_exempt == set(_ELISION_EXEMPT), f"stale elision exemptions: {set(_ELISION_EXEMPT) - seen_exempt}"


def test_the_video_caption_cannot_be_a_wrapping_label() -> None:
    """The caption is bound by TYPE, not by a call the next edit can forget. As a wrapped QLabel it
    was a four-line block -- the last line the full absolute path -- inside the video preview's own
    height budget, so at half height the picture got what the caption left."""
    header = _read("qt_ui/preview/MediaPreviewController.h")
    assert "spellvision::widgets::ElidingLabel *captionLabel" in header
    body = _read("qt_ui/preview/MediaPreviewController.cpp")
    assert "captionLabel->setFullText(" in body
    assert "captionLabel->setText(" not in body, "setText bypasses the stored full text, so the tooltip goes stale"


def test_the_lora_name_elides() -> None:
    """LoRA names are underscore-joined single tokens and U+005F is not a UAX-14 break opportunity,
    so setWordWrap had nothing to break and the name was cut mid-glyph in a 215px card."""
    body = _read("qt_ui/assets/LoraStackController.cpp")
    assert "new spellvision::widgets::ElidingLabel(row, Qt::ElideMiddle)" in body
    name_block = body[body.index("// Name only"):body.index("topRow->addWidget(enabledBox)")]
    assert "setWordWrap(true)" not in name_block


def test_the_aspect_fit_does_not_drop_chrome_at_a_constant() -> None:
    """fitBudget treated chrome over 160px as pre-layout garbage. A four-line caption plus a
    transport bar crosses that, and the cap then came out ~160px too tall. The guard is dimensional
    now: chrome cannot equal or exceed the budget it is measured inside."""
    body = _read("qt_ui/preview/AspectCap.cpp")
    assert "kSaneChrome" not in body, "the chrome guard is a magic number again"
    assert "chrome.width() >= budget.width()" in body
    assert "chrome.height() >= budget.height()" in body


# --- the bottom bar describes the page you are looking at -----------------------------------------

_BOTTOM_LABELS = ("bottomPageLabel_", "bottomModelLabel_", "bottomLoraLabel_")


def test_each_bottom_bar_label_has_one_writer() -> None:
    """The page name had three: `modeId.toUpper()` ("T2I"), `pageContextForMode()` ("Text to
    Image") and a setBottomPageContext setter -- so which one you saw depended on whether the queue
    had moved since the mode switch. Text now reaches these labels only through applyTelemetryText."""
    body = _strip_line_comments(_read("qt_ui/MainWindow.cpp"))
    offenders = []
    for name in _BOTTOM_LABELS:
        for match in re.finditer(rf"{name}->setText\(", body):
            offenders.append(f"{name}:{body.count(chr(10), 0, match.start()) + 1}")
    assert not offenders, f"a second writer of a bottom-bar label: {offenders}"
    assert "void MainWindow::setBottomPageContext" not in body


def test_the_bottom_bar_refreshes_on_a_page_change_and_on_a_plain_poll() -> None:
    """"Model:" showed the LAST-RUN model. Not a second writer -- one writer that was never called:
    syncBottomTelemetry hung off submits and afterQueueSnapshotApplied, which fires only when the
    queue CHANGED, so an idle app kept whatever the bar held when the queue last moved. This is the
    third instance of that trap in this file; the first two are the detection re-scan and the
    download poll, both fixed by moving to queuePollSucceeded."""
    body = _read("qt_ui/MainWindow.cpp")
    start = body.index("void MainWindow::applyShellStateForMode(")
    fn = body[start:body.index("\n}\n", start)]
    assert "syncBottomTelemetry();" in fn, "a mode change leaves the bar describing the previous page"
    poll = re.search(
        r"queuePollSucceeded,\s*\n\s*this, &MainWindow::syncBottomTelemetry\)",
        body,
    )
    assert poll is not None, "the bar only refreshes when the queue CHANGES, so an idle app never updates it"


def test_a_page_with_no_model_slot_does_not_claim_the_user_chose_nothing() -> None:
    """Three states, not two (Doc 50 rule 3). "Model: none" on Flows or History is a false
    statement about the user's choices, and it is the same string a generation page showed when
    nothing was picked."""
    presenter = _read("qt_ui/shell/TelemetryPresenter.cpp")
    assert "chip.visible = false;" in presenter
    assert "not selected" in presenter
    assert '"none"' not in presenter and "QStringLiteral(\"none\")" not in presenter
    main = _read("qt_ui/MainWindow.cpp")
    assert "bottomModelChipVisible_" in main, "the width reflow re-shows the chip the presenter hid"
