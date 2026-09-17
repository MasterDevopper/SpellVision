// The draft carries the cockpit's values.
//
// The workflow-drop path built a draft out of four PATHS, a warnings array and safe_to_submit
// hardcoded false. A workflow dropped on a page therefore filled nothing in and could not run, which
// is the whole reason "drop a workflow" read as broken. The extraction that does the real work had
// existed since Flows was built -- WorkflowLibraryPage::buildReusableDraft, walking the compiled
// prompt for KSampler, following its conditioning back to the CLIPTextEncode nodes, picking up the
// checkpoint, the LoRA stack, the sampler, the size -- and it was private to a page.
//
// These cases run against REAL workflows on disk under runtime/imported_workflows. That is not
// convenience: the classifier's and the extractor's job is graphs nobody here wrote, and a synthetic
// two-node prompt written to match the extractor proves only that the extractor matches itself. The
// owner's library has 88 of them, 80 with a compiled prompt, and the shapes below are drawn from it:
// an SDXL t2i with a four-LoRA stack, an i2i whose LoadImage feeds the graph, a Wan i2v that has no
// standalone checkpoint at all, and a v2v that must be refused.
//
// The three workflows the brief named -- Compact T2I v10, Krea2 Pro Grade v17 and Character Forge --
// are here too, and they carry a finding rather than an assertion of richness: all three are stored
// as UI GRAPHS with no prompt_api.json beside them, so the builder honestly refuses them for want of
// a compiled prompt. That refusal IS the case for task 3's sequence: compile_workflow_prompt is the
// step the drop path never called, and without it these three are exactly the workflows that would
// land on a page with nothing filled in. Compiling them here is not possible without a live ComfyUI
// (the converter needs the real /object_info schema), and inventing one would be the hardcoded
// 21-class widget table this repo already deleted once.

#include <QtTest>

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QElapsedTimer>
#include <QJsonObject>
#include <QString>

#include "shell/ProjectRoot.h"
#include "workflows/WorkflowDraftBuilder.h"
#include "workflows/WorkflowLaunchController.h"

using spellvision::workflows::WorkflowDraftBuilder;
using spellvision::workflows::WorkflowLaunchController;

