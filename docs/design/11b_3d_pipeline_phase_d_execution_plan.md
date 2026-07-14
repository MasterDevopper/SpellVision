# Doc 11b — 3D Game-Asset Content Pipeline: Phase D Execution Plan

> **Status:** Phase D, not started. You are mid-phase-C. This is an *execution-grade
> scaffolding plan*, not a build order to start today. The architecture below is
> pattern-stable and lift-able; the values marked **⚠️SURVEY** must be re-grounded
> from a live ComfyUI `/object_info` dump + the real workflow JSON at D-start —
> exactly the discipline that made the LTX migration go clean.
>
> **Target-contract correction (the missing input):** this plan was written targeting
> *generic* GLB. The real target is the custom engine's **as-built import contract —
> [Doc 23](23_engine_import_contract.md)** — which is stricter than the glTF spec and
> silently mis-handles several things the generative pipeline emits (tangents, scale,
> alpha, skinning). Read Doc 23 before treating any GLB as "engine-ready."

---

## 0. How to read this

Two confidence tiers run through the whole document:

- **STABLE** — mirrors the live `native_comfy_template` pattern (Wan/LTX). Safe to
  lift verbatim. The code in §4 is written against the shapes currently in
  `base.py`, `wan_adapter.py`, `registry.py`, `video_family_contracts.py`,
  `model_registry.py`, and `worker_service.py`.
- **⚠️SURVEY** — depends on the *then*-current best model and its node pack. Any 3D
  model you deploy this quarter is beaten within six months, so the model sits
  behind a swappable template; never make it load-bearing. These slots are
  *designed* to be filled from live output, not guessed.

---

## 1. The shape: 3D is two layers, not one feature

| Layer | What it is | Where it lives | Reuse |
|---|---|---|---|
| **L1 — single-asset generation** | One image → one clean textured mesh | New `native_comfy_template` family, identical to Wan/LTX | ~90% reuse of existing on-ramp |
| **L2 — composition** | Separable garments / multi-part assets | Chain Studio orchestration (NOT a model) | Reuses Chain `InputRef`/`resolveStageInput` |

**The strategic rule:** L1 makes 3D *work*; L2 makes 3D do what you specifically
asked for (separable clothing). Build and prove L1 first — L2 is vapor until
single-asset generation round-trips end to end.

### 1.1 Requirement → capability (from the live survey)

| Your requirement | Reality | Path |
|---|---|---|
| Buildings / weapons (hard-surface) | ✅ Mature, game-ready topology, GLB/OBJ/STL | L1 |
| Characters | ✅ Workable as a single mesh | L1 |
| Animals w/ coarse strand hair | ⚠️ Mesh gives sculpted hair *blobs*, not strands | L1 mesh + **Blender groom post-step** |
| Clothing as separable garments | ❌ Single-shot models fuse coat into body | **L2 composition** — garment generated as its own asset |

Hair grooming and clean retopo are **post-generation steps done outside the
generator** (Blender), never generation outputs. Treat them as pipeline handoffs,
not features to build into the worker.

---

## 2. With what — component inventory

### 2.1 Candidate model (swappable) — ⚠️SURVEY
- **Clean-open default (settled in 11d):** **TRELLIS 2 / TRELLIS.2-4B (MIT)** — chosen
  over Hunyuan3D specifically because users ship commercial games and MIT beats the
  Hunyuan community license. The base-mesh generator in the 11d runbook and the D1 gate
  (§3) both run through TRELLIS 2. The §4 scaffolding below is written illustratively
  against Hunyuan3D's two-stage shape→texture graph, but it is **model-agnostic pattern**
  — the family machinery does not change when the model does.
- **Hunyuan3D-2.1** stays a viable alternative (two-stage shape→texture, ComfyUI-native,
  `.glb` + PBR) if licensing is acceptable for a given asset.
- **At D-start:** re-survey live for the best ComfyUI-native image-to-3D model and current
  node-pack versions. The model is a *template component*; never load-bearing.

### 2.2 Output formats (from Doc 11 export table — STABLE)
GLB (default, engine-ready, embedded textures) · OBJ+MTL (Blender/DCC) ·
FBX via `pyfbx` (animation/engines) · STL (print, geometry only) · GLTF (separate
textures) · USDZ (deferred, post-v1.0).

### 2.3 New worker command
- **`i23d`** (image-to-3D). Primary path: image in → mesh out.
- `t23d` (text-direct-to-3D) only if a model warrants it later; most pipelines are
  T2I → I23D, which your Chain Studio already expresses as a two-stage chain.

