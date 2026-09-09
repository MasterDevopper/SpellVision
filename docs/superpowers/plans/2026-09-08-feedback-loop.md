# Feedback Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a running generation tell the truth about itself — real progress that moves, a Generate button that reflects the job rather than the ack — and stop the app freezing on the four paths every user crosses.

**Architecture:** The C++ progress consumer already exists and is unwired. Wire it once, then feed it from two producers in sequence: the queue item carrying real `step`/`total` (delivered by the existing poll), then a subscription channel that pushes. Sequencing banks the visible win before the wave's only real risk.

**Tech Stack:** C++17, Qt 6.10.2, CMake + MSVC, Python 3.12 worker over local TCP/JSON, pytest, QtTest, sweep ratchets.

**Spec:** `docs/superpowers/specs/2026-09-08-feedback-loop-design.md`

## Global Constraints

- **Do NOT stop the worker on port 8765** and do NOT touch anything under `runtime/`.
- **Do NOT run `Capture-SvThemes.ps1` or any full-screen capture** — it grabs a fixed screen region and photographs the owner's live personal desktop. Render offscreen with `QWidget::grab()`.
- **NEVER launch `SpellVision.exe` directly** — an accidental launch earlier in this programme dirtied the owner's real registry.
- `Stop-Process -Name SpellVision -ErrorAction SilentlyContinue` before EVERY build, or the link fails with LNK1168.
- Build: `cmake --build build --config Debug` from the repo root. Re-run configure only if `CMakeLists.txt` changed: `cmake -S . -B build -G "Visual Studio 17 2022" -A x64`.
- Tests: `ctest --test-dir build -C Debug --output-on-failure` and `$env:PYTHONPATH=""; .\.venv\Scripts\python.exe -m pytest tests -q`. Baselines at the start of this wave: **ctest 24/24, pytest 2026 passed / 14 skipped / 6 deselected, sweeps TOTAL 201 across 29 rules with 23 at zero.**
- **A C++ test touching `ThemeManager` or `ShellLayout` writes the REAL settings store** — both construct `QSettings("DarkDuck","SpellVision")` explicitly, so redirection is a no-op. Back up in `initTestCase`, restore in `cleanupTestCase`, keep any guard case LAST. Finish with `appearance/themePreset` `0x3`, `appearance/surfaceStyle` `0x2`, `ui/shellLayout` ABSENT, `setup/firstRunWizard_v1` unchanged.
- **A C++ test process is NOT the app.** It gets `SvStyle`, the bundled IBM Plex fonts and `applyApplicationChrome()` only if it asks — `tests/cpp/AppEnvironment.h` is the shared helper. Any assertion about colour, surface or text metrics needs it, and needs a stated THRESHOLD rather than `!=`.
- **`logging.info` is invisible** — the root logger defaults to WARNING. Promote diagnostics to `log.warning` or above; on the C++ side use `qWarning`.
- Sweep baselines in `tests/sweeps/exemptions.py` are ONE-WAY: a rise fails the build, a fall must be lowered in the same commit.
- Locate every edit site BY NAME, never by the line numbers in this plan — they are from `5e2bcff` and will shift. Read the file immediately before editing it.
- No object name may be renamed: tests, stylesheet selectors and the UIA capture scripts key off them.
- **No `Co-Authored-By` trailer on commits in this repo.**

## Verification standard

A test is a claim until it has been SEEN to fail. Plant every defect your cases claim to catch, confirm the right case fails naming it, run a CONTROL with the code restored, and report each exact failure message.

**GREEN IS NOT EVIDENCE — three different things print it**, all of which occurred in wave 2: a plant that never took, a defect that genuinely is not there, and an allowance too wide to notice one. Establish each separately: grep the planted line back off disk, confirm that translation unit recompiled, confirm a case exists naming the subject, confirm the allowance is narrow enough to fail.

