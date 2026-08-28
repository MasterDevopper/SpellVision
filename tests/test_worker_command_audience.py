"""The reachability ratchet: every command a user is supposed to reach must have a route.

Doc 49 measured that the queue was append-only from the UI. The uncomfortable part was not the
count -- it was that nothing distinguished a deliberately CLI-only command from one somebody forgot
to wire, so a one-off sweep could not become a standing guarantee.

These tests are that guarantee. The command list comes from ``worker_tcp``'s DISPATCH TABLE, not
from ``worker_client.CONTROL_COMMANDS`` -- the registry is a streaming-vs-one-shot classifier
covering 51 of the 113 dispatched commands, and treating it as the command list is what made the
first pass of this audit miss more than half the surface.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from worker_command_audience import (  # noqa: E402
    DIAGNOSTIC,
    INTERNAL,
    USER_FACING,
    all_classified,
    audience_of,
)


def dispatched_commands() -> set[str]:
    """Every command worker_tcp.handle() actually dispatches on."""
    source = (ROOT / "python" / "worker_tcp.py").read_text(encoding="utf-8", errors="replace")
    found = set(re.findall(r'command == "([a-z0-9_]+)"', source))
    for block in re.findall(r"command in \{([^}]+)\}", source):
        found.update(re.findall(r'"([a-z0-9_]+)"', block))
    return found


def cpp_sources() -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in (ROOT / "qt_ui").rglob("*.cpp"))


# --- the ratchet ------------------------------------------------------------------------------


def test_every_user_facing_command_has_a_route_in_the_ui():
    """The point of the whole file.

    Promoting a command to USER_FACING without wiring it fails here, so the declaration cannot
    drift ahead of the app. This is what turns Doc 49's sweep into a standing guarantee.
    """
    cpp = cpp_sources()
    unreachable = sorted(c for c in USER_FACING if f'"{c}"' not in cpp)
    assert not unreachable, (
        "declared user-facing but no qt_ui/ call site sends them:\n  "
        + "\n  ".join(unreachable)
        + "\n\nEither wire them up, or reclassify them as DIAGNOSTIC/INTERNAL with a reason."
    )


def test_every_dispatched_command_is_classified():
    """A new command forces an explicit decision about who it is for."""
    unclassified = sorted(dispatched_commands() - all_classified())
    assert not unclassified, (
        "worker_tcp dispatches these but worker_command_audience does not classify them:\n  "
        + "\n  ".join(unclassified)
        + "\n\nAdd each to USER_FACING, DIAGNOSTIC or INTERNAL."
    )


def test_the_audience_map_does_not_name_commands_that_no_longer_exist():
    """The other direction: a renamed or deleted command must not linger as a stale claim."""
    stale = sorted(all_classified() - dispatched_commands())
    assert not stale, (
        "classified but not dispatched by worker_tcp (renamed or removed?):\n  " + "\n  ".join(stale)
    )


def test_the_three_audiences_are_disjoint():
    assert not (USER_FACING & DIAGNOSTIC)
    assert not (USER_FACING & INTERNAL)
    assert not (DIAGNOSTIC & INTERNAL)


# --- what the classification asserts ------------------------------------------------------------


@pytest.mark.parametrize("command", sorted({
    "cancel_queue_item", "cancel_active_queue_item", "cancel_all_queue_items",
    "remove_queue_item", "clear_pending_queue", "pause_queue", "resume_queue",
    "move_queue_item_up", "move_queue_item_down", "retry_queue_item", "duplicate_queue_item",
}))
def test_the_queue_commands_are_user_facing_and_stay_reachable(command):
    """Doc 49's headline finding, pinned so it cannot regress.

    All eleven were implemented on the worker and reachable from nowhere until the queue context
    menu landed. A user could watch a job run with no way to stop it.
    """
    assert audience_of(command) == "user_facing"
    assert f'"{command}"' in cpp_sources()


def test_free_vram_stays_reachable():
    """unload_all_runtimes and clear_cuda_cache existed unreached while ComfyUI's accounting
    wedged (0.1 GB reported against an actual 29.8 GB) and Restart was the only recovery."""
    for command in ("unload_all_runtimes", "clear_cuda_cache"):
        assert audience_of(command) == "user_facing"
        assert f'"{command}"' in cpp_sources()


def test_credential_commands_are_internal_because_c_plus_plus_owns_the_store():
    """Not 'forgot to wire' -- superseded, and the distinction is the reason this file exists.

    qt_ui/shell/SecureCredentialStore implements the same DPAPI scheme natively: same entropy
    string, same key names, and the same file. Verified rather than assumed.
    """
    for command in ("save_credential", "clear_credential", "credential_status", "secrets_status"):
        assert audience_of(command) == "internal"

    store = (ROOT / "qt_ui" / "shell" / "SecureCredentialStore.cpp").read_text(
        encoding="utf-8", errors="replace")
    import credential_store

    assert credential_store.ENTROPY.decode() in store, "the two stores disagree on DPAPI entropy"
    for key in credential_store.KNOWN_KEYS:
        assert key in store, f"the C++ store does not know the {key!r} credential"
    assert "DarkDuck/SpellVision/credentials.json" in store
    assert credential_store.default_store_path().name == "credentials.json"


def test_the_ltx_prompt_api_family_is_diagnostic_not_missing_ui():
    """LTX is native/production; the prompt-API surface is an explicit fallback, not a user path."""
    for command in ("ltx_prompt_api_submit", "ltx_workflow_contract", "ltx_readiness_status"):
        assert audience_of(command) == "diagnostic"


def test_aliases_are_internal():
    for command in ("enqueue_job", "cancel_job", "retry_job", "history_video_status"):
        assert audience_of(command) == "internal"


def test_an_unknown_command_is_unclassified_rather_than_defaulted():
    """Three states, not two -- a name nobody has classified must not silently read as internal."""
    assert audience_of("some_future_command") is None
    assert audience_of("") is None
