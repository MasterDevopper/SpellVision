from pathlib import Path

h_path = Path("qt_ui/ImageGenerationPage.h")
cpp_path = Path("qt_ui/ImageGenerationPage.cpp")
builder_h_path = Path("qt_ui/generation/GenerationRequestBuilder.h")
builder_cpp_path = Path("qt_ui/generation/GenerationRequestBuilder.cpp")
doc_path = Path("docs/sprints/SPRINT15C_PASS29C_LTX_LAUNCH_OPTIONS_PANEL_README.md")
script_path = Path("scripts/refactors/apply_sprint15c_pass29c_ltx_launch_options_panel.py")

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")
builder_h = builder_h_path.read_text(encoding="utf-8")
builder_cpp = builder_cpp_path.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# 1) GenerationRequestDraft carries Prompt API export path.
# ----------------------------------------------------------------------

if "QString promptApiExportPath;" not in builder_h:
    marker = '''    QString workflowBackend;
    QString workflowMediaType;

    QVector<LoraRequestEntry> loras;'''
    replacement = '''    QString workflowBackend;
    QString workflowMediaType;
    QString promptApiExportPath;

    QVector<LoraRequestEntry> loras;'''
    if marker not in builder_h:
        raise SystemExit("Could not find GenerationRequestDraft workflow metadata marker.")
    builder_h = builder_h.replace(marker, replacement, 1)

builder_h_path.write_text(builder_h, encoding="utf-8")


# ----------------------------------------------------------------------
# 2) ImageGenerationPage owns LTX launch option widgets.
# ----------------------------------------------------------------------

if "ltxPromptApiExportPathEdit_" not in h:
    marker = '''    QComboBox *workflowCombo_ = nullptr;
    QWidget *loraStackContainer_ = nullptr;'''
    replacement = '''    QComboBox *workflowCombo_ = nullptr;
    QWidget *ltxLaunchOptionsPanel_ = nullptr;
    QLineEdit *ltxPromptApiExportPathEdit_ = nullptr;
    QLabel *ltxPromptApiHintLabel_ = nullptr;
    QPushButton *ltxBrowsePromptApiButton_ = nullptr;
    QPushButton *ltxUseDefaultPromptApiButton_ = nullptr;
    QPushButton *ltxApplySafeDefaultsButton_ = nullptr;
    QWidget *loraStackContainer_ = nullptr;'''
    if marker not in h:
        raise SystemExit("Could not find workflowCombo_ header marker.")
    h = h.replace(marker, replacement, 1)

h_path.write_text(h, encoding="utf-8")


# ----------------------------------------------------------------------
# 3) Add helper for default LTX Prompt API export.
# ----------------------------------------------------------------------

helper = r'''
QString defaultLtxPromptApiExportPath()
{
    const QString envPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_LTX_PROMPT_API_EXPORT")).trimmed();
    if (!envPath.isEmpty())
        return QDir::fromNativeSeparators(envPath);

    const QString legacyEnvPath = QString::fromLocal8Bit(qgetenv("SPELLVISION_LTX_API_WORKFLOW")).trimmed();
    if (!legacyEnvPath.isEmpty())
        return QDir::fromNativeSeparators(legacyEnvPath);

    return QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI/user/default/workflows/ltx_api.json");
}

'''

if "defaultLtxPromptApiExportPath" not in cpp:
    marker = '''bool selectComboByContains(QComboBox *combo, const QStringList &needles)'''
    if marker not in cpp:
        raise SystemExit("Could not find helper insertion marker.")
    cpp = cpp.replace(marker, helper + marker, 1)


# ----------------------------------------------------------------------
# 4) Build visible LTX launch options panel in Quick Controls.
# ----------------------------------------------------------------------

