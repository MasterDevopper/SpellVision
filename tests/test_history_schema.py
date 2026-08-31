from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from history_schema import attach_mode_payload, detail_label, mode_block, normalize_mode


def test_normalize_mode_from_command() -> None:
    assert normalize_mode("i2v", "video") == "i2v"
    assert normalize_mode("t2i", "image") == "t2i"
    assert normalize_mode("", "video") == "t2v"
    assert normalize_mode("enqueue", "image") == "t2i"


def test_attach_mode_payload_keeps_image_off_duration_field() -> None:
    entry = {"media_type": "image", "command": "t2i", "image_steps": 35}
    attach_mode_payload(
        entry,
        media_type="image",
        command="t2i",
        image_details={"image_steps": 35, "image_cfg": 7.0},
    )
    assert entry["schema_version"] == 2
    assert entry["mode"] == "t2i"
    assert mode_block(entry, "image")["image_steps"] == 35
    assert "duration_label" not in mode_block(entry, "image")
    assert detail_label(entry) == "T2I • 35 steps"


def test_video_detail_label_uses_duration_not_steps() -> None:
    entry = {"media_type": "video", "command": "t2v"}
    attach_mode_payload(
        entry,
        media_type="video",
        command="t2v",
        video_details={"duration_label": "81 frames @ 16 fps (5.1s)"},
    )
    assert detail_label(entry) == "81 frames @ 16 fps (5.1s)"
    assert mode_block(entry, "image") == {}
