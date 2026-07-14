# Doc 23 — Engine Import Contract (as-built) & Engine Roadmap

> **Status:** the missing input. The entire 3D pipeline plan (11b / 11c / 11d) was written
> targeting *generic glTF 2.0 GLB* — but SpellVision's target engine is custom and in
> active development, so it defines its **own** import contract. This document is the
> bridge between what the pipeline emits and what the engine actually loads. Everything
> the 3D plan calls "engine-ready" must be measured against §1 here, **not** against the
> glTF spec.
>
> Source: the developer's engine-import audit. The "dangerous silent fix-ups" (§1.2) and
> "entirely absent" (§1.3) lists are what re-order the 3D plan's priorities — see §2 and
> the corrections folded into 11b §3, 11c §4, and 11d.

---

## 1. As-built import state

### 1.1 What it accepts (works today)
- **Container:** glTF 2.0 — both `.gltf` and `.glb`. Loader is `gltf v1.4`. **No KHR
  extensions are parsed.**
- **Vertex attributes:** `POSITION` (required), `NORMAL`, `TEXCOORD_0`, `TANGENT`.
- **Indices:** `u32`.
- **Images:** decoded to `RGBA8`.
- **Vertex layout:** a fixed **60-byte** vertex.
- **Entry points:** `load_merged` / `load_model`.

This is the contract Track A (static props) can hit **today**: `POSITION` / `NORMAL` /
`TEXCOORD_0` / `TANGENT` + PBR textures.

### 1.2 Dangerous silent fix-ups (these bite the 3D pipeline specifically)
The engine does not reject malformed or underspecified input — it silently "fixes" it,
and several of those fix-ups corrupt generative-3D output **with no error**:

- **Missing normals → a fabricated up-vector.** Flat/wrong shading, no warning.
- **Missing tangents → an arbitrary, non-UV-aligned tangent** ⇒ **normal mapping renders
  WRONG, silently.** The single most damaging one for this pipeline: stage-4 baking
  produces normal maps, so a wrong tangent basis quietly ruins every baked asset (see §2
  Tier 0).
- **`COLOR_0` dropped.** Vertex colors silently discarded.
- **Node transforms world-baked.** No local transform / instancing survives.
- **`normalize_height` scales by max-extent, not height.** Breaks on A/T-pose characters
  (arm span > height ⇒ wrong scale).
- **Tangents go stale after deformation.** A skinned/deformed mesh keeps its rest-pose
  tangents.

### 1.3 Entirely absent (hard gaps, not fix-ups)
- **Skeleton / rig import** — none.
- **`JOINTS_0` / `WEIGHTS_0`** — skin-binding attributes are not read.
- **Morph targets** — none (blocks ARKit's 52 blendshapes).
- **Topology validation** — none.
- **Poly-budget / LOD / meshlet pipeline** — none.

### 1.4 Doc/code drift (recorded so it isn't rediscovered as a bug)
- `vfs.rs:148` says absolute paths are rejected; the code actually **collapses a leading
  `/`.**

---

## 2. Engine roadmap — ordered by what it blocks

The pipeline cannot emit around these — they are engine-side work. Ordered by which slice
of the 3D plan each tier unblocks, **cheapest first**.

### Tier 0 — blocks static props (do first)
- **Tangents: generate MikkTSpace on import when absent (or hard-require `TANGENT`).**
  *The highest-priority item on the entire list.* Stage-4 baking produces normal maps, and
  the current arbitrary-tangent fix-up renders them wrong silently (§1.2). `bpy` bakes
  against **MikkTSpace**, so generating MikkTSpace tangents on import matches the bake
  basis exactly.
- **Trust native units; drop / opt-out of `normalize_height`.** Max-extent normalization
  breaks A/T-pose characters (arm span > height). `bpy` guarantees real-world scale — the
  engine should trust it.
- **`alphaMode` / `alphaCutoff`.** Hair cards and foliage are alpha-cutout — missing this
  **blocks hair entirely.**
- **`doubleSided`.** Cloth, leaves, hair cards.

### Tier 1 — blocks the ENTIRE character spine
- **`JOINTS_0` / `WEIGHTS_0`.** Ignored today ⇒ the skinned mesh that stages 9/10 produce
  **cannot be loaded by the engine.** Hard blocker for every rigged asset.
- **Skeleton import + the canonical skeleton contract** (the frozen decision in 11c §0.5:
  Mixamo-compatible hierarchy produced via Rigify).

### Tier 2 — blocks the face
- **Morph targets** — required for ARKit's 52 blendshapes (stage 10 / 11d).

### Tier 3 — shippable quality
- **LOD convention.** The pipeline generates the LODs; the engine just loads them — pick
  **separate-GLB vs. `extras`**, and tell `bpy` which.
- **Collision-mesh convention.**
- **`KHR_texture_transform`**, **`KHR_materials_emissive_strength`.**

### Tier 4 — later
- **`COLOR_0`** — silently dropped today; at minimum **warn**.
- Multiple UV sets · image precision · cooked-asset cache · local transforms + instancing.

---

## 3. How this re-shapes the 3D plan

- **"Engine-ready" is redefined.** 11b/11c/11d call GLB "engine-ready"; the real bar is
  §1.1 **plus** the Tier-0 items. The D1 gate becomes "loads in *this* engine and looks
  right," not "a `.glb` exists" (folded into 11b §3 and 11c §4).
- **Two tracks meeting at the rig.** **Track A** (static props) runs against the as-built
  contract *today*. **Track B** (skinning import + tangents + alphaMode — Tiers 0–1) is
  the engine prerequisite the character spine waits on. **Do A first.**
- **Tangents are the top engine task**, because the entire bake pipeline (stage 4) is
  worthless *through this engine* without a correct tangent basis — and it fails silently,
  which is worse than a hard error.
