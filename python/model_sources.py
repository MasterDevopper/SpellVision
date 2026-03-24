from __future__ import annotations
from runtime_paths import RuntimePaths

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
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
CIVITAI_DOWNLOAD_RE = re.compile(r"^https?://(?:www\.)?civitai\.com/api/download/models/(?P<version_id>\d+)", re.IGNORECASE)
CIVITAI_MODEL_PAGE_RE = re.compile(r"^https?://(?:www\.)?civitai\.com/models/(?P<model_id>\d+)(?:[/?#].*)?$", re.IGNORECASE)


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
        return AssetReference(raw=value, kind="hf_repo", source_name="huggingface", asset_type=asset_type, repo_id=raw[5:])

    if HF_REPO_RE.match(raw) and not os.path.isabs(raw) and not raw.startswith("./") and not raw.startswith("../"):
        return AssetReference(raw=value, kind="hf_repo", source_name="huggingface", asset_type=asset_type, repo_id=raw)

    normalized = raw.replace("\\", "/")
    path = Path(raw)
    if path.suffix:
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
    force_download: bool = False,
    timeout_sec: int = 120,
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
        return MaterializedAsset(original=ref, resolved_kind="hf_repo", value=repo_id, repo_id=repo_id)

    if ref.kind in {"direct_url", "civitai_download_url", "civitai_model_page", "civitai_model_version"}:
        return _download_remote_asset(
            ref,
            cache_root=cache_root,
            civitai_api_key=civitai_api_key,
            force_download=force_download,
            timeout_sec=timeout_sec,
        )

    return MaterializedAsset(original=ref, resolved_kind=ref.kind, value=str(ref.raw or ""))


def materialize_request_assets(req: dict[str, Any], *, cache_root: str | None = None) -> dict[str, Any]:
    normalized = dict(req)
    cache_root = cache_root or default_asset_cache_root()
    civitai_api_key = str(normalized.get("civitai_api_key") or os.environ.get("CIVITAI_API_KEY") or "").strip() or None
    force_download = bool(normalized.get("force_model_download") or False)

    manifest: dict[str, Any] = {}

    model_ref = normalized.get("model_source") or normalized.get("checkpoint") or normalized.get("model")
    if model_ref:
        model_asset = materialize_asset(
            model_ref,
            asset_type="model",
            cache_root=cache_root,
            civitai_api_key=civitai_api_key,
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


def _download_remote_asset(
    ref: AssetReference,
    *,
    cache_root: str,
    civitai_api_key: str | None,
    force_download: bool,
    timeout_sec: int,
) -> MaterializedAsset:
    download_url, metadata = _resolve_download_url_and_metadata(ref, civitai_api_key=civitai_api_key, timeout_sec=timeout_sec)
    if not download_url:
        raise RuntimeError(f"Could not resolve download URL for asset: {ref.raw!r}")

    file_name = ref.filename or metadata.get("filename") or _filename_from_headers(metadata.get("headers") or {}) or _filename_from_url(download_url)
    if not file_name:
        file_name = f"{ref.asset_type}.bin"

    download_url = _append_query_params(download_url, ref.query_params)
    target_dir = Path(cache_root) / ref.source_name / ref.asset_type
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file_name

    if target_path.exists() and not force_download and target_path.stat().st_size > 0:
        return MaterializedAsset(
            original=ref,
            resolved_kind="downloaded_file",
            value=str(target_path),
            local_path=str(target_path),
            metadata={**metadata, "cache_hit": True},
        )

    headers = dict(ref.headers)
    if ref.source_name == "civitai" and civitai_api_key:
        headers.setdefault("Authorization", f"Bearer {civitai_api_key}")

    tmp_fd, tmp_name = tempfile.mkstemp(prefix="spellvision_", suffix=".part", dir=str(target_dir))
    os.close(tmp_fd)
    try:
        req = urllib.request.Request(download_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp, open(tmp_name, "wb") as fh:
            shutil.copyfileobj(resp, fh)
            response_headers = {k: v for k, v in resp.headers.items()}
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


def _resolve_download_url_and_metadata(ref: AssetReference, *, civitai_api_key: str | None, timeout_sec: int) -> tuple[str, dict[str, Any]]:
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
            versions = model_payload.get("modelVersions") or []
            if isinstance(versions, list) and versions:
                version_id = str(versions[0].get("id") or "")
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
    headers = {"Content-Type": "application/json"}
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
