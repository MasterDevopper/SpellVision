#pragma once

// W5 Task 4 -- "Refresh metadata", from inside the app.
//
// W2's cockpit caption told the user to "run Refresh metadata on the Models page" and the sentence
// had to be DELETED, because there was no such control: nothing in `qt_ui/` started a
// `model_intel_refresh` at all. W5 Task 3 added a per-model button on the inspector that sent the
// command and then blocked on the reply. This controller is the rest of it, and it owns three
// facts the button alone could not hold.
//
// **It is a long job.** The owner's library is 759 files and 2.09 TB -- roughly 79 minutes of
// hashing and lookups. A foreground refresh holds the connection for that whole time, so the
// library-wide action sends `"background": true`, gets the `job_id` back immediately, and watches
// `model_intel_progress` events arrive over `subscribe`. Something the user can watch and stop is
// the difference between a long job and a hung app.
//
// **Cancel is part of the action, not a courtesy.** `model_intel_cancel` is addressed by `job_id`,
// which is why the started event matters: a cancel sent before the id arrives has nothing to name.
// The controller holds the id and refuses to offer a cancel it could not deliver.
//
// **No API key is required, and the surface must not pretend otherwise.** Verified against the
// live API: CivitAI's by-hash reads are public, and the anonymous and keyed replies were
// byte-identical. A key buys downloads and mature previews -- nothing this action does. So
// `start()` consults no credential store, the request carries no key field, and a refusal for a
// missing key does not exist anywhere in this file. If one is ever needed, ask THEN, with a link
// to the page that creates it.
//
// And the narrow case that saves the library: a per-model refresh sends `files`, so the worker
// hashes ONE weight instead of walking every root. `RefreshJob` has supported that list since it
// was written; W5 Task 3 was the first caller to pass it. Without it, the inspector's button --
// which names one model -- costs 2.09 TB of reading.
//
// No socket. The controller builds requests and consumes replies; the page owns the connection.
// That is what lets every case below be driven with no worker, no ComfyUI and no network.

#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QStringList>

namespace spellvision::assets
{

class ModelRefreshController : public QObject
{
    Q_OBJECT

public:
    enum class Scope
    {
        None,
        Library,   // every weight under the model roots
        OneModel,  // exactly one file, named in `files`
    };

    explicit ModelRefreshController(QObject *parent = nullptr);

    // --- request builders (static: a test can assert the wire without a running controller) ---
    static QJsonObject buildLibraryRequest(const QStringList &roots);
    static QJsonObject buildModelRequest(const QStringList &roots, const QString &weightPath);
    static QJsonObject buildCancelRequest(const QString &jobId);

    // --- starting ---
    // Both return false only when there is nothing to ask for (no roots, or no weight). Neither
    // consults a credential store; see the header comment.
    bool startLibraryRefresh(const QStringList &roots);
    bool startModelRefresh(const QStringList &roots, const QString &weightPath);
    // Sends `model_intel_cancel` for the running job. False when no job id has arrived yet, which
    // is a real window: `background: true` replies with the started event, and a click landing
    // before it has no id to name.
    bool cancel();

    // --- the reply side ---
    // True when this reply was one of ours. A page that forwards every worker frame is not a bug.
    bool applyWorkerReply(const QJsonObject &reply);

    // --- what the controller is currently holding (the QA / test surface) ---
    bool isRunning() const { return running_; }
    bool canCancel() const { return running_ && !jobId_.isEmpty() && !cancelSent_; }
    Scope scope() const { return scope_; }
    QString jobId() const { return jobId_; }
    QString weightPath() const { return weightPath_; }
    int current() const { return current_; }
    int total() const { return total_; }
    // -1 until the first progress event: a bar sitting at 0% claims a total nobody has counted.
    int percent() const { return percent_; }
    QString progressText() const;
    QString statusText() const { return status_; }
    bool statusIsError() const { return statusIsError_; }
    // The last completed refresh's result object, empty until one finishes.
    QJsonObject lastResult() const { return lastResult_; }

signals:
    // One request, ready to send. The page owns the socket.
    void workerRequested(const QJsonObject &request);
    // Anything visible changed: running, progress, or the status line.
    void stateChanged();
    // A refresh ended -- completed OR cancelled, which are both endings. `weightPath` is empty for
    // a library pass. The caller uses this to drop the per-model defaults cache: every answer
    // resolved before this ran is a claim nobody has re-checked.
    void refreshFinished(const QString &weightPath, const QJsonObject &result);

private:
    bool start(Scope scope, const QJsonObject &request, const QString &weightPath,
               const QString &startingMessage);
    void setStatus(const QString &text, bool isError);
    void finish(const QJsonObject &result);

    bool running_ = false;
    bool cancelSent_ = false;
    Scope scope_ = Scope::None;
    QString jobId_;
    QString weightPath_;
    int current_ = 0;
    int total_ = 0;
    int percent_ = -1;
    QString message_;
    QString status_;
    bool statusIsError_ = false;
    QJsonObject lastResult_;
};

} // namespace spellvision::assets
