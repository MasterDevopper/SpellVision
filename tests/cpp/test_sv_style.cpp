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
#include <QPainter>
#include <QSettings>
#include <QStyleOptionButton>
#include <QTextEdit>

#include <utility>

#include "ThemeManager.h"
#include "style/SvKit.h"
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

// ThemeManager::save()/load() always construct QSettings(QStringLiteral("DarkDuck"),
// QStringLiteral("SpellVision")) -- the two-argument (organization, application) constructor.
// Confirmed empirically (a probe QSettings built the same way, right after calling
// QSettings::setDefaultFormat(IniFormat) + QSettings::setPath(IniFormat, UserScope, tempDir) +
// QCoreApplication::setOrganizationName/setApplicationName) that this constructor resolves to
// QSettings::NativeFormat and the real "HKEY_CURRENT_USER\Software\DarkDuck\SpellVision" registry
// key REGARDLESS of all four of those calls -- none of the usual QSettings redirection hooks catch
// it on Windows. So this binary cannot avoid writing the real store the moment a test calls
// ThemeManager::setPreset()/setStyle() (both call save()); the only thing a test can do is back up
// the owner's real values before the first such call and put them back afterward, using the same
// explicit-format constructor so the restore targets the real store regardless of anything else.
QSettings openRealThemeSettings()
{
    return QSettings(QSettings::NativeFormat, QSettings::UserScope, QStringLiteral("DarkDuck"),
                      QStringLiteral("SpellVision"));
}
} // namespace

