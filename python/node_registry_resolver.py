"""Resolve missing ComfyUI node CLASS names to installable **Registry** packs.

DATA SOURCE — official ComfyUI Registry REST API at ``api.comfy.org`` (Comfy-Org) ONLY.
This module does NOT read, port, vendor, scrape, or derive anything from ComfyUI-Manager
(GPL-3.0) — not its code, not its node->repo mapping table. SpellVision builds its own
resolver against this non-GPL source precisely to avoid that GPL dependency. If a class is not
found in the Registry (or the Registry is unreachable), the class is returned **UNRESOLVED**;
there is NO fallback to Manager, ever.

Dry-run / resolve-then-report (Stage 4, Pass 1): NO side effects — no filesystem, git, pip, or
ComfyUI. Only HTTPS GETs to the Registry.

--- Verified Registry API shape (Step-1 probe, api.comfy.org) ---
  * ``GET /nodes`` — paginated list of ALL packs. Its search/q/name params are IGNORED (every query
    returns all 4822 packs), so a bare class name CANNOT be searched here. Each pack carries
    ``id``, ``license`` (often "{}" / '{"file":"LICENSE"}' == unknown), ``repository``,
    ``latest_version``, ``downloads``, ``github_stars``.
  * ``GET /nodes/{id}`` — a specific pack by exact id (license, repo).
  * ``GET /comfy-nodes?comfy_node_name=X`` — EXISTENCE: total>0 iff some pack version provides class X.
    (Entries carry the node's I/O signature but NO pack reference.)
  * ``GET /nodes/{id}/versions/{v}/comfy-nodes`` — the INVERSE: the class list a pack version provides.
There is NO single-call class->pack lookup. So class->pack requires a reverse index we build ourselves
from the Registry (``build_class_pack_index``) — a non-GPL source. ``resolve_missing_nodes`` is then a
PURE lookup over that index (no network, fully testable).

Sibling to ``node_dependency_resolver.py`` (the Manager-based resolver); kept separate so the Registry
source stays isolated from the GPL bridge.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable
import json
import urllib.error
import urllib.parse
import urllib.request

REGISTRY_BASE = "https://api.comfy.org"
UNKNOWN_LICENSE = "UNKNOWN"

# SPDX-ish license ids we would consider auto-installable WITHOUT a manual license review.
# Seeded conservatively (permissive, non-copyleft only). This set is the ONLY thing the future
# auto-install toggle may treat as "safe to install without a click"; the toggle bypasses the
# user's click, it must NEVER bypass is_auto_installable().
ALLOWLIST: set[str] = {
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "Unlicense",
    "CC0-1.0",
}

_LICENSE_ALIASES: dict[str, str] = {
    "mit": "MIT", "mit license": "MIT", "the mit license": "MIT",
    "apache": "Apache-2.0", "apache 2.0": "Apache-2.0", "apache-2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0", "apache license, version 2.0": "Apache-2.0", "apache-2.0 license": "Apache-2.0",
    "bsd": "BSD-3-Clause", "bsd-3": "BSD-3-Clause", "bsd 3-clause": "BSD-3-Clause", "bsd-3-clause": "BSD-3-Clause",
    "bsd 3-clause license": "BSD-3-Clause", "bsd-3-clause license": "BSD-3-Clause",
    "bsd-2": "BSD-2-Clause", "bsd 2-clause": "BSD-2-Clause", "bsd-2-clause": "BSD-2-Clause",
    "isc": "ISC", "isc license": "ISC",
    "unlicense": "Unlicense", "the unlicense": "Unlicense",
    "cc0": "CC0-1.0", "cc0-1.0": "CC0-1.0", "cc0 1.0": "CC0-1.0",
    # copyleft / restricted — normalized so they read clearly and are provably NOT auto-installable
    "gpl": "GPL-3.0", "gpl-3.0": "GPL-3.0", "gpl3": "GPL-3.0", "gplv3": "GPL-3.0",
    "gpl-3.0 license": "GPL-3.0", "gnu general public license v3.0": "GPL-3.0", "gpl v3": "GPL-3.0",
    "gpl-2.0": "GPL-2.0", "gpl-2.0 license": "GPL-2.0",
    "agpl": "AGPL-3.0", "agpl-3.0": "AGPL-3.0", "agpl-3.0 license": "AGPL-3.0",
    "lgpl": "LGPL-3.0", "lgpl-3.0": "LGPL-3.0",
    "mpl": "MPL-2.0", "mpl-2.0": "MPL-2.0", "mozilla public license 2.0": "MPL-2.0",
    "cc-by-nc-4.0": "CC-BY-NC-4.0", "cc-by-sa-4.0": "CC-BY-SA-4.0",
}


def _normalize_license(raw: Any) -> str:
    """Map a raw Registry license value to an SPDX-ish id. UNKNOWN_LICENSE for empty/absent/filename
    references (a distinct, surfaced state — never blank). Unrecognized ids are returned trimmed
    as-is (so they fail the allowlist == treated as NOT auto-installable, the safe default)."""
    # Registry gives a bare string, sometimes a JSON-string ('{}' / '{"file":"LICENSE"}'), sometimes
    # an object. Reduce to a plain string of any actual license identity.
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped[:1] in "{[" and stripped[-1:] in "}]":
            try:
                raw = json.loads(stripped)
            except Exception:
                pass
    if isinstance(raw, dict):
        raw = raw.get("spdx") or raw.get("id") or raw.get("text") or raw.get("name") or ""  # "file" carries no identity
    text = str(raw or "").strip()
    if not text:
        return UNKNOWN_LICENSE
    lowered = text.lower()
    if lowered in _LICENSE_ALIASES:
        return _LICENSE_ALIASES[lowered]
    for spdx in ALLOWLIST:
        if lowered == spdx.lower():
            return spdx
    if lowered in {"license", "license file", "see repository", "see repo", "none", "null"}:
        return UNKNOWN_LICENSE
    return text


def is_auto_installable(license: str | None) -> bool:
    """The gate the future auto-install toggle MUST consult.

    Returns True ONLY when the (normalized) license is on the permissive ALLOWLIST. Returns False
    for UNKNOWN, blank/None, and anything copyleft or otherwise unrecognized. The auto-install
    toggle bypasses the user's confirmation click; it must NEVER bypass THIS predicate.
    """
    if not license:
        return False
    return _normalize_license(license) in ALLOWLIST


# ---------------------------------------------------------------------------
# Report data model
# ---------------------------------------------------------------------------

@dataclass
class Resolution:
    """One class-name -> Registry outcome. `status` is "RESOLVED" or "UNRESOLVED"."""

    class_name: str
    status: str
    pack_id: str | None = None
    version: str | None = None
    repo_url: str | None = None
    license: str = UNKNOWN_LICENSE  # first-class; UNKNOWN is a distinct state, never blank/omitted
    py_deps: list[str] = field(default_factory=list)
    auto_installable: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResolutionReport:
    resolved: list[Resolution] = field(default_factory=list)
    unresolved: list[Resolution] = field(default_factory=list)
    registry_reachable: bool = True
    registry_base: str = REGISTRY_BASE

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_base": self.registry_base,
            "registry_reachable": self.registry_reachable,
            "counts": {
                "requested": len(self.resolved) + len(self.unresolved),
                "resolved": len(self.resolved),
                "unresolved": len(self.unresolved),
                "resolved_auto_installable": sum(1 for r in self.resolved if r.auto_installable),
                "resolved_manual_only": sum(1 for r in self.resolved if not r.auto_installable),
            },
            "resolved": [r.to_dict() for r in self.resolved],
            "unresolved": [r.to_dict() for r in self.unresolved],
        }


# ---------------------------------------------------------------------------
# Registry HTTP (isolated; injectable for tests)
# ---------------------------------------------------------------------------

def _registry_get(path: str, params: dict[str, Any] | None = None, *, timeout: float = 20.0) -> Any:
    url = REGISTRY_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "SpellVision-NodeResolver/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def registry_has_class(class_name: str, *, getter: Callable[..., Any] = _registry_get, timeout: float = 20.0) -> bool:
    """EXISTENCE: does any pack version in the Registry provide this class? Cheap (one GET)."""
    data = getter("/comfy-nodes", {"comfy_node_name": class_name, "limit": 1}, timeout=timeout)
    return bool(isinstance(data, dict) and (data.get("total") or 0) > 0)


# ---------------------------------------------------------------------------
# Reverse index (class -> pack) — the only way to map a bare class name to a pack.
# Built from the Registry itself (non-GPL). Cacheable; reused by later passes.
# ---------------------------------------------------------------------------

def _pack_score(meta: dict[str, Any]) -> tuple[int, int]:
    """Rank competing providers of the same class: prefer more-downloaded, then more-starred."""
    return (int(meta.get("downloads") or 0), int(meta.get("github_stars") or 0))


def _fetch_pack_classes(
    getter: Callable[..., Any], pid: str, latest_ver: str | None, *, timeout: float, max_fallback: int = 8
) -> tuple[str | None, list[str]]:
    """Return (version, [class names]) for a pack. The Registry's node extraction on a pack's LATEST
    version is frequently EMPTY (extraction lags a fresh publish — e.g. comfyui-easy-use latest had 0
    classes while the prior version had 200). So if the latest version yields no classes, walk newest->
    older versions until one has a non-empty node list. Returns the latest version with an empty list
    only when no version has classes."""
    def classes_of(ver: str | None) -> list[str]:
        if not ver:
            return []
        try:
            cn = getter(f"/nodes/{urllib.parse.quote(pid)}/versions/{urllib.parse.quote(str(ver))}/comfy-nodes",
                        {"limit": 1000}, timeout=timeout)
        except Exception:
            return []
        return [e.get("comfy_node_name") for e in ((cn.get("comfy_nodes") or []) if isinstance(cn, dict) else []) if e.get("comfy_node_name")]

    cls = classes_of(latest_ver)
    if cls:
        return latest_ver, cls
    try:
        vlist = getter(f"/nodes/{urllib.parse.quote(pid)}/versions", timeout=timeout)
    except Exception:
        return latest_ver, []
    versions = [v.get("version") for v in vlist if isinstance(v, dict)] if isinstance(vlist, list) else []
    for ver in versions[:max_fallback]:
        if ver == latest_ver:
            continue
        cls = classes_of(ver)
        if cls:
            return ver, cls
    return latest_ver, []


def build_class_pack_index(
    *,
    getter: Callable[..., Any] = _registry_get,
    timeout: float = 20.0,
    progress: Callable[[str], None] | None = None,
    delay: float = 0.0,
    max_packs: int | None = None,
) -> dict[str, Any]:
    """Enumerate every Registry pack and its latest version's node classes, producing a
    ``{class_name: entry}`` index plus the pack metadata. This is the class->pack map the Registry
    does not expose directly. Expensive (one call per pack); intended to be cached to disk.

    Returns ``{"classes": {class: {pack_id, version, repo_url, license, py_deps, downloads, stars}},
               "packs_seen": N, "classes_indexed": M, "errors": [...]}``.
    """
    import time as _time

    def log(msg: str) -> None:
        if progress:
            progress(msg)

    # 1) page all packs (id, license, repo, latest_version, downloads, stars)
    packs: dict[str, dict[str, Any]] = {}
    page = 1
    while True:
        data = getter("/nodes", {"page": page, "limit": 100}, timeout=timeout)
        nodes = data.get("nodes") if isinstance(data, dict) else None
        for p in nodes or []:
            pid = p.get("id")
            if not pid:
                continue
            lv = p.get("latest_version") if isinstance(p.get("latest_version"), dict) else {}
            packs[pid] = {
                "license": p.get("license"),
                "repo_url": p.get("repository"),
                "version": lv.get("version"),
                "py_deps": lv.get("dependencies") or [],
                "downloads": p.get("downloads") or 0,
                "github_stars": p.get("github_stars") or 0,
            }
        total_pages = int(data.get("totalPages") or 1) if isinstance(data, dict) else 1
        log(f"listed packs page {page}/{total_pages} ({len(packs)} so far)")
        if page >= total_pages:
            break
        page += 1
        if delay:
            _time.sleep(delay)

    # 2) for each pack, fetch its latest version's node classes
    index: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    pack_ids = list(packs.keys())[: max_packs or len(packs)]
    for i, pid in enumerate(pack_ids):
        meta = packs[pid]
        ver = meta.get("version")
        try:
            if not ver:  # some list entries lack latest_version inline; fetch the pack
                detail = getter(f"/nodes/{urllib.parse.quote(pid)}", timeout=timeout)
                ver = (detail.get("latest_version") or {}).get("version") if isinstance(detail, dict) else None
                if isinstance(detail, dict):
                    meta.setdefault("license", detail.get("license"))
                    meta.setdefault("repo_url", detail.get("repository"))
            ver, classes = _fetch_pack_classes(getter, pid, ver, timeout=timeout)
        except Exception as exc:
            errors.append(f"{pid}: {type(exc).__name__}: {exc}")
            continue
        entry = {
            "pack_id": pid,
            "version": str(ver),
            "repo_url": meta.get("repo_url"),
            "license": meta.get("license"),
            "py_deps": [str(d) for d in (meta.get("py_deps") or []) if isinstance(d, str)],
            "downloads": meta.get("downloads") or 0,
            "github_stars": meta.get("github_stars") or 0,
        }
        for cls in classes:
            if not cls:
                continue
            prev = index.get(cls)
            if prev is None or _pack_score(entry) > _pack_score(prev):
                index[cls] = entry
        if (i + 1) % 250 == 0:
            log(f"indexed {i + 1}/{len(pack_ids)} packs, {len(index)} classes")
        if delay:
            _time.sleep(delay)

    log(f"done: {len(pack_ids)} packs, {len(index)} classes, {len(errors)} pack errors")
    return {"classes": index, "packs_seen": len(pack_ids), "classes_indexed": len(index), "errors": errors}


# ---------------------------------------------------------------------------
# Resolution — PURE lookup over the prebuilt index (no network, fully testable)
# ---------------------------------------------------------------------------

def resolve_missing_nodes(class_names: list[str], *, index: dict[str, Any]) -> ResolutionReport:
    """Resolve missing node class names against a prebuilt class->pack index (from
    ``build_class_pack_index``). RESOLVED when the class is in the index; UNRESOLVED otherwise
    (not in Registry). No Manager fallback. Pure — the network already happened in the index build.

    `index` is the dict returned by build_class_pack_index (it reads index["classes"]).
    """
    classes = index.get("classes", index) if isinstance(index, dict) else {}
    report = ResolutionReport()
    seen: set[str] = set()
    for cn in class_names:
        if cn in seen:
            continue
        seen.add(cn)
        entry = classes.get(cn)
        if not entry:
            report.unresolved.append(Resolution(class_name=cn, status="UNRESOLVED", reason="no Registry pack provides this class"))
            continue
        lic = _normalize_license(entry.get("license"))
        report.resolved.append(Resolution(
            class_name=cn,
            status="RESOLVED",
            pack_id=entry.get("pack_id"),
            version=entry.get("version"),
            repo_url=entry.get("repo_url"),
            license=lic,
            py_deps=list(entry.get("py_deps") or []),
            auto_installable=is_auto_installable(lic),
            reason="class in Registry pack node set",
        ))
    return report
