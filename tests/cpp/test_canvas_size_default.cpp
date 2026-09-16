// A page never opens with Generate blocked by a size the app could have chosen.
//
// The width/height spin boxes start at 0 and only a preset or a saved value ever set them, so on
// 2026-09-02 a fresh I2I (reached through "Prep for I2I", input already staged) and a fresh T2V
// both opened with "Choose a canvas size to generate." and a dead Generate. Two of the four
// generation pages. The rule: when width or height is unset, an i2i / i2v page takes the size of
// the image it was given, and any page takes its family's default. An explicit size is never
// overridden.

#include <QtTest>

#include <QApplication>
#include <QComboBox>
#include <QCoreApplication>
#include <QImage>
#include <QJsonArray>
#include <QJsonObject>
#include <QSettings>
#include <QSpinBox>
#include <QTemporaryDir>

#include "ImageGenerationPage.h"

namespace
{

struct CanvasSpins
{
    QSpinBox *width = nullptr;
    QSpinBox *height = nullptr;
};

// The two canvas spin boxes: range 0..8192 with the em-dash special value, in creation order.
CanvasSpins canvasSpins(ImageGenerationPage &page)
{
    CanvasSpins spins;
    for (QSpinBox *box : page.findChildren<QSpinBox *>())
    {
        if (box->maximum() != 8192 || box->specialValueText() != QStringLiteral("—"))
            continue;
        if (!spins.width)
            spins.width = box;
        else if (!spins.height)
            spins.height = box;
    }
    return spins;
}

// The frame and fps boxes, found by what they SAY rather than by creation order: the page has
// several spin boxes and their order is an implementation detail, while these two tooltips are the
// sentences the user reads.
QSpinBox *spinWithTooltipContaining(ImageGenerationPage &page, const QString &needle)
{
    for (QSpinBox *box : page.findChildren<QSpinBox *>())
    {
        if (box->toolTip().contains(needle, Qt::CaseInsensitive))
            return box;
    }
    return nullptr;
}

// wan's shape: two operating points, each carrying the canvas and the duration beside the sampling
// values -- which is what family_operating_points.py ships since W2 Task 1. Two rather than one on
// purpose: a single-point family hides the selector and never applies a bundle, so a one-point
// fixture would have tested the early-out instead of the applier.
QJsonObject familyTable(int width, int height, int frames, int fps)
{
    auto point = [&](const QString &name, int steps, double cfg) {
        QJsonObject params;
        params.insert(QStringLiteral("steps"), steps);
        params.insert(QStringLiteral("cfg"), cfg);
        params.insert(QStringLiteral("width"), width);
        params.insert(QStringLiteral("height"), height);
        params.insert(QStringLiteral("frames"), frames);
        params.insert(QStringLiteral("fps"), fps);
        QJsonObject out;
        out.insert(QStringLiteral("name"), name);
        out.insert(QStringLiteral("params"), params);
        return out;
    };
    QJsonObject table;
    table.insert(QStringLiteral("default_operating_point"), QStringLiteral("quality"));
    table.insert(QStringLiteral("operating_points"),
                 QJsonArray{point(QStringLiteral("quality"), 28, 4.0), point(QStringLiteral("fast"), 4, 1.0)});
    return table;
}

QString writePng(const QTemporaryDir &dir, const QString &name, const QSize &size)
{
    QImage image(size, QImage::Format_RGB32);
    image.fill(Qt::darkGray);
    const QString path = dir.filePath(name);
    image.save(path, "PNG");
    return path;
}

} // namespace

