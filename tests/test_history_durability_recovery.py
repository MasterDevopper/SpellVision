"""History and metadata durability/recovery regressions."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

import worker_metadata as wm


def _redirect_history(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(wm, "VIDEO_HISTORY_DIR", root)
    monkeypatch.setattr(wm, "VIDEO_HISTORY_INDEX_PATH", root / "video_history_index.json")
    monkeypatch.setattr(wm, "VIDEO_HISTORY_JSONL_PATH", root / "video_history.jsonl")


def test_corrupt_index_recovers_ledger_before_new_persist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_history(monkeypatch, tmp_path)
    wm.VIDEO_HISTORY_INDEX_PATH.write_text("{truncated", encoding="utf-8")
    ledger = [
        {"history_id": "h1", "output": "a.png"},
        {"history_id": "h2", "output": "b.png"},
    ]
    wm.VIDEO_HISTORY_JSONL_PATH.write_text(
        "".join(json.dumps(item) + "\n" for item in ledger), encoding="utf-8"
    )

    wm.persist_video_history_entry({"history_id": "h3", "output": "c.png"})

    payload = json.loads(wm.VIDEO_HISTORY_INDEX_PATH.read_text(encoding="utf-8"))
    assert [item["history_id"] for item in payload["items"]] == ["h1", "h2", "h3"]


def test_valid_index_reconciles_ledger_tail_after_interrupted_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_history(monkeypatch, tmp_path)
    wm.VIDEO_HISTORY_INDEX_PATH.write_text(
        json.dumps({"items": [{"history_id": "h1", "output": "a.png"}]}), encoding="utf-8"
    )
    wm.VIDEO_HISTORY_JSONL_PATH.write_bytes(
        (json.dumps({"history_id": "h1", "output": "a.png"}) + "\n").encode()
        + (json.dumps({"history_id": "h2", "output": "b.png"}) + "\n").encode()
        + b'{"history_id":"partial"'
    )

    snapshot = wm.video_history_snapshot(limit=10)

    assert [item["history_id"] for item in reversed(snapshot["items"])] == ["h1", "h2"]
    repaired = json.loads(wm.VIDEO_HISTORY_INDEX_PATH.read_text(encoding="utf-8"))
    assert [item["history_id"] for item in repaired["items"]] == ["h1", "h2"]


def test_atomic_json_failure_preserves_existing_target_and_cleans_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "metadata.json"
    target.write_text('{"old":true}', encoding="utf-8")

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("simulated publication failure")

    monkeypatch.setattr(wm.os, "replace", fail_replace)
    with pytest.raises(OSError, match="publication failure"):
        wm.write_metadata_file(str(target), {"new": True})

    assert target.read_text(encoding="utf-8") == '{"old":true}'
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".*.tmp")) == []
