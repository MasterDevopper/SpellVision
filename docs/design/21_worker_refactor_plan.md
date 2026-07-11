# Doc 21 — Python Worker Refactor Plan (sequenced, gated; PLAN ONLY)

Turns Doc 20 (`20_worker_runtime_ground_truth_map.md`) into a sequenced, gated refactor proposal. **No code is moved, split, edited, or deleted here.** Execution is a separate task after human review. Every proposal is judged against Doc 20's *measured* facts (state/lock topology, coupling constraints C1–C5, dead-code column), not filenames. Doc 20 `[inferred]` items are treated as unconfirmed. Anchors are point-in-time — passes reference Doc 20 concerns/seams by **name and role**, and execution re-anchors from live output.

**Prime directive:** behavior-preserving. Every pass is a pure refactor (same worker behavior, same TCP/JSON protocol, same outputs) **except** the §0 constraint passes that explicitly change behavior — those say so and are gated as behavior changes, never smuggled in as cleanup. Each pass is independently shippable, self-gated, and reversible (git tag before). No pass depends on a later pass to be correct.

---

## Investigation results (read-only, run now — they change the plan)

The task required two read-only checks up front because their results reshape the plan. Both were run 2026-07-10; **both cut against the task's stated expectation** — reported honestly.

### I-1 — C1 dispatcher reachability: the TCP-direct generation path is [inferred] vestigial
- `python/worker_client.py:50 normalize_outbound_request` maps the frontend's generation action `"enqueue_job"` → `command="enqueue"` + `task_command` (`:56–59`). Its `CONTROL_COMMANDS` set (`:28`) — every command the client forwards — **contains no bare `t2i`/`i2i`/`t2v`/`i2v`/`comfy_workflow`**. Generation is always enqueued.
- `grep tests/ -E '"command": *"t2i"|…"t2v"…|task_command'` → **empty**; the pytest suite enqueues (`test_worker_queue`) or uses `noop_slow`. No caller sends a bare generation command.
- **Verdict [inferred, static]:** the WorkerTCPHandler direct generation branches (`command == "t2i" → run_t2i`, etc.) are unreached by the real client and tests; `noop_slow` is the only bare command actually exercised there. **Consequence:** the C1 "divergence" (native-image fork present in the queue path, absent in the direct path) is **latent, not active** — real generation always takes the queue path, which *has* the fork, so native-image works today. The direct path's missing fork is a dormant bug, not a live one.
- **Residual gap:** I traced `worker_client.py`'s normalization, but the grep for how the Qt UI sets `action="enqueue_job"` came back empty (the frontend likely builds it via a controller variable not caught by a symbol grep). So "vestigial" is a **static** verdict — see the static-verdicts line in C6; the C1 pass must confirm it cold with a runtime trace before removing anything.

### I-2 — C6 widened `gpu_info.py` grep: did NOT flip it to live (opposite of the prediction)
- `grep -rn "gpu_info" qt_ui/ scripts/ --include=*.cpp --include=*.h --include=*.ps1` → **empty** (no caller by name).
- Widened `grep -rniE "gpu" qt_ui/ scripts/` → the only GPU-detection call site is **`qt_ui/MainWindow.cpp:3601`**, which runs **`nvidia-smi --query-gpu=memory.used,memory.total` directly in C++** — the frontend does its own GPU telemetry and **does not spawn `gpu_info.py`**. The backend launch (`qt_ui/main.cpp:53–61`, `MainWindow.cpp:1746/3333`) spawns only `python/worker_client.py`.
- **Verdict:** the prediction ("likely a QProcess-spawned startup helper → flips to live") **did not hold**. `gpu_info.py` has no caller anywhere (python/scripts/qt), and its function is independently implemented in C++. It **stays verify-first, leaning dead** — but still static; a runtime trace is required before removal (C6).

### I-3 — runtime_adapters/ and workflow_profile_registry (carried from Doc 20 §5)
No new grep needed — Doc 20's import grep + `backend_kind`/`get_adapter` dynamic-dispatch grep were both empty for `runtime_adapters/`; `workflow_profile_registry.py` had zero references. Both remain **decisions**, not auto-removals (below).

---

## §0 — Constraint passes (REQUIRED FIRST; before any file split)

A split done before these resolves has **relocated** the coupling, not removed it — that is failure. Each constraint gets a dedicated pass before any line-range extraction along the affected seam.

