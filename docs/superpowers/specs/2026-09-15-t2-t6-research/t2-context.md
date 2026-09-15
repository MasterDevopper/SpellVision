# T2 context (explorer report, 2026-09-14)

## Drop entry points
- No window-level drop target: MainWindow has no dragEnterEvent/dropEvent/setAcceptDrops.
- Generic widget: qt_ui/widgets/DropTargetFrame.cpp:12-64 (any local-file URL, first file, no ext filter).
- Cockpit page-wide: ImageGenerationPage.cpp:498 (setAcceptDrops), events :2899/:2918 -> acceptDroppedLocalFile.
- Prompt-row 84px chip :646 (T2I/I2I/I2V only, :644). Input Image card :776 (image only). Canvas :1102-1110 (all 4 families since 126c655). Model-stack card "Drop Comfy workflow .json" :1761-1772 -> acceptDroppedWorkflow.
- Router acceptDroppedLocalFile ImageGenerationPage.cpp:2887-2897: .json -> acceptDroppedWorkflow; T2V ignores stills; else setInputImagePath.
- acceptDroppedWorkflow ImageGenerationPage_catalog.cpp:822-840: pendingWorkflowPath_, runWorkflowButton_, emit workflowFileDropped.
- Prompt editors setAcceptDrops(false) (:718, :745; studios/Inspire/Dataset likewise).
- Flows page (WorkflowLibraryPage), Home, History, Settings: NO drop support.

## Import path
- MainWindow::connectGenerationPage workflowFileDropped lambda MainWindow.cpp:2631-2817 -> {command:"import_workflow", source, auto_apply_node_deps:false, auto_apply_model_deps:false}.
- worker_tcp.py:706 -> workflow_library_commands.handle_import_workflow_command (python/workflow_library_commands.py:28-137): dest root, comfy_root, keys, fetch URL (:64-80), live /object_info classes+aliases (:84-92), workflow_importer.import_workflow (python/workflow_importer.py:57-193).
- Writes <dest>/<slug>/{workflow.json, scan_report.json, profile.json, dependency_plan.json{node_plan,model_plan}, dependency_apply_result.json}.
- WorkflowImportResult (:36-51): ok, import_slug, inferred_task_command, inferred_media_type, artifacts, capability_report, supported_modes, classification_confidence, missing_custom_nodes, model_references, dependency_plan, dependency_apply_result, warnings, errors. NO launch readiness.
- Profile: comfy_slot_mapper.WorkflowProfile python/comfy_slot_mapper.py:34-138.
- Drop-path draft (MainWindow.cpp:2678-2790): source_name, source_profile_path, source_workflow_path, workflow_path, safe_to_submit=false HARDCODED (:2690), warnings. Ignores inferred_task_command / media_type / capability_report / supported_modes. Stub draft on failure (:2656-2664).
- Consumer ImageGenerationPage::applyWorkflowDraft ImageGenerationPage.cpp:2738-2854: prompt/neg, preset Custom, checkpoint via trySetSelectedModelByCandidate, sampler/scheduler exact, steps/cfg/seed/w/h/frames/fps, input_image (:2804), LoRA stack, workflowDraftBlocking_. State ImageGenerationPage.h:661-668; payload ImageGenerationPage.cpp:354-359 -> GenerationRequestBuilder.cpp:36-42 (workflow_profile, workflow_draft_source, workflow_profile_path, workflow_path, compiled_prompt_path, workflow_backend, workflow_media_type). Cleared ImageGenerationPage_catalog.cpp:1891-1898; gates :1750, :1689.
- RICH draft only in WorkflowLibraryPage::buildReusableDraft (qt_ui/WorkflowLibraryPage.cpp:2709-2902) from compiled prompt; refuses v2v/audio/3d (:2716-2723); Apply -> workflowDraftRequested (:1173-1188).

## WorkflowDownloadDialog
- qt_ui/workflows/WorkflowDownloadDialog.cpp:13-110; constructed only in drop path MainWindow.cpp:2756. Missing nodes from node_plan.dependencies minus already_installed/present (:2692-2720) else missing_custom_nodes; models from model_plan.install_actions minus already_present, host sniff -> needsCivitai/needsHf (:2721-2748).
- Accept (:2758-2786): SecureCredentialStore::setCredential(civitai_api_key/hf_token) then RE-SENDS import_workflow with auto_apply_* true + keys (download lane = importer: apply_node_install_plan python/node_dependency_resolver.py:239 bootstraps ComfyUI-Manager; apply_model_install_plan). Then workflowsPage_->refreshLibrary().
- Credentials: qt_ui/shell/SecureCredentialStore.cpp (DPAPI, entropy SpellVision.credentials.v2, keys hf_token/civitai_api_key/worker_integration_token :30); python/credential_store.py; SettingsPage.cpp:169-199.

## Classification
- python/workflow_scanner.py:860-1033: video sources/cores (_VIDEO_* :755-761), outputs; decision by OUTPUT (:964-989): v2v/i2v/t2v/i2i/t2i; confidence :996-1033; -> inferred_task_command/inferred_media_type/capability_report.primary_task (:380-388).
- C++: WorkflowLibraryPage::applyCapabilityReport :2554-2582 (modeId=primary_task, user_task_override :2098); HomePage.cpp:128-154 inferModeFromWorkflowProfile (substring fallback -> t2i); WorkflowLaunchController::resolveDraftModeId qt_ui/workflows/WorkflowLaunchController.cpp:36-60 (used only by MainWindow::openWorkflowDraft :2594-2620 <- Flows Apply :2177).
- Flows Launch onLaunchClicked :1003-1021 needs ReadinessState::Ready -> launchWorkflowRequested -> MainWindow::launchWorkflowProfileWithModel :3615-3734 (no page switch; borrows model/LoRA from cockpit of task_command :3668-3673) -> queue. Worker: worker_service.dispatch_generation python/worker_service.py:364-408 -> run_comfy_workflow when request_has_workflow_binding. Overrides comfy_prompt_client._apply_common_comfy_overrides :189-206; run_comfy_workflow :1013-1030.

## Tests
- tests/test_workflow_download_dialog.py (text greps). tests/test_first_run_honesty.py:545-593 (drops), :427-438. tests/test_worker_workflow_import.py (live). test_workflow_architecture_inference.py, test_workflow_url_import.py, test_workflow_zip_import.py, test_missing_node_detection.py, test_workflow_pack_resolver.py, test_workflow_compile_command.py. tests/cpp: none for drops.

## Navigation API
- MainWindow::switchToMode(modeId) (:1524 rail, :5060 palette). ensureGenerationPageBuilt(modeId) first (:2583-2591, :2603). isGenerationMode().
- Handoffs build->apply->switch: handleHomeLaunchRequest :2574-2592; openWorkflowDraft :2594-2620; sendToGenerationRequested :1730-1741 (applyWorkflowDraft + useImageAsInput + switchToMode); prepForI2IRequested :2818-2830; Home gallery :2135-2159; sendModelToGeneration. Rail spec ShellNavigationController.h:17-36.

## Gaps
1. No anywhere-in-window drop. 2. No routing on drop (lands on the page dropped on). 3. Classification thrown away by the drop draft. 4. Drop draft carries paths only; rich extraction needs compile_workflow_prompt which drop never calls. 5. Run workflow does not run (safe_to_submit=false). 6. Importer has no readiness; Flows' check_workflow_launch_readiness separate. 7. No page for v2v/audio/unknown. 8. Three divergent C++ classifiers. 9. No C++ tests; T2 pytest are source greps.
