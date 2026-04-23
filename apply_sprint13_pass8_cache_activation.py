from __future__ import annotations

from pathlib import Path
import sys


def backup_once(path: Path, suffix: str, original: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
        print(f"Backup written: {backup}")


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if old not in text:
        print(f"[skip] pattern not found: {label}")
        return text, False
    return text.replace(old, new, 1), True


def patch_mainwindow_h(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    if "class ModelManagerPage;" not in text:
        text, did = replace_once(
            text,
            "class ModePage;\n",
            "class ModePage;\nclass ModelManagerPage;\n",
            "add ModelManagerPage forward declaration",
        )
        changed = changed or did

    text, did = replace_once(
        text,
        "    ModePage *modelsPage_ = nullptr;\n",
        "    ModelManagerPage *modelsPage_ = nullptr;\n",
        "modelsPage_ type update",
    )
    changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_pass8_cache_activation.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def patch_mainwindow_cpp(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    if '#include "ModelManagerPage.h"\n' not in text:
        text, did = replace_once(
            text,
            '#include "ModePage.h"\n',
            '#include "ModePage.h"\n#include "ModelManagerPage.h"\n',
            "include ModelManagerPage.h",
        )
        changed = changed or did

    old_models_block = """    modelsPage_ = new ModePage(
        QStringLiteral("Models"),
        QStringLiteral("Keep model management adjacent to downloads and managers without cluttering creation pages."),
        {QStringLiteral("Surface checkpoints, LoRAs, VAEs, and upscalers with compatibility cues."),
         QStringLiteral("Show dependency health and install state in the library rather than scattering it across pages."),
         QStringLiteral("Reserve space for downloads, manager tools, and future multimodal assets.")},
        this);
"""
    new_models_block = """    modelsPage_ = new ModelManagerPage(this);
    modelsPage_->setProjectRoot(resolveProjectRoot());
    modelsPage_->warmCache();
"""
    text, did = replace_once(text, old_models_block, new_models_block, "replace placeholder models page")
    changed = changed or did

    workflow_setup = """    workflowsPage_ = new WorkflowLibraryPage(this);
    workflowsPage_->setProjectRoot(resolveProjectRoot());
    workflowsPage_->setPythonExecutable(resolvePythonExecutable());
    workflowsPage_->setProfilesRoot(defaultImportedWorkflowsRoot(resolveProjectRoot()));
"""
    workflow_setup_new = """    workflowsPage_ = new WorkflowLibraryPage(this);
    workflowsPage_->setProjectRoot(resolveProjectRoot());
    workflowsPage_->setPythonExecutable(resolvePythonExecutable());
    workflowsPage_->setProfilesRoot(defaultImportedWorkflowsRoot(resolveProjectRoot()));
    workflowsPage_->warmCache();
"""
    if "workflowsPage_->warmCache();" not in text:
        text, did = replace_once(text, workflow_setup, workflow_setup_new, "warmCache workflows page")
        changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_pass8_cache_activation.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def patch_cmake(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = False

    block = """    qt_ui/WorkflowLibraryPage.h
    qt_ui/WorkflowLibraryPage.cpp
)"""
    replacement = """    qt_ui/WorkflowLibraryPage.h
    qt_ui/WorkflowLibraryPage.cpp
    qt_ui/ModelManagerPage.h
    qt_ui/ModelManagerPage.cpp
)"""
    if "qt_ui/ModelManagerPage.h" not in text:
        text, did = replace_once(text, block, replacement, "add ModelManagerPage sources to CMake")
        changed = changed or did

    if not changed:
        return False

    backup_once(path, ".pre_pass8_cache_activation.bak", original)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_sprint13_pass8_cache_activation.py <SpellVision project root>")
        return 2

    root = Path(sys.argv[1]).resolve()
    targets = {
        "MainWindow.h": root / "qt_ui" / "MainWindow.h",
        "MainWindow.cpp": root / "qt_ui" / "MainWindow.cpp",
        "CMakeLists.txt": root / "CMakeLists.txt",
    }

    missing = [name for name, path in targets.items() if not path.exists()]
    if missing:
        print("Missing required files:")
        for name in missing:
            print(f"  {name}")
        return 1

    changed = False
    changed = patch_mainwindow_h(targets["MainWindow.h"]) or changed
    changed = patch_mainwindow_cpp(targets["MainWindow.cpp"]) or changed
    changed = patch_cmake(targets["CMakeLists.txt"]) or changed

    if not changed:
        print("No changes made. Files may already be patched or differ from the expected shape.")
        return 1

    print()
    print("Sprint 13 Pass 8 shell patch applied.")
    print("Next: copy WorkflowLibraryPage.* and ModelManagerPage.* from this bundle, then rebuild.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
