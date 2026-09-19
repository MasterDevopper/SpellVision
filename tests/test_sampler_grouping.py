"""Known-good samplers in Simple, everything the build has in Advanced, ONE dropdown.

Owner ruling (Doc 62), verbatim: "we will put the samplers that are known good with the models only
in basic mode but advanced mode will offer all as a distinctly separated from the others
continuation in the same dropdown."

So the control never moves, the head of the list is identical in both modes, and Advanced grows it
downward past a labelled separation. These tests own the PYTHON half -- what the two groups contain
and where "known good" comes from. The rendering half (separator, order, and the promise that a
mode switch never changes the selection) is `tests/cpp/test_sampling_controller.cpp`.

The fact that makes this a build and not a data edit: before it,
`FAMILY_SAMPLER_ALLOWLISTS[family]["samplers"]` was applied to the dropdown for NO family. The
tuples were read by `model_intelligence.resolve` to validate a published value and by nothing else,
so adding a family row changed no list anywhere. `family_sampling_choices` returned the whole live
KSampler catalog to every caller. This grouping is their first consumer.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import family_operating_points as fop  # noqa: E402

# A live KSampler list, trimmed. It deliberately contains names no family table mentions (`heun`,
# `dpmpp_3m_sde`, `lms`) -- those are the "everything else this build offers" that Advanced reveals.
LIVE_SAMPLERS = ["euler", "er_sde", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_3m_sde",
                 "euler_ancestral", "ddim", "heun", "lms", "res_multistep",
                 "euler_ancestral_cfg_pp", "euler_cfg_pp"]
LIVE_SCHEDULERS = ["simple", "normal", "karras", "sgm_uniform", "beta", "exponential"]


def choices(family, **kwargs):
    return fop.family_sampling_choices(
        family, live_samplers=LIVE_SAMPLERS, live_schedulers=LIVE_SCHEDULERS, **kwargs)


def test_the_two_groups_partition_what_the_build_offers():
    """Every sampler the build has is in exactly one group. A name in neither would be a sampler
    the user cannot reach in either mode -- which is what an allow-list applied to the dropdown
    WOULD have done, and is precisely what this ruling refuses."""
    c = choices("krea2")
    known, other = c["known_good_samplers"], c["other_samplers"]
    assert set(known) | set(other) == set(LIVE_SAMPLERS)
    assert not set(known) & set(other)


def test_simple_offers_the_family_table_and_advanced_continues_past_it():
    c = choices("krea2")
    # krea2_image declares ("euler", "er_sde"), er_sde is its default, and both are live.
    assert c["known_good_samplers"] == ["er_sde", "euler"]
    assert "heun" in c["other_samplers"]
    assert "heun" not in c["known_good_samplers"]


def test_the_known_good_head_is_the_head_of_the_advanced_list_too():
    """"Advanced reveals in place" is only true if nothing above the separation MOVES. The head is
    one list, rendered twice, and Advanced appends to it."""
    c = choices("sdxl")
    advanced_order = c["known_good_samplers"] + c["other_samplers"]
    assert advanced_order[:len(c["known_good_samplers"])] == c["known_good_samplers"]
    # The family's default leads, because that is what Auto resolves to and a user scanning the
    # list should meet it first.
    assert c["known_good_samplers"][0] == c["default_sampler"] == "dpmpp_2m"


def test_a_model_publishing_a_sampler_its_family_never_named_makes_it_known_good():
    """The richer of the two sources. 483 of 759 weights now carry a site-sourced sampler, and it
    is per-MODEL where the table is per-family -- so a weight whose author samples with dpmpp_3m_sde
    puts dpmpp_3m_sde in Simple for that weight, and leaves it in the tail for every other."""
    c = choices("krea2", model_sampler="dpmpp_3m_sde")
    assert "dpmpp_3m_sde" in c["known_good_samplers"]
    assert "dpmpp_3m_sde" not in c["other_samplers"]
    assert "dpmpp_3m_sde" in choices("krea2")["other_samplers"]


def test_a_published_scheduler_is_known_good_the_same_way():
    c = choices("krea2", model_scheduler="karras")
    assert "karras" in c["known_good_schedulers"]
    assert "karras" not in c["other_schedulers"]


def test_a_family_with_no_table_row_and_a_silent_model_still_offers_something():
    """THE FALLBACK IS THE POINT. An empty Simple dropdown is worse than the over-broad one this
    replaces: the user would have no sampler at all where they used to have sixty-three. A family
    with no curated tuple falls back to the default -- which every family has, because
    `_assert_every_family_declares_a_default` refuses the import otherwise."""
    c = choices("cogvideox")  # no FAMILY_SAMPLER_ALLOWLISTS row, no operating point
    assert c["known_good_samplers"] == [c["default_sampler"]]
    assert c["known_good_samplers"], "Simple would show an empty sampler list"


def test_a_family_that_declares_no_scheduler_at_all_stays_empty():
    """LTX's `schedulers` tuple is deliberately `()`: both its templates drive sigmas through
    ManualSigmas, so there is nothing to choose. Empty there is a STATEMENT, not an omission, and
    the fallback above must not overturn it -- nor may a scheduler the model published."""
    assert choices("ltx")["known_good_schedulers"] == []
    assert choices("ltx", model_scheduler="karras")["known_good_schedulers"] == []
    assert choices("ltx")["known_good_samplers"] == [
        "euler_ancestral_cfg_pp", "euler_cfg_pp", "euler"]


def test_a_known_good_name_the_build_does_not_have_is_in_neither_group():
    """Both groups are intersected with the live list. A curated name this build cannot run would
    otherwise sit at the top of Simple and 400 at the queue -- the one failure this resolver exists
    to prevent."""
    c = fop.family_sampling_choices("sdxl", live_samplers=["euler", "heun"],
                                    live_schedulers=["simple"])
    assert c["known_good_samplers"] == ["euler"]      # dpmpp_2m / ddim / ... are not in this build
    assert c["other_samplers"] == ["heun"]


def test_the_flat_list_is_unchanged_for_every_reader_that_predates_the_ruling():
    """`samplers` and `schedulers` keep their exact old contents and order. The builder validates
    against them, and under this ruling it must keep accepting anything the build offers."""
    c = choices("krea2")
    assert set(c["samplers"]) == set(LIVE_SAMPLERS)
    assert c["samplers"][0] == c["default_sampler"]
    assert c["samplers"] == sorted(LIVE_SAMPLERS, key=lambda n: (n != c["default_sampler"], n))


def test_the_grouping_reaches_the_cockpit_through_the_model_defaults_reply():
    """The per-model half can only be known where the model is known, so `model_recommended_settings`
    carries the finished pair. The C++ applies what it is handed and merges nothing -- a rule that
    lives in two places drifts in one of them."""
    import model_intelligence_commands as mic

    reply = mic.handle_model_recommended_settings_command(
        {"family": "krea2", "mode": "t2i",
         "live_samplers": LIVE_SAMPLERS, "live_schedulers": LIVE_SCHEDULERS})
    assert reply["ok"]
    sampling = reply["sampling"]
    assert sampling["known_good_samplers"] == ["er_sde", "euler"]
    assert "heun" in sampling["other_samplers"]


def test_the_family_contract_snapshot_carries_the_groups_for_every_family():
    """The other door into the same dropdown: `video_family_contracts` ships the family-keyed
    snapshot the cockpit applies before any model is chosen. A family whose groups were missing
    there would fall back to the flat list and silently show the pre-ruling dropdown."""
    snapshot = fop.family_sampling_snapshot()
    assert snapshot
    for family, block in snapshot.items():
        assert "known_good_samplers" in block, family
        assert "other_samplers" in block, family
        assert block["known_good_samplers"], f"{family} would show an empty Simple sampler list"
        assert not set(block["known_good_samplers"]) & set(block["other_samplers"]), family
