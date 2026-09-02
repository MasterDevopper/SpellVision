"""NOTICE exists, covers what actually ships, and cannot quietly lose an open question.

Doc 28 section 2 asserts "NOTICE — Aggregate third-party attributions shipped". There was no NOTICE
file in the tree at all, which is the failure shape Doc 50's governing observation describes: an
absent attribution file reports the same thing as a complete one — nothing — right up to the point
where a recipient asks.

Writing one is not the fix. A NOTICE is a document about a payload, and a document about a payload
goes stale the moment the payload moves; that is the mechanism behind eleven of the twenty findings
in the 2026-08-30 audit. So every assertion here that CAN be derived from the tree is derived from
the tree — the Qt version comes out of the launcher, the libwebp tag out of CMakeLists, the payload
classes out of Doc 28 section 5 itself, and the "no fonts ship" claim is checked against the tree
rather than believed.

The two properties that matter most are the last two:

* an ``UNDETERMINED`` marker cannot be dropped from the summary while it still stands in the body,
  or vice versa. An open licence question that falls out of the summary looks exactly like one that
  was answered.
* the file cannot contain placeholder text. "Aggregate third-party attributions shipped" is a gate
  a stub satisfies, and a stub is the confident-wrongness failure applied to a legal document.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from sweeps import sources  # noqa: E402

pytestmark = pytest.mark.ratchet

NOTICE = ROOT / "NOTICE"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def notice() -> str:
    assert NOTICE.exists(), (
        "there is no NOTICE file. Doc 28 section 2 requires aggregate third-party attributions to "
        "ship; Qt is LGPL, ComfyUI is GPL-3.0, and libwebp is linked into the binary."
    )
    return NOTICE.read_text(encoding="utf-8", errors="replace")


# --- it exists, and it is not a stub ---------------------------------------------------------------


def test_the_notice_is_substantial() -> None:
    body = notice()
    assert len(body.strip()) > 4000, (
        f"NOTICE is {len(body.strip())} characters -- too short to describe a payload that carries "
        f"Qt, ComfyUI, libwebp, two Python environments and pinned node packs"
    )


def test_the_notice_has_no_placeholder_text() -> None:
    """A gate that reads "attributions shipped" is satisfied by a file named NOTICE. It must not be
    satisfiable by a file that says TODO."""
    body = notice()
    for placeholder in ("TODO", "TBD", "FIXME", "XXX", "lorem ipsum", "<insert", "PLACEHOLDER"):
        assert placeholder.lower() not in body.lower(), f"NOTICE contains placeholder text: {placeholder!r}"


# --- it covers every class the payload contains ----------------------------------------------------


def test_the_notice_covers_every_payload_class_doc_28_names() -> None:
    """The payload classes are read out of Doc 28 section 5 rather than listed here, so a change to
    what ships fails this test instead of silently outdating the file."""
    doc = _read("docs/design/28_release_readiness_checklist.md")
    ships = re.search(r"\*\*Ships with the installer \(engines\):\*\*(.*?)\*\*Does not ship",
                      doc, re.S)
    assert ships, "Doc 28 section 5's payload list has moved -- this test can no longer derive it"
    bullets = [b.strip() for b in re.findall(r"^- (.+)$", ships.group(1), re.MULTILINE)]
    assert len(bullets) >= 4, bullets

    body = notice()
    # One representative token per payload class, chosen from the bullet itself.
    for bullet, token in (
        ("Qt runtime", "Qt 6."),
        ("project venv", "worker's project venv"),
        ("Isolated ComfyUI venv", "isolated ComfyUI venv"),
        ("Custom-node packs", "custom-node pack"),
    ):
        assert any(bullet.split()[0].strip("`") in b for b in bullets), (
            f"Doc 28 section 5 no longer mentions {bullet!r}; the payload changed"
        )
        assert token.lower() in body.lower(), f"NOTICE says nothing about the payload class {bullet!r}"


def test_the_notice_names_the_qt_version_the_build_actually_uses() -> None:
    """Derived from the launcher, not typed twice. A NOTICE naming a Qt version the build no longer
    uses is worse than none: it is a false statement about what was conveyed."""
    launcher = _read("scripts/dev/rebuild_ui.ps1")
    version = re.search(r"C:\\Qt\\(\d+\.\d+\.\d+)\\", launcher).group(1)
    assert f"Qt {version}" in notice(), f"NOTICE does not name Qt {version}"


def test_the_notice_names_the_libwebp_tag_cmake_pins() -> None:
    """libwebp is STATICALLY linked into SpellVision.exe -- the one third party that is genuinely
    inside the binary -- so its BSD-3-Clause notice is not optional."""
    cmake = _read("CMakeLists.txt")
    tag = re.search(r"GIT_TAG\s+(v[\d.]+)", cmake).group(1)
    body = notice()
    assert tag.lstrip("v") in body, f"NOTICE does not name the pinned libwebp {tag}"
    assert "BSD-3-Clause" in body


def test_the_notice_records_the_qt_relinking_obligation() -> None:
    """Doc 28 section 2's copyleft gate asks for "process-separation vs linking recorded". For Qt
    the obligation is relinking: LGPL conveys it on the condition a recipient can replace the
    libraries. That is a constraint on how the app is packaged, so it has to be written down where
    whoever packages it will read it."""
    body = notice()
    # Scoped to the Qt section. The first version searched the whole file and stayed green when the
    # "must not be statically linked" line was deleted, because libwebp's section says "statically
    # linked" about itself -- a rule reading the wrong span, reporting a pass it had not earned.
    qt = body[body.index("1. Qt 6."):body.index("2. libwebp")]
    assert "LGPL" in qt
    assert re.search(r"relink", qt, re.IGNORECASE), "the LGPL relinking obligation is not recorded"
    assert re.search(r"must not be statically linked", qt, re.IGNORECASE), (
        "NOTICE does not say Qt must not be statically linked -- the one packaging change that "
        "would break the obligation"
    )
    assert re.search(r"replace", qt, re.IGNORECASE), (
        "NOTICE does not say the Qt libraries must remain replaceable, which is what relinking means"
    )


def test_the_notice_records_how_comfyui_is_reached() -> None:
    """ComfyUI is GPL-3.0 and SpellVision is Apache-2.0. Whether that is a problem depends entirely
    on process separation vs linking, which is exactly what Doc 28 section 2 asks to be recorded."""
    body = notice()
    assert "GPL-3.0" in body
    assert re.search(r"process separation", body, re.IGNORECASE)


# --- what does NOT ship is stated, and checked against the tree ------------------------------------


def test_the_notice_says_model_weights_are_not_bundled() -> None:
    """Doc 28 section 5 puts weights in the "does not ship" column. Saying so explicitly is what
    keeps this file from being expected to enumerate model licences it has no business carrying --
    those are surfaced per family in the app instead."""
    body = notice()
    assert re.search(r"model weights are not bundled", body, re.IGNORECASE)
    doc = _read("docs/design/28_release_readiness_checklist.md")
    assert "Family checkpoints, VAEs, text encoders, clip-vision, LoRAs" in doc, (
        "Doc 28 section 5's 'does not ship' list changed -- re-check what NOTICE claims"
    )


def test_the_font_claim_matches_the_tree() -> None:
    """NOTICE states that no font file ships. That is a claim about the repository, so it is checked
    against the repository: the day someone adds a .ttf, this fails rather than the NOTICE quietly
    becoming false. Doc 28 section 2 lists Space Grotesk / Inter / JetBrains Mono under fonts, and
    the whole obligation turns on whether a file is redistributed or only a family NAME is asked
    for."""
    tracked = subprocess.run(
        ["git", "ls-files", "*.ttf", "*.otf", "*.woff", "*.woff2", "*.ttc", "*.eot"],
        cwd=ROOT, capture_output=True, text=True, check=False)
    fonts = [line for line in tracked.stdout.splitlines() if line.strip()]
    claims_none = "No font file of any kind ships" in notice()
    if fonts:
        assert not claims_none, (
            f"NOTICE claims no font ships, but the repository tracks: {fonts}. Each needs its "
            f"licence text (OFL-1.1 for the three Doc 28 names)."
        )
    else:
        assert claims_none, "NOTICE no longer states that no font file ships"
    # And no font is loaded at runtime either -- a font could be shipped outside git.
    loaders = [sources.relative(p) for p in sources.cpp_sources()
               if "addApplicationFont" in p.read_text(encoding="utf-8", errors="replace")]
    assert not loaders or not claims_none, f"a font is registered at runtime in {loaders}"


# --- the open questions cannot be lost -------------------------------------------------------------

_UNDETERMINED = "UNDETERMINED"


def test_undetermined_entries_are_present_and_each_states_a_reason() -> None:
    """No licence is guessed, so some entries are open. An open entry with no reason is
    indistinguishable from an oversight -- the same third state Doc 50 rule 3 is about, applied to a
    legal document."""
    body = notice()
    # The body only. The final summary section is a list OF these, checked for completeness by the
    # next test; scanning it here would demand a reason from the section heading itself -- which is
    # how the first version of this test failed, and why it is worth saying: a rule aimed at the
    # wrong span reports a violation that is really its own scope being wrong.
    head = body[:body.index("UNDETERMINED — the owner must decide")]
    lines = head.splitlines()
    marked = [i for i, line in enumerate(lines) if _UNDETERMINED in line]
    assert marked, (
        "NOTICE carries no UNDETERMINED markers. Either every licence in the payload was "
        "established from the artifact -- in which case say so -- or a guess was made."
    )
    for i in marked:
        window = "\n".join(lines[i:i + 6])
        assert re.search(r"no licen[cs]e|no LICENSE|declares|reason|because|not a git|does not exist"
                         r"|cannot|not bundled|has not been|beyond what",
                         window, re.IGNORECASE), (
            f"NOTICE line {i + 1} is marked UNDETERMINED with no reason:\n{window}"
        )


def test_the_summary_accounts_for_every_open_question_in_the_body() -> None:
    """The property that keeps the file honest as it is edited.

    The final section is the list an owner reads. If an entry can be removed from it while the
    problem still stands in the body, the list stops meaning anything and it stops meaning it
    silently -- an open licence question that falls out of the summary looks exactly like one that
    was answered.

    So each flag in the body names its own SUBJECT in parentheses, and the pin is set-equality on
    those subjects rather than a count. The first version compared counts with ``>=`` and stayed
    green when a summary item was deleted, because eleven items still outnumbered seven flags: Doc
    50 rule 10's "a count that silently absorbs a moved site hides it behind a number that looks
    unchanged", found by deleting one and watching nothing happen.
    """
    body = notice()
    split = body.index("UNDETERMINED — the owner must decide")
    head, summary = body[:split], body[split:]
    # Skip the preamble, which explains the markers rather than raising one.
    head = head[head.index("1. Qt 6."):]

    marker = r"(?:UNDETERMINED — needs owner check|⚠ RESTRICTION|⚠ AGPL-3\.0 in the payload)"
    flag = re.compile(marker + r"[^(\n]*\(([^)]+)\)")
    # Every flag must NAME its subject. Without this the pin has a hole exactly where it matters:
    # deleting "(RES4LYF)" from a restriction left the set smaller, the summary unchanged, and the
    # test green -- an unattributed warning that no longer belongs to anything.
    unattributed = len(re.findall(marker, head)) - len(flag.findall(head))
    assert unattributed == 0, (
        f"{unattributed} flag(s) in the body name no subject in parentheses, so the summary cannot "
        f"be pinned to them"
    )
    subjects = {part.strip() for m in flag.finditer(head) for part in m.group(1).split(",")}
    assert len(subjects) >= 5, (
        f"only {len(subjects)} flagged subject(s) found in the body -- either the payload's licences "
        f"were all resolved, or the flags lost the '(subject)' the summary is pinned to"
    )

    missing = sorted(s for s in subjects if s not in summary)
    assert not missing, (
        f"flagged in the body and absent from the summary an owner reads: {missing}"
    )

    # Whole items, not first lines: the section citation usually sits on a continuation line, and a
    # first-line-only capture reported every entry as uncited.
    starts = [m.start() for m in re.finditer(r"^\s{0,4}\d+\.\s+\S", summary, re.MULTILINE)]
    numbered = [summary[a:b].strip() for a, b in zip(starts, starts[1:] + [len(summary)])]
    assert len(numbered) >= len(subjects), (
        f"{len(subjects)} subjects are flagged but the summary lists {len(numbered)} items"
    )
    # The other direction, so a resolved question cannot sit on an owner's plate forever: every
    # numbered item cites the section it came from, and that section must exist. Matching the item's
    # prose against the body was tried first and rejected -- it reported four "orphans" that were
    # all real entries phrased differently in the summary than in the body, which is the
    # two-false-positives-per-true-one shape that gets a rule bypassed.
    sections = set(re.findall(r"^(\d+)\. \S", body, re.MULTILINE))
    uncited = []
    for item in numbered:
        cite = re.search(r"\(§(\d+)", item)
        if cite is None or cite.group(1) not in sections:
            uncited.append(item[:70])
    assert not uncited, (
        f"summary entries that cite no existing section: {uncited} (sections found: "
        f"{sorted(sections)})"
    )


def test_the_notice_is_not_silently_excluded_from_the_payload() -> None:
    """A NOTICE that is git-ignored, or that lives somewhere the installer does not look, ships as
    reliably as one that does not exist."""
    result = subprocess.run(["git", "check-ignore", "-q", "NOTICE"], cwd=ROOT, check=False)
    assert result.returncode != 0, "NOTICE is git-ignored"
    assert NOTICE.parent == ROOT, "NOTICE must sit beside LICENSE at the repository root"
    assert (ROOT / "LICENSE").exists()
