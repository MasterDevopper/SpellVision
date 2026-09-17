"""Creator and licence: the parent-model fetch that existed and was never called.

Doc 62 section 3k. `CivitaiClient.model()` was written, exported and unit-tested, and no code path
reached it -- so all 680 identified sidecars on this box wrote `"creator": null` and a licence
block of four nulls, while the fields looked wired. Measured live 2026-09-17, anonymously:

  * the by-hash VERSION payload carries no `creator` and no licence flag; its `model` sub-object
    holds `name`, `type`, `nsfw`, `poi` and nothing else -- which is exactly what the old
    `build_payload` read, and why it produced nulls rather than an error
  * `GET /api/v1/models/{id}` carries `creator.username` and all four flags
    (`allowCommercialUse` as a LIST, the other three booleans), and no licence NAME at all

The properties below are the ones that can silently stop holding: one fetch per DISTINCT model
id (532 ids behind 680 weights -- per-weight would be a 28% heavier ask for identical bytes), the
shape the Qt reader parses, and the user-override promise this subsystem has broken twice.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import backfill, civitai_lookup, hashing, refresh, sidecar

PARENT = {
    "id": 4384,
    "name": "DreamShaper",
    "type": "Checkpoint",
    "creator": {"username": "Lykon", "image": None},
    "allowCommercialUse": ["Image", "RentCivit", "Rent"],
    "allowDerivatives": True,
    "allowNoCredit": True,
    "allowDifferentLicense": True,
}

VERSION = {
    "id": 1, "modelId": 4384, "name": "V1", "baseModel": "SDXL 1.0",
    # Everything the VERSION payload really carries about its parent. No creator, no flag.
    "model": {"name": "DreamShaper", "type": "Checkpoint", "nsfw": False, "poi": False},
    "trainedWords": [], "images": [], "files": [],
}


class FakeResponse(io.BytesIO):
    status = 200

    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode("utf-8"))


class FakeOpener:
    def __init__(self, by_url):
        self.by_url = by_url
        self.urls: list[str] = []

    def open(self, request, timeout=None):
        self.urls.append(request.full_url)
        entry = self.by_url.get(request.full_url)
        if entry is None:
            raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)
        return FakeResponse(entry)


class HitClient:
    """A by-hash hit for every weight, and a parent for the ids it was given."""

    def __init__(self, parents=None):
        self.parents = {4384: PARENT} if parents is None else parents
        self.model_calls: list[int] = []

    def by_hash(self, digest):
        return dict(VERSION)

    def model(self, model_id):
        self.model_calls.append(int(model_id))
        return self.parents.get(int(model_id))


def _weight(root: Path, name: str, size: int = 32) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(name.encode()[:1] * size)
    return path


# --- the version payload is not the parent payload ---------------------------------------------


def test_the_version_payload_alone_still_produces_the_nulls_that_were_shipped():
    """The regression's own shape, pinned. Without a parent there is nothing to read, and the
    honest answer is null -- not an invented licence."""
    payload = sidecar.build_payload(
        weight=Path("w.safetensors"), sha256="a" * 64, kind="checkpoint", family="sdxl",
        civitai_version=VERSION, hf=None, recommended={},
    )
    assert payload["display"]["creator"] is None
    assert set(payload["display"]["license"]) == {"name", *sidecar.LICENSE_FLAGS}
    assert all(value is None for value in payload["display"]["license"].values())


def test_the_parent_payload_fills_creator_and_every_flag():
    payload = sidecar.build_payload(
        weight=Path("w.safetensors"), sha256="a" * 64, kind="checkpoint", family="sdxl",
        civitai_version=VERSION, hf=None, recommended={}, civitai_model=PARENT,
    )
    display = payload["display"]
    assert display["creator"] == "Lykon"
    assert display["license"]["allowCommercialUse"] == ["Image", "RentCivit", "Rent"]
    assert display["license"]["allowDerivatives"] is True
    assert display["license"]["allowNoCredit"] is True
    assert display["license"]["allowDifferentLicense"] is True
    # CivitAI states permissions, never an SPDX name. `name` stays the card's field, so a blank
    # here is the truth about CivitAI rather than a fetch that failed.
    assert display["license"]["name"] is None


def test_a_card_licence_name_survives_beside_the_civitai_flags():
    payload = sidecar.build_payload(
        weight=Path("w.safetensors"), sha256="a" * 64, kind="checkpoint", family="flux",
        civitai_version=VERSION, hf={"license": "apache-2.0"}, recommended={},
        civitai_model=PARENT,
    )
    assert payload["display"]["license"]["name"] == "apache-2.0"
    assert payload["display"]["license"]["allowNoCredit"] is True


# --- one fetch per DISTINCT model id ------------------------------------------------------------


def test_the_client_asks_for_one_model_id_once():
    url = "https://civitai.com/api/v1/models/4384"
    opener = FakeOpener({url: PARENT})
    client = civitai_lookup.CivitaiClient(opener=opener)
    assert [client.model(4384)["name"] for _ in range(3)] == ["DreamShaper"] * 3
    assert opener.urls == [url]


def test_a_model_id_the_site_does_not_know_is_asked_once_too():
    """A 404 is an answer. Re-asking it per weight is the same waste as re-asking a hit, and on a
    library where one dead id sits behind a dozen weights it is the more likely one."""
    opener = FakeOpener({})
    client = civitai_lookup.CivitaiClient(opener=opener)
    assert client.model(999) is None
    assert client.model(999) is None
    assert len(opener.urls) == 1


def test_the_backfill_fetches_once_per_distinct_id_not_once_per_weight(tmp_path: Path):
    """Three weights, two model ids. The live ratio is 532 ids behind 680 weights."""
    for index, model_id in enumerate((4384, 4384, 7808)):
        weight = _weight(tmp_path, f"w{index}.safetensors")
        sidecar.write(weight, {
            "schema": sidecar.SCHEMA,
            "identity": {"sources": [{"site": "civitai", "model_id": model_id, "version_id": 1}]},
            "display": {"creator": None, "license": {"name": None}},
            "recommended": {}, "user": {},
        })
    opener = FakeOpener({
        "https://civitai.com/api/v1/models/4384": PARENT,
        "https://civitai.com/api/v1/models/7808": {**PARENT, "id": 7808,
                                                   "creator": {"username": "rqdwdw"}},
    })
    result = backfill.BackfillJob([tmp_path],
                                  client=civitai_lookup.CivitaiClient(opener=opener)).run()
    assert result["examined"] == 3
    assert result["updated"] == 3
    assert result["distinct_model_ids"] == 2
    assert len(opener.urls) == 2


# --- a missing parent is a null, not a failed run -----------------------------------------------


def test_a_weight_whose_parent_is_a_404_still_gets_its_sidecar(tmp_path: Path):
    weight = _weight(tmp_path, "w.safetensors")
    client = HitClient(parents={})
    result = refresh.RefreshJob([tmp_path], client=client, models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["identified"] == 1
    assert result["errors"] == []
    loaded = sidecar.read(weight)
    assert loaded["display"]["creator"] is None
    assert loaded["display"]["name"]["value"] == "DreamShaper"


def test_a_parent_fetch_that_explodes_is_one_field_not_the_run(tmp_path: Path):
    class Exploding(HitClient):
        def model(self, model_id):
            raise OSError("network down")

    _weight(tmp_path, "a.safetensors", 10)
    _weight(tmp_path, "b.safetensors", 20)
    result = refresh.RefreshJob([tmp_path], client=Exploding(), models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["identified"] == 2
    assert result["lookup_failed"] == 0
    assert len(result["errors"]) == 2


def test_a_parent_we_could_not_reach_does_not_erase_the_one_we_did(tmp_path: Path):
    """The lesson `carry_forward` was written for, one field down. A refresh that cannot reach the
    parent must leave a creator a previous run established -- otherwise one throttled pass blanks
    the whole library and reports ok, which is exactly how the identity bug behaved."""
    weight = _weight(tmp_path, "w.safetensors")
    refresh.RefreshJob([tmp_path], client=HitClient(), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()
    assert sidecar.read(weight)["display"]["creator"] == "Lykon"

    class NoParent(HitClient):
        def model(self, model_id):
            raise OSError("network down")

    refresh.RefreshJob([tmp_path], client=NoParent(), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()
    loaded = sidecar.read(weight)
    assert loaded["display"]["creator"] == "Lykon"
    assert loaded["display"]["license"]["allowDerivatives"] is True


# --- the promise this subsystem has broken twice -------------------------------------------------


def test_a_user_override_survives_a_refresh_end_to_end(tmp_path: Path):
    weight = _weight(tmp_path, "w.safetensors")
    refresh.RefreshJob([tmp_path], client=HitClient(), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()

    payload = sidecar.read(weight)
    payload["display"]["name"] = {"value": "My Favourite Model", "user_override": True}
    payload["display"]["creator"] = {"value": "me", "user_override": True}
    payload["recommended"]["steps"] = {"value": 24, "provenance": "user", "confidence": 1.0,
                                       "n": None, "total": None}
    sidecar.write(weight, payload)

    refresh.RefreshJob([tmp_path], client=HitClient(), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json", force=True).run()
    loaded = sidecar.read(weight)
    assert loaded["display"]["name"]["value"] == "My Favourite Model"
    assert loaded["display"]["creator"] == {"value": "me", "user_override": True}
    assert loaded["recommended"]["steps"]["value"] == 24


def test_a_user_override_survives_the_backfill_end_to_end(tmp_path: Path):
    weight = _weight(tmp_path, "w.safetensors")
    sidecar.write(weight, {
        "schema": sidecar.SCHEMA,
        "identity": {"sources": [{"site": "civitai", "model_id": 4384, "version_id": 1}]},
        "display": {
            "name": {"value": "My Favourite Model", "user_override": True},
            "creator": {"value": "me", "user_override": True},
            "license": {"name": "apache-2.0", "user_override": True},
            "images": [{"local_path": "mine.jpg", "is_cover": True, "user_override": True}],
        },
        "recommended": {"steps": {"value": 24, "provenance": "user", "confidence": 1.0}},
        "user": {"notes": "mine", "favorite": True},
    })
    opener = FakeOpener({"https://civitai.com/api/v1/models/4384": PARENT})
    backfill.BackfillJob([tmp_path], client=civitai_lookup.CivitaiClient(opener=opener)).run()

    loaded = sidecar.read(weight)
    assert loaded["display"]["name"]["value"] == "My Favourite Model"
    assert loaded["display"]["creator"] == {"value": "me", "user_override": True}
    assert loaded["display"]["license"] == {"name": "apache-2.0", "user_override": True}
    assert loaded["display"]["images"][0]["local_path"] == "mine.jpg"
    assert loaded["recommended"]["steps"]["value"] == 24
    assert loaded["user"] == {"notes": "mine", "favorite": True}


# --- the backfill is a backfill ------------------------------------------------------------------


def test_the_backfill_changes_nothing_but_creator_and_licence(tmp_path: Path):
    weight = _weight(tmp_path, "w.safetensors")
    refresh.RefreshJob([tmp_path], client=HitClient(parents={}), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()
    before = sidecar.read(weight)

    opener = FakeOpener({"https://civitai.com/api/v1/models/4384": PARENT})
    backfill.BackfillJob([tmp_path], client=civitai_lookup.CivitaiClient(opener=opener)).run()
    after = sidecar.read(weight)

    assert after["display"]["creator"] == "Lykon"
    assert after["display"]["license"]["allowNoCredit"] is True
    before["display"].pop("creator"), after["display"].pop("creator")
    before["display"].pop("license"), after["display"].pop("license")
    assert before == after


def test_the_backfill_does_not_re_hash(tmp_path: Path, monkeypatch):
    """The whole reason this is a backfill: the 2026-09-17 pass cost 58 minutes of hashing for a
    result that already stores every model id it needs."""
    weight = _weight(tmp_path, "w.safetensors")
    refresh.RefreshJob([tmp_path], client=HitClient(parents={}), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()

    def explode(*args, **kwargs):
        raise AssertionError("the backfill hashed a weight")

    monkeypatch.setattr(hashing, "file_sha256", explode)
    monkeypatch.setattr(hashing, "hash_and_cache", explode)
    opener = FakeOpener({"https://civitai.com/api/v1/models/4384": PARENT})
    result = backfill.BackfillJob([tmp_path],
                                  client=civitai_lookup.CivitaiClient(opener=opener)).run()
    assert result["updated"] == 1
    assert sidecar.read(weight)["display"]["creator"] == "Lykon"


def test_a_sidecar_with_no_model_id_is_left_exactly_as_it_was(tmp_path: Path):
    weight = _weight(tmp_path, "w.safetensors")
    refresh.RefreshJob([tmp_path], client=HitClient(parents={}), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()
    unmatched = _weight(tmp_path, "u.safetensors", 40)
    sidecar.write(unmatched, {"schema": sidecar.SCHEMA, "identity": {"sources": []},
                              "display": {}, "recommended": {}, "user": {}})
    opener = FakeOpener({"https://civitai.com/api/v1/models/4384": PARENT})
    result = backfill.BackfillJob([tmp_path],
                                  client=civitai_lookup.CivitaiClient(opener=opener)).run()
    assert result["no_model_id"] == 1
    assert result["updated"] == 1
    assert sidecar.read(unmatched)["display"] == {}


def test_a_dry_run_reports_what_it_would_change_and_writes_nothing(tmp_path: Path):
    weight = _weight(tmp_path, "w.safetensors")
    refresh.RefreshJob([tmp_path], client=HitClient(parents={}), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()
    opener = FakeOpener({"https://civitai.com/api/v1/models/4384": PARENT})
    result = backfill.BackfillJob([tmp_path], client=civitai_lookup.CivitaiClient(opener=opener),
                                  dry_run=True).run()
    assert result["updated"] == 1
    assert sidecar.read(weight)["display"]["creator"] is None


def test_a_second_backfill_over_a_filled_library_changes_nothing(tmp_path: Path):
    weight = _weight(tmp_path, "w.safetensors")
    refresh.RefreshJob([tmp_path], client=HitClient(), models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()
    opener = FakeOpener({"https://civitai.com/api/v1/models/4384": PARENT})
    result = backfill.BackfillJob([tmp_path],
                                  client=civitai_lookup.CivitaiClient(opener=opener)).run()
    assert (result["updated"], result["unchanged"]) == (0, 1)
    assert sidecar.read(weight)["display"]["creator"] == "Lykon"
