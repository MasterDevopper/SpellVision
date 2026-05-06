from pathlib import Path

path = Path("qt_ui/MainWindow.cpp")
text = path.read_text(encoding="utf-8")

if "#include <limits>" not in text:
    text = text.replace("#include <algorithm>", "#include <algorithm>\n#include <limits>", 1)

text = text.replace(
    "std::numeric_limits<qint64>::min()",
    "(std::numeric_limits<qint64>::min)()"
)

path.write_text(text, encoding="utf-8")

print("Repaired Pass 28C Windows min macro collision.")
