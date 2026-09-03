# 53 — Consistency and robustness audit

**Status:** measured 2026-08-29 to 2026-08-30 against the whole repository. 28 commits. The tree at
the end of the pass: **91 Python modules** (92 at the start; Phase 4a deleted four unreachable ones
and this pass added three), 190 C++ sources and headers, **155 Python test files**, 6 ctest targets.

Every number below is followed by the measurement that produced it. The ones that turned out wrong
are recorded as wrong rather than removed — §5 is that list, and it includes both rules written in
this pass reporting a clean tree while silently broken.

The owner's assessment opened this pass:

> *the current setup seems fragile and brittle mostly hoping that everything goes right and doesnt
> make sure that they do. Optimizations arent consistent because the implementation is lacking
> consistentcy.*

A full-repo survey confirms it and, more usefully, finds the reason.

---

## 1. The finding: the defects are second copies

Eleven of the top twenty fragility findings were **second copies of a rule already applied correctly
once** — in six cases in the same file as the correct copy.

| the rule | applied correctly at | not applied at |
|---|---|---|
| `os.walk(onerror=)` so unreadable ≠ empty | `model_dependency_resolver.py:185` | `model_resolution_commands.py:115` |
| check `HasExited` before waiting out a timeout | `start_backend.ps1:170` | `comfy_runtime_manager.py:289` |
| handshake before adopting a listening port | `start_comfy.ps1:161` | `start_backend.ps1:128` |
| `0.0 <= strength <= 1.0` — zero is a legal denoise | flux, `native_image_graphs.py:112` | 6 builders, **same file** |
| `resolve_seed` — zero is a legal seed | 13 sites | `clothes_only.py:382`, `look_completion.py:1439` |
| `_sampling_for` — the dropdown must not be inert | 7 image builders | 8 video routes, 3 hardcoded |
| the memory profile places the text encoder | krea2 t2i | krea2 inpaint, look, clothes |
| one project-root tree walk | — | **5 copies**, disagreeing on depth |

This is Doc 50 rule 5 — *nothing else in the tree decides the same question differently* — failing at
the level of process rather than code. Each of those rules had been enforced at the site where its
defect was found and nowhere else.

**The ratchets meant to prevent exactly this had the same shape as the bug.**

| ratchet | the scope it actually had | what it could not see |
|---|---|---|
| `test_seed_is_one_rule.py` | 3 files named in `BUILDER_FILES` | 5 violations tree-wide |
| `test_comfy_endpoint.py` | `(ROOT/"python").glob("*.py")` | **82 of 92 modules** — `runtime_adapters/` and `video_adapters/` invisible to *every* sweep in the repo |
| `numeric_option` | a correct helper, no sweep | **87 sites** of the defect it prevents, 48 in one file |
| `test_worker_client_message_types.py` | the registry's self-consistency | **9** emitted types, unregistered |

So the governing rule of the pass, now **Doc 50 rule 10**: *a rule is applied to the tree, not to the
site.* A fix without a tree-wide ratchet was out of scope.

---

## 2. What was measured before anything was fixed

Doc 50 rule 1 says a heuristic ships with a number. These are the numbers the pass started from.

| | |
|---|---|
| Code | 39k lines Python (92 modules) · 63k lines C++ (186 files) |
| Tests | 136 files, 1088 passing — **19 of 82 Python modules never referenced**; 63k lines of C++ had **one** test executable, and `CMakeLists.txt` had no `enable_testing()` or `add_test()`, so it had never run |
| CI | **none** — no Actions, no hooks |
| Determinism | **26%** of test files needed the live worker, ComfyUI, or the internet. The run that measured this failed two tests purely because ComfyUI was down |
| Error handling | 433 `except` clauses, 310 bare `except Exception`, **106 swallow to nothing** |
| Divergence | 8 ComfyUI-root resolvers / 4 env names / 28 hardcoded absolute paths · 5 family key namespaces · 8 command-identity readers · 8 sampler mechanisms |
| Optimization reach | tiled VAE **0 of 11** image emitters · profile-aware encoder placement **1 of 11** · sage attention **2 of 20** · TeaCache 215 lines, **0 reachable** |
| Duplication | **21%** of `native_image_graphs.py` is 30 repeated statements. The krea2 graph existed in **5 places**; **1** routed the text encoder through the memory profile |
| Complexity | `worker_tcp.py::handle` 563 lines / **127 branches** · `MainWindow.cpp` 6961 / 98 methods · 43 functions over 100 lines |

The optimization complaint in one line: **the same model fitted as krea2 t2i and OOM'd as krea2
inpaint**, because only the t2i copy passed a `device` to its CLIPLoader.

---

## 3. The failures reported success

The pattern that made all of this survivable-looking. Almost none of these announced themselves.

**A job that failed before `STARTING` re-ran and re-failed on every launch, forever.**
`VALID_TRANSITIONS[QUEUED]` allowed only `{STARTING, CANCELLED}`, and `fail_job` discarded
`transition_job`'s return value. The item reverted to `QUEUED`, was persisted, was popped from
`pending` so it never drained — and manifest recovery rebuilds `pending` from `state == QUEUED`.
14 raise sites reached this; one sits eight lines below the comment describing the hazard.

**Cancelling did not cancel.** There was no `/interrupt` and no queue-delete anywhere in the
repository. Cancelling stopped SpellVision polling while ComfyUI rendered to completion holding
20+ GB.

**An auth refusal arrived as `{"ok": true}`.** `auth_error` was unregistered, so it was wrapped in a
`client_warning` envelope whose own `ok` was true, and `WorkerResponseParser.cpp` had no case for
that envelope either — discarded twice. The single highest-leverage line in the pass was flipping
`client_warning`'s own `ok` to `False`: an unknown type is now a failure, which converts every
*future* unregistered type from silent to loud.

**Four families shipped an alphabetical default.** `sdxl`, `pony`, `illustrious` and
`stable_diffusion` advertised `ddim` + `karras` because `family_sampling_choices` fell through to
`sorted(samplers)[0]` when no default was declared — **the default on 112 checkpoints**. An
allowlist without a declared default now raises at import.

