// W5 Task 1 -- the Models page's tabs come from the classifier.
//
// `ModelManagerPage::detectType` answered "what kind of weight is this" with six names matched as
// substrings against the file's path. Three things were wrong with it and only one of them was
// visible: `clip_vision` and `text_encoders` were both "Encoder", so two unrelated kinds shared a
// filter; an embedding matched nothing and fell through to "Model", so it sat in the list beside
// the checkpoints; and a style model had no name at all. The worker's classifier has answered
// this properly for months and writes its answer into `<stem>.spellvision.json`.
//
// The case that matters most is the one nobody can see going wrong. A weight whose kind nothing
// determined must land in Other, and Other must be on screen -- a model that appears under no tab
// is indistinguishable, from the user's chair, from a model that is not installed. So the last two
// cases here are not about tabs at all: they are the conservation law. Every model is in exactly
// one kind tab, and the tab counts add up to All.
//
// The sidecars under tests/fixtures/model_library are REAL -- copied out of F:/AI_ASSETS/models
// after the intelligence pass ran over the owner's library. Copied rather than read in place
// because a model root on this box can come up BitLocker-locked, and a suite that reads one at
// test time fails for a reason that has nothing to do with the code under test.

#include <QtTest>

#include <iterator>

#include <QDir>
#include <QFile>
#include <QHash>
#include <QStringList>

#include "assets/ModelCardModel.h"
#include "assets/ModelIntelSidecar.h"
#include "assets/ModelKindTabs.h"
#include "shell/ProjectRoot.h"

using spellvision::assets::ModelCardFilterProxy;
using spellvision::assets::ModelCardModel;
using spellvision::assets::ModelIntel;
using spellvision::assets::ModelKindTabBar;
namespace Tabs = spellvision::assets::ModelKindTabs;

namespace
{

QString fixtureDir()
{
    return QDir(spellvision::shell::resolveProjectRoot())
        .filePath(QStringLiteral("tests/fixtures/model_library"));
}

ModelIntel realSidecar(const QString &stem)
{
    const QString path = QDir(fixtureDir()).filePath(stem + QStringLiteral(".spellvision.json"));
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return {};
    return spellvision::assets::parseModelIntelDocument(file.readAll(), path);
}

// One inventory covering all ten kinds plus two that nothing can classify. The counts are
// deliberately uneven so a filter that returns everything, or nothing, cannot pass by coincidence.
struct Row
{
    const char *kind;
    const char *name;
};

const Row kInventory[] = {
    {"checkpoint", "sd3.5_medium.safetensors"},
    {"checkpoint", "juggernautXL.safetensors"},
    {"diffusion_model", "krea2_raw_fp8_scaled.safetensors"},
    {"diffusion_model", "wan2.2_t2v_high_noise.safetensors"},
    {"diffusion_model", "ltx-2.3-22b-dev.safetensors"},
    {"lora", "Detailer-KREA2.safetensors"},
    {"lora", "krea2_darkbrush.safetensors"},
    {"lora", "krea2_neondrip.safetensors"},
    {"lora", "chel_ltx23.safetensors"},
    {"vae", "qwen_image_vae.safetensors"},
    {"text_encoder", "qwen3vl_4b_bf16.safetensors"},
    {"text_encoder", "t5xxl_fp16.safetensors"},
    {"clip_vision", "clip_vision_h.safetensors"},
    {"embedding", "easynegative.pt"},
    {"embedding", "badhandv4.pt"},
    {"embedding", "ng_deepnegative_v1.pt"},
    {"upscaler", "4x-UltraSharp.pth"},
    {"controlnet", "krea2DepthControlnet.safetensors"},
    {"style_model", "flux1-redux-dev.safetensors"},
    // Two the classifier could not place. `video_stack` is a real answer from its own vocabulary
    // that has no tab of its own; the second is a weight nothing recognised at all.
    {"video_stack", "wan_stack_bundle.safetensors"},
    {"unknown", "mystery_weight.bin"},
};

QVector<ModelCardModel::Card> inventoryCards()
{
    QVector<ModelCardModel::Card> cards;
    for (const Row &row : kInventory)
    {
        ModelCardModel::Card card;
        card.kind = Tabs::normaliseKind(QString::fromLatin1(row.kind));
        card.type = Tabs::kindLabel(card.kind);
        card.fullName = QString::fromLatin1(row.name);
        card.strippedName = card.fullName;
        card.nativePath = QStringLiteral("F:/AI_ASSETS/models/") + card.fullName;
        card.modelValue = card.fullName;
        card.family = QStringLiteral("krea2");
        cards.push_back(card);
    }
    return cards;
}

QStringList inventoryKinds()
{
    QStringList kinds;
    for (const Row &row : kInventory)
        kinds << QString::fromLatin1(row.kind);
    return kinds;
}

} // namespace

