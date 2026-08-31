# ComfyUI node-contract baselines

Doc 25 S0/S2 artifacts. These exist so a core bump can be pre-screened for node-API drift
*before* burning render time on the S3 regression matrix.

## What is pinned

`node_contract_<core-sha>.json` records only the node classes SpellVision actually names — in
`python/video_templates/*.json` and in any `"class_type"` literal under `python/` — not the whole
`/object_info` dump. For each: whether the core provides it, its input names, whether each input is
required or optional, and the input's *type shape*.

Enum inputs are recorded as `ENUM[n]`, not their contents. A checkpoint list changes every time a
file lands on disk; that is not API drift and would bury the real signal.

| file | core | captured |
|---|---|---|
| `node_contract_206b9245.json` | `206b9245` (v0.27.0-46, Jul-10) — the live core | 2026-08-26 |

Regenerate against a running instance:

```
curl -s http://127.0.0.1:8188/object_info -o oi.json
python pin_node_contract.py oi.json "<label>" docs/pipeline/comfy_baselines/node_contract_<sha>.json
```

## Target pre-screen (2026-08-26)

Screened statically against shallow clones of each candidate tag, without standing up an isolated
venv. Live core is `206b9245` (v0.27.0-46); upstream's latest release is **v0.34.0**.

| target | core nodes | removed/renamed that we depend on |
|---|---|---|
| `v0.33.1` (`72865f4`) | ~1063 | **none** |
| `v0.33.4` | ~1074 | **none** |
| `v0.34.0` | ~1116 | **none** |

- **72** node classes depended on: **57** from core, **15** from custom packs — the split is the
  same at all three targets.
- **Class-level graph-breaking drift is ruled out for every candidate**, so the target choice is not
  constrained by node removals. `v0.34.0` is a superset; `v0.33.4` is the conservative pick if a
  settled patch release is preferred.
- The 15 custom-pack classes are unaffected by a *core* bump and must be re-verified against the
  packs themselves: `ClownSampler_Beta` (RES4LYF); `HyVideo*` + `DownloadAndLoadHyVideoTextEncoder`
  (kijai HunyuanVideoWrapper); `LTXFloatToInt`, `LTXVImgToVideoConditionOnly`,
  `LTXVTiledVAEDecode`, `GuiderParameters`, `MultimodalGuider` (LTX pack).

**What this does NOT cover:** a node keeping its name while an input is renamed, re-typed, or made
required, nor a pack importing a core-internal Python symbol. Both need a live target — see below.

## S2 against a live v0.34.0 (2026-08-26)

Parallel instance stood up on :8189 via `scripts/dev/setup_comfy_next.ps1` (core `12d5279`, packs
pinned to the live SHAs so the core is the only variable). Live install on :8188 untouched.

**The one real blocker, and its fix.** `ComfyUI-LTXVideo` @ `aceeae9` fails to import on v0.34.0:

```
ImportError: cannot import name 'interleaved_freqs_cis' from 'comfy.ldm.lightricks.model'
```

The symbol exists in the Jul core and is **gone** in v0.34.0. The pack dies entirely, taking
`GuiderParameters`, `LTXFloatToInt`, `LTXVImgToVideoConditionOnly`, `LTXVTiledVAEDecode` and
`MultimodalGuider` with it — and LTX is the production video path. **The static class-level
pre-screen cannot see this**: it is a core-*internal* Python symbol, not a node class.

Upstream already fixes it — `548a393 "Support core rope change"`. Updating the pack to `15d09ab`
(2026-08-20) clears it: **node_removed drops to zero, 1463 classes loaded.**

So the bump is: **core v0.34.0 + ComfyUI-LTXVideo ≥ `15d09ab`.** The other five packs are fine at
their current SHAs.

**Remaining drift is 7 `input_retyped`, none requiring a template change:**

