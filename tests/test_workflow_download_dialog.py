"""T2: drop a workflow with missing nodes → one Download dialog. Nothing fetches until click."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MW = ROOT / "qt_ui" / "MainWindow.cpp"
HDR = ROOT / "qt_ui" / "workflows" / "WorkflowDownloadDialog.h"
CPP = ROOT / "qt_ui" / "workflows" / "WorkflowDownloadDialog.cpp"
CMAKE = ROOT / "CMakeLists.txt"


def _drop_path_source() -> str:
    """The workflow-drop import, wherever it lives.

    These checks used to slice MainWindow.cpp between the ``workflowFileDropped`` connect and the
    next connect under it -- that is, they sliced a LAMBDA by its neighbours. The moment the lambda
    was lifted into a named function (it was 186 lines inside connectGenerationPage, and the window
    -level drop needed a second caller for it) the slice came back EMPTY and all four checks failed,
    with the behaviour they describe completely unchanged.

    A grep that is anchored on what sits next to the code is measuring the neighbourhood. Look the
    implementation up by name instead, and look in both homes: MainWindow while the import lives
    there, and WorkflowDropCoordinator once the sequence moves into its own unit.
    """
    parts = []
    coordinator = ROOT / "qt_ui" / "workflows" / "WorkflowDropCoordinator.cpp"
    if coordinator.is_file():
        parts.append(coordinator.read_text(encoding="utf-8"))
    mw = MW.read_text(encoding="utf-8")
    if "MainWindow::importDroppedWorkflow" in mw:
        parts.append(mw.split("MainWindow::importDroppedWorkflow", 1)[1].split("\nvoid MainWindow::", 1)[0])
    assert parts, "no workflow-drop implementation found in MainWindow.cpp or WorkflowDropCoordinator.cpp"
    return "\n".join(parts)


def test_workflow_download_dialog_exists_and_promises_no_fetch_until_click() -> None:
    assert HDR.is_file()
    assert CPP.is_file()
    cpp = CPP.read_text(encoding="utf-8")
    assert "Nothing is downloaded until you click Download" in cpp
    cmake = CMAKE.read_text(encoding="utf-8").replace("\\", "/")
    assert "qt_ui/workflows/WorkflowDownloadDialog.cpp" in cmake


def test_cockpit_drop_opens_download_dialog_when_nodes_are_missing() -> None:
    drop = _drop_path_source()
    assert "missing_custom_nodes" in drop
    assert "WorkflowDownloadDialog" in drop
    assert "auto_apply_node_deps" in drop


def test_cockpit_drop_opens_download_dialog_when_models_are_missing() -> None:
    """Missing checkpoints/UNETs/VAEs must share the same Download dialog.
    Nodes-only dialog left models on Flows with no fetch path."""
    drop = _drop_path_source()
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
    drop = _drop_path_source()
    assert "hasCredential" in drop
    assert "hf_token" in drop
    assert "civitai_api_key" in drop


def test_download_dialog_skips_already_installed_nodes() -> None:
    """BasicT2I_V23 listed 16 missing_custom_nodes whose packs were already_installed."""
    drop = _drop_path_source()
    assert "already_installed" in drop
    assert "node_plan" in drop
    assert "class_name" in drop


def test_flows_readiness_skips_already_installed_nodes() -> None:
    """Flows Launch used scan_report missing_custom_nodes even when node_plan said already_installed."""
    cpp = (ROOT / "qt_ui" / "WorkflowLibraryPage.cpp").read_text(encoding="utf-8")
    assert "already_installed" in cpp
    assert "dependency_plan.json" in cpp


def test_home_workflow_cards_skip_already_installed_nodes() -> None:
    """Home cards counted metadata.missing_custom_nodes even when last_launch_readiness said 0."""
    cpp = (ROOT / "qt_ui" / "HomePage.cpp").read_text(encoding="utf-8")
    assert "missing_node_classes" in cpp


def test_import_result_dialog_skips_already_installed_nodes() -> None:
    """Import result dialog counted scan-gap missing nodes even when node_plan said already_installed."""
    mw = MW.read_text(encoding="utf-8")
    body = mw.split("void MainWindow::showWorkflowImportResult", 1)[1].split("void MainWindow::", 1)[0]
    assert "already_installed" in body
    assert "node_plan" in body


def test_workflow_launch_log_skips_already_installed_nodes() -> None:
    """Launch log said review dependency warnings from scan-gap missing_custom_nodes."""
    mw = MW.read_text(encoding="utf-8")
    body = mw.split("void MainWindow::launchWorkflowProfileWithModel", 1)[1].split("void MainWindow::", 1)[0]
    assert "missing_node_classes" in body


def test_import_workflow_forwards_hf_token() -> None:
    """Download dialog stamps hf_token; import must actually use it."""
    lib = (ROOT / "python" / "workflow_library_commands.py").read_text(encoding="utf-8")
    assert 'req.get("hf_token"' in lib
    importer = (ROOT / "python" / "workflow_importer.py").read_text(encoding="utf-8")
    assert "hf_token" in importer
    resolver = (ROOT / "python" / "model_dependency_resolver.py").read_text(encoding="utf-8")
    sig = resolver.split("def build_model_install_plan", 1)[1].split(") -> ModelInstallPlan", 1)[0]
    assert "hf_token" in sig
