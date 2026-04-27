#include "CatalogPickerDialog.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QDialogButtonBox>
#include <QDir>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QSettings>
#include <QSplitter>
#include <QVBoxLayout>

#include <algorithm>

namespace spellvision::assets
{

CatalogPickerDialog::CatalogPickerDialog(const QString &title,
                    const QVector<CatalogEntry> &entries,
                    const QString &currentValue,
                    const QString &recentSettingsKey,
                    QWidget *parent)
    : QDialog(parent), entries_(entries), recentSettingsKey_(recentSettingsKey)
{
    setWindowTitle(title);
    resize(860, 620);

    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(14, 14, 14, 14);
    layout->setSpacing(10);

    auto *header = new QVBoxLayout;
    header->setContentsMargins(0, 0, 0, 0);
    header->setSpacing(6);

    searchEdit_ = new QLineEdit(this);
    searchEdit_->setPlaceholderText(QStringLiteral("Search by name, folder, file path, or family keyword"));
    header->addWidget(searchEdit_);

    auto *toolbar = new QHBoxLayout;
    toolbar->setContentsMargins(0, 0, 0, 0);
    toolbar->setSpacing(8);

    recentOnlyCheck_ = new QCheckBox(QStringLiteral("Recent only"), this);
    resultsLabel_ = new QLabel(this);
    resultsLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    toolbar->addWidget(recentOnlyCheck_);
    toolbar->addStretch(1);
    toolbar->addWidget(resultsLabel_);
    header->addLayout(toolbar);
    layout->addLayout(header);

    splitter_ = new QSplitter(Qt::Horizontal, this);

    listWidget_ = new QListWidget(splitter_);
    listWidget_->setSelectionMode(QAbstractItemView::SingleSelection);
    listWidget_->setAlternatingRowColors(true);

    auto *detailPane = new QWidget(splitter_);
    auto *detailLayout = new QVBoxLayout(detailPane);
    detailLayout->setContentsMargins(0, 0, 0, 0);
    detailLayout->setSpacing(8);

    detailTitleLabel_ = new QLabel(QStringLiteral("Select an asset"), detailPane);
    detailTitleLabel_->setObjectName(QStringLiteral("SectionTitle"));
    detailMetaLabel_ = new QLabel(QStringLiteral("Search and browse by recognition instead of recalling file names."), detailPane);
    detailMetaLabel_->setObjectName(QStringLiteral("SectionBody"));
    detailMetaLabel_->setWordWrap(true);
    detailPathLabel_ = new QLabel(detailPane);
    detailPathLabel_->setObjectName(QStringLiteral("ImageGenHint"));
    detailPathLabel_->setWordWrap(true);

    detailLayout->addWidget(detailTitleLabel_);
    detailLayout->addWidget(detailMetaLabel_);
    detailLayout->addWidget(detailPathLabel_);
    detailLayout->addStretch(1);

    splitter_->addWidget(listWidget_);
    splitter_->addWidget(detailPane);
    splitter_->setStretchFactor(0, 1);
    splitter_->setStretchFactor(1, 0);
    splitter_->setSizes({520, 260});
    layout->addWidget(splitter_, 1);

    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
    layout->addWidget(buttons);

    QObject::connect(searchEdit_, &QLineEdit::textChanged, this, [this](const QString &) { rebuild(); });
    QObject::connect(recentOnlyCheck_, &QCheckBox::toggled, this, [this](bool) { rebuild(); });
    QObject::connect(listWidget_, &QListWidget::currentItemChanged, this, [this](QListWidgetItem *current, QListWidgetItem *) { updateDetails(current); });
    QObject::connect(listWidget_, &QListWidget::itemDoubleClicked, this, [this](QListWidgetItem *) { accept(); });
    QObject::connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
    QObject::connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);

    const QStringList rawRecent = QSettings().value(recentSettingsKey_).toStringList();
    for (const QString &value : rawRecent)
    {
        const QString trimmed = value.trimmed();
        if (!trimmed.isEmpty() && !recentValues_.contains(trimmed))
            recentValues_.push_back(trimmed);
    }

    currentValue_ = currentValue.trimmed();
    rebuild();

    if (!currentValue_.isEmpty())
    {
        for (int row = 0; row < listWidget_->count(); ++row)
        {
            QListWidgetItem *item = listWidget_->item(row);
            if (item && item->data(Qt::UserRole).toString().compare(currentValue_, Qt::CaseInsensitive) == 0)
            {
                listWidget_->setCurrentRow(row);
                break;
            }
        }
    }

    if (listWidget_->currentRow() < 0 && listWidget_->count() > 0)
        listWidget_->setCurrentRow(0);
}


QString CatalogPickerDialog::selectedValue() const
{
    const QListWidgetItem *item = listWidget_ ? listWidget_->currentItem() : nullptr;
    return item ? item->data(Qt::UserRole).toString() : QString();
}


QString CatalogPickerDialog::selectedDisplay() const
{
    const QListWidgetItem *item = listWidget_ ? listWidget_->currentItem() : nullptr;
    return item ? item->data(Qt::UserRole + 1).toString() : QString();
}


