#pragma once

#include <QJsonArray>
#include <QList>
#include <QString>
#include <QStringList>

class QSettings;

namespace spellvision::shell
{

// The machines this install may render on.
//
// The second machine used to be a STRING LITERAL in ManagerPage.cpp: one literal printed it into a
// label, a second one probed http://192.168.1.127:8188/system_stats, and the label's own TEXT was
// then scraped for "healthy=yes" to decide whether the master was up. Three copies of one fact, the
// last of them stored in a QLabel -- so the app could not be pointed at a different second machine
// without a rebuild, and nothing outside that page could ask what endpoints exist at all.
//
// Endpoints are data now. They live in QSettings under `runtime/endpoints` as a JSON array, the
// worker receives the chosen one PER REQUEST (python/comfy_endpoint.py resolves `comfy_api_url`
// first), and nothing on the Python side keeps a second copy of the list.
struct Endpoint
{
    QString id;                  // stable across relabels and re-addressing; "local" for entry 0
    QString label;
    QString baseUrl;             // scheme://host:port, never a trailing slash
    bool enabled = true;

    // Families this endpoint has been PROVEN to render, one entry per family whose gate render
    // really succeeded there. Empty means nothing has been proven yet, and for a remote endpoint
    // that means it may not be routed to -- fail-closed, because "a 3090 Ti probably does Wan 2.2"
    // is a guess and a queued job that fails twenty minutes later is the cost of it.
    QStringList familiesAllowed;

    [[nodiscard]] bool isLocal() const;

    // Whether familiesAllowed gates routing. The local master is NOT gated: it is the machine this
    // app has always rendered on, and gating it would mean a fresh install could run nothing at
    // all. The asymmetry is deliberate and is the whole difference between entry 0 and the rest.
    [[nodiscard]] bool isGated() const { return !isLocal(); }
};

// "spellnode:8188" -> "http://spellnode:8188"; trailing slashes removed. Empty in, empty out.
// Same accommodation python/comfy_endpoint.py and RuntimeProfile::load make for a bare host:port.
QString normalizedEndpointUrl(const QString &raw);

// Mirrors comfy_endpoint.is_local_endpoint: loopback by ADDRESS, not by string equality.
bool endpointUrlIsLocal(const QString &url);

class EndpointRegistry
{
public:
    static QString localId();       // "local"
    static QString settingsKey();   // "runtime/endpoints"

    // Entry 0 only: the machine RuntimeProfile resolved. `localBaseUrl` is a parameter rather than
    // a literal here so this module never spells a host or a port -- the resolver owns that, and a
    // tenth endpoint resolver is exactly what CLAUDE.md 9 warns about.
    static EndpointRegistry defaults(const QString &localBaseUrl);

    // A stored value that does not parse, is not an array, or holds nothing usable yields the
    // DEFAULT registry, never an empty one. An empty registry has no local master, which would
    // leave the app unable to render on the machine it is running on -- a corrupt setting must not
    // be able to do that.
    static EndpointRegistry fromJson(const QJsonArray &stored, const QString &localBaseUrl);
    static EndpointRegistry load(QSettings &settings, const QString &localBaseUrl);
    static EndpointRegistry load(const QString &localBaseUrl);

    [[nodiscard]] QJsonArray toJson() const;
    void save(QSettings &settings) const;
    void save() const;

    [[nodiscard]] const QList<Endpoint> &entries() const { return entries_; }
    [[nodiscard]] int count() const { return entries_.size(); }
    [[nodiscard]] int indexOf(const QString &id) const;
    [[nodiscard]] const Endpoint *find(const QString &id) const;
    [[nodiscard]] const Endpoint &local() const { return entries_.first(); }

    // An id that is not already taken, derived from the label so it reads as something.
    [[nodiscard]] QString proposeId(const QString &label) const;

    // Add or replace. Refuses, with a reason, when the URL is unusable, when it duplicates another
    // entry's URL, or when it would re-address or rename the local master out from under the
    // resolver that owns it.
    //
    // The duplicate check is where the queue-lane question lands. python/worker_queue keys its
    // lanes on the endpoint URL string, so two entries for ONE machine would be two lanes and the
    // box would be given two concurrent jobs. Keying lanes on `id` would not have fixed that --
    // two entries have two ids either way -- so the fix belongs here, where the duplicate is
    // created. Residual, stated: two DNS names for one host still defeat it.
    bool upsert(const Endpoint &endpoint, QString *reason = nullptr);

    // The local master cannot be removed. It is the machine the app is running on.
    bool remove(const QString &id, QString *reason = nullptr);

    bool setEnabled(const QString &id, bool enabled);

    // Written by the app after a render really succeeded on that endpoint, and only then.
    bool allowFamily(const QString &id, const QString &family);
    // The user may untick. There is no tick: a checklist a user can fill in is a claim about
    // another machine that nothing measured.
    bool disallowFamily(const QString &id, const QString &family);

private:
    QList<Endpoint> entries_;
};

} // namespace spellvision::shell
