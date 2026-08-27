# 46 — Workflow dependency resolution: how it works, and what it cost to learn

**Status:** node packs and declared models shipped; model search / substitution and streamed
progress remain. **Branch:** `wave/rebuild-and-audit-fixes`.

SpellVision's promise is ComfyUI's power without node graphs. A workflow downloaded from Civitai is
the sharpest test of that promise, and until this pass it mostly failed — quietly, and often while
reporting success. This document is the operating manual for the machinery that replaced it, and the
record of what measurement changed about the design.

---

## 1. The governing rule

> Never guess, never silently substitute, and never let "we could not check" render as "fine".

Every defect found in this area had the same shape: **the dangerous failures reported success.** Not
one of them raised. A resolver that installed the wrong pack 33 times reported full coverage. A
converter that dropped every widget value produced a well-formed graph. A readiness check that had
never run reported *Ready*. So the design rule is not "be correct" — it is "be unable to look
correct while being wrong."

Three states, everywhere, never two:

| state | meaning | how it must render |
|---|---|---|
| resolved | verified against real data | the answer |
| unresolved | checked, and there is no answer | the reason, and what would produce one |
| unknown | **not checked** — offline, no index, no schema | visibly distinct from both |

Collapsing `unknown` into either of the others is the bug this codebase keeps rediscovering.

---

## 2. How node-pack resolution operates

**The unlock:** a ComfyUI workflow already names its own dependencies. Every node ComfyUI saves
carries the pack it came from:

```json
"properties": {
  "cnr_id": "comfyui-easy-use",
  "aux_id": "yolain/ComfyUI-Easy-Use",
  "ver": "717092a3ceb51c474b5b3f77fc188979f0db9d67"
}
```

Measured on the 81-workflow library: 431 non-core nodes carry all three, 257 carry `cnr_id` + `ver`,
14 carry `aux_id` + `ver`, 435 carry nothing. So for the common case the class→pack question is
answered *inside the file*, and `ver` is a pin — a commit sha when `aux_id` is present, a Registry
semver otherwise.

### The tiers (`python/workflow_pack_resolver.py`)

| tier | source | network | gives |
|---|---|---|---|
| 1 | `aux_id` → `github.com/{owner}/{repo}` | none | repo + exact pin |
| 2 | `cnr_id` → `api.comfy.org/nodes/{id}` | one GET, disk-cached | repo, licence, downloads, version |
| 3 | `ClassPackIndex` reverse index | none (pure lookup) | pack for a class that declares nothing |
| — | otherwise | — | reported undeclared, with a reason |

`build_node_install_plan` runs these ahead of the starter-catalog name match, which now only sees
classes nothing else could answer.

### Licence is disclosed, never a gate

`is_auto_installable()` looked like the right gate and is the wrong one. Verified live:
`comfyui-kjnodes`, `comfyui-videohelpersuite`, `rgthree-comfy` and `comfyui-easy-use` all publish
`license: {"file": "LICENSE"}`, which normalises to `UNKNOWN` → `auto_installable = False`. Those are
exactly the packs that unblock most workflows. Gating the install button on that predicate would make
the feature useless while looking rigorous.

So the plan carries pack id, repo, licence (including `UNKNOWN`, and real values like `AGPL-3.0-only`
where the Registry has them) and download count, and `requires_confirmation` is always true. The
user's informed click is the authorisation. `is_auto_installable` stays reserved for a future
unattended "don't ask me again" toggle — which is what its own docstring always said.

### Installing (`python/node_pack_installer.py`)

- **No git.** `git clone` was a hidden hard dependency and nothing in `CMakeLists.txt` ships git; on
  an MSI machine the install simply fails. GitHub serves any ref as a zip, which also pins it.
- **Pinned.** The workflow's own `ver` is preferred over the Registry's latest — it is the revision
  that produced this graph. A Registry semver is tried as both `1.5.0` and `v1.5.0`; if neither
  exists the default branch is used and the result is reported as **not pinned**, because that is a
  different promise.
