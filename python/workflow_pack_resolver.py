"""Resolve a workflow's missing node classes to installable packs using what the workflow declares.

ComfyUI stamps every node it saves with the pack it came from::

    "properties": {"cnr_id": "comfyui-easy-use",
                   "aux_id": "yolain/ComfyUI-Easy-Use",
                   "ver": "717092a3ceb51c474b5b3f77fc188979f0db9d67"}

So the class -> pack question that ``node_dependency_resolver`` answers by fuzzy-matching class names
against a 6-entry starter catalog is, for the common case, *already answered inside the file*. Measured
on this library: 431 non-core nodes carry cnr_id + aux_id + ver, 257 carry cnr_id + ver, 14 carry
aux_id + ver, and 435 carry nothing. Of the 40 classes that genuinely block a launch here, 26 name
their own pack.

``ver`` is the pin. When ``aux_id`` is present it is a git commit sha; with only ``cnr_id`` it is a
Registry semver. Either way the workflow tells us the exact revision that produced it, which is what
Doc 28 3 ("pinned commits, not floating main") asks for.

Tiers, in order:

  1. ``aux_id``  -> ``https://github.com/{owner}/{repo}``, pinned to ``ver``. Needs no network.
  2. ``cnr_id``  -> ``GET api.comfy.org/nodes/{id}`` for repo + license + published version.
  3. neither     -> caller's problem (``node_registry_resolver.build_class_pack_index`` reverse
     index, or manual review). Reported UNRESOLVED with a reason, never guessed.

Licence is **disclosed, never a gate**. Verified live: comfyui-kjnodes, comfyui-videohelpersuite,
rgthree-comfy and comfyui-easy-use all publish ``license: {"file": "LICENSE"}``, which normalises to
UNKNOWN -- and those are precisely the packs that unblock most workflows. Gating the install button on
``is_auto_installable`` would make the feature useless. That predicate is reserved for a future
unattended "don't ask me again" toggle; here we surface pack id, repo, licence (including UNKNOWN) and
download count, and let an informed click authorise the install.

Registry answers are cached to disk (see ``PackCache``) because the pack set moves slowly and the
resolve runs on every readiness check.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable
import json
import time
import urllib.error
import urllib.parse

from node_registry_resolver import (
    UNKNOWN_LICENSE,
    _normalize_license,
    _registry_get,
    is_auto_installable,
)
from workflow_scanner import WorkflowNodeInfo, WorkflowScanReport, node_pack_identity

# A Registry answer is good for a week; a miss for a day, so a pack published yesterday is not
# invisible for the rest of the week.
CACHE_TTL_SEC = 7 * 24 * 3600
NEGATIVE_CACHE_TTL_SEC = 24 * 3600
CACHE_VERSION = 1

SOURCE_AUX_ID = "workflow_aux_id"
SOURCE_CNR_ID = "workflow_cnr_id"
SOURCE_REGISTRY_SEARCH = "registry_class_search"
SOURCE_UNRESOLVED = "unresolved"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DeclaredPack:
    """The pack identity one or more missing classes declare."""

    key: str  # stable identity for grouping: aux_id when present, else cnr_id
    cnr_id: str | None = None
    aux_id: str | None = None
    declared_version: str | None = None  # properties.ver -- a commit sha or a semver
    class_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PackResolution:
    """A declared pack resolved (or not) to something installable.

    ``license`` is disclosure, not permission: UNKNOWN is a real, surfaced value and does not block
    the install button. ``auto_installable`` is carried for the future unattended toggle only.
    """

    key: str
    class_names: list[str]
    status: str  # RESOLVED | UNRESOLVED
    source: str
    pack_id: str | None = None
    aux_id: str | None = None
    repo_url: str | None = None
    install_ref: str | None = None  # the exact revision to install: sha or semver
    ref_kind: str = "unknown"  # commit | version | default_branch | unknown
    license: str = UNKNOWN_LICENSE
    auto_installable: bool = False
    downloads: int = 0
    github_stars: int = 0
    py_deps: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowPackPlan:
    resolutions: list[PackResolution] = field(default_factory=list)
    unresolved_classes: list[str] = field(default_factory=list)
    undeclared_classes: list[str] = field(default_factory=list)
    registry_reachable: bool = True
    registry_consulted: bool = False
    cache_path: str | None = None
    # Tier 3 state, so the UI can say "no pack found" rather than the misleading "nothing to install"
    # when the reverse index has simply never been built.
    index_available: bool = False
    index_complete: bool = False

    def resolved(self) -> list[PackResolution]:
        return [r for r in self.resolutions if r.status == "RESOLVED"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": {
                "packs": len(self.resolutions),
                "resolved_packs": len(self.resolved()),
                "classes_covered": sum(len(r.class_names) for r in self.resolved()),
                "classes_unresolved": len(self.unresolved_classes),
                "classes_undeclared": len(self.undeclared_classes),
            },
            "registry_reachable": self.registry_reachable,
            "registry_consulted": self.registry_consulted,
            "index_available": self.index_available,
            "index_complete": self.index_complete,
            "cache_path": self.cache_path,
            "resolutions": [r.to_dict() for r in self.resolutions],
            "unresolved_classes": self.unresolved_classes,
            "undeclared_classes": self.undeclared_classes,
        }


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------

def _cache_dir() -> Path:
    try:
        from runtime_paths import RuntimePaths

        return Path(RuntimePaths.CACHE) / "comfy_registry"
    except Exception:
        return Path(__file__).resolve().parent.parent / "runtime" / "cache" / "comfy_registry"


def default_cache_path() -> Path:
    return _cache_dir() / "packs.json"


def default_directory_path() -> Path:
    return _cache_dir() / "pack_directory.json"


def default_index_path() -> Path:
    return _cache_dir() / "class_pack_index.json"


class PackCache:
    """Registry pack details keyed by pack id, with TTLs and best-effort persistence.

    Never raises for IO: a cache that cannot be read or written degrades to "no cache", which is
    slower but correct. A corrupt file is discarded rather than half-trusted.
    """

    def __init__(self, path: str | Path | None = None, *, ttl: float = CACHE_TTL_SEC,
                 negative_ttl: float = NEGATIVE_CACHE_TTL_SEC) -> None:
        self.path = Path(path) if path else default_cache_path()
        self.ttl = ttl
        self.negative_ttl = negative_ttl
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            return
        entries = payload.get("packs")
        if isinstance(entries, dict):
            self._entries = {k: v for k, v in entries.items() if isinstance(v, dict)}

    def get(self, pack_id: str) -> dict[str, Any] | None:
        entry = self._entries.get(pack_id)
        if not isinstance(entry, dict):
            return None
        age = time.time() - float(entry.get("fetched_at") or 0.0)
        ttl = self.negative_ttl if entry.get("found") is False else self.ttl
        if age > ttl:
            return None
        return entry

    def put(self, pack_id: str, detail: dict[str, Any] | None) -> None:
        self._entries[pack_id] = {
            "fetched_at": time.time(),
            "found": detail is not None,
            "detail": detail or {},
        }
        self._dirty = True

    def flush(self) -> None:
        if not self._dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"version": CACHE_VERSION, "packs": self._entries}, indent=1),
                encoding="utf-8",
            )
            self._dirty = False
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Pack directory + verified class search (tier 3: classes the workflow does not declare)
# ---------------------------------------------------------------------------

class PackDirectory:
    """The Registry's full pack list, cached to disk.

    ``GET /nodes`` pages the whole catalogue (5340 packs / 54 pages, ~40s measured) and is the only
    bulk source there is: the search parameters are ignored -- re-verified, ``?search=comfyroll``
    still returns all 5340 -- and ``GET /comfy-nodes?comfy_node_name=X`` proves a class EXISTS but
    names no pack. So a class -> pack answer has to be assembled locally.

    Building the complete reverse index costs ~2s per pack, i.e. **~3.7 hours** measured. That is a
    background job, not something a dependency check may run. The directory is the cheap half: it
    lets ``search_class_in_registry`` pick a handful of plausible packs and then CONFIRM each one by
    reading its actual class list. The heuristic only chooses what to check; the answer still comes
    from an exact class-name match, so nothing is guessed.
    """

    def __init__(self, path: str | Path | None = None, *, ttl: float = CACHE_TTL_SEC) -> None:
        self.path = Path(path) if path else default_directory_path()
        self.ttl = ttl
        self.entries: list[dict[str, Any]] = []
        self.fetched_at: float = 0.0
        self._load()

    @property
    def fresh(self) -> bool:
        return bool(self.entries) and (time.time() - self.fetched_at) <= self.ttl

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            return
        entries = payload.get("packs")
        if isinstance(entries, list):
            self.entries = [e for e in entries if isinstance(e, dict)]
            self.fetched_at = float(payload.get("fetched_at") or 0.0)

    def ensure(
        self,
        *,
        getter: Callable[..., Any] = _registry_get,
        timeout: float = 20.0,
        progress: Callable[[str], None] | None = None,
        max_pages: int | None = None,
    ) -> bool:
        """Populate from the Registry unless a fresh copy is already cached. False on failure."""
        if self.fresh:
            return True
        entries: list[dict[str, Any]] = []
        page = 1
        while True:
            try:
                data = getter("/nodes", {"page": page, "limit": 100}, timeout=timeout)
            except Exception:
                return False
            if not isinstance(data, dict):
                return False
            for pack in data.get("nodes") or []:
                if not isinstance(pack, dict) or not pack.get("id"):
                    continue
                latest = pack.get("latest_version") if isinstance(pack.get("latest_version"), dict) else {}
                entries.append({
                    "id": pack.get("id"),
                    "name": pack.get("name") or "",
                    "description": (pack.get("description") or "")[:400],
                    "repository": pack.get("repository") or "",
                    "publisher": ((pack.get("publisher") or {}).get("name") or "") if isinstance(pack.get("publisher"), dict) else "",
                    "license": pack.get("license"),
                    "version": latest.get("version"),
                    "py_deps": [d for d in (latest.get("dependencies") or []) if isinstance(d, str)],
                    "downloads": int(pack.get("downloads") or 0),
                    "github_stars": int(pack.get("github_stars") or 0),
                })
            total_pages = int(data.get("totalPages") or 1)
            if progress:
                progress(f"pack directory page {page}/{total_pages} ({len(entries)} packs)")
            if page >= total_pages or (max_pages and page >= max_pages):
                break
            page += 1
        self.entries = entries
        self.fetched_at = time.time()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"version": CACHE_VERSION, "fetched_at": self.fetched_at, "packs": entries}, indent=0),
                encoding="utf-8",
            )
        except Exception:
            pass
        return True


class ClassPackIndex:
    """class name -> the Registry pack that publishes it. Built offline, cached, resumable.

    Why a full index and not a search: there is no class->pack endpoint, ``?search=`` is ignored, and
    a name heuristic does not work. Measured -- ranking packs by token overlap with the class name and
    then verifying against each candidate's real node list resolved **0 of the 16** undeclared classes
    in this library, because the packs that provide ``SetNode``, ``LoadImageBatch`` and
    ``CR Upscale Image`` share no tokens with those names. There is no shortcut: either the pack is
    named in the workflow, or every pack's node list has to be read once.

    Cost measured on the live Registry: 5340 packs, ~2s per pack sequentially (~3.7 hours), which is
    a background job -- never something a dependency check runs inline. ``build`` is resumable and
    honours a wall-clock budget, so it can be run in slices and its partial result is still usable.
    """

    def __init__(self, path: str | Path | None = None, *, ttl: float = CACHE_TTL_SEC) -> None:
        self.path = Path(path) if path else default_index_path()
        self.ttl = ttl
        self.classes: dict[str, dict[str, Any]] = {}
        self.packs_done: set[str] = set()
        self.fetched_at: float = 0.0
        self.complete: bool = False
        self._load()

    @property
    def usable(self) -> bool:
        """Any indexed class at all is usable; a partial index answers what it covers and no more."""
        return bool(self.classes) and (time.time() - self.fetched_at) <= self.ttl

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            return
        classes = payload.get("classes")
        if isinstance(classes, dict):
            self.classes = {k: v for k, v in classes.items() if isinstance(v, dict)}
        done = payload.get("packs_done")
        if isinstance(done, list):
            self.packs_done = {str(p) for p in done}
        self.fetched_at = float(payload.get("fetched_at") or 0.0)
        self.complete = bool(payload.get("complete"))

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({
                    "version": CACHE_VERSION,
                    "fetched_at": self.fetched_at or time.time(),
                    "complete": self.complete,
                    "packs_done": sorted(self.packs_done),
                    "classes": self.classes,
                }, indent=0),
                encoding="utf-8",
            )
        except Exception:
            pass

    def build(
        self,
        directory: PackDirectory,
        *,
        getter: Callable[..., Any] = _registry_get,
        timeout: float = 20.0,
        workers: int = 8,
        budget_sec: float | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Read every not-yet-indexed pack's node list. Resumable; returns a progress summary."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from node_registry_resolver import _fetch_pack_classes

        pending = [e for e in directory.entries if str(e.get("id")) not in self.packs_done]
        started = time.time()
        errors = 0
        done = 0

        def fetch(entry: dict[str, Any]) -> tuple[dict[str, Any], list[str] | None]:
            pack_id = str(entry.get("id"))
            try:
                _, classes = _fetch_pack_classes(getter, pack_id, entry.get("version"), timeout=timeout)
            except Exception:
                return entry, None
            return entry, classes

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(fetch, e): e for e in pending}
            for future in as_completed(futures):
                entry, classes = future.result()
                pack_id = str(entry.get("id"))
                done += 1
                if classes is None:
                    errors += 1
                else:
                    self.packs_done.add(pack_id)
                    record = {
                        "pack_id": pack_id,
                        "version": entry.get("version"),
                        "repo_url": entry.get("repository") or None,
                        "license": entry.get("license"),
                        "py_deps": list(entry.get("py_deps") or []),
                        "downloads": int(entry.get("downloads") or 0),
                        "github_stars": int(entry.get("github_stars") or 0),
                    }
                    for class_name in classes:
                        if not class_name:
                            continue
                        prev = self.classes.get(class_name)
                        # Several packs can publish the same class name; prefer the more used one.
                        if prev is None or record["downloads"] > int(prev.get("downloads") or 0):
                            self.classes[class_name] = record
                if progress and done % 100 == 0:
                    progress(f"indexed {done}/{len(pending)} packs, {len(self.classes)} classes, {errors} errors")
                if budget_sec is not None and (time.time() - started) >= budget_sec:
                    for pending_future in futures:
                        pending_future.cancel()
                    break

        self.fetched_at = time.time()
        self.complete = len(self.packs_done) >= len(directory.entries)
        self.save()
        return {
            "packs_total": len(directory.entries),
            "packs_indexed": len(self.packs_done),
            "classes_indexed": len(self.classes),
            "errors": errors,
            "complete": self.complete,
            "elapsed_sec": round(time.time() - started, 1),
        }


def search_class_in_registry(class_name: str, *, index: ClassPackIndex) -> PackResolution | None:
    """Look a class up in the reverse index. A hit is an exact class-name match published by that
    pack -- evidence, not a name guess. A miss returns None so the caller reports it honestly."""
    entry = index.classes.get(class_name)
    if not isinstance(entry, dict):
        return None
    lic = _normalize_license(entry.get("license"))
    return PackResolution(
        key=str(entry.get("pack_id")),
        class_names=[class_name],
        status="RESOLVED",
        source=SOURCE_REGISTRY_SEARCH,
        pack_id=str(entry.get("pack_id")),
        repo_url=str(entry.get("repo_url") or "").strip() or None,
        install_ref=entry.get("version"),
        ref_kind="version" if entry.get("version") else "default_branch",
        license=lic,
        auto_installable=is_auto_installable(lic),
        downloads=int(entry.get("downloads") or 0),
        github_stars=int(entry.get("github_stars") or 0),
        py_deps=list(entry.get("py_deps") or []),
        reason=f"Registry pack '{entry.get('pack_id')}' publishes a node named '{class_name}'",
    )


# ---------------------------------------------------------------------------
# Declaration extraction
# ---------------------------------------------------------------------------

def _github_repo_url(aux_id: str) -> str | None:
    parts = [p for p in aux_id.strip().strip("/").split("/") if p]
    if len(parts) != 2:
        return None
    owner, repo = parts
    if not owner or not repo:
        return None
    return f"https://github.com/{owner}/{repo}"


def _looks_like_commit(ref: str | None) -> bool:
    if not ref:
        return False
    text = ref.strip()
    return len(text) >= 7 and all(c in "0123456789abcdefABCDEF" for c in text)


def declared_packs(
    nodes: Iterable[WorkflowNodeInfo],
    class_names: Iterable[str],
) -> tuple[list[DeclaredPack], list[str]]:
    """Group the given class names by the pack identity their nodes declare.

    Returns ``(packs, undeclared_class_names)``. A class whose nodes carry no cnr_id/aux_id is
    undeclared -- reported, never guessed at here.

    When two nodes of the same class declare different packs (a graph assembled from two exports)
    the first identity wins and the class is still covered once; the alternative is an unresolvable
    fork that helps nobody.
    """
    wanted = {str(c) for c in class_names}
    by_key: dict[str, DeclaredPack] = {}
    seen_classes: set[str] = set()

    for node in nodes:
        class_type = (node.class_type or "").strip()
        if class_type not in wanted or class_type in seen_classes:
            continue
        ident = node_pack_identity(node)
        cnr_id = ident.get("cnr_id")
        aux_id = ident.get("aux_id")
        if cnr_id == "comfy-core":
            # A core node that is still missing is a version problem, not a pack to install.
            continue
        if not cnr_id and not aux_id:
            continue
        seen_classes.add(class_type)
        key = aux_id or cnr_id or class_type
        pack = by_key.get(key)
        if pack is None:
            pack = DeclaredPack(
                key=key,
                cnr_id=cnr_id,
                aux_id=aux_id,
                declared_version=ident.get("ver"),
            )
            by_key[key] = pack
        else:
            pack.cnr_id = pack.cnr_id or cnr_id
            pack.aux_id = pack.aux_id or aux_id
            pack.declared_version = pack.declared_version or ident.get("ver")
        pack.class_names.append(class_type)

    for pack in by_key.values():
        pack.class_names = sorted(set(pack.class_names))

    undeclared = sorted(wanted - seen_classes)
    packs = sorted(by_key.values(), key=lambda p: p.key.lower())
    return packs, undeclared


# ---------------------------------------------------------------------------
# Registry lookup
# ---------------------------------------------------------------------------

def _normalized_repo(repo_url: str | None) -> str | None:
    """A repo identity that survives case and the .git suffix, for deduplication."""
    if not repo_url:
        return None
    text = repo_url.strip().rstrip("/").lower()
    if text.endswith(".git"):
        text = text[:-4]
    return text or None


def _merge_same_repo(resolutions: list[PackResolution]) -> list[PackResolution]:
    """Collapse resolutions that point at the same repository.

    A graph assembled from several exports can name one pack under both identities -- measured here,
    some nodes declared ``cnr_id: ComfyUI_Comfyroll_CustomNodes`` and others
    ``aux_id: Suzie1/ComfyUI_Comfyroll_CustomNodes``. Grouping happens before the Registry is asked,
    so the two only reveal themselves as one pack once both have a repo URL. Left unmerged they
    produce two install actions for the same directory -- the duplicate-install failure mode this
    whole tier exists to end.

    The surviving resolution keeps the most precise pin (a commit beats a version) and whatever
    licence metadata was actually confirmed.
    """
    merged: dict[str, PackResolution] = {}
    order: list[str] = []
    out: list[PackResolution] = []

    for res in resolutions:
        repo_key = _normalized_repo(res.repo_url)
        if res.status != "RESOLVED" or repo_key is None:
            out.append(res)
            continue
        existing = merged.get(repo_key)
        if existing is None:
            merged[repo_key] = res
            order.append(repo_key)
            continue
        existing.class_names = sorted(set(existing.class_names) | set(res.class_names))
        existing.pack_id = existing.pack_id or res.pack_id
        existing.aux_id = existing.aux_id or res.aux_id
        if res.ref_kind == "commit" and existing.ref_kind != "commit":
            existing.install_ref, existing.ref_kind = res.install_ref, res.ref_kind
        elif existing.install_ref is None:
            existing.install_ref, existing.ref_kind = res.install_ref, res.ref_kind
        if existing.license == UNKNOWN_LICENSE and res.license != UNKNOWN_LICENSE:
            existing.license = res.license
            existing.auto_installable = res.auto_installable
        existing.downloads = max(existing.downloads, res.downloads)
        existing.github_stars = max(existing.github_stars, res.github_stars)
        existing.py_deps = sorted(set(existing.py_deps) | set(res.py_deps))
        if res.reason and res.reason not in existing.reason:
            existing.reason = f"{existing.reason}; also declared as {res.key}"

    resolved_in_order = [merged[k] for k in order]
    return resolved_in_order + out


def _registry_pack_detail(
    pack_id: str,
    *,
    getter: Callable[..., Any],
    cache: PackCache | None,
    timeout: float,
) -> tuple[dict[str, Any] | None, bool]:
    """Return ``(detail_or_None, network_ok)``.

    ``network_ok`` distinguishes "the Registry says this pack does not exist" (a real answer worth
    caching) from "the Registry could not be reached" (no answer at all -- never cached as a miss,
    or an offline moment would poison the cache for a day).
    """
    if cache is not None:
        entry = cache.get(pack_id)
        if entry is not None:
            return (entry.get("detail") or None) if entry.get("found") else None, True

    try:
        detail = getter(f"/nodes/{urllib.parse.quote(pack_id, safe='')}", timeout=timeout)
    except urllib.error.HTTPError as exc:
        if 400 <= int(getattr(exc, "code", 0) or 0) < 500:
            if cache is not None:
                cache.put(pack_id, None)
            return None, True
        return None, False
    except Exception:
        return None, False

    if not isinstance(detail, dict):
        if cache is not None:
            cache.put(pack_id, None)
        return None, True
    if cache is not None:
        cache.put(pack_id, detail)
    return detail, True


def _resolution_from_declaration(
    pack: DeclaredPack,
    *,
    getter: Callable[..., Any],
    cache: PackCache | None,
    timeout: float,
    offline: bool,
) -> tuple[PackResolution, bool | None]:
    """Resolve one declared pack. Second element is registry reachability (None = not consulted)."""
    repo_url = _github_repo_url(pack.aux_id) if pack.aux_id else None
    registry_ok: bool | None = None
    detail: dict[str, Any] | None = None

    if pack.cnr_id and not offline:
        detail, registry_ok = _registry_pack_detail(pack.cnr_id, getter=getter, cache=cache, timeout=timeout)

    license_raw: Any = None
    published_version: str | None = None
    downloads = 0
    stars = 0
    py_deps: list[str] = []
    if detail:
        repo_url = repo_url or (str(detail.get("repository") or "").strip() or None)
        license_raw = detail.get("license")
        latest = detail.get("latest_version") if isinstance(detail.get("latest_version"), dict) else {}
        published_version = str(latest.get("version") or "").strip() or None
        py_deps = [str(d) for d in (latest.get("dependencies") or []) if isinstance(d, str)]
        downloads = int(detail.get("downloads") or 0)
        stars = int(detail.get("github_stars") or 0)

    # The pin. The workflow's own ver is preferred over the Registry's latest: it is the revision
    # that actually produced this graph, which is the whole point of pinning.
    install_ref = pack.declared_version or published_version
    if _looks_like_commit(pack.declared_version):
        ref_kind = "commit"
    elif pack.declared_version:
        ref_kind = "version"
    elif published_version:
        ref_kind = "version"
    else:
        ref_kind = "default_branch"

    if not repo_url:
        reason = (
            f"pack '{pack.cnr_id}' is not in the ComfyUI Registry and the workflow declares no aux_id repo"
            if pack.cnr_id and registry_ok
            else "could not reach the ComfyUI Registry to look up this pack"
            if pack.cnr_id
            else "no installable source could be derived from the declared identity"
        )
        return (
            PackResolution(
                key=pack.key,
                class_names=list(pack.class_names),
                status="UNRESOLVED",
                source=SOURCE_UNRESOLVED,
                pack_id=pack.cnr_id,
                aux_id=pack.aux_id,
                install_ref=install_ref,
                ref_kind=ref_kind,
                reason=reason,
            ),
            registry_ok,
        )

    lic = _normalize_license(license_raw) if detail else UNKNOWN_LICENSE
    source = SOURCE_AUX_ID if pack.aux_id else SOURCE_CNR_ID
    if source == SOURCE_AUX_ID:
        reason = f"workflow declares aux_id '{pack.aux_id}'"
        if detail:
            reason += f"; Registry pack '{pack.cnr_id}' confirms repo and licence"
        elif pack.cnr_id:
            reason += f" (Registry lookup of '{pack.cnr_id}' unavailable, licence not confirmed)"
    else:
        reason = f"workflow declares cnr_id '{pack.cnr_id}'; Registry gives repo and licence"

    return (
        PackResolution(
            key=pack.key,
            class_names=list(pack.class_names),
            status="RESOLVED",
            source=source,
            pack_id=pack.cnr_id,
            aux_id=pack.aux_id,
            repo_url=repo_url,
            install_ref=install_ref,
            ref_kind=ref_kind,
            license=lic,
            auto_installable=is_auto_installable(lic),
            downloads=downloads,
            github_stars=stars,
            py_deps=py_deps,
            reason=reason,
        ),
        registry_ok,
    )


def resolve_declared_packs(
    nodes: Iterable[WorkflowNodeInfo],
    class_names: Iterable[str],
    *,
    getter: Callable[..., Any] = _registry_get,
    cache: PackCache | None = None,
    cache_path: str | Path | None = None,
    timeout: float = 20.0,
    offline: bool = False,
    search_undeclared: bool = False,
    index: ClassPackIndex | None = None,
    index_path: str | Path | None = None,
) -> WorkflowPackPlan:
    """Resolve missing class names to installable packs.

    Tier 1-2 read the workflow's own ``cnr_id`` / ``aux_id`` declarations. ``search_undeclared=True``
    adds tier 3 for the classes that declare nothing: a pure lookup in the cached ``ClassPackIndex``.
    Tier 3 never builds the index (that is a background job costing hours) -- if no index is cached
    the classes stay undeclared and ``index_available`` says why.

    ``offline=True`` skips every Registry call: aux_id packs still resolve -- a GitHub URL is
    derivable without a network -- but their licence stays UNKNOWN, and cnr_id-only packs stay
    unresolved. The plan says which, so the UI can distinguish "no pack exists" from "we could not
    check".
    """
    if cache is None and not offline:
        cache = PackCache(cache_path)

    packs, undeclared = declared_packs(nodes, class_names)
    plan = WorkflowPackPlan(
        undeclared_classes=undeclared,
        cache_path=str(cache.path) if cache is not None else None,
    )

    reachability: list[bool] = []
    resolutions: list[PackResolution] = []
    for pack in packs:
        resolution, registry_ok = _resolution_from_declaration(
            pack, getter=getter, cache=cache, timeout=timeout, offline=offline
        )
        resolutions.append(resolution)
        if registry_ok is not None:
            plan.registry_consulted = True
            reachability.append(registry_ok)

    if undeclared and search_undeclared:
        if index is None:
            index = ClassPackIndex(index_path)
        plan.index_available = index.usable
        plan.index_complete = index.complete
        if index.usable:
            still_undeclared: list[str] = []
            for class_name in undeclared:
                found = search_class_in_registry(class_name, index=index)
                if found is None:
                    still_undeclared.append(class_name)
                else:
                    resolutions.append(found)
            plan.undeclared_classes = still_undeclared

    plan.resolutions = _merge_same_repo(resolutions)
    for resolution in plan.resolutions:
        if resolution.status != "RESOLVED":
            plan.unresolved_classes.extend(resolution.class_names)

    plan.unresolved_classes = sorted(set(plan.unresolved_classes))
    plan.registry_reachable = any(reachability) if reachability else not plan.registry_consulted

    if cache is not None:
        cache.flush()
    return plan


def resolve_report_packs(
    report: WorkflowScanReport,
    **kwargs: Any,
) -> WorkflowPackPlan:
    """``resolve_declared_packs`` over a scan report's missing classes."""
    return resolve_declared_packs(report.nodes, report.missing_custom_nodes, **kwargs)


