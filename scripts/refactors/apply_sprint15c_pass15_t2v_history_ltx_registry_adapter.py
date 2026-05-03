from pathlib import Path
import re

root = Path(".")
history_h = root / "qt_ui" / "T2VHistoryPage.h"
history_cpp = root / "qt_ui" / "T2VHistoryPage.cpp"
doc_path = root / "docs" / "sprints" / "SPRINT15C_PASS15_T2V_HISTORY_LTX_REGISTRY_ADAPTER_README.md"
script_path = root / "scripts" / "refactors" / "apply_sprint15c_pass15_t2v_history_ltx_registry_adapter.py"

h = history_h.read_text(encoding="utf-8")

if "loadLtxRegistryHistoryItems" not in h:
    h = h.replace(
        "    QList<VideoHistoryItem> loadHistoryItems();\n",
        "    QList<VideoHistoryItem> loadHistoryItems();\n"
        "    QList<VideoHistoryItem> loadLtxRegistryHistoryItems() const;\n"
        "    void mergeLtxRegistryHistoryItems(QList<VideoHistoryItem> &items) const;\n",
        1,
    )

history_h.write_text(h, encoding="utf-8")

cpp = history_cpp.read_text(encoding="utf-8")

for include in [
    "#include <QFileInfo>",
    "#include <QProcessEnvironment>",
    "#include <QSet>",
]:
    if include not in cpp:
        cpp = cpp.replace("#include <QFile>", "#include <QFile>\n" + include, 1)

helpers = r'''
QString firstRegistryString(const QJsonObject &obj, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QString value = obj.value(key).toString().trimmed();
        if (!value.isEmpty())
            return value;
    }
    return QString();
}

QJsonObject firstRegistryObject(const QJsonObject &obj, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = obj.value(key);
        if (value.isObject())
            return value.toObject();
    }
    return {};
}

QJsonArray firstRegistryArray(const QJsonObject &obj, const QStringList &keys)
{
    for (const QString &key : keys)
    {
        const QJsonValue value = obj.value(key);
        if (value.isArray())
            return value.toArray();
    }
    return {};
}

QString ltxRegistryHistoryPath()
{
    const QProcessEnvironment env = QProcessEnvironment::systemEnvironment();

    const QString explicitPath = env.value(QStringLiteral("SPELLVISION_LTX_HISTORY_RECORDS_JSONL")).trimmed();
    if (!explicitPath.isEmpty())
        return QDir::fromNativeSeparators(explicitPath);

    const QString runtimeRoot = env.value(QStringLiteral("SPELLVISION_COMFY_RUNTIME_ROOT")).trimmed();
    if (!runtimeRoot.isEmpty())
    {
        return QDir(QDir::fromNativeSeparators(runtimeRoot))
            .filePath(QStringLiteral("spellvision_registry/history/records.jsonl"));
    }

    const QString assetRoot = env.value(QStringLiteral("SPELLVISION_ASSET_ROOT")).trimmed();
    if (!assetRoot.isEmpty())
    {
        return QDir(QDir::fromNativeSeparators(assetRoot))
            .filePath(QStringLiteral("comfy_runtime/spellvision_registry/history/records.jsonl"));
    }

    return QStringLiteral("D:/AI_ASSETS/comfy_runtime/spellvision_registry/history/records.jsonl");
}

QString registryOutputPathFromRecord(const QJsonObject &record)
{
    const QString direct = firstRegistryString(record, {
        QStringLiteral("primary_output_path"),
        QStringLiteral("output_path"),
        QStringLiteral("video_path"),
        QStringLiteral("path"),
    });
    if (!direct.isEmpty())
        return direct;

    const QJsonObject primary = firstRegistryObject(record, {
        QStringLiteral("primary_output"),
        QStringLiteral("primary"),
    });

    const QString primaryPath = firstRegistryString(primary, {
        QStringLiteral("path"),
        QStringLiteral("preview_path"),
        QStringLiteral("output_path"),
    });
    if (!primaryPath.isEmpty())
        return primaryPath;

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
        if (role != QStringLiteral("full"))
            continue;

        const QString path = firstRegistryString(output, {
            QStringLiteral("path"),
            QStringLiteral("preview_path"),
            QStringLiteral("output_path"),
        });
        if (!path.isEmpty())
            return path;
    }

    for (const QJsonValue &value : outputs)
    {
        if (!value.isObject())
            continue;

        const QJsonObject output = value.toObject();
        const QString path = firstRegistryString(output, {
            QStringLiteral("path"),
            QStringLiteral("preview_path"),
            QStringLiteral("output_path"),
        });
        if (!path.isEmpty())
            return path;
    }

    return QString();
}

QString registryMetadataPathFromRecord(const QJsonObject &record)
{
    const QString direct = firstRegistryString(record, {
        QStringLiteral("primary_metadata_path"),
        QStringLiteral("metadata_path"),
        QStringLiteral("metadata_output"),
    });
    if (!direct.isEmpty())
        return direct;

    const QJsonObject primary = firstRegistryObject(record, {
        QStringLiteral("primary_output"),
        QStringLiteral("primary"),
    });

    const QString primaryMetadata = firstRegistryString(primary, {
        QStringLiteral("metadata_path"),
        QStringLiteral("primary_metadata_path"),
        QStringLiteral("metadata_output"),
    });
    if (!primaryMetadata.isEmpty())
        return primaryMetadata;

    const QJsonArray outputs = firstRegistryArray(record, {
        QStringLiteral("outputs"),
        QStringLiteral("ui_outputs"),
    });

    for (const QJsonValue &value : outputs)
    {
        if (!value.isObject())
            continue;

        const QJsonObject output = value.toObject();
        const QString metadata = firstRegistryString(output, {
            QStringLiteral("metadata_path"),
            QStringLiteral("primary_metadata_path"),
            QStringLiteral("metadata_output"),
        });
        if (!metadata.isEmpty())
            return metadata;
    }

    const QString outputPath = registryOutputPathFromRecord(record);
    return outputPath.isEmpty() ? QString() : QStringLiteral("%1.spellvision.json").arg(outputPath);
}

QString compactPromptPreview(const QString &prompt)
{
    const QString compact = prompt.simplified();
    if (compact.size() <= 260)
        return compact;
    return compact.left(257) + QStringLiteral("...");
}

'''

