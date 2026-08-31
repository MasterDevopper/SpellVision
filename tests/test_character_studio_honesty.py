"""Character Studio does not advertise a live Pixal identity cook."""
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "qt_ui" / "studios" / "CharacterStudioPage.cpp"


def test_character_studio_does_not_sell_pixal_pipeline() -> None:
    text = PAGE.read_text(encoding="utf-8")
    header = (PAGE.parent / "CharacterStudioPage.h").read_text(encoding="utf-8")
    assert "Pixal3D → UltraShape → bake chain when available" not in text
    assert "UltraShape → adaptive remesh" not in header
    assert "Adjunct only — not character identity" in text
    assert "frozen female.glb" not in text
    assert "frozen female.glb" not in header
    assert 'QStringLiteral("assets/models/human/female.glb")' not in text
    assert "setHidden(true)" in text
    assert "StageId::BaseMesh" in text
    assert "Mark compose draft complete" not in text
    assert "Mark hair draft complete" not in text
    assert "JSON create contract (Path B)" in text
    assert 'QStringLiteral("GLB")' not in text
    assert "Export complete" not in text
    assert "JSON create contract written" in text
    assert "Apply house-style LoRA" not in text
    assert "Choose house LoRA" not in text
    assert "Apply style LoRA" in text
    assert "Stylized Realistic (house)" not in text
    assert 'QStringLiteral("krea2")' not in text
    assert "SpellBound-Engine/assets/models/human/female.glb" not in text
    assert "characterStudio/bodyGlb" in text
    assert "Pipeline ready" not in text
    assert "jump to mesh" not in text
    assert "C:/Users/xXste/pixal3d-spike" not in text
    assert "miniforge3/envs/pixal3d-spike" not in text


def test_python_character_paths_do_not_invent_a_body() -> None:
    root = PAGE.parents[2]
    create = (root / "python" / "character_create.py").read_text(encoding="utf-8")
    wrap = (root / "python" / "garment_shrinkwrap.py").read_text(encoding="utf-8")
    clothes = (root / "python" / "clothes_only.py").read_text(encoding="utf-8")
    assert '"source": "assets/models/human/female.glb"' not in create
    assert "body is required; choose a body mesh" in create
    assert "ENGINE_FEMALE_GLB_CANDIDATES" not in wrap
    assert "SpellBound-Engine" not in wrap
    assert "ENGINE_FEMALE_GLB" not in clothes
