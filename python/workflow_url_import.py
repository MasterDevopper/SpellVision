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

# civitai.red is Civitai's alternate domain and serves the same content. model_sources accepts it
# (`civitai\.(?:com|red)` in CIVITAI_DOWNLOAD_RE / CIVITAI_MODEL_PAGE_RE) and this lane did not, so
# the SAME link was accepted or refused depending on which box it was pasted into -- the model
# importer took it and the workflow importer answered "SpellVision will not download from that
# host". Every link in the batch that prompted this was civitai.red.
CIVITAI_HOSTS = {
    "civitai.com", "www.civitai.com", "image.civitai.com",
    "civitai.red", "www.civitai.red", "image.civitai.red",
}

# Civitai's download endpoint 302s to a delivery host, and the redirect handler refused the hop --
# so the remediation this module's own error message recommends ("open the workflow attachment and
# copy that link instead") dead-ended too. The model lane never hit this because it uses a bare
# urlopen that follows redirects unchecked; keeping the re-check and widening the policy is the
# safer reconciliation.
#
# Matched by REGISTRABLE DOMAIN rather than a hostname list. A first attempt hardcoded two guessed
# Cloudflare R2 names and both were wrong -- the live redirect goes to `b2.civitai.com`. A domain
# rule survives them moving CDN again, and it is no weaker: the same owner already serves the page
# we were told to trust, and the credential is only ever attached to a Civitai host.
CIVITAI_DOMAIN_SUFFIXES = (".civitai.com", ".civitai.red")

ALLOWED_HOSTS = {
    *CIVITAI_HOSTS,
    "huggingface.co",
    "cdn-lfs.huggingface.co",
    "raw.githubusercontent.com",
    "gist.githubusercontent.com",
    "objects.githubusercontent.com",
    "github.com",
    "www.github.com",
}
MAX_WORKFLOW_BYTES = 64 * 1024 * 1024  # generous for an embedded-workflow image, tiny for JSON
CHUNK_BYTES = 256 * 1024
IMAGE_SUFFIXES = {".png", ".webp"}
# Local-file header of every ZIP. Sniffed rather than trusting a suffix or content-type.
ZIP_MAGIC = b'PK'


def host_allowed(host: str) -> bool:
    """Is this host one we will download from?

    Exact match against ALLOWED_HOSTS, plus any subdomain of a Civitai registrable domain. The
    second half exists because the download endpoint redirects to a delivery host that is not the
    page host -- live, `b2.civitai.com` -- and hardcoding CDN names is a guess that expires.
    """
    name = str(host or "").strip().lower()
    if not name:
        return False
    if name in ALLOWED_HOSTS:
        return True
    return any(name.endswith(suffix) for suffix in CIVITAI_DOMAIN_SUFFIXES)


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
        if not host_allowed(host):
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


def civitai_model_page_ids(url: str) -> tuple[str, str] | None:
    """``(model_id, model_version_id)`` for a Civitai MODEL PAGE url, else None.

    ``model_version_id`` is "" when the link names no version -- that is the common shape, because
    the page URL a user copies from the address bar carries one only after they click a version tab.
    """
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if (parsed.hostname or "").lower() not in CIVITAI_HOSTS:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or parts[0] != "models" or not parts[1].isdigit():
        return None
    version = urllib.parse.parse_qs(parsed.query).get("modelVersionId", [""])[0].strip()
    return parts[1], version


