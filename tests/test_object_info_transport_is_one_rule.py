"""Four modules fetched /object_info and one had the transport fix.

The fix is recorded in CLAUDE.md, in `comfy_prompt_client`, and in
`tests/test_comfy_object_info_transport.py`: urllib **always** sends ``Connection: close``
(``AbstractHTTPHandler.do_open`` puts it in unconditionally), and against a core whose
``/object_info`` body is 6.76MB the server tears the socket down before the body flushes. Measured,
requests otherwise identical: bare and ``Accept-Encoding`` variants succeeded 3 of 3;
``Connection: close`` reset 3 of 3.

It shipped into ``comfy_prompt_client._http_get_json`` and stopped there. Three sites kept fetching
through urllib:

    comfy_node_contract.py       a bare urlopen -- the tool that exists to PRE-SCREEN a core bump,
                                 and it died on the first bump it was pointed at
    video_family_readiness.py    a bare urlopen wrapped in `except Exception: return {}` -- so the
                                 reset became an EMPTY object_info, every node looked absent, and
                                 every family reported NOT READY with nothing in the log
    flows_health.py              a urlopen still passing `Connection: close` EXPLICITLY, recorded at
                                 the time as the fix for the resets, retried five times

The readiness one is the dangerous shape and the reason this rule exists rather than three edits:
an unreadable answer became an empty one, which is the same defect as the ``os.walk`` rule one level
up, and it is silent by construction.

Found by running the node-contract tool against the staged v0.34.0 instance during the cutover
re-verification -- that is, by pointing the tooling at the very core the transport fix was measured
against. A rule applied at its own site is a memo; this is Doc 50 rule 10 in its most literal form.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from sweeps import rules, sources  # noqa: E402

RULE = [r for r in rules.ALL_RULES if r.name == "object-info-through-one-transport"][0]
FAKE = sources.ROOT / "python" / "Fake.py"

BARE_URLOPEN = (
    'with urllib.request.urlopen(f"{args.api}/object_info", timeout=90) as response:\n'
    '    object_info = json.loads(response.read().decode("utf-8"))'
)

SWALLOWED_TO_EMPTY = (
    'try:\n'
    '    with urllib.request.urlopen(f"{endpoint}/object_info", timeout=5) as response:\n'
    '        payload = response.read().decode("utf-8")\n'
    '    return json.loads(payload)\n'
    'except Exception:\n'
    '    return {}'
)

EXPLICIT_CLOSE_HEADER = (
    'req = urllib.request.Request(f"{api}/object_info", headers={"Connection": "close"})\n'
    'with urllib.request.urlopen(req, timeout=180) as r:\n'
    '    return json.loads(r.read().decode("utf-8"))'
)


# --- the tree is clean ---------------------------------------------------------------------------

def test_no_module_fetches_object_info_through_urllib() -> None:
    """The exemption is this file itself, which holds each broken shape as a fixture so the rule can
    be watched firing on it. Keyed and reasoned in exemptions.py rather than spelled around: a
    fixture that disguised itself would no longer be the code the rule has to catch."""
    from sweeps import exemptions

    exempt = exemptions.EXEMPT[RULE.name]
    unexplained = [str(v) for v in RULE.run() if sources.relative(v.path) not in exempt]
    assert not unexplained, unexplained


def test_the_reader_is_recognised_by_what_it_declares() -> None:
    """Keyed on its own contract, so moving or renaming the module does not disable the rule -- the
    failure mode of every ratchet this audit had to re-scope."""
    reader = sources.ROOT / "python/comfy_prompt_client.py"
    assert not rules._check_object_info_transport(reader, reader.read_text(encoding="utf-8"))
    elsewhere = sources.ROOT / "python/Somewhere.py"
    assert not rules._check_object_info_transport(elsewhere, reader.read_text(encoding="utf-8"))


# --- it fires on each shape it replaced -----------------------------------------------------------

@pytest.mark.parametrize("name,source", [
    ("comfy_node_contract: a bare urlopen", BARE_URLOPEN),
    ("video_family_readiness: the reset swallowed to an empty dict", SWALLOWED_TO_EMPTY),
    ("flows_health: the disproven Connection: close, retried five times", EXPLICIT_CLOSE_HEADER),
])
def test_the_rule_fires_on_each_site_it_replaced(name: str, source: str) -> None:
    """A guard nobody has watched fail is a guess about what it does. Two rules in this pass shipped
    silently broken and reported clean trees, so each one now gets fed the code it was written for."""
    assert rules._check_object_info_transport(FAKE, source), name


# --- and stays quiet on what it is not for --------------------------------------------------------

def test_urllib_against_a_different_endpoint_is_not_this_defect() -> None:
    """Only /object_info is big enough to reset. Flagging every urlopen would make the rule noise,
    and a rule with more false positives than true ones gets bypassed."""
    assert not rules._check_object_info_transport(
        FAKE, 'urllib.request.urlopen(f"{api}/system_stats", timeout=5)')


def test_naming_the_path_without_fetching_it_is_not_this_defect() -> None:
    assert not rules._check_object_info_transport(FAKE, 'cached = store["/object_info"]')


def test_the_fixed_call_is_clean() -> None:
    assert not rules._check_object_info_transport(
        FAKE,
        'from comfy_prompt_client import _http_get_json\n'
        'oi = _http_get_json(api_url, "/object_info", timeout=90)')


# --- the readiness contract is kept ---------------------------------------------------------------

def test_readiness_still_returns_an_empty_dict_but_says_why(caplog) -> None:
    """The `{}` return is a contract callers depend on, so it is kept. What changed is that an empty
    answer meaning "could not look" is now distinguishable in the log from one meaning "the core
    defines nothing" -- Doc 50 rule 3, and the reason this was invisible for so long. WARNING
    because the root logger drops info."""
    import logging

    sys.path.insert(0, str(ROOT / "python"))
    import video_family_readiness as vfr

    with caplog.at_level(logging.WARNING):
        result = vfr._fetch_comfy_object_info("http://127.0.0.1:9")
    assert result == {}
    assert any("object_info" in r.getMessage() for r in caplog.records), (
        "an unreadable /object_info must not be silently indistinguishable from an empty one"
    )


def test_an_empty_endpoint_is_still_empty_without_a_warning(caplog) -> None:
    """No endpoint configured is a known state, not a failed reading; it should not log."""
    import logging

    sys.path.insert(0, str(ROOT / "python"))
    import video_family_readiness as vfr

    with caplog.at_level(logging.WARNING):
        assert vfr._fetch_comfy_object_info("") == {}
    assert not [r for r in caplog.records if "object_info" in r.getMessage()]
