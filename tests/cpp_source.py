"""Find a C++ definition by name, wherever it lives.

Four tests broke when 320 lines moved out of ``MainWindow.cpp`` into their own translation unit --
not because the behaviour changed (the bodies moved verbatim) but because each test had spelled the
filename and sliced the text between two function names. One of them used a neighbouring function as
its END delimiter, so it depended on the ORDER of two unrelated definitions in a 7000-line file.

That is the same defect the sweep harness was built to remove, in the tests that assert on C++: a
check scoped to where the code happened to be is a memo about a past layout. These helpers take the
name and search the tree, so moving a function is a refactor rather than a test failure.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sweeps import sources  # noqa: E402


def _balanced_body(text: str, start: int) -> str:
    """From a definition's first character to the closing brace of its body."""
    open_brace = text.index("{", start)
    depth = 0
    for i in range(open_brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise AssertionError("unbalanced braces after offset %d" % start)


def find_definition(name: str, *, qualifier: str | None = None) -> tuple[Path, str]:
    """The body of ``name``, and the file it was found in.

    Brace-matched rather than sliced between two names: the end of a function is its closing brace,
    not whichever definition happens to follow it.
    """
    pattern = re.compile(
        r"^[A-Za-z_].*?\b" + (re.escape(qualifier) + "::" if qualifier else r"(?:\w+::)?")
        + re.escape(name) + r"\s*\(", re.M)
    for path in sources.cpp_sources():
        if path.suffix != ".cpp":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = pattern.search(text)
        if match:
            return path, _balanced_body(text, match.start())
    raise AssertionError(
        f"no definition of {name!r} anywhere in the C++ sources -- if it was renamed, the test "
        f"should follow the rename rather than the file"
    )


def definition_body(name: str, *, qualifier: str | None = None) -> str:
    return find_definition(name, qualifier=qualifier)[1]
