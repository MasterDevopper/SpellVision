"""First-run is honest: STARTING vs NEEDS SETUP, no F: house path, worker not killed at 5s."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpp_source import definition_body

ROOT = Path(__file__).resolve().parents[1]
DIALOG = ROOT / "qt_ui" / "shell" / "FirstRunDialog.cpp"
MAIN = ROOT / "qt_ui" / "MainWindow.cpp"


def test_first_run_has_starting_state_and_no_f_drive_assumption() -> None:
    text = DIALOG.read_text(encoding="utf-8")
    header = (ROOT / "qt_ui" / "shell" / "FirstRunDialog.h").read_text(encoding="utf-8")
    assert "STARTING" in text
    assert "F:/AI_ASSETS/models" not in text
    profile = (ROOT / "qt_ui" / "shell" / "RuntimeProfile.cpp").read_text(encoding="utf-8")
    helpers = (ROOT / "qt_ui" / "generation" / "OutputPathHelpers.cpp").read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    manager = (ROOT / "qt_ui" / "ManagerPage.cpp").read_text(encoding="utf-8")
    models = (ROOT / "qt_ui" / "ModelManagerPage.cpp").read_text(encoding="utf-8")
    runner = (ROOT / "qt_ui" / "workers" / "WorkerCommandRunner.cpp").read_text(encoding="utf-8")
    catalog = (ROOT / "qt_ui" / "ImageGenerationPage_catalog.cpp").read_text(encoding="utf-8")
    assert 'QStringLiteral("D:/AI_ASSETS/models")' not in profile
    assert 'QStringLiteral("D:/AI_ASSETS/models")' not in helpers
    assert 'QStringLiteral("D:/AI_ASSETS/models")' not in manager
    assert 'QStringLiteral("D:/AI_ASSETS/models")' not in models
    # The install literals are no longer asserted per-file HERE. RuntimeProfile.cpp is now the Qt
    # ComfyUI-root resolver -- it has to name the live and rollback installs, the way comfy_endpoint
    # names 127.0.0.1:8188 -- and the tree-wide `no-machine-paths` sweep enforces that it is the
    # ONLY Qt file that does, with the exemption carrying that reason. Three files named in a test
    # is the shape the sweep exists to replace: it was green while ImageGenerationPage and
    # ModelThumbnailCache both carried the rollback path, because neither was on this list.
    for source in (helpers, main):
        assert "C:/sv_comfynext/ComfyUI" not in source
        assert "D:/AI_ASSETS/comfy_runtime/ComfyUI" not in source
    assert 'filePath(QStringLiteral("runtime/comfy/ComfyUI"))' not in profile
    assert "if (!blockReason.isEmpty())" in runner
    assert "return;" in runner.split("if (!blockReason.isEmpty())", 1)[-1][:180]
    hunt = catalog[catalog.find("void ImageGenerationPage::queueHuntList") :]
    assert "readinessBlockReason()" in hunt[:400]
    assert "Choose an output folder to generate." in catalog
    assert "workerStarting" in text and "comfyStarting" in text
    assert "Model library folder" in text
    assert "Generation output folder" in text
    assert "image_generation/output_folder" in text
    assert "browseModelsRoot" in text
    assert "browseOutputFolder" in text
    assert "refreshChecks" in text
    assert "QTimer" in text
    assert "workerCheckStatus_" in header
    assert "Generation output" in text
    # By name, not by file: the builder moved out of MainWindow.cpp and the old split() on its
    # qualified name raised IndexError, which reads as a broken test rather than as a moved function.
    assert 'filePath(QStringLiteral("output"))' not in definition_body("buildWorkerGenerationRequest")[:800]
    assert "userGenerationDestFolder" in main
    submit = main[main.find("void MainWindow::submitGenerationRequest") :]
    assert "Choose an output folder to generate." in submit[:8000]


def test_worker_startup_wait_does_not_kill_live_process() -> None:
    text = MAIN.read_text(encoding="utf-8")
    wait = text[text.find("void MainWindow::ensureWorkerServiceAvailable") : text.find("void MainWindow::stopOwnedWorkerService")]
    profile = (ROOT / "qt_ui" / "shell" / "RuntimeProfile.cpp").read_text(encoding="utf-8")
    assert "Stop-Process" not in wait
    assert "if (probeWorkerService(350))" in wait
    assert "pong" in profile and 'QStringLiteral("result")' in profile
    # Startup is nonblocking: no synchronous waitForStarted/waitForFinished on
    # the GUI thread. A bounded readiness watchdog (kWorkerReadinessDeadlineMs)
    # terminates only an app-owned process that starts but never proves the
    # spellvision_worker protocol.
    assert "waitForStarted" not in wait
    assert "waitForFinished" not in wait
    assert "kWorkerReadinessDeadlineMs" in wait
    assert "workerReachable_" in wait


def test_dataset_and_ltx_readiness_have_no_house_defaults() -> None:
    dataset = (ROOT / "qt_ui" / "DatasetGenerationPage.cpp").read_text(encoding="utf-8")
    assert "runtime/datasets/latest" not in dataset
    assert 'setValue(1024)' not in dataset
    assert 'setValue(42)' not in dataset
    assert "Choose an output folder to generate." in dataset
    assert "Choose a canvas size to generate." in dataset
    readiness = (ROOT / "python" / "video_family_readiness.py").read_text(encoding="utf-8")
    assert 'Path("D:/AI_ASSETS")' not in readiness
    assert "D:/AI_ASSETS/models/diffusion_models" not in readiness
    assert "return None" in readiness