**Ask what else would make an assertion pass.** Wave 2 produced four guards that passed for a reason other than their subject. Watch the tautology: if the asserted value and the compared value both come from the code under test, any deterministic wrong answer reproduces faithfully. Anchor one side outside it.

**Suspect the instrument before the subject** when a measurement moves under re-examination.

C++ mutation recipe: real flags from `build/SpellVisionCore.dir/Debug/SpellVisionCore.tlog/CL.command.1.tlog`; `lib.exe /remove:<X>.obj` on a COPY of `SpellVisionCore.lib`; relink from the UNMODIFIED tracked test object; run the mutant from `build/Debug`; restore by REWRITING in place, never from a `.bak`. Python sweep rule: import it and call it on mutated text in memory, confirming it reports AT THE PLANTED LINE.

---

### Task 1: The reader stops throwing frames away

**Files:**
- Modify: `qt_ui/workers/WorkerSocketClient.cpp` (`parseLastJsonObject`, and the `readyRead` handler that calls it)
- Test: `tests/cpp/test_worker_socket_frames.cpp` (create), `CMakeLists.txt`

**Interfaces:**
- Produces: the socket client delivers EVERY complete JSON line it receives, in order, instead of the last one only. Later tasks depend on this; nothing works until it is true.

Nothing currently fails because of this, which is why it must be tested before it is fixed.

- [ ] **Step 1: Read the two functions and write down what they do**

`parseLastJsonObject` walks the buffer BACKWARDS and keeps one line. `docs/SPELLVISION_WORKER_PROTOCOL.md` line 475 forbids exactly that. Read both the function and that protocol line before changing anything, and record in your report what the protocol says the client must do.

- [ ] **Step 2: Write the failing test**

Feed the client a buffer containing three complete JSON objects separated by newlines, plus a trailing partial object. Assert: three parsed frames delivered in order, the partial retained for the next read, and the third frame's content matching the LAST object — so a regression to last-only behaviour still fails on the count, not merely on the content.

- [ ] **Step 3: Run it and watch it fail**

Expected: one frame delivered where three were required.

- [ ] **Step 4: Make it pass**

Parse each complete line in the `readyRead` handler; keep the remainder buffered. Preserve the existing 8 MiB cap, the timeout, and the `RemoteHostClosedError` handling — those are correct and tested.

- [ ] **Step 5: Prove it bites**

Plant the old backwards-walk back in; confirm the new case fails naming the frame count; run a clean control.

- [ ] **Step 6: Commit**

---

### Task 2: Guards for the telemetry nobody tested

**Files:**
- Test: `tests/cpp/test_bottom_telemetry.cpp` (create), `CMakeLists.txt`
- Read only: `qt_ui/MainWindow.cpp` (`syncBottomTelemetry`), `qt_ui/ImageGenerationPage.cpp` (`applyWorkerMessage`)

`syncBottomTelemetry` keeps seven dynamic properties of client-invented state and has **no test**. Its flash bug was found by eye. Every later task in this wave writes those properties, so the guards come first.

**Interfaces:**
- Produces: named cases covering the rank ratchet, the `svTelemetrySawActive` latch, the completed-rows-at-submit denominator, and the 900 ms idle pulse.

- [ ] **Step 1: Write a case per behaviour, each asserting what is ON SCREEN**

Cover, at minimum: the rank ratchet (`qMax(displayedRank, observedRank)`) cannot be walked back; a submit followed by an empty snapshot inside the 0–1800 ms window does NOT trip completion; the completed-rows denominator survives a mode switch that changes the proxy-filtered row count. Assert visible text and state, not internal members.

- [ ] **Step 2: Prove each one bites**

Plant a defect per case — remove the `qMax`, clear the latch, drop the denominator's mode-awareness — and confirm the matching case fails naming it. Report every message. A case that cannot be made to fail is decoration.

- [ ] **Step 3: Commit**

---

### Task 3: Producer A — the queue item carries real progress

