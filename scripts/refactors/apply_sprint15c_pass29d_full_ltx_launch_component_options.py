from pathlib import Path

h_path = Path("qt_ui/ImageGenerationPage.h")
cpp_path = Path("qt_ui/ImageGenerationPage.cpp")
builder_h_path = Path("qt_ui/generation/GenerationRequestBuilder.h")
builder_cpp_path = Path("qt_ui/generation/GenerationRequestBuilder.cpp")
doc_path = Path("docs/sprints/SPRINT15C_PASS29D_FULL_LTX_LAUNCH_COMPONENT_OPTIONS_README.md")
script_path = Path("scripts/refactors/apply_sprint15c_pass29d_full_ltx_launch_component_options.py")

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")
builder_h = builder_h_path.read_text(encoding="utf-8")
builder_cpp = builder_cpp_path.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# 1) GenerationRequestDraft carries explicit LTX component options.
# ----------------------------------------------------------------------

if "QString ltxPrimaryModelName;" not in builder_h:
    marker = '''    QString workflowMediaType;
    QString promptApiExportPath;

    QVector<LoraRequestEntry> loras;'''
    replacement = '''    QString workflowMediaType;
    QString promptApiExportPath;

    QString ltxPrimaryModelName;
    QString ltxTextEncoderName;
    QString ltxTextProjectionName;
    QString ltxAudioVaeName;
    QString ltxVideoVaeName;
    QString ltxVisionEncoderName;
    QString ltxOutputVariant;

    QVector<LoraRequestEntry> loras;'''
    if marker not in builder_h:
        raise SystemExit("Could not find promptApiExportPath marker in GenerationRequestBuilder.h.")
    builder_h = builder_h.replace(marker, replacement, 1)

builder_h_path.write_text(builder_h, encoding="utf-8")


# ----------------------------------------------------------------------
# 2) ImageGenerationPage owns explicit LTX component fields.
# ----------------------------------------------------------------------

if "ltxTextProjectionNameEdit_" not in h:
    marker = '''    QLineEdit *ltxPromptApiExportPathEdit_ = nullptr;
    QLabel *ltxPromptApiHintLabel_ = nullptr;'''
    replacement = '''    QLineEdit *ltxPromptApiExportPathEdit_ = nullptr;
    QLineEdit *ltxPrimaryModelNameEdit_ = nullptr;
    QLineEdit *ltxTextEncoderNameEdit_ = nullptr;
    QLineEdit *ltxTextProjectionNameEdit_ = nullptr;
    QLineEdit *ltxAudioVaeNameEdit_ = nullptr;
    QLineEdit *ltxVideoVaeNameEdit_ = nullptr;
    QLineEdit *ltxVisionEncoderNameEdit_ = nullptr;
    QLineEdit *ltxOutputVariantEdit_ = nullptr;
    QLabel *ltxPromptApiHintLabel_ = nullptr;'''
    if marker not in h:
        raise SystemExit("Could not find LTX prompt API edit marker in ImageGenerationPage.h.")
    h = h.replace(marker, replacement, 1)

h_path.write_text(h, encoding="utf-8")


# ----------------------------------------------------------------------
# 3) Add tiny helper for LTX component row creation.
# ----------------------------------------------------------------------

helper = r'''
QLineEdit *createLtxComponentEdit(QWidget *parent,
                                  QVBoxLayout *layout,
                                  const QString &label,
                                  const QString &defaultValue,
                                  const QString &tooltip)
{
    if (!parent || !layout)
        return nullptr;

    auto *caption = createSectionBody(label, parent);
    caption->setMaximumHeight(18);
    layout->addWidget(caption);

    auto *edit = new QLineEdit(parent);
    edit->setText(defaultValue);
    edit->setPlaceholderText(defaultValue);
    edit->setToolTip(tooltip);
    edit->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    layout->addWidget(edit);

    return edit;
}

'''

if "createLtxComponentEdit" not in cpp:
    marker = '''QString defaultLtxPromptApiExportPath()'''
    if marker not in cpp:
        raise SystemExit("Could not find defaultLtxPromptApiExportPath insertion marker.")
    cpp = cpp.replace(marker, helper + "\n" + marker, 1)


# ----------------------------------------------------------------------
# 4) Insert explicit LTX fields into the existing LTX Launch Options panel.
# ----------------------------------------------------------------------

field_marker = '''    ltxLaunchLayout->addWidget(ltxPromptApiExportPathEdit_);

    auto *ltxButtonsRow = new QHBoxLayout;'''

