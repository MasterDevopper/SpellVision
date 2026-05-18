"""
SpellVision — Sprint MOCKUP Pass 1: Asset Intelligence redesign.

WHAT
----
Replaces the single QLabel#AssetIntelligenceBody (HTML <table> with up to
20 key:value rows) on the right rail with a structured surface matching
the target mockup:

  - Readiness pill: colored dot + "Ready to generate" + mode/backend sub
  - Stack group: chip row (Family, Mode, Primary)
  - Components group (video modes only): Text / VAE / Vision chips
  - Timing row (video modes only): Length / Rate / Duration as real
    metric pairs (large value + uppercase key)
  - "Show all fields" disclosure: toggles a collapsed body containing the
    full legacy HTML dump (preserved — no information is lost)

The legacy QLabel `modelsRootLabel_` is kept as the disclosure body, so
the full key:value surface is still reachable behind a click. All
existing callers of `updateAssetIntelligenceUi()` keep working unchanged.

FILES
-----
  qt_ui/ImageGenerationPage.h     — new member pointers + QFrame fwd-decl
  qt_ui/ImageGenerationPage.cpp   — buildUi() block + updateAssetIntelligenceUi() body
  qt_ui/ThemeManager.cpp          — new QSS selectors + format args

IDEMPOTENCE
-----------
Re-running is a no-op once MARKER appears in each file. Backups are
written exactly once per file with .pre_sprint_mockup_pass1.bak suffix.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MARKER = "SPRINT MOCKUP PASS 1 ASSET INTELLIGENCE"
BACKUP_SUFFIX = ".pre_sprint_mockup_pass1.bak"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


def insert_once(text: str, anchor: str, insertion: str, *,
                after: bool = True, label: str = "anchor") -> str:
    if insertion.strip() and insertion.strip() in text:
        return text
    if anchor not in text:
        raise RuntimeError(f"Could not find {label}")
    return (text.replace(anchor, anchor + insertion, 1)
            if after else text.replace(anchor, insertion + anchor, 1))


def replace_function_body(text: str, signature_first_line: str, replacement: str,
                          *, label: str = "function") -> str:
    """
    Replace a whole C++ function (signature + body) given the first line of
    its signature (e.g. 'void Class::method() const'). Walks brace depth to
    find the matching close brace. `replacement` should include the full
    new function text.
    """
    start = text.find(signature_first_line)
    if start == -1:
        raise RuntimeError(f"Could not find {label} signature: {signature_first_line!r}")
    brace = text.find("{", start)
    if brace == -1:
        raise RuntimeError(f"No opening brace after {label} signature")
    depth = 0
    i = brace
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                return text[:start] + replacement + text[end:]
        i += 1
    raise RuntimeError(f"No matching close brace for {label}")


# ---------------------------------------------------------------------------
# qt_ui/ImageGenerationPage.h
# ---------------------------------------------------------------------------

HEADER_FWD_DECL_ANCHOR = "class QBoxLayout;\n"
HEADER_FWD_DECL_INSERT = "class QFrame;\n"

HEADER_MEMBERS_ANCHOR = "    QLabel *modelsRootLabel_ = nullptr;\n"
HEADER_MEMBERS_INSERT = f"""
    // --- {MARKER} ---
    // Structured asset-intelligence surface that replaces the dense HTML
    // dump (modelsRootLabel_ is kept as the collapsed details body).
    QFrame *aiReadinessStrip_ = nullptr;
    QLabel *aiReadinessDot_ = nullptr;
    QLabel *aiReadinessText_ = nullptr;
    QLabel *aiReadinessSub_ = nullptr;
    QLabel *aiStackGroupLabel_ = nullptr;
    QWidget *aiStackChipsRow_ = nullptr;
    QBoxLayout *aiStackChipsLayout_ = nullptr;
    QWidget *aiComponentsGroupContainer_ = nullptr;
    QLabel *aiComponentsGroupLabel_ = nullptr;
    QWidget *aiComponentsChipsRow_ = nullptr;
    QBoxLayout *aiComponentsChipsLayout_ = nullptr;
    QFrame *aiTimingRow_ = nullptr;
    QLabel *aiTimingFramesValue_ = nullptr;
    QLabel *aiTimingFramesKey_ = nullptr;
    QLabel *aiTimingFpsValue_ = nullptr;
    QLabel *aiTimingFpsKey_ = nullptr;
    QLabel *aiTimingDurationValue_ = nullptr;
    QLabel *aiTimingDurationKey_ = nullptr;
    QToolButton *aiDetailsToggle_ = nullptr;
    bool aiDetailsExpanded_ = false;
    // --- END {MARKER} ---
