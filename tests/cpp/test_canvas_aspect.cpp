// The canvas hugs the picture. Before this, it did not.
//
// The mechanism behind "the canvas is a gross excess ratio compared to the space the image
// occupies": the preview stack was Expanding on both axes, the column's width cap had been
// removed, and the image was aspect-fit into whatever box resulted. A 768x1024 render on a wide
// window sat centred in a card over 1000px wide. Nothing shrank the box to the picture.
//
// This drives the real ImagePreviewController against a synthetic stack -- the same shape the
// cockpit builds (a parent column, a stacked widget with a page, a label in the page) -- and
// asserts three things: the stack's aspect converges on the picture's, it does not oscillate, and
// it GROWS again when the parent grows. The last is the one a naive maximum-size cap gets wrong.

#include <QtTest>

#include <QApplication>
#include <QLabel>
#include <QPixmap>
#include <QStackedWidget>
#include <QVBoxLayout>
#include <QWidget>

#include "preview/AspectCap.h"
#include "preview/ImagePreviewController.h"

using spellvision::preview::ImagePreviewBindings;
using spellvision::preview::ImagePreviewController;

namespace
{

struct Rig
{
    QWidget *column = nullptr;
    QWidget *area = nullptr;   // the budget: what the cap may never shrink
    QStackedWidget *stack = nullptr;
    QLabel *label = nullptr;
    ImagePreviewController *controller = nullptr;
};

Rig makeRig(const QSize &columnSize)
{
    Rig rig;
    rig.column = new QWidget;
    auto *layout = new QVBoxLayout(rig.column);
    layout->setContentsMargins(0, 0, 0, 0);
    rig.stack = new QStackedWidget(rig.column);
    rig.stack->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    auto *page = new QWidget(rig.stack);
    auto *pageLayout = new QVBoxLayout(page);
    pageLayout->setContentsMargins(8, 8, 8, 8);
    rig.label = new QLabel(page);
    rig.label->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Ignored);
    rig.label->setMinimumSize(0, 0);
    pageLayout->addWidget(rig.label);
    rig.stack->addWidget(page);
    // The cockpit's own centring shape. Not setAlignment: an aligned item is given its size hint
    // and the stack collapses to 16px -- the first run of this test caught that in the product.
    auto *row = new QHBoxLayout;
    row->setContentsMargins(0, 0, 0, 0);
    row->addStretch(0);
    row->addWidget(rig.stack, 1);
    row->addStretch(0);
    // The centring layouts live in a PreviewArea widget, exactly as the cockpit builds it: the
    // area is the budget the controller fits against, the stack is what the cap shrinks inside it.
    rig.area = new QWidget(rig.column);
    rig.area->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    rig.area->setMinimumSize(0, 0);
    auto *col = new QVBoxLayout(rig.area);
    col->setContentsMargins(0, 0, 0, 0);
    col->addStretch(0);
    col->addLayout(row, 1);
    col->addStretch(0);
    layout->addWidget(rig.area, 1);

    rig.controller = new ImagePreviewController(rig.column);
    ImagePreviewBindings bindings;
    bindings.previewLabel = rig.label;
    bindings.sizeCapWidget = rig.stack;
    bindings.sizeBudgetWidget = rig.area;
    rig.controller->bind(bindings);

    rig.column->resize(columnSize);
    rig.column->show();
    return rig;
}

double aspect(const QWidget *w)
{
    return w->height() > 0 ? double(w->width()) / double(w->height()) : 0.0;
}

void settle(QWidget *w)
{
    // Two passes: the cap changes the layout, and the layout's Resize re-runs refit once more.
    for (int i = 0; i < 4; ++i)
    {
        QApplication::processEvents();
        QTest::qWait(20);
    }
    QVERIFY(QTest::qWaitForWindowExposed(w));
}

}  // namespace

