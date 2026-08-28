#include "workflows/CivitaiVariantDialog.h"

#include "ThemeManager.h"

#include <QButtonGroup>
#include <QDialogButtonBox>
#include <QJsonObject>
#include <QJsonValue>
#include <QLabel>
#include <QPushButton>
#include <QRadioButton>
#include <QScrollArea>
#include <QVBoxLayout>
#include <algorithm>

namespace {

QString humanSize(double sizeKb)
{
    if (sizeKb <= 0.0)
        return QString();
    const double mb = sizeKb / 1024.0;
    if (mb < 1024.0)
        return QStringLiteral("%1 MB").arg(mb, 0, 'f', 0);
    return QStringLiteral("%1 GB").arg(mb / 1024.0, 0, 'f', 1);
}

} // namespace

CivitaiVariantDialog::CivitaiVariantDialog(const QString &modelName,
                                           const QJsonArray &variants,
                                           const QString &preferredArchitecture,
                                           QWidget *parent)
    : QDialog(parent)
{
    setWindowTitle(tr("Choose a version"));
    setModal(true);
    setMinimumWidth(660);

    ThemeManager &theme = ThemeManager::instance();
    const int card = theme.spacing(ThemeManager::Spacing::Card);

    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(theme.spacing(ThemeManager::Spacing::Section),
                              theme.spacing(ThemeManager::Spacing::Section),
                              theme.spacing(ThemeManager::Spacing::Section),
                              theme.spacing(ThemeManager::Spacing::Section));
    outer->setSpacing(card);

    auto *heading = new QLabel(
        tr("\"%1\" has %n version(s). Which one?", nullptr, variants.size()).arg(modelName), this);
    heading->setObjectName(QStringLiteral("VariantHeading"));
    heading->setWordWrap(true);
    outer->addWidget(heading);

    auto *subheading = new QLabel(
        preferredArchitecture.isEmpty()
            ? tr("The link doesn't say which one, and they are not interchangeable.")
            : tr("The link doesn't say which one. This workflow needs %1 — those are marked, "
                 "but every version is listed.").arg(preferredArchitecture.toUpper()),
        this);
    subheading->setObjectName(QStringLiteral("VariantSubheading"));
    subheading->setWordWrap(true);
    outer->addWidget(subheading);

    auto *scroll = new QScrollArea(this);
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

    auto *host = new QWidget(scroll);
    auto *rows = new QVBoxLayout(host);
    rows->setContentsMargins(0, 0, 0, 0);
    rows->setSpacing(theme.spacing(ThemeManager::Spacing::Tight));

    group_ = new QButtonGroup(this);

    // Compatible first, original order preserved within each group. Sorted rather than filtered:
    // an architecture match is a hint, and the user may know something we do not.
    QList<QJsonObject> ordered;
    ordered.reserve(variants.size());
    for (const QJsonValue &value : variants)
    {
        if (value.isObject())
            ordered.append(value.toObject());
    }
    std::stable_sort(ordered.begin(), ordered.end(),
                     [](const QJsonObject &a, const QJsonObject &b) {
                         return a.value(QStringLiteral("architecture_match")).toBool()
                                > b.value(QStringLiteral("architecture_match")).toBool();
                     });

    for (const QJsonObject &variant : ordered)
    {
        const QString versionName = variant.value(QStringLiteral("version_name")).toString();
        const QString baseModel = variant.value(QStringLiteral("base_model")).toString();
        const QString filename = variant.value(QStringLiteral("filename")).toString();
        const QString size = humanSize(variant.value(QStringLiteral("size_kb")).toDouble());
        const bool matches = variant.value(QStringLiteral("architecture_match")).toBool();

        QString label = versionName;
        if (!baseModel.isEmpty())
            label += QStringLiteral("  ·  %1").arg(baseModel);
        if (!size.isEmpty())
            label += QStringLiteral("  ·  %1").arg(size);
        if (matches)
            label += tr("   ✓ compatible");

        auto *button = new QRadioButton(label, host);
        // The filename is the thing that ends up on disk, and it is what distinguishes these
        // variants from one another once downloaded -- so it is shown, not just tooltipped.
        button->setToolTip(filename);
        button->setProperty("svDownloadUrl", variant.value(QStringLiteral("download_url")).toString());
        button->setProperty("svVersionName", versionName);
        button->setProperty("svFilename", filename);
        group_->addButton(button);
        rows->addWidget(button);

        if (!filename.isEmpty())
        {
            auto *fileLabel = new QLabel(QStringLiteral("      %1").arg(filename), host);
            fileLabel->setObjectName(QStringLiteral("VariantFilename"));
            rows->addWidget(fileLabel);
        }
    }
    rows->addStretch(1);
    scroll->setWidget(host);
    outer->addWidget(scroll, 1);

    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
    QPushButton *okButton = buttons->button(QDialogButtonBox::Ok);
    okButton->setText(tr("Download"));
    // Nothing is preselected, so the action stays disabled until a deliberate choice is made.
    okButton->setEnabled(false);
    connect(group_, &QButtonGroup::buttonToggled, this, [okButton](QAbstractButton *, bool) {
        okButton->setEnabled(true);
    });
    connect(buttons, &QDialogButtonBox::accepted, this, [this]() {
        if (QAbstractButton *checked = group_->checkedButton())
        {
            selectedUrl_ = checked->property("svDownloadUrl").toString();
            selectedVersionName_ = checked->property("svVersionName").toString();
            selectedFilename_ = checked->property("svFilename").toString();
        }
        accept();
    });
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    outer->addWidget(buttons);

    applyTheme();
}

