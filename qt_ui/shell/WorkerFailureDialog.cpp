#include "WorkerFailureDialog.h"

#include <QMessageBox>
#include <QWidget>

namespace spellvision::shell
{

void showWorkerFailure(QWidget *parent, const QString &title, const QString &body, const QString &stderrText)
{
    QMessageBox box(parent);
    box.setIcon(QMessageBox::Warning);
    box.setWindowTitle(title);
    box.setText(body);
    const QString detail = stderrText.trimmed();
    if (!detail.isEmpty())
        box.setDetailedText(detail);
    box.setStandardButtons(QMessageBox::Ok);
    box.exec();
}

} // namespace spellvision::shell
