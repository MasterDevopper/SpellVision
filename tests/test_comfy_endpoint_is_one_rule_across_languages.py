"""Both languages resolve the ComfyUI endpoint the same way, or neither can be trusted.

``python/comfy_endpoint.py`` collapsed 26 divergent sites into one precedence chain, and the worker
consequently drives a ComfyUI on another machine correctly -- verified end to end against a real
second box on 2026-09-01.

The Qt side did not move with it. ``RuntimeProfile::comfyHost`` was a hardcoded ``127.0.0.1`` that
read no environment and no setting, while ``comfyPort`` three lines below it read
``SPELLVISION_COMFY_PORT``. So the app could be pointed at another machine's PORT and never at
another machine -- and because the worker *did* honour ``COMFY_API_URL``, the two halves could
disagree silently: generation running on the node while every Qt probe reported the health, queue
depth and readiness of a local ComfyUI that was serving nothing.

That is worse than either half being wrong on its own, because both look right. So the C++ resolver
is a deliberate copy of the Python one, and this test is what keeps it a copy: the precedence order
lives in ``ENDPOINT_ENV_VARS`` and the C++ must name those variables, in that order. Adding a name on
one side without the other fails here rather than in a machine-specific bug six months later.

Reading C++ from Python rather than from a Qt test on purpose -- the authority for the ordering is
the Python tuple, so the assertion belongs where that tuple is importable.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tests"))

import comfy_endpoint  # noqa: E402
from cpp_source import find_definition  # noqa: E402


def _load_body() -> str:
    _path, body = find_definition("load", qualifier="RuntimeProfile")
    return body


# --- the precedence chain is shared ----------------------------------------------------------

def test_the_cpp_resolver_names_every_python_endpoint_variable() -> None:
    body = _load_body()
    for name in comfy_endpoint.ENDPOINT_ENV_VARS:
        assert name in body, (
            f"{name} is in the Python precedence chain but the Qt resolver never reads it; "
            "the two halves would disagree about which ComfyUI is being used"
        )


def test_the_cpp_resolver_keeps_the_python_precedence_order() -> None:
    """Order is the content. A chain that reads the same names in a different order resolves a
    different endpoint whenever more than one is set."""
    body = _load_body()
    positions = [body.index(name) for name in comfy_endpoint.ENDPOINT_ENV_VARS]
    assert positions == sorted(positions), (
        f"the Qt resolver reads {comfy_endpoint.ENDPOINT_ENV_VARS} out of order"
    )


def test_the_cpp_resolver_reads_the_host_variable_too() -> None:
    """The host/port pair is the last step before the default, and it is the step whose ABSENCE was
    the bug: the port was read, the host was not."""
    body = _load_body()
    assert comfy_endpoint.HOST_ENV_VAR in body
    assert comfy_endpoint.PORT_ENV_VAR in body


def test_the_host_is_no_longer_assigned_only_as_a_literal() -> None:
    """The regression, stated exactly: a comfyHost that is only ever its initialiser."""
    body = _load_body()
    assert re.search(r"profile\.comfyHost\s*=", body), (
        "RuntimeProfile::load never assigns comfyHost, so it keeps its hardcoded 127.0.0.1 and the "
        "app cannot be pointed at a ComfyUI on another machine"
    )


# --- the locality predicate exists on both sides ----------------------------------------------

def test_cpp_has_a_locality_predicate() -> None:
    """Python's is_local_endpoint gates seven install-management commands. C++ needs the same
    question answerable before its output-directory scans can be fixed."""
    _path, body = find_definition("comfyEndpointIsLocal", qualifier="RuntimeProfile")
    assert "isLoopback" in body, "the check must be the address family, not equality with a literal"
    assert "localhost" in body


def test_both_predicates_agree_on_the_hosts_they_call_local() -> None:
    """Same set, spelled once per language. A LAN address is not local in either."""
    _path, body = find_definition("comfyEndpointIsLocal", qualifier="RuntimeProfile")
    for host in ("localhost", "0.0.0.0", "::1"):
        assert comfy_endpoint.is_local_endpoint({"comfy_host": host}) is True
        assert host in body, f"{host!r} is local to Python but not named in the C++ predicate"
    # And the one that matters: the node.
    assert comfy_endpoint.is_local_endpoint({"comfy_host": "192.168.1.127"}) is False