namespace
{

QString importedWorkflowsRoot()
{
    return QDir(spellvision::shell::resolveProjectRoot()).filePath(QStringLiteral("runtime/imported_workflows"));
}

QJsonObject readJsonObject(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return {};
    return QJsonDocument::fromJson(file.readAll()).object();
}

// One imported workflow, read the way the app reads it: the profile says what it is, the files beside
// it say what it contains.
WorkflowDraftBuilder::Source sourceForImport(const QString &slug)
{
    const QString root = QDir(importedWorkflowsRoot()).filePath(slug);
    const QJsonObject profile = readJsonObject(QDir(root).filePath(QStringLiteral("profile.json")));

    WorkflowDraftBuilder::Source source;
    source.displayName = profile.value(QStringLiteral("profile_name")).toString(slug);
    source.profilePath = QDir(root).filePath(QStringLiteral("profile.json"));
    source.sourceWorkflowPath = QDir(root).filePath(QStringLiteral("workflow.json"));
    source.compiledPromptPath = QDir(root).filePath(QStringLiteral("prompt_api.json"));
    if (!QFileInfo::exists(source.compiledPromptPath))
        source.compiledPromptPath.clear();
    source.sourceWorkflowFormat = QStringLiteral("comfy_ui_graph");
    source.modeId = profile.value(QStringLiteral("task_command")).toString();
    source.mediaType = profile.value(QStringLiteral("media_type")).toString();
    source.backend = profile.value(QStringLiteral("backend_kind")).toString();
    return source;
}

// --- synthetic fixtures ---------------------------------------------------------------------
//
// The cases above run against real owner workflows, and that is still the point. These build prompts
// by hand for one reason the library cannot serve: the shapes below have to be EXACT (a cfg that is
// a link and not a literal; a graph with no sampler at all; a cycle), and no imported workflow is a
// controlled example of any of them. Every class and input name here was taken from a live
// /object_info dump off the running core, not from memory -- SamplerCustomAdvanced takes
// noise/guider/sampler/sigmas/latent_image, CFGGuider takes model/positive/negative/cfg,
// KSamplerSelect takes sampler_name, RandomNoise takes noise_seed, BasicScheduler takes
// model/scheduler/steps/denoise.

QJsonObject promptNode(const QString &classType, const QJsonObject &inputs)
{
    QJsonObject node;
    node.insert(QStringLiteral("class_type"), classType);
    node.insert(QStringLiteral("inputs"), inputs);
    return node;
}

QJsonArray link(const QString &nodeId, int slot)
{
    QJsonArray ref;
    ref.append(nodeId);
    ref.append(slot);
    return ref;
}

WorkflowDraftBuilder::Source syntheticSource()
{
    WorkflowDraftBuilder::Source source;
    source.displayName = QStringLiteral("synthetic");
    source.modeId = QStringLiteral("t2i");
    source.mediaType = QStringLiteral("image");
    source.backend = QStringLiteral("comfy_workflow");
    return source;
}

// The modern chain, as a current Flux / SD3 / Krea graph writes it.
QJsonObject customSamplerPrompt()
{
    QJsonObject prompt;
    prompt.insert(QStringLiteral("1"),
                  promptNode(QStringLiteral("CheckpointLoaderSimple"),
                             {{QStringLiteral("ckpt_name"), QStringLiteral("krea2/base.safetensors")}}));
    prompt.insert(QStringLiteral("2"),
                  promptNode(QStringLiteral("CLIPTextEncode"),
                             {{QStringLiteral("clip"), link(QStringLiteral("1"), 1)},
                              {QStringLiteral("text"), QStringLiteral("a lighthouse at dusk")}}));
    prompt.insert(QStringLiteral("3"),
                  promptNode(QStringLiteral("CLIPTextEncode"),
                             {{QStringLiteral("clip"), link(QStringLiteral("1"), 1)},
                              {QStringLiteral("text"), QStringLiteral("blurry, watermark")}}));
    prompt.insert(QStringLiteral("4"),
                  promptNode(QStringLiteral("CFGGuider"),
                             {{QStringLiteral("model"), link(QStringLiteral("1"), 0)},
                              {QStringLiteral("positive"), link(QStringLiteral("2"), 0)},
                              {QStringLiteral("negative"), link(QStringLiteral("3"), 0)},
                              {QStringLiteral("cfg"), 4.5}}));
    prompt.insert(QStringLiteral("5"),
                  promptNode(QStringLiteral("KSamplerSelect"),
                             {{QStringLiteral("sampler_name"), QStringLiteral("dpmpp_2m")}}));
    prompt.insert(QStringLiteral("6"),
                  promptNode(QStringLiteral("BasicScheduler"),
                             {{QStringLiteral("model"), link(QStringLiteral("1"), 0)},
                              {QStringLiteral("scheduler"), QStringLiteral("karras")},
                              {QStringLiteral("steps"), 28},
                              {QStringLiteral("denoise"), 1.0}}));
    prompt.insert(QStringLiteral("7"),
                  promptNode(QStringLiteral("RandomNoise"),
                             {{QStringLiteral("noise_seed"), 987654321}}));
    prompt.insert(QStringLiteral("8"),
                  promptNode(QStringLiteral("EmptyLatentImage"),
                             {{QStringLiteral("width"), 1152},
                              {QStringLiteral("height"), 896},
                              {QStringLiteral("batch_size"), 1}}));
    prompt.insert(QStringLiteral("9"),
                  promptNode(QStringLiteral("SamplerCustomAdvanced"),
                             {{QStringLiteral("noise"), link(QStringLiteral("7"), 0)},
                              {QStringLiteral("guider"), link(QStringLiteral("4"), 0)},
                              {QStringLiteral("sampler"), link(QStringLiteral("5"), 0)},
                              {QStringLiteral("sigmas"), link(QStringLiteral("6"), 0)},
                              {QStringLiteral("latent_image"), link(QStringLiteral("8"), 0)}}));
    return prompt;
}

bool warnsAbout(const QJsonObject &draft, const QString &field)
{
    for (const QJsonValue &warning : draft.value(QStringLiteral("warnings")).toArray())
    {
        if (warning.toString().contains(field, Qt::CaseInsensitive))
            return true;
    }
    return false;
}

QString modeOf(const QString &slug)
{
    const QJsonObject profile =
        readJsonObject(QDir(QDir(importedWorkflowsRoot()).filePath(slug)).filePath(QStringLiteral("profile.json")));
    return WorkflowLaunchController::resolveModeId(profile);
}

} // namespace

