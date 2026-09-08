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
#include <QProgressBar>
#include <QPalette>
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

    void role_reads_the_property_only()
    {
        QPushButton a;
        a.setProperty("svRole", QStringLiteral("danger"));
        a.setObjectName(QStringLiteral("PrimaryActionButton"));
        QCOMPARE(SvStyle::roleOf(&a), Role::Danger);
        QPushButton b;
        b.setObjectName(QStringLiteral("PrimaryActionButton"));
        QCOMPARE(SvStyle::roleOf(&b), Role::None);
        QFrame f;
        f.setObjectName(QStringLiteral("PromptCard"));
        QCOMPARE(SvStyle::surfaceOf(&f), Surface::None);
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

    // The name claims a Surface Style change reaches a CONTROL, not just a panel. What this used to
    // assert was `QVERIFY(refined != matte)` on a Secondary button -- and between those two
    // materials the only things that move for that role are radiusControl (6 -> 4) and Border's
    // alpha (x1.0 -> x1.45). Surface2, the fill this role reads, does not move at all. So a single
    // antialiased corner pixel could carry the inequality: the same defect
    // every_material_reaches_a_panel was rewritten to avoid, in the test right next to it.
    //
    // Measured as a FRACTION of moved pixels now, and split in two, because the honest statement is
    // narrower than the name suggests: the material reaches this control through its corners and
    // its hairline, and its interior is material-invariant BY DESIGN. Asserting both halves is what
    // stops an edge pixel standing in for a fill that never changes.
    void the_material_reaches_the_control()
    {
        auto &tm = ThemeManager::instance();
        const auto secondaryUnder = [](ThemeManager::Style style) {
            ThemeManager::instance().setStyle(style);
            SvStyle::refreshAll();
            QPushButton b; // no text: a glyph would move with nothing but the font
            b.setProperty("svRole", QStringLiteral("secondary"));
            return grab(b);
        };
        // Pixels differing by more than 8 in any channel, over a chosen sub-rect.
        const auto movedIn = [](const QImage &a, const QImage &b, const QRect &area) {
            int n = 0;
            for (int y = area.top(); y <= area.bottom(); ++y)
                for (int x = area.left(); x <= area.right(); ++x)
                {
                    const QColor p = a.pixelColor(x, y);
                    const QColor q = b.pixelColor(x, y);
                    if (qAbs(p.red() - q.red()) > 8 || qAbs(p.green() - q.green()) > 8
                        || qAbs(p.blue() - q.blue()) > 8)
                        ++n;
                }
            return double(n) / double(area.width() * area.height());
        };
        const QImage refined = secondaryUnder(ThemeManager::Style::RefinedGlass);
        const QImage matte = secondaryUnder(ThemeManager::Style::MatteInstrument);
        const QRect whole(0, 0, refined.width(), refined.height());
        const QRect interior = whole.adjusted(6, 6, -6, -6); // clear of the corner arcs and hairline
        const double wholePair = movedIn(refined, matte, whole);
        const double interiorPair = movedIn(refined, matte, interior);
        const int matteRadius = tm.radiusControl();
        tm.setStyle(ThemeManager::Style::RefinedGlass);
        SvStyle::refreshAll();
        qInfo("material on a secondary button: whole %.4f, interior %.4f, matte radiusControl %d",
              wholePair, interiorPair, matteRadius);
        QVERIFY2(wholePair >= 0.02,
                 qPrintable(QStringLiteral("Refined and Matte paint a control the same: %1")
                                .arg(wholePair, 0, 'f', 4)));
        QVERIFY2(interiorPair <= 0.001,
                 qPrintable(QStringLiteral("the interior moved (%1) -- this role's fill is Surface2 "
                                           "under every material, so something else changed")
                                .arg(interiorPair, 0, 'f', 4)));
        QCOMPARE(matteRadius, 4);
        QCOMPARE(tm.radiusControl(), 6);
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

    // A blocked action button is still ENABLED -- applyActionReadinessStyle keeps it clickable so
    // the click can report why -- so :disabled never fires and the only signal is the property.
    // It used to be said by a stylesheet rule that set `border-color` with no border-style: it drew
    // no rim at all, and it could not round a corner, so once the base button rules were deleted a
    // blocked Generate was a square unrimmed slab among rounded controls. Three things have to hold
    // now: it must not look like a ready hero, it must still be rounded, and it must not read as an
    // ordinary secondary button.
    void the_blocked_primary_is_dimmed_but_still_a_rounded_hero()
    {
        const auto &tm = ThemeManager::instance();
        QPushButton ready; // no text: the centre column is fill, not glyph
        ready.setProperty("svRole", QStringLiteral("primary"));
        QPushButton blocked;
        blocked.setProperty("svRole", QStringLiteral("primary"));
        blocked.setProperty("readinessBlocked", true);

        const QImage readyImg = grab(ready);
        const QImage blockedImg = grab(blocked);
        const QColor readyCentre = readyImg.pixelColor(readyImg.width() / 2, readyImg.height() / 2);
        const QColor blockedCentre =
            blockedImg.pixelColor(blockedImg.width() / 2, blockedImg.height() / 2);
        const QColor blockedCorner = blockedImg.pixelColor(1, 1);

        QVERIFY2(!near(blockedCentre, readyCentre, 10),
                 qPrintable(QStringLiteral("blocked %1 is indistinguishable from the ready hero %2")
                                .arg(blockedCentre.name(), readyCentre.name())));
        QVERIFY2(!near(blockedCorner, blockedCentre, 10),
                 qPrintable(QStringLiteral("corner %1 carries the fill %2 -- the blocked hero is square")
                                .arg(blockedCorner.name(), blockedCentre.name())));
        QVERIFY2(!near(blockedCentre, tm.color(ThemeManager::Color::Surface2), 3),
                 qPrintable(QStringLiteral("blocked %1 is just a secondary button")
                                .arg(blockedCentre.name())));

        // Not the hero's state alone. applyActionReadinessStyle sets the property on Queue too, and
        // Queue is Secondary: scoping the branch to Primary left a blocked Queue looking ready.
        QPushButton readySecondary;
        readySecondary.setProperty("svRole", QStringLiteral("secondary"));
        QPushButton blockedSecondary;
        blockedSecondary.setProperty("svRole", QStringLiteral("secondary"));
        blockedSecondary.setProperty("readinessBlocked", true);
        const QColor readySec = grab(readySecondary).pixelColor(60, 17);
        const QColor blockedSec = grab(blockedSecondary).pixelColor(60, 17);
        QVERIFY2(!near(blockedSec, readySec, 10),
                 qPrintable(QStringLiteral("a blocked secondary %1 looks ready %2")
                                .arg(blockedSec.name(), readySec.name())));
    }

    // The label colour has to survive QStyleSheetStyle, which draws a button's label itself instead
    // of routing CE_PushButtonLabel to this style -- measured live, a blocked Generate and a ready
    // one came back the same 233,235,248. polish() writes the role's rest colour into the widget
    // palette, which the wrapper honours when no rule sets `color`.
    void the_role_writes_its_label_colour_into_the_palette()
    {
        const auto &tm = ThemeManager::instance();
        QPushButton b;
        spellvision::kit::setRole(&b, Role::Primary); // repolishes
        QCOMPARE(b.palette().color(QPalette::ButtonText), QColor(Qt::white));
        QCOMPARE(b.palette().color(QPalette::Text), QColor(Qt::white));

        // The DISABLED colour group is the one QCommonStyle::drawItemText reads for a disabled
        // widget, and the two-argument setColor writes all three groups -- so the enabled ink above
        // landed in it and a disabled label came back the live colour. It has to be written
        // explicitly, after. polish() also runs once, at construction, and setEnabled() does not
        // repolish: both states have to be right from that single visit.
        QCOMPARE(b.palette().color(QPalette::Disabled, QPalette::ButtonText),
                 tm.color(ThemeManager::Color::TextDisabled));
        QCOMPARE(b.palette().color(QPalette::Disabled, QPalette::Text),
                 tm.color(ThemeManager::Color::TextDisabled));
        b.setEnabled(false); // no repolish happens here -- that is the point
        QCOMPARE(b.palette().color(QPalette::Disabled, QPalette::ButtonText),
                 tm.color(ThemeManager::Color::TextDisabled));
        QCOMPARE(b.palette().color(QPalette::Active, QPalette::ButtonText), QColor(Qt::white));
        b.setEnabled(true);

        b.setProperty("readinessBlocked", true);
        b.style()->unpolish(&b);
        b.style()->polish(&b);
        QCOMPARE(b.palette().color(QPalette::ButtonText),
                 tm.color(ThemeManager::Color::TextDisabled));
        QCOMPARE(b.palette().color(QPalette::Text), tm.color(ThemeManager::Color::TextDisabled));
    }

    // A checked chip has to say so on a LIGHT ground as well as a dark one. The veil it used to
    // carry was 5 % white, which over Ivory Holograph's near-white Surface1 moved the plate by four
    // levels -- not a signal, and on Comic's panel board that is four plates with one selected and
    // no way to tell which. The fill is the channel that survives the qApp overlay sheet (the label
    // never reaches CE_PushButtonLabel), so it is the channel this measures.
    void the_checked_chip_reads_on_every_preset()
    {
        auto &tm = ThemeManager::instance();
        const auto centreOf = [](bool checked) {
            QPushButton b; // no text: the centre column is fill, not glyph
            b.setProperty("svRole", QStringLiteral("chip"));
            b.setCheckable(true);
            b.setChecked(checked);
            const QImage img = grab(b);
            return img.pixelColor(img.width() / 2, img.height() / 2);
        };
        for (const auto preset : {ThemeManager::Preset::ArcaneGlass,
                                  ThemeManager::Preset::IvoryHolograph})
        {
            tm.setPreset(preset);
            SvStyle::refreshAll();
            const QColor on = centreOf(true);
            const QColor off = centreOf(false);
            const int distance = qAbs(on.red() - off.red()) + qAbs(on.green() - off.green())
                + qAbs(on.blue() - off.blue());
            QVERIFY2(distance >= 24,
                     qPrintable(QStringLiteral("preset %1: %2 vs %3, distance %4")
                                    .arg(int(preset))
                                    .arg(on.name(), off.name())
                                    .arg(distance)));
        }
        tm.setPreset(ThemeManager::Preset::ArcaneGlass);
        SvStyle::refreshAll();
    }

    // Three Surface Style options have to be three surfaces. Task 8's captures had Refined Glass
    // and Hybrid within 0.0006 of each other on T2I -- one of the three settings was invisible on
    // the app's main page, and it is the one the owner runs. paintSurface asked
    // styleUsesGlass(true), the single argument for which Refined and Hybrid agree, so every
    // surface took the flat branch under all three materials and the only thing left between
    // Refined and Hybrid was a 2 px radius.
    //
    // "Different" here is a FRACTION of moved pixels, not operator!=: before the fix Refined and
    // Hybrid already differed on 0.0078 of a panel, because radiusCard is 10 / 8 / 6 -- so an
    // inequality check passed while the defect it was meant to catch was live. The two pairs below
    // are where the design says the difference has to land: Refined glasses an ordinary panel and
    // Hybrid does not, Hybrid glasses a hero plate and Matte does not.
    void every_material_reaches_a_panel()
    {
        auto &tm = ThemeManager::instance();
        const auto surfaceImage = [](ThemeManager::Style style, const QString &surface) {
            ThemeManager::instance().setStyle(style);
            SvStyle::refreshAll();
            QFrame f;
            f.setFrameShape(QFrame::StyledPanel);
            f.setProperty("svSurface", surface);
            return grab(f, 160, 80);
        };
        const auto moved = [](const QImage &a, const QImage &b) {
            int n = 0;
            for (int y = 0; y < a.height(); ++y)
                for (int x = 0; x < a.width(); ++x)
                {
                    const QColor p = a.pixelColor(x, y);
                    const QColor q = b.pixelColor(x, y);
                    if (qAbs(p.red() - q.red()) > 8 || qAbs(p.green() - q.green()) > 8
                        || qAbs(p.blue() - q.blue()) > 8)
                        ++n;
                }
            return double(n) / double(a.width() * a.height());
        };
        const QString panel = QStringLiteral("panel");
        const QString plate = QStringLiteral("plate");
        const QImage panelRefined = surfaceImage(ThemeManager::Style::RefinedGlass, panel);
        const QImage panelHybrid = surfaceImage(ThemeManager::Style::Hybrid, panel);
        const QImage plateHybrid = surfaceImage(ThemeManager::Style::Hybrid, plate);
        const QImage plateMatte = surfaceImage(ThemeManager::Style::MatteInstrument, plate);
        const double panelPair = moved(panelRefined, panelHybrid);
        const double platePair = moved(plateHybrid, plateMatte);
        tm.setStyle(ThemeManager::Style::RefinedGlass);
        SvStyle::refreshAll();
        QVERIFY2(panelPair >= 0.10,
                 qPrintable(QStringLiteral("Refined and Hybrid paint an ordinary panel the same: %1")
                                .arg(panelPair, 0, 'f', 4)));
        QVERIFY2(platePair >= 0.10,
                 qPrintable(QStringLiteral("Hybrid and Matte paint a hero plate the same: %1")
                                .arg(platePair, 0, 'f', 4)));
    }

    // A DISABLED button looked exactly like a live one, which is a regression the wave introduced:
    // the platform style greyed these before SvStyle took the paint over. buttonPaint read
    // State_Enabled for the label colour and the hover lift and nothing else, so a disabled Primary
    // painted the full accent gradient, a disabled Secondary the full Surface2 and a disabled Chip
    // the full Surface1. 118 setEnabled sites ride on this -- T2VHistoryPage ships its requeue
    // button disabled, and this wave converted Chain's REGENERATE to a real setEnabled(false).
    //
    // Measured on the FILL, with the same channel-sum distance the chip gate uses, because the fill
    // is the channel that survives the qApp overlay sheet. The three roles below are the three the
    // review named; they are also the three whose fills come from three different places (a
    // gradient, an opaque surface token, an opaque plate).
    //
    // The floor is 16 rather than the 24 the chip-SELECTION gate uses, and the reason is a ceiling
    // rather than a lowered bar. Measured on Arcane Glass: fill 312 (primary), 32 (secondary), 20
    // (chip). A chip's whole plate is only 31 channel-levels off the ground it sits on -- Surface1
    // against the window -- so no fill treatment at all, transparency included, can move it 24, and
    // 20 is 65 % of everything the channel has. That is why the EDGE is asserted beside it: Border
    // going to BorderSubtle moves 260 / 49 / 44, and on the chip it is the channel doing the work.
    // A test that gated the fill alone at 24 would be asking the chip for something its palette
    // cannot pay, and the honest answer is that a dimmed chip is said by its rim and its label.
    void the_disabled_button_is_dimmer_than_the_live_one()
    {
        const auto imageOf = [](Role role, bool enabled) {
            QPushButton b; // no text: the centre column is fill, not glyph
            b.setProperty("svRole", SvStyle::roleName(role));
            b.setEnabled(enabled);
            return grab(b);
        };
        const auto distance = [](const QColor &a, const QColor &b) {
            return qAbs(a.red() - b.red()) + qAbs(a.green() - b.green()) + qAbs(a.blue() - b.blue());
        };
        for (const Role role : {Role::Primary, Role::Secondary, Role::Chip})
        {
            const QImage live = imageOf(role, true);
            const QImage off = imageOf(role, false);
            const QColor liveFill = live.pixelColor(live.width() / 2, live.height() / 2);
            const QColor offFill = off.pixelColor(off.width() / 2, off.height() / 2);
            const QColor liveEdge = live.pixelColor(live.width() / 2, 0);
            const QColor offEdge = off.pixelColor(off.width() / 2, 0);
            const int fill = distance(liveFill, offFill);
            const int edge = distance(liveEdge, offEdge);
            qInfo("role %s: fill %s -> %s (%d), edge %s -> %s (%d)",
                  qPrintable(SvStyle::roleName(role)), qPrintable(liveFill.name()),
                  qPrintable(offFill.name()), fill, qPrintable(liveEdge.name()),
                  qPrintable(offEdge.name()), edge);
            QVERIFY2(fill >= 16,
                     qPrintable(QStringLiteral("role %1: disabled fill %2 vs live %3, distance %4")
                                    .arg(SvStyle::roleName(role), offFill.name(), liveFill.name())
                                    .arg(fill)));
            QVERIFY2(edge >= 24,
                     qPrintable(QStringLiteral("role %1: disabled rim %2 vs live %3, distance %4")
                                    .arg(SvStyle::roleName(role), offEdge.name(), liveEdge.name())
                                    .arg(edge)));
        }
    }

    // CE_ProgressBarContents returned early for an indeterminate bar behind a comment saying
    // GlowProgressBar painted its own phase loop. GlowProgressBar derives from QWidget, not
    // QProgressBar, so it never reaches that path at all -- while the bars that do (Dataset while
    // the worker queues, and the Character, Comic and Concept studios) were left with a groove and
    // nothing in it. A busy bar has to differ from a determinate one parked at zero, which is
    // exactly what the early return made it identical to.
    void the_indeterminate_progress_bar_paints_something()
    {
        const auto barImage = [](int minimum, int maximum) {
            QProgressBar bar;
            bar.setRange(minimum, maximum);
            bar.setValue(0);
            bar.setTextVisible(false);
            return grab(bar, 160, 20);
        };
        const QImage busy = barImage(0, 0);
        const QImage parked = barImage(0, 100);
        int moved = 0;
        for (int y = 0; y < busy.height(); ++y)
            for (int x = 0; x < busy.width(); ++x)
            {
                const QColor p = busy.pixelColor(x, y);
                const QColor q = parked.pixelColor(x, y);
                if (qAbs(p.red() - q.red()) > 8 || qAbs(p.green() - q.green()) > 8
                    || qAbs(p.blue() - q.blue()) > 8)
                    ++moved;
            }
        const double fraction = double(moved) / double(busy.width() * busy.height());
        qInfo("indeterminate vs parked-at-zero: %.4f of the bar moved", fraction);
        QVERIFY2(fraction >= 0.05,
                 qPrintable(QStringLiteral("an indeterminate bar draws the same as an empty one: %1")
                                .arg(fraction, 0, 'f', 4)));
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
