"""Doc 28 section 2, "Non-commercial surfaced", as properties of the tree.

The gate asserts: *"Hunyuan **and Anima** show a badge; commercial-use setting on -> **soft warn on
generate** (not a hard block)."* Both halves existed before this pass, and both were decided by this,
in ``qt_ui/assets/FamilyLicense.h``::

    return !(hay.contains("anima") || hay.contains("hunyuan"));

Two family names hardcoded in C++, matched as SUBSTRINGS, against the family key *or* the model
path. ``python/model_registry.py`` had already carried ``commercial_use`` and ``license_note`` since
Anima landed, and ``family_install_plan`` already consumed them -- the UI simply asked a second
question of a second source and got a different answer. That is Doc 50 rule 5, and it failed in both
directions at once:

* **False positive.** ``contains("anima")`` is true of animagine, animatediff and animation. The
  anima spec's own comment in the registry says its aliases are deliberately narrow because "a bare
  'anima' substring-collides with animagine/animatediff/animation decoys" -- the C++ copy had
  exactly the collision the Python side had designed around, so animagineXL was badged
  Non-commercial and raised a warning dialog on every generate.
* **False negative, and the dangerous one.** A third non-commercial family in the registry would
  have been badged by nothing and warned about by nothing, with no test anywhere that would notice:
  an absent badge is indistinguishable from an unneeded one. Doc 50 rule 4's "under-reporting is the
  more dangerous direction", applied to a licence.

So the answer is generated from the registry (``scripts/dev/generate_family_license_table.py``) and
these tests hold the property tree-wide rather than at the two sites where it was wrong. Nothing
here spells a family name: every case is derived from ``MODEL_FAMILIES``.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "python"))

from sweeps import sources  # noqa: E402

import cpp_source  # noqa: E402
from model_registry import (  # noqa: E402
    MODEL_FAMILIES,
    family_license_catalog,
    family_license_info,
    non_commercial_families,
)

# Tree-wide properties, not call-site checks.
pytestmark = pytest.mark.ratchet

GENERATED_HEADER = ROOT / "qt_ui" / "assets" / "FamilyLicenseTable.h"


def _generator():
    spec = importlib.util.spec_from_file_location(
        "generate_family_license_table",
        ROOT / "scripts" / "dev" / "generate_family_license_table.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _built_cpp_sources() -> list[Path]:
    """The C++ files CMake actually compiles.

    Derived from ``CMakeLists.txt`` rather than from a list here, and it is not a convenience: a
    file nobody builds cannot misbehave at runtime, so scoping the submit-path rules to the build is
    the honest scope AND it makes the exclusion a property instead of a memo. It also surfaced a
    finding -- ``qt_ui/VideoGenerationPage.cpp`` emits ``generateRequested`` and appears in no
    target, the C++ shape of the ``every-module-is-reachable`` rule.
    """
    cmake = _read("CMakeLists.txt")
    named = set(re.findall(r"^\s*(qt_ui/[\w/]+\.cpp)\s*$", cmake, re.MULTILINE))
    return [p for p in sources.cpp_sources() if sources.relative(p) in named]


# --- the export the UI consumes ------------------------------------------------------------------


def test_the_registry_still_carries_a_licence_dimension() -> None:
    """If this goes empty every downstream assertion here passes vacuously."""
    assert non_commercial_families(), (
        "no family in MODEL_FAMILIES sets commercial_use=False -- either the licence dimension was "
        "dropped or the Doc 28 gate has nothing left to surface"
    )


def test_every_non_commercial_family_survives_the_export() -> None:
    """The badge path reads the export, not the specs. A field that does not survive
    ``family_license_catalog`` is a field the UI cannot show, however correct the spec is."""
    exported = {row["key"]: row for row in family_license_catalog()}
    assert set(exported) == set(MODEL_FAMILIES), "the export lost or invented a family"
    for key in non_commercial_families():
        row = exported[key]
        assert row["commercial_use"] is False, f"{key}: commercial_use did not survive the export"
        assert str(row["license_note"]).strip(), (
            f"{key}: badged non-commercial with no license_note -- a badge with no reachable reason "
            f"is a label the user cannot act on"
        )
        # The one-family lookup and the whole-table export must agree; family_install_plan uses the
        # first and the UI uses the second.
        assert family_license_info(key)["commercial_use"] is False


def test_the_export_carries_the_aliases_that_make_exact_matching_possible() -> None:
    """The C++ lookup resolves by key or by exact alias. Without the aliases it could only match
    keys, and the classifier legitimately returns aliases -- which would silently un-badge them."""
    for row in family_license_catalog():
        assert list(row["aliases"]) == list(MODEL_FAMILIES[row["key"]].aliases)


def test_the_generated_table_has_not_drifted_from_the_registry() -> None:
    """The C++ table is a second copy, permitted by Doc 50 rule 5 only in the layering case and only
    "pinned together with a test". This is that pin: it re-renders and compares on every run, so a
    registry edit that is not regenerated fails here rather than shipping a stale badge."""
    rendered = _generator().render()
    assert GENERATED_HEADER.exists(), "the generated licence table is missing from the tree"
    current = GENERATED_HEADER.read_text(encoding="utf-8")
    assert current == rendered, (
        "qt_ui/assets/FamilyLicenseTable.h is stale -- run "
        "`python scripts/dev/generate_family_license_table.py`"
    )


def test_the_generated_table_names_every_family_and_marks_the_right_ones() -> None:
    """Read back out of the generated C++ rather than trusting render(): the file is what the
    compiler sees."""
    body = GENERATED_HEADER.read_text(encoding="utf-8")
    rows = dict(re.findall(r'^\s*\{"([^"]+)", "[^"]*", (true|false), ', body, re.MULTILINE))
    assert set(rows) == set(MODEL_FAMILIES)
    expected_false = set(non_commercial_families())
    actual_false = {key for key, flag in rows.items() if flag == "false"}
    assert actual_false == expected_false, (
        f"the generated table disagrees with the registry about who is non-commercial: "
        f"{actual_false ^ expected_false}"
    )


# --- one resolver (Doc 50 rule 5) ----------------------------------------------------------------

# The tokens the old predicate matched on. Derived from the registry, never listed: a key or an
# alias of a family the registry calls non-commercial.
def _licence_tokens() -> set[str]:
    tokens: set[str] = set()
    for key in non_commercial_families():
        tokens.add(key)
        tokens.update(MODEL_FAMILIES[key].aliases)
    return tokens


_LICENCE_CONTEXT = re.compile(r"licen[cs]e|commercial", re.IGNORECASE)
_CONTEXT_LINES = 8


def test_no_second_licence_resolver_exists_in_the_tree() -> None:
    """A C++ file that names a non-commercial family *near licence words* is deciding the licence
    question a second time.

    Scoped by PROXIMITY rather than by the bare token, and the difference is measured: the family
    keys appear on their own in ``ModelManagerPage``'s family-detection heuristics and in the video
    routing tables, which are a different question (which family is this) and not this one (what may
    the user do with it). Flagging those would be the R7 over-count Doc 50 rule 10 warns about --
    two false positives per true one, and then the rule gets bypassed. Measured on this tree: the
    bare token match reports **33 hits across 6 files, every one of them false** -- family detection
    in AssetCatalogScanner, ModelManagerPage and VideoGenerationPolicy, the video-family set, and two
    combo-box labels in ManagerPage. With the proximity clause: **0**.

    What it therefore cannot see, stated rather than hidden: a licence decision written with none of
    the words "licence", "license" or "commercial" within eight lines of the family name. That is
    Doc 50's "an omission has no syntax" as it applies here, and it is why the other properties in
    this file check the SHAPE of the one resolver (one settings key, one gate, one badge call)
    rather than relying on this scan alone.
    """
    tokens = _licence_tokens()
    assert tokens, "nothing to look for -- the registry lost its non-commercial families"
    patterns = {t: re.compile(r'"%s"' % re.escape(t)) for t in tokens}

    hits: list[str] = []
    for path in sources.cpp_sources():
        rel = sources.relative(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        # The resolver and its generated data are allowed to name their own subject -- identified by
        # what they declare, so renaming or moving either does not switch the rule off.
        if "kFamilyLicenseTable" in text or "LicenseGate licenseGateFor" in text:
            continue
        lines = text.splitlines()
        context = _LICENCE_CONTEXT
        for i, line in enumerate(lines):
            for token, pattern in patterns.items():
                if not pattern.search(line):
                    continue
                window = "\n".join(lines[max(0, i - _CONTEXT_LINES):i + _CONTEXT_LINES + 1])
                if context.search(window):
                    hits.append(f"{rel}:{i + 1}  decides the licence for {token!r} itself")
    assert not hits, (
        "a second licence resolver exists:\n" + "\n".join(hits) +
        "\n\nThe answer comes from python/model_registry.py through "
        "spellvision::assets::familyLicense. A copy here is how the badge and the warn came to "
        "disagree in the first place."
    )


def test_the_commercial_use_setting_is_read_through_one_accessor() -> None:
    """Same shape as test_dev_tool_visibility_is_one_env_read. The checkbox that writes the
    declaration and the warn that reads it used to spell the key separately, so a rename in either
    would have left the warn reading a key nothing writes -- which reads as "no commercial work
    declared", i.e. no warning at all, silently."""
    hits = []
    for p in sources.cpp_sources():
        text = p.read_text(encoding="utf-8", errors="replace")
        n = text.count('"usage/commercialUse"')
        if n:
            hits.append((sources.relative(p), n))
    assert hits == [("qt_ui/assets/FamilyLicense.cpp", 1)], hits


