# T6 web research (2026-09-15) — whole-job fan-out to SpellNode

[V]=verified against cited source, [I]=inferred, [U]=unverified.

## ComfyUI-Distributed (robertvoy) — 1.4.7, last commit 2026-07-12, Apache-2.0 [V]
- Master+workers all run the pack; workers `--listen --enable-cors-header`, master `--enable-cors-header`.
- Nodes: Distributed Seed, Distributed Collector (load_balance), USDU Distributed, Image Batch Divider, Audio Segment Divider, Distributed Value, Distributed Model Name.
- Dispatch is server-side Python (api/queue_orchestration.py, queue_request.py). `POST /distributed/queue` {prompt, enabled_worker_ids, client_id, workflow?, delegate_master?} -> {prompt_id, worker_count}. Per-worker: convert_paths_for_platform, prune_prompt_for_worker, apply_participant_overrides, sync_worker_media, dispatch over /distributed/worker_ws or POST /prompt. Results: worker POSTs master /distributed/job_complete (base64 PNG). Health probe GET /prompt.
- Works from external API client: YES but graph MUST contain DistributedCollector (+Seed) else "revert to standard master queuing" [V]. Semantics = same graph on N participants with different seeds; single remote = load_balance + delegate_master.
- Fail-closed: NO [V]. No reachable worker + delegate_master -> "Falling back to master execution" silently. Issue #48 master-free mode still open. Must detect worker_count==0 and cancel.
- Models must exist on each worker [I strong]; no availability check [V absence]. No auth [V]. Open issues #74 #80 #88 #89 orchestration bugs, #70 rgthree conflict.

## NetDist (city96) — last commit 2024-02-15, unmaintained [V]
- RemoteQueueSimple hidden PROMPT input (browser-independent) -> POST remote /prompt; FetchRemote polls /history; substitutes BLACK IMAGE on failure (silent) [V]. Seed jank per README.

## Others
- comfyui-mesh: model-split only (FLUX.2, LTX 2.3 22B), not routing [V]. MultiGPU_WorkUnits same-box [V]. --multi-user = per-user storage only [V].
- SwarmUI backends [V]: N "ComfyUI API" backends by address; first compatible claimed (model requirement check, MaxUsages, CurrentModelName reuse); models need identical filename+folder on all machines; down -> ERRORED, AllowIdle; enum DISABLED/ERRORED/WAITING/LOADING/IDLE/RUNNING. = Design B shape.
- Krita AI / StabilityMatrix / Invoke / comfy-cli: single endpoint [V/I]. Comfy Deploy / RunComfy: control-plane queue in front of N instances, POST /prompt, poll/webhook [V].

## Model availability on Linux worker
- mount.cifs: hard hangs forever; soft returns errors but reconnect wait = 3*echo_interval (default 60s -> ~180s) [V]. Comfy folder_paths walks model dirs at /object_info -> dead share stalls object_info [I].
- fstab: `//master/AI_ASSETS/models /mnt/ai_models cifs credentials=…,ro,soft,echo_interval=10,noserverino,_netdev,nofail,noauto,x-systemd.automount,x-systemd.idle-timeout=300,x-systemd.mount-timeout=15,x-systemd.device-timeout=10,vers=3.1.1 0 0` [V options / I combo]. Even tuned, ls on dead mount blocks for timeout.
- Fail-closed node => local copies + sync manifest ("model present" property of the node) [I].
- Per-instance model list: GET /models, GET /models/{folder} (folder_paths.get_filename_list; 404 unknown) present since 2024-08/09 [V] -> in v0.34.0. /object_info combo equivalent (mind legacy/V3 combo split). Use /models/{folder} for cheap polling.

## 3090 Ti (sm_86) caveats
- supports_fp8_compute False (major 8 minor<9) -> fp8 stored, cast bf16 per layer; Flux dev fp8 ~26s vs 5090 5.5s [V]. --fast fp8_matrix_mult inert [I]. NVFP4 emulated (ours 12.94GB best cell). SageAttention sm_80 kernels ok, fp8 PV sm_89-only; 1.0.6 Triton fallback [V]. CUDA 13 keeps Ampere [V]. aimdo default on Win+Linux, --disable-dynamic-vram [V].
- Families: SDXL/Pony/Krea2-fp8/Flux-fp8 yes [V/I]; Wan 2.2 14B fp8 480p probably (24GB class documented) [I]; LTX 2.3 22B "probably with --reserve-vram + host RAM>=32GB" unproven (issue #12047 OOM pre-aimdo) [I]; Hunyuan/Mochi unavailable until gate render [I].

## Recommendation: B — SpellVision-native routing
| Criterion | A Distributed | B native | C NetDist |
| API submission | needs Collector+Seed in every graph | plain POST /prompt | node pairs |
| Fail-closed | NO (silent master fallback) | yes by construction | NO (black image) |
| Model honesty | none | /models/{folder} + object_info diff pre-dispatch | none |
| VRAM honesty | no capacity model | explicit per-endpoint capability table | none |
| Install | pack both boxes, CORS, config, WS | nothing on either Comfy | pack both, dead |
| Maintenance | single maintainer, 4 open orch bugs | ours, core routes stable since 2024 | abandoned |
Notes: endpoint registry {name, base_url, platform, families_allowed, measured_peaks}; health GET /system_stats (does not touch model dirs); readiness GET /models/{folder} per referenced model + node-contract diff; inputs /upload/image on target; outputs /view HTTP into local history; family gate on node starts SDXL/Flux/Krea2, video families only after render-proven gate. Distributed stays an OPTION later for tile/seed fan-out. Update Doc 54.

Sources: github robertvoy/ComfyUI-Distributed (+docs/comfyui-distributed-api.md, api/queue_orchestration.py, issues/48), city96/ComfyUI_NetDist nodes/simple.py, shootthesound/comfyui-mesh, docs.comfy.org MultiGPU_WorkUnits + comms_routes, Comfy-Org/ComfyUI server.py + cli_args.py + model_management.py, discussions 9002/12699, issue 12047, SwarmUI docs "Using More GPUs.md", krita-ai-diffusion wiki Cloud-GPU, comfydeploy blog, man mount.cifs / systemd.mount, Arch bbs 250650/222977, samba wiki, SageAttention issue 77, NVIDIA CUDA 13.0.1 notes.
