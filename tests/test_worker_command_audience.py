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

import ast
import sys
from pathlib import Path

import pytest

# Tree-wide property, not a call-site check: every dispatched command declares who it is for.
# Runs in the pre-commit hook -- keep it fast.
pytestmark = pytest.mark.ratchet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from worker_command_audience import (  # noqa: E402
    DIAGNOSTIC,
    INTERNAL,
    USER_FACING,
    all_classified,
    audience_of,
)


# Dispatch shapes this extractor knows how to read. A shape absent from here is not silently
# skipped -- it fails `test_the_dispatch_uses_no_shape_this_cannot_read` by name.
_READABLE_COMPARISONS = {"Eq", "In", "NotIn"}


# The dispatch variable itself. Matched EXACTLY rather than by substring: `model_resolution_commands`
# is a module whose name contains "command", and a substring match reported its method call as an
# unreadable dispatch shape. Verified equivalent -- both forms extract the same 125 commands.
_DISPATCH_NAME = "command"


def _dispatch_comparisons(tree: ast.Module) -> list[ast.Compare]:
    """Every comparison whose left side is the dispatch variable."""
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == _DISPATCH_NAME
    ]


def dispatched_commands() -> set[str]:
    """Every command worker_tcp.handle() actually dispatches on.

    Read from the AST rather than by regex over the source text, and the difference is not
    cosmetic. The regex form of this function shipped MISSING the ``not in`` shape: the generation
    commands are admitted by a ``if command not in {...}: reject`` guard rather than an ``==``
    chain, so t2i, i2i, t2v, i2v, comfy_workflow and the studio verbs were invisible to it. The
    completeness test below passed while the most important commands in the protocol were
    unclassified, and it took tests/test_worker_auth.py cross-checking its own allowlist to notice.

    Patching the regex fixed that instance and left the CLASS of failure in place: an extractor that
    reads code as text returns less when it meets a shape it does not know, and returning less is
    indistinguishable from there being less. So this reads comparisons structurally, and the test
    below refuses any dispatch shape it cannot read instead of quietly under-reporting.

    (Measured when this was rewritten: the AST and the patched regex agreed exactly, on 125
    commands across Eq / In / NotIn. The change buys nothing today and removes the way this went
    wrong before.)
    """
    source = (ROOT / "python" / "worker_tcp.py").read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)
    found: set[str] = set()
    for node in _dispatch_comparisons(tree):
        for comparator in node.comparators:
            for literal in ast.walk(comparator):
                if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                    found.add(literal.value)
    return found


def test_the_dispatch_uses_no_shape_this_cannot_read():
    """The extractor must fail loudly on an unfamiliar dispatch, not return a shorter list.

    Every guarantee in this file rests on `dispatched_commands` being complete. A `match` statement,
    a dict lookup or a `startswith` added tomorrow would be read as "no commands here" by a reader
    that only understands comparisons -- the same silent under-report that left the generation
    commands unclassified, arriving in a new costume.
    """
    source = (ROOT / "python" / "worker_tcp.py").read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)

    unknown_ops = {
        type(op).__name__
        for node in _dispatch_comparisons(tree)
        for op in node.ops
    } - _READABLE_COMPARISONS
    assert not unknown_ops, (
        f"worker_tcp dispatches with comparison(s) this extractor cannot read: {sorted(unknown_ops)}. "
        "Teach dispatched_commands() the shape, or the completeness checks below silently stop "
        "covering whatever it admits."
    )

    matches = [n for n in ast.walk(tree) if isinstance(n, ast.Match)]
    assert not matches, (
        "worker_tcp now dispatches with a `match` statement, which dispatched_commands() does not "
        "read. Either teach it, or move the routing into an importable table."
    )

    dynamic = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "getattr"
        and any(isinstance(a, ast.Name) and a.id == _DISPATCH_NAME for a in n.args)
    ]
    assert not dynamic, (
        "worker_tcp resolves a handler by name from the command. No static reader can enumerate "
        "that; the routing has to become a table this test can import."
    )

    # `command.startswith("legacy_")` names no command and reads as "nothing dispatched here". This
    # slipped through the first version of this guard, found by feeding it each shape it claims to
    # catch -- a guard nobody has watched fail is a guess about what it does.
    prefixed = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name) and n.func.value.id == _DISPATCH_NAME
    ]
    assert not prefixed, (
        "worker_tcp dispatches on a string method of `command` "
        f"({sorted({n.func.attr for n in prefixed})}), which names no command this test can read."
    )


def _guard_fires(source: str) -> bool:
    """Whatever the guard above would object to, in one predicate the tests can reuse."""
    tree = ast.parse(source)
    unknown = {type(op).__name__ for n in _dispatch_comparisons(tree) for op in n.ops}
    if unknown - _READABLE_COMPARISONS:
        return True
    if any(isinstance(n, ast.Match) for n in ast.walk(tree)):
        return True
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        if (isinstance(n.func, ast.Name) and n.func.id == "getattr"
                and any(isinstance(a, ast.Name) and a.id == _DISPATCH_NAME for a in n.args)):
            return True
        if (isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                and n.func.value.id == _DISPATCH_NAME):
            return True
    return False


@pytest.mark.parametrize("shape,lines", [
    ("match statement", ["def handle(command):", "    match command:",
                         "        case 'x':", "            pass"]),
    ("getattr dispatch", ["def handle(command, ws):", "    return getattr(ws, command, None)"]),
    ("startswith dispatch", ["def handle(command):",
                             "    if command.startswith('legacy_'):", "        pass"]),
    ("unreadable comparison", ["def handle(command):", "    if command < 'm':", "        pass"]),
])
def test_the_guard_fires_on_each_unreadable_shape(shape, lines):
    """A guard nobody has watched fail is a guess about what it does.

    Feeding it each shape is how the `startswith` hole was found: the first version caught `match`,
    `getattr` and an unknown operator, and read `if command.startswith("legacy_")` as an empty
    dispatch -- silently, which is the exact failure it exists to prevent.
    """
    assert _guard_fires("\n".join(lines)), (
        f"a dispatch written as a {shape} would be read as 'no commands here'"
    )


def test_the_guard_stays_quiet_on_the_shapes_in_use():
    """The other half. A guard that fires on everything gets bypassed within a week."""
    lines = [
        "def handle(command):",
        "    if command == 'ping':",
        "        return 1",
        "    if command in {'a', 'b'}:",
        "        return 2",
        "    if command not in {'t2i', 'i2v'}:",
        "        return 3",
    ]
    assert not _guard_fires("\n".join(lines))


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
        # Lockstep matters because the write behaviour is asymmetric: the C++ store
        # read-modify-writes and preserves unknown keys, while the Python side rebuilds the
        # secrets object from its own KNOWN_KEYS and would drop a key only C++ knew about.
        assert key in store, (
            f"the C++ store does not know the {key!r} credential; add it to kKnownKeys in "
            f"qt_ui/shell/SecureCredentialStore.cpp or the two stores will disagree"
        )
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