# --- the badge (Doc 28: "show a badge") -----------------------------------------------------------


def test_the_model_card_badge_comes_from_the_family_the_classifier_returned() -> None:
    """The card grid paints the badge from FamilyRole through the one resolver. Painting it from the
    file name -- which is what the substring predicate effectively did -- is how a rename of a
    checkpoint changed its licence."""
    body = _read("qt_ui/assets/ModelCardDelegate.cpp")
    assert "familyLicenseBadgeText(family)" in body
    assert "index.data(ModelCardModel::FamilyRole)" in body


def test_the_card_tooltip_carries_the_reason_from_the_same_resolver() -> None:
    body = _read("qt_ui/assets/ModelCardModel.cpp")
    assert "familyLicenseNote(card.family)" in body


def test_every_surface_that_names_a_chosen_model_surfaces_its_licence() -> None:
    """The studios each show the picked checkpoint by name. Doc 50 rule 10: the badge is a property
    of "a surface that names a model", not of the one page that happened to have a label for it --
    Character Studio had one and Comic and Concept did not."""
    missing = []
    for path in _built_cpp_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "CatalogPickerDialog dlg(QStringLiteral(\"Choose checkpoint\")" not in text:
            continue
        if "familyLicenseBadgeText(" not in text:
            missing.append(sources.relative(path))
    assert not missing, f"picks a checkpoint and never shows its licence: {missing}"


