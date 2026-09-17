# W6 Endpoint Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Queue a whole generation job on the second machine, refuse honestly when it cannot run there, and never claim the two cards add up.

**Architecture:** SpellVision-native routing, not a ComfyUI extension. The worker already resolves its ComfyUI endpoint **per request** and already fetches outputs over HTTP; what is missing is anything that produces a non-local endpoint, a capability check before dispatch, and per-endpoint queue state. This wave supplies those three.

**Tech Stack:** C++17/Qt6, Python 3.12 stdlib, ComfyUI's own HTTP API. No new dependencies, no ComfyUI custom nodes.

**Spec:** `docs/superpowers/specs/2026-09-15-t2-t6-completion-design.md` §6. **Two research files are load-bearing:** `docs/superpowers/specs/2026-09-15-t2-t6-research/t6-context.md` (what the tree can do today, file:line) and `t6-research.md` (the 2026 landscape and why this design was chosen over the alternatives). Owner requirement: Doc 54 §1 T6 — checkboxes must say when they will download something, a share is mounted only with explicit consent, and the location lives in Settings.

## Global Constraints

- C++17, Qt 6.10.2; Python 3.12 **stdlib only**. Modules under 300 lines.
- **`Stop-Process -Name SpellVision` before every build** (`LNK1168`). `ctest` needs `-C Debug`. Record the gate count before you start; `shell_layout` and `test_godfile_split` are pre-existing failures.
- **Before any build, check nothing is measuring** (`MSBuild.exe`/`cl.exe`/`link.exe` and a running `measure_optimizations.py`) — a build during a measurement contaminated a full run once already.
- A new worker command trips four ratchets: audience, wire-type registry, protocol-doc counts, `ARCHITECTURE.md` + the counts block.
- Sweep rule **R18 `local-output-only-for-a-local-endpoint`** already exists and will fire on a mistake here. Do not baseline it; it is the guard that makes remote output correct.
- **No `Co-Authored-By` trailer.**
- **Never claim VRAM pools.** 32 GB and 24 GB are two machines, not 56 GB, and the honesty line already on the Runtime page says so.

## Why this shape, and not the obvious one

Doc 54 picked **ComfyUI-Distributed**. The 2026 research overturned that, and the reason is decisive for this project:

- With no reachable worker, Distributed **silently falls back to running the job on the master** (`queue_orchestration.py`, and its master-free mode is an open feature request). The owner's requirement is fail-closed. A router that quietly runs the job somewhere else is the opposite of one.
- It requires every graph to carry its `Distributed Collector` and `Distributed Seed` nodes, so SpellVision would have to inject them into every graph it builds.
- Its semantics are *parallel batch* — the same graph on N participants with different seeds — not *route this job there*.
- **NetDist** substitutes a **black image** when a fetch fails, and its last commit was February 2024.

Meanwhile the pieces for native routing are already in the tree. `python/comfy_endpoint.py` resolves the endpoint **per request** (`req["comfy_api_url"]` first), `comfy_prompt_client` parameterises every call on `api_url` and caches `/object_info` per endpoint, and `tests/test_remote_endpoint_output_locality.py` records a **real 2026-09-01 run against the 3090 Ti box**: 904-class `/object_info` over the wire, graph accepted, a 1.28 MB PNG fetched back through `/view`, first try. Only disk-reading paths were wrong, and sweep rule R18 now guards those.

**Nothing produces a non-local endpoint.** A repo-wide grep finds zero sites in `qt_ui/` that set `comfy_api_url`. That is the gap.

---

## Task 1: Endpoints are data

**Files:** new `qt_ui/shell/EndpointRegistry.{h,cpp}`, `qt_ui/shell/RuntimeProfile.*`, `tests/cpp/test_endpoint_registry.cpp`
**Read first:** `t6-context.md` §"Runtime page T6 surface"

Today the second machine is a **string literal in the C++** — `ManagerPage.cpp:290` prints it and `:628` probes `http://192.168.1.127:8188/system_stats` directly. Its health is then read by scraping `runtimeStateLabel_->text().contains("healthy=yes")`, which is label text used as a data source.