class WorkflowDraftBuilderTest : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();

    void aRealT2iWorkflowFillsInThePromptTheCheckpointAndTheSamplingRow();
    void aRealI2iWorkflowCarriesItsInputImage();
    void aRealVideoWorkflowWithNoCheckpointOpensButWarnsInsteadOfBlocking();
    void aVideoToVideoWorkflowIsRefusedInTheSameVocabularyTheResolverUses();
    void aUiGraphWithNoCompiledPromptIsRefusedForWantOfOneNotFilledWithBlanks();
    void theThreeOwnerWorkflowsResolveToTheirOwnModes();
    void theExtractionIsTheSameOneFlowsUses();

    void aCustomSamplerChainYieldsEverythingAKSamplerWould();
    void aKSamplerGraphStillReadsExactlyAsItDid();
    void aCfgArrivingOverALinkIsNotReportedAndIsNamed();
    void aGraphWithNoSamplerAtAllCarriesNoSamplingFieldsAndSaysWhich();
    void aCyclicGraphTerminates();

private:
    QString root_;
};

void WorkflowDraftBuilderTest::initTestCase()
{
    root_ = importedWorkflowsRoot();
    QVERIFY2(QFileInfo(root_).isDir(), qPrintable(QStringLiteral("no imported workflow library at %1").arg(root_)));
}

// --- 1: t2i, the shape most of the library is ----------------------------------------------------

void WorkflowDraftBuilderTest::aRealT2iWorkflowFillsInThePromptTheCheckpointAndTheSamplingRow()
{
    const QString slug = QStringLiteral("asteral-json");
    if (!QFileInfo::exists(QDir(QDir(root_).filePath(slug)).filePath(QStringLiteral("prompt_api.json"))))
        QSKIP("asteral-json has no compiled prompt in this checkout");

    QCOMPARE(modeOf(slug), QStringLiteral("t2i"));

    const auto result = WorkflowDraftBuilder::build(sourceForImport(slug));
    QVERIFY2(result.present, qPrintable(result.reason));

    const QJsonObject draft = result.draft;
    QCOMPARE(draft.value(QStringLiteral("mode_id")).toString(), QStringLiteral("t2i"));

    // Populated means populated: the prompt the graph carries, not an empty string.
    QVERIFY2(!draft.value(QStringLiteral("prompt")).toString().trimmed().isEmpty(),
             "the positive prompt did not come back from the CLIPTextEncode the sampler is fed by");
    QVERIFY(!draft.value(QStringLiteral("checkpoint")).toString().trimmed().isEmpty());
    QVERIFY(!draft.value(QStringLiteral("checkpoint_display")).toString().trimmed().isEmpty());
    QVERIFY(!draft.value(QStringLiteral("sampler")).toString().trimmed().isEmpty());
    QVERIFY(!draft.value(QStringLiteral("scheduler")).toString().trimmed().isEmpty());
    QVERIFY(draft.value(QStringLiteral("steps")).toInt() > 0);
    QVERIFY(draft.value(QStringLiteral("cfg")).toDouble() > 0.0);
    QVERIFY(draft.value(QStringLiteral("width")).toInt() > 0);
    QVERIFY(draft.value(QStringLiteral("height")).toInt() > 0);

    // The seed travels as a STRING, because a 64-bit seed does not survive a JSON double.
    QVERIFY(draft.value(QStringLiteral("seed")).isString());

    // This one has a four-LoRA stack, and every entry carries a strength the cockpit can show.
    const QJsonArray loras = draft.value(QStringLiteral("lora_stack")).toArray();
    QVERIFY2(loras.size() >= 2, qPrintable(QStringLiteral("expected a LoRA stack, got %1").arg(loras.size())));
    for (const QJsonValue &value : loras)
    {
        const QJsonObject lora = value.toObject();
        QVERIFY(!lora.value(QStringLiteral("name")).toString().trimmed().isEmpty());
        QVERIFY(!lora.value(QStringLiteral("display")).toString().trimmed().isEmpty());
        QVERIFY(lora.value(QStringLiteral("strength")).isDouble());
    }

    // More than one LoRA is a review warning, not a block -- the user is told, and can still run it.
    QVERIFY(result.safeToSubmit);
    QVERIFY(!draft.value(QStringLiteral("warnings")).toArray().isEmpty());
}

// --- 2: i2i, where the input image is part of the draft ------------------------------------------

