"""A LoRA imported through SpellVision keeps its trigger words.

materialize_asset captured trainedWords / modelId / modelVersionId from Civitai into
MaterializedAsset.metadata; import_model_choices copied the weights and dropped that dict. The Models
page reads trigger words from a sibling ``<stem>.metadata.json`` under ``civitai.trainedWords``
(ModelSidecar.cpp), so a LoRA the app itself imported showed none while one dropped in by hand with a
scraper's sidecar did. The import now writes the sidecar the page already reads, in the shape it
already parses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import model_import  # noqa: E402

CATALOG = {
    "choices": [{
        "choice_id": "c1",
        "download_url": "https://civitai.com/api/download/models/3262504?fileId=3146121",
        "model_type": "lora",
        "dest_subdir": "loras",
        "filename": "chel_ltx23.safetensors",
    }],
}


def _fake_materialize(tmp_path: Path, metadata: dict):
    src = tmp_path / "cache" / "chel_ltx23.safetensors"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"\x00" * 64)

    def materialize(ref, *, asset_type):
        return SimpleNamespace(local_path=str(src), metadata=metadata)

    return materialize


def test_the_import_writes_a_sidecar_the_models_page_reads(tmp_path) -> None:
    meta = {"trained_words": ["chel", "ltx style"], "model_id": 2823011, "model_version_id": 3262504,
            "sha256": "ABCDEF", "file_format": "SafeTensor"}
    result = model_import.import_model_choices(CATALOG, ["c1"], install_root=str(tmp_path / "models"),
                                               include_pairs=False, materialize=_fake_materialize(tmp_path, meta))
    assert result["ok"], result
    installed = Path(result["installed"][0])
    sidecar = installed.with_name(installed.stem + ".metadata.json")
    assert sidecar.exists(), "no sidecar written beside the imported file"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    # The exact shape ModelSidecar.cpp parses: civitai.trainedWords.
    assert payload["civitai"]["trainedWords"] == ["chel", "ltx style"]
    assert payload["civitai"]["modelId"] == 2823011
    assert payload["civitai"]["modelVersionId"] == 3262504
    assert payload["sha256"] == "abcdef", "digest is normalised to lower case like the rest of the tree"
    assert result["results"][0]["sidecar_path"] == str(sidecar)


def test_an_existing_sidecar_is_never_overwritten(tmp_path) -> None:
    """A scraper's file is richer -- previews, descriptions, versions. The import's is a floor."""
    dest = tmp_path / "models" / "loras"
    dest.mkdir(parents=True)
    existing = dest / "chel_ltx23.metadata.json"
    existing.write_text('{"civitai": {"trainedWords": ["from-scraper"]}, "description": "keep me"}', encoding="utf-8")
    meta = {"trained_words": ["chel"], "model_id": 1, "model_version_id": 2}
    result = model_import.import_model_choices(CATALOG, ["c1"], install_root=str(tmp_path / "models"),
                                               include_pairs=False, materialize=_fake_materialize(tmp_path, meta))
    assert result["ok"]
    assert json.loads(existing.read_text())["description"] == "keep me"
    assert result["results"][0]["sidecar_path"] is None


def test_nothing_is_written_when_the_provider_said_nothing(tmp_path) -> None:
    """A direct URL with no metadata gets no empty sidecar cluttering the folder."""
    result = model_import.import_model_choices(CATALOG, ["c1"], install_root=str(tmp_path / "models"),
                                               include_pairs=False, materialize=_fake_materialize(tmp_path, {}))
    assert result["ok"]
    installed = Path(result["installed"][0])
    assert not installed.with_name(installed.stem + ".metadata.json").exists()


def test_the_sidecar_name_matches_what_the_page_looks_for() -> None:
    """ModelSidecar.cpp: base = <dir>/<completeBaseName>, then <base>.metadata.json. completeBaseName
    strips only the LAST suffix, so a dotted stem must survive."""
    src = (ROOT / "qt_ui" / "assets" / "ModelSidecar.cpp").read_text(encoding="utf-8")
    assert 'QStringLiteral("metadata.json")' in src
    assert "info.completeBaseName()" in src
    target = Path("C:/models/loras/wan2.2_t2v_high_noise.safetensors")
    assert target.with_name(target.stem + ".metadata.json").name == "wan2.2_t2v_high_noise.metadata.json"
