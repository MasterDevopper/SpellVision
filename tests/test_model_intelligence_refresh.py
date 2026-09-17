"""Refreshing a whole library.

Sizing measured on this box 2026-09-16: 759 files, 2.09 TB, ~79 minutes of pure hashing at
440 MB/s. Three consequences the tests below pin:

  * SMALLEST FIRST. The 475 LoRAs are 130 GB and resolve in minutes; the 130 checkpoints are
    937 GB. Ordering by size means the library visibly fills up while the big files grind, rather
    than nothing happening for half an hour.
  * Cancellable, and a cancel must not lose the hashes already computed.
  * A locked root contributes a SKIP with a reason, never a silent zero.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import refresh, sidecar


class FakeClient:
    """Answers by-hash for weights whose bytes we planted, misses for everything else."""

    def __init__(self, known):
        self.known = known
        self.asked = []

    def by_hash(self, digest):
        self.asked.append(digest)
        return self.known.get(digest)


def _write(root: Path, name: str, size: int) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(name.encode()[:1] or b"x") * size)
    return path


def test_plan_orders_smallest_first(tmp_path: Path):
    _write(tmp_path, "big.safetensors", 3000)
    _write(tmp_path, "small.safetensors", 10)
    _write(tmp_path, "middle.safetensors", 500)
    assert [p.name for p in refresh.plan([tmp_path])] == [
        "small.safetensors", "middle.safetensors", "big.safetensors"
    ]


def test_plan_ignores_files_that_are_not_weights(tmp_path: Path):
    _write(tmp_path, "notes.txt", 10)
    _write(tmp_path, "w.safetensors", 10)
    assert [p.name for p in refresh.plan([tmp_path])] == ["w.safetensors"]


def test_a_hit_writes_a_sidecar(tmp_path: Path):
    from model_intelligence import hashing

    weight = _write(tmp_path, "w.safetensors", 64)
    digest = hashing.file_sha256(weight)
    client = FakeClient({digest: {"id": 1, "modelId": 2, "name": "V1", "baseModel": "Krea 2",
                                  "model": {"name": "A Model", "type": "LORA"},
                                  "trainedWords": ["trigger"], "images": [], "files": []}})
    result = refresh.RefreshJob([tmp_path], client=client, models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["identified"] == 1
    assert sidecar.read(weight)["display"]["name"]["value"] == "A Model"


def test_a_miss_records_no_match_and_still_writes_a_sidecar(tmp_path: Path):
    weight = _write(tmp_path, "w.safetensors", 64)
    result = refresh.RefreshJob([tmp_path], client=FakeClient({}), models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["no_match"] == 1
    loaded = sidecar.read(weight)
    assert loaded is not None
    assert loaded["identity"]["sources"] == []


def test_progress_is_reported_per_file(tmp_path: Path):
    _write(tmp_path, "a.safetensors", 10)
    _write(tmp_path, "b.safetensors", 20)
    seen = []
    refresh.RefreshJob([tmp_path], client=FakeClient({}), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json",
                       progress=lambda done, total, name: seen.append((done, total))).run()
    assert seen[-1] == (2, 2)


def test_cancel_stops_early_and_keeps_what_was_done(tmp_path: Path):
    """Cancel after the FIRST file completes, and the hash it computed must survive.

    Counting `cancel()` CALLS would not test this: `cancel` is consulted once per loop
    iteration AND once per chunk inside `file_sha256`, so a budget of two calls fires
    partway through file one, nothing ever finishes, and "keeps what was done" is
    vacuously true over an empty set. Counting completed FILES via `progress` is what
    makes the assertion mean something.
    """
    for index in range(5):
        _write(tmp_path, f"w{index}.safetensors", 10 + index)
    done = {"n": 0}

    def note(current: int, total: int, name: str) -> None:
        done["n"] = current

    result = refresh.RefreshJob(
        [tmp_path],
        client=FakeClient({}),
        models_root=tmp_path,
        cache_path=tmp_path / "cache.json",
        progress=note,
        cancel=lambda: done["n"] >= 1,
    ).run()
    assert 0 < result["examined"] < 5
    assert result["ok"] is True
    assert (tmp_path / "cache.json").exists()
    import json as _json

    entries = _json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))["entries"]
    assert len(entries) == result["examined"]


def test_a_locked_root_is_skipped_with_a_reason_not_counted_as_empty(tmp_path: Path, monkeypatch):
    good = tmp_path / "good"
    good.mkdir()
    _write(good, "w.safetensors", 10)
    locked = tmp_path / "locked"
    locked.mkdir()
    real = refresh.readable_roots.os.listdir

    def fake(target):
        if Path(target) == locked:
            raise OSError(-2144272384, "locked by BitLocker")
        return real(target)

    monkeypatch.setattr(refresh.readable_roots.os, "listdir", fake)
    result = refresh.RefreshJob([good, locked], client=FakeClient({}), models_root=good,
                                cache_path=tmp_path / "cache.json").run()
    assert result["skipped_unreadable"] == [str(locked)]
    assert result["examined"] == 1


def test_the_second_run_reuses_the_cache(tmp_path: Path, monkeypatch):
    """Count the HASHES, not the lookups.

    The first version of this test compared `client.asked[:first]` with `client.asked[first:]`.
    `by_hash` is called once per file per run whether or not the digest came from the cache, so
    the two halves were equal by construction -- it passed with `cache.json` DELETED between the
    runs. The cache's whole job is to not re-read 2.09 TB, so that is what is measured here.
    """
    from model_intelligence import hashing

    _write(tmp_path, "w.safetensors", 64)
    real = hashing.file_sha256
    hashed: list[str] = []

    def counted(path, **kwargs):
        hashed.append(str(path))
        return real(path, **kwargs)

    monkeypatch.setattr(hashing, "file_sha256", counted)
    cache = tmp_path / "cache.json"
    refresh.RefreshJob([tmp_path], client=FakeClient({}), models_root=tmp_path,
                       cache_path=cache).run()
    assert len(hashed) == 1, "the first run must hash the file once"
    refresh.RefreshJob([tmp_path], client=FakeClient({}), models_root=tmp_path,
                       cache_path=cache).run()
    assert len(hashed) == 1, f"the second run re-hashed {hashed[1:]}; the cache did not hold"


# --- a failed lookup is not an answer ---------------------------------------------------------


def test_a_hard_miss_is_counted_as_no_match_and_an_error_is_not(tmp_path: Path):
    """The site not knowing a hash and us not being able to ask are different facts, and only the
    first may be recorded as the model being unknown."""

    class Exploding:
        def by_hash(self, digest):
            raise OSError("network down")

    _write(tmp_path, "hit.safetensors", 10)
    miss = refresh.RefreshJob([tmp_path], client=FakeClient({}), models_root=tmp_path,
                              cache_path=tmp_path / "a.json").run()
    assert (miss["no_match"], miss["lookup_failed"]) == (1, 0)

    broken = refresh.RefreshJob([tmp_path], client=Exploding(), models_root=tmp_path,
                                cache_path=tmp_path / "b.json").run()
    assert (broken["no_match"], broken["lookup_failed"]) == (0, 1)


def test_a_lookup_error_preserves_what_the_previous_run_fetched(tmp_path: Path, monkeypatch):
    """The 466-second live run identified 34 models and fetched 123 pictures. One offline refresh
    reverted every one of them to its filename -- `civitai_version=None` went into `build_payload`
    regardless -- and reported ok, with the pictures orphaned on disk."""
    from model_intelligence import hashing

    monkeypatch.setattr(
        refresh.previews, "download_previews",
        lambda *a, **k: [{"local_path": "p0.jpg", "is_cover": True, "user_override": False}],
    )
    weight = _write(tmp_path, "w.safetensors", 64)
    digest = hashing.file_sha256(weight)
    known = FakeClient({digest: {
        "id": 1, "modelId": 2, "name": "V1", "baseModel": "Krea 2",
        "model": {"name": "Lox Utopic World", "type": "CHECKPOINT"},
        "trainedWords": ["loxtrigger"], "images": [{"url": "https://x.test/1.jpg"}], "files": [],
    }})
    refresh.RefreshJob([tmp_path], client=known, models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()

    class Exploding:
        def by_hash(self, digest):
            raise OSError("network down")

    result = refresh.RefreshJob([tmp_path], client=Exploding(), models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["lookup_failed"] == 1
    loaded = sidecar.read(weight)
    assert loaded["display"]["name"]["value"] == "Lox Utopic World"
    assert loaded["display"]["trigger_words"]["value"] == ["loxtrigger"]
    assert loaded["identity"]["sources"] and loaded["identity"]["sources"][0]["site"] == "civitai"
    assert loaded["display"]["images"] and loaded["display"]["images"][0]["local_path"] == "p0.jpg"


# --- a per-file failure is a per-file failure -------------------------------------------------


def test_a_malformed_preview_url_skips_the_image_not_the_run(tmp_path: Path):
    """`urllib.request.Request("not a url")` raises ValueError, the URL comes from the CivitAI
    response, and both guards caught OSError only -- so one bad URL ended the 79-minute run."""
    from model_intelligence import hashing

    weight = _write(tmp_path, "w.safetensors", 32)
    digest = hashing.file_sha256(weight)
    client = FakeClient({digest: {
        "id": 1, "modelId": 2, "model": {"name": "A Model"}, "trainedWords": [], "files": [],
        "images": [{"url": "not a url", "nsfwLevel": 1}],
    }})
    result = refresh.RefreshJob([tmp_path], client=client, models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["ok"] is True
    assert result["identified"] == 1
    assert sidecar.read(weight)["display"]["name"]["value"] == "A Model"


def test_an_http_exception_from_the_client_is_one_file_not_the_run(tmp_path: Path):
    """A truncated body surfaces as http.client.IncompleteRead -- an HTTPException, NOT an
    OSError. This repo has a memory note dedicated to exactly that on a ~6 MB body."""
    import http.client

    class Truncating:
        def by_hash(self, digest):
            raise http.client.IncompleteRead(b"{")

    _write(tmp_path, "a.safetensors", 10)
    _write(tmp_path, "b.safetensors", 20)
    result = refresh.RefreshJob([tmp_path], client=Truncating(), models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["examined"] == 2
    assert result["lookup_failed"] == 2
    assert len(result["errors"]) == 2


def test_a_value_error_from_the_client_is_one_file_not_the_run(tmp_path: Path):
    class BadJson:
        def by_hash(self, digest):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    _write(tmp_path, "a.safetensors", 10)
    result = refresh.RefreshJob([tmp_path], client=BadJson(), models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["ok"] is True and result["lookup_failed"] == 1


def test_the_refresh_command_answers_with_an_error_rather_than_raising(tmp_path: Path, monkeypatch):
    """`job.run()` was unwrapped and the one-shot branches in worker_tcp.handle() are not inside a
    try, so anything escaping reached socketserver.handle_error -- which logs and closes the
    connection WITHOUT a reply. The caller saw a timeout, indistinguishable from a hung worker."""
    import model_intelligence_commands as mic

    class Boom:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            raise ValueError("unknown url type: 'not a url'")

    monkeypatch.setattr(mic, "RefreshJob", Boom)
    reply = mic.handle_model_intel_refresh_command({"roots": [str(tmp_path)]})
    assert reply["ok"] is False
    assert reply["type"] == "model_intel_refresh"
    assert "unknown url type" in reply["error"]


def test_a_cache_save_failure_is_recorded_not_raised(tmp_path: Path, monkeypatch):
    """`cache.save()` sat outside every guard, so a failed hash-cache write threw away an hour of
    completed work -- and the caller saw a dropped connection rather than the report."""
    from model_intelligence import hashing

    def refuse(self):
        raise OSError("the cache directory went away")

    monkeypatch.setattr(hashing.HashCache, "save", refuse)
    _write(tmp_path, "w.safetensors", 24)
    result = refresh.RefreshJob([tmp_path], client=FakeClient({}), models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["ok"] is True
    assert result["examined"] == 1
    assert any("hash cache" in error["error"] for error in result["errors"])


# --- cancellable, and it says so --------------------------------------------------------------


def test_a_started_refresh_can_be_cancelled_and_reports_having_been_cancelled(
    tmp_path: Path, monkeypatch
):
    """`RefreshJob(cancel=...)` shipped from day one and nothing ever passed one: the command ran
    `job.run()` inline in the TCP handler, so the only way to stop a library pass was to kill the
    worker."""
    import threading as _threading

    import model_intelligence_commands as mic
    import worker_subscribe
    from model_intelligence import jobs

    gate = _threading.Event()

    class SlowClient:
        def by_hash(self, digest):
            gate.wait(timeout=10)
            return None

    monkeypatch.setattr(mic, "CivitaiClient", lambda **kwargs: SlowClient())
    for index in range(4):
        _write(tmp_path, f"w{index}.safetensors", 10 + index)

    seen: list[dict] = []

    class Subscriber:
        client_disconnected = False

        def emit(self, payload):
            seen.append(payload)

    worker_subscribe.reset_for_tests()
    worker_subscribe.register(Subscriber())
    try:
        started = mic.handle_model_intel_refresh_command(
            {"roots": [str(tmp_path)], "models_root": str(tmp_path), "background": True}
        )
        assert started["type"] == "model_intel_refresh_started"
        assert started["job_id"] in jobs.running()

        cancelled = mic.handle_model_intel_cancel_command({"job_id": started["job_id"]})
        assert cancelled["ok"] is True
        assert cancelled["cancelled"] == [started["job_id"]]
        gate.set()

        deadline = time.monotonic() + 10
        result = None
        while time.monotonic() < deadline and result is None:
            result = next((m for m in list(seen) if m.get("type") == "model_intel_refresh"), None)
            time.sleep(0.01)
        assert result is not None, f"no result reached the subscriber; saw {seen}"
        assert result["cancelled"] is True
        assert 0 <= result["examined"] < 4
    finally:
        gate.set()
        worker_subscribe.reset_for_tests()
        jobs.reset_for_tests()


def test_cancelling_a_job_nobody_is_running_is_refused_not_reported_as_done():
    import model_intelligence_commands as mic
    from model_intelligence import jobs

    jobs.reset_for_tests()
    reply = mic.handle_model_intel_cancel_command({"job_id": "mi_nope"})
    assert reply["ok"] is False
    assert reply["cancelled"] == []


# --- one kind vocabulary ----------------------------------------------------------------------


def test_an_unclassifiable_weight_records_other_and_a_null_family(tmp_path: Path):
    """`refresh` wrote the classifier's RAW `model_type` into the sidecar while `classify_models`
    normalised it, so one weight was `other` to the Models page and `unknown` in the file beside
    it -- and `family: "unknown"` is a TRUTHY string standing where "nothing determined one"
    belongs."""
    import model_intelligence_commands as mic

    weight = _write(tmp_path, "mystery.bin", 16)
    refresh.RefreshJob([tmp_path], client=FakeClient({}), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()
    identity = sidecar.read(weight)["identity"]
    assert identity["kind"] == "other"
    assert identity["family"] is None

    reply = mic.handle_model_recommended_settings_command({"path": str(weight)})
    assert reply["family"] is None
    # ...and a family the caller DOES know still brings its floor down with it.
    floored = mic.handle_model_recommended_settings_command(
        {"path": str(weight), "family": "sdxl"}
    )
    assert floored["settings"]["steps"]["value"] == 30
    assert floored["settings"]["steps"]["provenance"] == "table:family-default"


def test_a_lookup_error_is_recorded_and_the_run_continues(tmp_path: Path):
    class Exploding:
        def by_hash(self, digest):
            raise OSError("network down")

    _write(tmp_path, "a.safetensors", 10)
    _write(tmp_path, "b.safetensors", 20)
    result = refresh.RefreshJob([tmp_path], client=Exploding(), models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["examined"] == 2
    assert len(result["errors"]) == 2
