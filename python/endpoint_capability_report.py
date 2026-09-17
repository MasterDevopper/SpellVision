"""The shape of the answer to "can this job run there".

Split out of ``endpoint_capability`` for the same reason ``model_resolution_offer`` sits beside
``model_resolution_commands``: the probes that talk to a ComfyUI and the vocabulary a refusal is
written in are separate concerns, and the second is what every caller actually reads.

A refusal is a NAME, never a verdict. "Cannot run there" tells a user nothing they can act on;
"SpellNode does not have loxsUtopicWorldKrea2_v20Quants.safetensors" tells them what to copy. That
is why ``missing`` is a field and not something to be parsed back out of ``detail``, and why
``ok=False`` with an empty ``refusals`` reads as "was not checked" rather than as a silent no.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class Refusal:
    """A named reason. ``missing`` is what a user has to go and put on the machine."""

    check: str            # health | models | nodes | graph
    code: str             # machine-readable
    detail: str           # one sentence, names the endpoint and the thing
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilityReport:
    """``ok`` is only true when every check that ran passed. Default False: fail closed."""

    endpoint: str
    label: str = ""
    ok: bool = False
    checks_run: tuple[str, ...] = ()
    refusals: tuple[Refusal, ...] = ()
    health: dict[str, Any] = field(default_factory=dict)

    def missing_models(self) -> tuple[str, ...]:
        return tuple(m for r in self.refusals if r.check == "models" for m in r.missing)

    def missing_classes(self) -> tuple[str, ...]:
        return tuple(m for r in self.refusals if r.check == "nodes" for m in r.missing)

    def where(self) -> str:
        return self.label or self.endpoint

    def explain(self) -> str:
        if self.ok:
            return f"{self.where()} can run this job."
        if not self.refusals:
            # Not ok and nothing to say is its own answer, and saying so beats an empty string that
            # a UI would render as a blank refusal.
            return f"{self.where()} was not checked."
        return " ".join(r.detail for r in self.refusals)

    def payload(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "label": self.label,
            "ok": self.ok,
            "checks_run": list(self.checks_run),
            "message": self.explain(),
            "health": dict(self.health),
            "refusals": [
                {"check": r.check, "code": r.code, "detail": r.detail, "missing": list(r.missing)}
                for r in self.refusals
            ],
        }


def and_list(values: Iterable[str]) -> str:
    """"a", "a and b", "a, b and c" -- so a refusal naming three files reads as a sentence."""
    items = [str(v) for v in values]
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " and " + items[-1]