def resolve_civitai_workflow_url(
    url: str, *, civitai_api_key: str | None = None, timeout: float = 30.0
) -> tuple[str, str]:
    """Resolve a Civitai model page to a downloadable file URL. Returns ``(url, note)``.

    A model page is HTML. Fetching it and calling ``json.loads`` -- which is what this module did --
    fails with "that link did not return a workflow JSON file", which is true and useless: the page
    genuinely is the thing a user copies. The model lane already knows how to turn that id into a
    file, so this asks the same API rather than re-implementing a narrower version of it.

    A model with SEVERAL versions and no ``modelVersionId`` raises instead of guessing. One Civitai
    model id can hold variants built on entirely different architectures, so picking the first is a
    silent wrong-file import -- the same defect already fixed on the model lane.
    """
    ids = civitai_model_page_ids(url)
    if ids is None:
        return str(url or "").strip(), ""
    model_id, version_id = ids

    from model_sources import _civitai_api_get_json, model_variants, select_variant

    if version_id:
        payload = _civitai_api_get_json(
            f"https://civitai.com/api/v1/model-versions/{version_id}",
            civitai_api_key=civitai_api_key, timeout_sec=int(timeout),
        )
        files = [f for f in (payload.get("files") or []) if isinstance(f, dict)]
        chosen = _pick_workflow_file(files)
        if not chosen:
            raise WorkflowFetchError(
                f"Civitai model version {version_id} has no downloadable file to import."
            )
        return str(chosen.get("downloadUrl") or ""), (
            f"resolved the Civitai page to version {version_id} ({chosen.get('name')})"
        )

    payload = _civitai_api_get_json(
        f"https://civitai.com/api/v1/models/{model_id}",
        civitai_api_key=civitai_api_key, timeout_sec=int(timeout),
    )
    variants = model_variants(payload)
    if not variants:
        raise WorkflowFetchError(f"Civitai model {model_id} lists no versions to import.")
    if len(variants) > 1 and select_variant(variants, None) is None:
        listing = "; ".join(v.describe() for v in variants)
        raise WorkflowFetchError(
            f"That Civitai link names no version, and model {model_id} has {len(variants)}. "
            f"Open the version you want and copy that link (it will carry ?modelVersionId=). "
            f"Versions: {listing}"
        )
    only = variants[0]
    return only.download_url, f"resolved the Civitai page to its only version ({only.version_name})"


def _pick_workflow_file(files: list[dict]) -> dict:
    """Prefer an actual workflow file over a checkpoint sitting in the same version.

    A "Workflows"-type Civitai model ships a .json (sometimes .zip); a checkpoint page that also
    attaches its workflow ships both. Preferring by extension means pasting either kind of link
    into the workflow importer gets the workflow, not several gigabytes of weights.
    """
    def rank(entry: dict) -> tuple[int, float]:
        name = str(entry.get("name") or "").lower()
        if name.endswith(".json"):
            return (0, float(entry.get("sizeKB") or 0))
        if name.endswith(".zip"):
            return (1, float(entry.get("sizeKB") or 0))
        if name.endswith((".png", ".webp")):
            return (2, float(entry.get("sizeKB") or 0))
        return (3, float(entry.get("sizeKB") or 0))

    usable = [f for f in files if str(f.get("downloadUrl") or "").strip()]
    return sorted(usable, key=rank)[0] if usable else {}


def _validate_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise WorkflowFetchError("Workflow links must be https.")
    host = (parsed.hostname or "").lower()
    if not host_allowed(host):
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
    for suffix in (".json", ".png", ".webp", ".zip"):
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

    # A Civitai model page is HTML, so it has to become a file URL before anything downloads it.
    # Done here rather than in normalize_workflow_url because it needs the network and can fail
    # with a message of its own; normalize stays a pure string rewrite.
    resolved, note = resolve_civitai_workflow_url(
        normalized, civitai_api_key=civitai_api_key, timeout=timeout
    )
    if resolved and resolved != normalized:
        normalized = resolved
        if note:
            notes.append(note)

    body, content_type = _download(normalized, civitai_api_key=civitai_api_key, timeout=timeout)
    display_name = _name_from_url(normalized)
    suffix = Path(urllib.parse.urlparse(normalized).path).suffix.lower()
    is_image = suffix in IMAGE_SUFFIXES or content_type.lower().startswith("image/")

    # Detected by MAGIC BYTES, not by suffix or content-type. A Civitai download link is
    # `/api/download/models/<id>` -- no extension at all -- and the served content-type for an
    # archive is frequently a generic octet-stream. `_pick_workflow_file` deliberately ranks .zip
    # second, so this arrives through the normal path; without the sniff it fell into the JSON
    # branch and told the user the link "did not return a workflow JSON file", when in fact it
    # returned exactly the right file in a container we refused to open.
    is_zip = body[:4] == ZIP_MAGIC

    if is_zip:
        from workflow_scanner import _workflow_from_zip

        with tempfile.TemporaryDirectory(prefix="svwf_") as tmp:
            archive_path = Path(tmp) / "workflow.zip"
            archive_path.write_bytes(body)
            try:
                payload = _workflow_from_zip(archive_path)
            except ValueError as exc:
                raise WorkflowFetchError(str(exc)) from exc
        notes.append("read the graph from the downloaded ZIP archive")
        return FetchedWorkflow(payload=payload, display_name=display_name, source_url=normalized,
                               content_type=content_type, via="zip_archive", notes=notes)

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