if "ltxRegistryHistoryPath()" not in cpp:
    namespace_match = re.search(r"namespace\s*\{", cpp)
    if not namespace_match:
        raise SystemExit("Could not find anonymous namespace in T2VHistoryPage.cpp.")
    insert_at = namespace_match.end()
    cpp = cpp[:insert_at] + "\n" + helpers + cpp[insert_at:]

adapter_impl = r'''
QList<T2VHistoryPage::VideoHistoryItem> T2VHistoryPage::loadLtxRegistryHistoryItems() const
{
    QList<VideoHistoryItem> loaded;

    const QString path = ltxRegistryHistoryPath();
    if (path.trimmed().isEmpty())
        return loaded;

    QFile file(path);
    if (!file.exists() || !file.open(QIODevice::ReadOnly | QIODevice::Text))
        return loaded;

    while (!file.atEnd())
    {
        const QByteArray line = file.readLine().trimmed();
        if (line.isEmpty())
            continue;

        QJsonParseError parseError;
        const QJsonDocument document = QJsonDocument::fromJson(line, &parseError);
        if (parseError.error != QJsonParseError::NoError || !document.isObject())
            continue;

        const QJsonObject record = document.object();
        const QString family = record.value(QStringLiteral("family")).toString().trimmed().toLower();
        const QString taskType = record.value(QStringLiteral("task_type")).toString().trimmed().toLower();

        if (!family.isEmpty() && family != QStringLiteral("ltx"))
            continue;
        if (!taskType.isEmpty() && taskType != QStringLiteral("t2v"))
            continue;

        const QString outputPath = QDir::fromNativeSeparators(registryOutputPathFromRecord(record));
        if (outputPath.isEmpty())
            continue;

        const QString metadataPath = QDir::fromNativeSeparators(registryMetadataPathFromRecord(record));
        const QFileInfo outputInfo(outputPath);
        const QFileInfo metadataInfo(metadataPath);

        VideoHistoryItem item;
        item.promptPreview = compactPromptPreview(firstRegistryString(record, {
            QStringLiteral("prompt"),
            QStringLiteral("summary"),
            QStringLiteral("title"),
        }));
        item.lowModelName = firstRegistryString(record, {
            QStringLiteral("model"),
            QStringLiteral("video_primary_model_name"),
        });
        item.highModelName = QStringLiteral("LTX Prompt API");
        item.stackSummary = item.lowModelName.isEmpty()
                                ? QStringLiteral("LTX Prompt API")
                                : QStringLiteral("LTX • %1").arg(item.lowModelName);
        item.outputPath = outputPath;
        item.metadataPath = metadataPath;
        item.durationLabel = QStringLiteral("LTX");
        item.runtimeSummary = QStringLiteral("LTX registry • comfy_prompt_api");
        item.outputExists = outputInfo.exists() && outputInfo.isFile();
        item.metadataExists = metadataInfo.exists() && metadataInfo.isFile();
        item.outputFileSizeBytes = item.outputExists ? outputInfo.size() : 0;
        item.metadataStatus = item.metadataExists ? QStringLiteral("Metadata written") : QStringLiteral("Metadata missing");
        item.outputContractOk = item.outputExists && item.metadataExists;
        item.outputContractStatus = item.outputContractOk ? QStringLiteral("OK") : QStringLiteral("Needs review");

        QStringList warnings;
        if (!item.outputExists)
            warnings << QStringLiteral("Output missing");
        if (!item.metadataExists)
            warnings << QStringLiteral("Metadata missing");
        item.outputContractWarnings = warnings.join(QStringLiteral("; "));

        loaded.prepend(item);
    }

    return loaded;
}

void T2VHistoryPage::mergeLtxRegistryHistoryItems(QList<VideoHistoryItem> &items) const
{
    const QList<VideoHistoryItem> ltxItems = loadLtxRegistryHistoryItems();
    if (ltxItems.isEmpty())
        return;

    QSet<QString> knownOutputPaths;
    for (const VideoHistoryItem &item : items)
    {
        const QString path = QDir::fromNativeSeparators(item.outputPath).trimmed().toLower();
        if (!path.isEmpty())
            knownOutputPaths.insert(path);
    }

    QList<VideoHistoryItem> merged;
    for (const VideoHistoryItem &item : ltxItems)
    {
        const QString path = QDir::fromNativeSeparators(item.outputPath).trimmed().toLower();
        if (path.isEmpty() || knownOutputPaths.contains(path))
            continue;

        knownOutputPaths.insert(path);
        merged.append(item);
    }

    if (merged.isEmpty())
        return;

    for (int i = merged.size() - 1; i >= 0; --i)
        items.prepend(merged.at(i));
}

'''

