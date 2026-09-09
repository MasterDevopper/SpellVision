#pragma once

#include <QDialog>
#include <QStringList>

class QLabel;
class QLineEdit;

// T2: one dialog after a workflow drop that still has missing nodes and/or models.
// Nothing is fetched in the constructor. Download is Accepted; Not now is Rejected.
// Keys are asked only when the caller says the store is empty for a needed source.
class WorkflowDownloadDialog : public QDialog
{
    Q_OBJECT

public:
    explicit WorkflowDownloadDialog(const QStringList &missingNodeClasses,
                                    const QStringList &missingModels,
                                    bool askCivitaiKey = false,
                                    bool askHfToken = false,
                                    QWidget *parent = nullptr);

    QString typedCivitaiKey() const;
    QString typedHfToken() const;

private:
    QLineEdit *civitaiKeyEdit_ = nullptr;
    QLineEdit *hfTokenEdit_ = nullptr;
};
