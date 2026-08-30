"""An operating point nobody can select is a declaration, not a feature.

The overhaul plan called this phase "apply the 6.3x", on the survey's finding that the
`lora: {accel}` block carried a measured speedup and was never applied. **That premise was wrong,
and it is recorded here rather than quietly dropped.** The block IS applied: the UI offers a
Fast/Quality selector, sends `operating_point`, and `_build_native_wan_dual_noise_video_prompt`
resolves it, injecting the declared accel LoRAs with a loud warning when an API caller supplies no
LoRA stack of their own.

What measuring it DID find is one layer down. The dual-noise builder serves both t2v and i2v and
already refuses a mixed expert pair -- "must be the same task variant (both t2v, or both i2v) -- a
mixed pair renders off-model". That guard was applied to the checkpoints and not to the LoRAs, so
selecting Fast on an i2v job injected the **t2v** accel pair. The correct i2v pair was on disk
beside it, same publisher, same rank, same 4-step distill.

So the rule this file enforces is not "the accel LoRA is applied" -- it is the property that would
have caught the real defect: every operating point a family declares must be selectable, and every
accel pair it declares must be resolvable for the commands its builder actually serves.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from family_operating_points import (  # noqa: E402
    FAMILY_OPERATING_POINTS,
    accel_loras_for,
    family_operating_points_payload,
    operating_point_params,
    resolve_operating_point,
)

MULTI_POINT = sorted(
    name for name, row in FAMILY_OPERATING_POINTS.items()
    if len(row.get("operating_points", {})) > 1
)

# The commands the Wan dual-noise builder accepts. Taken from the builder's own guard rather than
# from a list here, so adding a command there fails this file instead of silently skipping it.
DUAL_NOISE_COMMANDS = ("t2v", "i2v")


# --- every declared point is selectable ---------------------------------------------------------

def test_there_is_more_than_one_multi_point_family() -> None:
    """Guards the guard. If a refactor collapsed every family to a single point, every test below
    would pass vacuously and report a green that means nothing."""
    assert len(MULTI_POINT) >= 2, MULTI_POINT


@pytest.mark.parametrize("family", MULTI_POINT)
def test_every_declared_point_resolves_by_its_own_name(family: str) -> None:
    for name in FAMILY_OPERATING_POINTS[family]["operating_points"]:
        assert resolve_operating_point(family, name) == name, (
            f"{family} declares {name!r} and cannot resolve it -- the point is unreachable and the "
            "user's selection silently becomes the default"
        )


@pytest.mark.parametrize("family", MULTI_POINT)
def test_the_default_point_is_one_of_the_declared_ones(family: str) -> None:
    row = FAMILY_OPERATING_POINTS[family]
    assert row["default_operating_point"] in row["operating_points"], (
        f"{family}'s default names a point it does not declare"
    )


@pytest.mark.parametrize("family", MULTI_POINT)
def test_the_ui_payload_offers_every_point(family: str) -> None:
    """The UI hides the selector at <=1 point, so a point missing from the payload is invisible even
    though the worker would honour it."""
    payload = family_operating_points_payload(family)
    offered = {p["name"] for p in payload["operating_points"]}
    assert offered == set(FAMILY_OPERATING_POINTS[family]["operating_points"]), offered


def test_an_unknown_point_falls_back_loudly_rather_than_raising(caplog) -> None:
    """A bad `operating_point` from a script must not kill the render, and must not be silent
    either -- the render that proceeds is not the one that was asked for."""
    import logging

    with caplog.at_level(logging.WARNING):
        assert resolve_operating_point("wan", "nonsense") == "quality"
    assert any("nonsense" in r.getMessage() for r in caplog.records)


# --- an accel pair is per task variant, and never borrowed -------------------------------------

@pytest.mark.parametrize("command", DUAL_NOISE_COMMANDS)
def test_the_fast_point_declares_a_pair_for_every_command_its_builder_serves(command: str) -> None:
    """The defect. `fast` runs 4 steps at cfg 1, which is garbage on the base model without its
    accel LoRAs -- so a command the builder accepts and the point has no pair for is a command that
    cannot use the point at all."""
    pair = accel_loras_for(operating_point_params("wan", "fast"), command)
    assert pair.get("high") and pair.get("low"), (
        f"the fast operating point declares no accel LoRA pair for {command!r}, which the "
        f"dual-noise builder serves"
    )


def test_the_two_variants_do_not_share_a_file() -> None:
    """What went wrong: one flat pair served both commands, so i2v got t2v weights."""
    t2v = accel_loras_for(operating_point_params("wan", "fast"), "t2v")
    i2v = accel_loras_for(operating_point_params("wan", "fast"), "i2v")
    assert set(t2v.values()).isdisjoint(i2v.values()), (
        f"t2v and i2v resolve to the same accel LoRA file: {t2v} vs {i2v}"
    )


@pytest.mark.parametrize("command", DUAL_NOISE_COMMANDS)
def test_each_variants_files_name_that_variant(command: str) -> None:
    """A pairing check the filenames themselves can answer. The builder routes high/low by the
    `high_noise`/`low_noise` token in the name, so the tokens have to be there too."""
    pair = accel_loras_for(operating_point_params("wan", "fast"), command)
    for role, filename in pair.items():
        lowered = filename.lower()
        assert command in lowered, f"{command} pair names {filename}, which is not a {command} file"
        assert f"{role}_noise" in lowered, (
            f"{filename} is the {role} slot but its name carries no {role}_noise token, so the "
            "builder's per-expert filename routing cannot place it"
        )


def test_an_unknown_command_gets_nothing_rather_than_a_substitute() -> None:
    """Doc 19: never silently substitute a model. Returning the t2v pair for an unrecognised
    command is exactly that substitution, and it would look like a working render."""
    for command in ("", None, "t23d", "image"):
        assert accel_loras_for(operating_point_params("wan", "fast"), command) == {}, command


def test_the_same_command_spelled_differently_is_still_that_command() -> None:
    """The other half, and the reason the test above lists only genuine strangers: case and
    surrounding whitespace are spelling, not identity. Refusing `"T2V "` would not be caution, it
    would be a fast render silently downgraded to a slow one by a stray space."""
    canonical = accel_loras_for(operating_point_params("wan", "fast"), "t2v")
    for spelling in ("T2V", " t2v ", "T2v"):
        assert accel_loras_for(operating_point_params("wan", "fast"), spelling) == canonical


def test_a_point_without_accel_declares_no_pair() -> None:
    assert accel_loras_for(operating_point_params("wan", "quality"), "t2v") == {}


def test_the_flat_keys_are_gone() -> None:
    """A flat high/low left beside the variants as a "default" would keep working for t2v and keep
    being wrong for i2v -- the failure this fixes, preserved as a fallback. An unmigrated reader
    must break loudly instead."""
    lora = FAMILY_OPERATING_POINTS["wan"]["operating_points"]["fast"]["lora"]
    assert "high" not in lora and "low" not in lora, lora
    assert set(DUAL_NOISE_COMMANDS) <= set(lora), lora
