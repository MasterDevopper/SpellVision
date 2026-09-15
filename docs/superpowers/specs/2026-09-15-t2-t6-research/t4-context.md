# T4 context (explorer report, 2026-09-14)

## Launch policy
- python/comfy_launch_policy.py: SAGE_FLAG :62, SPELLVISION_COMFY_ATTENTION :52, sageattention_available :149 (probe in Comfy venv, cached), resolve_attention_backend :178 (explicit-missing RuntimeError :205-212; unset+avail sage :216; unset+missing SDPA warn :217-223). VRAM_HEADROOM_ENV_VAR / RESERVE_VRAM_FLAG :98-99; INERT_UNDER_DYNAMIC_VRAM :109-118 refuses --lowvram/--novram/--highvram/--gpu-only/--cpu. Measured table :76-97. REQUIRED_ENV PYTHONUTF8/PYTHONIOENCODING :121-124; launch_env :292.
- Launch sites: start_comfy.ps1:200-286 (sage :238, reserve :277, UTF8 :290-291); comfy_bootstrap.py:273-299 -> comfy_runtime_manager.py:273-306 (sage yes; reserve param NOT forwarded — bootstrap_comfy_runtime :302-311 has no vram_headroom; Popen no env= :299-306 so PYTHONUTF8 dropped); MainWindow.cpp:1388-1401 (RuntimeProfile.cpp:311-347 sage, :349-380 reserve, UTF8 MainWindow.cpp:1333).
- Qt sage probe async, fails OPEN to SDPA on cache miss RuntimeProfile.cpp:269-308 (0910564, 0e8d4fb :288-290) -> first cold launch runs SDPA silently.
- --fast / torch.compile: not shipped anywhere in python/ qt_ui/ scripts/.

## Recorded today
- Runtime page ManagerPage.cpp:240-330 rows: manager/runtime state, version (:293), node index/summary, cache source, last checked, workers. No attention/argv/aimdo/triton row. zero 'optimization' hits in qt_ui/.
- system_stats probed comfy_runtime_manager.py:90,236; vram.py:146; MainWindow.cpp:5677; Gen3DPage.cpp:330; ManagerPage.cpp:628 — only version+VRAM read.
- T4 evidence doc-only: 55_t7_ship_walkthrough.html:384-403 (krea2 sage 120.72 vs SDPA 124.01, seed 7, 1024x1024, 52/3.5, restart between arms), assets t4_sage_ab.png/t4_sdpa_ab.png; :238 PARTIAL; 57:287. Produced BY HAND — no harness.
- Nearest rigs: scripts/dev/measure_vram_headroom.ps1 (Stop/Start-Comfy loop over --reserve-vram :17-33, hardcodes sage :25, varies seed :41-46, restores :63); measure_video_upscale_render.py (Peak sampler + seconds); measure_model_matrix.py:68 seconds per krea2 variant, no flag toggle.

## Seconds already captured
- worker_metadata.py:705 generation_time_sec, :706 steps_per_sec, :707 cache_hit via build_metadata_payload :633. Also comfy_prompt_client.py:1188, image_runners.py:917,1110, native_runners.py:211,409,660,785. Job record worker_service_state.py:220,490. Queue timestamps worker_queue.py:58-63 (:595,798,896,911,931). TeaCache provenance worker_service.py:1807-1829 + video_acceleration block.
- generation_time_sec NEVER shown in qt_ui/.

## fp16 / diffusers
- memory_optimization.py: build_paired_pipelines, MemoryProfile :134-153, auto_select_memory_profile :177, apply_attention_optimizations :263-350 (vae tiling default False :267, xformers attempt :343). CAST_FP32_TO_FP16 constant worker_runtime.py:23 (+worker_service.py:1133), passed :703 — not per-request. Diffusers route only (family_capability.py:106 sdxl/stable_diffusion/sd2; lineage :100 pony/illustrious).