void CatalogPickerDialog::rebuild()
{
    const QString needle = searchEdit_ ? searchEdit_->text().trimmed().toLower() : QString();
    const bool recentOnly = recentOnlyCheck_ && recentOnlyCheck_->isChecked();
    listWidget_->clear();

    QVector<CatalogEntry> sorted = entries_;
    std::sort(sorted.begin(), sorted.end(), [this](const CatalogEntry &lhs, const CatalogEntry &rhs) {
        const int lhsRecent = recentRank(lhs.value);
        const int rhsRecent = recentRank(rhs.value);
        const bool lhsCurrent = !currentValue_.isEmpty() && lhs.value.compare(currentValue_, Qt::CaseInsensitive) == 0;
        const bool rhsCurrent = !currentValue_.isEmpty() && rhs.value.compare(currentValue_, Qt::CaseInsensitive) == 0;
        if (lhsCurrent != rhsCurrent)
            return lhsCurrent;
        if ((lhsRecent >= 0) != (rhsRecent >= 0))
            return lhsRecent >= 0;
        if (lhsRecent >= 0 && rhsRecent >= 0 && lhsRecent != rhsRecent)
            return lhsRecent < rhsRecent;
        return QString::compare(lhs.display, rhs.display, Qt::CaseInsensitive) < 0;
    });

    int visibleCount = 0;
    for (const CatalogEntry &entry : sorted)
    {
        const QString trimmedValue = entry.value.trimmed();
        const bool isRecent = recentRank(trimmedValue) >= 0;
        if (recentOnly && !isRecent)
            continue;

        const QString haystack = QStringLiteral("%1 %2 %3 %4 %5 %6")
                                     .arg(entry.display, trimmedValue, entry.family, entry.modality, entry.role, entry.note)
                                     .toLower();
        if (!needle.isEmpty() && !haystack.contains(needle))
            continue;

        QString display = entry.display;
        if (display.trimmed().isEmpty())
            display = QFileInfo(trimmedValue).completeBaseName();
        if (display.trimmed().isEmpty())
            display = trimmedValue;

        const QFileInfo info(trimmedValue);
        QString secondary;
        if (info.exists())
        {
            secondary = info.dir().dirName();
            if (!secondary.isEmpty())
                display = QStringLiteral("%1  •  %2").arg(display, secondary);
        }

        auto *item = new QListWidgetItem(display, listWidget_);
        item->setData(Qt::UserRole, trimmedValue);
        item->setData(Qt::UserRole + 1, entry.display);
        item->setData(Qt::UserRole + 2, isRecent);
        item->setData(Qt::UserRole + 3, entry.family);
        item->setData(Qt::UserRole + 4, entry.modality);
        item->setData(Qt::UserRole + 5, entry.role);
        item->setData(Qt::UserRole + 6, entry.note);
        item->setToolTip(trimmedValue);
        ++visibleCount;
    }

    if (resultsLabel_)
        resultsLabel_->setText(QStringLiteral("%1 result%2").arg(visibleCount).arg(visibleCount == 1 ? QString() : QStringLiteral("s")));
}


int CatalogPickerDialog::recentRank(const QString &value) const
{
    for (int index = 0; index < recentValues_.size(); ++index)
    {
        if (recentValues_.at(index).compare(value, Qt::CaseInsensitive) == 0)
            return index;
    }
    return -1;
}


void CatalogPickerDialog::updateDetails(QListWidgetItem *item)
{
    if (!item)
    {
        detailTitleLabel_->setText(QStringLiteral("Select an asset"));
        detailMetaLabel_->setText(QStringLiteral("Search and browse by recognition instead of recalling file names."));
        detailPathLabel_->clear();
        return;
    }

    const QString value = item->data(Qt::UserRole).toString();
    const QString display = item->data(Qt::UserRole + 1).toString();
    const bool isRecent = item->data(Qt::UserRole + 2).toBool();
    const QFileInfo info(value);
    const QString family = item->data(Qt::UserRole + 3).toString().trimmed();
    const QString modality = item->data(Qt::UserRole + 4).toString().trimmed();
    const QString role = item->data(Qt::UserRole + 5).toString().trimmed();
    const QString note = item->data(Qt::UserRole + 6).toString().trimmed();

    detailTitleLabel_->setText(display.trimmed().isEmpty() ? value : display);

    QStringList meta;
    if (isRecent)
        meta << QStringLiteral("Recent selection");
    if (!modality.isEmpty())
        meta << QStringLiteral("Modality: %1").arg(modality);
    if (!family.isEmpty())
        meta << QStringLiteral("Family: %1").arg(family);
    if (!role.isEmpty())
        meta << QStringLiteral("Role: %1").arg(role);
    if (!note.isEmpty())
        meta << note;
    if (info.exists())
    {
        meta << (info.isDir() ? QStringLiteral("Directory") : QStringLiteral("File"));
        if (!info.suffix().trimmed().isEmpty())
            meta << QStringLiteral(".%1").arg(info.suffix().toLower());
        const qint64 sizeMb = info.size() / (1024 * 1024);
        if (sizeMb > 0)
            meta << QStringLiteral("%1 MB").arg(sizeMb);
        const QString folder = info.dir().dirName().trimmed();
        if (!folder.isEmpty())
            meta << QStringLiteral("Folder: %1").arg(folder);
    }
    else if (!value.trimmed().isEmpty())
    {
        meta << QStringLiteral("External or unresolved path");
    }
    detailMetaLabel_->setText(meta.join(QStringLiteral(" · ")));
    detailPathLabel_->setText(value);
    detailPathLabel_->setToolTip(value);
}


void persistRecentSelection(const QString &settingsKey, const QString &value)
{
    const QString trimmed = value.trimmed();
    if (settingsKey.trimmed().isEmpty() || trimmed.isEmpty())
        return;

    QSettings settings;
    QStringList values = settings.value(settingsKey).toStringList();
    values.removeAll(trimmed);
    values.prepend(trimmed);
    while (values.size() > 12)
        values.removeLast();
    settings.setValue(settingsKey, values);
}


} // namespace spellvision::assets
