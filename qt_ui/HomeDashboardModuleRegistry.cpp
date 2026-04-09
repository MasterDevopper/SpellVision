#include "HomeDashboardModuleRegistry.h"

#include "HomeModuleBase.h"

HomeDashboardModuleRegistry &HomeDashboardModuleRegistry::instance()
{
    static HomeDashboardModuleRegistry registry;
    return registry;
}

void HomeDashboardModuleRegistry::registerModule(const QString &moduleId, HomeModuleFactory factory)
{
    if (moduleId.trimmed().isEmpty())
        return;
    if (!factory)
        return;

    factories_.insert(moduleId, std::move(factory));
}

HomeModuleBase *HomeDashboardModuleRegistry::create(const QString &moduleId, QWidget *parent) const
{
    const auto it = factories_.find(moduleId);
    if (it == factories_.end())
        return nullptr;

    return it.value()(parent);
}

QStringList HomeDashboardModuleRegistry::availableModuleIds() const
{
    return factories_.keys();
}

bool HomeDashboardModuleRegistry::contains(const QString &moduleId) const
{
    return factories_.contains(moduleId);
}
