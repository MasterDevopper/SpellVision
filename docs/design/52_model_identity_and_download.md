# 52 — Model identity: how a reference becomes a file on disk

**Status:** current as of 2026-08-29. Describes what the code does, with the reasoning that shaped
it. Where a number appears it was measured, and the measurement is named.

This is the "how it operates" companion to Doc 50's rules. The subject is the single question the
whole abstraction layer rests on: **a workflow names a model — which bytes is that, and how do we
get them without ever guessing?**

Doc 19's rule governs throughout: *never auto-download on a guess, never silently substitute.*

---

## 1. The pipeline, end to end

```
workflow JSON                                                    ComfyUI
     |                                                              ^
     v                                                              |
workflow_scanner            -- extracts model_references            |
     |                                                              |
     v                                                              |
model_dependency_resolver   -- is it already here?  -----------> already_present
     |                         (build_model_install_plan)           |
     v                                                              |
workflow_model_declarations -- does the graph name a URL? ------> tier 1, exact
     |
     v
model_sources               -- parse the reference, enumerate what is on offer
     |                         (parse_asset_reference, model_variants)
     v
[ the choice ]              -- CivitaiVariantDialog, if there is one to make
     |
     v
model_sources               -- fetch, verify against SHA256, place
     |                         (materialize_asset -> _download_remote_asset)
     v
models/<subdir>/<file>
```

Nothing in that chain picks between genuinely different artifacts. Where it cannot decide, it
raises something that carries the options (`AmbiguousCivitaiModel`, `AmbiguousDownload`) so a human
does.

---

## 2. Is it already here?

`model_dependency_resolver._model_present`, in two passes.

**Precise.** The exact relative path under a root mapped for the reference's kind — plus a bare
basename, *only when the reference names no folder of its own*.

**Loose.** The basename anywhere under any configured model root. This exists for kind/subdir
mismatches, and it is deliberately **not** applied to a folder-qualified reference: `flux/ae.safetensors`
is *asserting* where the file lives, and honouring `vae/ae.safetensors` instead marks a different
file present — after which the launcher's own basename fallback binds and executes it. Generic
names make that ordinary rather than exotic: `ae.safetensors`, `clip_l.safetensors`,
`model.safetensors` and `qwen_image_vae.safetensors` all appear under several architectures here.

### An unreadable root is not an empty one

`extra_model_paths.yaml` maps `D:/AI_ASSETS/models` in, and that is where essentially every
checkpoint on this machine lives. With D: locked by BitLocker the index fell to **57 files**, every
model on that drive reported missing, and the plan would have offered to re-download tens of
gigabytes the user already owned.

Three separate behaviours turned "unreadable" into "empty", and all three were in one function:

| behaviour | effect |
|---|---|
| `Path.resolve()` **raises** on a locked drive | the `except Exception: pass` around it dropped the root before the walk |
| `Path.is_dir()` returns `False` for any `OSError` | a `if root.is_dir()` guard skips exactly what it cannot stat |
| `os.walk` discards errors without an `onerror` | subtree failures vanish |

`_build_model_search_context` now returns the roots it could not read, `ModelInstallPlan` carries
them with an error line each, and readiness puts them at the top of the model warnings. The model
still reports missing — there is no way to know otherwise — but the reason travels with it.
`FileNotFoundError` and `NotADirectoryError` stay silent: the config lists roots optimistically (an
F: drive sits alongside D: here), so "not there" is normal and must not drown the signal.

---

## 3. What is on offer

`model_sources.model_variants` reduces a `/api/v1/models/{id}` payload to `CivitaiVariant` per
version, each carrying every `CivitaiFile` in it.

**A filename is not a key.** Civitai reuses one filename across precisions inside a version —
`loxsUtopicWorldKrea2_v20Quants.safetensors` is the name of the nvfp4, the int8 *and* the fp8. The
key is `file_id`.

