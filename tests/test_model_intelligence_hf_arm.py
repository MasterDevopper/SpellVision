"""The HuggingFace arm, and the repo-candidate step that had to exist before it could run.

Doc 62 section 3j. `hf_lookup` was imported, exported, unit-tested and called by nothing, so the
three `card:*` tiers of the precedence order were unreachable -- and the refresh summary's
`no_match: 79, lookup_failed: 0` read as "both sites were asked" when one was.

The reason it was left is real: **HF has no by-hash endpoint.** A weight is identifiable there only
if a repo is already suspected, and `?blobs=true` confirms the guess by sha256. Measured over the
79 weights the 2026-09-17 refresh could not identify, anonymously:

    filename/folder search            21 / 79   26.6%
    + packager-scoped search          32 / 79   40.5%
    + shared repo index               38 / 79   48.1%

so the arm was wired rather than deleted. The remaining misses are weights HF does not host: the
owner's own fused LoRAs and CivitAI LoRAs nobody mirrored.

The property that makes guessing safe is the one asserted hardest below: **a candidate is only ever
accepted when its sha256 matches**, so a wrong guess costs a request and can never mislabel a file.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import hf_candidates, hf_lookup, refresh, sidecar

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


class FakeResponse(io.BytesIO):
    status = 200


class RecordingHf:
    """An HF client over a canned world. Records every question it was asked."""

    def __init__(self, repos=None, results=None, readmes=None):
        self.repos = repos or {}
        self.results = results or {}
        self.readmes = readmes or {}
        self.searched: list[tuple[str, str | None]] = []
        self.fetched: list[str] = []

    def search(self, query, *, author=None, limit=20):
        self.searched.append((query, author))
        return list(self.results.get((query, author), []))

    def model_info(self, repo):
        self.fetched.append(repo)
        return self.repos.get(repo)

    def readme(self, repo):
        return self.readmes.get(repo, "")


def _repo(*files):
    return {"siblings": [{"rfilename": name, "lfs": {"sha256": digest}}
                         for name, digest in files]}


def _weight(root: Path, name: str, size: int = 32) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(name.encode()[:1] * size)
    return path


# --- the candidate step ---------------------------------------------------------------------------


def test_the_queries_shorten_because_a_full_stem_finds_nothing():
    """`ltx-2.3-22b-distilled-lora-384-1.1` finds no repo; `ltx 2` finds `Lightricks/LTX-2.3`.
    That shortening is what turned a miss into a hit in the live measurement."""
    queries = hf_candidates.search_queries("D:/m/loras/ltx-2.3-22b-distilled-lora-384-1.1.safetensors")
    assert queries[0] == "ltx-2.3-22b-distilled-lora-384-1.1"
    assert any(q == "ltx 2 3 22b" for q in queries)
    assert queries[-1] == "loras" or "loras" not in queries


def test_a_folder_that_names_nothing_is_not_a_query():
    """`diffusion_models` is where a weight lives, not what it is. Searching it burns a request
    and returns twenty unrelated repos to fetch with `?blobs=true`."""
    assert "diffusion_models" not in hf_candidates.search_queries(
        "D:/m/diffusion_models/wan2.1_i2v_480p_14B_fp16.safetensors")


def test_an_org_repo_folder_names_its_own_repo():
    assert hf_candidates.direct_repo(
        "D:/m/facebook/dinov3-vitl16-pretrain-lvd1689m/model.safetensors"
    ) == "facebook/dinov3-vitl16-pretrain-lvd1689m"


def test_a_plain_kind_folder_is_not_a_repo():
    assert hf_candidates.direct_repo("D:/AI_ASSETS/models/loras/x.safetensors") is None


def test_a_candidate_whose_hash_does_not_match_is_never_accepted():
    """The property the whole arm rests on. The search returns a plausible, WRONG repo; the weight
    stays unidentified rather than being labelled with someone else's model."""
    client = RecordingHf(
        repos={"someone/lookalike": _repo(("model.safetensors", DIGEST_B))},
        results={("wan2.1_i2v", None): ["someone/lookalike"]},
    )
    found = hf_candidates.identify(client, weight="D:/m/loras/wan2.1_i2v.safetensors",
                                   sha256=DIGEST_A)
    assert found is None
    assert "someone/lookalike" in client.fetched


