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
required. That needs a live `/object_info` from the target core, which means S1's isolated venv —
so it stays part of S3, not a shortcut around it.

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
