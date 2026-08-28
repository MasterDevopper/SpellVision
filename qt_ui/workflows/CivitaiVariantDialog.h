#pragma once

#include <QDialog>
#include <QJsonArray>
#include <QString>

class QButtonGroup;

// Which version of a Civitai model should we download?
//
// A Civitai model-page URL names no version, and one model id can hold variants built on
// completely different architectures -- "Vintage Mix by AK" has six spanning Flux.1 D,
// ZImageTurbo, Pony, Krea 2, SDXL 1.0 and Illustrious. Taking the first was a silent wrong-model
// download that succeeded and looked fine, so this asks instead.
//
// Architecture narrows but does not decide: Pony, Illustrious and SDXL 1.0 all load SDXL, so three
// of those six are equally valid for an SDXL workflow. Compatible ones are marked and sorted
// first; none of them are hidden, and none is preselected.
class CivitaiVariantDialog : public QDialog
{
    Q_OBJECT

public:
    CivitaiVariantDialog(const QString &modelName,
                         const QJsonArray &variants,
                         const QString &preferredArchitecture,
                         QWidget *parent = nullptr);

    // Empty until the user picks one and accepts.
    QString selectedDownloadUrl() const { return selectedUrl_; }
    QString selectedVersionName() const { return selectedVersionName_; }
    QString selectedFilename() const { return selectedFilename_; }

private:
    void applyTheme();

    QButtonGroup *group_ = nullptr;
    QString selectedUrl_;
    QString selectedVersionName_;
    QString selectedFilename_;
};