class TestModelKindTabs : public QObject
{
    Q_OBJECT

private slots:
    void the_fixture_sidecars_are_present();
    void all_ten_kinds_give_the_right_tab_counts();
    void switching_tabs_filters_the_grid();
    void a_model_the_classifier_could_not_place_appears_under_other();
    void every_model_appears_in_exactly_one_tab_and_in_all();
    void the_tab_labels_carry_their_counts();
    void other_stays_visible_when_it_is_empty();
    void an_empty_tab_is_hidden_but_all_and_other_are_not();
    void clip_vision_and_text_encoders_are_no_longer_one_bucket();
    void the_sidecar_kind_beats_the_folder_the_file_sits_in();
    void a_weight_with_no_sidecar_still_lands_in_a_tab();
    void a_family_of_unknown_is_no_family();
};

void TestModelKindTabs::the_fixture_sidecars_are_present()
{
    // The fixtures are the point of this file; a silently-empty directory would turn every case
    // below that touches a real sidecar into a vacuous pass.
    const QDir dir(fixtureDir());
    QVERIFY2(dir.exists(), qPrintable(fixtureDir()));
    QVERIFY(dir.entryList({QStringLiteral("*.spellvision.json")}, QDir::Files).size() >= 8);
}

void TestModelKindTabs::all_ten_kinds_give_the_right_tab_counts()
{
    const QHash<QString, int> counts = Tabs::counts(inventoryKinds());

    QCOMPARE(counts.value(QStringLiteral("checkpoint")), 2);
    QCOMPARE(counts.value(QStringLiteral("diffusion_model")), 3);
    QCOMPARE(counts.value(QStringLiteral("lora")), 4);
    QCOMPARE(counts.value(QStringLiteral("vae")), 1);
    QCOMPARE(counts.value(QStringLiteral("text_encoder")), 2);
    QCOMPARE(counts.value(QStringLiteral("clip_vision")), 1);
    QCOMPARE(counts.value(QStringLiteral("embedding")), 3);
    QCOMPARE(counts.value(QStringLiteral("upscaler")), 1);
    QCOMPARE(counts.value(QStringLiteral("controlnet")), 1);
    QCOMPARE(counts.value(QStringLiteral("style_model")), 1);
    QCOMPARE(counts.value(Tabs::otherTabId()), 2);
    QCOMPARE(counts.value(Tabs::allTabId()), int(std::size(kInventory)));

    // Twelve tabs: All, the ten kinds, Other. Every one of them has an entry, zero included, so a
    // caller never has to tell "no entry" from "none of those".
    QCOMPARE(Tabs::tabs().size(), 12);
    for (const auto &tab : Tabs::tabs())
        QVERIFY2(counts.contains(tab.id), qPrintable(tab.id));
}

void TestModelKindTabs::switching_tabs_filters_the_grid()
{
    ModelCardModel model;
    model.setCards(inventoryCards());
    ModelCardFilterProxy proxy;
    proxy.setSourceModel(&model);

    QCOMPARE(proxy.rowCount(), int(std::size(kInventory)));

    proxy.setKindTab(QStringLiteral("lora"));
    QCOMPARE(proxy.rowCount(), 4);
    for (int row = 0; row < proxy.rowCount(); ++row)
        QCOMPARE(proxy.index(row, 0).data(ModelCardModel::KindRole).toString(), QStringLiteral("lora"));

    proxy.setKindTab(QStringLiteral("embedding"));
    QCOMPARE(proxy.rowCount(), 3);

    // The kind that the OLD page had no name for at all, and the one it merged with another.
    proxy.setKindTab(QStringLiteral("clip_vision"));
    QCOMPARE(proxy.rowCount(), 1);
    QCOMPARE(proxy.index(0, 0).data(ModelCardModel::StrippedNameRole).toString(),
             QStringLiteral("clip_vision_h.safetensors"));

    proxy.setKindTab(Tabs::allTabId());
    QCOMPARE(proxy.rowCount(), int(std::size(kInventory)));
}

