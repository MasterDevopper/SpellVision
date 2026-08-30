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


# --- R7: every emitted wire type is registered -------------------------------------------------------


def _registered_message_types() -> set[str]:
    """Read from worker_client rather than restated here -- a second list would drift."""
    import sys

    sys.path.insert(0, str(sources.ROOT / "python"))
    import worker_client  # noqa: PLC0415

    return {
        value
        for name, group in vars(worker_client).items()
        if name.endswith("_MESSAGE_TYPES") and isinstance(group, set)
        for value in group
    } | {worker_client.CANONICAL_MESSAGE_TYPE}


def _check_unregistered_message_type(path: Path, text: str) -> list[Violation]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    registered = _registered_message_types()
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        # A WIRE message carries `ok`. That one extra key is what separates the ~46 real message
        # literals from the 68 dicts with a "type" field: `{"type": "krea2"}` is a CLIPLoader input
        # and `{"type": "teacache"}` is an acceleration descriptor. Measured: without it the rule
        # reports 23 unregistered types and 18 of them are noise -- the same over-reporting the
        # precision-dispute check had at 11%.
        if "ok" not in keys:
            continue
        for key_node, value_node in zip(node.keys, node.values):
            if not (isinstance(key_node, ast.Constant) and key_node.value == "type"):
                continue
            if not (isinstance(value_node, ast.Constant) and isinstance(value_node.value, str)):
                continue
            name = value_node.value
            if name in registered:
                continue
            out.append(Violation(
                path=path,
                line=node.lineno,
                key=name,
                detail=(
                    f"wire message type {name!r} is not registered in worker_client -- it reaches "
                    "the UI wrapped in a client_warning envelope"
                ),
            ))
    return out


R_MESSAGE_TYPE_REGISTERED = Rule(
    name="wire-types-registered",
    citation=(
        "Nine emitted types were registered nowhere, so each arrived at the UI inside a "
        "client_warning envelope. auth_error was the sharpest: an AUTHORISATION REFUSAL reaching "
        "the UI as ok: true. The old test verified that the registered types were registered, which "
        "is not the same question -- nothing derived the EMITTED set from the worker."
    ),
    select=sources.python_sources,
    check=_check_unregistered_message_type,
)


# --- R8: a submitted prompt is cancellable ----------------------------------------------------------

# Names that constitute registering a way to stop out-of-process work. `on_submitted` counts because
# a transport-only submit helper legitimately hands its prompt id to the caller that owns the job.
_CANCEL_REGISTRARS = {"track_comfy_prompt", "add_cancel_hook", "run_cancel_hooks", "on_submitted"}
_SUBMIT_HELPERS = {"_submit_comfy_prompt", "submit_comfy_prompt"}


def _check_cancellable_submission(path: Path, text: str) -> list[Violation]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    # Module scope, not function scope. A submit helper and the job that owns it are routinely
    # different functions -- the LTX route submits inside a snapshot builder and registers from the
    # callback it was handed -- so demanding both in one body would report a split that is correct
    # design. What must not happen is a MODULE that reaches ComfyUI and has no idea how to stop it.
    registers = any(
        (isinstance(node, ast.Name) and node.id in _CANCEL_REGISTRARS)
        or (isinstance(node, ast.Attribute) and node.attr in _CANCEL_REGISTRARS)
        or (isinstance(node, ast.arg) and node.arg in _CANCEL_REGISTRARS)
        for node in ast.walk(tree)
    )

    # Functions this module defines itself. A same-named LOCAL helper is a different function with
    # a different signature -- look_completion has its own `submit_comfy_prompt(graph, *, api,
    # client_id)`, which has no active_job to pass and registers through a callback instead. Facet B
    # asks about the SHARED submitter, so a locally-defined name is not it.
    local_defs = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    out: list[Violation] = []
    for node in ast.walk(tree):
        # Facet A: this module POSTs to /prompt itself.
        #
        # Scoped to constants whose text ENDS in /prompt, i.e. a URL tail. Measured: without that,
        # any string merely mentioning /prompt matches and the rule reports 14 sites of which 9 are
        # prose -- module docstrings explaining that /prompt rejects UI-graph exports, an error
        # message quoting the endpoint. Scoped: 5, every one a real submitter.
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.rstrip("/").endswith("/prompt") and not registers:
                out.append(Violation(
                    path=path,
                    line=node.lineno,
                    key=_enclosing_function(tree, node.lineno),
                    detail=(
                        "submits to ComfyUI /prompt but registers no cancel hook -- a cancel here "
                        "stops SpellVision watching while the render holds the GPU"
                    ),
                ))
        # Facet B: this module calls the shared submitter without handing over the job handle.
        if isinstance(node, ast.Call):
            called = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else "")
            if called not in _SUBMIT_HELPERS or called in local_defs:
                continue
            passes_handle = len(node.args) >= 3 or any(k.arg == "active_job" for k in node.keywords)
            if not passes_handle:
                out.append(Violation(
                    path=path,
                    line=node.lineno,
                    key=f"{_enclosing_function(tree, node.lineno)}::call",
                    detail=f"{called} called without an active_job, so the prompt id is untracked",
                ))
    return out


