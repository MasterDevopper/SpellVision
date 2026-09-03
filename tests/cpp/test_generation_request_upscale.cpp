// The last hop: a tier the user set in the cockpit has to arrive in the request.
//
// `GenerationRequestBuilder::build` is pure and static and had no test, which is how the upscale
// keys spent their whole life fenced to image modes without anything noticing. The fence itself was
// correct while the row was hidden in video -- hidden widgets keep their values, so an unfenced
// build would have sent an `upscale_enabled` nobody could see or unset. What was missing was
// anything that would notice when the premise changed.
//
// It changed on 2026-09-03: the row is offered in video modes, the graft reaches every native video
// family's CreateVideo sink, and the keys are read. Measured through the shipping builder, LTX
// two-stage 768x512x49f with seeds varied so neither run was served a cached latent -- baseline peak
// 31.55 GB, with the upscale 31.70 GB, output 3072x2048x49f.

#include <QtTest>

#include <QJsonObject>

#include "generation/GenerationRequestBuilder.h"

using spellvision::generation::GenerationRequestBuilder;
using spellvision::generation::GenerationRequestDraft;

namespace
{
GenerationRequestDraft draftWithUpscale(const QString &mode, bool video)
{
    GenerationRequestDraft draft;
    draft.mode = mode;
    draft.isVideoMode = video;
    draft.prompt = QStringLiteral("a calm ocean wave");
    draft.model = QStringLiteral("D:/AI_ASSETS/models/checkpoints/ltx/ltx-2.3-22b-dev.safetensors");
    draft.modelFamily = video ? QStringLiteral("ltx") : QStringLiteral("anima");
    draft.upscaleEnabled = true;
    draft.upscaleMethod = QStringLiteral("model");
    draft.upscaleScale = 2.0;
    draft.upscaleModel = QStringLiteral("4x-UltraSharp.pth");
    return draft;
}
} // namespace

class GenerationRequestUpscaleTest : public QObject
{
    Q_OBJECT

private slots:
    void aVideoRequestCarriesTheUpscaleTheUserSet();
    void animageRequestStillCarriesIt();
    void offTravelsAsOffRatherThanAsAbsence();
};

void GenerationRequestUpscaleTest::aVideoRequestCarriesTheUpscaleTheUserSet()
{
    const QJsonObject r = GenerationRequestBuilder::build(draftWithUpscale(QStringLiteral("t2v"), true));

    QVERIFY2(r.contains(QStringLiteral("upscale_enabled")),
             "the cockpit offers the tier in video modes; a request that drops the key means the "
             "user sets it and nothing happens");
    QCOMPARE(r.value(QStringLiteral("upscale_enabled")).toBool(), true);
    QCOMPARE(r.value(QStringLiteral("upscale_method")).toString(), QStringLiteral("model"));
    QCOMPARE(r.value(QStringLiteral("upscale_scale")).toDouble(), 2.0);
    QCOMPARE(r.value(QStringLiteral("upscale_model_name")).toString(), QStringLiteral("4x-UltraSharp.pth"));
}

void GenerationRequestUpscaleTest::animageRequestStillCarriesIt()
{
    const QJsonObject r = GenerationRequestBuilder::build(draftWithUpscale(QStringLiteral("t2i"), false));
    QCOMPARE(r.value(QStringLiteral("upscale_enabled")).toBool(), true);
    QCOMPARE(r.value(QStringLiteral("upscale_scale")).toDouble(), 2.0);
}

void GenerationRequestUpscaleTest::offTravelsAsOffRatherThanAsAbsence()
{
    // A missing key and a false one are the same to a `req.get(...)` reader, but not to a human
    // reading a recorded request, and not to the request-keys-have-readers sweep. Off is stated.
    GenerationRequestDraft draft = draftWithUpscale(QStringLiteral("t2v"), true);
    draft.upscaleEnabled = false;
    draft.upscaleMethod = QStringLiteral("none");
    draft.upscaleScale = 1.0;
    draft.upscaleModel.clear();

    const QJsonObject r = GenerationRequestBuilder::build(draft);
    QVERIFY(r.contains(QStringLiteral("upscale_enabled")));
    QCOMPARE(r.value(QStringLiteral("upscale_enabled")).toBool(), false);
    QVERIFY2(!r.contains(QStringLiteral("upscale_model_name")),
             "an empty model name is not a choice and does not travel as one");
}

QTEST_MAIN(GenerationRequestUpscaleTest)
#include "test_generation_request_upscale.moc"