panel_code = r'''
    // Sprint 15C Pass 29C:
    // LTX Prompt API generation requires a real Comfy API-format workflow.
    // Expose that path directly in the T2V/I2V surface instead of hiding it
    // behind requeue-only tooling.
    ltxLaunchOptionsPanel_ = createCard(QStringLiteral("LtxLaunchOptionsPanel"));
    auto *ltxLaunchLayout = new QVBoxLayout(ltxLaunchOptionsPanel_);
    ltxLaunchLayout->setContentsMargins(10, 10, 10, 10);
    ltxLaunchLayout->setSpacing(8);

    ltxLaunchLayout->addWidget(createSectionTitle(QStringLiteral("LTX Launch Options"), ltxLaunchOptionsPanel_));

    ltxPromptApiHintLabel_ = createSectionBody(
        QStringLiteral("Required: Comfy Prompt API export. Default: user/default/workflows/ltx_api.json"),
        ltxLaunchOptionsPanel_);
    ltxPromptApiHintLabel_->setWordWrap(true);
    ltxLaunchLayout->addWidget(ltxPromptApiHintLabel_);

    ltxPromptApiExportPathEdit_ = new QLineEdit(ltxLaunchOptionsPanel_);
    ltxPromptApiExportPathEdit_->setObjectName(QStringLiteral("LtxPromptApiExportPathEdit"));
    ltxPromptApiExportPathEdit_->setPlaceholderText(QStringLiteral("Path to ltx_api.json Prompt API export"));
    ltxPromptApiExportPathEdit_->setText(defaultLtxPromptApiExportPath());
    ltxPromptApiExportPathEdit_->setToolTip(QStringLiteral("LTX requires a Comfy Prompt API-format export. This path is sent as prompt_api_export_path."));
    ltxLaunchLayout->addWidget(ltxPromptApiExportPathEdit_);

    auto *ltxButtonsRow = new QHBoxLayout;
    ltxButtonsRow->setContentsMargins(0, 0, 0, 0);
    ltxButtonsRow->setSpacing(8);

    ltxBrowsePromptApiButton_ = new QPushButton(QStringLiteral("Browse API JSON"), ltxLaunchOptionsPanel_);
    ltxBrowsePromptApiButton_->setObjectName(QStringLiteral("SecondaryActionButton"));

    ltxUseDefaultPromptApiButton_ = new QPushButton(QStringLiteral("Use Default"), ltxLaunchOptionsPanel_);
    ltxUseDefaultPromptApiButton_->setObjectName(QStringLiteral("TertiaryActionButton"));

    ltxApplySafeDefaultsButton_ = new QPushButton(QStringLiteral("LTX Defaults"), ltxLaunchOptionsPanel_);
    ltxApplySafeDefaultsButton_->setObjectName(QStringLiteral("TertiaryActionButton"));
    ltxApplySafeDefaultsButton_->setToolTip(QStringLiteral("Apply safe LTX test defaults: 512x320, 33 frames, 24 fps."));

    ltxButtonsRow->addWidget(ltxBrowsePromptApiButton_);
    ltxButtonsRow->addWidget(ltxUseDefaultPromptApiButton_);
    ltxButtonsRow->addWidget(ltxApplySafeDefaultsButton_);
    ltxButtonsRow->addStretch(1);
    ltxLaunchLayout->addLayout(ltxButtonsRow);

    connect(ltxBrowsePromptApiButton_, &QPushButton::clicked, this, [this]() {
        const QString filePath = QFileDialog::getOpenFileName(
            this,
            QStringLiteral("Choose LTX Prompt API export"),
            ltxPromptApiExportPathEdit_ ? QFileInfo(ltxPromptApiExportPathEdit_->text().trimmed()).absolutePath() : QString(),
            QStringLiteral("Comfy Prompt API JSON (*.json);;All Files (*)"));

        if (filePath.isEmpty() || !ltxPromptApiExportPathEdit_)
            return;

        ltxPromptApiExportPathEdit_->setText(QDir::fromNativeSeparators(filePath));
        scheduleUiRefresh();
    });

    connect(ltxUseDefaultPromptApiButton_, &QPushButton::clicked, this, [this]() {
        if (!ltxPromptApiExportPathEdit_)
            return;

        ltxPromptApiExportPathEdit_->setText(defaultLtxPromptApiExportPath());
        scheduleUiRefresh();
    });

    connect(ltxApplySafeDefaultsButton_, &QPushButton::clicked, this, [this]() {
        if (widthSpin_)
            widthSpin_->setValue(512);
        if (heightSpin_)
            heightSpin_->setValue(320);
        if (frameCountSpin_)
            frameCountSpin_->setValue(33);
        if (fpsSpin_)
            fpsSpin_->setValue(24);
        if (stepsSpin_)
            stepsSpin_->setValue(28);
        if (cfgSpin_)
            cfgSpin_->setValue(7.0);
        scheduleUiRefresh();
    });

    connect(ltxPromptApiExportPathEdit_, &QLineEdit::textChanged, this, [this]() {
        scheduleUiRefresh();
    });

    ltxLaunchOptionsPanel_->setVisible(isVideoMode());
    quickControlsLayout->addWidget(ltxLaunchOptionsPanel_);
'''

if "Sprint 15C Pass 29C:" not in cpp:
    marker = '''    quickControlsLayout->addWidget(quickControlsHint);
    leftLayout->addWidget(quickControlsCard);'''
    replacement = '''    quickControlsLayout->addWidget(quickControlsHint);
''' + panel_code + '''
    leftLayout->addWidget(quickControlsCard);'''
    if marker not in cpp:
        raise SystemExit("Could not find Quick Controls insertion marker.")
    cpp = cpp.replace(marker, replacement, 1)


# ----------------------------------------------------------------------
# 5) Draft carries the UI path into the request builder.
# ----------------------------------------------------------------------

