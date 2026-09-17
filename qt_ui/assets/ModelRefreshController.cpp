#include "ModelRefreshController.h"

#include <QFileInfo>
#include <QJsonArray>

namespace spellvision::assets
{

namespace
{
QJsonArray rootsArray(const QStringList &roots)
{
    QJsonArray out;
    for (const QString &root : roots)
    {
        const QString trimmed = root.trimmed();
        if (!trimmed.isEmpty())
            out.append(trimmed);
    }
    return out;
}
} // namespace

ModelRefreshController::ModelRefreshController(QObject *parent)
    : QObject(parent)
{
}

QJsonObject ModelRefreshController::buildLibraryRequest(const QStringList &roots)
{
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("model_intel_refresh"));
    request.insert(QStringLiteral("roots"), rootsArray(roots));
    // The whole point of the background mode. A foreground refresh holds the connection for the
    // duration, and the duration here is measured in tens of minutes.
    request.insert(QStringLiteral("background"), true);
    // Deliberately NO `files`: a library pass is every weight under the roots.
    return request;
}

QJsonObject ModelRefreshController::buildModelRequest(const QStringList &roots,
                                                      const QString &weightPath)
{
    const QString weight = weightPath.trimmed();
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("model_intel_refresh"));

    QJsonArray bounds = rootsArray(roots);
    // `roots` is required by the command, and it is also the containment the worker checks `files`
    // against. Falling back to the weight's own folder keeps the button working on a page whose
    // roots have not been pushed yet, and narrows the walk to one directory rather than to
    // whatever the worker would otherwise have chosen.
    if (bounds.isEmpty() && !weight.isEmpty())
        bounds.append(QFileInfo(weight).absolutePath());
    request.insert(QStringLiteral("roots"), bounds);

    // THE line that stops one model's button from reading 2.09 TB. `RefreshJob` has always
    // supported this list; nothing passed one until W5. Dropping it does not fail -- it succeeds
    // slowly, over the whole library, which is why it needs a test of its own.
    request.insert(QStringLiteral("files"), QJsonArray{weight});
    request.insert(QStringLiteral("background"), true);
    return request;
}

QJsonObject ModelRefreshController::buildCancelRequest(const QString &jobId)
{
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("model_intel_cancel"));
    request.insert(QStringLiteral("job_id"), jobId.trimmed());
    return request;
}

bool ModelRefreshController::startLibraryRefresh(const QStringList &roots)
{
    if (rootsArray(roots).isEmpty())
    {
        setStatus(QStringLiteral("Choose a model library folder first."), true);
        return false;
    }
    return start(Scope::Library, buildLibraryRequest(roots), QString(),
                 QStringLiteral("Reading the library…"));
}

bool ModelRefreshController::startModelRefresh(const QStringList &roots, const QString &weightPath)
{
    const QString weight = weightPath.trimmed();
    if (weight.isEmpty())
        return false;
    return start(Scope::OneModel, buildModelRequest(roots, weight), weight,
                 QStringLiteral("Refreshing metadata…"));
}

bool ModelRefreshController::start(Scope scope, const QJsonObject &request,
                                   const QString &weightPath, const QString &startingMessage)
{
    // One refresh at a time. Two overlapping passes would both write the same sidecars and the
    // progress row could only show one of them, so the second ask is refused OUT LOUD rather than
    // queued invisibly.
    if (running_)
    {
        setStatus(QStringLiteral("A metadata refresh is already running."), false);
        return false;
    }

    // Nothing above or below this line reads a credential store, and the request carries no key
    // field. CivitAI's by-hash reads are public; the anonymous and keyed replies were verified
    // identical. Demanding a key here would block the only action that does not need one.

    running_ = true;
    cancelSent_ = false;
    scope_ = scope;
    weightPath_ = weightPath;
    jobId_.clear();
    current_ = 0;
    total_ = 0;
    percent_ = -1;
    message_.clear();
    lastResult_ = QJsonObject();
    setStatus(startingMessage, false);
    emit workerRequested(request);
    return true;
}

bool ModelRefreshController::cancel()
{
    if (!canCancel())
        return false;
    cancelSent_ = true;
    setStatus(QStringLiteral("Stopping…"), false);
    emit workerRequested(buildCancelRequest(jobId_));
    return true;
}