**A control that is shown exactly where it is ignored.** VAE Tiling appeared only in the WAN
dual-noise route, which never reads `enable_vae_tiling`; the one builder that honours it is the
wrapper route, where the checkbox was hidden. Looking for the *rule* rather than the instance found
the same defect with the sign flipped: the cockpit sends six WAN split keys and the dual-noise
builder read none of them, so three more controls were inert. One edit would have fixed a checkbox.

**Native renders reported `cuda_allocated_gb: 0.0`.** On a native route the weights are in ComfyUI's
process, so torch in the worker sees nothing; on the FLUX.3 route the render happens on Black Forest
Labs' hardware and there is no local GPU at all. All three wrote the same zero into a field every
other route fills with a real measurement, and history rows and the bottom bar read it.

---

## 4. What the fixes could not have found without the sweeps

Four results that only exist because the rule was applied to the tree.

**Dead code satisfies ratchets.** `request-keys-have-readers` reported `python_exe` as *having* a
reader: `runtime_adapters/diffusers_adapter.py` did `request.get("python_exe")`. That package was
unreachable — nothing imported it — so a live rule was reporting a pass on the strength of code that
could never run. Deleting the package is what revealed the key had no live reader at all.

**An omission has no syntax.** Phase 4c routed nine text-encoder sites through one resolver and drove
that sweep to zero. Four krea2 loaders passed *no* device at all, and the rule — which matched a
device value written by hand — could not see them. The OOM-vs-fits bug survived the phase that was
fixing it. Widening the rule to match the *class* and check what it declares found two more the
moment it ran: sd3's `TripleCLIPLoader` (the family with three encoders and the most to gain) and the
qwen edit graph.

**Zero can mean the shape is wrong.** `zero-is-sayable` was written for the denoise defect, went to
zero, and stayed there for two phases while **eight copies survived in a shape it did not match** —
guards (`if not (0.0 < denoise <= 1.0): denoise = 0.6`) rather than the `or`-default it checked for.
A stated `0.0` silently became `0.6`, and an absent value was indistinguishable from a stated zero,
because both took the same branch. And the resolver could not have fixed them anyway: `strength` is
what the cockpit actually sends for i2i and it was **missing from the alias table**.

**Five copies, and grep could only find four.** The project-root walk was written by hand five times.
The fifth is called `spellVisionRepoRootForWorkerClient` and shares no substring with the other four,
so no name-keyed search could reach it. The sweep found it by what it does. MainWindow's copy
searched depth **7** where the other four searched **8** — a build eight levels below the root would
have had four components find the project and MainWindow fall back to the working directory, with no
error, because the fallback is a valid path. Not reachable in the default layout, where the
executable sits three levels down. **The reason it had never fired was a property of the build
directory, not of the code.**

---

## 5. What this audit is *not*

**It is not a claim that the counts are precise.** Two rules are recorded here as over-reporting,
because a rule's precision is part of its design.

*The wire-type rule reports 30 where 10 are real.* Naive — every `{"type": "..."}` literal — flags 30
across 68 literals, and most are false: `"type": "krea2"` is a `CLIPLoader` input, `"type":
"teacache"` an acceleration descriptor. Scoped to dicts that reach `emit()`, it returns exactly the
10 real ones. Both numbers are here because the first is the honest starting measurement.

*The project-root rule reported 3 where 1 was real.* Its first working version asked whether a file
mentioned the sentinel anywhere and climbed anywhere. MainWindow also climbs looking for
`qt_ui/icons` during a Debug run, and `WorkflowLibraryPage` climbs three levels to derive the Comfy
root from its workflows directory. Neither is a project-root search; both merely share a file with
one. Scoping to proximity rather than co-residence took it to 1.

**A rule that flags two false positives per true one gets bypassed, and then it protects nothing.**
That is why both numbers are recorded rather than quietly fixed.

**It is not a claim that the rules work because they are green.** Both rules written in this pass
were silently broken on their first run, and both looked exactly like success:

- The dispatch-shape guard — written to refuse any shape the command extractor cannot read — missed
  `command.startswith("legacy_")`, one of the four shapes it claims to catch. The silent
  under-report it exists to prevent, inside the thing preventing it.
- The project-root rule had a mangled escape that left a literal backspace in its compiled pattern,
  so it matched nothing and reported a clean tree. Fed the exact code it was written for, it stayed
  silent.

Both were found by feeding each rule every shape it claims to catch, and by asserting it stays quiet
on the shapes actually in use. Those probes are now parametrised tests. **A guard nobody has watched
fail is a guess about what it does.**

**It is not a claim that every planned item was needed.** The plan's Phase 4b premise — that the
measured 6.3× accel-LoRA speedup was never applied — was simply **wrong**. It is applied. Reported as
wrong rather than turned into work; and checking it found the real defect next door: the accel LoRAs
were paired to the t2v variant regardless of command, so **i2v runs loaded t2v LoRAs**.

**It is not a full decomposition of the god files.** `worker_tcp.handle` is still 569 lines and
`MainWindow.cpp` is still 6641. Section 8 explains why, and what was done instead.

**It was not CI** — at the time this was written. There was a pre-commit hook running the fast
subset in ~13 seconds, and every other guarantee waited on a human running `pytest` and `ctest`.
**Closed 2026-08-31** by `.github/workflows/ci.yml`: the hermetic Python lane on Windows and Linux,
plus a Windows job that configures, builds and runs `ctest`. Kept here as written, with the closure
noted, because the sentence is the measurement — see §7g for why leaving it in the present tense for
two days was the same defect as everything else in this document.

---

## 6. The C++ side, which had no ratchets at all

Doc 50's ratchet table named this as its own gap: *"every ratchet here is Python."*

`CMakeLists.txt` had no `enable_testing()`, no `add_test()`, and never requested `Qt6::Test`. One
test executable existed, was built on every configure, and **had never been executed** — 115 lines of
test that were compiled and discarded. Extracting `SpellVisionCore` as a library made the UI's
decision logic linkable, which is the prerequisite for everything else.

