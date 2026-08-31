#pragma once

#include <QDialog>
#include <QJsonArray>
#include <QJsonObject>
#include <QString>
#include <QVector>

class QComboBox;
class QLabel;
class QRadioButton;
class QVBoxLayout;

// The picker for models a workflow names but the machine does not have.
//
// It presents what the worker's `resolve_missing_models` offered, per missing model, and produces
// two things: a set of downloads to start, and a set of substitutions to apply at launch. It
// performs neither -- the caller owns the download lane and the launch profile.
//
// The rule this UI exists to honour (Doc 19): never auto-download on a guess, and never silently
// substitute. Every row therefore defaults to **Skip**, an identified download is labelled as
// identified rather than "found", and a substitute always shows what it is and why it qualifies.
class ModelResolutionDialog : public QDialog
{
    Q_OBJECT

public:
    // `offers` is the `offers` array from a `model_resolution_offers` response.
    explicit ModelResolutionDialog(const QJsonArray &offers,
                                   const QString &workflowName,
                                   QWidget *parent = nullptr);

    // wanted filename -> the local model chosen to stand in for it. Only rows where the user
    // actively chose "use one I have".
    QJsonObject substitutions() const;

    // References to hand to the download lane. Only rows where the user chose "download".
    QStringList downloads() const;

    // True when at least one row is still unresolved, so the caller can say so rather than
    // implying the workflow is now runnable.
    bool hasUnresolved() const;

private:
    enum class Choice
    {
        Skip,
        Download,
        Substitute,
    };

    struct Row
    {
        QString wanted;
        QString downloadUrl;
        QRadioButton *downloadButton = nullptr;
        QRadioButton *substituteButton = nullptr;
        QRadioButton *skipButton = nullptr;
        QComboBox *substituteCombo = nullptr;
    };

    void buildRow(QVBoxLayout *layout, const QJsonObject &offer);
    Choice choiceFor(const Row &row) const;
    void applyTheme();

    QVector<Row> rows_;
    QString workflowName_;
};
