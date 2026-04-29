from pathlib import Path
import re
import sys

ROOT = Path.cwd()
path = ROOT / "qt_ui" / "MainWindow.cpp"
if not path.exists():
    print(f"Missing file: {path}", file=sys.stderr)
    sys.exit(1)

text = path.read_text(encoding="utf-8")

patterns = [
    (
        re.compile(r"for\s*\(\s*const\s+(?:spellvision::shell::)?(?:ShellNavigationController::)?RailButtonSpec\s*&\s*spec\s*:\s*(spellvision::shell::ShellNavigationController::railButtonSpecs\(\))\s*\)"),
        r"for (const auto &spec : \1)",
    ),
    (
        re.compile(r"for\s*\(\s*const\s+(?:spellvision::shell::)?(?:ShellNavigationController::)?RailButtonSpec\s*&\s*spec\s*:\s*(ShellNavigationController::railButtonSpecs\(\))\s*\)"),
        r"for (const auto &spec : \1)",
    ),
]

updated = text
for pattern, replacement in patterns:
    updated = pattern.sub(replacement, updated)

if updated == text:
    print("No RailButtonSpec typed loop was found. Nothing changed.")
    sys.exit(0)

path.write_text(updated, encoding="utf-8", newline="")
print("Fixed MainWindow.cpp side-rail loop to use const auto &spec.")