R_CANCELLABLE_SUBMISSION = Rule(
    name="cancellable-comfy-submission",
    citation=(
        "There was no /interrupt and no queue delete anywhere in the repo. Cancel set a flag, the "
        "poll loop raised, the UI showed a clean cancel -- and ComfyUI rendered the prompt to "
        "completion holding 20+ GB, long enough for the next submission to OOM against a job the "
        "user had already cancelled. The failure REPORTED SUCCESS. This rule is what makes the "
        "next route inherit the fix: it found a sixth submitter in runtime_adapters/, the directory "
        "that was invisible to every sweep in the repo."
    ),
    select=sources.python_sources,
    check=_check_cancellable_submission,
)


# --- R9: samplers go through the one resolver -------------------------------------------------------

_SAMPLING_INPUTS = {"sampler_name", "scheduler"}


def _check_hardcoded_sampler(path: Path, text: str) -> list[Violation]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        # Scoped to a ComfyUI NODE literal -- a dict carrying `class_type` -- and to the `inputs`
        # dict inside it. Measured: without that scoping the rule reports 38 sites, 27 of them in
        # family_operating_points.py, which is the DECLARATION TABLE. A literal there is the rule
        # being obeyed, not broken, and flagging it would have buried the eight real ones.
        if "class_type" not in keys:
            continue
        for key_node, value_node in zip(node.keys, node.values):
            if not (isinstance(key_node, ast.Constant) and key_node.value == "inputs"):
                continue
            if not isinstance(value_node, ast.Dict):
                continue
            for input_key, input_value in zip(value_node.keys, value_node.values):
                if not (isinstance(input_key, ast.Constant) and input_key.value in _SAMPLING_INPUTS):
                    continue
                if not (isinstance(input_value, ast.Constant) and isinstance(input_value.value, str)):
                    continue
                out.append(Violation(
                    path=path,
                    line=node.lineno,
                    key=f"{_enclosing_function(tree, node.lineno)}::{input_key.value}",
                    detail=(
                        f"{input_key.value}={input_value.value!r} is a literal in a graph node; the "
                        "cockpit offers this family a dropdown that cannot reach it"
                    ),
                ))
    return out


R_SAMPLER_RESOLVER = Rule(
    name="samplers-through-one-resolver",
    citation=(
        "The sampler dropdown was visible, populated per family, and inert: choosing er_sde for "
        "Krea 2 rendered euler. sampling_for fixed that for the seven image builders and stopped at "
        "the file boundary -- it lived in native_image_graphs, so the VIDEO builders could not "
        "import it, and Hunyuan and Mochi kept a literal while the generic split-stack builder read "
        "the request and validated nothing. Hunyuan is the sharpest: its allowlist advertised "
        "dpmpp_2m/normal as the default, picked alphabetically, and the graph could only ever "
        "produce euler/simple."
    ),
    select=sources.python_sources,
    check=_check_hardcoded_sampler,
)


# --- R10: every request key the UI sends has a reader -----------------------------------------------

# The identifiers a request payload is built in. Scoping by RECEIVER rather than by file, because a
# rule may not name a file -- and because the receiver is the honest signal: `payload.insert(...)`
# in a page is a request key, while `entry.insert(...)` in the same page is a display model.
#
# Measured: unscoped, "every QStringLiteral key inserted anywhere in qt_ui" reports 424 keys and 174
# with no reader, of which the great majority are not request keys at all -- window geometry in
# HomeDashboardSettings, favourite/hidden flags in ModelOverlayStore, history rows in T2VHistoryPage.
# Scoped to these four receivers: 224 keys, 65 unread, and they are all plausibly requests.
_REQUEST_RECEIVERS = ("payload", "request", "req", "command")

