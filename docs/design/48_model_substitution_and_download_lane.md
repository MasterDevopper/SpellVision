# 48 — Tier-4 model substitution and the background download lane

**Status:** shipped on `wave/rebuild-and-audit-fixes` (`7b6f838`, `7f38f5e`, `2404fbe`).

Closes the two halves of plan Workstream A4/A6: a workflow that names a checkpoint you do not have
can now offer an architecture-compatible substitute, and anything it does download reports real
progress without taking the app away from you.

Doc 45 is the research this stands on. This is what actually shipped, including the two places the
research turned out to be measuring the wrong half.

---

## 1. The measurement that changed the plan

Doc 45 established that the architecture a workflow needs is recoverable from the graph for **53 of
55** workflows, against 10 by filename-family matching. That is the *supply* side of tier 4 — what
the workflow wants. It never measured the *demand* side: given an inferred architecture, is there
anything on this box to offer?

Measured before building anything. An SDXL request offered **2 candidates** out of a catalog of
**112 SDXL checkpoints**.

The cause was not a missing taxonomy. It was two bugs that each looked like a design gap.

### 1a. A family key that resolved to the wrong family

`infer_model_family` matched aliases by plain substring, iterating `MODEL_FAMILIES` in declaration
order. `stable_diffusion` is declared first and carries the alias `"sd"`. `"sd"` is a substring of
`"sdxl"`.

```
infer_model_family("sdxl")  ->  "stable_diffusion"
```

The literal family key resolved to a different family, and with it every `sdxl/`, pony and
illustrious path that carried no other signal. This is the same shape as the `"hair"` matching
`air`, and `"swan"` matching video, that this project has been bitten by twice before.

The fix is **boundary-aware, longest-token-first** matching, with the leading edge refusing a
letter or digit and the trailing edge refusing only a **letter**:

| candidate | token | matches? | why |
|---|---|---|---|
| `sdxl` | `sd` | no | followed by a letter — a different architecture that starts with the same letters |
| `sd15` | `sd` | yes | followed by a digit — a version suffix flush against the name |
| `flux1-dev` | `flux` | yes | same |
| `sdxl` | `sdxl` | yes | and it is longer, so it wins the ordering |

That asymmetry is the whole rule, and it exists because version suffixes are written flush
(`flux1`, `wan2.2`, `ltx2`, `sd15`).

**Then it broke something, and the fix for that is the interesting part.** Some aliases are
*deliberately prefixes* — `illustri` exists to match `illustrious`, `illustriousXL`, and the real
Civitai model `illustrijBTTR_v10`. Those legitimately continue with a letter, so the strict rule
refused them. So matching runs in **two passes**: boundary-aware first, and only if nothing matched
cleanly, the historical plain-substring pass. A clean match always wins, so `sdxl` can no longer be
captured by `sd`, while prefix aliases keep working.

### 1b. The directory layer never fired on the references that needed it

`classify_model` reads the architecture subfolder, but `_type_and_arch_dir` required the **level-1
category** component (`checkpoints/`, `diffusion_models/`) to be present in the path in order to
find the level-2 arch folder after it.

A reference that comes out of a workflow graph or a ComfyUI combo list is **already relative to that
category**: `sdxl/foo.safetensors`, not `models/checkpoints/sdxl/foo.safetensors`. So the directory
layer never fired on exactly the references tier 4 has to classify, and the family fell through to
the filename layer — i.e. to bug 1a.

A known arch folder in leading position now counts. An unrecognised one is ignored rather than
guessed at, so `my_downloads/foo.safetensors` still contributes nothing.

**Result: 2 candidates → 112.**

---

## 2. `workflow_architecture_inference`

### Three states, never two

`infer_required_architecture` returns **RESOLVED**, **AMBIGUOUS**, or **UNKNOWN**.

Ambiguous is a real answer with a real candidate set — `EmptySD3LatentImage` genuinely does not
separate SD3 from Flux from Krea 2 — and flattening it into either a confident guess or a blank is
what produces the failure mode this codebase keeps hitting: a component that reports success while
being wrong. Contradicting markers (`{sd3,flux}` intersected with `{lumina,krea2}`) intersect to
empty, which reports UNKNOWN rather than falling through to whichever marker was seen first.

### Signal order, and why it is that order

| # | signal | confidence | note |
|---|---|---|---|
| 1 | `CLIPLoader.type` and friends | 0.95 | structural; the text encoder is architecture-specific |
| 2 | an **unambiguous** marker node | 0.90 | `EmptyLTXVLatentVideo` cannot appear in a non-LTX graph |
| 3 | **the missing model's own filename** | 0.75 | what the author actually had |
| 4 | latent dimensions | 0.55 | weakest, tie-break only |

