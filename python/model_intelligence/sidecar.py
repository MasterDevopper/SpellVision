"""`<stem>.spellvision.json` -- what SpellVision knows about one weight.

Beside the weight rather than in a central database, for three reasons: it moves with the file,
it survives a reinstall, and the existing sidecar conventions (`<stem>.metadata.json`,
`<stem>.preview.png`) already live there, so a user who understands one understands this.

Two rules the merge exists to enforce:

  * anything the USER set is never overwritten by a refresh (`user_override: true` on a display
    field, `provenance: "user"` on a recommended one). A refresh that silently reverted a rename
    would be data loss wearing the costume of a working feature.
  * unknown top-level keys are preserved. A sidecar written by a newer build must survive a
    round-trip through an older one.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from model_intelligence import recommended as recommended_mod

SCHEMA = "spellvision.model-sidecar/1"
SUFFIX = ".spellvision.json"

_KNOWN_TOP_LEVEL = {"schema", "identity", "display", "recommended", "user"}


def sidecar_path(weight: str | Path) -> Path:
    path = Path(str(weight))
    return path.with_name(path.stem + SUFFIX)


def read(weight: str | Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(sidecar_path(weight).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def write(weight: str | Path, payload: dict[str, Any]) -> Path:
    target = sidecar_path(weight)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, target)
    return target


def user_values(existing: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The recommended entries the user set, for feeding back into `recommended.build`."""
    out: dict[str, dict[str, Any]] = {}
    for field, entry in ((existing or {}).get("recommended") or {}).items():
        if isinstance(entry, dict) and entry.get("provenance") == "user":
            out[field] = entry
    return out


def merge(existing: dict[str, Any] | None, fresh: dict[str, Any]) -> dict[str, Any]:
    """Fresh data wins, except where the user has spoken."""
    if not existing:
        return dict(fresh)

    merged = dict(fresh)

    display = dict(fresh.get("display") or {})
    for field, entry in (existing.get("display") or {}).items():
        if isinstance(entry, dict) and entry.get("user_override"):
            display[field] = entry
        elif field not in display:
            display[field] = entry
    merged["display"] = display

    wanted = dict(fresh.get("recommended") or {})
    wanted.update(user_values(existing))
    merged["recommended"] = wanted

    if existing.get("user"):
        merged["user"] = existing["user"]

    for key, value in existing.items():
        if key not in _KNOWN_TOP_LEVEL and key not in merged:
            merged[key] = value

    return merged


def carry_forward(
    existing: dict[str, Any] | None,
    *,
    weight: str | Path,
    sha256: str,
    kind: str,
    family: str | None,
) -> dict[str, Any]:
    """What a refresh is allowed to write when the LOOKUP FAILED.

    `build_payload(civitai_version=None, ...)` is the payload for "the site answered and does not
    know this hash". Using it for "we could not ask the site" is what let one offline refresh
    revert every identified model to its filename with no pictures and no trigger words, and
    report ok. This writes only what the run actually established -- the digest, the size, the
    kind, the family -- over whatever the last successful run recorded.
    """
    path = Path(str(weight))
    payload = dict(existing or {})
    identity = dict(payload.get("identity") or {})
    try:
        size: int | None = path.stat().st_size
    except OSError:
        size = None
    identity.update({
        "file_name": path.name,
        "size": size,
        "hashes": {"sha256": sha256, "autov2": (sha256 or "")[:10]},
        "kind": kind,
        # An undetermined family must not erase one a previous run determined.
        "family": family or identity.get("family"),
    })
    identity.setdefault("sources", [])
    payload["schema"] = SCHEMA
    payload["identity"] = identity
    payload.setdefault("display", {})
    payload.setdefault("recommended", {})
    payload.setdefault("user", {"notes": "", "favorite": False})
    return payload


def build_payload(
    *,
    weight: str | Path,
    sha256: str,
    kind: str,
    family: str | None,
    civitai_version: dict[str, Any] | None,
    hf: dict[str, Any] | None,
    recommended: dict[str, dict[str, Any]],
    images: list[dict[str, Any]] | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    path = Path(str(weight))
    version = civitai_version or {}
    model = version.get("model") or {}
    card = hf or {}

    sources: list[dict[str, Any]] = []
    if version:
        sources.append({
            "site": "civitai",
            "model_id": version.get("modelId"),
            "version_id": version.get("id"),
            "url": f"https://civitai.com/models/{version.get('modelId')}"
                   f"?modelVersionId={version.get('id')}",
            "fetched_at": fetched_at,
        })
    if card.get("repo"):
        sources.append({"site": "huggingface", "repo": card.get("repo"),
                        "path": card.get("path"), "fetched_at": fetched_at})

    try:
        size = path.stat().st_size
    except OSError:
        size = None

    name = model.get("name") or path.stem
    trained = [str(w) for w in version.get("trainedWords") or []]

    return {
        "schema": SCHEMA,
        "identity": {
            "file_name": path.name,
            "size": size,
            "hashes": {"sha256": sha256, "autov2": (sha256 or "")[:10]},
            "kind": kind,
            "family": family,
            # What the SITE calls this weight's operating point ("Turbo"), or None. Recorded here
            # so `resolve._select_operating_point` has a data answer to read: until 2026-09-16 the
            # only mechanism was a "turbo" substring in the FILE NAME, which named an operating
            # point wan does not have and erased its whole tuned point (steps 20/3.5 where the
            # table says 28/4.0). Derived by `recommended.variant_of`, the same function the
            # published-defaults floor already used, so the two can never disagree.
            "variant": recommended_mod.variant_of(version) if version else None,
            "base_model": version.get("baseModel") or card.get("base_model"),
            "quantisation": next(
                (str((f.get("metadata") or {}).get("fp") or "")
                 for f in version.get("files") or []
                 if (f.get("metadata") or {}).get("fp")),
                None,
            ) or None,
            "sources": sources,
        },
        "display": {
            "name": {"value": name, "user_override": False},
            "description_html": {"value": version.get("description") or "", "user_override": False},
            "creator": (version.get("creator") or {}).get("username")
                       if isinstance(version.get("creator"), dict) else None,
            "license": {
                "name": card.get("license") or card.get("license_name"),
                "allowCommercialUse": model.get("allowCommercialUse"),
                "allowDerivatives": model.get("allowDerivatives"),
                "allowNoCredit": model.get("allowNoCredit"),
            },
            "nsfw_level": version.get("nsfwLevel"),
            "trigger_words": {"value": trained, "user_override": False},
            "images": images or [],
        },
        "recommended": recommended,
        "user": {"notes": "", "favorite": False},
    }
