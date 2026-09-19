"""cm-cli cold is ~128 s; the UI request budget is 120 s.

Doc 62 3b: a first-ever import of a workflow with missing node packs timed out
because list_installed_nodes waited on `simple-show installed --mode cache` for
longer than the drop path's worker timeout. The folder walk already unions
custom_nodes names; the CLI must not hold the request past the UI budget.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from comfy_manager_bridge import list_installed_nodes  # noqa: E402


def test_the_cli_wait_fits_inside_the_ui_request_budget() -> None:
    default = inspect.signature(list_installed_nodes).parameters["timeout_sec"].default
    assert isinstance(default, int)
    assert default < 120, (
        f"list_installed_nodes waits {default}s; the drop path's worker timeout is 120s, "
        "so a cold cm-cli (~128s) times the import out before the folder walk can answer"
    )
    assert default <= 45
