// The error pill beside Generate shows as much of the message as the row allows, and never cuts it.
//
// A 280px maximum width with no elision showed "module 'worker_service' has no attribute 'res" and
// nothing else on 2026-09-02 -- a user could neither read the error nor find the rest of it. The
// pill now elides to the width the action row actually gives it, keeps the full text in the
// tooltip, and opens it in the shared failure dialog on click. This drives the real page at the
// two widths Doc 30 grades (half-screen and a 1080p full window) and asks: is the text elided
// rather than clipped, does it grow with the row, and is Generate still entirely on the page?

#include <QtTest>

#include <QApplication>
#include <QLabel>
#include <QPushButton>
#include <QRect>

#include "ImageGenerationPage.h"
#include "generation/ErrorPillLabel.h"
#include "AppEnvironment.h"

namespace
{

// A readiness hint, not an error. Long enough that no width the action row can give the pill will
// fit it, so "was it elided" is a question with an answer at every window size.
const QString kHint = QStringLiteral(
    "Choose an output folder to generate, and pick a checkpoint before you press it.");

const QString kMessage = QStringLiteral(
    "Internal error in SpellVision (please report this): AttributeError: module 'worker_service' "
    "has no attribute 'resolve_comfy_output_path'");

QLabel *errorPill(ImageGenerationPage &page)
{
    for (QLabel *label : page.findChildren<QLabel *>())
    {
        if (label->toolTip().startsWith(kMessage))
            return label;
    }
    return nullptr;
}

QPushButton *generateButton(ImageGenerationPage &page)
{
    // Several buttons share the PrimaryActionButton style; Generate is the visible one that says so.
    for (QPushButton *button : page.findChildren<QPushButton *>())
    {
        if (button->objectName() == QStringLiteral("PrimaryActionButton")
            && button->text().contains(QStringLiteral("Generate")))
            return button;
    }
    return nullptr;
}

void settle()
{
    for (int i = 0; i < 3; ++i)
        QApplication::processEvents();
}

} // namespace

class ActionRowPillTest : public QObject
{
    Q_OBJECT

private slots:
    // The environment main.cpp builds before any widget exists -- SvStyle, the bundled IBM Plex
    // faces at 12 px, and the themed application palette. Without it this file measures text in
    // SEGOE UI against a platform palette, and every fit/clip number below is about a different
    // program than the one that ships. See tests/cpp/AppEnvironment.h for what each omission cost
    // when it was found separately.
    void initTestCase() { spellvision::testenv::applyShippedAppEnvironment(); }

    void the_message_is_elided_to_the_row_and_grows_with_it()
    {
        ImageGenerationPage page(ImageGenerationPage::Mode::TextToImage);
        page.resize(1280, 800);
        page.show();
        QVERIFY(QTest::qWaitForWindowExposed(&page));
        settle();

        page.showGenerationError(kMessage);
        settle();

        QLabel *pill = errorPill(page);
        QVERIFY2(pill != nullptr, "no label carries the full message in its tooltip");
        QVERIFY(pill->isVisible());
        QVERIFY(pill->width() >= 60);
        QVERIFY(pill->width() <= 420);

        const QString narrow = pill->text();
        QVERIFY2(narrow.startsWith(QStringLiteral("⚠")), qPrintable(narrow));
        QVERIFY2(narrow.endsWith(QStringLiteral("…")), qPrintable("not elided: " + narrow));
        // Elided text fits inside the pill: nothing is cut by the widget edge.
        QVERIFY2(pill->fontMetrics().horizontalAdvance(narrow) <= pill->width(),
                 qPrintable(QStringLiteral("text %1px in a %2px pill").arg(pill->fontMetrics().horizontalAdvance(narrow)).arg(pill->width())));

        QPushButton *generate = generateButton(page);
        QVERIFY(generate != nullptr);
        QVERIFY(generate->isVisible());
        const QRect generateRect(generate->mapTo(&page, QPoint(0, 0)), generate->size());
        QVERIFY2(page.rect().contains(generateRect), "Generate pushed off the page by the pill");

        page.resize(1920, 1000);
        settle();
        const QString wide = pill->text();
        QVERIFY2(wide.size() >= narrow.size(),
                 qPrintable(QStringLiteral("wider row showed less: %1 -> %2 chars").arg(narrow.size()).arg(wide.size())));
        QVERIFY(pill->width() <= 420);

        page.clearGenerationError();
        settle();
        QVERIFY(!pill->text().contains(QStringLiteral("resolve_comfy")));
    }

