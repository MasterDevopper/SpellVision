"""The one source list every sweep uses.

**No rule may name a file.** That is the whole point of this module.

Eleven of the top twenty findings in the 2026-08-30 audit were second copies of a rule that had
already been applied correctly once, and the ratchets meant to prevent that had the same shape as
the bug:

* ``test_seed_is_one_rule.py`` pinned ``BUILDER_FILES`` to the three files where the defect was
  found. Two live seed-0 violations sat outside the tuple and the test was green.
* ``test_comfy_endpoint.py`` swept ``(ROOT/"python").glob("*.py")`` -- which sees **82 of 92
  modules**. ``python/runtime_adapters/`` and ``python/video_adapters/`` were invisible to it, and
  therefore to every sweep in the repo.

A rule scoped to where its defect was found is not a rule, it is a memo. So the scope lives here,
once, and rules receive whatever this returns.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Dead trees. Listed explicitly so the exclusion is a visible decision rather than an accident of
# whatever glob someone happened to write.
EXCLUDED_DIRS = frozenset({
    "attic",                 # archived by design (CLAUDE.md 8)
    "__pycache__",
    ".venv",
    ".venv_old",
    "build",
    "runtime",               # imported workflow JSON + templates, not source
    ".local_wip",            # a 2845-line fork of worker_service kept as a scratch copy
    "_sv_patch",
    "refactor_baseline",
})


# The file that marks a SpellVision checkout. Five hand-written searches climbed the tree looking
# for it, and all five agreed on this literal -- the only reason they could be merged without a
# behaviour decision. It lives here rather than in rules.py because it is a fact about this repo's
# layout, which is what this module owns; rules.py owns properties, and a rule that spelled a
# filename would look exactly like a rule scoped to one.
WORKER_ENTRY_POINT = "python/" + "worker_client" + ".py"
# The module that `_ws()` / `ws.` late-bind to. Spelled the same way, for the same reason.
WORKER_SERVICE_MODULE = "python/" + "worker_service" + ".py"
# The module that owns reading a live /object_info schema. Combo choices are read there and nowhere
# else, so a rule about that has to name it -- and a rule may not name a file, so the name lives
# here with its neighbours, for the same reason and spelled the same way.
COMFY_SCHEMA_READER_MODULE = "python/" + "comfy_graph_helpers" + ".py"


def _keep(path: Path) -> bool:
    return not any(part in EXCLUDED_DIRS for part in path.parts)


def python_sources() -> list[Path]:
    """Every Python module in the worker, including the ones in subdirectories.

    ``rglob`` rather than ``glob('*.py')``: the flat glob is exactly what hid
    ``python/runtime_adapters/`` and ``python/video_adapters/`` from every existing sweep.
    """
    return sorted(p for p in (ROOT / "python").rglob("*.py") if _keep(p))


def test_sources() -> list[Path]:
    """The tests themselves. Some rules apply here too -- a test that hardcodes a machine path is
    the same defect as production code that does."""
    return sorted(p for p in (ROOT / "tests").rglob("*.py") if _keep(p))


def cpp_sources() -> list[Path]:
    """The Qt side. Several rules are cross-language -- the seed range, the endpoint, machine paths
    -- and the audit found the C++ half of each of those unswept."""
    return sorted(
        p for p in (ROOT / "qt_ui").rglob("*")
        if p.suffix in {".cpp", ".h"} and _keep(p)
    )


def script_sources() -> list[Path]:
    """PowerShell launchers. Two of the audit's findings were a rule applied in one launcher and
    not its sibling."""
    return sorted(p for p in (ROOT / "scripts").rglob("*.ps1") if _keep(p))


def relative(path: Path) -> str:
    """Repo-relative, forward-slashed -- the form exemption keys use, so they are stable across
    machines and platforms."""
    return path.relative_to(ROOT).as_posix()
