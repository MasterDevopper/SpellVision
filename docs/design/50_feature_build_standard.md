# 50 — The feature build standard

**Status:** active. Apply to every feature from v0.1.0 onward.

The owner asked for two things alongside the Krea 2 work: a repeatable way to build each feature
*sophisticatedly*, and a critique of what was already built so v0.1.0 does not ship bugs we already
had the evidence to prevent.

This is the first. Every rule below is here because it caught a real defect — the citation is the
defect, not a principle. Nothing is aspirational.

---

## The governing observation

> **The dangerous failures report success.**

Every serious bug found across this work had the same shape. Not a crash, not a traceback — a green
result over a wrong or absent one:

| what it looked like | what it was |
|---|---|
| `ok: true` + empty payload | an unregistered worker command returning a `client_warning` envelope |
| `ready: true`, green badge | a scanner that skipped subgraph internals it could not read |
| "nothing missing" | a `scan_report.json` written before the check existed |
| a clean conversion | a bypassed `LoraLoader` leaving the sampler's `model` unset |
| a cancel that returned success | `snapshot_payload()` overriding the handler's `ok` |
| 764 tests passing | the download progress bar wired to a signal that never fired |
| `exact_download` | the first same-named file from an unrelated uploader |
| "★ recommended for your GPU" on every row | a recommendation computed per version on a model with one precision per version |
| a model list with nothing missing from it | a BitLocker-locked drive indexing as an empty one |
| a render that came back | a seed of 0 silently rendered as 1, or as a clock reading |

A rule that only prevents crashes is not worth writing down. These are the rules that prevent
confident wrongness.

---

## The nine rules

### 1. Measure before building

Every heuristic gets a number on the real corpus *before* it ships.

- Name-similarity substitution ranking: **0 of 16**. Deleted before it shipped.
- Tier-3 name search "resolved" **9 of 10** missing checkpoints — and 4 of those were a *style
  LoRA*, not the checkpoint. Constrained to exact-filename + type filter: **5 of 10, all correct.**
  An answer for 9 that is wrong about 4 is worse than an answer for 5 that knows it.
- "We have 2 substitution candidates" was actually **112**.
- The precision-dispute check — written in this same pass — was measured across the 100
  most-downloaded Civitai checkpoints before it shipped: **121 of 1101 candidates flagged, 11%**,
  essentially all false. The scope was wrong, not the idea. Narrowed to where identity is
  established rather than assumed, the same code flags **3 of 1101 (0.27%)**, and all three are
  real. Two more of the original five survivors came from mapping `fp32` into the 16-bit class,
  which made every honest fp16-alongside-fp32 SD1.5 pair look like a mislabel.

A heuristic without a number is a guess with formatting. **This applies hardest to the heuristic
you just wrote**: measuring it is how you find out it was scoped wrong, and the measurement takes
minutes against days of it being subtly wrong in the field.

### 2. Ground from live artifacts, never from memory

`/object_info` dumps, real API payloads, the actual workflow JSON.

- Live `CLIPLoader.type` returned `"Wan-2.2 T2V"`, matching no hardcoded table anywhere.
- `CLIPLoader.device` was confirmed as an *optional* input accepting exactly `{default, cpu}` by
  reading the live schema — not by copying the value out of the reference workflow.
- Two Cloudflare R2 delivery hostnames were guessed for the Civitai allowlist. **Both wrong**; the
  live redirect goes to `b2.civitai.com`.

Corollary, learned twice while writing this document's own commit: **a filename and a public API
listing are not the file.** Two module docstrings written from those alone were both wrong —
`comfy_graph_helpers` is schema introspection, not graph rewiring; `gpu_info` is an uncalled
standalone script, not the NVML fast path.

Second corollary, and the sharper one: **the live artifact can itself be wrong.** Grounding tells
you what a field *says*, not whether it is true. Civitai's `metadata.fp` is typed by an uploader,
and on model 2726029 a 12.57 GB file declares `bf16` while the genuine bf16 in the same model is
24.48 GB; LUSTIFY publishes one filename at 24.48 GB and 12.25 GB with every row declared `bf16`.
Ranking on that field promoted an int8 checkpoint to "the highest precision available".

