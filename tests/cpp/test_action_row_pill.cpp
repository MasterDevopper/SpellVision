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

namespace
{

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
