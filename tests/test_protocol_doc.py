"""The protocol document has to describe the protocol that exists.

It documented **3 request types against 125 commands**, listed `t2v` and `i2v` under "Planned
commands" while both had been shipping and render-proven for months, and typed `job_id` as an
integer (`"job_id": 12`) when the real one is a string uuid.

None of that is a code defect, and all of it is the same failure this pass keeps finding: a claim
that reads as authoritative and is not true. A reader building against this document would have
written an integer job id and concluded video was unimplemented.

Documenting all 125 is not the fix -- it would rot the same way. The fix is that the document states
its own COVERAGE, and that the coverage is checked against the module which owns the answer.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import worker_command_audience as audience  # noqa: E402

DOC = ROOT / "docs" / "SPELLVISION_WORKER_PROTOCOL.md"
TEXT = DOC.read_text(encoding="utf-8")

CLASSIFIED = audience.USER_FACING | audience.DIAGNOSTIC | audience.INTERNAL
DOCUMENTED = set(re.findall(r'"command"\s*:\s*"([a-z0-9_]+)"', TEXT))


def _table_count(label: str) -> int:
    match = re.search(rf"\|\s*\**{label}\**\s*\|\s*\**(\d+)\**\s*\|", TEXT)
    assert match, f"the coverage table has no row for {label!r}"
    return int(match.group(1))


# --- the document describes commands that exist -----------------------------------------------------

def test_every_documented_command_is_a_real_one() -> None:
    """A command in the document that the worker does not implement is worse than an undocumented
    one: it is an instruction to write code that cannot work."""
    unknown = sorted(DOCUMENTED - CLASSIFIED)
    assert not unknown, (
        f"documented but not implemented (or not classified in worker_command_audience): {unknown}"
    )


def test_the_document_states_how_much_it_covers() -> None:
    """The old version presented three request types as though they were the protocol.

    Stating "3 of 125" is not an apology for the gap -- it is the difference between a reader
    knowing to look further and a reader believing they have the whole surface.
    """
    match = re.search(r"details \*?\*?(\d+) of (\d+) commands", TEXT)
    assert match, "the document must state how many of the commands it details"
    documented, total = int(match.group(1)), int(match.group(2))
    assert documented == len(DOCUMENTED), (
        f"the document claims to detail {documented} commands and shows {len(DOCUMENTED)}"
    )
    assert total == len(CLASSIFIED), (
        f"the document claims {total} commands exist and worker_command_audience classifies "
        f"{len(CLASSIFIED)}"
    )


@pytest.mark.parametrize("label,expected", [
    ("user-facing", "USER_FACING"),
    ("diagnostic", "DIAGNOSTIC"),
    ("internal", "INTERNAL"),
])
def test_the_coverage_table_matches_the_classification(label: str, expected: str) -> None:
    assert _table_count(label) == len(getattr(audience, expected)), (
        f"the {label} count in the protocol document disagrees with worker_command_audience."
        f"{expected}"
    )


def test_the_total_row_adds_up() -> None:
    assert _table_count("total") == len(CLASSIFIED)


# --- the shapes it shows are the shapes that are sent ------------------------------------------------

def test_job_id_is_documented_as_a_string() -> None:
    """It was `"job_id": 12`. The real one is a uuid, and has been since the queue landed."""
    integer_ids = re.findall(r'"job_id"\s*:\s*(\d+)', TEXT)
    assert not integer_ids, (
        f"job_id is documented as an integer ({integer_ids}); the worker sends a string uuid, and a "
        "client written against this would fail to correlate a single event"
    )


def test_no_shipped_command_is_described_as_planned() -> None:
    """The specific rot this replaces: t2v and i2v sat under "Planned commands" while both were
    render-proven. A planned-work list inside a protocol reference goes stale silently, because
    nothing that ships ever comes back to edit it."""
    # Matched as a HEADING, not as text. The replacement section explains what the old one said,
    # and a substring check would flag that explanation -- a rule tripping over the record of the
    # thing it forbids.
    for heading in ("Future Request Types", "Planned commands"):
        assert not re.search(rf"^#+\s*{re.escape(heading)}\s*$", TEXT, re.MULTILINE), (
            f"{heading!r} is back as a section. A forward-looking list belongs in the roadmap, "
            "where shipping something is expected to update it."
        )


def test_the_document_points_at_the_authority() -> None:
    """A reader who needs a command this document does not detail must be told where to look,
    rather than concluding it does not exist."""
    assert "worker_command_audience" in TEXT
