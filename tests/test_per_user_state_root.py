"""Mutable worker state must live under an explicit per-user state root."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


def test_runtime_profile_exports_per_user_state_root() -> None:
    source = (ROOT / "qt_ui" / "shell" / "RuntimeProfile.cpp").read_text(encoding="utf-8")
    assert "QStandardPaths::AppLocalDataLocation" in source
    assert 'environment.insert(QStringLiteral("SPELLVISION_STATE_ROOT"), stateRoot)' in source
    assert 'QDir(profile.projectRoot).filePath(QStringLiteral("runtime"))' not in source


def test_history_and_manifests_share_configured_state_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPELLVISION_STATE_ROOT", str(tmp_path))
    import worker_durable_state
    import worker_metadata

    durable = importlib.reload(worker_durable_state)
    metadata = importlib.reload(worker_metadata)

    assert durable.worker_state_root() == tmp_path.resolve()
    assert metadata.VIDEO_HISTORY_DIR == tmp_path.resolve() / "history"
    assert metadata.VIDEO_HISTORY_INDEX_PATH.parent == tmp_path.resolve() / "history"