| finding | verdict |
|---|---|
| `CreateVideo.bit_depth` INT→COMBO | neither template sets it |
| `SaveVideo.codec` / `.format` COMBO→`COMFY_DYNAMICCOMBO_V3` | only `ltx_av_native` sets them (`auto`/`auto`), still valid; the default two-stage route sets neither |
| `LTXVEmptyLatentAudio.frame_rate` INT→FLOAT,INT | widened, and we pass a link not a literal |
| `CLIPLoader.type` ENUM[25]→[28] | more options |
| `CheckpointLoaderSimple.ckpt_name`, `LoadImage.image` | file/dir listings, environmental not API |

### S3 render matrix on v0.34.0 (2026-08-26)

Built with our production builders against the target's own `/object_info`, submitted there, and
required to produce a real file.

| row | result |
|---|---|
| LTX t2v (two-stage) | **PASS** 150.1s — 1536×1024×97f AV, frames verified |
| Wan t2v | **PASS** 35.0s |
| Hunyuan t2v | **PASS** 30.0s |
| Mochi t2v | **PASS** 30.3s |
| Krea2 image | **PASS** 100.1s |
| Anima image | **PASS** 8.0s |
| Flux image | **FAILS — but PRE-EXISTING**, see below |
| Diffusers SDXL t2i/i2i | **N/A** — runs in the worker's own venv via diffusers, never touches ComfyUI |
| LTX i2v | **PASS** 95.1s — 1280×960×49f, keyframe-conditioned |
| Wan i2v | **PASS** 35.0s |
| Hunyuan i2v | blocked — no kijai-format model on disk; the builder's own guard fires at BUILD time, before ComfyUI is touched, so it cannot be core-related |
| LTX long frames (193f) | **PASS** 130.1s — 1280×960×193f |
| Wan long frames (81f) | **PASS** 85.1s |
| Pixart / Lumina / Z-Image images | **PASS** 10.0 / 10.0 / 15.0s |
| Imported-workflow launches | **no bump impact** — see below |

**Imported workflows: identical on both cores.** All 81 run through the real UI-graph→API converter
against each core's own `/object_info`: **45/81 convertible, 36/81 blocked — same count, same
blocked list, on Jul core and v0.34.0 alike.** Six launched end-to-end; every failure reproduced
exactly on the live core.

One of those looked like a genuine regression and was not: `minimal-wan-json` fails with
`Required input is missing: codec` / `could not convert 'vp9' to FLOAT`, which matches the
`SaveVideo` COMBO→`COMFY_DYNAMICCOMBO_V3` drift the contract diff flagged. It reproduces
byte-identically on the Jul core — a pre-existing converter/widget misalignment.

**Separate finding, not bump-related: 36 of 81 Flows entries cannot launch on either core**, blocked
by custom node packs that were never installed. Ranked by workflows blocked: `VHS_VideoCombine` (12),
rgthree (11), IPAdapter (10), easy-use (10), KJNodes (8), then `UltimateSDUpscale`,
`UnetLoaderGGUF`, Florence2 (5 each). Installing VHS + rgthree + IPAdapter alone would unblock ~25
of the 36.

**No shipped long-video path exists.** Doc 24 is design-only; there is no `duration_layer` code. The
"long" rows above are long FRAME COUNTS through the normal builders — the closest real proxy — not a
product feature under test.

**Model names must come from the live loader catalog, not memory.** Guessed filenames produced
build failures for anima, pixart and z_image that all read as family breakage; every one passed once
the name was taken from `/object_info`.

**Flux is not a bump regression.** `flux\fluxmania_legacy.safetensors` fails with
`Could not detect model type` on **both** cores — confirmed by submitting the identical minimal
`CheckpointLoaderSimple` graph to `:8188` (Jul core) and `:8189` (v0.34.0) and getting the same
failure. Confirm this rather than inheriting it: a pre-existing failure discovered *during* a bump
looks exactly like a regression caused by it.

**Two failures in the first image sweep were the harness, not the core** — worth recording because
both would have read as bump regressions: `anima` was pointed at the similarly-named `sdxl`
checkpoint instead of its `diffusion_models` UNET (`anima\anima-base-v1.0.safetensors`), and the
first video sweep named no model at all. Always re-check a "the new core broke X" result against
the old core before believing it.