**Files:**
- Modify: `python/worker_service.py` (`QueueEmitter`), `python/worker_queue.py` (the queue item and `snapshot_payload`)
- Modify: `qt_ui/QueueManager.h` / its `.cpp` (`progressPercent`), `qt_ui/MainWindow.cpp` (`pass28sMinimumProgressForRank`)
- Test: `tests/test_worker_queue_progress.py` (create), plus a C++ case

**Interfaces:**
- Consumes: Task 1's frame delivery.
- Produces: a queue item exposing real `step`, `total` and `message`; `QueueItem::progressPercent()` returning a figure that moves.

- [ ] **Step 1: The Python side records progress onto the queue item**

`QueueEmitter.emit()` currently returns. Give it the job of updating the queue item from the payload it is handed — it already has `queue_manager` and `queue_item_id`. `emit_job_update` shows the shape. Carry `step`, `total` and `message` into `snapshot_payload()`.

- [ ] **Step 2: A pytest that watches the numbers move**

Submit a job through the live-worker harness and assert the snapshot's progress **changes at least five times** and is monotonic non-decreasing. Do NOT assert exact values; assert movement and ordering, which is what the criterion is.

- [ ] **Step 3: Delete the invented floor, in the same commit as the real numbers**

`pass28sMinimumProgressForRank` floors the bar at 3/7/12 %. Remove it ONLY once real numbers arrive — the spec's risk section says why: 0 % for a working render is worse than a wrong number. If any family still has no real progress, the floor must stay for that family and the report must name it.

- [ ] **Step 4: Prove it bites**

Plant `QueueEmitter.emit()` back to `return` and confirm the pytest fails on the movement count. Plant the floor back and confirm the C++ case catches an invented figure.

- [ ] **Step 5: Commit**

---

### Task 4: Generate reflects the job, not the ack

**Files:**
- Modify: `qt_ui/MainWindow.cpp` (the `setBusy(false)` at the enqueue response, and the completion path)
- Test: `tests/cpp/test_bottom_telemetry.cpp` (extend)

Today `setBusy(false)` fires on the ack and before `ok` is even checked, so Generate re-enables about 2 ms after the click while the job is still queued.

- [ ] **Step 1: Write the failing case**

Submit, let the ack arrive, and assert Generate is STILL disabled; then complete the job and assert it re-enables. Assert `isEnabled()` on the real button, not an internal flag.

- [ ] **Step 2: Fix, keeping the failure path honest**

A failed enqueue must re-enable immediately — the button is disabled by a job that now does not exist. Check `ok` before deciding.

- [ ] **Step 3: Prove both directions bite, then commit**

Plant the early `setBusy(false)` back and confirm the case fails; plant a failed-enqueue path that leaves the button disabled and confirm the second case fails.

---

### Task 5: The poll costs least when nothing is happening

**Files:**
- Modify: `qt_ui/workers/WorkerQueueController.cpp` (the 1800 ms timer, the idle-only second request, `stopPolling`)
- Test: `tests/cpp/test_worker_queue_controller.cpp` (create or extend)

Today the idle tick costs ~8× the busy tick, because a 12.97 ms `ltx_ui_queue_history_contract` request fires ONLY when idle.

- [ ] **Step 1: Write the failing case**

Assert the interval while a job is active is shorter than the idle interval, and that the expensive second request does NOT ride the idle tick. Anchor on observable request counts over a simulated period, not on the timer's configured value alone — a constant read back from the object under test proves nothing.

- [ ] **Step 2: Implement**

400 ms active, 3000 ms idle. Move the contract request off the idle tick. Give `stopPolling()` a caller or delete it — a function with no callers is a claim.

- [ ] **Step 3: Prove it bites, then commit**

---

### Task 6: Producer B — the subscription channel

