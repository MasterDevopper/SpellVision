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
    # Taken from the resolver rather than spelled here. Written out, these two literals silently
    # stopped matching anything at the 2026-08-31 cutover -- the test kept passing and stopped
    # catching a re-introduced hardcode of the CURRENT root, which is the only one worth catching.
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "python"))
    from comfy_root import LIVE_COMFY, SUPERSEDED_COMFY

    roots = [LIVE_COMFY, *SUPERSEDED_COMFY]
    for source in (helpers, main):
        for root in roots:
            assert str(root).replace("\\", "/") not in source, (
                f"{root} is hardcoded outside the resolver"
            )
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
    assert "Create library on this drive" in text
    assert "createModelsLibraryOnDrive" in text
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


def test_first_run_probes_do_not_block_the_dialog() -> None:
    """Ctor and the 1.5s tick used to call probeWorkerProtocol / probeComfyProtocol
    on the GUI thread. They belong on QtConcurrent; the dialog paints, then the
    badges update when the answer arrives."""
    start = definition_body("startReachabilityProbes", qualifier="FirstRunDialog")
    refresh = definition_body("refreshChecks", qualifier="FirstRunDialog")
    # Ctor has no return type, so definition_body cannot find it. Everything before showPage is
    # the anonymous helpers plus the constructor — the old blocking probes lived there.
    ctor = DIALOG.read_text(encoding="utf-8").split("void FirstRunDialog::showPage", 1)[0]
    assert "probeWorkerProtocol" not in ctor
    assert "probeComfyProtocol" not in ctor
    assert "workerIsReachable" not in ctor
    assert "probeWorkerProtocol" not in refresh
    assert "probeComfyProtocol" not in refresh
    assert "QThreadPool" in start
    assert "probeWorkerProtocol" in start
    assert "probeComfyProtocol" in start
    assert "QueuedConnection" in start


def test_launch_and_quit_do_not_block_the_window() -> None:
    """Runtimes start after the first paint; quit does not waitForFinished on Comfy."""
    main = MAIN.read_text(encoding="utf-8")
    assert "ctor after scheduling runtime" in main
    assert "ctor after ensureWorker" not in main
    assert "ctor after ensureComfy" not in main
    assert "QTimer::singleShot(0, this" in main
    tear = definition_body("tearDownComfyOnExit", qualifier="MainWindow")
    assert "waitForFinished" not in tear
    assert "setParent(nullptr)" in tear
    assert "probeComfyQueueState" not in tear, (
        "quit used to wait 500ms on /queue; that blocks the window's disappearance"
    )
    worker = definition_body("stopOwnedWorkerService", qualifier="MainWindow")
    assert "waitForFinished" not in worker
    assert "waitForStarted" not in worker


def test_failed_or_lost_job_clears_submitting() -> None:
    """Generate latches busy at click. Completion cleared it; failure and
    worker-lost reset the bottom bar to Idle and left the canvas on
    'Submitting generation…' with Queue 0."""
    main = MAIN.read_text(encoding="utf-8")
    fail = main.split("a fresh failure is the newest terminal state", 1)[0]
    fail = fail[fail.rfind("if (newestFailed") :]
    assert "showGenerationError" in fail
    assert "setBusy(false" in fail
    lost = main.split("queueConnectivityLost", 1)[1].split("queuePollSucceeded", 1)[0]
    assert "resetSubmissionTelemetry" in lost
    assert "setBusy(false" in lost


def test_t2i_catalog_scans_extra_model_roots() -> None:
    """Models page Add folder… wrote runtime/extraModelsRoots. T2I still scanned
    only the primary root, so F: populated Models and not the checkpoint picker."""
    catalog = (ROOT / "qt_ui" / "ImageGenerationPage_catalog.cpp").read_text(encoding="utf-8")
    refresh = catalog.split("void ImageGenerationPage::refreshModelCatalog", 1)[1]
    refresh = refresh.split("QString ImageGenerationPage::catalogSignature", 1)[0]
    assert "extraModelsRootsFromSettings" in refresh
    scan = catalog.split("ImageGenerationPage::scanCatalogs", 1)[1]
    scan = scan.split("void ImageGenerationPage::applyCatalogRefreshResult", 1)[0]
    assert "scannableModelsRoots(modelsRoot, extraRoots)" in scan