void WorkflowDraftBuilderTest::aRealI2iWorkflowCarriesItsInputImage()
{
    const QString slug = QStringLiteral("pose-control-v5-2-json");
    if (!QFileInfo::exists(QDir(QDir(root_).filePath(slug)).filePath(QStringLiteral("prompt_api.json"))))
        QSKIP("pose-control-v5-2-json has no compiled prompt in this checkout");

    QCOMPARE(modeOf(slug), QStringLiteral("i2i"));

    const auto result = WorkflowDraftBuilder::build(sourceForImport(slug));
    QVERIFY2(result.present, qPrintable(result.reason));

    const QJsonObject draft = result.draft;
    QCOMPARE(draft.value(QStringLiteral("mode_id")).toString(), QStringLiteral("i2i"));
    QVERIFY(!draft.value(QStringLiteral("prompt")).toString().trimmed().isEmpty());
    QVERIFY(!draft.value(QStringLiteral("checkpoint")).toString().trimmed().isEmpty());
    // An i2i graph names the still it was built around; without this key the cockpit opens with an
    // empty canvas and the draft cannot be run as it was authored.
    QVERIFY2(draft.contains(QStringLiteral("input_image")),
             "the LoadImage input never reached the draft");
    QVERIFY(!draft.value(QStringLiteral("input_image")).toString().trimmed().isEmpty());
}

// --- 3: video, where "no checkpoint" is normal ---------------------------------------------------

void WorkflowDraftBuilderTest::aRealVideoWorkflowWithNoCheckpointOpensButWarnsInsteadOfBlocking()
{
    const QString slug = QStringLiteral("wan-simple-i2v-json");
    if (!QFileInfo::exists(QDir(QDir(root_).filePath(slug)).filePath(QStringLiteral("prompt_api.json"))))
        QSKIP("wan-simple-i2v-json has no compiled prompt in this checkout");

    QCOMPARE(modeOf(slug), QStringLiteral("i2v"));

    const auto result = WorkflowDraftBuilder::build(sourceForImport(slug));
    QVERIFY2(result.present, qPrintable(result.reason));

    const QJsonObject draft = result.draft;
    QCOMPARE(draft.value(QStringLiteral("mode_id")).toString(), QStringLiteral("i2v"));
    QVERIFY(!draft.value(QStringLiteral("prompt")).toString().trimmed().isEmpty());
    QCOMPARE(draft.value(QStringLiteral("checkpoint")).toString(), QString());

    // A Wan graph carries its model stack as UNETLoader + CLIPLoader + VAELoader, so there is no
    // standalone checkpoint to find. Blocking on that would refuse every native video workflow in
    // the library; the draft opens, and says why the model row is empty.
    QVERIFY2(result.safeToSubmit,
             "a video workflow without a standalone checkpoint must open, not be blocked");
    bool warned = false;
    for (const QJsonValue &warning : draft.value(QStringLiteral("warnings")).toArray())
        warned = warned || warning.toString().contains(QStringLiteral("standalone checkpoint"));
    QVERIFY2(warned, "nothing told the user why no checkpoint was filled in");
}

// --- 4: the refusal, in one vocabulary -----------------------------------------------------------

void WorkflowDraftBuilderTest::aVideoToVideoWorkflowIsRefusedInTheSameVocabularyTheResolverUses()
{
    const QString slug = QStringLiteral("mmaudio-json");
    if (!QFileInfo::exists(QDir(QDir(root_).filePath(slug)).filePath(QStringLiteral("profile.json"))))
        QSKIP("mmaudio-json is not in this checkout");

    // The resolver refuses it first, and names v2v. The builder refuses it too, so a caller that
    // skips the resolver cannot get a half-draft -- but the coordinator asks the RESOLVER, so the
    // user sees one message for one cause rather than two different failures.
    const QJsonObject profile =
        readJsonObject(QDir(QDir(root_).filePath(slug)).filePath(QStringLiteral("profile.json")));
    const auto resolution = WorkflowLaunchController::modeResolution(profile);
    QVERIFY(!resolution.routable);
    QCOMPARE(resolution.verdict, QStringLiteral("v2v"));
    QVERIFY(resolution.reason.contains(QStringLiteral("v2v")));

    const auto result = WorkflowDraftBuilder::build(sourceForImport(slug));
    QVERIFY(!result.present);
    QVERIFY(!result.safeToSubmit);
    QVERIFY2(result.reason.contains(QStringLiteral("editable drafts")), qPrintable(result.reason));

    QVERIFY(!WorkflowDraftBuilder::isDraftableShape(QStringLiteral("v2v"), QStringLiteral("video")));
    QVERIFY(!WorkflowDraftBuilder::isDraftableShape(QStringLiteral("audio"), QStringLiteral("audio")));
    QVERIFY(!WorkflowDraftBuilder::isDraftableShape(QStringLiteral("i23d"), QStringLiteral("mesh")));
    QVERIFY(WorkflowDraftBuilder::isDraftableShape(QStringLiteral("t2i"), QStringLiteral("image")));
    QVERIFY(WorkflowDraftBuilder::isDraftableShape(QStringLiteral("i2v"), QStringLiteral("video")));
}