### 2.4 Libraries / external tools
- **Viewer (D2):** custom GL renderer + `tinygltf` (single-header MIT) for GLB load,
  per Doc 11 §6. Not Qt Quick 3D (pulls in QML the rest of the app avoids).
- **Blender:** external post-tool for strand groom + retopo. Out-of-app handoff;
  not a worker dependency.

### 2.5 File manifest
**New files (Python worker):**
- `python/worker/native/mesh_family_contracts.py` — STABLE (§4.2)
- `python/worker/native/mesh_family_readiness.py` — STABLE (§4.3)
- `python/worker/native/mesh_adapter.py` — STABLE shell, ⚠️SURVEY `required_nodes` (§4.4)

**Edited files:**
- `model_registry.py` — add `i23d` command + `hunyuan3d`/`mesh_3d` family (§4.1)
- `worker_service.py` — add `run_native_image_to_3d` + `_build_native_image_to_3d_prompt`
  + dispatch branch (§4.5)
- adapter `registry.py` — register the mesh adapter (if you keep mesh adapters in the
  same registry; otherwise a parallel `mesh_registry.py`)

**C++ (D2 — the genuinely new surface):**
- `Mode::ImageTo3D` on the polymodal generation page
- mesh preview path in `MediaPreviewController` (orbit/turntable, not a video player)
- `GenerationResultRouter` send-to-3D route
- mesh-to-thumbnail rendering for history/previews

### 2.6 The one thing that ripples: `media_type = "mesh"`
Your worker switches on `media_type`/`task_type`/`command` in several places
(asset extraction, preview routing, history labelling). A mesh is neither image nor
video. Adding the `"mesh"` media type is the single cross-cutting change that
touches the most existing code — budget for it explicitly in D2 rather than letting
it leak through D1.

---

## 3. How — build order (mirrors the LTX 4-step migration)

### D1 — single-asset image-to-3D, one family
The LTX pattern applied verbatim:
1. **Adapter + graph branch.** Add `MeshFamilyAdapter` (§4.4) and an `i23d` branch to
   the worker that builds the Hunyuan3D graph from a templatized live workflow.
2. **Native smoke test.** A real `run_native_image_to_3d()` round-trip that produces
   an actual `.glb`, not a Comfy-API stub. This is the analogue of the LTX smoke test.
3. **Contract status.** Flip `mesh_family_contract("hunyuan3d").validation_status`
   from `planned` → `validated` once (2) passes; add a `native_template_validated`
   flag if you want the gate to accept it without full production parity.
4. **Open the gate.** Remove/condition any routing that would block native i23d.

**Milestone (corrected — see 11c §4 and [Doc 23](23_engine_import_contract.md)).**
"First `.glb` round-trips" is **not** the gate — a `.glb` the custom engine chokes on is
a demo, not a milestone. The real D1 gate is:

> concept image → TRELLIS 2 → (optional UltraShape) → retopo / UV / bake → export →
> **loads in the custom engine and looks right.**

A static, textured, **game-ready prop** — no rig, no face, no garments. This path works
against the engine's *as-built* import contract **today** (`POSITION`/`NORMAL`/
`TEXCOORD_0`/`TANGENT` + PBR, Doc 23 §1.1), so it validates the whole generation chain
without blocking on engine work.

**Two tracks, meeting at the rig.** **Track A** (static props) is the gate above and
proceeds now. **Track B** (engine skinning import + tangents + alphaMode — Doc 23 Tiers
0–1) is the engine prerequisite; the character spine (rig / face / garments) completes
only *after* Track B lands. **Do A first.**

**D1 scope:** buildings, weapons, props, single characters. Separable garments and
strand hair are explicitly **out of D1 scope**.

### D2 — the 3D output surface (the part that reuses nothing)
- Mesh viewer (orbit/turntable, GL + tinygltf)
- Mesh-to-thumbnail rendering
- `media_type="mesh"` plumbed through asset extraction + result routing
- `Mode::ImageTo3D` page; send-to-3D handoff

This is the work that does **not** ride on the LTX/Wan rails. Schedule it as real
new engineering, not a templatization pass.

### D3 — composition layer (Layer 2: your headline requirement)
- A Chain Studio **stage type** for "generate part → assemble": body, coat, weapon
  each as a standalone single-mesh generation, composed downstream.
