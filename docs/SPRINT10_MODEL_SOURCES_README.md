
# Sprint 10 model sources + Civitai checkpoint/LoRA support

This bundle extends the Sprint 10 runtime foundation with a source resolver and asset cache.

## What it adds

- Local path, Hugging Face repo, direct URL, and Civitai model URL support
- Civitai checkpoint and LoRA resolution through the public API
- Cached downloads under `python/.cache/assets` by default
- `CIVITAI_API_KEY` support for authenticated downloads
- Request-level support for:
  - `model`
  - `model_source`
  - `checkpoint`
  - `lora`
  - `lora_source`
  - `loras` (list of LoRA references)
  - remote `input_image` / `input_video`

## Example request shapes

### Local checkpoint
```json
{
  "command": "t2i",
  "model": "C:/models/checkpoints/ponyXL.safetensors",
  "prompt": "hero pose"
}
```

### Hugging Face repo
```json
{
  "command": "t2v",
  "model": "Lightricks/LTX-Video",
  "model_family": "ltx",
  "backend_kind": "diffusers"
}
```

### Civitai checkpoint via modelVersionId
```json
{
  "command": "t2i",
  "model_source": {
    "source": "civitai",
    "civitai_model_version_id": 123456,
    "filename": "my-checkpoint.safetensors"
  },
  "prompt": "comic cover art"
}
```

### Civitai LoRA
```json
{
  "command": "t2i",
  "model": "C:/models/checkpoints/base.safetensors",
  "lora_source": {
    "source": "civitai",
    "civitai_model_version_id": 654321
  },
  "lora_scale": 0.8
}
```

### Multiple LoRAs
```json
{
  "command": "t2v",
  "model_family": "wan",
  "backend_kind": "native_python",
  "model": "Wan-AI/Wan2.2-T2V-A14B",
  "loras": [
    {"source": {"source": "civitai", "civitai_model_version_id": 111111}, "scale": 0.6, "name": "style"},
    {"path": "C:/models/loras/motion.safetensors", "scale": 0.9, "name": "motion"}
  ]
}
```

## Notes

- The existing image worker still applies one active LoRA directly to the in-process Diffusers pipeline. This bundle resolves and caches multiple LoRA references but only auto-promotes a single resolved LoRA into the current image path. The full multi-LoRA in-process stack is a good next patch.
- Video adapters now receive resolved local paths and a `loras_json` field so external Wan/LTX scripts or Comfy workflows can consume them.
- Default cache root: `python/.cache/assets`
- Override cache root with `SPELLVISION_ASSET_CACHE`
- Provide `CIVITAI_API_KEY` for authenticated Civitai assets
