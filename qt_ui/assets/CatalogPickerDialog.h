#pragma once

#include <QDialog>
#include <QJsonObject>
#include <QString>
#include <QStringList>
#include <QVector>

class QCheckBox;
class QLabel;
class QLineEdit;
class QListWidget;
class QListWidgetItem;
class QSplitter;
class QWidget;

namespace spellvision::assets
{

struct CatalogEntry
{
    QString display;
    QString value;
    QString family;
    QString modality;
    QString role;
    QString note;
    QJsonObject metadata;
};

class CatalogPickerDialog final : public QDialog
{
public:
    CatalogPickerDialog(const QString &title,
                        const QVector<CatalogEntry> &entries,
                        const QString &currentValue,
                        const QString &recentSettingsKey,
                        QWidget *parent = nullptr);

    QString selectedValue() const;
    QString selectedDisplay() const;

private:
    void rebuild();
    int recentRank(const QString &value) const;
    void updateDetails(QListWidgetItem *item);

    QVector<CatalogEntry> entries_;
    QStringList recentValues_;
    QString recentSettingsKey_;
    QString currentValue_;
    QLineEdit *searchEdit_ = nullptr;
    QCheckBox *recentOnlyCheck_ = nullptr;
    QLabel *resultsLabel_ = nullptr;
    QSplitter *splitter_ = nullptr;
    QListWidget *listWidget_ = nullptr;
    QLabel *detailTitleLabel_ = nullptr;
    QLabel *detailMetaLabel_ = nullptr;
    QLabel *detailPathLabel_ = nullptr;
};

void persistRecentSelection(const QString &settingsKey, const QString &value);

} // namespace spellvision::assets
