// Full-res preview decode used to run on the GUI thread at the moment a render
// finished — the worst possible time. A cold load must return without the pixmap
// and without blocking; the cache fills when the worker thread finishes.

#include <QtTest>

#include <QDir>
#include <QElapsedTimer>
#include <QImage>
#include <QLabel>
#include <QTemporaryDir>

#include "preview/ImagePreviewController.h"

using spellvision::preview::ImagePreviewController;

class ImagePreviewControllerTest : public QObject
{
    Q_OBJECT

private slots:
    void a_cold_load_does_not_decode_on_the_caller();
    void destroying_the_controller_mid_decode_does_not_crash();
};

void ImagePreviewControllerTest::a_cold_load_does_not_decode_on_the_caller()
{
    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    QImage image(QSize(512, 512), QImage::Format_RGB32);
    image.fill(Qt::darkCyan);
    const QString path = dir.filePath(QStringLiteral("out.png"));
    QVERIFY(image.save(path, "PNG"));

    ImagePreviewController controller;
    QElapsedTimer timer;
    timer.start();
    const bool ready = controller.loadPixmapIntoCache(path);
    const qint64 elapsed = timer.elapsed();

    QVERIFY2(elapsed < 150,
             qPrintable(QStringLiteral("cold load blocked the caller for %1 ms").arg(elapsed)));
    QVERIFY2(!ready, "a cold load must not decode on the caller");
    QVERIFY(!controller.hasCachedPixmap());

    QTRY_VERIFY_WITH_TIMEOUT(controller.hasCachedPixmap(), 5000);
    QVERIFY(!controller.cachedPixmap().isNull());
}

void ImagePreviewControllerTest::destroying_the_controller_mid_decode_does_not_crash()
{
    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    QImage image(QSize(256, 256), QImage::Format_RGB32);
    image.fill(Qt::darkMagenta);
    const QString path = dir.filePath(QStringLiteral("gone.png"));
    QVERIFY(image.save(path, "PNG"));

    auto *controller = new ImagePreviewController;
    QVERIFY(!controller->loadPixmapIntoCache(path));
    delete controller;
    QTest::qWait(200);
}

QTEST_MAIN(ImagePreviewControllerTest)
#include "test_image_preview_controller.moc"
