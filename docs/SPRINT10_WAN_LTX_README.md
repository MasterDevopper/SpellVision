# Sprint 10 Wan/LTX runtime foundation

This bundle adds real video runtime adapter paths to SpellVision:

- `backend_kind="comfy_workflow"` for Wan, LTX, Hunyuan Video, CogVideoX, Mochi, or any ComfyUI video workflow.
- `backend_kind="native_python"` for Wan/LTX or other official repos launched through an external Python entrypoint.
- `backend_kind="diffusers"` with an external helper script bridge for repo-id or local directory based models.

## Drop-in files

Copy these into your repo's `python/` tree:

- `python/model_registry.py`
- `python/worker_service.py`
- `python/runtime_adapters/base.py`
- `python/runtime_adapters/comfy_workflow_adapter.py`
- `python/runtime_adapters/native_video_adapter.py`
- `python/runtime_adapters/diffusers_adapter.py`

## Example: Wan T2V through ComfyUI

```json
{
  "command": "t2v",
  "model_family": "wan",
  "backend_kind": "comfy_workflow",
  "workflow_path": "C:/ComfyUI/user/default/workflows/wan22_t2v.json",
  "comfy_api_url": "http://127.0.0.1:8188",
  "comfy_output_dir": "C:/ComfyUI/output",
  "model": "Wan-AI/Wan2.2-T2V-A14B-Diffusers",
  "prompt": "cinematic anime heroine walking through a neon rain street",
  "negative_prompt": "blurry, bad anatomy, watermark",
  "width": 832,
  "height": 480,
  "steps": 30,
  "cfg": 6.0,
  "fps": 16,
  "num_frames": 81,
  "seed": 42,
  "output": "C:/Users/xXste/Code_Projects/SpellVision/outputs/video/wan_t2v_0001.mp4",
  "metadata_output": "C:/Users/xXste/Code_Projects/SpellVision/outputs/video/wan_t2v_0001.json",
  "workflow_overrides": {
    "6.inputs.text": "cinematic anime heroine walking through a neon rain street",
    "7.inputs.text": "blurry, bad anatomy, watermark"
  }
}
```

## Example: LTX I2V through a native repo

```json
{
  "command": "i2v",
  "model_family": "ltx",
  "backend_kind": "native_python",
  "model": "Lightricks/LTX-2.3",
  "native_repo_dir": "C:/AI/LTX-Video",
  "native_entrypoint": "C:/AI/LTX-Video/inference.py",
  "native_args_template": "--task {command} --model {model} --prompt "{prompt}" --image {input_image} --output {output} --frames {num_frames} --fps {fps} --seed {seed}",
  "prompt": "soft cinematic motion, hair and jacket moving in wind",
  "input_image": "C:/Users/xXste/Pictures/heroine.png",
  "fps": 16,
  "num_frames": 97,
  "seed": 77,
  "output": "C:/Users/xXste/Code_Projects/SpellVision/outputs/video/ltx_i2v_0001.mp4",
  "metadata_output": "C:/Users/xXste/Code_Projects/SpellVision/outputs/video/ltx_i2v_0001.json"
}
```

## Notes

- The Comfy adapter auto-applies common fields like `prompt`, `negative_prompt`, `seed`, `steps`, `cfg`, `width`, `height`, `fps`, `num_frames`, `input_image`, and `input_video` to matching node inputs when names match.
- The native adapter intentionally keeps CLI templates explicit because Wan/LTX repo CLIs change over time.
- The Diffusers adapter currently uses an explicit external helper path (`diffusers_entrypoint` + `diffusers_args_template`) instead of guessing each family's pipeline API.
