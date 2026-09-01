"""A render on another machine is not a file on this one.

Verified end to end on 2026-09-01 against a real second box (an Arch node with a 3090 Ti serving
ComfyUI 0.34.0 on the LAN). Everything that asks the ENDPOINT worked first time: the resolver picked
up ``COMFY_API_URL``, ``_fetch_comfy_object_info`` pulled 904 classes over the wire, the z-image
builder produced a graph the remote accepted, and ``_download_comfy_asset`` fetched the finished
1.28 MB PNG back through ``/view``.

Everything that asks the DISK was wrong, and wrong quietly. ``comfy_output_root()`` resolves this
machine's install whatever the endpoint is. The danger is not an empty directory -- it is a full one:
after a remote render, the local ``output/`` still holds the previous local session's images, so a
gallery scanning it shows an old picture as though it were the new one, and nothing errors.

``is_local_endpoint``'s own docstring already listed "reading an output from disk" among the things
that must check it. Every one of the ten readers ignored it -- the audit's governing pattern, where
a rule is stated once and applied only at the site that produced it.

The tree-wide half of this is the ``local-output-only-for-a-local-endpoint`` sweep. These are the
behaviours that sweep cannot see: that the guard actually fires, and that what it publishes when it
does is empty rather than a plausible-looking wrong path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import comfy_endpoint  # noqa: E402
import comfy_root  # noqa: E402

REMOTE = "http://192.168.1.127:8188"


@pytest.fixture
def remote(monkeypatch):
    for name in comfy_endpoint.ENDPOINT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COMFY_API_URL", REMOTE)
    return REMOTE


@pytest.fixture
def local(monkeypatch):
    for name in comfy_endpoint.ENDPOINT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("SPELLVISION_COMFY_HOST", raising=False)
    return comfy_endpoint.DEFAULT_ENDPOINT


# --- the predicate ---------------------------------------------------------------------------

def test_a_lan_host_is_not_local(remote) -> None:
    assert comfy_root.local_output_is_authoritative() is False


def test_the_default_endpoint_is_local(local) -> None:
    assert comfy_root.local_output_is_authoritative() is True


def test_a_loopback_alias_is_still_local(monkeypatch) -> None:
    """127.0.0.2 is loopback without being the literal default -- the check is the address family,
    not string equality with 127.0.0.1."""
    monkeypatch.setenv("COMFY_API_URL", "http://127.0.0.2:8188")
    assert comfy_root.local_output_is_authoritative() is True


def test_the_predicate_honours_a_per_request_endpoint(local) -> None:
    """The endpoint is a property of the REQUEST, not of the process. A module-level constant
    resolved at import -- which is what look_completion had -- cannot express that."""
    assert comfy_root.local_output_is_authoritative({"comfy_api_url": REMOTE}) is False


# --- the guard fires -------------------------------------------------------------------------

def test_the_output_root_warns_when_the_endpoint_is_remote(remote, caplog) -> None:
    """WARNING, not info: this repo's root logger sits at WARNING, so an info-level notice about
    reading the wrong directory would not be printed at all."""
    import logging

    with caplog.at_level(logging.WARNING, logger="spellvision.comfy"):
        comfy_root.comfy_output_root()
    assert any(REMOTE in record.getMessage() for record in caplog.records), (
        "the warning must name the endpoint, so the reader can tell which machine has the files"
    )


def test_the_output_root_is_quiet_when_the_endpoint_is_local(local, caplog) -> None:
    import logging

    with caplog.at_level(logging.WARNING, logger="spellvision.comfy"):
        comfy_root.comfy_output_root()
    assert not [r for r in caplog.records if "not on this filesystem" in r.getMessage()
                or "stale local work" in r.getMessage()]


# --- the two routes that read the disk --------------------------------------------------------

def test_look_completion_refuses_rather_than_timing_out(remote) -> None:
    """It polled the local directory on a 600 s deadline, so a remote endpoint produced
    "Comfy output timeout" -- which reads as a slow render, not as looking in the wrong place."""
    import look_completion

    with pytest.raises(look_completion.LookCompleteError) as excinfo:
        look_completion.wait_comfy_output("anything", 0.0, timeout=1.0)
    assert REMOTE in str(excinfo.value)


def test_look_completion_still_honours_an_explicit_directory(remote, tmp_path) -> None:
    """The refusal is about the DEFAULT. A caller that names a directory has said where to look,
    and must not be second-guessed -- that path is how a mounted share would be used."""
    import look_completion

    with pytest.raises(look_completion.LookCompleteError) as excinfo:
        look_completion.wait_comfy_output("nothing-here", 0.0, timeout=0.1, out_dir=tmp_path)
    assert "timeout" in str(excinfo.value).lower()


def test_the_ltx_route_publishes_no_location_when_there_is_none(remote) -> None:
    """_extract_history_outputs joins this root with the names ComfyUI reports. Path() normalises
    to "." -- publishing that would name the working directory as the place the renders are, which
    is a plausible-looking path pointing somewhere wrong: the exact failure being prevented."""
    import ltx_prompt_api_submission as ltx

    root = ltx._comfy_output_root(None)
    assert ltx._output_root_display(root) == ""


def test_the_ltx_route_still_publishes_a_local_location(local) -> None:
    import ltx_prompt_api_submission as ltx

    root = ltx._comfy_output_root(None)
    assert ltx._output_root_display(root).endswith("output")


def test_an_explicit_runtime_output_root_wins_over_the_guard(remote) -> None:
    """A caller that states the root has answered the question -- a UNC path to the node's share is
    exactly that, and is how these routes will eventually work remotely."""
    import ltx_prompt_api_submission as ltx

    root = ltx._comfy_output_root({"output_root": r"\spellnode\comfy\output"})
    assert ltx._output_root_display(root) != ""
