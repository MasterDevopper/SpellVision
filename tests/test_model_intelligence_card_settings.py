"""A CivitAI hit is an identity, not a set of settings.

The gap this file holds, measured over the owner's 759 sidecars on 2026-09-18:

    family            models   with a publisher-stated setting
    sdxl                 287   269
    illustrious           80    69
    pony                  52    48
    wan                   64    26
    ltx                   21     0
    hunyuan_video          7     0
    mochi                  2     0

**T5 was image-only.** Every video family fell back entirely to `family_seed_table` -- the floor the
whole model-defaults arc exists to replace. Not for want of supply: `settings_from_readme` on
`Lightricks/LTX-2.3` returns `steps 8 / cfg 1` at `card:prose-regex`, agreeing with the distilled
two-stage route CLAUDE.md S6 records. The cause was structural -- CivitAI HAS those files, the
second arm only ever ran on a MISS, and a CivitAI video post's `images[].meta` carries no sampler
settings.

The whole change rests on one property, and it is asserted here first rather than assumed from the
table: **a card value can never outrank a `site:image-meta-mode` value.** If that holds, consulting
the card more often cannot corrupt a good answer -- it can only fill a field the site left empty --
and the cost gate becomes a cost gate rather than a safety one.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import (
    card_settings,
    hashing,
    hf_lookup,
    recommended,
    refresh,
    settings_backfill,
    sidecar,
)

LTX_README = """
# LTX-2.3

