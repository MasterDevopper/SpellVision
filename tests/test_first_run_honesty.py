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


def test_adopted_comfy_still_writes_extra_model_paths() -> None:
    """probe success returned before writing yaml. Sage restart without
    SpellVision then left F: extras off live Comfy; Generate said krea2 stack incomplete."""
    main = MAIN.read_text(encoding="utf-8")
    launch = main.split("void MainWindow::ensureComfyRuntimeAvailable()", 1)[1]
    launch = launch.split("void MainWindow::", 1)[0]
    write_at = launch.find("writeManagedExtraModelPaths")
    probe_at = launch.find("probeComfyRuntime")
    assert write_at >= 0
    assert probe_at >= 0
    assert write_at < probe_at


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


def test_simple_mode_hides_operating_point_selector() -> None:
    """Simple auto-applies family+variant defaults. Speed card is Advanced-only."""
    body = definition_body("updateOperatingPointSelector", qualifier="ImageGenerationPage")
    assert "operatingPointCard_->setVisible(advanced_)" in body
    disc = definition_body("updateDisclosure", qualifier="ImageGenerationPage")
    assert "operatingPointCard_" in disc


def test_prep_for_i2i_applies_input_after_mode_switch() -> None:
    """Live hole 2026-09-09: Prep set I2I input then switchToMode; canvas stayed empty."""
    mw = MAIN.read_text(encoding="utf-8")
    body = mw.split("prepForI2IRequested", 1)[1].split("queueRequested", 1)[0]
    assert "switchToMode" in body
    assert "useImageAsInput" in body
    assert body.find("switchToMode") < body.find("useImageAsInput")
    assert "singleShot" in body


def test_restore_snapshot_skips_missing_input_image() -> None:
    body = definition_body("restoreSnapshot", qualifier="ImageGenerationPage")
    assert "inputImage" in body
    assert "QFileInfo::exists" in body.split("inputImage", 1)[1]


def test_i2i_source_preview_retries_async_pixmap_load() -> None:
    """Use Last Image painted the chip but canvas said no source — async load returns false once."""
    body = definition_body("refreshPreview", qualifier="ImageGenerationPage")
    assert "Loading source image" in body
    after = body.split("Loading source image", 1)[1][:500]
    assert "schedulePreviewRefresh" in after


def test_i2v_page_remaps_t2v_expert_filenames() -> None:
    """Live 2026-09-09: I2V Auto kept wan2.2_t2v_* so the keyframe was ignored."""
    video = (ROOT / "qt_ui" / "ImageGenerationPage_video.cpp").read_text(encoding="utf-8")
    assert "remapWanTaskVariantPath" in video
    assert "_t2v_" in video and "_i2v_" in video
    body = definition_body("setSelectedModel", qualifier="ImageGenerationPage")
    assert "remapWanTaskVariantPath" in body


def test_video_component_scan_includes_extra_model_roots() -> None:
    """I2V T3 missing umt5/vae: populateVideoComponentControls only scanned modelsRootDir_."""
    body = definition_body("populateVideoComponentControls", qualifier="ImageGenerationPage")
    assert "scannableModelsRoots" in body


def test_video_component_scan_includes_selected_checkpoint_library() -> None:
    """Live I2V T3: umt5 lives next to D: wan i2v, modelsRootDir_ is F:, extra roots are F:."""
    body = definition_body("populateVideoComponentControls", qualifier="ImageGenerationPage")
    assert "modelsLibraryRootFromSelected" in body


def test_ltx_family_select_swaps_wan_primary() -> None:
    """Live 2026-09-10: LTX tab said Ready while primary stayed wan2.2_t2v_*."""
    video = (ROOT / "qt_ui" / "ImageGenerationPage_video.cpp").read_text(encoding="utf-8")
    assert "applyVideoFamilyCheckpointIfNeeded" in video
    page = (ROOT / "qt_ui" / "ImageGenerationPage.cpp").read_text(encoding="utf-8")
    after = page.split("videoFamilyCombo_", 1)[1]
    assert "applyVideoFamilyCheckpointIfNeeded" in after


def test_video_choices_include_ltx_text_encoder_loader() -> None:
    """LTX resolver looks at LTXAVTextEncoderLoader, not CLIPLoader — empty choices -> T3."""
    body = definition_body("buildVideoComponentChoicesForResolver", qualifier="ImageGenerationPage")
    assert "LTXAVTextEncoderLoader" in body


def test_video_companion_override_ignored_if_not_in_valid_options() -> None:
    """Live 2026-09-09: I2V remapped to i2v experts but stack sidecar clip_l / junk VAE won over umt5."""
    body = definition_body("applyVideoAutoPopulateToCombos", qualifier="ImageGenerationPage")
    assert "overrideValid" in body


