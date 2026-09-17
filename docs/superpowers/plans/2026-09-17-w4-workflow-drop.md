# W4 Workflow Drop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop a ComfyUI workflow anywhere on the window and SpellVision loads it, works out what kind of generation it is, switches to that page, and fills the cockpit in — so the user never has to know which tab a graph belonged to.

**Architecture:** The worker already classifies a workflow by its outputs and already extracts a rich draft from a compiled prompt. Both answers are computed today and thrown away by the drop path. W4 adds a window-level drop target, routes on the classification instead of on where the mouse happened to be, and makes the drop path use the same rich draft the Flows page already builds.

**Tech Stack:** C++17/Qt6, Python 3.12 stdlib, existing worker TCP protocol, QTest.

**Spec:** `docs/superpowers/specs/2026-09-15-t2-t6-completion-design.md` §4. **The code inventory this plan is built on, with file:line for every site: `docs/superpowers/specs/2026-09-15-t2-t6-research/t2-context.md`. Each task names the part it needs.** Owner requirement: Doc 54 §1 T2, plus the "Owner T7 holes" note that the owner has real workflows to drop-test.

## Global Constraints

- C++17, Qt 6.10.2; Python 3.12 **stdlib only**. No new dependencies.
- Modules under 300 lines. Python test files need `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))`.
- **`Stop-Process -Name SpellVision` before every build** or the link fails `LNK1168`. Build: `.\scripts\dev\rebuild_ui.ps1`. `ctest` needs `-C Debug`.
- **Compare against the current gate: `ctest -C Debug` 31 of 32**, the one failure `shell_layout` pre-existing. ~20 Python failures also fail on a clean tree. Neither is yours; neither may hide a new one.
- Theme tokens for colour, spacing tokens for spacing. For a caption prefer `spellvision::widgets::ElidingLabel`; a second unnamed `ErrorPillLabel` on a page silently steals an existing test's `findChild`.
- A new worker command trips four ratchets: `worker_command_audience.py`, the wire-type registry in `python/worker_client.py`, protocol-doc counts, and `ARCHITECTURE.md` + the counts in `docs/design/53_consistency_and_robustness_audit.html`.
- **No `Co-Authored-By` trailer.**
- **`test_godfile_split` already fails**: `ImageGenerationPage.cpp` is ~3135 lines against a 3000 ceiling. Do not add to that file. New behaviour goes in a new unit — which is what the ceiling is for.

## What exists today, and what the drop path does with it

The worker's `import_workflow` returns `inferred_task_command`, `inferred_media_type`, `capability_report`, `supported_modes` and `classification_confidence`. `workflow_scanner.py:860-1033` computes them properly — **by output, not by node family**: a video output with an image source is `i2v`, a video output alone is `t2v`, an image output with an image source is `i2i`, and so on, with contradiction penalties on the confidence.

The drop path throws all of it away. `MainWindow.cpp:2678-2790` builds a draft carrying four paths, a warnings array, and `safe_to_submit` **hardcoded to false** with a comment saying the importer reports no launch readiness. So a dropped workflow lands on whatever page the mouse was over, fills nothing, and cannot run.

Meanwhile `WorkflowLibraryPage::buildReusableDraft` (`qt_ui/WorkflowLibraryPage.cpp:2709-2902`) already walks a compiled prompt for KSampler, CLIPTextEncode, checkpoint and LoRA loaders and produces exactly the rich draft the cockpit wants. The drop path never asks for a compiled prompt, so it never gets there.

**This wave is mostly about using answers that already exist.**

---

## Task 1: One mode resolver

**Files:**
- Modify: `qt_ui/workflows/WorkflowLaunchController.{h,cpp}`, `qt_ui/HomePage.cpp`, `qt_ui/WorkflowLibraryPage.cpp`
- Create: `tests/cpp/test_workflow_mode_resolver.cpp`; modify `CMakeLists.txt`
- Read first: `t2-context.md` §"Classification"

**Interfaces:**
- `WorkflowLaunchController::resolveModeId(const QJsonObject &importResultOrProfile) -> QString` — the single answer, returning an empty string when the workflow is not a generation workflow.
- `WorkflowLaunchController::modeResolution(...) -> struct { QString modeId; QString reason; double confidence; bool routable; }` — the answer plus why, because the UI has to explain a refusal.

**Why:** three C++ sites derive a mode independently today — `WorkflowLaunchController::resolveDraftModeId` (`:36-60`), `HomePage::inferModeFromWorkflowProfile` (`HomePage.cpp:128-154`) and `WorkflowLibraryPage`'s own normalisation. The Home one falls back to **matching substrings in the file path** and then to `t2i`, so a workflow whose classification failed is routed by its filename and lands somewhere plausible-looking. Three resolvers for one question is the defect Doc 50 rule 5 names, and W2 removed the same shape from sampling defaults.

- [ ] **Step 1: Write the failing C++ test**

