"""One ComfyUI install root, reachable under every name it has ever had.

The defect this closes is not a wrong path, it is two halves of the app disagreeing about which
ComfyUI they are discussing:

* Qt's ``RuntimeProfile`` exports exactly one name, ``SPELLVISION_COMFY``, into every child process.
* ``video_family_readiness`` read exactly two, ``SPELLVISION_COMFY_ROOT`` and ``COMFYUI_ROOT``.

The intersection is empty, so readiness could never see the configured root. It fell through to its
own default, and on a box with the D: tree present that is the ROLLBACK build CLAUDE.md 9.2 forbids
probing as live. Three more modules hardcoded that tree as a literal.

The gate the plan asks for is here as a test rather than as a manual check: point the resolver at a
root through each historical name and confirm every consumer moves with it -- and point it at a dead
path and confirm nothing silently falls back, which is the method that verified comfy_endpoint.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import comfy_root  # noqa: E402
from comfy_root import (  # noqa: E402
    LIVE_COMFY,
    ROLLBACK_COMFY,
    ROOT_ENV_VARS,
    comfy_output_root,
    comfy_user_workflow,
    prefer_live,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ROOT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


# --- every historical name reaches the resolver -----------------------------------------------------

@pytest.mark.parametrize("name", ROOT_ENV_VARS)
def test_every_historical_name_is_honoured(name: str, monkeypatch, tmp_path) -> None:
    """Nothing that worked stops working. They feed one chain now instead of four."""
    monkeypatch.setenv(name, str(tmp_path))
    assert comfy_root.comfy_root() == tmp_path.resolve()


def test_the_name_the_shell_exports_wins(monkeypatch, tmp_path) -> None:
    """SPELLVISION_COMFY is what RuntimeProfile puts in every child process, so it is the
    configured value in practice and outranks the others."""
    first, second, third = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    monkeypatch.setenv("COMFYUI_ROOT", str(third))
    monkeypatch.setenv("SPELLVISION_COMFY_ROOT", str(second))
    monkeypatch.setenv("SPELLVISION_COMFY", str(first))
    assert comfy_root.comfy_root() == first.resolve()


def test_an_explicit_argument_outranks_the_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SPELLVISION_COMFY", str(tmp_path / "env"))
    assert comfy_root.comfy_root(explicit=tmp_path / "explicit") == (tmp_path / "explicit").resolve()
    assert comfy_root.comfy_root({"comfy_root": str(tmp_path / "req")}) == (tmp_path / "req").resolve()


def test_an_unexpanded_template_is_not_a_path(monkeypatch, tmp_path) -> None:
    """A leaked ``${SPELLVISION_ROOT}`` is how a resolver starts pointing at a directory named
    after the variable nobody expanded."""
    monkeypatch.setenv("SPELLVISION_COMFY", "${SPELLVISION_ROOT}/comfy")
    monkeypatch.setenv("SPELLVISION_COMFY_ROOT", str(tmp_path))
    assert comfy_root.comfy_root() == tmp_path.resolve()


# --- every consumer moves together ------------------------------------------------------------------

def test_repointing_the_root_moves_every_consumer(monkeypatch, tmp_path) -> None:
    """The gate. Point at a root and confirm the derived paths follow it.

    These were three separate literals before -- two into the rollback tree and one into the live
    one -- so which module found a render depended on which literal it happened to carry.
    """
    monkeypatch.setenv("SPELLVISION_COMFY", str(tmp_path))
    assert comfy_output_root() == (tmp_path / "output").resolve()
    assert comfy_user_workflow("ltx_api.json") == (
        tmp_path / "user" / "default" / "workflows" / "ltx_api.json").resolve()

    import video_family_readiness

    assert video_family_readiness._default_comfy_root(None) == tmp_path.resolve()

    import runtime_identity

    assert runtime_identity.resolve_comfy_root() == tmp_path.resolve()


def test_a_dead_path_is_used_rather_than_silently_replaced(monkeypatch, tmp_path) -> None:
    """The method that verified comfy_endpoint: point at something that does not exist and confirm
    nothing quietly substitutes a working default. A resolver that repairs its input cannot be
    tested, and cannot be trusted when it disagrees with the user."""
    dead = tmp_path / "does" / "not" / "exist"
    monkeypatch.setenv("SPELLVISION_COMFY", str(dead))
    assert comfy_root.comfy_root() == dead.resolve()
    assert comfy_output_root() == (dead / "output").resolve()


# --- the rollback tree ------------------------------------------------------------------------------

def test_a_rollback_path_becomes_the_live_one(monkeypatch) -> None:
    """CLAUDE.md 9.2. Saved settings, old metadata and old contracts still carry the pre-cutover
    path; following it runs generation against the May core while everything else talks to July."""
    if not LIVE_COMFY.exists():
        pytest.skip("no live install on this machine; the redirect has nothing to redirect to")
    assert prefer_live(ROLLBACK_COMFY) == LIVE_COMFY
    assert prefer_live(str(ROLLBACK_COMFY).replace("/", "\\")) == LIVE_COMFY
    assert comfy_root.comfy_root(explicit=ROLLBACK_COMFY) == LIVE_COMFY.resolve()


def test_a_path_that_merely_mentions_comfy_runtime_is_left_alone(tmp_path) -> None:
    """The redirect matches the pre-cutover LAYOUT, not the word. An unrelated directory that
    happens to contain "comfy_runtime" in its name is the user's, not the rollback tree."""
    unrelated = tmp_path / "my_comfy_runtime_backups"
    assert prefer_live(unrelated) == unrelated


