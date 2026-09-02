"""The one per-user directory SpellVision keeps its own state in.

Two modules computed this independently -- credential_store for the DPAPI blob file, and now the
worker for its session-secret file -- and the Qt side computes the same location a third way, as
QStandardPaths::AppLocalDataLocation for org "DarkDuck" / app "SpellVision". They must all agree,
because the session file is how a client that did not spawn the worker finds the secret: if the
worker writes it under one spelling and the UI reads under another, every request is refused.

Windows: %LOCALAPPDATA%/DarkDuck/SpellVision -- what Qt's AppLocalDataLocation resolves to.
Elsewhere: XDG_CONFIG_HOME or ~ -- the credential store's existing behaviour, kept.
"""
from __future__ import annotations

import os
from pathlib import Path


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home())
    return Path(base) / "DarkDuck" / "SpellVision"
