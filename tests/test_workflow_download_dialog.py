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


def test_cockpit_drop_opens_download_dialog_when_models_are_missing() -> None:
    """Missing checkpoints/UNETs/VAEs must share the same Download dialog.
    Nodes-only dialog left models on Flows with no fetch path."""
    mw = MW.read_text(encoding="utf-8")
    drop = mw.split("workflowFileDropped", 1)[1].split("prepForI2IRequested", 1)[0]
    assert "dependency_plan" in drop
    assert "model_plan" in drop
    assert "install_actions" in drop
    assert "missingModels" in drop
    assert "auto_apply_model_deps" in drop
    hdr = HDR.read_text(encoding="utf-8")
    assert "missingModels" in hdr
    cpp = CPP.read_text(encoding="utf-8")
    assert "node" in cpp.lower()
    assert "model" in cpp.lower()


def test_download_dialog_asks_for_missing_keys_with_create_url() -> None:
    """If HF/CivitAI is needed and the store is empty, the same dialog asks
    and links the page that creates that key. Already-saved keys stay silent."""
    hdr = HDR.read_text(encoding="utf-8")
    cpp = CPP.read_text(encoding="utf-8")
    assert "askCivitaiKey" in hdr
    assert "askHfToken" in hdr
    assert "https://huggingface.co/settings/tokens" in cpp
    assert "https://civitai.com/user/account" in cpp
    mw = MW.read_text(encoding="utf-8")
    drop = mw.split("workflowFileDropped", 1)[1].split("prepForI2IRequested", 1)[0]
    assert "hasCredential" in drop
    assert "hf_token" in drop
    assert "civitai_api_key" in drop


def test_import_workflow_forwards_hf_token() -> None:
    """Download dialog stamps hf_token; import must actually use it."""
    lib = (ROOT / "python" / "workflow_library_commands.py").read_text(encoding="utf-8")
    assert 'req.get("hf_token"' in lib
    importer = (ROOT / "python" / "workflow_importer.py").read_text(encoding="utf-8")
    assert "hf_token" in importer
    resolver = (ROOT / "python" / "model_dependency_resolver.py").read_text(encoding="utf-8")
    sig = resolver.split("def build_model_install_plan", 1)[1].split(") -> ModelInstallPlan", 1)[0]
    assert "hf_token" in sig