def test_manual_video_combo_clears_t3_missing() -> None:
    """Live 2026-09-10: Gemma was on the Text combo, T3 still said missing text_encoder, Generate no-op."""
    body = definition_body("applyVideoComponentOverridesToSelectedStack", qualifier="ImageGenerationPage")
    assert "videoMissingRequiredComponents_" in body
    assert "removeAll" in body


def test_studio_model_picker_scans_extra_model_roots() -> None:
    """Comic Choose checkpoint listed 128 D: files and 0 for krea2_turbo on F:."""
    for qualifier in ("ComicStudioPage", "CharacterStudioPage", "ConceptReferencePage"):
        body = definition_body("pickModel", qualifier=qualifier)
        assert "scannableModelsRoots" in body, qualifier
        assert "extraModelsRootsFromSettings" in body, qualifier


def test_dataset_first_run_canvas_and_prompt_are_generateable() -> None:
    """Live 2026-09-10: Generate Dataset said 'Add at least one prompt' while the box
    showed a golden-hour line, then would have said choose a canvas — both were
    placeholder / special-value 0, not values Generate reads."""
    page = (ROOT / "qt_ui" / "DatasetGenerationPage.cpp").read_text(encoding="utf-8")
    ctor = page.split("void DatasetGenerationPage::buildUi", 1)[1].split(
        "void DatasetGenerationPage::applyTheme", 1
    )[0]
    after_prompts = ctor.split("datasetPromptsEdit_", 1)[1]
    assert "setPlainText" in after_prompts[:1200]
    assert "datasetWidthSpin_->setValue(0)" not in ctor
    assert "datasetHeightSpin_->setValue(0)" not in ctor


def test_dataset_takes_t2i_canvas_when_dataset_size_is_zero() -> None:
    """Dataset payload always inserts width/height, so takeIfMissing never fills from T2I."""
    main = MAIN.read_text(encoding="utf-8")
    body = main.split("generateDatasetRequested", 1)[1].split("openModelsRequested", 1)[0]
    assert "takeSizeIfUnset" in body
    assert 'takeSizeIfUnset("width")' in body
    assert 'takeSizeIfUnset("height")' in body


def test_dataset_submit_copies_extra_model_roots() -> None:
    """Dataset payload omits extras. Fan-out T2I then misses F:/D: on Flux peek."""
    main = MAIN.read_text(encoding="utf-8")
    body = main.split("generateDatasetRequested", 1)[1].split("openModelsRequested", 1)[0]
    assert 'takeIfMissing("models_root")' in body
    assert 'takeIfMissing("extra_models_roots")' in body


def test_dataset_simple_hides_backend_canvas_knobs() -> None:
    """T7 Dataset: robust settings — Simple is prompts+count+dest, not seed/canvas."""
    header = (ROOT / "qt_ui" / "DatasetGenerationPage.h").read_text(encoding="utf-8")
    page = (ROOT / "qt_ui" / "DatasetGenerationPage.cpp").read_text(encoding="utf-8")
    assert "void updateDisclosure(bool advanced)" in header
    assert "advancedBlock_" in page
    assert "setVisible(advanced)" in page
    main = MAIN.read_text(encoding="utf-8")
    ds = main.split('registerDeferredPage(QStringLiteral("dataset")', 1)[1].split(
        "pageTrace", 1
    )[0]
    assert "updateDisclosure" in ds


def test_train_page_simple_advanced_family_recipe_and_dataset_source() -> None:
    """T1: Train was a Sohya launcher. Simple needs family+dataset; Advanced reveals rank/batch."""
    page = (ROOT / "qt_ui" / "TrainPage.cpp").read_text(encoding="utf-8")
    header = (ROOT / "qt_ui" / "TrainPage.h").read_text(encoding="utf-8")
    assert "void updateDisclosure(bool advanced)" in header
    assert "train/lastDatasetRoot" in page
    assert "krea2" in page and "sdxl" in page and "flux" in page and "wan" in page and "ltx" in page
    assert "rankSpin_" in page and "batchSpin_" in page
    assert "advancedBlock_" in page
    assert "setVisible(advanced)" in page
    dataset = (ROOT / "qt_ui" / "DatasetGenerationPage.cpp").read_text(encoding="utf-8")
    assert "train/lastDatasetRoot" in dataset
    main = MAIN.read_text(encoding="utf-8")
    train = main.split('registerDeferredPage(QStringLiteral("train")', 1)[1].split(
        "pageTrace", 1
    )[0]
    assert "updateDisclosure" in train


def test_models_page_drop_imports_without_renaming() -> None:
    """T3: Models had paste-link only. Drop a local weight or a Civitai/HF URL."""
    header = (ROOT / "qt_ui" / "ModelManagerPage.h").read_text(encoding="utf-8")
    page = (ROOT / "qt_ui" / "ModelManagerPage.cpp").read_text(encoding="utf-8")
    assert "void dragEnterEvent" in header
    assert "void dropEvent" in header
    assert "handleDroppedReference" in page
    assert "QFile::copy" in page
    assert "fileName()" in page
    assert "downloadModelRequested" in page
    assert "never rewritten" in header