class SvStyleTest : public QObject
{
    Q_OBJECT
private slots:
    void initTestCase()
    {
        // Back up the owner's real settings before the first ThemeManager setter call anywhere in
        // this binary (setPreset()/setStyle() below are it).
        {
            QSettings real = openRealThemeSettings();
            realThemePresetBefore_ = real.value(QStringLiteral("appearance/themePreset")).toInt();
            realSurfaceStyleBefore_ = real.value(QStringLiteral("appearance/surfaceStyle")).toInt();
        }

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
        QCOMPARE(SvStyle::surfaceOf(&f), Surface::Plate);
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

    void field_panel_only_for_text_edits_and_item_views()
    {
        const auto &tm = ThemeManager::instance();

        // The app-wide stylesheet applyApplicationChrome() sets (for the escaping popups) makes Qt
        // wrap the installed style in QStyleSheetStyle, which paints any widget's ambient/unstyled
        // background straight from QApplication::palette() -- bypassing a manually-set LOCAL widget
        // palette override entirely, before the widget's own paintEvent (and so PE_Frame) ever
        // runs. Clear it for the span of this comparison so the pixels sampled reflect only
        // SvStyle's own PE_Frame decision, not that unrelated ambient repaint; restored below
        // before either QVERIFY2 (which returns early on failure).
        const QString appStyleSheet = qApp->styleSheet();
        qApp->setStyleSheet(QString());

        // A bare QFrame -- the same PE_Frame branch a plain QScrollArea page wrapper takes (every
        // Role check false) -- must NOT get the field-panel fill. Parent it to a widget whose
        // Window colour is a sentinel far from Surface0, so "no fill painted, the inherited
        // background shows through" is distinguishable from "the field fill happens to look dark
        // too".
        QWidget host;
        QPalette sentinel = host.palette();
        sentinel.setColor(QPalette::Window, QColor(QStringLiteral("#ff00ff")));
        host.setPalette(sentinel);
        auto *frame = new QFrame(&host);
        frame->setFrameShape(QFrame::StyledPanel);
        const QImage frameImg = grab(*frame, 120, 60);
        const QColor frameAt = frameImg.pixelColor(60, 30);

        // A QTextEdit IS a text field: it must get the dark Surface0 fill from paintFieldPanel.
        // Hide its internal viewport child first -- QAbstractScrollArea auto-fills the viewport
        // from its own (unrelated) resolved background, which paints over the field-panel fill for
        // nearly the whole interior and would otherwise mask what this asserts.
        QTextEdit edit;
        edit.viewport()->setVisible(false);
        const QImage editImg = grab(edit, 120, 60);
        const QColor editAt = editImg.pixelColor(60, 30);

        qApp->setStyleSheet(appStyleSheet);

        QVERIFY2(!near(frameAt, tm.color(ThemeManager::Color::Surface0), 3),
                 qPrintable(frameAt.name()));
        QVERIFY2(near(editAt, tm.color(ThemeManager::Color::Surface0), 3),
                 qPrintable(editAt.name()));
    }

    void numeric_font_has_tabular_figures()
    {
        const QFont f = ThemeManager::instance().numericFont();
        QVERIFY(f.featureTags().contains(QFont::Tag("tnum")));
    }

    // Task 4 moved the button label's weight out of the shell sheet, where one generic
    // `QPushButton { font-weight: 600 }` gave every button in the app the hero weight, and into
    // the style, which sets 600 for the primary role and 500 for the rest. Measured as glyph
    // COVERAGE on a transparent surface -- alpha, not colour -- so the role's text colour cannot
    // decide the outcome, and drawn through an own SvStyle instance so the qApp overlay sheet's
    // QStyleSheetStyle wrapper is not in the path.
    void the_primary_label_carries_more_weight_than_the_rest()
    {
        spellvision::style::SvStyle style;
        const auto coverage = [&style](Role role) {
            QPushButton b(QStringLiteral("Generate Preview"));
            b.setProperty("svRole", SvStyle::roleName(role));
            b.resize(220, 34);
            QStyleOptionButton opt;
            opt.initFrom(&b);
            opt.rect = QRect(0, 0, 220, 34);
            opt.text = b.text();
            opt.state |= QStyle::State_Enabled;
            QImage img(220, 34, QImage::Format_ARGB32_Premultiplied);
            img.fill(Qt::transparent);
            QPainter painter(&img);
            style.drawControl(QStyle::CE_PushButtonLabel, &opt, &painter, &b);
            const bool fontRestored = painter.font() == b.font();
            painter.end();
            int inked = 0;
            for (int y = 0; y < img.height(); ++y)
                for (int x = 0; x < img.width(); ++x)
                    if (qAlpha(img.pixel(x, y)) > 0)
                        ++inked;
            return std::pair<int, bool>(inked, fontRestored);
        };
        const auto primary = coverage(Role::Primary);
        const auto secondary = coverage(Role::Secondary);
        QVERIFY2(primary.first > 0 && secondary.first > 0, "the label drew nothing");
        QVERIFY2(primary.first > secondary.first,
                 qPrintable(QStringLiteral("primary ink %1 is not heavier than secondary %2")
                                .arg(primary.first)
                                .arg(secondary.first)));
        // The weight is set on the painter, so it has to be put back or the next thing drawn with
        // that painter inherits it.
        QVERIFY2(primary.second && secondary.second, "drawControl left its font on the painter");
    }

    void the_factory_sets_the_role_and_keeps_the_name()
    {
        QPushButton *b = spellvision::kit::button(Role::Primary, QStringLiteral("Generate"),
                                                  QStringLiteral("PrimaryActionButton"));
        QCOMPARE(b->objectName(), QStringLiteral("PrimaryActionButton"));
        QCOMPARE(b->property("svRole").toString(), QStringLiteral("primary"));
        QCOMPARE(SvStyle::roleOf(b), Role::Primary);
        spellvision::kit::setRole(b, Role::Secondary);
        QCOMPARE(SvStyle::roleOf(b), Role::Secondary);
        QFrame *f = spellvision::kit::card(Surface::Glass, QStringLiteral("CanvasCard"));
        QCOMPARE(f->frameShape(), QFrame::StyledPanel);
        QCOMPARE(SvStyle::surfaceOf(f), Surface::Glass);
        delete b;
        delete f;
    }

    // Declared LAST among the real test slots (QtTest runs slots in declaration order): every
    // earlier case that calls a ThemeManager setter has already run and already transiently wrote
    // the real registry-backed store (see openRealThemeSettings() above -- there is no redirecting
    // it). This puts the owner's real values back and proves the put-back landed; cleanupTestCase()
    // repeats the same restore as a guaranteed-to-run backstop in case this slot itself fails
    // before reaching the restore line.
    void the_test_does_not_touch_the_real_settings()
    {
        restoreRealSettings();
        QSettings real = openRealThemeSettings();
        QCOMPARE(real.value(QStringLiteral("appearance/themePreset")).toInt(),
                 realThemePresetBefore_);
        QCOMPARE(real.value(QStringLiteral("appearance/surfaceStyle")).toInt(),
                 realSurfaceStyleBefore_);
    }

    void cleanupTestCase()
    {
        restoreRealSettings();
    }

private:
    void restoreRealSettings()
    {
        if (realThemePresetBefore_ < 0)
            return; // initTestCase never captured a baseline (e.g. it failed before doing so)
        QSettings real = openRealThemeSettings();
        real.setValue(QStringLiteral("appearance/themePreset"), realThemePresetBefore_);
        real.setValue(QStringLiteral("appearance/surfaceStyle"), realSurfaceStyleBefore_);
        real.sync();
    }

    int realThemePresetBefore_ = -1;
    int realSurfaceStyleBefore_ = -1;
};

QTEST_MAIN(SvStyleTest)
#include "test_sv_style.moc"
