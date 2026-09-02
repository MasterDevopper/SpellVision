"""The rule is watched firing on the exact block it was written for, and staying quiet on the fix.

Three routes carried this block; the clean tree after the fix cannot prove the rule works, because a
rule with a broken pattern also reports a clean tree. Both of the sweep rules written in the audit's
first pass were silently broken on their first run and looked exactly like success -- one with a
mangled escape that matched nothing. So every rule gets fed the shape it claims to catch.

``FAKE`` sits under python/ so ``sources.relative`` resolves; the file never exists on disk.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from sweeps import rules, sources  # noqa: E402

RULE = [r for r in rules.ALL_RULES if r.name == "comfy-output-path-through-one-resolver"][0]
FAKE_PY = sources.ROOT / "python" / "Fake.py"
FAKE_CPP = sources.ROOT / "qt_ui" / "Fake.cpp"

# comfy_prompt_client.py:944-952 before the fix, verbatim shape.
THE_BLOCK = '''
def _run(req, asset, prompt_id, api_url):
    output_path = str(req.get("output") or "").strip()
    if not output_path:
        filename = str(asset.get("filename") or f"comfy_{prompt_id}.png")
        output_path = str(Path.cwd() / filename)
    else:
        requested_suffix = Path(output_path).suffix
        asset_suffix = Path(str(asset.get("filename") or "")).suffix
        if requested_suffix and asset_suffix and requested_suffix.lower() != asset_suffix.lower():
            output_path = str(Path(output_path).with_suffix(asset_suffix))
    return _download_comfy_asset(api_url, asset, output_path)
'''

# native_runners.py:308-315 before the fix -- the variant that spelled the cwd join on one line.
THE_ONE_LINER = '''
def _run(req, asset, prompt_id, api_url):
    output_path = str(req.get("output") or "").strip()
    if not output_path:
        output_path = str(Path.cwd() / (str(asset.get("filename")) or f"flux_native_{prompt_id}.png"))
    return _download_comfy_asset(api_url, asset, output_path)
'''

THE_FIX = '''
def _run(req, asset, prompt_id, api_url):
    output_path = resolve_comfy_output_path(req, asset, default_stem=f"comfy_{prompt_id}")
    return _download_comfy_asset(api_url, asset, output_path)
'''

# A reader of the filename that derives NOTHING local from it -- passes it back to the remote.
FILENAME_FOR_THE_QUERY = '''
def _view_url(api_url, asset):
    query = urllib.parse.urlencode({"filename": asset.get("filename", ""), "type": "output"})
    return f"{api_url}/view?{query}"
'''

SHELL_OPENS_A_FILE = '''
void open(const QString &p) {
    QDesktopServices::openUrl(QUrl::fromLocalFile(p));
}
'''
SHELL_OPENS_A_FOLDER = '''
void reveal(const QString &p) {
    QDesktopServices::openUrl(QUrl::fromLocalFile(QFileInfo(p).absolutePath()));
}
'''
THE_HELPER = '''
void openOutputAsset(const QString &path)
{
    QDesktopServices::openUrl(QUrl::fromLocalFile(path));
}
'''


def _fires_py(text: str) -> bool:
    return bool(RULE.check(FAKE_PY, text))


def _fires_cpp(text: str) -> bool:
    return bool(RULE.check(FAKE_CPP, text))


def test_it_fires_on_the_block_the_three_routes_carried() -> None:
    found = RULE.check(FAKE_PY, THE_BLOCK)
    assert found, "the exact pre-fix block did not trigger the rule"
    assert all("resolve_comfy_output_path" in v.detail for v in found)


def test_it_fires_on_the_one_line_variant() -> None:
    assert _fires_py(THE_ONE_LINER), "the single-line Path.cwd() join was not caught"


def test_it_stays_quiet_on_the_fix() -> None:
    assert not _fires_py(THE_FIX)


def test_reading_the_filename_for_the_view_query_is_not_a_violation() -> None:
    """The remote's filename has one legitimate use: asking the remote for that file. That is
    _download_comfy_asset's own query, and it derives no local path from it."""
    assert not _fires_py(FILENAME_FOR_THE_QUERY)


def test_the_resolver_itself_is_allowed_to_touch_the_filename() -> None:
    text = "def resolve_comfy_output_path(req, asset, *, default_stem):\n" + THE_BLOCK
    assert not _fires_py(text)


def test_it_fires_on_a_cpp_site_that_shell_opens_a_file() -> None:
    found = RULE.check(FAKE_CPP, SHELL_OPENS_A_FILE)
    assert found
    assert "openOutputAsset" in found[0].detail


def test_it_stays_quiet_on_a_cpp_site_that_reveals_a_folder() -> None:
    assert not _fires_cpp(SHELL_OPENS_A_FOLDER)


def test_the_helper_itself_is_allowed_to_shell_open() -> None:
    assert not _fires_cpp(THE_HELPER)


def test_the_live_tree_has_exactly_the_one_recorded_exemption() -> None:
    """Zero in Python: all three copies are gone. One in C++: Open-Workflow-JSON, exempted with a
    reason in exemptions.py. A second C++ hit, or any Python hit, means a copy came back."""
    live = RULE.run()
    py = [v for v in live if str(v.path).endswith(".py")]
    cpp = [v for v in live if not str(v.path).endswith(".py")]
    assert py == [], [str(v) for v in py]
    assert len(cpp) == 1 and "WorkflowLibraryPage" in str(cpp[0].path), [str(v) for v in cpp]