// --- 5: the honest empty ---------------------------------------------------------------------------

void WorkflowDraftBuilderTest::aUiGraphWithNoCompiledPromptIsRefusedForWantOfOneNotFilledWithBlanks()
{
    // All three of the owner workflows the brief names are stored this way. A draft of empty strings
    // would look like a working feature and fill the cockpit with nothing; refusing names the missing
    // step, which is the compile task 3 adds to the sequence.
    for (const QString &slug : {QStringLiteral("krea2-compact-t2i-v10"),
                                QStringLiteral("krea2-pro-grade-v17"),
                                QStringLiteral("krea2-character-forge-sheet")})
    {
        const QString dir = QDir(root_).filePath(slug);
        if (!QFileInfo(dir).isDir())
            QSKIP("the krea2 owner workflows are not in this checkout");
        QVERIFY2(!QFileInfo::exists(QDir(dir).filePath(QStringLiteral("prompt_api.json"))),
                 qPrintable(QStringLiteral("%1 now HAS a compiled prompt -- this case is describing a "
                                           "state that no longer holds and should assert the draft instead")
                                .arg(slug)));

        const auto result = WorkflowDraftBuilder::build(sourceForImport(slug));
        QVERIFY2(!result.present, qPrintable(slug));
        QVERIFY(!result.safeToSubmit);
        QVERIFY2(result.reason.contains(QStringLiteral("prompt")), qPrintable(result.reason));
        QVERIFY(result.draft.isEmpty());
    }
}

// --- 6: the three the brief named, by mode --------------------------------------------------------

void WorkflowDraftBuilderTest::theThreeOwnerWorkflowsResolveToTheirOwnModes()
{
    const QList<QPair<QString, QString>> expected = {
        {QStringLiteral("krea2-compact-t2i-v10"), QStringLiteral("t2i")},
        {QStringLiteral("krea2-pro-grade-v17"), QStringLiteral("i2i")},
        {QStringLiteral("krea2-character-forge-sheet"), QStringLiteral("i2i")},
    };
    for (const auto &pair : expected)
    {
        if (!QFileInfo(QDir(root_).filePath(pair.first)).isDir())
            QSKIP("the krea2 owner workflows are not in this checkout");
        QCOMPARE(modeOf(pair.first), pair.second);
    }
}

// --- 7: the move is a move ------------------------------------------------------------------------

void WorkflowDraftBuilderTest::theExtractionIsTheSameOneFlowsUses()
{
    // buildFromPrompt is the function the page calls through build(), so feeding it the same prompt
    // by hand must give the same draft. This is what makes "moved, not reimplemented" checkable: if
    // somebody re-adds an extractor beside this one, the two will not agree for long.
    const QString slug = QStringLiteral("asteral-json");
    const QString promptPath = QDir(QDir(root_).filePath(slug)).filePath(QStringLiteral("prompt_api.json"));
    if (!QFileInfo::exists(promptPath))
        QSKIP("asteral-json has no compiled prompt in this checkout");

    const auto viaFiles = WorkflowDraftBuilder::build(sourceForImport(slug));
    WorkflowDraftBuilder::Source source = sourceForImport(slug);
    source.compiledPromptPath = promptPath;
    const auto viaPrompt = WorkflowDraftBuilder::buildFromPrompt(readJsonObject(promptPath), source);

    QCOMPARE(viaPrompt.present, viaFiles.present);
    QCOMPARE(viaPrompt.safeToSubmit, viaFiles.safeToSubmit);
    QCOMPARE(viaPrompt.draft, viaFiles.draft);
}

// --- 8: the vocabulary the builder was missing ----------------------------------------------------

