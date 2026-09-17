#include "WorkflowCompileVerdict.h"

#include "WorkflowDropCoordinator.h"

namespace spellvision::workflows
{

namespace
{

QString stringAt(const QJsonObject &object, const QString &key)
{
    return object.value(key).toString().trimmed();
}

} // namespace

QJsonObject WorkflowCompileVerdict::buildCompileRequest(const QString &importRoot,
                                                        const QString &profilePath)
{
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("compile_workflow_prompt"));
    request.insert(QStringLiteral("import_root"), importRoot.trimmed());
    request.insert(QStringLiteral("profile_path"), profilePath.trimmed());
    return request;
}

WorkflowCompileVerdict::Prompt
WorkflowCompileVerdict::fromCompileReply(const QJsonObject &compileReply,
                                         const QString &sourceWorkflowPath)
{
    Prompt prompt;

    // FIRST, before the path is even looked at, and from the drop path's own function so that one
    // cause produces one message. A worker older than cd6d5ba still WROTE a prompt_api.json beside
    // its `ok: false`, so a reply can name a path and refuse in the same breath; the refusal is the
    // answer, and the file it points at is the rotten one.
    prompt.refusal = WorkflowDropCoordinator::compileRefusal(compileReply);
    if (!prompt.refusal.isEmpty())
        return prompt;

    const QString named = stringAt(compileReply, QStringLiteral("compiled_prompt_path"));
    if (!named.isEmpty())
    {
        // The file the compile that just ran wrote. Since cd6d5ba the worker writes nothing at all
        // on a refusal, so a named path is a compile that completed.
        prompt.path = named;
        prompt.verified = true;
        return prompt;
    }

    if (stringAt(compileReply, QStringLiteral("graph_format")) == QStringLiteral("comfy_api_prompt"))
    {
        // Nothing to compile: the imported graph is already an API prompt and IS the prompt. Note
        // that this answer OUTRANKS any prompt_api.json in the same directory -- an api-prompt
        // import that also has a stale compiled artefact beside it now reads the graph the user
        // imported, which is the second door the unconditional path assignment held open.
        const QString source = sourceWorkflowPath.trimmed();
        if (!source.isEmpty())
        {
            prompt.path = source;
            prompt.verified = true;
            return prompt;
        }

        prompt.unverifiedReason = QStringLiteral(
            "The workflow is already an API prompt, so nothing was compiled -- but this library row "
            "does not name the graph it was imported from, so there is no file to read.");
        return prompt;
    }

    // No refusal, no path, no format. Nobody answered, and an unanswered question is not a yes: the
    // drop path's stale-file fallback is deliberately absent here. See the header.
    prompt.unverifiedReason = QStringLiteral(
        "The worker did not say whether this workflow compiles against the live ComfyUI schema, so "
        "nothing vouches for a compiled prompt on disk. Check that the worker and ComfyUI are "
        "running, then try again.");
    return prompt;
}

} // namespace spellvision::workflows
