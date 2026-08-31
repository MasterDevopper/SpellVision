"""Turning a reference into a file on disk: Hugging Face, Civitai, or a local path.

Parses the reference (``parse_asset_reference``), enumerates what is actually on offer
(``model_variants``), and materialises the chosen one (``materialize_asset``).

The hard-won part is that **a filename is not an identity**. One Civitai version ships the same
checkpoint at several precisions under a single name -- ``file_id`` is the key, and ``metadata.fp``
carries the precision. A version also bundles its text encoder, VAE and workflow JSON alongside the
weights, so "the biggest file" and "the primary file" are both wrong selectors:
``precision_variants()`` are the files sharing the PRIMARY file's name and ``companion_files()``
are the rest. Without that split a naive "highest precision that fits" recommended a 0.24 GB VAE as
the model.

The second hard-won part is that **``metadata.fp`` is a field an uploader types, and it is wrong
often enough to matter**. Ranking on it recommended an int8 checkpoint as "the highest precision
available"; ranking on SIZE cannot go wrong the same way, because within one model more bytes is
more precision. ``precision_disputes`` reports the contradiction where it is measurable -- inside a
version, between files sharing one filename -- and stays silent across versions, where a size ratio
measures the architecture rather than the precision (measured: 11% false-positive rate across
versions against 0.27% within one, over the 100 most-downloaded Civitai checkpoints).

``recommend_file`` and ``recommend_across_variants`` therefore only ever RECOMMEND. Doc 19's rule
holds throughout this module: never auto-download on a guess, and never silently substitute --
ambiguity raises ``AmbiguousCivitaiModel`` so the caller can present the choice, and a disputed row
is marked rather than hidden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Sequence,
)
import hashlib
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
_PRECISION_RANK = {"nvfp4": 0, "nf4": 0, "fp4": 0, "int4": 0,
                   "int8": 1, "fp8": 2, "mxfp8": 2, "fp8_scaled": 3,
                   "fp16": 4, "bf16": 5}

# The same tokens folded to a bit-width class, for checking a DECLARED precision against a MEASURED
# one -- there the exact token matters less than the class it claims membership of.
# ``nf4`` is present because that is the string the live API returns for the nvfp4 file of model
# 2726029; the rank table above knew only ``nvfp4`` and scored the real row -1.
_PRECISION_BITS = {
    # fp32 is 32, not "the top class". Folding it into 16 made every honest fp16-alongside-fp32
    # pair look like a mislabel: the fp16 is half the fp32's size, so anchored on a 16-bit fp32 it
    # measured 8-bit. That was 2 of the 5 flags in the corpus sweep, on SD1.5 checkpoints where
    # 3.97 GB fp32 + 1.99 GB fp16 is the normal shipping pair.
    "fp32": 32, "float32": 32,
    "bf16": 16, "fp16": 16, "float16": 16,
    "fp8": 8, "fp8_scaled": 8, "mxfp8": 8, "int8": 8, "q8": 8,
    "nvfp4": 4, "nf4": 4, "fp4": 4, "int4": 4,
}
# Bit-widths a checkpoint is actually published at. Anything landing between them is a measurement
# error, not a new precision.
_BIT_CLASSES = (4, 8, 16, 32)

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
    # hashes.SHA256, lowercased. The only signal in the whole payload that identifies the BYTES
    # rather than describing them: name, size and precision are all things a page can get wrong,
    # and two of the three have been observed wrong. Present on every file measured. Empty when the
    # provider omits it, which is a real state -- it means the download cannot be verified, not
    # that it is fine.
    sha256: str = ""

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


def _fitting(files: Sequence[CivitaiFile], vram_gb: float | None) -> list[CivitaiFile]:
    """The weight files that fit the card, or the single smallest when none of them do.

    The ONE place that decides what "fits". A checkpoint needs headroom beyond its own size for
    activations and the VAE decode, so the budget is 80% of reported VRAM rather than all of it.

    Nothing fitting is a real answer with a real response -- offer the smallest and let the caller
    say why -- rather than an empty list the callers would each have to remember to handle.
    """
    weights = [f for f in files if f.is_weights]
    if not weights:
        return []
    if not vram_gb or vram_gb <= 0:
        return weights
    budget = vram_gb * 0.8
    fits = [f for f in weights if f.size_gb and f.size_gb <= budget]
    return fits or [min(weights, key=lambda f: f.size_kb or float("inf"))]


def _precisions_of(files: Sequence[CivitaiFile]) -> list[CivitaiFile]:
    """Narrow a raw file list to the precisions of ONE checkpoint -- what a user chooses between.

    The same rule ``CivitaiVariant.precision_variants`` applies: Civitai reuses one filename across
    precisions inside a version, while the companions bundled alongside (a ``_txt`` text encoder,
    ``qwen_image_vae.safetensors``, the workflow ``.json``) carry distinct names.

    Applied here for callers holding a raw list. It must be applied exactly ONCE, and at this
    level: ``recommend_across_variants`` works on a pool where each version has already been
    narrowed, and narrowing again across versions would collapse a legitimate cross-version
    candidate set -- six differently-named files that ARE the choice -- down to one.
    """
    weights = [f for f in files if f.is_weights]
    if len(weights) < 2:
        return weights
    primary = next((f for f in weights if f.primary), weights[0])
    target = primary.name.strip().lower()
    same = [f for f in weights if f.name.strip().lower() == target]
    return same if len(same) > 1 else weights


def recommend_file(files: Sequence[CivitaiFile], vram_gb: float | None = None) -> CivitaiFile | None:
    """The precision to SUGGEST out of one set of candidates. Never the one to take automatically.

    The owner's decision is "always ask, recommend one", so this MARKS a row -- it does not choose.

    Ranks by **size**, not by the declared precision, because the declared precision is a field that
    lies. Measured live against Civitai model 2726029 ("Krea 2 Turbo Official Comfy-Org
    Checkpoints"): the version ``krea2_turbo_int8_convrot`` reports ``metadata.fp = "bf16"`` at
    12.57 GB, while the genuine bf16 in the same model is 24.48 GB. Believing that label promoted an
    int8 checkpoint to "the highest precision available" and recommended it on every card.

    Size cannot lie the same way. Within one model the candidates are the same weights at different
    precisions, so more bytes is more precision. ``_PRECISION_RANK`` breaks a size tie and does
    nothing else.

    Ranking by size also kills the older failure structurally instead of by a guard: a bundled
    0.24 GB VAE is the SMALLEST file present, so a largest-that-fits rule can never surface it as
    the model. The previous version defended against that by narrowing to the primary file's name,
    which silently collapsed a cross-version candidate set to a single file and then returned it at
    every VRAM budget -- 12 GB and 32 GB got the same answer, and the fitting logic never ran.

    For a whole model use ``recommend_across_variants``, which adds the version axis. This is the
    single-version primitive: it narrows to one checkpoint's precisions (``_precisions_of``) and
    then takes the largest that fits (``_fitting``, shared with the model-wide path so "fits" is
    decided in one place).
    """
    candidates = _fitting(_precisions_of(files), vram_gb)
    if not candidates:
        return None
    return max(candidates, key=lambda f: (f.size_kb or 0.0,
                                          _PRECISION_RANK.get(f.precision.lower(), -1)))


def precision_candidates(
    variants: Sequence["CivitaiVariant"],
) -> list[tuple["CivitaiVariant", CivitaiFile]]:
    """Every precision of the checkpoint across the WHOLE model, each paired with its version.

    Civitai splits the precision axis two different ways and a chooser has to handle both.
    "Lox's Utopic World | Krea 2" (model 2823011) ships bf16, fp8, int8 and nvfp4 as separate FILES
    inside a version; "Krea 2 Turbo Official Comfy-Org Checkpoints" (2726029) gives each precision
    its own VERSION -- six of them, one file each. A recommendation computed per version marks every
    row on the second shape (measured: 6 of 6), which is a recommendation carrying no information.
    """
    return [(variant, file) for variant in variants for file in variant.precision_variants()]


def _snap_bits(value: float) -> int | None:
    """The published bit-width a measurement lands on, or None when it lands on none of them.

    The tolerance is deliberately loose (35%): a quantised checkpoint keeps some layers unquantised
    and adds scale tensors, so an 8-bit file is never exactly half a 16-bit one. Loose enough to
    accept real files, tight enough that a 2x error cannot pass as the next class down.
    """
    if value <= 0:
        return None
    best = min(_BIT_CLASSES, key=lambda bits: abs(value - bits) / bits)
    return best if abs(value - best) / best <= 0.35 else None


def measured_bit_classes(files: Sequence[CivitaiFile]) -> dict[str, int]:
    """Bit-width MEASURED from each file's size, keyed by file id. ``{}`` when unmeasurable.

    **Only valid on files already established to be the same weights** -- i.e. the output of
    ``CivitaiVariant.precision_variants()``, which are the files sharing one filename inside one
    version. There the ratio argument holds: 16-bit is about twice 8-bit, which is about twice
    4-bit, so a SIZE converts to a bit-width, and a bit-width is the thing an uploader cannot
    mistype.

    It does NOT hold across a model's versions, and assuming it did was wrong in a way worth
    recording. Measured over the 100 most-downloaded Civitai checkpoints: run across versions this
    flagged **121 of 1101 candidates, 11%** -- almost none of them mislabels. A model's versions
    routinely span different architectures and parameter counts (Pony Diffusion V6 XL carries a
    1.99 GB file and a 6.46 GB file, both honestly fp16), so a size ratio between them measures the
    architecture, not the precision. Restricted to one version's shared-name files the same code
    flags essentially nothing, because there the comparison is between two encodings of one
    artifact.

    The anchor cannot simply be the largest file, because the largest may be the mislabelled one.
    Every file carrying a declared precision is tried as the anchor and scored by how many others it
    explains; the best-scoring anchor wins and must explain a strict majority. A set that disagrees
    with itself yields ``{}`` rather than a guess.
    """
    sized = [f for f in files if (f.size_kb or 0) > 0]
    if len(sized) < 2:
        return {}

    anchors = [f for f in sized if f.precision.strip().lower() in _PRECISION_BITS]
    if not anchors:
        return {}

    def measured_under(anchor: CivitaiFile) -> dict[str, int | None]:
        anchor_bits = _PRECISION_BITS[anchor.precision.strip().lower()]
        anchor_size = anchor.size_kb or 0.0
        return {
            file.file_id: _snap_bits(anchor_bits * (file.size_kb or 0.0) / anchor_size)
            for file in sized
        }

    def agreement(anchor: CivitaiFile) -> int:
        measured = measured_under(anchor)
        return sum(
            1 for file in sized
            if measured.get(file.file_id) == _PRECISION_BITS.get(file.precision.strip().lower())
        )

    best = max(anchors, key=agreement)
    if agreement(best) * 2 <= len(sized):
        # No reading of the set explains most of it. Returning a class here would mean picking a
        # winner among mutually inconsistent metadata -- a guess wearing a verdict's clothes.
        return {}
    return {fid: bits for fid, bits in measured_under(best).items() if bits}


def precision_disputes(variants: Sequence["CivitaiVariant"]) -> dict[str, str]:
    """File ids whose declared precision contradicts their measured size, and why.

    Computed **per version**, over the files that share one filename there -- the only place the
    comparison means anything (see ``measured_bit_classes``). A dispute is therefore always
    "these two encodings of the same checkpoint cannot both be what they say they are".

    A disputed row is still offered, because it may be exactly the file the user wants. Marked,
    never hidden -- and never the recommendation.

    Silent by design when it cannot tell: a version with one file has nothing to compare against,
    which is common, and staying silent there is the honest answer rather than a weaker check.
    """
    out: dict[str, str] = {}
    for variant in variants:
        candidates = variant.precision_variants()
        measured = measured_bit_classes(candidates)
        if not measured:
            continue
        by_id = {file.file_id: file for file in candidates}
        for file_id, found in measured.items():
            file = by_id.get(file_id)
            if file is None:
                continue
            claimed = _PRECISION_BITS.get(file.precision.strip().lower())
            if claimed and claimed != found:
                out[file_id] = (
                    f"declared {file.precision} ({claimed}-bit) but at {file.size_gb:.2f} GB it "
                    f"measures {found}-bit against the other precisions of this same file"
                )
    return out


# Two candidates whose sizes are within this of each other are the same choice as far as a
# recommendation is concerned, so something else should break the tie. Measured need: model 2823011
# offers V1.0's 12.57 GB int8 and V2.0's 12.25 GB int8, 2.6% apart -- ranking on size alone spent
# that 0.32 GB on an older model.
_SIZE_TIE_BAND = 0.05


def recommend_across_variants(
    variants: Sequence["CivitaiVariant"],
    vram_gb: float | None = None,
) -> tuple[str, str] | None:
    """``(version_id, file_id)`` of the ONE row to mark for the whole model, or None.

    Model-wide rather than per-version, because the precision axis is sometimes the version axis.
    Computed per version the mark landed on every row of model 2726029 -- six of six, a star that
    says nothing while looking like guidance.

    Ranked in this order:

    1. **it has to fit** -- ``_fitting``, the same rule ``recommend_file`` uses, so "fits" is
       decided in one place;
    2. **the largest**, because within a model more bytes is more precision and, unlike
       ``metadata.fp``, the size is not a field anyone types;
    3. **the version the author put first**, among candidates within ``_SIZE_TIE_BAND`` of the
       largest. Civitai returns ``modelVersions`` in the author's order and the dialog lists them
       that way, so the first is the one being presented as current -- for model 2823011 that is
       V2.0 ahead of V1.0. Note this is the author's ORDERING, not an inference from version ids,
       which are not monotonic on either model measured.

    A row whose precision is disputed is excluded from the recommendation but stays in the list;
    hiding it would be the silent substitution this module exists to prevent.
    """
    pairs = precision_candidates(variants)
    if not pairs:
        return None

    disputed = precision_disputes(variants)
    pool = [(v, f) for v, f in pairs if f.file_id not in disputed] or list(pairs)

    fits = {f.file_id for f in _fitting([f for _, f in pool], vram_gb)}
    pool = [(v, f) for v, f in pool if f.file_id in fits] or pool

    largest = max((f.size_kb or 0.0) for _, f in pool)
    band = largest * (1.0 - _SIZE_TIE_BAND)
    tied = [(v, f) for v, f in pool if (f.size_kb or 0.0) >= band] or pool

    order = {variant.version_id: index for index, variant in enumerate(variants)}
    variant, file = min(
        tied,
        key=lambda pair: (order.get(pair[0].version_id, len(order)), -(pair[1].size_kb or 0.0)),
    )
    return (variant.version_id, file.file_id)


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
            hashes = entry.get("hashes") if isinstance(entry.get("hashes"), dict) else {}
            parsed.append(CivitaiFile(
                file_id=str(entry.get("id") or ""),
                name=str(entry.get("name") or ""),
                size_kb=_as_float(entry.get("sizeKB")),
                precision=str(metadata.get("fp") or "").strip(),
                file_format=str(metadata.get("format") or "").strip(),
                primary=bool(entry.get("primary")),
                download_url=str(entry.get("downloadUrl") or ""),
                sha256=str(hashes.get("SHA256") or "").strip().lower(),
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

    # The provider's digest for the exact file being fetched, when it published one. Hashed as the
    # bytes arrive rather than by re-reading afterwards: these files reach 24 GB, and a second full
    # read to verify would roughly double the wall-clock cost of every download.
    declared_sha256 = str(metadata.get("sha256") or "").strip().lower()

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
            digest = hashlib.sha256() if declared_sha256 else None
            while True:
                if cancel_cb is not None and cancel_cb():
                    raise DownloadCancelled(f"Download cancelled: {file_name}")
                chunk = resp.read(DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise RuntimeError(f"Model download exceeded configured byte limit ({max_bytes}).")
                if digest is not None:
                    digest.update(chunk)
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
            # Identity, not plausibility. The size checks above pass for ANY file of about the right
            # length, and the whole failure mode this module is shaped around is receiving a
            # different artifact than the one that was chosen -- a name collision, a redirect to
            # another uploader's file, a page whose metadata points at a different model. The digest
            # is the one field that describes the bytes rather than the listing.
            #
            # Raised, not warned: the partial file is discarded by the handler below, so a mismatch
            # leaves nothing behind for a later run to treat as a cache hit.
            if digest is not None and digest.hexdigest() != declared_sha256:
                raise RuntimeError(
                    "Downloaded file does not match the provider's SHA256 for the file that was "
                    f"chosen (expected {declared_sha256}, got {digest.hexdigest()}). The bytes "
                    "received are not the file that was selected; nothing has been kept."
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
    metadata["sha256_verified"] = declared_sha256 != ""
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
        # This is the path the variant dialog produces -- it hands back the chosen file's own
        # downloadUrl, which matches CIVITAI_DOWNLOAD_RE. Without the lookup below it would be the
        # ONE download path with no digest to verify against, i.e. exactly the common case going
        # unchecked while the rarer ones were covered.
        meta: dict[str, Any] = {"filename": ref.filename, "model_version_id": ref.model_version_id}
        entry = _civitai_file_behind_download_url(
            ref, civitai_api_key=civitai_api_key, timeout_sec=timeout_sec)
        if entry:
            meta["sha256"] = str((entry.get("hashes") or {}).get("SHA256") or "").strip().lower()
            meta["size_kb"] = entry.get("sizeKB")
            meta.setdefault("filename", None)
            meta["filename"] = ref.filename or str(entry.get("name") or "") or None
        return ref.url or "", meta

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
        # Honour an explicit ?fileId= if the reference carries one. Civitai reuses a filename
        # across precisions, so the version's PRIMARY file is frequently not the file being
        # fetched -- and attaching the primary's digest to a different file's bytes would fail
        # verification on a perfectly good download.
        primary_file = _pick_primary_civitai_file(payload, ref.query_params.get("fileId"))
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
            # Verified against the bytes after the transfer. See _download_remote_asset.
            "sha256": str((primary_file.get("hashes") or {}).get("SHA256") or "").strip().lower(),
        }
        return download_url, meta

    return ref.url or "", {"filename": ref.filename}


def _civitai_file_behind_download_url(
    ref: AssetReference, *, civitai_api_key: str | None, timeout_sec: int
) -> dict[str, Any]:
    """The version-payload entry a ``/api/download/models/<id>?...`` URL refers to, or ``{}``.

    Civitai encodes the choice in the query string -- either ``?fileId=`` or the
    ``type``/``format``/``size``/``fp`` selectors its own download buttons use -- so the URL alone
    says which of a version's files is being fetched, but not its digest. This looks the digest up.

    Returns ``{}`` and never raises when it cannot be sure: no version id, the API unreachable, or
    several files matching the selectors equally. An unverifiable download proceeds and is reported
    as unverified (``metadata["sha256_verified"]``); guessing at which file was meant would attach
    the wrong digest and fail a perfectly good transfer.
    """
    version_id = str(ref.model_version_id or "").strip()
    if not version_id:
        return {}
    try:
        payload = _civitai_api_get_json(
            f"https://civitai.com/api/v1/model-versions/{version_id}",
            civitai_api_key=civitai_api_key,
            timeout_sec=timeout_sec,
        )
    except Exception:
        # A metadata lookup failure is not a download failure. It costs verification, which the
        # caller is told about, and that is the whole consequence.
        return {}

    files = [f for f in (payload.get("files") or []) if isinstance(f, dict)]
    if not files:
        return {}

    params = {str(k).lower(): str(v) for k, v in (ref.query_params or {}).items()}
    wanted_id = params.get("fileid", "").strip()
    if wanted_id:
        for entry in files:
            if str(entry.get("id") or "").strip() == wanted_id:
                return entry
        return {}

    # The selector form. Every key present in the URL has to agree, so a URL naming only `format`
    # still narrows by format alone -- which is why the count is checked afterwards rather than
    # trusting the first hit.
    selectors = {"type": "type", "format": "format", "size": "size", "fp": "fp"}
    matches = []
    for entry in files:
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        fields = {"type": entry.get("type"), "format": metadata.get("format"),
                  "size": metadata.get("size"), "fp": metadata.get("fp")}
        if all(str(fields[field] or "").lower() == params[key].lower()
               for key, field in selectors.items() if key in params):
            matches.append(entry)

    if len(matches) == 1:
        return matches[0]
    if not params and len(files) == 1:
        # A bare version download URL with a single file in the version is unambiguous.
        return files[0]
    return {}


def _pick_primary_civitai_file(payload: dict[str, Any], file_id: str | None = None) -> dict[str, Any]:
    """The file entry a download refers to: the one named by ``file_id``, else the primary.

    ``file_id`` matters because a name does not identify a file here -- one version publishes the
    same filename at several precisions, and the download URL distinguishes them with ``?fileId=``.
    Returning the primary regardless attached the wrong size and the wrong digest to the bytes
    being fetched.
    """
    files = [f for f in (payload.get("files") or []) if isinstance(f, dict)]
    if not files:
        return {}
    wanted = str(file_id or "").strip()
    if wanted:
        for file in files:
            if str(file.get("id") or "").strip() == wanted:
                return file
        # Asked for a specific file and this version does not have it -- almost always a reference
        # pointing at a different version. Falling through to the primary would hand back another
        # file's size and digest for the bytes actually being fetched, so a verification that only
        # exists to catch the wrong file would itself cause one to be refused.
        return {}
    for file in files:
        if file.get("primary"):
            return file
    return files[0]


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
