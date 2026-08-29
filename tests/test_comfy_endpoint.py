"""One resolver decides which ComfyUI to talk to.

26 sites across 12 modules each resolved this independently and they did not agree: five different
environment variable names, two modules that hardcoded ``http://127.0.0.1:8188`` as a constant and
read no environment at all, and one resolver in ``comfy_prompt_client`` that honoured
``SPELLVISION_COMFY_URL`` while its sibling three hundred lines away did not.

So pointing SpellVision at a ComfyUI on another machine would have moved SOME paths and silently
left others on localhost — a health check reporting success from the remote host while generation
ran locally. Same shape as the inert sampler dropdown.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import comfy_endpoint as ce  # noqa: E402

ALL_VARS = (*ce.ENDPOINT_ENV_VARS, ce.HOST_ENV_VAR, ce.PORT_ENV_VAR)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ALL_VARS:
        monkeypatch.delenv(name, raising=False)


# --- precedence ---------------------------------------------------------------------------------


def test_the_default_is_local_comfy():
    assert ce.comfy_endpoint() == "http://127.0.0.1:8188"
    assert ce.is_local_endpoint() is True


@pytest.mark.parametrize("name", ce.ENDPOINT_ENV_VARS)
def test_every_historical_env_var_still_works(name, monkeypatch):
    """Four names were in use across the tree. None may stop working, or someone's setup breaks
    silently -- they just all feed one chain now."""
    monkeypatch.setenv(name, "http://gpubox:8188")
    assert ce.comfy_endpoint() == "http://gpubox:8188"


def test_the_host_port_pair_still_works(monkeypatch):
    """comfy_bootstrap used this pair exclusively and would not have followed COMFY_API_URL."""
    monkeypatch.setenv(ce.HOST_ENV_VAR, "gpubox")
    monkeypatch.setenv(ce.PORT_ENV_VAR, "9999")
    assert ce.comfy_endpoint() == "http://gpubox:9999"
    assert ce.comfy_host() == "gpubox"
    assert ce.comfy_port() == 9999


def test_a_full_url_beats_the_host_port_pair(monkeypatch):
    monkeypatch.setenv("COMFY_API_URL", "http://explicit:1234")
    monkeypatch.setenv(ce.HOST_ENV_VAR, "ignored")
    assert ce.comfy_endpoint() == "http://explicit:1234"


def test_a_per_request_override_beats_the_environment(monkeypatch):
    monkeypatch.setenv("COMFY_API_URL", "http://env-host:8188")
    assert ce.comfy_endpoint({"comfy_api_url": "http://req-host:9000"}) == "http://req-host:9000"
    assert ce.comfy_endpoint({"comfy_host": "h2", "comfy_port": 7777}) == "http://h2:7777"


def test_a_bare_host_port_is_accepted_rather_than_punished(monkeypatch):
    """COMFY_API_URL=otherbox:8188 is the obvious thing to type, and used to produce a URL urllib
    rejects."""
    monkeypatch.setenv("COMFY_API_URL", "otherbox:8188")
    assert ce.comfy_endpoint() == "http://otherbox:8188"


def test_a_trailing_slash_is_dropped(monkeypatch):
    monkeypatch.setenv("COMFY_API_URL", "http://gpubox:8188/")
    assert ce.comfy_endpoint() == "http://gpubox:8188"


def test_blank_values_do_not_win(monkeypatch):
    monkeypatch.setenv("COMFY_API_URL", "   ")
    monkeypatch.setenv("SPELLVISION_COMFY_URL", "http://real:8188")
    assert ce.comfy_endpoint() == "http://real:8188"


# --- locality, which gates process and file management -------------------------------------------


@pytest.mark.parametrize("host,local", [
    ("127.0.0.1", True), ("localhost", True), ("::1", True),
    ("gpubox", False), ("192.168.1.50", False), ("10.0.0.5", False),
])
def test_locality_is_reported_correctly(host, local, monkeypatch):
    """Starting or stopping the process, installing node packs into custom_nodes/ and reading an
    output off disk are all meaningless against a remote endpoint. Callers that manage the install
    must branch on this instead of assuming co-location."""
    monkeypatch.setenv("COMFY_API_URL", f"http://{host}:8188")
    assert ce.is_local_endpoint() is local


# --- the ratchet ---------------------------------------------------------------------------------


def test_no_module_resolves_the_endpoint_behind_the_resolvers_back():
    """The durable half. A second hardcoded endpoint is exactly how the fragmentation grew.

    Fails on any new ``127.0.0.1:8188`` literal or direct read of an endpoint environment variable
    outside comfy_endpoint.py, which is what a reviewer would otherwise have to notice by eye.
    """
    offenders = []
    pattern = re.compile("|".join(re.escape(v) for v in ALL_VARS))
    for path in sorted((ROOT / "python").glob("*.py")):
        if path.name == "comfy_endpoint.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{number} reads an endpoint env var directly")
            elif "127.0.0.1" in line and ("8188" in line or "comfy" in line.lower()):
                offenders.append(f"{path.name}:{number} hardcodes a ComfyUI endpoint")
    assert not offenders, (
        "resolve through comfy_endpoint() instead:\n  " + "\n  ".join(offenders)
    )


def test_the_install_directory_variable_is_not_confused_with_the_endpoint():
    """SPELLVISION_COMFY is the install PATH (runtime_paths), not the HTTP endpoint. A remote
    endpoint has no local install path, so conflating them would make a remote setup try to read
    files that are not there."""
    assert "SPELLVISION_COMFY" not in ALL_VARS
    source = (ROOT / "python" / "comfy_endpoint.py").read_text(encoding="utf-8")
    assert 'os.environ.get("SPELLVISION_COMFY")' not in source