There are now 6 ctest targets and 4 sweep rules over `qt_ui/**`.

**And then the C++ suite could not say why it failed.** Breaking an assertion on purpose turned ctest
red correctly and printed `<end of output>`. The binaries are console subsystem — `dumpbin` confirms
CUI, so the existing comment in `CMakeLists.txt` names the right cause and is wrong that setting
`WIN32_EXECUTABLE FALSE` was sufficient — and still wrote **zero bytes to stdout and stderr**. Qt
routes its logging to the debugger when it cannot see an attached console, and ctest runs every test
through a pipe. All five Qt tests had been in this state since they were written.
`QT_ASSUME_STDERR_HAS_CONSOLE` in the ctest environment fixes it: the same broken assertion now names
the case, the actual, the expected and the file and line.

**A test suite that cannot say why it failed is Doc 50 rule 4 failing about itself.** The only way to
find it was to make one fail on purpose.

---

## 7. Where the ratchets live

The sweep harness is one module, `tests/sweeps/`, and the shape is the point:

- `sources.py` — the **only** source list. All 92 Python modules via `rglob` (the flat glob is
  exactly what hid two packages from every sweep), plus `qt_ui/**`, the tests, and the PowerShell
  launchers. Dead trees are excluded **explicitly**, so the exclusion is a visible decision.
- `rules.py` — each rule as `(name, citation, select, check) -> [Violation]`. **No rule may name a
  file**, enforced by a test. A rule without a citation over 80 characters fails.
- `exemptions.py` — keyed by site, valued by a **reason**, never a boolean. A test pins the count in
  **both directions**, so adding one forces a reviewer to read the reason and a count going *down*
  fails too.

That third state is the whole argument. `clothes_only.py:382` was not compliant, not violating, and
not a documented exception — it was merely *out of scope*, which is how a defect hides in plain
sight.

**19 rules. Baseline total 74, with 15 of the 19 at zero.** The four that are not:

| rule | open | why it is not zero |
|---|---|---|
| `no-machine-paths` | 11 | each one exempted with a reason — mostly documentation of the ComfyUI cutover, where naming the path *is* the content |
| `request-keys-have-readers` | 55 | a genuine backlog of keys the UI sends that nothing reads. Recorded rather than half-fixed: each needs a decision about whether the control should exist |
| `object-info-through-one-transport` | 1 | the rule's own test file, which holds the broken shape as a fixture so the rule can be watched firing on it |
| `local-output-only-for-a-local-endpoint` | 7 | all Qt. `COMFY_API_URL` appears **zero** times under `qt_ui/`, so C++ has no locality predicate to call — see below |

| rule | holds |
|---|---|
| `seed-one-rule` | no seed assignment outside `resolve_seed` / `stated_seed` |
| `zero-is-sayable` | no field that permits zero can have it replaced by a default — reading which fields those are from `FIELD_BOUNDS`, the table the resolver itself uses |
| `no-machine-paths` | no machine-specific absolute path, in either language |
| `terminalisers-check-their-hop` | no discarded `transition_job` return |
| `wire-types-registered` | every emitted wire `type` is registered on both sides |
| `cancellable-comfy-submission` | a route that registers an active job registers a cancel hook |
| `samplers-through-one-resolver` | samplers go through `_sampling_for` |
| `request-keys-have-readers` | every key the Qt builder inserts has a Python reader |
| `one-comfy-root-resolver` | one install-root resolver per side; never the rollback build |
| `every-module-is-reachable` | no module nothing imports, resolving relative imports |
| `text-encoder-placement-through-one-resolver` | the memory profile reaches every text encoder — including the ones that named no device |
| `latent-decode-through-one-resolver` | tiled decode is a property of the shared builder, not a per-family call |
| `vram-numbers-name-their-source` | a GPU number says which process it measured; "not measured" is `None`, never `0.0` |
| `one-project-root-resolver` | five copies of one tree walk stay one |
| `object-info-through-one-transport` | `/object_info` is fetched through the one reader that survives a 6.76 MB body |
| `local-output-only-for-a-local-endpoint` | a render produced on another machine is never located on this machine's disk |
| `comfy-output-path-through-one-resolver` | a downloaded output's local name and extension come from one resolver, and only media is handed to the OS shell |
| `late-bound-names-resolve` | a name reached through the `ws.` / `_ws()` shim exists on the module it late-binds to — the split-drift class that killed both LTX routes twice |
| `combo-options-through-one-reader` | a combo's choices come from the one reader that absorbs both `/object_info` shapes — seven readers existed, one was correct, and the module docstring named a wrong one |

The C++ column, which Doc 50's table named as empty, is in §7 of that document.

### 7a. The rule found by moving the product, not by reading it

Every other rule here came from reading the tree. This one came from pointing SpellVision at a
ComfyUI on a **second machine** (an Arch node with a 3090 Ti, same core 0.34.0) and watching which
halves moved with it.

Everything that asks the **endpoint** worked with no changes: the resolver's precedence chain, a
904-class `/object_info` fetch over the wire, the native image builder, and a 1.28 MB render pulled
back through `/view`. Six of six, first run.

Everything that asks the **disk** was wrong. `comfy_output_root()` resolves *this* machine's install
whatever the endpoint is — and the hazard is not that the directory comes back empty. It comes back
**full**, of the previous local session's renders, so a gallery scanning it after a remote render
shows an old image as though it were the new one, and nothing errors. `is_local_endpoint`'s own
docstring already listed *"reading an output from disk"* among the things that must check it. None of
the ten readers did.

Two rule-writing lessons, both paid for on this single ratchet:

- Unscoped it reported **13 where 10 were real** — a header declaration and two definitions. The
  same over-count shape as R7's 30-vs-10, and recorded for the same reason.