- **Torch cannot move.** A pack's `requirements.txt` routinely names a different torch, which breaks
  every generation family at once. `--no-deps` is too blunt (it dropped `wcwidth`, `pyparsing` and
  matplotlib's transitive deps, and the packs then failed to import in a way that looked exactly
  like a core incompatibility — `bf3c1af`). Requirements install under a **constraints file** read
  from the target interpreter, and the versions are re-read afterwards: a move fails the install
  loudly. Files on disk is not success when the stack shifted.
- **The archive is hostile input.** https and GitHub only; every member must resolve inside the
  destination (zip-slip); symlink members refused; size-capped; staged in a temp dir so a failure
  leaves nothing behind and a replace can roll back.

### Measured result

| | before | after |
|---|---|---|
| blocking classes across the library | 46 | 40 (display-name tier removed 6) |
| classes resolving to a pack + repo URL | 0 (or wrong) | 34 |
| blocked workflows fully covered | 0 | 13 of 16 |
| install actions for `mmaudio-json` | — | 2 packs for 4 classes, both commit-pinned |

The 6 that remain are reported with a reason: 3 are node *titles* rather than class names, 2 are
KJNodes classes newer than the last version the Registry extracted, and `CR Upscale Image` belongs to
a Registry pack with **zero published versions** — which has no node set to read, ever.

End-to-end gate, run for real: `mmaudio-json` → `ComfyUI-VFI` resolved from `aux_id` → installed at
commit `6176a430` into the parallel instance → `RIFEInterpolation` registers → torch still
`2.10.0+cu128` despite the pack's `requirements.txt` naming `torch>=2.0.0`.

---

## 3. How model resolution operates

Same insight, smaller coverage. Loader nodes can carry:

```json
"properties": {"models": [{"name": "wan_2.1_vae.safetensors",
                           "url": "https://huggingface.co/.../wan_2.1_vae.safetensors",
                           "directory": "vae"}]}
```

7 of 80 workflows, 20 declarations, all three fields on every one. An exact URL *and* a destination.

Order, stopping at the first that answers:

0. **Present locally** — `extra_model_paths.yaml`-aware, unchanged.
1. **Declared URL** — this tier. Nothing is inferred, so it goes first.
2. **The reference is itself a URL / Civitai id** — materialise it.
3. **Otherwise** — reported for review, never guessed.

The declared `directory` beats the one derived from the node class: a `CLIPLoader` declaring
`text_encoders` must not land in `models/clip`. The declaration is untrusted input from a downloaded
file, so the URL must be https and the directory must be one plain path component.

**The dead end that blocked the rest of the ladder:** `parse_asset_reference` classified a bare
`foo.safetensors` as `local_file` with an absolute path to a file that does not exist, so
`install_action` could only ever be `"review"` — for the single most common way a workflow names a
model. It is now `kind="model_name"`, which the later tiers can act on, and the plan says *"the
workflow names this model but gives no source"* instead of claiming a path that was never real.

**Still to build:** hash/AIR exact identity, name search with a picker, and architecture-compatible
substitution (Doc 45). All of them depend on `model_name` existing as a state.

---

## 3b. Importing from a link

The dialog was local-file only, so the actual user story — "I found this on Civitai" — had no front
door. Two forms are accepted, because those are the two a shared workflow really takes: a **JSON
document** (Civitai attachment, GitHub/gist raw, Hugging Face) and an **image carrying the graph in
its metadata**. GitHub `/blob/` page URLs are rewritten to raw, and the rewrite is reported rather
than done silently. Image extraction reuses `workflow_scanner._extract_embedded_workflow`.

`SecureCredentialStore` had **no read-back API at all** — it could write a secret and check presence,
but nothing could retrieve one. The Civitai key a user saved in Settings was unusable by
construction, so a link needing auth failed with a 401 the app already had the answer to.

This downloads and parses attacker-influenceable input, and is treated that way:

| property | why |
|---|---|
| https only, explicit host allowlist | a fetcher that follows any pasted URL is an SSRF primitive aimed at the user's LAN |
| redirects re-checked against the allowlist | checking only the first hop checks nothing |
| Civitai token stripped when a redirect leaves civitai.com | a token must not follow a redirect to another host |
| size cap on `Content-Length` **and** while streaming | the header can lie |
| payload must look like a UI graph or an API prompt | "it downloaded" is not "it is a workflow" — a JSON error page parses fine |

