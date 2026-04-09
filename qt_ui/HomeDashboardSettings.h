#pragma once

#include "HomeDashboardTypes.h"

#include <QObject>

class HomeDashboardSettings : public QObject
{
    Q_OBJECT

public:
    explicit HomeDashboardSettings(QObject *parent = nullptr);

    HomeDashboardConfig load() const;
    void save(const HomeDashboardConfig &config);
    void reset(HomeDashboardPreset preset);

private:
    QString serialize(const HomeDashboardConfig &config) const;
    HomeDashboardConfig deserialize(const QString &jsonText) const;
};
