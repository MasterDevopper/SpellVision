"""Model intelligence: who a local weight is, according to the site that hosts it.

A weight on disk is a filename and some bytes. This package turns it into an identity -- name,
pictures, trigger words, licence -- and, the part the rest of the app cares about, the settings
its author actually renders with.

Measured on this box 2026-09-16: a by-hash lookup hit 4 of 4 local files ANONYMOUSLY, and the
owner's own house checkpoint publishes 10 steps / CFG 1 across 10 of 10 example images while
SpellVision was rendering it at 52 / 3.5 from the family table. Per-model settings are not a
convenience here; they are a correctness fix.
"""
from __future__ import annotations

from model_intelligence.civitai_lookup import (
    ALLOWED_HOSTS,
    DEFAULT_HOST,
    CivitaiClient,
    CivitaiThrottled,
)
from model_intelligence.family_seed_table import SEED_TABLE, seed_for
from model_intelligence.hashing import HashCache, autov2, file_sha256, hash_and_cache
from model_intelligence.hf_lookup import HfClient, card_identity, settings_from_readme, sha256_index
from model_intelligence.meta_parse import mode_over, parse_meta, split_sampler
from model_intelligence.previews import cover_path, download_previews, preview_dir, set_user_picture
from model_intelligence.readable_roots import readable_models_roots, root_status
from model_intelligence.recommended import FIELDS, PROVENANCE_ORDER, build
from model_intelligence.sidecar import SCHEMA as SIDECAR_SCHEMA
from model_intelligence.sidecar import build_payload as build_sidecar_payload
from model_intelligence.sidecar import merge as merge_sidecar
from model_intelligence.sidecar import read as read_sidecar
from model_intelligence.sidecar import sidecar_path
from model_intelligence.sidecar import user_values as sidecar_user_values
from model_intelligence.sidecar import write as write_sidecar

__all__ = [
    "ALLOWED_HOSTS",
    "DEFAULT_HOST",
    "CivitaiClient",
    "CivitaiThrottled",
    "FIELDS",
    "HashCache",
    "HfClient",
    "PROVENANCE_ORDER",
    "SEED_TABLE",
    "SIDECAR_SCHEMA",
    "autov2",
    "build",
    "build_sidecar_payload",
    "card_identity",
    "cover_path",
    "download_previews",
    "file_sha256",
    "hash_and_cache",
    "merge_sidecar",
    "mode_over",
    "parse_meta",
    "preview_dir",
    "read_sidecar",
    "readable_models_roots",
    "root_status",
    "seed_for",
    "set_user_picture",
    "settings_from_readme",
    "sha256_index",
    "sidecar_path",
    "sidecar_user_values",
    "split_sampler",
    "write_sidecar",
]