- Convention: a garment is generated from an image of *just the garment on a clean
  background*, producing a separable mesh — the separation comes from generating
  parts as standalone objects, not from decomposing a dressed character.
- Blender handoff for groom + retopo + final assembly.
- A "dressed character" asset = a **chain**, not a single call. This is closer to
  Chain mechanics than to your single-shot T2I/video paths — you already built the
  orchestration.

**Gate discipline:** do not start D3 until D1 single-asset generation is solid.
Conflating the layers is how this turns into vapor.

---

## 4. Pattern-stable scaffolding (lift-able now)

> All code follows the live shapes read from your repo. ⚠️SURVEY markers flag the
> exact lines that must be filled from a live `/object_info` dump at D-start.

### 4.1 `model_registry.py` additions

```python
# 1) extend the command set
SUPPORTED_GENERATION_COMMANDS = {"t2i", "i2i", "t2v", "i2v", "v2v", "ti2v", "i23d"}

# 2) (optional) runtime hint — mesh families run through Comfy, never diffusers
DEFAULT_MESH_RUNTIME_HINTS: dict[str, list[str]] = {
    "hunyuan3d": ["comfy_workflow"],
    "trellis": ["comfy_workflow"],
    "unknown_mesh": ["comfy_workflow"],
}

# 3) new family spec — mirrors the Anima decision (explicitly NOT diffusers)
#    add inside MODEL_FAMILIES:
    "hunyuan3d": ModelFamilySpec(
        key="hunyuan3d",
        display_name="Hunyuan3D",
        task_family="mesh",            # new task family
        media_type="mesh",            # new media type — see §2.6
        supported_commands=("i23d",),
        preferred_backends=("comfy_workflow",),   # split-file / multi-node graph
        aliases=("hunyuan-3d", "hunyuan_3d", "hy3d", "hunyuan3d-2", "hunyuan3d-2.1"),
        accepted_extensions=(".safetensors", ".ckpt"),
        # ⚠️SURVEY: confirm repo prefixes against the real model card at D-start
        repo_id_prefixes=("tencent/hunyuan3d", "tencent/hunyuan3d-2"),
    ),
```

> Note: `task_family="mesh"` and `media_type="mesh"` are new enum values. Grep for
> every `media_type ==` / `task_family ==` switch before D2 — that is the §2.6 ripple.

### 4.2 `mesh_family_contracts.py` (full — mirrors `video_family_contracts.py`)

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

CONTRACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MeshFamilyContract:
    family: str
    display_name: str
    tasks: tuple[str, ...]                  # ("i23d",) for now
    validation_status: str                  # planned < detected < validated < production
    backend_route: str                      # "native_comfy_template" when wired
    stack_kind: str                         # "two_stage_shape_texture" for Hunyuan3D
    required_components: tuple[str, ...]
    optional_components: tuple[str, ...]
    output_format_default: str              # "glb"
    export_formats: tuple[str, ...]
    history_label_style: str
    runtime_affinity_fields: tuple[str, ...]
    readiness_notes: tuple[str, ...]
    markers: tuple[str, ...]
    pipeline_candidates_i23d: tuple[str, ...]

    @property
    def production_ready(self) -> bool:
        return self.validation_status == "production"

    @property
    def validated(self) -> bool:
        return self.validation_status in {"validated", "production"}

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = CONTRACT_SCHEMA_VERSION
        payload["production_ready"] = self.production_ready
        payload["validated"] = self.validated
        for key, value in list(payload.items()):
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