void WorkflowDraftBuilderTest::aCustomSamplerChainYieldsEverythingAKSamplerWould()
{
    const auto result = WorkflowDraftBuilder::buildFromPrompt(customSamplerPrompt(), syntheticSource());
    QVERIFY2(result.present, qPrintable(result.reason));

    const QJsonObject draft = result.draft;
    QCOMPARE(draft.value(QStringLiteral("prompt")).toString(), QStringLiteral("a lighthouse at dusk"));
    QCOMPARE(draft.value(QStringLiteral("negative_prompt")).toString(), QStringLiteral("blurry, watermark"));
    QCOMPARE(draft.value(QStringLiteral("sampler")).toString(), QStringLiteral("dpmpp_2m"));
    QCOMPARE(draft.value(QStringLiteral("scheduler")).toString(), QStringLiteral("karras"));
    QCOMPARE(draft.value(QStringLiteral("steps")).toInt(), 28);
    QCOMPARE(draft.value(QStringLiteral("cfg")).toDouble(), 4.5);
    QCOMPARE(draft.value(QStringLiteral("seed")).toString(), QStringLiteral("987654321"));
    QCOMPARE(draft.value(QStringLiteral("width")).toInt(), 1152);
    QCOMPARE(draft.value(QStringLiteral("height")).toInt(), 896);
    QCOMPARE(draft.value(QStringLiteral("checkpoint")).toString(), QStringLiteral("krea2/base.safetensors"));

    // Nothing was missed, so nothing is named as missing.
    QVERIFY2(draft.value(QStringLiteral("warnings")).toArray().isEmpty(),
             "a fully readable graph must not warn about fields it read");
}

// --- 9: the old path, unchanged -------------------------------------------------------------------

void WorkflowDraftBuilderTest::aKSamplerGraphStillReadsExactlyAsItDid()
{
    QJsonObject prompt;
    prompt.insert(QStringLiteral("1"),
                  promptNode(QStringLiteral("CheckpointLoaderSimple"),
                             {{QStringLiteral("ckpt_name"), QStringLiteral("sdxl/base.safetensors")}}));
    prompt.insert(QStringLiteral("2"),
                  promptNode(QStringLiteral("CLIPTextEncode"),
                             {{QStringLiteral("clip"), link(QStringLiteral("1"), 1)},
                              {QStringLiteral("text"), QStringLiteral("a brass orrery")}}));
    prompt.insert(QStringLiteral("3"),
                  promptNode(QStringLiteral("CLIPTextEncode"),
                             {{QStringLiteral("clip"), link(QStringLiteral("1"), 1)},
                              {QStringLiteral("text"), QStringLiteral("text, signature")}}));
    prompt.insert(QStringLiteral("4"),
                  promptNode(QStringLiteral("EmptyLatentImage"),
                             {{QStringLiteral("width"), 1024},
                              {QStringLiteral("height"), 1024},
                              {QStringLiteral("batch_size"), 1}}));
    prompt.insert(QStringLiteral("5"),
                  promptNode(QStringLiteral("KSampler"),
                             {{QStringLiteral("model"), link(QStringLiteral("1"), 0)},
                              {QStringLiteral("positive"), link(QStringLiteral("2"), 0)},
                              {QStringLiteral("negative"), link(QStringLiteral("3"), 0)},
                              {QStringLiteral("latent_image"), link(QStringLiteral("4"), 0)},
                              {QStringLiteral("seed"), 12345},
                              {QStringLiteral("steps"), 30},
                              {QStringLiteral("cfg"), 7.0},
                              {QStringLiteral("sampler_name"), QStringLiteral("euler")},
                              {QStringLiteral("scheduler"), QStringLiteral("normal")},
                              {QStringLiteral("denoise"), 1.0}}));

    const auto result = WorkflowDraftBuilder::buildFromPrompt(prompt, syntheticSource());
    QVERIFY(result.present);

    const QJsonObject draft = result.draft;
    QCOMPARE(draft.value(QStringLiteral("prompt")).toString(), QStringLiteral("a brass orrery"));
    QCOMPARE(draft.value(QStringLiteral("negative_prompt")).toString(), QStringLiteral("text, signature"));
    QCOMPARE(draft.value(QStringLiteral("sampler")).toString(), QStringLiteral("euler"));
    QCOMPARE(draft.value(QStringLiteral("scheduler")).toString(), QStringLiteral("normal"));
    QCOMPARE(draft.value(QStringLiteral("steps")).toInt(), 30);
    QCOMPARE(draft.value(QStringLiteral("cfg")).toDouble(), 7.0);
    QCOMPARE(draft.value(QStringLiteral("seed")).toString(), QStringLiteral("12345"));
    QCOMPARE(draft.value(QStringLiteral("width")).toInt(), 1024);
    QCOMPARE(draft.value(QStringLiteral("height")).toInt(), 1024);
    QVERIFY(draft.value(QStringLiteral("warnings")).toArray().isEmpty());

    // And a KSampler still wins over a custom chain in the same graph, so adding the new vocabulary
    // cannot change what an existing workflow restores as.
    QJsonObject mixed = customSamplerPrompt();
    for (auto it = prompt.constBegin(); it != prompt.constEnd(); ++it)
        mixed.insert(QStringLiteral("k") + it.key(), it.value());
    const QJsonObject mixedDraft = WorkflowDraftBuilder::buildFromPrompt(mixed, syntheticSource()).draft;
    QCOMPARE(mixedDraft.value(QStringLiteral("steps")).toInt(), 30);
    QCOMPARE(mixedDraft.value(QStringLiteral("sampler")).toString(), QStringLiteral("euler"));
}

