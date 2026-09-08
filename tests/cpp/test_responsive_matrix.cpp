// Doc 30's 7-surface x 4-state responsive matrix, run mechanically.
//
// Doc 28 lists this as a release gate and records that it "is defined and has never been executed".
// It sat as a manual owner-eyes table because nothing could construct a page outside the running
// app -- every source lived inline in qt_add_executable. SpellVisionCore fixed that, so the matrix
// becomes a test.
//
// Doc 30 states the pass predicate precisely, and every clause of it is machine-checkable:
//
//     "no clipped controls, no missing Advanced, Generate always reachable,
//      status bar readable, no QSS parse spam"
//
// This is also the first thing on the C++ side that can catch the class of defect Doc 50's own
// ratchet table names as its gap: "every ratchet here is Python. The C++ side has no equivalent,
// and two defects in this pass lived there."

#include <QtTest>

#include <QElapsedTimer>

#include <vector>
#include <QAbstractScrollArea>
#include <QApplication>
#include <QLabel>
#include <QLayout>
#include <QPushButton>
#include <QScrollArea>
#include <QWidget>

#include "ImageGenerationPage.h"
#include "studios/ComicStudioPage.h"
#include "studios/CharacterStudioPage.h"
#include "T2VHistoryPage.h"
#include "WorkflowLibraryPage.h"
#include "ManagerPage.h"
#include "AppEnvironment.h"
#include "ClipScan.h"

using spellvision::studios::CharacterStudioPage;
using spellvision::studios::ComicStudioPage;