- The first scoping fix then **ate a real violation**: `return chooseComfyOutputPath();` matched the
  definition filter, because `return` sat where a return type would. Tightening a rule manufactures a
  false negative as readily as looseness manufactures a false positive — and the false negative is
  the one nobody notices, because a rule reporting less always looks like progress.

The meta-test also caught the rule selecting its sources by file *extension*, which is the same
prohibition as naming a file. The harness refusing its own author is the strongest evidence in this
document that §1's pattern is being enforced rather than described.

---

## 7b. The security pass, and what it added to the pattern

A read-only audit of the network-facing and untrusted-file surfaces (2026-09-01) found three
HIGH, three MEDIUM and a handful of LOW findings, and every one of them had the audit's shape:
a rule stated once and applied at the site that produced it.

| finding | the rule that existed | where it was not applied |
|---|---|---|
| integration tier reaches arbitrary local read/write | `INTEGRATION_COMMANDS` bounds the *command* | the *fields* those commands honour — `comfy_api_url`, `input_image`, `output` — and the queued `task_command` under `enqueue` |
| loopback trusts every local account | `assert_bind_is_safe` holds the *bind address* closed | the peer address on a shared machine, which every account shares |
| remote chooses the output extension; UI ShellExecutes it | `_safe_download_filename` sanitises *model* downloads | the *render* download, three copies, all taking `.suffix` from the history entry |
| `auth_token` persisted in the clear | `redact_secrets` on the *queue manifest* | `archive_job`, three lines away, feeding `retry` |
| git fallback steerable by URL | the archive installer is *https-only with a host allowlist* | the fallback taken exactly when that installer refuses the URL |
| "pinned" reported for a branch | Doc 28 §3 says *pinned commits* | `download_repo_archive` returned True when the *requested ref existed* |

Each landed as a property, in the order the audit suggested: request-schema allowlist for the
integration tier with a tree-wide test over every path-like request key (which found four the
audit had not); a per-launch session secret published to a user-only file, with the shipped worker
driven over a raw socket to prove it refuses; one output-path resolver with a suffix allowlist and
a magic-byte check, plus R19 to stop a fourth copy; and the git fallback fenced behind `https://`
and `--`, with consent now asked *after* the plan is fetched and *with each repository in view*.

Two of the tree-wide tests did more than pin the fix. The request-schema ratchet, run once, named
`inpaint_mask`, `models_root`, `workflow_profile_path` and `compiled_prompt_path` — none in the
audit, all real. And the session-secret change touched every client at once because the test
fixture *is* a client: 1670 tests presented the secret correctly on the first run, which is a
stronger statement about the rollout than any review.

What it did not do, recorded rather than implied: the remote endpoint is still plaintext HTTP with
no authentication option; HF downloads still have no digest check; `materialize_request_assets`
is dead code that would attach stored credentials to requests if ever wired, and should be
deleted rather than left to be reconnected.

---

## 7c. The UI pass: zero dead controls, six located defects, and a rule that found more

A per-page audit (2026-09-01) of all fifteen rail surfaces found **no dead or inert control on
any page** — 36 cockpit buttons cross-checked against their `connect()` calls — and six defects,
each located to a line:

| defect | where | the property that keeps it fixed |
|---|---|---|
| nine-button non-wrapping action row | Workflows detail pane | two rows; page added to the responsive matrix |
| no scroll region at all | Runtime page | one `QScrollArea`; page added to the matrix |
| a batch-testing tool visible in Simple mode | cockpit Output card | gated on the one `devToolsVisible()` predicate the hidden modes already use |
| canvas floats the picture in a much wider box | cockpit preview | `AspectCap`: the stack's maximum hugs the fitted content; released on parent resize; one helper for image and video |
| no version, About, or update check anywhere | Settings, system menu | `project(VERSION)` is the single spelling; About in the menu; a check that only reports |
| raw worker stderr as dialog body | four Workflows sites | `showWorkerFailure`: summary in the body, stderr behind Show Details |

The last row is the one to notice. The audit found four sites. The tree-wide rule written for
them — *no static `QMessageBox` takes `stderrText` in its arguments* — found **three more** on its
first run, two in MainWindow's import path and one in Workflows' model resolution. A page-private
helper would have fixed four and left three; the helper became a free function in `shell/` instead.
Same shape as the request-schema ratchet finding four keys the security audit missed.

Two of this pass's ratchets were wrong on their first run, in the direction that matters: one
matched the word "download" inside a comment explaining that nothing is downloaded; one matched a
stale phrase inside the comment explaining why it was removed. Both now read code, not comments.

The four feature small-fixes that followed were all the same shape as each other and as §1: **two
ends that already existed with no middle.** The download captured trigger words and the import
dropped them (`model_import` now writes the sidecar `ModelSidecar.cpp` already parses). The
streamed download lane existed and only the Flows page could reach it (Models now emits into the
same `startModelDownload`). The render's sidecar held the whole recipe and Inspire forwarded only
the prompt (`recipeDraft()` maps sidecar keys to the names `applyWorkflowDraft` reads — and a test
asserts every key is written by one end and read by the other, because a key one side writes and
the other never reads is how all four gaps opened). The comic caption reached the manifest and
never the page. Delete was the one genuinely new thing, so it fails closed: contained under the
models root, refuses links and directories, refuses with no root configured, and the sweep for
unregistered wire types caught its result type before the first commit.

---

## 7d. The first live render, and what only a screen shows (2026-09-02)

The owner asked for the canvas change to be judged by eye, not by its tests: *"actually looks good
and doesn't just code well."* The pass drove the built exe through Windows UI Automation
(`scripts/dev/uia/`), rendered through each generation page, and screenshotted every rail page at
the four window states. It found more than the previous two passes combined, and every finding was
a case where a rig or a ratchet had said PASS.

