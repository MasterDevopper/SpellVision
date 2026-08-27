"""Fetch a workflow from a link.

The import dialog was local-file only, so the actual user story -- "I found a workflow on Civitai" --
had no front door at all. The only paste-a-link affordances in the app were for *models*.

Two forms are accepted, because those are the two forms a shared workflow really takes:

  * **a JSON document** -- a Civitai attachment, a GitHub/gist raw file, a Hugging Face file. GitHub
    ``/blob/`` page URLs are rewritten to their raw form, since that is what people copy.
  * **an image carrying the graph in its metadata** -- how ComfyUI workflows are shared most often.
    Extraction reuses ``workflow_scanner._extract_embedded_workflow``; nothing new parses PNG chunks.

This downloads and parses attacker-influenceable input, so:

  * https only, and only from an explicit host allowlist -- a workflow link is pasted from the
    internet, and a fetcher that follows any URL is an SSRF primitive pointed at the user's LAN;
  * redirects are followed only to allowlisted hosts (the check is worthless if the first hop can
    redirect anywhere);
  * the body is size-capped and read in chunks, never ``resp.read()`` on an unbounded stream;
  * the result must actually look like a workflow before it is handed on. "It downloaded" is not
    "it is a workflow", and a JSON error page parses perfectly well.

The Civitai token is attached only for civitai.com, and never sent to another host, including
through a redirect.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_HOSTS = {
    "civitai.com",
    "www.civitai.com",
    "image.civitai.com",
    "huggingface.co",
    "cdn-lfs.huggingface.co",
    "raw.githubusercontent.com",
    "gist.githubusercontent.com",
    "objects.githubusercontent.com",
    "github.com",
    "www.github.com",
}
CIVITAI_HOSTS = {"civitai.com", "www.civitai.com", "image.civitai.com"}
MAX_WORKFLOW_BYTES = 64 * 1024 * 1024  # generous for an embedded-workflow image, tiny for JSON
CHUNK_BYTES = 256 * 1024
IMAGE_SUFFIXES = {".png", ".webp"}


class WorkflowFetchError(RuntimeError):
    """A link could not be turned into a workflow. The message is shown to the user."""


@dataclass
class FetchedWorkflow:
    payload: dict[str, Any]
    display_name: str
    source_url: str
    content_type: str = ""
    via: str = ""  # "json" | "image_metadata"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse a redirect that leaves the allowlist. Without this the allowlist is decorative."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102 - stdlib signature
        host = (urllib.parse.urlparse(newurl).hostname or "").lower()
        if host not in ALLOWED_HOSTS:
            raise WorkflowFetchError(f"The link redirected to {host or newurl!r}, which SpellVision will not download from.")
        new_request = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_request is not None and host not in CIVITAI_HOSTS:
            # Never carry a Civitai token onto another host.
            new_request.headers.pop("Authorization", None)
            new_request.headers.pop("authorization", None)
        return new_request


def normalize_workflow_url(url: str) -> str:
    """Rewrite the URLs people actually copy into the ones that serve bytes.

    A GitHub ``/blob/`` link is an HTML page; its raw form is the file. Everything else is returned
    unchanged rather than guessed at.
    """
    text = str(url or "").strip()
    parsed = urllib.parse.urlparse(text)
    host = (parsed.hostname or "").lower()
    if host in {"github.com", "www.github.com"}:
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 5 and parts[2] == "blob":
            owner, repo, _blob, ref = parts[0], parts[1], parts[2], parts[3]
            rest = "/".join(parts[4:])
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{rest}"
    return text


def _validate_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise WorkflowFetchError("Workflow links must be https.")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise WorkflowFetchError(
            f"SpellVision does not download workflows from {host or 'that host'!r}. "
            f"Supported: {', '.join(sorted({'civitai.com', 'huggingface.co', 'github.com'}))}."
        )
    return parsed


def _download(url: str, *, civitai_api_key: str | None, timeout: float) -> tuple[bytes, str]:
    parsed = _validate_url(url)
    headers = {"User-Agent": "SpellVision/1.0 (workflow import)", "Accept": "*/*"}
    if civitai_api_key and (parsed.hostname or "").lower() in CIVITAI_HOSTS:
        headers["Authorization"] = f"Bearer {civitai_api_key}"

    opener = urllib.request.build_opener(_AllowlistRedirectHandler)
    request = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(request, timeout=timeout) as resp:
            content_type = str(resp.headers.get("Content-Type") or "")
            declared = resp.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_WORKFLOW_BYTES:
                raise WorkflowFetchError("That file is too large to be a workflow.")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_WORKFLOW_BYTES:
                    raise WorkflowFetchError("That file is too large to be a workflow.")
                chunks.append(chunk)
    except WorkflowFetchError:
        raise
    except urllib.error.HTTPError as exc:
        if int(getattr(exc, "code", 0) or 0) in (401, 403):
            raise WorkflowFetchError(
                "That link needs credentials. Add a Civitai API key in Settings, then try again."
            ) from exc
        raise WorkflowFetchError(f"The link returned HTTP {exc.code}.") from exc
    except Exception as exc:
        raise WorkflowFetchError(f"Could not download the link: {exc}") from exc
    return b"".join(chunks), content_type


def looks_like_workflow(payload: Any) -> bool:
    """A UI graph has a ``nodes`` list; an API prompt maps node ids to objects with a class_type.

    Checked because a JSON error page, a model index, or any other JSON parses perfectly well, and
    importing one of those produces a profile that fails much later for no visible reason.
    """
    if not isinstance(payload, dict) or not payload:
        return False
    if isinstance(payload.get("nodes"), list):
        return True
    for value in payload.values():
        if not isinstance(value, dict):
            return False
        if "class_type" not in value and "inputs" not in value:
            return False
    return True


def _name_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    name = Path(urllib.parse.unquote(path)).name or "imported-workflow"
    for suffix in (".json", ".png", ".webp"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name or "imported-workflow"


def fetch_workflow_from_url(
    url: str,
    *,
    civitai_api_key: str | None = None,
    timeout: float = 60.0,
) -> FetchedWorkflow:
    """Turn a link into a workflow payload, or raise ``WorkflowFetchError`` saying why not."""
    normalized = normalize_workflow_url(url)
    notes: list[str] = []
    if normalized != url.strip():
        notes.append("rewrote the GitHub page link to its raw file")

    body, content_type = _download(normalized, civitai_api_key=civitai_api_key, timeout=timeout)
    display_name = _name_from_url(normalized)
    suffix = Path(urllib.parse.urlparse(normalized).path).suffix.lower()
    is_image = suffix in IMAGE_SUFFIXES or content_type.lower().startswith("image/")

    if not is_image:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise WorkflowFetchError(
                "That link did not return a workflow JSON file. If it is a Civitai page rather than "
                "a file, open the workflow attachment or the image and copy that link instead."
            ) from exc
        if not looks_like_workflow(payload):
            raise WorkflowFetchError("That JSON file is not a ComfyUI workflow.")
        return FetchedWorkflow(payload=payload, display_name=display_name, source_url=normalized,
                               content_type=content_type, via="json", notes=notes)

    # An image: the graph is in its metadata. Reuse the extractor the local-file import already uses
    # rather than growing a second PNG-chunk parser that can drift from it.
    from workflow_scanner import _extract_embedded_workflow

    with tempfile.TemporaryDirectory(prefix="svwf_") as tmp:
        image_path = Path(tmp) / f"workflow{suffix or '.png'}"
        image_path.write_bytes(body)
        try:
            payload = _extract_embedded_workflow(image_path)
        except Exception as exc:
            raise WorkflowFetchError(
                "That image does not carry a ComfyUI workflow in its metadata. Civitai strips it "
                "from some uploads -- look for a workflow JSON attachment on the model page."
            ) from exc

    if not looks_like_workflow(payload):
        raise WorkflowFetchError("The workflow embedded in that image is not a ComfyUI graph.")
    notes.append("read the graph from the image's metadata")
    return FetchedWorkflow(payload=payload, display_name=display_name, source_url=normalized,
                           content_type=content_type, via="image_metadata", notes=notes)


def is_url(value: Any) -> bool:
    text = str(value or "").strip()
    return text.lower().startswith(("http://", "https://"))


__all__ = [
    "ALLOWED_HOSTS",
    "FetchedWorkflow",
    "WorkflowFetchError",
    "fetch_workflow_from_url",
    "is_url",
    "looks_like_workflow",
    "normalize_workflow_url",
]