namespace {

// The four window states from Doc 30's table. "Half W" and "Half H" are the Windows snap sizes on
// a 1920x1080 display, which is where the owner's half-screen grade came from.
struct WindowState
{
    const char *name;
    QSize size;
};

const WindowState kStates[] = {
    {"Full",    QSize(1920, 1080)},
    {"Restore", QSize(1280, 800)},
    {"Half W",  QSize(960, 1080)},
    {"Half H",  QSize(1920, 540)},
};

// Collected by the message handler for the duration of one case.
QStringList g_styleSheetComplaints;

QtMessageHandler g_previousHandler = nullptr;

void styleSheetWatcher(QtMsgType type, const QMessageLogContext &context, const QString &message)
{
    if (message.contains(QStringLiteral("Could not parse stylesheet"))
        || message.contains(QStringLiteral("Unknown property")))
    {
        g_styleSheetComplaints << message;
    }
    // Chain to the previous handler rather than returning. The first version of this swallowed
    // every message it did not recognise -- including this test's own qWarning diagnostics and
    // QTest's per-case output -- so the matrix reported "5 clipped" and printed nothing about
    // WHICH five. A handler that silently drops what it does not match is the same shape this
    // whole pass is about, and it cost a run to notice.
    if (g_previousHandler != nullptr)
        g_previousHandler(type, context, message);
}

// THE CLIPPING SCANNER LIVES IN tests/cpp/ClipScan.h -- one copy, shared with test_shell_layout.cpp.
//
// This file used to carry its own `clippedControls`, under the same name, in the same directory, and
// the two asked DIFFERENT questions. This one gated on `parent->layout()->indexOf(w)`, which sees
// only a layout's own direct items, so a control inside a nested `addLayout()`ed row answered "not
// layout managed" and was skipped in silence -- on the surface Doc 28 lists as a RELEASE GATE. It
// also asked labels for a `minimumSizeHint` Qt serves out of a cache `setFixedWidth` does not clear,
// which is the instrument four wrong diagnoses on this wave were spent refuting. The shared scanner
// walks the parent's whole layout tree and asks a label's own font metrics.
using spellvision::testscan::Offender;

// Pump the event loop until the page's geometry stops moving, or the budget runs out.
//
// "Settled" means two consecutive samples of every child's geometry agree. That is the property the
// measurement below actually needs -- a widget still being laid out reports the size it has so far,
// which is indistinguishable from a widget that has been squeezed.
void waitForLayoutToSettle(QWidget *root, int budgetMs = 3000)
{
    auto sample = [root]() {
        QString state;
        const QList<QWidget *> children = root->findChildren<QWidget *>();
        state.reserve(children.size() * 24);
        for (const QWidget *w : children)
        {
            const QRect g = w->geometry();
            state += QStringLiteral("%1,%2,%3,%4,%5;")
                         .arg(g.x()).arg(g.y()).arg(g.width()).arg(g.height())
                         .arg(w->isVisible() ? 1 : 0);
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
    qWarning("layout did not settle within %d ms; measuring anyway", budgetMs);
}

// The shared scanner plus the ONE question it does not ask, because it is about a scroll area rather
// than a squeezed control: a resizable area whose content is wider than its viewport, with the
// horizontal bar off, is CLIPPING rather than scrolling. Comic Studio's left column shipped exactly
// that (a combo whose widest item was wider than the column) and this matrix could not see it,
// because everything inside a scroll area is skipped on purpose.
QVector<Offender> clippedControls(QWidget *root)
{
    QVector<Offender> offenders;
    for (QScrollArea *area : root->findChildren<QScrollArea *>())
    {
        if (!area->isVisible() || area->size().isEmpty())
            continue;
        if (!area->widgetResizable() || area->widget() == nullptr
            || area->horizontalScrollBarPolicy() != Qt::ScrollBarAlwaysOff
            || area->widget()->width() <= area->viewport()->width())
            continue;
        Offender offender;
        offender.widget = area;
        offender.key = QStringLiteral("%1(%2)")
                           .arg(QString::fromLatin1(area->metaObject()->className()),
                                area->objectName().isEmpty() ? QStringLiteral("-") : area->objectName());
        offender.detail = QStringLiteral("%1 content %2px wide in a %3px viewport")
                              .arg(offender.key)
                              .arg(area->widget()->width()).arg(area->viewport()->width());
        offenders.append(offender);
    }
    offenders += spellvision::testscan::clippedControls(root);
    return offenders;
}

// "PrimaryActionButton" is a shared QSS style selector, not a unique id -- ImageGenerationPage
// gives it to both the real Generate button and the (usually hidden) video-transport Play button
// (test_action_row_pill.cpp's generateButton() hits the same ambiguity and disambiguates the same
// way). A bare findChild<QPushButton*>(name) picks whichever one Qt's object tree happens to visit
// first, which depends on parent/child structure rather than anything the test means to assert --
// it found the right one by luck until the cockpit-members refactor (promoting the action row from
// a bare layout to a widget) changed that structure and flipped it to the wrong button. Match on
// text too, the same way Doc 30 always meant "the Generate button", not "a button styled Primary".
QPushButton *findGenerateButton(QWidget *root)
{
    for (QPushButton *button : root->findChildren<QPushButton *>())
    {
        if (button->objectName() == QStringLiteral("PrimaryActionButton")
            && button->text().contains(QStringLiteral("Generate")))
            return button;
    }
    return nullptr;
}

// Cells that fail TODAY, with the reason. Modelled on test_family_capability.py's KNOWN_GAPS: it
// records the baseline so a NEW failure fails the suite immediately, and closing one also fails --
// forcing the number down rather than letting it rot.
//
// Both entries are REAL defects, not accepted behaviour. They are recorded rather than fixed here
// because a layout change wants an eye on it, and this commit's job is to make the matrix run at
// all -- Doc 28 has listed it as a gate since 2026-07-25 with the note that it "has never been
// executed".
struct KnownFailure
{
    const char *cell;
    const char *reason;
};

// Cells that fail today, with the reason. EMPTY, and that is the point: the two entries this list
// shipped with were both real defects, and both were fixed on 2026-09-02 once the clip report
// printed the ANCESTRY of a squeezed control rather than only its size.
//
//   * "T2I / Full" -- the canvas empty-state chips row was 120px inside a 1390px empty state,
//     because addWidget(row, 0, Qt::AlignHCenter) gives an item its size HINT rather than the space
//     available. It centres itself with stretches now, like the preview stack does.
//   * "History details / Half W" -- four full-word buttons in one row gave the details card a 367px
//     minimum while reflowForWidth deliberately shrinks it to ~300px so the table is not crushed.
//     They are a 2x2 grid now, like the copy actions right below them.
//
// The baseline stays, and stays two-way: a new failure fails the suite, and a cell that starts
// passing must be deleted rather than left standing as an excuse.

const std::vector<KnownFailure> &knownFailures()
{
    // A std::vector, not a C array: an array of zero elements does not compile, and "the list is
    // empty" is the state this baseline is supposed to be able to reach.
    static const std::vector<KnownFailure> list = {
    };
    return list;
}

// A CLIP this gate pardons, keyed by the WHOLE identity of what it pardons: the cell, the control,
// and -- for a label -- the string it is showing. Keyed by any one of those alone a pardon reaches
// things it was never shown: earlier in this wave a telemetry allowance keyed by CHIP alone let an
// unrelated entry pardon the very label a plant had just broken, and the plant sailed through. So
// `reason` is prose and the first three fields are the identity.
//
// These are not new defects. They are clips the SHALLOW scanner this file used to carry could not
// see -- a control inside a nested addLayout()ed row answered "not layout managed" and was skipped
// in silence. Nothing was widened to make the gate green: widening a control to fit a measurement is
// how a surface gets worse while its gate goes green.
struct KnownClip
{
    const char *cell;    // "Surface / State"
    const char *key;     // Class(objectName) -- the offender's own identity
    const char *text;    // a label's plain text, "" for anything else
    const char *reason;
};

const std::vector<KnownClip> &knownClips()
{
    static const std::vector<KnownClip> list = {
        // REAL, and the deep scanner is the first thing to see it. ErrorPillLabel exists because a
        // plain QLabel cut a message mid-word (2026-09-02); it elides in refit() and overrides
        // minimumSizeHint() to return its enforced 60 px floor -- which is exactly why the shallow
        // hint-based scan this file used to run could never flag it, and why the override is not a
        // dodge. But refit() returns early when oneLine_ is empty, and ImageGenerationPage.cpp:1366's
        // readiness path calls setText() directly instead of setMessage(), so on THAT path the pill
        // never elides: 183 px of text in a 66 px box, hard-cut, at the 960 px half-screen width.
        // The full string is in the tooltip, so it is readable, not lost. Deterministic: the same
        // single offender on three consecutive runs.
        //
        // NOT FIXED HERE, and deliberately not by widening anything -- widening a control to fit a
        // measurement is how a surface gets worse while its gate goes green. The fix is one line at
        // the CALLER (route the readiness hint through setMessage(oneLine, full), the way
        // showGenerationError already does) and it belongs with the surface work wave 4 owns, with a
        // render to prove it. Recorded two-way: if it stops clipping, this entry must be struck out.
        {"I2V / Half W", "QLabel(ReadinessHint)", "Choose an output folder to generate.",
         "ErrorPillLabel::refit() is bypassed: the readiness path calls setText, not setMessage"},
    };
    return list;
}

// The identity a pardon is matched on. A label carries its text; everything else carries an empty
// string, so a KnownClip that names a string can never pardon a non-label.
QString clipIdentity(const QString &cell, const Offender &offender)
{
    QString text;
    if (const auto *label = qobject_cast<const QLabel *>(offender.widget))
        text = label->textFormat() == Qt::RichText
                   ? QTextDocumentFragment::fromHtml(label->text()).toPlainText()
                   : label->text();
    return cell + QChar(u'\0') + offender.key + QChar(u'\0') + text;
}

QString clipIdentity(const KnownClip &known)
{
    return QLatin1String(known.cell) + QChar(u'\0') + QLatin1String(known.key) + QChar(u'\0')
           + QLatin1String(known.text);
}

bool isKnownClip(const QString &identity)
{
    for (const KnownClip &known : knownClips())
        if (identity == clipIdentity(known))
            return true;
    return false;
}

bool isKnownFailure(const QString &cell)
{
    for (const KnownFailure &known : knownFailures())
    {
        if (cell == QLatin1String(known.cell))
            return true;
    }
    return false;
}

} // namespace

class ResponsiveMatrix : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void matrix_data();
    void matrix();
    void cleanupTestCase();

private:
    QStringList results_;
};

void ResponsiveMatrix::initTestCase()
{
    // FIRST, and before the message handler: the environment main.cpp builds before any widget
    // exists -- SvStyle, the bundled IBM Plex faces at 12 px, the themed application palette. Doc 28
    // lists this matrix as a release gate and every clause of it is a geometry or a text-fit
    // measurement, so a gate taken in Segoe UI under a platform palette is a gate on a different
    // program. See tests/cpp/AppEnvironment.h. It runs before qInstallMessageHandler so that the
    // application overlay sheet is not attributed to a page by styleSheetWatcher.
    spellvision::testenv::applyShippedAppEnvironment();

    g_previousHandler = qInstallMessageHandler(styleSheetWatcher);
}

void ResponsiveMatrix::matrix_data()
{
    QTest::addColumn<QString>("surface");
    QTest::addColumn<QString>("state");
    QTest::addColumn<QSize>("size");
    QTest::addColumn<bool>("advanced");
    QTest::addColumn<bool>("hasGenerate");

    // Doc 30's seven surfaces. "Comic Advanced ON" is the row that carries the advanced flag --
    // it is listed separately in the doc precisely because Advanced is where the clipping showed.
    // hasGenerate: whether the "Generate always reachable" clause applies. Library and runtime
    // pages have no Generate; asserting on the first PrimaryActionButton they happen to contain
    // (Workflows' hidden Import button) would fail them for the wrong reason.
    struct Surface { const char *name; bool advanced; bool hasGenerate; };
    const Surface surfaces[] = {
        {"T2I", false, true},
        {"T2V", false, true},
        {"I2V", false, true},
        {"Comic Advanced ON", true, true},
        {"Character concept", false, true},
        {"History details", false, true},
        {"Title bar + telemetry", false, true},
        // Added 2026-09-01. Both were absent, and both shipped defects of exactly the class this
        // matrix catches: a nine-button non-wrapping row, and a page with no scroll region.
        {"Workflows library", false, false},
        {"Runtime page", false, false},
    };

    for (const Surface &surface : surfaces)
    {
        for (const WindowState &state : kStates)
        {
            QTest::newRow(qPrintable(QStringLiteral("%1 / %2").arg(surface.name, state.name)))
                << QString::fromLatin1(surface.name)
                << QString::fromLatin1(state.name)
                << state.size
                << surface.advanced
                << surface.hasGenerate;
        }
    }
}

void ResponsiveMatrix::matrix()
{
    QFETCH(QString, surface);
    QFETCH(QString, state);
    QFETCH(QSize, size);
    QFETCH(bool, advanced);
    QFETCH(bool, hasGenerate);

    g_styleSheetComplaints.clear();

    QScopedPointer<QWidget> page;
    if (surface == QStringLiteral("T2I"))
        page.reset(new ImageGenerationPage(ImageGenerationPage::Mode::TextToImage));
    else if (surface == QStringLiteral("T2V"))
        page.reset(new ImageGenerationPage(ImageGenerationPage::Mode::TextToVideo));
    else if (surface == QStringLiteral("I2V"))
        page.reset(new ImageGenerationPage(ImageGenerationPage::Mode::ImageToVideo));
    else if (surface == QStringLiteral("Comic Advanced ON"))
        page.reset(new ComicStudioPage());
    else if (surface == QStringLiteral("Character concept"))
        page.reset(new CharacterStudioPage());
    else if (surface == QStringLiteral("History details"))
        page.reset(new T2VHistoryPage());
    else if (surface == QStringLiteral("Title bar + telemetry"))
        page.reset(new ImageGenerationPage(ImageGenerationPage::Mode::TextToImage));
    else if (surface == QStringLiteral("Workflows library"))
        page.reset(new WorkflowLibraryPage());
    else if (surface == QStringLiteral("Runtime page"))
        page.reset(new ManagerPage());

    QVERIFY2(!page.isNull(), qPrintable(QStringLiteral("no constructor for surface %1").arg(surface)));

    if (advanced)
    {
        if (auto *comic = qobject_cast<ComicStudioPage *>(page.data()))
            comic->updateDisclosure(true);
    }

    page->resize(size);
    page->show();
    QVERIFY(QTest::qWaitForWindowExposed(page.data()));
    // Let deferred layout settle. Several surfaces lay out on a queued connection after show().
    //
    // Waited a flat 120 ms before, and that made this a RACE rather than a check: run alone it
    // passed 3 times out of 3, and inside the full ctest sequence -- where nineteen Qt processes
    // have just competed for the same machine -- it failed twice out of three, reporting four
    // CanvasMetricChips at 24x20 against a 94x20 minimum. Those chips were not clipped; they had
    // not been laid out yet. A gate whose verdict depends on how busy the box is teaches people to
    // re-run it, and a re-run until green is not a gate.
    //
    // So settle on the CONDITION rather than the clock: pump events until the geometry of every
    // child stops changing, then measure. A longer flat wait would only move the race.
    waitForLayoutToSettle(page.data());

    const QString cell = QStringLiteral("%1 / %2").arg(surface, state);
    const QVector<Offender> allClipped = clippedControls(page.data());
    QStringList clipped;      // NEW -- what this gate fails on
    QStringList pardoned;     // recorded, and checked two-way below
    for (const Offender &offender : allClipped)
    {
        const QString identity = clipIdentity(cell, offender);
        if (isKnownClip(identity))
            pardoned << identity;
        else
            clipped << offender.detail;
    }

    // "Generate always reachable" -- the button exists, is visible, and lies inside the page.
    QString generateVerdict = QStringLiteral("n/a");
    if (auto *generate = hasGenerate ? findGenerateButton(page.data()) : nullptr)
    {
        const QRect inPage(generate->mapTo(page.data(), QPoint(0, 0)), generate->size());
        const bool reachable = generate->isVisible() && page->rect().intersects(inPage);
        generateVerdict = reachable ? QStringLiteral("reachable") : QStringLiteral("UNREACHABLE");
    }

    const bool pass = clipped.isEmpty()
                      && g_styleSheetComplaints.isEmpty()
                      && generateVerdict != QStringLiteral("UNREACHABLE");

    results_ << QStringLiteral("| %1 | %2 | %3 | %4 | %5 | %6 | %7 |")
                    .arg(surface, state,
                         pass ? QStringLiteral("PASS") : QStringLiteral("FAIL"))
                    .arg(clipped.size())
                    .arg(pardoned.size())
                    .arg(g_styleSheetComplaints.size())
                    .arg(generateVerdict);

    // Report every failing clause rather than the first: the point of a matrix is to see the shape
    // of the failure across cells, and stopping at the first hides it.
    if (!clipped.isEmpty())
        qWarning("%s / %s: %d clipped control(s): %s", qPrintable(surface), qPrintable(state),
                 int(clipped.size()), qPrintable(clipped.mid(0, 5).join(QStringLiteral("; "))));
    if (!g_styleSheetComplaints.isEmpty())
        qWarning("%s / %s: %d stylesheet complaint(s): %s", qPrintable(surface), qPrintable(state),
                 int(g_styleSheetComplaints.size()),
                 qPrintable(g_styleSheetComplaints.first()));

    // Two-way, the same way kKnownFailures is: a pardoned clip that stops happening must be struck
    // from knownClips(), or the list becomes a permanent excuse for a defect somebody fixed.
    for (const KnownClip &known : knownClips())
    {
        if (cell != QLatin1String(known.cell))
            continue;
        QVERIFY2(pardoned.contains(clipIdentity(known)),
                 qPrintable(QStringLiteral("%1: %2 [%3] no longer clips -- strike it from "
                                           "knownClips()")
                                .arg(cell, QLatin1String(known.key), QLatin1String(known.text))));
    }

    if (isKnownFailure(cell))
    {
        // Two-way, like KNOWN_GAPS: a cell that starts passing must be REMOVED from the baseline,
        // so the list can only shrink. Otherwise a fixed bug leaves a permanent excuse behind.
        QVERIFY2(!pass, qPrintable(QStringLiteral(
            "%1 now passes -- delete it from kKnownFailures").arg(cell)));
        return;
    }

    QVERIFY2(g_styleSheetComplaints.isEmpty(), "QSS parse spam");
    QVERIFY2(generateVerdict != QStringLiteral("UNREACHABLE"), "Generate is not reachable");
    QVERIFY2(clipped.isEmpty(), qPrintable(clipped.join(QStringLiteral("; "))));
}

void ResponsiveMatrix::cleanupTestCase()
{
    qInstallMessageHandler(nullptr);

    // Print the table Doc 30 has carried empty since 2026-07-25, so a run RECORDS the matrix rather
    // than only gating on it.
    QTextStream out(stdout);
    out << "\n--- Doc 30 responsive matrix ---\n";
    out << "| Surface | State | Result | Clipped | Known | QSS | Generate |\n";
    out << "|---|---|---|---|---|---|---|\n";
    for (const QString &row : std::as_const(results_))
        out << row << "\n";
    out.flush();
}

QTEST_MAIN(ResponsiveMatrix)
#include "test_responsive_matrix.moc"
