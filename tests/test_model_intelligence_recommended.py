"""Merging every source of "what settings does this model want" into one answer.

Precedence, strongest first:
    user  >  site:image-meta-mode  >  card:snippet-regex  >  card:prose-regex  >  table:family-default

The site mode wins over a card snippet because it is what the model's OWN author rendered with,
repeatedly, rather than a generic family example. But it only wins when enough examples agree --
a single example carrying a setting is recorded with its n and given low confidence, not treated
as a recommendation.

Nothing is ever defaulted silently: a field with no source is ABSENT.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from model_intelligence import recommended

FIXTURES = Path(__file__).parent / "fixtures" / "model_intelligence"


def _version(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_the_house_checkpoint_recommends_what_its_author_renders():
    """Lox's Utopic World v2.0 Quants: 10 steps / cfg 1, unanimous over 10 examples."""
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings=None,
        family="krea2",
    )
    assert block["steps"]["value"] == 10
    assert block["steps"]["provenance"] == "site:image-meta-mode"
    assert block["steps"]["n"] == 10
    assert block["cfg"]["value"] == 1.0
    assert block["sampler"]["value"] == "er_sde"
    assert block["scheduler"]["value"] == "simple"


def test_the_family_table_fills_only_what_the_site_did_not_say():
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings=None,
        family="krea2",
    )
    # The site said nothing about canvas size for this model, so the family floor supplies it.
    assert block["width"]["provenance"] == "table:family-default"
    assert block["steps"]["provenance"] == "site:image-meta-mode"


def test_a_card_snippet_beats_the_family_table_but_loses_to_the_site():
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings={"steps": {"value": 50, "provenance": "card:snippet-regex"},
                       "guidance": {"value": 3.5, "provenance": "card:snippet-regex"}},
        family="krea2",
    )
    assert block["steps"]["value"] == 10           # site wins
    assert block["guidance"]["value"] == 3.5       # card fills what the site lacked
    assert block["guidance"]["provenance"] == "card:snippet-regex"


def test_a_user_value_beats_everything():
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings=None,
        family="krea2",
        existing_user={"steps": {"value": 24, "provenance": "user"}},
    )
    assert block["steps"]["value"] == 24
    assert block["steps"]["provenance"] == "user"


def test_a_lone_example_is_low_confidence_not_a_recommendation():
    block = recommended.build(
        civitai_version=_version("civitai_controlnet_sparse_meta"),
        card_settings=None,
        family=None,
    )
    assert block["steps"]["n"] == 1
    assert block["steps"]["confidence"] < 0.5


def test_unanimous_examples_are_high_confidence():
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings=None,
        family=None,
    )
    assert block["steps"]["confidence"] >= 0.9


def test_an_unknown_family_and_no_site_data_yields_nothing():
    assert recommended.build(civitai_version=None, card_settings=None, family="not_a_family") == {}


def test_trained_words_become_a_prompt_prefix():
    block = recommended.build(
        civitai_version=_version("civitai_lora_split_sampler"), card_settings=None, family="krea2"
    )
    assert block["prompt_prefix"]["value"] == "Character design"
    assert block["prompt_prefix"]["provenance"] == "site:trainedWords"


def test_every_value_declares_its_provenance():
    block = recommended.build(
        civitai_version=_version("civitai_lora_split_sampler"), card_settings=None, family="krea2"
    )
    assert block
    for field, entry in block.items():
        assert entry["provenance"] in recommended.PROVENANCE_ORDER, field


# --------------------------------------------------------------------------- W2: findings deferred from W1's review

def test_a_card_cannot_claim_the_user_provenance():
    """Only the user is the user. A card entry claiming "user" would outrank a unanimous site
    value AND be preserved forever by sidecar.user_values -- a permanent wrong default written by
    a third party's README."""
    block = recommended.build(
        civitai_version=_version("civitai_checkpoint_combined_sampler"),
        card_settings={"steps": {"value": 999, "provenance": "user"}},
        family="krea2",
    )
    assert block["steps"]["value"] == 10
    assert block["steps"]["provenance"] == "site:image-meta-mode"


def test_a_card_provenance_outside_the_vocabulary_is_ignored():
    block = recommended.build(
        civitai_version=None,
        card_settings={"steps": {"value": 999, "provenance": "totally-made-up"}},
        family="krea2",
    )
    assert block["steps"]["provenance"] == "table:family-default"


def test_a_lone_example_does_not_outrank_a_card_snippet():
    """The spec's n>=3 gate. One uploader's single example is evidence, not a recommendation."""
    block = recommended.build(
        civitai_version=_version("civitai_controlnet_sparse_meta"),  # steps present in 1 of 4
        card_settings={"steps": {"value": 28, "provenance": "card:snippet-regex"}},
        family=None,
    )
    assert block["steps"]["value"] == 28
    assert block["steps"]["provenance"] == "card:snippet-regex"


def test_a_lone_example_still_beats_nothing():
    """Below the gate it is demoted, not discarded -- it still outranks the family floor."""
    block = recommended.build(
        civitai_version=_version("civitai_controlnet_sparse_meta"),
        card_settings=None,
        family="krea2",
    )
    assert block["steps"]["value"] == 8
    assert block["steps"]["provenance"] == "site:image-meta-weak"
    assert block["steps"]["n"] == 1


def test_three_agreeing_examples_clear_the_gate():
    version = {"images": [{"meta": {"steps": 7}} for _ in range(3)]}
    block = recommended.build(civitai_version=version, card_settings=None, family=None)
    assert block["steps"]["provenance"] == "site:image-meta-mode"