MESH_FAMILY_CONTRACTS: dict[str, MeshFamilyContract] = {
    "hunyuan3d": MeshFamilyContract(
        family="hunyuan3d",
        display_name="Hunyuan3D",
        tasks=("i23d",),
        # 'planned' = documented, not yet surveyed/detected. Flip to 'validated'
        # only after the §3 D1 smoke test produces a real .glb.
        validation_status="planned",
        backend_route="native_comfy_template",
        stack_kind="two_stage_shape_texture",
        # ⚠️SURVEY: confirm the real component split (shape model, texture/paint
        # model, vae, conditioner) from the official Hunyuan3D ComfyUI workflow.
        required_components=("shape_model", "texture_model"),
        optional_components=("vae", "conditioner", "delight_model"),
        output_format_default="glb",
        export_formats=("glb", "obj", "stl", "gltf", "fbx"),
        history_label_style="single_mesh_stack",
        runtime_affinity_fields=(
            "family", "stack_kind", "shape_model", "texture_model",
            "output_format", "backend_route",
        ),
        readiness_notes=(
            "Planned only. Re-survey the live model + node pack before wiring.",
            "Single-asset mesh path. Separable garments are a composition chain (L2), not this family.",
        ),
        markers=("hunyuan3d", "hunyuan_3d", "hunyuan-3d", "hy3d"),
        # ⚠️SURVEY: these are placeholders; Hunyuan3D is graph-based, not a single
        # diffusers pipeline class. Likely unused until/if a diffusers path exists.
        pipeline_candidates_i23d=(),
    ),
    "trellis": MeshFamilyContract(
        family="trellis",
        display_name="TRELLIS",
        tasks=("i23d",),
        validation_status="planned",
        backend_route="native_comfy_template",
        stack_kind="single_stage_mesh",
        required_components=("model",),
        optional_components=("vae", "conditioner"),
        output_format_default="glb",
        export_formats=("glb", "obj", "stl", "gltf"),
        history_label_style="single_mesh_stack",
        runtime_affinity_fields=("family", "stack_kind", "model", "output_format", "backend_route"),
        readiness_notes=("Planned only. Surface only if it beats Hunyuan3D at D-start.",),
        markers=("trellis",),
        pipeline_candidates_i23d=(),
    ),
}


UNKNOWN_MESH_FAMILY_CONTRACT = MeshFamilyContract(
    family="unknown_mesh",
    display_name="Unknown Mesh Family",
    tasks=("i23d",),
    validation_status="unsupported",
    backend_route="unknown",
    stack_kind="unknown",
    required_components=(),
    optional_components=(),
    output_format_default="glb",
    export_formats=("glb",),
    history_label_style="generic",
    runtime_affinity_fields=("family", "stack_kind", "model", "backend_route"),
    readiness_notes=("Unknown mesh family. Select a supported family before generating.",),
    markers=(),
    pipeline_candidates_i23d=(),
)


_ALIASES = {
    "hunyuan-3d": "hunyuan3d",
    "hunyuan_3d": "hunyuan3d",
    "hy3d": "hunyuan3d",
    "hunyuan3d-2": "hunyuan3d",
    "hunyuan3d-2.1": "hunyuan3d",
}


def normalize_mesh_family_id(value: Any) -> str:
    family = str(value or "").strip().lower().replace(" ", "_")
    family = _ALIASES.get(family.replace("_", "-"), _ALIASES.get(family, family))
    return family or "unknown_mesh"


def mesh_family_contract(family: Any) -> MeshFamilyContract:
    family_id = normalize_mesh_family_id(family)
    return MESH_FAMILY_CONTRACTS.get(family_id, UNKNOWN_MESH_FAMILY_CONTRACT)


def infer_mesh_family_from_text(*values: Any) -> str:
    text = " ".join(str(v or "") for v in values).strip().lower().replace("-", "_")
    if not text:
        return "unknown_mesh"
    for family, contract in MESH_FAMILY_CONTRACTS.items():
        for marker in contract.markers:
            m = marker.lower().replace("-", "_")
            if m and m in text:
                return family
    return "unknown_mesh"


def mesh_family_contracts_snapshot() -> dict[str, Any]:
    families = {f: c.to_payload() for f, c in MESH_FAMILY_CONTRACTS.items()}
    families["unknown_mesh"] = UNKNOWN_MESH_FAMILY_CONTRACT.to_payload()
    return {
        "type": "mesh_family_contracts",
        "ok": True,
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "active_candidate_family": "hunyuan3d",
        "families": families,
    }
```

### 4.3 `mesh_family_readiness.py` (the gate — mirrors the native video gate)

```python
from __future__ import annotations

from typing import Any

from .mesh_family_contracts import mesh_family_contract, normalize_mesh_family_id


def _infer_native_mesh_family(req: dict[str, Any]) -> str:
    for key in ("resolved_native_mesh_family", "mesh_family", "model_family", "family"):
        value = req.get(key)
        if value:
            return normalize_mesh_family_id(value)
    return "unknown_mesh"


def raise_if_unvalidated_native_mesh_family(family: str, *, command: str) -> None:
    """Hard gate, identical in spirit to _raise_if_unvalidated_native_video_family.

    Only families whose contract is at least 'validated' may run the native
    template path. 'planned'/'detected'/'unsupported' are blocked.
    """
    contract = mesh_family_contract(family)
    if contract.validated:
        return
    raise RuntimeError(
        f"Native mesh family {family!r} is not validated for {command!r} "
        f"(status={contract.validation_status!r}). "
        "Run the D1 smoke test and flip the contract before enabling."
    )