class CanvasAspectTest : public QObject
{
    Q_OBJECT

private slots:
    void aPortraitRenderInAWideColumnGetsAPortraitBox()
    {
        Rig rig = makeRig(QSize(1600, 900));
        settle(rig.column);
        QVERIFY(rig.stack->width() > 1000);   // the pre-fix shape: the stack takes the column

        QPixmap portrait(768, 1024);
        portrait.fill(Qt::darkGreen);
        rig.controller->showPixmap(QStringLiteral("test://portrait"), portrait, QString());
        settle(rig.column);

        const double want = 768.0 / 1024.0;
        const double got = aspect(rig.stack);
        QVERIFY2(std::abs(got - want) < 0.06,
                 qPrintable(QStringLiteral("stack aspect %1 vs picture %2 (stack %3x%4)")
                                .arg(got).arg(want).arg(rig.stack->width()).arg(rig.stack->height())));
        QVERIFY2(rig.stack->width() < 800, "the stack is still far wider than the picture");
        delete rig.column;
    }

    void aWideClipInATallColumnGetsAWideBox()
    {
        Rig rig = makeRig(QSize(700, 1200));
        settle(rig.column);
        QPixmap wide(832, 480);
        wide.fill(Qt::darkBlue);
        rig.controller->showPixmap(QStringLiteral("test://wide"), wide, QString());
        settle(rig.column);
        const double want = 832.0 / 480.0;
        QVERIFY2(std::abs(aspect(rig.stack) - want) < 0.08,
                 qPrintable(QStringLiteral("stack aspect %1 vs picture %2").arg(aspect(rig.stack)).arg(want)));
        QVERIFY2(rig.stack->height() < 600, "the stack is still far taller than the picture");
        delete rig.column;
    }

    void aColdLabelDoesNotPinTheCap()
    {
        // The live failure of 2026-09-02: a 1080x1920 render arrived while the label was a cold
        // 48x86, the fit was measured on the label, and the cap pinned it there at every window
        // size. The fit must be measured on the budget, which the cap cannot touch.
        Rig rig = makeRig(QSize(1600, 900));
        settle(rig.column);
        spellvision::preview::applyAspectCap(rig.stack, rig.label, QSize(40, 70));
        settle(rig.column);
        QVERIFY2(rig.stack->height() < 120, "the rig failed to reproduce the cold, capped state");

        QPixmap portrait(1080, 1920);
        portrait.fill(Qt::darkCyan);
        rig.controller->showPixmap(QStringLiteral("test://cold"), portrait, QString());
        settle(rig.column);

        QVERIFY2(rig.stack->height() > rig.area->height() - 40,
                 qPrintable(QStringLiteral("stack %1x%2 in an area %3x%4 -- still pinned small")
                                .arg(rig.stack->width()).arg(rig.stack->height())
                                .arg(rig.area->width()).arg(rig.area->height())));
        const double want = 1080.0 / 1920.0;
        QVERIFY2(std::abs(aspect(rig.stack) - want) < 0.06,
                 qPrintable(QStringLiteral("stack aspect %1 vs picture %2").arg(aspect(rig.stack)).arg(want)));
        delete rig.column;
    }

    void theBoxShrinksWithTheBudget()
    {
        Rig rig = makeRig(QSize(1600, 900));
        settle(rig.column);
        QPixmap portrait(768, 1024);
        portrait.fill(Qt::darkMagenta);
        rig.controller->showPixmap(QStringLiteral("test://shrink"), portrait, QString());
        settle(rig.column);
        QVERIFY(rig.stack->height() > 700);

        rig.column->resize(900, 500);
        settle(rig.column);
        QVERIFY2(rig.stack->height() <= rig.area->height(),
                 qPrintable(QStringLiteral("stack %1 taller than its area %2").arg(rig.stack->height()).arg(rig.area->height())));
        QVERIFY2(rig.stack->height() > rig.area->height() - 40, "the stack did not follow the smaller budget");
        const double want = 768.0 / 1024.0;
        QVERIFY2(std::abs(aspect(rig.stack) - want) < 0.06,
                 qPrintable(QStringLiteral("stack aspect %1 vs picture %2").arg(aspect(rig.stack)).arg(want)));
        delete rig.column;
    }

