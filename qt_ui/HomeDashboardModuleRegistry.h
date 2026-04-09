#pragma once

#include <functional>

#include <QHash>
#include <QString>
#include <QStringList>

class HomeModuleBase;
class QWidget;

using HomeModuleFactory = std::function<HomeModuleBase *(QWidget *parent)>;

class HomeDashboardModuleRegistry
{
public:
    static HomeDashboardModuleRegistry &instance();

    void registerModule(const QString &moduleId, HomeModuleFactory factory);
    HomeModuleBase *create(const QString &moduleId, QWidget *parent) const;
    QStringList availableModuleIds() const;
    bool contains(const QString &moduleId) const;

private:
    HomeDashboardModuleRegistry() = default;

    QHash<QString, HomeModuleFactory> factories_;
};
