#pragma once

#include <QJsonObject>
#include <QString>
#include <QStringList>

namespace spellvision::workflows
{

// The compiled prompt, read back out as cockpit values.
//
// A dropped workflow that lands on a page with nothing filled in is a workflow the user cannot run,
// and the drop path's draft carried four PATHS and a warnings array -- no prompt, no checkpoint, no
// sampler, no size. Meanwhile WorkflowLibraryPage::buildReusableDraft had done the real extraction
// since Flows was built: walk the compiled prompt for KSampler / KSamplerAdvanced, follow its
// positive and negative conditioning back to the CLIPTextEncode that feeds them, and pick up the
// checkpoint, the LoRA stack, the sampler, the scheduler, steps, cfg, seed, width, height, frames,
// fps and the input image on the way past.
//
// This is that function, moved rather than reimplemented. Two extractors that disagree about what a
// graph says is the shape of defect this wave keeps finding one level up -- three classifiers that
// disagreed about what a graph IS -- and a second one written for the drop path would have started
// disagreeing on the first workflow whose loader is not a plain CheckpointLoaderSimple.
//
// WHAT IT REFUSES, and why that refusal is not the last word: v2v, audio and 3d have no generation
// page, so there is nothing to open them on. That is the same fact WorkflowLaunchController states,
// with the same vocabulary, and the coordinator asks the RESOLVER first -- so one cause produces one
// message. The refusal here is the backstop for a caller that did not ask.
class WorkflowDraftBuilder final
{
public:
    // Everything the builder needs that is not in the prompt itself: where the files are, what the
    // importer decided this workflow is, and what the readiness pass already found missing.
    struct Source
    {
        QString displayName;
        QString profilePath;
        QString sourceWorkflowPath;
        // "comfy_api_prompt" means the source graph IS a prompt, so it can stand in when no compiled
        // prompt was written beside it.
        QString sourceWorkflowFormat;
        QString compiledPromptPath;
        QString modeId;
        QString mediaType;
        QString backend;
        QStringList missingRuntimeAssets;
        QStringList missingCustomNodes;
    };

    struct Result
    {
        // False means no draft at all -- `reason` says why, and it is always set.
        bool present = false;
        // False means "open it, but do not let it be submitted until somebody looks". The cockpit
        // reads this off the draft as `safe_to_submit` and latches workflowDraftBlocking_.
        bool safeToSubmit = false;
        QString reason;
        QJsonObject draft;
    };

    WorkflowDraftBuilder() = delete;

    // Reads the compiled prompt from disk (falling back to the source graph when that graph is
    // already an API prompt) and extracts it.
    static Result build(const Source &source);

    // The extraction itself, with no filesystem in it. Every case in the test suite drives this with
    // a real owner workflow's prompt, because the graphs that matter are the ones nobody here wrote.
    static Result buildFromPrompt(const QJsonObject &prompt, const Source &source);

    // Which file the draft would be read from, or empty when there is none.
    static QString resolvePromptPath(const Source &source);

    static bool isVideoMode(const QString &modeId, const QString &mediaType);
    static bool isImageMode(const QString &modeId, const QString &mediaType);
    // True for exactly the shapes that can open as an editable draft: image, t2v and i2v. v2v,
    // audio and 3d are out, and so is anything unclassified.
    static bool isDraftableShape(const QString &modeId, const QString &mediaType);
};

} // namespace spellvision::workflows
