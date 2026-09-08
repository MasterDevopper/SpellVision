#include <QtTest>
#include <QSettings>
#include <QSignalSpy>
#include "MainWindow.h"
#include "SettingsPage.h"
#include "shell/LayoutPickerWidget.h"
#include "shell/ShellGeometry.h"
#include "shell/ShellLayout.h"
#include "shell/ShellNavigationController.h"
#include "shell/SideRail.h"
#include "style/SvStyle.h"
#include "generation/CockpitInspector.h"

#include <QAbstractButton>
#include <QApplication>
#include <QBoxLayout>
#include <QFocusEvent>
#include <QFont>
#include <QImage>
#include <QLabel>
#include <QPixmap>
#include <QPoint>
#include <QPointer>
#include <QPushButton>
#include <QRect>
#include <QAbstractSpinBox>
#include <QStackedWidget>
#include <QTextEdit>
#include <QToolButton>

using spellvision::shell::LayoutPickerWidget;
using spellvision::shell::ShellLayout;
using spellvision::shell::SideRail;
using Layout = spellvision::shell::ShellLayout::Layout;

namespace
{
// Rec. 709 relative luminance on the plain 0-255 channel scale -- not gamma-linearised, a coarse but
// stable proxy adequate for a THRESHOLD rather than a colorimetric claim.
qreal luminance(const QColor &c)
{
    return 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue();
}

// The row's own centre pixel: no layout LayoutPickerWidget.cpp draws ever puts a rail, an inspector
// column, a strip or a top bar there -- every fraction in the diagram is comfortably under half the
// interior width, and Workspaces' bar is confined to the top of the thumbnail -- so it reads as bare
// backdrop in every one of the three layouts, selected or not.
QColor backgroundOf(const QImage &img, int y)
{
    return img.pixelColor(img.width() / 2, y);
}

bool isBackground(const QColor &px, const QColor &bg, int tolerance = 6)
{
    return qAbs(px.red() - bg.red()) <= tolerance
        && qAbs(px.green() - bg.green()) <= tolerance
        && qAbs(px.blue() - bg.blue()) <= tolerance;
}

// A fixed skip past the thumbnail's own chrome before any chip could begin: the outer pad (6 px)
// plus the backdrop's inner margin (5 px), both fixed in LayoutThumbnail::paintEvent, plus a few
// pixels of slack for antialiasing. This is a STARTING POINT for the scan, not a colour test --
// measured empirically while building this helper (a real profile of Instrument's rendered
// thumbnail, printed row by row): the backdrop's own outer stroke (drawn in the selection colour
// when selected) and the chip's own inner stroke sit close enough together, under the live preset,
// that under 2 px of true flat backdrop fill separates them -- nowhere near enough consecutive
// pixels for a "wait for N consecutive background pixels" scan to trust as a real gap, and short
// enough that treating the whole span as undifferentiated "not background" would swallow the
// following chip into the same run instead of stopping before it. Skipping a fixed distance
// sidesteps trying to tell the two apart by colour at all.
constexpr int kEdgeMargin = 16;

// The width, in pixels, of the CHIP found starting kEdgeMargin in from the LEFT edge: zero if that
// point already reads as background (no chip reaches this close to the edge -- the geometric
// signature of "no rail here at all"), otherwise the run of non-background pixels from there until
// the row returns to background.
//
// Fix round 1, REQUIRED 1: replaces a single pixel sampled at one x, which cannot tell "narrower"
// from "differently coloured" -- Canvas's rail planted at Instrument's own fraction still differed
// in colour from Instrument's OWN unselected backdrop at that x (nothing about the plant changed
// which card sat on which side of the comparison), and the old case never noticed the rail had grown.
int leftBandWidth(const QImage &img, int y)
{
    const QColor bg = backgroundOf(img, y);
    int x = kEdgeMargin;
    if (x >= img.width() || isBackground(img.pixelColor(x, y), bg))
        return 0;
    int w = 0;
    while (x < img.width() && !isBackground(img.pixelColor(x, y), bg))
    {
        ++w;
        ++x;
    }
    return w;
}

// Same, working in from the RIGHT edge -- an inspector column, or a glyph strip.
int rightBandWidth(const QImage &img, int y)
{
    const QColor bg = backgroundOf(img, y);
    int x = img.width() - 1 - kEdgeMargin;
    if (x < 0 || isBackground(img.pixelColor(x, y), bg))
        return 0;
    int w = 0;
    while (x >= 0 && !isBackground(img.pixelColor(x, y), bg))
    {
        ++w;
        --x;
    }
    return w;
}
} // namespace

