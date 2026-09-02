"""The remote names the output; this side decides what it is allowed to be.

Security finding 3 + 4, 2026-09-01. Three routes each copied one block that took the ComfyUI
history entry's ``filename`` and (a) used it whole as a local path under cwd when the request had no
``output``, and (b) adopted its extension via ``with_suffix`` unconditionally. That history entry is
authored by whichever machine served the render -- a remote node, a LAN peer answering for it over
plaintext HTTP, or a custom node pack inside a local ComfyUI. The UI's "Open last output" then hands
the file to the OS shell. ``render.hta`` served from ``/view`` was one click from running.

Now one resolver (``resolve_comfy_output_path``) and one checked download (``_download_comfy_asset``
verifies the bytes begin like the extension claims). These tests are the behaviour; the sweep rule
``comfy-output-path-through-one-resolver`` is the structural half that keeps a fourth copy from
appearing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import comfy_prompt_client as cpc  # noqa: E402
from comfy_prompt_client import (  # noqa: E402
    ALLOWED_OUTPUT_SUFFIXES,
    asset_bytes_match_suffix,
    resolve_comfy_output_path,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 32
HTA = b"<html><script>new ActiveXObject('WScript.Shell').Run('calc')</script></html>"


# --- the suffix is bounded --------------------------------------------------------------------

@pytest.mark.parametrize("bad", [".hta", ".exe", ".bat", ".ps1", ".cmd", ".scr", ".lnk", ".url", ".vbs", ".js", ".html"])
def test_a_remote_extension_this_app_does_not_produce_is_refused(bad, tmp_path) -> None:
    req = {"output": str(tmp_path / "render.png")}
    with pytest.raises(RuntimeError, match="does not produce or open"):
        resolve_comfy_output_path(req, {"filename": f"render{bad}"}, default_stem="x")


@pytest.mark.parametrize("good", sorted(ALLOWED_OUTPUT_SUFFIXES))
def test_every_allowed_extension_resolves(good, tmp_path) -> None:
    req = {"output": str(tmp_path / "render.png")}
    out = resolve_comfy_output_path(req, {"filename": f"render{good}"}, default_stem="x")
    assert out.lower().endswith(good)


def test_the_allowlist_has_no_executable_or_document_types() -> None:
    forbidden = {".exe", ".bat", ".cmd", ".ps1", ".hta", ".vbs", ".js", ".lnk", ".scr", ".msi",
                 ".html", ".htm", ".svg", ".pdf", ".zip", ".py", ".dll"}
    assert not (ALLOWED_OUTPUT_SUFFIXES & forbidden)


# --- the remote contributes a basename, never a path --------------------------------------------

@pytest.mark.parametrize("traversal", [
    "..\\..\\..\\Users\\victim\\Startup\\x.png",
    "../../../etc/cron.d/x.png",
    "C:\\Windows\\Temp\\x.png",
    "/tmp/x.png",
    "sub\\dir\\x.png",
])
def test_a_remote_filename_is_reduced_to_its_basename_when_no_output_is_requested(traversal, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    out = Path(resolve_comfy_output_path({}, {"filename": traversal}, default_stem="x"))
    assert out.parent == tmp_path, f"{traversal!r} escaped cwd to {out}"
    assert out.name == "x.png"


def test_the_stripping_handles_the_other_os_separator(monkeypatch, tmp_path) -> None:
    """A Linux node reporting backslashes, or a Windows one reporting slashes -- the remote's OS is
    not this one's, so both separators are stripped regardless of the platform this runs on."""
    monkeypatch.chdir(tmp_path)
    for name in ("a\\b\\c.png", "a/b/c.png", "a\\b/c.png"):
        assert Path(resolve_comfy_output_path({}, {"filename": name}, default_stem="x")).name == "c.png"


def test_a_requested_output_keeps_its_directory_and_stem(tmp_path) -> None:
    req = {"output": str(tmp_path / "renders" / "mine.png")}
    out = Path(resolve_comfy_output_path(req, {"filename": "..\\..\\evil.png"}, default_stem="x"))
    assert out.parent == tmp_path / "renders"
    assert out.stem == "mine"


def test_the_remote_suffix_still_wins_when_it_is_allowed(tmp_path) -> None:
    """The one legitimate use of the remote's suffix: a video route asked for .png by a stale
    default gets the .mp4 ComfyUI actually produced."""
    req = {"output": str(tmp_path / "clip.png")}
    out = resolve_comfy_output_path(req, {"filename": "clip_00001_.mp4"}, default_stem="x")
    assert out.endswith(".mp4")