So where two fields describe the same thing, **prefer the one the source cannot mistype**. Size is
a consequence of the bytes; precision is a label typed beside them. Ranking on size also killed an
older bug structurally rather than by a guard — a bundled 0.24 GB VAE is the *smallest* file
present, so a largest-that-fits rule can never surface it as the model. Same for identity: a name,
a size and a precision are all things a listing can get wrong, and two of the three have been
observed wrong, which is why a download is now checked against the provider's SHA256 rather than
against its length.

### 3. Three states, never two

`resolved` / `ambiguous` / `unknown`. **Ambiguity is an answer**, and collapsing it into either
neighbour is how a guess gets laundered into a fact.

- `AmbiguousDownload` when several genuinely different files share a filename.
- `AmbiguousCivitaiModel` when a link names no version.
- Architecture inference reports `ambiguous` rather than picking the likelier family.
- A ZIP holding two workflows refuses and names them.

- A precision dispute is reported only where a majority of the same model's files agree on a
  reading. Two files that contradict each other are a tie, not a verdict — nothing says which of
  them is the mislabelled one — so that case reports nothing rather than naming a culprit.
- `stated_seed` returns `None` for "the request said nothing", separately from `0` for "the request
  said zero". The LTX templates carry two deliberately different blueprint seeds, so silence has to
  stay distinguishable from a stated zero.

**"Unreadable" is a third state too, and the standard library keeps collapsing it into "empty."**
Three separate behaviours each turn one into the other: `Path.resolve()` *raises* on a
BitLocker-locked drive rather than returning the path, `Path.is_dir()` answers `False` for any
`OSError` so a guard skips exactly what it cannot stat, and `os.walk` discards errors unless given
an `onerror` handler. All three were present in one function. With D: locked, the model index fell
from thousands of files to 57 and every model on that drive reported missing — an invitation to
re-download tens of gigabytes the user already owned, with nothing anywhere naming the cause.

The test of a two-state design: ask what it returns when it does not know. If that is the same
value it returns for one of the real answers, it will lie.

### 4. A component must be unable to look correct while being wrong

Not "should not" — *unable*. Design so the failure mode is loud.

- No `ok: true` around an empty payload.
- No "nothing missing" derived from an artifact that could not be read.
- Readiness fails on an unresolved subgraph, because a green badge was the last route to a launch
  that would then refuse with a raw UUID.
- A model root that could not be read is named in the plan and at the top of the readiness
  warnings. The model still reports missing — there is no way to know otherwise — but the reason
  now travels with it.
- A downloaded file is checked against the provider's SHA256, hashed from the transfer's own
  chunks. Every check before it was a *plausibility* check — Content-Length against declared size,
  bytes written against Content-Length, size within 1% — and all of those pass for any file of
  roughly the right length, which is precisely the failure being guarded against.

Note the asymmetry worth designing around: **under-reporting is the more dangerous direction here.**
Over-reporting presence fails loudly at load time. Under-reporting fails by quietly proposing an
expensive wrong answer.

### 5. One resolver, not two

A checker that decides differently from the doer is a bug generator.

- The model picker offered 112 substitutes for a model the launcher could already resolve, because
  the picker required an exact match and the launcher resolved bare basenames.
- The subgraph expander is **pure topology, no `/object_info`** specifically so the scanner (which
  runs with ComfyUI unreachable, by contract) and the converter share one code path and agree on
  node ids.
- The Qt import dialog had a file-dialog filter *and* a separate hard-coded validator list. Adding
  ZIP to the backend would have left the Import button disabled with a message naming the old set.
- 26 sites across 12 modules each resolved the ComfyUI endpoint their own way, using five
  different environment variable names, with two modules hardcoding `127.0.0.1:8188` and reading no
  environment at all. Pointing SpellVision at another machine would have moved some paths and
  silently left others on localhost.
- Twelve graph builders each wrote their own seed line and four of them were wrong. One rule
  (`resolve_seed`) plus a test that fails on any seed assignment not going through it.
- Where a second copy is genuinely unavoidable (layering), **pin them together with a test** —
  `test_the_zip_predicate_agrees_with_the_url_importer`.