void TestModelKindTabs::a_model_the_classifier_could_not_place_appears_under_other()
{
    ModelCardModel model;
    model.setCards(inventoryCards());
    ModelCardFilterProxy proxy;
    proxy.setSourceModel(&model);

    proxy.setKindTab(Tabs::otherTabId());
    QCOMPARE(proxy.rowCount(), 2);

    QStringList shown;
    for (int row = 0; row < proxy.rowCount(); ++row)
        shown << proxy.index(row, 0).data(ModelCardModel::StrippedNameRole).toString();
    shown.sort();
    QCOMPARE(shown, (QStringList{QStringLiteral("mystery_weight.bin"),
                                 QStringLiteral("wan_stack_bundle.safetensors")}));

    // And it is not ALSO sitting in some real tab. A weight in two tabs is a weight whose kind was
    // guessed twice.
    for (const auto &tab : Tabs::tabs())
    {
        if (tab.id == Tabs::allTabId() || tab.id == Tabs::otherTabId())
            continue;
        QVERIFY2(!Tabs::tabAccepts(tab.id, QStringLiteral("unknown")), qPrintable(tab.id));
        QVERIFY2(!Tabs::tabAccepts(tab.id, QStringLiteral("video_stack")), qPrintable(tab.id));
        QVERIFY2(!Tabs::tabAccepts(tab.id, QString()), qPrintable(tab.id));
    }
}

void TestModelKindTabs::every_model_appears_in_exactly_one_tab_and_in_all()
{
    ModelCardModel model;
    model.setCards(inventoryCards());
    ModelCardFilterProxy proxy;
    proxy.setSourceModel(&model);

    QHash<QString, int> appearances;
    int filed = 0;
    for (const auto &tab : Tabs::tabs())
    {
        if (tab.id == Tabs::allTabId())
            continue;
        proxy.setKindTab(tab.id);
        filed += proxy.rowCount();
        for (int row = 0; row < proxy.rowCount(); ++row)
            ++appearances[proxy.index(row, 0).data(ModelCardModel::StrippedNameRole).toString()];
    }

    QCOMPARE(filed, int(std::size(kInventory)));
    QCOMPARE(appearances.size(), int(std::size(kInventory)));
    for (auto it = appearances.cbegin(); it != appearances.cend(); ++it)
        QVERIFY2(it.value() == 1, qPrintable(QStringLiteral("%1 appears in %2 tabs").arg(it.key()).arg(it.value())));

    proxy.setKindTab(Tabs::allTabId());
    QCOMPARE(proxy.rowCount(), int(std::size(kInventory)));
}

void TestModelKindTabs::the_tab_labels_carry_their_counts()
{
    ModelKindTabBar bar;
    bar.setCounts(Tabs::counts(inventoryKinds()));

    QCOMPARE(bar.labelForTab(QStringLiteral("lora")), QStringLiteral("LoRAs 4"));
    QCOMPARE(bar.labelForTab(QStringLiteral("text_encoder")), QStringLiteral("Text encoders 2"));
    QCOMPARE(bar.labelForTab(Tabs::otherTabId()), QStringLiteral("Other 2"));
    QCOMPARE(bar.labelForTab(Tabs::allTabId()),
             QStringLiteral("All %1").arg(int(std::size(kInventory))));
}

void TestModelKindTabs::other_stays_visible_when_it_is_empty()
{
    ModelKindTabBar bar;
    // A library where everything classified: Other holds nothing, and is still on the bar. Hiding
    // it would mean the one tab whose whole job is "nothing got lost" disappears exactly when the
    // user would want to check.
    bar.setCounts(Tabs::counts({QStringLiteral("lora"), QStringLiteral("lora"),
                                QStringLiteral("checkpoint")}));
    QVERIFY(bar.visibleTabIds().contains(Tabs::otherTabId()));
    QCOMPARE(bar.labelForTab(Tabs::otherTabId()), QStringLiteral("Other 0"));
}

void TestModelKindTabs::an_empty_tab_is_hidden_but_all_and_other_are_not()
{
    ModelKindTabBar bar;
    bar.setCounts(Tabs::counts({QStringLiteral("lora"), QStringLiteral("checkpoint")}));

    const QStringList visible = bar.visibleTabIds();
    QCOMPARE(visible, (QStringList{Tabs::allTabId(), QStringLiteral("checkpoint"),
                                   QStringLiteral("lora"), Tabs::otherTabId()}));
    QVERIFY(!visible.contains(QStringLiteral("upscaler")));
}

void TestModelKindTabs::clip_vision_and_text_encoders_are_no_longer_one_bucket()
{
    // The exact collapse the old detectType performed: both folders returned "Encoder".
    QCOMPARE(Tabs::kindFromPath(QStringLiteral("F:/AI_ASSETS/models/clip_vision/clip_vision_h.safetensors")),
             QStringLiteral("clip_vision"));
    QCOMPARE(Tabs::kindFromPath(QStringLiteral("F:/AI_ASSETS/models/text_encoders/t5xxl_fp16.safetensors")),
             QStringLiteral("text_encoder"));
    QVERIFY(Tabs::kindLabel(QStringLiteral("clip_vision")) != Tabs::kindLabel(QStringLiteral("text_encoder")));

    // And the two the old vocabulary had no word for.
    QCOMPARE(Tabs::kindFromPath(QStringLiteral("D:/AI_ASSETS/models/embeddings/easynegative.pt")),
             QStringLiteral("embedding"));
    QCOMPARE(Tabs::kindFromPath(QStringLiteral("D:/AI_ASSETS/models/style_models/flux1-redux-dev.safetensors")),
             QStringLiteral("style_model"));
}