## 3c. Building the reverse index from the app

Tier 3 shipped with no way to trigger it: the worker command existed and had no caller, so the tier
was dead for anyone not running Python by hand. Runtime now shows the index state and a build button
that runs **budget-bounded slices** (45s each) instead of one long call, so the count climbs while it
works and a stall shows up as a slice that does not return rather than a frozen page. Stop keeps the
progress — verified: two 12s slices took it 0 → 142 → 294 of 5340 packs.

## 4. Display names are not missing nodes

Hand-written and LLM-generated graphs put the human-readable name in `node.type`. On
`wangpt-optimized-json`, **six of nine** "missing custom node" classes were core nodes under their
display names — `Load Diffusion Model` (`UNETLoader`), `VAE Decode`, `KSampler (Advanced)`,
`Load CLIP`, `Load VAE`, `Empty HunyuanVideo 1.0 Latent`. Nothing was absent; the workflow could
never convert and Launch stayed disabled with no way to clear it.

`comfy_graph_converter.display_name_aliases()` builds the mapping **from the live `/object_info`**,
so it cannot go stale. Ambiguous names are dropped rather than picked: the live set has 9 display
names shared by two classes (`Int` is both `PrimitiveInt` and `Int-🔬`), and choosing one would
rewire the graph to a node the author did not select.

The converter and the scanner take the same alias set. They have to: detection reporting these as
missing while conversion handles them would disable Launch on a workflow that runs — the same shape
of bug as the 26-name builtin list.

---

## 5. ComfyUI version detection

Both halves of "are you behind?" were already available and being thrown away.

- **Installed:** `/system_stats` → `system.comfyui_version`, fetched in four places with the body
  discarded.
- **Latest:** `api.github.com/repos/**Comfy-Org**/ComfyUI/releases/latest`. No auth, no git.

Two traps:

- **The repo moved.** `comfyanonymous/ComfyUI` 301-redirects. An earlier plan note said to avoid the
  releases API and use `git ls-remote --tags` — wrong twice, because git is not on an MSI machine and
  it invites the second trap.
- **Versions are not strings.** Plain lexical `sort` over the 183 published tags returns **`v0.9.2`**
  as newest; `sort -V` returns `v0.34.1`. Comparison is always a numeric tuple.

The failure direction is deliberate: unreachable GitHub → `unknown`, never `up_to_date`. A stale
cached release beats no answer; a prerelease is never offered.

Runtime shows `ComfyUI 0.27.0 · update available → v0.34.0` and reveals the Update button only in
that state. The button **discloses rather than acts**: Doc 25's rule is absolute — the live install is
never mutated and never `git pull`ed — so an update is built as a parallel instance on its own port,
packs pinned to what is installed now, isolated venv, drift-checked and smoke-rendered, and only then
cut over, which keeps rollback at "stop using the new port". Driving that from inside the app needs
streamed progress, so for now the dialog states the procedure, links the release notes and hands over
the `setup_comfy_next.ps1` command.

---

## 6. The `/object_info` reset: a fix that was the bug

Worth its own section, because it inverted an existing "hard-won lesson".

The recorded lesson was: *the ~2MB `/object_info` body resets mid-read, so send `Connection: close`
and retry.* Measured against core v0.34.0 on `:8189` (6.76MB body), requests otherwise identical:

| request | result |
|---|---|
| bare | 3 of 3 succeeded |
| `Accept-Encoding: identity` | 3 of 3 succeeded |
| `Accept-Encoding: gzip` | 3 of 3 succeeded |
| **`Connection: close`** (± gzip) | **3 of 3 `ConnectionResetError`** |

The header added *as the fix* is the cause. The server tears the socket down at its end before the
body is flushed. The old core on `:8188` (2.4MB) tolerated it, which is why it read as "one run in
three" flakiness rather than a header bug — and why the response was retries instead of a different
client.

**And deleting the explicit header changes nothing**: `urllib` always sends it
(`AbstractHTTPHandler.do_open` puts it unconditionally). No `urlopen`-based fetch can avoid it. The
fix is `http.client`.