Applying a rule at the wrong *level* is the same bug wearing a disguise. `recommend_file` narrowed
its candidates to one checkpoint's precisions, which is correct for a single version's raw file
list — and applying it again across versions collapsed a legitimate six-file choice to one file,
returning the same answer for a 12 GB card and a 32 GB one with the fitting logic never running.
One rule, applied exactly once, at the level where it is true.

### 6. Gate on the artifact, not the build

Pixels on the surface. Bytes on disk. A render in `/history`. Never a green suite alone.

- 764 tests passed while the download progress bar was dead — it polled off a signal that only
  fired on *change*.
- An MP4 decoded perfectly and never displayed: `QVideoWidget` failed silently.
- A byte-identical resubmit hit ComfyUI's node cache and returned a *fake* 12.1 s / 23.62 GB
  measurement. Vary the seed to force real sampling.

A green build says the code compiles, not that the feature exists.

### 7. Register the seam

Every new worker response type goes into `worker_client`'s message types **in the same commit** as
its command, with a test. An unregistered type is wrapped in a `client_warning` envelope whose own
`ok` is `true` — the UI sees success and shows nothing.

Generalised: when a feature crosses a boundary, the boundary's registry is part of the feature.

### 8. A default must not be able to replace a stated value

A default is for the absence of an answer. The moment it can also replace an answer the user gave,
the control is decorative — and it looks like it worked, because something still renders.

The mechanical forms, all found in this tree:

- **`or` against a falsy-but-legitimate value.** `int(req.get("seed") or 1)` cannot express seed 0.
  Same trap as the `/object_info` budget and the VRAM figure, where `or` turned a deliberate `0`
  into auto-detection.
- **A clamp that moves a legal value.** `if seed <= 0: seed = 1` — 0 is legal (`KSampler`'s `seed`
  declares `min: 0`) and is a value people type on purpose.
- **A sentinel nobody implemented.** Chain's panel offered "random (-1)"; `-1` meant seed 1 on Wan,
  a clock reading on the split routes, and a 400 from ComfyUI on the image families.
- **A widget that cannot express the range.** The cockpit's seed box ranged `1..999999999`, so the
  minimum made the most likely seed unreachable and the maximum silently clamped any recalled seed
  above it — the re-render then came back a different image.
- **A default computed from the clock.** Two builders derived a seed from `time.time()`, which
  makes the render unreproducible from its own metadata: the seed recorded is not a seed that can
  be replayed.

Each of those read as deliberate where it stood. They only looked wrong beside the other eleven
builders — which is the argument for rule 5, and for asking of every default: *what legitimate
input does this make unsayable?*

### 9. State the cause you verified, not the one you assume

Three separate messages this session named a cause that was never checked. Text-scanning source
produced a confidently wrong conclusion **five times** — including "lumina and pixart are
unreachable by any user", reported as fact, when the detection simply lived in C++ where the scan
was not looking.

Before asserting a cause: check it a second way. Call sites, not just string literals. The menu,
not just the handler. The bytes, not just the return value.

---

### 10. A rule is applied to the tree, not to the site

The nine rules above are sound. They were also enforced **at the place each defect was found and
nowhere else**, which is rule 5 failing one level up: at the level of process rather than code.

The 2026-08-30 audit surveyed the whole repository against them and found that **eleven of the top
twenty fragility findings were second copies of a rule already applied correctly once** — usually in
the same file as the correct copy:

| the rule | applied correctly at | not applied at |
|---|---|---|
| `os.walk(onerror=)` so unreadable ≠ empty | `model_dependency_resolver.py` | `model_resolution_commands.py` |
| check `HasExited` before waiting out a timeout | `start_backend.ps1` | `comfy_runtime_manager.py` |
| handshake before adopting a listening port | `start_comfy.ps1` | `start_backend.ps1` |
| `0.0 <= strength <= 1.0` — zero is a legal denoise | flux, `native_image_graphs.py:112` | 6 builders, same file |
| `resolve_seed` — zero is a legal seed | 13 sites | `clothes_only.py`, `look_completion.py` |
| `_sampling_for` — the dropdown must not be inert | 7 image builders | 8 video routes |
| the memory profile places the text encoder | krea2 t2i | krea2 inpaint, look, clothes |
| one project-root search | — | 5 copies, disagreeing on depth |