## VAE tiling / wrapper attention / caches
- comfy_graph_helpers.py:777-830 vae_decode_node (enable_vae_tiling req, default_tiled family, fallback :813-818, _TILED_DECODE_DEFAULTS :787; "no number" comment :783-786). hunyuan/mochi default_tiled True native_video_graphs.py:2199,2285; wan/ltx False :901,1092; image families none native_image_graphs.py:343,428,516,607,702,852,988; diffusers gate image_runners.py:625.
- _wrapper_attention_mode native_video_graphs.py:1877-1889 default "sageattn", request attention_mode; used :1151 (Wan wrapper), :2088 (HyVideoModelLoader). Doc 25 S5 Hunyuan 129f 317s->237s.
- PrunaVAED CLAUDE.md:127 only. MagCache removed (CLAUDE.md:216, docs/pipeline/comfy_baselines/README.md:258-265,321); wrapper-topology TeaCache guard worker_service.py:1757-1774.

## Families
- model_registry.py:52-260: stable_diffusion, sdxl, pony, illustrious, sd3, flux, pixart, lumina, z_image, anima, krea2, wan, ltx, hunyuan_video, cogvideox, mochi. No qwen family.
- native image builders native_image_graphs.py:43 {flux,pixart,lumina,z_image,anima,krea2,sd3}. Diffusers {sdxl,stable_diffusion,sd2} + lineage. Template {ltx}. Video contracts video_family_contracts.py:65-195 wan, ltx, flux3, hunyuan_video, cogvideox, mochi, workflow. Pseudo {flux3, workflow} family_capability.py:149.
- OP acceleration slot family_operating_points.py:87-330 (wan teacache balanced :102).

## Restart
- ManagerPage.cpp:255 Restart -> :474 -> restartComfyRuntime :987-1002 -> restart_comfy_runtime (180s) -> worker_tcp.py:771-772 -> worker_service.py:1642-1648 (only comfy_root, libraries, startup_timeout_sec) -> ComfyRuntimeManager.restart :426 -> start :243 -> bootstrap_comfy_runtime(apply_launch_policy=True) :273-283. Attention/headroom from worker os.environ only. build_launch_command extra_args no caller (comfy_bootstrap.py:290-293). restart_comfy_runtime in worker_command_audience.py:52.

## Gaps
1 no in-app A/B (restart_comfy_runtime needs attention/vram_headroom -> bootstrap -> build_launch_command). 2 no committed harness. 3 no optimization provenance in sidecar. 4 seconds invisible in UI. 5 no Optimizations panel. 6 Qt first launch races to SDPA. 7 worker launch drops PYTHONUTF8 + cannot pass reserve. 8 untimed: Wan/LTX sage vs unopt, VAE tiling, fp16 cast, wrapper attention_mode, TeaCache (node not installed). 9 matrix rows ~15:1 vs evidence.

## CORRECTION (explorer follow-up)
- T4 arms are in app state: runtime/state/job_archive.json entries[].result.generation_time_sec — t4_sage_queue_3d2236390c95 159.27s (cold, 00:56), t4_sage_queue_f0c81eedff84 120.72s, t4_sdpa_queue_44896cfc9aca 124.01s; all seed 7 / 52 / 3.5 / 1024². Doc 55 quotes the second sage run, never mentions the 159s first arm -> published ~3% delta is SMALLER than cold-load variance on the same config. Writer worker_service.py:924-931 _persist_job_archive_unlocked, MAX_ARCHIVED_JOBS=200 :197 FIFO :929-932.
- runtime/state/history/video_history.jsonl append-only (105 rows, images too) written worker_metadata.py:503-513; 59 keys incl generation_time_sec, seed/steps/cfg/w/h, model_name, backend_name, created_at, finished_at. All three T4 rows present.
- Revised gap 3/4: stopwatch exists twice; NO key records which optimization produced the number (zero of 59 keys match atten|sage|sdpa|accel|teacache|tiling|fp16|comfy). Arms distinguishable only by human-typed filename. Load-bearing gap = provenance block next to generation_time_sec at worker_metadata.py:705. Retention: archive evicts FIFO at 200; JSONL permanent.
- Harness discipline: an A/B needs a WARM arm on each side (discard first run per config) or explicit cold/warm labelling.
