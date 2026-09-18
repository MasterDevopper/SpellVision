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
#include <QLabel>
#include <QCoreApplication>
#include <QImage>
#include <QJsonArray>
#include <QJsonObject>
#include <QLineEdit>
#include <QPushButton>
#include <QSettings>
#include <QSignalSpy>
#include <QSpinBox>
#include <QTemporaryDir>

#include "DatasetGenerationPage.h"
#include "ImageGenerationPage.h"
#include "workers/WorkerRequestBuilder.h"

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

// The video "Primary" checkpoint combo, found by the label beside it -- the same identification
// tests/cpp/test_model_defaults_apply.cpp uses, and for the same reason: its currentIndexChanged
// handler calls the private setSelectedModel(), so driving it simulates a real checkpoint pick
// rather than reaching around one. A model CHANGE is the event clearUserEditedFields() runs on, and
// without it this file's staged-canvas case could not fail however the flags behaved.
QComboBox *videoPrimaryModelComboOf(ImageGenerationPage &page)
{
    for (QLabel *label : page.findChildren<QLabel *>())
    {
        if (label->text() != QStringLiteral("Primary"))
            continue;
        if (QWidget *cell = label->parentWidget())
        {
            if (QComboBox *combo = cell->findChild<QComboBox *>())
                return combo;
        }
    }
    return nullptr;
}

// --- the dataset page's half of the same question -----------------------------------------------

// The dataset page's canvas spins: range 0..2048 with the em-dash special value. Same shape as the
// cockpit's, different maximum, and they live inside the Advanced block.
CanvasSpins datasetCanvasSpins(DatasetGenerationPage &page)
{
    CanvasSpins spins;
    for (QSpinBox *box : page.findChildren<QSpinBox *>())
    {
        if (box->maximum() != 2048 || box->specialValueText() != QStringLiteral("—"))
            continue;
        if (!spins.width)
            spins.width = box;
        else if (!spins.height)
            spins.height = box;
    }
    return spins;
}

// The read-only line the page shows about the canvas, found by what it SAYS. An object name would
// be an implementation detail; this sentence is the thing the ruling is about -- Dataset inherits
// the cockpit canvas AND SAYS SO -- so the test looks for it the way a user would.
QLabel *canvasCaptionOf(DatasetGenerationPage &page)
{
    for (QLabel *label : page.findChildren<QLabel *>())
    {
        if (label->text().startsWith(QStringLiteral("Canvas:")))
            return label;
    }
    return nullptr;
}

QPushButton *buttonWithText(DatasetGenerationPage &page, const QString &text)
{
    for (QPushButton *button : page.findChildren<QPushButton *>())
    {
        if (button->text() == text)
            return button;
    }
    return nullptr;
}

// The page refuses on an empty destination before it ever looks at the canvas, so every generate
// case has to get past that first. The single QLineEdit on the page is the output directory.
void stageOutputFolder(DatasetGenerationPage &page, const QString &path)
{
    if (QLineEdit *edit = page.findChild<QLineEdit *>())
        edit->setText(path);
}

// The page's own status line -- where the refusal sentence lands.
QLabel *previewLabelOf(DatasetGenerationPage &page)
{
    return page.findChild<QLabel *>(QStringLiteral("DatasetPreview"));
}

// What ImageGenerationPage::buildRequestPayload hands the shell. 768x1344 rather than a round
// number on purpose: a case that passed because page and cockpit happened to agree on 1024 would
// prove nothing, and 1024 is the exact house default this change removed.
QJsonObject cockpitDraftWithCanvas(int width, int height)
{
    QJsonObject draft;
    draft.insert(QStringLiteral("model"), QStringLiteral("krea2.safetensors"));
    if (width > 0)
        draft.insert(QStringLiteral("width"), width);
    if (height > 0)
        draft.insert(QStringLiteral("height"), height);
    return draft;
}

// generateDataset() writes train/lastDatasetRoot into the REAL DarkDuck/SpellVision store -- it
// constructs its own QSettings with those names rather than using the application's, so the test
// harness's organisation name does not contain it. Saved and put back, so running the suite does
// not repoint the Train page at a temporary directory that no longer exists.
class RestoreDatasetRootSetting
{
public:
    RestoreDatasetRootSetting()
        : settings_(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision")),
          had_(settings_.contains(QStringLiteral("train/lastDatasetRoot"))),
          previous_(settings_.value(QStringLiteral("train/lastDatasetRoot")))
    {
    }

    ~RestoreDatasetRootSetting()
    {
        if (had_)
            settings_.setValue(QStringLiteral("train/lastDatasetRoot"), previous_);
        else
            settings_.remove(QStringLiteral("train/lastDatasetRoot"));
    }

private:
    QSettings settings_;
    bool had_ = false;
    QVariant previous_;
};

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
        // The Aspect presets are literal pairs, and choosing one is the user stating a size -- not
        // a value the next family default may quietly replace. Orientation is a DIFFERENT control
        // (added 2026-09-16, spec 2.2): it swaps the resolved pair instead of replacing it, and is
        // covered by tests/cpp/test_model_defaults_apply.cpp. This comment used to say Aspect was
        // the only orientation there was, which recorded a missing feature in a place nobody
        // reading the ledger would find it.
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