class TestShellLayout : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase()
    {
        // Fix round 1, REQUIRED 3: this file never installed SvStyle, so every widget it built
        // painted through whatever the platform's DEFAULT style draws for a bare QFrame/QWidget --
        // kit::setSurface's svSurface property was set but never READ, because nothing in the
        // undecorated style looks at it. Measured before this line existed: the plate came back
        // #2d2d2d under test against #f7faff in the real app, and the margin-band selection
        // separation measured 2.22 levels under test against 12.58 in the app. Installed before any
        // widget in this binary exists, the same way main.cpp does it for the shipped app and
        // test_sv_style.cpp does it for its own suite.
        QApplication::setStyle(new spellvision::style::SvStyle);

        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        savedHadKey_ = s.contains(QStringLiteral("ui/shellLayout"));
        savedLayout_ = s.value(QStringLiteral("ui/shellLayout"), 0).toInt();
        // A MainWindow opens on ui/lastModeId and writes it back. Pinned to Home so the pages the
        // cases below build are known to be unbuilt when they build them -- and saved, because this
        // binary writes the owner's real registry (see the QSettings note in test_sv_style.cpp).
        savedHadMode_ = s.contains(QStringLiteral("ui/lastModeId"));
        savedMode_ = s.value(QStringLiteral("ui/lastModeId")).toString();
        s.setValue(QStringLiteral("ui/lastModeId"), QStringLiteral("home"));
        s.sync();

        // A MainWindow reaches for the machine's runtimes on construction: it adopts a running
        // ComfyUI or STARTS one (90 s of GPU on a test run), and it adopts a running worker or
        // starts a python one. This suite is meant to run anywhere, and a suite that spawns and
        // kills processes on somebody else's machine is a bad citizen.
        //
        // Blocked STRUCTURALLY rather than by starving the environment. The previous attempt pointed
        // SPELLVISION_COMFY at a missing root, which works for ComfyUI and CANNOT work for the
        // worker: RuntimeProfile falls back to <projectRoot>/.venv/Scripts/python.exe and no
        // variable makes that path unfindable. MainWindow now honours one switch before either
        // probe, so the outcome does not depend on what happens to be listening.
        qputenv("SPELLVISION_NO_RUNTIME_LAUNCH", "1");
    }

    // The rail exists so ONE place answers "where does page content begin". The drawer has been
    // computing that from the rail's width, which is right only for as long as the rail never moves.
    void the_rail_reports_where_content_begins()
    {
        spellvision::shell::SideRail rail;
        rail.addMode(QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("image"));
        rail.resize(rail.sizeHint());
        const QPoint origin = rail.contentOrigin();
        QCOMPARE(origin.y(), 0);
        QVERIFY2(origin.x() >= 48, qPrintable(QString::number(origin.x())));
    }

    // The whole point of task 3: the rail can lie down. A rail that swapped its LAYOUT but kept its
    // 56x48 under-icon tiles would look like a layout bug somewhere else, so the shape of a BUTTON is
    // what this asserts, not the direction of a QBoxLayout -- the direction is reachable only through
    // the metrics it is supposed to produce.
    void the_rail_changes_shape_with_its_orientation()
    {
        spellvision::shell::SideRail rail;
        rail.addMode(QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("image"));
        rail.addMode(QStringLiteral("home"), QStringLiteral("Home"), QStringLiteral("home"));
        // Shown (off-screen) because a horizontal tile's HEIGHT is now a layout outcome rather than
        // a number the button carries: it fills the strip, so that the strip's margins and its
        // scrollbar come out of the tile instead of clipping it. A hidden widget never lays out, and
        // the tile would still be reporting the 56x48 it had while standing.
        rail.setAttribute(Qt::WA_DontShowOnScreen);
        rail.show();

        rail.setOrientation(Qt::Vertical);
        rail.resize(rail.sizeHint());
        const QPoint vertical = rail.contentOrigin();
        const QSize verticalButton = rail.buttonFor(QStringLiteral("t2i"))->size();

        rail.setOrientation(Qt::Horizontal);
        // WIDE, and deliberately not sizeHint(): a horizontal bar is as wide as the window, and a
        // bar measured at its own hint is measured in the degraded form it adopts when it has no
        // room -- which is a different question from the one this case asks.
        rail.resize(1600, rail.sizeHint().height());
        QCOMPARE(rail.density(), spellvision::shell::SideRail::Density::Full);
        const QPoint horizontal = rail.contentOrigin();
        const QSize horizontalButton = rail.buttonFor(QStringLiteral("t2i"))->size();

        QCOMPARE(vertical.y(), 0);
        QVERIFY(vertical.x() > 0);
        QCOMPARE(horizontal.x(), 0);
        QVERIFY(horizontal.y() > 0);
        QVERIFY2(horizontalButton.width() > verticalButton.width(),
                 "a horizontal rail sets its label beside the icon, so its buttons are wider");
        QVERIFY2(horizontalButton.height() < verticalButton.height(),
                 "and shorter");
    }

    // The rail is fixed across its thickness and free along its length, and the constraint it is NOT
    // using has to be released. A setOrientation that only adds the new fixed dimension leaves the old
    // one in force, so the rail keeps the shape it just left while every other symptom says it turned.
    void the_rail_releases_the_constraint_it_is_not_using()
    {
        spellvision::shell::SideRail rail;
        rail.addMode(QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("image"));

        rail.setOrientation(Qt::Horizontal);
        QVERIFY2(rail.maximumWidth() == QWIDGETSIZE_MAX,
                 "a horizontal rail is free along its length; the vertical fixed width must be gone");
        QVERIFY(rail.minimumHeight() == rail.maximumHeight());

        rail.setOrientation(Qt::Vertical);
        QVERIFY2(rail.maximumHeight() == QWIDGETSIZE_MAX,
                 "and back: the horizontal fixed height must be gone");
        QVERIFY(rail.minimumWidth() == rail.maximumWidth());
    }

    // Turning the rail must not cost it anything it was carrying: the buttons are relaid out, never
    // rebuilt, so the checked mode, the button objects and their order all survive the round trip.
    void the_rail_stands_back_up_without_losing_what_it_held()
    {
        spellvision::shell::SideRail rail;
        rail.addMode(QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("image"));
        rail.addMode(QStringLiteral("home"), QStringLiteral("Home"), QStringLiteral("home"));
        rail.setCurrentMode(QStringLiteral("home"));

        QToolButton *before = rail.buttonFor(QStringLiteral("home"));
        const QSize verticalButton = before->size();

        rail.setOrientation(Qt::Horizontal);
        rail.setOrientation(Qt::Vertical);

        QCOMPARE(rail.buttonFor(QStringLiteral("home")), before);
        QCOMPARE(rail.modeIds(), QStringList({QStringLiteral("t2i"), QStringLiteral("home")}));
        QCOMPARE(rail.currentMode(), QStringLiteral("home"));
        QVERIFY2(before->isChecked(), "the checked mode survives the turn");
        QCOMPARE(rail.buttonFor(QStringLiteral("home"))->size(), verticalButton);
    }

    // A group header is one widget with two forms. Horizontally it is the labelled boundary the
    // spec asks for; vertically the rail that ships is flat, so the form is kept and the paint is not.
    void a_group_header_is_labelled_only_when_the_rail_lies_down()
    {
        spellvision::shell::SideRail rail;
        rail.addGroupHeader(QStringLiteral("Create"));
        rail.addMode(QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("image"));

        auto *header = rail.findChild<QLabel *>(QStringLiteral("SideRailCaption"));
        QVERIFY2(header, "addGroupHeader has to produce a widget the style can reach by name");
        QVERIFY2(header->isHidden(), "the vertical rail ships flat");
        QVERIFY(header->text().isEmpty());

        rail.setAttribute(Qt::WA_DontShowOnScreen);
        rail.show();
        rail.setOrientation(Qt::Horizontal);
        // A caption is the first thing the bar gives up when it runs out of width, so it is only a
        // caption while there is room for one. Given the room.
        rail.resize(1600, rail.sizeHint().height());
        QCOMPARE(rail.density(), spellvision::shell::SideRail::Density::Full);
        QVERIFY2(!header->isHidden(), "a horizontal rail shows its group boundaries");
        QCOMPARE(header->text().toLower(), QStringLiteral("create"));
    }

    // The drawer starts where PAGE CONTENT BEGINS, and the whole defect was that it started at the
    // rail's WIDTH instead -- indistinguishable while the rail is a left-hand strip and wrong the
    // moment it is not. Fed the rail's real answer for both orientations rather than two hand-typed
    // points, so a contentOrigin() that stopped turning would fail here too.
    void the_drawer_starts_where_page_content_begins()
    {
        spellvision::shell::SideRail rail;
        rail.addMode(QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("image"));
        const QSize shell(1200, 800);

        rail.setOrientation(Qt::Vertical);
        rail.resize(rail.sizeHint());
        const QRect beside = spellvision::shell::drawerRect(rail.contentOrigin(), true, shell, 300);

        rail.setOrientation(Qt::Horizontal);
        rail.resize(rail.sizeHint());
        const QRect below = spellvision::shell::drawerRect(rail.contentOrigin(), true, shell, 300);

        // Vertical: inset from the left by the rail, full height available, flush to the bottom.
        QVERIFY2(beside.left() > 0, "a vertical rail insets the drawer from the left");
        QCOMPARE(beside.right(), shell.width() - 1);
        QCOMPARE(beside.bottom(), shell.height() - 1);
        QCOMPARE(beside.height(), 300);

        // Horizontal: NOT inset from the left -- the failure mode of the old code was that it
        // still would have been, because width() is a number whatever the rail's shape.
        QCOMPARE(below.left(), 0);
        QCOMPARE(below.width(), shell.width());
        QCOMPARE(below.bottom(), shell.height() - 1);
    }

    // THE GUARD, and the case that exists because deleting it used to be free. contentOrigin() is
    // pure geometry on purpose, and a HIDDEN WIDGET KEEPS ITS GEOMETRY -- togglePrimarySidebar()
    // only calls setVisible(false), so a collapsed rail still reports (64, 0). The SAME origin has
    // to give two different answers depending on one bool, which is why both halves are asserted
    // here: a drawerRect that ignored `railVisible` would pass the second half and fail the first,
    // and one that ignored the origin entirely would pass the first and fail the second.
    //
    // Fed from the real rail rather than a typed point, so "a hidden rail still measures 64" is
    // demonstrated rather than assumed -- hide it, then read the origin back.
    void a_hidden_rail_does_not_inset_the_drawer_it_is_not_occupying()
    {
        spellvision::shell::SideRail rail;
        rail.addMode(QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("image"));
        rail.resize(rail.sizeHint());
        rail.setVisible(false);

        const QPoint origin = rail.contentOrigin();
        QVERIFY2(origin.x() > 0,
                 "a hidden widget keeps its geometry -- if this is 0 the guard is untestable and "
                 "the rest of this case proves nothing");

        const QSize shell(1200, 800);
        const QRect hidden = spellvision::shell::drawerRect(origin, false, shell, 300);
        const QRect shown = spellvision::shell::drawerRect(origin, true, shell, 300);

        QCOMPARE(hidden.left(), 0);
        QCOMPARE(hidden.width(), shell.width());
        QCOMPARE(shown.left(), origin.x());
        QCOMPARE(shown.width(), shell.width() - origin.x());
    }

    // The same decision on the other axis: a hidden HORIZONTAL rail must not cost the drawer the
    // height it is no longer occupying. The x half of the guard could be satisfied by a function
    // that only ever zeroed the origin's x.
    void a_hidden_horizontal_rail_does_not_shorten_the_drawer_either()
    {
        spellvision::shell::SideRail rail;
        rail.addMode(QStringLiteral("t2i"), QStringLiteral("T2I"), QStringLiteral("image"));
        rail.setOrientation(Qt::Horizontal);
        rail.resize(rail.sizeHint());
        rail.setVisible(false);

        const QPoint origin = rail.contentOrigin();
        QVERIFY(origin.y() > 0);

        const QSize shell(1200, 800);
        const QRect hidden = spellvision::shell::drawerRect(origin, false, shell, 5000);
        const QRect shown = spellvision::shell::drawerRect(origin, true, shell, 5000);

        QCOMPARE(hidden.height(), shell.height() - spellvision::shell::kDrawerPageRemainder);
        QCOMPARE(shown.height(),
                 shell.height() - origin.y() - spellvision::shell::kDrawerPageRemainder);
    }

    // The two clamps, and the second is the one the turn introduced. A drawer taller than the shell
    // must not swallow the page, and with a horizontal rail the space it may take is what the rail
    // leaves BELOW itself -- otherwise a maximised drawer covers the navigation.
    void the_drawer_never_covers_the_rail_or_the_whole_page()
    {
        const QSize shell(1200, 800);

        const QRect floored = spellvision::shell::drawerRect(QPoint(64, 0), true, shell, 10);
        QCOMPARE(floored.height(), spellvision::shell::kDrawerMinimumHeight);

        const QRect capped = spellvision::shell::drawerRect(QPoint(64, 0), true, shell, 5000);
        QCOMPARE(capped.height(), shell.height() - spellvision::shell::kDrawerPageRemainder);

        const QRect underRail = spellvision::shell::drawerRect(QPoint(0, 44), true, shell, 5000);
        QCOMPARE(underRail.height(), shell.height() - 44 - spellvision::shell::kDrawerPageRemainder);
        QVERIFY2(underRail.top() >= 44, "a horizontal rail is never covered by the drawer");

        // A shell too short for the floor still yields the floor rather than a negative height.
        const QRect tiny = spellvision::shell::drawerRect(QPoint(0, 44), true, QSize(1200, 60), 300);
        QCOMPARE(tiny.height(), spellvision::shell::kDrawerMinimumHeight);
    }

    void the_default_is_instrument()
    {
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        s.remove(QStringLiteral("ui/shellLayout"));
        ShellLayout::instance().load();
        QCOMPARE(ShellLayout::instance().layout(), Layout::Instrument);
    }

    void the_choice_survives_a_round_trip()
    {
        ShellLayout::instance().setLayout(Layout::Workspaces);
        ShellLayout::instance().load();
        QCOMPARE(ShellLayout::instance().layout(), Layout::Workspaces);
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        QCOMPARE(s.value(QStringLiteral("ui/shellLayout")).toInt(), 2);
    }

    void a_no_op_set_does_not_announce_a_change()
    {
        ShellLayout::instance().setLayout(Layout::Canvas);
        QSignalSpy spy(&ShellLayout::instance(), &ShellLayout::layoutChanged);
        ShellLayout::instance().setLayout(Layout::Canvas);
        QCOMPARE(spy.count(), 0);
        ShellLayout::instance().setLayout(Layout::Instrument);
        QCOMPARE(spy.count(), 1);
    }

    void an_out_of_range_index_is_ignored_rather_than_crashing()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);
        ShellLayout::instance().setLayoutByIndex(7);
        QCOMPARE(ShellLayout::instance().layout(), Layout::Instrument);
        ShellLayout::instance().setLayoutByIndex(-1);
        QCOMPARE(ShellLayout::instance().layout(), Layout::Instrument);
    }

    void a_stored_value_this_build_does_not_know_reads_as_instrument()
    {
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        s.setValue(QStringLiteral("ui/shellLayout"), 99);
        s.sync();
        ShellLayout::instance().load();
        QCOMPARE(ShellLayout::instance().layout(), Layout::Instrument);

        s.setValue(QStringLiteral("ui/shellLayout"), -4);
        s.sync();
        ShellLayout::instance().load();
        QCOMPARE(ShellLayout::instance().layout(), Layout::Instrument);
    }

    void every_layout_has_a_name_and_a_sentence()
    {
        QCOMPARE(ShellLayout::instance().layoutNames().size(), 3);
        for (const QString &name : ShellLayout::instance().layoutNames())
            QVERIFY(!name.isEmpty());
        for (int i = 0; i < 3; ++i)
            QVERIFY(!ShellLayout::instance().layoutDescription(static_cast<Layout>(i)).isEmpty());
    }

    // THE ROUND TRIP THROUGH THE UI (task 8 brief, step 3). SettingsPage carries a LayoutPickerWidget
    // in its Appearance section; a click on one of its three cards has to reach the real singleton
    // and the real settings store exactly the way the Surface Style combo already does --
    // setLayoutByIndex called directly off the click (SettingsPage.cpp's surfaceStyleCombo_
    // connection is the model), not a detour through a page signal into MainWindow glue.
    //
    // Driven through QTest::mouseClick on the cards reached BY NAME, never by calling
    // setLayoutByIndex on the singleton directly -- that would prove the enum round-trips (already
    // covered above) and nothing about whether the WIDGET is wired to it at all.
    void picking_a_card_in_settings_writes_the_real_layout()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);

        SettingsPage page;
        page.setAttribute(Qt::WA_DontShowOnScreen);
        page.resize(900, 760);
        page.show();
        QCoreApplication::processEvents();

        auto *picker = page.findChild<spellvision::shell::LayoutPickerWidget *>(
            QStringLiteral("LayoutPickerWidget"));
        QVERIFY2(picker, "SettingsPage has no LayoutPickerWidget reachable by name");

        QSignalSpy pickedSpy(picker, &spellvision::shell::LayoutPickerWidget::layoutPicked);

        struct Case { const char *cardName; Layout layout; };
        const Case cases[] = {
            {"LayoutCard_Canvas", Layout::Canvas},
            {"LayoutCard_Workspaces", Layout::Workspaces},
            {"LayoutCard_Instrument", Layout::Instrument},
        };
        for (const Case &c : cases)
        {
            QWidget *card = picker->findChild<QWidget *>(QString::fromLatin1(c.cardName));
            QVERIFY2(card, qPrintable(QStringLiteral("no card named %1").arg(c.cardName)));
            QTest::mouseClick(card, Qt::LeftButton);
            QCoreApplication::processEvents();

            QCOMPARE(ShellLayout::instance().layout(), c.layout);
            QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
            QCOMPARE(s.value(QStringLiteral("ui/shellLayout")).toInt(), static_cast<int>(c.layout));
        }
        // One notification per real change -- the same "only on a real change" contract
        // setLayoutByIndex itself carries, reached this time through the widget's own relay.
        QCOMPARE(pickedSpy.count(), 3);

        ShellLayout::instance().setLayout(Layout::Instrument);
    }

    // THE GUARD for "derived, never cached". A `selected_` member a click handler sets would pass
    // the case above outright -- every pick in it IS a click -- so this one changes the singleton
    // from OUTSIDE the widget, with no click on either card, and asks whether the picker noticed
    // anyway. Read from the SCREEN (a grabbed pixel), not from a property, because a widget that
    // recorded "selected" in a flag and never repainted from it would satisfy any assertion about
    // state.
    //
    // Fix round 1, REQUIRED 3: this used to compare with `!=`, which a ONE-level separation passes
    // exactly like a hundred -- the defect class this case exists to catch (wave-1's original chip
    // bug measured a 4-level separation, functionally invisible) would have sailed through unnoticed.
    // Rewritten as a THRESHOLD on luminance separation: floor 8, comfortably below the smallest zone
    // the fix-round-1 review measured under the live preset (11.87 in the label band) and
    // comfortably above a near-invisible regression. Only reachable once SvStyle is actually
    // installed (initTestCase, above) -- an unstyled QFrame paints no svSurface fill at all, so this
    // pixel would have been the SAME transparent nothing before and after the switch, and `!=` would
    // have failed for a reason that had nothing to do with selection.
    void a_card_s_selection_follows_the_singleton_not_a_click_flag()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);

        LayoutPickerWidget picker;
        picker.setAttribute(Qt::WA_DontShowOnScreen);
        picker.resize(720, 220);
        picker.show();
        QCoreApplication::processEvents();

        QWidget *instrumentCard = picker.findChild<QWidget *>(QStringLiteral("LayoutCard_Instrument"));
        QWidget *canvasCard = picker.findChild<QWidget *>(QStringLiteral("LayoutCard_Canvas"));
        QVERIFY(instrumentCard);
        QVERIFY(canvasCard);

        // A point inside the card's own margin -- left of the thumbnail, above the name label --
        // which nothing else paints. The card frame is the only thing that reaches this pixel, so
        // its colour is a clean read of "selected or not" with no anti-aliased stroke edge to land
        // wrong on.
        auto marginPixel = [](QWidget *card) {
            return card->grab().toImage().pixelColor(8, card->height() / 2);
        };

        const QColor instrumentAtRest = marginPixel(instrumentCard);
        const QColor canvasAtRest = marginPixel(canvasCard);

        // Changed from OUTSIDE the widget entirely. No click on either card.
        ShellLayout::instance().setLayout(Layout::Canvas);
        QCoreApplication::processEvents();

        const QColor instrumentAfter = marginPixel(instrumentCard);
        const QColor canvasAfter = marginPixel(canvasCard);

        const qreal floor = 8.0;
        const qreal deltaCanvas = qAbs(luminance(canvasAfter) - luminance(canvasAtRest));
        const qreal deltaInstrument = qAbs(luminance(instrumentAfter) - luminance(instrumentAtRest));
        QVERIFY2(deltaCanvas >= floor,
                 qPrintable(QStringLiteral("Canvas's margin separated by only %1 luminance levels "
                                           "(floor %2) when the singleton picked it -- with no click "
                                           "on Canvas at all, only a live read of the singleton could "
                                           "have moved it")
                                .arg(deltaCanvas, 0, 'f', 2).arg(floor, 0, 'f', 2)));
        QVERIFY2(deltaInstrument >= floor,
                 qPrintable(QStringLiteral("Instrument's margin separated by only %1 luminance levels "
                                           "(floor %2) when the singleton moved off it")
                                .arg(deltaInstrument, 0, 'f', 2).arg(floor, 0, 'f', 2)));

        // The two colours are also cross-checked against EACH OTHER rather than only against a
        // floor: whatever the active preset's unselected fill and selected tint actually are,
        // Instrument's post-switch colour must equal Canvas's pre-switch colour (both "the
        // unselected fill") and Canvas's post-switch colour must equal Instrument's pre-switch
        // colour (both "the selected tint") -- which a hardcoded comparison colour would not prove,
        // and which a threshold alone does not either (two DIFFERENT tints could each individually
        // clear the floor against their own rest colour).
        QCOMPARE(instrumentAfter, canvasAtRest);
        QCOMPARE(canvasAfter, instrumentAtRest);

        ShellLayout::instance().setLayout(Layout::Instrument);
    }

    // THE CARRIED CONSTRAINT FROM TASK 7'S REVIEW: Canvas's rail must not share Instrument's width --
    // a thumbnail that drew both the same advertises two layouts that look identical, when the rail
    // is the largest single thing that separates them in the shipped shell.
    //
    // Fix round 1, REQUIRED 1: this used to sample a single pixel at a fixed x and assert the two
    // colours differed. That is a claim about COLOUR, not about WIDTH, and it does not survive the
    // plant the carried constraint actually describes -- Canvas's rail widened to Instrument's own
    // fraction still differs in colour from Canvas's OWN unselected backdrop at that x (both cards
    // are rendered from the same theme, so the two rails paint identically, but the case only ever
    // compared Instrument's pixel against Canvas's, which stayed the rail's fill on both sides of
    // the plant and never noticed the rail had grown). Measured against the code with the plant
    // applied: the suite read 40 passed, 0 failed.
    //
    // Rewritten to measure the band's WIDTH via leftBandWidth() (a profile across the whole row,
    // not one point), which is what "narrower" actually means, and compared with a MARGIN rather
    // than a bare `<` -- Canvas's rail must come in at no more than 70% of Instrument's, not merely
    // one pixel less, so a rounding-level difference cannot pass for "visibly thinner".
    void canvas_s_thumbnail_rail_reads_narrower_than_instrument_s()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);

        LayoutPickerWidget picker;
        picker.setAttribute(Qt::WA_DontShowOnScreen);
        picker.resize(720, 220);
        picker.show();
        QCoreApplication::processEvents();

        QWidget *instrumentThumb = thumbnailOf(picker, QStringLiteral("LayoutCard_Instrument"));
        QWidget *canvasThumb = thumbnailOf(picker, QStringLiteral("LayoutCard_Canvas"));
        QVERIFY(instrumentThumb);
        QVERIFY(canvasThumb);
        QCOMPARE(instrumentThumb->size(), canvasThumb->size());

        const int y = instrumentThumb->height() / 2;
        const int instrumentRail = leftBandWidth(instrumentThumb->grab().toImage(), y);
        const int canvasRail = leftBandWidth(canvasThumb->grab().toImage(), y);

        QVERIFY2(instrumentRail > 4,
                 qPrintable(QStringLiteral("premise: Instrument's rail measured only %1px; there is "
                                           "nothing here to be narrower than").arg(instrumentRail)));
        QVERIFY2(canvasRail > 0, "premise: Canvas has SOME rail -- collapsed, not absent");
        QVERIFY2(canvasRail <= instrumentRail * 0.7,
                 qPrintable(QStringLiteral("Canvas's rail measured %1px against Instrument's %2px -- "
                                           "not visibly narrower")
                                .arg(canvasRail).arg(instrumentRail)));
    }

    // REQUIRED 2a: Workspaces has NO LEFT RAIL AT ALL (spec table, section 2.1) -- the vertical rail
    // is gone, replaced by a horizontal bar across the top. Nothing in the suite asked this before
    // fix round 1: a plant that gave Workspaces Instrument's rail left the suite at 40 passed, 0
    // failed. Measured at mid-height, which is BELOW Workspaces' top bar (28% of the thumbnail's
    // interior height) -- exactly the row a left rail would occupy if one were wrongly drawn there.
    void workspaces_has_no_left_rail_in_its_thumbnail()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);

        LayoutPickerWidget picker;
        picker.setAttribute(Qt::WA_DontShowOnScreen);
        picker.resize(720, 220);
        picker.show();
        QCoreApplication::processEvents();

        QWidget *instrumentThumb = thumbnailOf(picker, QStringLiteral("LayoutCard_Instrument"));
        QWidget *workspacesThumb = thumbnailOf(picker, QStringLiteral("LayoutCard_Workspaces"));
        QVERIFY(instrumentThumb);
        QVERIFY(workspacesThumb);
        QCOMPARE(instrumentThumb->size(), workspacesThumb->size());

        const int y = instrumentThumb->height() / 2;
        const int instrumentRail = leftBandWidth(instrumentThumb->grab().toImage(), y);
        QVERIFY2(instrumentRail > 4,
                 qPrintable(QStringLiteral("premise: Instrument's rail measured only %1px at this row")
                                .arg(instrumentRail)));

        const int workspacesLeft = leftBandWidth(workspacesThumb->grab().toImage(), y);
        QVERIFY2(workspacesLeft <= 2,
                 qPrintable(QStringLiteral("Workspaces shows a %1px left-anchored band -- it must "
                                           "have no left rail at all").arg(workspacesLeft)));
    }

    // REQUIRED 2b: Canvas's inspector is a THIN STRIP of tab glyphs, never a column (spec table,
    // section 2.1 -- "it must read as a strip, not as a column"). A plant that widened the strip
    // fraction to a column left the suite at 40 passed, 0 failed before this case existed. Two
    // bounds: narrower than Instrument's OWN inspector column (relative -- the two must not
    // converge), and comfortably under a quarter of the thumbnail's full width (absolute -- a strip
    // that widened toward Instrument's fraction but never quite reached it would still pass a
    // relative-only check).
    void canvas_s_inspector_reads_as_a_strip_not_a_column()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);

        LayoutPickerWidget picker;
        picker.setAttribute(Qt::WA_DontShowOnScreen);
        picker.resize(720, 220);
        picker.show();
        QCoreApplication::processEvents();

        QWidget *instrumentThumb = thumbnailOf(picker, QStringLiteral("LayoutCard_Instrument"));
        QWidget *canvasThumb = thumbnailOf(picker, QStringLiteral("LayoutCard_Canvas"));
        QVERIFY(instrumentThumb);
        QVERIFY(canvasThumb);
        QCOMPARE(instrumentThumb->size(), canvasThumb->size());

        const int y = instrumentThumb->height() / 2;
        const int instrumentInspector = rightBandWidth(instrumentThumb->grab().toImage(), y);
        const int canvasStrip = rightBandWidth(canvasThumb->grab().toImage(), y);

        QVERIFY2(instrumentInspector > 4,
                 qPrintable(QStringLiteral("premise: Instrument's inspector measured only %1px; "
                                           "there is nothing here to be narrower than")
                                .arg(instrumentInspector)));
        QVERIFY2(canvasStrip > 0, "premise: Canvas has SOME strip -- glyphs, not nothing");
        QVERIFY2(canvasStrip <= instrumentInspector * 0.7,
                 qPrintable(QStringLiteral("Canvas's strip measured %1px against Instrument's %2px "
                                           "column -- not narrower, reads as a column")
                                .arg(canvasStrip).arg(instrumentInspector)));
        QVERIFY2(canvasStrip < instrumentThumb->width() / 4,
                 qPrintable(QStringLiteral("Canvas's strip measured %1px, a quarter of the "
                                           "thumbnail's own %2px width -- too wide to read as a strip "
                                           "regardless of what Instrument's column measures")
                                .arg(canvasStrip).arg(instrumentThumb->width())));
    }

    // I3: the schematic used to draw the rail WIDER than the inspector -- 44px against 37px at the
    // fixture size -- backwards from the shipped shell, where a 64px rail sits against a 280-460px
    // inspector. Checked on both layouts that carry a real inspector column: Instrument, and
    // Workspaces, whose column is seated below the bar rather than beside a rail but still has to
    // carry the same "wider than a rail" relationship.
    void the_inspector_reads_wider_than_the_rail_in_instrument_and_workspaces()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);

        LayoutPickerWidget picker;
        picker.setAttribute(Qt::WA_DontShowOnScreen);
        picker.resize(720, 220);
        picker.show();
        QCoreApplication::processEvents();

        QWidget *instrumentThumb = thumbnailOf(picker, QStringLiteral("LayoutCard_Instrument"));
        QWidget *workspacesThumb = thumbnailOf(picker, QStringLiteral("LayoutCard_Workspaces"));
        QVERIFY(instrumentThumb);
        QVERIFY(workspacesThumb);

        const int y = instrumentThumb->height() / 2;
        const QImage instrumentImg = instrumentThumb->grab().toImage();
        const int instrumentRail = leftBandWidth(instrumentImg, y);
        const int instrumentInspector = rightBandWidth(instrumentImg, y);
        QVERIFY2(instrumentRail > 0 && instrumentInspector > 0, "premise: both bands are measurable");
        QVERIFY2(instrumentInspector > instrumentRail,
                 qPrintable(QStringLiteral("Instrument's rail measured %1px against an inspector of "
                                           "only %2px -- the proportion the real shell carries is "
                                           "inverted").arg(instrumentRail).arg(instrumentInspector)));

        // Workspaces' inspector sits below the bar rather than beside a rail, but the same row (mid
        // height, below the 28%-tall bar) already serves workspaces_has_no_left_rail_in_its_thumbnail
        // for the same reason: it is where a rail would be if one were wrongly drawn, and where the
        // inspector column actually is.
        const int workspacesInspector = rightBandWidth(workspacesThumb->grab().toImage(), y);
        QVERIFY2(workspacesInspector > instrumentRail,
                 qPrintable(QStringLiteral("Workspaces' inspector measured %1px, no wider than "
                                           "Instrument's %2px rail")
                                .arg(workspacesInspector).arg(instrumentRail)));
    }

    // I2: task 9's first-run dialog must not write a real setting before the user accepts (spec
    // 2.7 -- dismissing first run is never a trap), so a pick in Deferred mode has to stop short of
    // the singleton. Proven the same way the round trip above proves Immediate mode: through a real
    // click, checking the REAL entry point (ShellLayout::instance().layout()) stays put and the
    // widget's OWN selectedLayout() moves, then that commitSelection() is the one thing that closes
    // the gap.
    void deferred_mode_does_not_touch_the_singleton_until_committed()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);

        LayoutPickerWidget picker;
        picker.setCommitMode(LayoutPickerWidget::CommitMode::Deferred);
        picker.setAttribute(Qt::WA_DontShowOnScreen);
        picker.resize(720, 220);
        picker.show();
        QCoreApplication::processEvents();

        QSignalSpy pickedSpy(&picker, &LayoutPickerWidget::layoutPicked);

        QWidget *canvasCard = picker.findChild<QWidget *>(QStringLiteral("LayoutCard_Canvas"));
        QVERIFY(canvasCard);
        QTest::mouseClick(canvasCard, Qt::LeftButton);
        QCoreApplication::processEvents();

        QCOMPARE(ShellLayout::instance().layout(), Layout::Instrument);
        QCOMPARE(picker.selectedLayout(), Layout::Canvas);
        QCOMPARE(pickedSpy.count(), 1);

        picker.commitSelection();
        QCOMPARE(ShellLayout::instance().layout(), Layout::Canvas);

        ShellLayout::instance().setLayout(Layout::Instrument);
    }

    // I4: layoutPicked used to forward ShellLayout::layoutChanged verbatim, so it fired for a change
    // this widget had nothing to do with -- task 9 connects to this exact signal to learn a pick
    // happened. Two phases distinguish the fix from the old behaviour: an EXTERNAL change first
    // (no click on either card), which must emit nothing, then a REAL click, which must emit
    // exactly once. The old code would have shown 1 after the external change alone.
    void layout_picked_fires_only_for_a_pick_this_widget_made()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);

        LayoutPickerWidget picker;
        picker.setAttribute(Qt::WA_DontShowOnScreen);
        picker.resize(720, 220);
        picker.show();
        QCoreApplication::processEvents();

        QSignalSpy pickedSpy(&picker, &LayoutPickerWidget::layoutPicked);

        ShellLayout::instance().setLayout(Layout::Canvas);
        QCoreApplication::processEvents();
        QCOMPARE(pickedSpy.count(), 0);

        QWidget *workspacesCard = picker.findChild<QWidget *>(QStringLiteral("LayoutCard_Workspaces"));
        QVERIFY(workspacesCard);
        QTest::mouseClick(workspacesCard, Qt::LeftButton);
        QCoreApplication::processEvents();
        QCOMPARE(pickedSpy.count(), 1);

        ShellLayout::instance().setLayout(Layout::Instrument);
    }

    // The ladder. `Prefs` read `Pr` at 1600 px in the layout this task shipped: sixteen modes and
    // three captions do not fit a 1600 px bar, and scrolling made the mode reachable while leaving
    // the bar looking broken at rest. So the bar gives things up in order -- captions, then labels
    // -- and it decides by MEASURING its own content against its own width.
    //
    // Driven from requiredWidthFor() rather than from typed pixel counts. A test that said "at
    // 900 px it goes icon-only" would be asserting today's fonts and today's sixteen modes; asking
    // the bar what each form costs and then handing it one pixel less is asserting the RULE.
    void the_bar_gives_up_its_captions_before_its_labels()
    {
        using Density = spellvision::shell::SideRail::Density;
        spellvision::shell::SideRail rail;
        QString section;
        for (const auto &spec : spellvision::shell::ShellNavigationController::railButtonSpecs())
        {
            if (spec.section != section)
            {
                section = spec.section;
                rail.addGroupHeader(section);
            }
            rail.addMode(spec.modeId, spec.text, spec.modeId, spec.toolTip);
        }
        // Filled BEFORE it is shown, which is the order MainWindow uses and the only order under
        // which a visibility assertion means anything: a widget created as a child of an
        // already-visible parent starts hidden, and QLayout::addChildWidget does not show it. Shown
        // first, every tile reads as hidden and the guard below fires on the test rather than on the
        // rail.
        rail.setAttribute(Qt::WA_DontShowOnScreen);
        rail.show();
        rail.setOrientation(Qt::Horizontal);

        // The premise, stated rather than assumed: every tile is on screen to begin with, so a
        // failure of the same assertion at the narrowest rung is the LADDER hiding something.
        for (const QString &id : rail.modeIds())
            QVERIFY2(rail.buttonFor(id)->isVisibleTo(&rail),
                     qPrintable(QStringLiteral("%1 was already hidden before the bar narrowed").arg(id)));

        const int full = rail.requiredWidthFor(Density::Full);
        const int noCaptions = rail.requiredWidthFor(Density::NoCaptions);
        const int iconOnly = rail.requiredWidthFor(Density::IconOnly);
        qInfo("rail widths: Full %d, NoCaptions %d, IconOnly %d", full, noCaptions, iconOnly);
        QVERIFY2(full > noCaptions, "dropping the captions has to actually save width");
        QVERIFY2(noCaptions > iconOnly, "dropping the labels has to actually save width");

        const int barHeight = rail.sizeHint().height();
        rail.resize(full + 40, barHeight);
        QCOMPARE(rail.density(), Density::Full);

        rail.resize(full - 1, barHeight);
        QCOMPARE(rail.density(), Density::NoCaptions);

        rail.resize(noCaptions - 1, barHeight);
        QCOMPARE(rail.density(), Density::IconOnly);

        // THE guard, at the rung where the temptation is greatest: the ladder may narrow a tile and
        // may never REMOVE one. Asserted per spec and against the SCREEN -- isVisibleTo, because a
        // rail in a test has no shown ancestor and isVisible() would be false for every tile.
        //
        // A count of modeIds() is not this assertion and was not a substitute for it: a density that
        // hid the last mode and left it out of the width sum satisfied a count, dropped the required
        // width by 50px, made `Prefs` vanish from the bar and kept every case in this file green.
        for (const auto &spec : spellvision::shell::ShellNavigationController::railButtonSpecs())
        {
            QToolButton *button = rail.buttonFor(spec.modeId);
            QVERIFY2(button, qPrintable(QStringLiteral("mode %1 is not on the bar").arg(spec.modeId)));
            QVERIFY2(button->isVisibleTo(&rail),
                     qPrintable(QStringLiteral("the bar fitted by HIDING %1").arg(spec.modeId)));
        }
        // And the grouping survives the narrowest rung too. Dropping the captions replaced them with
        // a hairline; dropping the labels must not quietly finish the job the captions started.
        for (QLabel *header : rail.findChildren<QLabel *>(QStringLiteral("SideRailCaption")))
            QVERIFY2(header->isVisibleTo(&rail),
                     "a group boundary is hidden at the rung that needs the structure most");

        // Nothing becomes unidentifiable: an icon-only tile says its own name.
        QToolButton *tile = rail.buttonFor(QStringLiteral("t2i"));
        QVERIFY(tile);
        QCOMPARE(tile->toolButtonStyle(), Qt::ToolButtonIconOnly);
        QVERIFY2(tile->toolTip().contains(QStringLiteral("T2I")),
                 qPrintable(QStringLiteral("icon-only tooltip lost the label: %1").arg(tile->toolTip())));

        // And it recovers. A ladder that only goes down is a ladder that traps the user in the
        // degraded form the first time they narrow the window.
        rail.resize(full + 40, barHeight);
        QCOMPARE(rail.density(), Density::Full);
        QCOMPARE(tile->toolButtonStyle(), Qt::ToolButtonTextBesideIcon);
    }

    // A theme is free to hand the rail a different label font or a different icon size, and either
    // changes what a tile COSTS -- so refreshIcons(), which is what a preset change calls, has to
    // re-decide the rung as well as re-ink the glyphs. Without that the bar keeps the decision it
    // made under the old theme until something resizes it, which is the clipped bar returning by a
    // second route.
    //
    // Driven by widening the labels directly rather than by switching preset: no preset this app
    // ships changes the rail's font (makeButton pins it at 10px) or its 18px icons, so a preset
    // switch would move no width and the case would pass whether or not the fix were there. The
    // mechanism is what is under test, and this is the mechanism.
    void a_theme_change_re_decides_the_rung()
    {
        using Density = spellvision::shell::SideRail::Density;
        spellvision::shell::SideRail rail;
        QString section;
        for (const auto &spec : spellvision::shell::ShellNavigationController::railButtonSpecs())
        {
            if (spec.section != section)
            {
                section = spec.section;
                rail.addGroupHeader(section);
            }
            rail.addMode(spec.modeId, spec.text, spec.modeId, spec.toolTip);
        }
        // Filled BEFORE it is shown, which is the order MainWindow uses and the only order under
        // which a visibility assertion means anything: a widget created as a child of an
        // already-visible parent starts hidden, and QLayout::addChildWidget does not show it. Shown
        // first, every tile reads as hidden and the guard below fires on the test rather than on the
        // rail.
        rail.setAttribute(Qt::WA_DontShowOnScreen);
        rail.show();
        rail.setOrientation(Qt::Horizontal);

        // Exactly enough room for the richest form, and not one pixel more.
        const int full = rail.requiredWidthFor(Density::Full);
        rail.resize(full, rail.sizeHint().height());
        QCOMPARE(rail.density(), Density::Full);

        // The theme hands every tile a bigger face. Nothing resizes the bar.
        for (const QString &id : rail.modeIds())
        {
            QToolButton *button = rail.buttonFor(id);
            QFont bigger = button->font();
            bigger.setPixelSize(bigger.pixelSize() + 6);
            button->setFont(bigger);
        }
        QVERIFY2(rail.requiredWidthFor(Density::Full) > rail.width(),
                 "the premise failed: the wider face has to make Full stop fitting");

        rail.refreshIcons();
        QVERIFY2(rail.density() != Density::Full,
                 "refreshIcons re-inked the glyphs and kept a rung that no longer fits");
        QVERIFY2(rail.requiredWidthFor(rail.density()) <= rail.width(),
                 "the rung it re-decided on does not fit either");
    }

    // --- the shell, wired ------------------------------------------------------------------------

    // FIRST, and the order is the point. Generation pages are pre-warmed one per event-loop turn
    // 250 ms after the window is shown, so this is the only moment at which one is guaranteed still
    // unbuilt: the window has just been constructed and no event loop has turned since. That makes
    // the ensureGenerationPageBuilt tail testable rather than coincidental.
    //
    // The shell is bent by hand first. Without that, a builder that never re-asserted the layout
    // would pass -- the shell would already be in the right shape and nothing would have to happen.
    void a_generation_page_built_after_a_switch_arrives_into_the_switched_shell()
    {
        ShellLayout::instance().setLayout(Layout::Workspaces);
        MainWindow &window = mainWindow();
        QCOMPARE(shellDirection(window), QBoxLayout::TopToBottom);

        QStackedWidget *stack = window.findChild<QStackedWidget *>(QStringLiteral("MainPageStack"));
        QVERIFY(stack);
        const int before = stack->count();

        shellLayoutOf(window)->setDirection(QBoxLayout::LeftToRight);
        QVERIFY(QMetaObject::invokeMethod(&window, "switchToMode",
                                          Q_ARG(QString, QStringLiteral("t2v"))));

        QVERIFY2(stack->count() > before,
                 "t2v was already built, so this case proved nothing about the builder's tail");
        QCOMPARE(shellDirection(window), QBoxLayout::TopToBottom);
    }

    // THE case this task exists for. A layout is a rearrangement of furniture, so the page inside it
    // has to come through untouched -- the same object, still holding what the user typed. A switch
    // that rebuilt the cockpit would pass a "the shell turned" assertion and cost the user the
    // prompt, and it would look like a glitch rather than a bug.
    //
    // The last two assertions are not decoration: without them a MainWindow::applyShellLayout that
    // did NOTHING AT ALL would pass every line above, since a page that is never disturbed is
    // trivially preserved. The page has to survive a shell that really did move.
    void a_layout_switch_keeps_the_page_and_what_is_typed_in_it()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);
        MainWindow &window = mainWindow();
        QVERIFY(QMetaObject::invokeMethod(&window, "switchToMode",
                                          Q_ARG(QString, QStringLiteral("t2i"))));

        QWidget *before = window.currentPageForTest();
        QVERIFY(before);
        QTextEdit *prompt = before->findChild<QTextEdit *>(QStringLiteral("PromptEditor"));
        QVERIFY2(prompt, "the cockpit's prompt has to be reachable by name, not by tree order -- "
                         "the negative prompt is a QTextEdit too");
        prompt->setPlainText(QStringLiteral("a lighthouse in a storm"));

        ShellLayout::instance().setLayout(Layout::Workspaces);
        QCoreApplication::processEvents();

        QCOMPARE(window.currentPageForTest(), before);
        QCOMPARE(prompt->toPlainText(), QStringLiteral("a lighthouse in a storm"));
        QCOMPARE(rail(window)->orientation(), Qt::Horizontal);
        QCOMPARE(shellDirection(window), QBoxLayout::TopToBottom);
    }

    // The two layouts have to be two layouts. Instrument is a column beside the pages; Workspaces is
    // a bar above them, and the drawer's origin moves from an x-offset to a y-offset with it --
    // which is the fact the whole drawer geometry chain in this file is built on.
    void the_two_layouts_arrange_the_shell_differently()
    {
        MainWindow &window = mainWindow();

        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
        QCOMPARE(shellDirection(window), QBoxLayout::LeftToRight);
        QCOMPARE(rail(window)->orientation(), Qt::Vertical);
        const QPoint standing = rail(window)->contentOrigin();

        ShellLayout::instance().setLayout(Layout::Workspaces);
        QCoreApplication::processEvents();
        QCOMPARE(shellDirection(window), QBoxLayout::TopToBottom);
        QCOMPARE(rail(window)->orientation(), Qt::Horizontal);
        const QPoint lying = rail(window)->contentOrigin();

        QVERIFY2(standing.x() > 0 && standing.y() == 0, "a vertical rail insets from the left");
        QVERIFY2(lying.y() > 0 && lying.x() == 0, "a horizontal rail insets from the top");
    }

    // The residual task 4 could not close. drawerRect() is pure and thoroughly tested, but the two
    // ARGUMENTS MainWindow feeds it -- the rail's origin and whether the rail is visible -- were
    // reached by no test at all, because nothing constructed a MainWindow. Hardcoding `true` for
    // the visibility would have passed everything.
    //
    // Driven through the real path rather than by calling the private positioner: the title bar's
    // signals are what move this furniture in the app, and invoking one by name is the handle a
    // test has on them. Three states, and each would survive a different wrong implementation -- a
    // positioner that ignored the origin passes the second, one that ignored the orientation passes
    // the first, one that ignored visibility passes both.
    void the_drawer_is_placed_from_the_rail_the_shell_actually_has()
    {
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();

        QWidget *bar = window.findChild<QWidget *>(QStringLiteral("CustomTitleBar"));
        QVERIFY(bar);
        QVERIFY(QMetaObject::invokeMethod(bar, "bottomPanelToggleRequested"));
        QWidget *drawer = window.findChild<QWidget *>(QStringLiteral("QueueOverlay"));
        QVERIFY(drawer);
        QVERIFY2(drawer->isVisible(), "the drawer has to be open or its geometry means nothing");

        const int shellWidth = window.centralWidget()->width();
        QCOMPARE(drawer->x(), rail(window)->contentOrigin().x());
        QVERIFY2(drawer->x() > 0, "a vertical rail insets the drawer from the left");
        QCOMPARE(drawer->x() + drawer->width(), shellWidth);

        ShellLayout::instance().setLayout(Layout::Workspaces);
        QCoreApplication::processEvents();
        QCOMPARE(drawer->x(), 0);
        QCOMPARE(drawer->width(), shellWidth);
        QVERIFY2(drawer->y() >= rail(window)->contentOrigin().y(),
                 "a horizontal rail is never covered by the drawer");

        // And the guard: a hidden rail KEEPS its geometry, so contentOrigin() still reports the
        // rail's thickness. The drawer must not inset for a column that is not on screen.
        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
        QVERIFY(drawer->x() > 0);
        QVERIFY(QMetaObject::invokeMethod(bar, "primarySidebarToggleRequested"));
        QVERIFY(!rail(window)->isVisible());
        QVERIFY2(rail(window)->contentOrigin().x() > 0,
                 "a hidden widget keeps its geometry -- if this is 0 the guard is untestable");
        QCOMPARE(drawer->x(), 0);
        QCOMPARE(drawer->width(), shellWidth);

        // Put the shell back the way the next case expects to find it.
        QVERIFY(QMetaObject::invokeMethod(bar, "primarySidebarToggleRequested"));
        QVERIFY(rail(window)->isVisible());
        QVERIFY(QMetaObject::invokeMethod(bar, "bottomPanelToggleRequested"));
    }

    // The same rule in the real shell, at both ends of the range the app supports: the minimum
    // window size MainWindow sets (1180x760) and the 1600 the capture rig uses. "Nothing clipped at
    // rest" is exactly `required <= available` for the density the bar chose, and it is asserted
    // rather than eyeballed -- the first Workspaces capture LOOKED fine until `Prefs` was read.
    void the_bar_fits_at_both_ends_of_the_window_range()
    {
        using Density = spellvision::shell::SideRail::Density;
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Workspaces);
        QCoreApplication::processEvents();

        const QSize before = window.size();
        for (const QSize &size : {QSize(1180, 760), QSize(1600, 1000)})
        {
            window.resize(size);
            QCoreApplication::processEvents();
            spellvision::shell::SideRail *bar = rail(window);
            const int available = bar->width();
            const int required = bar->requiredWidthFor(bar->density());
            qInfo("window %dx%d: bar available %d, required %d at density %d (Full would need %d)",
                  size.width(), size.height(), available, required, int(bar->density()),
                  bar->requiredWidthFor(Density::Full));
            QVERIFY2(required <= available,
                     qPrintable(QStringLiteral("the bar needs %1 and has %2 at %3 px")
                                    .arg(required).arg(available).arg(size.width())));
            // Every mode is still ON THE BAR -- per spec, and asked of the SCREEN rather than of a
            // list. `modeIds().size() == railButtonSpecs().size()` stood here and was the wrong
            // noun: it counts entries in modes_, which a density that HIDES a tile leaves untouched.
            // Planted, that density made `Prefs` disappear at 1180 and every case here stayed green.
            for (const auto &spec : spellvision::shell::ShellNavigationController::railButtonSpecs())
            {
                QToolButton *button = bar->buttonFor(spec.modeId);
                QVERIFY2(button, qPrintable(QStringLiteral("mode %1 is not on the bar").arg(spec.modeId)));
                QVERIFY2(button->isVisibleTo(bar),
                         qPrintable(QStringLiteral("the bar fitted at %1px by HIDING %2")
                                        .arg(size.width()).arg(spec.modeId)));
            }
            QToolButton *models = bar->buttonFor(QStringLiteral("models"));
            QVERIFY(models);
            models->click();
            QCoreApplication::processEvents();
            QCOMPARE(bar->currentMode(), QStringLiteral("models"));
        }
        window.resize(before);
        QCoreApplication::processEvents();
    }

    // Canvas changes the COCKPIT, not the shell. It must not quietly become Workspaces on the way
    // past: the rail stands and the body still runs left to right, exactly as in Instrument.
    void canvas_keeps_the_shell_it_does_not_change()
    {
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Workspaces);
        QCoreApplication::processEvents();
        ShellLayout::instance().setLayout(Layout::Canvas);
        QCoreApplication::processEvents();
        QCOMPARE(shellDirection(window), QBoxLayout::LeftToRight);
        QCOMPARE(rail(window)->orientation(), Qt::Vertical);
        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
    }

    // The fourth thing Canvas is (spec section 2.1): the rail stands, and collapses to glyphs. Every
    // assertion here is about the SCREEN. `modeIds().size()` would count entries in a vector that a
    // density which HID a tile leaves untouched -- the wrong noun, and the one a planted defect
    // already walked through once in this wave -- so reachability is asked of isVisibleTo and of a
    // click that actually navigates.
    void canvas_collapses_the_rail_to_glyphs_without_losing_a_mode()
    {
        using Density = spellvision::shell::SideRail::Density;
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
        spellvision::shell::SideRail *bar = rail(window);
        QCOMPARE(bar->density(), Density::Full);
        const int standing = bar->width();
        const QPoint standingOrigin = bar->contentOrigin();

        ShellLayout::instance().setLayout(Layout::Canvas);
        QCoreApplication::processEvents();
        QCOMPARE(rail(window), bar); // the rail is re-laid, never rebuilt
        QCOMPARE(bar->orientation(), Qt::Vertical);
        QCOMPARE(bar->density(), Density::IconOnly);
        QVERIFY2(bar->width() < standing,
                 qPrintable(QStringLiteral("the rail is still %1 px wide").arg(bar->width())));
        // The drawer reads contentOrigin(), so a rail that narrowed without saying so would leave a
        // gap down the left of every overlay.
        QVERIFY2(bar->contentOrigin().x() < standingOrigin.x(), "contentOrigin did not follow the rail in");

        for (const auto &spec : spellvision::shell::ShellNavigationController::railButtonSpecs())
        {
            QToolButton *button = bar->buttonFor(spec.modeId);
            QVERIFY2(button, qPrintable(QStringLiteral("mode %1 left the rail").arg(spec.modeId)));
            QVERIFY2(button->isVisibleTo(bar),
                     qPrintable(QStringLiteral("Canvas collapsed the rail by HIDING %1").arg(spec.modeId)));
            // A GLYPH, asked of the tile's drawn form rather than of its text(): ToolButtonIconOnly
            // leaves text() intact and simply stops painting it, so `text().isEmpty()` would be the
            // model-not-the-screen noun again.
            QVERIFY2(button->toolButtonStyle() == Qt::ToolButtonIconOnly,
                     qPrintable(QStringLiteral("%1 is still drawing its label").arg(spec.modeId)));
            QVERIFY2(button->width() < 56,
                     qPrintable(QStringLiteral("%1 kept the 56 px labelled tile").arg(spec.modeId)));
            // And the label the glyph dropped has to be somewhere, or sixteen icons are sixteen guesses.
            QVERIFY2(button->toolTip().contains(spec.text),
                     qPrintable(QStringLiteral("%1 lost its name: tile text '%2', tooltip '%3'")
                                    .arg(spec.modeId, button->text(), button->toolTip())));
        }

        // Reachable, not merely present.
        QToolButton *models = bar->buttonFor(QStringLiteral("models"));
        QVERIFY(models);
        models->click();
        QCoreApplication::processEvents();
        QCOMPARE(bar->currentMode(), QStringLiteral("models"));

        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
        QCOMPARE(bar->density(), Density::Full);
        QCOMPARE(bar->width(), standing);
        QCOMPARE(bar->contentOrigin(), standingOrigin);
        QToolButton *home = bar->buttonFor(QStringLiteral("home"));
        QVERIFY(home);
        QCOMPARE(home->toolButtonStyle(), Qt::ToolButtonTextUnderIcon);
        QCOMPARE(home->size(), QSize(56, 48));
    }

    // A request may not make the bar RICHER than it fits. Canvas asks for glyphs and Workspaces lies
    // the rail down; the horizontal ladder still owns the answer, and asking for Full at 1180 px must
    // not undo the degradation the bar needs to fit -- which is the failure mode of a "requested
    // density" that is applied instead of compared.
    void a_request_never_makes_the_bar_richer_than_it_fits()
    {
        using Density = spellvision::shell::SideRail::Density;
        MainWindow &window = mainWindow();
        const QSize before = window.size();
        ShellLayout::instance().setLayout(Layout::Workspaces);
        QCoreApplication::processEvents();
        spellvision::shell::SideRail *bar = rail(window);
        QCOMPARE(bar->densityRequest(), Density::Full);

        window.resize(QSize(1180, 760));
        QCoreApplication::processEvents();
        QVERIFY2(bar->density() != Density::Full,
                 "premise: at 1180 the bar cannot afford Full, or this case proves nothing");
        QVERIFY2(bar->requiredWidthFor(bar->density()) <= bar->width(),
                 "the Full request was applied instead of compared, and the bar no longer fits");

        window.resize(before);
        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
    }

    // Canvas gives the room to the image, and it does it to the page rather than to the shell. Both
    // halves are asserted on the SCREEN -- the prompt's actual height in pixels and the inspector's
    // actual width -- because a cockpit that recorded a "canvas" flag and drew itself unchanged
    // would satisfy any assertion about state.
    void canvas_folds_the_prompt_and_collapses_the_inspector()
    {
        MainWindow &window = mainWindow();
        QWidget *page = t2iPage(window);
        QVERIFY(page);
        QTextEdit *prompt = page->findChild<QTextEdit *>(QStringLiteral("PromptEditor"));
        QVERIFY(prompt);
        QWidget *inspector = page->findChild<QWidget *>(QStringLiteral("CockpitInspector"));
        QVERIFY(inspector);

        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
        const int openPrompt = prompt->height();
        const int openInspector = inspector->width();
        QVERIFY2(openPrompt > 0 && openInspector > 0,
                 "premise: the cockpit is laid out before anything is folded");

        ShellLayout::instance().setLayout(Layout::Canvas);
        QCoreApplication::processEvents();
        QVERIFY2(prompt->height() < openPrompt,
                 qPrintable(QStringLiteral("prompt stayed %1 px").arg(prompt->height())));
        QVERIFY2(inspector->width() < openInspector / 2,
                 qPrintable(QStringLiteral("inspector stayed %1 px").arg(inspector->width())));
        // The canvas is what the room is given TO, so it has to actually receive it.
        QWidget *canvasCard = page->findChild<QWidget *>(QStringLiteral("CanvasCard"));
        QVERIFY(canvasCard);
        QVERIFY2(canvasCard->width() > openInspector, "the canvas did not take the freed width");

        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
    }

    // THE requirement of this task. A layout is a rearrangement, so the way back has to land on the
    // arrangement it left -- the same page object, the same text, and the same measured width, not a
    // default that happens to look similar. The inspector's budget is ADAPTIVE and is recomputed
    // from the page width, so "restores the budget it had" is the assertion that separates a real
    // restore from a hardcoded 380.
    void canvas_and_back_restores_the_cockpit_exactly()
    {
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Instrument);
        QWidget *page = t2iPage(window);
        QVERIFY(page);
        QCoreApplication::processEvents();

        // QPointer on everything that has to SURVIVE the round trip. A defect that destroys one
        // instead of hiding it would otherwise crash on the next dereference, and a fatal error
        // prints the case's name but never its message -- the reader learns which case died, not
        // what it was guarding. A QPointer nulls instead, so the failure gets to speak.
        QPointer<QTextEdit> prompt = page->findChild<QTextEdit *>(QStringLiteral("PromptEditor"));
        QVERIFY(prompt);
        prompt->setPlainText(QStringLiteral("a lighthouse in a storm"));
        QPointer<QWidget> inspector = page->findChild<QWidget *>(QStringLiteral("CockpitInspector"));
        QVERIFY(inspector);
        QCoreApplication::processEvents();

        const int width = inspector->width();
        const int promptHeight = prompt->height();
        const QRect actionRow = actionRowGeometry(page);
        QVERIFY(actionRow.isValid());

        ShellLayout::instance().setLayout(Layout::Canvas);
        QCoreApplication::processEvents();
        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();

        QVERIFY2(prompt, "the round trip DESTROYED the prompt instead of re-laying it");
        QVERIFY2(inspector, "the round trip DESTROYED the inspector instead of expanding it");
        QCOMPARE(window.currentPageForTest(), page);
        QCOMPARE(prompt->toPlainText(), QStringLiteral("a lighthouse in a storm"));
        QCOMPARE(inspector->width(), width);
        QCOMPARE(prompt->height(), promptHeight);
        QCOMPARE(actionRowGeometry(page), actionRow);
    }

    // "Restores the budget it had" needs a case that can TELL a budget from a constant, and the
    // one above cannot: it compares the width before a switch with the width after, so a build that
    // gave the inspector one hardcoded width everywhere passes it. Planted (const int w = 380 in
    // applyWidthBudget) that build was green across all 33 cases.
    //
    // So this one makes the budget prove it is a budget. Two window sizes must give two widths --
    // asserted, because if they do not then nothing here can distinguish a restore from a constant
    // and the case has to say so rather than pass. Then the window is resized WHILE COLLAPSED, which
    // separates the three candidate implementations: a restore that replays the width remembered at
    // collapse time gives the wide number, a restore that falls back to a default gives neither, and
    // only one that applies the budget the page went on computing gives the narrow one.
    void an_expanded_inspector_returns_to_the_budget_not_to_a_default()
    {
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Instrument);
        QWidget *page = t2iPage(window);
        QVERIFY(page);
        QWidget *inspector = page->findChild<QWidget *>(QStringLiteral("CockpitInspector"));
        QVERIFY(inspector);
        const QSize before = window.size();

        window.resize(QSize(1180, 760));
        QCoreApplication::processEvents();
        const int narrow = inspector->width();
        window.resize(QSize(1600, 1000));
        QCoreApplication::processEvents();
        const int wide = inspector->width();
        QVERIFY2(narrow != wide,
                 qPrintable(QStringLiteral("the inspector is %1 px at both 1180 and 1600, so its "
                                           "width is not a budget and no case here can prove a "
                                           "restore of one").arg(narrow)));

        ShellLayout::instance().setLayout(Layout::Canvas);
        QCoreApplication::processEvents();
        window.resize(QSize(1180, 760));
        QCoreApplication::processEvents();
        QVERIFY2(inspector->width() < narrow / 2,
                 "a resize while collapsed re-opened the column behind the layout's back");

        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
        QCOMPARE(inspector->width(), narrow);

        window.resize(before);
        QCoreApplication::processEvents();
    }

    // Where a value would go missing. The collapse hides the tabs' content, and a control inside a
    // hidden tab is the one thing on this page a user cannot watch disappear -- so the case proves
    // it is off the screen (isVisibleTo, not a flag) AND that its value came back with it.
    void a_control_inside_a_collapsed_tab_keeps_its_value()
    {
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Instrument);
        QWidget *page = t2iPage(window);
        QVERIFY(page);
        QCoreApplication::processEvents();

        QWidget *inspector = page->findChild<QWidget *>(QStringLiteral("CockpitInspector"));
        QVERIFY(inspector);
        QStackedWidget *tabs = inspector->findChild<QStackedWidget *>(QStringLiteral("InspectorStack"));
        QVERIFY(tabs);

        // The premise, SEARCHED FOR rather than assumed, and this is the second time this task paid
        // for that. A widget added under an already-visible parent can start hidden; and the app's
        // Simple mode hides whole rows, so in Simple the Sampling tab puts NO spin box on screen and
        // a case pinned to it fails on unmutated code -- which is exactly what happened here. So it
        // walks the visible tabs until a control is genuinely on screen, and only then is there a
        // premise to rest on.
        QPointer<QAbstractSpinBox> spin = nullptr;
        QPointer<QAbstractButton> openTab = nullptr;
        const auto tabButtons = inspector->findChildren<QAbstractButton *>(QStringLiteral("InspectorTab"));
        for (QAbstractButton *tab : tabButtons)
        {
            if (!tab->isVisibleTo(page))
                continue;
            tab->click();
            QCoreApplication::processEvents();
            const auto candidates = tabs->currentWidget()->findChildren<QAbstractSpinBox *>();
            for (QAbstractSpinBox *candidate : candidates)
            {
                if (candidate->isVisibleTo(page))
                {
                    spin = candidate;
                    break;
                }
            }
            if (spin)
            {
                openTab = tab;
                break;
            }
        }
        QVERIFY2(spin, "no inspector tab put a spin box on screen; there is nothing to lose");
        QVERIFY(openTab);

        // Read as TEXT so the case works for whichever numeric control it found -- an int spin and a
        // double spin do not share a value type, and what the user would lose is what the box says.
        const QString typed = spin->text();
        QVERIFY2(!typed.isEmpty(), "a spin box showing nothing is not a value to lose");

        ShellLayout::instance().setLayout(Layout::Canvas);
        QCoreApplication::processEvents();
        // Destroyed, not hidden, is the failure this whole case exists to rule out, so it is the
        // first thing asked -- and asked of a QPointer, which can answer it without dereferencing a
        // dangling widget and taking the message down with the binary.
        QVERIFY2(spin, "collapsing DESTROYED the control instead of hiding it");
        QVERIFY2(!spin->isVisibleTo(page), "a collapsed inspector still had its content on screen");
        QCOMPARE(spin->text(), typed);
        // Hidden content, VISIBLE tabs: the strip is how the user gets the content back, so it may
        // not go with it.
        QVERIFY2(openTab->isVisibleTo(page), "the collapsed strip lost its tab glyphs");

        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
        QVERIFY2(spin, "expanding DESTROYED the control instead of showing it again");
        QVERIFY(spin->isVisibleTo(page));
        QCOMPARE(spin->text(), typed);
    }

    // THE OTHER HALF OF "RESTORES THE BUDGET", and neither half excludes the other's defect.
    //
    // The two-window-size case below proves the opened width is not a CONSTANT. It cannot prove the
    // width is CORRECT: `applyExpandedForm` returning `budget * 9 / 10` still gives two different
    // numbers at two different window sizes and sails through it. This case closes that by asserting
    // exact equality against a width `applyExpandedForm` DID NOT PRODUCE.
    //
    // That is the whole trick, and it is why the sequence starts from an inspector the LAYOUT has
    // opened. `expandedByTheLayout` came out of the page's adaptive pass -- setWidthBudget ->
    // applyWidthBudget -- so comparing the collapse/expand round trip against it compares two
    // independent routes to the same number. Starting from a collapsed inspector instead would take
    // both numbers from applyExpandedForm, and any deterministic wrong answer would be reproduced
    // faithfully and pass.
    //
    // No resize and no layout switch anywhere in it, so `budget_` cannot legitimately have moved:
    // collapsing the inspector re-lays the page's children but does not change the PAGE's own size,
    // and updateAdaptiveLayout only runs from resizeEvent. Every number here must therefore be the
    // same number, exactly.
    void expanding_reproduces_the_width_the_page_gave_the_inspector()
    {
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Instrument);
        QPointer<QWidget> page = t2iPage(window);
        QVERIFY(page);
        QCoreApplication::processEvents();

        QPointer<CockpitInspector> inspector = page->findChild<CockpitInspector *>(QStringLiteral("CockpitInspector"));
        QVERIFY2(inspector, "the cockpit inspector is not reachable by name");
        QVERIFY2(!inspector->isCollapsed(), "premise: Instrument leaves the inspector open");
        const int expandedByTheLayout = inspector->width();
        QVERIFY2(expandedByTheLayout > 100,
                 qPrintable(QStringLiteral("premise: the inspector is laid out; it is %1 px")
                                .arg(expandedByTheLayout)));

        // Driven through the production API rather than a glyph click, because a click also changes
        // the selected tab and this case is about a width. Same two functions the layout calls.
        inspector->setCollapsed(true);
        QCoreApplication::processEvents();
        const int collapsed = inspector->width();
        QVERIFY2(collapsed < expandedByTheLayout / 2,
                 qPrintable(QStringLiteral("the column did not collapse; it is %1 px").arg(collapsed)));

        inspector->setCollapsed(false);
        QCoreApplication::processEvents();
        QVERIFY2(inspector, "expanding DESTROYED the inspector instead of restoring it");
        QVERIFY2(inspector->width() == expandedByTheLayout,
                 qPrintable(QStringLiteral("the column came back %1 px wide where the page had given "
                                           "it %2 -- a scaled or offset restore, not the budget")
                                .arg(inspector->width()).arg(expandedByTheLayout)));

        // And again, so a restore that DRIFTS -- each expansion a little narrower than the last --
        // is caught too. Nothing between the two expansions changes anything the budget depends on.
        inspector->setCollapsed(true);
        QCoreApplication::processEvents();
        inspector->setCollapsed(false);
        QCoreApplication::processEvents();
        QVERIFY2(inspector->width() == expandedByTheLayout,
                 qPrintable(QStringLiteral("the second expansion came back %1 px against %2 -- the "
                                           "restore is not reproducible")
                                .arg(inspector->width()).arg(expandedByTheLayout)));
        QCOMPARE(inspector->isCollapsed(), false);
    }

    // Expand on demand, and back. The judgement call this task carried was overlay versus push, and
    // the push is asserted the way the user meets it: the column is wide again and the canvas is
    // narrower, and a second click on the same glyph undoes both -- so the canvas is never left in a
    // state with no way out.
    //
    // IT IS ALSO THE ONLY PATH THAT PROVES THE RESTORED WIDTH IS A BUDGET. Every layout SWITCH now
    // resizes the page -- fix round 1 made the rail 16 px narrower in Canvas, so Canvas-to-Instrument
    // fires resizeEvent -> updateAdaptiveLayout -> setWidthBudget -> applyWidthBudget, which restores
    // the width by a second route. A constant planted in applyExpandedForm is invisible to any case
    // that switches layouts, because the resize repairs it before the case looks. A glyph click
    // resizes nothing, so what the column comes back to is what applyExpandedForm decided and
    // nothing else.
    void a_tab_glyph_opens_the_collapsed_inspector_and_closes_it_again()
    {
        MainWindow &window = mainWindow();
        const QSize restore = window.size();
        QPointer<QWidget> page = t2iPage(window);
        QVERIFY(page);
        ShellLayout::instance().setLayout(Layout::Canvas);
        QCoreApplication::processEvents();
        window.resize(QSize(1600, 1000));
        QCoreApplication::processEvents();

        // QPointer, not a raw pointer, on everything held across a layout switch. A defect that
        // DESTROYS one of these instead of hiding it would otherwise take the whole binary down on
        // the next dereference, and a fatal error prints the case's name but never its message --
        // the reader is told which case died, not what it was protecting.
        QPointer<QWidget> inspector = page->findChild<QWidget *>(QStringLiteral("CockpitInspector"));
        QVERIFY2(inspector, "the inspector was destroyed, not collapsed");
        QPointer<QWidget> canvasCard = page->findChild<QWidget *>(QStringLiteral("CanvasCard"));
        QVERIFY2(canvasCard, "the canvas card was destroyed by a layout switch");
        const int strip = inspector->width();
        const int wideCanvas = canvasCard->width();

        QPointer<QAbstractButton> output = tabNamed(inspector, QStringLiteral("Output"));
        QVERIFY2(output, "a collapsed tab must still be findable by the name it carries");
        output->click();
        QCoreApplication::processEvents();
        const int openedWide = inspector->width();
        QVERIFY2(openedWide > strip, "the glyph did not open the column");
        QVERIFY2(canvasCard->width() < wideCanvas, "a push narrows the canvas; this did not");

        output->click();
        QCoreApplication::processEvents();
        QCOMPARE(inspector->width(), strip);
        QCOMPARE(canvasCard->width(), wideCanvas);

        // THE ASSERTION THAT SEPARATES A BUDGET FROM A CONSTANT, on the one path where nothing else
        // can restore the width. The window is resized WHILE THE COLUMN IS SHUT, so the budget the
        // page keeps computing is recorded and not applied; the glyph then opens the column with no
        // resize of its own. Two window sizes must give two opened widths -- a hardcoded width in
        // applyExpandedForm gives one, and passes every other case in this file.
        //
        // The literal "the opened width equals the width it had before it collapsed" cannot be
        // asserted across a layout boundary any more: the Canvas rail is 16 px narrower than the
        // Instrument one since fix round 1, so the page is wider and its adaptive budget genuinely
        // differs. Measured at the fixture size: 360 standing, 378 peeked. Comparing the two would
        // fail on correct code.
        window.resize(QSize(1180, 760));
        QCoreApplication::processEvents();
        QVERIFY2(inspector->width() == strip,
                 "a resize while collapsed re-opened the column behind the layout's back");
        output->click();
        QCoreApplication::processEvents();
        const int openedNarrow = inspector->width();
        QVERIFY2(openedNarrow > strip, "the glyph did not open the column at the narrow size");
        QVERIFY2(openedNarrow != openedWide,
                 qPrintable(QStringLiteral("the column opens to %1 px at both 1600 and 1180, so it "
                                           "is restoring a constant rather than the budget")
                                .arg(openedNarrow)));

        window.resize(restore);
        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
    }

    // The prompt is a line UNTIL IT IS FOCUSED. Driven with real focus events sent to the widget
    // rather than by calling setFocus on an off-screen window, which does not deliver one.
    void the_folded_prompt_grows_when_it_is_focused()
    {
        MainWindow &window = mainWindow();
        QWidget *page = t2iPage(window);
        QVERIFY(page);
        ShellLayout::instance().setLayout(Layout::Canvas);
        QCoreApplication::processEvents();

        QTextEdit *prompt = page->findChild<QTextEdit *>(QStringLiteral("PromptEditor"));
        QVERIFY(prompt);
        const int folded = prompt->maximumHeight();

        QFocusEvent focusIn(QEvent::FocusIn);
        QCoreApplication::sendEvent(prompt, &focusIn);
        QCoreApplication::processEvents();
        QVERIFY2(prompt->maximumHeight() > folded, "focus did not grow the folded prompt");

        QFocusEvent focusOut(QEvent::FocusOut);
        QCoreApplication::sendEvent(prompt, &focusOut);
        QCoreApplication::processEvents();
        QCoreApplication::processEvents(); // the re-fold is deferred one turn on purpose
        QCOMPARE(prompt->maximumHeight(), folded);

        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
    }

    // The action row is the canvas card FOOTER, in every layout. Spec section 2.6 describes Canvas
    // as moving it there; the tree already had it there before this task and before task 6, so what
    // is worth asserting is the seat rather than a move -- and asserting it in all three layouts is
    // what would catch a future arrangement that quietly lifted it out.
    void the_action_row_is_the_canvas_card_footer_in_every_layout()
    {
        MainWindow &window = mainWindow();
        QWidget *page = t2iPage(window);
        QVERIFY(page);
        for (Layout layout : {Layout::Instrument, Layout::Canvas, Layout::Workspaces})
        {
            ShellLayout::instance().setLayout(layout);
            QCoreApplication::processEvents();
            QWidget *canvasCard = page->findChild<QWidget *>(QStringLiteral("CanvasCard"));
            QVERIFY(canvasCard);
            QWidget *footer = canvasFooter(page);
            QVERIFY2(footer, "the canvas card has no last widget to be a footer");
            QCOMPARE(footer->parentWidget(), canvasCard);
            QWidget *generate = generateButton(page);
            QVERIFY(generate);
            QVERIFY2(footer->isAncestorOf(generate),
                     "the Generate button is not in the canvas card footer");
            QVERIFY2(generate->isVisibleTo(page), "the action row lost its hero button");
        }
        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
    }

    // Idempotent, and idempotent by ASKING rather than by remembering. The second half is the half a
    // `lastAppliedLayout_` flag would fail: knock the shell out of shape behind the function's back
    // and the next call must put it right, because that is precisely the situation the page-builder
    // tail exists for.
    void applying_the_same_layout_twice_is_free_and_applying_it_to_a_bent_shell_is_not()
    {
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Workspaces);
        QCoreApplication::processEvents();

        QWidget *page = window.currentPageForTest();
        const int widgets = window.findChild<QStackedWidget *>(QStringLiteral("MainPageStack"))->count();
        QToolButton *tile = rail(window)->buttonFor(QStringLiteral("t2i"));
        QVERIFY(tile);

        window.applyShellLayout(Layout::Workspaces);
        QCOMPARE(window.currentPageForTest(), page);
        QCOMPARE(window.findChild<QStackedWidget *>(QStringLiteral("MainPageStack"))->count(), widgets);
        QCOMPARE(rail(window)->buttonFor(QStringLiteral("t2i")), tile);
        QCOMPARE(shellDirection(window), QBoxLayout::TopToBottom);

        shellLayoutOf(window)->setDirection(QBoxLayout::LeftToRight);
        window.applyShellLayout(Layout::Workspaces);
        QCOMPARE(shellDirection(window), QBoxLayout::TopToBottom);
    }

    // The other lazy builder. The rail pages register a builder instead of constructing, and nothing
    // pre-warms them -- they are built on first navigation and only then -- so unlike the generation
    // case above this one does not depend on where in the file it sits.
    void a_deferred_rail_page_built_after_a_switch_arrives_into_the_switched_shell()
    {
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Workspaces);
        QCoreApplication::processEvents();

        QStackedWidget *stack = window.findChild<QStackedWidget *>(QStringLiteral("MainPageStack"));
        QVERIFY(stack);

        for (const QString &mode : {QStringLiteral("history"), QStringLiteral("train")})
        {
            const int before = stack->count();
            shellLayoutOf(window)->setDirection(QBoxLayout::LeftToRight);
            QVERIFY(QMetaObject::invokeMethod(&window, "switchToMode", Q_ARG(QString, mode)));
            QVERIFY2(stack->count() > before,
                     qPrintable(QStringLiteral("%1 was already built; nothing was proved").arg(mode)));
            QVERIFY2(shellDirection(window) == QBoxLayout::TopToBottom,
                     qPrintable(QStringLiteral("building %1 left the shell in the old shape").arg(mode)));
            QVERIFY(window.currentPageForTest());
        }
    }

    void cleanupTestCase()
    {
        delete window_;
        window_ = nullptr;

        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        if (savedHadKey_)
            s.setValue(QStringLiteral("ui/shellLayout"), savedLayout_);
        else
            s.remove(QStringLiteral("ui/shellLayout"));
        if (savedHadMode_)
            s.setValue(QStringLiteral("ui/lastModeId"), savedMode_);
        else
            s.remove(QStringLiteral("ui/lastModeId"));
        s.sync();
    }

