from __future__ import annotations
from runtime_paths import RuntimePaths

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request


REMOTE_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
HF_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CIVITAI_DOWNLOAD_RE = re.compile(
    r"^https?://(?:www\.)?civitai\.(?:com|red)/api/download/models/(?P<version_id>\d+)",
    re.IGNORECASE,
)
CIVITAI_MODEL_PAGE_RE = re.compile(
    r"^https?://(?:www\.)?civitai\.(?:com|red)/models/(?P<model_id>\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)

DEFAULT_MAX_MODEL_DOWNLOAD_BYTES = 128 * 1024 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
DOWNLOAD_DISK_HEADROOM_BYTES = 64 * 1024 * 1024
# How many bytes must accumulate before another progress callback fires. At a 1 MB chunk a 6 GB
# checkpoint is ~6000 chunks; reporting each one would take the manager lock 6000 times for a bar
# that cannot render more than a few hundred distinct positions.
DOWNLOAD_PROGRESS_STRIDE_BYTES = 4 * 1024 * 1024
CACHE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

# (bytes_done, total_or_None) -- total is None when the server sent no Content-Length and the
# provider declared no size. An indeterminate download is a real state and must stay expressible.
ProgressCallback = Callable[[int, "int | None"], None]
# Returns True to abort. Checked once per chunk, so a cancel lands within one chunk read rather
# than at the end of a multi-gigabyte transfer.
CancelCallback = Callable[[], bool]


# Precision tokens Civitai reports in files[].metadata.fp, worst-to-best quality. The ORDER is the
# recommendation order once VRAM has ruled options out -- it is not a quality claim beyond
# "more bits is closer to the original weights".
_PRECISION_RANK = {"nvfp4": 0, "int8": 1, "fp8": 2, "fp8_scaled": 3, "fp16": 4, "bf16": 5}

# Extensions that are not weights. A version bundles more than the checkpoint: the real
# "Lox's Utopic World | Krea 2" V1.0 BF16 version carries the 23.88 GB checkpoint, an 11.94 GB fp8
# of it under THE SAME FILENAME, a 4.88 GB text encoder, a 0.24 GB VAE and the workflow .json.
_NON_WEIGHT_SUFFIXES = (".json", ".yaml", ".yml", ".txt", ".md", ".png", ".webp", ".jpg", ".jpeg")


@dataclass(frozen=True)
class CivitaiFile:
    """One downloadable file inside a model version.

    Identified by ``file_id``, never by name. Civitai reuses one filename across precisions --
    ``loxsUtopicWorldKrea2_v20Quants.safetensors`` is the name of the nvfp4, the int8 AND the fp8
    file in a single version -- so a name is not a key, and picking by name would fetch whichever
    happened to be first.
    """

    file_id: str
    name: str
    size_kb: float | None
    precision: str          # metadata.fp: bf16 / fp8 / int8 / nvfp4 / fp8_scaled, "" when absent
    file_format: str        # metadata.format: "SafeTensor", ...
    primary: bool
    download_url: str

    @property
    def is_weights(self) -> bool:
        return not self.name.lower().endswith(_NON_WEIGHT_SUFFIXES)

    @property
    def size_gb(self) -> float:
        return (self.size_kb or 0.0) / 1048576.0

    def describe(self) -> str:
        bits = f" {self.precision}" if self.precision else ""
        size = f" ({self.size_gb:.2f} GB)" if self.size_kb else ""
        return f"{self.name}{bits}{size}"


@dataclass(frozen=True)
class CivitaiVariant:
    """One ``modelVersion`` of a Civitai model, reduced to what a choice needs."""

    version_id: str
    version_name: str
    base_model: str          # Civitai's own string: "SDXL 1.0", "Flux.1 D", "Pony", "Krea 2"...
    architecture: str | None  # folded onto our axis; None when we cannot map it
    filename: str
    size_kb: float | None
    download_url: str
    # EVERY file in the version. The singular fields above describe the primary one and are kept
    # so existing callers are unaffected; this is what lets a caller offer the fp8 instead.
    files: tuple[CivitaiFile, ...] = ()

    def weight_files(self) -> tuple[CivitaiFile, ...]:
        return tuple(f for f in self.files if f.is_weights)

    def precision_variants(self) -> tuple[CivitaiFile, ...]:
        """The same checkpoint at different precisions -- the set a user chooses BETWEEN.

        Identified by sharing the PRIMARY file's name. Civitai reuses one filename across
        precisions inside a version (nvfp4, int8 and fp8 of "V2.0 Quants" are all
        ``loxsUtopicWorldKrea2_v20Quants.safetensors``), while the companions it bundles alongside
        -- a ``_txt`` text encoder, ``qwen_image_vae.safetensors``, the workflow ``.json`` -- carry
        distinct names.

        Without this split a naive "highest precision that fits" recommended the 0.24 GB bf16 VAE
        as the model to download: it is bf16, it is weights, and it fits easily.
        """
        weights = self.weight_files()
        if not weights:
            return ()
        target = (self.filename or weights[0].name).strip().lower()
        same = tuple(f for f in weights if f.name.strip().lower() == target)
        return same or (weights[0],)

    def companion_files(self) -> tuple[CivitaiFile, ...]:
        """Weights bundled with the checkpoint but not a precision of it -- VAE, text encoder.

        These are the "Required Components" the Civitai page lists, shipped inside the version.
        """
        variants = {f.file_id for f in self.precision_variants()}
        return tuple(f for f in self.weight_files() if f.file_id not in variants)

    def describe(self) -> str:
        size = f", {self.size_kb / 1024:.0f} MB" if self.size_kb else ""
        extra = ""
        weights = self.weight_files()
        if len(weights) > 1:
            extra = f" (+{len(weights) - 1} other precision(s))"
        return f"{self.version_name} [{self.base_model}] -> {self.filename}{size}{extra}"


def recommend_file(files: Sequence[CivitaiFile], vram_gb: float | None = None) -> CivitaiFile | None:
    """The precision to SUGGEST. Never the one to take automatically.

    The owner's decision is "always ask, recommend one", so this marks a row -- it does not choose.
    Two rules, in order:

    * it has to fit. A checkpoint needs headroom beyond its own size for activations and the VAE
      decode, so the budget is 80% of reported VRAM rather than all of it;
    * among what fits, prefer the highest precision.

    With no VRAM figure, recommend the highest precision and let the size be the user's problem to
    read -- guessing a card is worse than not guessing.
    """
    weights = [f for f in files if f.is_weights]
    if not weights:
        return None

    # Only ever recommend among PRECISIONS OF ONE CHECKPOINT. Passed a whole version's file list,
    # an earlier version of this happily recommended the 0.24 GB bf16 VAE -- highest precision,
    # smallest, fits any card, and completely the wrong file. Callers should pass
    # variant.precision_variants(); this narrows defensively for the ones that do not.
    names = {f.name.strip().lower() for f in weights}
    if len(names) > 1:
        primary_name = next((f.name for f in weights if f.primary), weights[0].name)
        narrowed = [f for f in weights if f.name.strip().lower() == primary_name.strip().lower()]
        if narrowed:
            weights = narrowed

    def rank(entry: CivitaiFile) -> tuple[int, float]:
        return (_PRECISION_RANK.get(entry.precision.lower(), -1), -(entry.size_kb or 0.0))

    if vram_gb and vram_gb > 0:
        budget = vram_gb * 0.8
        fits = [f for f in weights if f.size_gb and f.size_gb <= budget]
        if fits:
            return max(fits, key=rank)
        # Nothing fits: recommend the smallest rather than nothing, and let the caller say why.
        return min(weights, key=lambda f: f.size_kb or float("inf"))
    return max(weights, key=rank)


class AmbiguousCivitaiModel(Exception):
    """A model-page URL that names no version, on a model that has several.

    Carries the variants so the caller can present them. Refusing is the point: the alternative
    is downloading one of them and hoping.
    """

    def __init__(self, model_id: str, variants: "list[CivitaiVariant]",
                 preferred_architecture: str | None = None):
        self.model_id = model_id
        self.variants = list(variants)
        self.preferred_architecture = preferred_architecture
        hint = (f" Nothing matched the required architecture {preferred_architecture!r} uniquely."
                if preferred_architecture else "")
        listing = "; ".join(v.describe() for v in self.variants)
        super().__init__(
            f"Civitai model {model_id} has {len(self.variants)} versions and the link names none of "
            f"them.{hint} Choose one: {listing}"
        )


def civitai_base_model_architecture(base_model: str) -> str | None:
    """Map Civitai's ``baseModel`` string onto our architecture axis.

    ``baseModel`` is the reliable signal here, and the filename is not: five of the six variants of
    "Vintage Mix by AK" follow a ``Vintage_Mix_<FAMILY>_epoch_N`` convention while the Krea 2 one is
    ``Vintage Mix Krea2 v1.safetensors`` -- different separators, different shape, no epoch.

    Spaces are normalised to hyphens before matching, because the registry aliases are written
    ``krea-2`` while Civitai writes ``Krea 2``.
    """
    from model_registry import infer_model_family
    from workflow_architecture_inference import architecture_of_family

    text = str(base_model or "").strip().lower().replace(" ", "-")
    if not text:
        return None
    return architecture_of_family(infer_model_family(text))


def model_variants(model_payload: dict[str, Any]) -> list[CivitaiVariant]:
    """Reduce a ``/api/v1/models/{id}`` payload to its selectable variants."""
    out: list[CivitaiVariant] = []
    for version in (model_payload.get("modelVersions") or []):
        if not isinstance(version, dict):
            continue
        raw_files = [f for f in (version.get("files") or []) if isinstance(f, dict)]
        parsed: list[CivitaiFile] = []
        for entry in raw_files:
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            parsed.append(CivitaiFile(
                file_id=str(entry.get("id") or ""),
                name=str(entry.get("name") or ""),
                size_kb=_as_float(entry.get("sizeKB")),
                precision=str(metadata.get("fp") or "").strip(),
                file_format=str(metadata.get("format") or "").strip(),
                primary=bool(entry.get("primary")),
                download_url=str(entry.get("downloadUrl") or ""),
            ))
        # Primary among the WEIGHTS. A version bundles its text encoder, VAE and workflow .json
        # alongside the checkpoint, and files[0] is frequently one of those -- the real V1.0 Quants
        # version lists qwen_image_vae.safetensors first.
        # Prefer the primary WEIGHT file, because files[0] is frequently a companion -- the real
        # "V1.0 Quants" version lists qwen_image_vae.safetensors first. But fall back to the full
        # list when a version has no weights at all: a Workflows-type model's only file IS the
        # .json, and treating it as "no primary" left such a version with an empty filename and an
        # empty download url.
        weights = [f for f in parsed if f.is_weights]
        pool = weights or parsed
        primary_file = next((f for f in pool if f.primary), pool[0] if pool else None)
        files = raw_files
        primary = {
            "name": primary_file.name if primary_file else "",
            "sizeKB": primary_file.size_kb if primary_file else None,
            "downloadUrl": primary_file.download_url if primary_file else "",
        }
        version_id = str(version.get("id") or "").strip()
        if not version_id:
            continue
        base_model = str(version.get("baseModel") or "")
        out.append(CivitaiVariant(
            version_id=version_id,
            version_name=str(version.get("name") or version_id),
            base_model=base_model,
            architecture=civitai_base_model_architecture(base_model),
            filename=str(primary.get("name") or ""),
            size_kb=_as_float(primary.get("sizeKB")),
            download_url=str(primary.get("downloadUrl") or ""),
            files=tuple(parsed),
        ))
    return out


def select_variant(variants: list[CivitaiVariant], preferred_architecture: str | None):
    """The one variant a preferred architecture picks out, or None.

    None when there is no preference, when nothing matches, and -- importantly -- when SEVERAL
    match. Pony, Illustrious and SDXL 1.0 all fold to ``sdxl``, so three of that model's six
    variants are equally valid for an SDXL workflow. Architecture narrows the choice; it does not
    make it, and pretending otherwise would pick a Pony LoRA for an Illustrious render.
    """
    if not preferred_architecture:
        return None
    matches = [v for v in variants if v.architecture == preferred_architecture]
    return matches[0] if len(matches) == 1 else None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class DownloadCancelled(Exception):
    """Raised inside the transfer loop when the caller's cancel callback returns True.

    A distinct type because a cancelled download is a normal outcome, not a failure -- the
    manager reports CANCELLED, and the partial .part file is removed by the existing cleanup.
    """


@dataclass
class AssetReference:
    raw: Any
    kind: str
    source_name: str
    asset_type: str
    path: str | None = None
    url: str | None = None
    repo_id: str | None = None
    filename: str | None = None
    model_id: str | None = None
    model_version_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MaterializedAsset:
    original: AssetReference
    resolved_kind: str
    value: str
    local_path: str | None = None
    repo_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def default_asset_cache_root() -> str:
    return os.path.abspath(
        os.environ.get(
            "SPELLVISION_ASSET_CACHE",
            str(Path(__file__).resolve().parent / ".cache" / "assets"),
        )
    )


def parse_asset_reference(value: Any, *, asset_type: str = "model") -> AssetReference:
    if isinstance(value, AssetReference):
        return value

    if isinstance(value, dict):
        return _parse_asset_reference_dict(value, asset_type=asset_type)

    raw = str(value or "").strip()
    if not raw:
        return AssetReference(raw=value, kind="empty", source_name="empty", asset_type=asset_type)

    if REMOTE_URL_RE.match(raw):
        return _parse_url_reference(raw, asset_type=asset_type)

    if raw.startswith("hf://"):
        rest = raw[5:].strip().strip("/")
        parts = rest.split("/")
        if len(parts) >= 3:
            repo_id = "/".join(parts[:2])
            filename = "/".join(parts[2:])
        elif len(parts) == 2 and "." in parts[1]:
            repo_id, filename = parts[0], parts[1]
        else:
            repo_id, filename = rest, None
        return AssetReference(
            raw=value,
            kind="hf_repo",
            source_name="huggingface",
            asset_type=asset_type,
            repo_id=repo_id,
            filename=filename or None,
        )

    if HF_REPO_RE.match(raw) and not os.path.isabs(raw) and not raw.startswith("./") and not raw.startswith("../"):
        return AssetReference(raw=value, kind="hf_repo", source_name="huggingface", asset_type=asset_type, repo_id=raw)

    normalized = raw.replace("\\", "/")
    path = Path(raw)
    if path.suffix:
        if path.exists():
            return AssetReference(raw=value, kind="local_file", source_name="local", asset_type=asset_type, path=os.path.abspath(raw), filename=path.name)
        # A bare "foo.safetensors" out of a workflow is a model NAME, not a path. Classifying it as
        # local_file produced an absolute path to a file that does not exist, so the only possible
        # outcome was install_action="review" -- a permanent dead end for the single most common
        # form a workflow names a model in. As model_name it can be resolved: matched against a
        # properties.models declaration, looked up by hash, or searched for by name.
        # A value with a directory component is still a path; only a bare filename is a name.
        if "/" not in normalized.strip("/") and not os.path.isabs(raw):
            return AssetReference(raw=value, kind="model_name", source_name="unknown", asset_type=asset_type, filename=path.name)
        return AssetReference(raw=value, kind="local_file", source_name="local", asset_type=asset_type, path=os.path.abspath(raw), filename=path.name)
    if normalized.endswith("/") or path.exists():
        return AssetReference(raw=value, kind="local_dir", source_name="local", asset_type=asset_type, path=os.path.abspath(raw))
    return AssetReference(raw=value, kind="unknown", source_name="unknown", asset_type=asset_type, path=raw)


def _parse_asset_reference_dict(data: dict[str, Any], *, asset_type: str) -> AssetReference:
    raw = data
    kind = str(data.get("kind") or "").strip().lower()
    source_name = str(data.get("source") or data.get("provider") or data.get("site") or "").strip().lower()
    path = str(data.get("path") or data.get("local_path") or "").strip() or None
    url = str(data.get("url") or data.get("download_url") or "").strip() or None
    repo_id = str(data.get("repo_id") or data.get("hf_repo") or data.get("model") or "").strip() or None
    filename = str(data.get("filename") or "").strip() or None
    model_version_id = str(data.get("civitai_model_version_id") or data.get("modelVersionId") or data.get("version_id") or "").strip() or None
    model_id = str(data.get("civitai_model_id") or data.get("modelId") or "").strip() or None
    headers = {str(k): str(v) for k, v in (data.get("headers") or {}).items()} if isinstance(data.get("headers"), dict) else {}
    query_params = {str(k): str(v) for k, v in (data.get("query_params") or {}).items()} if isinstance(data.get("query_params"), dict) else {}
    metadata = dict(data.get("metadata") or {}) if isinstance(data.get("metadata"), dict) else {}

    if model_version_id:
        return AssetReference(
            raw=raw,
            kind="civitai_model_version",
            source_name="civitai",
            asset_type=asset_type,
            filename=filename,
            model_id=model_id or None,
            model_version_id=model_version_id,
            headers=headers,
            query_params=query_params,
            metadata=metadata,
        )

    if url:
        ref = _parse_url_reference(url, asset_type=asset_type)
        ref.headers.update(headers)
        ref.query_params.update(query_params)
        if filename:
            ref.filename = filename
        ref.metadata.update(metadata)
        return ref

    if repo_id:
        return AssetReference(
            raw=raw,
            kind="hf_repo",
            source_name="huggingface",
            asset_type=asset_type,
            repo_id=repo_id,
            headers=headers,
            query_params=query_params,
            metadata=metadata,
        )

    if path:
        resolved_kind = "local_dir" if os.path.isdir(path) else "local_file"
        return AssetReference(
            raw=raw,
            kind=kind or resolved_kind,
            source_name=source_name or "local",
            asset_type=asset_type,
            path=os.path.abspath(path),
            filename=filename or Path(path).name,
            headers=headers,
            query_params=query_params,
            metadata=metadata,
        )

    return AssetReference(raw=raw, kind=kind or "unknown", source_name=source_name or "unknown", asset_type=asset_type, filename=filename, metadata=metadata)


def _parse_url_reference(url: str, *, asset_type: str) -> AssetReference:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)

    m = CIVITAI_DOWNLOAD_RE.match(url)
    if m:
        return AssetReference(
            raw=url,
            kind="civitai_download_url",
            source_name="civitai",
            asset_type=asset_type,
            url=url,
            model_version_id=m.group("version_id"),
            query_params={k: v[-1] for k, v in query.items() if v},
        )

    m = CIVITAI_MODEL_PAGE_RE.match(url)
    if m:
        model_version_id = (query.get("modelVersionId") or query.get("modelversionid") or [None])[-1]
        return AssetReference(
            raw=url,
            kind="civitai_model_page",
            source_name="civitai",
            asset_type=asset_type,
            url=url,
            model_id=m.group("model_id"),
            model_version_id=model_version_id,
            query_params={k: v[-1] for k, v in query.items() if v},
        )

    return AssetReference(
        raw=url,
        kind="direct_url",
        source_name=(parsed.netloc or "remote").lower(),
        asset_type=asset_type,
        url=url,
        filename=Path(parsed.path).name or None,
        query_params={k: v[-1] for k, v in query.items() if v},
    )


