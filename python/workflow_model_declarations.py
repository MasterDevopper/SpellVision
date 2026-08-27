"""Models a workflow names an exact download URL for.

The same insight as node packs: the file already carries the answer. ComfyUI writes a
``properties.models`` array onto loader nodes when the graph is saved from a template or shared
through the Manager::

    "properties": {"models": [{"name": "wan_2.1_vae.safetensors",
                               "url": "https://huggingface.co/.../wan_2.1_vae.safetensors",
                               "directory": "vae"}]}

That is an exact URL *and* the destination subdirectory -- not a filename to go searching for. It is
therefore **tier 1** of model resolution, ahead of hash lookup, name search and any substitution,
because nothing about it is inferred.

Measured on this library: 7 of 80 workflows, 20 declarations, every one carrying all three fields.
Coverage is modest, but where it exists it is the only tier that cannot be wrong.

The destination directory comes from the declaration rather than from the node's class, which
matters for the loaders that can read several kinds (a CLIPLoader declaring ``text_encoders``).
It is still validated as a single safe path component, since it is used to build a filesystem path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable
import re

from workflow_scanner import WorkflowNodeInfo

# A destination subdir is used to build a path under the models root, so it must be one plain
# component -- never absolute, never containing a traversal.
_SAFE_DIRECTORY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_ALLOWED_URL_SCHEMES = ("https://",)


@dataclass
class DeclaredModel:
    """One ``properties.models`` entry, validated."""

    name: str
    url: str
    directory: str | None = None
    node_ids: list[str] = field(default_factory=list)
    class_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_directory(value: Any) -> str | None:
    text = str(value or "").strip().strip("/").strip("\\")
    if not text or not _SAFE_DIRECTORY_RE.match(text) or text in {".", ".."}:
        return None
    return text


def _safe_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text.lower().startswith(_ALLOWED_URL_SCHEMES):
        # http:// and file:// are refused: this URL is followed by a downloader, and a workflow is
        # untrusted input that a user pasted from the internet.
        return None
    return text


def declared_models(nodes: Iterable[WorkflowNodeInfo]) -> dict[str, DeclaredModel]:
    """``{model filename: DeclaredModel}`` for every valid declaration in the graph.

    Keyed by the filename because that is what the node's widget value holds, so a model reference
    can be looked up directly. Duplicate declarations of one file (a VAE used by several nodes)
    merge, recording every node that wanted it.
    """
    out: dict[str, DeclaredModel] = {}
    for node in nodes:
        props = node.raw.get("properties") if isinstance(node.raw, dict) else None
        if not isinstance(props, dict):
            continue
        entries = props.get("models")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            url = _safe_url(entry.get("url"))
            if not name or not url:
                continue
            directory = _safe_directory(entry.get("directory"))
            existing = out.get(name)
            if existing is None:
                existing = DeclaredModel(name=name, url=url, directory=directory)
                out[name] = existing
            elif existing.url != url:
                # Two different URLs for one filename. Keep the first and say nothing further about
                # it here; silently preferring one would be a substitution.
                continue
            if node.node_id not in existing.node_ids:
                existing.node_ids.append(node.node_id)
            if node.class_type not in existing.class_types:
                existing.class_types.append(node.class_type)
    return out


def declaration_for(declarations: dict[str, DeclaredModel], value: str) -> DeclaredModel | None:
    """Look a model reference up, tolerating the subfolder prefixes Comfy allows (``ltx/foo.st``)."""
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return None
    direct = declarations.get(text)
    if direct is not None:
        return direct
    return declarations.get(text.rsplit("/", 1)[-1])
