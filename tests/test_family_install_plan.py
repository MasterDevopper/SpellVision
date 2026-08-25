from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from family_install_plan import apply_family_install_plan, build_family_install_plan


def test_wan_missing_vae_is_fetchable() -> None:
    plan = build_family_install_plan("wan", task="t2v", present_basenames=[])
    vae = next(item for item in plan["slots"] if item["component"] == "vae")
    assert vae["install_action"] == "fetch"
    assert vae["fetch_ref"].startswith("hf://Comfy-Org/")
    assert "vae" in plan["missing_required"]
    assert vae["fetch_ref"] in plan["fetchable"]


def test_wan_present_vae_is_already_present() -> None:
    plan = build_family_install_plan(
        "wan",
        task="t2v",
        present_basenames=["wan_2.1_vae.safetensors", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
    )
    vae = next(item for item in plan["slots"] if item["component"] == "vae")
    te = next(item for item in plan["slots"] if item["component"] == "text_encoder")
    assert vae["install_action"] == "already_present"
    assert te["install_action"] == "already_present"
    assert plan["missing_required"] == []


def test_clip_vision_only_on_i2v() -> None:
    t2v = build_family_install_plan("wan", task="t2v", present_basenames=[])
    i2v = build_family_install_plan("wan", task="i2v", present_basenames=[])
    assert all(item["component"] != "clip_vision" for item in t2v["slots"])
    assert any(item["component"] == "clip_vision" for item in i2v["slots"])


def test_non_commercial_family_reviews_instead_of_fetch() -> None:
    plan = build_family_install_plan("anima", task="t2i", present_basenames=[])
    assert plan["commercial_use"] is False
    assert all(item["install_action"] != "fetch" for item in plan["slots"])


def test_apply_dry_run_does_not_materialize() -> None:
    calls: list[str] = []

    def boom(ref: str, **kwargs):
        calls.append(ref)
        raise AssertionError("dry_run must not materialize")

    plan = build_family_install_plan("wan", task="t2v", present_basenames=[])
    applied = apply_family_install_plan(plan, dry_run=True, materialize=boom)
    assert applied["dry_run"] is True
    assert applied["would_fetch"]
    assert calls == []
    assert all(row.get("dry_run") for row in applied["results"] if not row.get("skipped"))


def test_apply_fetches_only_fetch_slots() -> None:
    seen: list[str] = []

    class Fake:
        def __init__(self, ref: str):
            self.local_path = f"/tmp/{ref.split('/')[-1]}"
            self.resolved_kind = "downloaded_file"

    def fake_materialize(ref: str, **kwargs):
        seen.append(ref)
        return Fake(ref)

    plan = build_family_install_plan(
        "wan",
        task="t2v",
        present_basenames=["umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
    )
    applied = apply_family_install_plan(plan, dry_run=False, materialize=fake_materialize)
    assert all(ref.startswith("hf://") for ref in seen)
    assert applied["fetched"]
    te = next(row for row in applied["results"] if row["component"] == "text_encoder")
    assert te["skipped"] is True
    vae = next(row for row in applied["results"] if row["component"] == "vae")
    assert vae["ok"] is True and vae["skipped"] is False


def test_apply_copies_into_install_root(tmp_path: Path) -> None:
    src = tmp_path / "cache" / "wan_2.1_vae.safetensors"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"vae")
    dest = tmp_path / "models"

    class Fake:
        def __init__(self):
            self.local_path = str(src)
            self.resolved_kind = "downloaded_file"

    plan = build_family_install_plan("wan", task="t2v", present_basenames=[])
    applied = apply_family_install_plan(
        plan,
        dry_run=False,
        install_root=str(dest),
        materialize=lambda ref, **kwargs: Fake(),
    )
    installed = dest / "vae" / "wan_2.1_vae.safetensors"
    assert installed.is_file()
    assert str(installed) in applied["installed"]


def test_apply_only_one_component(tmp_path: Path) -> None:
    seen: list[str] = []

    class Fake:
        def __init__(self, ref: str):
            path = tmp_path / Path(ref).name
            path.write_bytes(b"x")
            self.local_path = str(path)
            self.resolved_kind = "downloaded_file"

    plan = build_family_install_plan("wan", task="t2v", present_basenames=[])
    apply_family_install_plan(
        plan,
        dry_run=False,
        only_components=["vae"],
        materialize=lambda ref, **kwargs: seen.append(ref) or Fake(ref),
    )
    assert len(seen) == 1
    assert "vae" in seen[0]

