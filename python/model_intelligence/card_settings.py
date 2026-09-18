"""When a weight's settings must come from a HuggingFace card, and how they are fetched.

`refresh._hf` already asks HuggingFace about a weight CivitAI does not know, and its docstring is
right about IDENTITY: a CivitAI hit is already an identity, so asking the other site again would
spend up to 25 requests per weight for nothing. It is wrong about SETTINGS, and the measurement is
unambiguous. Over the owner's 759 sidecars, 2026-09-18:

    family            models   with a publisher-stated setting
    sdxl                 287   269
    illustrious           80    69
    pony                  52    48
    wan                   64    26
    ltx                   21     0
    hunyuan_video          7     0
    mochi                  2     0

Every video family fell back entirely to `family_seed_table` -- the floor the whole model-defaults
arc exists to replace -- and not because the supply is missing. `settings_from_readme` on
`Lightricks/LTX-2.3` returns `steps 8 / cfg 1` at `card:prose-regex`, which agrees with the
distilled two-stage route CLAUDE.md S6 records. The reason those 21 LTX weights carried nothing is
structural: CivitAI HAS the files, so the second arm was never reached, and CivitAI's
`images[].meta` yields no sampler settings for a video post.

So the rule this module owns is: **a CivitAI hit ends the search for identity, not for settings.**
A weight whose `recommended` block carries no `site:*` entry at all has been identified and told us
nothing, and its card is worth reading.

**This cannot corrupt a good answer, and the reason is structural rather than a new rule.**
`recommended.PROVENANCE_ORDER` already ranks every `card:*` tier BELOW `site:image-meta-mode` and
`site:trainedWords`, and `recommended._offer` only replaces an entry a candidate outranks. So a card
value can only ever fill a field the site left empty. `needs_card_settings` is therefore a COST
control, not a safety one -- the safety is the order, and `tests/test_model_intelligence_card_
settings.py` asserts it directly rather than trusting the table.

Cost, in the order the brief asked for it:

  * only a weight with no `site:*` value at all is asked about
  * `hf_candidates.RepoIndex` is shared across the whole pass, so one confirmed repo serves every
    other weight in it for free -- LTX is 21 files that cost one confirmation
  * READMEs are memoised per repo here, because 21 files in one repo is otherwise 21 identical
    fetches of the same 40 KB of markdown
  * `HfThrottled` propagates. It exists because a 429 was once read as "not on HuggingFace" and
    cost 13 identifications while reporting zero errors.
"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any, Iterable

from model_intelligence import hf_candidates, hf_lookup

# How many FURTHER repos holding the same bytes may be tried when the confirmed one's card states
# nothing. See `CardReader._mirror_with_a_card` for the measurement that put this here.
MAX_MIRROR_REPOS = 6

# What a CARD is able to state about a weight. Sampling, never a canvas.
#
# `hf_lookup._SNIPPET_KEYS` carries the write-side reason (a diffusers snippet's `height=512` is
# template boilerplate, not a statement about this weight, and every canvas value the route produced
# over the live library was wrong). This is the same fact expressed where a READER can use it:
# `settings_backfill.apply_to_payload` prunes a card-provenanced entry for any field outside this
# set, so a sidecar written by the version that could claim a canvas stops displaying one without a
# schema bump and without anyone re-running a refresh.
#
# The same shape as `resolve._apply_quorum`: a gate the writer applies is ALSO applied on the read,
# from the evidence the entry carries about itself, so a file written by any version resolves the
# same way.
CARD_STATABLE_FIELDS: frozenset[str] = frozenset({"steps", "cfg", "guidance", "shift"})


def has_site_settings(block: dict[str, Any] | None) -> bool:
    """Whether a `recommended` block carries anything the SITE said about this weight.

    Read off the provenance strings rather than off a field list, so it cannot drift from
    `recommended.PROVENANCE_ORDER`. `site:image-meta-weak` counts: it is one real example of this
    model, which is thin evidence and still evidence -- a weight that has it is not the silent case
    this module exists for.
    """
    for entry in (block or {}).values():
        if isinstance(entry, dict) and str(entry.get("provenance") or "").startswith("site:"):
            return True
    return False


def needs_card_settings(block: dict[str, Any] | None) -> bool:
    return not has_site_settings(block)


class CardReader:
    """Confirm a weight's repo by sha256 and read the settings its card states.

    Holds the shared `RepoIndex` and the per-repo README cache for one pass. Both refresh and the
    sidecar backfill drive it, so "which weights get asked" and "how they are asked" are one rule
    in one place rather than two implementations that agree today.
    """

    def __init__(self, client: Any, index: hf_candidates.RepoIndex | None = None) -> None:
        self.client = client
        self.index = index if index is not None else hf_candidates.RepoIndex(client)
        self._readmes: dict[str, str] = {}
        self.repos_confirmed = 0
        self.readmes_read = 0
        # How often the settings came from a MIRROR rather than the repo that
        # confirmed the bytes -- reported so a pass says which mechanism did the work.
        self.mirrors_used = 0

    def readme(self, repo: str) -> str:
        name = str(repo or "")
        if name not in self._readmes:
            self._readmes[name] = str(self.client.readme(name) or "")
            self.readmes_read += 1
        return self._readmes[name]

    def _card_for(self, repo: str, rfilename: str) -> dict[str, Any]:
        card = dict(hf_lookup.card_identity(self.index.info.get(repo)))
        card.update({"repo": repo, "path": rfilename})
        return card

    def _mirror_with_a_card(self, candidates: Iterable[str], digest: str, confirmed: str
                            ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]] | None:
        """Another repo holding the SAME bytes whose card actually states settings.

        MEASURED 2026-09-18, and it is the whole reason the first live pass moved 1 of 21 LTX
        weights. `Lightricks/LTX-2.3`'s card really does yield `steps 8 / cfg 1` -- verified
        anonymously against the live API. But the owner's `ltx-2.3-22b-dev.safetensors` confirms
        `asheng386/LTX-2.3` for one copy and `darksidewalker/DaSiWa-LTX2.3` for another, because
        `identify` accepts the FIRST candidate whose sha256 matches and the free-text search ranks
        re-uploads ahead of the publisher. The hash match is perfectly correct -- a mirror holds
        identical bytes -- and the card beside it is a stub. (The same shape as Doc 62 3l one layer
        out: a correct match to the wrong SOURCE for the question being asked.)

        So a repo whose card says nothing is not the end of the search. Identity is already settled
        by then, which is what makes continuing safe: every repo tried here must ALSO hold the
        digest, so the worst case is a different mirror of the same bytes.

        Bounded at `MAX_MIRROR_REPOS` because each extra candidate is one `model_info` request and
        HuggingFace's anonymous limit is what a library pass runs into first -- 48 of 172 weights
        were throttled on the second live pass even at two seconds a weight.

        `candidates` is the `tee`d branch of the candidate generator `read` already started, handed
        in rather than re-derived: calling `candidate_repos` again re-issues up to 22 SEARCHES for a
        weight that has already been searched for, which is the expensive half of the request budget
        and the half the rate limit actually bites on. It replays what the confirm pass pulled and
        only then advances the generator further.
        """
        tried = 0
        for repo in candidates:
            if repo == confirmed:
                continue
            if tried >= MAX_MIRROR_REPOS:
                return None
            tried += 1
            index = self.index.add(repo)
            if digest not in index:
                continue
            settings = hf_lookup.settings_from_readme(self.readme(repo))
            if settings:
                return self._card_for(repo, index[digest]), settings
        return None

    def read(self, *, weight: str | Path, sha256: str) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]] | None]:
        """(card, settings) for one weight, or (None, None) when no repo confirms its bytes.

        Raises nothing but `HfThrottled`, which the caller must record as an error rather than as
        "this weight is not on HuggingFace" -- the distinction `HfThrottled` was created for.
        """
        if self.client is None or not sha256:
            return None, None
        digest = str(sha256).strip().lower()
        # ONE search pass for this weight, shared by the confirm loop and the mirror walk below.
        #
        # `tee`, not `list`: `candidate_repos` is a GENERATOR that issues a search only when the
        # consumer asks for more, and `identify` stops at the first repo whose sha256 matches -- so
        # materialising the list would run all 22 searches for every weight, including the common
        # case that matches on the first candidate. `tee` keeps that laziness and lets the mirror
        # walk replay what the confirm loop already pulled without re-asking for it.
        confirm_pass, mirror_pass = itertools.tee(
            hf_candidates.candidate_repos(self.client, weight))
        found = hf_candidates.identify(self.client, weight=weight, sha256=digest, index=self.index,
                                       candidates=confirm_pass)
        if not found:
            return None, None
        self.repos_confirmed += 1
        card = self._card_for(found["repo"], found["path"])
        settings = hf_lookup.settings_from_readme(self.readme(found["repo"]))
        if settings:
            return card, settings
        mirror = self._mirror_with_a_card(mirror_pass, digest, found["repo"])
        if mirror:
            self.mirrors_used += 1
            return mirror
        return card, settings
