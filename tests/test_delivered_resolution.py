"""The resolution a render REPORTS has to be the resolution of the file it wrote.

Doc 27 recorded this as "nothing claims the wrong number", on the strength of a grep through
`native_runners.py`. That was wrong, and the correction is the point: `video_request_metadata_from_
request` in `worker_service.py` computed `video_resolution` from `req["width"]` and `req["height"]`,
and that field feeds the column History labels **Resolution**. So a 768x512 request that wrote a
1536x1024 file did not leave the field blank -- it filled it in with the wrong number, which is the
worse of the two failures and the one this repository keeps finding.

Two things move the delivered size, and both are properties of the GRAPH rather than of the request:

* the default LTX route runs `LTXVLatentUpsampler` between its two samplers, so the requested pair
  is the size of the LATENT (measured: 768x512 in, 1536x1024 out);
* the upscale graft appends an `ImageScale` that states the final size outright (measured: 3072x2048
  with a 2x model upscale on that same request).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from native_video_graphs import delivered_frame_size  # noqa: E402
from worker_service import video_request_metadata_from_request  # noqa: E402


def _graph(*, upsampler: bool, scale_to: tuple[int, int] | None):
    graph: dict = {
        "1": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": 768, "height": 512}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["1", 0]}},
        "10": {"class_type": "CreateVideo", "inputs": {"images": ["9", 0], "fps": 16}},
    }
    if upsampler:
        graph["5"] = {"class_type": "LTXVLatentUpsampler", "inputs": {"samples": ["1", 0]}}
    if scale_to is not None:
        graph["20"] = {"class_type": "ImageScale", "inputs": {
            "image": ["9", 0], "upscale_method": "lanczos",
            "width": scale_to[0], "height": scale_to[1], "crop": "disabled"}}
        graph["10"]["inputs"]["images"] = ["20", 0]
    return graph


def test_a_plain_route_delivers_what_was_asked_for() -> None:
    assert delivered_frame_size(_graph(upsampler=False, scale_to=None), 768, 512) == (768, 512)


def test_a_spatial_upsampler_doubles_the_frame() -> None:
    assert delivered_frame_size(_graph(upsampler=True, scale_to=None), 768, 512) == (1536, 1024)


def test_an_upscale_states_the_final_size_outright() -> None:
    """The ImageScale wins over the derivation: it is the last word on the size."""
    graph = _graph(upsampler=True, scale_to=(3072, 2048))
    assert delivered_frame_size(graph, 768, 512) == (3072, 2048)


def test_a_scale_node_on_another_branch_does_not_answer() -> None:
    """Read from the SINK backwards. A graph can contain an ImageScale that is not the output."""
    graph = _graph(upsampler=True, scale_to=None)
    graph["30"] = {"class_type": "ImageScale", "inputs": {
        "image": ["9", 0], "upscale_method": "lanczos", "width": 99, "height": 99, "crop": "disabled"}}
    assert delivered_frame_size(graph, 768, 512) == (1536, 1024)


# --- the record ---------------------------------------------------------------------------------


def _video_request(**extra) -> dict:
    req = {"command": "t2v", "video_family": "ltx", "width": 768, "height": 512,
           "frames": 49, "fps": 16, "output": "C:/tmp/x.mp4"}
    req.update(extra)
    return req


def test_the_record_states_the_delivered_resolution_not_the_requested_one() -> None:
    metadata = video_request_metadata_from_request(
        _video_request(delivered_width=1536, delivered_height=1024))
    assert metadata["video_resolution"] == "1536x1024", (
        "History's Resolution column reads this field; stating the request there is a wrong number, "
        "not a missing one"
    )
    # The request is not lost -- it is a different fact, and both are worth having.
    assert metadata["video_requested_resolution"] == "768x512"
    assert metadata["video_width"] == 768


def test_without_a_delivered_size_the_request_is_still_the_right_answer() -> None:
    """Every non-native route reaches this with no graph to ask, and for those the request IS what
    is delivered. The fallback is correct rather than merely safe."""
    metadata = video_request_metadata_from_request(_video_request())
    assert metadata["video_resolution"] == "768x512"
    assert metadata["video_delivered_width"] == 0