def materialize_asset(
    value: Any,
    *,
    asset_type: str = "model",
    cache_root: str | None = None,
    civitai_api_key: str | None = None,
    hf_token: str | None = None,
    force_download: bool = False,
    timeout_sec: int = 120,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
    # The architecture the caller needs. Only used to disambiguate a Civitai model-page URL whose
    # model holds variants for several architectures; never used to pick a DIFFERENT model.
    preferred_architecture: str | None = None,
) -> MaterializedAsset:
    ref = parse_asset_reference(value, asset_type=asset_type)
    cache_root = os.path.abspath(cache_root or default_asset_cache_root())

    if ref.kind in {"empty", "unknown"}:
        return MaterializedAsset(original=ref, resolved_kind=ref.kind, value=ref.path or "")

    if ref.kind in {"local_file", "local_dir"}:
        return MaterializedAsset(
            original=ref,
            resolved_kind=ref.kind,
            value=ref.path or "",
            local_path=ref.path or None,
            metadata={"exists": bool(ref.path and os.path.exists(ref.path))},
        )

    if ref.kind == "hf_repo":
        repo_id = ref.repo_id or ""
        filename = str(ref.filename or ref.metadata.get("filename") or "").strip()
        if not filename:
            return MaterializedAsset(
                original=ref,
                resolved_kind="hf_repo",
                value=repo_id,
                repo_id=repo_id,
                metadata={"needs_filename": True, "fetched": False},
            )
        from credential_store import get_credential

        token = get_credential("hf_token", explicit=hf_token)
        download_ref = AssetReference(
            raw=ref.raw,
            kind="direct_url",
            source_name="huggingface",
            asset_type=ref.asset_type,
            url=f"https://huggingface.co/{repo_id}/resolve/main/{filename}",
            filename=Path(filename).name,
            headers={"Authorization": f"Bearer {token}"} if token else {},
            metadata={"repo_id": repo_id, "hf_path": filename, "hf_token_present": bool(token)},
        )
        return _download_remote_asset(
            download_ref,
            cache_root=cache_root,
            civitai_api_key=None,
            force_download=force_download,
            timeout_sec=timeout_sec,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
            preferred_architecture=preferred_architecture,
        )

    if ref.kind in {"direct_url", "civitai_download_url", "civitai_model_page", "civitai_model_version"}:
        return _download_remote_asset(
            ref,
            cache_root=cache_root,
            civitai_api_key=civitai_api_key,
            force_download=force_download,
            timeout_sec=timeout_sec,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
            preferred_architecture=preferred_architecture,
        )

    return MaterializedAsset(original=ref, resolved_kind=ref.kind, value=str(ref.raw or ""))


