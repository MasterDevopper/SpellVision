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

**Also flagged by the new core, and a genuine decision:** v0.34.0 warns
`You need pytorch with cu130 or higher to use optimized CUDA operations`. We are on cu128. Doc 25 §7
says a torch move is "its own decision, not silent" — so it is recorded here, not taken.

**Install gotcha that produced a false alarm:** installing pack requirements with a blanket
`--no-deps` dropped `wcwidth`, `pyparsing` and matplotlib's `fonttools`/`kiwisolver`/
`python-dateutil`. Three packs then failed to import and the drift report blamed the *core* for six
missing node classes — three of which were purely the install error. Use a pip **constraints file**
pinning the torch stack instead; everything else resolves normally.

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
