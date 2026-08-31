from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from plate_to_sliders import PlateToSlidersError, solve_plate_to_sliders


def test_clothes_pack_does_not_invent_whr(tmp_path: Path) -> None:
    pack = tmp_path / "jarvis_pack"
    pack.mkdir()
    (pack / "pack_manifest.json").write_text(
        '{"images": {"face_front": {}, "clothes_front": {}, "clothes_side": {}}}',
        encoding="utf-8",
    )
    with pytest.raises(PlateToSlidersError, match="no figure plates"):
        solve_plate_to_sliders(
            {
                "pack_dir": str(pack),
                "sliders": {"waist_slim": 0.4},
            }
        )
    out = tmp_path / "sliders.json"
    result = solve_plate_to_sliders({"pack_dir": str(pack), "output": str(out)})
    assert result["complete"] is False
    assert result["sliders"] == {}
    assert "no_figure_plates" in result["blocked_on"]
    assert "cheek" in result["blocked_on"]
    assert "jaw_width" not in result["blocked_on"]
    assert "chin" not in result["blocked_on"]
    assert out.is_file()


def test_refuses_performance_and_clothes_as_figure() -> None:
    with pytest.raises(PlateToSlidersError, match="performance"):
        solve_plate_to_sliders({"sliders": {"breath_chest": 0.2}})
    with pytest.raises(PlateToSlidersError, match="clothes"):
        solve_plate_to_sliders({"clothes_as_figure": True})
    with pytest.raises(PlateToSlidersError, match="not a shipped identity"):
        solve_plate_to_sliders({"sliders": {"height": 0.5}, "images": {"figure_front": {}}})
