"""User-bound credential store.

On Windows, values are encrypted with DPAPI (CryptProtectData) for the current
user. The on-disk JSON never contains plaintext secrets. Status never echoes them.
v1 plaintext files are migrated in place on the next read/write.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

HF_ENV_KEYS = ("SPELLVISION_HF_TOKEN", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")
CIVITAI_ENV_KEYS = ("SPELLVISION_CIVITAI_API_KEY", "CIVITAI_API_KEY")
KNOWN_KEYS = ("hf_token", "civitai_api_key")
STORE_VERSION = 2
STORE_BACKEND = "dpapi"
ENTROPY = b"SpellVision.credentials.v2"


def default_store_path() -> Path:
    override = str(os.environ.get("SPELLVISION_CREDENTIAL_STORE") or "").strip()
    if override:
        return Path(override).expanduser()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home())
    return Path(base) / "DarkDuck" / "SpellVision" / "credentials.json"


def _protect(text: str) -> str:
    raw = str(text or "").encode("utf-8")
    if sys.platform != "win32":
        raise RuntimeError("Credential encryption requires Windows DPAPI")
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.create_string_buffer(raw, len(raw))
    ent_buf = ctypes.create_string_buffer(ENTROPY, len(ENTROPY))
    blob_in = DATA_BLOB(len(raw), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    blob_ent = DATA_BLOB(len(ENTROPY), ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        ctypes.c_wchar_p("SpellVision credential"),
        ctypes.byref(blob_ent),
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptProtectData failed")
    try:
        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
    return base64.b64encode(data).decode("ascii")


def _unprotect(blob_b64: str) -> str:
    if not blob_b64:
        return ""
    if sys.platform != "win32":
        return ""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    raw = base64.b64decode(str(blob_b64))
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.create_string_buffer(raw, len(raw))
    ent_buf = ctypes.create_string_buffer(ENTROPY, len(ENTROPY))
    blob_in = DATA_BLOB(len(raw), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    blob_ent = DATA_BLOB(len(ENTROPY), ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        ctypes.byref(blob_ent),
        None,
        None,
        0x1,
        ctypes.byref(blob_out),
    ):
        return ""
    try:
        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
    return data.decode("utf-8", errors="replace")


def _restrict_acl(path: Path) -> bool:
    """Narrow a credential file to the current user. Returns whether it fully succeeded.

    Every failure here used to be swallowed by ``except Exception: pass``, including a non-zero
    ``icacls`` exit, so the store could be left inheritable by other principals with nothing said
    anywhere. That is defence in depth rather than a key leak -- the contents are DPAPI blobs bound
    to this user, so a readable file is ciphertext another account cannot decrypt -- but a security
    control that reports nothing when it fails is indistinguishable from one that is not there.

    Failures are logged at WARNING deliberately: the root logger sits at WARNING in this app, so
    anything below it is invisible (CLAUDE.md section 4).
    """
    ok = True
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        ok = False
        log.warning("Could not restrict permissions on the credential store %s: %s", path, exc)

    if sys.platform != "win32":
        return ok

    user = os.environ.get("USERNAME") or ""
    if not user:
        log.warning("USERNAME is unset, so the credential store ACL at %s was left inherited.", path)
        return False
    try:
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(R,W)"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            ok = False
            # check=False means a non-zero exit raises nothing; it has to be read to be noticed.
            log.warning("icacls could not restrict the credential store %s (exit %s): %s",
                        path, result.returncode, (result.stderr or result.stdout or "").strip())
    except OSError as exc:
        ok = False
        log.warning("Could not run icacls to restrict the credential store %s: %s", path, exc)
    return ok


def _decode_payload(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    version = int(payload.get("version") or 1)
    if version >= 2 and isinstance(payload.get("secrets"), dict):
        for key in KNOWN_KEYS:
            blob = str(payload["secrets"].get(key) or "").strip()
            if not blob:
                continue
            value = _unprotect(blob)
            if value:
                out[key] = value
        return out
    for key in KNOWN_KEYS:
        value = str(payload.get(key) or "").strip()
        if value:
            out[key] = value
    return out


def _read_store(path: Path | None = None) -> dict[str, str]:
    store = path or default_store_path()
    if not store.is_file():
        return {}
    try:
        payload = json.loads(store.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    values = _decode_payload(payload)
    if values and int(payload.get("version") or 1) < STORE_VERSION:
        _write_store(values, store)
    return values


def _write_store(values: dict[str, str], path: Path | None = None) -> Path:
    store = path or default_store_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    secrets = {}
    for key in KNOWN_KEYS:
        token = str(values.get(key) or "").strip()
        if token:
            secrets[key] = _protect(token)
    payload = {"version": STORE_VERSION, "backend": STORE_BACKEND, "secrets": secrets}
    tmp = store.with_suffix(store.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # Harden BEFORE the rename. Writing the temp file leaves it at default (inherited) permissions,
    # and restricting only after the rename means the real store exists unrestricted for the window
    # in between. Applying it to the temp file closes that window; NTFS carries the ACL through the
    # rename, and the second call re-asserts it in case the destination pre-existed.
    _restrict_acl(tmp)
    tmp.replace(store)
    _restrict_acl(store)
    return store


def set_credential(name: str, value: str, *, path: Path | None = None) -> dict[str, Any]:
    key = str(name or "").strip().lower()
    if key not in KNOWN_KEYS:
        raise ValueError(f"Unknown credential {name!r}")
    current = _read_store(path)
    token = str(value or "").strip()
    if token:
        current[key] = token
    else:
        current.pop(key, None)
    _write_store(current, path)
    return credential_status(path=path)


def clear_credential(name: str, *, path: Path | None = None) -> dict[str, Any]:
    return set_credential(name, "", path=path)


def get_credential(name: str, *, explicit: str | None = None, path: Path | None = None) -> str:
    key = str(name or "").strip().lower()
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    env_keys = HF_ENV_KEYS if key == "hf_token" else CIVITAI_ENV_KEYS if key == "civitai_api_key" else ()
    for env_key in env_keys:
        value = str(os.environ.get(env_key) or "").strip()
        if value:
            return value
    return _read_store(path).get(key, "")


def credential_status(*, path: Path | None = None) -> dict[str, Any]:
    store = path or default_store_path()
    stored = _read_store(store)
    backend = STORE_BACKEND if store.is_file() else ""
    try:
        payload = json.loads(store.read_text(encoding="utf-8")) if store.is_file() else {}
        backend = str(payload.get("backend") or backend)
        version = int(payload.get("version") or 0)
    except Exception:
        version = 0
    return {
        "ok": True,
        "type": "credential_status",
        "store_path": str(store),
        "encrypted": version >= STORE_VERSION and backend == STORE_BACKEND,
        "backend": backend,
        "hf_token_present": bool(get_credential("hf_token", path=store)),
        "civitai_api_key_present": bool(get_credential("civitai_api_key", path=store)),
        "hf_token_stored": "hf_token" in stored,
        "civitai_api_key_stored": "civitai_api_key" in stored,
    }
