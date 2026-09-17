#pragma once

#include <QJsonObject>
#include <QString>

namespace spellvision::workflows
{

// Whether there is a compiled prompt to read, answered by the COMPILE and not by the directory.
//
// WorkflowLibraryPage set `record.compiledPromptPath` to `<import_root>/prompt_api.json`
// unconditionally, for every row, on every refresh. It read the DIRECTORY. Nothing in that
// assignment had ever seen a compile reply, so the path meant no more than "a file with that name is
// lying there" -- whatever wrote it, whenever, and whether or not the converter that runs today
// would refuse the graph outright. From there it went straight into WorkflowDraftBuilder::Source,
// which reads values out of the file and puts them in the cockpit, and the user renders them.
//
// A structural check does not save this. The seven stale prompt_api.json files on this box are
// well-formed JSON with no dangling ids, written by an older converter whose widget cursor did not
// advance past an input promoted to a link: they carry a WIDTH in a `batch_size` field. Nothing
// rejects them. They are simply wrong, all the way to a render.
//
// So Flows asks. compile_workflow_prompt runs the live converter against live /object_info and
// answers in one of three ways, and this is the unit that keeps them apart:
//
//   a REFUSAL      -- the graph names classes the live schema does not publish. There is no prompt,
//                     and the sentence naming the packs to install is the answer the user gets.
//   UNVERIFIED     -- ComfyUI was unreachable, so nothing was checked. A fact about the MACHINE,
//                     not about the graph: the row OPENS from the source workflow, with submission
//                     closed and the reason shown as a warning. It was briefly folded into the
//                     refusal above, which cost offline inspection for no gain; "we could not
//                     check" and "we checked and it is broken" are different answers.
//   a NAMED PATH   -- the file the compile just wrote. That, and only that, is verified.
//   SILENCE        -- a reply carrying none of the above. It is not a yes.
//
// The refusal is read FIRST, before the path is even looked at, because a worker older than cd6d5ba
// wrote prompt_api.json UNCONDITIONALLY beside its own `ok: false` -- such a reply names a path and
// refuses in the same breath, and the file it names is the rotten one. That ordering is the shape
// fe3ad7d established for the drop path, and the refusal SENTENCE is literally that path's, taken
// from WorkflowDropCoordinator::compileRefusal rather than written a second time: one cause must
// produce one message, and a second vocabulary for "this workflow needs a node pack" would start
// disagreeing with the first one on the first graph that has two.
//
// WHERE THIS DIVERGES from the drop path, deliberately: fe3ad7d kept a stale-file fallback for a
// reply that carries nothing at all, announced in the log. Flows has no such fallback. The drop path
// is handed a file the user chose seconds ago and has no older artefact to confuse it with; Flows is
// looking at a directory that has been accumulating artefacts since the workflow was first imported,
// and the whole defect being closed here is that it treated one of them as an answer.
class WorkflowCompileVerdict final
{
public:
    // What the compile said about where this workflow's prompt is.
    struct Prompt
    {
        // Empty unless something actually vouched for it. Never constructed from a directory.
        QString path;
        // The worker's own sentence, with the packs and repository URLs it named. Non-empty means
        // there is no prompt and no draft -- not "look somewhere else".
        QString refusal;
        // Neither a path nor a refusal: nobody answered the question. Said out loud, because a
        // question nobody answered reading as "yes" is the defect this unit exists for.
        QString unverifiedReason;
        // True for ONE of the unverified cases: ComfyUI was unreachable, so nothing could be
        // checked. That is a fact about the machine and not about the graph, so the row still OPENS
        // -- from the source workflow, never from an artefact -- with `unverifiedReason` shown as a
        // warning and submission closed. Every other unverified reply is still a dead end here,
        // because it means the WORKER did not answer, which is not the same as ComfyUI being down.
        bool schemaUnavailable = false;
        // True only when `path` came from the compile. The one field a caller may key a draft on.
        bool verified = false;
    };

    WorkflowCompileVerdict() = delete;

    // The request a Flows row makes. The worker resolves the import root from either key, and a
    // record that carries only one of them still has to work.
    static QJsonObject buildCompileRequest(const QString &importRoot, const QString &profilePath);

    // Read the reply. `sourceWorkflowPath` is only consulted for the one legitimate reply with a
    // null path: the graph WAS already an API prompt, so nothing was compiled and the source
    // workflow IS the prompt -- which is also how a stale prompt_api.json sitting beside an
    // api-prompt import stops being preferred to the graph the user imported.
    static Prompt fromCompileReply(const QJsonObject &compileReply, const QString &sourceWorkflowPath);
};

} // namespace spellvision::workflows