def test_a_matching_hash_returns_the_repo_and_the_file_inside_it():
    client = RecordingHf(
        repos={"org/repo": _repo(("split_files/vae/wan_vae.safetensors", DIGEST_A))},
        results={("wan_vae", None): ["org/repo"]},
    )
    found = hf_candidates.identify(client, weight="D:/m/vae/wan_vae.safetensors", sha256=DIGEST_A)
    assert found == {"repo": "org/repo", "path": "split_files/vae/wan_vae.safetensors",
                     "via": "search"}


def test_one_confirmed_repo_identifies_the_rest_of_its_bundle_without_a_search():
    """The cheapest win and the least obvious one. `llava_llama3_vision` sits in the same
    Comfy-Org repo as the Hunyuan transformer and shares no search term with it -- measured, it is
    the difference between 40.5% and 48.1%."""
    index = hf_candidates.RepoIndex(RecordingHf())
    client = RecordingHf(
        repos={"Comfy-Org/Bundle": _repo(("transformer.safetensors", DIGEST_A),
                                        ("vision.safetensors", DIGEST_B))},
        results={("transformer", None): ["Comfy-Org/Bundle"]},
    )
    index.client = client
    assert hf_candidates.identify(client, weight="D:/m/transformer.safetensors", sha256=DIGEST_A,
                                  index=index)["repo"] == "Comfy-Org/Bundle"
    client.searched.clear()
    second = hf_candidates.identify(client, weight="D:/m/unrelated_name.safetensors",
                                    sha256=DIGEST_B, index=index)
    assert second == {"repo": "Comfy-Org/Bundle", "path": "vision.safetensors", "via": "cache"}
    assert client.searched == []


def test_a_search_that_raises_is_zero_candidates_not_a_failed_run():
    class Broken(RecordingHf):
        def search(self, query, *, author=None, limit=20):
            raise OSError("dns down")

    assert hf_candidates.identify(Broken(), weight="D:/m/x.safetensors", sha256=DIGEST_A) is None


def test_the_packager_search_runs_last_and_only_on_short_queries():
    """It exists for files whose repo shares no token with them, and a long query never matches
    those. Running it first would spend seven requests per weight before the cheap answer."""
    client = RecordingHf()
    list(hf_candidates.candidate_repos(client, "D:/m/diffusion_models/hunyuan_video_t2v_720p_bf16.safetensors"))
    authored = [pair for pair in client.searched if pair[1]]
    assert authored, "no author-scoped search was attempted"
    assert client.searched.index(authored[0]) > 0
    assert set(a for _q, a in authored) == set(hf_candidates.PACKAGERS)


# --- the client ------------------------------------------------------------------------------------


def test_search_sends_the_author_filter_and_returns_repo_ids():
    class Opener:
        def __init__(self):
            self.urls = []

        def open(self, request, timeout=None):
            self.urls.append(request.full_url)
            return FakeResponse(json.dumps([{"modelId": "Comfy-Org/X"}, {"id": "Kijai/Y"}]).encode())

    opener = Opener()
    repos = hf_lookup.HfClient(opener=opener).search("hunyuan video", author="Comfy-Org")
    assert repos == ["Comfy-Org/X", "Kijai/Y"]
    assert "author=Comfy-Org" in opener.urls[0]
    assert "search=hunyuan+video" in opener.urls[0]


def test_a_query_too_short_to_mean_anything_is_not_sent():
    class Exploding:
        def open(self, request, timeout=None):
            raise AssertionError("a two-character query was sent to the API")

    assert hf_lookup.HfClient(opener=Exploding()).search("ab") == []


# --- the arm inside the refresh ---------------------------------------------------------------------


class MissingCivitai:
    def by_hash(self, digest):
        return None

    def model(self, model_id):  # pragma: no cover - never reached without a version
        raise AssertionError("no version, so no parent")


