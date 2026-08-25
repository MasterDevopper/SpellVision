from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_registry import family_license_info, resolve_model_capabilities


def test_anima_and_hunyuan_are_non_commercial() -> None:
    anima = family_license_info("anima")
    assert anima["commercial_use"] is False
    assert "Non-Commercial" in str(anima["license_note"]) or "non-commercial" in str(anima["license_note"]).lower()

    hunyuan = family_license_info("hunyuan")
    assert hunyuan["key"] == "hunyuan_video"
    assert hunyuan["commercial_use"] is False


def test_wan_and_mochi_remain_commercial() -> None:
    assert family_license_info("wan")["commercial_use"] is True
    assert family_license_info("mochi")["commercial_use"] is True
    assert resolve_model_capabilities("ltx").commercial_use is True
