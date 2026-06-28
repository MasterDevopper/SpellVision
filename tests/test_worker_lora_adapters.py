"""LoRA / shared-UNet regression guard (TCP harness, real generations).

After the VRAM fix, the t2i and i2i pipelines SHARE one UNet/VAE/text_encoder
(weight-sharing dedup). The old LoRA code fused LoRAs destructively into those
weights and tracked them with a per-role cache that assumed the two pipes were
independent. That made this chain silently wrong:

    T2I(LoRA-A)  -> shared UNet = base+A, t2i cache=A
    I2I(LoRA-B)  -> shared UNet = base+B, t2i cache STILL A (stale)
    T2I(LoRA-A)  -> t2i cache hit on A, re-applies nothing -> renders B  (BUG)

The fix loads each LoRA once as a NAMED adapter (never fused) and re-selects the
role's adapter with set_adapters() before every generation, so the shared UNet
is never mutated and the two roles are independent.

This test drives the exact chain through the worker and asserts, at each step:
  * the active adapter is correct (via the result payload's active_adapters), and
  * fixed-seed PIXEL HASHES prove the render actually used the right LoRA:
      - T2I(A) after I2I(B) reproduces the FIRST T2I(A) render (regression guard)
      - LoRA-A and LoRA-B renders differ (so the equality above is meaningful)
      - no-LoRA renders the base (disable path), differing from T2I(A)
  * VRAM stays on the ~6.6GB plateau (no double-residency regression).

Dev-machine-only: skipped unless the SDXL checkpoint + both LoRAs exist on D:.
"""

from __future__ import annotations

import os

import pytest

CKPT = r"D:/AI_ASSETS/models/checkpoints/sdxl/animagineXL40_v10.safetensors"
# Both must be SDXL LoRAs (cross-attn context dim 2048) so they load on the SDXL
# UNet; an SD1.5 LoRA raises a size-mismatch at load time.
LORA_A = r"D:/AI_ASSETS/models/loras/Pony_DetailV2.0.safetensors"
LORA_B = r"D:/AI_ASSETS/models/loras/2.5DRealistic.safetensors"
PROMPT = "a photograph of a red apple on a rustic wooden table, soft daylight, detailed"

_ASSETS = [CKPT, LORA_A, LORA_B]
pytestmark = pytest.mark.skipif(
    not all(os.path.exists(p) for p in _ASSETS),
    reason="SDXL checkpoint / LoRAs not present under D:/AI_ASSETS — LoRA-chain test is dev-machine-only",
)

GEN_TIMEOUT = 360.0  # first call also loads the ~6.5GB checkpoint


def _pixels(path: str):
    import numpy as np
    from PIL import Image

    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float32)


def _mad(a, b) -> float:
    import numpy as np

    return float(np.mean(np.abs(a - b)))


def _result(messages: list[dict]) -> dict:
    results = [m for m in messages if m.get("type") == "result"]
    assert results, (
        "no terminal result message; types="
        + repr([m.get("type") for m in messages])
        + (f"; last={messages[-1]}" if messages else "")
    )
    res = results[-1]
    assert res.get("ok") is True, f"generation not ok: {res}"
    return res