`tests/cpp/test_workflow_mode_resolver.cpp`. Cases:
1. `inferred_task_command: "i2v"` resolves `i2v`.
2. A `capability_report.primary_task` of `t2v` with no `inferred_task_command` resolves `t2v`.
3. **A `user_task_override` beats the inference** (Flows already supports that; it must survive the consolidation).
4. `v2v`, `audio` and an unrecognised verdict resolve to **empty with a reason**, not to `t2i`.
5. **A workflow whose classification is absent resolves to empty — never to a guess from the file path.** Plant the old substring fallback and watch this fail.
6. A hidden mode (`chain`, `gen3d`, `train` — `ShellNavigationController.h:17-36`) resolves empty with a reason naming it as unavailable, so the drop path can say so rather than switching to a page the rail does not show.

- [ ] **Step 2: Run to verify it fails.** `ctest -C Debug -R workflow_mode_resolver`
- [ ] **Step 3: Implement**, then make `HomePage` and `WorkflowLibraryPage` call it. Delete the path-substring fallback outright — do not keep it behind a flag.
- [ ] **Step 4: Run; expect 32 of 33** (the new target plus the pre-existing `shell_layout`).
- [ ] **Step 5: Prove case 5 bites** — restore the substring fallback, rebuild, watch it fail, revert, rebuild, watch it pass. **Rebuild between plant and revert** or the experiment proves nothing.
- [ ] **Step 6: Add the ratchet** `one-workflow-mode-resolver`: no function outside `WorkflowLaunchController` derives a mode from a workflow profile or import result. Write its self-test in `tests/test_sweeps.py` — **not optional; W2 shipped a rule whose self-test was never written and the final review caught it.**
- [ ] **Step 7: Commit.**

```
refactor(workflows): one answer to "what kind of generation is this"

Three sites derived it independently and the Home one fell back to matching
substrings in the FILE PATH and then to t2i -- so a workflow whose
classification failed was routed by its filename and landed somewhere
plausible-looking. The worker already decides this properly, by output
rather than by node family. Now one place asks it, and a workflow that is
not a generation workflow resolves to nothing with a reason instead of to
a guess.
```

---

## Task 2: The window accepts a workflow anywhere

**Files:**
- Create: `qt_ui/shell/WindowDropTarget.{h,cpp}`
- Modify: `qt_ui/MainWindow.{h,cpp}`
- Create: `tests/cpp/test_window_drop_target.cpp`; modify `CMakeLists.txt`
- Read first: `t2-context.md` §"Drop entry points"

**Interfaces:**
- `WindowDropTarget` — an event filter installed on the application, deciding whether a drag carries something the window handles and emitting `workflowDropped(QString path)` / `imageDropped(QString path)`.
- `WindowDropTarget::classifyDrop(const QMimeData *) -> enum { Workflow, Image, Ignored }`

**Today** `MainWindow` has no `dragEnterEvent`, no `dropEvent`, no `setAcceptDrops` — verified by a repo-wide grep. Only leaf widgets accept drops, so a `.json` dropped on the rail, the title bar, Flows, Home, History or Settings is silently discarded. The user gets no feedback at all, which reads as the app being broken rather than as the drop being in the wrong place.

**Design points:**
- **Prompt editors must keep `setAcceptDrops(false)`** (`ImageGenerationPage.cpp:718`, `:745`, and the studios) — that was a deliberate fix so a dropped file does not become pasted text. The window-level filter must handle their drops rather than letting them swallow the file. Verify that behaviour survives; `tests/test_first_run_honesty.py:545-593` covers it.
- **An image dropped on a generation page must keep today's behaviour.** The window filter routes a `.json`; it must not hijack the image drops the cockpit already handles per page (`t2-context.md` §1 lists every one).
- A drag-enter carrying a workflow shows an overlay saying so. A drag carrying something unhandled shows nothing — silence is correct for a file the app has no use for, an overlay that appears and then rejects is not.