Effect: `_fetch_comfy_object_info` went from 3 of 3 failures after burning the full 120s retry budget
on `:8189`, to 8 of 8 successes under 0.6s across both cores. One test went **20.9s → 0.12s**.

---

## 6b. A prompt is not evidence about the task

The classifier read node *text* — which concatenates the class name, the title, the input names **and
the input values**, i.e. the user's prompt — and matched bare substrings against it. Reproduced on a
plain SDXL text-to-image graph (CheckpointLoaderSimple → CLIPTextEncode → EmptyLatentImage →
KSampler → VAEDecode → SaveImage):

| prompt | before | after |
|---|---|---|
| "a portrait of a woman, studio lighting" | t2i / image 0.90 | t2i / image 0.90 |
| "a **swan** gliding on a still lake" | **t2v / video 0.99** | t2i / image 0.90 |
| "a **wandering** knight" | **t2v / video 0.99** | t2i / image 0.90 |
| "a night market in **Taiwan**" | **t2v / video 0.99** | t2i / image 0.90 |
| "a plate of **mochi** dessert" | **t2v / video 0.99** | t2i / image 0.90 |

`image_output` was sitting in the evidence list of every one of those verdicts. `primary_task` drives
the launch type and the output file extension, so those would have been submitted as video jobs.

Four fixes: match the **class name** and the **schema input names**, never the values; match whole
words split with camelCase awareness (so `wan` hits `WanImageToVideo` and not `SwanTransform`); let
the **output nodes decide** — the video core is corroboration and only decides when nothing
contradicts it; and make contradicting evidence **subtract** from confidence. A flat penalty was
tried first and was not enough — it has to cancel the contradicting evidence's own contribution,
which a test caught.

Measuring it turned up a second defect: three t2i workflows had *no detected output at all*, because
they save through `Image Saver` (alexopus/ComfyUI-Image-Saver) rather than core `SaveImage`. Output
detection now matches on words — an image word **and** a save/preview word — so custom savers count
while `LoadImage`, `ImageResizeKJv2` and `Sampler Selector (Image Saver)` do not.

Library effect: 53 image / 28 video → **56 image / 25 video**, no unknowns, and no workflow
classified video while its only output is an image.

## 7. Lessons

**A fix that treats a symptom can become the defect.** The `Connection: close` retry hardening was
correct-looking, documented, and load-bearing — and it caused the failure it described. When a
mitigation is in place and the symptom persists, re-test *without* the mitigation before adding more.

**Measure the heuristic before shipping it.** Tier 3 was first written as "rank packs by name
similarity, then verify against each candidate's real class list". Verification made it honest, but
ranking made it useless: **0 of 16** undeclared classes resolved, because the packs providing
`SetNode`, `LoadImageBatch` and `CR Upscale Image` share no words with those names. Deleted rather
than shipped. A plausible heuristic that has not been measured is a guess with extra steps.

**"0 errors" is not "complete".** The first reverse-index build reported 5340 packs, 20650 classes,
**0 errors** — and contained nothing at all from KJNodes, one of the most-used packs in existence.
`_fetch_pack_classes` walked the 8 newest versions for a non-empty node list; KJNodes publishes 50
and is empty from 1.3.0 up. Emptiness ran newest-first, so a binary search finds the boundary in ~6
probes. Classes 20650 → 23373. **A completion metric that cannot detect an absent input is not a
check.** Spot-check the index for something you know must be in it.

