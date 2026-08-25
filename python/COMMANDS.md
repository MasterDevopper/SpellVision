# Worker commands owned by this lane

Clothes+wire registers these. This file is the contract so that lane can wire
`look_complete` without guessing.

## `look_complete`

Complete a Robust / Character still that is **not** head-to-toe. Recreate the
**real clothes present**. Never I2I-photocopy a Grok still as identity.
Refuse clothes-only (that is the `clothes_only` lane).

Producer (do not switch houses):

`F:/AI_ASSETS/models/diffusion_models/loxsUtopicWorldKrea2_v10Quants.safetensors`
(`model_family=krea2`)

### Request

```json
{
  "command": "look_complete",
  "input_image": "C:/path/to/still.jpg",
  "present_regions": ["face", "hair", "torso_clothes"],
  "target": "full_body_768x1344",
  "method": "t2i_identity",
  "identity_prompt": "",
  "outfit_hint": "",
  "seed": 4419
}
```

| field | required | notes |
|---|---|---|
| `input_image` | yes | source still |
| `present_regions` | no | `face`, `hair`, `torso_clothes`, `legs`, `feet`, `hands` — planner detects if omitted |
| `target` | no | must be `full_body_768x1344` (768×1344, feet visible) |
| `method` | no | `t2i_identity` (default) or `pad_inpaint` |
| `identity_prompt` / `outfit_hint` | no | override clauses derived from what is present |
| `seed` | no | int |

### Result

Completed PNG + report. Payload shape from `LookCompletePlan.to_payload()`:

```json
{
  "command": "look_complete",
  "input_image": "...",
  "present_regions": ["face", "hair", "torso_clothes"],
  "missing_regions": ["legs", "feet"],
  "target": "full_body_768x1344",
  "width": 768,
  "height": 1344,
  "method": "t2i_identity",
  "prompt": "full body, entire figure, head to toe, feet visible, ...",
  "negative_prompt": "close-up, cropped, bust shot, missing feet, ...",
  "identity_prompt": "...",
  "model": "F:/AI_ASSETS/models/diffusion_models/loxsUtopicWorldKrea2_v10Quants.safetensors",
  "model_family": "krea2",
  "unet_name": "loxsUtopicWorldKrea2_v10Quants.safetensors",
  "steps": 52,
  "cfg": 3.5,
  "seed": 4419,
  "crop": "bust",
  "already_complete": false,
  "pack": "witch"
}
```

### Fail closed

- `LookCompleteRefused` if the source is clothes-only / no face+hair.
- `already_complete=true` + `method=noop` if the still is already 768-class full body with feet — do not generate.
- Never `POST /free` while a job is in flight.
- Graph builders: `look_completion.build_krea2_t2i_graph` or
  `look_completion.build_look_complete_inpaint_graph` (imports
  `krea2_regional_inpaint.build_krea2_regional_inpaint_graph`, does not edit it).

### CLI (this lane)

```
.venv/Scripts/python.exe python/look_completion.py inventory
.venv/Scripts/python.exe python/look_completion.py plan --image <still>
.venv/Scripts/python.exe python/look_completion.py complete --image <still> --out runtime/characters/robust_inventory/proofs
```