_CPP_INSERT = re.compile(
    r"\b(?:" + "|".join(_REQUEST_RECEIVERS) + r")\s*\.\s*insert\(\s*QStringLiteral\(\"([a-z0-9_]+)\"\)"
)

# What counts as the worker knowing about a key: it names the key, anywhere.
#
# Deliberately looser than ".get(key)". Measured both ways: the strict form reports 65 unread keys
# and the loose form 50, and every one of the 15 in the difference is a false positive -- a key read
# through a tuple of aliases (`for key in ("input_image", ..., "i2v_source_image")`), through
# `bounded_option(req, "steps")`, or through the FIELD_ALIASES table. The strict form would also
# have started flagging keys the moment they were routed through the resolver they were supposed to
# go through, which is a ratchet that punishes the fix.
#
# The question this rule asks is "can this key possibly be doing anything", and a key the worker
# never mentions by name cannot be.
_PY_STRING_LITERAL = re.compile(r"""["']([a-z0-9_]+)["']""")


def _worker_known_keys() -> set[str]:
    keys: set[str] = set()
    for path in sources.python_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        keys.update(m.group(1) for m in _PY_STRING_LITERAL.finditer(text))
    return keys


def _check_unread_request_key(path: Path, text: str) -> list[Violation]:
    read = _worker_known_keys()
    out: list[Violation] = []
    seen: set[str] = set()
    for match in _CPP_INSERT.finditer(text):
        key = match.group(1)
        if key in read or key in seen:
            continue
        seen.add(key)
        out.append(Violation(
            path=path,
            line=text.count("\n", 0, match.start()) + 1,
            key=key,
            detail=(
                f"the UI sends {key!r} and nothing on the worker side reads it -- if it drives a "
                "control, that control does nothing"
            ),
        ))
    return out


R_REQUEST_KEY_HAS_READER = Rule(
    name="request-keys-have-readers",
    citation=(
        "VAE Tiling was shown EXACTLY where it is ignored: the checkbox appeared only for WAN "
        "dual-noise, and the dual-noise builder never reads enable_vae_tiling -- the one builder "
        "that does is the wrapper route, where the checkbox was hidden. Looking for the rule rather "
        "than the instance found the same defect with the sign flipped: the cockpit sends six WAN "
        "split keys (wan_split, high_steps, low_steps, split_step, noise_split_step, "
        "wan_noise_split_step) and the dual-noise builder read NONE of them, so High Noise Steps, "
        "Low Noise Steps and Split Step were three inert controls, visible only in the mode where "
        "they did nothing. One edit would have fixed a checkbox; the rule found four more."
    ),
    select=sources.cpp_sources,
    check=_check_unread_request_key,
)


# --- R11: one ComfyUI root resolver -----------------------------------------------------------------

# The four names the install root has been read under. All four still work -- they feed one chain --
# but only inside the resolver.
_ROOT_ENV_NAMES = ("SPELLVISION_COMFY", "SPELLVISION_COMFY_ROOT", "COMFYUI_ROOT", "COMFY_ROOT")

_ENV_READ = re.compile(
    r"""(?:environ\s*(?:\.get\(|\[)|getenv\(|qgetenv\()\s*["']("""
    + "|".join(_ROOT_ENV_NAMES) + r""")["']"""
)

# Mechanises CLAUDE.md 9.2. The rollback tree is kept so the 2026-07-17 cutover can be undone; code
# that NAMES it is code that can silently run against the May core while everything else talks to
# the July one.
_ROLLBACK_TREE = re.compile(r"comfy_runtime[/\\]+ComfyUI", re.IGNORECASE)


def _rollback_site_key(text: str, line: int) -> str:
    """The enclosing function where the source parses as Python, else the line.

    Deliberately not a suffix test: this rule sweeps both languages, and a literal file extension in
    a rule is what `test_no_rule_names_a_file` exists to stop -- it caught this very expression.
    """
    try:
        return _enclosing_function(ast.parse(text), line)
    except SyntaxError:
        return str(line)


