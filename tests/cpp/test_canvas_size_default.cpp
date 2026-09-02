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
#include <QCoreApplication>
#include <QImage>
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
};

QTEST_MAIN(CanvasSizeDefaultTest)
#include "test_canvas_size_default.moc"