    void a_canvas_taken_from_the_staged_image_survives_a_model_change()
    {
        // ensureCanvasSizeDefault marks the canvas when it came from the image the user staged,
        // with a comment saying "a checkpoint picked afterwards must not resize their input out
        // from under them". setSelectedModel then called clearUserEditedFields() on EVERY model
        // change -- performing the sentence the comment forbids. Stage a 1280x720 keyframe on I2V,
        // pick a wan checkpoint, and it became 832x480.
        //
        // Both rules were right and neither was wrong: a deliberate model change IS a request for
        // that model's numbers, and a staged keyframe's shape IS the shape the user asked for. What
        // was missing is that they are two different facts sharing one set.
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const QString keyframe = writePng(dir, QStringLiteral("keyframe.png"), QSize(1280, 720));

        ImageGenerationPage page(ImageGenerationPage::Mode::ImageToVideo);
        const CanvasSpins spins = canvasSpins(page);
        QVERIFY(spins.width && spins.height);
        spins.width->setValue(0);
        spins.height->setValue(0);

        page.useImageAsInput(keyframe);
        QCOMPARE(spins.width->value(), 1280);
        QCOMPARE(spins.height->value(), 720);

        // A REAL model change, through the combo whose handler calls setSelectedModel(). That is
        // the event clearUserEditedFields() runs on, and it is the whole subject: a version of this
        // test that only refreshed the operating point passed against the planted defect, because
        // the flags were never cleared and nothing was ever overwritten.
        page.setOperatingPointsProvider([](const QString &) { return familyTable(832, 480, 81, 16); });
        page.pinVideoFamily(QStringLiteral("wan"));
        QComboBox *primary = videoPrimaryModelComboOf(page);
        QVERIFY2(primary, "primary video model combo not found");
        const int index = primary->count();
        primary->addItem(QStringLiteral("wan checkpoint"),
                         QStringLiteral("D:/AI_ASSETS/models/diffusion_models/wan2.2_t2v.safetensors"));
        if (primary->currentIndex() != index)
            primary->setCurrentIndex(index);
        page.refreshOperatingPointSelector();
        page.updateDisclosure(true);
        page.updateDisclosure(false);
        page.refreshModelDefaults();

        QCOMPARE(spins.width->value(), 1280);
        QCOMPARE(spins.height->value(), 720);
    }

    void staging_a_different_image_does_replace_the_canvas_it_gave()
    {
        // The other half, and the reason this is a second SET rather than a flag that is never
        // cleared: the mark protects a size against a model change, not against the content it came
        // from being replaced. Without this, the first keyframe's shape would outlive the keyframe.
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const QString first = writePng(dir, QStringLiteral("first.png"), QSize(1280, 720));
        const QString second = writePng(dir, QStringLiteral("second.png"), QSize(720, 1280));

        ImageGenerationPage page(ImageGenerationPage::Mode::ImageToVideo);
        const CanvasSpins spins = canvasSpins(page);
        QVERIFY(spins.width && spins.height);
        spins.width->setValue(0);
        spins.height->setValue(0);

        page.useImageAsInput(first);
        QCOMPARE(spins.width->value(), 1280);

        spins.width->setValue(0);
        spins.height->setValue(0);
        page.useImageAsInput(second);
        QCOMPARE(spins.width->value(), 720);
        QCOMPARE(spins.height->value(), 1280);
    }

    // --- Doc 62: Dataset in Simple inherits the cockpit canvas, and says so ---------------------
    //
    // adb1c97 removed the house default from the two dataset canvas spins -- correctly, it stated a
    // size nobody chose. But those spins live in the Advanced block, so a Simple user was left
    // pressing Generate and reading "Choose a canvas size to generate." beside no canvas control at
    // all. The old default had been masking a dead end rather than causing it.
    //
    // The ruling is inheritance, stated: the size comes from Text to Image, the page names it
    // before the user commits, and the substitution happens in ONE place -- the shell's
    // mergeDatasetRequestFromCockpit, which until now could not run, because the page refused
    // before emitting anything it could act on. These cases drive the page and then run what it
    // emits through that merge, which is the whole of the path the worker sees.

    void a_simple_dataset_page_generates_with_the_canvas_it_inherited()
    {
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const RestoreDatasetRootSetting guard;

        DatasetGenerationPage page;
        page.updateDisclosure(false); // Simple: the width/height spins are not on screen
        stageOutputFolder(page, dir.path());
        page.setInheritedCanvas(768, 1344);

        QSignalSpy submitted(&page, &DatasetGenerationPage::generateDatasetRequested);
        QPushButton *generate = buttonWithText(page, QStringLiteral("Generate Dataset"));
        QVERIFY2(generate, "the Generate Dataset button was not found");
        generate->click();

        QCOMPARE(submitted.count(), 1);
        const QJsonObject payload = submitted.at(0).at(0).toJsonObject();
        // The page reports its canvas as UNSET. It does not copy the inherited numbers in: the rule
        // would then live in two places, which is the duplication this codebase keeps paying for.
        QCOMPARE(payload.value(QStringLiteral("width")).toInt(), 0);
        QCOMPARE(payload.value(QStringLiteral("height")).toInt(), 0);

        // ...and what reaches the worker carries the cockpit's canvas.
        const QJsonObject merged = spellvision::workers::mergeDatasetRequestFromCockpit(
            payload, cockpitDraftWithCanvas(768, 1344));
        QCOMPARE(merged.value(QStringLiteral("width")).toInt(), 768);
        QCOMPARE(merged.value(QStringLiteral("height")).toInt(), 1344);
    }

