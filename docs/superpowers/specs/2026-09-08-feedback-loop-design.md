# Wave 3 — the feedback loop

**Status:** approved 2026-09-08, not started. Base `main` at `0ef2b5b`.

The third wave of the S+ UI programme. Waves 1 (foundation kit) and 2 (shell layouts) are merged.

---

## 1. What is actually true today

Every claim here carries file:line and was established by survey against `5e2bcff`, not from the wave's original scope note. **Three of that note's four premises were false**, which is why this section exists before any design.

### 1.1 The click IS acknowledged, synchronously

`ImageGenerationPage.cpp:1383` → `WorkerCommandRunner::submit` → `MainWindow.cpp:3131-3163` latches the telemetry state to `"Submitting"` and `:3167` calls `page->setBusy(true, "Submitting generation…")`, which hard-disables Generate and Queue (`ImageGenerationPage_catalog.cpp:1696-1701`). None of that waits on I/O. The socket round trip behind it is **1.75 ms median / 2.04 p90 / 4.42 max** (n=15).

So "optimistic acknowledgement on Generate" is **already built**. The original scope note was wrong, and building it again would be the third facility this programme has found built twice.

Two real defects sit next to it:

- **`setBusy(false)` fires on the ack, not on completion** (`MainWindow.cpp:3213`, and before `ok` is even checked). Generate re-enables about 2 ms after the click while the job is still queued.
- **No queue row ever appears.** `queueDock_` is permanently `nullptr` (`MainWindow.h:416`), so both "open the queue on submit" calls (`MainWindow.cpp:2976`, `:3229`) are dead code.

### 1.2 There are no GUI-thread waits in the generate path

No `QThread` subclass, no `moveToThread`, no `BlockingQueuedConnection`, no sleeps. The single `processEvents` and single `QEventLoop` are both in `ChainSelfTest.cpp:151` and selftest-only. The 19-second model-catalog scan is correctly on `QtConcurrent` (`ImageGenerationPage_catalog.cpp:119`).

The freezes are real but they are **elsewhere**, and the four this wave takes are the four every user crosses:

| worst case | where | what it waits on |
|---|---|---|
| **35 000 ms** | `shell/RuntimeProfile.cpp:279`, from the MainWindow ctor via `:1075`→`:1462` | spawns the Comfy venv to run `import sageattention`; skipped only if Comfy already answers (`MainWindow.cpp:1380`) |
| **1 400 ms per 1 500 ms tick** | `shell/FirstRunDialog.cpp:470/484`, timer at `:354` | a **93 % duty-cycle freeze**, in the dialog wave 2 just added a page to |
| **4 500 ms** | `MainWindow.cpp:3504/3518/3521`, `tearDownComfyOnExit` on `aboutToQuit` | the window hangs between clicking X and vanishing |
| GUI-thread decode | `ImagePreviewController.cpp:147` | decodes the full-resolution output on the GUI thread, landing exactly when a render finishes |

A 3× multiplier compounds the first-run numbers: `probeWorkerProtocol` (`RuntimeProfile.cpp:458-480`) spends the full `timeoutMs` on `waitForConnected`, **again** on `waitForBytesWritten`, and **again** in the read loop, because the deadline timer only starts at `:473`. `probeComfyProtocol` (`:108`/`:115`) clamps correctly — the two disagree, and the correct one is the model.

### 1.3 The push channel exists at both ends and is severed in the middle

- **Python emits.** `worker_tcp.py:58-66` `EventEmitter.emit()` is a real multi-frame writer; `:76-87` `progress(step, total)` computes a percentage. `image_runners.py:423-453` wires `callback_on_step_end` at `:796`/`:985` with genuine per-step data. A `ping` returns **3 frames in 1.83 ms** on the wire.
- **C++ consumes.** `ImageGenerationPage::applyWorkerMessage` (`ImageGenerationPage.cpp:2510-2555`) plus a dedicated `GenerationStatusController` are written and have **zero callers**.
- **The seam is one line.** `worker_service.py:1416` — `QueueEmitter.emit()` is `return`. Every generation goes through `enqueue`, so every frame is swallowed.