field_insert = r'''    ltxLaunchLayout->addWidget(ltxPromptApiExportPathEdit_);

    ltxPrimaryModelNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Primary checkpoint"),
        QStringLiteral("ltx/ltx-2.3-22b-dev.safetensors"),
        QStringLiteral("LTX primary checkpoint sent as video_primary_model_name."));

    ltxTextEncoderNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Text encoder"),
        QStringLiteral("ltx/comfy_gemma_3_12B_it.safetensors"),
        QStringLiteral("Gemma text encoder for LTX."));

    ltxTextProjectionNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Text projection"),
        QStringLiteral("ltx-2.3_text_projection_bf16.safetensors"),
        QStringLiteral("LTX 2.3 text projection model."));

    ltxAudioVaeNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Audio VAE"),
        QStringLiteral("ltx/LTX23_audio_vae_bf16.safetensors"),
        QStringLiteral("LTX audio VAE component."));

    ltxVideoVaeNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Video VAE"),
        QStringLiteral("ltx/LTX23_video_vae_bf16.safetensors"),
        QStringLiteral("LTX video VAE component."));

    ltxVisionEncoderNameEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Vision encoder"),
        QStringLiteral("clip_vision_g"),
        QStringLiteral("Vision encoder used by LTX/I2V-capable graphs."));

    ltxOutputVariantEdit_ = createLtxComponentEdit(
        ltxLaunchOptionsPanel_,
        ltxLaunchLayout,
        QStringLiteral("Preferred output"),
        QStringLiteral("distilled"),
        QStringLiteral("Preferred LTX output variant. Use distilled for the better preview/output when available."));

    auto *ltxButtonsRow = new QHBoxLayout;'''

if "ltxTextProjectionNameEdit_ = createLtxComponentEdit" not in cpp:
    if field_marker not in cpp:
        raise SystemExit("Could not find LTX panel field marker.")
    cpp = cpp.replace(field_marker, field_insert, 1)


# ----------------------------------------------------------------------
# 5) LTX Defaults now fills component fields too.
# ----------------------------------------------------------------------

default_marker = '''        if (cfgSpin_)
            cfgSpin_->setValue(7.0);
        scheduleUiRefresh();
    });'''

default_replacement = '''        if (cfgSpin_)
            cfgSpin_->setValue(7.0);

        if (ltxPromptApiExportPathEdit_)
            ltxPromptApiExportPathEdit_->setText(defaultLtxPromptApiExportPath());
        if (ltxPrimaryModelNameEdit_)
            ltxPrimaryModelNameEdit_->setText(QStringLiteral("ltx/ltx-2.3-22b-dev.safetensors"));
        if (ltxTextEncoderNameEdit_)
            ltxTextEncoderNameEdit_->setText(QStringLiteral("ltx/comfy_gemma_3_12B_it.safetensors"));
        if (ltxTextProjectionNameEdit_)
            ltxTextProjectionNameEdit_->setText(QStringLiteral("ltx-2.3_text_projection_bf16.safetensors"));
        if (ltxAudioVaeNameEdit_)
            ltxAudioVaeNameEdit_->setText(QStringLiteral("ltx/LTX23_audio_vae_bf16.safetensors"));
        if (ltxVideoVaeNameEdit_)
            ltxVideoVaeNameEdit_->setText(QStringLiteral("ltx/LTX23_video_vae_bf16.safetensors"));
        if (ltxVisionEncoderNameEdit_)
            ltxVisionEncoderNameEdit_->setText(QStringLiteral("clip_vision_g"));
        if (ltxOutputVariantEdit_)
            ltxOutputVariantEdit_->setText(QStringLiteral("distilled"));

        // Also try to select the matching model stack if the catalog contains it.
        trySetSelectedModelByCandidate({
            QStringLiteral("ltx-2.3-22b-dev"),
            QStringLiteral("ltx/ltx-2.3-22b-dev"),
            QStringLiteral("ltx-2.3"),
            QStringLiteral("ltx")
        });
        syncVideoComponentControlsFromSelectedStack();
        updateAssetIntelligenceUi();

        scheduleUiRefresh();
    });'''

if "ltxTextEncoderNameEdit_->setText(QStringLiteral(\"ltx/comfy_gemma_3_12B_it.safetensors\"));" not in cpp:
    if default_marker not in cpp:
        raise SystemExit("Could not find LTX Defaults lambda marker.")
    cpp = cpp.replace(default_marker, default_replacement, 1)


# ----------------------------------------------------------------------
# 6) Text changes refresh readiness.
# ----------------------------------------------------------------------

connect_marker = '''    connect(ltxPromptApiExportPathEdit_, &QLineEdit::textChanged, this, [this]() {
        scheduleUiRefresh();
    });'''

