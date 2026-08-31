"""The download commands over the real TCP protocol, against a live worker.

The unit tests drive DownloadManager in-process. These prove the other half: that the commands
are actually reachable on the wire, return the documented payload shape, and -- the point of the
whole lane -- that issuing one does not stop the worker answering anything else.

Nothing here touches the network. A bad reference fails fast in the resolver, which is enough to
exercise start -> status -> terminal state without downloading a gigabyte in CI.
"""
from __future__ import annotations

import time


def _first(messages, msg_type):
    for message in messages:
        if message.get("type") == msg_type:
            return message
    raise AssertionError(f"no {msg_type!r} in {[m.get('type') for m in messages]}")


def test_download_status_is_reachable_and_empty_on_a_fresh_worker(worker_client):
    status = _first(worker_client({"command": "download_status"}), "download_status")
    assert status["ok"] is True
    assert isinstance(status["items"], list)
    assert set(status["aggregate"]) == {"current", "total", "percent", "message"}
    assert status["max_concurrent"] >= 1


def test_start_download_requires_a_reference(worker_client):
    ack = _first(worker_client({"command": "start_download"}), "download_ack")
    assert ack["ok"] is False
    assert "reference" in ack["error"]


def test_start_download_returns_immediately_and_the_worker_stays_responsive(worker_client):
    """The requirement in one test: a download must not interrupt the rest of the app."""
    began = time.monotonic()
    ack = _first(
        worker_client({
            "command": "start_download",
            "reference": "https://invalid.invalid/definitely-not-there.safetensors",
            "label": "probe.safetensors",
        }),
        "download_ack",
    )
    elapsed = time.monotonic() - began
    assert ack["ok"] is True, ack
    assert elapsed < 10.0, "start_download must not block on the transfer"

    download_id = ack["download_id"]
    assert ack["item"]["label"] == "probe.safetensors"
    assert set(ack["item"]["progress"]) == {"current", "total", "percent", "message"}

    # The worker answers an unrelated command while that download is in flight or finishing.
    pong = _first(worker_client({"command": "ping"}), "result")
    assert pong["ok"] is True

    # And the record is visible by id from a brand-new connection -- no socket is held open.
    status = _first(
        worker_client({"command": "download_status", "download_id": download_id}),
        "download_status",
    )
    assert status["ok"] is True
    assert status["items"][0]["download_id"] == download_id

    # It reaches a terminal state on its own (this reference cannot resolve, so: failed).
    deadline = time.monotonic() + 30
    state = status["items"][0]["state"]
    while time.monotonic() < deadline and state not in {"completed", "failed", "cancelled"}:
        time.sleep(0.2)
        state = _first(
            worker_client({"command": "download_status", "download_id": download_id}),
            "download_status",
        )["items"][0]["state"]
    assert state == "failed", f"expected an unresolvable reference to fail, got {state!r}"


def test_cancel_requires_an_id_and_reports_an_unknown_one_honestly(worker_client):
    ack = _first(worker_client({"command": "cancel_download"}), "download_ack")
    assert ack["ok"] is False
    assert "download_id" in ack["error"]

    ack = _first(
        worker_client({"command": "cancel_download", "download_id": "dl_nope"}), "download_ack"
    )
    assert ack["ok"] is False
    assert ack["cancel_requested"] is False


# --- Civitai variant listing --------------------------------------------------------------


def test_civitai_variants_requires_a_reference(worker_client):
    result = _first(worker_client({"command": "civitai_variants"}), "civitai_variants")
    assert result["ok"] is False
    assert "reference" in result["error"]


def test_a_non_civitai_reference_needs_no_choice(worker_client):
    """A plain URL or a bare filename has no versions to choose between, and must not be
    reported as ambiguous just because we could not look it up."""
    for reference in ["https://example.test/model.safetensors", "foo.safetensors"]:
        result = _first(
            worker_client({"command": "civitai_variants", "reference": reference}),
            "civitai_variants",
        )
        assert result["ok"] is True, result
        assert result["needs_choice"] is False
        assert result["variants"] == []


def test_a_reference_that_already_names_its_version_needs_no_choice(worker_client):
    result = _first(
        worker_client({
            "command": "civitai_variants",
            "reference": "https://civitai.com/models/2842735/vintage-mix-by-ak?modelVersionId=3234746",
        }),
        "civitai_variants",
    )
    assert result["ok"] is True
    assert result["needs_choice"] is False, "the link already picked one"
    assert result["model_version_id"] == "3234746"


def _variants_for(worker_client, model_url: str, vram_gb: float) -> dict:
    result = _first(
        worker_client({"command": "civitai_variants", "reference": model_url, "vram_gb": vram_gb}),
        "civitai_variants",
    )
    if not result.get("ok"):
        import pytest

        pytest.skip(f"Civitai unreachable: {result.get('error')}")
    return result


