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

QTEST_MAIN(WorkflowDraftBuilderTest)
#include "test_workflow_draft_builder.moc"
