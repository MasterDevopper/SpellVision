# Character look-complete + clothes-only system (Doc 44)

Owner 2026-08-19. Binding for the 3-hour execute wave.

**Producer model stays Utopic Quants:**
`F:/AI_ASSETS/models/diffusion_models/loxsUtopicWorldKrea2_v10Quants.safetensors`
(`model_family=krea2`). Do not switch to stock Krea2 raw or Qwen-Edit as the house producer.

## Product promise

1. **Wardrobe on lock** — change clothes/hair on a locked 768×1344 identity plate without a second face, while keeping Utopic house look.
2. **Look-complete** — if a Robust / Character still is not head-to-toe, complete the missing body/clothes from what is already present (same identity, same outfit, feet in frame).
3. **Clothes-only** — generate isolated garments (white/empty bg, T-/A-pose dummy or no body) so Character Studio can shrink-wrap them onto frozen `female.glb` 14517.
4. **Wired** — worker commands + Character Studio stages, not one-off smoke scripts.

## Honest floors

- Body identity stays **14517** `female.glb`. TRELLIS/UltraShape = props only.
- Stills→mesh / garment cook remain **Degraded**. This wave delivers **stills + contracts + shrinkwrap scaffold**, not a cooked wearable.
- Do not fill `WARDROBE_20` into the LoRA dataset until a house-ok proof exists.
- Never `/free` an in-flight Comfy job. Comfy is live on `:8188`.
- Worker `:8765` may be down — start repo `.venv` `python/worker_service.py` if you need TCP; Comfy `/prompt` is enough for graph smokes.
- `logging.info` is invisible — use WARNING+.

## File ownership (do not cross)

| Owner | May edit |
|---|---|
| **Wardrobe / last-task** | `python/krea2_regional_inpaint.py`, `python/lock_plate_blend.py`, `tests/test_krea2_regional_inpaint.py`, `runtime/style/datasets/wrought_house_v1/FEATURE_BLUEPRINT.md`, `runtime/tmp_inpaint_smoke/*` (temp), proof stills under `runtime/style/datasets/wrought_house_v1/staging/` |
| **Look-complete** | **NEW** `python/look_completion.py`, `tests/test_look_completion.py`, `runtime/characters/robust_inventory/` |
| **Clothes + wire** | **NEW** `python/clothes_only.py`, `python/garment_shrinkwrap.py`, `tests/test_clothes_only.py`, Character Studio garments payload in `qt_ui/studios/CharacterStudioPage.*`, worker allow-list + dispatch in `python/worker_tcp.py` + `python/worker_service.py` / `native_runners.py` / `image_runners.py` |

Shared read-only: `python/qwen_image_edit_graph.py`, `python/character_pack.py`, `python/character_create.py`, this doc.

If a module needs a worker command, **Clothes + wire** registers it. Other lanes write a `COMMANDS.md` next to their module listing the intended command + payload.

## Worker commands (target)

| command | payload | result |
|---|---|---|
| `krea2_regional_inpaint` | lock, mask, edit, identity, denoise, latent_mode, unet | edited PNG |
| `look_complete` | input_image, present_regions, target=`full_body_768x1344` | completed PNG + report |
| `clothes_only` | garment_text or ref_image, views=`front,side,back`, dummy=`whbs`\|`none` | clothes plates |
| `garment_shrinkwrap` | clothes plates + optional body mesh | wrap report + dest under `runtime/characters/<id>/garments/` |

Fail closed. Do not pretend cook is done.

## Canvas / prompt locks

- Character stills: **768×1344**, `full body, entire figure, head to toe, feet visible`.
- Clothes-only: **1024×1024** product sheet **and** 768×1344 worn-on-dummy T-pose (white bg) for wrap.
- Clothes dummy if needed: **white hair black skin** (dark skin, short curly white hair, blue eyes) — not a new face.
- Recreate real clothes. No maxi-dress substitution. Hips visible unless the garment is honestly long.
- Anti-bodysuit: bare-skin / named pieces. Opaque recreation of sheer refs.

## Verification

```
export PATH="$(pwd)/.venv/Scripts:$PATH" VIRTUAL_ENV="$(pwd)/.venv" PYTHONNOUSERSITE=1
unset PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/test_krea2_regional_inpaint.py tests/test_look_completion.py tests/test_clothes_only.py tests/test_character_pack.py tests/test_character_create.py -q
```

UI: kill `SpellVision` then `cmake --build build --config Debug --target SpellVision` after C++ edits.

Update this doc's **Status** section when a lane lands.

## Status (2026-08-19 cron continue)

| Lane | Status |
|---|---|
| Wardrobe / last-task | **Measured, not house-ok** — `python/krea2_regional_inpaint.py` + smokes `runtime/tmp_inpaint_smoke/sweep_tee_*.png` (denoise sweep incl. 0.70). Qwen-Edit edits land; house restyle after edit does **not**. `FEATURE_BLUEPRINT.md`: **do not** fill `WARDROBE_20` into LoRA dataset. |
| Look-complete | **Live + studio-wired** — `python/look_completion.py`; inventory 18 packs / 338 unique. Concept preview **Complete look (head to toe)** emits `look_complete`; worker forwards `input_image`. Proofs Utopic Quants 768×1344: witch / afro / cow girl **KEEP** in `runtime/characters/robust_inventory/proofs/`. |
| Clothes + wire | **Plate-silhouette wrap** — Compose `garment_shrinkwrap` builds a cage from the clothes-only front mask and shrink-wraps it to `female.glb` 14517 (`used_plate_silhouette=true`, witch proof **9506** verts, not a body clone). Plates: `witch_fitted_pants_top` / `fox_lady_shrine` / `whbs_tank_cargos`. Cook still **Degraded**. |

**Pytest (Doc 44 suite):** 49 passed (`test_krea2_regional_inpaint` + `test_look_completion` + `test_clothes_only` + `test_character_pack` + `test_character_create`).

**Producer lock:** `F:/AI_ASSETS/models/diffusion_models/loxsUtopicWorldKrea2_v10Quants.safetensors`. Body freeze **14517**. No `/free` during in-flight gens.
