"""Tree-wide properties, each cited to the defect that produced it.

A rule here answers one question over every source file, and it may not name a file -- see
``sources.py`` for why. Where a site legitimately differs, it goes in ``exemptions.py`` **with a
reason**, which is the third state the old ratchets lacked: today a violation outside a ratchet's
hardcoded file list is not compliant, not violating, and not a documented exception -- it is merely
out of scope, which is how a defect hides in plain sight.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from . import sources


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    key: str      # stable across line shifts -- the exemption key
    detail: str

    @property
    def site(self) -> str:
        return f"{sources.relative(self.path)}::{self.key}"

    def __str__(self) -> str:
        return f"{sources.relative(self.path)}:{self.line}  {self.detail}"


@dataclass(frozen=True)
class Rule:
    name: str
    citation: str
    select: Callable[[], list[Path]]
    check: Callable[[Path, str], list[Violation]]

    def run(self) -> list[Violation]:
        found: list[Violation] = []
        for path in self.select():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            found.extend(self.check(path, text))
        return found


def _enclosing_function(tree: ast.Module, lineno: int) -> str:
    """The nearest enclosing def, used as the exemption key.

    A line number would be a terrible key -- every edit above a site would invalidate its exemption
    and quietly re-report it. A function name survives ordinary editing.
    """
    best = "<module>"
    best_line = -1
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= lineno <= (node.end_lineno or node.lineno) and node.lineno > best_line:
                best, best_line = node.name, node.lineno
    return best


# --- R1: seeds -------------------------------------------------------------------------------------

_SEED_RESOLVERS = {"resolve_seed", "stated_seed"}


def _check_seed(path: Path, text: str) -> list[Violation]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if not any(n in {"seed", "noise_seed"} for n in names):
            continue
        # A literal is not a decision about the request -- `seed = 0` as a local default is fine.
        if isinstance(node.value, ast.Constant):
            continue
        calls = {
            c.func.id for c in ast.walk(node.value)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        }
        if calls & _SEED_RESOLVERS:
            continue
        # Does it read the request at all? A seed derived from something else entirely (a loop
        # index, a hash) is not this rule's business.
        source = ast.unparse(node.value)
        if not re.search(r"\b(req|request|payload)\b", source):
            continue
        out.append(Violation(
            path=path,
            line=node.lineno,
            key=_enclosing_function(tree, node.lineno),
            detail=f"seed from the request without resolve_seed/stated_seed: {source[:90]}",
        ))
    return out


R_SEED = Rule(
    name="seed-one-rule",
    citation=(
        "Seed 0 meant four different things across twelve builders: honoured, silently 1, a clock "
        "reading, or no generator at all. resolve_seed/stated_seed is the one rule. The ratchet "
        "that shipped with it named three files and missed clothes_only.py (seed 0 -> 7) and "
        "look_completion.py (seed 0 -> 4419)."
    ),
    select=sources.python_sources,
    check=_check_seed,
)


# --- R2: a default must not replace a stated value -------------------------------------------------

# Fields where a falsy value is a legitimate thing to ask for. cfg 0.0 is a real request (KSampler
# declares min 0.0 and both spin boxes offer it); denoise 0.0 means "return the input unchanged";
# a timeout or limit of 0 is a deliberate instruction.
_ZERO_IS_MEANINGFUL = (
    "cfg", "denoise", "strength", "guidance", "shift", "steps", "width", "height",
    "timeout", "timeout_sec", "limit", "batch", "fps", "frames", "scale", "weight",
    "overlap", "threshold", "seed",
)

_REQUEST_GET = re.compile(
    r"""(?:req|request|payload|_op|_defaults|stack|model_stack)\s*\.\s*get\s*\(\s*["']([a-z0-9_]+)["']"""
)


def _check_numeric_default(path: Path, text: str) -> list[Violation]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    out: list[Violation] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)):
            continue
        default = node.values[-1]
        if not (isinstance(default, ast.Constant)
                and isinstance(default.value, (int, float))
                and not isinstance(default.value, bool)):
            continue
        # `x or 0` substitutes a value equal to what it replaced -- harmless.
        if default.value == 0:
            continue
        source = ast.unparse(node)
        match = _REQUEST_GET.search(source)
        if not match:
            continue
        field = match.group(1)
        if not any(field == name or field.endswith("_" + name) or field.startswith(name + "_")
                   for name in _ZERO_IS_MEANINGFUL):
            continue
        out.append(Violation(
            path=path,
            line=node.lineno,
            key=f"{_enclosing_function(tree, node.lineno)}:{field}",
            detail=f"`or {default.value}` makes a stated 0 unsayable for {field!r}: {source[:90]}",
        ))
    return out