def test_primary_models_root_resolves_like_extra_folders() -> None:
    """Browse / settings for the primary library must walk drive → AI_ASSETS
    → models the same way extra folders do. Storing D:/ or D:/AI_ASSETS as
    modelsRoot left T2I looking for D:/checkpoints."""
    browse = (ROOT / "qt_ui" / "shell" / "FirstRunDialog.cpp").read_text(encoding="utf-8")
    browse = browse.split("void FirstRunDialog::browseModelsRoot", 1)[1]
    browse = browse.split("void FirstRunDialog::createModelsLibraryOnDrive", 1)[0]
    assert "resolveModelsLibraryRoot" in browse
    choose = (ROOT / "qt_ui" / "generation" / "OutputPathHelpers.cpp").read_text(encoding="utf-8")
    choose = choose.split("QString chooseModelsRootPath()", 1)[1]
    choose = choose.split("QString chooseComfyOutputPath()", 1)[0]
    assert "resolveModelsLibraryRoot" in choose
    manager = (ROOT / "qt_ui" / "ManagerPage.cpp").read_text(encoding="utf-8")
    pick = manager.split("void ManagerPage::chooseModelsRoot()", 1)[1]
    pick = pick.split("void ManagerPage::openComfyRoot()", 1)[0]
    assert "resolveModelsLibraryRoot" in pick


def test_comfy_launch_writes_extra_model_paths() -> None:
    """Add folder only helps Generate if Comfy extra_model_paths.yaml lists those
    libraries before the process starts."""
    main = MAIN.read_text(encoding="utf-8")
    launch = main.split("void MainWindow::ensureComfyRuntimeAvailable()", 1)[1]
    launch = launch.split("void MainWindow::", 1)[0]
    assert "writeManagedExtraModelPaths" in launch
    assert "extraModelsRootsFromSettings" in launch


def test_changing_checkpoint_clears_stale_generation_error() -> None:
    """Flux fail left 'Flux mo…' on the action row after they picked anima."""
    catalog = (ROOT / "qt_ui" / "ImageGenerationPage_catalog.cpp").read_text(encoding="utf-8")
    body = catalog.split("void ImageGenerationPage::setSelectedModel", 1)[1]
    body = body.split("void ImageGenerationPage::resolveAndApplyVideoComponents", 1)[0]
    assert "modelChanged" in body
    assert "clearGenerationError" in body


def test_busy_overlay_rewrites_when_job_is_running() -> None:
    """Live Krea2 T2I: bar went Running / est. remaining; canvas and
    readiness strip stayed on 'Submitting generation…' the whole sample.
    Message-only setBusy stored the copy and did not paint. Telemetry
    Running must rewrite the overlay without clearing busy."""
    body = definition_body("setBusy", qualifier="ImageGenerationPage")
    assert "Keep the new text internally and" not in body
    assert "readinessLabel" in body
    early = body.split("lockHeightForBusy", 1)[0]
    assert "aiReadinessText_" in early
    sync = definition_body("syncBottomTelemetry", qualifier="MainWindow")
    assert "Generating…" in sync
    assert "setBusy(true" in sync


def test_in_flight_job_does_not_clear_busy_from_older_completed() -> None:
    """After a restart, queue poll sees yesterday's completed still as
    'new' and setBusy(false) while this submit is still Running."""
    body = definition_body("syncGenerationPreviewsFromQueue", qualifier="MainWindow")
    assert "page->isBusy()" in body
    assert "queueItemIsActiveForGeneration" in body


def test_same_family_checkpoint_change_reapplies_operating_point() -> None:
    """Live Krea2 stayed at 60 steps (table default 52) because
    applyOperatingPoint ran only when operatingPointFamily_ changed."""
    body = definition_body("updateOperatingPointSelector", qualifier="ImageGenerationPage")
    assert "else if (!defaultPoint.isEmpty())" in body
    assert "applyOperatingPoint(defaultPoint)" in body
    assert 'else if (family == QStringLiteral("krea2")' not in body


def test_krea2_hidden_selector_uses_table_sampler() -> None:
    """krea2_image table sampler is er_sde (render comparison 2026-08-28).
    Hidden selector (<=1 point) hardcoded euler."""
    body = definition_body("updateOperatingPointSelector", qualifier="ImageGenerationPage")
    hidden = body.split("points.size() <= 1", 1)[1].split("return;", 1)[0]
    assert "er_sde" in hidden
    assert 'QStringLiteral("euler")' not in hidden