    // THE HINT PATH, which for the life of this widget did not exist.
    //
    // ErrorPillLabel elided only what arrived through setMessage(), because refit() early-returned
    // on an empty oneLine_ -- and NINE call sites wrote the pill with a raw QLabel::setText(). So
    // every readiness hint, the most-shown string the pill carries, was hard cut: 183 px of
    // "Choose an output folder to generate." in a 66 px box on I2V at the half-screen width Doc 30
    // grades. The responsive matrix found it the day that gate was pointed at the deeper clip
    // scanner, and could not have found it before: ErrorPillLabel overrides minimumSizeHint() to
    // report its enforced 60 px floor, so a hint-based scan sees a control inside its contract.
    //
    // The fix is NOT to route those callers at setMessage(). That would give every hint a warning
    // glyph, a "Click for the full message." tooltip, a pointing-hand cursor and a click that opens
    // a failure dialog about nothing -- error affordances on a sentence that is not an error, which
    // is a worse defect than the clip. So this case asserts BOTH halves: the hint is elided like a
    // message, and it is dressed like nothing at all.
    void a_hint_is_elided_like_a_message_and_dressed_like_neither()
    {
        ImageGenerationPage page(ImageGenerationPage::Mode::TextToImage);
        // The half-screen width Doc 30 grades, where the clip was measured.
        page.resize(960, 1000);
        page.show();
        QVERIFY(QTest::qWaitForWindowExposed(&page));
        settle();

        auto *pill = page.findChild<spellvision::generation::ErrorPillLabel *>();
        QVERIFY2(pill != nullptr, "the action row has no ErrorPillLabel");
        pill->setHint(kHint);
        settle();

        // A premise, not decoration: the page updates its own readiness on a dozen signals, and a
        // queued one landing between setHint and the reads below would leave this case measuring a
        // different string while still passing every assertion under it.
        QVERIFY2(pill->toolTip() == kHint,
                 qPrintable(QStringLiteral("something overwrote the hint: %1").arg(pill->toolTip())));

        const QString shown = pill->text();
        // ELIDED LIKE A MESSAGE. Both halves: the ellipsis says the widget shortened it, and the
        // font-metric fit says the result is inside the box rather than merely shorter.
        QVERIFY2(shown.endsWith(QStringLiteral("…")), qPrintable("not elided: " + shown));
        QVERIFY2(pill->fontMetrics().horizontalAdvance(shown) <= pill->width(),
                 qPrintable(QStringLiteral("hint %1px in a %2px pill: %3")
                                .arg(pill->fontMetrics().horizontalAdvance(shown))
                                .arg(pill->width()).arg(shown)));

        // DRESSED LIKE NEITHER. No warning glyph, no invitation to click, no hand cursor, and
        // nothing for the click handler to open -- hasMessage() still answers "is an ERROR showing".
        QVERIFY2(!shown.startsWith(QStringLiteral("⚠")), qPrintable("a hint wearing the error glyph: " + shown));
        QVERIFY2(!pill->toolTip().contains(QStringLiteral("Click")),
                 qPrintable("a hint offering the failure dialog: " + pill->toolTip()));
        QCOMPARE(pill->cursor().shape(), Qt::ArrowCursor);
        QVERIFY2(!pill->hasMessage(), "a hint is being reported as an error");
        QVERIFY2(pill->fullText().isEmpty(), "a hint left something for the failure dialog to show");

        // And the error path still reaches all four of those from the same widget, immediately
        // after: the two paths share one label and must not leave each other's state behind.
        page.showGenerationError(kMessage);
        settle();
        QVERIFY2(pill->text().startsWith(QStringLiteral("⚠")), qPrintable(pill->text()));
        QVERIFY(pill->toolTip().contains(QStringLiteral("Click")));
        QCOMPARE(pill->cursor().shape(), Qt::PointingHandCursor);
        QVERIFY(pill->hasMessage());
        QCOMPARE(pill->fullText(), kMessage);
    }

    void the_full_text_is_one_hover_or_click_away()
    {
        ImageGenerationPage page(ImageGenerationPage::Mode::TextToImage);
        page.resize(1280, 800);
        page.show();
        QVERIFY(QTest::qWaitForWindowExposed(&page));
        settle();

        page.showGenerationError(kMessage);
        settle();
        QLabel *pill = errorPill(page);
        QVERIFY(pill != nullptr);
        QVERIFY(pill->toolTip().startsWith(kMessage));
        QVERIFY(pill->toolTip().contains(QStringLiteral("Click")));
        QCOMPARE(pill->cursor().shape(), Qt::PointingHandCursor);

        page.clearGenerationError();
        settle();
        QCOMPARE(pill->cursor().shape(), Qt::ArrowCursor);
    }
};

QTEST_MAIN(ActionRowPillTest)
#include "test_action_row_pill.moc"