**Estimate, then measure, then re-estimate.** The reverse index was estimated at ~3.7 hours from a
20-pack sample and dismissed as "a background job, not something a dependency check may run". At 6
workers it took **409s**. The conclusion (don't run it inline) survived; the reasoning behind it did
not. Say which number the decision rests on.

**Two lists of the same concept drift.** The UI-only node set, the display-name aliases, the builtin
class list — every one of these exists in two places at some point, and every divergence produces
"detection says missing, conversion says fine", i.e. a disabled Launch button on a working workflow.
Import the set; do not copy it. There is a test whose only job is to assert the two agree.

**Group before you act, and merge after you resolve.** Comfyroll appeared under `cnr_id` on some
nodes and `aux_id` on others. Grouping happens before the Registry answers, so the two only converge
once both have a repo URL — unmerged, that is two clones into one directory. The duplicate-install
failure mode does not go away just because you fixed the resolver that caused it the first time.

**Cache answers, not outages.** A 404 from the Registry is a real answer worth remembering. "Could
not reach the Registry" is not — caching it makes one offline moment look like a missing pack for a
day. Different TTLs, and network failures are never written.

**Read the tool's own source before believing your header.** Two of this pass's findings — urllib
forcing `Connection: close`, and `all([])` being `True` — are stdlib behaviour that looked like
application logic.

**Verify on the thing, not near it.** A pack on disk is not a registered class. The A4 gate was only
met when `RIFEInterpolation` appeared in `NODE_CLASS_MAPPINGS` after a real install — the same
discipline as "gate on pixels-on-surface, not file-exists".

---

## 8. Where it lives

| file | role |
|---|---|
| `python/workflow_pack_resolver.py` | declared-pack tiers, Registry cache, `PackDirectory`, `ClassPackIndex` |
| `python/node_pack_installer.py` | pinned archive install, zip hardening, torch constraints |
| `python/node_dependency_resolver.py` | plan assembly; declared tiers ahead of the starter catalog |
| `python/node_registry_resolver.py` | Registry client; `_fetch_pack_classes` binary-search version walk |
| `python/workflow_model_declarations.py` | `properties.models` extraction and validation |
| `python/model_dependency_resolver.py` | model tiers; `download_declared` |
| `python/comfy_graph_converter.py` | `display_name_aliases`, conversion, `ConversionResult` |
| `python/comfy_version_check.py` | installed-vs-latest, numeric-tuple compare |
| `python/comfy_prompt_client.py` | `_http_get_json` — the non-urllib `/object_info` transport |
| `python/workflow_url_import.py` | link fetch, host allowlist, redirect re-check, shape validation |
| `python/workflow_scanner.py` | capability classification, missing-node tiers, pack identity |
| `qt_ui/ManagerPage.{cpp,h}` | version row, update disclosure, node-index build |
| `qt_ui/shell/SecureCredentialStore.{cpp,h}` | `credential()` — the getter the store never had |

Worker commands added: `build_node_class_index` (resumable, budget-bounded);
`comfy_runtime_status` now carries `version_check`; `import_workflow` accepts a URL as `source`.

Tests: `test_workflow_pack_resolver.py`, `test_node_pack_installer.py`,
`test_workflow_model_declarations.py`, `test_display_name_aliases.py`,
`test_comfy_object_info_transport.py`, `test_comfy_version_check.py`,
`test_workflow_url_import.py`, `test_capability_classification.py`.
Suite: 552 → 644 passed.

---

## 9. Remaining

Two of these are on Doc 28's cut list as **NOT YET DECIDED** rather than silently deferred, because
both are gaps a real user hits and the call is the owner's:

- **Model tiers 2–4** — hash/AIR identity, name search with a picker, architecture-compatible
  substitution (Doc 45). `kind="model_name"` is the state they hang off. Today a workflow naming an
  absent, undeclared model says *"the workflow names this model but gives no source"*: honest, but it
  leaves the user to go find it.
- **Streamed progress** — installs and multi-GB downloads are `subprocess.run`, one blob at the end.
  A large fetch will read as a hang. This is also what blocks driving the guided ComfyUI update from
  inside the app rather than handing over a command.

Not blocked on a decision, just not done:

- **Subgraph node types.** Newer graphs reference a subgraph definition by UUID, so `node.type` is
  something like `161abbcf-b93a-46be-99c4-21b331350999` and it reads as a missing class. Two
  workflows in this library hit it. The definitions are in the file, so this is the same shape of
  fix as the display-name tier: resolve from what the workflow already carries.
- **Node titles.** Three classes in `wangpt-optimized-json` are node *titles* ("CLIP Text Encode
  (Positive Prompt)") rather than display names, so there is nothing to match them against without
  guessing. Left unresolved deliberately.
