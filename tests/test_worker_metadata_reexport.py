"""Facade must re-export metadata helpers used by native/comfy runners."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import worker_service as ws


def test_output_media_type_for_metadata_is_on_worker_service():
    assert hasattr(ws, "output_media_type_for_metadata")
    assert ws.output_media_type_for_metadata({"command": "i2v"}, "out.mp4") == "video"
    assert ws.output_media_type_for_metadata({"command": "t2i"}, "out.png") == "image"