def _check_comfy_root_resolver(path: Path, text: str) -> list[Violation]:
    out: list[Violation] = []
    # The resolver is allowed to name what it resolves between -- that is what makes it the
    # resolver. Identified by DECLARING the precedence list rather than by filename, so moving or
    # renaming the module does not silently disable the rule.
    if ("ROOT_ENV_VARS" in text and "def comfy_root(" in text) or (
            "kComfyRootEnvNames" in text and "resolvePreferredComfyRoot" in text):
        return out

    for match in _ENV_READ.finditer(text):
        out.append(Violation(
            path=path,
            line=text.count("\n", 0, match.start()) + 1,
            key=f"env:{match.group(1)}",
            detail=(
                f"reads {match.group(1)} directly; the install root has four historical names and "
                "reading one of them is how a consumer stops seeing the configured value"
            ),
        ))

    for match in _ROLLBACK_TREE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        # A COMMENT may name it -- half of what this repo knows about the cutover is written down
        # next to the code that had to change for it.
        source_line = text.splitlines()[line - 1].strip() if line <= text.count("\n") + 1 else ""
        if source_line.startswith(("#", "//", "*", "/*")):
            continue
        out.append(Violation(
            path=path,
            line=line,
            key=f"rollback:{_rollback_site_key(text, line)}",
            detail=(
                "names the ROLLBACK ComfyUI tree (CLAUDE.md 9.2 keeps it for rollback only); "
                "resolve the root instead"
            ),
        ))
    return out


R_COMFY_ROOT_RESOLVER = Rule(
    name="one-comfy-root-resolver",
    citation=(
        "Qt's RuntimeProfile exports SPELLVISION_COMFY and nothing else; video_family_readiness "
        "read SPELLVISION_COMFY_ROOT and COMFYUI_ROOT and nothing else. The intersection is empty, "
        "so readiness could NEVER see the configured root -- it answered about a different ComfyUI "
        "than the one generating, and on a box with the D: tree present that was the rollback build "
        "CLAUDE.md 9.2 forbids probing as live. Three more modules hardcoded that tree outright."
    ),
    select=lambda: sources.python_sources() + sources.cpp_sources(),
    check=_check_comfy_root_resolver,
)


# --- R12: every module is reachable, and every import is used ----------------------------------------

_ENTRY_POINTS = frozenset({"worker_service", "worker_client", "worker_tcp"})

# An import can BE its own purpose. Neither of these is dead, and removing either turns a checked
# capability into a crash at the point of use.
_DELIBERATE = (
    "inside a try/except ImportError -- an availability probe whose signal is the exception",
    "marked # noqa: F401 -- the author already told the linter it is deliberate",
)


def _module_name(path: Path) -> str:
    rel = path.relative_to(sources.ROOT / "python")
    name = str(rel.with_suffix("")).replace("\\", ".").replace("/", ".")
    return name[: -len(".__init__")] if name.endswith(".__init__") else name


def _import_edges(name: str, tree: ast.Module) -> set[str]:
    """Every module this one imports, with RELATIVE imports resolved.

    Resolving them is the whole correctness of this rule. The first version of this sweep skipped
    `node.level` and reported `video_adapters/ltx_adapter.py` as unreachable -- a live adapter,
    reached only by `from .ltx_adapter import LtxVideoAdapter` in its sibling registry, and one
    deletion away from being removed on the strength of a green sweep.
    """
    pkg = name.rsplit(".", 1)[0] if "." in name else ""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg if node.level == 1 else ".".join(pkg.split(".")[: -(node.level - 1)])
                target = f"{base}.{node.module}" if node.module else base
            elif node.module:
                target = node.module
            else:
                continue
            out.add(target)
            out.update(f"{target}.{a.name}" for a in node.names if a.name != "*")
    return out


def _reachable_modules() -> set[str]:
    """Computed once for the whole tree; the per-file check just asks whether it is in the set."""
    trees: dict[str, ast.Module] = {}
    for path in sources.python_sources():
        try:
            trees[_module_name(path)] = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue

    # A module named in an IMPORT STATEMENT of a test or script is an entry too. Matched as an
    # import rather than as a bare word: `base` and `registry` appear in ordinary prose, and a
    # substring heuristic would call every module reachable and report nothing forever.
    seeds = set(_ENTRY_POINTS)
    named = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)
    for path in sources.test_sources() + sources.script_sources() + sources.cpp_sources():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        seeds.update(named.findall(text))
        # Qt and PowerShell spawn workers by file name, not by import. The suffix is built rather
        # than spelled: a literal here trips the guard that forbids a rule from naming files, and
        # that guard is right to -- it is the same check that caught R11.
        suffix = "." + "py"
        for module in trees:
            if module.split(".")[-1] + suffix in text:
                seeds.add(module)

    seen: set[str] = set()
    stack = [s for s in seeds]
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in trees:
            continue
        seen.add(cur)
        for dep in _import_edges(cur, trees[cur]):
            parts = dep.split(".")
            for i in range(len(parts), 0, -1):
                cand = ".".join(parts[:i])
                if cand in trees and cand not in seen:
                    stack.append(cand)
    return seen