def test_simple_restore_does_not_clobber_operating_point() -> None:
    """Live T7: restoreSnapshot wrote last-chose steps after OP apply, so Simple was not OP."""
    restore = definition_body("restoreSnapshot", qualifier="ImageGenerationPage")
    assert "ui/advancedMode" in restore
    assert "applySimpleOperatingPointDefaults" in restore
    disclose = definition_body("updateDisclosure", qualifier="ImageGenerationPage")
    assert "applySimpleOperatingPointDefaults" in disclose


def test_backend_launchers_strip_foreign_pythonpath() -> None:
    """Hermes PYTHONPATH leaks into Start-Process and numpy ABI-crashes the worker."""
    for name in ("start_backend.ps1", "start_comfy.ps1"):
        text = (ROOT / "scripts" / "dev" / name).read_text(encoding="utf-8")
        start = text.index("$proc = Start-Process")
        prelude = text[:start]
        assert "Remove-Item Env:PYTHONPATH" in prelude, name
        assert "Remove-Item Env:PYTHONHOME" in prelude, name
        assert "PYTHONNOUSERSITE" in prelude, name

    ui = (ROOT / "scripts" / "dev" / "run_ui.ps1").read_text(encoding="utf-8")
    compile_at = ui.index("Invoke-PythonSyntaxCheck -PythonExe")
    prelude = ui[:compile_at]
    assert "Remove-Item Env:PYTHONPATH" in prelude
    assert "Remove-Item Env:PYTHONHOME" in prelude

    for name in ("rebuild_ui.ps1", "run_backend_checks.ps1"):
        text = (ROOT / "scripts" / "dev" / name).read_text(encoding="utf-8")
        py = text.index("python -m py_compile")
        prelude = text[:py]
        assert "Remove-Item Env:PYTHONPATH" in prelude, name
        assert "Remove-Item Env:PYTHONHOME" in prelude, name


def test_generation_request_sends_extra_model_roots() -> None:
    """Flux peek reads extra_models_roots. Cockpit never sent the key."""
    builder = (ROOT / "qt_ui" / "generation" / "GenerationRequestBuilder.cpp").read_text(
        encoding="utf-8"
    )
    assert 'payload.insert(QStringLiteral("extra_models_roots")' in builder
    header = (ROOT / "qt_ui" / "generation" / "GenerationRequestBuilder.h").read_text(
        encoding="utf-8"
    )
    assert "extraModelsRoots" in header
    page = (ROOT / "qt_ui" / "ImageGenerationPage.cpp").read_text(encoding="utf-8")
    assert "extraModelsRootsFromSettings" in page
    assert "draft.extraModelsRoots" in page


def test_worker_client_qprocess_strips_foreign_pythonpath() -> None:
    """Hermes PYTHONPATH ABI-crashes worker_client.py the same as the worker service."""
    for name, qualifier in (
        ("sendWorkerRequestAsync", "MainWindow"),
        ("sendWorkerRequestAsync", "ManagerPage"),
        ("openWorkflowImportDialog", "MainWindow"),
        ("discoverComfyWorkflows", "WorkflowLibraryPage"),
        ("startWorkflowLifecycleCommand", "WorkflowLibraryPage"),
        ("validateSelectedLtxRequeueDraft", "HistoryPage"),
        ("submitSelectedLtxRequeueDraft", "HistoryPage"),
    ):
        body = definition_body(name, qualifier=qualifier)
        env_at = body.index("QProcessEnvironment")
        env_block = body[env_at:]
        label = f"{qualifier}::{name}"
        assert 'remove(QStringLiteral("PYTHONPATH"))' in env_block, label
        assert 'remove(QStringLiteral("PYTHONHOME"))' in env_block, label
        assert "PYTHONNOUSERSITE" in env_block, label

    runtime = MAIN.read_text(encoding="utf-8")
    blocking = runtime.split("QJsonObject sendWorkerRequestForRuntime", 1)[1].split(
        "process.start();", 1
    )[0]
    assert 'remove(QStringLiteral("PYTHONPATH"))' in blocking
    assert 'remove(QStringLiteral("PYTHONHOME"))' in blocking
    assert "PYTHONNOUSERSITE" in blocking


def test_sage_probe_strips_foreign_pythonpath() -> None:
    """Hermes PYTHONPATH ABI-crashes `import sageattention`; the probe then skips sage."""
    body = definition_body("sageAttentionAvailable")
    assert 'remove(QStringLiteral("PYTHONPATH"))' in body
    assert 'remove(QStringLiteral("PYTHONHOME"))' in body
    assert "PYTHONNOUSERSITE" in body