    void a_simple_dataset_page_with_nothing_to_inherit_still_refuses()
    {
        // The gate is not relaxed. It now fires on the case it was always for -- nothing anywhere
        // states a canvas -- and it keeps the same words, because they are still the right words.
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const RestoreDatasetRootSetting guard;

        DatasetGenerationPage page;
        page.updateDisclosure(false);
        stageOutputFolder(page, dir.path());
        page.setInheritedCanvas(0, 0);

        QSignalSpy submitted(&page, &DatasetGenerationPage::generateDatasetRequested);
        QPushButton *generate = buttonWithText(page, QStringLiteral("Generate Dataset"));
        QVERIFY(generate);
        generate->click();

        QCOMPARE(submitted.count(), 0);
        QLabel *preview = previewLabelOf(page);
        QVERIFY(preview);
        QCOMPARE(preview->text(), QStringLiteral("Choose a canvas size to generate."));
    }

    void a_stated_dataset_canvas_outranks_the_inherited_one()
    {
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const RestoreDatasetRootSetting guard;

        DatasetGenerationPage page;
        page.updateDisclosure(true); // Advanced: the spins are revealed in place
        stageOutputFolder(page, dir.path());
        page.setInheritedCanvas(768, 1344);

        const CanvasSpins spins = datasetCanvasSpins(page);
        QVERIFY2(spins.width && spins.height, "the dataset canvas spin boxes were not found");
        spins.width->setValue(512);
        spins.height->setValue(512);

        QSignalSpy submitted(&page, &DatasetGenerationPage::generateDatasetRequested);
        QPushButton *generate = buttonWithText(page, QStringLiteral("Generate Dataset"));
        QVERIFY(generate);
        generate->click();

        QCOMPARE(submitted.count(), 1);
        const QJsonObject payload = submitted.at(0).at(0).toJsonObject();
        QCOMPARE(payload.value(QStringLiteral("width")).toInt(), 512);
        const QJsonObject merged = spellvision::workers::mergeDatasetRequestFromCockpit(
            payload, cockpitDraftWithCanvas(768, 1344));
        QCOMPARE(merged.value(QStringLiteral("width")).toInt(), 512);
        QCOMPARE(merged.value(QStringLiteral("height")).toInt(), 512);
    }

    void the_caption_names_the_inherited_canvas_and_where_it_came_from()
    {
        // Saying it is the point of the ruling. A silent inheritance would be exactly the hidden
        // output-changing state the v0.1.0 hardening pass was about, and from the user's side of
        // the screen it would be indistinguishable from a house default.
        DatasetGenerationPage page;
        page.setInheritedCanvas(768, 1344);
        page.updateDisclosure(false);

        QLabel *caption = canvasCaptionOf(page);
        QVERIFY2(caption, "the page states no canvas anywhere");
        QVERIFY2(caption->text().contains(QStringLiteral("768"))
                     && caption->text().contains(QStringLiteral("1344")),
                 qPrintable(caption->text()));
        QVERIFY2(caption->text().contains(QStringLiteral("Text to Image")), qPrintable(caption->text()));

        // Visible in SIMPLE -- the mode that has no canvas control. A caption that only appeared
        // beside the spins would be telling the one user who can already see the answer.
        QVERIFY2(caption->isVisibleTo(&page), "the canvas caption is hidden in Simple");
        const CanvasSpins spins = datasetCanvasSpins(page);
        QVERIFY(spins.width);
        QVERIFY2(!spins.width->isVisibleTo(&page), "Simple is showing the Advanced canvas spins");

        // Advanced reveals the spins IN PLACE; it does not take the sentence away.
        page.updateDisclosure(true);
        QVERIFY(caption->isVisibleTo(&page));
        QVERIFY(spins.width->isVisibleTo(&page));
    }

    void a_page_with_nothing_to_inherit_says_so_rather_than_naming_a_size()
    {
        DatasetGenerationPage page;
        page.updateDisclosure(false);
        QLabel *caption = canvasCaptionOf(page);
        QVERIFY(caption);
        QVERIFY2(!caption->text().contains(QStringLiteral("1024")), qPrintable(caption->text()));
        QVERIFY2(caption->text().contains(QStringLiteral("not set")), qPrintable(caption->text()));
    }
};

QTEST_MAIN(CanvasSizeDefaultTest)
#include "test_canvas_size_default.moc"
