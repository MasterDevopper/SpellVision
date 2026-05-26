"""Project-root pytest configuration.

This file lives at the repository root (next to CMakeLists.txt) and is
automatically loaded by pytest. It owns two concerns:

  1. Collection filtering. Keep pytest out of vendored Python trees and
     build artifact directories.
  2. Mark registration. Register the project's custom marks so --strict-markers
     can be enabled later without churn, and so we don't get spurious warnings
     about unknown marks today.

The actual test fixtures live in tests/conftest.py.
"""

from __future__ import annotations


# Directories pytest must never descend into when collecting tests.
# Glob patterns are evaluated relative to the rootdir.
collect_ignore_glob = [
    "runtime/*",
    "runtime/**/*",
    "build/*",
    "build/**/*",
    "dist/*",
    "dist/**/*",
    ".venv/*",
    ".venv/**/*",
    "venv/*",
    "venv/**/*",
    "qt_ui_build/*",
    "qt_ui_build/**/*",
    "node_modules/*",
    "node_modules/**/*",
]


def pytest_configure(config) -> None:
    """Register custom marks so they don't trip 'unknown mark' warnings.

    Putting this here (instead of pytest.ini) makes it work regardless of
    whether pytest.ini is being loaded successfully on this machine.
    """
    config.addinivalue_line(
        "markers",
        "contract: tests that pin the worker JSON contract surface",
    )
    config.addinivalue_line(
        "markers",
        "slow: tests that boot heavy backends and may take >30s",
    )
