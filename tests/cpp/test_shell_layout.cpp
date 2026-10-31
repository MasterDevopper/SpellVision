#include <QtTest>
#include <QSettings>
#include <QSignalSpy>
#include "ImageGenerationPage.h"
#include "MainWindow.h"
#include "SettingsPage.h"
#include "shell/FirstRunDialog.h"
#include "shell/LayoutPickerWidget.h"
#include "shell/ProjectRoot.h"
#include "shell/ShellGeometry.h"
#include "shell/ShellLayout.h"
#include "shell/ShellNavigationController.h"
#include "shell/SideRail.h"
#include "style/SvFonts.h"
#include "style/SvStyle.h"
#include "ThemeManager.h"
#include "generation/CockpitInspector.h"
#include "AppEnvironment.h"
#include "ClipScan.h"

#include <QAbstractButton>
#include <QAbstractScrollArea>
#include <QApplication>
#include <QBoxLayout>
#include <QCheckBox>
#include <QDir>
#include <QElapsedTimer>
#include <QFocusEvent>
#include <QFont>
#include <QImage>
#include <QLabel>
#include <QPixmap>
#include <QPoint>
#include <QPointer>
#include <QPushButton>
#include <QRect>
#include <QSet>
#include <QAbstractSpinBox>
#include <QStackedWidget>
#include <QTextEdit>
#include <QToolButton>
#include <QTextDocumentFragment>
#include <QVariant>

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
// ---------------------------------------------------------------------------------------------
// Task 9's measurement tools. Both exist so the wave's success criteria are MEASURED into the spec
// rather than asserted at it.

// scripts/dev/uia/compare_captures.py's comparison, in process, pixel for pixel: the per-channel
// absolute difference, PIL's ITU-R 601-2 luminance of that difference (R*299 + G*587 + B*114, /1000,
// integer), a > 8 threshold, and the fraction of pixels over it. Reproduced rather than invoked so a
// case can gate on it, and cross-checked against the real script on saved PNGs (see the capture-dir
// hook below) so the two are known to agree rather than assumed to.
//
// Offscreen, from QWidget::grab(), NOT from a screen grab. The capture rig photographs a fixed
// 1600x1000 SCREEN region rather than the window, so it also photographs whatever happens to be in
// front of the app -- on a live desktop that has already produced one contaminated pass in this wave.
// A grab is also deterministic: no taskbar clock, so a number means what it says.
qreal changedFraction(const QImage &a, const QImage &b)
{
    if (a.isNull() || b.isNull() || a.size() != b.size())
        return -1.0;
    const QImage x = a.convertToFormat(QImage::Format_RGB32);
    const QImage y = b.convertToFormat(QImage::Format_RGB32);
    qint64 changed = 0;
    for (int row = 0; row < x.height(); ++row)
    {
        const auto *pa = reinterpret_cast<const QRgb *>(x.constScanLine(row));
        const auto *pb = reinterpret_cast<const QRgb *>(y.constScanLine(row));
        for (int col = 0; col < x.width(); ++col)
        {
            const int dr = qAbs(qRed(pa[col]) - qRed(pb[col]));
            const int dg = qAbs(qGreen(pa[col]) - qGreen(pb[col]));
            const int db = qAbs(qBlue(pa[col]) - qBlue(pb[col]));
            if ((dr * 299 + dg * 587 + db * 114) / 1000 > 8)
                ++changed;
        }
    }
    return qreal(changed) / qreal(qint64(x.width()) * qint64(x.height()));
}

// The clipping scanner now lives in ONE place (tests/cpp/ClipScan.h) and the responsive matrix --
// Doc 28's release gate -- asks the same function. It used to carry its own `clippedControls` under
// the same name, gated by a shallow layout check and the stale-minimumSizeHint predicate four wrong
// diagnoses on this branch were spent refuting.
using spellvision::testscan::Offender;
using spellvision::testscan::clippedControls;
using spellvision::testscan::insideScrollArea;
using spellvision::testscan::layoutManagedDeep;
using spellvision::testscan::textOverflowPx;

// Telemetry chips whose SHIPPED text does not fit their SHIPPED ladder width. Measured under the
// bundled IBM Plex Sans (see initTestCase, N2) by driving every rail mode through switchToMode.
// Not fixed here: the ladder and the strings both predate this branch, widening a rung is surface
// work, and wave 4 owns the strip. Two-way -- a label that stops overflowing must be struck out, and
// any label NOT on this list fails the guard the moment it overflows.
// The chips production sets with elide=FALSE, so an overflow is a hard clip rather than an
// ellipsis. Taken from MainWindow::syncBottomTelemetry's own calls -- applyTelemetryText(ready, ...,
// false, false), (page, ..., false, false), (queue, ..., false, false), (state, ..., false, false),
// (eta, ..., false, false) -- plus the backend chip, whose rich text updateBackendHealthLabel sets
// directly. VRAM, Model and LoRA pass elide=true and are therefore already fitted by
// widgets::elideForWidget; measuring them here would report that helper's own margin arithmetic as a
// defect (observed: the model chip reads 1 px over a 238 px box on a long checkpoint name, because
// the helper fits to width - 6 while the contents box is narrower still). This list is a COPY of a
// decision that lives in MainWindow.cpp: flip one of those flags and this guard stops watching that
// chip without saying so.
bool isHardClippingChip(const QString &objectName)
{
    static const QStringList chips = {
        QStringLiteral("BottomReadyLabel"),   QStringLiteral("BottomPageLabel"),
        QStringLiteral("BottomBackendLabel"), QStringLiteral("BottomQueueLabel"),
        QStringLiteral("BottomStateLabel"),   QStringLiteral("BottomEtaLabel"),
    };
    return chips.contains(objectName);
}

struct KnownStripOverflow
{
    const char *objectName;
    const char *text;
    const char *reason;
};

const KnownStripOverflow kKnownStripOverflows[] = {
    // Measured 2026-09-08 under IBM Plex Sans, driving every rail mode through switchToMode. Box
    // widths at 1180 px; the page chip is still over at 1600, where its box is 104.
    //
    // Keyed by the LABEL AND ITS TEXT, not by the label. Keyed by label alone -- which is how this
    // shipped for one run -- a NEW overflow on a label already on the list is invisible: putting
    // Ready's rung back to 48 made "Ready" spill its box by 2 px and this guard stayed silent,
    // because "IMPORTING" had already bought that label a pardon. Only the criterion-4 scan caught
    // it. The pair is the unit that was actually measured, so it is the unit that is excused.
    {"BottomStateLabel", "Workflow import running", "125 px in a 56 px box, same path"},
};

bool isKnownStripOverflow(const QString &objectName, const QString &text)
{
    for (const KnownStripOverflow &known : kKnownStripOverflows)
        if (objectName == QLatin1String(known.objectName) && text == QLatin1String(known.text))
            return true;
    return false;
}

// Controls already squeezed below their own minimum at 1180x760, measured 2026-09-08 on the tree
// this task shipped. Every one of them reads IDENTICALLY in all three layouts, which is what says
// this wave did not cause them -- they are the shell's own pre-existing debt at the size the shell
// itself declares as its minimum, and criterion 4 is recorded as a MISS in the spec's Results table
// because of them rather than as a pass with an asterisk.
//
// Two-way, like tests/cpp/test_responsive_matrix.cpp's knownFailures(): an offender outside these
// three groups fails the case in whichever layout it appears, and a group that stops offending must
// be DELETED here rather than left standing as a permanent excuse.
//
// GROUPS, not a list of object names, and that is a measurement result rather than a convenience:
// the telemetry strip's members are squeezed according to the TEXT they currently hold, and the
// VRAM readout's text changes when the NVML poll lands -- a first run of this case named three
// labels, the next named four. A ratchet keyed to the exact five would have been a coin flip. The
// group is the strip, whose overflow is the actual defect; which of its labels loses the argument on
// a given second is not.
enum class ClipGroup
{
    CentralShell,
    PageStack,
    Unknown,
};