**Also flagged by the new core, and a genuine decision:** v0.34.0 warns
`You need pytorch with cu130 or higher to use optimized CUDA operations`. We are on cu128. Doc 25 §7
says a torch move is "its own decision, not silent" — so it is recorded here, not taken.

**Install gotcha that produced a false alarm:** installing pack requirements with a blanket
`--no-deps` dropped `wcwidth`, `pyparsing` and matplotlib's `fonttools`/`kiwisolver`/
`python-dateutil`. Three packs then failed to import and the drift report blamed the *core* for six
missing node classes — three of which were purely the install error. Use a pip **constraints file**
pinning the torch stack instead; everything else resolves normally.

## S3 RE-RUN against the staged instance (2026-08-31)

The 2026-08-26 matrix passed with node packs pinned to the **live SHAs, so the core was the only
variable**. Since then **23 packs have been installed into `C:\sv_comfynext_v034`** — the instance
now carries 29 packs against the live install's 6. So the thing that passed the matrix was no longer
the thing a cutover would move to, and the matrix was re-run.

**Result: the bump still holds. Three things were found, and one of them is a real fix.**

### The tooling broke before the core did

`comfy_node_contract.py` — the tool whose entire job is to pre-screen a core bump — died with
`ConnectionResetError` on the first bump it was pointed at. It fetched `/object_info` through
`urllib`, which always sends `Connection: close`, against a 6.76MB body. **The transport fix from
2026-08-27 had been applied to `comfy_prompt_client` and to nothing else.** Two more sites had it:

| site | shape |
|---|---|
| `video_family_readiness.py` | bare `urlopen` inside `except Exception: return {}` — the reset became an EMPTY object_info, so every node looks absent and **every family reports NOT READY, silently** |
| `flows_health.py` | `urlopen` still passing `Connection: close` **explicitly**, retried five times around a request guaranteed to fail |

All three now route through the shared reader, and sweep rule `object-info-through-one-transport`
stops a fourth appearing. The readiness one would have hit precisely at cutover and would have read
as "the new core broke every family."

### Contract diff — clean

Against the pinned `206b9245` contract, on the staged instance: **no `node_removed`, no
`input_removed`, no `input_now_required`.** Six `input_retyped`, all already assessed above as
requiring no template change. Exit code 0 — the CI gate passes.

### The 23 new packs do not shadow anything

All **72** classes SpellVision names are present, and their provenance comes from the server's own
`python_module` field rather than a source scan: **57 from core, 15 from our own six packs** —
exactly the split recorded in the pre-screen. **Zero classes are provided by any of the 23 new
packs.**

*A scan that read the packs' `NODE_CLASS_MAPPINGS` instead returned "0 classes, no shadowing" for
every pack — a false clean.* `core_node_drift.mapping_keys()` skips any path containing
`custom_nodes`, so pointing it INTO `custom_nodes` filters everything out. That is the same
zero-nodes trap this README already warns about, met from a new direction. Prefer `python_module`
from a live `/object_info`; it is authoritative and cannot be filtered away by accident.

### One pack does not survive the bump

`ComfyUI-MagCache` **fails to import on v0.34.0**:

```
ImportError: cannot import name 'precompute_freqs_cis' from 'comfy.ldm.lightricks.model'
```

The same class of failure as the LTXVideo blocker — a core-internal Lightricks symbol removed in
v0.34.0 — and again invisible to a class-level pre-screen. **Not a blocker:** SpellVision names no
MagCache class, so the pack is inert noise rather than a broken dependency. It needs an upstream
version that supports the core rope change, or removal.

`ComfyUI-KJNodes` also loses one node, `PatchTritonVAE`, for want of `triton`. See the venv gap.

### The staged venv is not the live venv

| package | live | staged |
|---|---|---|
| `sageattention` | **1.0.6** | **missing** |
| `triton-windows` | **3.7.1.post27** | **missing** |
| `kornia` | 0.8.2 | 0.8.2 |
| `torch` | 2.10.0+cu128 | 2.10.0+cu128 |

