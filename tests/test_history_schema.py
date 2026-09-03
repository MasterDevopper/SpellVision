from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from history_schema import attach_mode_payload, normalize_mode


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
    image = entry["mode_payload"]["image"]
    assert image["image_steps"] == 35
    # The point of v2: an image's numbers live in the IMAGE block, so nothing downstream has to
    # borrow a video field to find them. v1 flattened them onto a video-shaped row and the UI put
    # the step count in the Duration column.
    assert "duration_label" not in image
    assert "video" not in entry["mode_payload"]


# The two detail-label assertions that used to live here moved to tests/cpp/test_history_row_labels.
# `detail_label` had no production caller: the page that renders that column had its own inline copy
# of the rule, so the tested implementation and the used one were different code. The coverage went
# where the rule went rather than being deleted with it.
