from pathlib import Path

path = Path("qt_ui/workers/WorkerQueueController.cpp")
text = path.read_text(encoding="utf-8")

old = '''    item.insert(QStringLiteral("created_at"), contract.value(QStringLiteral("created_at")).toString(QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs)));
    item.insert(QStringLiteral("updated_at"), QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs));
'''

new = '''    const QString contractCreatedAt = contract.value(QStringLiteral("created_at")).toString();
    const QString stableTimestamp = contractCreatedAt.isEmpty()
        ? QStringLiteral("1970-01-01T00:00:00.000Z")
        : contractCreatedAt;

    item.insert(QStringLiteral("created_at"), stableTimestamp);
    item.insert(QStringLiteral("updated_at"), stableTimestamp);
'''

if old not in text:
    raise SystemExit("Could not find unstable Pass 24 timestamp block.")

text = text.replace(old, new, 1)

# Keep the display string ASCII-stable too; PowerShell paste may have stripped the bullet already.
text = text.replace(
    'QStringLiteral("LTX requeue • ready")',
    'QStringLiteral("LTX requeue ready")',
)

path.write_text(text, encoding="utf-8")

print("Stabilized Pass 24 synthetic LTX queue item timestamps to prevent preview reload flicker.")
