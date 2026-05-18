"""
SpellVision — Sprint MOCKUP Pass 4: collapse fix + Advanced name fix.

Screenshot bug
--------------
Collapsed disclosure cards (Sampler & Scheduler, and the now-unfixed
Advanced) only clamp the CARD to 58px via setMaximumHeight. That
visually clips but does NOT hide the body widgets, so the multi-row
body content (Aspect / Image Sampler / Image Scheduler / Video
Sampler / Video Scheduler rows, empty combo boxes) bleeds out under
the header and overlaps the title text.

The OutputQueue/Advanced pattern this was copied from only ever looked
fine because their bodies were a single short hint label. A tall body
exposes the latent flaw.

This pass:

1. SAMPLER & SCHEDULER body gating
   samplerSchedulerLayout_ is a member (QBoxLayout*). In
   updateAdaptiveLayout(), when the card is collapsed, hide every
   widget in samplerSchedulerLayout_ AND the SamplerSchedulerBodyHint
   label; when expanded, show them. The header (title + toggle) stays
   visible because it's added directly to samplerSchedulerCardLayout,
   not samplerSchedulerLayout_.

2. LTX body gating
   The LTX panel adds its body widgets after ltxLaunchHeader. Give
   the header an object name ("LtxLaunchHeader") so the collapse
   logic can walk ltxLaunchOptionsPanel_'s direct children and hide
   everything except the header when collapsed.

3. ADVANCED card name mismatch (pre-existing bug, not introduced by
   any earlier pass)
   The card is created as createCard("AdvancedCard") but the collapse
   logic does findChild("AdvancedControlsCard") — which never matches,
   so the Advanced card has never actually collapsed (visible in
   screenshot 6, fully expanded). Fix the lookup to "AdvancedCard".
   Then also gate its body: walk advancedCard's children, keep the
   header + hint, hide the rest when collapsed.

Note on chipState: verified there are NO chipState remnants. Fixup 3
cleanly swapped to setObjectName(AiChipSet/AiChipAuto) with no dead
references. Nothing to remove there.

Order: apply after Pass 3.
Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "SPRINT MOCKUP PASS 4 COLLAPSE FIX"
BACKUP_SUFFIX = ".pre_sprint_mockup_pass4.bak"


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
# 1. Give the LTX disclosure header an object name so it can be skipped
#    when walking the panel's children to hide the body.
# ---------------------------------------------------------------------------

LTX_HEADER_NAME_ANCHOR = (
    '    auto *ltxLaunchHeader = new QWidget(ltxLaunchOptionsPanel_);\n'
)
LTX_HEADER_NAME_NEW = (
    '    auto *ltxLaunchHeader = new QWidget(ltxLaunchOptionsPanel_);\n'
    f'    ltxLaunchHeader->setObjectName(QStringLiteral("LtxLaunchHeader"));  // {MARKER}\n'
)


# ---------------------------------------------------------------------------
# 2. Sampler & Scheduler collapse block — add body gating.
#    Replace the existing SS collapse block (Pass 3) with one that also
#    hides samplerSchedulerLayout_ contents + the body hint.
# ---------------------------------------------------------------------------

SS_BLOCK_OLD = (
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
)

SS_BLOCK_NEW = (
    '    if (QFrame *samplerSchedulerCard = findChild<QFrame *>(QStringLiteral("SamplerSchedulerCard")))\n'
    '    {\n'
    '        const bool collapseSS = !samplerSchedulerForceOpen_;\n'
    '        samplerSchedulerCard->setMinimumHeight(collapseSS ? 58 : 0);\n'
    '        samplerSchedulerCard->setMaximumHeight(collapseSS ? 58 : QWIDGETSIZE_MAX);\n'
    '        samplerSchedulerCard->setToolTip(collapseSS\n'
    '            ? QStringLiteral("Sampler & Scheduler is collapsed to protect prompt and canvas space. Click Open to expand.")\n'
    '            : QStringLiteral("Sampler & Scheduler controls."));\n'
    f'        // --- {MARKER}: hide body widgets when collapsed (not just clamp height) ---\n'
    '        if (samplerSchedulerLayout_)\n'
    '        {\n'
    '            for (int i = 0; i < samplerSchedulerLayout_->count(); ++i)\n'
    '            {\n'
    '                if (QLayoutItem *it = samplerSchedulerLayout_->itemAt(i))\n'
    '                {\n'
    '                    if (QWidget *w = it->widget())\n'
    '                        w->setVisible(!collapseSS);\n'
    '                }\n'
    '            }\n'
    '        }\n'
    '        if (QLabel *ssHint = findChild<QLabel *>(QStringLiteral("SamplerSchedulerBodyHint")))\n'
    '            ssHint->setVisible(!collapseSS);\n'
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
)


# ---------------------------------------------------------------------------
# 3. LTX collapse block — add body gating (walk panel children, skip header).
# ---------------------------------------------------------------------------

LTX_BLOCK_OLD = (
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
)

LTX_BLOCK_NEW = (
    '            const bool collapseLtx = !ltxLaunchForceOpen_;\n'
    '            ltxCard->setMinimumHeight(collapseLtx ? 58 : 0);\n'
    '            ltxCard->setMaximumHeight(collapseLtx ? 58 : QWIDGETSIZE_MAX);\n'
    '            ltxCard->setToolTip(collapseLtx\n'
    '                ? QStringLiteral("LTX launch options are collapsed by default. Click Open to expand.")\n'
    '                : QStringLiteral("LTX launch options."));\n'
    f'            // --- {MARKER}: hide LTX body (every direct child except the header) ---\n'
    '            const QList<QWidget *> ltxKids = ltxCard->findChildren<QWidget *>(\n'
    '                QString(), Qt::FindDirectChildrenOnly);\n'
    '            for (QWidget *kid : ltxKids)\n'
    '            {\n'
    '                if (kid->objectName() == QStringLiteral("LtxLaunchHeader"))\n'
    '                    continue;\n'
    '                kid->setVisible(!collapseLtx);\n'
    '            }\n'
    '            if (ltxLaunchToggleButton_)\n'
    '            {\n'
    '                ltxLaunchToggleButton_->setVisible(true);\n'
    '                ltxLaunchToggleButton_->setMinimumWidth(collapseLtx ? 72 : 74);\n'
    '                ltxLaunchToggleButton_->setText(collapseLtx ? QStringLiteral("Open") : QStringLiteral("Close"));\n'
    '                ltxLaunchToggleButton_->setToolTip(collapseLtx\n'
    '                    ? QStringLiteral("Expand LTX launch options.")\n'
    '                    : QStringLiteral("Collapse LTX launch options."));\n'
    '            }\n'
)


# ---------------------------------------------------------------------------
# 4. Advanced card — fix the name mismatch + add body gating.
#    The existing block looks up "AdvancedControlsCard" (never matches).
#    Replace the whole block with one that uses "AdvancedCard" and gates
#    the body (children after the header). The Advanced header widget is
#    `advancedHeader` (added to advancedLayout) and there's an
#    `AdvancedBodyHint` label. We give the header an object name in the
#    builder so we can keep it visible.
# ---------------------------------------------------------------------------

ADV_HEADER_NAME_ANCHOR = (
    '    auto *advancedHeader = new QWidget(advancedCard);\n'
)
ADV_HEADER_NAME_NEW = (
    '    auto *advancedHeader = new QWidget(advancedCard);\n'
    f'    advancedHeader->setObjectName(QStringLiteral("AdvancedHeader"));  // {MARKER}\n'
)

ADV_BLOCK_OLD = (
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

ADV_BLOCK_NEW = (
    f'    // --- {MARKER}: fixed name "AdvancedCard" (was "AdvancedControlsCard", never matched) ---\n'
    '    if (QFrame *advancedCard = findChild<QFrame *>(QStringLiteral("AdvancedCard")))\n'
    '    {\n'
    '        const bool advancedAutoCollapsed = true;\n'
    '        const bool collapseAdvanced = advancedAutoCollapsed && !advancedForceOpen_;\n'
    '        advancedCard->setMinimumHeight(collapseAdvanced ? 58 : 0);\n'
    '        advancedCard->setMaximumHeight(collapseAdvanced ? 58 : QWIDGETSIZE_MAX);\n'
    '        advancedCard->setToolTip(collapseAdvanced\n'
    '            ? QStringLiteral("Advanced controls are collapsed by default to keep the prompt rail usable.")\n'
    '            : QStringLiteral("Advanced controls."));\n'
    f'        // --- {MARKER}: hide Advanced body (direct children except header + hint) ---\n'
    '        const QList<QWidget *> advKids = advancedCard->findChildren<QWidget *>(\n'
    '            QString(), Qt::FindDirectChildrenOnly);\n'
    '        for (QWidget *kid : advKids)\n'
    '        {\n'
    '            const QString kn = kid->objectName();\n'
    '            if (kn == QStringLiteral("AdvancedHeader") || kn == QStringLiteral("AdvancedBodyHint"))\n'
    '                continue;\n'
    '            kid->setVisible(!collapseAdvanced);\n'
    '        }\n'
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

    text = replace_once(text, LTX_HEADER_NAME_ANCHOR, LTX_HEADER_NAME_NEW,
                        "LTX header object name")
    text = replace_once(text, ADV_HEADER_NAME_ANCHOR, ADV_HEADER_NAME_NEW,
                        "Advanced header object name")
    text = replace_once(text, SS_BLOCK_OLD, SS_BLOCK_NEW,
                        "Sampler/Scheduler collapse block")
    text = replace_once(text, LTX_BLOCK_OLD, LTX_BLOCK_NEW,
                        "LTX collapse block")
    text = replace_once(text, ADV_BLOCK_OLD, ADV_BLOCK_NEW,
                        "Advanced collapse block (name fix + gating)")

    write_text(path, text)
    print(f"  Patched: {path.name}")


def main() -> int:
    project = Path(__file__).resolve().parent
    print(f"Applying {MARKER}")
    print(f"  Project root: {project}")
    print()
    print("ImageGenerationPage.cpp")
    patch_image_generation_cpp(project)
    print()
    print(f"Done — {MARKER} applied.")
    print("Next: rebuild with .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