def test_a_page_that_picks_a_checkpoint_captures_the_classified_family() -> None:
    """Without this the payload carries `model` and no `model_family`, and the warn has nothing to
    key on -- which is precisely why the old predicate fell back to a substring test on the PATH."""
    missing = []
    for path in _built_cpp_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "CatalogPickerDialog dlg(QStringLiteral(\"Choose checkpoint\")" not in text:
            continue
        if "dlg.selectedFamily()" not in text:
            missing.append(sources.relative(path))
    assert not missing, f"picks a checkpoint without capturing its family: {missing}"


def test_every_page_that_asks_for_a_generation_sends_a_family() -> None:
    """Three shapes are legitimate: insert `model_family` directly, build the payload through
    GenerationRequestBuilder (which inserts it), or call buildRequestPayload() (which uses the
    builder). Anything else reaches the warn with no family and is waved through."""
    offenders = []
    for path in _built_cpp_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "emit generateRequested(" not in text:
            continue
        # The needle is the PAYLOAD insert, not the literal anywhere in the file. The first
        # version accepted `o.insert(QStringLiteral("model_family"), ...)` in a project-state
        # writer, so deleting the payload line left the test green -- watched, and fixed.
        if ('payload.insert(QStringLiteral("model_family")' in text
                or "GenerationRequestBuilder" in text
                or "buildRequestPayload()" in text):
            continue
        offenders.append(sources.relative(path))
    assert not offenders, (
        f"emits a generation request with no model family: {offenders} -- the licence warn keys on "
        f"the family, so a payload without one is a warn that can never fire"
    )


# --- the warn is soft (Doc 28: "not a hard block") -------------------------------------------------


def test_the_gate_type_cannot_express_a_block() -> None:
    """Stated in the type rather than in a comment. `LicenseGate` has exactly two enumerators and
    neither is a block, so a future call site cannot spell one without editing the enum -- which is a
    change a reviewer sees, unlike an `if (...) return;` added to a submit path."""
    header = _read("qt_ui/assets/FamilyLicense.h")
    block = re.search(r"enum class LicenseGate\s*\{(.*?)\}", header, re.S).group(1)
    names = re.findall(r"^\s*(\w+),", block, re.MULTILINE)
    assert names == ["Proceed", "WarnThenProceed"], names
    assert not re.search(r"block", block, re.IGNORECASE)


def test_the_warn_offers_a_proceed_button_and_defaults_to_it() -> None:
    """A warn whose safe default is "cancel my render" is a block wearing a warning's clothes. The
    previous version defaulted to No."""
    body = cpp_source.definition_body("licenseGateAllowsSubmit", qualifier="MainWindow")
    assert "AcceptRole" in body, "the warn has no proceeding button"
    assert "box.setDefaultButton(proceed)" in body, "the warn does not default to proceeding"
    # It must not reach past the dialog to disable the generate action.
    for forbidden in ("setEnabled(false)", "setVisible(false)", "->setDisabled("):
        assert forbidden not in body, f"the licence warn disables a control ({forbidden})"


def test_the_warn_never_fires_when_the_user_has_not_declared_commercial_work() -> None:
    body = cpp_source.definition_body("licenseGateAllowsSubmit", qualifier="MainWindow")
    assert "commercialUseDeclared()" in body
    assert "LicenseGate::Proceed" in body


def test_every_submit_path_consults_the_one_gate() -> None:
    """Doc 50 rule 10. The warn shipped on the cockpit path only; the chain path submitted the same
    families to the same worker with nothing asked. A path may either consult the gate or delegate to
    another submit path that does -- both are one answer, which is the point."""
    definitions = []
    for path in _built_cpp_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        definitions += re.findall(r"^\w[^\n=]*::(submit\w*Generation\w*Request\w*)\s*\(",
                                  text, re.MULTILINE)
    assert len(definitions) >= 2, f"the submit-path scan found {definitions} -- it has stopped seeing them"
    ungated = []
    for name in sorted(set(definitions)):
        body = cpp_source.definition_body(name, qualifier="MainWindow")
        delegates = any(re.search(r"\b%s\(" % other, body)
                        for other in set(definitions) if other != name)
        if "licenseGateAllowsSubmit(" not in body and not delegates:
            ungated.append(name)
    assert not ungated, f"submits a generation without asking the licence gate: {ungated}"