**Files:**
- Modify: `python/worker_tcp.py` (a `subscribe` command and a fan-out registry), `python/worker_service.py` (`QueueEmitter` forwards to subscribers)
- Modify: `qt_ui/workers/WorkerSocketClient.{h,cpp}` (a long-lived subscriber connection), the C++ consumer wiring
- Modify: `docs/SPELLVISION_WORKER_PROTOCOL.md`
- Test: `tests/test_worker_subscribe.py` (create), plus a C++ case

**This task carries the wave's risk.** It is sequenced last among the producers so that everything above still ships if it is cut.

**Interfaces:**
- Consumes: Task 1's frame delivery; Task 3's progress payloads.
- Produces: pushed frames on a second connection, with the poll as the recovery path.

- [ ] **Step 1: Read how auth works before designing the command**

The per-launch session secret is worker-owned. Read `python/worker_auth.py` and the protocol doc, and state in your report how a long-lived subscriber authenticates and what happens when the secret rotates.

- [ ] **Step 2: The Python side**

A `subscribe` command registers the request's `EventEmitter` in a fan-out set; `QueueEmitter.emit()` forwards to every live subscriber. A dead subscriber is dropped on the first write failure — `EventEmitter` already tracks `client_disconnected`.

- [ ] **Step 3: The C++ side**

A second, long-lived connection that subscribes and feeds the SAME consumer Task 3 wired. On disconnect, reconnect with backoff; while disconnected, the poll from Task 5 is still delivering, so the bar slows rather than stopping.

- [ ] **Step 4: Prove the degradation, not just the happy path**

The important case is the one nobody writes: kill the subscription mid-render and assert progress KEEPS MOVING from the poll. Plant a subscription that never reconnects and confirm the case still passes — then plant a poll that stops when the subscription exists and confirm it fails.

- [ ] **Step 5: Update the protocol doc and commit**

Adding a worker command trips three ratchets in this repo — the wire-type registry, the audience list, and the protocol-doc counts. Expect them and fix them in the same commit.

---

### Task 7: The probe that spends its timeout three times

**Files:**
- Modify: `qt_ui/shell/RuntimeProfile.cpp` (`probeWorkerProtocol`)
- Modify: `qt_ui/shell/FirstRunDialog.cpp` (the timer-driven probe)
- Test: `tests/cpp/test_runtime_probe.cpp` (create)

`probeWorkerProtocol` spends the full `timeoutMs` on `waitForConnected`, again on `waitForBytesWritten`, and again in the read loop — the deadline timer only starts partway through. `probeComfyProtocol` clamps correctly and is the model. The consequence is a first-run dialog blocking 1400 ms out of every 1500 ms tick: a 93 % duty-cycle freeze in the dialog wave 2 just added a page to.

- [ ] **Step 1: Write the failing case**

Point the probe at a port that accepts and never answers, and assert the total elapsed time is within one timeout plus a small margin. Measure the wall clock; do not read the configured value back.

- [ ] **Step 2: Fix the deadline, modelling `probeComfyProtocol`**

- [ ] **Step 3: Make the first-run probe asynchronous**

The dialog paints and updates when the answer arrives. Assert the GUI thread is never blocked more than 150 ms across a full tick.

- [ ] **Step 4: Prove both bite, then commit**

---

### Task 8: Launch and quit stop freezing

**Files:**
- Modify: `qt_ui/shell/RuntimeProfile.cpp` (the 35 s venv probe), `qt_ui/MainWindow.cpp` (the ctor call site and `tearDownComfyOnExit`)
- Test: `tests/cpp/test_runtime_probe.cpp` (extend)

The venv probe spawns the Comfy interpreter to run `import sageattention` with a 5 s start plus 30 s finish wait, from the MainWindow constructor. `tearDownComfyOnExit` blocks up to 4.5 s on `aboutToQuit`, so the window hangs between clicking X and vanishing.

- [ ] **Step 1: Move the probe off the constructor**

Nothing needs its answer before the window is on screen. Whatever consumes it must handle "not known yet" rather than assuming a value.

