from __future__ import annotations

from pathlib import Path
import re
import sys


DECL_BLOCK = """
    QString managerStatusDisplaySource(const QString &applySource = QString());
    QString managerStatusLastCheckedText();

"""

DEF_BLOCK = """
    QString managerStatusDisplaySource(const QString &applySource)
    {
        if (!applySource.trimmed().isEmpty())
            return applySource.trimmed();

        if (!hasManagerStatusCache())
            return QStringLiteral("none");

        if (g_managerStatusCacheOrigin == QStringLiteral("disk"))
            return QStringLiteral("disk");

        if (g_managerStatusCacheOrigin == QStringLiteral("live"))
            return QStringLiteral("memory");

        return QStringLiteral("memory");
    }

    QString managerStatusLastCheckedText()
    {
        if (g_managerStatusCacheAtMs <= 0)
            return QStringLiteral("never");

        return QDateTime::fromMSecsSinceEpoch(g_managerStatusCacheAtMs)
            .toLocalTime()
            .toString(QStringLiteral("yyyy-MM-dd hh:mm:ss AP"));
    }

"""


def backup_once(path: Path, suffix: str, original: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
        print(f"Backup written: {backup}")


def find_anonymous_namespace(text: str) -> tuple[int, int] | tuple[None, None]:
    patterns = [r'namespace\s*\{', r'namespace\s*\r?\n\s*\{']
    match = None
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            break
    if not match:
        return None, None

    open_brace = text.find("{", match.start())
    if open_brace < 0:
        return None, None

    depth = 0
    for index in range(open_brace, len(text)):
        ch = text[index]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return open_brace, index
    return None, None


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_manager_cache_helper_forward_decl_fix.py <SpellVision project root>")
        return 2

    root = Path(sys.argv[1]).resolve()
    target = root / "qt_ui" / "ManagerPage.cpp"
    if not target.exists():
        print(f"Missing file: {target}")
        return 1

    text = target.read_text(encoding="utf-8")
    original = text

    ns_open, ns_close = find_anonymous_namespace(text)
    if ns_open is None or ns_close is None:
        print("Could not locate the anonymous namespace block in ManagerPage.cpp")
        return 1

    changed = False

    if "QString managerStatusDisplaySource(const QString &applySource = QString());" not in text:
        insert_at = ns_open + 1
        text = text[:insert_at] + "\n" + DECL_BLOCK + text[insert_at:]
        ns_close += len("\n" + DECL_BLOCK)
        changed = True
        print("Inserted forward declarations.")

    if "QString managerStatusDisplaySource(const QString &applySource)" not in text:
        text = text[:ns_close] + "\n" + DEF_BLOCK + text[ns_close:]
        changed = True
        print("Inserted helper definitions.")

    if not changed:
        print("No changes made. Helper declarations/definitions already exist.")
        return 0

    backup_once(target, ".pre_manager_cache_helper_fix.bak", original)
    target.write_text(text, encoding="utf-8")
    print(f"Patched: {target}")
    print("Rebuild with: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