def materialize_request_assets(req: dict[str, Any], *, cache_root: str | None = None) -> dict[str, Any]:
    normalized = dict(req)
    cache_root = cache_root or default_asset_cache_root()
    civitai_api_key = str(normalized.get("civitai_api_key") or os.environ.get("CIVITAI_API_KEY") or "").strip() or None
    from credential_store import get_credential
    if not civitai_api_key:
        civitai_api_key = get_credential("civitai_api_key") or None
    hf_token = str(normalized.get("hf_token") or "").strip() or None
    force_download = bool(normalized.get("force_model_download") or False)

    manifest: dict[str, Any] = {}

    model_ref = normalized.get("model_source") or normalized.get("checkpoint") or normalized.get("model")
    if model_ref:
        model_asset = materialize_asset(
            model_ref,
            asset_type="model",
            cache_root=cache_root,
            civitai_api_key=civitai_api_key,
            hf_token=hf_token,
            force_download=force_download,
        )
        normalized["model"] = model_asset.value
        manifest["model"] = {
            "kind": model_asset.resolved_kind,
            "value": model_asset.value,
            "local_path": model_asset.local_path,
            "repo_id": model_asset.repo_id,
            "metadata": model_asset.metadata,
        }

    for field in ("input_image", "input_video"):
        if normalized.get(field):
            asset = materialize_asset(
                normalized[field],
                asset_type=field,
                cache_root=cache_root,
                civitai_api_key=civitai_api_key,
                hf_token=hf_token,
                force_download=force_download,
            )
            normalized[field] = asset.value
            manifest[field] = {
                "kind": asset.resolved_kind,
                "value": asset.value,
                "local_path": asset.local_path,
                "metadata": asset.metadata,
            }

    primary_lora = normalized.get("lora_source") or normalized.get("lora")
    if primary_lora:
        lora_asset = materialize_asset(
            primary_lora,
            asset_type="lora",
            cache_root=cache_root,
            civitai_api_key=civitai_api_key,
            hf_token=hf_token,
            force_download=force_download,
        )
        normalized["lora"] = lora_asset.value
        manifest["lora"] = {
            "kind": lora_asset.resolved_kind,
            "value": lora_asset.value,
            "local_path": lora_asset.local_path,
            "metadata": lora_asset.metadata,
        }

    resolved_loras = []
    loras = normalized.get("loras")
    if isinstance(loras, list):
        for index, item in enumerate(loras):
            scale = 1.0
            name = f"lora_{index+1:02d}"
            ref_value = item
            if isinstance(item, dict):
                ref_value = item.get("source") or item.get("url") or item.get("path") or item.get("repo_id") or item.get("value") or item
                try:
                    scale = float(item.get("scale", item.get("weight", 1.0)))
                except Exception:
                    scale = 1.0
                if item.get("name"):
                    name = str(item.get("name"))
            asset = materialize_asset(
                ref_value,
                asset_type="lora",
                cache_root=cache_root,
                civitai_api_key=civitai_api_key,
                hf_token=hf_token,
                force_download=force_download,
            )
            resolved_loras.append(
                {
                    "name": name,
                    "scale": scale,
                    "path": asset.value,
                    "kind": asset.resolved_kind,
                    "metadata": asset.metadata,
                }
            )
        normalized["loras_resolved"] = resolved_loras
        manifest["loras"] = resolved_loras
        if not normalized.get("lora") and len(resolved_loras) == 1:
            normalized["lora"] = resolved_loras[0]["path"]
            normalized["lora_scale"] = resolved_loras[0]["scale"]

    if manifest:
        normalized["asset_manifest"] = manifest
    return normalized


