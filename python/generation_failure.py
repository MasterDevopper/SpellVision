"""Label a job failure by whose fault it is.

The pill beside Generate shows whatever message the exception carried. For a bad width or a missing
checkpoint that is the right text. For `module 'worker_service' has no attribute
'resolve_comfy_output_path'` it is not: that is a SpellVision defect, and a user reading it has no
way to know it is not something they did. The 2026-09-01 security pass shipped exactly that message
to the first live T2I on 2026-09-02, and it was the wording, as much as the break, that made the
error unhelpful.

So the queue runner classifies before it emits. A programming error -- the exception types that only
a defect raises -- gets code ``internal_error`` and a message that says so and asks for a report,
with the original text preserved after it. Everything else keeps its message and the
``generation_error`` code that History, the runtime cache and the UI already understand.
"""
from __future__ import annotations

INTERNAL_ERROR_CODE = "internal_error"
GENERATION_ERROR_CODE = "generation_error"

# Types no user input can raise on a working build. KeyError and TypeError are here deliberately:
# a request that reaches the runner has already passed validation, so a KeyError deep in a builder
# is a builder bug, not a bad request. If a family ever needs to raise one of these for a user
# mistake, it should raise ValueError with a sentence instead.
PROGRAMMING_ERRORS: tuple[type[BaseException], ...] = (
    AttributeError,
    NameError,
    TypeError,
    KeyError,
    IndexError,
    ImportError,
    AssertionError,
    NotImplementedError,
    RecursionError,
    UnboundLocalError,
)

INTERNAL_ERROR_PREFIX = "Internal error in SpellVision (please report this)"


def classify_failure(exc: BaseException) -> tuple[str, str]:
    """(code, user-facing message) for an exception that stopped a job."""
    text = str(exc).strip() or type(exc).__name__
    if isinstance(exc, PROGRAMMING_ERRORS):
        return INTERNAL_ERROR_CODE, f"{INTERNAL_ERROR_PREFIX}: {type(exc).__name__}: {text}"
    return GENERATION_ERROR_CODE, text


def is_internal_error_code(code: str | None) -> bool:
    return (code or "") == INTERNAL_ERROR_CODE