def test_no_filename_at_all_falls_back_to_the_default_stem(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    out = Path(resolve_comfy_output_path({}, {}, default_stem="comfy_abc"))
    assert out.name == "comfy_abc.png"


# --- the bytes must match the name ---------------------------------------------------------------

@pytest.mark.parametrize("data,suffix", [(PNG, ".png"), (JPG, ".jpg"), (JPG, ".jpeg"), (MP4, ".mp4"),
                                         (MP4, ".mov"), (WEBM, ".webm"), (WEBM, ".mkv"),
                                         (b"RIFF\x00\x00\x00\x00WEBPVP8 ", ".webp"),
                                         (b"RIFF\x00\x00\x00\x00WAVEfmt ", ".wav"),
                                         (b"GIF89a\x00", ".gif"), (b"ID3\x03", ".mp3"),
                                         (b"\xff\xfb\x90", ".mp3"), (b"fLaC\x00", ".flac"),
                                         (b"glTF\x02", ".glb"), (b'  {"a": 1}', ".json"), (b"[1]", ".json")])
def test_genuine_bytes_match_their_extension(data, suffix) -> None:
    assert asset_bytes_match_suffix(data, suffix)


@pytest.mark.parametrize("suffix", sorted(ALLOWED_OUTPUT_SUFFIXES))
def test_an_hta_payload_matches_no_allowed_extension(suffix) -> None:
    """The payload from the audit, tried under every extension the resolver would let through."""
    assert not asset_bytes_match_suffix(HTA, suffix)


def test_png_bytes_do_not_pass_as_mp4_and_vice_versa() -> None:
    assert not asset_bytes_match_suffix(PNG, ".mp4")
    assert not asset_bytes_match_suffix(MP4, ".png")


def test_an_unknown_suffix_never_matches() -> None:
    assert not asset_bytes_match_suffix(PNG, ".exe")
    assert not asset_bytes_match_suffix(b"", ".png")


# --- the download refuses before it writes ----------------------------------------------------

class _Resp:
    def __init__(self, body: bytes):
        self._b = body
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_a_mismatched_body_is_not_written(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cpc.urllib.request, "urlopen", lambda *a, **k: _Resp(HTA))
    dest = tmp_path / "out" / "render.png"
    with pytest.raises(RuntimeError, match="do not look like that format"):
        cpc._download_comfy_asset("http://x", {"filename": "render.png"}, str(dest))
    assert not dest.exists()
    assert not dest.parent.exists(), "the directory must not be created for a refused write either"


def test_a_matching_body_is_written(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cpc.urllib.request, "urlopen", lambda *a, **k: _Resp(PNG))
    dest = tmp_path / "out" / "render.png"
    assert cpc._download_comfy_asset("http://x", {"filename": "render.png"}, str(dest)) == str(dest)
    assert dest.read_bytes() == PNG


def test_a_destination_with_a_forbidden_suffix_is_refused_even_if_the_resolver_was_bypassed(monkeypatch, tmp_path) -> None:
    """Defence in depth: the download checks the suffix again, so a caller that built its own path
    cannot get an .hta written by skipping the resolver."""
    monkeypatch.setattr(cpc.urllib.request, "urlopen", lambda *a, **k: _Resp(HTA))
    dest = tmp_path / "render.hta"
    with pytest.raises(RuntimeError, match="Refusing to write"):
        cpc._download_comfy_asset("http://x", {"filename": "render.hta"}, str(dest))
    assert not dest.exists()


# --- the three routes use the one resolver ----------------------------------------------------

def test_the_three_routes_call_the_resolver_and_none_keeps_a_copy() -> None:
    nr = (ROOT / "python" / "native_runners.py").read_text(encoding="utf-8")
    pc = (ROOT / "python" / "comfy_prompt_client.py").read_text(encoding="utf-8")
    assert nr.count("resolve_comfy_output_path(") == 2
    assert pc.count("resolve_comfy_output_path(") >= 2  # definition + the call
    for text, name in ((nr, "native_runners.py"), (pc, "comfy_prompt_client.py")):
        assert "with_suffix(asset_suffix)" not in text, f"{name} still adopts the remote suffix directly"