R_NUMERIC_DEFAULT = Rule(
    name="zero-is-sayable",
    citation=(
        "Doc 50 rule 8. denoise 0.0 ('return the input unchanged') is clamped to 0.6 in six image "
        "builders and INVERTED to 1.0 in two video builders, while Flux in the same file honours "
        "it. cfg 0.0 is unsayable in nine builders while both UI spin boxes offer it. "
        "numeric_option() was written for exactly this and is used at three call sites."
    ),
    select=sources.python_sources,
    check=_check_numeric_default,
)


# --- R8: machine-specific absolute paths ------------------------------------------------------------

_MACHINE_PATH = re.compile(
    r"""["'][A-Za-z]:[\\/](?!tmp\b)[^"'\n]{3,}["']""",
    re.IGNORECASE,
)


def _check_machine_path(path: Path, text: str) -> list[Violation]:
    out: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("#", "//", "*")):
            continue
        match = _MACHINE_PATH.search(line)
        if not match:
            continue
        out.append(Violation(
            path=path,
            line=number,
            key=match.group(0).strip("\"'"),
            detail=f"machine-specific absolute path: {match.group(0)}",
        ))
    return out


R_MACHINE_PATH = Rule(
    name="no-machine-paths",
    citation=(
        "The ComfyUI install root is resolved at eight sites under four env names, and two of them "
        "cannot see the configured value at all -- they fall back to a hardcoded "
        "D:/AI_ASSETS/comfy_runtime/ComfyUI, the rollback build CLAUDE.md 9.2 forbids probing as "
        "live. A hardcoded path is how a resolver stops being one."
    ),
    select=lambda: sources.python_sources() + sources.cpp_sources(),
    check=_check_machine_path,
)


# --- R6: a terminaliser must not discard its transition ---------------------------------------------

_TERMINAL_TARGETS = {"COMPLETED", "FAILED", "CANCELLED"}


def _check_discarded_terminal_transition(path: Path, text: str) -> list[Violation]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    out: list[Violation] = []
    for node in ast.walk(tree):
        # An Expr statement wrapping a Call is a call whose value is thrown away.
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name != "transition_job":
            continue
        target = ast.unparse(node.value.args[-1]) if node.value.args else ""
        if not any(t in target for t in _TERMINAL_TARGETS):
            continue
        out.append(Violation(
            path=path,
            line=node.lineno,
            key=f"{_enclosing_function(tree, node.lineno)}:{target.split('.')[-1]}",
            detail=(
                f"discards transition_job(..., {target.split('.')[-1]}) -- if the hop is illegal the "
                "job stays non-terminal and the queue item re-runs on every restart"
            ),
        ))
    return out


R_TERMINAL_TRANSITION = Rule(
    name="terminalisers-check-their-hop",
    citation=(
        "QUEUED -> FAILED is not a legal transition and fail_job discarded transition_job's return, "
        "so fourteen handlers that raise before STARTING left the job at QUEUED with an error. The "
        "queue item then reverted to QUEUED, was persisted, and was rebuilt into `pending` on every "
        "worker start -- re-running and re-failing forever. Scoped to TERMINAL targets: a discarded "
        "STARTING/RUNNING hop is a different, milder question and flagging all 30 would bury this."
    ),
    select=sources.python_sources,
    check=_check_discarded_terminal_transition,
)


ALL_RULES: tuple[Rule, ...] = (
    R_SEED,
    R_NUMERIC_DEFAULT,
    R_MACHINE_PATH,
    R_TERMINAL_TRANSITION,
)


def run_all() -> dict[str, list[Violation]]:
    return {rule.name: rule.run() for rule in ALL_RULES}