ClipGroup clipGroupOf(const Offender &offender, const QWidget *centralWidget)
{
    if (offender.widget == centralWidget)
        return ClipGroup::CentralShell;
    if (offender.key == QStringLiteral("QStackedWidget(MainPageStack)"))
        return ClipGroup::PageStack;
    // A THIRD group stood here until fix round 1: everything under BottomTelemetryContainer, six
    // labels squeezed under their own text at 1180 px. It was DELETED rather than kept, because the
    // labels were fixed -- the ladder's middle rung now carries each label's own minimum. The
    // two-way check below is what forces that: a group that stops offending has to go, or it becomes
    // a permanent excuse. Anything in the strip that clips again lands in Unknown and fails.
    return ClipGroup::Unknown;
}

const char *clipGroupName(ClipGroup group)
{
    switch (group)
    {
    // MainWindow::centralWidget(): the page stack's minimum, propagated up. Matched by IDENTITY, not
    // by the key "QWidget(-)", which would pardon every unnamed QWidget in the shell.
    case ClipGroup::CentralShell:   return "centralShell";
    // A QStackedWidget's minimum is the MAXIMUM over every page ever added, and this binary visits
    // all 16 rail modes. InspirationPage's own minimum is 953x1209 and DatasetGenerationPage's is
    // 360x977, both taller than the 760 the shell declares. Real in the app too, once the user has
    // visited either page.
    case ClipGroup::PageStack:      return "MainPageStack";
    case ClipGroup::Unknown:        break;
    }
    return "unknown";
}

// Pump until every child's geometry stops moving, or the budget runs out -- the responsive matrix's
// lesson, and it is the same one here: a flat wait makes a gate's verdict depend on how busy the box
// is, and a widget still being laid out reports a size indistinguishable from a squeezed one.
void settle(QWidget *root, int budgetMs = 2500)
{
    auto sample = [root]() {
        QString state;
        for (const QWidget *w : root->findChildren<QWidget *>())
        {
            const QRect g = w->geometry();
            state += QStringLiteral("%1,%2,%3,%4,%5;").arg(g.x()).arg(g.y())
                         .arg(g.width()).arg(g.height()).arg(w->isVisible() ? 1 : 0);
        }
        return state;
    };
    QString previous = sample();
    QElapsedTimer timer;
    timer.start();
    while (timer.elapsed() < budgetMs)
    {
        QTest::qWait(30);
        const QString current = sample();
        if (current == previous)
            return;
        previous = current;
    }
}

// A QPushButton by the text it carries. kit::button() gives both of the dialog's primaries the
// object name "PrimaryButton" -- it is the QSS selector, shared on purpose and not renameable -- so
// the text is what distinguishes Next from Continue, the same disambiguation the cockpit's hero
// button already needs.
QPushButton *buttonWithText(QWidget *root, const QString &text)
{
    for (QPushButton *button : root->findChildren<QPushButton *>())
        if (button->text() == text)
            return button;
    return nullptr;
}

// A laid-out item's NATURAL height at the width it currently has.
//
// Two deliberate choices, both of which were wrong in the first draft of this helper and were caught
// by the anchor reading a constant +67 px in BOTH hosts -- a bias the comparison would have absorbed
// silently while the number underneath meant nothing:
//
//   * A word-wrapped QLabel is asked heightForWidth(), never sizeHint(). sizeHint() answers
//     sizeForWidth(-1) -- a question about a width the label does not have -- and it is served out
//     of the `valid_hints` cache that broke four diagnoses on this branch. heightForWidth()
//     recomputes from the live width every call. It is reached through QLabel rather than through
//     QWidget::hasHeightForWidth(), which is a SIZE-POLICY flag a word-wrapped label does not
//     necessarily carry; asking the policy falls through to the cached hint for exactly the widget
//     this measurement is about.
//   * Everything else is asked through its LAYOUT ITEM, not the widget. QWidget::sizeHint() is
//     (-1, -1) for a plain QWidget that overrides nothing -- which is what LayoutThumbnail is, with
//     its 64 px set by setFixedHeight -- so a widget-side read scored the card's diagram as -1 px of
//     content. QWidgetItem::sizeHint() bounds the hint by the widget's min/max, so a fixed height
//     comes back as itself.
int naturalHeightOf(QLayoutItem *item)
{
    QWidget *w = item->widget();
    if (auto *label = qobject_cast<QLabel *>(w))
        if (label->wordWrap() && label->width() > 0)
            return label->heightForWidth(label->width());
    return item->sizeHint().height();
}

// How much taller a layout-picker card is than the content inside it: its real height minus the
// column's margins, spacings and its children's natural heights. Zero means the card is exactly as
// tall as what it holds; a large number means a host handed the card surplus height and the card had
// to put it somewhere -- which, with a stretch on the description label, becomes blank bands inside
// the card rather than blank space under the picker.
//
// -1 when the card cannot be measured at all, so a caller cannot read "no cards found" as "dense".
int cardSurplusPx(QWidget *card)
{
    QLayout *column = card ? card->layout() : nullptr;
    if (!column || card->height() <= 0)
        return -1;
    const QMargins m = column->contentsMargins();
    int natural = m.top() + m.bottom();
    int items = 0;
    for (int i = 0; i < column->count(); ++i)
    {
        QLayoutItem *item = column->itemAt(i);
        QWidget *w = item->widget();
        if (!w || w->isHidden())
            continue;
        natural += naturalHeightOf(item);
        ++items;
    }
    if (items == 0)
        return -1;
    if (items > 1)
        natural += column->spacing() * (items - 1);
    return card->height() - natural;
}

// The worst surplus over a picker's three cards, and which card carries it. Worst rather than mean:
// one stretched card is one stretched card, and averaging it against two dense ones would dilute
// exactly the signal this measures.
int worstCardSurplus(QWidget *picker, QString *worstCard, QString *report)
{
    int worst = -1;
    QStringList lines;
    for (const char *name : {"LayoutCard_Instrument", "LayoutCard_Canvas", "LayoutCard_Workspaces"})
    {
        QWidget *card = picker ? picker->findChild<QWidget *>(QString::fromLatin1(name)) : nullptr;
        const int surplus = cardSurplusPx(card);
        if (surplus < 0)
            continue;
        lines << QStringLiteral("%1 %2px tall, %3px surplus")
                     .arg(QString::fromLatin1(name)).arg(card->height()).arg(surplus);
        if (surplus > worst)
        {
            worst = surplus;
            if (worstCard)
                *worstCard = QString::fromLatin1(name);
        }
    }
    if (report)
        *report = lines.join(QStringLiteral("; "));
    return worst;
}
} // namespace