| what the screen showed | what had said it was fine | the rule that now says otherwise |
|---|---|---|
| Every Comfy-native image family failed at the output step: `module 'worker_service' has no attribute 'resolve_comfy_output_path'` | py_compile, `import`, 1735 tests — every test of that runner mocks the `_ws()` shim | `late-bound-names-resolve`: each late-bound name is checked against what worker_service actually binds. One violation tree-wide, the one that shipped |
| That error, shown to the user as if they had done it | the error event carried whatever the exception said | `internal_error`: programming-error types are labelled as SpellVision's, with the text kept for the report |
| The error pill read `module 'worker_service' has no attribute 'res` and nothing else | a 280px cap on a QLabel; no test looked at the pill | `ErrorPillLabel` elides to the row and keeps the full text one hover or click away; tested at 1280 and 1920 |
| A finished 1080×1920 render displayed as a 48×86 stamp at every window size | `test_canvas_aspect`: converges, no oscillation, grows with the parent — with a label that started at full size | the fit is measured on a `PreviewArea` the cap cannot shrink; the cold-label case is in the test |
| "Queue: 1" after the job completed | two writers of one label, one of them the tray's terminal-only row count | one `tallyQueue`; the drawer's "N running • N pending" reads it too, on every queue change |
| LoRA card buttons clipped to "hang" / "low" / "mo" under 1600px | the matrix skips scroll-area children by design | the row is tested at the 215px it gets; arrows are glyphs on the name row |
| I2I after "Prep for I2I" and a fresh T2V: Generate dead behind "Choose a canvas size" | the readiness rule was correct; nothing had ever set a size | `ensureCanvasSizeDefault`: input image size for i2i/i2v, family default otherwise, never over an explicit value |
| Wan T2V's ETA hit "6s" at 99 s of a 305 s render and climbed for three minutes | the poller sent a 1..95 tick as `step/100`; the UI extrapolated | the wait is a heartbeat (`total == 0`); the UI shows elapsed and a busy indicator; diffusers' ETA anchors to the first observed step, not to job start |
| Comic Studio's left column clipped at 1776 and at half width | Comic cells PASS in the matrix | a viewport-overflow clause; Comic was its only hit |
| Runtime page: "Comfy root: C:/sv_comfynext/ComfyUI" beside "ComfyUI 0.34.0" | the superseded-root redirect existed and was applied to settings and env, not to the cached worker payload | the payload path goes through the same `resolvePreferredComfyRoot` |
| The title-bar breadcrumb reading "nage" for "Text to Image" | the label's own geometry was correct | lazily built pages sat visible at the window origin before joining the page stack — see the commit that homes them |

Two lessons for the method. First, **a rig passes for the shape it was built in**: the canvas test
began with a laid-out label, the matrix skipped the one container that clips, and the runner's tests
mocked the shim that was broken. A screenshot of the product is the only test that starts from the
product's own state. Second, **a tool bug costs the same as a product bug**: an hour went into a
window that "grew to 1460px on its own" before it turned out to be the driving script — PowerShell
variable names are case-insensitive and a local `$h` had overwritten the `$H` height parameter with
the window handle. The lesson is written into the helper, and the helper is now in the repo.

Left open from this pass: the video preview at half-height loses most of its budget to a four-line
caption; the Dataset page keeps its "Choose a canvas size" gate by the first-run-honesty rule, which
this pass respected rather than overrode; the LoRA name clips without an ellipsis at half width.
**The first and third of those are closed in §7e; the Dataset gate stands by the rule.**

---

## 7e. Two defects that were one property, and a chip that was never asked (2026-09-02)

The video caption and the LoRA name were logged as separate cosmetic items. They are one defect:
**a label showing a value whose length the UI does not control must elide, and must not demand that
value's width from the layout.** The caption was a four-line block — the last line the full absolute
path — spending ~64px of a ~330px canvas budget at half height. The LoRA name was cut mid-glyph in a
215px card, because `setWordWrap(true)` is not elision and, for `Realistic_Anime_Illustrious_v2`, is
not even wrapping: **U+005F is not a UAX-14 break opportunity**, so wrap had nothing to break. Both
now use `widgets/ElidingLabel`, and the caption is bound *by type* so a later edit cannot hand it a
wrapping QLabel.

Two facts only the rig could establish, and both changed the fix:

- **A minimum-width threshold is not the property.** The first test asserted the label's
  `minimumSizeHint()` was under 96px; it came back 97 while the widget was behaving correctly,
  because a layout asks `qSmartMinSize` and ignores that hint for a horizontally-Ignored policy. The
  assertion is now made *through a layout* and states that the minimum does not grow with the text.
- **The old row test could not have caught this.** Every fixture LoRA name in it contained a hyphen
  (class HY), which *is* a break opportunity. The fixture now includes a name with none.

Three further findings came only from the screen, after a real 317s render:

- **Yielding is only a virtue when what yields can afford it.** The reorder arrows had been moved
  onto the name row on the reasoning that the name label yields width. It does — measured live at
  the 1180px minimum window it yielded to **48px**, showing `3D_…yle`. The arrows moved to the
  weight row, beside a spinner that can give up 64px without losing a digit; the name went to 128px.
- **A cap on the picture was capping the controls.** Making `fitBudget`'s chrome guard dimensional
  (chrome cannot equal or exceed the budget it is measured in — it had been a flat `> 160`, which a
  four-line caption plus a transport bar crossed, silently dropping real chrome) made the cap tight
  enough to bind, and the transport bar was squeezed into the clip's 301px: buttons as slivers, the
  time reading `:05 / 00:`. `applyAspectCap` now expands to the capped widget's own
  `minimumSizeHint()`. **A fix that lands correctly can expose the next defect rather than cause
  it** — but only a screen said which.
- **Hiding one chip and not its neighbour.** The Model chip is hidden on pages with no model slot;
  the LoRA chip beside it was left to the width reflow, which runs only on resize — so
  "LoRA: not selected" sat on Flows, History and Settings until the window changed size.

The bottom-bar "Model:" defect was **not** the two-writer shape it was filed as. `bottomModelLabel_`
has one writer and already read the current page; that writer was simply never *called* on a page
change, because `syncBottomTelemetry` hung off submits and `afterQueueSnapshotApplied`, which fires
only when the queue changed. **This is the third instance of that trap in `MainWindow.cpp`, and the
first two are documented in comments a few lines apart** (the detection re-scan and the download
poll, both moved to `queuePollSucceeded`). The page NAME did have three writers — `modeId.toUpper()`,
`pageContextForMode()`, and a `setBottomPageContext` setter that turned out to be dead code — which
is why it read "T2I" or "Text to Image" depending on when the queue last moved.