// --- 10: a value that is a LINK is not a value -----------------------------------------------------

void WorkflowDraftBuilderTest::aCfgArrivingOverALinkIsNotReportedAndIsNamed()
{
    // This is Pro Grade v17's shape in miniature: the guider's cfg, positive and negative all arrive
    // from a custom pipe node that carries no literal of its own. The old builder reported cfg 0.0
    // for exactly this and said nothing; there is no number in this graph to report.
    QJsonObject prompt = customSamplerPrompt();
    prompt.insert(QStringLiteral("20"),
                  promptNode(QStringLiteral("LCPipeOut"), {{QStringLiteral("pipe"), link(QStringLiteral("21"), 0)}}));
    prompt.insert(QStringLiteral("21"),
                  promptNode(QStringLiteral("LCPipeEdit"), {{QStringLiteral("pipe"), link(QStringLiteral("20"), 0)}}));
    prompt.insert(QStringLiteral("4"),
                  promptNode(QStringLiteral("CFGGuider"),
                             {{QStringLiteral("model"), link(QStringLiteral("1"), 0)},
                              {QStringLiteral("positive"), link(QStringLiteral("20"), 14)},
                              {QStringLiteral("negative"), link(QStringLiteral("20"), 16)},
                              {QStringLiteral("cfg"), link(QStringLiteral("20"), 19)}}));

    const auto result = WorkflowDraftBuilder::buildFromPrompt(prompt, syntheticSource());
    QVERIFY(result.present);
    const QJsonObject draft = result.draft;

    QVERIFY2(!draft.contains(QStringLiteral("cfg")),
             "a cfg that is a link was reported as a number the workflow never carried");
    QVERIFY2(!draft.contains(QStringLiteral("prompt")),
             "a prompt behind a pipe was reported as an empty prompt the workflow never carried");
    QVERIFY2(!draft.contains(QStringLiteral("negative_prompt")), "same, for the negative prompt");

    QVERIFY(warnsAbout(draft, QStringLiteral("guidance scale")));
    QVERIFY(warnsAbout(draft, QStringLiteral("prompt text")));
    QVERIFY(warnsAbout(draft, QStringLiteral("negative prompt")));

    // The rest of the chain is still readable, and is still read.
    QCOMPARE(draft.value(QStringLiteral("steps")).toInt(), 28);
    QCOMPARE(draft.value(QStringLiteral("sampler")).toString(), QStringLiteral("dpmpp_2m"));
    QCOMPARE(draft.value(QStringLiteral("seed")).toString(), QStringLiteral("987654321"));
}

// --- 11: nothing read means nothing claimed --------------------------------------------------------

