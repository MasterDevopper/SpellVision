from __future__ import annotations

from pathlib import Path
import sys


HELPER_BLOCK = """
    QString managerStatusDisplaySource(const QString &applySource = QString())
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


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_sprint13_pass7_compile_fix.py <SpellVision project root>")
        return 2

    root = Path(sys.argv[1]).resolve()
    target = root / "qt_ui" / "ManagerPage.cpp"
    if not target.exists():
        print(f"Missing file: {target}")
        return 1

    text = target.read_text(encoding="utf-8")
    original = text

    if "managerStatusDisplaySource(" in text and "managerStatusLastCheckedText(" in text:
        print("Helper functions already exist. No changes made.")
        return 0

    anchor = '        return hasManagerStatusCache() &&\n               g_managerStatusCacheAtMs > 0 &&\n               (QDateTime::currentMSecsSinceEpoch() - g_managerStatusCacheAtMs) < kManagerStatusCacheFreshMs;\n    }\n'
    if anchor not in text:
        print("Could not find managerStatusCacheFresh() anchor. No changes made.")
        return 1

    text = text.replace(anchor, anchor + "\n" + HELPER_BLOCK, 1)

    backup_once(target, ".pre_sprint13_pass7_compile_fix.bak", original)
    target.write_text(text, encoding="utf-8")
    print(f"Patched: {target}")
    print("Rebuild with: .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
