// W5 Task 2 -- the card shows what the site says.
//
// The Models page showed a filename. `<stem>.spellvision.json` has carried the site's own title,
// its cover picture, the site the metadata came from and the weight's quantisation since the
// intelligence pass ran over this library, and nothing on the page read any of it.
//
// Two rules here are not about layout and are the reason this file exists.
//
// **The file is never renamed.** The display name replaces the filename ON THE PAGE. The value
// the card hands the cockpit, the path it points at and the tooltip all stay the file on disk --
// an explicit owner requirement, and the kind of thing that is easy to satisfy on the day and
// quietly broken by a later convenience.
//
// **A model with no sidecar must not look like one that was identified and had nothing to say.**
// Those are different facts: one has an action behind it (run a refresh) and the other is a
// finished answer (the site does not have this file). Rendering them the same means the user
// cannot tell "we asked and found nothing" from "we never asked", and would go on re-running a
// refresh that will never change anything.
//
// Driven by REAL sidecars copied out of F:/AI_ASSETS/models. Copied rather than read in place:
// a model root on this box can come up BitLocker-locked, and a suite that reads one at test time
// fails for a reason that has nothing to do with the code under test.

#include <QtTest>

#include <QDir>
#include <QFile>
#include <QImage>
#include <QTemporaryDir>

#include "assets/ModelCardModel.h"
#include "assets/ModelIntelSidecar.h"
#include "shell/ProjectRoot.h"

using spellvision::assets::ModelCardModel;
using spellvision::assets::ModelIdentification;
using spellvision::assets::ModelIntel;
using spellvision::assets::ModelIntelImage;
using spellvision::assets::identificationCaption;
using spellvision::assets::previewShouldBlur;

namespace
{

QString fixtureDir()
{
    return QDir(spellvision::shell::resolveProjectRoot())
        .filePath(QStringLiteral("tests/fixtures/model_library"));
}

QString fixturePath(const QString &stem)
{
    return QDir(fixtureDir()).filePath(stem + QStringLiteral(".spellvision.json"));
}

ModelIntel realSidecar(const QString &stem)
{
    QFile file(fixturePath(stem));
    if (!file.open(QIODevice::ReadOnly))
        return {};
    return spellvision::assets::parseModelIntelDocument(file.readAll(), fixturePath(stem));
}

// The page's own card build, reduced to the two decisions this task owns: which string the card
// PRINTS, and which string it hands on. Written here rather than reaching into ModelManagerPage
// because the page needs a models root, a QSettings scope and a background scan to exist at all.
ModelCardModel::Card cardFor(const QString &fileName, const ModelIntel &intel, int nsfwCeiling = 2)
{
    ModelCardModel::Card card;
    card.fullName = fileName;
    QString stripped = fileName;
    if (stripped.endsWith(QStringLiteral(".safetensors"), Qt::CaseInsensitive))
        stripped.chop(QStringLiteral(".safetensors").size());
    card.strippedName = intel.displayName.trimmed().isEmpty() ? stripped : intel.displayName.trimmed();
    card.modelValue = fileName;
    card.nativePath = QStringLiteral("F:/AI_ASSETS/models/diffusion_models/") + fileName;
    card.kind = intel.kind;
    card.family = intel.family;
    card.quantisation = intel.quantisation;
    card.identification = intel.identification();
    if (intel.identified())
        card.siteBadge = intel.primarySource().siteLabel();
    const ModelIntelImage cover = intel.coverImage();
    card.previewPath = cover.localPath;
    card.previewNsfwLevel = cover.nsfwLevel;
    card.blurPreview = previewShouldBlur(cover.nsfwLevel, nsfwCeiling);
    return card;
}

QVariant roleOf(const ModelCardModel &model, int row, int role)
{
    return model.index(row, 0).data(role);
}

} // namespace

class TestModelCardSidecar : public QObject
{
    Q_OBJECT

private slots:
    void the_card_prints_the_name_the_site_gave_the_file();
    void the_file_is_never_renamed();
    void the_badge_names_the_site_the_metadata_came_from();
    void quantisation_separates_variants_that_share_one_name();
    void a_model_with_no_sidecar_reads_as_never_asked();
    void identified_with_nothing_found_is_not_the_same_as_never_asked();
    void the_cover_comes_from_the_sidecar();
    void a_preview_above_the_nsfw_setting_is_blurred();
    void the_local_path_is_normalised_off_the_native_spelling();
    void a_sidecar_that_is_not_json_is_an_absent_sidecar_not_a_crash();
};

