#include <QApplication>
#include <QString>
#include <QStringList>
#include "MainWindow.h"
#include "chain/ChainSelfTest.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QApplication::setApplicationName("SpellVision");
    QApplication::setOrganizationName("Dark Duck Studio");

    // --- CHAIN STUDIO PASS 6 SELF-TEST ---
    // Headless verification entry point. When --chain-selftest is
    // present we run the chain studio engine harness and exit
    // with the number of failed scenarios (0 == all passed).
    // MainWindow is NEVER constructed in this path.
    if (QCoreApplication::arguments().contains(QStringLiteral("--chain-selftest")))
        return spellvision::chain::runChainSelfTest();

    MainWindow window;
    window.show();

    return app.exec();
}