connect_replacement = '''    connect(ltxPromptApiExportPathEdit_, &QLineEdit::textChanged, this, [this]() {
        scheduleUiRefresh();
    });

    const QList<QLineEdit *> ltxOptionEdits = {
        ltxPrimaryModelNameEdit_,
        ltxTextEncoderNameEdit_,
        ltxTextProjectionNameEdit_,
        ltxAudioVaeNameEdit_,
        ltxVideoVaeNameEdit_,
        ltxVisionEncoderNameEdit_,
        ltxOutputVariantEdit_
    };

    for (QLineEdit *edit : ltxOptionEdits)
    {
        if (!edit)
            continue;

        connect(edit, &QLineEdit::textChanged, this, [this]() {
            scheduleUiRefresh();
        });
    }'''

if "const QList<QLineEdit *> ltxOptionEdits" not in cpp:
    if connect_marker not in cpp:
        raise SystemExit("Could not find LTX prompt API textChanged connect marker.")
    cpp = cpp.replace(connect_marker, connect_replacement, 1)


# ----------------------------------------------------------------------
# 7) buildRequestPayload copies LTX fields into draft.
# ----------------------------------------------------------------------

payload_marker = '''    draft.promptApiExportPath = ltxPromptApiExportPathEdit_
                                    ? ltxPromptApiExportPathEdit_->text().trimmed()
                                    : QString();'''

payload_replacement = '''    draft.promptApiExportPath = ltxPromptApiExportPathEdit_
                                    ? ltxPromptApiExportPathEdit_->text().trimmed()
                                    : QString();
    draft.ltxPrimaryModelName = ltxPrimaryModelNameEdit_ ? ltxPrimaryModelNameEdit_->text().trimmed() : QString();
    draft.ltxTextEncoderName = ltxTextEncoderNameEdit_ ? ltxTextEncoderNameEdit_->text().trimmed() : QString();
    draft.ltxTextProjectionName = ltxTextProjectionNameEdit_ ? ltxTextProjectionNameEdit_->text().trimmed() : QString();
    draft.ltxAudioVaeName = ltxAudioVaeNameEdit_ ? ltxAudioVaeNameEdit_->text().trimmed() : QString();
    draft.ltxVideoVaeName = ltxVideoVaeNameEdit_ ? ltxVideoVaeNameEdit_->text().trimmed() : QString();
    draft.ltxVisionEncoderName = ltxVisionEncoderNameEdit_ ? ltxVisionEncoderNameEdit_->text().trimmed() : QString();
    draft.ltxOutputVariant = ltxOutputVariantEdit_ ? ltxOutputVariantEdit_->text().trimmed() : QString();'''

if "draft.ltxTextProjectionName" not in cpp:
    if payload_marker not in cpp:
        raise SystemExit("Could not find draft.promptApiExportPath assignment marker.")
    cpp = cpp.replace(payload_marker, payload_replacement, 1)

cpp_path.write_text(cpp, encoding="utf-8")


# ----------------------------------------------------------------------
# 8) Builder emits all explicit LTX aliases expected by Python worker/adapter.
# ----------------------------------------------------------------------

builder_marker = '''    payload.insert(QStringLiteral("default_ltx_api_json"), ltxPromptApiExportPath);'''

builder_insert = '''    payload.insert(QStringLiteral("default_ltx_api_json"), ltxPromptApiExportPath);

    const QString ltxPrimaryModelName = draft.ltxPrimaryModelName.trimmed().isEmpty()
                                            ? (draft.model.trimmed().isEmpty()
                                                   ? QStringLiteral("ltx/ltx-2.3-22b-dev.safetensors")
                                                   : draft.model.trimmed())
                                            : draft.ltxPrimaryModelName.trimmed();
    const QString ltxTextEncoderName = draft.ltxTextEncoderName.trimmed().isEmpty()
                                           ? QStringLiteral("ltx/comfy_gemma_3_12B_it.safetensors")
                                           : draft.ltxTextEncoderName.trimmed();
    const QString ltxTextProjectionName = draft.ltxTextProjectionName.trimmed().isEmpty()
                                              ? QStringLiteral("ltx-2.3_text_projection_bf16.safetensors")
                                              : draft.ltxTextProjectionName.trimmed();
    const QString ltxAudioVaeName = draft.ltxAudioVaeName.trimmed().isEmpty()
                                        ? QStringLiteral("ltx/LTX23_audio_vae_bf16.safetensors")
                                        : draft.ltxAudioVaeName.trimmed();
    const QString ltxVideoVaeName = draft.ltxVideoVaeName.trimmed().isEmpty()
                                        ? QStringLiteral("ltx/LTX23_video_vae_bf16.safetensors")
                                        : draft.ltxVideoVaeName.trimmed();
    const QString ltxVisionEncoderName = draft.ltxVisionEncoderName.trimmed().isEmpty()
                                             ? QStringLiteral("clip_vision_g")
                                             : draft.ltxVisionEncoderName.trimmed();
    const QString ltxOutputVariant = draft.ltxOutputVariant.trimmed().isEmpty()
                                         ? QStringLiteral("distilled")
                                         : draft.ltxOutputVariant.trimmed();

    payload.insert(QStringLiteral("video_primary_model_name"), ltxPrimaryModelName);
    payload.insert(QStringLiteral("ltx_primary_model_name"), ltxPrimaryModelName);
    payload.insert(QStringLiteral("video_checkpoint_name"), ltxPrimaryModelName);

    payload.insert(QStringLiteral("video_text_encoder_name"), ltxTextEncoderName);
    payload.insert(QStringLiteral("ltx_text_encoder_name"), ltxTextEncoderName);

    payload.insert(QStringLiteral("video_text_projection_name"), ltxTextProjectionName);
    payload.insert(QStringLiteral("ltx_text_projection_name"), ltxTextProjectionName);

    payload.insert(QStringLiteral("video_audio_vae_name"), ltxAudioVaeName);
    payload.insert(QStringLiteral("ltx_audio_vae_name"), ltxAudioVaeName);

    payload.insert(QStringLiteral("video_video_vae_name"), ltxVideoVaeName);
    payload.insert(QStringLiteral("video_vae_name"), ltxVideoVaeName);
    payload.insert(QStringLiteral("ltx_video_vae_name"), ltxVideoVaeName);

    payload.insert(QStringLiteral("video_vision_encoder_name"), ltxVisionEncoderName);
    payload.insert(QStringLiteral("ltx_vision_encoder_name"), ltxVisionEncoderName);
    payload.insert(QStringLiteral("preferred_ltx_output_variant"), ltxOutputVariant);'''

