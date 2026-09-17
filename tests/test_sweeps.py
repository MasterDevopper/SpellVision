"""Tree-wide properties, run over every source file rather than the ones a defect was found in.

Eleven of the top twenty findings in the 2026-08-30 audit were second copies of a rule that had
already been applied correctly once. The ratchets meant to prevent that had the same shape as the
bug they were guarding:

* the seed ratchet pinned three filenames; three live violations sat outside them and it was green;
* the endpoint ratchet globbed ``python/*.py``, which is **82 of 92 modules** -- everything under
  ``python/runtime_adapters/`` and ``python/video_adapters/`` was invisible to every sweep here.

So the scope lives in one place (``sweeps/sources.py``), no rule may name a file, and a site that is
legitimately different carries a REASON rather than being silently out of scope.
"""
from __future__ import annotations

import ast
import collections
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Tree-wide property, not a call-site check: this IS the sweep harness.
# Runs in the pre-commit hook -- keep it fast.
pytestmark = pytest.mark.ratchet

from sweeps import exemptions, rules, sources  # noqa: E402


@pytest.fixture(scope="module")
def findings() -> dict[str, list[rules.Violation]]:
    return rules.run_all()


# --- the scope itself ------------------------------------------------------------------------------


def test_the_sweep_sees_every_module_including_the_subdirectories():
    """The bug that made every other ratchet weaker than it looked.

    ``glob('*.py')`` saw 82 modules of 92. Ten lived in ``runtime_adapters/`` and
    ``video_adapters/``, and both packages held live violations no sweep could see.

    This test no longer names ``runtime_adapters``: Phase 4a deleted it, on the strength of the
    reachability rule the flat glob had also been hiding. What the test asserts is the PROPERTY --
    that subdirectory modules are swept at all -- rather than the two package names that happened
    to expose the gap, because a name here would rot exactly the way the glob did.
    """
    found = sources.python_sources()
    assert len(found) >= 88, f"expected at least 88 modules, swept {len(found)}"

    in_subdirs = [p for p in found if p.parent.name != "python"]
    assert in_subdirs, "the sweep is flat again -- subdirectory modules are invisible"


def test_no_rule_names_a_file():
    """A rule scoped to where its defect was found is a memo, not a rule."""
    source = (Path(__file__).parent / "sweeps" / "rules.py").read_text(encoding="utf-8")
    for suspicious in (".py\"", ".py'", "BUILDER_FILES", "FILES = ("):
        assert suspicious not in source, (
            f"rules.py mentions {suspicious!r} -- rules take their sources from sources.py"
        )


def test_every_rule_states_why_it_exists():
    """A rule without a citation is an opinion. Doc 50's own rules each name the defect that
    produced them, and these are the enforcement of those rules."""
    for rule in rules.ALL_RULES:
        assert len(rule.citation) > 80, f"{rule.name} has no real citation"


# --- the rules -------------------------------------------------------------------------------------


@pytest.mark.parametrize("rule", rules.ALL_RULES, ids=lambda r: r.name)
def test_rule_matches_its_baseline(rule, findings):
    """Two-way, like KNOWN_GAPS.

    A count going UP is a regression. A count going DOWN means the baseline must be lowered rather
    than left standing as a permanent allowance -- otherwise a fixed bug leaves an excuse behind and
    the number stops meaning anything.
    """
    violations = [v for v in findings[rule.name] if not exemptions.is_exempt(rule.name, v.site)]
    actual = collections.Counter(sources.relative(v.path) for v in violations)
    expected = exemptions.baseline_for(rule.name)

    new_files = {f: n for f, n in actual.items() if f not in expected}
    assert not new_files, (
        f"\n{rule.name}: NEW violation(s) in {len(new_files)} file(s).\n"
        f"why this rule exists: {rule.citation}\n\n"
        + "\n".join(str(v) for v in violations
                    if sources.relative(v.path) in new_files)
        + "\n\nRoute the new code through the existing resolver. If the site is genuinely "
          "different, add it to EXEMPT with a reason."
    )

    grew = {f: (expected[f], actual[f]) for f in expected if actual.get(f, 0) > expected[f]}
    assert not grew, f"{rule.name}: violations increased in {grew} (was, now)"

    shrank = {f: (expected[f], actual.get(f, 0)) for f in expected if actual.get(f, 0) < expected[f]}
    assert not shrank, (
        f"{rule.name}: violations DROPPED in {shrank} (was, now) -- lower the baseline in "
        "sweeps/exemptions.py. A baseline that is not tightened stops being one."
    )