### Pass C1 — Dispatcher unification *(behavior change — gated as such)*
- **Goal:** make the two generation dispatchers agree; eliminate the native-image-fork divergence.
- **Resolution (given I-1):** two options, presented as a tradeoff for the reviewer:
  - **(a) Collapse to one** `dispatch_generation(command, req, …)` function that both the queue-execute path and the TCP-direct path call. Safest if any client ever sends a bare command; behavior-preserving for the queue path, behavior-*fixing* for the direct path (it gains the native-image fork).
  - **(b) Remove the dead direct-generation branches** (keep `noop_slow` + all control/command handlers), so generation has exactly one dispatcher (the queue path). Simpler and removes the divergence at the source — **but it is a removal, so it runs under the C6 protocol** (runtime-trace cold-confirmation first).
  - **[inferred] recommendation: (a) collapse to one `dispatch_generation` both paths call — as the default.** It removes the divergence (the direct path *gains* the native-image fork = behavior-fixing there) while staying behavior-preserving on the live queue path, and it leaves the direct branch as a **thin forwarder** rather than a deleted entry point. *Rationale: (a) and (b) both remove the divergence; (a) is the lower-regret default because it does not delete an entry point on a static-only verdict.* Reframe (b): *if*, after the C6 runtime trace proves the direct path unreachable **and** the reviewer wants the entry point gone, do the deletion as a **separate removal pass under C6** — not as part of C1. The tradeoff stays visible; only the default flips.
