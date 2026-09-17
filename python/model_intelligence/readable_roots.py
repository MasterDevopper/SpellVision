"""Which model roots can be read RIGHT NOW.

D:/AI_ASSETS can come up BitLocker-locked. When it does, `os.listdir` raises WinError
-2144272384 -- and the three stdlib behaviours that matter all turn that into silence:
`Path.resolve(strict=True)` raises, `Path.is_dir()` swallows the error and answers False, and
`os.walk` discards the failing directory without a word. Every one of them converts "I could not
read this" into "there is nothing here", which is the dangerous answer: an empty inventory looks
exactly like a successful scan of an empty folder.

So readability is ASKED, once, explicitly, and a root that cannot answer is dropped by name with
a reason rather than contributing zero models to a total.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Sequence

# WinError for a BitLocker-locked volume, as raised by os.listdir on this box.
_BITLOCKER_ERRNOS = {-2144272384, 2144272384}


def root_status(root: str | Path) -> dict[str, Any]:
    """Report one root's readability without ever raising."""
    path = Path(str(root))
    try:
        os.listdir(path)
    except FileNotFoundError:
        return {"path": str(path), "readable": False, "reason": "missing"}
    except NotADirectoryError:
        return {"path": str(path), "readable": False, "reason": "error"}
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        locked = winerror in _BITLOCKER_ERRNOS or "BitLocker" in str(exc)
        return {"path": str(path), "readable": False, "reason": "locked" if locked else "error"}
    except ValueError:
        # os.listdir raises ValueError (not OSError) for a path with an embedded null byte, e.g.
        # "embedded null character". One malformed root must not abort enumeration of the rest.
        return {"path": str(path), "readable": False, "reason": "error"}
    return {"path": str(path), "readable": True, "reason": ""}


def readable_models_roots(roots: Sequence[str | Path] | Iterable[str | Path]) -> list[Path]:
    """The subset of roots that can be listed, in the order given, de-duplicated."""
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        text = str(root or "").strip()
        if not text:
            continue
        path = Path(text)
        key = str(path).rstrip("\\/").lower()
        if key in seen:
            continue
        seen.add(key)
        if root_status(path)["readable"]:
            out.append(path)
    return out