if "video_text_projection_name" not in builder_cpp:
    if builder_marker not in builder_cpp:
        raise SystemExit("Could not find default_ltx_api_json marker.")
    builder_cpp = builder_cpp.replace(builder_marker, builder_insert, 1)


route_marker = '''            payload.insert(QStringLiteral("ltx_prompt_api_export_path"), ltxPromptApiExportPath);'''

route_insert = '''            payload.insert(QStringLiteral("ltx_prompt_api_export_path"), ltxPromptApiExportPath);
            payload.insert(QStringLiteral("video_primary_model_name"), ltxPrimaryModelName);
            payload.insert(QStringLiteral("video_text_encoder_name"), ltxTextEncoderName);
            payload.insert(QStringLiteral("video_text_projection_name"), ltxTextProjectionName);
            payload.insert(QStringLiteral("video_audio_vae_name"), ltxAudioVaeName);
            payload.insert(QStringLiteral("video_video_vae_name"), ltxVideoVaeName);
            payload.insert(QStringLiteral("video_vision_encoder_name"), ltxVisionEncoderName);
            payload.insert(QStringLiteral("preferred_ltx_output_variant"), ltxOutputVariant);'''

if "preferred_ltx_output_variant" in builder_cpp and "payload.insert(QStringLiteral(\"video_video_vae_name\"), ltxVideoVaeName);" not in builder_cpp[builder_cpp.find("Sprint 15C Pass 29B:"):]:
    if route_marker not in builder_cpp:
        raise SystemExit("Could not find route prompt API export marker.")
    builder_cpp = builder_cpp.replace(route_marker, route_insert, 1)

builder_cpp_path.write_text(builder_cpp, encoding="utf-8")


# ----------------------------------------------------------------------
# 9) Documentation.
# ----------------------------------------------------------------------

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text("""# Sprint 15C Pass 29D — Full LTX Launch Component Options

## Goal

Expose the remaining LTX runtime options that are required for first-class Generate, instead of relying on hidden requeue-only defaults.

## Added to the T2V/I2V LTX panel

- Primary checkpoint
- Text encoder
- Text projection
- Audio VAE
- Video VAE
- Vision encoder
- Preferred output variant

## Payload aliases emitted

- `video_primary_model_name`
- `video_text_encoder_name`
- `video_text_projection_name`
- `video_audio_vae_name`
- `video_video_vae_name`
- `video_vae_name`
- `video_vision_encoder_name`
- `preferred_ltx_output_variant`

## Defaults

- `ltx/ltx-2.3-22b-dev.safetensors`
- `ltx/comfy_gemma_3_12B_it.safetensors`
- `ltx-2.3_text_projection_bf16.safetensors`
- `ltx/LTX23_audio_vae_bf16.safetensors`
- `ltx/LTX23_video_vae_bf16.safetensors`
- `clip_vision_g`
- `distilled`

## Expected result

T2V/I2V LTX now exposes the user-editable launch requirements needed by the Prompt API adapter before submission.
""", encoding="utf-8")

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 29D: full LTX launch component options.")
