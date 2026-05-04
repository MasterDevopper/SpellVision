from pathlib import Path
import re

root = Path(".")
image_cpp = root / "qt_ui" / "ImageGenerationPage.cpp"
history_cpp = root / "qt_ui" / "T2VHistoryPage.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS25_NO_STARTUP_VIDEO_RESTORE_DISTILLED_LTX_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass25_no_startup_video_restore_distilled_ltx.py"

img = image_cpp.read_text(encoding="utf-8")
hist = history_cpp.read_text(encoding="utf-8")

# ----------------------------------------------------------------------
# 1) T2V startup should not auto-load the last generated video preview.
#    Keep restoreSnapshot() for prompts/settings, but clear restored video preview state.
# ----------------------------------------------------------------------

old_ctor = '''    reloadCatalogs();
    restoreSnapshot();
    updateAdaptiveLayout();
    updatePrimaryActionAvailability();
    schedulePreviewRefresh(busy_ ? 0 : 30);
'''

new_ctor = '''    reloadCatalogs();
    restoreSnapshot();

    // Sprint 15C Pass 25:
    // Restoring the last generated video into T2V on startup is not intended.
    // Keep restored controls/prompts, but do not bind media automatically.
    // Users can still open History or Queue to inspect prior outputs explicitly.
    if (isVideoMode())
    {
        generatedPreviewPath_.clear();
        generatedPreviewCaption_.clear();

        if (mediaPreviewController_)
            mediaPreviewController_->clearVideoPreview();
    }

    updateAdaptiveLayout();
    updatePrimaryActionAvailability();
    schedulePreviewRefresh(busy_ ? 0 : 30);
'''

if old_ctor not in img:
    raise SystemExit("Could not find ImageGenerationPage constructor restoreSnapshot block.")

img = img.replace(old_ctor, new_ctor, 1)
image_cpp.write_text(img, encoding="utf-8")

# ----------------------------------------------------------------------
# 2) LTX history/preview should prefer distilled output over full output.
#    Existing registry records store primary_output_path as full, so Qt must
#    prefer outputs[] role=distilled when present.
# ----------------------------------------------------------------------

helper = r'''
QJsonObject preferredLtxRegistryOutputObject(const QJsonObject &record)
{
    const QJsonArray outputs = firstRegistryArray(record, {
        QStringLiteral("outputs"),
        QStringLiteral("ui_outputs"),
    });

    for (const QJsonValue &value : outputs)
    {
        if (!value.isObject())
            continue;

        const QJsonObject output = value.toObject();
        const QString role = output.value(QStringLiteral("role")).toString().trimmed().toLower();

        if (role == QStringLiteral("distilled"))
            return output;
    }

    for (const QJsonValue &value : outputs)
    {
        if (!value.isObject())
            continue;

        const QJsonObject output = value.toObject();
        const QString filename = firstRegistryString(output, {
            QStringLiteral("filename"),
            QStringLiteral("path"),
            QStringLiteral("preview_path"),
            QStringLiteral("output_path"),
        }).toLower();

        if (filename.contains(QStringLiteral("output_d_")) || filename.contains(QStringLiteral("_d_")))
            return output;
    }

    for (const QJsonValue &value : outputs)
    {
        if (!value.isObject())
            continue;

        const QJsonObject output = value.toObject();
        const QString role = output.value(QStringLiteral("role")).toString().trimmed().toLower();

        if (role == QStringLiteral("full"))
            return output;
    }

    for (const QJsonValue &value : outputs)
    {
        if (value.isObject())
            return value.toObject();
    }

    return {};
}

QJsonObject preferredLtxUiOutputObject(const QJsonArray &outputs)
{
    for (const QJsonValue &value : outputs)
    {
        if (!value.isObject())
            continue;

        const QJsonObject output = value.toObject();
        const QString role = output.value(QStringLiteral("role")).toString().trimmed().toLower();

        if (role == QStringLiteral("distilled"))
            return output;
    }

    for (const QJsonValue &value : outputs)
    {
        if (!value.isObject())
            continue;

        const QJsonObject output = value.toObject();
        const QString filename = output.value(QStringLiteral("filename")).toString().toLower()
            + QStringLiteral(" ")
            + output.value(QStringLiteral("path")).toString().toLower();

        if (filename.contains(QStringLiteral("output_d_")) || filename.contains(QStringLiteral("_d_")))
            return output;
    }

    for (const QJsonValue &value : outputs)
    {
        if (value.isObject())
            return value.toObject();
    }

    return {};
}

'''

