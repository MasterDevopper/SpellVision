#include "shell/EndpointProbe.h"

#include <QCoreApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QPointer>
#include <QUrl>

namespace spellvision::shell
{
namespace
{
constexpr int kHealthTimeoutMs = 2500;
// The two follow-ups are allowed longer than health, and they only ever run AFTER health answered.
// A listing is the call that stalls on a dead model share, so it must never be what decides whether
// a machine is up.
constexpr int kDetailTimeoutMs = 8000;
constexpr double kBytesPerGb = 1073741824.0;

double gigabytes(const QJsonValue &value)
{
    return value.toDouble(0.0) / kBytesPerGb;
}
} // namespace

EndpointProbe::EndpointProbe(QObject *parent)
    : QObject(parent)
    , network_(new QNetworkAccessManager(this))
{
}

EndpointProbe &EndpointProbe::instance()
{
    // Parented to the application rather than left as a function-local static.
    //
    // A static QObject is destroyed AFTER main() returns, which means its QNetworkAccessManager --
    // and any reply still in flight -- is torn down when QCoreApplication no longer exists. That is
    // a crash at exit, and the worst kind: it happens after every test has reported PASS, so it
    // reads as a suite that is green and a process that died.
    //
    // QPointer rather than a raw one so a host that destroys its QApplication and builds another
    // (which is exactly what a Qt test binary does) gets a new probe instead of a dangling one.
    static QPointer<EndpointProbe> probe;
    if (!probe)
        probe = new EndpointProbe(QCoreApplication::instance());
    return *probe;
}

void EndpointProbe::refresh(const EndpointRegistry &registry)
{
    for (const Endpoint &endpoint : registry.entries())
    {
        if (endpoint.enabled)
            refreshOne(endpoint);
    }
}

void EndpointProbe::refreshOne(const Endpoint &endpoint)
{
    if (endpoint.baseUrl.trimmed().isEmpty())
        return;
    baseUrls_.insert(endpoint.id, endpoint.baseUrl);
    get(endpoint.id, endpoint.baseUrl + QStringLiteral("/system_stats"), kHealthTimeoutMs,
        &EndpointProbe::applyStats);
}

EndpointStatus EndpointProbe::statusFor(const QString &endpointId) const
{
    return statuses_.value(endpointId);
}

bool EndpointProbe::isStale(const QString &endpointId, int seconds) const
{
    const EndpointStatus status = statuses_.value(endpointId);
    if (!status.probed || !status.checkedAt.isValid())
        return true;
    return status.checkedAt.secsTo(QDateTime::currentDateTime()) > seconds;
}

void EndpointProbe::setStatusForTesting(const QString &endpointId, const EndpointStatus &status)
{
    statuses_.insert(endpointId, status);
    emit statusChanged(endpointId);
}

void EndpointProbe::get(const QString &endpointId, const QString &url, int timeoutMs,
                        void (EndpointProbe::*apply)(const QString &, const QByteArray &))
{
    QNetworkRequest request{QUrl(url)};
    request.setTransferTimeout(timeoutMs);
    QNetworkReply *reply = network_->get(request);
    connect(reply, &QNetworkReply::finished, this, [this, reply, endpointId, apply]() {
        const bool ok = reply->error() == QNetworkReply::NoError
            && reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt() == 200;
        const QByteArray body = ok ? reply->readAll() : QByteArray();
        const QString failure = ok ? QString() : reply->errorString();
        reply->deleteLater();

        EndpointStatus &status = statuses_[endpointId];
        status.probed = true;
        status.checkedAt = QDateTime::currentDateTime();
        if (!ok)
        {
            // Only the HEALTH call may declare an endpoint unreachable. A /queue or /models failure
            // after a good /system_stats means one route answered and another did not, and calling
            // the machine offline for it would hide the half that works.
            if (apply == &EndpointProbe::applyStats)
            {
                status.reachable = false;
                status.queueKnown = false;
                status.modelsKnown = false;
                status.checkpoints.clear();
                status.detail = failure;
            }
            emit statusChanged(endpointId);
            return;
        }
        (this->*apply)(endpointId, body);
        emit statusChanged(endpointId);
    });
}

void EndpointProbe::applyStats(const QString &endpointId, const QByteArray &body)
{
    const QJsonObject root = QJsonDocument::fromJson(body).object();
    EndpointStatus &status = statuses_[endpointId];
    status.reachable = true;
    status.detail.clear();

    const QJsonObject system = root.value(QStringLiteral("system")).toObject();
    status.comfyVersion = system.value(QStringLiteral("comfyui_version")).toString().trimmed();

    const QJsonArray devices = root.value(QStringLiteral("devices")).toArray();
    if (!devices.isEmpty())
    {
        const QJsonObject device = devices.first().toObject();
        status.gpuName = device.value(QStringLiteral("name")).toString().trimmed();
        status.vramTotalGb = gigabytes(device.value(QStringLiteral("vram_total")));
        status.vramFreeGb = gigabytes(device.value(QStringLiteral("vram_free")));
    }

    // The endpoint answered, so the follow-ups are safe to ask for. They are separate requests on
    // purpose: either can fail without taking the health verdict with it.
    const QString url = baseUrls_.value(endpointId);
    if (url.isEmpty())
        return;
    get(endpointId, url + QStringLiteral("/queue"), kDetailTimeoutMs, &EndpointProbe::applyQueue);
    get(endpointId, url + QStringLiteral("/models/checkpoints"), kDetailTimeoutMs,
        &EndpointProbe::applyModels);
}

void EndpointProbe::applyQueue(const QString &endpointId, const QByteArray &body)
{
    const QJsonObject root = QJsonDocument::fromJson(body).object();
    EndpointStatus &status = statuses_[endpointId];
    status.queueKnown = true;
    status.busy = !root.value(QStringLiteral("queue_running")).toArray().isEmpty();
}

void EndpointProbe::applyModels(const QString &endpointId, const QByteArray &body)
{
    const QJsonArray names = QJsonDocument::fromJson(body).array();
    EndpointStatus &status = statuses_[endpointId];
    status.modelsKnown = true;
    status.checkpoints.clear();
    for (const QJsonValue &value : names)
    {
        const QString name = value.toString().trimmed();
        if (!name.isEmpty())
            status.checkpoints.append(name);
    }
}

} // namespace spellvision::shell