void TestModelKindTabs::the_sidecar_kind_beats_the_folder_the_file_sits_in()
{
    // Real sidecars. The Lox weights live in diffusion_models/ and the classifier agrees; the
    // point here is that the kind is READ, and that a real document parses into the vocabulary.
    const ModelIntel lox = realSidecar(QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4"));
    QVERIFY(lox.present);
    QCOMPARE(lox.kind, QStringLiteral("diffusion_model"));

    const ModelIntel lora = realSidecar(QStringLiteral("Detailer-KREA2"));
    QVERIFY(lora.present);
    QCOMPARE(lora.kind, QStringLiteral("lora"));

    // This one is the whole argument. `krea2DepthControlnet_v10` is a LoRA whose FILE NAME says
    // "controlnet" -- and the old detectType matched its six names against the whole path, so the
    // same weight outside a loras/ folder was filed under ControlNet. The classifier says lora,
    // and the folder fallback refuses to answer from the file name at all.
    const ModelIntel controlnetNamed = realSidecar(QStringLiteral("krea2DepthControlnet_v10"));
    QVERIFY(controlnetNamed.present);
    QCOMPARE(controlnetNamed.kind, QStringLiteral("lora"));
    QCOMPARE(Tabs::kindFromPath(QStringLiteral("F:/weights/krea2DepthControlnet_v10.safetensors")),
             Tabs::otherTabId());
    QCOMPARE(Tabs::kindFromPath(QStringLiteral("F:/AI_ASSETS/models/loras/krea2DepthControlnet_v10.safetensors")),
             QStringLiteral("lora"));
    // And the other direction: a checkpoint in a per-family subfolder is still a checkpoint.
    QCOMPARE(Tabs::kindFromPath(QStringLiteral("F:/AI_ASSETS/models/checkpoints/sd3/sd3.5_medium.safetensors")),
             QStringLiteral("checkpoint"));

    const ModelIntel encoder = realSidecar(QStringLiteral("qwen3vl_4b_fp8_scaled"));
    QVERIFY(encoder.present);
    QCOMPARE(encoder.kind, QStringLiteral("text_encoder"));

    const ModelIntel vae = realSidecar(QStringLiteral("qwen_image_vae"));
    QVERIFY(vae.present);
    QCOMPARE(vae.kind, QStringLiteral("vae"));

    const ModelIntel checkpoint = realSidecar(QStringLiteral("sd3.5_medium_incl_clips_t5xxlfp8scaled"));
    QVERIFY(checkpoint.present);
    QCOMPARE(checkpoint.kind, QStringLiteral("checkpoint"));
}

void TestModelKindTabs::a_weight_with_no_sidecar_still_lands_in_a_tab()
{
    // Most of a library has never been through a refresh. The folder fallback answers in the same
    // vocabulary, and a path that says nothing ends at Other rather than at "checkpoint".
    QCOMPARE(Tabs::kindFromPath(QStringLiteral("F:/AI_ASSETS/models/loras/krea2_darkbrush.safetensors")),
             QStringLiteral("lora"));
    QCOMPARE(Tabs::kindFromPath(QStringLiteral("F:/weights/something_nobody_sorted.safetensors")),
             Tabs::otherTabId());
    QVERIFY(!Tabs::kindFromPath(QStringLiteral("")).isEmpty());
    QCOMPARE(Tabs::kindFromPath(QString()), Tabs::otherTabId());

    // Windows separators, because the page hands this native paths.
    QCOMPARE(Tabs::kindFromPath(QStringLiteral("F:\\AI_ASSETS\\models\\vae\\qwen_image_vae.safetensors")),
             QStringLiteral("vae"));
}

void TestModelKindTabs::a_family_of_unknown_is_no_family()
{
    // Sidecars written before `normalise_family` landed carry the literal string "unknown", which
    // is truthy and so reads as a real family to anything that does not go through here. Two of
    // the fixture sidecars are exactly that.
    const ModelIntel encoder = realSidecar(QStringLiteral("qwen3vl_4b_fp8_scaled"));
    QVERIFY(encoder.present);
    QVERIFY2(encoder.family.isEmpty(), qPrintable(encoder.family));

    const ModelIntel lox = realSidecar(QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4"));
    QCOMPARE(lox.family, QStringLiteral("krea2"));
}

QTEST_MAIN(TestModelKindTabs)
#include "test_model_kind_tabs.moc"
