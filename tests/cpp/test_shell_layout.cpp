#include <QtTest>
#include <QSettings>
#include <QSignalSpy>
#include "MainWindow.h"
#include "shell/ShellGeometry.h"
#include "shell/ShellLayout.h"
#include "shell/SideRail.h"

#include <QBoxLayout>
#include <QLabel>
#include <QStackedWidget>
#include <QTextEdit>
#include <QToolButton>

using spellvision::shell::ShellLayout;
using spellvision::shell::SideRail;
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
        // A MainWindow opens on ui/lastModeId and writes it back. Pinned to Home so the pages the
        // cases below build are known to be unbuilt when they build them -- and saved, because this
        // binary writes the owner's real registry (see the QSettings note in test_sv_style.cpp).
        savedHadMode_ = s.contains(QStringLiteral("ui/lastModeId"));
        savedMode_ = s.value(QStringLiteral("ui/lastModeId")).toString();
        s.setValue(QStringLiteral("ui/lastModeId"), QStringLiteral("home"));
        s.sync();

        // A MainWindow adopts a running ComfyUI and, failing that, STARTS one -- 90 s of GPU on a
        // test run, and a session file overwritten on the way past even when the probe succeeds.
        // Both halves are refused here: an endpoint nothing is listening on so the probe fails
        // fast, and a root that does not exist so comfyRootReady() is false and no launch follows.
        // The worker is deliberately NOT blocked the same way: MainWindow probes 127.0.0.1:8765 and
        // adopts a healthy one, which is the normal state on a dev box, and there is no environment
        // that can make the venv python it would otherwise fall back to unfindable. See the report.
        qputenv("SPELLVISION_COMFY", "C:/spellvision-tests-no-comfy-here");
        qputenv("SPELLVISION_COMFY_PORT", "59187");
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

    // Canvas is not built yet, and the thing it must NOT do on the way past is quietly become
    // Workspaces. It keeps today's shell; what it changes is the cockpit, which is a later task.
    void canvas_keeps_the_shell_it_has_not_changed_yet()
    {
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Workspaces);
        QCoreApplication::processEvents();
        ShellLayout::instance().setLayout(Layout::Canvas);
        QCoreApplication::processEvents();
        QCOMPARE(shellDirection(window), QBoxLayout::LeftToRight);
        QCOMPARE(rail(window)->orientation(), Qt::Vertical);
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
