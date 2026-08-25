"""Worker models root is env/explicit only — no D:/AI_ASSETS house fallback."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from runtime_identity import resolve_models_root  # noqa: E402


def test_unset_models_root_is_empty(monkeypatch) -> None:
    monkeypatch.delenv("SPELLVISION_MODELS", raising=False)
    assert resolve_models_root() is None


def test_models_root_uses_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SPELLVISION_MODELS", str(tmp_path))
    assert resolve_models_root() == tmp_path.resolve()
