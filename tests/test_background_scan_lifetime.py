"""Background filesystem scans never dereference QWidget instances."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_CPP = (ROOT / "qt_ui" / "ModelManagerPage.cpp").read_text(encoding="utf-8")
MODEL_H = (ROOT / "qt_ui" / "ModelManagerPage.h").read_text(encoding="utf-8")
FLOW_CPP = (ROOT / "qt_ui" / "WorkflowLibraryPage.cpp").read_text(encoding="utf-8")
FLOW_H = (ROOT / "qt_ui" / "WorkflowLibraryPage.h").read_text(encoding="utf-8")


def test_model_inventory_future_uses_captured_roots_only() -> None:
    body = MODEL_CPP.split("void ModelManagerPage::refreshInventory", 1)[1].split(
        "void ModelManagerPage::onRefreshFinished", 1
    )[0]
    assert "[this]" not in body
    assert "modelsRoot" in body and "downloadsRoot" in body
    assert "static RefreshResult scanModelInventory" in MODEL_H


def test_workflow_library_future_uses_captured_root_only() -> None:
    body = FLOW_CPP.split("void WorkflowLibraryPage::refreshLibrary", 1)[1].split(
        "void WorkflowLibraryPage::onLibraryRefreshFinished", 1
    )[0]
    assert "[this]" not in body
    assert "importedWorkflowsRoot" in body
    assert "static LibraryRefreshResult buildLibraryRefreshResult" in FLOW_H