Cutting over as it stands **loses SageAttention**, which is a measured +25% on video. Install both
into the staged venv before the flip. Worth noting that nothing would crash: `comfy_launch_policy`
refuses to pass `--use-sage-attention` to an interpreter without the package, so the app would
quietly run sdpa — a capability regression, reported rather than fatal.

### Renders

| row | result |
|---|---|
| LTX t2v two-stage, 768×512×49f | **PASS** 75.3s — the production video path, on the bumped pack |
| Krea2 image, 1024×1024 | **PASS** 48.1s |
| Wan t2v dual-noise, 640×480×33f | **PASS** 30.1s — VAE resolved to `wan_2.1_vae` (16-ch), the `force_version` guard behaving |

**And one failure that was not one.** A Wan request built from a bare single high-noise expert — no
stack, no `force_version` — failed at `VAEDecode` with `Expected tensor to have size 48 at dimension
1, but got size 16`: the filename probe picked the 48-channel `wan2.2_vae` for a model emitting
16-channel latents. Submitted to **both** cores, it fails **byte-identically on the live core**, so
it is not a bump regression. It is a request shape the cockpit does not produce, and the guard that
corrects it is exactly the one the production dual-noise path carries. Recorded because it is a
latent trap for any future caller that omits `force_version`, and because the S3 rule earned it:
*a pre-existing failure discovered during a bump looks exactly like one caused by it.*

### Both pre-flip items closed (2026-08-31)

**`sageattention` 1.0.6 + `triton-windows` 3.7.1.post27 installed into the staged venv**, matching
the live install exactly, under a constraints file pinning `torch`/`torchvision`/`torchaudio`/
`kornia` so nothing pulled in as a dependency could move them. Verified after: torch still
`2.10.0+cu128`, torchvision `0.25.0+cu128`, kornia `0.8.2`; both new packages import.

`comfy_launch_policy.resolve_attention_backend()` now returns **`sage`** for the staged interpreter,
same as live, so a cutover launches with `--use-sage-attention` rather than silently degrading.

**The setup script was the real fix.** `setup_comfy_next.ps1` builds the staged venv and did not
install either package, so rebuilding the instance would have reproduced the gap. It installs both
now, under the same constraints file it already used for pack requirements, and reports their
versions next to the torch line at the end — a MISSING there says in words that sage will not be
offered. Fixing the instance without fixing its generator is the site-not-the-tree mistake.

**`ComfyUI-MagCache` removed from the staged instance** — *moved* to
`C:\sv_comfynext_v034\_removed_packs\ComfyUI-MagCache_47bdd2a`, not deleted, so it is reversible.

Upstream is a dead end, not a pending update: `47bdd2a` (2025-11-27) **is** the tip of
`origin/main`, so there is no release supporting the v0.34.0 core rope change and the repo has been
untouched for nine months. Four imported workflows carry live `MagCache` nodes
(`img-to-video-base`, `-base-speed`, `-gguf`, `-gguf-speed`, two nodes each, `mode: 0`), so they do
depend on it — but **the live install has never had MagCache at all**, so those four already sit in
the blocked-36 today. Removing a pack that cannot import changes nothing except that boot stops
reporting a failure, and a dead import no longer sits there to mask a real one later.

### Re-verified after both changes

Relaunched with the exact arguments the launch policy produces (`--use-sage-attention`, plus
`PYTHONUTF8`/`PYTHONIOENCODING`), **seed varied to defeat ComfyUI's node cache**:

| row | result |
|---|---|
| import failures at boot | **zero** (was 1: MagCache) |
| `Using sage attention` in the log | confirmed |
| LTX t2v two-stage 768×512×49f | **PASS** 84.2s |
| Krea2 image 1024×1024 | **PASS** 48.1s |
| Wan dual-noise t2v 640×480×33f | **PASS** 33.1s, VAE `wan_2.1_vae` |

**These timings are not a speed claim in either direction.** The sage and non-sage runs had
different model-load state, which is exactly the trap the FP8 measurement recorded: a re-submit that
changes only the output filename gets the node cache, and a cold load is not comparable to a warm
one. Measuring SageAttention's +25% properly needs matched load state and is a separate exercise.
What these rows establish is that **sage does not break any production path**, which is what a
cutover needs to know.