def _safe_cache_component(value: str, label: str) -> str:
    component = str(value or "").strip()
    if component in {"", ".", ".."} or not CACHE_COMPONENT_RE.fullmatch(component):
        raise ValueError(f"Unsafe model cache {label}: {value!r}")
    return component


def _safe_download_filename(value: str) -> str:
    filename = str(value or "").strip()
    if (
        not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or any(ord(char) < 32 for char in filename)
        or any(char in '<>:"|?*' for char in filename)
        or filename.endswith((" ", "."))
        or len(filename) > 255
    ):
        raise ValueError(f"Unsafe model download filename: {value!r}")
    return filename


def _require_contained_path(root: Path, candidate: Path, label: str) -> None:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Unsafe {label}: path escapes configured cache root") from exc


def _max_model_download_bytes() -> int:
    raw = os.environ.get("SPELLVISION_MAX_MODEL_DOWNLOAD_BYTES", "").strip()
    if not raw:
        return DEFAULT_MAX_MODEL_DOWNLOAD_BYTES
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("SPELLVISION_MAX_MODEL_DOWNLOAD_BYTES must be a positive integer.") from exc
    if value <= 0:
        raise RuntimeError("SPELLVISION_MAX_MODEL_DOWNLOAD_BYTES must be a positive integer.")
    return value


