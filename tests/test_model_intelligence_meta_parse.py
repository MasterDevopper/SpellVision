"""Turning a CivitAI example image's `meta` into settings.

Captured live 2026-09-16 (tests/fixtures/model_intelligence/): CivitAI publishes the sampler in
TWO shapes and the desk research only knew about one.

  1. Split, A1111-style   -- "sampler": "Euler",          "scheduler": "beta"
  2. Combined, Comfy-style -- "sampler": "er_sde_simple",  and no scheduler key at all

Getting (2) wrong is the expensive case: "er_sde_simple" is not a sampler ComfyUI will accept, and
a naive split on the last underscore yields "er_sde" + "simple" by luck while yielding
"dpmpp_2m_sde" -> "dpmpp_2m" + "sde" -- a real sampler and a scheduler that does not exist. So the
split is resolved against the live catalogues, longest sampler first.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import meta_parse

FIXTURES = Path(__file__).parent / "fixtures" / "model_intelligence"


def _metas(name: str) -> list[dict]:
    payload = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return [image["meta"] for image in payload.get("images", []) if image.get("meta")]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("er_sde_simple", ("er_sde", "simple")),
        ("euler", ("euler", None)),
        ("Euler", ("euler", None)),
        ("euler_ancestral_beta", ("euler_ancestral", "beta")),
        ("dpmpp_2m_sde_karras", ("dpmpp_2m_sde", "karras")),
        ("dpmpp_2m_sde", ("dpmpp_2m_sde", None)),
        ("DPM++ 2M Karras", ("dpmpp_2m", "karras")),
        ("DPM++ 2M SDE Karras", ("dpmpp_2m_sde", "karras")),
        ("Euler a", ("euler_ancestral", None)),
        ("", (None, None)),
        ("something nobody ships", (None, None)),
    ],
)
def test_split_sampler(text, expected):
    assert meta_parse.split_sampler(text) == expected


def test_the_naive_last_underscore_split_would_be_wrong():
    """dpmpp_2m_sde is a whole sampler name; 'sde' is not a scheduler."""
    sampler, scheduler = meta_parse.split_sampler("dpmpp_2m_sde")
    assert sampler == "dpmpp_2m_sde"
    assert scheduler is None


def test_parse_meta_reads_size_and_numbers():
    parsed = meta_parse.parse_meta(
        {"steps": 10, "cfgScale": 1, "sampler": "er_sde_simple", "clipSkip": 2, "Size": "832x1216"}
    )
    assert parsed["steps"] == 10
    assert parsed["cfg"] == 1.0
    assert parsed["sampler"] == "er_sde"
    assert parsed["scheduler"] == "simple"
    assert parsed["clip_skip"] == 2
    assert parsed["width"] == 832
    assert parsed["height"] == 1216


def test_parse_meta_prefers_an_explicit_scheduler_key():
    parsed = meta_parse.parse_meta({"sampler": "Euler", "scheduler": "beta"})
    assert parsed["sampler"] == "euler"
    assert parsed["scheduler"] == "beta"


def test_parse_meta_omits_what_it_cannot_read():
    parsed = meta_parse.parse_meta({"prompt": "a cat", "steps": "not a number"})
    assert "steps" not in parsed
    assert "sampler" not in parsed


def test_the_house_checkpoint_fixture_yields_ten_steps_cfg_one_er_sde_simple():
    """The owner's own model. SpellVision renders it at 52/3.5 today; its author uses 10/1."""
    modes = meta_parse.mode_over(_metas("civitai_checkpoint_combined_sampler"))
    assert modes["steps"]["value"] == 10
    assert modes["steps"]["n"] == 10
    assert modes["cfg"]["value"] == 1.0
    assert modes["sampler"]["value"] == "er_sde"
    assert modes["scheduler"]["value"] == "simple"


def test_the_lora_fixture_yields_the_split_shape():
    modes = meta_parse.mode_over(_metas("civitai_lora_split_sampler"))
    assert modes["sampler"]["value"] == "euler"
    assert modes["scheduler"]["value"] == "beta"
    assert modes["steps"]["value"] == 8
    assert modes["steps"]["n"] == 8
    assert modes["steps"]["total"] == 10


def test_mode_reports_how_many_examples_agreed():
    modes = meta_parse.mode_over(
        [{"steps": 8}, {"steps": 8}, {"steps": 30}, {"prompt": "no settings here"}]
    )
    assert modes["steps"] == {"value": 8, "n": 2, "total": 4}


def test_mode_over_nothing_is_empty():
    assert meta_parse.mode_over([]) == {}
