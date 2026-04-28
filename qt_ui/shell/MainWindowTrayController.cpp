#include "MainWindowTrayController.h"

#include <QDockWidget>
#include <QMainWindow>
#include <QString>
#include <QWidget>

namespace spellvision::shell
{

void MainWindowTrayController::buildPersistentDocks(const Bindings &bindings)
{
    if (!bindings.owner || !bindings.queueDock || !bindings.createBottomUtilityWidget)
        return;

    auto *queueDock = new QDockWidget(QStringLiteral("UtilityTray"), bindings.owner);
    queueDock->setObjectName(QStringLiteral("QueueDock"));
    queueDock->setAllowedAreas(Qt::BottomDockWidgetArea);
    queueDock->setFeatures(QDockWidget::DockWidgetMovable | QDockWidget::DockWidgetFloatable);

    QWidget *bottomUtilityWidget = bindings.createBottomUtilityWidget();
    if (!bottomUtilityWidget)
        bottomUtilityWidget = new QWidget(queueDock);
    queueDock->setWidget(bottomUtilityWidget);

    if (bindings.hideNativeDockTitleBar)
        bindings.hideNativeDockTitleBar(queueDock);

    bindings.owner->addDockWidget(Qt::BottomDockWidgetArea, queueDock);

    *bindings.queueDock = queueDock;

    if (bindings.detailsDock)
        *bindings.detailsDock = nullptr;
    if (bindings.logsDock)
        *bindings.logsDock = nullptr;

    if (bindings.updateDockChrome)
        bindings.updateDockChrome();
}

} // namespace spellvision::shell
