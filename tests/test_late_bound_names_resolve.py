"""Watched-fail fixture for the `late-bound-names-resolve` sweep rule.

`_ws().resolve_comfy_output_path` shipped on 2026-09-01 with a green suite: py_compile passes,
`import native_runners` passes, and every test that touches the runner mocks the shim. The
AttributeError fired on the first live T2I the next day and stopped every Comfy-native image family.
The rule reads each late-bound attribute (`_ws().name`, `ws.name`, `worker_service.name`) against
the names worker_service actually binds at module level. This file proves the rule fires on the
exact shape that got through, and that it stays quiet on a real name.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from sweeps import rules, sources  # noqa: E402

FAKE_PY = sources.ROOT / "python" / "Fake.py"


def _run(snippet: str):
    return rules._check_late_bound_names(FAKE_PY, snippet)


def test_the_tree_is_at_zero():
    violations = rules.R_LATE_BOUND_NAMES.run()
    assert violations == [], "\n".join(str(v) for v in violations)


def test_the_name_that_stopped_native_image_generation_is_flagged():
    found = _run(
        "def run_native_image(req, asset, prompt_id):\n"
        "    return _ws().resolve_comfy_output_path(req, asset, default_stem=f'x_{prompt_id}')\n"
    )
    assert [v.key for v in found] == ["resolve_comfy_output_path"]
    assert found[0].line == 2


def test_the_module_alias_form_is_flagged_too():
    found = _run("import worker_service as ws\n\ndef f(job):\n    ws.no_such_function(job)\n")
    assert [v.key for v in found] == ["no_such_function"]


def test_a_real_worker_service_name_passes():
    assert _run("def f(item_command, req, emitter, job, active_job):\n"
                "    _ws().dispatch_generation(item_command, req, emitter, job, active_job)\n") == []


def test_names_bound_inside_guarded_imports_count():
    # worker_service imports several things under try/except; those are real names.
    names = rules._worker_service_names()
    assert "dispatch_generation" in names
    assert "archive_job" in names
    assert "resolve_comfy_output_path" not in names, (
        "worker_service now re-exports the resolver; the fixture below documents the incident "
        "against the state that produced it -- update both together"
    )


def test_the_rule_ignores_unrelated_attribute_access():
    assert _run("class Thing:\n    pass\n\nws = Thing()\nother = object()\nother.anything()\n") == []