And the ratchet for the elision rule went through the same precision loop this document keeps
recording. A heuristic to separate widget elision from painted elision was tried twice — the nearest
column-0 function definition (which names a file-scope helper for a delegate's indented `paint()`)
and "a QPainter within 1500 characters" (which misses both painters, whose QPainter is a parameter
50 lines up). Two known sites do not need a classifier: they are exemptions keyed by site and valued
by a **reason**, per §7's convention. The bottom-bar rule also flagged its own explanatory comment on
first run — the same trap already recorded here for the update check — so it strips line comments
before it looks.

---

## 7f. Finishing the tail: what a diagnostic bought, and one thing measurement could not settle (2026-09-02)

**The two responsive-matrix cells were fixed by improving the REPORT, not the layout.** Both had sat
in `kKnownFailures` since the matrix first ran, described accurately and understood by nobody:
`QWidget(-) 120x32 < min 364x32` names a squeezed row and says nothing about which container lost the
width. The clip report now prints the parent chain with each step's width against its minimum, and
the first line of the first run answered it: `CanvasEmptyState 1390w/min364`. The parent had the
room; the row was not being given it, because `addWidget(row, 0, Qt::AlignHCenter)` gives an item its
size *hint*. The second cell was the LoRA button row again — four full-word buttons in a column that
`reflowForWidth` deliberately shrinks — and took the same 2×2 grid. **The baseline is now empty**, and
it stays in the test, two-way, so a new failure fails the suite and a fixed cell must be deleted
rather than left standing.

**The drawer's square corners were a palette fill, not a missing radius.** The activity drawer was
made opaque with `autoFillBackground` + an opaque `QPalette::Window`, chosen years-equivalent ago
because a plain QWidget does not paint a stylesheet background. That fill paints the whole rectangle,
so no `border-radius` could ever have survived it. The fill moved to an inner `QueueOverlaySurface`
QFrame, and the corners it rounds away now show the page behind them.

**And one thing this pass could not settle honestly.** The obvious home for that frame's style was
the shell stylesheet, beside the drawer's existing rules. A byte-identical
`#QueueOverlaySurface { background: #FF0000; }` **painted when placed at the front of the sheet and
did nothing at the position where those rules live.** Three theories were tested and all three were
wrong: `border-bottom: none` (removed, still inert), brace imbalance (counted, balanced), and
"everything after some point is dead" (a bisect that inserted probes *inside* other rules' brace
blocks, so it proved nothing — recorded here because a flawed measurement that looks decisive is
worse than none). The surface is styled locally from tokens instead, which is the house pattern for
exactly this situation and is re-applied on `themeChanged`. **The sheet question is open**, and it
matters beyond one drawer: if rules late in a 62-argument, 12KB stylesheet are silently inert, other
rules are too. It needs a proper investigation, not a cosmetic fix's time budget.

**Two process notes from the same hours.** Three stacked `SpellVision.exe` instances made two
measurements lie before anyone noticed — UIA attaches to the first window it finds, so screenshots
came from a build two changes old. Every launch now kills what is running first. And the pixel probe
that finally settled things was worth more than any screenshot: `CopyFromScreen` at one coordinate,
compared against an expected colour, answers "did this rule apply" in a second.

**Character Studio's copy: 36 phrases, one file, and the counterweight that made the number
trustworthy.** The page narrated its own build status in SpellBound's vocabulary — "Cook still
Degraded", `dummy=none`/`dummy=whbs` (CLI flags verbatim), "Not a 14517 cook", "hair.wear.scalp is
empty", "Path B", "Jarvis pack". The rule that finds them scans only string literals containing a
space, which is what keeps it off object names, JSON keys (`adjunct_gen3d` is correct on the wire)
and command ids. Measured before shipping: **36 hits, all real, all in `CharacterStudioPage.cpp`, and
0 in `ComicStudioPage.cpp` and `ConceptReferencePage.cpp`** — the two pages a read said were clean.
That zero is the number that makes the 36 believable.

Every "this is not finished" statement survived the rewrite, in words a user can act on: *the garment
itself is not built here* rather than *cook still Degraded*. An existing ratchet,
`test_character_studio_honesty.py`, failed on the change because it pinned one **phrasing** of the
limit rather than the limit itself; it now asserts the property. A rule that breaks when the thing it
guards is improved is measuring the wrong thing.

**"Owner A/R" was on screen and not in the tree, and both were true.** It lives in
`runtime/characters/character_01/project.json` — a stage note in the developer's own local project,
which is gitignored and never shipped. The copy rule covers code; a user's own note is their words. A
fresh install shows none of it.

---

## 7g. The last unswept surface was this document (2026-09-02)

Nineteen sweep rules and a shelf of ratchets now hold the tree. Nothing held the documents that describe the tree — and they had
drifted in exactly the way the code had, for exactly the reason section 1 gives.

**`ARCHITECTURE.md` routed readers to four modules this audit deleted.** Its Python table still
listed `python/video/t2v_worker.py` and `i2v_worker.py` (the directory is gone), `gpu_info.py` and
`workflow_profile_registry.py` (both deleted in Phase 4a, and this document records deleting them).
It named `runtime/comfy/ComfyUI/` as where ComfyUI lives — the path `runtime_paths.py` carries as
unused drift, not the live root — and called LTX "experimental" while LTX has been the default,
production, render-proven video route since Doc 25. Its "Known issues" opened with a ping
state-machine bug whose test no longer exists, and its Tests table listed three files out of 173.

A reader following that map would have looked for the video workers, not found them, and had no way
to tell whether they had been moved or had never been where the map said.

**Two more claims were false in the same way.** `CLAUDE.md` §3 and §9 item 5 asked for a Rust-
prerequisite purge that had already happened — both files it named were already correct, so the
instruction outlived its own completion. And §8 said seven historically cited documents "are not in
tree": all seven exist, six of them one directory down in `docs/`. They were cited by bare name,
looked for at the root, and written off.

**The measurement, and the over-count that came with it.** A naive rule — every backticked string
that looks path-shaped — reported **28 stale references across 218**. Most were false: globs
(`scripts/dev/*.ps1`), QSettings keys (`appearance/themePreset`), bare extensions (`.cpp`), a git
ref (`origin/main`), a sampler pair (`dpmpp_2m/karras`). Scoped to a **file** the document names — a
token ending in a source extension, no glob characters — it reported **8 across 161**, of which
**4 were real**; the other four are deliberate mentions of things that correctly do not exist (a
recorded deletion, a generated `CMakeCache.txt`, a runtime-written `prompt.txt`) and are exempt with
that reason. That is the third time in this audit the naive form of a rule reported roughly three
times the truth. It is worth stating as a habit rather than a coincidence: **the first form of a
rule is a draft, and the measurement is what turns it into a rule.**

**What shipped:** `tests/test_governing_docs.py`, marked `ratchet`, holding the five present-tense
documents to the tree. Its exemptions are keyed by `(document, token)` and valued by a reason, and a
second test fails if an exemption outlives the sentence it was granted for — an exemption list
nobody prunes becomes a list of rules that quietly no longer apply.

`ARCHITECTURE.md` was then rewritten as the **operations map**: the three processes and the two
decoupled venvs, the Generate path end to end through all eight seams, true module tables for both
languages, a section on how the guarantees actually run (lanes, ratchets, sweeps, hook, CI, ctest),
how to add a command / a family / a rule / a C++ test, and what is deliberately unfinished with the
reason. That last section matters as much as the first: a map that shows only the finished parts is
how a known limit gets rediscovered as a bug.

**And the CI line in this document was stale in the other direction.** Section 5 said "It is not CI"
and section 9 listed "No CI" as an open item, two days after `.github/workflows/ci.yml` landed. The
audit that exists because claims outlive their truth had two of its own. Both are now marked closed
rather than deleted, because the sentence is the measurement.

---

## 7h. One question, seven readers, and a feature that had never run (2026-09-02)

`/object_info` publishes a combo **two ways in the same payload**, and the live core ships both:
**1738** in the legacy `[[choices], {…}]` shape and **562** in the V3
`["COMBO", {"options": […]}]` one. Which shape a class uses is a property of *that class*, so the
migration is per-class and still running. `CheckpointLoaderSimple`, `UNETLoader`, `KSampler`,
`LoraLoader`, `VAELoader` and `CLIPLoader` are still legacy. **`UpscaleModelLoader.model_name` has
already moved.**

A legacy-only reader returns `[]` on a migrated class, and **every caller in this tree reads `[]` as
"no constraint" rather than as "I could not read it."** So `upscale_engine._combo_choices` returned
`[]`, `resolve_upscale_model_name` returned `""`, and `graft_pixel_upscale` returned the graph
untouched. The pixel upscale route did nothing at all, on every family that reaches it, and reported
success. Doc 27 §2.1 had it filed as *not built*; it was built, wired, tested, and inert.

**Seven readers of that one question, one correct — and the module docstring named a wrong one.**
`_comfy_input_choices` (16 call sites, legacy only) sat one letter from `_sv_comfy_input_choices`
(4 call sites, both shapes) **in the same file**, and the docstring told readers to use the first.
Five further hand-rolled copies: the sampler intersection, the krea2 UNET name, both checkpoint-name
resolvers, and the video adapter base. Four of those read classes that are *still* legacy — correct
that day, silent failure on the day those move. That is the audit's thesis with a clock attached:
a second copy is not merely redundant, it is a scheduled outage.

The rule is `combo-options-through-one-reader`, an **AST taint** check rather than a pattern match,
because the six copies spelled the same read six different ways — including one that fetched the
bucket with a **loop variable** over `("required", "optional")`, which no literal-key analysis can
see. It fires on all six historical forms and is silent on the three modules that legitimately read
input *names*.

**The upscaler's other four defects were the same species.** `Model` on a diffusers checkpoint
resampled with lanczos and reported success (`basicsr` and `realesrgan` are in neither venv — that
was every SDXL run); krea2 and sd3 could not upscale by any method, because a second, smaller family
list existed beside `NATIVE_IMAGE_FAMILIES`; the Scale box changed nothing, because
`ImageUpscaleWithModel` has no scale input; and "Auto" meant `choices[0]`, which is
`4x-AnimeSharp.safetensors` — an anime model as the default for every photoreal render, chosen by
catalog order. Each is now either performed or refused, never substituted.

**The render gate, because "it runs" is not "it works".** Pixel distance is the wrong measurement
here: it answers *did the bytes change*, and the silent fallback changed the bytes too. What
separates a real upscale from a resample is high-frequency energy at identical dimensions — the
detail a filter cannot invent because it is not in the source. Measured on anima, 512×768 → 1024×1536,
seed fixed, the two graphs differing only in how they scale:

| | Laplacian variance | high-band energy (>0.25 Nyquist) |
|---|---|---|
| model (`4x-UltraSharp` → `ImageScale`) | 0.111086 | 21.20% |
| lanczos (`ImageScale` alone) | 0.013130 | 9.06% |
| **ratio** | **×8.46** | **×2.34** |

Downsampled back to the render's own size, the lanczos output is MAE **2.57** from the base and the
model output **9.14** — reconstruction, not resizing, and still the same picture. The gate was
watched failing at **×1.00** when a model request was served by a resize.

**One recon claim corrected by the measurement.** The note that produced this work said pixel
distance "passes today's silent lanczos". The two outputs are MAE **16.14** apart, so distance does
register the difference — what it cannot do is say *which* of the two is the upscale. The honest
form of the rule is that a distance check detects a change without telling you its direction, and
that is why the gate is spectral.

**And a process mistake worth more than the fix.** Deciding whether the legacy reader was dead, I
ran a grep piped through `head`, saw no callers in the visible lines, and deleted it. It had **16
live call sites** — checkpoint, VAE and CLIP binding for every native image and video family. The
truncation, not the tree, produced the answer. An unrelated sweep hit surfaced a seventh reader,
which made me re-run the grep without `head`. **For an existence question, `| head` converts "I did
not look" into "there is nothing."**

---

## 8. What was deliberately not done

**`worker_tcp.handle` is not a dispatch dict.** The plan called for it, justified as making
`test_worker_command_audience`'s extractor exhaustive. Measured first: the patched regex and an AST
reader agree exactly — 125 commands across `Eq`/`In`/`NotIn`, no gap today. So the *class* of failure
was closed without restructuring live protocol dispatch, where branch order is load-bearing. The
extractor now reads comparisons structurally and **refuses** any shape it cannot read: unknown
operators, `match`, `getattr(ws, command)`, string methods on `command`. Silently incomplete became
loudly unknown. If the dict is taken up later, gate it on the extractor becoming an *import* rather
than a parse.

**`MainWindow.cpp` was not split by line count.** The plan flagged this as a conflict and asked for
the split to be gated on coupling: *"if the header doesn't shrink, the split didn't happen."* The
evidence for caution was `ImageGenerationPage`, already split into 6 files and still 7801 lines
coupled through a 626-line header.

So coupling was measured. Clustering MainWindow's 102 methods by shared member field gives **one
component of 67 methods, 4557 lines, 87 fields**, plus 30 singletons. There is no seam in the blob.
But **nine methods touch no member field at all** — functions of their arguments that happened to be
declared inside a QMainWindow — and three form a closed unit: the request builders, 321 lines that
decide what the worker receives, reachable by no test because reaching a private member of a
QMainWindow means launching the GUI and rendering something.

Those moved, verbatim. `MainWindow.h` went from 443 to 437 lines. **That is a small number and it is
the honest one**: the header is 296 lines of private declarations for a single coupled component, and
no behaviour-preserving extraction is going to halve it. The gain is not the six lines; it is 24 test
cases over defaults that had never been asserted — including that the seed goes through
`toLongLong()` rather than `toInt()`, which is load-bearing because the cockpit spin box reaches past
2³¹.

Two things the extraction put on record rather than changed:

- `buildWorkerGenerationRequest` has **side effects despite its name**. It creates the output
  directory, and for a filename beginning `plate` it writes `prompt.txt` beside the output. A caller
  that builds a request in order to inspect it will have touched the disk.
- A studio command is stamped into **five** request keys and a chain queue id into **three**. Both
  are documented in the source as belt-and-braces. They are pinned rather than tidied, because which
  one the worker dispatch actually reads has not been established, and removing four would be a
  guess. What the test buys is that they can never *disagree*.

**Four Python tests broke on that move, and the fix was the finding.** Each had spelled
`MainWindow.cpp` and sliced the text between two function names; one used a neighbouring function as
its *end* delimiter, so it depended on the order of two unrelated definitions in a 7000-line file.
That is the memo-not-a-rule defect inside the tests that assert on C++. `tests/cpp_source.py` now
finds a definition by name across the tree and brace-matches its body.

**Other deliberate omissions**, each with the reason:

- The five family namespaces were **pinned, not merged** — they sit at different layers, and merging
  them would be applying a rule at the wrong level, which is this audit's own subject.
- `sd3` and `cogvideox` sampler tables were **not filled by copying a neighbour**. Doc 52 §7 already
  refused this for sd3 (flow matching makes `dpmpp_2m/karras` wrong); `cogvideox` is unrouted and its
  empty table is honest. An inert row that looks authoritative is worse than a gap.
- Flux's pinned CFG and its `[0,1] → [0.55, 1.0]` denoise remap were **not normalised**. Both were
  calibrated deliberately; flattening them to match six neighbours would be the same mistake.
- The krea2 inpaint topology was **not forced into the t2i shape**. Sixteen nodes through
  `VAEEncodeForInpaint` against ten; they differ because the work differs. Only the loader block —
  the part that was genuinely identical, and the part the defect lived in — was merged.
- TeaCache was **not wired**. Its win is assumed and has never been measured in this repository, and
  it is blacklisted on one of its three builders. Doc 50 rule 1 says a heuristic ships with a number.
- The 310 bare `except Exception` clauses were **not chased as a number**. Roughly 60% are legitimate
  best-effort.

---

## 9. Where it landed

| | before | after |
|---|---|---|
| Python tests | 1088 | **1456** |
| Python test files | 136 | 155 |
| C++ tests run by ctest | **0** | 6 |
| Sweep rules | 0 | 14 |
| Sweep baseline | — | 66, with 12 of 14 rules at zero |
| Modules no sweep could see | 10 of 92 | 0 |
| Modules nothing imports | 19 | 0 |
| ComfyUI root resolvers | 8 | 1 per side |
| Project-root searches | 5 | 1 |
| krea2 loader blocks | 4 | 1 |
| Pre-commit hook | none | ~13s fast subset |

The open items, stated as items rather than as a clean bill:

- ~~**No CI.** The hook is the floor.~~ **Closed 2026-08-31** — `.github/workflows/ci.yml` runs the
  hermetic lane on two platforms and `ctest` on Windows. The hook is now the fast floor, not the
  only one.
- **55 request keys with no reader.** A backlog with a decision behind each one.
- **`worker_tcp.handle`** remains 569 lines; its ratchet is exhaustive, its shape is not improved.
- **`MainWindow.cpp`** remains 6641 lines over one coupled component of 87 fields. The next honest
  move there is to break the coupling, not to move more lines.

---

## 10. The one-line version

Every defect in this audit was a place where the codebase already knew the right answer and applied
it once. The fragility was never ignorance of the rule; it was the absence of anything that carried
the rule to the second site. That is what the sweep harness is, and it is why the deliverable of each
fix is the property rather than the edit.