def _hf_for(weight: Path, digest: str, readme: str = "") -> RecordingHf:
    return RecordingHf(
        repos={"org/repo": _repo((f"split_files/{weight.name}", digest))},
        results={(weight.stem, None): ["org/repo"]},
        readmes={"org/repo": readme},
    )


def _digest(weight: Path) -> str:
    from model_intelligence import hashing

    return hashing.file_sha256(weight)


def test_a_weight_civitai_does_not_know_is_identified_by_huggingface(tmp_path: Path):
    weight = _weight(tmp_path, "hunyuan_video_t2v_720p_bf16.safetensors")
    hf = _hf_for(weight, _digest(weight))
    result = refresh.RefreshJob([tmp_path], client=MissingCivitai(), hf=hf, models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert (result["identified"], result["identified_hf"], result["no_match"]) == (1, 1, 0)
    sources = sidecar.read(weight)["identity"]["sources"]
    assert sources[0]["site"] == "huggingface"
    assert sources[0]["repo"] == "org/repo"
    assert sources[0]["path"].endswith(weight.name)


def test_the_card_tiers_are_reachable_for_the_first_time(tmp_path: Path):
    """The point of wiring the arm at all: until now no sidecar in a 759-model run could carry a
    `card:*` provenance, because nothing read a card."""
    weight = _weight(tmp_path, "flux_thing.safetensors")
    hf = _hf_for(weight, _digest(weight),
                 readme="```python\npipe(prompt, num_inference_steps=28, guidance_scale=3.5)\n```")
    refresh.RefreshJob([tmp_path], client=MissingCivitai(), hf=hf, models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()
    block = sidecar.read(weight)["recommended"]
    assert block["steps"]["value"] == 28
    assert block["steps"]["provenance"] == "card:snippet-regex"
    assert block["guidance"]["provenance"] == "card:snippet-regex"


def test_the_card_licence_lands_where_the_inspector_reads_it(tmp_path: Path):
    weight = _weight(tmp_path, "thing.safetensors")
    hf = _hf_for(weight, _digest(weight))
    hf.repos["org/repo"]["cardData"] = {"license": "apache-2.0", "base_model": "black-forest-labs/FLUX.1-dev"}
    refresh.RefreshJob([tmp_path], client=MissingCivitai(), hf=hf, models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()
    loaded = sidecar.read(weight)
    assert loaded["display"]["license"]["name"] == "apache-2.0"
    assert loaded["identity"]["base_model"] == "black-forest-labs/FLUX.1-dev"


def test_a_weight_neither_site_knows_is_still_a_plain_no_match(tmp_path: Path):
    weight = _weight(tmp_path, "my_own_fused_lora.safetensors")
    hf = RecordingHf()
    result = refresh.RefreshJob([tmp_path], client=MissingCivitai(), hf=hf, models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert (result["identified_hf"], result["no_match"]) == (0, 1)
    assert sidecar.read(weight)["identity"]["sources"] == []


def test_the_arm_is_skipped_entirely_without_a_client(tmp_path: Path):
    _weight(tmp_path, "w.safetensors")
    result = refresh.RefreshJob([tmp_path], client=MissingCivitai(), models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert (result["no_match"], result["identified_hf"]) == (1, 0)


def test_a_civitai_hit_that_published_settings_never_asks_huggingface(tmp_path: Path):
    """A hash CivitAI knows is already an identity. Asking HF anyway would spend up to 25 requests
    per weight across a 759-file library for nothing.

    NARROWED 2026-09-18: the clause that matters is "that published settings". A hit ends the
    search for IDENTITY, which is all a hash match establishes -- it does not end the search for
    what to render the weight with, and `tests/test_model_intelligence_card_settings.py` holds that
    half. This case keeps the cost property by giving the site something to say: three agreeing
    example images, so the block comes back carrying `site:image-meta-mode` and the second arm has
    no question left to ask.
    """
    class Hit(MissingCivitai):
        def by_hash(self, digest):
            meta = {"steps": 30, "cfgScale": 7.0, "sampler": "dpmpp_2m_karras"}
            return {"id": 1, "modelId": 2, "model": {"name": "A Model"},
                    "images": [{"meta": dict(meta)} for _ in range(3)], "files": []}

        def model(self, model_id):
            return None

    weight = _weight(tmp_path, "w.safetensors")
    hf = _hf_for(weight, _digest(weight))
    refresh.RefreshJob([tmp_path], client=Hit(), hf=hf, models_root=tmp_path,
                       cache_path=tmp_path / "cache.json").run()
    assert hf.searched == []
    assert hf.fetched == []


def test_a_lookup_that_failed_is_never_handed_to_huggingface(tmp_path: Path):
    """"CivitAI does not have it" and "we could not ask CivitAI" are different facts -- the lesson
    `carry_forward` was written for. Only the first may reach the second arm."""
    class Exploding(MissingCivitai):
        def by_hash(self, digest):
            raise OSError("network down")

    weight = _weight(tmp_path, "w.safetensors")
    hf = _hf_for(weight, _digest(weight))
    result = refresh.RefreshJob([tmp_path], client=Exploding(), hf=hf, models_root=tmp_path,
                               cache_path=tmp_path / "cache.json").run()
    assert result["lookup_failed"] == 1
    assert hf.searched == [] and hf.fetched == []


def test_an_exploding_hf_arm_is_one_file_not_the_run(tmp_path: Path):
    class Broken(RecordingHf):
        def model_info(self, repo):
            raise ValueError("unparseable")

    weight = _weight(tmp_path, "w.safetensors")
    hf = Broken(results={("w", None): ["org/repo"]})
    result = refresh.RefreshJob([tmp_path], client=MissingCivitai(), hf=hf, models_root=tmp_path,
                                cache_path=tmp_path / "cache.json").run()
    assert result["examined"] == 1
    assert result["no_match"] == 1
    assert sidecar.read(weight) is not None


# --- a throttle is not an answer ---------------------------------------------------------------


def test_a_429_is_retried_and_then_raised_rather_than_read_as_a_miss():
    """Measured the expensive way on 2026-09-17. The candidate step asks HF up to 25 times per
    unidentified weight, so a library pass WILL meet a 429; `_get` raised a bare HTTPError,
    `_search` caught it as "no candidates", and the weight was written down as not on HuggingFace.
    The pass dropped from 38 identifications to 25 and reported zero errors."""
    import urllib.error

    class Throttling:
        def __init__(self):
            self.calls = 0

        def open(self, request, timeout=None):
            self.calls += 1
            raise urllib.error.HTTPError(request.full_url, 429, "slow down", {}, None)

    opener = Throttling()
    client = hf_lookup.HfClient(opener=opener, sleep=lambda _seconds: None)
    try:
        client.search("hunyuan video")
    except hf_lookup.HfThrottled:
        pass
    else:  # pragma: no cover - the assertion below reports it
        raise AssertionError("a 429 was swallowed and read as an empty result")
    assert opener.calls == hf_lookup.MAX_ATTEMPTS


def test_a_throttled_arm_is_recorded_as_an_error_not_as_a_missing_weight(tmp_path: Path):
    class Throttled(RecordingHf):
        def search(self, query, *, author=None, limit=20):
            raise hf_lookup.HfThrottled("429 from huggingface.co after 4 attempts")

    weight = _weight(tmp_path, "hunyuan_video_t2v_720p_bf16.safetensors")
    result = refresh.RefreshJob([tmp_path], client=MissingCivitai(), hf=Throttled(),
                                models_root=tmp_path, cache_path=tmp_path / "cache.json").run()
    assert result["examined"] == 1
    assert any("huggingface" in error["error"] for error in result["errors"])
    assert sidecar.read(weight) is not None
    # The error list is not the summary. `no_match` is "HuggingFace does not host this";
    # a 429 is "we could not ask". Those used to collapse, which is how a throttled pass
    # reported `no_match: 79, lookup_failed: 0` while identifying nothing.
    assert (result["no_match"], result["lookup_failed"]) == (0, 1)
