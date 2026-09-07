// One style draws every control. Before this, the primary button was defined seven times at two
// radii and three weights, and switching the Surface Style setting changed nothing on the cockpit.
// These assertions read pixels back from real widgets, because "the token is set" is not "the
// control is drawn".
#include <QtTest>
#include <QApplication>
#include <QImage>
#include <QPushButton>
#include <QToolButton>
#include <QFrame>

#include "ThemeManager.h"
#include "style/SvStyle.h"

using spellvision::style::Role;
using spellvision::style::Surface;
using spellvision::style::SvStyle;

namespace
{
QImage grab(QWidget &w, int width = 120, int height = 34)
{
    w.resize(width, height);
    w.setAttribute(Qt::WA_DontShowOnScreen);
    w.show();
    return w.grab().toImage().convertToFormat(QImage::Format_ARGB32);
}

bool near(const QColor &a, const QColor &b, int tolerance)
{
    return qAbs(a.red() - b.red()) <= tolerance && qAbs(a.green() - b.green()) <= tolerance
        && qAbs(a.blue() - b.blue()) <= tolerance;
}

QColor mix(const QColor &a, const QColor &b, qreal t)
{
    return QColor::fromRgbF(a.redF() + (b.redF() - a.redF()) * t,
                            a.greenF() + (b.greenF() - a.greenF()) * t,
                            a.blueF() + (b.blueF() - a.blueF()) * t);
}
} // namespace

class SvStyleTest : public QObject
{
    Q_OBJECT
private slots:
    void initTestCase()
    {
        QApplication::setStyle(new SvStyle);
        ThemeManager::instance().setPreset(ThemeManager::Preset::ArcaneGlass);
        ThemeManager::instance().setStyle(ThemeManager::Style::RefinedGlass);
    }

    void the_installed_style_is_ours()
    {
        QStyle *s = QApplication::style();
        QVERIFY(qobject_cast<SvStyle *>(s) != nullptr || s->inherits("QStyleSheetStyle"));
    }

    void role_reads_the_property_first_then_the_object_name()
    {
        QPushButton a;
        a.setProperty("svRole", QStringLiteral("danger"));
        a.setObjectName(QStringLiteral("PrimaryActionButton"));
        QCOMPARE(SvStyle::roleOf(&a), Role::Danger);
        QPushButton b;
        b.setObjectName(QStringLiteral("PrimaryActionButton"));
        QCOMPARE(SvStyle::roleOf(&b), Role::Primary);
        QPushButton c;
        c.setObjectName(QStringLiteral("SecondaryActionButton"));
        QCOMPARE(SvStyle::roleOf(&c), Role::Secondary);
        QFrame f;
        f.setObjectName(QStringLiteral("PromptCard"));
        QCOMPARE(SvStyle::surfaceOf(&f), Surface::Panel);
    }

    void primary_is_painted_from_the_accent()
    {
        const auto &tm = ThemeManager::instance();
        QPushButton b; // no text: the centre column is fill, not glyph
        b.setProperty("svRole", QStringLiteral("primary"));
        const QImage img = grab(b);
        const QColor at80 = img.pixelColor(img.width() / 2, int(img.height() * 0.8));
        const QColor expected = mix(tm.color(ThemeManager::Color::AccentHover),
                                    tm.color(ThemeManager::Color::Accent), 0.8);
        QVERIFY2(near(at80, expected, 14),
                 qPrintable(at80.name() + QStringLiteral(" vs ") + expected.name()));
    }

    void secondary_is_the_raised_surface()
    {
        const auto &tm = ThemeManager::instance();
        QPushButton b;
        b.setProperty("svRole", QStringLiteral("secondary"));
        const QImage img = grab(b);
        const QColor centre = img.pixelColor(img.width() / 2, img.height() / 2);
        QVERIFY2(near(centre, tm.color(ThemeManager::Color::Surface2), 3),
                 qPrintable(centre.name()));
    }

    void the_material_reaches_the_control()
    {
        auto &tm = ThemeManager::instance();
        QPushButton b;
        b.setProperty("svRole", QStringLiteral("secondary"));
        tm.setStyle(ThemeManager::Style::RefinedGlass);
        SvStyle::refreshAll();
        const QImage refined = grab(b);
        tm.setStyle(ThemeManager::Style::MatteInstrument);
        SvStyle::refreshAll();
        const QImage matte = grab(b);
        QVERIFY(refined != matte);
        QVERIFY(tm.radiusControl() == 4);
        tm.setStyle(ThemeManager::Style::RefinedGlass);
    }

    void numeric_font_has_tabular_figures()
    {
        const QFont f = ThemeManager::instance().numericFont();
        QVERIFY(f.featureTags().contains(QFont::Tag("tnum")));
    }
};

QTEST_MAIN(SvStyleTest)
#include "test_sv_style.moc"