_REACHABLE: set[str] | None = None


def _check_module_is_reachable(path: Path, text: str) -> list[Violation]:
    global _REACHABLE
    if _REACHABLE is None:
        _REACHABLE = _reachable_modules()
    name = _module_name(path)
    if name in _REACHABLE:
        return []
    return [Violation(
        path=path,
        line=1,
        key=f"unreachable:{name}",
        detail=(
            "no entry point reaches this module -- it is a parallel implementation that cannot "
            "receive a fix applied to the live one"
        ),
    )]


R_MODULE_REACHABLE = Rule(
    name="every-module-is-reachable",
    citation=(
        "`python/runtime_adapters/` was a complete, coherent, 713-line second implementation of "
        "submit-and-poll that nothing imported. Doc 20 flagged it as orphaned in 2026-06 and Doc 21 "
        "left it as an author call; it then sat there long enough to collect its own copies of two "
        "defects this audit fixed elsewhere -- an unsayable zero and an uncancellable submission -- "
        "which had to be written up as exemptions in code with no consumer. An unreachable module "
        "is where the meta-finding lives: it looks like an implementation, so the next reader "
        "believes the rule is applied twice when it is applied once."
    ),
    select=sources.python_sources,
    check=_check_module_is_reachable,
)


# --- R13: text encoder placement goes through the one resolver --------------------------------------

_DEVICE_INPUT_NAMES = {"device"}
_TEXT_ENCODER_RESOLVERS = {"text_encoder_device", "text_encoder_device_input"}


def _check_text_encoder_placement(path: Path, text: str) -> list[Violation]:
    """A `device` input on a text-encoder node, written by hand.

    Two node families answer "where does the text encoder run" with different words for the same
    place -- core ComfyUI spells on-GPU "default", the kijai Wan wrapper spells it "gpu" -- and five
    builders wrote the answer inline while all of them read ONE request key. A stated "gpu" reached
    a combo that does not contain it and ComfyUI answered with a 400 naming a node the user never
    chose. Four of the five also skipped the memory profile entirely, so a low-VRAM setting offloaded
    krea2's text encoder and nobody else's.

    Merging the vocabularies would be the wrong fix at the wrong level; translating one intent into
    each node's own spelling, read from /object_info, is the right one.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    out: list[Violation] = []
    for node in ast.walk(tree):
        # `_set_if_allowed(inputs, allowed, ("device",), <expr>)`
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else "")
            if name == "_set_if_allowed" and len(node.args) >= 4:
                key = node.args[2]
                names = {e.value for e in key.elts
                         if isinstance(e, ast.Constant) and isinstance(e.value, str)}                     if isinstance(key, (ast.Tuple, ast.List)) else set()
                if names & _DEVICE_INPUT_NAMES and not _calls_any(node.args[3], _TEXT_ENCODER_RESOLVERS):
                    out.append(Violation(
                        path=path, line=node.lineno,
                        key=f"{_enclosing_function(tree, node.lineno)}::device",
                        detail=("a text-encoder `device` written by hand; the two node families "
                                "spell the same placement differently, so the user's word has to be "
                                "translated per node rather than forwarded"),
                    ))
        # A literal node dict carrying a hand-written `device`.
        #
        # Scoped to the `inputs` of a dict that also names a `class_type`, rather than to any dict
        # with a "device" key. The looser form reported three sites where two were real: the third
        # was MODEL_CACHE, a plain state dict whose "device" is a torch device, not a node input.
        # A rule that flags three where two are real is the R7 over-count again.
        if isinstance(node, ast.Dict) and _is_node_literal(node):
            inputs = _dict_value(node, "inputs")
            if inputs is None:
                continue
            for k, v in zip(inputs.keys, inputs.values):
                if not (isinstance(k, ast.Constant) and k.value in _DEVICE_INPUT_NAMES):
                    continue
                if isinstance(v, ast.Constant) or _reads_request_key(v):
                    out.append(Violation(
                        path=path, line=getattr(k, "lineno", node.lineno),
                        key=f"{_enclosing_function(tree, getattr(k, 'lineno', node.lineno))}::device-literal",
                        detail=("a `device` value written into a node literal; it must come from "
                                "the resolver, which reads the node's own accepted values"),
                    ))
    return out


def _is_node_literal(node: ast.Dict) -> bool:
    """A dict that declares a `class_type` -- i.e. a ComfyUI node, not any dict with a device key."""
    return any(isinstance(k, ast.Constant) and k.value == "class_type" for k in node.keys)


def _dict_value(node: ast.Dict, name: str) -> ast.Dict | None:
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and k.value == name and isinstance(v, ast.Dict):
            return v
    return None


def _calls_any(expr: ast.AST, names: set[str]) -> bool:
    for node in ast.walk(expr):
        if isinstance(node, ast.Call):
            called = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else "")
            if called in names:
                return True
    return False


def _reads_request_key(expr: ast.AST) -> bool:
    """`req.get("...")` anywhere in the expression -- a hand-rolled read of the user's value."""
    for node in ast.walk(expr):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"req", "request", "stack"}):
            return True
    return False


