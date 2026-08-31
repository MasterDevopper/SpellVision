"""Hunt dest <stem>/plate.png must prefix Comfy files as {stem}_{job}, not plate_{job}."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from comfy_graph_helpers import _filename_prefix_from_output


def test_plate_dest_uses_parent_folder_as_prefix() -> None:
    dest = r"D:/hunts/goblin_a/plate.png"
    assert _filename_prefix_from_output(dest, "job42") == "goblin_a_job42"
    assert _filename_prefix_from_output(dest.replace("plate.png", "plate_02.png"), "abc") == "goblin_a_abc"


def test_plain_comfy_dest_keeps_file_stem() -> None:
    dest = r"C:/sv_comfynext/ComfyUI/output/render_t2i.png"
    assert _filename_prefix_from_output(dest, "job9") == "render_t2i_job9"
