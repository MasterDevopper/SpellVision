from pathlib import Path

path = Path("qt_ui/QueueManager.cpp")
text = path.read_text(encoding="utf-8")

old = '''        if (item.state.trimmed().compare(QStringLiteral("completed"), Qt::CaseInsensitive) == 0)
'''

new = '''        if (obj.value(QStringLiteral("state")).toString().trimmed().compare(QStringLiteral("completed"), Qt::CaseInsensitive) == 0)
'''

if old not in text:
    print("Repair not needed: invalid item.state.trimmed() check was not found.")
else:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Repaired Sprint 15C Pass 29Q v2 compile issue.")