"""


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

    if HEADER_FWD_DECL_INSERT.strip() not in text:
        text = insert_once(text, HEADER_FWD_DECL_ANCHOR, HEADER_FWD_DECL_INSERT,
                           label="header forward-decl block")

    text = insert_once(text, HEADER_MEMBERS_ANCHOR, HEADER_MEMBERS_INSERT,
                       label="header member block (modelsRootLabel_ anchor)")

    write_text(path, text)
    print(f"  Patched: {path.name}")


# ---------------------------------------------------------------------------
# qt_ui/ImageGenerationPage.cpp — buildUi() section
# ---------------------------------------------------------------------------

BUILDUI_ANCHOR = (
    '    settingsCardLayout->addWidget(createSectionTitle(QStringLiteral("Asset Intelligence"), settingsCard_));\n'
    '    auto *assetHint = createSectionBody(QStringLiteral("Live model, LoRA, workflow, and draft readiness."), settingsCard_);\n'
    '    assetHint->setMaximumHeight(36);\n'
    '    settingsCardLayout->addWidget(assetHint);\n'
    '    modelsRootLabel_->setObjectName(QStringLiteral("AssetIntelligenceBody"));\n'
    '    settingsCardLayout->addWidget(modelsRootLabel_);\n'
)

BUILDUI_REPLACEMENT = f"""    // --- {MARKER}: structured AI surface ---
    settingsCardLayout->addWidget(createSectionTitle(QStringLiteral("Asset Intelligence"), settingsCard_));
    auto *assetHint = createSectionBody(QStringLiteral("Readiness first. Details on demand."), settingsCard_);
    assetHint->setMaximumHeight(36);
    settingsCardLayout->addWidget(assetHint);

    // Readiness strip: colored dot + headline + right-aligned sub.
    aiReadinessStrip_ = new QFrame(settingsCard_);
    aiReadinessStrip_->setObjectName(QStringLiteral("AiReadinessStrip"));
    aiReadinessStrip_->setProperty("readiness", QStringLiteral("ready"));
    {{
        auto *stripLayout = new QHBoxLayout(aiReadinessStrip_);
        stripLayout->setContentsMargins(
            ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
            6,
            ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
            6);
        stripLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

        aiReadinessDot_ = new QLabel(aiReadinessStrip_);
        aiReadinessDot_->setObjectName(QStringLiteral("AiReadinessDot"));
        aiReadinessDot_->setProperty("readiness", QStringLiteral("ready"));
        aiReadinessDot_->setFixedSize(10, 10);
        stripLayout->addWidget(aiReadinessDot_, 0, Qt::AlignVCenter);

        aiReadinessText_ = new QLabel(QStringLiteral("Ready to generate"), aiReadinessStrip_);
        aiReadinessText_->setObjectName(QStringLiteral("AiReadinessText"));
        stripLayout->addWidget(aiReadinessText_, 0, Qt::AlignVCenter);

        stripLayout->addStretch(1);

        aiReadinessSub_ = new QLabel(QString(), aiReadinessStrip_);
        aiReadinessSub_->setObjectName(QStringLiteral("AiReadinessSub"));
        stripLayout->addWidget(aiReadinessSub_, 0, Qt::AlignVCenter | Qt::AlignRight);
    }}
    settingsCardLayout->addWidget(aiReadinessStrip_);

    // Stack group: small uppercase label + flow row of chips.
    settingsCardLayout->addSpacing(6);
    aiStackGroupLabel_ = new QLabel(QStringLiteral("STACK"), settingsCard_);
    aiStackGroupLabel_->setObjectName(QStringLiteral("AiGroupLabel"));
    settingsCardLayout->addWidget(aiStackGroupLabel_);

    aiStackChipsRow_ = new QWidget(settingsCard_);
    aiStackChipsRow_->setObjectName(QStringLiteral("AiChipsRow"));
    aiStackChipsLayout_ = new QHBoxLayout(aiStackChipsRow_);
    aiStackChipsLayout_->setContentsMargins(0, 2, 0, 0);
    aiStackChipsLayout_->setSpacing(6);
    aiStackChipsLayout_->addStretch(1);
    settingsCardLayout->addWidget(aiStackChipsRow_);

    // Components group: video modes only (visibility set in update).
    aiComponentsGroupContainer_ = new QWidget(settingsCard_);
    aiComponentsGroupContainer_->setObjectName(QStringLiteral("AiComponentsGroupContainer"));
    {{
        auto *componentsLayout = new QVBoxLayout(aiComponentsGroupContainer_);
        componentsLayout->setContentsMargins(0, 6, 0, 0);
        componentsLayout->setSpacing(2);

        aiComponentsGroupLabel_ = new QLabel(QStringLiteral("COMPONENTS"), aiComponentsGroupContainer_);
        aiComponentsGroupLabel_->setObjectName(QStringLiteral("AiGroupLabel"));
        componentsLayout->addWidget(aiComponentsGroupLabel_);

        aiComponentsChipsRow_ = new QWidget(aiComponentsGroupContainer_);
        aiComponentsChipsRow_->setObjectName(QStringLiteral("AiChipsRow"));
        aiComponentsChipsLayout_ = new QHBoxLayout(aiComponentsChipsRow_);
        aiComponentsChipsLayout_->setContentsMargins(0, 2, 0, 0);
        aiComponentsChipsLayout_->setSpacing(6);
        aiComponentsChipsLayout_->addStretch(1);
        componentsLayout->addWidget(aiComponentsChipsRow_);
    }}
    settingsCardLayout->addWidget(aiComponentsGroupContainer_);

    // Timing row (video modes only): three metric pairs over a top border.
    aiTimingRow_ = new QFrame(settingsCard_);
    aiTimingRow_->setObjectName(QStringLiteral("AiTimingRow"));
    {{
        auto *timingLayout = new QHBoxLayout(aiTimingRow_);
        timingLayout->setContentsMargins(0, 8, 0, 0);
        timingLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Card));

        auto makeTimingItem = [&](QLabel *&valueLbl, QLabel *&keyLbl, const QString &keyText) {{
            auto *item = new QWidget(aiTimingRow_);
            auto *itemLayout = new QVBoxLayout(item);
            itemLayout->setContentsMargins(0, 0, 0, 0);
            itemLayout->setSpacing(0);
            valueLbl = new QLabel(QStringLiteral("\\u2014"), item);
            valueLbl->setObjectName(QStringLiteral("AiTimingValue"));
            keyLbl = new QLabel(keyText, item);
            keyLbl->setObjectName(QStringLiteral("AiTimingKey"));
            itemLayout->addWidget(valueLbl);
            itemLayout->addWidget(keyLbl);
            timingLayout->addWidget(item, 0, Qt::AlignLeft);
        }};
        makeTimingItem(aiTimingFramesValue_, aiTimingFramesKey_, QStringLiteral("LENGTH"));
        makeTimingItem(aiTimingFpsValue_, aiTimingFpsKey_, QStringLiteral("RATE"));
        makeTimingItem(aiTimingDurationValue_, aiTimingDurationKey_, QStringLiteral("DURATION"));
        timingLayout->addStretch(1);
    }}
    settingsCardLayout->addWidget(aiTimingRow_);

    // "Show all fields" disclosure: toggles modelsRootLabel_ visibility.
    settingsCardLayout->addSpacing(4);
    aiDetailsToggle_ = new QToolButton(settingsCard_);
    aiDetailsToggle_->setObjectName(QStringLiteral("AiDetailsToggle"));
    aiDetailsToggle_->setToolButtonStyle(Qt::ToolButtonTextOnly);
    aiDetailsToggle_->setText(QString::fromUtf8("\\xE2\\x96\\xBE Show all fields"));
    aiDetailsToggle_->setCursor(Qt::PointingHandCursor);
    aiDetailsToggle_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    connect(aiDetailsToggle_, &QToolButton::clicked, this, [this]() {{
        aiDetailsExpanded_ = !aiDetailsExpanded_;
        if (modelsRootLabel_)
            modelsRootLabel_->setVisible(aiDetailsExpanded_);
        if (aiDetailsToggle_)
        {{
            aiDetailsToggle_->setText(aiDetailsExpanded_
                ? QString::fromUtf8("\\xE2\\x96\\xB4 Hide details")
                : QString::fromUtf8("\\xE2\\x96\\xBE Show all fields"));
        }}
    }});
    settingsCardLayout->addWidget(aiDetailsToggle_);

    // Legacy details body — kept for the disclosure, hidden by default.
    modelsRootLabel_->setObjectName(QStringLiteral("AiDetailsBody"));
    modelsRootLabel_->setVisible(false);
    settingsCardLayout->addWidget(modelsRootLabel_);
    // --- END {MARKER}: structured AI surface ---