def test_falling_back_to_the_rollback_tree_is_never_quiet(monkeypatch, caplog) -> None:
    import logging

    # Written against the SUPERSEDED list rather than a drive letter. The first version keyed on
    # "D:", which is the May build -- so at the 2026-08-31 cutover, when the first rollback became
    # a C: tree, the test stopped exercising the fallback at all and failed for the wrong reason.
    monkeypatch.setattr(comfy_root, "LIVE_COMFY", Path("Z:/no/such/live"))
    for depth, tree in enumerate(comfy_root.SUPERSEDED_COMFY):
        caplog.clear()
        monkeypatch.setattr(comfy_root.Path, "exists",
                            lambda self, _t=str(tree): str(self) == _t)
        with caplog.at_level(logging.WARNING):
            resolved = comfy_root.comfy_root()
        assert resolved == tree.resolve(), f"depth {depth}: {resolved}"
        assert any("ROLLBACK" in record.getMessage() for record in caplog.records), (
            f"depth {depth}: a readiness check answering about the wrong ComfyUI must say so"
        )


def test_rollback_is_two_deep_and_ordered_newest_first() -> None:
    """The 2026-08-31 cutover made the previous live install a rollback tree, so there are now two.
    Order matters: falling back past the v0.27.0 core to the May build would skip a generation."""
    assert len(comfy_root.SUPERSEDED_COMFY) == 2
    assert comfy_root.ROLLBACK_COMFY == comfy_root.SUPERSEDED_COMFY[0]
    assert "sv_comfynext" in str(comfy_root.SUPERSEDED_COMFY[0])
    assert "comfy_runtime" in str(comfy_root.SUPERSEDED_COMFY[1])
    assert comfy_root.LIVE_COMFY not in comfy_root.SUPERSEDED_COMFY


def test_the_live_root_is_not_redirected_by_its_own_prefix() -> None:
    """`C:/sv_comfynext_v034/ComfyUI` has `C:/sv_comfynext/ComfyUI` as a bare string prefix. A
    substring test would redirect the live install onto itself today and onto the wrong tree the
    moment the names stop overlapping -- so the match is anchored on the separator."""
    assert prefer_live(comfy_root.LIVE_COMFY) == comfy_root.LIVE_COMFY
    assert prefer_live(comfy_root.SUPERSEDED_COMFY[0]) == comfy_root.LIVE_COMFY


# --- the shape is the same on both sides ------------------------------------------------------------

def test_the_qt_resolver_knows_the_same_names() -> None:
    """The two halves are only useful if they agree. RuntimeProfile.cpp declares the same list in
    the same order; a name added to one and not the other puts the halves back out of step, which
    is the whole defect."""
    source = (Path(__file__).resolve().parents[1] / "qt_ui" / "shell" / "RuntimeProfile.cpp").read_text(
        encoding="utf-8", errors="replace")
    start = source.index("kComfyRootEnvNames")
    block = source[start:source.index("};", start)]
    for name in ROOT_ENV_VARS:
        assert f'"{name}"' in block, f"the Qt resolver does not know {name}"