The ratchets meant to prevent this had **the same shape as the bug**:

| ratchet | the scope it actually had | what it could not see |
|---|---|---|
| `test_seed_is_one_rule.py` | 3 files named in `BUILDER_FILES` | 5 violations tree-wide |
| `test_comfy_endpoint.py` | `(ROOT/"python").glob("*.py")` | 10 of 92 modules — two whole packages |
| `numeric_option` | a helper with no sweep | 87 sites of the defect it prevents |
| `test_worker_client_message_types.py` | the registry's self-consistency | 9 emitted types, unregistered |

So: **a fix ships as a property enforced across the tree, or it has not shipped.** A rule scoped to
where its defect was found is not a rule, it is a memo. In practice:

- The scope lives in **one place** and rules receive it. No rule may name a file.
- An exemption is keyed by site and valued by a **reason**, never a boolean. The third state —
  neither compliant, nor violating, nor documented, merely *out of scope* — is how a defect hides in
  plain sight.
- The count is pinned in **both directions**. A count that may only go down turns a baseline into a
  permanent allowance, and a count that silently absorbs a moved site hides it behind a number that
  looks unchanged.

Four things the audit learned about writing these, each from a rule that failed while reporting
success:

**Dead code satisfies ratchets.** `python_exe` had a reader — in a package nothing imported. The key
was satisfied by code that could never run, and deleting the package is what revealed it had no live
reader at all. An unreachable module does not merely carry duplicate defects; it makes a live rule
report a pass.

**An omission has no syntax.** The text-encoder rule caught a `device` written by hand and drove
itself to zero across nine sites while four loaders passed no device at all — the OOM-vs-fits bug,
untouched, in the phase that was fixing it. A rule that matches a wrong value cannot see an absent
one; match the *class*, then check what it declares.

**Zero can mean the shape is wrong, not that the tree is clean.** `zero-is-sayable` was written for
the denoise defect, went to zero, and stayed there for two phases while eight copies survived as
guards (`if not (0.0 < x <= 1.0)`) rather than as the `or`-default it matched.

**A guard nobody has watched fail is a guess about what it does.** Both new rules in this pass were
silently broken on first run. The dispatch-shape guard missed one of the four shapes it claims to
catch. The project-root rule had a mangled escape that left a literal backspace in its pattern, so it
matched nothing and reported a clean tree — indistinguishable from success. Feed a rule every shape
it claims to catch, and assert it stays quiet on the shapes actually in use.

And the counterweight, so this rule does not become its own defect: **a rule that flags two false
positives per true one gets bypassed, and then it protects nothing.** The wire-type sweep reports 30
against 10 real when scoped to every `{"type": ...}` literal. The project-root rule reported 3
against 1 real when scoped to files rather than to proximity. Both numbers are recorded in Doc 53
rather than quietly fixed, because a rule's precision is part of its design, not an implementation
detail.

---

## Applying it

A feature is done when:

1. Its heuristics have numbers from the real corpus (rule 1) — including the ones just written.
2. Its schema assumptions came from a live dump, and where the dump itself could be wrong it ranks
   on the field the source cannot mistype (rule 2).
3. It has a name for "I don't know", and a separate one for "I could not look" (rule 3).
4. Its failure is louder than its success is quiet (rule 4).
5. Nothing else in the tree decides the same question differently, and its rule is applied once, at
   the level where it is true (rule 5).
6. It was verified on the artifact, not the build (rule 6).
7. Every boundary it crosses is registered, with a test (rule 7).
8. No default it carries can replace a value the user stated (rule 8).
9. Every causal claim in its commit message was checked twice (rule 9).
10. Every rule it relies on is enforced across the tree, by a check that has been watched fail
    (rule 10).

## Where the ratchets live

Rules are advice; tests are enforcement. The ones that hold this standard in place:

| ratchet | holds |
|---|---|
| `tests/test_family_capability.py` | a family cannot be "supported" while missing a layer |
| `tests/test_queue_commands_live.py` | every menu command + its payload key, over the real protocol |
| `tests/test_comfy_subgraph_expansion.py` | 268/268 identity on non-subgraph templates |
| `tests/test_worker_client_message_types.py` | rule 7, mechanically |
| `tests/test_comfy_object_info_transport.py` | the transport fix stays fixed |
| `tests/test_credential_store.py` | the plaintext secret never reaches disk |
| the god-file drift sweeps | split modules keep their imports (`py_compile` passes either way) |
| `tests/test_worker_command_audience.py` | every command declares who it is for, and nothing is unclassified |
| `tests/test_comfy_endpoint.py` | no second hardcoded endpoint or direct env read |
| `tests/test_seed_is_one_rule.py` | no seed assignment outside `resolve_seed` / `stated_seed` |
| `tests/test_model_root_readability.py` | an unreadable model root is named, not indexed as empty |
| `tests/test_model_download_verification.py` | bytes are checked against the provider digest, not just a length |
| `tests/sweeps/` + `tests/test_sweeps.py` | rule 10, mechanically: 17 rules over one source list, no rule naming a file |
| `tests/test_project_root_is_one_rule.py` | five copies of one tree walk stay one |
| `tests/test_vram_reader.py` | a GPU number says which process it measured; "not measured" is null, never zero |
| `tests/test_krea2_loader_block.py` | four krea2 routes share one loader block, so the memory profile reaches all of them |
| `tests/test_denoise_is_one_rule.py` | a stated `0.0` denoise survives under every spelling the cockpit sends |
| `tests/test_comfy_launch_policy.py` | ComfyUI is never launched with an attention backend the interpreter lacks |
| `tests/test_remote_endpoint_output_locality.py` | a render on another machine is never located on this one's disk |
| `tests/test_worker_auth_request_schema.py` | an integration caller cannot choose the machine, the install, or the path; every path-like request key has a stated policy |
| `tests/test_worker_session_secret.py` | loopback alone buys `ping`; the full surface needs this launch's user-only secret, and the shipped worker is driven over a raw socket to prove it |
| `tests/test_comfy_output_asset_safety.py` | the remote contributes a basename and an allowed suffix, and the bytes must look like the suffix before they are written |
| `tests/test_node_install_trust.py` | the git fallback is https-only behind `--`; `pinned` means a commit; consent is asked after the plan and lists each repository |
| `tests/test_ui_release_polish.py` | worker stderr is never a dialog body (tree-wide); dev tools read one env predicate; the version is spelled once; the update check only reports |
| `tests/cpp/test_responsive_matrix.cpp` | now nine surfaces — Workflows and Runtime were absent, and both shipped exactly the defects the matrix catches |
| `tests/cpp/test_app_version.cpp` | version comparison is numeric, antisymmetric, and the binary knows its version |
| `tests/cpp/test_canvas_aspect.cpp` | the canvas converges on the picture's aspect, does not oscillate, and grows again when the parent grows |
| `tests/test_import_writes_trigger_sidecar.py` | a LoRA imported through the app keeps its trigger words, in the sidecar shape the Models page reads; an existing sidecar is never overwritten |
| `tests/test_model_delete_containment.py` | delete removes one model under the configured root with its sidecars; refuses outside, traversal, links, directories, non-model suffixes, and an unconfigured root; not reachable by the integration tier |
| `tests/test_v1_feature_small_fixes.py` | Inspire forwards the recipe and every key it reads is one the worker writes and one the cockpit reads; Models reaches the one download lane; the comic page is lettered |
| `tests/sweeps` rule `late-bound-names-resolve` + `tests/test_late_bound_names_resolve.py` | every `_ws().name` / `ws.name` / `worker_service.name` is a name worker_service binds at module level — py_compile, import and a mocked suite all passed while `resolve_comfy_output_path` stopped every native image family |
| `tests/test_generation_failure_classification.py` | a programming-error type is emitted as `internal_error` with a message that says so; user and environment errors keep their message — through the real queue runner, read back from the manifest |
| `tests/test_comfy_wait_progress_is_honest.py` | the ComfyUI wait is a heartbeat (`total == 0`), never a fake percentage the status bar can extrapolate a countdown from |
| `tests/cpp/test_canvas_aspect.cpp` (cold-label case) | the fit is measured against the preview AREA, never the label the cap constrains: a render arriving at a cold 48×86 label fills the column |
| `tests/cpp/test_action_row_pill.cpp` | the error pill elides to the row it gets, grows with the row, keeps the full text one hover or click away, and never pushes Generate off the page |
| `tests/cpp/test_lora_stack_row.cpp` | every button in a LoRA card fits at the 215px the card gets at half-screen; the reorder arrows know the ends of the stack |
| `tests/cpp/test_queue_tally.cpp` | "Queue: N" is outstanding work over the mode's commands; failed is counted beside it; terminal rows never count |
| `tests/cpp/test_canvas_size_default.cpp` | every generation page opens with a canvas size; an unsized i2i / i2v page takes its input image's size, snapped and bounded; an explicit size is never overridden |
| `tests/cpp/test_responsive_matrix.cpp` (viewport clause) | a resizable scroll area with its horizontal bar off never holds content wider than its viewport — the one shape the matrix's own scroll-area skip could not see |
| `tests/test_ui_release_polish.py` (parked pages) | a page built ahead of its first visit is hidden until the stack homes it — a visible child at the window origin painted over the title bar |
| `tests/test_family_license_surfaced.py` | the licence answer is the registry's, once: the generated C++ table cannot drift from `MODEL_FAMILIES`, no second resolver names a family near licence words (33 bare hits, all false; 0 with the proximity clause), the settings key is spelled once, every surface that names a chosen model shows its licence, and every submit path asks the one gate |
| `tests/cpp/test_family_license.cpp` | the decoy corpus the substring predicate failed on — animagine, animatediff, animation, a model path — is not badged; every alias answers like its key; the gate has two states and neither blocks a render |
| `tests/test_notice_file.py` | NOTICE exists, is not a stub, names the Qt version the launcher uses and the libwebp tag CMake pins, covers every payload class Doc 28 §5 lists, and its open-questions summary is pinned both ways to the flags in its body |
| `tests/cpp/test_eliding_label.cpp` | a value whose length the UI does not control elides, keeps its full text a hover away, and does not raise the layout's minimum — asserted with a fixture name that has **no** UAX-14 break opportunity, because the old row test's names all contained a hyphen and so could not tell wrapping from eliding |
| `tests/cpp/test_telemetry_presenter.cpp` | the bottom bar's page name has one source, and a chip that cannot apply to a page is hidden rather than reading "none" |
| `tests/cpp/test_canvas_aspect.cpp` (caption + chrome + squash) | a caption's height does not grow with what it says; chrome is subtracted however much of it there is (no 160px constant); the cap limits the picture and never shrinks the controls beside it below what they need |
| `tests/test_ui_release_polish.py` (elision + bar) | one elision helper for widget text, with painted elision exempted by a written reason; each bottom-bar label has exactly one writer; the bar refreshes on a page change **and** on a plain poll, not only when the queue changes |
| `tests/test_ui_release_polish.py` (vocabulary) | no user-facing string speaks the engine's internal vocabulary — measured 36 hits before the fix, all real, all in one file, and **0** in Comic and Concept, which a read said were clean |
| `tests/cpp/test_responsive_matrix.cpp` (ancestry) | a clipped control is reported with its parent chain, each step's width against its minimum — the two cells this baseline shipped with were both diagnosed the moment the chain appeared |
| `tests/test_governing_docs.py` | every source file the five present-tense documents name exists — measured naive **28 of 218**, scoped **8 of 161**, **4 real**, the other four exempt by a written reason; and an exemption dies with the sentence it was granted for. The four real ones were modules this standard's own audit had deleted, still on the map four passes later |
| `tests/test_comfy_combo_schema.py` | every reader of an `/object_info` combo answers under **both** live shapes — 1738 legacy and 562 V3 on the same core, migrating per class, so a one-shape reader is correct until the class it reads moves |
| `tests/test_upscale_engine.py` | an upscale is performed or refused, never substituted: a model request the build cannot run says so, an unknown model name refuses with the installed list, the scale reaches the graph, Auto prefers a model that declares no subject |
| `tests/test_upscale_render_gate.py` (`needs_comfy`) | the model route carries high-frequency energy a resample cannot — ×8.46 Laplacian variance and ×2.34 high-band at identical dimensions, watched failing at ×1.00 when a model request was served by a resize |
| `tests/cpp/test_upscale_controller.cpp` | one switch for "is an upscale requested" (a checkbox beside a method list made "off" sayable twice), and Advanced revealing the raw knobs **in the same card** without changing what would be generated |
| `tests/test_upscale_reaches_every_family.py` | every graph a native builder produces has an image sink the graft can reach — the graft searched for the literal `SaveImage`, so every video family's `CreateVideo` was invisible to it and the upscale was neither performed nor refused; a terminal class is in `IMAGE_SINKS` or is documented as taking something other than an IMAGE, and the third state is what hid this |
| `tests/test_surface_honesty.py` (offered-vs-sent) | the modes that offer the upscale row and the modes whose request carries its keys **agree** — pinning either answer would turn a correct change into a red build, so the rule is the agreement, not the fence |
| `tests/cpp/test_generation_request_upscale.cpp` | the last hop — a tier set in the cockpit arrives in the request, in **video** modes as well as image. `GenerationRequestBuilder::build` is pure and static and had no test at all, which is how the upscale keys stayed fenced to image modes long after the premise for the fence stopped being true |
| `tests/cpp/test_generation_status.cpp` | a worker note left as the job's terminal message becomes the caption beside the image — the hop that made "the user is told" a property rather than an assumption |
| `tests/test_surface_honesty.py` (hidden state) | a control a surface does not offer does not contribute to that surface's request — hidden widgets keep their values, and every video request was carrying the last image-mode `upscale_enabled` |