**Replace with a registry:** QSettings `runtime/endpoints`, a JSON list of `{id, label, base_url, enabled, families_allowed[]}`, with the local master always entry 0 and not removable. The worker receives it per request; it holds no second copy of the truth.

**Add the sweep rule** `no-hardcoded-endpoint-literal`: no `192.168.` or `:8188` literal in `qt_ui/` outside `RuntimeProfile`'s defaults. **Write its self-test in `tests/test_sweeps.py`** — two waves running, a rule whose self-test was skipped got caught by a final review.

- [ ] Steps: failing C++ test (round-trip; the local entry cannot be removed; a malformed stored value yields the default registry rather than an empty one) → implement → rule + self-test → prove the malformed case bites → commit.

---

## Task 2: Can this job run there?

**Files:** new `python/endpoint_capability.py`, `python/endpoint_commands.py`, registrations
**Read first:** `t6-context.md` §"Model availability" and §"Worker endpoint model"; `t6-research.md` §"Model availability on the Linux worker"

Three checks, in cost order, each of which must be able to say *why not*:

1. **Health** — `GET /system_stats`. Use this and not a model listing, because a hung CIFS mount makes ComfyUI's model directories block: the research records `cifs_wait_for_server_reconnect` stalling a start when the share host was down. `/system_stats` does not touch model dirs.
2. **Models present** — every model the compiled prompt references must appear in `GET /models/{folder}` on **that** endpoint. That route exists (added upstream 2024-08/09, so present on 0.34.0) and is cheaper than `/object_info`. Mind the recorded combo-schema split if you fall back to `/object_info`.
3. **Node classes** — the existing contract diff against that endpoint's `/object_info`, which is already cached per `api_url`.

**Fail closed, and say which check failed and what was missing.** "Cannot run there" is useless; "SpellNode does not have `loxsUtopicWorldKrea2_v20Quants.safetensors`" is actionable.

- [ ] Steps: failing tests against a fake ComfyUI HTTP server (healthy+complete passes; offline refuses naming health; a missing checkpoint refuses naming the file; a missing node class refuses naming the class; a hung model listing does not hang the health check) → implement → register the command → commit.

---

## Task 3: The worker routes, and keeps its state per endpoint

**Files:** `python/worker_queue.py`, `python/worker_service.py`, `python/worker_runtime.py`, `python/comfy_prompt_client.py`
**Read first:** `t6-context.md` §"Queue/concurrency" — it lists exactly what is process-global today

Four pieces of state assume one endpoint:

- `QueueManager._start_next_locked` (`worker_queue.py:583-600`) keeps a single `active_queue_item_id`; `QueueItem` has no endpoint field. → an active **map** keyed by endpoint, one job per endpoint.
- `get_comfy_runtime_manager` (`worker_service.py:1522-1543`) is a single global, rebuilt whenever host/port differ — two endpoints would thrash it. → keyed by endpoint. **And `ensure_comfy_runtime` for a non-local endpoint must be the health probe only**: today `run_comfy_workflow` calls it unconditionally, so a remote job would try to *start a local process*.
- `request_comfy_free_memory` and `wait_until_comfy_queue_idle` accept an `api_url` and **every caller omits it** (`worker_runtime.py:435, 436, 648`), so a remote job would free memory on the wrong machine. → pass it.
- The image/video runtime caches and the `transition` computation are module globals read against the *ambient* endpoint, so alternating endpoints would invalidate a warm remote runtime every time. → key by endpoint.

**Outputs come back over `/view`.** `comfy_root.local_output_is_authoritative` and sweep rule R18 already enforce that a remote endpoint's outputs are never read from a local disk path.

- [ ] Steps: failing tests against two fake endpoints (two lanes run concurrently; `/free` goes to the right one; a remote job never calls the local process manager; a warm remote runtime survives an alternating local job) → implement → **prove the `/free` case bites** by planting the bare call back → commit.

---

## Task 4: The Runtime page, honestly

