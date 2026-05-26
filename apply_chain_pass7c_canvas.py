r"""
SpellVision — Chain Studio Pass 7c: wire ChainCanvasWidget.

Four coordinated edits:

1. CMakeLists.txt — register ChainCanvasWidget.h/.cpp.
2. ChainStudioPage.cpp — include the canvas widget; replace the
   buildCanvas() placeholder body with a real ChainCanvasWidget;
   wire variationSelectionChanged and lockRequested signals to stub
   handlers; cache the canvas pointer so the rail's selection
   handler can update it.
3. ChainStudioPage.h — add canvasWidget_ pointer + the two new stub
   slot declarations.
4. ChainStudioPage.cpp — update buildStubChain() to point variation
   outputPath at real images in the project root (SpellVision.jpg,
   SpellVision2.jpg) so the canvas renders actual content during
   Pass 7c review. The resolution uses QCoreApplication::application
   DirPath() + "../../" which lands at the project root from the
   build/Debug/ output dir.

All Pass 8 wiring (engine.lock, engine.selectVariation, real output
paths) replaces these stubs. Pass 7c is purely visual.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "CHAIN STUDIO PASS 7C CANVAS"
CMAKE_BACKUP_SUFFIX = ".pre_chain_pass7c_cmake.bak"
HDR_BACKUP_SUFFIX   = ".pre_chain_pass7c_page_hdr.bak"
CPP_BACKUP_SUFFIX   = ".pre_chain_pass7c_page_cpp.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Anchor not found: {label}")
    if text.count(old) > 1:
        raise RuntimeError(f"Anchor not unique ({text.count(old)}x): {label}")
    return text.replace(old, new, 1)


# =============================================================================
# 1. CMakeLists.txt — append after Pass 7B rail registration
# =============================================================================

CMAKE_ANCHOR = (
    "    # --- CHAIN STUDIO PASS 7B RAIL CMAKE REGISTRATION ---\n"
    "    qt_ui/chain/ChainRailWidget.h\n"
    "    qt_ui/chain/ChainRailWidget.cpp\n"
)

CMAKE_REPLACEMENT = (
    "    # --- CHAIN STUDIO PASS 7B RAIL CMAKE REGISTRATION ---\n"
    "    qt_ui/chain/ChainRailWidget.h\n"
    "    qt_ui/chain/ChainRailWidget.cpp\n"
    f"    # --- {MARKER} CMAKE REGISTRATION ---\n"
    "    qt_ui/chain/ChainCanvasWidget.h\n"
    "    qt_ui/chain/ChainCanvasWidget.cpp\n"
)


def patch_cmake(project: Path) -> None:
    path = project / "CMakeLists.txt"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, CMAKE_BACKUP_SUFFIX)
    text = replace_once(text, CMAKE_ANCHOR, CMAKE_REPLACEMENT,
                        "Pass 7b CMake block tail")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# =============================================================================
# 2. ChainStudioPage.h — add canvasWidget_ member + new slot declarations
# =============================================================================

HDR_ANCHOR = (
    "    Chain stubChain_;\n"
    "    QString selectedStageId_;\n"
    "    void buildStubChain();\n"
    "    void onRailStageSelected(const QString &stageId);\n"
    "    void onRailAddStageRequested();\n"
    "};\n"
)

HDR_REPLACEMENT = (
    "    Chain stubChain_;\n"
    "    QString selectedStageId_;\n"
    "    void buildStubChain();\n"
    "    void onRailStageSelected(const QString &stageId);\n"
    "    void onRailAddStageRequested();\n"
    f"\n    // --- {MARKER} ---\n"
    "    // Cached pointer to the canvas widget so the rail's selection\n"
    "    // handler can route to it. Pass 8 will replace this with a\n"
    "    // proper engine-driven signal flow.\n"
    "    ChainCanvasWidget *canvasWidget_ = nullptr;\n"
    "    void onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx);\n"
    "    void onCanvasLockRequested(const QString &stageId);\n"
    "};\n"
)

# Need to forward-declare ChainCanvasWidget in the header. Add the
# forward decl in the same namespace just before the page class.
HDR_FWD_ANCHOR = (
    "namespace spellvision::chain\n"
    "{\n"
    "\n"
    "class ChainStudioPage : public QWidget\n"
)

HDR_FWD_REPLACEMENT = (
    "namespace spellvision::chain\n"
    "{\n"
    f"\n// --- {MARKER}: forward-declare ChainCanvasWidget ---\n"
    "class ChainCanvasWidget;\n"
    "\n"
    "class ChainStudioPage : public QWidget\n"
)


def patch_page_header(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, HDR_BACKUP_SUFFIX)
    text = replace_once(text, HDR_FWD_ANCHOR, HDR_FWD_REPLACEMENT,
                        "forward-decl insertion point")
    text = replace_once(text, HDR_ANCHOR, HDR_REPLACEMENT,
                        "ChainStudioPage class tail")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# =============================================================================
# 3. ChainStudioPage.cpp — include + buildCanvas rewrite + slot impls +
#    buildStubChain real-image swap
# =============================================================================

CPP_INCLUDE_ANCHOR = (
    '#include "chain/ChainRailWidget.h"\n'
    '#include <QDateTime>\n'
    '#include <QUuid>\n'
)

CPP_INCLUDE_REPLACEMENT = (
    '#include "chain/ChainRailWidget.h"\n'
    f'// --- {MARKER} ---\n'
    '#include "chain/ChainCanvasWidget.h"\n'
    '#include <QCoreApplication>\n'
    '#include <QDir>\n'
    '#include <QDateTime>\n'
    '#include <QUuid>\n'
)

# Replace the buildCanvas() body. The current Pass 7a impl returns a
# placeholder QFrame; Pass 7c returns a real ChainCanvasWidget.
CPP_BUILDCANVAS_OLD = (
    'QWidget *ChainStudioPage::buildCanvas()\n'
    '{\n'
    '    auto *canvas = new QFrame(this);\n'
    '    canvas->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);\n'
    '    applyPlaceholderStyle(canvas,\n'
    '        QStringLiteral("CANVAS — last completed variation + pager + lock button (Pass 7c)"));\n'
    '    return canvas;\n'
    '}\n'
)

CPP_BUILDCANVAS_NEW = (
    'QWidget *ChainStudioPage::buildCanvas()\n'
    '{\n'
    f'    // --- {MARKER} ---\n'
    '    // Pass 7c: real canvas widget against stub chain data.\n'
    '    // Selection comes IN via setSelectedStageId() (called from\n'
    '    // onRailStageSelected). Navigation/lock requests go OUT via\n'
    '    // signals. Pass 8 will replace the stub handlers with engine\n'
    '    // calls.\n'
    '    canvasWidget_ = new ChainCanvasWidget(this);\n'
    '    canvasWidget_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);\n'
    '\n'
    '    connect(canvasWidget_, &ChainCanvasWidget::variationSelectionChanged,\n'
    '            this, &ChainStudioPage::onCanvasVariationSelectionChanged);\n'
    '    connect(canvasWidget_, &ChainCanvasWidget::lockRequested,\n'
    '            this, &ChainStudioPage::onCanvasLockRequested);\n'
    '\n'
    '    // Bind the same stub chain the rail uses + the same selection.\n'
    '    canvasWidget_->setChain(stubChain_);\n'
    '    canvasWidget_->setSelectedStageId(selectedStageId_);\n'
    '\n'
    '    return canvasWidget_;\n'
    '}\n'
)

# The rail's onRailStageSelected handler needs to also push selection
# into the canvas. The current impl only updates the rail; Pass 7c
# extends it to route to canvas_ as well.
CPP_RAILSELECT_OLD = (
    'void ChainStudioPage::onRailStageSelected(const QString &stageId)\n'
    '{\n'
    '    if (stageId == selectedStageId_)\n'
    '        return;\n'
    '    selectedStageId_ = stageId;\n'
    '    // Selection routing — Pass 7c (canvas) and 7d (config) read\n'
    '    // selectedStageId_ to update. For Pass 7b we just record the\n'
    '    // selection and let the rail show its highlight; nothing\n'
    '    // downstream is wired yet.\n'
    '    if (auto *rail = qobject_cast<ChainRailWidget *>(chainRail_))\n'
    '        rail->setSelectedStageId(stageId);\n'
    '}\n'
)

CPP_RAILSELECT_NEW = (
    'void ChainStudioPage::onRailStageSelected(const QString &stageId)\n'
    '{\n'
    '    if (stageId == selectedStageId_)\n'
    '        return;\n'
    '    selectedStageId_ = stageId;\n'
    '    if (auto *rail = qobject_cast<ChainRailWidget *>(chainRail_))\n'
    '        rail->setSelectedStageId(stageId);\n'
    f'    // --- {MARKER}: route selection to canvas ---\n'
    '    if (canvasWidget_ != nullptr)\n'
    '        canvasWidget_->setSelectedStageId(stageId);\n'
    '}\n'
)

# Append the two new slot impls + buildStubChain rewrite that uses
# real images. The buildStubChain replacement is the bigger change,
# so we replace the whole function rather than try to surgically edit
# the outputPath line.
CPP_BUILDSTUB_OLD = (
    'void ChainStudioPage::buildStubChain()\n'
    '{\n'
    '    stubChain_ = Chain{};\n'
    '    stubChain_.id = QUuid::createUuid().toString(QUuid::WithoutBraces);\n'
    '    stubChain_.createdAt = QDateTime::currentDateTimeUtc();\n'
    '    stubChain_.updatedAt = stubChain_.createdAt;\n'
    '    stubChain_.entryKind = EntryKind::DescribedText;\n'
    '\n'
    '    auto makeStub = [](StageKind k, StageStatus s, int varCount, int idx) {\n'
    '        Stage stage;\n'
    '        stage.id = QUuid::createUuid().toString(QUuid::WithoutBraces);\n'
    '        stage.index = idx;\n'
    '        stage.kind = k;\n'
    '        stage.status = s;\n'
    '        stage.config.stageKind = k;\n'
    '        for (int i = 0; i < varCount; ++i)\n'
    '        {\n'
    '            Variation v;\n'
    '            v.id = QUuid::createUuid().toString(QUuid::WithoutBraces);\n'
    '            v.createdAt = QDateTime::currentDateTimeUtc();\n'
    '            v.outputPath = QStringLiteral("/tmp/stub_out_") +\n'
    '                QString::number(i) + QStringLiteral(".png");\n'
    '            stage.variations.append(v);\n'
    '        }\n'
    '        if (varCount > 0)\n'
    '            stage.selectedVarIdx = varCount - 1;\n'
    '        if (s == StageStatus::Locked && varCount > 0)\n'
    '            stage.lockedVarIdx = varCount - 1;\n'
    '        return stage;\n'
    '    };\n'
    '\n'
    '    stubChain_.stages.append(makeStub(StageKind::T2I, StageStatus::Locked,    3, 0));\n'
    '    stubChain_.stages.append(makeStub(StageKind::I2V, StageStatus::Completed, 2, 1));\n'
    '    stubChain_.stages.append(makeStub(StageKind::I2_3D, StageStatus::Draft,   0, 2));\n'
    '}\n'
)

CPP_BUILDSTUB_NEW = (
    'void ChainStudioPage::buildStubChain()\n'
    '{\n'
    f'    // --- {MARKER}: point stub outputPaths at real images in\n'
    '    // the project root so the canvas renders actual content\n'
    '    // during review. Pass 8 replaces these with real engine\n'
    '    // output paths.\n'
    '    const QString projectRoot = QDir(QCoreApplication::applicationDirPath())\n'
    '        .filePath(QStringLiteral("../.."));\n'
    '    const QStringList stubImages = {\n'
    '        QDir(projectRoot).filePath(QStringLiteral("SpellVision.jpg")),\n'
    '        QDir(projectRoot).filePath(QStringLiteral("SpellVision2.jpg")),\n'
    '    };\n'
    '\n'
    '    stubChain_ = Chain{};\n'
    '    stubChain_.id = QUuid::createUuid().toString(QUuid::WithoutBraces);\n'
    '    stubChain_.createdAt = QDateTime::currentDateTimeUtc();\n'
    '    stubChain_.updatedAt = stubChain_.createdAt;\n'
    '    stubChain_.entryKind = EntryKind::DescribedText;\n'
    '\n'
    '    auto makeStub = [&stubImages](StageKind k, StageStatus s, int varCount, int idx) {\n'
    '        Stage stage;\n'
    '        stage.id = QUuid::createUuid().toString(QUuid::WithoutBraces);\n'
    '        stage.index = idx;\n'
    '        stage.kind = k;\n'
    '        stage.status = s;\n'
    '        stage.config.stageKind = k;\n'
    '        for (int i = 0; i < varCount; ++i)\n'
    '        {\n'
    '            Variation v;\n'
    '            v.id = QUuid::createUuid().toString(QUuid::WithoutBraces);\n'
    '            v.createdAt = QDateTime::currentDateTimeUtc();\n'
    '            // Cycle through the available real images so each\n'
    '            // variation looks distinct.\n'
    '            v.outputPath = stubImages.at(i % stubImages.size());\n'
    '            stage.variations.append(v);\n'
    '        }\n'
    '        if (varCount > 0)\n'
    '            stage.selectedVarIdx = varCount - 1;\n'
    '        if (s == StageStatus::Locked && varCount > 0)\n'
    '            stage.lockedVarIdx = varCount - 1;\n'
    '        return stage;\n'
    '    };\n'
    '\n'
    '    stubChain_.stages.append(makeStub(StageKind::T2I, StageStatus::Locked,    3, 0));\n'
    '    stubChain_.stages.append(makeStub(StageKind::I2V, StageStatus::Completed, 2, 1));\n'
    '    stubChain_.stages.append(makeStub(StageKind::I2_3D, StageStatus::Draft,   0, 2));\n'
    '}\n'
)

# Append the two new slot impls before the namespace closer.
CPP_TAIL_OLD = (
    'void ChainStudioPage::onRailAddStageRequested()\n'
    '{\n'
    '    // Pass 7d will show a kind-picker menu here. Pass 8 wires the\n'
    '    // engine call. Pass 7b is a no-op stub so the button is\n'
    '    // clickable without throwing.\n'
    '}\n'
    '\n'
    '} // namespace spellvision::chain\n'
)

CPP_TAIL_NEW = (
    'void ChainStudioPage::onRailAddStageRequested()\n'
    '{\n'
    '    // Pass 7d will show a kind-picker menu here. Pass 8 wires the\n'
    '    // engine call. Pass 7b is a no-op stub so the button is\n'
    '    // clickable without throwing.\n'
    '}\n'
    '\n'
    f'// --- {MARKER}: canvas slot impls ---\n'
    '\n'
    'void ChainStudioPage::onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx)\n'
    '{\n'
    '    // Stub handler: update the in-memory stub chain so the canvas\n'
    '    // reflects the new selection on next refresh. Pass 8 will\n'
    '    // call engine.selectVariation() instead.\n'
    '    for (auto &stage : stubChain_.stages)\n'
    '    {\n'
    '        if (stage.id != stageId)\n'
    '            continue;\n'
    '        if (newVarIdx < 0 || newVarIdx >= stage.variations.size())\n'
    '            return;\n'
    '        stage.selectedVarIdx = newVarIdx;\n'
    '        if (canvasWidget_ != nullptr)\n'
    '            canvasWidget_->setChain(stubChain_);\n'
    '        return;\n'
    '    }\n'
    '}\n'
    '\n'
    'void ChainStudioPage::onCanvasLockRequested(const QString &stageId)\n'
    '{\n'
    '    // Stub handler: flip the stage to Locked in the stub chain and\n'
    '    // refresh both the rail and the canvas so the lock visual\n'
    '    // appears. Pass 8 will call engine.lock(stageId) instead\n'
    '    // (which also triggers downstream-cascade if there were any\n'
    '    // generated downstream stages — Pass 8 territory).\n'
    '    for (auto &stage : stubChain_.stages)\n'
    '    {\n'
    '        if (stage.id != stageId)\n'
    '            continue;\n'
    '        if (stage.status != StageStatus::Completed)\n'
    '            return;\n'
    '        stage.status = StageStatus::Locked;\n'
    '        stage.lockedVarIdx = stage.selectedVarIdx;\n'
    '        if (auto *rail = qobject_cast<ChainRailWidget *>(chainRail_))\n'
    '        {\n'
    '            rail->setChain(stubChain_);\n'
    '            rail->setSelectedStageId(selectedStageId_);\n'
    '            const bool canAdd = stubChain_.stages.isEmpty() ||\n'
    '                stubChain_.stages.back().status == StageStatus::Locked;\n'
    '            rail->setCanAddStage(canAdd);\n'
    '        }\n'
    '        if (canvasWidget_ != nullptr)\n'
    '            canvasWidget_->setChain(stubChain_);\n'
    '        return;\n'
    '    }\n'
    '}\n'
    '\n'
    '} // namespace spellvision::chain\n'
)


def patch_page_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path, CPP_BACKUP_SUFFIX)
    text = replace_once(text, CPP_INCLUDE_ANCHOR, CPP_INCLUDE_REPLACEMENT, "includes")
    text = replace_once(text, CPP_BUILDCANVAS_OLD, CPP_BUILDCANVAS_NEW, "buildCanvas body")
    text = replace_once(text, CPP_RAILSELECT_OLD, CPP_RAILSELECT_NEW, "onRailStageSelected")
    text = replace_once(text, CPP_BUILDSTUB_OLD, CPP_BUILDSTUB_NEW, "buildStubChain")
    text = replace_once(text, CPP_TAIL_OLD, CPP_TAIL_NEW, "namespace tail / slot impls")
    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("CMakeLists.txt")
    patch_cmake(project)
    print()
    print("qt_ui/chain/ChainStudioPage.h")
    patch_page_header(project)
    print()
    print("qt_ui/chain/ChainStudioPage.cpp")
    patch_page_cpp(project)
    print()
    print(f"Done — {MARKER} applied.")
    print()
    print("Save ChainCanvasWidget.h/.cpp to qt_ui/chain/ first, then:")
    print("    .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
