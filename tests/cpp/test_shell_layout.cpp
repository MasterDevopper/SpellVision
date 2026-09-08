#include <QtTest>
#include <QSettings>
#include <QSignalSpy>
#include "shell/ShellGeometry.h"
#include "shell/ShellLayout.h"
#include "shell/SideRail.h"

#include <QLabel>
#include <QToolButton>

using spellvision::shell::ShellLayout;
using Layout = spellvision::shell::ShellLayout::Layout;

class TestShellLayout : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase()
    {
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        savedHadKey_ = s.contains(QStringLiteral("ui/shellLayout"));
        savedLayout_ = s.value(QStringLiteral("ui/shellLayout"), 0).toInt();
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

        rail.setOrientation(Qt::Vertical);
        rail.resize(rail.sizeHint());
        const QPoint vertical = rail.contentOrigin();
        const QSize verticalButton = rail.buttonFor(QStringLiteral("t2i"))->size();

        rail.setOrientation(Qt::Horizontal);
        rail.resize(rail.sizeHint());
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

        rail.setOrientation(Qt::Horizontal);
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

    void cleanupTestCase()
    {
        QSettings s(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        if (savedHadKey_)
            s.setValue(QStringLiteral("ui/shellLayout"), savedLayout_);
        else
            s.remove(QStringLiteral("ui/shellLayout"));
        s.sync();
    }

private:
    bool savedHadKey_ = false;
    int savedLayout_ = 0;
};

QTEST_MAIN(TestShellLayout)
#include "test_shell_layout.moc"
