"""Generation output allocation must never reuse an existing user artifact."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "qt_ui" / "generation" / "OutputPathHelpers.cpp").read_text(encoding="utf-8")


def test_output_allocator_treats_every_existing_output_or_sidecar_as_occupied() -> None:
    body = SOURCE.split("void resolveGenerationOutputPaths", 1)[1].split(
        "QString metadataPathForOutputPath", 1
    )[0]
    helper = SOURCE.split("bool outputCandidateOccupied", 1)[1].split("} // namespace", 1)[0]
    assert "metadataPathForOutputPath(path)" in helper
    assert "while (outputCandidateOccupied(candidate))" in helper
    assert "nextAvailableOutputPath" in body
    assert ".size()" not in body
    assert "n < 100" not in body


def test_salvage_never_overwrites_even_a_small_existing_plate() -> None:
    body = SOURCE.split("bool salvageHuntPlate", 1)[1].split(
        "void persistLatestGeneratedOutput", 1
    )[0]
    assert "if (QFileInfo::exists(plate))" in body
    assert "QFile::remove(plate)" not in body
    assert "size() > 40960" not in body.split("QDir comfyDir", 1)[0]
