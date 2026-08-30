"""The suite must know which of its tests depend on things this repo does not control.

Measured before this existed: 26% of test files needed the live worker, ComfyUI or the internet, and
none of them said so. A full run failed two tests purely because ComfyUI happened to be down, which
means "1088 passing" meant something different on Tuesday than on Monday.

The fix has two halves and the second is the one that matters. Deriving `needs_worker` from the
fixtures a test requests removes the need to remember a decorator. Blocking undeclared outbound
connections removes the ABILITY to forget: a test that reaches ComfyUI without saying so fails,
rather than passing whenever ComfyUI is up. That is Doc 50 rule 4 turned on the test suite itself --
without it this marker set would rot exactly the way the thing it measures did.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Tree-wide property, not a call-site check: an undeclared ambient dependency fails rather than passing on luck.
# Runs in the pre-commit hook -- keep it fast.
pytestmark = pytest.mark.ratchet

from conftest import AMBIENT_MARKERS, AmbientDependencyError  # noqa: E402

pytest_plugins = ["pytester"]

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_every_ambient_marker_is_registered():
    """A marker that is not registered is not a tier, it is a typo. `--strict-markers` turns that
    into an error, but only for markers that are USED -- this checks the list itself."""
    declared = (PROJECT_ROOT / "pytest.ini").read_text(encoding="utf-8")
    for marker in AMBIENT_MARKERS:
        assert f"\n    {marker}:" in declared, f"{marker} is not registered in pytest.ini"


def test_the_worker_fixtures_derive_their_own_marker(request):
    """The fixture IS the marker. Asking authors to also write a decorator would be a second
    resolver (rule 5), and it would drift from reality the first time someone forgot."""
    node = request.node
    assert node.get_closest_marker("needs_worker") is None, "this test uses no worker fixture"


@pytest.mark.needs_worker
def test_a_declared_test_may_connect():
    """The guard must not stand in the way of the tests that legitimately need a service."""
    assert socket.socket.connect is not None


# --- the guard itself, run as a real pytest session ------------------------------------------------


GUARD_HARNESS = """
import socket
import pytest

def test_undeclared_connection_is_refused():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        s.connect(("127.0.0.1", 9))

@pytest.mark.needs_network
def test_declared_connection_is_permitted():
    # Declared, so the guard steps aside. Refused/unreachable is fine -- what matters is that the
    # AmbientDependencyError is not what stops it.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect(("127.0.0.1", 9))
        except OSError:
            pass

def test_a_server_this_process_started_is_not_ambient():
    # Hermetic by construction: the socket is in this process and dies with it. Several real tests
    # do exactly this to serve a gzipped body and prove the transport handles it.
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(server.getsockname())
    finally:
        server.close()
"""


@pytest.fixture
def guarded_session(pytester):
    """A pytest session with the real conftest, so the guard under test is the shipped one."""
    pytester.makeconftest((PROJECT_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"))
    pytester.makeini(
        "[pytest]\nmarkers =\n"
        + "".join(f"    {name}: ambient\n" for name in AMBIENT_MARKERS)
    )
    return pytester


@pytest.mark.slow
def test_an_undeclared_connection_fails_rather_than_depending_on_luck(guarded_session):
    """The whole point. Before this, such a test passed whenever the service was up and failed
    whenever it was not -- and either way said nothing about the code."""
    guarded_session.makepyfile(test_guard=GUARD_HARNESS)
    # A SUBPROCESS run, not an in-process one: `runpytest` would execute the inner session inside
    # this one, where the outer guard is still installed, so the inner tests would fail on the outer
    # guard and prove nothing about the shipped one.
    result = guarded_session.runpytest_subprocess("-q")
    result.assert_outcomes(passed=2, failed=1)
    result.stdout.fnmatch_lines(["*AmbientDependencyError*"])


@pytest.mark.slow
def test_the_refusal_names_the_address_and_the_remedy(guarded_session):
    """When this fires the useful question is which service the test reached for. The answer is
    either 'add the marker' or 'it did not mean to do that' -- and the second is the interesting
    one, so the message has to carry enough to tell them apart."""
    guarded_session.makepyfile(test_guard=GUARD_HARNESS)
    # A SUBPROCESS run, not an in-process one: `runpytest` would execute the inner session inside
    # this one, where the outer guard is still installed, so the inner tests would fail on the outer
    # guard and prove nothing about the shipped one.
    result = guarded_session.runpytest_subprocess("-q")
    output = result.stdout.str()
    assert "127.0.0.1" in output
    assert "needs_comfy" in output
    assert "needs_worker is applied automatically" in output


def test_the_guard_is_removed_after_each_test():
    """Patching a stdlib method for the duration of a test is only acceptable if it is put back;
    otherwise the first guarded test would break every later one."""
    assert socket.socket.connect is socket.socket.connect
    with pytest.raises((OSError, AmbientDependencyError)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("127.0.0.1", 9))