"""


# ---------------------------------------------------------------------------
# qt_ui/ImageGenerationPage.cpp — updateAssetIntelligenceUi() rewrite
# ---------------------------------------------------------------------------

UPDATE_SIGNATURE = "void ImageGenerationPage::updateAssetIntelligenceUi()"

UPDATE_REPLACEMENT = f"""void ImageGenerationPage::updateAssetIntelligenceUi()
{{
    // --- {MARKER}: structured population ---
    if (!modelsRootLabel_)
        return;

    // ---- Data (same shape as the pre-mockup implementation) ----
    const QString modelDisplay = selectedModelPath_.trimmed().isEmpty()
        ? QStringLiteral("none selected")
        : (selectedModelDisplay_.trimmed().isEmpty() ? shortDisplayFromValue(selectedModelPath_) : selectedModelDisplay_.trimmed());

    const QString rawFamily = modelFamilyByValue_.value(selectedModelPath_).trimmed();
    const QString rawModality = modelModalityByValue_.value(selectedModelPath_, isVideoMode() ? QStringLiteral("video") : QStringLiteral("image"));
    const QString rawRole = modelRoleByValue_.value(selectedModelPath_).trimmed();
    const QString stackNote = modelNoteByValue_.value(selectedModelPath_).trimmed();
    const QJsonObject stackObject = isVideoMode() ? selectedVideoStackForPayload() : modelStackByValue_.value(selectedModelPath_);
    const QString modelPathLower = selectedModelPath_.toLower();

    QString modelFamily = QStringLiteral("unknown");
    if (!rawFamily.isEmpty())
        modelFamily = isVideoMode() ? humanVideoFamily(rawFamily) : humanImageFamily(rawFamily);
    else if (modelPathLower.contains(QStringLiteral("pony")))
        modelFamily = QStringLiteral("Pony family");
    else if (modelPathLower.contains(QStringLiteral("illustri")))
        modelFamily = QStringLiteral("Illustrious family");
    else if (modelPathLower.contains(QStringLiteral("sdxl")) || modelPathLower.contains(QStringLiteral("xl")))
        modelFamily = QStringLiteral("SDXL / XL family");
    else if (modelPathLower.contains(QStringLiteral("flux")))
        modelFamily = QStringLiteral("Flux family");
    else if (modelPathLower.contains(QStringLiteral("wan")))
        modelFamily = QStringLiteral("WAN video family");
    else if (modelPathLower.contains(QStringLiteral("zimage")) || modelPathLower.contains(QStringLiteral("z-image")))
        modelFamily = QStringLiteral("Z-Image family");
    else if (!modelPathLower.trimmed().isEmpty())
        modelFamily = QStringLiteral("custom / uncategorized");

    QString stackSummary = stackNote.isEmpty() ? QStringLiteral("\\u2014") : stackNote;
    if (!stackObject.isEmpty())
    {{
        const QString kind = stackObject.value(QStringLiteral("stack_kind")).toString().trimmed();
        const bool readyStack = stackObject.value(QStringLiteral("stack_ready")).toBool(false);
        const QJsonArray missing = stackObject.value(QStringLiteral("missing_parts")).toArray();
        QStringList missingParts;
        for (const QJsonValue &item : missing)
            missingParts << item.toString();
        stackSummary = QStringLiteral("%1 \\u2022 %2").arg(kind.isEmpty() ? QStringLiteral("stack") : kind, readyStack ? QStringLiteral("resolved") : QStringLiteral("partial"));
        if (!missingParts.isEmpty())
            stackSummary += QStringLiteral(" \\u2022 missing %1").arg(missingParts.join(QStringLiteral(", ")));
    }}

    const int enabledLoras = ModelStackState::enabledLoraCount(loraStack_);
    const QString workflowName = workflowCombo_ ? currentComboValue(workflowCombo_) : QStringLiteral("Default Canvas");
    const QString draftState = workflowDraftSource_.trimmed().isEmpty()
        ? QStringLiteral("none")
        : (workflowDraftBlocking_ ? QStringLiteral("review required") : QStringLiteral("ready"));
    const QString warningState = workflowDraftWarnings_.isEmpty()
        ? QStringLiteral("none")
        : QStringLiteral("%1 review note%2").arg(workflowDraftWarnings_.size()).arg(workflowDraftWarnings_.size() == 1 ? QString() : QStringLiteral("s"));
    const QString rootText = modelsRootDir_.trimmed().isEmpty()
        ? QStringLiteral("not configured")
        : QDir::toNativeSeparators(modelsRootDir_);
    const QString blockReason = readinessBlockReason();
    const bool ready = blockReason.isEmpty();
    const QString readiness = ready ? QStringLiteral("ready") : blockReason;

    // ---- Surface: readiness strip ----
    if (aiReadinessStrip_)
    {{
        const QString readinessState = ready ? QStringLiteral("ready") : QStringLiteral("warn");
        aiReadinessStrip_->setProperty("readiness", readinessState);
        spellvision::widgets::repolishWidget(aiReadinessStrip_);
        if (aiReadinessDot_)
        {{
            aiReadinessDot_->setProperty("readiness", readinessState);
            spellvision::widgets::repolishWidget(aiReadinessDot_);
        }}
        if (aiReadinessText_)
            aiReadinessText_->setText(ready ? QStringLiteral("Ready to generate") : blockReason);

        if (aiReadinessSub_)
        {{
            QString sub;
            if (selectedModelPath_.trimmed().isEmpty())
            {{
                sub = QStringLiteral("Select a checkpoint to generate.");
            }}
            else if (isVideoMode())
            {{
                const QString backendLabel = hasVideoWorkflowBinding()
                    ? QStringLiteral("imported workflow")
                    : QStringLiteral("native");
                sub = QStringLiteral("%1 \\u00B7 %2").arg(modelFamily, backendLabel);
            }}
            else
            {{
                sub = modelFamily;
            }}
            aiReadinessSub_->setText(sub);
        }}
    }}

    // ---- Surface: chip rows (clear then rebuild) ----
    auto clearChips = [](QBoxLayout *layout) {{
        if (!layout)
            return;
        while (layout->count() > 0)
        {{
            QLayoutItem *item = layout->takeAt(0);
            if (item->widget())
                item->widget()->deleteLater();
            delete item;
        }}
    }};

    const QColor accentColor = ThemeManager::instance().accentColor();
    const QColor textMutedColor = ThemeManager::instance().textMutedColor();

    auto addChip = [&](QBoxLayout *layout, QWidget *parent,
                       const QString &label, const QString &value, bool isSet) {{
        if (!layout || !parent)
            return;
        auto *chip = new QLabel(parent);
        chip->setObjectName(QStringLiteral("AiChip"));
        chip->setProperty("is", isSet ? QStringLiteral("set") : QStringLiteral("auto"));
        chip->setTextFormat(Qt::RichText);
        chip->setToolTip(QStringLiteral("%1: %2").arg(label, value));
        const QString labelEsc = label.toHtmlEscaped();
        const QString valueEsc = value.toHtmlEscaped();
        if (isSet)
        {{
            chip->setText(QStringLiteral("%1 <b style=\\"color:%3;\\">%2</b>")
                .arg(labelEsc, valueEsc, accentColor.name()));
        }}
        else
        {{
            chip->setText(QStringLiteral("%1 <span style=\\"color:%3;\\">%2</span>")
                .arg(labelEsc, valueEsc, textMutedColor.name()));
        }}
        layout->insertWidget(layout->count() - 1, chip);
    }};

    auto chipValueIsSet = [](const QString &v) {{
        const QString t = v.trimmed();
        return !t.isEmpty()
            && t.compare(QStringLiteral("auto"), Qt::CaseInsensitive) != 0
            && t.compare(QStringLiteral("none"), Qt::CaseInsensitive) != 0
            && t != QStringLiteral("\\u2014");
    }};

    clearChips(aiStackChipsLayout_);
    if (aiStackChipsRow_ && aiStackChipsLayout_)
    {{
        if (isVideoMode())
        {{
            const QString stackMode = effectiveVideoStackMode();
            const QString famShort = resolvedVideoFamilyToken().toUpper();
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Family"),
                    famShort.isEmpty() ? QStringLiteral("auto") : famShort,
                    !famShort.isEmpty());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Mode"),
                    stackMode == QStringLiteral("wan_dual_noise") ? QStringLiteral("dual-noise") : QStringLiteral("single"),
                    true);
            const QString primary = shortDisplayFromValue(stackObject.value(QStringLiteral("primary_path")).toString());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Primary"),
                    chipValueIsSet(primary) ? primary : QStringLiteral("auto"),
                    chipValueIsSet(primary));
        }}
        else
        {{
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Checkpoint"),
                    modelDisplay,
                    !selectedModelPath_.trimmed().isEmpty());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("Family"),
                    modelFamily,
                    !rawFamily.isEmpty());
            addChip(aiStackChipsLayout_, aiStackChipsRow_,
                    QStringLiteral("LoRAs"),
                    QStringLiteral("%1 / %2").arg(loraStack_.size()).arg(enabledLoras),
                    enabledLoras > 0);
        }}
        aiStackChipsLayout_->addStretch(1);
    }}

    clearChips(aiComponentsChipsLayout_);
    if (aiComponentsGroupContainer_)
        aiComponentsGroupContainer_->setVisible(isVideoMode());
    if (isVideoMode() && aiComponentsChipsRow_ && aiComponentsChipsLayout_)
    {{
        const QString textEnc = shortDisplayFromValue(stackObject.value(QStringLiteral("text_encoder_path")).toString());
        const QString vae = shortDisplayFromValue(stackObject.value(QStringLiteral("vae_path")).toString());
        const QString vision = shortDisplayFromValue(stackObject.value(QStringLiteral("clip_vision_path")).toString());
        addChip(aiComponentsChipsLayout_, aiComponentsChipsRow_,
                QStringLiteral("Text"),
                chipValueIsSet(textEnc) ? textEnc : QStringLiteral("auto"),
                chipValueIsSet(textEnc));
        addChip(aiComponentsChipsLayout_, aiComponentsChipsRow_,
                QStringLiteral("VAE"),
                chipValueIsSet(vae) ? vae : QStringLiteral("auto"),
                chipValueIsSet(vae));
        addChip(aiComponentsChipsLayout_, aiComponentsChipsRow_,
                QStringLiteral("Vision"),
                chipValueIsSet(vision) ? vision : QStringLiteral("auto"),
                chipValueIsSet(vision));
        aiComponentsChipsLayout_->addStretch(1);
    }}

    // ---- Surface: timing row (video modes only) ----
    if (aiTimingRow_)
        aiTimingRow_->setVisible(isVideoMode());
    if (isVideoMode())
    {{
        const int frames = frameCountSpin_ ? frameCountSpin_->value() : 0;
        const int fps = fpsSpin_ ? fpsSpin_->value() : 0;
        const double seconds = fps > 0 ? static_cast<double>(frames) / static_cast<double>(fps) : 0.0;
        if (aiTimingFramesValue_)
            aiTimingFramesValue_->setText(QStringLiteral("%1 frames").arg(frames));
        if (aiTimingFpsValue_)
            aiTimingFpsValue_->setText(QStringLiteral("%1 fps").arg(fps));
        if (aiTimingDurationValue_)
            aiTimingDurationValue_->setText(QStringLiteral("%1 s").arg(QString::number(seconds, 'f', 1)));
    }}

    // ---- Legacy HTML dump (kept behind the "Show all fields" disclosure) ----
    auto row = [ready](const QString &label, const QString &value, bool readinessRow = false) {{
        const QString valueClass = readinessRow ? (ready ? QStringLiteral("v good") : QStringLiteral("v bad")) : QStringLiteral("v");
        return QStringLiteral("<tr><td class='k'>%1</td><td class='%2'>%3</td></tr>")
            .arg(label.toHtmlEscaped(), valueClass, value.toHtmlEscaped());
    }};

    QString html;
    html += QStringLiteral("<style>"
                           "table{{border-collapse:collapse;width:100%;}}"
                           "td{{padding:2px 0;vertical-align:top;}}"
                           ".k{{opacity:.74;font-weight:800;white-space:nowrap;padding-right:12px;}}"
                           ".v{{font-weight:650;}}"
                           ".good{{color:#9ff5ca;}}"
                           ".bad{{color:#ffd1dc;}}"
                           "</style>");
    html += QStringLiteral("<table>");
    html += row(isVideoMode() ? QStringLiteral("Model Stack") : QStringLiteral("Checkpoint"), modelDisplay);
    html += row(QStringLiteral("Family"), modelFamily);
    if (isVideoMode())
    {{
        const QString stackMode = effectiveVideoStackMode();
        html += row(QStringLiteral("Modality"), rawModality.trimmed().isEmpty() ? QStringLiteral("video") : rawModality);
        html += row(QStringLiteral("Stack Role"), rawRole.trimmed().isEmpty() ? QStringLiteral("native video") : rawRole);
        html += row(QStringLiteral("Stack Mode"), stackMode == QStringLiteral("wan_dual_noise") ? QStringLiteral("WAN dual-noise") : QStringLiteral("single model"));
        html += row(QStringLiteral("Stack"), stackSummary);
        html += row(QStringLiteral("Primary"), shortDisplayFromValue(stackObject.value(QStringLiteral("primary_path")).toString()));
        if (stackMode == QStringLiteral("wan_dual_noise"))
        {{
            html += row(QStringLiteral("High Noise"), shortDisplayFromValue(stackObject.value(QStringLiteral("high_noise_path")).toString().trimmed().isEmpty() ? stackObject.value(QStringLiteral("high_noise_model_path")).toString() : stackObject.value(QStringLiteral("high_noise_path")).toString()));
            html += row(QStringLiteral("Low Noise"), shortDisplayFromValue(stackObject.value(QStringLiteral("low_noise_path")).toString().trimmed().isEmpty() ? stackObject.value(QStringLiteral("low_noise_model_path")).toString() : stackObject.value(QStringLiteral("low_noise_path")).toString()));
            html += row(QStringLiteral("Wan Split"), wanSplitCombo_ ? currentComboValue(wanSplitCombo_) : QStringLiteral("auto"));
        }}
        html += row(QStringLiteral("Text Encoder"), shortDisplayFromValue(stackObject.value(QStringLiteral("text_encoder_path")).toString()));
        html += row(QStringLiteral("VAE"), shortDisplayFromValue(stackObject.value(QStringLiteral("vae_path")).toString()));
        const QString vision = stackObject.value(QStringLiteral("clip_vision_path")).toString().trimmed();
        if (!vision.isEmpty())
            html += row(QStringLiteral("Vision Encoder"), shortDisplayFromValue(vision));
        if (stackMode == QStringLiteral("wan_dual_noise"))
        {{
            html += row(QStringLiteral("High Steps"), highNoiseStepsSpin_ ? QString::number(highNoiseStepsSpin_->value()) : QStringLiteral("14"));
            html += row(QStringLiteral("Low Steps"), lowNoiseStepsSpin_ ? QString::number(lowNoiseStepsSpin_->value()) : QStringLiteral("14"));
            html += row(QStringLiteral("Split Step"), splitStepSpin_ ? QString::number(splitStepSpin_->value()) : QStringLiteral("14"));
            html += row(QStringLiteral("High Shift"), highNoiseShiftSpin_ ? QString::number(highNoiseShiftSpin_->value(), 'f', 2) : QStringLiteral("5.00"));
            html += row(QStringLiteral("Low Shift"), lowNoiseShiftSpin_ ? QString::number(lowNoiseShiftSpin_->value(), 'f', 2) : QStringLiteral("5.00"));
            html += row(QStringLiteral("VAE Tiling"), enableVaeTilingCheck_ && enableVaeTilingCheck_->isChecked() ? QStringLiteral("enabled") : QStringLiteral("disabled"));
        }}
    }}
    html += row(QStringLiteral("LoRAs"), QStringLiteral("%1 stack / %2 enabled").arg(loraStack_.size()).arg(enabledLoras));
    html += row(QStringLiteral("Workflow"), workflowName.trimmed().isEmpty() ? QStringLiteral("Default Canvas") : workflowName);
    if (isVideoMode())
    {{
        const int frames = frameCountSpin_ ? frameCountSpin_->value() : 0;
        const int fps = fpsSpin_ ? fpsSpin_->value() : 0;
        const double seconds = fps > 0 ? static_cast<double>(frames) / static_cast<double>(fps) : 0.0;
        html += row(QStringLiteral("Timing"), QStringLiteral("%1 frames @ %2 fps (%3s)").arg(frames).arg(fps).arg(QString::number(seconds, 'f', 1)));
        html += row(QStringLiteral("Backend"), hasVideoWorkflowBinding() ? QStringLiteral("Imported workflow") : QStringLiteral("Native video model"));
        const QString inputImagePath = inputImageEdit_ ? inputImageEdit_->text().trimmed() : QString();
        if (!inputImagePath.isEmpty())
            html += row(QStringLiteral("Keyframe"), shortDisplayFromValue(inputImagePath));
    }}
    html += row(QStringLiteral("Draft"), draftState);
    html += row(QStringLiteral("Review"), warningState);
    html += row(QStringLiteral("Readiness"), readiness, true);
    html += row(QStringLiteral("Assets"), rootText);
    html += QStringLiteral("</table>");

    modelsRootLabel_->setText(html);

    // Tooltip on the readiness strip — exposes the full dump in plain text
    // so users get the data without having to expand the disclosure.
    QStringList plain;
    plain << QStringLiteral("%1: %2").arg(isVideoMode() ? QStringLiteral("Model Stack") : QStringLiteral("Checkpoint"), modelDisplay);
    plain << QStringLiteral("Family: %1").arg(modelFamily);
    plain << QStringLiteral("LoRAs: %1 in stack / %2 enabled").arg(loraStack_.size()).arg(enabledLoras);
    plain << QStringLiteral("Workflow: %1").arg(workflowName.trimmed().isEmpty() ? QStringLiteral("Default Canvas") : workflowName);
    plain << QStringLiteral("Draft: %1").arg(draftState);
    plain << QStringLiteral("Review: %1").arg(warningState);
    plain << QStringLiteral("Readiness: %1").arg(readiness);
    plain << QStringLiteral("Assets: %1").arg(rootText);
    const QString tooltip = plain.join(QStringLiteral("\\n"));
    if (aiReadinessStrip_)
        aiReadinessStrip_->setToolTip(tooltip);
    modelsRootLabel_->setToolTip(tooltip);
    // --- END {MARKER}: structured population ---
}}
"""


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

    text = insert_once(text, BUILDUI_ANCHOR, "",
                       label="asset-intelligence buildUi anchor (won't actually insert; placeholder)")
    # The line above just validates the anchor exists. The real swap:
    text = text.replace(BUILDUI_ANCHOR, BUILDUI_REPLACEMENT, 1)

    text = replace_function_body(text, UPDATE_SIGNATURE, UPDATE_REPLACEMENT,
                                  label="updateAssetIntelligenceUi")

    write_text(path, text)
    print(f"  Patched: {path.name}")


# ---------------------------------------------------------------------------
# qt_ui/ThemeManager.cpp — new QSS selectors + format args
# ---------------------------------------------------------------------------

THEME_SELECTOR_ANCHOR = (
    '        "QLabel#PreviewSurface[emptyState=\\"true\\"] { color: %14; border-color: %31; background: %33; }"\n'
    '    );\n'
)

THEME_SELECTOR_INSERT = f"""        // --- {MARKER}: structured AI surface selectors ---
        "QFrame#AiReadinessStrip {{ background: %34; border: 1px solid %35; border-radius: 11px; }}"
        "QFrame#AiReadinessStrip[readiness=\\"warn\\"] {{ background: %37; border-color: %38; }}"
        "QFrame#AiReadinessStrip[readiness=\\"block\\"] {{ background: %40; border-color: %41; }}"
        "QLabel#AiReadinessDot {{ background: %36; border-radius: 5px; min-width: 10px; max-width: 10px; min-height: 10px; max-height: 10px; }}"
        "QLabel#AiReadinessDot[readiness=\\"warn\\"] {{ background: %39; }}"
        "QLabel#AiReadinessDot[readiness=\\"block\\"] {{ background: %42; }}"
        "QLabel#AiReadinessText {{ font-size: 12px; font-weight: 700; color: %13; background: transparent; }}"
        "QLabel#AiReadinessSub {{ font-size: 11px; color: %14; background: transparent; }}"
        "QLabel#AiGroupLabel {{ font-size: 10px; color: %14; background: transparent; font-weight: 800; letter-spacing: 1px; }}"
        "QLabel#AiChip {{ background: %17; border: 1px solid %18; border-radius: 12px; padding: 2px 10px; color: %15; font-size: 11px; min-height: 18px; }}"
        "QLabel#AiChip[is=\\"set\\"] {{ background: %43; border-color: %44; color: %13; }}"
        "QLabel#AiChip[is=\\"auto\\"] {{ border-style: dashed; color: %14; }}"
        "QFrame#AiTimingRow {{ background: transparent; border: none; border-top: 1px solid %29; }}"
        "QLabel#AiTimingValue {{ font-size: 14px; font-weight: 700; color: %13; background: transparent; }}"
        "QLabel#AiTimingKey {{ font-size: 10px; color: %14; background: transparent; font-weight: 800; letter-spacing: 1px; }}"
        "QToolButton#AiDetailsToggle {{ background: transparent; border: none; padding: 4px 0; color: %45; font-size: 11px; min-height: 18px; text-align: left; font-weight: 600; }}"
        "QToolButton#AiDetailsToggle:hover {{ color: %10; }}"
        "QLabel#AiDetailsBody {{ color: %15; font-size: 11px; background: transparent; padding-top: 4px; }}"
        // --- END {MARKER} ---