def test_the_seed_rule_is_at_zero_and_stays_there(findings):
    """The rule this harness was built to prove. It shipped with a ratchet naming three files and
    was green while three modules outside that list rendered seed 0 as 7, as 4419, and as a prompt
    hash. Swept properly, and fixed."""
    assert findings["seed-one-rule"] == [], "\n".join(
        str(v) for v in findings["seed-one-rule"])


def test_every_exemption_states_a_reason():
    """A boolean here would be indistinguishable from the out-of-scope state this module abolishes."""
    for rule, sites in exemptions.EXEMPT.items():
        for site, reason in sites.items():
            assert isinstance(reason, str) and len(reason) > 30, (
                f"{rule} / {site}: an exemption needs a reason, not a placeholder"
            )


def test_the_baseline_is_reported_so_it_cannot_be_forgotten(findings, capsys):
    """Prints the current debt. A baseline nobody reads becomes permanent."""
    # Only the rules CARRYING debt are printed. The baseline is 21 rules of which 17 are zero, and a
    # zero is not debt -- printing every one on every run buried the four numbers that matter under
    # seventeen that never move. Measured 2026-09-07: this block ran 405 times in one session for
    # ~204k tokens, and anything printed into a session's context is re-read on every later turn, so
    # boilerplate here is not paid once. The line that cannot be forgotten is the TOTAL, and it stays
    # unconditional -- as does the count of rules at zero, so a rule going quiet is still visible.
    with capsys.disabled():
        carrying = [(r.name, sum(exemptions.baseline_for(r.name).values())) for r in rules.ALL_RULES]
        carrying = [(name, total) for name, total in carrying if total]
        print("\n--- sweep baseline ---")
        for name, total in carrying:
            print(f"  {name:20s} {total:4d} known")
        clean = len(rules.ALL_RULES) - len(carrying)
        print(f"  {'TOTAL':20s} {exemptions.total_baseline():4d}"
              f"   ({clean} of {len(rules.ALL_RULES)} rules at zero)")


# --- a rule at zero has to be a rule that would FIRE ------------------------------------------------


def test_the_weight_rule_catches_every_spelling_the_spec_names():
    """`type-weight-on-ramp` is one of the zeroes, and a zero is only worth what the rule covers.
    The spec (§2.6) says it counts "`font-weight: 700|800|900` in stylesheets, plus `setWeight` off
    the 400/500/600 ramp" -- and until this review it did not do the second half at all:
    `setWeight(700)` and `setWeight(QFont::Weight(700))` both passed, because the only setWeight it
    could see was the `QFont::Bold` spelling. QSS `bold` (which IS 700) passed too. Fed the shapes
    directly, because the tree is clean: a rule proven only by finding nothing has not been proven.
    """
    probe = "\n".join([
        "f.setWeight(700);",
        "f.setWeight(QFont::Weight(700));",
        "f.setWeight(QFont::Bold);",
        'sheet += "font-weight: bold;";',
        "sheet += \"font: bold 12px 'IBM Plex Sans';\";",
        "f.setWeight(QFont::DemiBold);",  # 600, on the ramp
        "f.setWeight(500);",              # on the ramp
        "f.setWeight(static_cast<QFont::Weight>(fontWeight(token)));",  # the ramp table itself
    ])
    caught = [v.line for v in rules._check_weight_on_ramp(Path("probe.cpp"), probe)]
    assert caught == [1, 2, 3, 4, 5], caught


def test_the_family_rule_catches_a_family_named_from_either_side_of_the_wall():
    """`font-family-is-shipped` is the other zero, and it saw only a `font-family:` declaration
    inside a stylesheet. `QFont("JetBrains Mono")` names exactly the same unshipped face from C++,
    and so does the `font: 500 11px 'X'` shorthand; both passed. The last three lines are the
    false-positive counterweight -- QFontMetrics, a copy constructor and QFont::Tag must NOT be read
    as families, or the rule would report a face nobody asked for."""
    probe = "\n".join([
        'QFont mono(QStringLiteral("JetBrains Mono"), 10);',
        'f.setFamily("Cascadia Mono");',
        'f.setFamilies({"Comic Sans MS"});',
        "sheet += \"font: 500 11px 'JetBrains Mono';\";",
        "sheet += \"font-family:'IBM Plex Mono',monospace;\";",  # shipped
        "QFont copy(painter->font());",
        "QFontMetrics fm(f);",
        'const QFont::Tag tag("tnum");',
    ])
    caught = [(v.line, v.key) for v in rules._check_font_family_is_shipped(Path("probe.cpp"), probe)]
    assert caught == [(1, "JetBrains Mono"), (2, "Cascadia Mono"), (3, "Comic Sans MS"),
                      (4, "JetBrains Mono")], caught


