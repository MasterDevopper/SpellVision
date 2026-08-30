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
    with capsys.disabled():
        print("\n--- sweep baseline ---")
        for rule in rules.ALL_RULES:
            total = sum(exemptions.baseline_for(rule.name).values())
            print(f"  {rule.name:20s} {total:4d} known")
        print(f"  {'TOTAL':20s} {exemptions.total_baseline():4d}")