R_TEXT_ENCODER_PLACEMENT = Rule(
    name="text-encoder-placement-through-one-resolver",
    citation=(
        "Core ComfyUI's CLIPLoader takes device ['default', 'cpu']; the kijai WanVideoTextEncode "
        "takes ['gpu', 'cpu']. Five builders read one request key and forwarded the user's word to "
        "whichever of those was in front of them, so a stated 'gpu' 400'd on a core route and a "
        "stated 'default' 400'd on the wrapper -- and LTX read a DIFFERENT key entirely, silently "
        "dropping the cockpit's value. Four of the five never consulted the memory profile, so a "
        "low-VRAM profile moved krea2's text encoder off the GPU and left every other family's on it."
    ),
    select=sources.python_sources,
    check=_check_text_encoder_placement,
)


# --- R14: the latent decode is a declaration, not a literal ------------------------------------------

def _check_decode_through_resolver(path: Path, text: str) -> list[Violation]:
    """A ``VAEDecode`` written as a node literal cannot see ``enable_vae_tiling``.

    The cockpit inserts that key into EVERY request it builds, and eleven image decode sites wrote a
    bare VAEDecode -- so the answer "yes, tile" had nowhere to land on any image route. The video
    side had the opposite problem: hunyuan and mochi hardcoded VAEDecodeTiled, which is a decision
    taken away from the user rather than one offered to them.

    Tiling is wired as a CONTROL and carries no speed or memory claim: rule 1 says a heuristic ships
    with a number, and there is no measurement for tiled image decode on this box. What was wrong was
    never the absence of a default -- it was that the switch was unreachable.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Dict) and _is_node_literal(node)):
            continue
        for k, v in zip(node.keys, node.values):
            if not (isinstance(k, ast.Constant) and k.value == "class_type"):
                continue
            if isinstance(v, ast.Constant) and v.value in {"VAEDecode", "VAEDecodeTiled"}:
                out.append(Violation(
                    path=path, line=node.lineno,
                    key=f"{_enclosing_function(tree, node.lineno)}::{v.value}",
                    detail=(f"{v.value} written as a literal; the decode must come from "
                            "vae_decode_node so the request's tiling switch is reachable"),
                ))
    return out


R_DECODE_RESOLVER = Rule(
    name="latent-decode-through-one-resolver",
    citation=(
        "`enable_vae_tiling` is inserted into every request the cockpit builds and eleven image "
        "decode sites wrote a bare VAEDecode, so the switch had nowhere to land on any image route. "
        "Meanwhile hunyuan and mochi hardcoded VAEDecodeTiled -- the same decision, taken away from "
        "the user instead of offered. Decode-side memory is the lever that matters here: the FP8 "
        "measurement established that peak is driven by activations and VAE decode rather than "
        "weights, which is why a quantized checkpoint bought only ~1.5 GB."
    ),
    select=sources.python_sources,
    check=_check_decode_through_resolver,
)


ALL_RULES: tuple[Rule, ...] = (
    R_SEED,
    R_NUMERIC_DEFAULT,
    R_MACHINE_PATH,
    R_TERMINAL_TRANSITION,
    R_MESSAGE_TYPE_REGISTERED,
    R_CANCELLABLE_SUBMISSION,
    R_SAMPLER_RESOLVER,
    R_REQUEST_KEY_HAS_READER,
    R_COMFY_ROOT_RESOLVER,
    R_MODULE_REACHABLE,
    R_TEXT_ENCODER_PLACEMENT,
    R_DECODE_RESOLVER,
)


def run_all() -> dict[str, list[Violation]]:
    return {rule.name: rule.run() for rule in ALL_RULES}