Signal 3 is the one Doc 45 skipped, because it was measuring graph inference *against* filename
matching. For substitution they compose: the graph says what the pipeline needs, the name says what
the author used.

Signal 4 was demoted on evidence. The `width >= 768 → SDXL` rule reads well, and it fired for SD1.5
exactly twice in the library — `endercomic-v1` and `simple-t2i-generator` — and was **wrong both
times**. Both run an Illustrious (i.e. SDXL) checkpoint at width 512. Authors render SDXL small
routinely. So dimensions now only break a tie the filename could not, and a dimensions-only answer
is capped below 0.6 so it cannot look confident.

### Never compare a raw graph value literally

A live workflow in the library carries:

```json
{"class_type": "CLIPLoader", "inputs": {"type": "Wan-2.2 T2V"}}
```

No hardcoded table contains that string. Every raw value is normalised through
`infer_model_family` instead, which reduces it to `wan`.

### Lineage is a preference, not a gate

An Illustrious request is legally served by **any** SDXL checkpoint, with same-lineage sorted first
and the distinction shown so the user's choice is informed. Gating on lineage is precisely what
turns 112 candidates back into 0 — and it was the shape of the original "11 illustrious requests, 0
candidates" result.

### Sweep over the real library

| outcome | count |
|---|---|
| workflows naming a missing checkpoint/unet | **53** |
| resolved architecture **with** candidates on disk | **48** |
| resolved architecture, nothing on disk to offer | 0 |
| ambiguous (narrowed set, user picks) | 5 |
| unknown (no signal at all) | 0 |

The 5 ambiguous are the honest outcome, not a shortfall: four carry `EmptySD3LatentImage` with a
filename that names no family, and one narrows to `{lumina, krea2}`.

**Still true, and unchanged:** never auto-download on a guess, and never silently substitute. Tier 4
produces a ranked, reasoned *offer*.

---

## 3. The download lane

### Why it is not a queue command

`QueueManager._start_next_locked` returns immediately when `active_queue_item_id is not None`. The
generation queue is **strictly serial by design**, so a multi-gigabyte checkpoint enqueued there
would block every render until it finished — the opposite of the requirement. Downloads get their
own lane, threads and lock, and never touch the queue's.

### Real progress was nearly free

`model_sources._download_remote_asset` already read in 1 MB chunks with full byte accounting, for
its size-limit and disk-headroom guards. **It simply never told anyone.** It now takes `progress_cb`
and `cancel_cb`, and `DownloadManager` turns those into the same
`{current, total, percent, message}` shape a queue item exposes — so `GlowProgressBar` renders a
download with no new widget.

### Decisions worth keeping

- **Progress reports on a byte stride, not per chunk.** A 6 GB model at a 1 MB chunk is ~6000
  callbacks, each taking the manager lock, for a bar that cannot render that many positions.
- **Cancel is checked once per chunk**, so it lands within one chunk read rather than at the end of
  the transfer. A cancel that surfaces as some *other* exception — a socket torn down mid-read — is
  still reported as CANCELLED. A user who pressed Cancel must not be shown a red error for it.
- **An indeterminate total stays expressible.** No `Content-Length` and no declared size is a real
  state; it does not get an invented percentage.
- **Concurrency capped at 2.** One serialises a batch behind the largest file; unbounded saturates
  the link and makes every individual bar crawl, which reads as a hang.
- **Nothing holds a socket open.** The UI polls `download_status`, so a client can disconnect,
  reconnect, and still see a transfer that ran the whole time.
- **No resume, deliberately.** The existing path validates the final size against both
  `Content-Length` and the provider declaration. Re-establishing those against a partial file and
  getting it subtly wrong yields a corrupt checkpoint that loads and renders garbage. Restarting is
  slower and honest.

### In the shell

Generation outranks downloads for the bar. The download aggregate takes it only while nothing is
rendering; when both are live the bar stays with the render and the state text picks up a compact
`· ↓ N (P%)` suffix. The poll is decimated to every 8th queue tick while the lane is empty, and a
failed poll **clears** the lane rather than leaving a stale percentage claiming a transfer is
running.

---

## 4. The bug the pixel gate caught

The download poll first hung off `afterQueueSnapshotApplied`, which `WorkerQueueController` invokes
**only when the queue snapshot actually changed**. An idle app with an empty queue never changes —
so a download started while nothing was rendering, which is the normal case, never reached the bar.

