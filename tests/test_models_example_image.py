"""T3: inspect shows a local sidecar example image. Nothing is fetched.

This asserted `exampleImageLabel_` -- a QLabel member of ModelManagerPage -- in the header and in
the .cpp. W5 Task 3 replaced the details card with `assets/ModelInspectorPanel`, which shows up to
six of the sidecar's pictures instead of one, and the member went with it. The BEHAVIOUR did not
move; the name did, and a test that spells a member name reports a rename as a lost feature.

So it is stated as the behaviour now, in three parts that together say "a local picture reaches the
screen without a network fetch":

* the page hands the selected weight to the inspector when the selection changes;
* the inspector puts a picture on a tile by loading it FROM DISK, and never opens a socket;
* and the rendering itself -- pictures on tiles, in order, with a missing file left out -- is
  exercised for real by `tests/cpp/test_model_inspector.cpp`, which writes sidecars and PNGs to a
  temporary library and reads the tiles back. A text scan cannot see a pixmap; what it can see is
  that the test which can is still built and still registered with ctest.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpp_source import definition_body

ROOT = Path(__file__).resolve().parents[1]


def test_selecting_a_model_hands_the_weight_to_the_inspector() -> None:
    body = definition_body("updateDetailsForRow", qualifier="ModelManagerPage")
    assert "inspectorPanel_->showModel(" in body, (
        "the inspector is never told which weight to show, so the details pane cannot display "
        "this model's pictures"
    )
    assert "inspectorPanel_->setModelRoots(" in body


def test_the_inspector_shows_a_picture_from_disk_and_fetches_nothing() -> None:
    panel = (ROOT / "qt_ui" / "assets" / "ModelInspectorPanel.cpp").read_text(encoding="utf-8")
    # The picture comes off the local path the sidecar names ...
    assert "pixmap.load(image.localPath)" in panel
    assert "tile->setPixmap(" in panel
    # ... and a path the sidecar names but the disk does not have leaves the tile out rather than
    # showing an empty box (the reason the load result is checked at all).
    assert "if (pixmap.isNull())" in panel
    # T3 is "nothing is fetched": the panel has no network client of its own. It emits requests and
    # the page owns the socket, which is what lets the C++ test drive the whole surface with no
    # worker and no network.
    for network in ("QNetworkAccessManager", "QNetworkRequest", "QNetworkReply", "QTcpSocket"):
        assert network not in panel, f"the inspector opened a {network}; the picture is local"


def test_the_rendering_is_covered_by_a_test_that_can_see_pixels() -> None:
    cpp = (ROOT / "tests" / "cpp" / "test_model_inspector.cpp").read_text(encoding="utf-8")
    assert "galleryImageAt(" in cpp
    assert "the_gallery_renders_every_picture_the_sidecar_names" in cpp
    # Comment lines dropped first. `# add_test(NAME model_inspector ...)` still contains the
    # substring while registering nothing -- measured: commenting the line out left this green.
    # It is the same trap this suite already records for "download" matching inside the sentence
    # that explains nothing is downloaded.
    cmake = "\n".join(
        line for line in (ROOT / "CMakeLists.txt").read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "qt_add_executable(test_model_inspector" in cmake
    assert "add_test(NAME model_inspector" in cmake, (
        "the only test that can see a rendered picture is not registered with ctest, so it would "
        "stop running without anything failing"
    )