if "preferredLtxRegistryOutputObject" not in hist:
    marker = "QString registryOutputPathFromRecord(const QJsonObject &record)"
    index = hist.find(marker)
    if index < 0:
        raise SystemExit("Could not find registryOutputPathFromRecord marker.")
    hist = hist[:index] + helper + "\n" + hist[index:]

# Prefer distilled in registryOutputPathFromRecord before direct primary_output_path.
old_output_start = '''QString registryOutputPathFromRecord(const QJsonObject &record)
{
    const QString direct = firstRegistryString(record, {
'''

new_output_start = '''QString registryOutputPathFromRecord(const QJsonObject &record)
{
    const QJsonObject preferredOutput = preferredLtxRegistryOutputObject(record);
    const QString preferredPath = firstRegistryString(preferredOutput, {
        QStringLiteral("path"),
        QStringLiteral("preview_path"),
        QStringLiteral("output_path"),
        QStringLiteral("uri"),
    });
    if (!preferredPath.isEmpty())
        return preferredPath;

    const QString direct = firstRegistryString(record, {
'''

if old_output_start not in hist:
    raise SystemExit("Could not patch registryOutputPathFromRecord opening block.")

hist = hist.replace(old_output_start, new_output_start, 1)

# Prefer distilled metadata sidecar before direct primary_metadata_path.
old_metadata_start = '''QString registryMetadataPathFromRecord(const QJsonObject &record)
{
    const QString direct = firstRegistryString(record, {
'''

new_metadata_start = '''QString registryMetadataPathFromRecord(const QJsonObject &record)
{
    const QJsonObject preferredOutput = preferredLtxRegistryOutputObject(record);
    const QString preferredMetadata = firstRegistryString(preferredOutput, {
        QStringLiteral("metadata_path"),
        QStringLiteral("primary_metadata_path"),
        QStringLiteral("metadata_output"),
    });
    if (!preferredMetadata.isEmpty())
        return preferredMetadata;

    const QString direct = firstRegistryString(record, {
'''

if old_metadata_start not in hist:
    raise SystemExit("Could not patch registryMetadataPathFromRecord opening block.")

hist = hist.replace(old_metadata_start, new_metadata_start, 1)

# In the Pass 23 queue/preview contract builder, prefer distilled ui_outputs over primary_output/full.
old_contract_output_block = '''    const QJsonArray uiOutputs = response.value(QStringLiteral("ui_outputs")).toArray();
    const QJsonObject firstUiOutput = firstObjectFromArray(uiOutputs);

    QJsonObject output = resultPrimaryOutput;
    if (output.isEmpty())
        output = firstUiOutput;
'''

new_contract_output_block = '''    const QJsonArray uiOutputs = response.value(QStringLiteral("ui_outputs")).toArray();
    const QJsonObject preferredUiOutput = preferredLtxUiOutputObject(uiOutputs);
    const QJsonObject firstUiOutput = firstObjectFromArray(uiOutputs);

    QJsonObject output = preferredUiOutput;
    if (output.isEmpty())
        output = resultPrimaryOutput;
    if (output.isEmpty())
        output = firstUiOutput;
'''

if old_contract_output_block in hist:
    hist = hist.replace(old_contract_output_block, new_contract_output_block, 1)
elif "preferredLtxUiOutputObject(uiOutputs)" not in hist:
    raise SystemExit("Could not find queue/preview contract output block to patch.")

history_cpp.write_text(hist, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 25 — Disable Startup Video Restore and Prefer LTX Distilled Output\n\n"
    "Fixes two UX regressions discovered after Pass 24:\n\n"
    "1. T2V no longer auto-loads the last generated video preview on startup. `restoreSnapshot()` still restores controls and prompts, but video preview state is cleared for video modes.\n"
    "2. LTX history/preview paths now prefer `role=distilled` outputs over `role=full` outputs when available.\n\n"
    "This prevents Home/T2V startup from probing the previous MP4 and ensures LTX uses the better distilled render for preview/history surfaces.\n",
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 25 startup video restore disable + LTX distilled preference.")