The distilled two-stage route samples in 8 steps with the guiders pinned at cfg 1.
"""


class RecordingHf:
    """An HF client over a canned world, recording every question asked."""

    def __init__(self, repos=None, results=None, readmes=None):
        self.repos = repos or {}
        self.results = results or {}
        self.readmes = readmes or {}
        self.searched: list[tuple[str, str | None]] = []
        self.fetched: list[str] = []
        self.readme_calls: list[str] = []

    def search(self, query, *, author=None, limit=20):
        self.searched.append((query, author))
        return list(self.results.get((query, author), []))

    def model_info(self, repo):
        self.fetched.append(repo)
        return self.repos.get(repo)

    def readme(self, repo):
        self.readme_calls.append(repo)
        return self.readmes.get(repo, "")


class CivitaiKnowsIt:
    """CivitAI has the file. What it publishes about it is the argument of each case."""

    def __init__(self, images=None):
        self.images = images if images is not None else []

    def by_hash(self, digest):
        return {"id": 11, "modelId": 22, "baseModel": "LTX-Video",
                "model": {"name": "LTX 2.3 22B"}, "images": list(self.images), "files": []}

    def model(self, model_id):
        return {"id": 22, "creator": {"username": "Lightricks"}, "allowCommercialUse": ["Image"]}


def _weight(root: Path, name: str, size: int = 48) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(name.encode()[:1] * size)
    return path


def _repo(*files):
    return {"siblings": [{"rfilename": name, "lfs": {"sha256": digest}}
                         for name, digest in files]}


def _hf_holding(weights: dict[Path, str], repo: str = "Lightricks/LTX-2.3",
                readme: str = LTX_README) -> RecordingHf:
    """One repo holding every named weight, findable by the FIRST weight's stem only.

    The others share no search term with it on purpose -- that is the shared-index property the
    cost control rests on, and it is what makes 21 LTX files cost one confirmation.
    """
    first = next(iter(weights))
    return RecordingHf(
        repos={repo: _repo(*[(f"split_files/{p.name}", d) for p, d in weights.items()])},
        results={(first.stem, None): [repo]},
        readmes={repo: readme},
    )


def _digest(weight: Path) -> str:
    return hashing.file_sha256(weight)


# --- the property that makes the change safe -------------------------------------------------


def test_a_card_value_never_outranks_the_sites_own_example_images():
    """The regression guard for the whole change, asserted against the ONE precedence function
    rather than against the table that documents it. If this ever flips, consulting the card more
    often stops being free and starts overwriting the best evidence there is."""
    meta = {"steps": 30, "cfgScale": 7.0}
    version = {"images": [{"meta": dict(meta)} for _ in range(4)]}
    block = recommended.build(
        civitai_version=version,
        card_settings={"steps": {"value": 8, "provenance": "card:prose-regex"},
                       "cfg": {"value": 1.0, "provenance": "card:snippet-regex"}},
        family="ltx",
    )
    assert block["steps"]["value"] == 30
    assert block["steps"]["provenance"] == "site:image-meta-mode"
    assert block["cfg"]["value"] == 7.0
    assert block["cfg"]["provenance"] == "site:image-meta-mode"


def test_a_card_value_does_fill_a_field_the_site_left_empty():
    """The other half of the same sentence. Without this, the guard above is satisfied by a card
    that is ignored entirely, which is the state this work exists to change."""
    version = {"images": [{"meta": {"steps": 30}} for _ in range(4)]}
    block = recommended.build(
        civitai_version=version,
        card_settings={"cfg": {"value": 1.0, "provenance": "card:prose-regex"}},
        family="ltx",
    )
    assert block["steps"]["provenance"] == "site:image-meta-mode"
    assert (block["cfg"]["value"], block["cfg"]["provenance"]) == (1.0, "card:prose-regex")


# --- the gate --------------------------------------------------------------------------------


def test_a_block_with_any_site_value_is_not_asked_about():
    assert card_settings.needs_card_settings(
        {"steps": {"value": 8, "provenance": "table:family-default"}}) is True
    assert card_settings.needs_card_settings(
        {"steps": {"value": 8, "provenance": "site:image-meta-weak"}}) is False
    assert card_settings.needs_card_settings(
        {"prompt_prefix": {"value": "x", "provenance": "site:trainedWords"}}) is False
    assert card_settings.needs_card_settings({}) is True


# --- the mirror --------------------------------------------------------------------------------


def test_a_mirror_with_a_stub_card_does_not_end_the_search(tmp_path: Path):
    """MEASURED live, and it is why the first pass moved 1 of 21 LTX weights.

    `Lightricks/LTX-2.3`'s card really does yield `steps 8 / cfg 1`. But the owner's
    `ltx-2.3-22b-dev.safetensors` confirms `asheng386/LTX-2.3` for one copy and
    `darksidewalker/DaSiWa-LTX2.3` for another, because `identify` accepts the FIRST candidate whose
    sha256 matches and the free-text search ranks re-uploads ahead of the publisher. The hash match
    is correct -- a mirror holds identical bytes -- and the card beside it is a stub.

    Identity is settled by the time this runs, and every further repo must ALSO hold the digest, so
    the worst case is a different mirror of the same bytes.
    """
    weight = _weight(tmp_path, "ltx-2.3-22b-dev.safetensors")
    digest = _digest(weight)
    client = RecordingHf(
        repos={"someone/mirror": _repo(("ltx.safetensors", digest)),
               "Lightricks/LTX-2.3": _repo(("ltx.safetensors", digest))},
        # The mirror ranks first, exactly as the live search returns it.
        results={("ltx-2.3-22b-dev", None): ["someone/mirror", "Lightricks/LTX-2.3"]},
        readmes={"someone/mirror": "# A re-upload\n\nNo settings here.",
                 "Lightricks/LTX-2.3": LTX_README},
    )
    reader = card_settings.CardReader(client)
    card, settings = reader.read(weight=weight, sha256=digest)

    assert settings["steps"]["value"] == 8
    assert settings["steps"]["provenance"] == "card:prose-regex"
    assert card["repo"] == "Lightricks/LTX-2.3"
    assert reader.mirrors_used == 1


def test_the_first_repo_wins_when_its_own_card_states_something(tmp_path: Path):
    """The mirror walk is a FALLBACK, not a preference. A confirmed repo whose card answers must
    not cost six more requests per weight across a 759-file library."""
    weight = _weight(tmp_path, "ltx-2.3-22b-dev.safetensors")
    digest = _digest(weight)
    client = RecordingHf(
        repos={"someone/mirror": _repo(("ltx.safetensors", digest)),
               "Lightricks/LTX-2.3": _repo(("ltx.safetensors", digest))},
        results={("ltx-2.3-22b-dev", None): ["someone/mirror", "Lightricks/LTX-2.3"]},
        readmes={"someone/mirror": LTX_README, "Lightricks/LTX-2.3": LTX_README},
    )
    reader = card_settings.CardReader(client)
    card, settings = reader.read(weight=weight, sha256=digest)

    assert settings["steps"]["value"] == 8
    assert card["repo"] == "someone/mirror"
    assert reader.mirrors_used == 0
    # `Lightricks/LTX-2.3` is never fetched at all. (`direct_repo` also offers `<parent>/<dir>`,
    # which under pytest's tmp_path is a plausible-looking pair that 404s -- that is one wasted
    # request per weight in the fixture, not a second pass over the candidates.)
    assert "Lightricks/LTX-2.3" not in client.fetched
    assert client.fetched[-1] == "someone/mirror"


def test_the_mirror_walk_does_not_search_the_same_weight_twice(tmp_path: Path):
    """The candidate list is a GENERATOR that issues a search only when asked for more, and the
    mirror walk is a second consumer of it. Re-deriving it would re-issue up to 22 searches for a
    weight already searched for -- and the anonymous SEARCH limit is what a library pass runs into
    first, measured at 48 throttled weights in 172. `tee` is what makes one pass serve both.

    Asserted as an exact list, not a count, because "no query is repeated" is the property; a
    looser check would pass against a second pass that happened to be shorter.
    """
    weight = _weight(tmp_path, "ltx-2.3-22b-dev.safetensors")
    digest = _digest(weight)
    client = RecordingHf(
        repos={"someone/mirror": _repo(("ltx.safetensors", digest)),
               "Lightricks/LTX-2.3": _repo(("ltx.safetensors", digest))},
        results={("ltx-2.3-22b-dev", None): ["someone/mirror"],
                 ("ltx 2 3 22b", None): ["Lightricks/LTX-2.3"]},
        readmes={"someone/mirror": "# A re-upload\n\nNo settings here.",
                 "Lightricks/LTX-2.3": LTX_README},
    )
    reader = card_settings.CardReader(client)
    _card, settings = reader.read(weight=weight, sha256=digest)

    assert settings["steps"]["value"] == 8
    assert len(client.searched) == len(set(client.searched)), \
        f"a query was issued twice: {client.searched}"


# --- the arm, inside the refresh ---------------------------------------------------------------


def test_a_video_weight_civitai_identified_and_said_nothing_about_resolves_to_a_card_tier(tmp_path: Path):
    """The whole point. CivitAI holds `ltx-2.3-22b-dev` and publishes no sampler settings for it,
    so before this the weight resolved `steps` from `table:family-default` -- the family floor the
    arc exists to replace. It now resolves 8 at `card:prose-regex`, from Lightricks' own card."""
    weight = _weight(tmp_path, "ltx-2.3-22b-dev.safetensors")
    hf = _hf_holding({weight: _digest(weight)})
    result = refresh.RefreshJob([tmp_path], client=CivitaiKnowsIt(), hf=hf, models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()

    assert result["settings_from_card"] == 1
    block = sidecar.read(weight)["recommended"]
    assert block["steps"]["value"] == 8
    assert block["steps"]["provenance"] == "card:prose-regex"
    assert block["cfg"]["value"] == 1
    assert block["cfg"]["provenance"] == "card:prose-regex"


def test_the_civitai_identity_is_not_overwritten_by_the_card(tmp_path: Path):
    """Identity stays CivitAI's. The card is consulted for SETTINGS; a repo that happens to state
    a different base model or a different name must not rename a confirmed weight."""
    weight = _weight(tmp_path, "ltx-2.3-22b-dev.safetensors")
    hf = _hf_holding({weight: _digest(weight)})
    hf.repos["Lightricks/LTX-2.3"]["cardData"] = {"license": "other", "base_model": "some/other-model"}
    refresh.RefreshJob([tmp_path], client=CivitaiKnowsIt(), hf=hf, models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()

    loaded = sidecar.read(weight)
    assert loaded["display"]["name"]["value"] == "LTX 2.3 22B"
    assert loaded["identity"]["base_model"] == "LTX-Video"
    assert loaded["display"]["creator"] == "Lightricks"
    # And the second site is still DISCLOSED -- where the settings came from is part of the answer.
    sites = [source.get("site") for source in loaded["identity"]["sources"]]
    assert sites == ["civitai", "huggingface"]


def test_a_site_that_did_publish_settings_keeps_them_over_the_card(tmp_path: Path):
    """End to end through the refresh, not only through `recommended.build`: the gate means the
    card is never even fetched here, and if it were, the order would still hold."""
    images = [{"meta": {"steps": 30, "cfgScale": 7.0}} for _ in range(4)]
    weight = _weight(tmp_path, "ltx-2.3-22b-dev.safetensors")
    hf = _hf_holding({weight: _digest(weight)})
    refresh.RefreshJob([tmp_path], client=CivitaiKnowsIt(images=images), hf=hf,
                       models_root=tmp_path, cache_path=tmp_path / "cache.json").run()

    block = sidecar.read(weight)["recommended"]
    assert block["steps"]["value"] == 30
    assert block["steps"]["provenance"] == "site:image-meta-mode"
    assert hf.searched == [] and hf.fetched == []


def test_one_confirmed_repo_serves_the_rest_of_its_files_and_its_readme_once(tmp_path: Path):
    """The cost control the brief asked for, as a property. LTX is 21 files in one repo; this is
    three, two of which share no search term with the first, and the run must cost one search and
    one README fetch."""
    first = _weight(tmp_path, "ltx-2.3-22b-dev.safetensors")
    second = _weight(tmp_path, "unrelated_encoder.safetensors", size=64)
    third = _weight(tmp_path, "other_vae.safetensors", size=80)
    hf = _hf_holding({first: _digest(first), second: _digest(second), third: _digest(third)})

    result = refresh.RefreshJob([tmp_path], client=CivitaiKnowsIt(), hf=hf, models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()

    assert result["settings_from_card"] == 3
    # Fetched ONCE for three weights, and searched for only by the one file whose stem names it.
    # (`direct_repo` also offers `<parent>/<dir>` for any weight, which under pytest's tmp_path is
    # a plausible-looking pair -- that is one 404 per weight, not a repeat of the confirmed repo.)
    assert hf.fetched.count("Lightricks/LTX-2.3") == 1
    assert hf.searched == [("ltx-2.3-22b-dev", None)]
    assert hf.readme_calls == ["Lightricks/LTX-2.3"]


def test_a_throttled_card_read_is_an_error_not_a_weight_with_no_settings(tmp_path: Path):
    """`HfThrottled` exists because a 429 was once read as "not on HuggingFace" and cost 13
    identifications while reporting zero errors. The same trap is open on this path."""
    from model_intelligence import hf_lookup

    class Throttled(RecordingHf):
        def search(self, query, *, author=None, limit=20):
            raise hf_lookup.HfThrottled("429 from huggingface.co after 4 attempts")

    weight = _weight(tmp_path, "ltx-2.3-22b-dev.safetensors")
    result = refresh.RefreshJob([tmp_path], client=CivitaiKnowsIt(), hf=Throttled(),
                                models_root=tmp_path, cache_path=tmp_path / "cache.json").run()

    assert result["settings_from_card"] == 0
    assert any("huggingface" in error["error"] for error in result["errors"])
    # And the weight is still identified by CivitAI -- a card we could not read costs settings,
    # never an identity.
    assert result["identified"] == 1
    assert sidecar.read(weight)["display"]["name"]["value"] == "LTX 2.3 22B"


# --- the sidecar backfill ----------------------------------------------------------------------
#
# `refresh` only helps a library somebody re-refreshes, and the full pass cost 58 minutes of
# hashing. These sidecars are already written and already store the sha256 that confirms a repo.


DIGEST = "c" * 64


def _sidecar(root: Path, name: str, *, recommended_block, sources=None, digest=DIGEST):
    weight = root / name
    weight.parent.mkdir(parents=True, exist_ok=True)
    weight.write_bytes(b"x")
    payload = {
        "schema": sidecar.SCHEMA,
        "identity": {"file_name": name, "hashes": {"sha256": digest}, "family": "ltx",
                     "sources": sources if sources is not None else [{"site": "civitai", "model_id": 7}]},
        "display": {},
        "recommended": recommended_block,
        "user": {"notes": "", "favorite": False},
    }
    path = sidecar.write(weight, payload)
    return weight, path


def test_the_backfill_fills_a_table_only_block_and_names_where_it_came_from(tmp_path: Path):
    weight, _path = _sidecar(
        tmp_path, "ltx-2.3-22b-dev.safetensors",
        recommended_block={"steps": {"value": 8, "provenance": "table:family-default",
                                     "confidence": 1.0, "n": None, "total": None},
                           "cfg": {"value": 1.0, "provenance": "table:family-default",
                                   "confidence": 1.0, "n": None, "total": None}})
    hf = RecordingHf(
        repos={"Lightricks/LTX-2.3": _repo(("ltx.safetensors", DIGEST))},
        results={("ltx-2.3-22b-dev", None): ["Lightricks/LTX-2.3"]},
        readmes={"Lightricks/LTX-2.3": LTX_README},
    )
    result = settings_backfill.SettingsBackfillJob([tmp_path], hf=hf).run()

    assert (result["updated"], result["lookup_failed"]) == (1, 0)
    loaded = sidecar.read(weight)
    assert loaded["recommended"]["steps"]["provenance"] == "card:prose-regex"
    assert loaded["recommended"]["steps"]["value"] == 8
    # WHERE it came from is part of the answer: a number under a provenance caption whose source is
    # not in the file is the defect this whole arc is about.
    assert [s["site"] for s in loaded["identity"]["sources"]] == ["civitai", "huggingface"]
    assert loaded["identity"]["sources"][1]["repo"] == "Lightricks/LTX-2.3"


def test_the_backfill_never_touches_a_value_the_user_set(tmp_path: Path):
    weight, _path = _sidecar(
        tmp_path, "ltx-2.3-22b-dev.safetensors",
        recommended_block={"steps": {"value": 40, "provenance": "user",
                                     "confidence": 1.0, "n": None, "total": None}})
    hf = RecordingHf(
        repos={"Lightricks/LTX-2.3": _repo(("ltx.safetensors", DIGEST))},
        results={("ltx-2.3-22b-dev", None): ["Lightricks/LTX-2.3"]},
        readmes={"Lightricks/LTX-2.3": LTX_README},
    )
    settings_backfill.SettingsBackfillJob([tmp_path], hf=hf).run()

    block = sidecar.read(weight)["recommended"]
    assert (block["steps"]["value"], block["steps"]["provenance"]) == (40, "user")
    # And the card still fills the field the user said nothing about.
    assert block["cfg"]["provenance"] == "card:prose-regex"


def test_a_sidecar_the_site_already_answered_is_skipped_without_a_request(tmp_path: Path):
    _sidecar(tmp_path, "known.safetensors",
             recommended_block={"steps": {"value": 30, "provenance": "site:image-meta-mode",
                                          "confidence": 1.0, "n": 5, "total": 5}})
    hf = RecordingHf()
    result = settings_backfill.SettingsBackfillJob([tmp_path], hf=hf).run()

    assert (result["skipped_has_site"], result["updated"]) == (1, 0)
    assert hf.searched == [] and hf.fetched == []


def test_a_throttled_backfill_leaves_the_file_alone_and_says_so(tmp_path: Path):
    from model_intelligence import hf_lookup

    class Throttled(RecordingHf):
        def search(self, query, *, author=None, limit=20):
            raise hf_lookup.HfThrottled("429 from huggingface.co after 4 attempts")

    weight, _path = _sidecar(
        tmp_path, "ltx-2.3-22b-dev.safetensors",
        recommended_block={"steps": {"value": 8, "provenance": "table:family-default",
                                     "confidence": 1.0, "n": None, "total": None}})
    result = settings_backfill.SettingsBackfillJob([tmp_path], hf=Throttled()).run()

    assert (result["lookup_failed"], result["updated"]) == (1, 0)
    assert sidecar.read(weight)["recommended"]["steps"]["provenance"] == "table:family-default"


def test_a_dry_run_reports_what_it_would_write_and_writes_nothing(tmp_path: Path):
    weight, _path = _sidecar(
        tmp_path, "ltx-2.3-22b-dev.safetensors",
        recommended_block={"steps": {"value": 8, "provenance": "table:family-default",
                                     "confidence": 1.0, "n": None, "total": None}})
    hf = RecordingHf(
        repos={"Lightricks/LTX-2.3": _repo(("ltx.safetensors", DIGEST))},
        results={("ltx-2.3-22b-dev", None): ["Lightricks/LTX-2.3"]},
        readmes={"Lightricks/LTX-2.3": LTX_README},
    )
    result = settings_backfill.SettingsBackfillJob([tmp_path], hf=hf, dry_run=True).run()

    assert result["updated"] == 1
    assert sidecar.read(weight)["recommended"]["steps"]["provenance"] == "table:family-default"


# --- a card states sampling, never a canvas ------------------------------------------------------
#
# Measured over the live library on 2026-09-18, after the arm started reading cards at scale: every
# canvas value the snippet route produced was wrong.
#
#   LTX23_video_vae_bf16   width 50             (`width` matched prose that is not a canvas)
#   wan2.2_vae             512x512, 24 frames   (a VAE repo's demo snippet)
#   wan2.2_*_pov_* LoRAs   854x480, 16f @ 8fps  (a LoRA pack's demo snippet)
#
# `num_inference_steps=28` is the author stating how to sample this weight. `height=512` beside it
# is boilerplate from the diffusers template, copied into thousands of cards.


def test_a_card_snippet_states_sampling_and_not_a_canvas():
    body = """```python
pipe(prompt, num_inference_steps=28, guidance_scale=3.5, height=512, width=512, num_frames=81, fps=24)
```"""
    out = hf_lookup.settings_from_readme(body)
    assert out["steps"]["value"] == 28
    assert out["guidance"]["value"] == 3.5
    for canvas in ("width", "height", "frames", "fps"):
        assert canvas not in out, f"a card snippet claimed {canvas}, which it cannot honestly state"


def test_a_sidecar_that_already_claims_a_card_canvas_is_pruned(tmp_path: Path):
    """The READ side of the same fact, so a file written by the version that could claim a canvas
    stops displaying one -- no schema bump, no re-running the 58-minute refresh. Only `card:*` is
    touched: a site-stated canvas is exactly the evidence this arc exists to surface."""
    weight, _path = _sidecar(
        tmp_path, "LTX23_video_vae_bf16.safetensors",
        recommended_block={
            "steps": {"value": 8, "provenance": "card:prose-regex",
                      "confidence": 1.0, "n": None, "total": None},
            "width": {"value": 50, "provenance": "card:snippet-regex",
                      "confidence": 1.0, "n": None, "total": None},
            "height": {"value": 512, "provenance": "site:image-meta-mode",
                       "confidence": 1.0, "n": 5, "total": 5},
        })
    result = settings_backfill.SettingsBackfillJob([tmp_path], hf=RecordingHf()).run()

    assert result["pruned"] == 1
    block = sidecar.read(weight)["recommended"]
    assert "width" not in block
    assert block["steps"]["value"] == 8                      # a card MAY state sampling
    assert block["height"]["provenance"] == "site:image-meta-mode"  # the site MAY state a canvas


def test_the_prune_runs_even_on_a_sidecar_the_gate_skips(tmp_path: Path):
    """It costs no request, so a pass cleans every file -- including the 587 the gate skips and the
    ones a 429 stops short of. A cleanup that only reached the weights being fetched would leave
    exactly the files nobody is going to fetch again."""
    weight, _path = _sidecar(
        tmp_path, "already_known.safetensors",
        recommended_block={
            "steps": {"value": 30, "provenance": "site:image-meta-mode",
                      "confidence": 1.0, "n": 5, "total": 5},
            "fps": {"value": 8, "provenance": "card:snippet-regex",
                    "confidence": 1.0, "n": None, "total": None},
        })
    hf = RecordingHf()
    result = settings_backfill.SettingsBackfillJob([tmp_path], hf=hf).run()

    assert (result["pruned"], result["skipped_has_site"]) == (1, 1)
    assert hf.searched == [] and hf.fetched == []
    assert "fps" not in sidecar.read(weight)["recommended"]


def test_the_resolver_ignores_a_card_canvas_without_waiting_for_a_backfill(tmp_path: Path):
    """The prune rewrites a file, and a file is only rewritten on a pass. This is the same gate on
    the READ, so a sidecar from any version resolves the same way with no pass at all -- the
    reasoning `resolve._apply_quorum` already carries for the mode quorum.

    Both halves: the card canvas is refused AND the family's own value arrives in its place, so the
    case cannot be satisfied by a resolver that simply answered nothing.
    """
    from model_intelligence import resolve

    answer = resolve.resolve_model_defaults(
        path="D:/m/checkpoints/x.safetensors", family="sdxl", mode="t2i",
        sidecar_payload={"recommended": {
            "width": {"value": 50, "provenance": "card:snippet-regex",
                      "confidence": 1.0, "n": None, "total": None},
            "steps": {"value": 8, "provenance": "card:prose-regex",
                      "confidence": 1.0, "n": None, "total": None},
        }},
    )
    settings = answer["settings"]
    assert settings["width"]["value"] == 1024                      # sdxl's own, not the card's 50
    assert settings["width"]["provenance"].startswith("table:")
    assert (settings["steps"]["value"], settings["steps"]["provenance"]) == (8, "card:prose-regex")
