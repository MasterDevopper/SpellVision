"""The documents that describe the tree have to describe the tree that exists.

Five documents in this repository are written in the present tense about the current code:
`CLAUDE.md`, `README.md`, `ARCHITECTURE.md`, Doc 50 (the build standard) and Doc 53 (the audit).
Everything else under `docs/` is historical intent, and `CLAUDE.md` 8 says so explicitly -- sweeping
those would report drift that is not drift.

Measured before this rule shipped, and the pair is the point:

* A naive rule -- every backticked string that looks path-shaped -- reported **28 across 218
  references**. Most were false: globs (`scripts/dev/*.ps1`), QSettings keys
  (`appearance/themePreset`), bare extensions (`.cpp`), a git ref (`origin/main`), a sampler pair
  (`dpmpp_2m/karras`).
* Scoped to a **file** the document names -- a token ending in a source extension, no glob
  characters -- it reported **8 across 161**, of which **4 were real** and 4 are the deliberate
  mentions listed in `EXEMPT` below.

That is the same shape as the `wire-types-registered` over-count recorded in Doc 53 5: a rule that
flags 30 where 10 are real is not a rule yet.

The four real ones were all in `ARCHITECTURE.md`'s module table, and all four were modules the
consistency pass had **deleted**: `python/video/t2v_worker.py`, `python/video/i2v_worker.py`,
`gpu_info.py` and `workflow_profile_registry.py`. The map still routed a reader to code that no
longer existed, four passes after it stopped existing. This is the audit's own subject applied to
its own documents: the rule was known, it was applied where the defect was found, and nothing
carried it to the second site.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.ratchet

ROOT = Path(__file__).resolve().parents[1]

# Present-tense documents only. A sprint README describes what was true during that sprint.
GOVERNING_DOCS = (
    "CLAUDE.md",
    "README.md",
    "ARCHITECTURE.md",
    "docs/design/50_feature_build_standard.md",
    "docs/design/53_consistency_and_robustness_audit.md",
)

# A source file, not a path-shaped string.
SOURCE_EXTENSIONS = (".py", ".cpp", ".h", ".ps1", ".yml", ".ini", ".qss")
BACKTICKED = re.compile(r"`([^`\n]+)`")

# Keyed by (document, token), valued by a REASON -- never a boolean. A boolean records that someone
# silenced the rule; a reason records why the mention is correct. Doc 53 7 has the argument.
EXEMPT: dict[tuple[str, str], str] = {
    ("CLAUDE.md", "workflow_profile_registry.py"): (
        "Records the Phase 4a deletion. The sentence exists BECAUSE the file does not."
    ),
    ("CLAUDE.md", "CMakeCache.txt"): (
        "A generated build artifact under build/, never tracked. The mention is a rebuild hazard "
        "(the wrong generator corrupts it), not a claim that the file is in the tree."
    ),
    ("docs/design/53_consistency_and_robustness_audit.md", "runtime_adapters/diffusers_adapter.py"): (
        "Names the package the pass deleted, as the evidence that a live rule was reporting a pass "
        "on unreachable code."
    ),
    ("docs/design/53_consistency_and_robustness_audit.md", "prompt.txt"): (
        "Written beside an output at runtime by buildWorkerGenerationRequest. Not a repo file."
    ),
    # 7g names the four modules that were on the map after being deleted. The first thing this rule
    # caught was the section announcing it, which is the correct behaviour and a good illustration:
    # naming an absent file is a defect in a MAP and the content of a RECORD, and only a reason can
    # tell those apart.
    ("docs/design/53_consistency_and_robustness_audit.md", "python/video/t2v_worker.py"): (
        "7g -- the deleted module ARCHITECTURE.md was still routing readers to."
    ),
    ("docs/design/53_consistency_and_robustness_audit.md", "i2v_worker.py"): (
        "7g -- as above; the whole python/video/ package is gone."
    ),
    ("docs/design/53_consistency_and_robustness_audit.md", "gpu_info.py"): (
        "7g -- deleted in Phase 4a, and this document records deleting it."
    ),
    ("docs/design/53_consistency_and_robustness_audit.md", "workflow_profile_registry.py"): (
        "7g -- deleted in Phase 4a as a second workflow-profile store nothing imported."
    ),
}


def _tracked_files() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return {line.replace("\\", "/") for line in out.split()}


TRACKED = _tracked_files()
BASENAMES = {path.rsplit("/", 1)[-1] for path in TRACKED}


def _is_named_file(token: str) -> bool:
    if any(ch in token for ch in "*{}(), "):
        return False
    if token.startswith(("http", "$", "-", ".")):
        return False
    if re.match(r"^[A-Za-z]:", token):  # a machine path is rule R8's subject, not this one
        return False
    return token.endswith(SOURCE_EXTENSIONS)


def _resolves(token: str) -> bool:
    token = token.replace("\\", "/")
    if token in TRACKED or (ROOT / token).exists():
        return True
    # A document may name a module by basename ("`worker_tcp.py` dispatches"). That is a real
    # reference and it resolves as long as exactly that file exists somewhere in the tree.
    return token.rsplit("/", 1)[-1] in BASENAMES


def _references(doc: str) -> list[tuple[int, str]]:
    text = (ROOT / doc).read_text(encoding="utf-8", errors="replace")
    found = []
    for match in BACKTICKED.finditer(text):
        token = match.group(1)
        if _is_named_file(token):
            found.append((text.count("\n", 0, match.start()) + 1, token))
    return found


# --- the rule --------------------------------------------------------------------------------


@pytest.mark.parametrize("doc", GOVERNING_DOCS)
def test_every_file_a_governing_document_names_exists(doc: str) -> None:
    """A map that routes a reader to a deleted module is worse than a gap in the map: the gap makes
    the reader look, and the wrong entry makes them conclude."""
    assert (ROOT / doc).exists(), f"{doc} is itself a governing document that does not exist"

    stale = [
        f"{doc}:{line}  {token}"
        for line, token in _references(doc)
        if not _resolves(token) and (doc, token) not in EXEMPT
    ]
    assert not stale, (
        "these documents name source files that are not in the tree:\n  "
        + "\n  ".join(stale)
        + "\n\nEither fix the document or add the reference to EXEMPT with the reason it is correct."
    )


def test_no_exemption_outlives_its_mention() -> None:
    """An exemption list nobody prunes becomes a list of rules that no longer apply.

    Each entry has to still be a live mention in its document; when the sentence goes, so does the
    exemption, rather than sitting there granting silence to whatever text arrives next.
    """
    dead = []
    for (doc, token), reason in EXEMPT.items():
        assert reason.strip(), f"{doc}:{token} is exempt for no stated reason"
        if token not in (ROOT / doc).read_text(encoding="utf-8", errors="replace"):
            dead.append(f"{doc}  {token}")
    assert not dead, f"EXEMPT entries whose document no longer mentions them: {dead}"


def test_the_published_artifact_states_the_current_counts() -> None:
    """The HTML artifact beside Doc 53 is a *designed summary*, not a mirror, so it is not held to
    the document's prose. But it carries a dated "since the pass" block of live counts, and those
    are exactly the claims that go stale: it read "14 sweep rules" and "6 C++ tests" while the tree
    had 18 and 17, and "No CI" two days after CI landed.

    Deriving the numbers here means adding a rule or a ctest target tells you the artifact needs a
    line, rather than the artifact quietly describing a smaller repository than the one that exists.
    """
    import sys

    sys.path.insert(0, str(ROOT / "tests"))
    from sweeps import exemptions, rules  # noqa: PLC0415

    html = (ROOT / "docs" / "design" / "53_consistency_and_robustness_audit.html").read_text(
        encoding="utf-8"
    )
    block = html.split("Since the pass")[-1].split("</div>")[0]

    ctest_targets = len(
        re.findall(r"add_test\(NAME", (ROOT / "CMakeLists.txt").read_text(encoding="utf-8"))
    )
    at_zero = sum(
        1 for rule in rules.ALL_RULES if not sum(exemptions.baseline_for(rule.name).values())
    )

    # Test FILES rather than test cases. The case count moves with every parametrisation and a
    # number that must be edited on every commit gets edited without being read; the file count is
    # stable, derivable in one glob, and still catches an artifact describing a smaller repository
    # than the one that exists.
    test_files = len(list((ROOT / "tests").glob("test_*.py")))

    # Each number is matched WITH THE WORDS AROUND IT, not anywhere in the block.
    #
    # The first version searched the block for the bare value, and it passed for the wrong reason
    # the moment two claims shared a number: the artifact said "18 C++ tests" while the tree had 19,
    # and the check was satisfied by the "19 sweep rules" sitting two lines away. A ratchet that can
    # be satisfied by a different sentence is not measuring the sentence it names -- which is the
    # same defect, one level up, as the rules this file exists to enforce.
    for label, value, tail in (
        ("sweep rules", len(rules.ALL_RULES), r"\s*(?:</span>)?\s*sweep rules"),
        ("C++ ctest targets", ctest_targets, r"\s*(?:</span>)?\s*C\+\+ tests"),
        ("rules at zero", at_zero, r"\s*at zero"),
        ("baseline total", exemptions.total_baseline(), r"\s*(?:</span>)?\s*\.?\s*$|\s*\."),
        ("Python test files", test_files, r"\s*(?:</span>)?\s*files"),
    ):
        pattern = rf"(?<!\d){value}(?!\d){tail}"
        assert re.search(pattern, block, re.MULTILINE), (
            f"the artifact's since-the-pass block does not state the live {label} ({value}) "
            f"next to the words that name it. "
            "Update docs/design/53_consistency_and_robustness_audit.html."
        )


def test_the_safety_net_entry_points_the_map_names_are_real() -> None:
    """`ARCHITECTURE.md` tells a newcomer how the guarantees run. Those two files are the whole
    answer -- one for the machine, one for the commit -- and a map that names a lane which is not
    wired is how "we have CI" survives having none."""
    ci = ROOT / ".github" / "workflows" / "ci.yml"
    hook = ROOT / ".githooks" / "pre-commit"
    assert ci.exists(), "ARCHITECTURE.md documents a CI lane; .github/workflows/ci.yml is missing"
    assert hook.exists(), "ARCHITECTURE.md documents a pre-commit hook; .githooks/pre-commit is missing"

    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    for named in (".github/workflows/ci.yml", ".githooks/pre-commit"):
        assert named in architecture, (
            f"ARCHITECTURE.md does not name {named}. The map has to point at the lane, or the lane "
            "is something a reader has to already know about to find."
        )
