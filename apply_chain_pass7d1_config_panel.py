r"""
SpellVision — Chain Studio Pass 7d.1: config panel.

Three coordinated edits:

1. CMakeLists.txt — register ChainConfigPanelWidget.h/.cpp.

2. ChainStudioPage.h — forward-declare ChainConfigPanelWidget in the
   chain namespace (same pattern Pass 7c used for ChainCanvasWidget).
   Add the configPanelWidget_ member pointer + onConfigRegenerateRequested
   slot declaration.

3. ChainStudioPage.cpp — include the panel header; replace buildConfigPanel's
   placeholder body with a real ChainConfigPanelWidget; wire its
   regenerateRequested signal to the stub handler; bind it to the stub chain
   + selection; also update onRailStageSelected and the two stub mutation
   slots so config panel refreshes alongside rail and canvas.

Reuse-first: the panel uses ClickOnlyComboBox from spellvision::widgets and
mirrors ImageGenerationPage's local configureComboBox / configureSpinBox /
configureDoubleSpinBox helpers (duplicated locally; Pass 10 polish can
promote them to a shared header).

Full-file rewrite of ChainStudioPage.cpp (avoids the CRLF/anchor mismatch
problems Pass 7c hit). Surgical edits to ChainStudioPage.h and CMakeLists.txt.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "CHAIN STUDIO PASS 7D1 CONFIG PANEL"
CMAKE_BACKUP = ".pre_pass7d1_cmake.bak"
HDR_BACKUP   = ".pre_pass7d1_page_hdr.bak"
CPP_BACKUP   = ".pre_pass7d1_page_cpp.bak"


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
# 1. CMakeLists.txt — append after Pass 7C
# =============================================================================

CMAKE_ANCHOR = (
    "    # --- CHAIN STUDIO PASS 7C CANVAS CMAKE REGISTRATION ---\n"
    "    qt_ui/chain/ChainCanvasWidget.h\n"
    "    qt_ui/chain/ChainCanvasWidget.cpp\n"
)

CMAKE_REPLACEMENT = (
    "    # --- CHAIN STUDIO PASS 7C CANVAS CMAKE REGISTRATION ---\n"
    "    qt_ui/chain/ChainCanvasWidget.h\n"
    "    qt_ui/chain/ChainCanvasWidget.cpp\n"
    f"    # --- {MARKER} CMAKE REGISTRATION ---\n"
    "    qt_ui/chain/ChainConfigPanelWidget.h\n"
    "    qt_ui/chain/ChainConfigPanelWidget.cpp\n"
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
    backup_once(path, CMAKE_BACKUP)
    text = replace_once(text, CMAKE_ANCHOR, CMAKE_REPLACEMENT,
                        "Pass 7C CMake block tail")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# =============================================================================
# 2. ChainStudioPage.h — forward-decl + member + slot
# =============================================================================

# Insert the forward-decl beside ChainCanvasWidget's. Both live in the
# chain namespace; one line each.
HDR_FWD_ANCHOR = (
    "// --- CHAIN STUDIO PASS 7C CANVAS: forward-declare ChainCanvasWidget ---\n"
    "class ChainCanvasWidget;\n"
)

HDR_FWD_REPLACEMENT = (
    "// --- CHAIN STUDIO PASS 7C CANVAS: forward-declare ChainCanvasWidget ---\n"
    "class ChainCanvasWidget;\n"
    f"// --- {MARKER}: forward-declare ChainConfigPanelWidget ---\n"
    "class ChainConfigPanelWidget;\n"
)

# Insert member + slot inside the class, right after the canvas member +
# slot block. Pattern matches the existing layout.
HDR_MEMBER_ANCHOR = (
    "    // --- CHAIN STUDIO PASS 7C CANVAS ---\n"
    "    // Cached pointer to the canvas widget so the rail's selection\n"
    "    // handler can route to it. Pass 8 will replace this with a\n"
    "    // proper engine-driven signal flow.\n"
    "    ChainCanvasWidget *canvasWidget_ = nullptr;\n"
    "    void onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx);\n"
    "    void onCanvasLockRequested(const QString &stageId);\n"
    "};\n"
)

HDR_MEMBER_REPLACEMENT = (
    "    // --- CHAIN STUDIO PASS 7C CANVAS ---\n"
    "    // Cached pointer to the canvas widget so the rail's selection\n"
    "    // handler can route to it. Pass 8 will replace this with a\n"
    "    // proper engine-driven signal flow.\n"
    "    ChainCanvasWidget *canvasWidget_ = nullptr;\n"
    "    void onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx);\n"
    "    void onCanvasLockRequested(const QString &stageId);\n"
    "\n"
    f"    // --- {MARKER} ---\n"
    "    // Cached pointer to the config panel so the rail's selection\n"
    "    // handler can route to it. Pass 8 will harvest the panel's\n"
    "    // edited config when Regenerate is clicked and route to\n"
    "    // engine.regenerate(stageId, config).\n"
    "    ChainConfigPanelWidget *configPanelWidget_ = nullptr;\n"
    "    void onConfigRegenerateRequested(const QString &stageId);\n"
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
    backup_once(path, HDR_BACKUP)
    text = replace_once(text, HDR_FWD_ANCHOR, HDR_FWD_REPLACEMENT,
                        "forward-decl block")
    text = replace_once(text, HDR_MEMBER_ANCHOR, HDR_MEMBER_REPLACEMENT,
                        "canvas member tail")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# =============================================================================
# 3. ChainStudioPage.cpp — full-file rewrite
# =============================================================================
#
# Full rewrite avoids the CRLF/anchor mismatch issues that bit Pass 7c
# fixups three times. The new file integrates the config panel into
# buildConfigPanel(), routes selection from onRailStageSelected to all
# three child widgets (rail/canvas/config), and updates the lock + var-
# selection stubs so the config panel sees the same updated chain.

PAGE_CPP = r'''#include "chain/ChainStudioPage.h"

#include "ThemeManager.h"
// --- CHAIN STUDIO PASS 7B RAIL ---
#include "chain/ChainRailWidget.h"
// --- CHAIN STUDIO PASS 7C CANVAS ---
#include "chain/ChainCanvasWidget.h"
// --- ''' + MARKER + r''' ---
#include "chain/ChainConfigPanelWidget.h"
#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QDateTime>
#include <QUuid>

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QSizePolicy>
#include <QVBoxLayout>

namespace spellvision::chain
{

namespace
{

constexpr int kTopStripHeight   = 56;
constexpr int kChainRailHeight  = 64;
constexpr int kConfigPanelWidth = 318;

QString placeholderLabelStyle()
{
    const auto &tm = ThemeManager::instance();
    return QStringLiteral(
        "color: %1; "
        "font-size: 11px; "
        "letter-spacing: 0.6px; "
        "font-weight: 600;"
    ).arg(tm.textMutedColor().name());
}

// Mirrors MainWindow.cpp's brandIconCandidates pattern (lines 414-442)
// to find SpellVision.{jpg,jpeg,png} wherever it actually lives.
QString findBrandImage(const QString &basename)
{
    const QStringList starts = {
        QCoreApplication::applicationDirPath(),
        QDir::currentPath()
    };
    const QStringList suffixes = {
        QStringLiteral(".jpg"),
        QStringLiteral(".jpeg"),
        QStringLiteral(".png"),
    };
    const QStringList relPrefixes = {
        QStringLiteral("qt_ui/icons/"),
        QStringLiteral("icons/"),
        QStringLiteral(""),
    };
    for (const QString &start : starts)
    {
        QDir dir(start);
        for (int depth = 0; depth < 7; ++depth)
        {
            for (const QString &prefix : relPrefixes)
            {
                for (const QString &suffix : suffixes)
                {
                    const QString candidate = dir.filePath(prefix + basename + suffix);
                    if (QFileInfo::exists(candidate))
                        return QDir::cleanPath(candidate);
                }
            }
            if (!dir.cdUp())
                break;
        }
    }
    return QString();
}

} // anonymous namespace

ChainStudioPage::ChainStudioPage(QWidget *parent)
    : QWidget(parent)
{
    const auto &tm = ThemeManager::instance();
    setAutoFillBackground(true);
    QPalette pal = palette();
    pal.setColor(QPalette::Window, tm.background1Color());
    setPalette(pal);

    auto *root = new QVBoxLayout(this);
    const int outerVert = tm.spacing(ThemeManager::Spacing::Snug);
    const int outerHorz = tm.spacing(ThemeManager::Spacing::Card);
    root->setContentsMargins(outerHorz, outerVert, outerHorz, outerVert);
    root->setSpacing(tm.spacing(ThemeManager::Spacing::Snug));

    topStrip_  = buildTopStrip();
    chainRail_ = buildChainRail();

    auto *mainRow = new QHBoxLayout;
    mainRow->setContentsMargins(0, 0, 0, 0);
    mainRow->setSpacing(tm.spacing(ThemeManager::Spacing::Snug));

    canvas_ = buildCanvas();
    configPanel_ = buildConfigPanel();

    mainRow->addWidget(canvas_, 1);
    mainRow->addWidget(configPanel_, 0);

    root->addWidget(topStrip_);
    root->addWidget(chainRail_);
    root->addLayout(mainRow, 1);
}

QWidget *ChainStudioPage::buildTopStrip()
{
    auto *strip = new QFrame(this);
    strip->setFixedHeight(kTopStripHeight);
    strip->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    applyPlaceholderStyle(strip,
        QStringLiteral("TOP STRIP \u2014 upload box + dialog bar + + button (Pass 7d.2)"));
    return strip;
}

QWidget *ChainStudioPage::buildChainRail()
{
    auto *rail = new ChainRailWidget(this);
    rail->setFixedHeight(kChainRailHeight);
    rail->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    connect(rail, &ChainRailWidget::stageSelected,
            this, &ChainStudioPage::onRailStageSelected);
    connect(rail, &ChainRailWidget::addStageRequested,
            this, &ChainStudioPage::onRailAddStageRequested);

    buildStubChain();
    rail->setChain(stubChain_);
    if (!stubChain_.stages.isEmpty())
    {
        selectedStageId_ = stubChain_.stages.first().id;
        rail->setSelectedStageId(selectedStageId_);
    }
    const bool canAdd = stubChain_.stages.isEmpty() ||
        stubChain_.stages.back().status == StageStatus::Locked;
    rail->setCanAddStage(canAdd);

    return rail;
}

QWidget *ChainStudioPage::buildCanvas()
{
    canvasWidget_ = new ChainCanvasWidget(this);
    canvasWidget_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    connect(canvasWidget_, &ChainCanvasWidget::variationSelectionChanged,
            this, &ChainStudioPage::onCanvasVariationSelectionChanged);
    connect(canvasWidget_, &ChainCanvasWidget::lockRequested,
            this, &ChainStudioPage::onCanvasLockRequested);

    canvasWidget_->setChain(stubChain_);
    canvasWidget_->setSelectedStageId(selectedStageId_);

    return canvasWidget_;
}

QWidget *ChainStudioPage::buildConfigPanel()
{
    // --- ''' + MARKER + r''' ---
    // Pass 7d.1: real config panel widget against stub chain data.
    // Selection comes IN via setSelectedStageId() (called from
    // onRailStageSelected). Regenerate requests go OUT via the
    // regenerateRequested signal. Pass 8 will replace the stub handler
    // with the engine.regenerate(stageId, config) call.
    configPanelWidget_ = new ChainConfigPanelWidget(this);
    configPanelWidget_->setFixedWidth(kConfigPanelWidth);
    configPanelWidget_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);

    connect(configPanelWidget_, &ChainConfigPanelWidget::regenerateRequested,
            this, &ChainStudioPage::onConfigRegenerateRequested);

    configPanelWidget_->setChain(stubChain_);
    configPanelWidget_->setSelectedStageId(selectedStageId_);

    return configPanelWidget_;
}

void ChainStudioPage::applyPlaceholderStyle(QWidget *region, const QString &debugLabel)
{
    if (region == nullptr)
        return;

    const auto &tm = ThemeManager::instance();

    region->setStyleSheet(QStringLiteral(
        "QFrame { "
        "  background: %1; "
        "  border: 1px solid %2; "
        "  border-radius: %3px; "
        "}"
    ).arg(tm.surface1Color().name(),
          tm.borderToneColor().name(),
          QString::number(tm.radiusCard())));

    auto *layout = new QVBoxLayout(region);
    const int innerPad = tm.spacing(ThemeManager::Spacing::Snug);
    layout->setContentsMargins(innerPad, tm.spacing(ThemeManager::Spacing::Tight),
                               innerPad, tm.spacing(ThemeManager::Spacing::Tight));
    layout->setSpacing(0);
    layout->addStretch(1);

    auto *label = new QLabel(debugLabel, region);
    label->setStyleSheet(placeholderLabelStyle());
    label->setAlignment(Qt::AlignCenter);
    label->setWordWrap(true);
    layout->addWidget(label, 0, Qt::AlignCenter);

    layout->addStretch(1);
}

void ChainStudioPage::buildStubChain()
{
    const QString brand1 = findBrandImage(QStringLiteral("SpellVision"));
    const QString brand2 = findBrandImage(QStringLiteral("SpellVision2"));
    QStringList stubImages;
    if (!brand1.isEmpty()) stubImages << brand1;
    if (!brand2.isEmpty()) stubImages << brand2;
    if (stubImages.isEmpty())
        stubImages << QString();

    stubChain_ = Chain{};
    stubChain_.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
    stubChain_.createdAt = QDateTime::currentDateTimeUtc();
    stubChain_.updatedAt = stubChain_.createdAt;
    stubChain_.entryKind = EntryKind::DescribedText;

    auto makeStub = [&stubImages](StageKind k, StageStatus s, int varCount, int idx) {
        Stage stage;
        stage.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
        stage.index = idx;
        stage.kind = k;
        stage.status = s;
        stage.config.stageKind = k;
        // --- ''' + MARKER + r''' ---
        // Seed the stub stage's config so the panel has interesting
        // values to show on first render. Pass 8 will harvest engine
        // state instead.
        stage.config.imageSampler   = QStringLiteral("dpmpp_2m");
        stage.config.imageScheduler = QStringLiteral("karras");
        stage.config.steps          = (idx == 0) ? 25 : 30;
        stage.config.cfg            = 7.5;
        stage.config.seed           = (idx == 0) ? 42 : -1;
        stage.config.width          = 1024;
        stage.config.height         = 1024;
        for (int i = 0; i < varCount; ++i)
        {
            Variation v;
            v.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
            v.createdAt = QDateTime::currentDateTimeUtc();
            v.outputPath = stubImages.at(i % stubImages.size());
            stage.variations.append(v);
        }
        if (varCount > 0)
            stage.selectedVarIdx = varCount - 1;
        if (s == StageStatus::Locked && varCount > 0)
            stage.lockedVarIdx = varCount - 1;
        return stage;
    };

    stubChain_.stages.append(makeStub(StageKind::T2I, StageStatus::Locked,    3, 0));
    stubChain_.stages.append(makeStub(StageKind::I2V, StageStatus::Completed, 2, 1));
    stubChain_.stages.append(makeStub(StageKind::I2_3D, StageStatus::Draft,   0, 2));
}

void ChainStudioPage::onRailStageSelected(const QString &stageId)
{
    if (stageId == selectedStageId_)
        return;
    selectedStageId_ = stageId;
    if (auto *rail = qobject_cast<ChainRailWidget *>(chainRail_))
        rail->setSelectedStageId(stageId);
    if (canvasWidget_ != nullptr)
        canvasWidget_->setSelectedStageId(stageId);
    // --- ''' + MARKER + r''' ---
    if (configPanelWidget_ != nullptr)
        configPanelWidget_->setSelectedStageId(stageId);
}

void ChainStudioPage::onRailAddStageRequested()
{
    // Pass 7d.3 will show a kind-picker menu here. Pass 8 wires the
    // engine call.
}

void ChainStudioPage::onCanvasVariationSelectionChanged(const QString &stageId, int newVarIdx)
{
    for (auto &stage : stubChain_.stages)
    {
        if (stage.id != stageId)
            continue;
        if (newVarIdx < 0 || newVarIdx >= stage.variations.size())
            return;
        stage.selectedVarIdx = newVarIdx;
        if (canvasWidget_ != nullptr)
            canvasWidget_->setChain(stubChain_);
        return;
    }
}

void ChainStudioPage::onCanvasLockRequested(const QString &stageId)
{
    for (auto &stage : stubChain_.stages)
    {
        if (stage.id != stageId)
            continue;
        if (stage.status != StageStatus::Completed)
            return;
        stage.status = StageStatus::Locked;
        stage.lockedVarIdx = stage.selectedVarIdx;
        if (auto *rail = qobject_cast<ChainRailWidget *>(chainRail_))
        {
            rail->setChain(stubChain_);
            rail->setSelectedStageId(selectedStageId_);
            const bool canAdd = stubChain_.stages.isEmpty() ||
                stubChain_.stages.back().status == StageStatus::Locked;
            rail->setCanAddStage(canAdd);
        }
        if (canvasWidget_ != nullptr)
            canvasWidget_->setChain(stubChain_);
        // --- ''' + MARKER + r''' ---
        // Config panel needs to know about the status change so it
        // can disable controls + recompute the header subtitle.
        if (configPanelWidget_ != nullptr)
            configPanelWidget_->setChain(stubChain_);
        return;
    }
}

// --- ''' + MARKER + r''' ---

void ChainStudioPage::onConfigRegenerateRequested(const QString &stageId)
{
    // Stub handler: Pass 8 will call engine.regenerate(stageId,
    // editedConfig). For 7d.1 review we just acknowledge the click
    // (the panel logged the request via its signal emission).
    Q_UNUSED(stageId);
}

} // namespace spellvision::chain
'''


def patch_page_cpp(project: Path) -> None:
    path = project / "qt_ui" / "chain" / "ChainStudioPage.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    backup_once(path, CPP_BACKUP)
    crlf = PAGE_CPP.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_bytes(crlf.encode("utf-8"))
    print(f"  Rewrote (CRLF): {path.name}")


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
    print("Save ChainConfigPanelWidget.h/.cpp to qt_ui/chain/ first, then:")
    print("    .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