void WorkflowDraftBuilderTest::aGraphWithNoSamplerAtAllCarriesNoSamplingFieldsAndSaysWhich()
{
    QJsonObject prompt;
    prompt.insert(QStringLiteral("1"),
                  promptNode(QStringLiteral("CheckpointLoaderSimple"),
                             {{QStringLiteral("ckpt_name"), QStringLiteral("sdxl/base.safetensors")}}));
    // A node that HAS a width and a height and nothing to do with the canvas. The old scan took the
    // first `width` input in the graph whatever node it was on, which is where 100x100 came from.
    prompt.insert(QStringLiteral("2"),
                  promptNode(QStringLiteral("LCImageCrop"),
                             {{QStringLiteral("image"), link(QStringLiteral("3"), 0)},
                              {QStringLiteral("width"), 100},
                              {QStringLiteral("height"), 100}}));
    prompt.insert(QStringLiteral("3"),
                  promptNode(QStringLiteral("LoadImage"), {{QStringLiteral("image"), QStringLiteral("ref.png")}}));

    const auto result = WorkflowDraftBuilder::buildFromPrompt(prompt, syntheticSource());
    QVERIFY(result.present);
    const QJsonObject draft = result.draft;

    for (const QString &key : {QStringLiteral("prompt"),
                               QStringLiteral("negative_prompt"),
                               QStringLiteral("sampler"),
                               QStringLiteral("scheduler"),
                               QStringLiteral("steps"),
                               QStringLiteral("cfg"),
                               QStringLiteral("seed"),
                               QStringLiteral("width"),
                               QStringLiteral("height")})
    {
        QVERIFY2(!draft.contains(key),
                 qPrintable(QStringLiteral("draft claims '%1' from a graph that says nothing about it").arg(key)));
    }

    // And each one is named, so the user is told what did not come across rather than shown a zero.
    QVERIFY(warnsAbout(draft, QStringLiteral("prompt text")));
    QVERIFY(warnsAbout(draft, QStringLiteral("negative prompt")));
    QVERIFY(warnsAbout(draft, QStringLiteral("step count")));
    QVERIFY(warnsAbout(draft, QStringLiteral("guidance scale")));
    QVERIFY(warnsAbout(draft, QStringLiteral("sampler")));
    QVERIFY(warnsAbout(draft, QStringLiteral("scheduler")));
    QVERIFY(warnsAbout(draft, QStringLiteral("seed")));
    QVERIFY(warnsAbout(draft, QStringLiteral("output size")));
}

// --- 12: cycles ------------------------------------------------------------------------------------

void WorkflowDraftBuilderTest::aCyclicGraphTerminates()
{
    // Every walk this file does is a graph walk, and an imported ip-adapter workflow once overflowed
    // the native stack on one. A cycle on the conditioning, the sigma chain AND the latent chain at
    // once must still come back.
    QJsonObject prompt = customSamplerPrompt();
    prompt.insert(QStringLiteral("2"),
                  promptNode(QStringLiteral("ConditioningCombine"),
                             {{QStringLiteral("conditioning"), link(QStringLiteral("3"), 0)}}));
    prompt.insert(QStringLiteral("3"),
                  promptNode(QStringLiteral("ConditioningCombine"),
                             {{QStringLiteral("conditioning"), link(QStringLiteral("2"), 0)}}));
    prompt.insert(QStringLiteral("6"),
                  promptNode(QStringLiteral("SplitSigmas"),
                             {{QStringLiteral("sigmas"), link(QStringLiteral("10"), 0)},
                              {QStringLiteral("step"), 4}}));
    prompt.insert(QStringLiteral("10"),
                  promptNode(QStringLiteral("SplitSigmas"),
                             {{QStringLiteral("sigmas"), link(QStringLiteral("6"), 0)},
                              {QStringLiteral("step"), 4}}));
    prompt.insert(QStringLiteral("8"),
                  promptNode(QStringLiteral("LatentUpscale"), {{QStringLiteral("samples"), link(QStringLiteral("11"), 0)}}));
    prompt.insert(QStringLiteral("11"),
                  promptNode(QStringLiteral("LatentUpscale"), {{QStringLiteral("samples"), link(QStringLiteral("8"), 0)}}));

    QElapsedTimer timer;
    timer.start();
    const auto result = WorkflowDraftBuilder::buildFromPrompt(prompt, syntheticSource());
    QVERIFY2(timer.elapsed() < 2000, "the walk did not terminate promptly on a cyclic graph");
    QVERIFY(result.present);

    // It came back, and it came back honest: none of the cyclic chains yielded a value.
    QVERIFY(!result.draft.contains(QStringLiteral("prompt")));
    QVERIFY(!result.draft.contains(QStringLiteral("steps")));
    QVERIFY(!result.draft.contains(QStringLiteral("width")));
    // The parts outside the cycles are unaffected.
    QCOMPARE(result.draft.value(QStringLiteral("cfg")).toDouble(), 4.5);
    QCOMPARE(result.draft.value(QStringLiteral("sampler")).toString(), QStringLiteral("dpmpp_2m"));
}

QTEST_MAIN(WorkflowDraftBuilderTest)
#include "test_workflow_draft_builder.moc"
