#include "shell/EndpointPanel.h"

// The rendering half of EndpointPanel: what each row SAYS, and what the family checklist shows.
//
// Split from the widget's construction and its gestures for the same reason
// ImageGenerationPage_catalog.cpp is split from ImageGenerationPage.cpp -- one class, one header,
// two translation units, each under the size a person can hold in their head. What lives here is
// everything that turns a fact into a string, which is exactly the part that has to be able to say
// "not listed" where a careless version would say "0".

#include <QHeaderView>
#include <QLabel>
#include <QListWidget>
#include <QTableWidget>

#include "assets/FamilyLicenseTable.h"

namespace spellvision::shell
{

QStringList EndpointPanel::knownFamilies()
{
    QStringList families;
    for (const auto &row : assets::generated::kFamilyLicenseTable)
    {
        const QString key = QString::fromLatin1(row.key);
        if (key == QString::fromLatin1(assets::generated::kFamilyLicenseFallbackKey))
            continue;
        families.append(key);
    }
    return families;
}


QString EndpointPanel::statusText(const Endpoint &endpoint, const EndpointStatus &status)
{
    if (!endpoint.enabled)
        return QStringLiteral("off");
    if (!status.probed)
        return QStringLiteral("not checked");
    if (!status.reachable)
        return QStringLiteral("offline");
    if (status.queueKnown && status.busy)
        return QStringLiteral("rendering");
    return QStringLiteral("online");
}


void EndpointPanel::refreshRows()
{
    if (!table_)
        return;
    const QString keepSelected = selectedEndpointId();
    table_->setRowCount(registry_.count());
    for (int row = 0; row < registry_.count(); ++row)
    {
        const Endpoint &endpoint = registry_.entries().at(row);
        const EndpointStatus status = statusResolver_ ? statusResolver_(endpoint.id)
                                                      : EndpointStatus();
        const QString vram = status.vramTotalGb > 0.0
            ? QStringLiteral("%1 (%2 / %3 GB free)")
                  .arg(status.gpuName)
                  .arg(status.vramFreeGb, 0, 'f', 1)
                  .arg(status.vramTotalGb, 0, 'f', 1)
            : status.gpuName;
        // "not listed" is not "none". An endpoint that could not answer must not render as a
        // machine holding zero checkpoints -- that is a fact, and this is the absence of one.
        const QString models = status.modelsKnown ? QString::number(status.checkpoints.size())
                                                  : QStringLiteral("not listed");
        const QStringList cells{
            endpoint.label,
            endpoint.baseUrl,
            statusText(endpoint, status),
            status.comfyVersion,
            vram,
            models,
            endpoint.familiesAllowed.isEmpty() ? QStringLiteral("none yet")
                                               : endpoint.familiesAllowed.join(QStringLiteral(", ")),
        };
        for (int column = 0; column < ColumnCount; ++column)
        {
            auto *item = new QTableWidgetItem(cells.at(column));
            if (column == LabelColumn)
                item->setData(Qt::UserRole, endpoint.id);
            table_->setItem(row, column, item);
        }
    }
    if (!keepSelected.isEmpty())
    {
        const int index = registry_.indexOf(keepSelected);
        if (index >= 0)
            table_->selectRow(index);
    }
    else if (registry_.count() > 0 && table_->currentRow() < 0)
    {
        table_->selectRow(0);
    }
    rebuildFamilyList();
}


int EndpointPanel::rowCount() const
{
    return table_ ? table_->rowCount() : 0;
}

QString EndpointPanel::cellText(int row, Column column) const
{
    if (!table_ || row < 0 || row >= table_->rowCount())
        return {};
    const QTableWidgetItem *item = table_->item(row, column);
    return item ? item->text() : QString();
}

void EndpointPanel::selectRow(int row)
{
    if (table_ && row >= 0 && row < table_->rowCount())
        table_->selectRow(row);
}

QString EndpointPanel::selectedEndpointId() const
{
    if (!table_)
        return {};
    const int row = table_->currentRow();
    if (row < 0 || row >= registry_.count())
        return {};
    return registry_.entries().at(row).id;
}


void EndpointPanel::rebuildFamilyList()
{
    if (!familyList_)
        return;
    applyingFamilies_ = true;
    familyList_->clear();
    const Endpoint *endpoint = registry_.find(selectedEndpointId());
    for (const QString &family : knownFamilies())
    {
        const bool ticked = endpoint && endpoint->familiesAllowed.contains(family);
        auto *item = new QListWidgetItem(family, familyList_);
        item->setCheckState(ticked ? Qt::Checked : Qt::Unchecked);
        // An unticked family is not tickable. The tick is an OUTCOME -- it appears when a render
        // has finished on that machine -- so offering the gesture would be offering the user a way
        // to state something about another computer that nothing has measured.
        Qt::ItemFlags flags = item->flags();
        if (ticked)
            flags |= Qt::ItemIsEnabled;
        else
            flags &= ~Qt::ItemIsEnabled;
        item->setFlags(flags);
        if (!ticked)
        {
            item->setToolTip(QStringLiteral(
                "Not proven here yet. SpellVision ticks a family after a render really finishes on "
                "this machine."));
        }
    }
    if (endpoint && !endpoint->isGated())
    {
        familyCaption_->setText(QStringLiteral(
            "This machine is the master -- every family runs here; the list is a record, not a gate."));
    }
    else
    {
        familyCaption_->setText(QStringLiteral(
            "Proven families. An unticked family will not be queued to this machine."));
    }
    applyingFamilies_ = false;
}


QStringList EndpointPanel::familiesShown() const
{
    QStringList shown;
    if (!familyList_)
        return shown;
    for (int row = 0; row < familyList_->count(); ++row)
        shown.append(familyList_->item(row)->text());
    return shown;
}

bool EndpointPanel::familyIsTicked(const QString &family) const
{
    const Endpoint *endpoint = registry_.find(selectedEndpointId());
    return endpoint && endpoint->familiesAllowed.contains(family.trimmed().toLower());
}

} // namespace spellvision::shell
