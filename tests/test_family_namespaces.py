"""Five tables key on "a family" and they do not mean the same thing by it.

The plan for this pass says explicitly: **pin, do not merge.** The five namespaces sit at different
layers, and collapsing them would be applying a rule at the wrong level -- the same mistake as
narrowing a file recommendation by name when the axis was precision.

    model_registry.MODEL_FAMILIES     the ARCHITECTURE a checkpoint is
    FAMILY_OPERATING_POINTS           tuned params, keyed per ROUTE -- wan_core, wan_wrapper and
                                      wan_diffusers are three ways to run one family
    FAMILY_SAMPLER_ALLOWLISTS         what the cockpit may offer for a family
    VIDEO_FAMILY_CONTRACTS            video readiness, including families that are not checkpoints
                                      at all: a hosted API, a raw workflow
    COMPONENT_MANIFEST                the component stack to resolve

What must hold is that every key in every table is EXPLICABLE -- a registry family, a declared
route, or a declared pseudo-family -- and that every alias points at something that exists. Today
they all do. Nothing asserted it, so the next drift would have been silent, and this namespace has
drifted before: `z_image` was once unable to resolve its own tuned defaults by its own registry key,
because the alias map carried `zimage` and `z-image` and not the spelling the registry actually uses.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from family_capability import (  # noqa: E402
    PSEUDO_FAMILIES,
    ROUTE_KEYS,
    family_ids,
    family_namespace_report,
    resolve_family_key,
)

REPORT = family_namespace_report()
CANONICAL_TABLES = [name for name in REPORT if not name.endswith("aliases")]
ALIAS_TABLES = [name for name in REPORT if name.endswith("aliases")]


@pytest.mark.parametrize("table", CANONICAL_TABLES)
def test_every_key_is_a_family_a_route_or_a_declared_pseudo_family(table: str) -> None:
    """An unexplained key is a family name nobody can reach -- a typo, or a rename that landed in
    one table and not the others."""
    unexplained = REPORT[table]["unexplained"]
    assert not unexplained, (
        f"{table} has {len(unexplained)} key(s) that are neither a registry family, a declared "
        f"route ({sorted(ROUTE_KEYS)}) nor a declared pseudo-family ({sorted(PSEUDO_FAMILIES)}): "
        f"{unexplained}. If one of these is a new route or a new pseudo-family, declare it; if it "
        "is a family, it belongs in the registry."
    )


@pytest.mark.parametrize("table", ALIAS_TABLES)
def test_every_alias_points_at_something_that_exists(table: str) -> None:
    """An alias is checked against ITS OWN table, not against the registry.

    That distinction is the point: `hunyuan` is not a registry id -- the id is `hunyuan_video` --
    and it is a perfectly good alias key. What would be broken is an alias whose VALUE names no row.
    """
    dangling = REPORT[table]["unexplained"]
    assert not dangling, f"{table} has aliases pointing at rows that do not exist: {dangling}"


def test_a_route_key_is_not_mistaken_for_a_family() -> None:
    """wan_core is a way of running wan, not a thing a checkpoint can be. If routes resolved to
    families the completeness check above would pass for a table full of typos."""
    for route in ROUTE_KEYS:
        assert resolve_family_key(route) is None, f"{route} resolves as a family"


def test_naming_drift_resolves_but_a_wrong_name_does_not() -> None:
    """Separators and task suffixes are naming; anything else is identity.

    Compared with separators REMOVED rather than swapped, because the live drift was a missing one:
    the operating-point table keys `zimage_image` and the registry id is `z_image`.
    """
    assert resolve_family_key("zimage_image") == "z_image"
    assert resolve_family_key("z-image") == "z_image"
    assert resolve_family_key("krea2_image") == "krea2"
    assert resolve_family_key("sd_3") == "sd3"

    assert resolve_family_key("nonsense") is None
    assert resolve_family_key("") is None
    assert resolve_family_key("sdxl_turbo") is None, (
        "a DIFFERENT family with a shared prefix must not resolve to its neighbour -- that is how "
        "a substring match silently binds the wrong model"
    )


def test_a_declared_route_or_pseudo_family_is_never_also_a_registry_family() -> None:
    """The declarations are escape hatches. One that overlaps the registry would let a real family
    be explained away as a route instead of being checked as a family."""
    ids = family_ids()
    assert not (ROUTE_KEYS & ids), sorted(ROUTE_KEYS & ids)
    assert not (PSEUDO_FAMILIES & ids), sorted(PSEUDO_FAMILIES & ids)


def test_the_declared_escape_hatches_are_all_actually_used() -> None:
    """A stale declaration is as bad as a missing one: it keeps explaining a key that is gone, and
    the next typo of that name is explained away with it."""
    used: set[str] = set()
    for table in CANONICAL_TABLES:
        used.update(REPORT[table]["route"])
        used.update(REPORT[table]["pseudo"])
    unused = (ROUTE_KEYS | PSEUDO_FAMILIES) - used
    assert not unused, f"declared but named by no table: {sorted(unused)}"


def test_the_registry_is_the_only_place_a_family_is_born() -> None:
    """Every family any table names is in the registry. The reverse is NOT asserted -- a registry
    family with no operating point is a normal, deliberate state (sdxl has none on purpose, and
    that reasoning is recorded in family_capability)."""
    named: set[str] = set()
    for table in CANONICAL_TABLES:
        named.update(resolve_family_key(key) or "" for key in REPORT[table]["family"])
    named.discard("")
    assert named <= family_ids(), sorted(named - family_ids())
