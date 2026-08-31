"""The kijai wrapper nodes need their OWN attention setting.

HyVideoModelLoader and WanVideoModelLoader call sageattn themselves instead of routing through
ComfyUI's global --use-sage-attention path, so the launcher flag never reaches them. Both were
pinned to "sdpa" with no caller ever overriding, which meant the wrapper families were leaving
the same speedup on the table that the global flag was.

Guards that the default is sageattn and that an explicit request value still wins -- including
"sdpa", which is the documented escape hatch and must not be swallowed by an `or` fallback.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import native_video_graphs as nvg  # noqa: E402


def test_default_is_sageattn():
    assert nvg._wrapper_attention_mode({}) == "sageattn"


def test_explicit_sdpa_is_honoured_not_swallowed():
    # The regression risk: `req.get("attention_mode") or "sageattn"` would keep "sdpa" fine, but
    # any future truthiness shortcut that treats the fallback as unconditional would break the
    # documented escape hatch. Pin it.
    assert nvg._wrapper_attention_mode({"attention_mode": "sdpa"}) == "sdpa"


@pytest.mark.parametrize("value", ["sageattn", "sdpa", "flash_attn", "comfy"])
def test_explicit_values_pass_through(value):
    assert nvg._wrapper_attention_mode({"attention_mode": value}) == value


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_falls_back_to_default(blank):
    assert nvg._wrapper_attention_mode({"attention_mode": blank}) == "sageattn"


def test_hunyuan_wrapper_graph_carries_the_resolved_mode():
    """The Hunyuan i2v builder hardcoded "sdpa" inline; assert it now reads the resolver."""
    import inspect

    src = inspect.getsource(nvg._build_native_hunyuan_wrapper_i2v_prompt)
    assert '"attention_mode": "sdpa"' not in src, "Hunyuan wrapper re-hardcoded sdpa"
    assert "_wrapper_attention_mode(req)" in src