### Verdict

**The bump is re-confirmed on the instance as it actually stands, with both pre-flip items closed.**
The staged venv now matches live, the staged instance boots clean, and all three production render
paths pass with sage engaged.

Remaining, unchanged and still not taken: v0.34.0 warns `You need pytorch with cu130 or higher to
use optimized CUDA operations` and we are on cu128. Doc 25 §7 says a torch move is its own decision.

Also noted, not acted on: `rgthree-comfy` warns that ComfyUI's Node 2.0 canvas rendering may break
some of its nodes. That is a ComfyUI **web-canvas** concern; SpellVision submits API graphs and never
opens that canvas, so it does not affect the cutover.

---

## Runtime layer: detect, then absorb

Two modules, deliberately separate — detection can be broad and noisy, conversion must be narrow
and confirmed.

**`python/comfy_node_contract.py` — what changed.** Diffs a pinned contract against a live
`/object_info`, over the classes we actually name. Findings are typed and ordered worst-first:
`node_removed`, `input_removed`, `input_now_required`, `input_retyped`, `node_added`. Run it after
any ComfyUI update, before trusting a render:

```
python python/comfy_node_contract.py docs/pipeline/comfy_baselines/node_contract_206b9245.json --candidates
```

Exit code is non-zero only on drift that will actually reject a graph, so it works as a CI gate.
`--candidates` proposes replacements for removed nodes, ranked by identical output types plus
name-token overlap. **Report only.**

**`python/comfy_node_aliases.py` + `.json` — absorbing it.** A curated rename map applied to the
finished graph immediately before submission, on both submit paths: the `comfy_workflow` launch
path ([comfy_prompt_client.py](../../../python/comfy_prompt_client.py)) and the native-video path
([native_video_graphs.py](../../../python/native_video_graphs.py)). Builders keep naming the
identity they were grounded on; the map translates to whatever the live core calls it.

This is deliberately the same shape as `_resolve_graph_model_names`, which already rewrites model
*file* names against the live catalog for the same reason. Node and input identity is that problem
one level up, at the same seam.

**Every rewrite is validated against the live schema.** A class rename is taken only when the old
name is genuinely gone *and* the replacement genuinely exists; an input rename only when the target
input is genuinely in that class's schema. So a stale alias entry is inert rather than destructive,
and the pass is a complete no-op on a core that still defines what the builder named.

**Why renames are never auto-applied from a guess:** a wrong rename converts a loud `/prompt`
rejection into a silent wrong render. Graphs that submit successfully but produce garbage are this
codebase's most expensive failure mode — the LTX prefix bug, the Wan VAE version mismatch, the
`ltx-2.3-22b-dev` hardlink decoy. Candidates stay in a report until a human promotes them, ideally
after a confirming render.

Unresolvable classes now fail with the node named ("ComfyUI does not provide these node classes:
X") instead of a generic validation error that does not say which node.

**Custom packs are the harder half** — 15 of our 72 classes, versioning independently with no
release discipline. Same contract diff applies per pack; each is a git repo, so pin SHAs.

**Extraction gotcha worth keeping:** modern core registers nodes through the **V3 schema** —
`class Foo(io.ComfyNode)` declaring `node_id="Foo"` in `define_schema()`, collected by an extension
class list. Nothing named `NODE_CLASS_MAPPINGS` appears. Keying only on that name found 344 of
~1063 nodes and wrongly classified core nodes such as `BasicGuider` and `KSamplerSelect` as
custom-pack. Any scanner over this tree must match both registration styles, and `custom_nodes/`
must be excluded when deciding what "core" provides.

**Second guard, learned the same way:** a wrong or missing target path yields zero nodes, which then
reports *every* depended-on class as removed — a terrifying and entirely false result that would
scare someone off a healthy bump. `core_node_drift.py` now refuses to report drift from a tree
defining fewer than 200 nodes, since a real core defines ~1000+.
