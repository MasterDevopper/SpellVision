"""What to offer the user when a workflow names a model they do not have.

This is the top of the resolution ladder (plan Workstream A4). Tiers 1 and 2 already live in
``model_dependency_resolver``: a URL the workflow declared for itself, and a reference that is
already a URL or a Civitai id. Both are exact and neither needs a decision. What is left is the
common case -- a bare ``foo.safetensors`` with no source at all -- and that is what this module
turns into a concrete, reasoned offer.

## Tier 3 is identification, not search

Measured against ten real missing checkpoints from the library:

| query shape | result |
|---|---|
| name search, no type filter | 9 of 10 "resolved" |
| ... but the top hit for 4 of them | a **style LoRA**, not the checkpoint |
| `types=Checkpoint` + **exact filename match** | **5 of 10**, all correct |

A search that returns something for 9 of 10 and is wrong about 4 is worse than one that answers 5
and knows it. So a download is only ever offered when a Civitai model *version* contains a file
whose name matches the wanted filename **exactly**. Anything looser is not "your file" and is not
presented as one.

The five that find nothing are not a failure: they fall through to tier 4, which on this box has
112 architecture-compatible candidates waiting. Together, every one of the ten has a path.

## Tier 4 never happens silently

An offered substitute is a ranked list with a stated architecture and the reason it was inferred.
Doc 19's rule stands and is the reason this module returns an *offer* rather than performing one:
never auto-download on a guess, and never silently substitute.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from workflow_architecture_inference import (
    ArchitectureInference,
    SubstitutionCandidate,
    infer_required_architecture,
    rank_substitution_candidates,
)

CIVITAI_SEARCH_URL = "https://civitai.com/api/v1/models"

# Civitai's own type vocabulary, keyed by the reference kind we carry internally. A search that
# does not constrain the type is what returned a style LoRA for a checkpoint request in 4 of 10
# measured cases -- the filter is load-bearing, not a nicety.
CIVITAI_TYPE_FOR_KIND: dict[str, str] = {
    "checkpoint": "Checkpoint",
    "model": "Checkpoint",
    "unet": "Checkpoint",
    "diffusion_model": "Checkpoint",
    "lora": "LORA",
    "vae": "VAE",
    "controlnet": "Controlnet",
    "embedding": "TextualInversion",
    "upscaler": "Upscaler",
}

EXACT_DOWNLOAD = "exact_download"
SUBSTITUTE = "substitute"
AMBIGUOUS = "ambiguous"
NONE = "none"

_WEIGHT_SUFFIX_RE = re.compile(r"\.(safetensors|ckpt|gguf|pt|pth|bin)$", re.IGNORECASE)
_TRAILING_VERSION_RE = re.compile(r"[._-]?v?\d[\d.]*$", re.IGNORECASE)
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


@dataclass(frozen=True)
class DownloadOption:
    """A file we have positively identified -- never a near-miss."""

    filename: str
    url: str
    model_name: str
    version_name: Optional[str]
    size_kb: Optional[float]
    match: str = "exact_filename"


class AmbiguousDownload(Exception):
    """Several DIFFERENT files on Civitai carry the wanted filename.

    Raised rather than returning one, because the label this module would attach is
    ``exact_download`` -- the strongest confidence it has -- and picking among genuinely different
    artifacts would make that label a lie. Carries every candidate so the caller can present the
    choice the way the version chooser already does.
    """

    def __init__(self, wanted: str, candidates: "list[DownloadOption]"):
        self.wanted = wanted
        self.candidates = list(candidates)
        listing = "; ".join(
            f"{c.model_name} / {c.version_name or '?'} ({(c.size_kb or 0) / 1048576:.2f} GB)"
            for c in self.candidates
        )
        super().__init__(
            f"{len(self.candidates)} different files on Civitai are named {wanted!r}: {listing}"
        )


@dataclass(frozen=True)
class ResolutionOffer:
    wanted: str
    state: str                                          # exact_download | substitute | ambiguous | none
    download: Optional[DownloadOption] = None
    substitutes: tuple[SubstitutionCandidate, ...] = ()
    architecture: Optional[str] = None
    architecture_state: str = "unknown"
    architecture_reason: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wanted": self.wanted,
            "state": self.state,
            "download": None if self.download is None else {
                "filename": self.download.filename,
                "url": self.download.url,
                "model_name": self.download.model_name,
                "version_name": self.download.version_name,
                "size_kb": self.download.size_kb,
                "match": self.download.match,
            },
            "substitutes": [
                {
                    "name": c.name,
                    "architecture": c.architecture,
                    "lineage": c.lineage,
                    "lineage_match": c.lineage_match,
                    "score": c.score,
                    "reason": c.reason,
                }
                for c in self.substitutes
            ],
            "architecture": self.architecture,
            "architecture_state": self.architecture_state,
            "architecture_reason": self.architecture_reason,
            "notes": list(self.notes),
        }


def search_queries(filename: str) -> list[str]:
    """Progressively looser queries for one filename, most specific first.

    Measured shapes that matter: the full stem works often enough to try first
    (``cyberrealisticPony_v141``), the pre-underscore segment rescues
    ``oneObsessionBranch_matureMAXEPS``, and splitting camelCase rescues
    ``JANKUTrainedNoobaiRouwei`` -- Civitai indexes those as separate words.
    """
    base = _WEIGHT_SUFFIX_RE.sub("", str(filename or "").strip())
    if not base:
        return []
    first = base.split("_")[0]
    trimmed = _TRAILING_VERSION_RE.sub("", first) or first
    spaced = _CAMEL_BOUNDARY_RE.sub(" ", trimmed)

    out: list[str] = []
    for query in (base, first, trimmed, spaced):
        if query and query not in out:
            out.append(query)
    return out


def _default_fetch(url: str, *, timeout: float = 25.0) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "SpellVision/1.0 (model resolution)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def find_exact_download(
    filename: str,
    *,
    kind: str = "checkpoint",
    fetch: Callable[..., Any] = _default_fetch,
    limit: int = 5,
) -> Optional[DownloadOption]:
    """Identify a file by NAME EQUALITY against a model version's file list.

    Returns None rather than a best guess. A fuzzy name hit is not the user's file, and offering
    one as though it were is the failure this whole module is shaped around.
    """
    wanted = str(filename or "").strip()
    if not wanted:
        return None
    wanted_lower = wanted.lower()
    civitai_type = CIVITAI_TYPE_FOR_KIND.get(str(kind or "").lower())

    for query in search_queries(wanted):
        params: dict[str, Any] = {"query": query, "limit": limit}
        if civitai_type:
            params["types"] = civitai_type
        try:
            payload = fetch(f"{CIVITAI_SEARCH_URL}?{urllib.parse.urlencode(params)}")
        except Exception:
            # A search failure is not a resolution failure -- the substitute path still applies.
            continue

        # Collect EVERY match before returning one. Filename equality is not identity: Civitai
        # reuses a name across precisions inside a single version (bf16 and fp8 of one checkpoint
        # share it), and unrelated uploaders publish generic names like model.safetensors and
        # pytorch_lora_weights.safetensors. Returning the first hit while labelling it
        # `exact_download` -- the strongest confidence this module has -- asserted an identity
        # nobody had established.
        matches: list[DownloadOption] = []
        for item in (payload or {}).get("items") or []:
            for version in item.get("modelVersions") or []:
                for file_info in version.get("files") or []:
                    if str(file_info.get("name") or "").lower() != wanted_lower:
                        continue
                    url = str(file_info.get("downloadUrl") or "").strip()
                    if not url:
                        continue
                    matches.append(DownloadOption(
                        filename=str(file_info.get("name")),
                        url=url,
                        model_name=str(item.get("name") or ""),
                        version_name=str(version.get("name") or "") or None,
                        size_kb=_as_float(file_info.get("sizeKB")),
                    ))

        if not matches:
            continue
        if len(matches) == 1:
            return matches[0]

        # Several files share the name. If they also share a size they are the same artifact
        # mirrored, and any of them will do; otherwise they are DIFFERENT files and choosing one
        # would be the silent substitution this module exists to avoid.
        sizes = {round(m.size_kb or 0.0) for m in matches}
        if len(sizes) == 1:
            return matches[0]
        raise AmbiguousDownload(wanted, matches)
    return None


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_offer(
    wanted: str,
    *,
    graph: Any = None,
    installed: Iterable[str] = (),
    kind: str = "checkpoint",
    fetch: Callable[..., Any] = _default_fetch,
    search_online: bool = True,
    inference: Optional[ArchitectureInference] = None,
) -> ResolutionOffer:
    """Assemble the full offer for one missing model.

    Order matters: an exact identification is strictly better than a substitute, because it gets
    the user the file the workflow was authored against. Substitutes are still computed and
    returned alongside it, so "download it" and "use one I have" are both on the table -- a user
    on a metered connection with 112 compatible checkpoints should not be told to fetch 6 GB.
    """
    name = str(wanted or "").strip()
    if not name:
        return ResolutionOffer(wanted="", state=NONE, notes=("no model name given",))

    result = inference if inference is not None else infer_required_architecture(graph, wanted_model=name)

    substitutes: tuple[SubstitutionCandidate, ...] = ()
    if result.is_resolved and result.architecture:
        substitutes = tuple(rank_substitution_candidates(result.architecture, name, installed))

    download: Optional[DownloadOption] = None
    ambiguous_downloads: list[DownloadOption] = []
    if search_online:
        try:
            download = find_exact_download(name, kind=kind, fetch=fetch)
        except AmbiguousDownload as exc:
            # Not an error and not a resolution: it is a CHOICE. Recorded so the caller can offer
            # it, while the substitute path below still runs.
            ambiguous_downloads = exc.candidates

    notes: list[str] = []
    if download is not None:
        state = EXACT_DOWNLOAD
        notes.append("identified by exact filename match, not by name similarity")
    elif ambiguous_downloads:
        state = AMBIGUOUS
        notes.append(
            f"{len(ambiguous_downloads)} different files on Civitai carry this name; "
            "choosing one would be a guess"
        )
    elif substitutes:
        state = SUBSTITUTE
        if search_online:
            notes.append("no exact match online; these are architecture-compatible files you already have")
    elif result.state == "ambiguous":
        state = AMBIGUOUS
        notes.append(
            "the graph narrows the architecture to "
            + ", ".join(result.candidates)
            + " but does not pin one, so no substitute can be offered safely"
        )
    else:
        state = NONE
        notes.append("no exact match online and no compatible model on disk")

    return ResolutionOffer(
        wanted=name,
        state=state,
        download=download,
        substitutes=substitutes,
        architecture=result.architecture,
        architecture_state=result.state,
        architecture_reason=result.reason,
        notes=tuple(notes),
    )
