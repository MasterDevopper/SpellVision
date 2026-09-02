"""Delete removes one model file that is ours to remove, and refuses everything else.

The Models page had no delete. Adding one means the worker unlinks a path the UI names, so the path
is held to the one place models may live -- the configured models root -- and the command fails
closed when that root is not configured. Sidecars go with the file so the library cannot show a
ghost. Local-only by construction: not in the integration allowlist.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import model_delete  # noqa: E402
from model_delete import delete_model, plan_delete  # noqa: E402


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "models"
    (r / "loras").mkdir(parents=True)
    return r.resolve()


def _model(root: Path, name: str = "chel.safetensors", with_sidecars: bool = True) -> Path:
    p = root / "loras" / name
    p.write_bytes(b"\x00" * 16)
    if with_sidecars:
        stem = p.with_suffix("")
        for suffix in (".metadata.json", ".png", ".civitai.info"):
            Path(str(stem) + suffix).write_text("x", encoding="utf-8")
    return p


# --- what is deleted ------------------------------------------------------------------------------

def test_the_file_and_its_sidecars_go_together(root) -> None:
    p = _model(root)
    result = delete_model(str(p), root)
    assert result["ok"], result
    assert not p.exists()
    for suffix in (".metadata.json", ".png", ".civitai.info"):
        assert not Path(str(p.with_suffix("")) + suffix).exists(), f"{suffix} left behind as a ghost"
    assert len(result["deleted"]) == 4


def test_the_plan_names_what_will_go_before_anything_does(root) -> None:
    p = _model(root)
    plan = plan_delete(str(p), root)
    assert plan["ok"]
    assert len(plan["sidecars"]) == 3
    assert p.exists(), "planning must not delete"


def test_a_sibling_model_with_a_shared_prefix_is_untouched(root) -> None:
    """chel.safetensors must not take chel_v2.safetensors or chel_v2.png with it."""
    p = _model(root)
    other = _model(root, "chel_v2.safetensors")
    delete_model(str(p), root)
    assert other.exists()
    assert Path(str(other.with_suffix("")) + ".png").exists()


# --- what is refused ------------------------------------------------------------------------------

def test_outside_the_root_is_refused(root, tmp_path) -> None:
    elsewhere = tmp_path / "elsewhere" / "victim.safetensors"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(b"x")
    result = delete_model(str(elsewhere), root)
    assert not result["ok"]
    assert "outside the models root" in result["error"]
    assert elsewhere.exists()


def test_traversal_out_of_the_root_is_refused(root, tmp_path) -> None:
    victim = tmp_path / "victim.safetensors"
    victim.write_bytes(b"x")
    sneaky = root / "loras" / ".." / ".." / "victim.safetensors"
    result = delete_model(str(sneaky), root)
    assert not result["ok"]
    assert victim.exists()


def test_no_root_configured_refuses_rather_than_deleting_anywhere(root, monkeypatch) -> None:
    p = _model(root)
    monkeypatch.setattr(model_delete, "models_root", lambda: None)
    result = delete_model(str(p))
    assert not result["ok"]
    assert "SPELLVISION_MODELS" in result["error"]
    assert p.exists()


def test_a_directory_is_refused(root) -> None:
    result = delete_model(str(root / "loras"), root)
    assert not result["ok"]
    assert (root / "loras").exists()


def test_a_non_model_suffix_is_refused(root) -> None:
    txt = root / "loras" / "notes.txt"
    txt.write_text("keep", encoding="utf-8")
    result = delete_model(str(txt), root)
    assert not result["ok"]
    assert "model extension" in result["error"]
    assert txt.exists()


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs a privilege on Windows")
def test_a_symlink_is_refused_not_followed(root, tmp_path) -> None:
    real = tmp_path / "real.safetensors"
    real.write_bytes(b"x")
    link = root / "loras" / "link.safetensors"
    link.symlink_to(real)
    result = delete_model(str(link), root)
    assert not result["ok"]
    assert link.is_symlink() and real.exists()


def test_an_empty_path_is_refused(root) -> None:
    assert not delete_model("", root)["ok"]


# --- the command's place in the protocol -----------------------------------------------------------

def test_delete_is_not_reachable_by_an_integration_caller() -> None:
    import worker_auth

    assert "delete_model" not in worker_auth.INTEGRATION_COMMANDS
    assert worker_auth.permits(worker_auth.INTEGRATION, "delete_model") is False
    assert worker_auth.permits(worker_auth.LOCAL_PROBE, "delete_model") is False


def test_delete_is_dispatched_and_classified_user_facing() -> None:
    tcp = (ROOT / "python" / "worker_tcp.py").read_text(encoding="utf-8")
    assert 'if command == "delete_model":' in tcp
    import worker_command_audience

    assert "delete_model" in worker_command_audience.USER_FACING


def test_the_models_root_is_the_shared_resolver_not_a_second_env_read() -> None:
    src = (ROOT / "python" / "model_delete.py").read_text(encoding="utf-8")
    assert "RuntimePaths.MODELS" in src
    assert 'os.environ.get("SPELLVISION_MODELS")' not in src
