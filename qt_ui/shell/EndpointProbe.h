#pragma once

#include <QDateTime>
#include <QHash>
#include <QObject>
#include <QString>
#include <QStringList>

#include "shell/EndpointRegistry.h"

class QNetworkAccessManager;

namespace spellvision::shell
{

// What an endpoint actually answered, as opposed to what a label said about it.
//
// The Runtime page used to decide the master was healthy by reading another QLabel's text:
//
//     const bool localHealthy = runtimeStateLabel_->text().contains("healthy=yes");
//
// A label is a rendering of a fact, not the fact. Reword the caption, translate it, elide it, and
// the health of the machine silently becomes false -- and the only symptom is a dot that stopped
// being green. This structure is the fact; the labels render it.
struct EndpointStatus
{
    bool probed = false;      // a probe has completed at least once
    bool reachable = false;   // /system_stats answered 200
    bool busy = false;        // /queue reports a running job
    bool queueKnown = false;  // ... and we were able to ask
    bool modelsKnown = false; // /models/checkpoints answered

    QString comfyVersion;
    QString gpuName;
    double vramTotalGb = 0.0;
    double vramFreeGb = 0.0;
    QStringList checkpoints;

    QDateTime checkedAt;
    QString detail;           // why it is not reachable, in words a person can act on

    // Never "unknown means fine". An endpoint that has not answered is not routable.
    [[nodiscard]] bool idle() const { return reachable && (!queueKnown || !busy); }
};

// Probes every enabled endpoint over HTTP and keeps the answers. One instance, shared: the Runtime
// page renders it and the cockpit refuses a route on it, and two probers would be two answers.
class EndpointProbe : public QObject
{
    Q_OBJECT

public:
    explicit EndpointProbe(QObject *parent = nullptr);

    static EndpointProbe &instance();

    // Health first, and on its own timeout. NOT a model listing: ComfyUI's folder_paths walks its
    // model directories to answer one, and a CIFS share whose host is down stalls that walk for
    // minutes -- so a health check built on a listing hangs precisely in the state it exists to
    // detect. python/endpoint_capability.py makes the same choice for the same reason.
    void refresh(const EndpointRegistry &registry);
    void refreshOne(const Endpoint &endpoint);

    [[nodiscard]] EndpointStatus statusFor(const QString &endpointId) const;
    [[nodiscard]] bool isStale(const QString &endpointId, int seconds = 90) const;

    // Test seam. The panel and the routing decision are rendered from statuses, and a test that had
    // to stand up an HTTP server to produce one would be testing QNetworkAccessManager.
    void setStatusForTesting(const QString &endpointId, const EndpointStatus &status);

signals:
    void statusChanged(const QString &endpointId);

private:
    void applyStats(const QString &endpointId, const QByteArray &body);
    void applyQueue(const QString &endpointId, const QByteArray &body);
    void applyModels(const QString &endpointId, const QByteArray &body);
    void get(const QString &endpointId, const QString &url, int timeoutMs,
             void (EndpointProbe::*apply)(const QString &, const QByteArray &));

    QNetworkAccessManager *network_ = nullptr;
    QHash<QString, EndpointStatus> statuses_;
    // The address each id was last probed at, so the follow-up calls do not have to be handed the
    // registry a second time -- and so a reply that arrives after the endpoint was re-addressed
    // cannot make the app ask the new address about the old one's answer.
    QHash<QString, QString> baseUrls_;
};

} // namespace spellvision::shell