It built clean. Every Python test passed. The first screenshot showed an **empty bar and "Idle"**
while the worker was reporting **30.09%**.

`MainWindow.cpp:1170` already carried a comment saying to use `queuePollSucceeded` and not the
change-gated signal, for exactly this reason, written the last time someone hit it.

Verified after the fix against a real 2.1 GB transfer: worker at 19.47%, bar rendered 19% with the
byte readout in the state label, app interactive throughout.

**The rule this reinforces:** gate on pixels on the surface, not on "it compiled and the unit tests
are green". The Python side had 21 tests including four over the live TCP protocol, and every one of
them passed while the feature was invisible to the user.

---

## 5. The offer — `resolve_missing_models`

Tiers 1 and 2 (a URL the workflow declared for itself; a reference that is already a URL or a
Civitai id) were already exact and needed no decision. The command assembles what is left.

### Tier 3 is identification, not search

Measured against ten real missing checkpoints from the library:

| query shape | result |
|---|---|
| name search, no type filter | 9 of 10 "resolved" |
| ...but the top hit for 4 of them | a **style LoRA**, not the checkpoint |
| `types=Checkpoint` + **exact filename match** | **5 of 10**, all correct |

A search that answers 9 and is wrong about 4 is worse than one that answers 5 and knows it. A
download is offered only when a Civitai model *version* contains a file whose name matches the
wanted filename exactly. The five that find nothing fall through to tier 4 — together, all ten have
a path.

Substitutes are returned **alongside** an exact match, not instead of it. A user on a metered
connection with 112 compatible checkpoints should not be told to fetch 6 GB without being shown the
alternative.

### Catalog sources, in order

1. **Live `/object_info`** when ComfyUI is up — what the launch path itself will see, so the offer
   *predicts* the launch rather than approximating it.
2. **The configured model roots on disk**, `extra_model_paths.yaml`-aware, when it is not.

Both yield names **relative to the category root** (`sdxl/foo.safetensors`). The architecture lives
in that leading folder; a basename throws it away and the classifier then has nothing to go on.

### Three defects, all of which reported success while being wrong

**The 120-second block.** The offer inherited the `/object_info` retry budget, which exists so a
generation job can ride out a model swap. An interactive "what is missing?" blocked for two minutes
against a ComfyUI that was simply down. `_comfy_object_info` now takes an optional `budget_sec`;
the default and every existing caller are unchanged. **120 s → 6.6 s.**

**The stale cached compile.** Falling back to `prompt_api.json` is only safe if its loaders still
carry inputs. The superseded C++ converter stripped them from 530 nodes across 19 workflows, and a
graph that binds no model names answers *"nothing is missing"* — a confident all-clear on a
workflow that cannot run. `_loaders_have_inputs` guards it, and **caught 7 stale profiles on the
first sweep**.

**The checkpoints-only catalog.** Wan and Hunyuan ship as diffusion models under
`diffusion_models/` or `unet/`, so every video workflow was told nothing on disk could serve it
while 30 compatible files sat one folder over. It surfaced as an *empty result*, never as an error.
`none` went from **33 → 0**.

Plus two smaller ones: walking the model roots per call took minutes across the library (now cached
with a 30 s TTL, so a newly downloaded model still appears on its own), and
`req.get("object_info_budget_sec") or 6.0` turned a caller's deliberate **zero** into the default.

### Library sweep, offline

No Civitai lookup, so no exact match can appear — this is the floor, not the ceiling:

| | count |
|---|---|
| readable profiles | 74 |
| substitute offers | **65** |
| honestly ambiguous | 6 |
| nothing to say | **0** |
| correctly reported as stale artifacts | 7 |

Substitute breadth: min 30 (video), median 112.

---

## 6. Remaining

- **The picker UI is not built.** The worker returns the ranked offer; nothing yet presents it.
  That is the next piece — the dialog serves tier 3 and tier 4 together.
- **7 profiles carry a stale `prompt_api.json`.** They are correctly reported as unreadable rather
  than silently passing, but recompiling them through the Python converter would recover them.
- **`hunyuan_3d` is not a registry family**, so `infer_model_family` cannot return it; the directory
  layer covers it. Pre-existing, harmless, worth knowing.
- **The state label elides hard** on a long download message. Pre-existing bottom-strip behaviour —
  full text on hover — but a shorter message form would read better in the strip.
- Download records are **in-memory only**; a worker restart forgets an in-flight transfer.