def test_the_layout_switch_rule_reads_a_noexcept_definition():
    """`layout-switch-is-not-a-rebuild` failed its own control, and the failure was in what it READ.

    `_LAYOUT_SWITCH_DEFINITION` allowed `const` before the opening brace and no other trailing
    specifier, so

        void MainWindow::applyShellLayout(Layout l) noexcept { page->deleteLater(); }

    -- legal C++ on an out-of-line definition -- was not scanned AT ALL and the rule reported a clean
    zero over a body it had never opened. That is worse than the five holes its docstring names: a
    narrow rule tells you what it does not cover, a rule that skips the definition tells you nothing
    and looks identical to a passing one.

    The first four lines must fire (the specifier is the only difference between them). The last
    three are the counterweight: a declaration is not a definition, a call is not a definition, and a
    noexcept definition that rebuilds nothing must stay silent, or the fix would have traded a hole
    for a false positive.
    """
    probe = "\n".join([
        "void MainWindow::applyShellLayout(Layout l) noexcept { page->deleteLater(); }",       # 1
        "void MainWindow::applyShellLayout(Layout l) noexcept(true) { page->deleteLater(); }",  # 2
        "void MainWindow::applyShellLayout(Layout l) const { page->deleteLater(); }",           # 3
        "void MainWindow::applyShellLayout(Layout l) { page->deleteLater(); }",                 # 4
        "void MainWindow::applyShellLayout(Layout l) noexcept;",                # 5  a declaration
        "    applyShellLayout(l);",                                             # 6  a call
        "void MainWindow::applyShellLayout(Layout l) noexcept { relayout(); }", # 7  rebuilds nothing
    ])
    caught = [v.line for v in
              rules._check_layout_switch_is_not_a_rebuild(Path("qt_ui/Probe.cpp"), probe)]
    assert caught == [1, 2, 3, 4], caught


def test_the_qss_rule_sees_the_frame_the_style_draws():
    """`qss-draws-a-control` reported zero while five stylesheets painted QFrames.

    SvStyle draws PE_Frame, so a QFrame is a control the style owns -- but `_OWNED_TYPES` did not
    name it, and a type the matcher does not name is not a site the rule can fail on. Its zero was
    over a tree it was not looking at. Adding it surfaced 18 live sites in 7 files, now baselined.

    Lines 1-3 must fire: the bare type, the type with an id and a pseudo-state, and a border-only
    rule (painting is not only backgrounds). Lines 4-5 are the counterweight -- a QFrame rule that
    sets only geometry is exactly what a stylesheet is still ALLOWED to do, and QWidget is not a
    control the style draws, so neither may be reported or the retreat would have no landing place.
    """
    probe = "\n".join([
        'sheet += "QFrame { background: #101014; }";',                          # 1
        'sheet += "QFrame#UploadBox:hover { border: 1px solid #7c5cff; }";',    # 2
        'sheet += "QFrame#Divider { border-color: #2a2a33; }";',                # 3
        'sheet += "QFrame#Row { padding: 6px 10px; margin: 0; }";',             # 4  geometry only
        'sheet += "QWidget { background: #101014; }";',                         # 5  not an owned type
    ])
    caught = [v.line for v in
              rules._check_qss_draws_a_control(Path("qt_ui/Probe.cpp"), probe)]
    assert caught == [1, 2, 3], caught


