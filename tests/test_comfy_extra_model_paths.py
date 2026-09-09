"""Add folder… must land in Comfy extra_model_paths.yaml or Generate cannot see F:."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from comfy_extra_model_paths import (
    BEGIN_MARK,
    END_MARK,
    compose_managed_block,
    merge_managed_block,
    stanza_name,
)


def test_empty_libraries_compose_nothing() -> None:
    assert compose_managed_block([]) == ""


def test_primary_and_extra_get_distinct_stanzas(tmp_path: Path) -> None:
    primary = tmp_path / "D_models"
    extra = tmp_path / "F_models"
    primary.mkdir()
    extra.mkdir()
    block = compose_managed_block([str(primary), str(extra)])
    assert BEGIN_MARK in block and END_MARK in block
    assert "spellvision:" in block
    assert "spellvision_extra_0:" in block
    assert "base_path:" in block
    assert "checkpoints: checkpoints" in block
    assert "D:/" not in block
    assert str(primary).replace("\\", "/") in block.replace("\\", "/")
    assert str(extra).replace("\\", "/") in block.replace("\\", "/")


def test_merge_replaces_only_the_managed_block() -> None:
    existing = "other:\n    base_path: /keep/me\n"
    block = compose_managed_block(["/tmp/models"])
    merged = merge_managed_block(existing, block)
    assert "base_path: /keep/me" in merged
    twice = merge_managed_block(merged, block)
    assert twice.count(BEGIN_MARK) == 1


def test_stanza_name_is_stable() -> None:
    assert stanza_name(0) == "spellvision"
    assert stanza_name(1) == "spellvision_extra_0"
    assert stanza_name(2) == "spellvision_extra_1"
