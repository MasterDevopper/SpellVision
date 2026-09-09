"""T1: Train defaults come from this machine. No house Sohya path."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "qt_ui" / "TrainPage.cpp"
HDR = ROOT / "qt_ui" / "TrainPage.h"


def test_train_page_does_not_invent_sohya_path() -> None:
    cpp = CPP.read_text(encoding="utf-8")
    body = cpp.split("QString TrainPage::defaultSohyaPath()", 1)[1].split("void TrainPage::", 1)[0]
    assert "return QString();" in body


def test_train_page_shows_hardware_smart_defaults() -> None:
    cpp = CPP.read_text(encoding="utf-8")
    hdr = HDR.read_text(encoding="utf-8")
    assert "GpuMemoryProbe" in cpp
    assert "hardwareDefaultsLabel_" in hdr
    assert "cluster not joined" in cpp
    assert "krea2" in cpp.lower()
