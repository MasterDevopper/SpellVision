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

The gap this table made visible — nothing distinguishing a command that is *deliberately* CLI-only
from one someone forgot to wire — is now closed by `test_worker_command_audience.py`, which turns
Doc 49's one-off sweep into a standing guarantee. Writing it also demonstrated rule 9 on itself: the
first version's regex missed `command not in {...}`, so a block of generation commands sat
unclassified while the completeness test stayed green.

The gap the table makes visible *now*: every ratchet here is Python. The C++ side has no equivalent,
and two defects in this pass lived there — a seed spin box that could not express the value the
worker had just been taught to honour, and a sentinel the panel advertised that no builder
implemented. A UI control's range is part of the contract, and nothing currently checks that it
matches.
