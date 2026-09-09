"""T2: drop a workflow with missing nodes → one Download dialog. Nothing fetches until click."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MW = ROOT / "qt_ui" / "MainWindow.cpp"
HDR = ROOT / "qt_ui" / "workflows" / "WorkflowDownloadDialog.h"
CPP = ROOT / "qt_ui" / "workflows" / "WorkflowDownloadDialog.cpp"
CMAKE = ROOT / "CMakeLists.txt"


def test_workflow_download_dialog_exists_and_promises_no_fetch_until_click() -> None:
    assert HDR.is_file()
    assert CPP.is_file()
    cpp = CPP.read_text(encoding="utf-8")
    assert "Nothing is downloaded until you click Download" in cpp
    cmake = CMAKE.read_text(encoding="utf-8").replace("\\", "/")
    assert "qt_ui/workflows/WorkflowDownloadDialog.cpp" in cmake


def test_cockpit_drop_opens_download_dialog_when_nodes_are_missing() -> None:
    mw = MW.read_text(encoding="utf-8")
    drop = mw.split("workflowFileDropped", 1)[1].split("prepForI2IRequested", 1)[0]
    assert "missing_custom_nodes" in drop
    assert "WorkflowDownloadDialog" in drop
    assert "auto_apply_node_deps" in drop