def _header_content_length(headers: dict[str, Any]) -> int | None:
    raw = headers.get("Content-Length") or headers.get("content-length")
    if raw in {None, ""}:
        return None
    try:
        value = int(str(raw))
    except ValueError as exc:
        raise RuntimeError("Invalid Content-Length returned by model provider.") from exc
    if value < 0:
        raise RuntimeError("Invalid negative Content-Length returned by model provider.")
    return value


def _declared_download_size(metadata: dict[str, Any]) -> int | None:
    for key in ("size_bytes", "file_size_bytes"):
        raw = metadata.get(key)
        if raw not in {None, ""}:
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            return value if value >= 0 else None
    raw_kb = metadata.get("size_kb")
    if raw_kb not in {None, ""}:
        try:
            value = int(float(raw_kb) * 1024)
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None
    return None


def _download_remote_asset(
    ref: AssetReference,
    *,
    cache_root: str,
    civitai_api_key: str | None,
    force_download: bool,
    timeout_sec: int,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
    preferred_architecture: str | None = None,
) -> MaterializedAsset:
    download_url, metadata = _resolve_download_url_and_metadata(
        ref, civitai_api_key=civitai_api_key, timeout_sec=timeout_sec,
        preferred_architecture=preferred_architecture,
    )
    if not download_url:
        raise RuntimeError(f"Could not resolve download URL for asset: {ref.raw!r}")

    file_name = ref.filename or metadata.get("filename") or _filename_from_headers(metadata.get("headers") or {}) or _filename_from_url(download_url)
    if not file_name:
        file_name = f"{ref.asset_type}.bin"

    source_component = _safe_cache_component(ref.source_name, "source")
    type_component = _safe_cache_component(ref.asset_type, "asset type")
    file_name = _safe_download_filename(str(file_name))

    download_url = _append_query_params(download_url, ref.query_params)
    cache_path = Path(cache_root).expanduser().resolve()
    target_dir = (cache_path / source_component / type_component).resolve()
    _require_contained_path(cache_path, target_dir, "asset cache directory")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = (target_dir / file_name).resolve()
    _require_contained_path(target_dir, target_path, "download filename")

    if target_path.exists() and not force_download and target_path.stat().st_size > 0:
        return MaterializedAsset(
            original=ref,
            resolved_kind="downloaded_file",
            value=str(target_path),
            local_path=str(target_path),
            metadata={**metadata, "cache_hit": True},
        )

    headers = dict(ref.headers)
    headers.setdefault("User-Agent", "SpellVision/1.0 (local guided-fetch; +https://github.com/)")
    if ref.source_name == "civitai" and civitai_api_key:
        headers.setdefault("Authorization", f"Bearer {civitai_api_key}")

    tmp_fd, tmp_name = tempfile.mkstemp(prefix="spellvision_", suffix=".part", dir=str(target_dir))
    os.close(tmp_fd)
    try:
        req = urllib.request.Request(download_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp, open(tmp_name, "wb") as fh:
            response_headers = {k: v for k, v in resp.headers.items()}
            max_bytes = _max_model_download_bytes()
            content_length = _header_content_length(response_headers)
            declared_size = _declared_download_size(metadata)
            if content_length is not None and content_length > max_bytes:
                raise RuntimeError(
                    f"Model download exceeds configured byte limit ({content_length} > {max_bytes})."
                )
            if declared_size is not None and declared_size > max_bytes:
                raise RuntimeError(
                    f"Declared model size exceeds configured byte limit ({declared_size} > {max_bytes})."
                )
            if content_length is not None and declared_size is not None:
                tolerance = max(1024 * 1024, int(declared_size * 0.01))
                if abs(content_length - declared_size) > tolerance:
                    raise RuntimeError("Content-Length does not match the provider-declared model size.")

            expected_for_space = content_length or declared_size or min(max_bytes, 1024 * 1024 * 1024)
            if shutil.disk_usage(target_dir).free < expected_for_space + DOWNLOAD_DISK_HEADROOM_BYTES:
                raise RuntimeError("Insufficient disk space for model download and safety headroom.")

            total_expected = content_length or declared_size
            if progress_cb is not None:
                progress_cb(0, total_expected)

            written = 0
            last_reported = 0
            while True:
                if cancel_cb is not None and cancel_cb():
                    raise DownloadCancelled(f"Download cancelled: {file_name}")
                chunk = resp.read(DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise RuntimeError(f"Model download exceeded configured byte limit ({max_bytes}).")
                fh.write(chunk)
                # Report on a byte stride, not per chunk: a 6 GB model at a 1 MB chunk is ~6000
                # callbacks, and each one costs a lock plus a snapshot rebuild on the manager side.
                if progress_cb is not None and written - last_reported >= DOWNLOAD_PROGRESS_STRIDE_BYTES:
                    last_reported = written
                    progress_cb(written, total_expected)
                if shutil.disk_usage(target_dir).free < DOWNLOAD_DISK_HEADROOM_BYTES:
                    raise RuntimeError("Model download stopped because disk safety headroom was exhausted.")
            if progress_cb is not None:
                progress_cb(written, total_expected or written)
            if content_length is not None and written != content_length:
                raise RuntimeError(
                    f"Content-Length mismatch: expected {content_length} bytes, received {written}."
                )
            if declared_size is not None:
                tolerance = max(1024 * 1024, int(declared_size * 0.01))
                if abs(written - declared_size) > tolerance:
                    raise RuntimeError(
                        f"Downloaded size does not match provider declaration: {written} vs {declared_size}."
                    )
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except Exception:
            pass
        raise

    metadata = dict(metadata)
    metadata["cache_hit"] = False
    metadata["download_url"] = download_url
    metadata["headers"] = response_headers
    metadata.setdefault("filename", file_name)
    return MaterializedAsset(
        original=ref,
        resolved_kind="downloaded_file",
        value=str(target_path),
        local_path=str(target_path),
        metadata=metadata,
    )


def _resolve_download_url_and_metadata(ref: AssetReference, *, civitai_api_key: str | None, timeout_sec: int,
                                       preferred_architecture: str | None = None) -> tuple[str, dict[str, Any]]:
    if ref.kind == "direct_url":
        return ref.url or "", {"filename": ref.filename}

    if ref.kind == "civitai_download_url":
        return ref.url or "", {"filename": ref.filename, "model_version_id": ref.model_version_id}

    if ref.kind in {"civitai_model_page", "civitai_model_version"}:
        version_id = ref.model_version_id
        if not version_id and ref.model_id:
            model_payload = _civitai_api_get_json(
                f"https://civitai.com/api/v1/models/{ref.model_id}",
                civitai_api_key=civitai_api_key,
                timeout_sec=timeout_sec,
            )
            variants = model_variants(model_payload)
            # A model-page URL carries no version. Taking versions[0] was silently wrong: one
            # Civitai model id can hold variants for SEVERAL DIFFERENT ARCHITECTURES -- measured on
            # "Vintage Mix by AK" (2842735), six versions spanning Flux.1 D, ZImageTurbo, Pony,
            # Krea 2, SDXL 1.0 and Illustrious. Picking the first gave whoever pasted that link a
            # Flux LoRA no matter what their workflow needed, and it downloaded successfully with a
            # plausible name, so nothing looked wrong.
            if len(variants) == 1:
                version_id = str(variants[0].version_id)
            elif len(variants) > 1:
                chosen = select_variant(variants, preferred_architecture)
                if chosen is None:
                    raise AmbiguousCivitaiModel(ref.model_id, variants, preferred_architecture)
                version_id = str(chosen.version_id)
        if not version_id:
            raise RuntimeError(f"Civitai reference does not contain a resolvable modelVersionId: {ref.raw!r}")

        payload = _civitai_api_get_json(
            f"https://civitai.com/api/v1/model-versions/{version_id}",
            civitai_api_key=civitai_api_key,
            timeout_sec=timeout_sec,
        )
        primary_file = _pick_primary_civitai_file(payload)
        download_url = str(primary_file.get("downloadUrl") or payload.get("downloadUrl") or f"https://civitai.com/api/download/models/{version_id}")
        filename = str(primary_file.get("name") or payload.get("name") or ref.filename or "").strip() or None
        meta = {
            "filename": filename,
            "model_version_id": version_id,
            "model_id": ref.model_id or payload.get("modelId"),
            "trained_words": payload.get("trainedWords") or [],
            "file_format": primary_file.get("format"),
            "pickle_scan_result": primary_file.get("pickleScanResult"),
            "virus_scan_result": primary_file.get("virusScanResult"),
            "size_kb": primary_file.get("sizeKB"),
        }
        return download_url, meta

    return ref.url or "", {"filename": ref.filename}


def _pick_primary_civitai_file(payload: dict[str, Any]) -> dict[str, Any]:
    files = payload.get("files") or []
    if isinstance(files, list):
        for file in files:
            if isinstance(file, dict) and file.get("primary"):
                return file
        for file in files:
            if isinstance(file, dict):
                return file
    return {}


def _civitai_api_get_json(url: str, *, civitai_api_key: str | None, timeout_sec: int) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SpellVision/1.0 (local guided-fetch; +https://github.com/)",
        "Accept": "application/json",
    }
    if civitai_api_key:
        headers["Authorization"] = f"Bearer {civitai_api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Civitai API request failed: {exc}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Civitai API request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Civitai API response for {url!r}")
    return payload


def _append_query_params(url: str, params: dict[str, str]) -> str:
    if not params:
        return url
    parsed = urllib.parse.urlparse(url)
    current = urllib.parse.parse_qs(parsed.query)
    for key, value in params.items():
        current[str(key)] = [str(value)]
    new_query = urllib.parse.urlencode(current, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def _filename_from_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    name = Path(parsed.path).name
    return name or None


def _filename_from_headers(headers: dict[str, Any]) -> str | None:
    disposition = str(headers.get("Content-Disposition") or headers.get("content-disposition") or "").strip()
    if not disposition:
        return None
    parts = disposition.split(";")
    for part in parts:
        part = part.strip()
        if part.lower().startswith("filename*="):
            value = part.split("=", 1)[1].strip()
            if "''" in value:
                value = value.split("''", 1)[1]
            return urllib.parse.unquote(value.strip('"'))
        if part.lower().startswith("filename="):
            value = part.split("=", 1)[1].strip().strip('"')
            return value or None
    return None
