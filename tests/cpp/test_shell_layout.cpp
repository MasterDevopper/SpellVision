#include <QtTest>
#include <QSettings>
#include <QSignalSpy>
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