def test_the_shell_geometry_rule_fires_on_the_defect_it_was_written_from():
    """`shell-geometry-through-the-layout` ships at zero, and a zero is worth exactly its coverage.

    Two halves, and the second is the one that would have gone unnoticed. The first six lines are
    reads that must FIRE: the drawer's own `sideRail_->width()`, its horizontal twin, the position
    spellings that make the same assumption from the other side, and the chrome tokens read through
    `chrome()` with and without the `ThemeManager::` prefix.

    The rest is the false-positive counterweight, and it is not decoration. `Chrome::ModeRailWidth`
    appears in the enum that DECLARES it and in the switch that gives it its 64 -- neither is a
    reader, and a rule that flagged them could only reach zero by exempting ThemeManager, i.e. by
    pardoning the file it should watch. And the fix for this very defect left a comment naming
    `sideRail_->width()` three lines above the code that no longer calls it, so a rule that did not
    blank comments would report its own citation forever.
    """
    probe = "\n".join([
        "void MainWindow::a() { const int w = sideRail_->width(); }",           # 1  the defect
        "void MainWindow::b() { const int h = sideRail_->height(); }",          # 2  its twin
        "void MainWindow::c() { const int r = sideRail_->geometry().right(); }",# 3  position, not extent
        "void MainWindow::d() { const QSize s = sideRail_->size(); }",          # 4  extent, indirectly
        "void MainWindow::e() { int n = tm.chrome(ThemeManager::Chrome::ModeRailWidth); }",  # 5
        "void MainWindow::f() { int n = chrome(Chrome::RailBarHeight); }",      # 6
        "// it used to read sideRail_->width() here -- the fix's own comment",  # 7  not a read
        "/* chrome(Chrome::ModeRailWidth) in a block comment */",               # 8  not a read
        "    case Chrome::ModeRailWidth:   return 64;",                         # 9  the definition
        "        ModeRailWidth,        // the vertical rail's width",           # 10 the declaration
        "void MainWindow::g() { sideRail_->setVisible(!sideRail_->isVisible()); }",   # 11 not geometry
        "void MainWindow::h() { const QPoint o = sideRail_->contentOrigin(); }",      # 12 the answer
    ])
    caught = [(v.line, v.key) for v in
              rules._check_shell_geometry_through_the_layout(Path("qt_ui/Probe.cpp"), probe)]
    assert caught == [
        (1, "MainWindow::a:sideRail_->width()"),
        (2, "MainWindow::b:sideRail_->height()"),
        (3, "MainWindow::c:sideRail_->geometry()"),
        (4, "MainWindow::d:sideRail_->size()"),
        (5, "MainWindow::e:chrome(ThemeManager::Chrome::ModeRailWidth)"),
        (6, "MainWindow::f:chrome(Chrome::RailBarHeight)"),
    ], caught


def test_the_shell_geometry_rule_lets_the_shell_measure_its_own_rail():
    """The scope, proved from both sides in one call. The SAME text is silent under a shell path and
    loud under any other -- so the exception is the owning package and not, as a rule that quietly
    matched nothing would be, everything."""
    probe = "void SideRail::applyOrientation() { setFixedWidth(sideRail_->width()); }"
    inside = rules._check_shell_geometry_through_the_layout(Path("qt_ui/shell/SideRail.cpp"), probe)
    outside = rules._check_shell_geometry_through_the_layout(Path("qt_ui/MainWindow.cpp"), probe)
    assert inside == [], inside
    assert [v.line for v in outside] == [1], outside


def test_the_layout_switch_rule_fires_on_the_rebuild_it_forbids():
    """`layout-switch-is-not-a-rebuild` ships at zero, and a zero is worth exactly its coverage.

    The first five lines are the rebuild, spelled five ways, all inside `applyShellLayout`'s own
    braces. Every one of them costs the user what they had typed into the page, and none of them
    errors -- the window simply comes back empty, which reads as a glitch.

    The rest is the counterweight, and it is the half that decides whether the rule means anything.
    A rule scoped to one function has to be silent on the SAME text in another function, or its
    scope is a claim rather than a property: the neighbours below construct, delete and clear pages
    legitimately, which is what `ensureGenerationPageBuilt` and `buildPages` are FOR. The comment
    inside the body is there because this function's own comment names `deleteLater` while
    explaining why it does not call it, and a rule that could not tell those apart would report its
    own citation forever. The last line is the shape the rule has to walk past to reach the body at
    all: a CALL to applyShellLayout, in a function full of exactly the words it forbids.
    """
    probe = "\n".join([
        "void MainWindow::applyShellLayout(Layout layout)",                          # 1
        "{",                                                                         # 2
        "    pageStack_->removeWidget(pageStack_->currentWidget());",                 # 3  FIRE
        "    t2iPage_->deleteLater();",                                              # 4  FIRE
        "    delete i2iPage_;",                                                      # 5  FIRE
        "    pageStack_->clear();",                                                  # 6  FIRE
        "    t2iPage_ = new ImageGenerationPage(mode, this);",                       # 7  FIRE
        "    // it must never deleteLater() a page or call pageStack_->clear()",     # 8  comment
        '    appendLogLine(QStringLiteral("} delete everything"));',                 # 9  a literal
        "    sideRail_->setOrientation(Qt::Horizontal);",                            # 10 the real work
        "}",                                                                         # 11
        "void MainWindow::ensureGenerationPageBuilt(const QString &modeId)",         # 12
        "{",                                                                         # 13
        "    t2vPage_ = new ImageGenerationPage(mode, this);",                       # 14 legitimate
        "    pageStack_->removeWidget(old);",                                        # 15 legitimate
        "    old->deleteLater();",                                                   # 16 legitimate
        "    applyShellLayout(ShellLayout::instance().layout());",                   # 17 a CALL
        "}",                                                                         # 18
    ])
    caught = [(v.line, v.key) for v in
              rules._check_layout_switch_is_not_a_rebuild(Path("qt_ui/MainWindow.cpp"), probe)]
    assert caught == [
        (3, "applyShellLayout:removeWidget("),
        (4, "applyShellLayout:deleteLater("),
        (5, "applyShellLayout:delete i"),
        (6, "applyShellLayout:pageStack_->clear("),
        (7, "applyShellLayout:new ImageGenerationPage"),
    ], caught


