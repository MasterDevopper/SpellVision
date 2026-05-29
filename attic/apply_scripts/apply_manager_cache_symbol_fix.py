from __future__ import annotations

from pathlib import Path
import re
import sys


VAR_BLOCK = '    QString g_managerStatusCacheOrigin = QStringLiteral("none");\n'

DECL_BLOCK = """    QString managerStatusDisplaySource(const QString &applySource = QString());
    QString managerStatusLastCheckedText();

"""

DEF_BLOCK = """    QString managerStatusDisplaySource(const QString &applySource)
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
    match = re.search(r'namespace\s*\{', text)
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


def insert_after_once(text: str, anchor: str, insertion: str, label: str) -> tuple[str, bool]:
    if insertion.strip() in text:
        return text, False
    if anchor not in text:
        print(f"[skip] anchor not found for {label}")
        return text, False
    return text.replace(anchor, anchor + insertion, 1), True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_manager_cache_symbol_fix.py <SpellVision project root>")
        return 2

    root = Path(sys.argv[1]).resolve()
    target = root / "qt_ui" / "ManagerPage.cpp"
    if not target.exists():
        print(f"Missing file: {target}")
        return 1

    text = target.read_text(encoding="utf-8")
    original = text
    changed = False

    if 'QString g_managerStatusCacheOrigin = QStringLiteral("none");' not in text:
        anchor_options = [
            '    qint64 g_managerStatusCacheAtMs = 0;\n',
            '    qint64 g_managerStatusCacheAtMs = 0;\r\n',
        ]
        did_var = False
        for anchor in anchor_options:
            text, did_var = insert_after_once(text, anchor, VAR_BLOCK, "cache origin variable")
            if did_var:
                changed = True
                print("Inserted g_managerStatusCacheOrigin.")
                break
        if not did_var:
            print("[skip] could not place g_managerStatusCacheOrigin next to cache globals")

    ns_open, ns_close = find_anonymous_namespace(text)
    if ns_open is None or ns_close is None:
        print("Could not locate anonymous namespace in ManagerPage.cpp")
        return 1

    if "QString managerStatusDisplaySource(const QString &applySource = QString());" not in text:
        insert_at = ns_open + 1
        text = text[:insert_at] + "\n" + DECL_BLOCK + text[insert_at:]
        ns_close += len("\n" + DECL_BLOCK)
        changed = True
        print("Inserted helper forward declarations.")

    if "QString managerStatusDisplaySource(const QString &applySource)" not in text:
        text = text[:ns_close] + "\n" + DEF_BLOCK + text[ns_close:]
        changed = True
        print("Inserted helper definitions.")

    if not changed:
        print("No changes made. Symbols already appear to exist.")
        return 0

    backup_once(target, ".pre_manager_cache_symbol_fix.bak", original)
    target.write_text(text, encoding="utf-8")
    print(f"Patched: {target}")
    print("Rebuild with: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
