# Doc 62 — T2–T6 follow-ups

**Status:** open work list, opened 2026-09-17 on branch `fix/t2-t6-followups`, off the T2–T6 merge (`bd084ab`).

Every item here was found by the work that built T2–T6 and recorded rather than fixed, because fixing it belonged to a different wave or would have widened one already in flight. Each says what it is, where it lives, and how it was found — a list of symptoms is not a work list.

Ordered by what a user hits first.

---

## 1. Coverage, not code — the largest gap by far

Every gate reads PARTIAL for the same reason: the mechanism works and has been pointed at a fraction of the library.

| gate | proven on | the whole |
|---|---|---|
| T3 models | **14** identified | **759** |
| T5 defaults | one page, one family | four pages × ~16 families |
| T4 optimizations | krea2, ltx | six shipped families |
| T2 drop | 5 workflows, **none video** | ~90 imported |
| T6 routing | SDXL on the node | every family it can run |

**The cheapest large win is one click:** a full `model_intel_refresh` over both model roots, roughly 79 minutes unattended. It takes T3 from 14 to 759 *and* gives T5 real per-model defaults across the whole library instead of one checkpoint. Nothing needs writing first.

---

## 2. Regressions in honesty — things that now correctly look worse

These are not bugs. They are the old answer being wrong. Listed so nobody "fixes" them back.

- **`krea2-compact-t2i-v10` shows NOT ready in Flows**, where it used to show Ready. It has 1 of 4 models present. A UI graph with no compiled prompt yields zero model references, and zero read as "nothing missing".
- **The model-stack card's "Loaded: `<name>`" label no longer updates on a drag-drop**, because the window claims the drag first. The draft chip on the page the workflow lands on is better feedback and on the right page — but that card changed.

---

## 3. Real defects, in the order a user meets them

**3a. Pro Grade v17 lands with an empty prompt.** The owner's headline graph drops, routes and populates its checkpoint — then sits at 100×100 with cfg 0.0 and no prompt. The draft builder finds no text to carry. `qt_ui/workflows/WorkflowDraftBuilder.cpp`.

**3b. A first-ever import of a workflow with missing node packs times out at 120 s.** cm-cli cold is ~128 s; the cache is why the *second* drop works. Either raise the budget for a cold import or make the first call warm the cache without holding the request. `python/node_dependency_resolver.py`.

**3c. The Download dialog cannot see a UI graph's missing models.** It reads the import's own model plan; readiness sees them and closes submission. So the user is told the workflow is not ready and is not offered the download that would fix it. `MainWindow.cpp` drop path + `workflow_library_commands.py`.

**3d. A file that is not a workflow is refused for the wrong reason** — treated as an API prompt and timing out, rather than "this is not a workflow".

**3e. `clip_skip` and `guidance` are resolved by the worker and discarded.** No widget exists for either. Either add them to Advanced or stop resolving them; silently dropping a published setting is the defect class this whole arc was about. Blocked on `ImageGenerationPage.cpp` being over its 3000-line ceiling.

**3f. A preset and a model's own defaults both write steps and CFG**, so which the user sees depends on the order they touched them. Decide it: a preset is a deliberate choice and should win until the model changes.

**3g. Card kinds are read at scan time**, so a sidecar written after a scan does not move the card between tabs until the next inventory refresh. The inspector updates immediately; the card does not.

**3h. NSFW blur has no reveal.** A blurred preview is a 10×10 downscale re-expanded — genuinely unreadable, and permanent until the setting changes. No click-to-reveal.

**3i. No rate-limit backoff is surfaced.** A CivitAI 429 lands in `lookup_failed` and the summary says so, but the user is not told to wait rather than retry.

---

## 4. Test-suite debt

**4a. `test_godfile_split` fails**: `ImageGenerationPage.cpp` is ~3135 lines against a 3000 ceiling, and it blocks 3e and 3f. Splitting it is the unblock.

**4b. `shell_layout` fails on two cases**, both **self-invalidating guards failing on an unmet precondition** — `a_control_inside_a_collapsed_tab_keeps_its_value` ("no inspector tab put a spin box on screen") and `a_deferred_rail_page_built_after_a_switch_arrives_into_the_switched_shell` ("train was already built; nothing was proved"). A test that cannot set up its subject should report that it could not try, not report failure. Its own defect class.

**4c. Ten more pre-existing failures** on main, mostly worker-timeout shaped. They predate this arc and were verified against a clean tree.

**4d. The pre-commit hook runs only the 211 ratchet-marked tests**, so a red full suite is invisible to it. That is how a set of failures swapped underneath a matching count during this arc.

---

## 5. Architecture debt this arc created or exposed

**5a. `kLeverProbes` is a second list of lever ids** in the Runtime panel's C++, mirroring `optimization_levers.ALL_LEVERS`. Verified by hand today; a drift surface a sweep rule should close. Failure mode is safe (an id added only in Python reads "unknown").

**5b. Queue lanes key on the endpoint URL string**, so `http://192.168.1.127:8188` and `http://spellnode:8188` would be two lanes for one machine. The registry gives an endpoint a stable id; lanes should key on that.

**5c. `INPUT_FOLDERS` is a table** mapping loader input → `/models/{folder}`. A missing entry costs a slower check and never a wrong verdict, but tables go stale.

**5d. The arm memory is process-wide and leaks between pytest tests.** A `forget_arm()` call sits in one fixture; no ratchet enforces it for future tests that launch a manager.

**5e. `host_ram_gb` is accepted and unwired.** Deliberate — CLAUDE.md §6 records host RAM as real but unmeasured, and inventing a threshold would repeat the VRAM mistake. Either measure it or drop the parameter.

---

## 6. Measurement follow-ups

**6a. The harness should measure the baseline twice — first and last — and report against the trailing one.** The first arm of a session runs 7–8% slow even after its cold render is discarded, which is larger than most effects being measured. Currently done by hand; it belongs in the harness.

**6b. SageAttention 2.2 is not installed.** The venv has `sageattention 1.0.6`, which is SA1 Triton kernels. The research puts the first real measurement at SA2.2. Installing it changes the owner's render environment, so it is the owner's call — but every sage number in Doc 60 should be read as SA1 until then.

**6c. Four families are untimed** — wan, hunyuan, mochi, flux — and video is where the only real attention win showed up.

---

## Related

Doc 54 (requirements) · Doc 55 (the walkthrough and its verdict table) · Doc 60 (T4 measurement) · Doc 61 (SpellNode setup) · the per-wave ledgers under `.superpowers/sdd/2026-09-1*/progress.md`, which hold every ruling and the reasoning behind it
