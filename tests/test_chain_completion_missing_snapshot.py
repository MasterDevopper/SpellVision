"""Chain correlations fail visibly when a previously observed row disappears."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CPP = (ROOT / "qt_ui" / "chain" / "ChainCompletionWatcher.cpp").read_text(encoding="utf-8")
HEADER = (ROOT / "qt_ui" / "chain" / "ChainCompletionWatcher.h").read_text(encoding="utf-8")


def test_chain_watcher_has_bounded_missing_snapshot_grace() -> None:
    assert "Observed" in HEADER
    assert "missingSinceMs" in HEADER
    assert "unseenSuccessfulPolls" in HEADER
    assert "kMissingSnapshotGraceMs" in CPP
    assert "kUnseenSuccessfulPollLimit" in CPP
    assert "queuePollSucceeded" in CPP
    assert "QTimer::singleShot" in CPP
    assert "missingSinceMs = 0" in CPP
    assert "disappeared from worker queue snapshots" in CPP
