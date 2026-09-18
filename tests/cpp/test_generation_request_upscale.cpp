// The last hop: a value the user set in the cockpit has to arrive in the request.
//
// Two fields, one property. The upscale tier is the case the file was written for;
// `guidance` joined it on 2026-09-18 (Doc 62 3e) because it is the SAME defect one field
// over -- `GenerationRequestBuilder::build` is the only place either can be dropped, and a
// dropped key means the user sets a control and nothing happens.
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
    void flux3StatesOffRatherThanTheLastVideoTier();
    void aStatedGuidanceReachesTheRequest();
    void autoGuidanceIsAbsentRatherThanAZero();
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

void GenerationRequestUpscaleTest::flux3StatesOffRatherThanTheLastVideoTier()
{
    GenerationRequestDraft draft = draftWithUpscale(QStringLiteral("t2v"), true);
    draft.modelFamily = QStringLiteral("flux3");
    draft.model = QStringLiteral("flux3");

    const QJsonObject r = GenerationRequestBuilder::build(draft);
    QVERIFY(r.contains(QStringLiteral("upscale_enabled")));
    QCOMPARE(r.value(QStringLiteral("upscale_enabled")).toBool(), false);
    QCOMPARE(r.value(QStringLiteral("upscale_method")).toString(), QStringLiteral("none"));
    QVERIFY2(!r.contains(QStringLiteral("upscale_model_name")),
             "FLUX.3 has no upscale graft; a leftover model name is not a choice");
}

// --- Doc 62 3e: `guidance` had a consumer and no producer ---------------------------------------

void GenerationRequestUpscaleTest::aStatedGuidanceReachesTheRequest()
{
    // `native_image_graphs._flux_guidance_from_request` and both Hunyuan video builders read
    // `guidance`. Nothing in qt_ui ever wrote it, so a Flux model's published figure was shown in
    // the Models inspector under a provenance caption and then replaced by cfg at render time.
    GenerationRequestDraft draft = draftWithUpscale(QStringLiteral("t2i"), false);
    draft.modelFamily = QStringLiteral("flux");
    draft.cfg = 7.0;
    draft.guidance = 3.5;

    const QJsonObject r = GenerationRequestBuilder::build(draft);

    QVERIFY2(r.contains(QStringLiteral("guidance")),
             "the cockpit offers a Guidance control and the builders read this key; a request that "
             "drops it means the user sets it and the render ignores them");
    QCOMPARE(r.value(QStringLiteral("guidance")).toDouble(), 3.5);
    // And cfg is untouched -- they are two different numbers on these families, not aliases.
    QCOMPARE(r.value(QStringLiteral("cfg")).toDouble(), 7.0);
}

void GenerationRequestUpscaleTest::autoGuidanceIsAbsentRatherThanAZero()
{
    // 0.0 is the spin box's "Auto (follow CFG)" sentinel. Stating it would make Auto mean
    // "guidance 0", which on a distilled model is the unguided case -- so a control nobody touched
    // would silently change the render the day it appeared. Absence is what lets
    // `guidance_from_request` fall through to cfg, which is what this app has always done.
    GenerationRequestDraft draft = draftWithUpscale(QStringLiteral("t2i"), false);
    draft.modelFamily = QStringLiteral("flux");
    draft.guidance = 0.0;

    const QJsonObject r = GenerationRequestBuilder::build(draft);

    QVERIFY2(!r.contains(QStringLiteral("guidance")),
             "Auto was sent as a guidance of 0, which is the unguided case rather than a default");
}

QTEST_MAIN(GenerationRequestUpscaleTest)
#include "test_generation_request_upscale.moc"