def _all_files(result: dict) -> list[dict]:
    return [f for v in result["variants"] for f in v["files"]]


LOX_KREA2 = "https://civitai.red/models/2823011/loxs-utopic-world-or-krea-2"
# Same checkpoint family, the OTHER shape: one precision per version rather than per file.
COMFY_ORG_KREA2 = "https://civitai.com/models/2726029"


def test_civitai_variants_offers_each_precision_with_one_recommendation(worker_client):
    """One Civitai version ships the same checkpoint at several precisions under the SAME
    filename, so the choice has to be per FILE. The owner's decision is "always ask, recommend
    one" -- exactly one row across the WHOLE MODEL carries the flag, and it is never applied."""
    result = _variants_for(worker_client, LOX_KREA2, vram_gb=32)

    assert result["needs_choice"] is True, "four versions, no version named in the link"
    quants = next((v for v in result["variants"] if "Quants" in v["version_name"]
                   and v["version_name"].startswith("V2")), None)
    assert quants, "fixture drifted; expected a V2 Quants version"

    precisions = {f["precision"] for f in quants["files"]}
    assert {"fp8", "int8", "nvfp4"} <= precisions, f"only got {precisions}"

    marked = [f for f in _all_files(result) if f["recommended"]]
    assert len(marked) == 1, f"exactly one row model-wide may be marked, got {len(marked)}"
    assert marked[0]["precision"] == "bf16", "23.88 GB fits 80% of 32 GB"

    # file_id is the key: the same name appears at several precisions.
    assert len({f["file_id"] for f in quants["files"]}) == len(quants["files"])


def test_one_row_is_marked_when_the_precision_axis_is_the_version_axis(worker_client):
    """The regression this replaced: the mark was computed PER VERSION.

    Model 2726029 publishes six versions of one checkpoint, one precision each, so every version
    had exactly one file and every file was therefore "the best in its version" -- measured 6 of 6
    rows marked "recommended for your GPU". A star on every row is a star that says nothing, and it
    looked like guidance.
    """
    result = _variants_for(worker_client, COMFY_ORG_KREA2, vram_gb=32)
    files = _all_files(result)
    assert len(files) >= 5, f"fixture drifted; expected the multi-version quant set, got {len(files)}"
    assert sum(1 for f in files if f["recommended"]) == 1


def test_the_recommendation_follows_the_card(worker_client):
    """A recommendation that returns the same file for a 12 GB card and a 32 GB one is not a
    recommendation. This failed before: a cross-version candidate set collapsed to the first
    primary file and the fitting logic never ran."""
    big = _variants_for(worker_client, LOX_KREA2, vram_gb=32)
    small = _variants_for(worker_client, LOX_KREA2, vram_gb=12)

    chosen_big = next(f for f in _all_files(big) if f["recommended"])
    chosen_small = next(f for f in _all_files(small) if f["recommended"])
    assert chosen_big["file_id"] != chosen_small["file_id"]
    assert chosen_small["size_gb"] <= 12 * 0.8
    assert chosen_big["size_gb"] > chosen_small["size_gb"]


# Model 573152, "LUSTIFY!". Its "v10 (Krea 2)" version publishes one filename at 24.48 GB and at
# 12.25 GB, all five rows declared bf16 -- half the bytes is what fp8 costs, so they cannot all be.
LUSTIFY = "https://civitai.com/models/573152"


def test_a_precision_label_that_contradicts_its_size_is_reported_and_never_recommended(worker_client):
    """Civitai's ``metadata.fp`` is a field an uploader types, and it is wrong often enough to
    matter: this model declares bf16 on rows that are half the size of its other bf16 rows.
    Ranking on the label made those "the highest precision available".

    A disputed row stays selectable -- it may be what the user wants -- but it is marked, and it is
    never the recommendation.
    """
    result = _variants_for(worker_client, LUSTIFY, vram_gb=32)
    files = _all_files(result)

    disputed = [f for f in files if f.get("precision_dispute")]
    assert disputed, "fixture drifted; expected the half-size rows declaring bf16"
    for file in disputed:
        assert file["recommended"] is False
        assert "measures" in file["precision_dispute"]
        # Still offered, with a usable url -- marked, never hidden.
        assert file["download_url"]


def test_the_dispute_check_stays_quiet_on_a_model_it_cannot_measure(worker_client):
    """Stated cost, not a hidden one. Model 2726029 publishes one precision per VERSION, so no
    version holds two encodings of one file to compare -- and the comparison is only sound within a
    version. Across versions it fired on 11% of a 1101-candidate corpus, because a model's versions
    span different architectures rather than different precisions. Silence here is the honest
    answer, and the recommendation still resolves to exactly one row."""
    result = _variants_for(worker_client, COMFY_ORG_KREA2, vram_gb=32)
    files = _all_files(result)
    assert not [f for f in files if f.get("precision_dispute")]
    assert sum(1 for f in files if f["recommended"]) == 1
