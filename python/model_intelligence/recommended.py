"""One answer for "what settings does this model want", with its provenance attached.

Four sources disagree, so the order is declared once, here:

    user  >  site:image-meta-mode  >  card:snippet-regex  >  card:prose-regex  >  table:family-default

The site's own example images outrank a card snippet because they are what THIS model's author
renders with, repeatedly. That ordering is not theoretical: the owner's house checkpoint publishes
10 steps / CFG 1 unanimously across ten examples while the family table says 52 / 3.5, and the
app has been rendering it at 52.

Confidence is agreement, not certainty: unanimous over ten examples is 1.0, one example out of
four is 0.25. It travels with the value so a caller can show "n=10" rather than implying the
number is authoritative.

A field with no source is ABSENT. Nothing here invents a value.
"""
from __future__ import annotations

from typing import Any

from model_intelligence import family_seed_table, meta_parse

PROVENANCE_ORDER: tuple[str, ...] = (
    "user",
    "site:image-meta-mode",
    "site:trainedWords",
    "card:frontmatter",
    "card:snippet-regex",
    "card:prose-regex",
    "table:family-default",
)

_RANK = {name: index for index, name in enumerate(PROVENANCE_ORDER)}

FIELDS = (
    "steps", "cfg", "guidance", "shift", "sampler", "scheduler", "clip_skip",
    "width", "height", "frames", "fps", "lora_strength", "prompt_prefix",
)


def _entry(value: Any, provenance: str, *, n: int | None = None, total: int | None = None,
           confidence: float | None = None) -> dict[str, Any]:
    if confidence is None:
        confidence = (n / total) if (n and total) else 1.0
    return {
        "value": value,
        "provenance": provenance,
        "confidence": round(float(confidence), 3),
        "n": n,
        "total": total,
    }


def _offer(out: dict[str, dict[str, Any]], field: str, candidate: dict[str, Any]) -> None:
    """Keep the candidate only if its provenance outranks what is already there."""
    if field not in FIELDS:
        return
    current = out.get(field)
    if current is None or _RANK[candidate["provenance"]] < _RANK[current["provenance"]]:
        out[field] = candidate


def build(
    *,
    civitai_version: dict[str, Any] | None,
    card_settings: dict[str, dict[str, Any]] | None,
    family: str | None,
    existing_user: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    for field, entry in (existing_user or {}).items():
        if field in FIELDS:
            out[field] = _entry(entry.get("value"), "user", confidence=1.0)

    version = civitai_version or {}
    metas = [image.get("meta") for image in version.get("images") or []]
    for field, mode in meta_parse.mode_over(metas).items():
        _offer(out, field, _entry(mode["value"], "site:image-meta-mode",
                                  n=mode["n"], total=mode["total"]))

    words = [str(w).strip() for w in version.get("trainedWords") or [] if str(w).strip()]
    if words:
        _offer(out, "prompt_prefix", _entry(", ".join(words), "site:trainedWords"))

    for field, entry in (card_settings or {}).items():
        provenance = str(entry.get("provenance") or "card:prose-regex")
        if provenance in _RANK:
            _offer(out, field, _entry(entry.get("value"), provenance))

    variant = None
    base = str(version.get("baseModel") or "")
    name = f"{version.get('name') or ''} {base}".lower()
    if "turbo" in name:
        variant = "turbo"
    for field, value in family_seed_table.seed_for(family, variant).items():
        _offer(out, field, _entry(value, "table:family-default"))

    return out
