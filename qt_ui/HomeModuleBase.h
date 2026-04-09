#pragma once

#include "HomeDashboardTypes.h"

#include <QSize>
#include <QWidget>

class HomeModuleBase : public QWidget
{
    Q_OBJECT

public:
    explicit HomeModuleBase(QWidget *parent = nullptr);
    ~HomeModuleBase() override = default;

    virtual QString moduleId() const = 0;
    virtual QString displayName() const = 0;

    virtual void applyPreferences(const HomeModulePreferences &prefs) = 0;
    virtual QSize minimumDashboardSpan() const = 0;
    virtual QSize preferredDashboardSpan() const = 0;

    virtual void setRuntimeSummary(const HomeRuntimeSummary &summary);
    virtual void setCustomizeMode(bool enabled);

signals:
    void modeRequested(const QString &modeId);
    void managerRequested(const QString &managerId);
    void launchRequested(const QString &modeId,
                         const QString &title,
                         const QString &subtitle,
                         const QString &sourceLabel);
    void starterPreviewRequested(const QString &title,
                                 const QString &subtitle,
                                 const QString &modeId,
                                 const QString &sourceLabel);

protected:
    bool customizeMode_ = false;
    HomeRuntimeSummary runtimeSummary_;
};