def test_the_layout_switch_rule_is_not_confused_by_a_brace_in_a_string():
    """A `"}"` inside a message must not close the function early -- if it did, everything after it
    would be scanned as though it were outside the body, and the rule would go quiet exactly when
    somebody added a log line. Same body twice; only the literal differs."""
    body = ["void MainWindow::applyShellLayout(Layout layout)", "{",
            '    appendLogLine(QStringLiteral("{ unbalanced"));',
            "    pageStack_->clear();", "}"]
    caught = [v.line for v in
              rules._check_layout_switch_is_not_a_rebuild(Path("qt_ui/MainWindow.cpp"),
                                                          "\n".join(body))]
    assert caught == [4], caught


def test_the_blocking_wait_rule_reports_at_the_planted_line():
    """Five APIs, not dataflow. A comment, a string, and a similarly named function stay silent."""
    probe = "\n".join([
        "socket.waitForConnected(350);",
        "process.waitForFinished(2000);",
        "socket.waitForReadyRead(100);",
        "socket.waitForBytesWritten(50);",
        "process.waitForStarted(5000);",
        "// process.waitForFinished(1);",
        'QString msg("waitForFinished(");',
        "waitForSomethingElse();",
    ])
    caught = [v.line for v in rules._check_blocking_wait(Path("qt_ui/Probe.cpp"), probe)]
    assert caught == [1, 2, 3, 4, 5], caught


def test_reachability_resolves_a_relative_import_from_a_packages_own_init():
    """`_import_edges` got `node.level` right and its caller wrong.

    `_module_name` reduces `model_intelligence/__init__.py` to `"model_intelligence"` -- a name
    with NO DOT in it. `_import_edges` used to derive the owning package with
    `name.rsplit(".", 1)[0] if "." in name else ""`, which fell to the empty-string branch for
    exactly that name. `level == 1` inside a package's own `__init__.py` means the package
    ITSELF (`from .hashing import x` -> `pkg.hashing`), not its parent, so `pkg=""` turned the
    edge into `.hashing` -- a leading-dot string matching no module in the graph -- and the real
    target was silently dropped. A module reached only through a relative import from its
    package's `__init__.py` read as unreachable, and the rule's count was never the true count:
    an entire import form was invisible to it while it kept reporting green.

    Two trees, same source text (`from .hashing import thing`), told apart only by `is_package`
    -- the fact `_module_name` already threw away and the caller now has to hand back in:
    `pkg/__init__.py`'s edge must land on `pkg.hashing`, and `pkg/mod.py`'s edge (the case the
    first fix already got right) must still land on `pkg.hashing` too, not on `pkg.mod`'s own
    non-existent sibling package.
    """
    tree = ast.parse("from .hashing import thing\n")

    init_edges = rules._import_edges("model_intelligence", tree, is_package=True)
    assert "model_intelligence.hashing" in init_edges, init_edges
    assert not any(e.startswith(".") for e in init_edges), init_edges

    sibling_edges = rules._import_edges("model_intelligence.other", tree, is_package=False)
    assert "model_intelligence.hashing" in sibling_edges, sibling_edges

    nested_init_edges = rules._import_edges("model_intelligence.sub", tree, is_package=True)
    assert "model_intelligence.sub.hashing" in nested_init_edges, nested_init_edges