**A version is not just the checkpoint.** It bundles the text encoder, the VAE and the workflow
JSON. So `precision_variants()` (files sharing the primary weight's name) is what a user chooses
*between*, and `companion_files()` is what comes along with whichever they pick. Without that split
a "highest precision that fits" rule recommended a 0.24 GB bf16 VAE as the model.

**The precision axis is sometimes the version axis.** Two shapes, both real, both must work:

| model | shape |
|---|---|
| 2823011 "Lox's Utopic World \| Krea 2" | 4 versions; bf16/fp8/int8/nvfp4 as *files* inside a version |
| 2726029 "Krea 2 Turbo Official Comfy-Org" | 6 versions, one file and one precision each |

---

## 4. The recommendation

Owner's decision: **always ask, recommend one.** `recommend_across_variants` marks exactly one row
for the whole model and never applies it.

Computed per version it marked **6 of 6** rows on model 2726029 — every version held one file, so
every file was the best in its version. A star on every row is a star that says nothing while
looking like guidance.

Ranked in this order:

1. **it fits** — `_fitting`, budget 80% of reported VRAM, because a checkpoint needs headroom
   beyond its own size for activations and the VAE decode. Nothing fitting is answered with the
   smallest, not with nothing;
2. **the largest**, because within one model more bytes is more precision;
3. **the version the author put first**, among candidates within 5% of the largest. Size alone
   crossed a version boundary to spend 0.32 GB on an older model. This is the author's *ordering* as
   the API returns it, not an inference from version ids — those are not monotonic on either model
   measured.

Measured after: one row marked at every budget, and the mark tracks the card (32 GB → bf16
24.48 GB; 16 GB → the 8-bit tier; 12 GB → nvfp4 7.15 GB).

### Why size and not `metadata.fp`

`fp` is typed by an uploader and it is wrong often enough to matter. On 2726029 the version
`krea2_turbo_int8_convrot` declares `bf16` at 12.57 GB against a 24.48 GB genuine bf16. Ranking on
the label promoted an int8 checkpoint to "the highest precision available".

Ranking on size also removes the VAE bug *structurally* rather than by a guard: a companion is the
smallest file present, so largest-that-fits can never surface it.

### Disputed precisions

`precision_disputes` reports a declared precision that contradicts its measured size — **within one
version, across files sharing one filename**, and nowhere else.

The scope was set by measurement, not assumption. Across a model's *versions* the same code flagged
**121 of 1101 candidates (11%)** over the 100 most-downloaded Civitai checkpoints: a model's
versions span different architectures and parameter counts (Pony Diffusion V6 XL carries a 1.99 GB
file and a 6.46 GB file, both honestly fp16), so a size ratio between them measures the
architecture. Within one version it flags **3 of 1101 (0.27%)**, and those are real — LUSTIFY's
"v10 (Krea 2)" publishes one filename at 24.48 GB and at 12.25 GB with every row declared `bf16`.

Two more of the original five survivors came from folding `fp32` into the 16-bit class, which made
every honest fp16-alongside-fp32 SD1.5 pair look like a mislabel. `fp32` is 32.

Three states, as always. A majority of the version's files must agree on a reading, or nothing is
reported: two files that contradict each other are a tie, and nothing says which one is wrong.

**The stated cost:** a model publishing one precision per version has nothing to compare within a
version, so 2726029's real mislabel goes unreported. "Cannot tell" is the honest answer there, and
it is better than a check that fires on 11% of correct data.

A disputed row is excluded from the recommendation and **still offered**, marked, with the
measurement in its tooltip. It may be exactly the file the user wants; hiding it would be the
silent substitution this module exists to prevent.

---

## 5. Getting the bytes, and proving they are the right bytes

`materialize_asset` → `_download_remote_asset`.

The size checks were already thorough — Content-Length against the provider's declared size, bytes
written against Content-Length, declared size within 1% — but every one of them is a **plausibility**
check. They all pass for any file of roughly the right length, and receiving a *different artifact*
of the right length is the exact failure this area is shaped around.

So the transfer now hashes its own chunks and compares against the provider's SHA256. Hashed as the
bytes arrive, not by re-reading afterwards: these files reach 24 GB, and a second full read would
roughly double the wall-clock cost of every download. A mismatch raises, and the existing handler
discards the partial — so nothing is left for a later run to treat as a cache hit.

Two details decide whether this helps or hurts:

- **The digest must belong to the file being fetched.** `_pick_primary_civitai_file` honours an
  explicit `?fileId=`, because a version's primary file is frequently not the one being downloaded.
  An unknown `fileId` returns nothing rather than falling back to the primary: better no digest
  than the wrong one, since a wrong digest refuses a perfectly good download.
- **The common path had to be covered.** The variant dialog hands back the chosen file's own
  `downloadUrl`, which parses as `civitai_download_url` — the one path with no digest attached.
  `_civitai_file_behind_download_url` looks it up, matching on `?fileId=` or on the
  `type`/`format`/`size`/`fp` selectors Civitai puts in its own links.

Unverifiable is a state, not a failure: an unreachable API, several files matching equally, or a
provider that publishes no hash all proceed and are reported as `metadata["sha256_verified"] =
False`. Refusing would break every Hugging Face and direct-URL download.

Verified live against model 2823011: all eight per-precision URLs the dialog produces resolve to the
correct digest, including the three files sharing one filename inside "V2.0 Quants" — where a wrong
match would have been invisible.

### There is no hash *tier*

Two comments used to promise one. There is none, and there cannot be one from workflow data:
measured across the **415 workflows** in the library, not one carries a hash of any kind — no
`sha256`, no `AutoV2`, no `hash` key anywhere in the JSON. `properties.models` declarations carry
exactly `name`, `url` and `directory`. Hashes exist on the provider side and are used there, but
that verifies a file already chosen; it cannot choose one.

The resolution tiers are: **already present → declared URL → the reference is itself a URL/Civitai
id → reported for review.** Never guessed at, never substituted.

---

## 6. Where a workflow ends up if it is pasted into the model box

`model_import.dest_subdir` matched substrings of the filename, so *"Krea2 Two Image Edit v1.2.json"*
hit the `krea2` rule and was copied into `models/diffusion_models/`, where it later appeared as
garbage in ComfyUI's loader lists. A workflow is named after the model it drives, so this is normal
use, not an edge case.

Non-model suffixes are now checked **before** any family token, and route to a `workflows` subdir —
inert and obvious if one ever slips past the caller, which is expected to send it to the workflow
importer instead.

---

## 7. What is deliberately not built

- **`extra.anomalous_hashes`.** The plan expected to read it. Measured: absent from all 415
  workflows in the library. Building a reader for a field no artifact carries is speculation.
- **Model-weight hashing on disk.** Nothing hashes local files, and nothing needs to: the reference
  identifies a model by name, and no workflow carries a digest to match it against.
- **`sd3` sampler allowlist.** SD3 is flow-matching, so copying `dpmpp_2m`/`karras` would be wrong,
  and there is no SD3 checkpoint on this box to validate against. Left unfilled on purpose.
