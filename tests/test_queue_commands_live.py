"""Every queue-management command the context menu sends, over the real TCP protocol.

Until the menu landed the queue was **append-only from the UI**: the worker had implemented
cancel / cancel-active / cancel-all / remove / clear-pending / pause / resume / reorder / retry /
duplicate since the queue existed, the UI sent ``enqueue`` and nothing else, and the queue table
had no context menu at all. A user could watch a job run and had no way to stop it (Doc 49).

These tests pin the exact wire contract the menu depends on -- **the command string and the
payload key** -- because that pairing is where it already went wrong once: ``retry_queue_item`` is
keyed by ``job_id`` while every other command is keyed by ``queue_item_id``, and the first version
of the menu sent ``queue_item_id`` to all ten. The worker would have read an empty id, failed, and
the user would have seen a Retry that did nothing.

Command-name drift is the other half. A renamed handler leaves the C++ literal pointing at
nothing, and an unknown command is not a crash -- it is a quiet non-answer, which is exactly the
failure mode this session kept finding.
"""
from __future__ import annotations

import pytest

# The literals in qt_ui/MainWindow.cpp showQueueContextMenu, paired with the payload key each one
# is sent with. Kept as data so a rename shows up here as a failing row, not as a dead menu item.
MENU_COMMANDS = [
    ("cancel_queue_item", "queue_item_id"),
    ("cancel_active_queue_item", None),
    ("cancel_all_queue_items", None),
    ("remove_queue_item", "queue_item_id"),
    ("clear_pending_queue", None),
    ("pause_queue", None),
    ("resume_queue", None),
    ("move_queue_item_up", "queue_item_id"),
    ("move_queue_item_down", "queue_item_id"),
    ("duplicate_queue_item", "queue_item_id"),
    ("retry_queue_item", "job_id"),
]


# A queue ack IS a queue snapshot: the message carries both the action's result and fresh queue
# state, and the transport routes on the snapshot type. The action is identified by the `action`
# key, not by a distinct message type -- handlers used to set "queue_ack" but the snapshot spread
# always overrode it, so no such message has ever reached the wire.
def _acks(messages):
    return [m for m in messages if m.get("action")]


def _snapshot(worker_client):
    for message in worker_client({"command": "queue_status"}):
        if "items" in message or message.get("type") in {"queue_status", "queue_snapshot"}:
            return message
    raise AssertionError("queue_status returned no snapshot")


@pytest.mark.parametrize("command,key", MENU_COMMANDS)
def test_every_menu_command_is_answered_by_the_worker(worker_client, command, key):
    """Reachability, at the wire level.

    An unregistered command does not raise -- it returns a ``client_warning`` envelope whose own
    ``ok`` is ``true``, which is how an unwired seam looked like success earlier this session. So
    the assertion is that a RECOGNISED response type comes back, not merely that something did.
    """
    request = {"command": command}
    if key:
        request[key] = "no-such-item"

    messages = worker_client(request)
    assert messages, f"{command} returned nothing at all"

    types = {m.get("type") for m in messages}
    assert "client_warning" not in types, (
        f"{command} is not registered on the worker -- the UI would get a warning envelope "
        f"whose ok is true and show nothing. Messages: {messages}"
    )


@pytest.mark.parametrize("command,key", [(c, k) for c, k in MENU_COMMANDS if k == "queue_item_id"])
def test_an_unknown_queue_item_is_refused_with_a_reason(worker_client, command, key):
    """``ok: false`` plus a message -- never ``ok: true`` over a no-op.

    The menu surfaces the reason in the activity log. A command that reports success while doing
    nothing would leave the user watching a row that never changes.
    """
    acks = _acks(worker_client({"command": command, key: "definitely-not-a-queue-item"}))
    assert acks, f"{command} emitted no queue_ack"
    ack = acks[0]
    assert ack["ok"] is False
    assert ack["action"] == command
    assert str(ack.get("message") or ack.get("error") or "").strip(), (
        f"{command} refused the request without saying why"
    )


def test_retry_is_keyed_by_job_id_not_queue_item_id(worker_client):
    """The bug the first version of the menu had.

    Sending ``queue_item_id`` to retry means the worker reads an empty job id. It must not be
    mistaken for a working call: an empty id is refused, and refused for a *stated* reason.
    """
    wrong = _acks(worker_client({"command": "retry_queue_item", "queue_item_id": "abc"}))
    assert wrong and wrong[0]["ok"] is False

    right = _acks(worker_client({"command": "retry_queue_item", "job_id": "not-in-archive"}))
    assert right and right[0]["ok"] is False
    assert right[0].get("source_job_id") == "not-in-archive", (
        "the worker did not read job_id -- the menu's payload key is wrong"
    )


def test_cancel_without_an_id_targets_the_active_job(worker_client):
    """``cancel_active_queue_item`` and an id-less ``cancel_queue_item`` are the same handler.

    The menu relies on this: the active row is cancelled with no id, because it is mid-run inside
    the worker rather than sitting in the pending list.
    """
    for command in ("cancel_queue_item", "cancel_active_queue_item"):
        acks = _acks(worker_client({"command": command}))
        assert acks, f"{command} emitted no queue_ack"
        # Nothing is running in a fresh worker, so this is a clean refusal -- the point is that it
        # is ANSWERED and does not require an id.
        assert acks[0]["action"] == "cancel_queue_item"


def test_pause_and_resume_move_the_flag_both_ways(worker_client):
    """State that the menu reads back: the item is labelled Pause or Resume from this flag.

    The key is ``queue_paused``, which is what QueueManager::applyQueueSnapshot reads. Pinned by
    name because ``isPaused()`` decides which of two labels the menu shows, and a rename would
    silently leave it stuck on "Pause Queue" for a queue that is already paused.
    """
    paused = _acks(worker_client({"command": "pause_queue"}))
    assert paused and paused[0]["ok"] is True
    assert _snapshot(worker_client).get("queue_paused") is True

    resumed = _acks(worker_client({"command": "resume_queue"}))
    assert resumed and resumed[0]["ok"] is True
    assert _snapshot(worker_client).get("queue_paused") is False


def test_queue_wide_commands_are_safe_on_an_empty_queue(worker_client):
    """Clear and cancel-all are one click from a right-click. On an empty queue they must be a
    clean no-op, not an exception that reaches the user as a failure."""
    for command in ("clear_pending_queue", "cancel_all_queue_items"):
        acks = _acks(worker_client({"command": command}))
        assert acks and acks[0]["ok"] is True, f"{command} failed on an empty queue: {acks}"


def test_every_queue_ack_carries_a_fresh_snapshot(worker_client):
    """The menu polls after each command, but the ack already carries the new state.

    Asserting it here keeps that guarantee: without it, a cancel would be invisible until the next
    1.8s poll tick, which reads as "the click did nothing".
    """
    for command, key in MENU_COMMANDS:
        request = {"command": command}
        if key:
            request[key] = "no-such-item"
        for ack in _acks(worker_client(request)):
            assert "items" in ack, f"{command} ack carried no queue snapshot"