def test_the_progress_floor_rule_reports_at_the_planted_line():
    """minimumProgressForRank( is the floor. A comment and a different name stay silent."""
    probe = "\n".join([
        "int x = minimumProgressForRank(3);",
        "// minimumProgressForRank(1);",
        "int y = maximumProgressForRank(3);",
        "progress = job.activeProgress;",
    ])
    caught = [v.line for v in rules._check_progress_not_invented(Path("qt_ui/Probe.cpp"), probe)]
    assert caught == [1], caught
def test_the_sampling_rule_sees_all_three_forms_of_the_function_it_is_named_after():
    """Plan Task 7 Step 3's self-test, written the way `_import_edges`' regression test was.

    The rule guards a DELETION: applyOptimalVideoSamplingDefaults' wan/ltx/flux3 blocks, which held
    sampling numbers duplicating the operating-point table and had already drifted from it. It
    shipped matching spin-box `setValue` only -- so of the three forms that function used, it saw
    the numbers and was blind to the CANVAS and to the SAMPLER, both of which its own citation
    names. The final review planted exactly that function's shape and scored zero violations.

    This is the plant, held in place. Line 1 is the canvas; line 4 is a literal sampler pushed into
    a video sampler combo; line 5 is a number the rule already caught.
    """
    probe = "\n".join([
        'widthSpin_->setValue(832);',
        'heightSpin_->setValue(480);',
        'frameCountSpin_->setValue(49);',
        'selectComboValue(sampling_->videoSamplerCombo(), QStringLiteral("uni_pc"));',
        'sampling_->cfgSpin()->setValue(5.0);',
    ])
    caught = [v.line for v in rules._check_sampling_defaults_are_data(Path("qt_ui/Probe.cpp"), probe)]
    assert caught == [1, 2, 3, 4, 5], caught


def test_the_sampling_rule_still_ignores_a_value_it_was_handed():
    """LITERALS ONLY, and this is the half that keeps the rule usable.

    The correct implementation -- the one this whole wave exists to produce -- writes what the
    resolver answered. If the widened rule flagged that, it would be widened back by exemption
    until it measured nothing, which is the failure mode the exemptions module was written about.
    A comment, a sampler read from a variable, and an unrelated spin box all stay silent.
    """
    probe = "\n".join([
        'widthSpin_->setValue(width.toInt());',
        'heightSpin_->setValue(values.value("height").toInt());',
        'selectComboValue(samplerTarget, sampler);',
        'selectComboValue(sampling_->videoSamplerCombo(), resolved);',
        '// widthSpin_->setValue(832);',
        'selectComboValue(workflowCombo_, QStringLiteral("Default Canvas"));',
        'denoiseSpin_->setValue(0.55);',
    ])
    caught = [v.line for v in rules._check_sampling_defaults_are_data(Path("qt_ui/Probe.cpp"), probe)]
    assert caught == [], caught


def test_the_watched_fields_rule_fires_on_a_write_with_no_watcher():
    """`highNoiseStepsSpin_` was written by applyResolvedSettings and watched by nothing, so a
    hand-set 20/8 MoE split was reset to 14/14 on the next Simple/Advanced toggle -- while the
    ledger recorded ruling W2-E3 ("one flag per field the wave writes") as satisfied.

    The two bodies are paired here rather than compared to a list, so the next field added to the
    applier cannot repeat it. `sampling_->stepsSpin()` is the case that first made this rule lie: an
    earlier alternation matched the `sampling_` in it and reported steps and CFG -- watched since
    the day the function was written -- as unwatched.
    """
    probe = "\n".join([
        "void ImageGenerationPage::watchForUserEdits()",
        "{",
        "    watchSpin(widthSpin_, ResolvedField::Width);",
        "    watchSpin(sampling_->stepsSpin(), ResolvedField::Steps);",
        "    watchDouble(sampling_->cfgSpin(), ResolvedField::Cfg);",
        "}",
        "",
        "void ImageGenerationPage::applyResolvedSettings(const QJsonObject &values)",
        "{",
        "    widthSpin_->setValue(w);",
        "    sampling_->stepsSpin()->setValue(s);",
        "    sampling_->cfgSpin()->setValue(c);",
        "    highNoiseStepsSpin_->setValue(half);",
        "    lowNoiseStepsSpin_->setValue(half);",
        "}",
    ])
    found = rules._check_resolved_fields_are_watched(Path("qt_ui/Probe.cpp"), probe)
    assert [v.line for v in found] == [13, 14], [(v.line, v.key) for v in found]
    assert {v.key for v in found} == {
        "applyResolvedSettings:highNoiseStepsSpin_",
        "applyResolvedSettings:lowNoiseStepsSpin_",
    }