private:
    // ONE window for the whole binary. A MainWindow costs several seconds to construct (it builds
    // the shell, scans the model catalog and homes a page), and the cases below are about what a
    // switch does to a shell that already exists rather than about construction.
    MainWindow &mainWindow()
    {
        if (!window_)
        {
            window_ = new MainWindow;
            window_->resize(1400, 900);
            window_->setAttribute(Qt::WA_DontShowOnScreen);
            window_->show();
        }
        return *window_;
    }

    // A card's own painted diagram, reached by the card's object name from a LayoutPickerWidget
    // rather than by a per-layout thumbnail name -- LayoutCardThumbnail is deliberately generic
    // (each card's own subtree holds exactly one), so scoping the search to the named card is what
    // makes the answer unambiguous.
    static QWidget *thumbnailOf(LayoutPickerWidget &picker, const QString &cardName)
    {
        QWidget *card = picker.findChild<QWidget *>(cardName);
        return card ? card->findChild<QWidget *>(QStringLiteral("LayoutCardThumbnail")) : nullptr;
    }

    // The shell's rail and its body layout, reached the way a test may and production may not. The
    // `shell-geometry-through-the-layout` sweep rule forbids reading the rail's geometry outside
    // qt_ui/shell/; the C++ tests are not in its scope on purpose, because proving contentOrigin()
    // turns means reading it.
    static SideRail *rail(MainWindow &window)
    {
        SideRail *found = window.findChild<SideRail *>(QStringLiteral("SideRail"));
        Q_ASSERT(found);
        return found;
    }

    // The T2I cockpit, built if it is not there yet. Every Canvas case needs the same page, and
    // switchToMode is the only sanctioned way to get one.
    static QWidget *t2iPage(MainWindow &window)
    {
        QMetaObject::invokeMethod(&window, "switchToMode", Q_ARG(QString, QStringLiteral("t2i")));
        QCoreApplication::processEvents();
        return window.currentPageForTest();
    }

    // A tab by the name it carries. Collapsed, the button TEXT is a glyph and the name moves to the
    // tooltip, so a case that looked for the text alone would stop finding it exactly when the strip
    // is what it is testing.
    static QAbstractButton *tabNamed(QWidget *inspector, const QString &name)
    {
        const auto tabs = inspector->findChildren<QAbstractButton *>(QStringLiteral("InspectorTab"));
        for (QAbstractButton *tab : tabs)
            if (tab->text() == name || tab->toolTip() == name)
                return tab;
        return nullptr;
    }

    // The last widget in the canvas card layout -- which is what "the canvas card footer" MEANS, and
    // is therefore what has to be asked for. Reached from the card down rather than from a button
    // up: "PrimaryActionButton" is not unique on this page (the video transport bar carries one
    // too), so findChild by that name returns whichever was built first, and a case that trusted it
    // was asserting the seat of the Play button.
    static QWidget *canvasFooter(QWidget *page)
    {
        QWidget *card = page->findChild<QWidget *>(QStringLiteral("CanvasCard"));
        QLayout *layout = card ? card->layout() : nullptr;
        if (!layout || layout->count() == 0)
            return nullptr;
        QLayoutItem *last = layout->itemAt(layout->count() - 1);
        return last ? last->widget() : nullptr;
    }

    // The cockpit hero button, by the text it carries. Its object name is shared, its text is not.
    static QWidget *generateButton(QWidget *page)
    {
        const auto buttons = page->findChildren<QPushButton *>(QStringLiteral("PrimaryActionButton"));
        for (QPushButton *button : buttons)
            if (button->text().contains(QStringLiteral("Generate")))
                return button;
        return nullptr;
    }

    // Where the action row sits, in the page own coordinates. Compared before and after a round
    // trip: a row that came back a few pixels off is a row something re-laid rather than restored.
    static QRect actionRowGeometry(QWidget *page)
    {
        QWidget *row = canvasFooter(page);
        if (!row)
            return QRect();
        return QRect(row->mapTo(page, QPoint(0, 0)), row->size());
    }

    static QBoxLayout *shellLayoutOf(MainWindow &window)
    {
        auto *layout = qobject_cast<QBoxLayout *>(window.centralWidget()->layout());
        Q_ASSERT(layout);
        return layout;
    }

    static QBoxLayout::Direction shellDirection(MainWindow &window)
    {
        return shellLayoutOf(window)->direction();
    }

    MainWindow *window_ = nullptr;
    bool savedHadKey_ = false;
    int savedLayout_ = 0;
    bool savedHadMode_ = false;
    QString savedMode_;
};

QTEST_MAIN(TestShellLayout)
#include "test_shell_layout.moc"
