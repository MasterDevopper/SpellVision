from pathlib import Path

path = Path("qt_ui/T2VHistoryPage.h")
text = path.read_text(encoding="utf-8")

if "#include <QJsonObject>" not in text:
    if "#include <QWidget>" in text:
        text = text.replace("#include <QWidget>", "#include <QWidget>\n#include <QJsonObject>", 1)
    else:
        text = "#include <QJsonObject>\n" + text

path.write_text(text, encoding="utf-8")

print("Added QJsonObject include for Pass 23 header member.")