def test_the_watched_fields_rule_is_silent_when_every_write_is_watched():
    probe = "\n".join([
        "void ImageGenerationPage::watchForUserEdits()",
        "{",
        "    watchSpin(widthSpin_, ResolvedField::Width);",
        "    watchSpin(highNoiseStepsSpin_, ResolvedField::SplitSteps);",
        "}",
        "",
        "void ImageGenerationPage::applyResolvedSettings(const QJsonObject &values)",
        "{",
        "    widthSpin_->setValue(w);",
        "    highNoiseStepsSpin_->setValue(half);",
        "}",
    ])
    assert rules._check_resolved_fields_are_watched(Path("qt_ui/Probe.cpp"), probe) == []


def test_the_watched_fields_rule_says_nothing_about_a_file_with_no_applier():
    """Most of qt_ui has neither function. A rule that reported every other file as missing a
    watcher would be noise with a baseline, which is the shape of a ratchet nobody reads."""
    assert rules._check_resolved_fields_are_watched(
        Path("qt_ui/Probe.cpp"), "void Other::thing() { spin_->setValue(3); }") == []


def test_the_argv_rule_fires_on_a_dict_with_no_arm():
    """W3 Task 1's self-test -- required, not optional: W2 shipped a ratchet whose self-test was
    never written and the final review caught it.

    generation_time_sec with no optimizations beside it is the exact shape of the defect the rule
    exists to catch: job_archive.json's third, unlabelled sage arm at 159.27s, discovered only
    because a human happened to notice it -- nothing structural would have.
    """
    probe = "\n".join([
        "def build_payload():",
        "    return {",
        '        "ok": True,',
        '        "generation_time_sec": round(elapsed, 2),',
        '        "steps_per_sec": round(steps_per_sec, 2),',
        "    }",
    ])
    found = rules._check_argv_named(Path("python/probe.py"), probe)
    assert [v.line for v in found] == [2], [(v.line, v.key) for v in found]
    assert found[0].key == "build_payload"


def test_the_argv_rule_is_silent_when_the_arm_is_recorded():
    probe = "\n".join([
        "def build_payload():",
        "    return {",
        '        "generation_time_sec": round(elapsed, 2),',
        '        "optimizations": _optimizations_block(req),',
        "    }",
    ])
    assert rules._check_argv_named(Path("python/probe.py"), probe) == []


def test_the_argv_rule_says_nothing_about_a_dict_with_no_seconds():
    """A rule that fired on every dict literal would be noise, not a ratchet."""
    probe = "def other():\n    return {\"ok\": True, \"cache_hit\": False}\n"
    assert rules._check_argv_named(Path("python/probe.py"), probe) == []


def test_the_one_resolver_rule_fires_on_the_filename_guess_it_was_written_from():
    """W4 Task 1's self-test -- required, not optional: W2 shipped a ratchet whose self-test was
    never written and the final review caught it.

    This is `HomePage::inferModeFromWorkflowProfile`, restored verbatim. It read the workflow's own
    task keys, then -- when they said nothing -- looked for "i2v"/"t2v"/"i2i"/"t2i" as SUBSTRINGS OF
    THE FILE PATH, and then returned t2i regardless. A workflow whose classification failed therefore
    opened a cockpit chosen by its filename, holding a graph that does not belong there, and nothing
    told the user: the page just looked wrong.

    Checked against the real deleted function too, not only this probe -- run over `git show
    HEAD~1:qt_ui/HomePage.cpp` it reports lines 128 and 156, which are the two it was written for.
    """
    probe = "\n".join([
        "QString inferModeFromWorkflowProfile(const QJsonObject &profile)",
        "{",
        '    const QString directTask = normalizedModeId(profile.value(QStringLiteral("task_command")).toString());',
        "    if (!directTask.isEmpty())",
        "        return directTask;",
        '    const QString mediaType = profile.value(QStringLiteral("media_type")).toString();',
        '    if (mediaType == QStringLiteral("video"))',
        '        return QStringLiteral("t2v");',
        '    const QString workflowPath = profile.value(QStringLiteral("workflow_path")).toString().toLower();',
        '    for (const QString &candidate : {QStringLiteral("i2v"), QStringLiteral("t2i")})',
        "    {",
        "        if (workflowPath.contains(candidate))",
        "            return candidate;",
        "    }",
        '    return QStringLiteral("t2i");',
        "}",
    ])
    found = rules._check_one_workflow_mode_resolver(sources.ROOT / "qt_ui" / "Probe.cpp", probe)
    assert [v.line for v in found] == [1], [(v.line, v.key) for v in found]
    assert found[0].key == "inferModeFromWorkflowProfile"
    assert "t2i" in found[0].detail and "t2v" in found[0].detail, found[0].detail


