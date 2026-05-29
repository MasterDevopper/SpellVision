r"""
SpellVision — Chain Studio Pass 7b (page + CMake): wire ChainRailWidget.

Three coordinated edits:

1. CMakeLists.txt — register ChainRailWidget.h/.cpp.
2. ChainStudioPage.h — declare stub chain build helper + selection
   handler slot.
3. ChainStudioPage.cpp — replace the chainRail_ placeholder QFrame
   with a real ChainRailWidget bound to stub Chain data, and wire
   selection routing.

This is the third sub-script of Pass 7b. Run AFTER:
    python .\apply_chain_pass7b_engine_canaddstage.py
    python .\apply_chain_pass7b_theme_status_colors.py

The engine + theme patches must land first because ChainStudioPage's
new code references both ChainEngine::canAddStage() (engine patch)
and ThemeManager::successColorPublic()/etc. (theme patch).

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "CHAIN STUDIO PASS 7B RAIL"
CMAKE_BACKUP_SUFFIX = ".pre_chain_pass7b_cmake.bak"
HDR_BACKUP_SUFFIX   = ".pre_chain_pass7b_page_hdr.bak"
CPP_BACKUP_SUFFIX   = ".pre_chain_pass7b_page_cpp.bak"


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


# ----- CMakeLists.txt: append onto Pass 7a -----

CMAKE_ANCHOR = (
    "    # --- CHAIN STUDIO PASS 7A CMAKE REGISTRATION ---\n"
    "    qt_ui/chain/ChainStudioPage.h\n"
    "    qt_ui/chain/ChainStudioPage.cpp\n"
)

CMAKE_REPLACEMENT = (
    "    # --- CHAIN STUDIO PASS 7A CMAKE REGISTRATION ---\n"
    "    qt_ui/chain/ChainStudioPage.h\n"
    "    qt_ui/chain/ChainStudioPage.cpp\n"
    f"    # --- {MARKER} CMAKE REGISTRATION ---\n"
    "    qt_ui/chain/ChainRailWidget.h\n"
    "    qt_ui/chain/ChainRailWidget.cpp\n"
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
                        "Pass 7a CMake block tail")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# ----- ChainStudioPage.h: add stub chain + selection slot -----

PAGE_HDR_ANCHOR = (
    "    // Region pointers kept on the instance for later passes (7b-7d\n"
    "    // will populate them; 8 will bind them to engine signals).\n"
    "    QWidget *topStrip_     = nullptr;\n"
    "    QWidget *chainRail_    = nullptr;\n"
    "    QWidget *canvas_       = nullptr;\n"
    "    QWidget *configPanel_  = nullptr;\n"
    "};\n"
)

PAGE_HDR_REPLACEMENT = (
    "    // Region pointers kept on the instance for later passes (7b-7d\n"
    "    // will populate them; 8 will bind them to engine signals).\n"
    "    QWidget *topStrip_     = nullptr;\n"
    "    QWidget *chainRail_    = nullptr;\n"
    "    QWidget *canvas_       = nullptr;\n"
    "    QWidget *configPanel_  = nullptr;\n"
    "\n"
    f"    // --- {MARKER} ---\n"
    "    // Stub chain used while Track B is built against placeholder\n"
    "    // data. Pass 8 will replace this with a live ChainEngine\n"
    "    // reference and bind to engine signals.\n"
    "    Chain stubChain_;\n"
    "    QString selectedStageId_;\n"
    "    void buildStubChain();\n"
    "    void onRailStageSelected(const QString &stageId);\n"
    "    void onRailAddStageRequested();\n"
    "};\n"
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
    text = replace_once(text, PAGE_HDR_ANCHOR, PAGE_HDR_REPLACEMENT,
                        "ChainStudioPage class tail")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# ----- ChainStudioPage.cpp: replace placeholder rail with real widget -----

# Add the include + ChainEngine include alongside existing includes.
CPP_INCLUDE_ANCHOR = (
    '#include "chain/ChainStudioPage.h"\n'
    '\n'
    '#include "ThemeManager.h"\n'
    '\n'
    '#include <QFrame>\n'
    '#include <QHBoxLayout>\n'
    '#include <QLabel>\n'
    '#include <QSizePolicy>\n'
    '#include <QVBoxLayout>\n'
)

CPP_INCLUDE_REPLACEMENT = (
    '#include "chain/ChainStudioPage.h"\n'
    '\n'
    '#include "ThemeManager.h"\n'
    f'// --- {MARKER} ---\n'
    '#include "chain/ChainRailWidget.h"\n'
    '#include <QDateTime>\n'
    '#include <QUuid>\n'
    '\n'
    '#include <QFrame>\n'
    '#include <QHBoxLayout>\n'
    '#include <QLabel>\n'
    '#include <QSizePolicy>\n'
    '#include <QVBoxLayout>\n'
)

# Swap the buildChainRail() body to instantiate ChainRailWidget.
CPP_BUILDRAIL_ANCHOR = (
    'QWidget *ChainStudioPage::buildChainRail()\n'
    '{\n'
    '    auto *rail = new QFrame(this);\n'
    '    rail->setFixedHeight(kChainRailHeight);\n'
    '    rail->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);\n'
    '    applyPlaceholderStyle(rail,\n'
    '        QStringLiteral("CHAIN RAIL — stage nodes + connectors + add-stage placeholder (Pass 7b)"));\n'
    '    return rail;\n'
    '}\n'
)

CPP_BUILDRAIL_REPLACEMENT = (
    'QWidget *ChainStudioPage::buildChainRail()\n'
    '{\n'
    '    // Pass 7b: real rail widget against stub chain data. Selection\n'
    '    // and add-stage requests routed through this page so the\n'
    '    // future engine wiring (Pass 8) replaces stub handlers cleanly.\n'
    '    auto *rail = new ChainRailWidget(this);\n'
    '    rail->setFixedHeight(kChainRailHeight);\n'
    '    rail->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);\n'
    '\n'
    '    connect(rail, &ChainRailWidget::stageSelected,\n'
    '            this, &ChainStudioPage::onRailStageSelected);\n'
    '    connect(rail, &ChainRailWidget::addStageRequested,\n'
    '            this, &ChainStudioPage::onRailAddStageRequested);\n'
    '\n'
    '    // Populate stub data so the rail renders with something to\n'
    '    // look at during Pass 7b review.\n'
    '    buildStubChain();\n'
    '    rail->setChain(stubChain_);\n'
    '    if (!stubChain_.stages.isEmpty())\n'
    '    {\n'
    '        selectedStageId_ = stubChain_.stages.first().id;\n'
    '        rail->setSelectedStageId(selectedStageId_);\n'
    '    }\n'
    '    // canAddStage rule lives in ChainEngine; for stub mode we\n'
    '    // mirror it locally: true iff last stage is Locked (or empty).\n'
    '    const bool canAdd = stubChain_.stages.isEmpty() ||\n'
    '        stubChain_.stages.back().status == StageStatus::Locked;\n'
    '    rail->setCanAddStage(canAdd);\n'
    '\n'
    '    return rail;\n'
    '}\n'
)

# Append the stub-builder + slot impls at the end of the namespace.
CPP_NAMESPACE_TAIL_ANCHOR = (
    '} // namespace spellvision::chain\n'
)

CPP_NAMESPACE_TAIL_REPLACEMENT = (
    '\n'
    f'// --- {MARKER} ---\n'
    '\n'
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
    '\n'
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
    '\n'
    'void ChainStudioPage::onRailAddStageRequested()\n'
    '{\n'
    '    // Pass 7d will show a kind-picker menu here. Pass 8 wires the\n'
    '    // engine call. Pass 7b is a no-op stub so the button is\n'
    '    // clickable without throwing.\n'
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
    text = replace_once(text, CPP_INCLUDE_ANCHOR, CPP_INCLUDE_REPLACEMENT, "includes block")
    text = replace_once(text, CPP_BUILDRAIL_ANCHOR, CPP_BUILDRAIL_REPLACEMENT, "buildChainRail body")
    text = replace_once(text, CPP_NAMESPACE_TAIL_ANCHOR, CPP_NAMESPACE_TAIL_REPLACEMENT, "namespace tail")
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
    print("Build with .\\scripts\\dev\\run_ui.ps1")
    print("Page is still not routed into the shell — Pass 9 does that.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