- [ ] **Step 2: The shutdown wait stops blocking the window's disappearance**

- [ ] **Step 3: Assert both**

Cold-construct with no Comfy listening and assert the constructor returns within 150 ms; assert the quit path does not block. Plant the blocking calls back and confirm both fail.

- [ ] **Step 4: Commit**

---

### Task 9: The output decodes off the GUI thread

**Files:**
- Modify: `qt_ui/preview/ImagePreviewController.cpp`
- Test: `tests/cpp/test_image_preview_controller.cpp` (create or extend)

It decodes the full-resolution output on the GUI thread, landing exactly when a render finishes — the worst possible moment.

- [ ] **Step 1: Write the failing case** — decode a large image through the controller and assert the GUI thread is not blocked beyond 150 ms.
- [ ] **Step 2: Move the decode to `QtConcurrent`, delivering the result on the GUI thread.** Handle a controller destroyed while a decode is in flight; that is the defect this shape usually ships with.
- [ ] **Step 3: Prove it bites, then commit.**

---

### Task 10: Two ratchets, each proved

**Files:**
- Modify: `tests/sweeps/rules.py`, `tests/sweeps/exemptions.py`, `tests/test_sweeps.py`
- Read and reconcile: `tests/test_no_gui_sync_worker_rpc.py`

- [ ] **Step 1: Reconcile the contradiction FIRST**

`tests/test_no_gui_sync_worker_rpc.py:29` asserts `"waitForFinished" in helper` — it REQUIRES the blocking wait to stay, which is the opposite of what its filename suggests and of the rule you are about to write. Read it, decide, and record the ruling. Do not write a rule that contradicts a passing test.

- [ ] **Step 2: `no-blocking-wait-on-the-gui-thread`**

Flags `waitForFinished` / `waitForStarted` / `waitForReadyRead` / `waitForConnected` / `waitForBytesWritten` reached from a widget constructor or a signal handler. Per-file baseline for what this wave does not fix — Chain Studio, Character Studio, T2V History.

- [ ] **Step 3: `progress-is-not-invented`**

Flags a floor or default applied to a progress percentage, so a new one cannot appear once real numbers arrive.

- [ ] **Step 4: Prove BOTH by planting violations in memory**

Import each rule and call it on mutated text; confirm it reports AT THE PLANTED LINE, and confirm three negatives stay silent. Record each rule's REAL coverage, not its name — wave 1's final review found four of six rules narrower than their names.

- [ ] **Step 5: Commit**

---

### Task 11: Measure the six criteria into the spec

**Files:**
- Modify: `docs/superpowers/specs/2026-09-08-feedback-loop-design.md` (add a Results section)

- [ ] **Step 1: Measure all six**

1. A ComfyUI render's progress figure changes at least five times. 2. `setBusy(false)` fires on completion, not the ack. 3. No GUI-thread block over 150 ms on cold launch, first run, submit, completion, quit. 4. The idle tick costs less than the busy tick. 5. Both ratchets at zero with planted-violation proofs. 6. ctest and pytest green, wave 1 and 2 ratchets at their totals.

Criterion 1 needs a REAL ComfyUI render, not a simulated job — the whole wave exists because the ComfyUI path is the one that shows a frozen 12 %. Criterion 3 wants wall-clock measurements on the GUI thread, not reasoning about which calls are blocking.

- [ ] **Step 2: Write a Results table with a measured value and an explicit pass or miss per row**

A row you could not measure says so, with the reason. An honest gap beats a number nobody took. Wave 1 shipped a spec whose numbers lived only in git-ignored directories and its review called that the central failure.

- [ ] **Step 3: Commit**

---

## Self-review

