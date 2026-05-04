from pathlib import Path

path = Path("qt_ui/workers/WorkerQueueController.cpp")
text = path.read_text(encoding="utf-8")

old = '''QJsonObject appendLatestLtxRequeuePreviewContractItem(QJsonObject snapshot)
{
    QJsonArray items = snapshot.value(QStringLiteral("items")).toArray();
    const QJsonObject contract = loadLatestLtxRequeueQueuePreviewContract();
'''

new = '''QJsonObject appendLatestLtxRequeuePreviewContractItem(QJsonObject snapshot)
{
    // Pass 24 safety gate:
    // Do not inject preview-backed synthetic queue rows during normal queue polling.
    // Queue polling runs globally, including while Home is visible. Injecting a media-backed
    // completed row on every snapshot can cause preview consumers to rebind the same MP4
    // repeatedly, which shows up as FFmpeg probe spam and visible flicker.
    //
    // Later, the Queue/Preview panel should request this explicitly when it is visible.
    bool envParsed = false;
    const int enabled = qEnvironmentVariableIntValue("SPELLVISION_ENABLE_LTX_QUEUE_CONTRACT_PREVIEW", &envParsed);
    if (!envParsed || enabled != 1)
        return snapshot;

    QJsonArray items = snapshot.value(QStringLiteral("items")).toArray();
    const QJsonObject contract = loadLatestLtxRequeueQueuePreviewContract();
'''

if old not in text:
    raise SystemExit("Could not find appendLatestLtxRequeuePreviewContractItem opening block.")

text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")

print("Disabled global Pass 24 LTX queue contract injection by default.")
