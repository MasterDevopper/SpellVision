# T6 context (explorer report, 2026-09-14)

## Runtime page surface (ManagerPage)
- workersLabel_ static QLabel, endpoints hardcoded literal text ManagerPage.cpp:289-291, :329; updateWorkersLabel :611-623 (online/offline/checking/fail-closed + honesty clause).
- probeSpellNodeWorker :625-640: raw QNAM GET http://192.168.1.127:8188/system_stats, 2500ms, host is a C++ literal (not setting/RuntimeProfile). Fired from refreshStatus :855. localHealthy scraped from runtimeStateLabel_->text().contains("healthy=yes") :635.
- Consent/share: persistDualPcSettings :1527-1533 QSettings runtime/dualPcConsent, runtime/dualPcShareFolder; restore :1536-1547; browse :1549-1561; updateDualPcEnableState :1562-1568. dualPcShareFolder has NO consumer.
- enableDistributedPack :1569-1622: refuse without consent / missing dir; GET /queue refuse if queue_running non-empty :1598-1605; sends install_custom_node {package_name ComfyUI-Distributed, repo_url robertvoy, install_method archive} :1607-1612; no restart (log only :1606). Installs into MASTER custom_nodes; install_custom_node is in LOCAL_INSTALL_COMMANDS (worker_tcp.py:123-126) and refused for remote COMFY_API_URL (:739-754). Pack can never reach SpellNode from this button.

## Worker endpoint model (strong)
- python/comfy_endpoint.py: per-request resolver comfy_endpoint(req): req.comfy_api_url/comfy_endpoint -> comfy_host+comfy_port -> COMFY_API_URL -> SPELLVISION_COMFY_URL -> SPELLVISION_COMFY_ENDPOINT -> SPELLVISION_COMFY_HOST/PORT -> 127.0.0.1:8188. is_local_endpoint via ipaddress.is_loopback.
- Honored at comfy_prompt_client.py:1047-1051, native_runners.py:100-105, :292-297. ZERO producers in qt_ui/. C++ RuntimeProfile::comfyHost/comfyPort (RuntimeProfile.h:21, .cpp:581-620), comfyEndpointIsLocal :528-540 (probes only).
- comfy_prompt_client API endpoint-parameterized: _submit_comfy_prompt :358-399; _poll_comfy_history :473-552; _download_comfy_asset :696-722; _upload_comfy_image :942-1004; _comfy_object_info cached per endpoint _OBJECT_INFO_CACHE[api_url] :828-842; _http_get_json :845-877; request_comfy_free_memory / wait_until_comfy_queue_idle take api_url (:49-90) but callers omit it: worker_runtime.py:435, :436, :648 (cross-firing /free trap).
- Remote output locality solved: comfy_root.local_output_is_authoritative :195-204, warning :183-192; tests/test_remote_endpoint_output_locality.py (real 2026-09-01 run vs 3090 Ti: 904-class object_info, PNG via /view). Sweep R18 local-output-only-for-a-local-endpoint tests/sweeps/rules.py:1268-1360.

## Existing remote tooling (bypasses worker)
- runtime/night_run.py (API argv, /system_stats health, one runner per endpoint) -> scripts/dev/generate_wrought_dataset.py --api (:491-492 names spellnode) -> scripts/dev/wrought_comfy.py Endpoint dataclass :60-91 (submit/wait/fetch/free_ram_gb). Productized path never ran a job on SpellNode.

## Model availability
- python/comfy_extra_model_paths.py writes LOCAL yaml managed block; invoked _sync_comfy_extra_model_paths in handle_ensure_comfy_runtime_command worker_service.py:1609-1621 (local restart on change). No remote variant. Node CIFS //192.168.1.182/AI_ASSETS_models hangs when host down (Doc 54:98).
- Per-endpoint availability mechanism exists: model_resolution_commands.installed_from_object_info :44-62 (endpoint resolved :251-264, catalog_source object_info :281-283); comfy_prompt_client._resolve_graph_model_names :321-341.

## Queue/concurrency
- worker_queue.QueueManager._start_next_locked :583-600 single active_queue_item_id; _finalize_queue_item :602-607. QueueItem :68-96 no endpoint field.
- worker_service.get_comfy_runtime_manager :1522-1543 single global COMFY_RUNTIME_MANAGER rebuilt on host/port change; ComfyRuntimeManager.__init__ comfy_runtime_manager.py:34-46 bakes endpoint. run_comfy_workflow :1041 calls ensure_comfy_runtime unconditionally (would try to start LOCAL process for remote job).
- worker_runtime.prepare_runtime_for_request :394-476 transition keyed by job kind vs module-global caches; video_runtime_truth_for_snapshot :269-305 compares cached vs current endpoint but comfy_runtime_identity_snapshot reads ambient comfy_endpoint() :243 -> alternating endpoints thrash.

## Tests
- tests/test_runtime_identity.py:104-128 three T6 text greps. tests/test_remote_endpoint_guard.py (LOCAL_INSTALL_COMMANDS :27-33). tests/test_remote_endpoint_output_locality.py. tests/test_comfy_endpoint.py, test_comfy_endpoint_is_one_rule_across_languages.py, tests/cpp/test_comfy_endpoint_profile.cpp (:73,:98,:145). test_runtime_probe.cpp unrelated. No test for probeSpellNodeWorker.

## Router needs
1 worker registry as data (QSettings) replacing literals. 2 C++ producer sets req.comfy_api_url. 3 per-endpoint queue lanes (QueueItem.endpoint, active map). 4 per-endpoint runtime manager / short-circuit ensure_comfy_runtime for non-local. 5 pass api_url to /free + idle waits; key runtime caches by endpoint. 6 pre-dispatch capability gate via installed_from_object_info on candidate endpoint. 7 remote pack install stays fail-closed (provision out-of-band). 8 output via /view; resolve_comfy_output_path :631, unlink_comfy_side_save_if_copied :593 need locality. 9 model parity on node (share or replicate or restrict by object_info). 10 replace label-text health scrape.