void TestModelCardSidecar::the_card_prints_the_name_the_site_gave_the_file()
{
    const ModelIntel intel = realSidecar(QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4"));
    QVERIFY2(intel.present, qPrintable(fixturePath(QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4"))));
    QVERIFY(intel.identified());

    ModelCardModel model;
    model.setCards({cardFor(QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4.safetensors"), intel)});

    const QString printed = roleOf(model, 0, ModelCardModel::StrippedNameRole).toString();
    QVERIFY2(printed.startsWith(QStringLiteral("Lox")), qPrintable(printed));
    QVERIFY2(printed.contains(QStringLiteral("Krea 2")), qPrintable(printed));
    QVERIFY2(!printed.contains(QStringLiteral("safetensors")), qPrintable(printed));
    QVERIFY2(printed != QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4"), qPrintable(printed));

    // A LoRA too, so this is not one hand-picked document.
    const ModelIntel lora = realSidecar(QStringLiteral("Detailer-KREA2"));
    QCOMPARE(lora.displayName, QStringLiteral("[KREA 2] Detail Slider"));
}

void TestModelCardSidecar::the_file_is_never_renamed()
{
    const ModelIntel intel = realSidecar(QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4"));
    const QString fileName = QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4.safetensors");

    ModelCardModel model;
    model.setCards({cardFor(fileName, intel)});

    // What the cockpit is handed, what the page points at, and what the tooltip says are all the
    // FILE. The display name lives on the card face and nowhere else.
    QCOMPARE(roleOf(model, 0, ModelCardModel::ModelValueRole).toString(), fileName);
    QCOMPARE(roleOf(model, 0, ModelCardModel::FullNameRole).toString(), fileName);
    QVERIFY(roleOf(model, 0, ModelCardModel::NativePathRole).toString().endsWith(fileName));
    QVERIFY2(roleOf(model, 0, Qt::ToolTipRole).toString().contains(fileName),
             qPrintable(roleOf(model, 0, Qt::ToolTipRole).toString()));
    QVERIFY(roleOf(model, 0, ModelCardModel::StrippedNameRole).toString() != fileName);
}

void TestModelCardSidecar::the_badge_names_the_site_the_metadata_came_from()
{
    const ModelIntel intel = realSidecar(QStringLiteral("Detailer-KREA2"));
    QVERIFY(intel.identified());
    QCOMPARE(intel.primarySource().site, QStringLiteral("civitai"));
    QCOMPARE(intel.primarySource().siteLabel(), QStringLiteral("CivitAI"));
    QVERIFY(intel.primarySource().url.startsWith(QStringLiteral("https://civitai.com/models/")));
    QCOMPARE(intel.primarySource().modelId, Q_INT64_C(2729908));

    ModelCardModel model;
    model.setCards({cardFor(QStringLiteral("Detailer-KREA2.safetensors"), intel)});
    QCOMPARE(roleOf(model, 0, ModelCardModel::SiteBadgeRole).toString(), QStringLiteral("CivitAI"));
    QCOMPARE(roleOf(model, 0, ModelCardModel::IdentificationRole).toInt(),
             static_cast<int>(ModelIdentification::Identified));
    // Nothing to explain when the badge is there.
    QVERIFY(roleOf(model, 0, ModelCardModel::IdentificationCaptionRole).toString().isEmpty());

    // The other site the reader knows, from a document shaped like the ones the HF lane writes.
    const QByteArray hfDocument =
        "{\"schema\":\"spellvision.model-sidecar/1\","
        " \"identity\":{\"kind\":\"diffusion_model\",\"sources\":["
        "   {\"site\":\"huggingface\","
        "    \"url\":\"https://huggingface.co/black-forest-labs/FLUX.1-dev\"}]}}";
    const ModelIntel hf = spellvision::assets::parseModelIntelDocument(hfDocument);
    QCOMPARE(hf.primarySource().siteLabel(), QStringLiteral("HuggingFace"));
}

void TestModelCardSidecar::quantisation_separates_variants_that_share_one_name()
{
    // Three real Lox sidecars. Two of them print the SAME display name and carry the same cover
    // picture -- the quantisation is the only thing on the card that tells them apart, which is
    // why it is a chip and not a line in the inspector.
    const ModelIntel nvfp4 = realSidecar(QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4"));
    const ModelIntel bf16 = realSidecar(QStringLiteral("loxsUtopicWorldKrea2_v20BF16"));
    QVERIFY(nvfp4.present && bf16.present);

    QCOMPARE(nvfp4.displayName, bf16.displayName);
    QCOMPARE(nvfp4.quantisation, QStringLiteral("nvfp4"));
    QCOMPARE(bf16.quantisation, QStringLiteral("bf16"));

    ModelCardModel model;
    model.setCards({cardFor(QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4.safetensors"), nvfp4),
                    cardFor(QStringLiteral("loxsUtopicWorldKrea2_v20BF16.safetensors"), bf16)});
    QCOMPARE(roleOf(model, 0, ModelCardModel::StrippedNameRole).toString(),
             roleOf(model, 1, ModelCardModel::StrippedNameRole).toString());
    QVERIFY(roleOf(model, 0, ModelCardModel::QuantisationRole).toString()
            != roleOf(model, 1, ModelCardModel::QuantisationRole).toString());

    const ModelIntel fp8 = realSidecar(QStringLiteral("krea2_turbo_fp8_scaled"));
    QCOMPARE(fp8.quantisation, QStringLiteral("fp8"));
}

void TestModelCardSidecar::a_model_with_no_sidecar_reads_as_never_asked()
{
    QTemporaryDir tmp;
    QVERIFY(tmp.isValid());
    const QString weight = QDir(tmp.path()).filePath(QStringLiteral("nobody_looked.safetensors"));
    QFile file(weight);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write("not a real weight");
    file.close();

    const ModelIntel intel = spellvision::assets::readModelIntel(weight);
    QVERIFY(!intel.present);
    QCOMPARE(intel.identification(), ModelIdentification::NeverAsked);

    ModelCardModel model;
    model.setCards({cardFor(QStringLiteral("nobody_looked.safetensors"), intel)});
    // The filename, because there is nothing else to show.
    QCOMPARE(roleOf(model, 0, ModelCardModel::StrippedNameRole).toString(),
             QStringLiteral("nobody_looked"));
    QVERIFY(roleOf(model, 0, ModelCardModel::SiteBadgeRole).toString().isEmpty());
    QCOMPARE(roleOf(model, 0, ModelCardModel::IdentificationCaptionRole).toString(),
             QStringLiteral("Not identified yet"));
}

void TestModelCardSidecar::identified_with_nothing_found_is_not_the_same_as_never_asked()
{
    // The real sd3.5 sidecar: the refresh ran, hashed 11 GB, asked CivitAI and got nothing back.
    // `sources` is empty, `images` is empty and the name fell back to the file stem -- so every
    // FIELD looks like the no-sidecar case, and only the sidecar's existence tells them apart.
    const ModelIntel found = realSidecar(QStringLiteral("sd3.5_medium_incl_clips_t5xxlfp8scaled"));
    QVERIFY(found.present);
    QVERIFY(found.sources.isEmpty());
    QVERIFY(found.images.isEmpty());
    QCOMPARE(found.identification(), ModelIdentification::NothingFound);

    QTemporaryDir tmp;
    QVERIFY(tmp.isValid());
    const QString weight = QDir(tmp.path()).filePath(QStringLiteral("nobody_looked.safetensors"));
    QFile file(weight);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.close();
    const ModelIntel never = spellvision::assets::readModelIntel(weight);

    QVERIFY(found.identification() != never.identification());

    // And the difference reaches the user as two different sentences, not as two enum values that
    // render identically.
    const QString askedCaption = identificationCaption(found.identification());
    const QString neverCaption = identificationCaption(never.identification());
    QVERIFY(!askedCaption.isEmpty());
    QVERIFY(!neverCaption.isEmpty());
    QVERIFY2(askedCaption != neverCaption, qPrintable(askedCaption));
    QCOMPARE(askedCaption, QStringLiteral("No match on any site"));
    QCOMPARE(identificationCaption(ModelIdentification::Identified), QString());

    ModelCardModel model;
    model.setCards({cardFor(QStringLiteral("sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors"), found),
                    cardFor(QStringLiteral("nobody_looked.safetensors"), never)});
    QVERIFY(roleOf(model, 0, ModelCardModel::IdentificationCaptionRole).toString()
            != roleOf(model, 1, ModelCardModel::IdentificationCaptionRole).toString());
}

void TestModelCardSidecar::the_cover_comes_from_the_sidecar()
{
    const ModelIntel intel = realSidecar(QStringLiteral("Detailer-KREA2"));
    QCOMPARE(intel.images.size(), 6);

    const ModelIntelImage cover = intel.coverImage();
    QVERIFY(cover.isCover);
    QVERIFY2(cover.localPath.contains(QStringLiteral(".spellvision/previews/")), qPrintable(cover.localPath));
    QVERIFY2(cover.localPath.contains(intel.sha256), qPrintable(cover.localPath));
    QVERIFY(cover.localPath.endsWith(QStringLiteral("/0.jpg")));
    QCOMPARE(cover.originUrl.isEmpty(), false);

    // A weight the site knows nothing about has no cover, and the reader says so with an empty
    // path rather than by handing back a broken one.
    const ModelIntel none = realSidecar(QStringLiteral("sd3.5_medium_incl_clips_t5xxlfp8scaled"));
    QVERIFY(none.coverPath().isEmpty());
}

void TestModelCardSidecar::a_preview_above_the_nsfw_setting_is_blurred()
{
    // The real Lox sidecar. Its MODEL-level nsfw_level is 60; its pictures are level 2, which is
    // the ceiling `download_previews` fetches at -- so at the default setting the pictures the
    // refresh was willing to download are exactly the pictures the page is willing to show.
    const ModelIntel lox = realSidecar(QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4"));
    QCOMPARE(lox.nsfwLevel, 60);
    QCOMPARE(lox.coverImage().nsfwLevel, 2);

    ModelCardModel model;
    model.setCards({cardFor(QStringLiteral("lox.safetensors"), lox, /*nsfwCeiling=*/2),
                    cardFor(QStringLiteral("lox.safetensors"), lox, /*nsfwCeiling=*/1)});
    QCOMPARE(roleOf(model, 0, ModelCardModel::BlurPreviewRole).toBool(), false);
    QCOMPARE(roleOf(model, 1, ModelCardModel::BlurPreviewRole).toBool(), true);

    // The rule itself. An UNRATED picture (level 0) is not "safe" -- but it is also not above any
    // non-negative ceiling, so it renders, and a user who sets the ceiling below zero gets
    // everything blurred rather than everything through.
    QVERIFY(!previewShouldBlur(0, 2));
    QVERIFY(!previewShouldBlur(2, 2));
    QVERIFY(previewShouldBlur(3, 2));
    QVERIFY(previewShouldBlur(1, 0));
    QVERIFY(previewShouldBlur(0, -1));
}

void TestModelCardSidecar::the_local_path_is_normalised_off_the_native_spelling()
{
    // Python writes `local_path` with Windows separators (`F:\AI_ASSETS\...`). Every consumer here
    // -- QPixmap, the thumbnail cache, QFileInfo -- gets one spelling, so a cache key built from
    // the path cannot come out two different ways for one picture.
    const ModelIntel intel = realSidecar(QStringLiteral("Detailer-KREA2"));
    for (const ModelIntelImage &image : intel.images)
    {
        QVERIFY2(!image.localPath.contains(QLatin1Char('\\')), qPrintable(image.localPath));
        QVERIFY(image.localPath.contains(QLatin1Char('/')));
    }

    QFile raw(fixturePath(QStringLiteral("Detailer-KREA2")));
    QVERIFY(raw.open(QIODevice::ReadOnly));
    QVERIFY2(QString::fromUtf8(raw.readAll()).contains(QStringLiteral("\\\\AI_ASSETS\\\\")),
             "the fixture no longer carries native separators, so this case proves nothing");
}

void TestModelCardSidecar::a_sidecar_that_is_not_json_is_an_absent_sidecar_not_a_crash()
{
    QTemporaryDir tmp;
    QVERIFY(tmp.isValid());
    const QString weight = QDir(tmp.path()).filePath(QStringLiteral("half_written.safetensors"));
    QFile sidecar(QDir(tmp.path()).filePath(QStringLiteral("half_written.spellvision.json")));
    QVERIFY(sidecar.open(QIODevice::WriteOnly));
    sidecar.write("{\"identity\": {\"kind\": \"lo");  // a refresh killed mid-write
    sidecar.close();

    const ModelIntel intel = spellvision::assets::readModelIntel(weight);
    QVERIFY(!intel.present);
    QCOMPARE(intel.identification(), ModelIdentification::NeverAsked);
    QVERIFY(intel.coverPath().isEmpty());
}

QTEST_MAIN(TestModelCardSidecar)
#include "test_model_card_sidecar.moc"