class CanvasSizeDefaultTest : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase()
    {
        // The page restores its last size from QSettings; the test must see an empty store, not
        // the developer's saved 1080x1920.
        QCoreApplication::setOrganizationName(QStringLiteral("DarkDuckTest"));
        QCoreApplication::setApplicationName(QStringLiteral("SpellVisionCanvasSizeTest"));
        QSettings settings;
        settings.clear();
        settings.sync();
    }

    void every_generation_page_opens_with_a_canvas_size_data()
    {
        QTest::addColumn<int>("mode");
        QTest::newRow("t2i") << static_cast<int>(ImageGenerationPage::Mode::TextToImage);
        QTest::newRow("i2i") << static_cast<int>(ImageGenerationPage::Mode::ImageToImage);
        QTest::newRow("t2v") << static_cast<int>(ImageGenerationPage::Mode::TextToVideo);
        QTest::newRow("i2v") << static_cast<int>(ImageGenerationPage::Mode::ImageToVideo);
    }

    void every_generation_page_opens_with_a_canvas_size()
    {
        QFETCH(int, mode);
        ImageGenerationPage page(static_cast<ImageGenerationPage::Mode>(mode));
        const CanvasSpins spins = canvasSpins(page);
        QVERIFY2(spins.width && spins.height, "canvas spin boxes not found");
        QVERIFY2(spins.width->value() >= 64 && spins.height->value() >= 64,
                 qPrintable(QStringLiteral("page opened at %1x%2 -- Generate would be blocked")
                                .arg(spins.width->value()).arg(spins.height->value())));
    }

    void a_video_page_defaults_to_a_landscape_video_canvas()
    {
        ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
        const CanvasSpins spins = canvasSpins(page);
        QVERIFY(spins.width && spins.height);
        QCOMPARE(spins.width->value(), 832);
        QCOMPARE(spins.height->value(), 480);
    }

    void an_unsized_i2i_page_takes_the_size_of_the_image_it_is_given()
    {
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const QString portrait = writePng(dir, QStringLiteral("portrait.png"), QSize(720, 1280));

        ImageGenerationPage page(ImageGenerationPage::Mode::ImageToImage);
        const CanvasSpins spins = canvasSpins(page);
        QVERIFY(spins.width && spins.height);
        // Back to the unsized state the live failure started from.
        spins.width->setValue(0);
        spins.height->setValue(0);

        page.useImageAsInput(portrait);
        QCOMPARE(spins.width->value(), 720);
        QCOMPARE(spins.height->value(), 1280);
    }

    void a_large_input_is_fitted_and_snapped_not_copied()
    {
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const QString huge = writePng(dir, QStringLiteral("huge.png"), QSize(3000, 4500));

        ImageGenerationPage page(ImageGenerationPage::Mode::ImageToImage);
        const CanvasSpins spins = canvasSpins(page);
        QVERIFY(spins.width && spins.height);
        spins.width->setValue(0);
        spins.height->setValue(0);

        page.useImageAsInput(huge);
        QVERIFY2(spins.width->value() <= 2048 && spins.height->value() <= 2048,
                 qPrintable(QStringLiteral("%1x%2 exceeds the 2048 long edge").arg(spins.width->value()).arg(spins.height->value())));
        QCOMPARE(spins.width->value() % 16, 0);
        QCOMPARE(spins.height->value() % 16, 0);
        QVERIFY(spins.width->value() >= 64 && spins.height->value() >= 64);
    }

    void an_explicit_size_is_not_overridden_by_an_input()
    {
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const QString portrait = writePng(dir, QStringLiteral("portrait.png"), QSize(720, 1280));

        ImageGenerationPage page(ImageGenerationPage::Mode::ImageToImage);
        const CanvasSpins spins = canvasSpins(page);
        QVERIFY(spins.width && spins.height);
        spins.width->setValue(1024);
        spins.height->setValue(1024);

        page.useImageAsInput(portrait);
        QCOMPARE(spins.width->value(), 1024);
        QCOMPARE(spins.height->value(), 1024);
    }

    // --- W2 Task 6: the canvas comes from the same answer as the sampling values -----------------

    void the_canvas_and_the_duration_come_from_the_resolved_answer()
    {
        ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
        const CanvasSpins spins = canvasSpins(page);
        QSpinBox *frames = spinWithTooltipContaining(page, QStringLiteral("Total frames"));
        QSpinBox *fps = spinWithTooltipContaining(page, QStringLiteral("frames per second"));
        QVERIFY(spins.width && spins.height && frames && fps);

        page.setOperatingPointsProvider([](const QString &) { return familyTable(640, 384, 33, 12); });
        page.pinVideoFamily(QStringLiteral("wan"));
        page.updateDisclosure(false);

        // Before W2 the canvas was mode-based only -- every video page opened 832x480 whatever the
        // family said -- and frames/fps kept the spin boxes' construction values.
        QCOMPARE(spins.width->value(), 640);
        QCOMPARE(spins.height->value(), 384);
        QCOMPARE(frames->value(), 33);
        QCOMPARE(fps->value(), 12);
    }

    void a_size_the_user_typed_is_not_overwritten()
    {
        ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
        const CanvasSpins spins = canvasSpins(page);
        QSpinBox *frames = spinWithTooltipContaining(page, QStringLiteral("Total frames"));
        QVERIFY(spins.width && spins.height && frames);

        page.setOperatingPointsProvider([](const QString &) { return familyTable(640, 384, 33, 12); });
        page.pinVideoFamily(QStringLiteral("wan"));
        page.updateDisclosure(false);
        QCOMPARE(spins.width->value(), 640);

        // A write from outside the page's own ProgrammaticWrite scope is exactly what a human
        // typing looks like, which is what makes this a real simulation rather than a poke at a flag.
        spins.width->setValue(1216);
        spins.height->setValue(704);
        frames->setValue(81);

        // The three triggers that re-run the appliers: a Simple/Advanced round trip, and the
        // family/operating-point refresh a model change fans out into.
        page.updateDisclosure(true);
        page.updateDisclosure(false);
        page.refreshOperatingPointSelector();
        page.refreshModelDefaults();

        QCOMPARE(spins.width->value(), 1216);
        QCOMPARE(spins.height->value(), 704);
        QCOMPARE(frames->value(), 81);
    }

    void a_simple_mode_aspect_choice_survives_the_same_way()
    {
        // Orientation in Simple is expressed through the Aspect presets (there is no separate
        // Portrait/Landscape toggle), and they are still literal pairs. What must hold is that
        // choosing one is treated as the user stating a size, not as a value the next family
        // default may quietly replace.
        ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
        const CanvasSpins spins = canvasSpins(page);
        QVERIFY(spins.width && spins.height);

        QComboBox *aspect = nullptr;
        for (QComboBox *combo : page.findChildren<QComboBox *>())
        {
            if (combo->findData(QStringLiteral("768x1024")) >= 0)
                aspect = combo;
        }
        QVERIFY2(aspect, "the Aspect preset combo was not found");

        page.setOperatingPointsProvider([](const QString &) { return familyTable(640, 384, 33, 12); });
        page.pinVideoFamily(QStringLiteral("wan"));
        page.updateDisclosure(false);

        aspect->setCurrentIndex(aspect->findData(QStringLiteral("768x1024")));
        QCOMPARE(spins.width->value(), 768);
        QCOMPARE(spins.height->value(), 1024);

        page.updateDisclosure(true);
        page.updateDisclosure(false);
        QCOMPARE(spins.width->value(), 768);
        QCOMPARE(spins.height->value(), 1024);
    }
};

QTEST_MAIN(CanvasSizeDefaultTest)
#include "test_canvas_size_default.moc"
