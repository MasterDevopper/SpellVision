"""The resolution offer: identify exactly, or substitute explicitly, or say nothing was found.

Network is always injected. The fixtures below are shaped from real Civitai responses recorded
while measuring coverage, including the wrong-asset case that motivated the type filter.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from model_resolution_offer import (  # noqa: E402
    AMBIGUOUS,
    EXACT_DOWNLOAD,
    NONE,
    SUBSTITUTE,
    build_offer,
    find_exact_download,
    search_queries,
)

CATALOG = [
    "sdxl/juggernautXL_v9.safetensors",
    "sdxl/ponyDiffusionV6XL.safetensors",
    "sdxl/hassakuXLIllustrious_v32.safetensors",
    "flux/flux1-dev.safetensors",
]


def graph(*nodes):
    return {str(i): n for i, n in enumerate(nodes)}


def node(class_type, **inputs):
    return {"class_type": class_type, "inputs": inputs}


def fetcher(responses):
    """Serve recorded payloads by the query string inside the URL."""
    calls = []

    def _fetch(url, **kwargs):
        calls.append(url)
        for needle, payload in responses.items():
            if f"query={needle}" in url.replace("+", "%20") or f"query={needle}" in url:
                return payload
        return {"items": []}

    _fetch.calls = calls
    return _fetch


def civitai_model(name, file_name, *, version="v1.0", url="https://civitai.test/dl/1", size=6_000_000.0):
    return {
        "name": name,
        "modelVersions": [
            {"name": version, "files": [{"name": file_name, "downloadUrl": url, "sizeKB": size}]}
        ],
    }


# --- query shapes -------------------------------------------------------------------------


def test_queries_go_most_specific_to_loosest():
    assert search_queries("cyberrealisticPony_v141.safetensors")[0] == "cyberrealisticPony_v141"

    queries = search_queries("JANKUTrainedNoobaiRouwei_v60.safetensors")
    assert "JANKUTrainedNoobaiRouwei" in queries
    # The split fires on lower/digit -> upper, so a leading all-caps run stays glued to the word
    # after it. "JANKUTrained Noobai Rouwei" is the exact query that returned the hit when this
    # was measured live -- pinned as-is rather than "improved" into an untested shape.
    assert "JANKUTrained Noobai Rouwei" in queries

    assert search_queries("oneObsessionBranch_matureMAXEPS.safetensors")[1] == "oneObsessionBranch"


def test_queries_of_an_empty_name_are_empty():
    assert search_queries("") == []
    assert search_queries("   ") == []


# --- identification, not search ------------------------------------------------------------


def test_exact_filename_match_is_what_produces_a_download():
    fetch = fetcher({
        "cyberrealisticPony_v141": {
            "items": [civitai_model("CyberRealistic Pony", "cyberrealisticPony_v141.safetensors",
                                    version="v14.1")]
        }
    })
    option = find_exact_download("cyberrealisticPony_v141.safetensors", fetch=fetch)
    assert option is not None
    assert option.filename == "cyberrealisticPony_v141.safetensors"
    assert option.model_name == "CyberRealistic Pony"
    assert option.version_name == "v14.1"
    assert option.match == "exact_filename"


def test_a_near_miss_is_not_offered_as_your_file():
    """The live failure: searching hassakuXLIllustrious returned a *style LoRA* named for it."""
    fetch = fetcher({
        "hassakuXLIllustrious_v32": {
            "items": [civitai_model("HassaKu | Shiiro's Styles", "hassaku_style_lora.safetensors")]
        }
    })
    assert find_exact_download("hassakuXLIllustrious_v32.safetensors", fetch=fetch) is None


def test_the_search_is_constrained_by_asset_type():
    fetch = fetcher({})
    find_exact_download("x.safetensors", kind="checkpoint", fetch=fetch)
    assert any("types=Checkpoint" in url for url in fetch.calls)

    fetch = fetcher({})
    find_exact_download("x.safetensors", kind="lora", fetch=fetch)
    assert any("types=LORA" in url for url in fetch.calls)


def test_a_search_failure_is_not_a_resolution_failure():
    def exploding_fetch(url, **kwargs):
        raise TimeoutError("civitai unreachable")

    assert find_exact_download("x.safetensors", fetch=exploding_fetch) is None


def test_a_matching_file_with_no_download_url_is_skipped():
    payload = {"items": [{"name": "M", "modelVersions": [
        {"name": "v1", "files": [{"name": "x.safetensors", "downloadUrl": ""}]}]}]}
    assert find_exact_download("x.safetensors", fetch=fetcher({"x": payload})) is None


# --- the assembled offer -------------------------------------------------------------------


def test_an_exact_match_wins_but_substitutes_stay_on_the_table():
    """A user on a metered connection with 3 compatible checkpoints should not be told to
    fetch 6 GB without being shown the alternative."""
    fetch = fetcher({
        "juggernautXL_v9": {
            "items": [civitai_model("Juggernaut XL", "juggernautXL_v9.safetensors")]
        }
    })
    offer = build_offer(
        "juggernautXL_v9.safetensors",
        graph=graph(node("EmptyLatentImage", width=1024, height=1024)),
        installed=CATALOG,
        fetch=fetch,
    )
    assert offer.state == EXACT_DOWNLOAD
    assert offer.download is not None
    assert offer.substitutes, "the substitutes are computed even when a download is available"
    assert offer.architecture == "sdxl"


def test_no_exact_match_falls_through_to_substitutes():
    offer = build_offer(
        "nova3DCGXL_ilV70.safetensors",
        graph=graph(node("EmptyLatentImage", width=1080, height=1920)),
        installed=CATALOG,
        fetch=fetcher({}),
    )
    assert offer.state == SUBSTITUTE
    assert offer.download is None
    assert [c.name for c in offer.substitutes]
    assert all(c.architecture == "sdxl" for c in offer.substitutes)
    assert offer.architecture_reason


def test_an_ambiguous_architecture_offers_no_substitute_and_says_why():
    offer = build_offer(
        "NetaYumev35_pretrained_all_in_one.safetensors",
        graph=graph(node("EmptySD3LatentImage", width=1024)),
        installed=CATALOG,
        fetch=fetcher({}),
    )
    assert offer.state == AMBIGUOUS
    assert offer.substitutes == ()
    assert "does not pin one" in " ".join(offer.notes)


def test_nothing_found_says_nothing_found():
    offer = build_offer(
        "mysteryModel.safetensors",
        graph=graph(node("SaveImage")),
        installed=[],
        fetch=fetcher({}),
    )
    assert offer.state == NONE
    assert offer.download is None
    assert offer.substitutes == ()


def test_offline_mode_skips_the_network_entirely():
    fetch = fetcher({})
    offer = build_offer(
        "nova3DCGXL_ilV70.safetensors",
        graph=graph(node("EmptyLatentImage", width=1024)),
        installed=CATALOG,
        fetch=fetch,
        search_online=False,
    )
    assert fetch.calls == []
    assert offer.state == SUBSTITUTE


def test_an_empty_name_is_not_an_offer():
    offer = build_offer("", installed=CATALOG, fetch=fetcher({}))
    assert offer.state == NONE


def test_to_dict_is_json_shaped_for_the_worker_protocol():
    offer = build_offer(
        "nova3DCGXL_ilV70.safetensors",
        graph=graph(node("EmptyLatentImage", width=1024)),
        installed=CATALOG,
        fetch=fetcher({}),
    )
    payload = offer.to_dict()
    assert payload["state"] == SUBSTITUTE
    assert payload["download"] is None
    assert payload["substitutes"][0]["name"]
    assert set(payload["substitutes"][0]) == {
        "name", "architecture", "lineage", "lineage_match", "score", "reason"
    }
    import json

    json.dumps(payload)  # must be serialisable as-is


# --- filename equality is not identity -------------------------------------------------------


def test_two_different_files_with_one_name_are_a_choice_not_a_pick():
    """`exact_download` is the strongest confidence this module has. Returning the first of
    several genuinely different artifacts would make that label a lie -- and generic names collide
    constantly (model.safetensors, pytorch_lora_weights.safetensors), while Civitai also reuses a
    name across precisions inside a single version."""
    from model_resolution_offer import AmbiguousDownload

    payload = {"items": [
        {"name": "Uploader A", "modelVersions": [{"name": "v1", "files": [
            {"name": "model.safetensors", "sizeKB": 6_000_000.0, "downloadUrl": "https://x/a"}]}]},
        {"name": "Uploader B", "modelVersions": [{"name": "v2", "files": [
            {"name": "model.safetensors", "sizeKB": 2_000_000.0, "downloadUrl": "https://x/b"}]}]},
    ]}
    with pytest.raises(AmbiguousDownload) as excinfo:
        find_exact_download("model.safetensors", fetch=fetcher({"model": payload}))

    assert len(excinfo.value.candidates) == 2
    assert "Uploader A" in str(excinfo.value) and "Uploader B" in str(excinfo.value)


def test_the_same_file_mirrored_twice_is_not_ambiguous():
    """Equal sizes mean one artifact listed twice; either copy will do."""
    payload = {"items": [
        {"name": "A", "modelVersions": [{"name": "v", "files": [
            {"name": "m.safetensors", "sizeKB": 100.0, "downloadUrl": "https://x/a"}]}]},
        {"name": "B", "modelVersions": [{"name": "v", "files": [
            {"name": "m.safetensors", "sizeKB": 100.0, "downloadUrl": "https://x/b"}]}]},
    ]}
    option = find_exact_download("m.safetensors", fetch=fetcher({"m": payload}))
    assert option is not None and option.filename == "m.safetensors"


def test_an_ambiguous_download_becomes_an_ambiguous_offer_not_a_crash():
    payload = {"items": [
        {"name": "A", "modelVersions": [{"name": "v", "files": [
            {"name": "x.safetensors", "sizeKB": 100.0, "downloadUrl": "https://x/a"}]}]},
        {"name": "B", "modelVersions": [{"name": "v", "files": [
            {"name": "x.safetensors", "sizeKB": 900.0, "downloadUrl": "https://x/b"}]}]},
    ]}
    offer = build_offer("x.safetensors", graph=graph(node("SaveImage")), installed=[],
                        fetch=fetcher({"x": payload}))
    assert offer.state == AMBIGUOUS
    assert offer.download is None
    assert "different files" in " ".join(offer.notes)