**Spec coverage.** §1.1 the ack and `setBusy` — Task 4; the dead queue row is explicitly out of scope (§2.4). §1.2 the four freezes — Tasks 7, 8, 9. §1.3 the severed push channel — Tasks 1, 3, 6. §1.4 adaptive polling — Task 5. §1.5 no constraint to design around — nothing to build. §2.1 one consumer two producers — Tasks 3 and 6 share the consumer wired in Task 3. §3 both ratchets — Task 10, each with a planted proof. §4 the six criteria — Task 11. §5 risks: `applyWorkerMessage` and `syncBottomTelemetry` untested — Task 2, deliberately before anything writes them; `parseLastJsonObject` — Task 1, first; the floor is load-bearing — Task 3 Step 3 removes it only alongside real numbers.

**Placeholders.** None. Where this plan does not quote code it says to read the file first, because every line number here is from `5e2bcff` and will shift — and because two waves of this programme were damaged by specs describing mechanisms the code did not have.

**Ordering.** Task 1 precedes 3 and 6 because nothing multi-frame works until the reader keeps its frames. Task 2 precedes 3 and 4 because both write telemetry that has no guard today. Task 3 precedes 6 so the visible win is banked before the wave's risk is taken. Task 10 follows 7–9 so the baselines describe the tree as it will ship.

---

### Task 12: ComfyUI's own progress, and a bottom bar that shows both halves

**Added 2026-09-08**, after the owner ran the build and reported that the bar never moves and that the strip shows elapsed without remaining. Spec §2.2b and §2.2c.

**Files:**
- Create: `python/comfy_progress_socket.py`
- Modify: `python/comfy_prompt_client.py` (the 1 Hz `/history` poll and its honest `total=0`)
- Modify: `qt_ui/MainWindow.cpp` (`syncBottomTelemetry` and the telemetry strip's layout)
- Test: `tests/test_comfy_progress_socket.py`, plus a C++ case in `tests/cpp/test_bottom_telemetry.cpp`

**Interfaces:**
- Consumes: the consumer wired in Task 3; the frame delivery from Task 1.
- Produces: per-step progress for ComfyUI families, and a strip showing elapsed, an estimated remaining, and a bar whose fill is the real percentage.

- [ ] **Step 1: Establish what ComfyUI actually sends before writing a client**

There are ZERO references to `websocket`, `ws://` or `/ws` in this tree, so nothing here is grounded yet. Connect to the live ComfyUI on `127.0.0.1:8188`, run one real render, and CAPTURE the message stream. Write down the message types, their fields, and which of them carry a step count against a total. Source the shape from that capture, never from memory of ComfyUI's API — this repo has a standing rule about grounding node and protocol details in a live dump, and it exists because guessing cost a wave.

- [ ] **Step 2: The client, fed by the capture**

A small consumer that subscribes to ComfyUI's socket for the prompt ids we submitted, and reports step/total onto the job the same way `image_runners.py` does for diffusers. `comfy_prompt_client.py:440` currently emits `total=0` deliberately and honestly; it stops needing to.

- [ ] **Step 3: Prove the numbers are ComfyUI's, not a timer's**

The trap this wave exists to avoid is a figure that moves for the wrong reason. Assert the reported steps match the capture's, and plant a version that interpolates from elapsed time — the case must fail. A bar that moves smoothly because something is guessing is the defect, not the fix.

- [ ] **Step 4: The bottom bar shows elapsed AND remaining**

Both, in the width already there — the strip has unused space, so this is not a space problem. The bar's fill carries the percentage rather than a separate widget. **Remaining is an ESTIMATE and must be labelled as one**, and it must never be derived from a floor or from a fake tick: this programme has already shipped one confidently wrong ETA. Until Task 12 Step 2 lands for a given family, that family shows elapsed alone.

- [ ] **Step 5: Prove the strip, then commit**

Plant a remaining figure computed from the floor and confirm a case catches it. Watch the two known traps in this strip: the rank ratchet uses `qMax` and cannot be walked back, and long labels already clip here (`Runtime / Comfy Manager` needs 132 px in an 82 px box) — do not add a field that makes that worse without measuring it.