class TestShellLayout : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase()
    {
        // THE ENVIRONMENT main.cpp BUILDS BEFORE ANY WIDGET EXISTS: the SvStyle install (task 8
        // R3), the bundled IBM Plex faces at main.cpp's own 12 px (task 9 N2) and the themed
        // application palette + overlay sheet (final review, I1). All three were separately absent
        // from this binary, each was found by tripping over it, and each meant every measurement
        // here was quietly about a different program. They live in ONE function now
        // (tests/cpp/AppEnvironment.h, which records what each cost) so a fourth member is fixed in
        // every C++ test at once rather than wherever somebody happens to be standing.
        const QStringList bundled = spellvision::testenv::applyShippedAppEnvironment();
        qInfo("FIXR2-FONT application font is %s (bundled: %s)",
              qPrintable(QApplication::font().family()), qPrintable(bundled.join(QStringLiteral(", "))));

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

        // A FirstRunDialog's accept path runs persistFolders(), and RuntimeProfile::save() writes
        // four runtime/* values. On this machine the runtime group does not exist at all, while
        // RuntimeProfile::load() RESOLVES a Comfy root and a python from the environment -- so an
        // accepted dialog in a test would CREATE settings the owner never had, and a later run would
        // then read a pinned root instead of resolving one. The dialog also touches
        // image_generation/output_folder. setup/firstRunWizard_v1 is here because it GATES the
        // dialog in the shipped app: a test that tripped it would change what the owner sees at
        // next launch, so it is saved even though nothing below writes it.
        for (const QString &key : dialogWrittenKeys())
            savedDialogKeys_.append({key, s.contains(key) ? s.value(key) : QVariant()});
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

    // Fix round 2, M2: the thumbnail's own backdrop moved from Surface1/radiusCard() (the SAME
    // recipe the card it sits inside already uses -- no contrast at all) to the Inset recipe
    // (Surface0 -- SvStyle.cpp's paintSurface, corroborated by the numbers below). ThemeManager is
    // the EXTERNAL anchor: the sampled pixel is compared against both candidate tokens, neither of
    // which this test computes itself, so a plant that reverts the fill is a claim about a real
    // colour rather than about this test's own arithmetic.
    //
    // Measured under the live preset (Ivory Holograph / Hybrid) while building this case: Surface0
    // #eef2f9 (lum 241.655), Surface1 #f7faff (lum 249.723) -- 8.07 luminance levels apart, which is
    // the whole budget this comparison has to work with. The rendered plate came back #eef2f9
    // exactly: 0 from Surface0, 8.07 from Surface1. Floor set at 4.0 -- half that budget -- so the
    // assertion needs a real majority separation, not a rounding-level nudge, while still being
    // comfortably inside what the two tokens actually allow.
    //
    // Workspaces is the ACTIVE layout here, not Instrument: sampling Instrument's OWN thumbnail
    // while Instrument is selected would land on the AccentSubtle-tinted fill, a third colour this
    // case is not about. Reading Instrument's thumbnail while a DIFFERENT layout is selected samples
    // its plain, untinted backdrop -- the one M2 actually describes.
    void the_thumbnail_s_plate_reads_nearer_surface0_than_surface1()
    {
        ShellLayout::instance().setLayout(Layout::Workspaces);

        LayoutPickerWidget picker;
        picker.setAttribute(Qt::WA_DontShowOnScreen);
        picker.resize(720, 220);
        picker.show();
        QCoreApplication::processEvents();

        QWidget *instrumentThumb = thumbnailOf(picker, QStringLiteral("LayoutCard_Instrument"));
        QVERIFY(instrumentThumb);

        const QImage img = instrumentThumb->grab().toImage();
        const int y = instrumentThumb->height() / 2;
        const QColor plate = img.pixelColor(img.width() / 2, y);

        const ThemeManager &t = ThemeManager::instance();
        const qreal toSurface0 = qAbs(luminance(plate) - luminance(t.color(ThemeManager::Color::Surface0)));
        const qreal toSurface1 = qAbs(luminance(plate) - luminance(t.color(ThemeManager::Color::Surface1)));
        const qreal floor = 4.0;

        QVERIFY2(toSurface1 - toSurface0 >= floor,
                 qPrintable(QStringLiteral("plate %1 sits %2 from Surface0 and %3 from Surface1 -- "
                                           "not clearly nearer Surface0 (floor %4)")
                                .arg(plate.name()).arg(toSurface0, 0, 'f', 2).arg(toSurface1, 0, 'f', 2)
                                .arg(floor, 0, 'f', 2)));

        ShellLayout::instance().setLayout(Layout::Instrument);
    }

    // I1: keyboard reachability, proven end to end rather than as a property check alone. focusPolicy
    // and accessibleName are cheap premises -- a screen reader or a Tab press needs both -- but the
    // assertion that actually matters is what a Space press does to the REAL singleton, delivered
    // straight to the card (QTest::keyClick targets the widget directly, bypassing whatever the
    // window's current focus happens to be, which is what makes this reach the same keyPressEvent a
    // real Tab-then-Space would).
    void a_card_is_keyboard_reachable_and_space_picks_it()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);

        LayoutPickerWidget picker;
        picker.setAttribute(Qt::WA_DontShowOnScreen);
        picker.resize(720, 220);
        picker.show();
        QCoreApplication::processEvents();

        const QStringList cardNames = {
            QStringLiteral("LayoutCard_Instrument"),
            QStringLiteral("LayoutCard_Canvas"),
            QStringLiteral("LayoutCard_Workspaces"),
        };
        for (const QString &name : cardNames)
        {
            QWidget *card = picker.findChild<QWidget *>(name);
            QVERIFY2(card, qPrintable(name));
            QVERIFY2(card->focusPolicy() != Qt::NoFocus,
                     qPrintable(QStringLiteral("%1 has no focus policy -- unreachable by Tab").arg(name)));
            QVERIFY2(!card->accessibleName().isEmpty(),
                     qPrintable(QStringLiteral("%1 has no accessible name").arg(name)));
        }

        QWidget *canvasCard = picker.findChild<QWidget *>(QStringLiteral("LayoutCard_Canvas"));
        QVERIFY(canvasCard);
        QTest::keyClick(canvasCard, Qt::Key_Space);
        QCoreApplication::processEvents();
        QCOMPARE(ShellLayout::instance().layout(), Layout::Canvas);

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


    // ============================================================================================
    // Task 9, step 1: the layout is the first thing the app asks.
    // ============================================================================================

    // ORDER, and exclusivity in BOTH directions. "Page 0 contains a picker" alone would pass a
    // dialog that put the picker and the checklist on the same page and left page 1 empty, and
    // "page 1 contains the checklist" alone would pass one that showed both everywhere -- so each
    // page is asked what it holds AND what it does not, and the dialog is asked which one it opens
    // on. currentPageIndex() is read rather than a QSettings key because in Deferred mode there IS
    // no setting yet, which is the point of the mode.
    void first_run_asks_for_a_layout_before_it_asks_about_the_machine()
    {
        spellvision::shell::FirstRunDialog dialog(spellvision::shell::resolveProjectRoot());
        dialog.setAttribute(Qt::WA_DontShowOnScreen);

        auto *pages = dialog.findChild<QStackedWidget *>(QStringLiteral("FirstRunPages"));
        QVERIFY2(pages, "the dialog is not a QStackedWidget named FirstRunPages");
        QCOMPARE(pages->count(), 2);
        QCOMPARE(dialog.currentPageIndex(), 0);

        QWidget *first = pages->widget(0);
        QWidget *second = pages->widget(1);
        QVERIFY(first && second);

        QVERIFY2(first->findChild<LayoutPickerWidget *>(), "page 0 carries no layout picker");
        QVERIFY2(!first->findChild<QFrame *>(QStringLiteral("FirstRunCheckRow")),
                 "page 0 carries the environment checklist as well -- the picker is not a page of "
                 "its own, so nothing puts it BEFORE the checklist");
        QVERIFY2(second->findChild<QFrame *>(QStringLiteral("FirstRunCheckRow")),
                 "page 1 carries no environment checklist");
        QVERIFY2(!second->findChild<LayoutPickerWidget *>(),
                 "page 1 carries the picker too -- the two surfaces are not in the order the spec "
                 "fixes");

        // The picker on page 0 is the SAME widget Settings hosts, in the one mode that makes
        // dismissal safe. Read off the widget rather than off the source text.
        auto *picker = first->findChild<LayoutPickerWidget *>();
        QCOMPARE(picker->commitMode(), LayoutPickerWidget::CommitMode::Deferred);

        // The gate and the suppression checkbox are unchanged (task 9 brief, step 1).
        QVERIFY2(dialog.findChild<QCheckBox *>(), "the suppression checkbox is gone");
        QVERIFY2(buttonWithText(&dialog, QStringLiteral("Next")), "no way forward from page 0");
        // Next reaches the checklist, Back comes home.
        QTest::mouseClick(buttonWithText(&dialog, QStringLiteral("Next")), Qt::LeftButton);
        QCOMPARE(dialog.currentPageIndex(), 1);
        QTest::mouseClick(buttonWithText(&dialog, QStringLiteral("Back")), Qt::LeftButton);
        QCOMPARE(dialog.currentPageIndex(), 0);
    }

    // SPEC 2.7's PROMISE, as a property. A user who picks a card and then closes the dialog keeps
    // what they had. The premise is asserted first and separately: the pick REGISTERED on the
    // widget. Without it a dialog whose picker was inert -- disconnected cards, a dead reportPick --
    // would satisfy "the layout did not change" perfectly, and the case would be green for the
    // opposite of the reason it exists.
    //
    // Anchored outside ShellLayout on the way out: the raw QSettings value is read back too, so a
    // singleton that held Instrument in memory while having already written a 1 to the store is
    // caught. That store IS the thing that survives the restart criterion 1 is about.
    void dismissing_first_run_keeps_the_layout_nobody_confirmed()
    {
        // Through Canvas, so ui/shellLayout is PRESENT and holds 0 before the dialog opens. Fix
        // round 1, M1: a plain setLayout(Instrument) is a no-op when Instrument is already current,
        // the key can then be absent entirely, and `value(key, 0).toInt() == 0` is satisfied by the
        // DEFAULT -- an assertion that cannot fail is not an assertion. The presence of the key is
        // asserted below as a premise, so the two readings that follow are readings of a real value.
        ShellLayout::instance().setLayout(Layout::Canvas);
        ShellLayout::instance().setLayout(Layout::Instrument);
        {
            QSettings seeded(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
            QVERIFY2(seeded.contains(QStringLiteral("ui/shellLayout")),
                     "ui/shellLayout is absent, so the store assertions below would pass on their "
                     "own default rather than on anything the dialog did");
        }

        spellvision::shell::FirstRunDialog dialog(spellvision::shell::resolveProjectRoot());
        dialog.setAttribute(Qt::WA_DontShowOnScreen);
        dialog.show();
        QCoreApplication::processEvents();

        auto *picker = dialog.findChild<LayoutPickerWidget *>();
        QVERIFY(picker);
        QWidget *canvasCard = picker->findChild<QWidget *>(QStringLiteral("LayoutCard_Canvas"));
        QVERIFY(canvasCard);
        QTest::mouseClick(canvasCard, Qt::LeftButton);
        QCoreApplication::processEvents();

        QVERIFY2(picker->selectedLayout() == Layout::Canvas,
                 "the click never reached the picker -- everything below would pass for the wrong "
                 "reason");
        QCOMPARE(ShellLayout::instance().layout(), Layout::Instrument);
        QSettings store(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        QCOMPARE(store.value(QStringLiteral("ui/shellLayout")).toInt(),
                 static_cast<int>(Layout::Instrument));

        dialog.reject();
        QCoreApplication::processEvents();
        QCOMPARE(ShellLayout::instance().layout(), Layout::Instrument);
        QSettings after(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        QCOMPARE(after.value(QStringLiteral("ui/shellLayout")).toInt(),
                 static_cast<int>(Layout::Instrument));
    }

    // THE OTHER HALF: accepting commits. The intermediate assertion is what makes this case catch
    // BOTH of the defects it is written for -- a picker left in Immediate mode fails on the line
    // before the accept, and an accept path that never calls commitSelection() fails on the line
    // after it. One without the other would leave one of the two invisible.
    void accepting_first_run_commits_the_layout_it_showed()
    {
        ShellLayout::instance().setLayout(Layout::Instrument);

        spellvision::shell::FirstRunDialog dialog(spellvision::shell::resolveProjectRoot());
        dialog.setAttribute(Qt::WA_DontShowOnScreen);
        dialog.show();
        QCoreApplication::processEvents();

        auto *picker = dialog.findChild<LayoutPickerWidget *>();
        QVERIFY(picker);
        QWidget *card = picker->findChild<QWidget *>(QStringLiteral("LayoutCard_Workspaces"));
        QVERIFY(card);
        QTest::mouseClick(card, Qt::LeftButton);
        QCoreApplication::processEvents();
        QCOMPARE(picker->selectedLayout(), Layout::Workspaces);
        QVERIFY2(ShellLayout::instance().layout() == Layout::Instrument,
                 "the pick reached the real setting before the user accepted anything -- the picker "
                 "is not Deferred, and closing the dialog now would strand a layout nobody confirmed");

        QPushButton *next = buttonWithText(&dialog, QStringLiteral("Next"));
        QVERIFY(next);
        QTest::mouseClick(next, Qt::LeftButton);
        QCOMPARE(dialog.currentPageIndex(), 1);

        // Either wording of the hero, whichever this machine's readiness produced.
        QPushButton *finish = buttonWithText(&dialog, QStringLiteral("Start creating"));
        if (!finish)
            finish = buttonWithText(&dialog, QStringLiteral("Continue in limited mode"));
        QVERIFY2(finish, "neither wording of the continue button is on the checklist page");
        QTest::mouseClick(finish, Qt::LeftButton);
        QCoreApplication::processEvents();

        QCOMPARE(dialog.result(), int(QDialog::Accepted));
        QCOMPARE(dialog.action(), spellvision::shell::FirstRunDialog::Action::Continue);
        QCOMPARE(ShellLayout::instance().layout(), Layout::Workspaces);
        QSettings store(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        QCOMPARE(store.value(QStringLiteral("ui/shellLayout")).toInt(),
                 static_cast<int>(Layout::Workspaces));

        ShellLayout::instance().setLayout(Layout::Instrument);
    }

    // ============================================================================================
    // Task 9, step 2: the wave's success criteria, measured.
    // ============================================================================================

    // CRITERION 2, second half, taken as far as a suite without a GPU can take it. "Switching while a
    // job runs does not interrupt it" needs a real job to be literally true, and this binary starts
    // no runtime on purpose (SPELLVISION_NO_RUNTIME_LAUNCH, initTestCase). What it CAN prove is the
    // MECHANISM by which a switch would interrupt one: the cockpit's in-flight state lives on the
    // page, and a switch that rebuilt or reset the page would drop it. So the page is put into its
    // busy state through the same entry point the worker's telemetry uses -- ImageGenerationPage::
    // setBusy -- and the state is read back after a full trip around all three layouts and home.
    //
    // The PREMISE is asserted first and separately: busy has to have changed something observable, or
    // "unchanged after the switch" is a statement about a page that was never busy to begin with --
    // the tautology this wave has already produced four of.
    void a_layout_switch_does_not_interrupt_a_page_that_is_mid_job()
    {
        MainWindow &window = mainWindow();
        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
        auto *cockpit = qobject_cast<ImageGenerationPage *>(t2iPage(window));
        QVERIFY(cockpit);

        QTextEdit *prompt = cockpit->findChild<QTextEdit *>(QStringLiteral("PromptEditor"));
        QVERIFY(prompt);
        prompt->setPlainText(QStringLiteral("a lighthouse in a storm"));

        auto secondaryStates = [cockpit]() {
            QList<bool> states;
            for (QPushButton *button :
                 cockpit->findChildren<QPushButton *>(QStringLiteral("TertiaryActionButton")))
                states << button->isEnabled();
            return states;
        };
        QWidget *generate = generateButton(cockpit);
        QVERIFY(generate);

        const QList<bool> idleSecondary = secondaryStates();
        const bool idleGenerate = generate->isEnabled();
        QVERIFY(!idleSecondary.isEmpty());

        cockpit->setBusy(true, QStringLiteral("Rendering 3/20"));
        QCoreApplication::processEvents();
        const QList<bool> busySecondary = secondaryStates();
        const bool busyGenerate = generate->isEnabled();
        QVERIFY2(busySecondary != idleSecondary || busyGenerate != idleGenerate,
                 "setBusy(true) changed nothing this case can see, so everything below would be a "
                 "statement about a page that was never busy");

        for (Layout layout : {Layout::Canvas, Layout::Workspaces, Layout::Instrument})
        {
            ShellLayout::instance().setLayout(layout);
            QCoreApplication::processEvents();
            const QString name = ShellLayout::instance().layoutNames().at(static_cast<int>(layout));
            QVERIFY2(qobject_cast<ImageGenerationPage *>(window.currentPageForTest()) == cockpit,
                     qPrintable(QStringLiteral("%1 replaced the page that was mid-job").arg(name)));
            QVERIFY2(secondaryStates() == busySecondary,
                     qPrintable(QStringLiteral("%1 released the controls a running job had locked")
                                    .arg(name)));
            QVERIFY2(generate->isEnabled() == busyGenerate,
                     qPrintable(QStringLiteral("%1 re-armed Generate under a running job").arg(name)));
            QCOMPARE(prompt->toPlainText(), QStringLiteral("a lighthouse in a storm"));
        }

        cockpit->setBusy(false);
        QCoreApplication::processEvents();
        QCOMPARE(secondaryStates(), idleSecondary);
    }

    // ============================================================================================
    // Task 9 fix round 1.
    // ============================================================================================

    // REQUIRED 1. The card and its own diagram have to agree about what is selected.
    //
    // They did not, and only in Deferred mode: LayoutCard::selected() asked the picker while
    // LayoutThumbnail::paintEvent asked ShellLayout::instance() directly, so in the ONE mode where
    // those two readings differ -- the mode the first-run dialog sets -- the Canvas card was framed
    // as chosen while the Instrument card's diagram kept the accent tint. Six plants walked past it
    // because every one of them exercised Immediate mode, where the two readings coincide.
    //
    // ANCHORED OUTSIDE THE MODE UNDER TEST. The floor is not a constant I chose: the same click is
    // performed first on an IMMEDIATE picker, whose thumbnail was never broken, and the Deferred
    // thumbnail is required to move at least half as far as the Immediate one did. A number the
    // defective code cannot produce (it moved 0.0000) and that a future repaint change cannot
    // silently erode, because both sides move together.
    void a_thumbnail_shows_the_same_pick_its_card_does_in_deferred_mode()
    {
        auto clickCanvasAndMeasure = [this](LayoutPickerWidget::CommitMode mode,
                                            qreal *cardMove, qreal *thumbMove, qreal *otherThumbMove) {
            ShellLayout::instance().setLayout(Layout::Instrument);

            LayoutPickerWidget picker;
            picker.setCommitMode(mode);
            picker.setAttribute(Qt::WA_DontShowOnScreen);
            picker.resize(720, 220);
            picker.show();
            QCoreApplication::processEvents();

            QWidget *canvasCard = picker.findChild<QWidget *>(QStringLiteral("LayoutCard_Canvas"));
            QWidget *canvasThumb = thumbnailOf(picker, QStringLiteral("LayoutCard_Canvas"));
            QWidget *instrumentThumb = thumbnailOf(picker, QStringLiteral("LayoutCard_Instrument"));
            QVERIFY(canvasCard && canvasThumb && instrumentThumb);

            const QImage cardBefore = canvasCard->grab().toImage();
            const QImage thumbBefore = canvasThumb->grab().toImage();
            const QImage otherBefore = instrumentThumb->grab().toImage();

            QTest::mouseClick(canvasCard, Qt::LeftButton);
            QCoreApplication::processEvents();

            *cardMove = changedFraction(cardBefore, canvasCard->grab().toImage());
            *thumbMove = changedFraction(thumbBefore, canvasThumb->grab().toImage());
            *otherThumbMove = changedFraction(otherBefore, instrumentThumb->grab().toImage());
        };

        qreal immediateCard = 0, immediateThumb = 0, immediateOther = 0;
        clickCanvasAndMeasure(LayoutPickerWidget::CommitMode::Immediate,
                              &immediateCard, &immediateThumb, &immediateOther);
        ShellLayout::instance().setLayout(Layout::Instrument);

        qreal deferredCard = 0, deferredThumb = 0, deferredOther = 0;
        clickCanvasAndMeasure(LayoutPickerWidget::CommitMode::Deferred,
                              &deferredCard, &deferredThumb, &deferredOther);

        qInfo("FIXR1-THUMB immediate card %.4f thumb %.4f other-thumb %.4f",
              immediateCard, immediateThumb, immediateOther);
        qInfo("FIXR1-THUMB deferred  card %.4f thumb %.4f other-thumb %.4f",
              deferredCard, deferredThumb, deferredOther);

        // Premises, so a picker that rendered nothing at all cannot pass by standing still.
        QVERIFY2(immediateThumb > 0.05,
                 qPrintable(QStringLiteral("the Immediate thumbnail did not move either (%1) -- "
                                           "this case has no working reference to compare against")
                                .arg(immediateThumb, 0, 'f', 4)));
        QVERIFY2(deferredCard > 0.05,
                 qPrintable(QStringLiteral("the Deferred CARD did not move (%1); the click never "
                                           "landed, so the thumbnail assertion below would be about "
                                           "nothing").arg(deferredCard, 0, 'f', 4)));

        QVERIFY2(deferredThumb >= immediateThumb * 0.5,
                 qPrintable(QStringLiteral("the picked card's DIAGRAM moved %1 in Deferred mode "
                                           "against %2 in Immediate -- the thumbnail is reading a "
                                           "different selection from the card that frames it")
                                .arg(deferredThumb, 0, 'f', 4).arg(immediateThumb, 0, 'f', 4)));
        QVERIFY2(deferredOther >= immediateOther * 0.5,
                 qPrintable(QStringLiteral("the DESELECTED card's diagram moved %1 in Deferred mode "
                                           "against %2 in Immediate -- it is still wearing the tint "
                                           "of a selection the user has moved off")
                                .arg(deferredOther, 0, 'f', 4).arg(immediateOther, 0, 'f', 4)));

        ShellLayout::instance().setLayout(Layout::Instrument);
    }

    // I1. The window must not flinch at the first thing the user does in the app. The dialog was
    // 33 px shorter on the layout page because the suppression checkbox is hidden there, so pressing
    // Next grew it. Premises first: the page really turned, and the checkbox's visibility really
    // changed -- otherwise "the height did not move" is a fact about a dialog that did nothing.
    void the_first_run_dialog_keeps_its_height_across_its_pages()
    {
        spellvision::shell::FirstRunDialog dialog(spellvision::shell::resolveProjectRoot());
        dialog.setAttribute(Qt::WA_DontShowOnScreen);
        dialog.show();
        QCoreApplication::processEvents();
        settle(&dialog, 1200);

        QCheckBox *suppress = dialog.findChild<QCheckBox *>();
        QVERIFY(suppress);
        const bool suppressVisibleOnPageZero = suppress->isVisible();
        const QSize onLayoutPage = dialog.size();
        QCOMPARE(dialog.currentPageIndex(), 0);

        QPushButton *next = buttonWithText(&dialog, QStringLiteral("Next"));
        QVERIFY(next);
        QTest::mouseClick(next, Qt::LeftButton);
        QCoreApplication::processEvents();
        settle(&dialog, 1200);

        QCOMPARE(dialog.currentPageIndex(), 1);
        QVERIFY2(suppress->isVisible() != suppressVisibleOnPageZero,
                 "the suppression checkbox did not change visibility between the pages, so this "
                 "case is not measuring the transition it was written for");
        const QSize onChecklistPage = dialog.size();
        qInfo("FIXR1-HEIGHT layout page %dx%d, checklist page %dx%d",
              onLayoutPage.width(), onLayoutPage.height(),
              onChecklistPage.width(), onChecklistPage.height());
        QVERIFY2(onChecklistPage.height() == onLayoutPage.height(),
                 qPrintable(QStringLiteral("the dialog jumped from %1 px tall to %2 px when Next was "
                                           "pressed").arg(onLayoutPage.height()).arg(onChecklistPage.height())));
    }

    // R1's guard, and the case above is the reason it is needed: that one asserts the dialog's
    // height is STABLE across its pages, and NOTHING in this file asserted the height is USED. Page 0
    // handed all ~385 px of the stack's surplus to the picker (stretch 1, no addStretch of its own),
    // the picker handed it to the cards, and the description label's own stretch split it into a
    // ~195 px void above the description and a ~190 px void below -- 72 % of a 535 px card, on the
    // first screen of the app, under fifty passing cases.
    //
    // ANCHORED OUTSIDE THE CODE UNDER TEST. The threshold is not a number chosen here: it is the
    // SAME WIDGET measured in its other host, SettingsPage, where it is correct and has always been
    // correct. That is what makes this an assertion about the dialog rather than about a constant --
    // if the shared widget itself later starts padding its cards, the anchor moves with it and this
    // case keeps asking the only question worth asking: is the first-run copy of the picker as dense
    // as the Settings copy? The two hosts are different widths, so the measure is surplus over
    // NATURAL content height at the live width, not raw card height.
    void the_first_run_cards_are_as_dense_as_the_settings_cards()
    {
        SettingsPage page;
        page.setAttribute(Qt::WA_DontShowOnScreen);
        page.resize(900, 760);
        page.show();
        QCoreApplication::processEvents();
        settle(&page, 1200);

        auto *settingsPicker = page.findChild<LayoutPickerWidget *>(QStringLiteral("LayoutPickerWidget"));
        QVERIFY2(settingsPicker, "SettingsPage has no LayoutPickerWidget -- the anchor is gone");
        QString settingsWorstCard;
        QString settingsReport;
        const int settingsSurplus = worstCardSurplus(settingsPicker, &settingsWorstCard, &settingsReport);
        QVERIFY2(settingsSurplus >= 0,
                 qPrintable(QStringLiteral("no Settings card could be measured (%1) -- an unmeasurable "
                                           "anchor would let this case pass for the wrong reason")
                                .arg(settingsReport)));

        spellvision::shell::FirstRunDialog dialog(spellvision::shell::resolveProjectRoot());
        dialog.setAttribute(Qt::WA_DontShowOnScreen);
        dialog.show();
        QCoreApplication::processEvents();
        settle(&dialog, 1200);
        QCOMPARE(dialog.currentPageIndex(), 0);

        auto *dialogPicker = dialog.findChild<LayoutPickerWidget *>();
        QVERIFY2(dialogPicker, "the first-run dialog has no LayoutPickerWidget on page 0");
        QString dialogWorstCard;
        QString dialogReport;
        const int dialogSurplus = worstCardSurplus(dialogPicker, &dialogWorstCard, &dialogReport);
        QVERIFY2(dialogSurplus >= 0,
                 qPrintable(QStringLiteral("no first-run card could be measured (%1)").arg(dialogReport)));

        qInfo("R1-DENSITY settings[%s] worst %s +%dpx | first-run[%s] worst %s +%dpx",
              qPrintable(settingsReport), qPrintable(settingsWorstCard), settingsSurplus,
              qPrintable(dialogReport), qPrintable(dialogWorstCard), dialogSurplus);

        // The premise: both pickers really laid out. A hidden or zero-height picker would report a
        // surplus of nothing at all and pass this on an empty measurement.
        QVERIFY2(settingsPicker->height() > 64 && dialogPicker->height() > 64,
                 qPrintable(QStringLiteral("a picker never laid out: settings %1px, first-run %2px")
                                .arg(settingsPicker->height()).arg(dialogPicker->height())));

        // The two hosts wrap the descriptions to different line counts, so the taller card in a row
        // can legitimately leave the shorter ones a line or two of slack. kDensitySlackPx is that,
        // and it is nowhere near what the defect costs: measured 2 px in both hosts with the fix,
        // and the mutation (the picker put back to stretch 1, FirstRunDialog.cpp recompiled) reports
        // 347 px against the same 2 px anchor, on a card grown from 189 px to 534 px.
        constexpr int kDensitySlackPx = 48;
        QVERIFY2(dialogSurplus <= settingsSurplus + kDensitySlackPx,
                 qPrintable(QStringLiteral("the first-run card %1 is %2 px taller than its content, "
                                           "against %3 px for the same widget's worst card in Settings "
                                           "(%4). Page 0 is handing the picker surplus height that "
                                           "ends up as blank bands INSIDE the cards; give the picker "
                                           "stretch 0 and the column an addStretch of its own. "
                                           "settings: %5 | first-run: %6")
                                .arg(dialogWorstCard).arg(dialogSurplus).arg(settingsSurplus)
                                .arg(settingsWorstCard, settingsReport, dialogReport)));
    }

    // N2's guard. Every text measurement in this binary is only worth the typeface it was taken in,
    // and this binary measured SEGOE UI for its whole life because registerBundledFonts() is called
    // in main.cpp and nowhere else -- the same shape as the SvStyle defect fix round 1 of task 8
    // found, one layer down. It is not academic: "Ready" advances 32 px under Segoe against 34 under
    // Plex, in a 34 px box.
    //
    // Anchored outside initTestCase: the expected family comes from QFontDatabase, through
    // registerBundledFonts(), not from a literal this case and the harness both spell. If the
    // bundle genuinely cannot be found -- a stripped build tree -- the case says so and skips the
    // comparison rather than asserting a font that is not there.
    void the_suite_measures_the_typeface_the_app_ships()
    {
        const QStringList bundled = spellvision::style::registerBundledFonts();
        QVERIFY2(bundled.contains(QStringLiteral("IBM Plex Sans")),
                 qPrintable(QStringLiteral("the bundled faces did not register from %1; every text "
                                           "measurement in this binary is in the wrong typeface")
                                .arg(spellvision::style::fontsDirectory())));
        QCOMPARE(QApplication::font().family(), QStringLiteral("IBM Plex Sans"));
        // main.cpp pins the size too; a different one here would be a third program again.
        QCOMPARE(QApplication::font().pixelSize(), 12);

        // And the strip's own chips wear it, not just qApp -- ThemeManager::numericFont() derives
        // from font(Type::Body), so a chip could in principle be set from somewhere else entirely.
        MainWindow &window = mainWindow();
        QLabel *ready = window.findChild<QLabel *>(QStringLiteral("BottomReadyLabel"));
        QVERIFY(ready);
        QCOMPARE(ready->font().family(), QStringLiteral("IBM Plex Sans"));
    }

    // REQUIRED 2 / N1. What the strip shows, not what it happens to be holding.
    //
    // The first version of this guard measured ONE text per label -- whatever the bar had at the
    // moment it ran -- and so could not see the widest string the strip actually displays. The page
    // chip alone carries a different string for each of the 16 rail modes. It now drives every mode
    // through switchToMode at every rung the window can reach, and additionally measures the two
    // strings the workflow-import path writes straight onto the Ready and State chips.
    //
    // The predicate is horizontalAdvance(text) against contentsRect().width(): both independent of
    // the widget's width, which a scan built on QLabel::minimumSizeHint() is not -- not because the
    // hint is wrong, but because setFixedWidth does not clear QWidget's valid_hints, so a scan that
    // resizes first reads the PREVIOUS rung's cached answer (see textOverflowPx).
    //
    // The overflows this finds are NOT fixed here and are NOT this wave's: they are the shipped
    // ladder meeting the shipped strings, they predate the branch, and wave 4 owns the strip. They
    // are recorded two-way, so a NEW label joining them fails immediately and a label that stops
    // overflowing has to be struck out rather than left standing as an excuse.
    //
    // MainWindow::setMinimumSize is 1180x760, so the ladder's `tight` rung (< 1100 px) is unreachable
    // through the shell and is NOT covered.
    void the_telemetry_strip_fits_the_text_it_actually_shows()
    {
        MainWindow &window = mainWindow();
        const QSize before = window.size();

        QSet<QString> overflowing;
        QStringList unexpected;
        int readings = 0;

        auto scan = [&](int rung, const QString &context) {
            QWidget *strip = window.findChild<QWidget *>(QStringLiteral("BottomTelemetryContainer"));
            if (!strip)
                return;
            for (QLabel *label : strip->findChildren<QLabel *>())
            {
                if (!label->isVisible() || label->text().trimmed().isEmpty())
                    continue;
                if (!isHardClippingChip(label->objectName()))
                    continue;
                ++readings;
                const int overflow = textOverflowPx(label);
                if (overflow <= 0)
                    continue;
                const int box = label->contentsRect().width();
                qInfo("FIXR2-STRIP %4d %-12s %-20s box %3d px, text %3d px, over %3d  [%s]",
                      rung, qPrintable(context), qPrintable(label->objectName()),
                      box, box + overflow, overflow, qPrintable(label->text()));
                overflowing.insert(label->objectName() + QStringLiteral("\u0000") + label->text());
                if (!isKnownStripOverflow(label->objectName(), label->text()))
                    unexpected << QStringLiteral("%1 at %2px on %3: %4 px past a %5 px box (%6)")
                                      .arg(label->objectName()).arg(rung).arg(context)
                                      .arg(overflow).arg(box).arg(label->text());
            }
        };

        for (int rung : {1180, 1280, 1600})
        {
            window.resize(rung, rung == 1180 ? 760 : 1000);
            QCoreApplication::processEvents();
            settle(&window);

            // Every page-chip string production can produce, produced the way production produces
            // it -- a real navigation, not a setText this case composed.
            for (const auto &spec : spellvision::shell::ShellNavigationController::railButtonSpecs())
            {
                QMetaObject::invokeMethod(&window, "switchToMode", Q_ARG(QString, spec.modeId));
                QCoreApplication::processEvents();
                settle(&window, 800);
                scan(rung, spec.modeId);
            }

            // The two strings MainWindow's workflow-import path writes STRAIGHT onto these chips
            // (setText("IMPORTING") / setText("Workflow import running")) rather than through
            // applyTelemetryText. That path needs a file dialog and a QProcess, so the strings are
            // placed here instead of driven -- which makes them COPIES: rename them in
            // MainWindow.cpp and this guard goes quiet about them without saying so. Recorded as the
            // cost of covering them at all.
            struct Direct { const char *objectName; const char *text; };
            const Direct directs[] = {
                {"BottomReadyLabel", "IMPORTING"},
                {"BottomStateLabel", "Workflow import running"},
            };
            for (const Direct &direct : directs)
            {
                QLabel *label = window.findChild<QLabel *>(QString::fromLatin1(direct.objectName));
                if (!label)
                    continue;
                const QString restore = label->text();
                label->setText(QString::fromLatin1(direct.text));
                scan(rung, QStringLiteral("import"));
                label->setText(restore);
            }
        }

        window.resize(before);
        QMetaObject::invokeMethod(&window, "switchToMode", Q_ARG(QString, QStringLiteral("t2i")));
        QCoreApplication::processEvents();

        // A premise: 16 modes x several visible chips x 3 rungs, plus the import pair. If the strip
        // stopped being found, or the modes stopped switching, this guard would otherwise report a
        // clean bill of health over nothing at all.
        QVERIFY2(readings >= 200,
                 qPrintable(QStringLiteral("only %1 chip readings; the strip is not being measured")
                                .arg(readings)));
        QVERIFY2(unexpected.isEmpty(),
                 qPrintable(QStringLiteral("NEW overflow: %1")
                                .arg(unexpected.mid(0, 6).join(QStringLiteral(" | ")))));
        for (const KnownStripOverflow &known : kKnownStripOverflows)
        {
            const QString key = QLatin1String(known.objectName) + QStringLiteral("\u0000")
                                + QLatin1String(known.text);
            QVERIFY2(overflowing.contains(key),
                     qPrintable(QStringLiteral("%1 no longer overflows on \"%2\" -- strike that pair "
                                               "from kKnownStripOverflows")
                                    .arg(QLatin1String(known.objectName), QLatin1String(known.text))));
        }
    }

    // CRITERION 3. Three layouts, three pairs, three pages: nine numbers, each the fraction of
    // pixels that move by more than 8/255 of luminance -- scripts/dev/uia/compare_captures.py's
    // comparison, reproduced in process against an OFFSCREEN grab rather than a screen photograph.
    //
    // The gate is the one wave 1 used to catch a Surface Style option that had never actually
    // differed: two layouts under 1 % apart are not two layouts. Every number is printed whether the
    // case passes or fails, because the spec's Results table needs the measurements and not the
    // verdict.
    void every_layout_differs_from_the_other_two_on_every_page()
    {
        MainWindow &window = mainWindow();
        const QSize before = window.size();
        window.resize(1600, 1000);
        QCoreApplication::processEvents();

        const QString captureDir = QString::fromLocal8Bit(qgetenv("SPELLVISION_LAYOUT_CAPTURE_DIR"));
        if (!captureDir.isEmpty())
            QDir().mkpath(captureDir);

        struct Page { const char *mode; const char *label; };
        const Page pages[] = {
            {"t2i", "T2I"}, {"home", "Home"}, {"models", "Models"},
        };
        const Layout layouts[] = {Layout::Instrument, Layout::Canvas, Layout::Workspaces};

        QStringList failures;
        for (const Page &page : pages)
        {
            QImage shot[3];
            for (int index = 0; index < 3; ++index)
            {
                ShellLayout::instance().setLayout(layouts[index]);
                QCoreApplication::processEvents();
                QVERIFY(QMetaObject::invokeMethod(&window, "switchToMode",
                                                  Q_ARG(QString, QString::fromLatin1(page.mode))));
                QCoreApplication::processEvents();
                settle(&window);
                shot[index] = window.grab().toImage();
                QVERIFY2(!shot[index].isNull(), "the window grabbed nothing");
                if (!captureDir.isEmpty())
                    shot[index].save(QStringLiteral("%1/%2_%3.png")
                                         .arg(captureDir, QString::fromLatin1(page.label),
                                              ShellLayout::instance().layoutNames().at(index)));
            }

            const int pairs[3][2] = {{0, 1}, {0, 2}, {1, 2}};
            for (const auto &pair : pairs)
            {
                const qreal fraction = changedFraction(shot[pair[0]], shot[pair[1]]);
                const QString name = QStringLiteral("%1 %2 vs %3")
                                         .arg(QString::fromLatin1(page.label),
                                              ShellLayout::instance().layoutNames().at(pair[0]),
                                              ShellLayout::instance().layoutNames().at(pair[1]));
                qInfo("CRITERION-3 %-34s %.4f", qPrintable(name), fraction);
                if (!(fraction >= 0.01))
                    failures << QStringLiteral("%1 = %2").arg(name).arg(fraction, 0, 'f', 4);
            }
        }

        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
        window.resize(before);
        QCoreApplication::processEvents();

        QVERIFY2(failures.isEmpty(),
                 qPrintable(QStringLiteral("under the 1 %% gate: %1").arg(failures.join(QStringLiteral("; ")))));
    }

    // CRITERION 4. The minimum window size the shell declares (MainWindow::setMinimumSize(1180,760)),
    // in all three layouts: every rail mode still ON the rail and still reachable, and nothing
    // squeezed below its own minimum.
    //
    // Reachability is asked of the SCREEN and of a CLICK, never of modeIds().size() -- a density that
    // HIDES a tile leaves that vector untouched, and a planted one already walked past a count-based
    // assertion once in this wave. The clipping scan closes the responsive matrix's recorded blind
    // spot (see layoutManagedDeep, above), so it is a strictly harder question than the matrix asks.
    void every_rail_mode_is_reachable_at_the_minimum_window_size_in_every_layout()
    {
        MainWindow &window = mainWindow();
        const QSize before = window.size();
        const QSize minimum(1180, 760);
        QCOMPARE(window.minimumSize(), minimum);

        QStringList failures;
        for (Layout layout : {Layout::Instrument, Layout::Canvas, Layout::Workspaces})
        {
            ShellLayout::instance().setLayout(layout);
            QCoreApplication::processEvents();
            window.resize(minimum);
            QCoreApplication::processEvents();
            settle(&window);

            const QString name = ShellLayout::instance().layoutNames().at(static_cast<int>(layout));
            SideRail *bar = rail(window);
            for (const auto &spec : spellvision::shell::ShellNavigationController::railButtonSpecs())
            {
                QToolButton *button = bar->buttonFor(spec.modeId);
                if (!button || !button->isVisibleTo(bar))
                {
                    failures << QStringLiteral("%1: %2 is not on the rail").arg(name, spec.modeId);
                    continue;
                }
                button->click();
                QCoreApplication::processEvents();
                if (bar->currentMode() != spec.modeId)
                    failures << QStringLiteral("%1: clicking %2 did not navigate").arg(name, spec.modeId);
            }
            settle(&window);
            const QVector<Offender> clipped = clippedControls(&window);
            qInfo("CRITERION-4 %-12s modes %d reachable, clipped %d", qPrintable(name),
                  int(spellvision::shell::ShellNavigationController::railButtonSpecs().size()),
                  int(clipped.size()));

            QSet<int> seen;
            for (const Offender &offender : clipped)
            {
                const ClipGroup group = clipGroupOf(offender, window.centralWidget());
                qInfo("CRITERION-4   %s: [%s] %s", qPrintable(name), clipGroupName(group),
                      qPrintable(offender.detail));
                if (group == ClipGroup::Unknown)
                {
                    failures << QStringLiteral("%1: NEW clip %2").arg(name, offender.detail);
                    continue;
                }
                seen.insert(static_cast<int>(group));
            }
            for (ClipGroup group : {ClipGroup::CentralShell, ClipGroup::PageStack})
            {
                if (!seen.contains(static_cast<int>(group)))
                    failures << QStringLiteral("%1: %2 no longer clips -- delete its case from "
                                               "clipGroupOf/clipGroupName")
                                    .arg(name, QLatin1String(clipGroupName(group)));
            }

            // What the stack's minimum is MADE of, so the entry above is diagnosable rather than
            // merely recorded.
            if (auto *stack = window.findChild<QStackedWidget *>(QStringLiteral("MainPageStack")))
            {
                for (int index = 0; index < stack->count(); ++index)
                {
                    QWidget *page = stack->widget(index);
                    const QSize need = page->minimumSizeHint();
                    if (need.height() > minimum.height() || need.width() > minimum.width())
                        qInfo("CRITERION-4   %s: stack page %s(%s) wants %dx%d",
                              qPrintable(name), page->metaObject()->className(),
                              qPrintable(page->objectName()), need.width(), need.height());
                }
            }
        }

        ShellLayout::instance().setLayout(Layout::Instrument);
        QCoreApplication::processEvents();
        window.resize(before);
        QCoreApplication::processEvents();

        QVERIFY2(failures.isEmpty(), qPrintable(failures.join(QStringLiteral(" | "))));
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
        for (const auto &saved : std::as_const(savedDialogKeys_))
        {
            if (saved.second.isValid())
                s.setValue(saved.first, saved.second);
            else
                s.remove(saved.first);
        }
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

    // The keys a FirstRunDialog's accept path can write, backed up in initTestCase and put back
    // verbatim (or removed, when they were absent) in cleanupTestCase.
    static QStringList dialogWrittenKeys()
    {
        return {
            QStringLiteral("runtime/comfyRoot"),
            QStringLiteral("runtime/modelsRoot"),
            QStringLiteral("runtime/comfyPython"),
            QStringLiteral("runtime/workerPython"),
            QStringLiteral("image_generation/output_folder"),
            QStringLiteral("setup/firstRunWizard_v1"),
        };
    }

    QList<QPair<QString, QVariant>> savedDialogKeys_;
    MainWindow *window_ = nullptr;
    bool savedHadKey_ = false;
    int savedLayout_ = 0;
    bool savedHadMode_ = false;
    QString savedMode_;
};

QTEST_MAIN(TestShellLayout)
#include "test_shell_layout.moc"