if "T2VHistoryPage::loadLtxRegistryHistoryItems()" not in cpp:
    load_match = re.search(
        r"QList\s*<\s*T2VHistoryPage::VideoHistoryItem\s*>\s*T2VHistoryPage::loadHistoryItems\s*\(",
        cpp,
    )
    if not load_match:
        raise SystemExit("Could not find loadHistoryItems() function in T2VHistoryPage.cpp.")
    cpp = cpp[:load_match.start()] + adapter_impl + "\n" + cpp[load_match.start():]

if "mergeLtxRegistryHistoryItems(items_);" not in cpp:
    cpp = cpp.replace(
        "    items_ = loadHistoryItems();\n    applyFilters();",
        "    items_ = loadHistoryItems();\n    mergeLtxRegistryHistoryItems(items_);\n    applyFilters();",
        1,
    )

cpp = cpp.replace("Generate a Wan T2V job", "Generate a Wan or LTX T2V job")
cpp = cpp.replace(
    "Generate a Wan T2V job to populate runtime/history/video_history_index.json.",
    "Generate a Wan or LTX T2V job to populate History.",
)
cpp = cpp.replace(
    "loaded from runtime/history/video_history_index.json.",
    "loaded from runtime/history/video_history_index.json and the LTX registry.",
)
cpp = cpp.replace(
    "shown after filters from runtime/history/video_history_index.json.",
    "shown after filters from runtime/history/video_history_index.json and the LTX registry.",
)

history_cpp.write_text(cpp, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
'''# Sprint 15C Pass 15 — T2V History Page LTX Registry Adapter

## Goal

Make the T2V History page consume completed LTX registry results.

## What changed

- `T2VHistoryPage` still reads the existing Wan/native index:
  - `runtime/history/video_history_index.json`
- It now also reads the Pass 12 LTX registry:
  - `D:\\AI_ASSETS\\comfy_runtime\\spellvision_registry\\history\\records.jsonl`
- LTX records are mapped into the existing `VideoHistoryItem` structure.
- Duplicate output paths are ignored.
- History details now show LTX output path, metadata path, model summary, and contract status through the existing details panel.

## Environment overrides

The registry path can be controlled with:

- `SPELLVISION_LTX_HISTORY_RECORDS_JSONL`
- `SPELLVISION_COMFY_RUNTIME_ROOT`
- `SPELLVISION_ASSET_ROOT`

Fallback path:

`D:\\AI_ASSETS\\comfy_runtime\\spellvision_registry\\history\\records.jsonl`

## Expected UI behavior

The History page should show the same completed LTX video that is already visible in Queue.
''',
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Sprint 15C Pass 15 T2V History LTX registry adapter.")
