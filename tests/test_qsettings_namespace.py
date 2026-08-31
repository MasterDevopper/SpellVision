"""QSettings default and explicit call sites must use one canonical namespace."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = (ROOT / "qt_ui" / "main.cpp").read_text(encoding="utf-8")


def test_canonical_identity_is_set_before_qapplication() -> None:
    identity = 'QCoreApplication::setOrganizationName(QStringLiteral("DarkDuck"))'
    assert identity in MAIN
    assert MAIN.index(identity) < MAIN.index("QApplication app(argc, argv)")
    assert 'QApplication::setOrganizationName("Dark Duck Studio")' not in MAIN


def test_legacy_namespace_migrates_missing_keys_only() -> None:
    assert 'QSettings legacy(QStringLiteral("Dark Duck Studio"), QStringLiteral("SpellVision"))' in MAIN
    assert 'QSettings canonical(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"))' in MAIN
    assert "if (!canonical.contains(key))" in MAIN
    assert 'settings/canonicalNamespaceMigration_v1' in MAIN