**Why it was stubbed, which the design must respect:** `EventEmitter` writes to `self.handler.wfile` — the *submitting connection*. `handle_enqueue_command` (`worker_tcp.py:185-192`) emits one ack and returns, ending that request. When the queue worker later runs the job there is no socket to write to. `QueueEmitter` is not lazy; it is a stub standing where a transport is missing.

**The visible consequence:** `QueueItem::progressPercent()` (`QueueManager.h:101`) returns 0, and `pass28sMinimumProgressForRank` (`MainWindow.cpp:223-234`) floors the bar at 3/7/**12** %. **Every ComfyUI render shows "Running, 12 %" for its whole duration.** Diffusers T2I/I2I gets a real percentage, sampled at 1800 ms.

Also: `MainWindow.cpp:3699` still comments that *"Direct worker messages own active progress"*. There are none.

### 1.4 Polling costs the most when nothing is happening

Three timers, none adaptive, none ever stopped — `stopPolling()` (`WorkerQueueController.cpp:497`) has zero callers.

| what | interval | measured |
|---|---|---|
| queue snapshot | 1800 ms (`WorkerQueueController.cpp:331`) | **1.75 ms**, 27 933 B |
| `ltx_ui_queue_history_contract` | same tick, **idle only** (`:464-481`) | **12.97 ms**, 921 B |
| VRAM (NVML) | 2000 ms (`MainWindow.cpp:5431`) | — |
| Comfy health | 3000 ms (`MainWindow.cpp:5534`) | — |
| Comfy `/history` | 1000 ms (`comfy_prompt_client.py:426`) | no step data; honestly emits `total=0` |

**The idle tick costs about 8× the busy tick** (~14.7 ms against 1.75 ms). There is no WebSocket anywhere in the tree — zero hits for `websocket`, `ws://` or `/ws` in `python/`, `qt_ui/` or `docs/`.

### 1.5 The hazard on record was already fixed

`CLAUDE.md` warned that `QUEUED → COMPLETED` silently fails behind a strict xfail. Corrected at `0ef2b5b`: `worker_service_state.py:389-397` walks the full path, there is no xfail marker, `pytest.ini` sets no `xfail_strict`, and the test passes. **There is no constraint to design around** — but the walk applies intermediate states *without emitting*, which is precisely this wave's subject.

---

## 2. Design

### 2.1 One consumer, two producers, in that order

The C++ consumer already exists and is unwired. Wire it once, then feed it from two sources built in sequence, so the wave ships a real moving bar even if the second producer proves difficult.

**Producer A — the queue item carries real progress (small, safe, first).** The queue worker records `step`/`total`/`message` onto the queue item as the job runs; `snapshot_payload()` carries them; the existing poll delivers real numbers. This is not push, and it is not pretending to be. It deletes the fake 12 % floor on its own.

**Producer B — a subscription channel (true push, second).** A second, long-lived connection sends `subscribe`, the worker registers that emitter in a fan-out set, and `QueueEmitter.emit()` forwards to every registered subscriber instead of returning. Authenticated with the existing per-launch session secret, and treated as an optimisation: if the subscription drops, the poll from Producer A is still delivering, so a dropped push degrades to a slower bar rather than a dead one.

**Why both, and in this order.** Producer A alone fixes what the user sees. Producer B alone is the architecturally right answer and carries the whole wave's risk — a new protocol command, a connection lifetime, reconnection, and auth. Sequencing them means the visible win is banked before the risk is taken.

### 2.2 Polling becomes adaptive, and the idle tick stops costing more

- While any job is active: **400 ms** (the busy tick is 1.75 ms, so this is affordable), or slower when Producer B is delivering.
- Idle: **3000 ms**, and the 12.97 ms `ltx_ui_queue_history_contract` request stops riding the idle tick — it is exactly backwards today.
- `stopPolling()` gains a caller, or is deleted. A function with no callers is a claim.

### 2.3 The four freezes

- **`RuntimeProfile.cpp:279`** — move the 35 s venv probe off the constructor. It answers a question nothing needs before the window is on screen.
- **`FirstRunDialog.cpp:470/484`** — the probe becomes asynchronous; the dialog paints and updates when the answer arrives. First fix `probeWorkerProtocol`'s 3× deadline bug (`RuntimeProfile.cpp:458-480`) by modelling it on `probeComfyProtocol`, which clamps correctly.
- **`MainWindow.cpp:3504-3521`** — the 4.5 s shutdown wait stops blocking the window's disappearance.
- **`ImagePreviewController.cpp:147`** — decode off the GUI thread.

### 2.4 Deliberately out of scope

The 10–18 s waits in Chain Studio, Character Studio and T2V History; the unbounded modals opened from async callbacks (`MainWindow.cpp:5638`, `T2VHistoryPage.cpp:1814` and neighbours); the dead duplicate-submit guard (`ImageGenerationPage.h:325-326, 639-640`, four declarations with no definitions); and the missing queue row (`queueDock_` permanently `nullptr`). All are recorded for wave 4.

---

## 3. Ratchets

Two new sweep rules, each proved against a planted violation before it is trusted — wave 1's final review found four of six rules narrower than their names.

- **`no-blocking-wait-on-the-gui-thread`** — flags `waitForFinished`/`waitForStarted`/`waitForReadyRead`/`waitForConnected`/`waitForBytesWritten` reached from a widget constructor or a signal handler, with a per-file baseline for what this wave does not fix. **Note the trap:** `tests/test_no_gui_sync_worker_rpc.py:29` currently asserts `"waitForFinished" in helper` — it *requires* the blocking wait to stay. That test must be read and reconciled before the rule is written, or the two will contradict each other.
- **`progress-is-not-invented`** — flags a floor or default applied to a progress percentage. `pass28sMinimumProgressForRank` (`MainWindow.cpp:223-234`) is the instance that exists; the rule keeps a new one from appearing once the real numbers arrive.

---

## 4. Success criteria

1. A ComfyUI render shows a progress figure that **changes at least five times** between submit and completion. Today it shows 12 % throughout.
2. `setBusy(false)` fires on completion or failure, not on the enqueue ack; Generate stays disabled while the job the click created is still running.
3. No GUI-thread block longer than **150 ms** on: cold app launch, the first-run dialog, submitting a generation, a render completing, and quitting.
4. The idle poll tick costs **less** than the busy tick, reversing today's 8×.
5. Both new ratchets at zero, each with a recorded planted-violation proof.
6. `ctest` and `pytest` green, and the wave-1 and wave-2 ratchets at their totals — currently ctest 24/24, pytest 2026 passed / 14 skipped / 6 deselected, sweeps 201 across 29 rules with 23 at zero.

Every criterion is measured into a Results section of this document before the wave closes. Wave 1 shipped numbers that lived only in git-ignored directories and its own review called that the central failure.

---

## 5. Risks

- **Producer B is the whole wave's risk.** A new protocol command, a connection lifetime and an auth path. Sequencing it second means the wave still delivers if it is cut.
- **`applyWorkerMessage` has no test at all** and neither does `syncBottomTelemetry` — including its rank ratchet (`MainWindow.cpp:5861`, `qMax(displayedRank, observedRank)`, which cannot be walked back), the `svTelemetrySawActive` latch (`:5783`) and the 900 ms idle pulse (`:5836`). The bottom-bar flash bug was found by eye, not by a test. Anything that writes those properties needs a guard written first.
- **`WorkerSocketClient::parseLastJsonObject` (`:47-63`) walks backwards and keeps one line**, which the protocol forbids at line 475 and which silently discards every frame but the last. Multi-frame delivery does not work until that is fixed, and nothing currently fails because of it.
- **The 3 % / 7 % / 12 % floor is load-bearing for the current UI.** Removing it before real numbers arrive would show 0 % for a working render, which is worse than a wrong number.
