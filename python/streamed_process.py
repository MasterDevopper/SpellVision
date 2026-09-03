"""One runner for a child process whose output a person is waiting to see.

``subprocess.run(capture_output=True)`` hands back everything at once, when the process is already
finished. For a probe that answers in a second that is exactly right, and seven call sites in this
tree do it correctly. For work that takes minutes it is the difference between a progress report and
a hang: measured on this tree before this module existed, three call sites could block with no
output at all --

    node_pack_installer.py   pip install -r requirements   timeout 1800 s
    comfy_manager_bridge.py  git / pip for the Comfy manager  timeout  900 s
    garment_shrinkwrap.py    a Blender run                    timeout  180 s

-- against a longest compliant probe of 120 s. A user installing a node pack for a workflow they
pasted sees a still screen for up to half an hour, and the honest reading of a still screen is that
the application has crashed.

So this streams. Both pipes are read on their own threads, because a merged stream would change the
shape of the results the existing callers return, and because "which stream said this" is the
difference between pip's progress chatter and pip's error.

**A caveat worth stating rather than discovering:** pip and git draw progress bars with carriage
returns, not newlines, so a line-oriented reader holds a download bar until the bar finishes. What
arrives promptly is the step-level narration -- "Collecting torch", "Installing collected packages"
-- which is what tells someone the machine is working. Byte-level progress for a MODEL download is a
different mechanism and already exists in ``download_manager``; this is for installs, where the
useful signal is which step is running rather than how many bytes are in.
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

log = logging.getLogger("spellvision.process")

# The stream a line came from, so a caller can route pip's chatter and pip's failure differently.
STDOUT = "stdout"
STDERR = "stderr"

LineCallback = Callable[[str, str], None]  # (stream, line)


@dataclass
class StreamedResult:
    """What ``subprocess.run`` would have returned, plus what happened while it ran."""

    cmd: list[str]
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    seconds: float = 0.0
    error: str = ""
    lines: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.error

    @property
    def tail(self) -> str:
        """The last of the output, for a message. Prefers stderr, which is where the reason is."""
        return (self.stderr or self.stdout or "").strip()[-2000:]


def _pump(stream: Any, tag: str, sink: list[str], on_line: LineCallback | None,
          lines: list[tuple[str, str]], lock: threading.Lock) -> None:
    try:
        for raw in iter(stream.readline, ""):
            if not raw:
                break
            line = raw.rstrip("\r\n")
            sink.append(raw)
            with lock:
                lines.append((tag, line))
            if on_line is not None and line.strip():
                try:
                    on_line(tag, line)
                except Exception:  # a reporting callback must never kill the run it reports on
                    log.warning("[process] a line callback raised; continuing", exc_info=True)
    except Exception:  # pragma: no cover - a pipe closing under us is not the caller's problem
        log.warning("[process] reading %s failed", tag, exc_info=True)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def run_streamed(
    cmd: Iterable[str],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    on_line: LineCallback | None = None,
) -> StreamedResult:
    """Run ``cmd``, forwarding each output line as it arrives, and return the whole of it too.

    Never raises for a process outcome: a failure to start, a non-zero exit and a timeout all come
    back on the result, because every caller here is reporting to a user rather than asserting.
    """
    argv = [str(part) for part in cmd]
    result = StreamedResult(cmd=argv)
    started = time.perf_counter()
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    lock = threading.Lock()

    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd else None,
            env=dict(env) if env is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        result.seconds = round(time.perf_counter() - started, 2)
        return result

    readers = [
        threading.Thread(target=_pump, args=(proc.stdout, STDOUT, out_chunks, on_line, result.lines, lock), daemon=True),
        threading.Thread(target=_pump, args=(proc.stderr, STDERR, err_chunks, on_line, result.lines, lock), daemon=True),
    ]
    for reader in readers:
        reader.start()

    try:
        result.returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        result.timed_out = True
        # Kill, then wait: leaving a pip behind holding a lock on site-packages is how the NEXT
        # install fails for a reason that has nothing to do with it.
        proc.kill()
        try:
            result.returncode = proc.wait(timeout=15)
        except Exception:
            pass
    finally:
        for reader in readers:
            reader.join(timeout=5)

    result.stdout = "".join(out_chunks)
    result.stderr = "".join(err_chunks)
    result.seconds = round(time.perf_counter() - started, 2)
    if result.timed_out and not result.error:
        result.error = f"timed out after {timeout}s"
    return result
