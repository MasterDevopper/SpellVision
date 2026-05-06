from pathlib import Path

path = Path("qt_ui/MainWindow.h")
text = path.read_text(encoding="utf-8")

if "void applyQueuePresentationForCurrentMode();" not in text:
    marker = "    void updateDockChrome();"
    if marker not in text:
        raise SystemExit("Could not find updateDockChrome declaration marker.")
    text = text.replace(marker, marker + "\n    void applyQueuePresentationForCurrentMode();", 1)

path.write_text(text, encoding="utf-8")
print("Declared applyQueuePresentationForCurrentMode in MainWindow.h.")