```

### 4.4 `mesh_adapter.py` (reuses `base.py` helpers — STABLE shell)

```python
from __future__ import annotations

from typing import Any

from .base import (
    AdapterPrepareResult,
    VideoFamilyAdapter,        # generic enough to reuse; rename to AssetFamilyAdapter if you split base
    haystack_for_detection,
    stack_dict_from_request,
)


class MeshFamilyAdapter(VideoFamilyAdapter):
    family = "hunyuan3d"
    display_name = "Hunyuan3D"
    # ⚠️SURVEY: fill from a live /object_info dump of the installed Hunyuan3D node
    # pack. These are the gate for is_available(). Do NOT ship guessed names.
    required_nodes: tuple[str, ...] = (
        # e.g. "Hy3DModelLoader", "Hy3DGenerateMesh", "Hy3DExportMesh"  ← VERIFY LIVE
    )

    def score(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> int:
        if command not in {"i23d"}:
            return 0
        haystack = haystack_for_detection(req, family)
        if not any(m in haystack for m in ("hunyuan3d", "hunyuan_3d", "hy3d")):
            return 0
        return 100 if self.is_available(object_info) else 0

    def prepare_request(self, req: dict[str, Any], object_info: dict[str, Any], *, command: str, family: str) -> AdapterPrepareResult:
        payload = dict(req)
        warnings: list[str] = []
        stack = stack_dict_from_request(payload)

        payload["resolved_native_mesh_family"] = self.family
        payload["model_family"] = self.family
        payload["mesh_family"] = self.family
        payload.setdefault("backend_kind", "native_mesh")
        payload.setdefault("stack_kind", "two_stage_shape_texture")
        payload.setdefault("output_format", "glb")

        stack["family"] = self.family
        stack["model_family"] = self.family
        stack.setdefault("backend_kind", "native_mesh")
        stack.setdefault("stack_kind", "two_stage_shape_texture")

        payload["mesh_model_stack"] = stack
        payload["model_stack"] = stack
        payload["native_mesh_adapter_warnings"] = warnings
        return AdapterPrepareResult(payload=payload, warnings=warnings)
```

### 4.5 `worker_service.py` round-trip (skeleton — mirrors `run_native_split_stack_video`)

```python
def run_native_image_to_3d(req, emitter, job, active_job):
    command = str(req.get("command") or req.get("task_type") or "").strip().lower()
    family = _infer_native_mesh_family(req)                       # from mesh_family_readiness
    raise_if_unvalidated_native_mesh_family(family, command=command)
    if command != "i23d":
        raise RuntimeError(f"Native image-to-3D only supports i23d, got {command!r}.")

    transition_job(job, JobState.STARTING)
    emitter.status(job, "starting Comfy runtime for native image-to-3D")
    emitter.emit_job_update(job)
    prepare_runtime_for_request(req, emitter, job)

    runtime_status = handle_ensure_comfy_runtime_command(req)
    if not runtime_status.get("healthy"):
        raise RuntimeError(runtime_status.get("message") or "Managed Comfy runtime is not ready")
    api_url = str(req.get("comfy_api_url") or runtime_status.get("endpoint")
                  or os.environ.get("COMFY_API_URL") or "http://127.0.0.1:8188").rstrip("/")

    raise_if_cancelled(active_job, emitter, "Comfy runtime startup")
    object_info = _comfy_object_info(api_url)
    req = _prepare_native_mesh_adapter_request(req, object_info, command=command, family=family)
    family = str(req.get("resolved_native_mesh_family") or family)

    workflow = _build_native_image_to_3d_prompt(req, object_info, command=command, family=family, job_id=job.job_id)
    debug_path = _native_prompt_debug_path(req, job.job_id)
    _write_native_prompt_debug_file(debug_path, workflow)

    issues = _validate_comfy_prompt_against_object_info(workflow, object_info)
    if issues:
        raise RuntimeError("Native i23d prompt failed local validation: " + "; ".join(issues[:30]))

    transition_job(job, JobState.RUNNING)
    prompt_id = _submit_comfy_prompt(api_url, workflow)
    history = _poll_comfy_history(api_url, prompt_id, req, emitter, job, active_job)

    # ⚠️SURVEY: confirm the actual output bucket keys Hunyuan3D writes to.
    asset = _extract_comfy_asset(history, ["meshes", "models", "3d", "glb", "gltf"])
    if asset is None:
        raise RuntimeError("ComfyUI completed the i23d template but produced no mesh asset")
    return _settle_native_asset_result(asset, req, job, command="i23d", media_type="mesh")


def _build_native_image_to_3d_prompt(req, object_info, *, command, family, job_id):
    family_key = _infer_native_mesh_family(req)
    raise_if_unvalidated_native_mesh_family(family_key, command=command)

    # ⚠️SURVEY: every class-name tuple below is filled from a live /object_info dump
    # + the official Hunyuan3D workflow JSON. The _first_available_class +
    # _set_if_allowed pattern is identical to _build_native_split_video_prompt.
    image_load_class = _first_available_class(object_info, ("LoadImage",), label="input image")
    shape_loader     = _first_available_class(object_info, ("Hy3DModelLoader",),   label="shape model")     # VERIFY
    shape_gen        = _first_available_class(object_info, ("Hy3DGenerateMesh",),  label="shape stage")     # VERIFY
    texture_gen      = _first_available_class(object_info, ("Hy3DTexturePaint",),  label="texture stage")   # VERIFY
    mesh_export      = _first_available_class(object_info, ("Hy3DExportMesh",),    label="mesh save")       # VERIFY

    seed = _int_or_default(req.get("seed"), 0) or int(time.time() * 1000) % 2147483647
    out_format = str(req.get("output_format") or "glb").lower()

    prompt: dict[str, Any] = {}
    # node "0": LoadImage  → node "1": shape loader → "2": shape gen
    # → "3": texture gen   → "4": export    (wiring ⚠️SURVEY against the real graph)
    # Use _comfy_class_inputs(object_info, cls) + _set_if_allowed(...) for every input,
    # so only inputs the live node actually exposes get set — same as the video builder.
    ...
    return prompt
```

**Dispatch:** add an `i23d` branch wherever the worker selects its run function
(alongside `run_native_video` / `run_native_split_stack_video`), routing `command ==
"i23d"` to `run_native_image_to_3d`.

---

## 5. Live-survey checklist (run at D-start, before any of §4 ships)

1. Re-survey the current best ComfyUI-native image-to-3D model + node-pack versions.
2. Install it; pull a **live `/object_info` dump**.
3. Import the **official workflow JSON** through Flows (`WorkflowImportDialog` →
   `workflow_importer` → `CatalogPickerDialog`) and confirm it generates a `.glb`
   manually first — Path A before Path B, same as the Anima plan.
4. Fill from live output:
   - `MeshFamilyAdapter.required_nodes`
   - every `_first_available_class(...)` candidate tuple in `_build_native_image_to_3d_prompt`
   - the two-stage shape→texture **wiring** (node links)
   - the **mesh export node** class + its `output_format` enum choices
   - the **asset-extraction bucket keys** Hunyuan3D writes to
   - model **filenames / repo IDs / download targets** (`model_sources.py`,
     `model_dependency_resolver.py`)
   - confirm the **output folder** + extension
5. Run the D1 smoke test; flip the contract `planned → validated`; open the gate.

---

## 6. The `i23d` worker command contract

**Request (UI → worker):**
```json
{
  "command": "i23d",
  "request_id": "req_xyz",
  "mesh_family": "hunyuan3d",
  "input_image_path": "C:/Users/.../inputs/concept.png",
  "output_format": "glb",
  "seed": 0,
  "shape_model": "<resolved at adapter time>",
  "texture_model": "<resolved at adapter time>",
  "comfy_api_url": "http://127.0.0.1:8188"
}
```

**Response (worker → UI):**
```json
{
  "type": "job_result",
  "request_id": "req_xyz",
  "media_type": "mesh",
  "command": "i23d",
  "asset_path": "C:/Users/.../outputs/concept.glb",
  "output_format": "glb",
  "mesh_family": "hunyuan3d"
}
```

The `media_type: "mesh"` is the field D2 surfaces (viewer + thumbnail + routing) keys
off of. See §2.6.

---

## 7. What is explicitly NOT in this plan
- **No node class names treated as truth** — all are ⚠️SURVEY placeholders.
- **No strand-hair generation** — Blender groom post-step (L2/external).
- **No clean-retopo guarantee** — Blender retopo post-step (L2/external).
- **No separable-garment model** — does not exist as a single model; delivered by the
  L2 composition chain (D3), not L1.
- **No USDZ** — deferred past v1.0.