    void itDoesNotOscillate()
    {
        Rig rig = makeRig(QSize(1600, 900));
        settle(rig.column);
        QPixmap portrait(768, 1024);
        portrait.fill(Qt::gray);
        rig.controller->showPixmap(QStringLiteral("test://p"), portrait, QString());
        settle(rig.column);
        const QSize first = rig.stack->size();
        for (int i = 0; i < 10; ++i)
        {
            QApplication::processEvents();
            QTest::qWait(15);
        }
        QCOMPARE(rig.stack->size(), first);
        delete rig.column;
    }

    void itGrowsAgainWhenTheParentGrows()
    {
        // The one a naive maximum-size cap gets wrong: once capped, a widget never sees a larger
        // offer, so the picture would freeze at the size of the first layout. The parent's Resize
        // releases the cap; the layout offers the full column; the label's Resize re-caps.
        Rig rig = makeRig(QSize(900, 600));
        settle(rig.column);
        QPixmap portrait(768, 1024);
        portrait.fill(Qt::black);
        rig.controller->showPixmap(QStringLiteral("test://grow"), portrait, QString());
        settle(rig.column);
        const int before = rig.stack->height();

        rig.column->resize(1400, 1000);
        settle(rig.column);
        QVERIFY2(rig.stack->height() > before + 100,
                 qPrintable(QStringLiteral("stack did not grow: %1 -> %2").arg(before).arg(rig.stack->height())));
        QVERIFY(std::abs(aspect(rig.stack) - 768.0 / 1024.0) < 0.06);
        delete rig.column;
    }

    void clearingReleasesTheCap()
    {
        Rig rig = makeRig(QSize(1600, 900));
        settle(rig.column);
        QPixmap portrait(768, 1024);
        portrait.fill(Qt::red);
        rig.controller->showPixmap(QStringLiteral("test://c"), portrait, QString());
        settle(rig.column);
        QVERIFY(rig.stack->maximumWidth() != QWIDGETSIZE_MAX);
        rig.controller->clearLabelPixmap();
        QCOMPARE(rig.stack->maximumWidth(), QWIDGETSIZE_MAX);
        QCOMPARE(rig.stack->maximumHeight(), QWIDGETSIZE_MAX);
        delete rig.column;
    }

    void theHelperIsIdempotentWithinAPixel()
    {
        // The chrome is measured as cap minus content, so the content must follow the cap through
        // a real layout -- exactly as the preview label follows the stack in the cockpit. Without
        // a layout the first cap resizes the cap widget, the content stays put, and the second
        // measurement reads a negative chrome. That is not the helper being wrong; it is the rig.
        QWidget parent;
        auto *cap = new QWidget(&parent);
        auto *capLayout = new QVBoxLayout(cap);
        capLayout->setContentsMargins(10, 10, 10, 10);
        auto *content = new QWidget(cap);
        content->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Ignored);
        capLayout->addWidget(content);
        parent.resize(500, 400);
        cap->resize(400, 300);
        parent.show();
        QVERIFY(QTest::qWaitForWindowExposed(&parent));
        QApplication::processEvents();

        spellvision::preview::applyAspectCap(cap, content, QSize(200, 100));
        QCOMPARE(cap->maximumSize(), QSize(220, 120));
        QApplication::processEvents();
        // Off by one: no change, so rounding in the layout cannot make this flap.
        spellvision::preview::applyAspectCap(cap, content, QSize(201, 101));
        QCOMPARE(cap->maximumSize(), QSize(220, 120));
        spellvision::preview::releaseAspectCap(cap);
        QCOMPARE(cap->maximumWidth(), QWIDGETSIZE_MAX);
    }
};

QTEST_MAIN(CanvasAspectTest)
#include "test_canvas_aspect.moc"
