#include <QtTest>
#include <QSettings>
#include <QSignalSpy>
#include "shell/ShellLayout.h"
#include "shell/SideRail.h"

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