- [ ] Steps: failing test (a synthetic `QDropEvent` on the title bar, on the rail, and on a page with no drop handling, each reaching the window handler; an image drop on the cockpit still handled by the cockpit; a prompt editor's drop reaching the window rather than becoming text) → implement → build → `responsive_matrix` still green → prove the prompt-editor case bites → commit.

---

## Task 3: The drop asks for everything the worker already knows

**Files:**
- Create: `qt_ui/workflows/WorkflowDropCoordinator.{h,cpp}`
- Modify: `qt_ui/MainWindow.cpp` (the `workflowFileDropped` lambda shrinks to a call)
- Create: `tests/cpp/test_workflow_drop_coordinator.cpp`
- Read first: `t2-context.md` §"Import path" and §"WorkflowDownloadDialog"

**The sequence**, each step of which exists already and is simply not chained:

```
import_workflow
   → missing nodes or models?  → WorkflowDownloadDialog (exists, MainWindow.cpp:2756)
   → compile_workflow_prompt   (exists; the drop path never calls it)
   → check_workflow_launch_readiness  (exists; Flows calls it, the drop path does not)
   → WorkflowDraftBuilder      (Task 4)
   → resolveModeId             (Task 1)
   → ensureGenerationPageBuilt → applyWorkflowDraft → switchToMode
```

**`safe_to_submit` stops being hardcoded false** and becomes the readiness verdict. That single literal (`MainWindow.cpp:2690`) is why a dropped workflow cannot run today, and its comment — "importer reports no launch readiness" — is true of the *importer* and false of the *system*, which has a readiness command Flows already uses.

**Put the coordinator in its own unit.** `MainWindow.cpp` is a god file and `ImageGenerationPage.cpp` already fails its size ceiling; a 180-line lambda is how both got that way.

- [ ] Steps: failing test with a fake worker returning each stage's reply (including a workflow that needs nodes, one that is not routable, one where readiness says not-ready) → implement → build → prove `safe_to_submit` tracks readiness by planting a not-ready verdict and asserting Generate stays disabled → commit.

---

## Task 4: The draft carries the cockpit's values

**Files:**
- Create: `qt_ui/workflows/WorkflowDraftBuilder.{h,cpp}` (moved out of `WorkflowLibraryPage`)
- Modify: `qt_ui/WorkflowLibraryPage.cpp` to call it
- Create: `tests/cpp/test_workflow_draft_builder.cpp`
- Read first: `t2-context.md` §"Import path", the `buildReusableDraft` paragraph

**`WorkflowLibraryPage::buildReusableDraft` (`:2709-2902`) already does this work** — it walks a compiled prompt for KSampler, CLIPTextEncode, checkpoint and LoRA loaders. Move it to a unit both callers share, rather than writing a second extractor.

**Populated means:** prompt, negative, checkpoint (via `trySetSelectedModelByCandidate`), LoRA stack, sampler, scheduler, steps, cfg, seed, width, height, frames, fps, and the input image for i2i/i2v. Plus the "Loaded from workflow: <name>" chip **with a Detach action** that returns the page to native graphs — a state the user can enter and cannot leave is a trap, and `workflowDraftBlocking_` already exists to gate submission.

**One thing to get right:** `buildReusableDraft` refuses v2v/audio/3d (`:2716-2723`). Keep that refusal, and make sure the coordinator surfaces it as the same "not routable" message Task 1 produces, rather than as two different failures for one cause.

- [ ] Steps: failing tests over the three owner workflows already in `runtime/imported_workflows` (Compact T2I v10, Krea2 Pro Grade v17, Character Forge) asserting each yields the right mode and a populated draft → move the function → both callers use it → prove the move is behaviour-preserving by running the existing Flows tests → commit.

---

## Task 5: Python — readiness on the import reply, and the three owner workflows as fixtures

**Files:**
- Modify: `python/workflow_library_commands.py`
- Create: `tests/test_workflow_drop_contract.py`
- Read first: `t2-context.md` §"Import path"

`WorkflowImportResult` has no launch-readiness field, so the C++ must make a second round trip to learn whether a dropped workflow can run. Add it to the import reply — the readiness check already exists and Flows already calls it.

Fixtures: the owner's real workflows. **Do not invent a synthetic graph** — the classification's whole job is to handle graphs nobody on this project wrote.

- [ ] Steps: failing test asserting the import reply carries a readiness verdict and that each owner workflow classifies to the mode it actually is → implement → run against the real files → protocol doc + its counts → commit.

---

## Task 6: The live proof

**Files:** `docs/design/55_t7_ship_walkthrough.html`, captures in `docs/design/55_t7_assets/`

- [ ] **Drop each of the three owner workflows on a part of the window that is not a cockpit** — the title bar, the rail, the Flows page — and capture: the overlay, the dialog when nodes are missing, the page it landed on, and the populated cockpit.
- [ ] **Generate once from a dropped workflow** and capture the dest.
- [ ] **Capture a refusal**: drop something that is not a generation workflow and show the message naming why, rather than a silent landing on T2I.
- [ ] Write it into the walkthrough. **Do not paint T2 green** — the owner's bar is their real workflows drop-tested, and this proves three. Say which three and what is untested.

---

## Self-Review

**Spec §4 coverage:** window-level drop (2) · routing on the classification (1, 3) · the rich draft (4) · `safe_to_submit` from readiness (3, 5) · one resolver + ratchet (1) · no page for v2v/audio/unknown, refused with a reason (1, 4) · C++ tests (1-4) · live proof (6).

**Ordering:** Task 1 first because Tasks 3 and 4 both depend on the resolver, and doing it first means the divergent copies are gone before anything new calls them.

**What this wave does not do:** drop-and-run without landing on a page (the owner asked for auto-population, and a graph that runs without the user seeing what it will do is the opposite); node-pack installation beyond the existing dialog; and the Models-page side of a model that a dropped workflow needs, which is W5's.
