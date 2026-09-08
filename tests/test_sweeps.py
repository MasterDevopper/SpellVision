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
