"""
SpellVision — Sprint MOCKUP Pass 3: Disclosure promotion + grid pairing.

Three concerns, one pass (as requested):

1. SAMPLER & SCHEDULER -> own collapsed-by-default disclosure card
   The Aspect / Image Sampler / Image Scheduler / Video Sampler /
   Video Scheduler cells live in samplerSchedulerLayout_, which is
   added directly into the Quick Controls card. This pass:
     - creates a new "SamplerSchedulerCard" with the same
       header+toggle disclosure pattern as OutputQueueCard/AdvancedCard
     - moves samplerSchedulerLayout_ into that card instead of
       quickControlsLayout
     - wires a samplerSchedulerForceOpen_ flag + collapse logic into
       updateAdaptiveLayout()

2. LTX LAUNCH OPTIONS -> own collapsed-by-default disclosure card
   ltxLaunchOptionsPanel_ is currently created as a bare card and
   added straight into quickControlsLayout. This pass wraps it in a
   disclosure header (toggle button, collapsed by default) and moves
   it out of the Quick Controls flow into its own slot in leftLayout,
   right after the Quick Controls card. It still respects the
   existing video-family visibility logic (only shown for LTX video).

3. GRID PAIRING RETUNE
   configureAdaptivePair() only goes two-column when
   `wideLeftRail && !constrainedLeftHeight`, where wideLeftRail needs
   leftRailWidth >= 410 AND mode == Wide, and constrainedLeftHeight is
   true for any rail height < 900. In practice the left rail is ~370px
   and height is usually < 900, so Width|Height and Steps|CFG never
   pair side-by-side — they always stack. The mockup wants them as a
   2-col mini-grid.
   This pass adds a width-only `pairableLeftRail` (>= 360px, enough
   for two 110px-min fields + 8px gap) and switches the size/steps
   pairs to use it, independent of height. Sampler/Scheduler and
   Seed/Batch groups keep stacking (they were never paired).

Order note: this pass anchors against the POST-Pass-2 file state
(title "Generation Controls", makeStackedField present). Apply Pass 2
before Pass 3.

Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "SPRINT MOCKUP PASS 3 DISCLOSURE PROMOTION"
BACKUP_SUFFIX = ".pre_sprint_mockup_pass3.bak"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Anchor not found: {label}")
    if text.count(old) > 1:
        raise RuntimeError(f"Anchor not unique ({text.count(old)}x): {label}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 1. ImageGenerationPage.h — new members
# ---------------------------------------------------------------------------

HEADER_TOGGLE_ANCHOR = "    QToolButton *advancedToggleButton_ = nullptr;\n"
HEADER_TOGGLE_INSERT = (
    f"    // --- {MARKER}: disclosure toggles ---\n"
    "    QToolButton *samplerSchedulerToggleButton_ = nullptr;\n"
    "    QToolButton *ltxLaunchToggleButton_ = nullptr;\n"
)

HEADER_FLAG_ANCHOR = "    bool advancedForceOpen_ = false;\n"
HEADER_FLAG_INSERT = (
    f"    // --- {MARKER}: disclosure force-open flags ---\n"
    "    bool samplerSchedulerForceOpen_ = false;\n"
    "    bool ltxLaunchForceOpen_ = false;\n"
)


def patch_header(project: Path) -> None:
    path = project / "qt_ui" / "ImageGenerationPage.h"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)
    text = replace_once(text, HEADER_TOGGLE_ANCHOR,
                        HEADER_TOGGLE_ANCHOR + HEADER_TOGGLE_INSERT,
                        "header toggle members")
    text = replace_once(text, HEADER_FLAG_ANCHOR,
                        HEADER_FLAG_ANCHOR + HEADER_FLAG_INSERT,
                        "header force-open flags")
    write_text(path, text)
    print(f"  Patched: {path.name}")


# ---------------------------------------------------------------------------
# 2. ImageGenerationPage.cpp
# ---------------------------------------------------------------------------

# 2a. Create the SamplerSchedulerCard right after the Quick Controls card
#     header+hint (anchored on the post-Pass-2 "Core generation controls."
#     line + the maxheight + addWidget that follow it), and BEFORE the
#     LTX panel creation.

QC_HEAD_ANCHOR = (
    '    quickControlsLayout->addWidget(createSectionTitle(QStringLiteral("Generation Controls"), quickControlsCard));\n'
    '    auto *quickControlsHint = createSectionBody(QStringLiteral("Core generation controls."), quickControlsCard);\n'
    '    quickControlsHint->setMaximumHeight(22);\n'
    '    quickControlsLayout->addWidget(quickControlsHint);\n'
)

QC_HEAD_REPLACEMENT = (
    '    quickControlsLayout->addWidget(createSectionTitle(QStringLiteral("Generation Controls"), quickControlsCard));\n'
    '    auto *quickControlsHint = createSectionBody(QStringLiteral("Core controls stay visible. The rest collapses."), quickControlsCard);\n'
    '    quickControlsHint->setMaximumHeight(22);\n'
    '    quickControlsLayout->addWidget(quickControlsHint);\n'
    '\n'
    f'    // --- {MARKER}: Sampler & Scheduler disclosure card ---\n'
    '    auto *samplerSchedulerCard = createCard(QStringLiteral("SamplerSchedulerCard"));\n'
    '    auto *samplerSchedulerCardLayout = new QVBoxLayout(samplerSchedulerCard);\n'
    '    samplerSchedulerCardLayout->setContentsMargins(\n'
    '        ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),\n'
    '        ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),\n'
    '        ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),\n'
    '        ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));\n'
    '    samplerSchedulerCardLayout->setSpacing(8);\n'
    '    auto *samplerSchedulerHeader = new QWidget(samplerSchedulerCard);\n'
    '    auto *samplerSchedulerHeaderLayout = new QHBoxLayout(samplerSchedulerHeader);\n'
    '    samplerSchedulerHeaderLayout->setContentsMargins(0, 0, 0, 0);\n'
    '    samplerSchedulerHeaderLayout->setSpacing(8);\n'
    '    samplerSchedulerHeaderLayout->addWidget(createSectionTitle(QStringLiteral("Sampler & Scheduler"), samplerSchedulerCard), 1);\n'
    '    samplerSchedulerToggleButton_ = new QToolButton(samplerSchedulerCard);\n'
    '    samplerSchedulerToggleButton_->setObjectName(QStringLiteral("InspectorSectionToggle"));\n'
    '    samplerSchedulerToggleButton_->setToolButtonStyle(Qt::ToolButtonTextOnly);\n'
    '    samplerSchedulerToggleButton_->setText(QStringLiteral("Open"));\n'
    '    samplerSchedulerToggleButton_->setMinimumWidth(72);\n'
    '    samplerSchedulerToggleButton_->setMinimumHeight(26);\n'
    '    samplerSchedulerToggleButton_->setFixedHeight(26);\n'
    '    samplerSchedulerToggleButton_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);\n'
    '    samplerSchedulerHeaderLayout->addWidget(samplerSchedulerToggleButton_, 0, Qt::AlignRight | Qt::AlignVCenter);\n'
    '    samplerSchedulerCardLayout->addWidget(samplerSchedulerHeader);\n'
    '    auto *samplerSchedulerHint = createSectionBody(QStringLiteral("Sampler, scheduler and aspect. Collapsed to protect rail space."), samplerSchedulerCard);\n'
    '    samplerSchedulerHint->setObjectName(QStringLiteral("SamplerSchedulerBodyHint"));\n'
    '    samplerSchedulerHint->setMaximumHeight(24);\n'
    '    samplerSchedulerCardLayout->addWidget(samplerSchedulerHint);\n'
    '    connect(samplerSchedulerToggleButton_, &QToolButton::clicked, this, [this](bool) {\n'
    '        samplerSchedulerForceOpen_ = !samplerSchedulerForceOpen_;\n'
    '        updateAdaptiveLayout();\n'
    '        if (!samplerSchedulerForceOpen_ || !leftScrollArea_)\n'
    '            return;\n'
    '        QTimer::singleShot(0, this, [this]() {\n'
    '            QWidget *card = findChild<QWidget *>(QStringLiteral("SamplerSchedulerCard"));\n'
    '            if (!card || !leftScrollArea_)\n'
    '                return;\n'
    '            leftScrollArea_->ensureWidgetVisible(card, 4, 8);\n'
    '        });\n'
    '    });\n'
)


# 2b. The samplerSchedulerLayout_ is currently added into
#     quickControlsLayout. Re-home it into the new SamplerSchedulerCard
#     instead, and add the card to leftLayout right after the Quick
#     Controls card. The four-addLayout block currently reads:
#         quickControlsLayout->addLayout(samplerSchedulerLayout_);
#         quickControlsLayout->addLayout(sizeLayout_);
#         quickControlsLayout->addLayout(stepsCfgLayout_);
#         quickControlsLayout->addLayout(seedBatchLayout_);

QC_ADDLAYOUT_ANCHOR = (
    '    quickControlsLayout->addLayout(samplerSchedulerLayout_);\n'
    '    quickControlsLayout->addLayout(sizeLayout_);\n'
    '    quickControlsLayout->addLayout(stepsCfgLayout_);\n'
    '    quickControlsLayout->addLayout(seedBatchLayout_);\n'
)

QC_ADDLAYOUT_REPLACEMENT = (
    f'    // --- {MARKER}: samplerSchedulerLayout_ re-homed into its own card ---\n'
    '    samplerSchedulerCardLayout->addLayout(samplerSchedulerLayout_);\n'
    '    quickControlsLayout->addLayout(sizeLayout_);\n'
    '    quickControlsLayout->addLayout(stepsCfgLayout_);\n'
    '    quickControlsLayout->addLayout(seedBatchLayout_);\n'
)


# 2c. The Quick Controls card is added to leftLayout. Find that line and
#     insert the new SamplerSchedulerCard right after it. The LTX panel
#     was being added inside quickControlsLayout; we move it out too.
#
#     Current (post-Pass-2): line ~849
#         ltxLaunchOptionsPanel_->setVisible(isVideoMode() && resolvedVideoFamilyToken() == QStringLiteral("ltx"));
#         quickControlsLayout->addWidget(ltxLaunchOptionsPanel_);
#
#     We change the addWidget target and wrap LTX with a disclosure
#     header. Because the panel widgets are already children of
#     ltxLaunchOptionsPanel_, we only need to (a) insert a disclosure
#     header at the TOP of its layout and (b) re-parent the card into
#     leftLayout. Simplest robust approach: keep ltxLaunchOptionsPanel_
#     as-is but give it a toggle in its existing header area and add it
#     to leftLayout after the SamplerSchedulerCard.

LTX_ADD_ANCHOR = (
    '    ltxLaunchOptionsPanel_->setVisible(isVideoMode() && resolvedVideoFamilyToken() == QStringLiteral("ltx"));\n'
    '    quickControlsLayout->addWidget(ltxLaunchOptionsPanel_);\n'
)

LTX_ADD_REPLACEMENT = (
    f'    // --- {MARKER}: LTX panel moved out of Quick Controls flow ---\n'
    '    ltxLaunchOptionsPanel_->setVisible(isVideoMode() && resolvedVideoFamilyToken() == QStringLiteral("ltx"));\n'
)


# 2d. The LTX panel's title is a plain section title. Replace it with a
#     header row that carries a disclosure toggle, mirroring the other
#     cards. The current line (post-Pass-2 unchanged from original):
#         ltxLaunchLayout->addWidget(createSectionTitle(QStringLiteral("LTX Launch Options"), ltxLaunchOptionsPanel_));

LTX_TITLE_ANCHOR = (
    '    ltxLaunchLayout->addWidget(createSectionTitle(QStringLiteral("LTX Launch Options"), ltxLaunchOptionsPanel_));\n'
)

LTX_TITLE_REPLACEMENT = (
    f'    // --- {MARKER}: LTX disclosure header ---\n'
    '    auto *ltxLaunchHeader = new QWidget(ltxLaunchOptionsPanel_);\n'
    '    auto *ltxLaunchHeaderLayout = new QHBoxLayout(ltxLaunchHeader);\n'
    '    ltxLaunchHeaderLayout->setContentsMargins(0, 0, 0, 0);\n'
    '    ltxLaunchHeaderLayout->setSpacing(8);\n'
    '    ltxLaunchHeaderLayout->addWidget(createSectionTitle(QStringLiteral("LTX Launch Options"), ltxLaunchOptionsPanel_), 1);\n'
    '    ltxLaunchToggleButton_ = new QToolButton(ltxLaunchOptionsPanel_);\n'
    '    ltxLaunchToggleButton_->setObjectName(QStringLiteral("InspectorSectionToggle"));\n'
    '    ltxLaunchToggleButton_->setToolButtonStyle(Qt::ToolButtonTextOnly);\n'
    '    ltxLaunchToggleButton_->setText(QStringLiteral("Open"));\n'
    '    ltxLaunchToggleButton_->setMinimumWidth(72);\n'
    '    ltxLaunchToggleButton_->setMinimumHeight(26);\n'
    '    ltxLaunchToggleButton_->setFixedHeight(26);\n'
    '    ltxLaunchToggleButton_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);\n'
    '    ltxLaunchHeaderLayout->addWidget(ltxLaunchToggleButton_, 0, Qt::AlignRight | Qt::AlignVCenter);\n'
    '    ltxLaunchLayout->addWidget(ltxLaunchHeader);\n'
    '    connect(ltxLaunchToggleButton_, &QToolButton::clicked, this, [this](bool) {\n'
    '        ltxLaunchForceOpen_ = !ltxLaunchForceOpen_;\n'
    '        updateAdaptiveLayout();\n'
    '        if (!ltxLaunchForceOpen_ || !leftScrollArea_)\n'
    '            return;\n'
    '        QTimer::singleShot(0, this, [this]() {\n'
    '            QWidget *card = findChild<QWidget *>(QStringLiteral("LtxLaunchOptionsPanel"));\n'
    '            if (!card || !leftScrollArea_)\n'
    '                return;\n'
    '            leftScrollArea_->ensureWidgetVisible(card, 4, 8);\n'
    '        });\n'
    '    });\n'
)


# 2e. Add the two new cards to leftLayout. We anchor on where the
#     Quick Controls card is added to leftLayout. Find that addWidget
#     (post-Pass-2; original line ~931 area). It reads:
#         leftLayout->addWidget(quickControlsCard);
#     We insert the sampler/scheduler + LTX cards right after it.

LEFTLAYOUT_QC_ANCHOR = "    leftLayout->addWidget(quickControlsCard);\n"

LEFTLAYOUT_QC_REPLACEMENT = (
    "    leftLayout->addWidget(quickControlsCard);\n"
    f"    // --- {MARKER}: disclosure cards added after Quick Controls ---\n"
    "    leftLayout->addWidget(samplerSchedulerCard);\n"
    "    leftLayout->addWidget(ltxLaunchOptionsPanel_);\n"
)


# 2f. Adaptive collapse for the two new cards. Mirror the AdvancedCard
#     block. Anchor on the end of the AdvancedCard collapse block.

ADAPTIVE_ANCHOR = (
    '    if (QFrame *advancedCard = findChild<QFrame *>(QStringLiteral("AdvancedControlsCard")))\n'
    '    {\n'
    '        const bool advancedAutoCollapsed = true;\n'
    '        const bool collapseAdvanced = advancedAutoCollapsed && !advancedForceOpen_;\n'
    '        advancedCard->setMinimumHeight(collapseAdvanced ? 58 : 0);\n'
    '        advancedCard->setMaximumHeight(collapseAdvanced ? 58 : QWIDGETSIZE_MAX);\n'
    '        advancedCard->setToolTip(collapseAdvanced\n'
    '            ? QStringLiteral("Advanced controls are collapsed by default to keep the prompt rail usable.")\n'
    '            : QStringLiteral("Advanced controls."));\n'
    '        if (advancedToggleButton_)\n'
    '        {\n'
    '            advancedToggleButton_->setVisible(advancedCard->isVisible());\n'
    '            advancedToggleButton_->setMinimumWidth(collapseAdvanced ? 72 : 74);\n'
    '            advancedToggleButton_->setText(collapseAdvanced ? QStringLiteral("Open") : QStringLiteral("Close"));\n'
    '            advancedToggleButton_->setToolTip(collapseAdvanced\n'
    '                ? QStringLiteral("Expand advanced controls.")\n'
    '                : QStringLiteral("Collapse advanced controls."));\n'
    '        }\n'
    '    }\n'
)

ADAPTIVE_INSERT = (
    f'\n    // --- {MARKER}: Sampler & Scheduler collapse ---\n'
    '    if (QFrame *samplerSchedulerCard = findChild<QFrame *>(QStringLiteral("SamplerSchedulerCard")))\n'
    '    {\n'
    '        const bool collapseSS = !samplerSchedulerForceOpen_;\n'
    '        samplerSchedulerCard->setMinimumHeight(collapseSS ? 58 : 0);\n'
    '        samplerSchedulerCard->setMaximumHeight(collapseSS ? 58 : QWIDGETSIZE_MAX);\n'
    '        samplerSchedulerCard->setToolTip(collapseSS\n'
    '            ? QStringLiteral("Sampler & Scheduler is collapsed to protect prompt and canvas space. Click Open to expand.")\n'
    '            : QStringLiteral("Sampler & Scheduler controls."));\n'
    '        if (samplerSchedulerToggleButton_)\n'
    '        {\n'
    '            samplerSchedulerToggleButton_->setVisible(true);\n'
    '            samplerSchedulerToggleButton_->setMinimumWidth(collapseSS ? 72 : 74);\n'
    '            samplerSchedulerToggleButton_->setText(collapseSS ? QStringLiteral("Open") : QStringLiteral("Close"));\n'
    '            samplerSchedulerToggleButton_->setToolTip(collapseSS\n'
    '                ? QStringLiteral("Expand sampler and scheduler controls.")\n'
    '                : QStringLiteral("Collapse sampler and scheduler controls."));\n'
    '        }\n'
    '    }\n'
    '\n'
    f'    // --- {MARKER}: LTX Launch Options collapse (LTX video only) ---\n'
    '    if (QFrame *ltxCard = findChild<QFrame *>(QStringLiteral("LtxLaunchOptionsPanel")))\n'
    '    {\n'
    '        const bool ltxApplicable = isVideoMode() && resolvedVideoFamilyToken() == QStringLiteral("ltx");\n'
    '        ltxCard->setVisible(ltxApplicable);\n'
    '        if (ltxApplicable)\n'
    '        {\n'
    '            const bool collapseLtx = !ltxLaunchForceOpen_;\n'
    '            ltxCard->setMinimumHeight(collapseLtx ? 58 : 0);\n'
    '            ltxCard->setMaximumHeight(collapseLtx ? 58 : QWIDGETSIZE_MAX);\n'
    '            ltxCard->setToolTip(collapseLtx\n'
    '                ? QStringLiteral("LTX launch options are collapsed by default. Click Open to expand.")\n'
    '                : QStringLiteral("LTX launch options."));\n'
    '            if (ltxLaunchToggleButton_)\n'
    '            {\n'
    '                ltxLaunchToggleButton_->setVisible(true);\n'
    '                ltxLaunchToggleButton_->setMinimumWidth(collapseLtx ? 72 : 74);\n'
    '                ltxLaunchToggleButton_->setText(collapseLtx ? QStringLiteral("Open") : QStringLiteral("Close"));\n'
    '                ltxLaunchToggleButton_->setToolTip(collapseLtx\n'
    '                    ? QStringLiteral("Expand LTX launch options.")\n'
    '                    : QStringLiteral("Collapse LTX launch options."));\n'
    '            }\n'
    '        }\n'
    '    }\n'
)


# 2g. Grid pairing retune. Add a width-only `pairableLeftRail` and use
#     it for the size/steps pairs.

PAIR_TUNE_ANCHOR = (
    '    const bool wideLeftRail = (mode == AdaptiveLayoutMode::Wide) && leftRailWidth >= 410;\n'
    '    const bool constrainedLeftHeight = leftRailHeight > 0 && leftRailHeight < 900;\n'
)

PAIR_TUNE_REPLACEMENT = (
    '    const bool wideLeftRail = (mode == AdaptiveLayoutMode::Wide) && leftRailWidth >= 410;\n'
    '    const bool constrainedLeftHeight = leftRailHeight > 0 && leftRailHeight < 900;\n'
    f'    // --- {MARKER}: width-only pairing gate for size/steps mini-grid ---\n'
    '    // Two 110px-min fields + 8px gap fit comfortably above ~360px.\n'
    '    // Height is irrelevant for a 2-col pair, so this gate ignores it.\n'
    '    const bool pairableLeftRail = (mode != AdaptiveLayoutMode::Compact) && leftRailWidth >= 360;\n'
)

PAIR_USE_ANCHOR = (
    '    auto configureAdaptivePair = [wideLeftRail, constrainedLeftHeight](QBoxLayout *layout) {\n'
    '        if (!layout)\n'
    '            return;\n'
    '        const bool useTwoColumns = wideLeftRail && !constrainedLeftHeight;\n'
    '        layout->setDirection(useTwoColumns ? QBoxLayout::LeftToRight : QBoxLayout::TopToBottom);\n'
    '        layout->setSpacing(useTwoColumns ? 8 : 3);\n'
    '    };\n'
)

PAIR_USE_REPLACEMENT = (
    f'    // --- {MARKER}: pair on width alone, not height ---\n'
    '    auto configureAdaptivePair = [pairableLeftRail](QBoxLayout *layout) {\n'
    '        if (!layout)\n'
    '            return;\n'
    '        const bool useTwoColumns = pairableLeftRail;\n'
    '        layout->setDirection(useTwoColumns ? QBoxLayout::LeftToRight : QBoxLayout::TopToBottom);\n'
    '        layout->setSpacing(useTwoColumns ? 8 : 3);\n'
    '    };\n'
)


def patch_image_generation_cpp(project: Path) -> None:
    path = project / "qt_ui" / "ImageGenerationPage.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)

    text = replace_once(text, QC_HEAD_ANCHOR, QC_HEAD_REPLACEMENT,
                        "Quick Controls header (SamplerSchedulerCard creation)")
    text = replace_once(text, QC_ADDLAYOUT_ANCHOR, QC_ADDLAYOUT_REPLACEMENT,
                        "Quick Controls addLayout block")
    text = replace_once(text, LTX_ADD_ANCHOR, LTX_ADD_REPLACEMENT,
                        "LTX add-to-quickControls")
    text = replace_once(text, LTX_TITLE_ANCHOR, LTX_TITLE_REPLACEMENT,
                        "LTX section title -> disclosure header")
    text = replace_once(text, LEFTLAYOUT_QC_ANCHOR, LEFTLAYOUT_QC_REPLACEMENT,
                        "leftLayout add Quick Controls (insert disclosure cards)")
    text = replace_once(text, ADAPTIVE_ANCHOR, ADAPTIVE_ANCHOR + ADAPTIVE_INSERT,
                        "adaptive collapse block (Advanced anchor)")
    text = replace_once(text, PAIR_TUNE_ANCHOR, PAIR_TUNE_REPLACEMENT,
                        "pairableLeftRail declaration")
    text = replace_once(text, PAIR_USE_ANCHOR, PAIR_USE_REPLACEMENT,
                        "configureAdaptivePair lambda")

    write_text(path, text)
    print(f"  Patched: {path.name}")


# ---------------------------------------------------------------------------
# 3. ThemeManager.cpp — make the new cards reuse the existing card chrome
# ---------------------------------------------------------------------------
#
# The shared card selector currently lists:
#   QFrame#PromptCard, QFrame#InputCard, QFrame#QuickControlsCard,
#   QFrame#OutputQueueCard, QFrame#AdvancedCard, QFrame#SettingsCard,
#   QFrame#OutputCard, QFrame#CanvasCard
# and a border-color override list:
#   QFrame#QuickControlsCard, QFrame#OutputQueueCard, QFrame#AdvancedCard,
#   QFrame#SettingsCard, QFrame#OutputCard
# Add SamplerSchedulerCard and LtxLaunchOptionsPanel to both so they
# get the same gradient/border treatment as their sibling disclosures.

THEME_CARD_LIST_ANCHOR = (
    '"QFrame#PromptCard, QFrame#InputCard, QFrame#QuickControlsCard, QFrame#OutputQueueCard, QFrame#AdvancedCard, QFrame#SettingsCard, QFrame#OutputCard, QFrame#CanvasCard {"'
)
THEME_CARD_LIST_NEW = (
    '"QFrame#PromptCard, QFrame#InputCard, QFrame#QuickControlsCard, QFrame#SamplerSchedulerCard, QFrame#LtxLaunchOptionsPanel, QFrame#OutputQueueCard, QFrame#AdvancedCard, QFrame#SettingsCard, QFrame#OutputCard, QFrame#CanvasCard {"'
)

THEME_BORDER_LIST_ANCHOR = (
    '"QFrame#QuickControlsCard, QFrame#OutputQueueCard, QFrame#AdvancedCard, QFrame#SettingsCard, QFrame#OutputCard { border-color: %11; }"'
)
THEME_BORDER_LIST_NEW = (
    '"QFrame#QuickControlsCard, QFrame#SamplerSchedulerCard, QFrame#LtxLaunchOptionsPanel, QFrame#OutputQueueCard, QFrame#AdvancedCard, QFrame#SettingsCard, QFrame#OutputCard { border-color: %11; }"'
)


def patch_theme_manager(project: Path) -> None:
    path = project / "qt_ui" / "ThemeManager.cpp"
    if not path.exists():
        print(f"  Skipped (not found): {path}")
        return
    text = read_text(path)
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return
    backup_once(path)
    text = replace_once(text, THEME_CARD_LIST_ANCHOR, THEME_CARD_LIST_NEW,
                        "shared card selector list")
    text = replace_once(text, THEME_BORDER_LIST_ANCHOR, THEME_BORDER_LIST_NEW,
                        "card border-color selector list")
    # Stamp marker for idempotency.
    text = text.replace(
        '"QLabel#SectionTitle',
        f'/* {MARKER} */ "QLabel#SectionTitle',
        1,
    )
    write_text(path, text)
    print(f"  Patched: {path.name}")


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------

def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("ImageGenerationPage.h")
    patch_header(project)
    print()
    print("ImageGenerationPage.cpp")
    patch_image_generation_cpp(project)
    print()
    print("ThemeManager.cpp")
    patch_theme_manager(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next: rebuild with .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