The gap this table made visible in 2026-08-28 — nothing distinguishing a command that is
*deliberately* CLI-only from one someone forgot to wire — is closed by
`test_worker_command_audience.py`, which turns Doc 49's one-off sweep into a standing guarantee.
Writing it also demonstrated rule 9 on itself: the first version's regex missed `command not in
{...}`, so a block of generation commands sat unclassified while the completeness test stayed green.
Its second version, in the 2026-08-30 pass, replaced the regex with an AST reader and added a guard
that **refuses any dispatch shape the extractor cannot read** — then missed one of the four shapes it
claims to catch, until each was fed to it in turn.

**The C++ column, which this table previously named as its own gap.** Two defects in that pass lived
on the Qt side — a seed spin box that could not express the value the worker had just been taught to
honour, and a sentinel the panel advertised that no builder implemented — and nothing checked either.
It is no longer empty:

| ratchet | holds |
|---|---|
| `enable_testing()` + `add_test()` in `CMakeLists.txt` | the C++ tests are *run*, not merely built — 115 lines of existing test had never executed |
| `SpellVisionCore` object library | the UI's decision logic is linkable, which is what makes any of the rest possible |
| `tests/cpp/test_responsive_matrix.cpp` | Doc 30's 7×4 matrix, mechanically — the gate that had never been run |
| `tests/cpp/test_sampling_controller.cpp` | a widget's range expresses what the worker honours |
| `tests/cpp/test_worker_response_parser.cpp` | an unknown envelope is a failure, not a silent discard |
| `tests/cpp/test_project_root.cpp` | the merged tree walk, on a fixture tree rather than this checkout |
| `tests/cpp/test_worker_request_builder.cpp` | the 320 lines that decide what the worker receives |
| `tests/cpp_source.py` | a C++ assertion follows a function by name, so moving it is a refactor and not a failure |
| four sweep rules over `qt_ui/**` | machine paths, the ComfyUI root, request keys with no reader, and the project root |
| `QT_ASSUME_STDERR_HAS_CONSOLE` in the ctest environment | a failing C++ test says *which* case, not just that one failed |

That last row was found by breaking an assertion on purpose. ctest went red correctly and printed
`<end of output>`: the binaries are console subsystem and still wrote zero bytes to both streams,
because Qt logs to the debugger when it cannot see an attached console and ctest runs every test
through a pipe. All five Qt tests had been in that state. **A test suite that cannot say why it
failed is rule 4 failing about itself** — and the only way to find it was to make one fail.

The gap this table makes visible *now*: there is no CI. Every guarantee here waits on a human running
`pytest` and `ctest`. The pre-commit hook runs the fast subset in about thirteen seconds, which is
the floor, not the ceiling.
