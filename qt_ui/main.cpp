#include <QApplication>
#include "MainWindow.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QApplication::setApplicationName("SpellVision");
    QApplication::setOrganizationName("Dark Duck Studio");

    MainWindow window;
    window.show();

    return app.exec();
}