**Files:** `qt_ui/ManagerPage.cpp`, `tests/cpp/test_endpoint_panel.cpp`
**Read first:** `t6-context.md` §"Runtime page T6 surface"

Per endpoint: label, URL, status, ComfyUI version, GPU and VRAM (from `/system_stats`), models visible (from `/models/checkpoints`), and a **Families** checklist that is **empty until a gate render passes on that endpoint** — the app writes an entry only after a real success there; the user may untick but not tick.

**Delete** the ComfyUI-Distributed Enable button, its zipball install and the share-folder consent UI. Say why in the commit: Distributed falls back to the master when the worker is offline, and `install_custom_node` is fail-closed for remote endpoints by design, so that button could never have installed anything on the second machine anyway.

Keep the honesty line. Add Add/Edit/Remove and a single "Allow queuing to remote workers" consent.

**Replace the label-text health scrape** with a real status.

- [ ] Steps: failing test (a fake registry and fake probes render the rows; an offline endpoint reads offline; an ungated family cannot be ticked; the local entry has no remove button) → implement → build → ctest → commit.

---

## Task 5: Run on, in the cockpit

**Files:** `qt_ui/ImageGenerationPage_catalog.cpp` **(careful: that file is near its size ceiling — put the control's logic in a new unit)**, `qt_ui/workers/WorkerRequestBuilder.cpp`
**Read first:** `t6-context.md` §"Worker endpoint model"

Advanced gains **Run on**: Auto · Local · <endpoint>. Simple is always Auto.

**Auto = the first idle, enabled endpoint in registry order whose capability check passes.** The local master is entry 0, so a free local machine always wins — which is the behaviour a user expects and the one that makes Auto safe to default to.

A remote pick that fails the check **refuses before enqueue**, naming the reason. Not a queued job that fails later.

`WorkerRequestBuilder` gains `comfy_api_url` — the producer the tree has been missing.

- [ ] Steps: failing C++ test (Auto picks local when free; Auto skips an offline endpoint; an explicit pick that fails the check refuses before enqueue with the reason; the request carries `comfy_api_url` only for a non-local choice) → implement → build → commit.

---

## Task 6: The second machine, for real

**Files:** new `docs/design/61_spellnode_setup.md`, `docs/design/55_t7_ship_walkthrough.html`, Doc 54's T6 row
**Read first:** `t6-research.md` §"Model availability on the Linux worker"

Models on the node are **out of band** — the app never mounts anything. Document both routes: the tuned CIFS fstab line (`soft,echo_interval=10,noserverino,_netdev,nofail,x-systemd.automount,x-systemd.mount-timeout=15`, so a dead share cannot hang ComfyUI's start) and the rsync alternative, with the honest note that even a tuned mount blocks for its timeout and only local copies make "model present" a property of the node.

**Gate order:** SDXL and Krea2 first on the 3090 Ti (Ampere has no fp8 tensor cores, so fp8 weights dequantise per layer — it works and it is slower). Video families only after their own gate render there.

**Then run it.** If SpellNode is reachable: queue an SDXL job with Run on = SpellNode, fetch the dest over `/view`, capture it, and write `families_allowed` from that success. If it is not reachable: ship the code, green the fake-server tests, and record the gate as **PENDING — node offline on <date>**. Do not paint it green either way.

- [ ] Steps: write the setup doc → attempt the live gate → capture or record PENDING → rewrite Doc 54's T6 row to say native routing and why → commit.

---

## Self-Review

**Spec §6 coverage:** registry as data (1) · capability check, fail-closed with a reason (2) · per-endpoint lanes, runtime managers, `/free` and caches (3) · Runtime page with gated families (4) · Run on, Auto = first idle passing (5) · out-of-band models doc and the live gate (6). The Distributed pack and share-folder UI are deleted in (4) with the reason recorded.

**Ordering:** the registry first because everything reads it; capability before routing because routing must be able to refuse; the cockpit last because it is the only part that can enqueue a wrong job.

**Not in this wave:** same-box CFG split (needs two identical GPUs; this box has one), ComfyUI-Mesh model splitting, and any form of VRAM pooling. All are Doc 54 §3.2 or never.
