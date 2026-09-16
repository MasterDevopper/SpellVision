"""HuggingFace metadata.

Verified live 2026-09-16: `GET /api/models/{repo}` returns cardData/siblings, and `?blobs=true`
is REQUIRED for `siblings[].lfs.sha256` -- without it there is no lfs block at all, so the flag is
what makes a sha256 -> repo index possible. HF has no by-hash endpoint, so identification only
works for repos we already know about.

The most machine-readable settings on a model card are the diffusers snippet kwargs
(`num_inference_steps=50`, `guidance_scale=3.5`), which is why they outrank prose.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import hf_lookup

FIXTURES = Path(__file__).parent / "fixtures" / "model_intelligence"


class FakeResponse(io.BytesIO):
    status = 200


class FakeOpener:
    def __init__(self, bodies):
        self.bodies = bodies
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        body = self.bodies.pop(0)
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        return FakeResponse(body.encode("utf-8"))


def _flux():
    return json.loads((FIXTURES / "hf_flux1_dev_blobs.json").read_text(encoding="utf-8"))


def test_model_info_asks_for_blobs():
    opener = FakeOpener([_flux()])
    hf_lookup.HfClient(opener=opener).model_info("black-forest-labs/FLUX.1-dev")
    assert "blobs=true" in opener.requests[0].full_url


def test_a_token_is_sent_as_a_bearer():
    opener = FakeOpener([_flux()])
    hf_lookup.HfClient(token="secret", opener=opener).model_info("x/y")
    assert opener.requests[0].get_header("Authorization") == "Bearer secret"


def test_sha256_index_maps_digests_to_filenames():
    index = hf_lookup.sha256_index(_flux())
    assert index
    assert all(len(digest) == 64 for digest in index)
    assert "ae.safetensors" in index.values()


def test_sha256_index_is_empty_without_blobs():
    assert hf_lookup.sha256_index({"siblings": [{"rfilename": "a.safetensors"}]}) == {}


def test_card_identity_reads_the_frontmatter():
    identity = hf_lookup.card_identity(_flux())
    assert identity["license"] == "other"
    assert identity["pipeline_tag"] == "text-to-image"
    assert identity["library_name"] == "diffusers"


def test_settings_from_a_diffusers_snippet():
    readme = """
    ```python
    image = pipe(prompt, num_inference_steps=50, guidance_scale=3.5, max_sequence_length=512).images[0]
    ```
    """
    found = hf_lookup.settings_from_readme(readme)
    assert found["steps"]["value"] == 50
    assert found["steps"]["provenance"] == "card:snippet-regex"
    assert found["guidance"]["value"] == 3.5


def test_settings_from_prose_when_there_is_no_snippet():
    found = hf_lookup.settings_from_readme("We recommend 8 steps and a CFG of 1.0 with shift 5.")
    assert found["steps"]["value"] == 8
    assert found["steps"]["provenance"] == "card:prose-regex"
    assert found["cfg"]["value"] == 1.0
    assert found["shift"]["value"] == 5.0


def test_a_snippet_outranks_prose():
    readme = """
    Community reports say 30 steps works well.
    ```python
    pipe(prompt, num_inference_steps=8)
    ```
    """
    assert hf_lookup.settings_from_readme(readme)["steps"]["value"] == 8


def test_nothing_found_is_empty_not_defaulted():
    assert hf_lookup.settings_from_readme("A model card with no numbers in it.") == {}
