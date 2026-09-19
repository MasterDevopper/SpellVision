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
// It reads the CURRENT sampling vocabulary, not just KSampler. A Flux / SD3 / Qwen / Krea graph
// samples through SamplerCustomAdvanced + CFGGuider + KSamplerSelect + a sigma schedule -- all core
// ComfyUI classes -- and none of those values sit on the sampler node, so each is walked to across
// one link hop. Two hops is guessing, and it refuses instead.
//
// The MODEL is read off the model PATH, not off an input name. The sampler's `model` input is
// followed upstream through the LoRA loaders, the ModelSampling* patches and the untyped switches to
// the node that loads a model from a filename, and that node's filename input is the answer whatever
// it is called. Matching names instead is how an UpscaleModelLoader's `model_name` came to fill the
// model row of a Krea graph while every Wan 2.2 graph in the library -- whose loader carries
// `unet_name` -- filled in nothing. A Wan dual-noise pair is reported as a pair, under the names
// AssetCatalogScanner already uses for it. A graph with no diffusion loader on any model path
// reports NO checkpoint and says so.
//
// AND IT OMITS WHAT IT COULD NOT READ. Every value in the draft is a value the graph actually
// carried; a field that could not be recovered is ABSENT from the draft and named in `warnings`, so
// the page keeps its own default rather than adopting a zero that reads like the workflow's choice.
// Callers must therefore test for the KEY, not for a sentinel: `steps` absent means unknown, and
// `steps` present means the workflow said so, including when it said 0.
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
        // False unless a compile named this path. The library scan constructs compiledPromptPath
        // from the import directory; that file is "something wrote this name", not "this is the
        // prompt". Reading it into a draft is how a stale width in batch_size reached the cockpit.
        bool compiledPromptVerified = false;
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

    // A draft for a workflow NOTHING HAS VERIFIED, because ComfyUI was unreachable when the compile
    // was asked for. "We could not check" is not "this is broken": the workflow is exactly as
    // readable as it was a minute ago, so it opens for inspection -- and it is never submittable.
    //
    // It ignores `source.compiledPromptPath` on purpose. That path names an artefact whose age
    // nothing vouches for, and reading it is the defect this whole arc removed; opening offline must
    // not become the door it comes back through. The only file it may read is the SOURCE graph, and
    // only when that graph is already an API prompt. A UI graph cannot be read without the live
    // schema, so it opens with no values at all -- fewer fields, honestly empty, and `reason` says
    // why. `reason` is prepended to the draft's warnings and is the sentence the user sees.
    //
    // What it does NOT relax: a shape with no page to open on (v2v, audio, 3d) is still refused,
    // because there is still nowhere to put it.
    static Result buildUnverified(const Source &source, const QString &reason);

    // Which file the draft would be read from, or empty when there is none.
    static QString resolvePromptPath(const Source &source);

    static bool isVideoMode(const QString &modeId, const QString &mediaType);
    static bool isImageMode(const QString &modeId, const QString &mediaType);
    // True for exactly the shapes that can open as an editable draft: image, t2v and i2v. v2v,
    // audio and 3d are out, and so is anything unclassified.
    static bool isDraftableShape(const QString &modeId, const QString &mediaType);
};

} // namespace spellvision::workflows
