# SpellVision Native WAN Core Route Pass

This pass makes WAN native generation default to the proven core Comfy WAN graph used by imported working workflows:

- `CLIPLoader(type="wan")`
- `CLIPTextEncode` positive / negative
- `UNETLoader`
- `VAELoader`
- `ModelSamplingSD3`
- `EmptyHunyuanLatentVideo`
- `KSamplerAdvanced`
- `VAEDecode`
- `CreateVideo`
- `SaveVideo`

The previous WanVideoWrapper route remains available only when explicitly selected as a wrapper route. This avoids feeding `umt5_xxl_fp8_e4m3fn_scaled.safetensors` into `LoadWanVideoT5TextEncoder`, which the wrapper rejects.