def test_the_one_resolver_rule_fires_on_a_derivation_that_spells_no_mode_at_all():
    """The second of the three merged resolvers looked nothing like the first.

    `WorkflowLibraryPage::loadWorkflowRecord` named no mode anywhere -- it read the classification
    keys straight into `record.modeId` through a normaliser. The literal-only half of this rule
    scored ZERO on that file, which is exactly the "a plant of the defect's own shape scores zero"
    result the sampling rule was widened for. So the rule has two halves, and this is the second.
    """
    probe = "\n".join([
        "WorkflowRecord WorkflowLibraryPage::loadWorkflowRecord(const QString &profilePath)",
        "{",
        "    WorkflowRecord record;",
        "    record.modeId = normalizedModeId(safeObjectString(object, {",
        '        QStringLiteral("mode_id"),',
        '        QStringLiteral("task_command")',
        "    }));",
        "    return record;",
        "}",
    ])
    found = rules._check_one_workflow_mode_resolver(sources.ROOT / "qt_ui" / "Probe.cpp", probe)
    assert [v.line for v in found] == [1], [(v.line, v.key) for v in found]
    assert "record.modeId" in found[0].detail, found[0].detail


def test_the_one_resolver_rule_is_silent_on_carrying_a_mode_it_did_not_decide():
    """The false-positive counterweight, and the reason the rule is written this narrowly.

    Writing a mode OUT under a classification key, and COMPARING against one, are things dozens of
    sites in qt_ui legitimately do -- the launch request builder, isImageMode, the rail specs. A rule
    that flagged them would be exempted until it measured nothing, which is the shape of a ratchet
    nobody reads.
    """
    probe = "\n".join([
        "QJsonObject buildLaunchRequest(const WorkflowRecord &record)",
        "{",
        "    QJsonObject request;",
        '    request.insert(QStringLiteral("workflow_task_command"), record.modeId);',
        '    request.insert(QStringLiteral("task_command"), record.modeId);',
        '    if (normalizedModeId(record.modeId) != QStringLiteral("v2v"))',
        '        request.insert(QStringLiteral("draftable"), true);',
        "    return request;",
        "}",
    ])
    assert rules._check_one_workflow_mode_resolver(sources.ROOT / "qt_ui" / "Probe.cpp", probe) == []


def test_the_one_resolver_rule_says_nothing_about_a_function_that_never_asks():
    """Most of qt_ui names no classification key at all. A rule that reported every function holding
    a mode string would be noise with a baseline."""
    probe = "\n".join([
        "void MainWindow::switchToMode(const QString &modeId)",
        "{",
        '    if (modeId == QStringLiteral("t2i"))',
        '        currentModeId_ = QStringLiteral("t2i");',
        "}",
    ])
    assert rules._check_one_workflow_mode_resolver(sources.ROOT / "qt_ui" / "Probe.cpp", probe) == []


def test_the_one_resolver_rule_exempts_only_the_resolver_itself():
    """The owner is allowed to derive a mode -- that is what it is for -- and nothing else is. The
    owner is named in sources.py, not here, for the same reason no rule may name a file."""
    probe = "\n".join([
        "QString derive(const QJsonObject &source)",
        "{",
        '    if (!source.value(QStringLiteral("inferred_task_command")).toString().isEmpty())',
        '        return QStringLiteral("i2v");',
        '    return QStringLiteral("t2i");',
        "}",
    ])
    owner = sources.ROOT / "qt_ui" / "workflows" / (sources.WORKFLOW_MODE_RESOLVER + ".cpp")
    assert rules._check_one_workflow_mode_resolver(owner, probe) == []
    assert rules._check_one_workflow_mode_resolver(sources.ROOT / "qt_ui" / "Probe.cpp", probe)


def test_the_one_resolver_rule_is_at_zero_and_stays_there(findings):
    """No baseline, and it did not need one: all four live sites were routed through the resolver
    rather than exempted. Three were the resolvers the wave set out to merge; the fourth --
    OutputCardModel::buildOutput, which labelled a gallery card by "it is a video file, therefore
    t2v" -- the rule found, and nothing else had."""
    assert findings["one-workflow-mode-resolver"] == [], "\n".join(
        str(v) for v in findings["one-workflow-mode-resolver"])