QString ModelRefreshController::progressText() const
{
    if (!running_ && lastResult_.isEmpty())
        return QString();
    if (total_ <= 0)
        return message_.isEmpty() ? status_ : message_;
    const QString counted = QStringLiteral("%1 of %2").arg(current_).arg(total_);
    return message_.isEmpty() ? counted : QStringLiteral("%1 · %2").arg(counted, message_);
}

void ModelRefreshController::setStatus(const QString &text, bool isError)
{
    status_ = text;
    statusIsError_ = isError;
    emit stateChanged();
}

void ModelRefreshController::finish(const QJsonObject &result)
{
    running_ = false;
    cancelSent_ = false;
    lastResult_ = result;
    const bool cancelled = result.value(QStringLiteral("cancelled")).toBool(false);
    const int examined = result.value(QStringLiteral("examined")).toInt(0);
    const int identified = result.value(QStringLiteral("identified")).toInt(0);
    // `no_match` and `lookup_failed` are different facts and the worker counts them separately: the
    // site saying "I do not know this hash" is an answer, and never reaching the site is not. A
    // summary that added them together would report an outage as a library full of unknown weights.
    const int noMatch = result.value(QStringLiteral("no_match")).toInt(0);
    const int failed = result.value(QStringLiteral("lookup_failed")).toInt(0);

    QString summary = cancelled ? QStringLiteral("Stopped after %1 of %2")
                                      .arg(examined)
                                      .arg(result.value(QStringLiteral("total")).toInt(examined))
                                : QStringLiteral("Examined %1").arg(examined);
    summary += QStringLiteral(" · %1 identified").arg(identified);
    if (noMatch > 0)
        summary += QStringLiteral(" · %1 not on the site").arg(noMatch);
    if (failed > 0)
        summary += QStringLiteral(" · %1 could not be looked up").arg(failed);
    setStatus(summary, failed > 0);
    emit refreshFinished(weightPath_, result);
    weightPath_.clear();
    scope_ = Scope::None;
}

bool ModelRefreshController::applyWorkerReply(const QJsonObject &reply)
{
    const QString type = reply.value(QStringLiteral("type")).toString();
    const bool ok = reply.value(QStringLiteral("ok")).toBool(false);

    if (type == QStringLiteral("model_intel_refresh_started"))
    {
        if (!running_)
            return false;
        jobId_ = reply.value(QStringLiteral("job_id")).toString();
        emit stateChanged();
        return true;
    }

    if (type == QStringLiteral("model_intel_progress"))
    {
        const QString id = reply.value(QStringLiteral("job_id")).toString();
        // A progress event for someone else's job must not drive this row. `subscribe` is a
        // fan-out to every listener, so frames from an unrelated refresh do arrive here.
        if (!running_ || (!jobId_.isEmpty() && !id.isEmpty() && id != jobId_))
            return false;
        current_ = reply.value(QStringLiteral("current")).toInt(current_);
        total_ = reply.value(QStringLiteral("total")).toInt(total_);
        if (reply.contains(QStringLiteral("percent")))
            percent_ = reply.value(QStringLiteral("percent")).toInt(0);
        else if (total_ > 0)
            percent_ = static_cast<int>(100.0 * current_ / total_);
        message_ = reply.value(QStringLiteral("message")).toString();
        emit stateChanged();
        return true;
    }

    if (type == QStringLiteral("model_intel_cancel"))
    {
        if (!ok)
        {
            // The worker answers `ok: false` when no refresh is running under that id. Saying so
            // is the point: a caller told `ok` for the wrong id watches the job continue and
            // concludes cancel is broken.
            const QString error = reply.value(QStringLiteral("error")).toString();
            cancelSent_ = false;
            setStatus(error.isEmpty() ? QStringLiteral("Nothing to stop.") : error, true);
        }
        return true;
    }

    if (type == QStringLiteral("model_intel_refresh"))
    {
        if (!running_)
            return false;
        const QString id = reply.value(QStringLiteral("job_id")).toString();
        if (!jobId_.isEmpty() && !id.isEmpty() && id != jobId_)
            return false;
        if (!ok)
        {
            running_ = false;
            cancelSent_ = false;
            const QString error = reply.value(QStringLiteral("error")).toString();
            lastResult_ = reply;
            setStatus(error.isEmpty() ? QStringLiteral("The refresh did not finish.") : error, true);
            emit refreshFinished(weightPath_, reply);
            weightPath_.clear();
            scope_ = Scope::None;
            return true;
        }
        finish(reply);
        return true;
    }

    return false;
}

} // namespace spellvision::assets
