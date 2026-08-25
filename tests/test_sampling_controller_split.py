"""God-page split: SamplingController owns sampler widgets + allow-lists.
ImageGenerationPage must not keep the shared 49-item static menus.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGP_CPP = ROOT / "qt_ui" / "ImageGenerationPage.cpp"
IGP_H = ROOT / "qt_ui" / "ImageGenerationPage.h"
CTRL_H = ROOT / "qt_ui" / "generation" / "SamplingController.h"
CTRL_CPP = ROOT / "qt_ui" / "generation" / "SamplingController.cpp"
CMAKE = ROOT / "CMakeLists.txt"


def test_sampling_controller_files_exist():
    assert CTRL_H.is_file(), "missing qt_ui/generation/SamplingController.h"
    assert CTRL_CPP.is_file(), "missing qt_ui/generation/SamplingController.cpp"
    header = CTRL_H.read_text(encoding="utf-8")
    impl = CTRL_CPP.read_text(encoding="utf-8")
    assert "class SamplingController" in header
    assert "applyFamilyChoices" in header
    assert "heunpp2" not in impl
    cmake = CMAKE.read_text(encoding="utf-8")
    assert "qt_ui/generation/SamplingController.cpp" in cmake.replace("\\", "/")


def test_image_generation_page_does_not_own_static_sampler_menus():
    cpp = IGP_CPP.read_text(encoding="utf-8")
    header = IGP_H.read_text(encoding="utf-8")
    assert 'addItem(QStringLiteral("heunpp2")' not in cpp
    assert "samplerCombo_ = new ClickOnlyComboBox" not in cpp
    assert "QComboBox *samplerCombo_ =" not in header
    assert "SamplingController" in header
    assert "sampling_" in header
