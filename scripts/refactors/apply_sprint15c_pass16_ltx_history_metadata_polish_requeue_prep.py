from pathlib import Path
import re

root = Path(".")
history_h = root / "qt_ui" / "T2VHistoryPage.h"
history_cpp = root / "qt_ui" / "T2VHistoryPage.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS16_LTX_HISTORY_METADATA_POLISH_REQUEUE_PREP_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass16_ltx_history_metadata_polish_requeue_prep.py"

cpp = history_cpp.read_text(encoding="utf-8")

for include in [
    "#include <QDateTime>",
    "#include <QtGlobal>",
]:
    if include not in cpp:
        cpp = cpp.replace("#include <QFile>", "#include <QFile>\n" + include, 1)

helper_anchor = r'''QString compactPromptPreview(const QString &prompt)
{
    const QString compact = prompt.simplified();
    if (compact.size() <= 260)
        return compact;
    return compact.left(257) + QStringLiteral("...");
}

'''

new_helpers = r'''int registryIntValue(const QJsonObject &record, const QStringList &keys, int fallback = 0)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = record.value(key);
        if (value.isDouble())
            return value.toInt();
        if (value.isString())
        {
            bool ok = false;
            const int parsed = value.toString().trimmed().toInt(&ok);
            if (ok)
                return parsed;
        }
    }
    return fallback;
}

double registryDoubleValue(const QJsonObject &record, const QStringList &keys, double fallback = 0.0)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = record.value(key);
        if (value.isDouble())
            return value.toDouble();
        if (value.isString())
        {
            bool ok = false;
            const double parsed = value.toString().trimmed().toDouble(&ok);
            if (ok)
                return parsed;
        }
    }
    return fallback;
}

QString ltxResolutionLabel(const QJsonObject &record)
{
    const int width = registryIntValue(record, {QStringLiteral("width"), QStringLiteral("video_width")});
    const int height = registryIntValue(record, {QStringLiteral("height"), QStringLiteral("video_height")});

    if (width > 0 && height > 0)
        return QStringLiteral("%1x%2").arg(width).arg(height);

    return QStringLiteral("unknown");
}

QString ltxDurationLabel(const QJsonObject &record)
{
    const int frames = registryIntValue(record, {QStringLiteral("frames"), QStringLiteral("frame_count")});
    const double fps = registryDoubleValue(record, {QStringLiteral("fps"), QStringLiteral("frame_rate")});

    if (frames > 0 && fps > 0.0)
    {
        const double seconds = static_cast<double>(frames) / fps;
        return QStringLiteral("%1 frames @ %2 fps (%3s)")
            .arg(frames)
            .arg(QString::number(fps, 'f', fps == static_cast<int>(fps) ? 0 : 2))
            .arg(QString::number(seconds, 'f', 1));
    }

    if (frames > 0)
        return QStringLiteral("%1 frames").arg(frames);

    return QStringLiteral("LTX");
}

QString ltxFinishedLabel(const QJsonObject &record)
{
    const QString rawTimestamp = firstRegistryString(record, {
        QStringLiteral("registered_at"),
        QStringLiteral("created_at"),
        QStringLiteral("finished_at"),
        QStringLiteral("completed_at"),
    });

    if (rawTimestamp.isEmpty())
        return QStringLiteral("unknown");

    QDateTime parsed = QDateTime::fromString(rawTimestamp, Qt::ISODateWithMs);
    if (!parsed.isValid())
        parsed = QDateTime::fromString(rawTimestamp, Qt::ISODate);

    if (parsed.isValid())
        return parsed.toLocalTime().toString(QStringLiteral("MMM d, h:mm AP"));

    return rawTimestamp;
}

QString ltxRuntimeSummary(const QJsonObject &record)
{
    const QString promptId = firstRegistryString(record, {
        QStringLiteral("registry_prompt_id"),
        QStringLiteral("prompt_id"),
    });

    if (!promptId.isEmpty())
        return QStringLiteral("LTX registry • comfy_prompt_api • requeue-ready • %1").arg(promptId);

    return QStringLiteral("LTX registry • comfy_prompt_api • requeue-ready");
}

'''

if "ltxResolutionLabel(const QJsonObject &record)" not in cpp:
    if helper_anchor not in cpp:
        raise SystemExit("Could not find compactPromptPreview helper block in T2VHistoryPage.cpp.")
    cpp = cpp.replace(helper_anchor, helper_anchor + new_helpers, 1)

# Detect existing VideoHistoryItem label members from the current file.
resolution_member = None
for candidate in ["resolutionLabel", "resolution", "resolutionText"]:
    if re.search(rf"\bitem\.{candidate}\s*=", cpp):
        resolution_member = candidate
        break

finished_member = None
for candidate in ["finishedLabel", "finishedAtLabel", "finished", "finishedText", "finishedAtText"]:
    if re.search(rf"\bitem\.{candidate}\s*=", cpp):
        finished_member = candidate
        break

duration_block_old = '''        item.durationLabel = QStringLiteral("LTX");
        item.runtimeSummary = QStringLiteral("LTX registry • comfy_prompt_api");
'''

extra_assignments = ""
if resolution_member:
    extra_assignments += f'        item.{resolution_member} = ltxResolutionLabel(record);\n'
if finished_member:
    extra_assignments += f'        item.{finished_member} = ltxFinishedLabel(record);\n'

duration_block_new = f'''        item.durationLabel = ltxDurationLabel(record);
{extra_assignments}        item.runtimeSummary = ltxRuntimeSummary(record);
'''

if duration_block_old in cpp:
    cpp = cpp.replace(duration_block_old, duration_block_new, 1)
else:
    # Idempotent fallback for already partially edited files.
    cpp = cpp.replace(
        '        item.durationLabel = QStringLiteral("LTX");',
        '        item.durationLabel = ltxDurationLabel(record);',
        1,
    )
    cpp = cpp.replace(
        '        item.runtimeSummary = QStringLiteral("LTX registry • comfy_prompt_api");',
        '        item.runtimeSummary = ltxRuntimeSummary(record);',
        1,
    )

history_cpp.write_text(cpp, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
'''# Sprint 15C Pass 16 — LTX History Metadata Polish and Requeue Prep

## Goal

Polish LTX records in the T2V History page and prepare the row metadata for future requeue/rerun actions.

## What changed

- LTX History rows now map registry metadata into visible labels:
  - `width` + `height` → resolution label
  - `frames` + `fps` → duration label
  - `registered_at` / `created_at` → finished label when supported by the current `VideoHistoryItem` shape
- LTX runtime summary now includes:
  - `LTX registry`
  - `comfy_prompt_api`
  - `requeue-ready`
  - registry prompt id when available

## Why this pass exists

Pass 15 proved LTX records can appear in History, but the first version still showed some generic `unknown` values. Pass 16 uses the durable registry metadata already written by Pass 12.

## Expected UI behavior

The LTX row should no longer show generic `LTX` / `unknown` where metadata exists. It should display the registry resolution, frame count/fps duration, and a local finished timestamp where the current UI item structure supports it.

## Requeue prep

This pass does not add the final Requeue button yet. It makes the LTX History item carry enough stable context for the next pass to create a requeue command from the selected history row.
''',
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 16 LTX history metadata polish and requeue prep.")
print(f"Detected resolution member: {resolution_member or '<none>'}")
print(f"Detected finished member: {finished_member or '<none>'}")
