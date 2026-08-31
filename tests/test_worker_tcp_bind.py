"""C6: handle() must not copy worker_service names into module globals()."""
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

import worker_tcp  # noqa: E402


def test_handle_does_not_bind_worker_service_names_into_globals():
    """The extract leftover that did ``globals()[_name] = getattr(ws, _name)`` is gone.

    handle() must resolve worker_service symbols via explicit import or ``_ws().attr``,
    not by copying 30+ names into this module's globals on every request.
    """
    handle_src = inspect.getsource(worker_tcp.WorkerTCPHandler.handle)
    assert "globals()[" not in handle_src, (
        "WorkerTCPHandler.handle() still writes into module globals(); "
        "use _ws().attr or an explicit import instead"
    )


def test_worker_tcp_has_no_globals_bind_helper():
    """No leftover bind helper may still dump worker_service names into globals()."""
    module_src = Path(worker_tcp.__file__).read_text(encoding="utf-8")
    assert "globals()[_name]" not in module_src
    assert "globals()[" not in module_src