# ---------------------------------------------------------------------------
# Install actions
# ---------------------------------------------------------------------------

def package_name_for(resolution: PackResolution) -> str:
    """The directory name the pack installs under.

    Prefer the repo name from aux_id: that is what a git/zipball install produces on disk and what
    ``list_installed_nodes`` will report back, so an "already installed" check can match it. The
    Registry id (lowercase, hyphenated) frequently differs in case from the repo directory.
    """
    if resolution.aux_id and "/" in resolution.aux_id:
        return resolution.aux_id.split("/")[-1]
    if resolution.repo_url:
        tail = resolution.repo_url.rstrip("/").split("/")[-1]
        if tail:
            return tail[:-4] if tail.endswith(".git") else tail
    return resolution.pack_id or resolution.key


def install_actions_for(plan: WorkflowPackPlan) -> list[dict[str, Any]]:
    """Install actions in the shape ``install_custom_node`` already accepts.

    Every action carries the licence and download count so the confirmation UI can disclose what is
    about to be installed and from where. ``requires_confirmation`` is always True: the informed
    click is the authorisation, and nothing here installs itself.
    """
    actions: list[dict[str, Any]] = []
    for resolution in plan.resolved():
        actions.append(
            {
                "kind": "git_clone",
                "package_name": package_name_for(resolution),
                "pack_id": resolution.pack_id,
                "repo_url": resolution.repo_url,
                "install_method": "git",
                "install_ref": resolution.install_ref,
                "ref_kind": resolution.ref_kind,
                "class_names": list(resolution.class_names),
                "license": resolution.license,
                "auto_installable": resolution.auto_installable,
                "downloads": resolution.downloads,
                "github_stars": resolution.github_stars,
                "source": resolution.source,
                "reason": resolution.reason,
                "requires_confirmation": True,
            }
        )
    return actions