- **Behavior:** **CHANGE** (the two paths currently disagree; after this they don't). Not cleanup.
- **Gate:** a characterization test (G-dispatch, see §3) that pins current *queue-path* behavior for t2i/i2i/one-video-family/comfy_workflow, plus proof that the direct path now produces the **identical** dispatch (default (a)). The C6 runtime import-trace is a required input **only if** the reviewer elects the optional (b) deletion (a separate C6 pass); it is not needed for (a).
- **Rollback:** git tag `pre-c1-dispatch`; single revert.
- **Blocks:** no file may be extracted along the generation-dispatch seam (queue, dispatch, run_* entrypoints) until this lands.

### Pass C2 — `req`-mutation ownership *(the refactor spine; behavior-preserving)* — **CLOSED 2026-07-11 (premise not borne out)**

> **CLOSED — `req` is already effectively copy-isolated; the spine pass has no systemic risk to fix.** Two read-only recons traced *object identity* (not just static structure) end-to-end and cut against C2's premise:
> - **Original premise (Doc 20):** `req` is an unowned shared mutable bag threaded through every layer — a systemic ownership risk requiring a spine pass to make it a boundary.
> - **The queue path deep-copies twice before any `run_*` sees `req`:** `clone_request_snapshot`→`copy.deepcopy` in `enqueue` (builds `item.request_snapshot`), then again in `_run_queue_item` (`req = clone_request_snapshot(item.request_snapshot)`). The run's object is already isolated from everything upstream.
> - **Every other write is on a copy or is stage-owned:** command/normalization writes land on **local copies** (`_normalize_ltx_prompt_api_request`'s `ltx_req` deepcopy; the `enqueue` snapshot), never the caller's dict; the constructed-request builders (dataset/retry — `job_req`/`retry_req`/`new_req`) are all **fresh** `clone_request_snapshot` dicts; queue-stage writes are **stage-owned** (output-path construction).
> - **The one genuine ownership ambiguity is benign by reconstruction:** `run_native_split_stack_video` rebinds `req` to the adapter copy at `~:5622` (`_prepare_native_video_adapter_request(...)` returns `dict(req)`), so later writes land on the copy while the caller keeps the pre-fork object. The only such key read off the pre-fork object downstream — `resolved_native_video_family`, via `build_history_entry`→`video_completion_diagnostics`→`video_request_metadata_from_request` — is **recomputed** by the same deterministic function (`_video_family_from_request_parts`) that produced the copy's value (the adapter sets it to `self.family` = the family that function selected). No reader observes a stale or absent value.
> - **Conclusion:** **C2 is closed.** There is no `req`-ownership risk to spine-fix, and the precondition "resolve `req` before builder/dispatch extraction" is already satisfied — #10/#12 inherit no `req`-mutation coupling (the §5 self-check concern is moot, not violated). The `:5622` rebind is a **code-hygiene smell** (shadowing `req` with a copy — a future write after that line silently would not reach the caller's object), **not a correctness defect**; it is addressed *optionally* as a local hygiene rename (separate commit), never as a spine pass.
> - **[inferred] known non-issue (recorded, not an action item):** adapter selection is `object_info`-aware (`score()` gates on availability) while the history family-recompute is not; *if* a family-specific adapter whose `self.family` differs from `_infer_native_video_family(R)` ever won selection, history could mislabel the family. Unreachable in current flows — `score()`'s haystack-keyword gate prevents a cross-family win and the generic/fallback adapters preserve the request's family.
>
> The original C2 proposal below is retained as the record of what was planned and gated; it is **not scheduled**.

- **Goal:** turn `req` from an unowned shared mutable dict into a boundary, so downstream seams become real. **This is sequenced before any builder/dispatch extraction** — a plan that splits builders before this is cosmetic (self-check §5 confirms it doesn't).
- **(a) Enumerate every `req` key written after enqueue, by stage** (execution list; anchors re-confirmed live at execution). **This table is a starting point, not the authority — the Gate below turns it into a *tested invariant*: the key-set-diff baseline mechanically captures the true set, so an incomplete enumeration here cannot silently pass.**
  | Stage | Keys written (representative) |
  |---|---|
  | enqueue (QueueManager) | the 6 command keys, `queue_display_command`, `source_generation_mode`, `generation_mode`, `task_type`, `mode`, `job_id`, `original_output`, `queue_item_id` |
  | queue execute (per-item prep) | `queue_warm_reuse_*`, `queue_affinity_signature` |
  | adapter prep (`_prepare_native_video_adapter_request`) | `native_video_adapter_family`, `resolved_native_video_family`, `video_family`, `model_family`, `native_video_route`, sampler/scheduler/text-encoder picks |
  | video dispatch/builders | `resolved_native_video_family`, `native_video_route` |
  | run_native_* | `input_image_comfy_name`, `native_prompt_api_path`, `resolved_media_type`, `comfy_asset_kind` |
  | image builders | (read `command`/`strength`/etc.; write none beyond local) |
- **(b) Ownership model (proposal, choose one at review):**
  - **B1 — "builders return, never mutate":** each `_build_*_prompt` returns `(graph, RequestDelta)` where `RequestDelta` names the keys it wants set; the caller applies them. Smallest change, directly unblocks builder extraction.
  - **B2 — typed request object:** a `GenerationRequest` dataclass with explicit fields + a `.extras` dict for pass-through; stages take/return it. Larger, but kills the 6-key aliasing (pairs with C3) and the ad-hoc `req.get(...)` fallbacks.
  - **B3 — owned-key contract per stage:** document + assert (in tests) which stage owns which key; least code change, weakest enforcement.
  - **[inferred] recommendation:** **B1 first** (unblocks Pass 7 with minimal risk), with **B2 as a follow-on** if the aliasing (C3) proves painful. Present B2's larger blast radius as the tradeoff.
- **Behavior:** **preserving** (same keys end up set; only *who* sets them changes).
- **Gate (exhaustive `req` key-set diff — not a spot-check):** *before C2 executes*, capture the full `req` key-set diff (keys present after-run **minus** keys present before-enqueue) for one real run per path — **t2i / i2i / one video family / comfy_workflow / ltx_gated** — today, as the baseline. C2's acceptance is: the after-vs-before key-set diff is **identical to that baseline for every path** — the full set matches, not a sampled subset. This makes enumeration completeness a *tested property*, so an incomplete §0-C2(a) table cannot cause B1 ("builders return a delta, never mutate") to silently drop a mutation. **G-graph does NOT cover this** — G-graph pins the submitted *graph*, not post-run `req` *state*; the key-set-diff gate is therefore required **in addition to** G-graph, for C2 and for the builder extraction (#10). *Rationale: the spine pass could regress invisibly if the enumeration is incomplete; an exhaustive key-set diff makes completeness tested rather than claimed.*
- **Blocks:** Pass 7 (builders + dispatch + Wan resolvers) — the largest block — must not start until C2 lands.

### Pass C3 — Command-identity normalization *(behavior-preserving; scope narrowed on live inspection)*
- **Finding (live inspection, corrects the premise):** "command identity" is **not one value with six aliases** — it is **three distinct resolution mechanisms** that only agree *after* `_normalize_ltx_prompt_api_request` runs: (1) the **plain dispatch reads** (`command == "t2i"` etc.); (2) `_queue_ltx_execution_command`, an **ordered-precedence LTX-detection heuristic** with an `LTX_PROMPT_API_DISPATCH_COMMANDS` membership check and a ~20-field substring haystack fallback — **not a key read at all**; and (3) several ad-hoc `req.get("command") or req.get("task_command") or …` **or-chains with their own, non-matching fallback orders**.
- **Goal (narrowed):** introduce `canonical_command(req)` encoding **the precedence the plain dispatch reads use today**, and route **only the plain dispatch switches** through it.
- **Scope — narrowed to plain dispatch reads only:** `canonical_command(req)` replaces just the plain switches (`command == "t2i" / "i2i" / "comfy_workflow" / in {"t2v","i2v"}`, both dispatchers). **Explicitly out of scope this pass** (each becomes its own later, separately-gated pass): folding in `_queue_ltx_execution_command` (a detection heuristic whose substring fallback a key-accessor *cannot* replace), and migrating the divergent **or-chains** (each must be individually proven equivalent to the canonical order before migration; **any that differ are left as-is and flagged, not "fixed" under a behavior-preserving pass**). **Keep writing all six keys**, as before; removing redundant keys from the wire is a separate protocol change.
- **Behavior:** preserving. **Gate:** every plain dispatch decision resolves identically — the G-dispatch characterization test (§3), **which must include adversarial fixtures per path where the six keys deliberately disagree** (that conflict case is the only place precedence is observable). **Pairs with C1** (both touch the dispatch seam) — may ship together or C3 first.
- *Rationale: live inspection showed command identity is three mechanisms that only coincide after LTX normalization, so C3 is narrowed to the plain dispatch reads a single accessor can faithfully encode; the LTX heuristic and the divergent or-chains are each their own later pass, not force-fit under one accessor.*

### Pass C4 — Cache ownership *(behavior-preserving; state moves with its lock)*
- **Goal:** each mutable cache owned by exactly one module, other concerns get a read-only accessor. **State never splits from its lock and accessors.**
  | Cache | New owner module (proposed) | Read-only accessor exposed to |
  |---|---|---|
  | `MODEL_CACHE` (+`CACHE_LOCK`, LoRA state, `lora_adapters`) | `worker_image_runtime` (diffusers pipeline+LoRA runtime) | affinity, status/diagnostics |
  | `VIDEO_RUNTIME_CACHE` (+`VIDEO_RUNTIME_LOCK`) | `worker_video_runtime` | affinity, status/diagnostics |
  | `QUEUE_MANAGER` | `worker_queue` | TCP command handlers (via methods only) |
- **`MODEL_CACHE["lora_adapters"]` live-aliasing (C4 explicit):** `_lora_adapter_registry` currently lazy-inits and **hands out the live nested dict** for callers to mutate. The pass must **de-alias** it — either fold the adapter registry into the owner module's API (callers call `owner.register_adapter(name)`, never touch the dict) or make the accessor return a copy for reads and a method for writes. No module outside the owner may hold a reference to the live dict.
- **Behavior:** preserving. **Gate:** lora-adapter test (`tests/test_worker_lora_adapters.py`) passes unchanged; a new test asserts no external module imports the cache symbol directly (grep-gate).
- **Note:** this pass *is* partly structural (it extracts the cache + its accessors), but it is listed in §0 because ownership must be decided before the runtime modules are carved — doing it later means re-touching every reader.

### Pass C5 — Preserve lazy-import cycle-breaks *(constraint, not a standalone pass — a rule every structural pass obeys)*
- **Rule:** the proposed module DAG (§1) must keep Doc 20's ~9 lazy edges intact **or** re-break the cycle a documented way. Specifically the `model_dependency_manifest → model_registry` lazy edge (`:401`, alias-aware) and `worker_service`'s lazy imports of `component_resolver`, `model_classification`, `video_adapters.registry`, `workflow_importer/scanner`, `node/model_dependency_resolver`, `comfy_manager_bridge`.
- **Enforcement:** each structural pass (§2) must, as part of its gate, prove no new import cycle (`python -c "import <new_module>"` clean + a cycle-check across the touched modules). No lazy import is promoted to top-level without that proof. Where a top-level promotion *would* cycle, keep it lazy and note why.

### Pass C6 — Dead-code protocol *(destructive-change firewall)*
**This line is carried verbatim into every VERIFY-FIRST removal pass:** *"Verdicts are static; before deletion, confirm cold via a runtime import-trace/coverage of one real end-to-end run per generation path (t2i, i2i, one video family, comfy_workflow)."* No verify-first item moves to "confirmed-removable" on static evidence alone; a future execution pass must not read "verify" as "verified." **For confirmed-dead items, static proof is sufficient** — a confirming grep that the item is empty / zero-reader is the whole gate; **no G-trace is required** (the runtime trace would add nothing a static check on a 0-byte file / zero-reader constant doesn't already give). *Rationale: applying the strictest gate uniformly created an ordering deadlock — G-trace is not authored until the runtime-pass prerequisites are built, so it cannot gate the first pass; the trace is for items whose static reachability is genuinely uncertain, which the two confirmed-dead items are not.* **Every removal is its own isolated pass with a git tag and a one-revert restore note; no removal rides inside a structural pass.**

- **Confirmed-dead (plan for removal; static proof sufficient — one confirming grep each is the whole gate, no G-trace):**
  - `python/video/{i2v_worker,t2v_worker,video_job_schema}.py` (0 LoC, no importer).
  - `DEFAULT_VIDEO_RUNTIME_HINTS` (`model_registry.py`, zero source readers).
- **Verify-first (must clear its specific check before the plan may propose removal; each remains a DECISION):**
  - `runtime_adapters/` package — import grep + dynamic-dispatch grep both empty (Doc 20). **Author call:** deprecated vs. reserved-WIP. Not auto-removed.
  - `workflow_profile_registry.py` — zero references. **Confirm** it isn't a planned/public API before removal.
  - `gpu_info.py` — **I-2 result:** widened grep empty; frontend does GPU telemetry via `nvidia-smi` in C++ instead. Leans dead, but **stays verify** (static). Confirm nothing execs it out-of-band before removal.
- **Sequencing:** the confirmed-dead removals may come **early** (shrink the surface), each after its confirming grep (static proof sufficient — **no runtime-trace gate**, which is why they can run first). The verify-first items stay parked as decisions until the runtime trace + author call.

---

## §1 — Proposed target structure

From Doc 20's ⟂ fault lines (§6) and state topology (§3). Each module owns its state **with its lock and accessors**. `worker_service_state.py` (the already-clean `ACTIVE_JOBS` extraction) is the model. Direction is strictly leaf-ward; the C5 lazy edges are preserved.

| Proposed module | Owns (symbols) | Owns (state + lock) | Depends on (→) |
|---|---|---|---|
| `worker_service_state.py` *(exists)* | JobState machine, Job* dataclasses, `ActiveJobHandle` | `ACTIVE_JOBS`+lock | — (leaf) |
| `worker_comfy_client.py` | `_comfy_object_info`, `_submit_comfy_prompt`, `_poll_comfy_history`, `_extract/_download_comfy_asset`, `_upload_comfy_image`, `_comfy_input_choices`, node-build helpers | none (stateless) | — (leaf) |
| `worker_metadata.py` | `build_metadata_payload`, `save_metadata`, writer loop | `METADATA_WRITE_QUEUE`, `_METADATA_WRITER_STARTED`+lock | — |
| `worker_history.py` | `build_history_entry`, `persist_video_history_entry`, `archive_job`, `get_archived_job` | `JOB_ARCHIVE(+ORDER)`+lock, video-history-file lock | state |
| `worker_image_runtime.py` | `build_pipelines`, `get_or_load_pipelines`, LoRA load/reset, `unload_cached_pipelines`, `run_t2i`, `run_i2i` | `MODEL_CACHE`(+lora_adapters)+`CACHE_LOCK` | memory_optimization, model_classification, comfy_client, metadata |
| `worker_video_runtime.py` | runtime prep/reset/invalidate, `_load_native_video_pipeline`, `run_native_video` | `VIDEO_RUNTIME_CACHE`+lock | model_classification, comfy_client |
| `builders/image_builders.py` | `_build_{flux,pixart,lumina,zimage,anima}_image_prompt`, `_build_native_image_prompt`, `_resolve_native_image_stack`, `_should_route_native_image`, `run_native_image` | none (stateless) | component_resolver, model_classification, comfy_client |
| `builders/video_builders.py` | `_build_native_{wan_core,wan_split,ltx,hunyuan}_video_prompt`, `_build_native_split_video_prompt`, Wan `_sv_core_wan_*` resolvers, `_resolve_native_video_stack`, `run_native_split_stack_video` | none (stateless) | component_resolver, video_adapters.registry, comfy_client |
| `worker_queue.py` | `QueueItem*`, `QueueManager` | `QUEUE_MANAGER`+lock | state, dispatch (injected callable — see below) |
| `worker_dispatch.py` *(post-C1)* | the single `dispatch_generation`, `canonical_command` | none | image_runtime, video_runtime, builders, comfy_workflow, ltx |
| `worker_commands/` *(package)* | the ~50 `handle_*_command` grouped: `queue_cmds`, `comfy_runtime_cmds`, `workflow_import_cmds`, `node_mgmt_cmds`, `memory_cmds`, `ltx_cmds` | none | queue, runtimes, subsystems |
| `worker_server.py` | `WorkerTCPHandler`, `ThreadedTCPServer`, `main` | none | commands, queue, dispatch |

**DAG note / flagged boundaries not yet real:**
- `worker_queue` → `worker_dispatch` is the one edge that risks a cycle (queue executes items *by dispatching*, dispatch may need to enqueue retries). **Break it by dependency injection:** `QueueManager` takes a `dispatch` callable at construction (or via a registry), so `worker_queue` does not import `worker_dispatch` top-level. [inferred — this is the same shape as the existing lazy edges; validate at execution.]
- Any builder module reaching into a runtime cache would be a false boundary — the builders are **stateless by construction** in Doc 20 §7, so this holds; the gate for Pass 7 must assert no builder imports a cache symbol.
- `worker_image_runtime` and `worker_video_runtime` both depend on `comfy_client` + `model_classification` (shared leaves) — fine, that's leaf-ward.

---

## §2 — Sequenced pass list

Ordering: §0 constraints first; confirmed-dead removals early (surface-shrink); the largest block (builders) only after C1 + C2; the TCP server last. Each pass: goal · scope · behavior · deps · gate · rollback.

| # | Pass | Behavior | Deps | Gate (summary; full in §3) | Rollback tag |
|---|---|---|---|---|---|
| 0-doc | **Doc: the 3 undocumented modules** (`comfy_bootstrap`, `comfy_slot_mapper`, `worker_client`) — standalone, needs no extraction | doc-only (prose) | — (runs immediately) | G-docs | `pre-0doc` |
| 0 | **C6-a: remove confirmed-dead** (`python/video/*` stubs, `DEFAULT_VIDEO_RUNTIME_HINTS`) | removal | — | confirming grep (empty file / zero source readers) — static proof sufficient, no G-trace | `pre-deadcode-1` |
| 1 | **C3: `canonical_command` for plain dispatch reads only** (LTX heuristic + or-chains explicitly out of scope) | preserving | — | G-dispatch identical incl. adversarial key-conflict fixtures | `pre-c3` |
| 2 | **C1: dispatcher collapse-to-one** (default (a); optional (b)-remove is a separate C6 pass) | **change** | C3 | G-dispatch (queue-path pinned; both paths produce identical dispatch) — C6 trace needed only for optional (b) | `pre-c1` |
| ~~3~~ | **C2: `req` ownership — CLOSED 2026-07-11** (premise not borne out; `req` already copy-isolated by the queue's double deepcopy — recon, see §0 C2) | n/a (not run) | — | closed by recon; no spine pass — `:5622` rebind is optional hygiene only | `—` |
| 4 | **C4: cache ownership + de-alias lora_adapters** | preserving | — | lora test unchanged + grep-gate no external cache import | `pre-c4` |
| 5 | Extract `worker_comfy_client.py` (stateless helpers) | preserving | — | import-clean; graph baseline identical | `pre-extract-comfy` |
| 6 | Extract `worker_metadata.py` | preserving | — | metadata written identically for one run/path | `pre-extract-meta` |
| 7 | Extract `worker_history.py` | preserving | — | queue/history tests pass; history index byte-identical | `pre-extract-history` |
| 8 | Extract `worker_image_runtime.py` (owns MODEL_CACHE) | preserving | C4 | t2i/i2i characterization + lora test | `pre-extract-imgrt` |
| 9 | Extract `worker_video_runtime.py` (owns VIDEO_RUNTIME_CACHE) | preserving | C4 | one video-family end-to-end identical | `pre-extract-vidrt` |
| 10 | **Extract builders block** (`image_builders`+`video_builders`, ~2,100 lines) | preserving | **C1, C2** | full 7-family graph baseline byte-identical + no builder imports a cache | `pre-extract-builders` |
| 11 | Extract `worker_queue.py` (owns QUEUE_MANAGER; DI dispatch) | preserving | C1, C4 | queue test + no import cycle | `pre-extract-queue` |
| 12 | Extract `worker_dispatch.py` | preserving | C1, #10, #11 | dispatch characterization identical | `pre-extract-dispatch` |
| 13 | Extract `worker_commands/` (grouped handlers) | preserving | subsystems above | every command replays identical response | `pre-extract-commands` |
| 14 | Reduce `worker_service.py` → `worker_server.py` (thin TCP layer + main) | preserving | all above | full suite + one run/path | `pre-server-thin` |
| 5-doc … 14-doc | **Paired doc pass** — one prose-only pass after **each** extraction #5–#14 (see "Paired documentation passes" below) | doc-only (prose) | its extraction #N landed | G-docs | `pre-<N>doc` |
| — | **C6-b: verify-first decisions** (`runtime_adapters/`, `workflow_profile_registry`, `gpu_info`) | removal *(if approved)* | runtime trace + author call | per-item cold-trace + decision recorded | per-item tag |

**Sequencing tradeoffs (presented, not silently resolved):**
- **C6-a early vs. after structure:** placed early to shrink surface, but it's genuinely independent — could run anytime. Early wins are small (2 removals); if the reviewer prefers zero destructive changes until structure is proven, move all of C6 to the end. *Tradeoff surfaced, not decided.*
- **C1 vs C3 order:** C3 (accessor) *before* C1 (unify) means the unified dispatcher reads one field from day one; but they touch the same seam and could ship as one pass. Listed C3→C1; pairing is acceptable.
- **C4 as §0 vs. as the first structural pass:** it's half-constraint, half-extraction. Listed in §0 because ownership must precede the runtime carves (#8/#9); a reviewer could fold it into #8/#9 if willing to re-touch readers. *Tradeoff surfaced.*
- **Builders (#10) is the single largest unit** — Doc 20 flags ~2,100 lines. It is gated hardest and sequenced last among extractions except queue/dispatch/commands, strictly after C1+C2.

**Paired documentation passes (new — a first-class, separately-gated pass type).** In-code documentation is a **deliverable, not a side effect**. Every structural pass above is behavior-preserving, so a pure extraction *relocates* existing doc gaps into tidier files rather than closing them (Doc 20 found three modules with **no docstring at all**). Improving in-code docs — for maintainability and open-source contributor onboarding — is an explicit goal, and it is the one goal in mild tension with "behavior-preserving," so it is carried as its **own prose-only pass**, never folded into an extraction.

- **Convention:** each structural extraction (#5–#14) is immediately followed by a paired `#N-doc` pass (`#5-doc`, `#8-doc`, …), **prose-only** (docstrings + comments; **zero logic change**), sequenced *after* its extraction lands and gated separately (**G-docs**, §3). Plus **Pass 0-doc** — a standalone quick win for the three currently-undocumented modules (`comfy_bootstrap.py`, `comfy_slot_mapper.py`, `worker_client.py`), whose responsibilities Doc 20 §2 already states, so it is transcription and needs no extraction to precede it; it **can run immediately**.
- **Scope per module (deliberately bounded):**
  - one **module docstring** — what it owns, what mutable state (+ its lock) it owns, and its dependency direction (this content already exists in Doc 20 §1–§3 and §7 — largely transcription);
  - **docstrings on the public surface only** — the module's entry points / builders / command handlers — *not* every private helper;
  - **why-comments on the non-obvious** — the load-bearing mechanisms a reader can't infer from the code: the lazy imports that break import cycles (C5), the Wan two-stage high/low-noise boundary handoff, the Flux denoise = `0.55 + 0.45*strength` remap, the `MODEL_CACHE["lora_adapters"]` de-aliasing (C4), and the six-key command normalization (C3).
- **Explicit anti-goal:** do **NOT** aim for comprehensive / wall-to-wall docstrings. Over-documenting re-bloats the modules and multiplies stale-comment risk (**a wrong comment is worse than none**). Target = one real module docstring per file + public-surface docstrings + why-comments where behavior is non-obvious; a private helper gets a docstring only when its purpose isn't self-evident from name + signature.
- *Rationale: behavior-preserving extraction relocates doc gaps rather than closing them, so in-code documentation is carried as its own prose-only paired pass — scoped to module docstrings, the public surface, and why-comments — to serve maintainability and contributor onboarding without re-bloating the modules or risking stale comments.*

---

## §3 — Acceptance gates

**Baseline harness assessment.** `tests/` is thin (ping, queue, lora-adapters, workflow-import) — it does **not** cover t2i/i2i/video generation end-to-end. `refactor_baseline/_capture.py` captures the **submitted native prompt graph** per family (7 families incl. Hunyuan) — it *can* characterize the **builder extraction (#10)**'s graph output (byte-identical graphs = preserved graph construction), but it does **NOT** cover the **C2 `req`-state change**: the graph is the builder's *output*, not its `req` *mutations*, so C2 additionally requires the key-set-diff gate (**G-reqdiff**, below). It also **cannot** characterize the **dispatcher (C1)**, **queue (#11)**, **runtimes (#8/#9)**, or **command handlers (#13)** — those aren't graph-shaped.

**Characterization tests that must exist before the risky passes run (a pass whose behavior can't be pinned does not run until its gate exists):**

| Gate | Covers passes | What it pins |
|---|---|---|
| **G-graph** (extend `refactor_baseline/_capture.py`) | builders (#10) graph output; C2 (#3) *graph only* | byte-identical submitted graph for all 7 families under a fixed request. **Does NOT pin post-run `req` state** — see G-reqdiff. |
| **G-reqdiff** (new; per-path key-set baseline) | C2 (#3), builders (#10) | the after-run **minus** before-enqueue `req` key-set diff matches a per-path baseline (t2i/i2i/one-video/comfy_workflow/ltx_gated). **Required in addition to G-graph**, which pins the graph, not `req` state. |
| **G-dispatch** (new) | C1 (#2), C3 (#1), dispatch (#12) | replay a captured set of requests (t2i/i2i/t2v/i2v/comfy_workflow/ltx_gated/noop_slow) through the dispatcher, assert the same `run_*` target + the same native-image-fork decision. **Must include adversarial fixtures per path where the six command keys deliberately disagree** (e.g. `command="t2i"` but `task_command="i2i"`, and the reverse) — because the six keys are identical *after* normalization, a fixture set drawn only from normalized requests would make G-dispatch green **and blind**; the key-conflict case is the only place precedence is observable and the only thing that catches a wrong-order accessor. |
| **G-e2e** (new, worker-TCP, one run/path) | runtimes (#8/#9), queue (#11), server (#14) | drive the live worker over TCP for t2i, i2i, one video family, comfy_workflow; assert job reaches `QUEUED→STARTING→RUNNING→COMPLETED`, an output file exists, and the metadata sidecar fields match a pinned snapshot. Respect the known `QUEUED→COMPLETED` xfail. |
| **G-trace** (the C6 runtime import-trace) | **C6-b only** (verify-first removals) | `python -X importtime` / `coverage` over one real end-to-end run per path; an item is removable only if it never loads. **Doubles as the cold-confirmation gate for the verify-first removals.** (C6-a confirmed-dead needs no trace — static proof suffices.) |
| **G-cycle** (per structural pass) | #5–#14 | `import` clean + no new import cycle across touched modules; C5 lazy edges intact |
| **G-docs** (doc passes) | 0-doc, all `#N-doc` | **prose-only:** a mechanical check that the diff touches only comments/docstrings (**no executable line changed** — e.g. AST-equal before/after); the module docstring answers owns-what / owns-which-state / depends-on-what; the public surface is covered. Because a doc pass changes no logic, it **inherits its extraction's behavior gates unchanged** — G-suite stays green by construction. |
| **G-suite** | every pass | existing `tests/` (ping/queue/lora/workflow-import) stay green |

**G-dispatch and G-e2e must be authored before C1 (#2) and before #8/#11/#14 respectively.** G-graph already exists (extend it). G-trace is run once and reused by the verify-first (C6-b) removal passes; **C6-a needs no trace** (static proof).

---

## §4 — Scope statement

**The C++/Qt frontend is OUT OF SCOPE for this plan.** This plan refactors only the Python worker (`python/`). `qt_ui/ImageGenerationPage.cpp` (5,546 lines — one `Mode`-parameterized class over T2I/I2I/T2V/I2V, the largest source file in the repo) is the **frontend mirror of this exact god-file problem**, but it is not planned here; it needs its own survey + plan (a Doc-20-equivalent for the Qt side) before any frontend extraction. Nothing in §0–§3 touches C++.

**Documentation scope:** the paired doc passes + Pass 0-doc (§2) are **in scope for the Python worker only**, consistent with the rest of the plan; C++/frontend documentation is part of that separate frontend pass.

---

## §5 — Self-check (required by C2)

- **Does any file split precede `req` resolution?** No. Pass C2 (`req` ownership) is sequenced (#3) **before** the builders extraction (#10) and the dispatch extraction (#12) — the only passes that would otherwise inherit `req`-mutation coupling. The stateless extractions (#5–#7) and the state-owning extractions (#8/#9/#11) do not cross the `req`-mutation seam, so they may precede C2 without becoming cosmetic. **If execution reorders #10/#12 before #3, that is a cosmetic split — flag and stop.**
- **Does any split precede dispatcher (C1) on the generation seam?** No. #10/#11/#12 all list C1 as a dependency.
- **Does any proposed module reach into another's mutable state?** Per §1, no — the one at-risk edge (`worker_queue`→`worker_dispatch`) is broken by dependency injection, and builders are stateless. Pass gates assert this (grep-gate: no builder imports a cache symbol).
- **Are all removals static-verdict-guarded?** The verify-first removals (C6-b) are — C6's verbatim static-verdicts line governs them; no "verify" item is treated as "verified" without G-trace. The two confirmed-dead items (C6-a) are removable on static proof alone (0-byte file / zero readers), which is why C6-a needs no trace and can run first — the strict trace gate applies only where static reachability is genuinely uncertain.
- **Anything behavior-changing smuggled as cleanup?** Only C1 changes behavior, and it is labeled a behavior change with its own characterization gate. All other structural passes are behavior-preserving.
- **Are the doc passes kept out of the behavior surface?** Yes — every `#N-doc` and Pass 0-doc is prose-only, sequenced *after* its extraction, and gated by G-docs (a mechanical no-executable-line-changed check); documentation improvement — the one goal in mild tension with "behavior-preserving" — is carried as its own pass type so it never rides inside an extraction.

---

## Caveats
- All line/anchor references defer to Doc 20 and to live re-anchoring at execution (`worker_service.py` was 8,666 lines on 2026-07-10 and grows).
- Module names in §1 are proposals, not prescriptions — the *boundaries* (state ownership, DAG direction, C5 lazy edges) are the load-bearing part; names are a reviewer's call.
- `[inferred]` items (direct-path vestigiality, B1-first recommendation, DI for the queue→dispatch edge) are unconfirmed until their gate/trace runs.