if "draft.promptApiExportPath" not in cpp:
    marker = '''    draft.workflowBackend = workflowDraftBackend_;
    draft.workflowMediaType = workflowDraftMediaType_;'''
    replacement = '''    draft.workflowBackend = workflowDraftBackend_;
    draft.workflowMediaType = workflowDraftMediaType_;
    draft.promptApiExportPath = ltxPromptApiExportPathEdit_
                                    ? ltxPromptApiExportPathEdit_->text().trimmed()
                                    : QString();'''
    if marker not in cpp:
        raise SystemExit("Could not find buildRequestPayload workflow draft marker.")
    cpp = cpp.replace(marker, replacement, 1)

cpp_path.write_text(cpp, encoding="utf-8")


# ----------------------------------------------------------------------
# 6) Builder emits Prompt API export fields and has a safe fallback default.
# ----------------------------------------------------------------------

if "default_ltx_api_json" not in builder_cpp:
    marker = '''    payload.insert(QStringLiteral("workflow_backend"), draft.workflowBackend);
    payload.insert(QStringLiteral("workflow_media_type"), draft.workflowMediaType);'''
    replacement = '''    payload.insert(QStringLiteral("workflow_backend"), draft.workflowBackend);
    payload.insert(QStringLiteral("workflow_media_type"), draft.workflowMediaType);

    const QString ltxPromptApiExportPath = draft.promptApiExportPath.trimmed().isEmpty()
                                               ? QStringLiteral("D:/AI_ASSETS/comfy_runtime/ComfyUI/user/default/workflows/ltx_api.json")
                                               : draft.promptApiExportPath.trimmed();
    payload.insert(QStringLiteral("prompt_api_export_path"), ltxPromptApiExportPath);
    payload.insert(QStringLiteral("api_workflow_path"), ltxPromptApiExportPath);
    payload.insert(QStringLiteral("ltx_prompt_api_export_path"), ltxPromptApiExportPath);
    payload.insert(QStringLiteral("default_ltx_api_json"), ltxPromptApiExportPath);'''
    if marker not in builder_cpp:
        raise SystemExit("Could not find builder workflow metadata marker.")
    builder_cpp = builder_cpp.replace(marker, replacement, 1)

if "ltx_prompt_api_export_path" in builder_cpp and "payload.insert(QStringLiteral(\"prompt_api_export_path\"), ltxPromptApiExportPath);" not in builder_cpp:
    raise SystemExit("Prompt API export path insertion did not land correctly.")

# Ensure the LTX route block keeps these explicit after command rewrite.
route_marker = '''            payload.insert(QStringLiteral("video_backend_name"), QStringLiteral("LTX Prompt API"));'''
route_replacement = '''            payload.insert(QStringLiteral("video_backend_name"), QStringLiteral("LTX Prompt API"));
            payload.insert(QStringLiteral("prompt_api_export_path"), ltxPromptApiExportPath);
            payload.insert(QStringLiteral("api_workflow_path"), ltxPromptApiExportPath);
            payload.insert(QStringLiteral("ltx_prompt_api_export_path"), ltxPromptApiExportPath);'''

if "payload.insert(QStringLiteral(\"ltx_prompt_api_export_path\"), ltxPromptApiExportPath);" not in builder_cpp[builder_cpp.find("Sprint 15C Pass 29B:"):]:
    if route_marker not in builder_cpp:
        raise SystemExit("Could not find LTX route marker for explicit prompt API path.")
    builder_cpp = builder_cpp.replace(route_marker, route_replacement, 1)

builder_cpp_path.write_text(builder_cpp, encoding="utf-8")


# ----------------------------------------------------------------------
# 7) Documentation.
# ----------------------------------------------------------------------

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text("""# Sprint 15C Pass 29C — LTX Launch Options Panel

## Goal

Expose the missing LTX launch requirement directly in the T2V/I2V UI: the Comfy Prompt API export path.

## What changed

- Added an LTX Launch Options panel to video generation pages.
- Added a Prompt API export path field.
- Added Browse API JSON.
- Added Use Default.
- Added LTX Defaults:
  - 512x320
  - 33 frames
  - 24 fps
  - 28 steps
  - CFG 7.0
- The generation payload now emits:
  - `prompt_api_export_path`
  - `api_workflow_path`
  - `ltx_prompt_api_export_path`

## Why this matters

The worker-side LTX adapter blocks submission unless a valid Prompt API graph is provided. Pass 29B routed LTX Generate to the right worker path, but the UI still did not expose the required API export field.

## Expected behavior

With an LTX model stack selected, T2V/I2V users can now provide or accept the default `ltx_api.json` Prompt API export path before pressing Generate.
""", encoding="utf-8")

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 29C: LTX launch options panel and Prompt API export path.")
