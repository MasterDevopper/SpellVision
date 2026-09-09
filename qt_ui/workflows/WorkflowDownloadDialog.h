#pragma once

#include <QDialog>
#include <QStringList>

class QLabel;

// T2: one dialog after a workflow drop that still has missing node classes.
// Nothing is fetched in the constructor. Download is Accepted; Not now is Rejected.
class WorkflowDownloadDialog : public QDialog
{
    Q_OBJECT

public:
    explicit WorkflowDownloadDialog(const QStringList &missingNodeClasses,
                                    QWidget *parent = nullptr);
};
