#pragma once

#include <QStringList>
#include <QWidget>
#include <functional>

#include "shell/EndpointProbe.h"
#include "shell/EndpointRegistry.h"

class QCheckBox;
class QLabel;
class QListWidget;
class QListWidgetItem;
class QPushButton;
class QTableWidget;

namespace spellvision::shell
{

// The Runtime page's list of machines, rendered from facts rather than from a sentence.
//
// What it replaces, and why the replacement is smaller than the thing it replaces:
//
//   * Doc 54 chose ComfyUI-Distributed. The research overturned it. With no reachable worker the
//     pack logs "Falling back to master execution" and runs the job HERE -- the exact opposite of
//     the fail-closed requirement -- and its master-free mode is an open feature request (#48). It
//     also needs its own Collector and Seed nodes injected into every graph, and its semantics are
//     parallel-batch, not route-this-job-there. NetDist, the alternative, substitutes a BLACK IMAGE
//     when a fetch fails and last shipped in February 2024.
//   * So the Enable-ComfyUI-Distributed button, its zipball install and the share-folder consent
//     are gone. The button could never have worked in any case: `install_custom_node` is in
//     LOCAL_INSTALL_COMMANDS and is refused for a remote COMFY_API_URL by design, so it installed
//     the pack into THIS machine's custom_nodes and reported success.
//
// What is here instead is the endpoint registry, each row carrying what that machine answered.
class EndpointPanel : public QWidget
{
    Q_OBJECT

public:
    enum Column
    {
        LabelColumn = 0,
        UrlColumn,
        StatusColumn,
        VersionColumn,
        GpuColumn,
        ModelsColumn,
        FamiliesColumn,
        ColumnCount,
    };

    explicit EndpointPanel(QWidget *parent = nullptr);

    // Where a row's facts come from. Defaults to EndpointProbe::instance(); a test supplies its own
    // so the panel can be driven without an HTTP server, which would be testing QNetworkAccessManager.
    void setStatusResolver(std::function<EndpointStatus(const QString &)> resolver);

    void setRegistry(const EndpointRegistry &registry);
    [[nodiscard]] const EndpointRegistry &registry() const { return registry_; }

    void refreshRows();

    [[nodiscard]] int rowCount() const;
    [[nodiscard]] QString cellText(int row, Column column) const;
    void selectRow(int row);
    [[nodiscard]] QString selectedEndpointId() const;

    // The gestures, as OUTCOMES. Each returns whether it changed anything, and leaves the reason in
    // lastRefusal() when it did not -- so a test asserts what happened rather than whether a button
    // looked enabled. (UIA's IsEnabled lied to the last wave; a disabled-looking control and a
    // refused action are not the same claim.)
    bool removeSelected();
    bool addEndpoint(const QString &label, const QString &url);
    bool renameSelected(const QString &label);
    bool setSelectedEnabled(bool enabled);

    // The user may untick a family. There is no tick: an entry is written only by a real render on
    // that endpoint, through recordGateRender().
    bool setFamilyChecked(const QString &family, bool checked);
    bool recordGateRender(const QString &endpointId, const QString &family);
    [[nodiscard]] QStringList familiesShown() const;
    [[nodiscard]] bool familyIsTicked(const QString &family) const;

    [[nodiscard]] QString lastRefusal() const { return lastRefusal_; }

    [[nodiscard]] bool remoteQueuingAllowed() const;
    void setRemoteQueuingAllowed(bool allowed);

    // "offline", "online", "rendering", "not checked" -- one sentence per state, derived.
    [[nodiscard]] static QString statusText(const Endpoint &endpoint, const EndpointStatus &status);

    // Every family the model registry knows, which is what a checklist may show. Not a list written
    // here: a hand-kept one would go stale the first time a family was added.
    [[nodiscard]] static QStringList knownFamilies();

signals:
    void registryChanged();
    void refreshRequested();

private:
    void buildUi();
    void rebuildFamilyList();
    void onFamilyItemChanged(QListWidgetItem *item);

    EndpointRegistry registry_;
    std::function<EndpointStatus(const QString &)> statusResolver_;
    QString lastRefusal_;
    bool applyingFamilies_ = false;

    QTableWidget *table_ = nullptr;
    QListWidget *familyList_ = nullptr;
    QCheckBox *remoteConsentCheck_ = nullptr;
    QPushButton *addButton_ = nullptr;
    QPushButton *editButton_ = nullptr;
    QPushButton *removeButton_ = nullptr;
    QPushButton *refreshButton_ = nullptr;
    QLabel *honestyLabel_ = nullptr;
    QLabel *familyCaption_ = nullptr;
};

} // namespace spellvision::shell