void CivitaiVariantDialog::applyTheme()
{
    ThemeManager &theme = ThemeManager::instance();

    QString sheet = QStringLiteral(
        "QDialog { background: @s0@; }"
        "QLabel { color: @mid@; }"
        "QLabel#VariantHeading { color: @hi@; font-size: 15px; font-weight: 600; }"
        "QLabel#VariantSubheading { color: @lo@; }"
        "QLabel#VariantFilename { color: @lo@; }"
        "QRadioButton { color: @hi@; padding: 4px 0; }"
        "QRadioButton:hover { color: @accent@; }"
        "QRadioButton:focus { color: @accent@; }"
        "QPushButton { background: @s2@; color: @hi@; border: 1px solid @border@;"
        "  border-radius: 5px; padding: 6px 16px; }"
        "QPushButton:hover { border-color: @strong@; }"
        "QPushButton:pressed { background: @s1@; }"
        "QPushButton:focus { border-color: @accent@; }"
        "QPushButton:disabled { color: @disabled@; border-color: @subtle@; }"
        "QPushButton:default:enabled { background: @accent@; border-color: @accent@; }"
        "QPushButton:default:enabled:hover { background: @accenthover@; }");

    sheet.replace(QStringLiteral("@s0@"), theme.css(ThemeManager::Color::Surface0));
    sheet.replace(QStringLiteral("@s1@"), theme.css(ThemeManager::Color::Surface1));
    sheet.replace(QStringLiteral("@s2@"), theme.css(ThemeManager::Color::Surface2));
    sheet.replace(QStringLiteral("@hi@"), theme.css(ThemeManager::Color::TextHi));
    sheet.replace(QStringLiteral("@mid@"), theme.css(ThemeManager::Color::TextMid));
    sheet.replace(QStringLiteral("@lo@"), theme.css(ThemeManager::Color::TextLo));
    sheet.replace(QStringLiteral("@disabled@"), theme.css(ThemeManager::Color::TextDisabled));
    sheet.replace(QStringLiteral("@border@"), theme.css(ThemeManager::Color::Border));
    sheet.replace(QStringLiteral("@strong@"), theme.css(ThemeManager::Color::BorderStrong));
    sheet.replace(QStringLiteral("@subtle@"), theme.css(ThemeManager::Color::BorderSubtle));
    sheet.replace(QStringLiteral("@accenthover@"), theme.css(ThemeManager::Color::AccentHover));
    sheet.replace(QStringLiteral("@accent@"), theme.css(ThemeManager::Color::Accent));

    setStyleSheet(sheet);
}