@pytest.mark.contract
def test_lora_chain_keeps_roles_independent(worker_client, tmp_path):
    import torch

    if not torch.cuda.is_available():
        pytest.skip("CUDA required for the LoRA-chain generation test")

    base = dict(
        model=CKPT,
        prompt=PROMPT,
        negative_prompt="",
        width=512,
        height=512,
        steps=6,
        cfg=6.0,
        seed=1234,
    )

    def make_req(idx: int, command: str, *, lora: str | None = None, input_image: str | None = None) -> dict:
        r = dict(base)
        r["command"] = command
        r["output"] = str(tmp_path / f"o{idx}.png")
        r["metadata_output"] = str(tmp_path / f"o{idx}.json")
        r["lora"] = lora or ""
        r["lora_scale"] = 1.0
        if command == "i2i":
            r["input_image"] = input_image
            r["strength"] = 0.6
        return r

    def run(req: dict) -> dict:
        return _result(worker_client(req, timeout=GEN_TIMEOUT))

    # The exact regression chain: A -> B(i2i) -> A, then no-LoRA, then a B control.
    r1 = run(make_req(1, "t2i", lora=LORA_A))                                   # T2I(A)
    r2 = run(make_req(2, "i2i", lora=LORA_B, input_image=str(tmp_path / "o1.png")))  # I2I(B)
    r3 = run(make_req(3, "t2i", lora=LORA_A))                                   # T2I(A) again
    r4 = run(make_req(4, "t2i", lora=None))                                     # T2I(no LoRA) -> base
    r5 = run(make_req(5, "t2i", lora=LORA_B))                                   # T2I(B) control

    a1, a2, a3, a5 = (r.get("active_adapters") for r in (r1, r2, r3, r5))

    # --- active-adapter state is correct and role-independent ---
    assert a1 and len(a1) == 1, f"T2I(A) active adapters: {a1!r}"
    assert a2 and len(a2) == 1, f"I2I(B) active adapters: {a2!r}"
    assert a1 != a2, f"A and B resolved to the same adapter name: {a1!r} == {a2!r}"
    assert a3 == a1, f"T2I(A)-after-I2I(B) active adapter wrong: {a3!r} (expected {a1!r})"
    assert a5 == a2, f"T2I(B) control active adapter wrong: {a5!r} (expected {a2!r})"

    # --- pixel comparison proves the render actually used the right LoRA ---
    # Exact byte-equality is NOT reproducible across the worker's threaded request
    # handlers (cudnn.benchmark + TF32 give sub-pixel run-to-run noise; in-process
    # single-thread it is bit-exact). So we use mean-abs pixel distance with
    # RELATIVE thresholds: the T2I(A)-after-I2I(B) render must be far closer to the
    # original A render than to the B or base renders. On the OLD (buggy) code step
    # 3 rendered B, so d(A,A3) would be ~ d(A,B) and this fails loudly.
    px1, px3, px4, px5 = (_pixels(r["output"]) for r in (r1, r3, r4, r5))
    d_AA = _mad(px1, px3)   # A vs A-after-B  -> ~noise when correct
    d_AB = _mad(px1, px5)   # A vs B          -> large
    d_An = _mad(px1, px4)   # A vs base       -> large
    print(f"[lora-chain] d(A,A3)={d_AA:.3f}  d(A,B)={d_AB:.3f}  d(A,base)={d_An:.3f}")

    assert d_AB > 1.0, f"LoRA-A and LoRA-B render nearly identically (d={d_AB:.3f}); pick LoRAs with distinct effects"
    assert d_An > 1.0, f"no-LoRA render is nearly identical to LoRA-A (d={d_An:.3f}); disable-adapters path may have failed"
    assert d_AA < 0.25 * d_AB, (
        f"REGRESSION: T2I(A)-after-I2I(B) is not close to the original A render "
        f"(d(A,A3)={d_AA:.3f} vs d(A,B)={d_AB:.3f}) — the shared UNet leaked the other role's LoRA."
    )
    assert d_AA < 0.25 * d_An, (
        f"REGRESSION: T2I(A)-after-I2I(B) drifted from A toward base "
        f"(d(A,A3)={d_AA:.3f} vs d(A,base)={d_An:.3f})."
    )

    # --- VRAM plateau preserved (the shared-weight + adapters fix, not 2x copies) ---
    for label, r in (("t2i#1", r1), ("i2i#2", r2), ("t2i#3", r3), ("t2i#4", r4), ("t2i#5", r5)):
        alloc = r.get("cuda_allocated_gb")
        assert alloc is not None and alloc < 12.0, f"VRAM regression at {label}: cuda_allocated_gb={alloc}"
