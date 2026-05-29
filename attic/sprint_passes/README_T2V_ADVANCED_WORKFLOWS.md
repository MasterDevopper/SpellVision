# SpellVision T2V Advanced Wan Controls + Saved Workflows

This bundle adds a focused T2V pass:

- T2V-only saved generation workflows / recipes.
- Mode-segregated storage under `runtime/generation_recipes/<mode>/`.
- T2V recipe UI in the Model Stack rail.
- Advanced Wan controls in the Advanced rail.
- Payload wiring for `wan_split_mode`, `wan_high_steps`, `wan_low_steps`, `wan_noise_split_step`, `high_noise_shift`, and `low_noise_shift`.
- Backend support for manual high/low step control.
- Metadata enrichment for Wan split mode, high/low steps, split step, and shifts.

## Storage

T2V recipes are saved to:

```text
runtime/generation_recipes/t2v/
```

Each recipe is a JSON file tagged with:

```json
{
  "recipe_type": "spellvision_generation_recipe",
  "mode": "t2v"
}
```

The T2V page only loads recipes tagged for T2V.

## Verification

After copying the files into your project, run:

```powershell
cd C:\Users\xXste\Code_Projects\SpellVision
& .\.venv\Scripts\Activate.ps1
python -m py_compile .\python\worker_service.py
python -m py_compile .\python\worker_client.py
.\scripts\dev\run_ui.ps1
```

Then test:

1. Open the T2V page.
2. Select the Wan high-noise / low-noise stack.
3. Open Advanced.
4. Select Manual high / low steps.
5. Set High Steps and Low Steps.
6. Save Current as a T2V workflow.
7. Reload the workflow from the T2V Recipe dropdown.
8. Generate and inspect the latest native prompt.

Expected native prompt:

- Node 4: high-noise UNET.
- Node 5: low-noise UNET.
- Node 10: high-noise KSamplerAdvanced.
- Node 11: low-noise KSamplerAdvanced.