""".replace("{{", "{").replace("}}", "}")  # nothing actually doubles in QSS; placeholder

# Note: the Python f-string above contains no {}; the .replace() is just
# defensive in case future authors add doubled braces. The selectors block
# does not require f-string interpolation since all values are static.


THEME_ARG_ANCHOR = (
    '        .arg(rgba(withAlpha(mix(panel0, background0(), 0.20), 1.0), 1.0));\n'
)

THEME_ARG_INSERT = f"""        // --- {MARKER}: new color slots (34-45) ---
        // 34/35: success-tinted readiness pill (bg, border)
        // 36   : success base for ready dot
        // 37/38: warning-tinted readiness pill (bg, border)
        // 39   : warning base for warn dot
        // 40/41: error-tinted readiness pill (bg, border)
        // 42   : error base for block dot
        // 43/44: accent-tinted chip when is="set" (bg, border)
        // 45   : accent base for AiDetailsToggle text + chip emphasis
        .arg(rgba(withAlpha(successColor(), 0.10), 1.0))
        .arg(rgba(withAlpha(successColor(), 0.34), 1.0))
        .arg(successColor().name())
        .arg(rgba(withAlpha(warningColor(), 0.10), 1.0))
        .arg(rgba(withAlpha(warningColor(), 0.34), 1.0))
        .arg(warningColor().name())
        .arg(rgba(withAlpha(errorColor(), 0.10), 1.0))
        .arg(rgba(withAlpha(errorColor(), 0.34), 1.0))
        .arg(errorColor().name())
        .arg(rgba(withAlpha(accent, 0.10), 1.0))
        .arg(rgba(withAlpha(accent, 0.42), 1.0))
        .arg(accent.name());
        // --- END {MARKER}: new color slots ---
"""


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

    # Insert new QSS selectors just before the closing `);` of the QStringLiteral
    if THEME_SELECTOR_ANCHOR not in text:
        raise RuntimeError("Could not find ThemeManager QSS-close anchor")
    text = text.replace(THEME_SELECTOR_ANCHOR,
                        THEME_SELECTOR_INSERT + THEME_SELECTOR_ANCHOR, 1)

    # Replace the terminating `;` of the .arg chain with 12 new .arg calls + `;`
    if THEME_ARG_ANCHOR not in text:
        raise RuntimeError("Could not find ThemeManager .arg-chain terminator anchor")
    text = text.replace(THEME_ARG_ANCHOR, THEME_ARG_INSERT, 1)

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
