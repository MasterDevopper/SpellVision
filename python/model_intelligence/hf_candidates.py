"""Which HuggingFace repo might this weight be in -- the step that was missing.

`hf_lookup` could read a repo since the day it was written and nothing called it, because HF has
**no by-hash endpoint** (verified 2026-09-16, re-verified 2026-09-17). A weight can only be
identified there if a repo is already suspected; `?blobs=true` then supplies
`siblings[].lfs.sha256`, which CONFIRMS the guess exactly. That confirmation is what makes guessing
safe: a wrong candidate cannot mislabel anything, it simply fails to match. (Doc 62 3l is the
opposite case -- a genuine CivitAI hash match to a BUNDLE, where the name belongs to the upload
rather than the file. Nothing here can produce that, because the sibling's own `rfilename` is
recorded alongside the repo.)

Measured over the 79 weights the 2026-09-17 refresh could not identify, anonymously:

  * filename/folder search alone confirmed **21 of 79 (26.6%)**
  * adding an author-scoped search over the handful of packagers that republish ComfyUI weights
    caught files whose repo shares no token with them at all --
    `hunyuan_video_t2v_720p_bf16` lives in `Comfy-Org/HunyuanVideo_repackaged`
  * and the cheapest win is structural: once ANY weight confirms a repo, every other weight in the
    library can be matched against that repo's index for free. `llava_llama3_vision` is in the
    same Comfy-Org repo as the Hunyuan transformer and shares no search term with it.

The remaining misses are overwhelmingly weights HF does not host: the owner's own fused LoRAs, and
CivitAI LoRAs whose uploader never mirrored them. That is a real answer, not a failure.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from model_intelligence import hf_lookup

# The accounts that republish ComfyUI-shaped weights under names sharing no token with the file.
# A list, not a heuristic: each is an author whose repos actually hold weights in this library.
PACKAGERS = ("Comfy-Org", "Kijai", "city96", "QuantStack", "calcuis", "lightx2v", "Lightricks")

MAX_REPOS_PER_WEIGHT = 25
_SPLIT = re.compile(r"[ _\-.]+")
_NOISE = {"models", "checkpoints", "loras", "lora", "diffusion", "diffusion_models", "vae",
          "clip", "clip_vision", "text_encoders", "upscale", "upscale_models", "ipadapter",
          "embeddings", "llm", "unet", "controlnet", "ai_assets"}


def search_queries(weight: str | Path) -> list[str]:
    """Free-text queries for one weight, most specific first.

    The full stem first (an exact repo name is common for a single-file upload), then the stem as
    words, then shortening prefixes, then the folder it sits in. Shortening matters: a query of
    `ltx 2` is what found `Lightricks/LTX-2.3`, which the full stem never would.
    """
    path = Path(str(weight))
    out: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(cleaned) >= 3 and cleaned.lower() not in seen and cleaned.lower() not in _NOISE:
            seen.add(cleaned.lower())
            out.append(cleaned)

    stem = path.stem
    add(stem)
    tokens = [t for t in _SPLIT.split(stem) if t]
    add(" ".join(tokens))
    for count in (4, 3, 2):
        if len(tokens) > count:
            add(" ".join(tokens[:count]))
    add(path.parent.name)
    return out


def direct_repo(weight: str | Path) -> str | None:
    """`<org>/<repo>/<file>` on disk names its own repo -- an `hf download` lands exactly that way.

    Free to try and exact when it is right: `facebook/dinov3-vitl16-pretrain-lvd1689m/model.safetensors`
    is the one shape where a weight called `model.safetensors` is identifiable at all.
    """
    parts = Path(str(weight)).parts
    if len(parts) < 3:
        return None
    org, repo = parts[-3], parts[-2]
    if org.lower() in _NOISE or repo.lower() in _NOISE or not org or not repo:
        return None
    return f"{org}/{repo}"


class RepoIndex:
    """Every repo looked at in this run, by sha256, so one confirmation serves the whole library.

    The cache is the point, not an optimisation: a repackaged bundle holds a transformer, a VAE and
    a text encoder that share no searchable name, and confirming one of them hands us the other
    two for nothing. It also keeps a MISS cached, so a repo that answered 404 is asked once.
    """

    def __init__(self, client: Any) -> None:
        self.client = client
        self.repos: dict[str, dict[str, str]] = {}
        self.info: dict[str, dict[str, Any] | None] = {}
        self.by_digest: dict[str, tuple[str, str]] = {}

    def add(self, repo: str) -> dict[str, str]:
        name = str(repo or "").strip().strip("/")
        if name in self.repos:
            return self.repos[name]
        try:
            info = self.client.model_info(name)
        except hf_lookup.HfThrottled:
            raise  # see `_search`: a throttle must never read as "this repo does not have it"
        except Exception:  # noqa: BLE001 -- one candidate, never the run
            info = None
        self.info[name] = info
        index = hf_lookup.sha256_index(info)
        self.repos[name] = index
        for digest, rfilename in index.items():
            self.by_digest.setdefault(digest, (name, rfilename))
        return index

    def lookup(self, sha256_hex: str) -> tuple[str, str] | None:
        return self.by_digest.get(str(sha256_hex or "").lower())


def _search(client: Any, query: str, author: str | None = None) -> list[str]:
    try:
        return client.search(query, author=author)
    except hf_lookup.HfThrottled:
        # A throttle is NOT an answer. Swallowing it here returns zero candidates, which the
        # caller cannot tell from "HF does not have this weight" -- measured, that silently cost
        # 13 of 38 identifications in one pass and reported no error at all.
        raise
    except Exception:  # noqa: BLE001 -- a failed search is zero candidates, not a failed run
        return []


def candidate_repos(client: Any, weight: str | Path) -> Iterable[str]:
    """Repo ids to try for this weight, most likely first, without repeating one."""
    seen: set[str] = set()

    def offer(repo: str) -> Iterable[str]:
        name = str(repo or "").strip().strip("/")
        if name and "/" in name and name not in seen:
            seen.add(name)
            yield name

    direct = direct_repo(weight)
    if direct:
        yield from offer(direct)

    queries = search_queries(weight)
    for query in queries:
        for repo in _search(client, query):
            yield from offer(repo)

    # The author-scoped pass runs LAST and only on the shortest query forms: it exists for the
    # files whose repo name shares nothing with them, and a long query never matches those.
    for query in queries[-3:]:
        for author in PACKAGERS:
            for repo in _search(client, query, author=author):
                yield from offer(repo)


def identify(client: Any, *, weight: str | Path, sha256: str, index: RepoIndex | None = None,
             max_repos: int = MAX_REPOS_PER_WEIGHT) -> dict[str, Any] | None:
    """The repo and path this weight's bytes are in, confirmed by sha256, or None.

    `index` is shared across a run so a repo is fetched once and a confirmed repo identifies the
    rest of its own bundle without a search at all -- which is why the cache is checked FIRST.
    """
    digest = str(sha256 or "").strip().lower()
    if len(digest) != 64:
        return None
    index = index if index is not None else RepoIndex(client)

    found = index.lookup(digest)
    if found:
        return {"repo": found[0], "path": found[1], "via": "cache"}

    tried = 0
    for repo in candidate_repos(client, weight):
        if tried >= max_repos:
            break
        tried += 1
        if digest in index.add(repo):
            return {"repo": repo, "path": index.repos[repo][digest], "via": "search"}
    return None
