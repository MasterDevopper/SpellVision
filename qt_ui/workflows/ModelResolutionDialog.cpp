#include "workflows/ModelResolutionDialog.h"

#include "ThemeManager.h"

#include <QButtonGroup>
#include <QComboBox>
#include <QDialogButtonBox>
#include <QFrame>
#include <QJsonValue>
#include <QLabel>
#include <QPushButton>
#include <QRadioButton>
#include <QScrollArea>
#include <QVBoxLayout>

namespace {

// Byte sizes arrive from Civitai in KB. A checkpoint is normally single-digit GB, and "6291456 KB"
// is not a number anyone reads.
QString humanSize(double sizeKb)
{
    if (sizeKb <= 0.0)
        return QString();
    const double mb = sizeKb / 1024.0;
    if (mb < 1024.0)
        return QStringLiteral("%1 MB").arg(mb, 0, 'f', 0);
    return QStringLiteral("%1 GB").arg(mb / 1024.0, 0, 'f', 1);
}

QString shortName(const QString &path)
{
    const int slash = qMax(path.lastIndexOf(QLatin1Char('/')), path.lastIndexOf(QLatin1Char('\\')));
    return slash >= 0 ? path.mid(slash + 1) : path;
}

} // namespace

ModelResolutionDialog::ModelResolutionDialog(const QJsonArray &offers,
                                             const QString &workflowName,
                                             QWidget *parent)
    : QDialog(parent)
    , workflowName_(workflowName)
{
    setWindowTitle(tr("Missing models"));
    setModal(true);
    setMinimumWidth(680);

    ThemeManager &theme = ThemeManager::instance();

    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(theme.spacing(ThemeManager::Spacing::Section),
                              theme.spacing(ThemeManager::Spacing::Section),
                              theme.spacing(ThemeManager::Spacing::Section),
                              theme.spacing(ThemeManager::Spacing::Section));
    outer->setSpacing(theme.spacing(ThemeManager::Spacing::Card));

    auto *heading = new QLabel(
        tr("%1 needs %n model(s) you don't have.", nullptr, offers.size()).arg(workflowName), this);
    heading->setObjectName(QStringLiteral("ModelResolutionHeading"));
    heading->setWordWrap(true);
    outer->addWidget(heading);

    auto *subheading = new QLabel(
        tr("Nothing is downloaded or swapped until you choose it here."), this);
    subheading->setObjectName(QStringLiteral("ModelResolutionSubheading"));
    subheading->setWordWrap(true);
    outer->addWidget(subheading);

    // One scroll region, never nested: the rows are the only thing that can overflow.
    auto *scroll = new QScrollArea(this);
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

    auto *rowsHost = new QWidget(scroll);
    auto *rowsLayout = new QVBoxLayout(rowsHost);
    rowsLayout->setContentsMargins(0, 0, 0, 0);
    rowsLayout->setSpacing(theme.spacing(ThemeManager::Spacing::Snug));

    for (const QJsonValue &value : offers)
    {
        if (value.isObject())
            buildRow(rowsLayout, value.toObject());
    }
    rowsLayout->addStretch(1);

    scroll->setWidget(rowsHost);
    outer->addWidget(scroll, 1);

    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
    buttons->button(QDialogButtonBox::Ok)->setText(tr("Apply"));
    connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    outer->addWidget(buttons);

    applyTheme();
}

void ModelResolutionDialog::buildRow(QVBoxLayout *layout, const QJsonObject &offer)
{
    ThemeManager &theme = ThemeManager::instance();

    Row row;
    row.wanted = offer.value(QStringLiteral("wanted")).toString();

    auto *card = new QFrame(this);
    card->setObjectName(QStringLiteral("ModelResolutionCard"));
    auto *cardLayout = new QVBoxLayout(card);
    cardLayout->setContentsMargins(theme.spacing(ThemeManager::Spacing::Card),
                                   theme.spacing(ThemeManager::Spacing::Card),
                                   theme.spacing(ThemeManager::Spacing::Card),
                                   theme.spacing(ThemeManager::Spacing::Card));
    cardLayout->setSpacing(theme.spacing(ThemeManager::Spacing::Tight));

    auto *wantedLabel = new QLabel(shortName(row.wanted), card);
    wantedLabel->setObjectName(QStringLiteral("ModelResolutionWanted"));
    wantedLabel->setToolTip(row.wanted);
    cardLayout->addWidget(wantedLabel);

    // Always show HOW the architecture was decided. A substitution the user cannot reason about is
    // one they cannot sanity-check, and the reason is the difference between an informed choice and
    // a shrug.
    const QString architecture = offer.value(QStringLiteral("architecture")).toString();
    const QString reason = offer.value(QStringLiteral("architecture_reason")).toString();
    if (!architecture.isEmpty() || !reason.isEmpty())
    {
        auto *why = new QLabel(architecture.isEmpty()
                                   ? reason
                                   : tr("%1 — %2").arg(architecture.toUpper(), reason),
                               card);
        why->setObjectName(QStringLiteral("ModelResolutionReason"));
        why->setWordWrap(true);
        cardLayout->addWidget(why);
    }

    auto *group = new QButtonGroup(card);

    // Option 1 -- an exact identification, when there is one.
    const QJsonObject download = offer.value(QStringLiteral("download")).toObject();
    if (!download.isEmpty())
    {
        row.downloadUrl = download.value(QStringLiteral("url")).toString();
        const QString size = humanSize(download.value(QStringLiteral("size_kb")).toDouble());
        QString text = tr("Download \"%1\"").arg(download.value(QStringLiteral("model_name")).toString());
        const QString version = download.value(QStringLiteral("version_name")).toString();
        if (!version.isEmpty())
            text += QStringLiteral(" · %1").arg(version);
        if (!size.isEmpty())
            text += QStringLiteral(" · %1").arg(size);

        row.downloadButton = new QRadioButton(text, card);
        // "identified", not "found": the match is on the exact filename, and saying so is what
        // distinguishes this from the name-similarity guess we deliberately do not offer.
        row.downloadButton->setToolTip(tr("Identified by exact filename match — %1").arg(row.downloadUrl));
        group->addButton(row.downloadButton);
        cardLayout->addWidget(row.downloadButton);
    }

    // Option 2 -- something already on disk that can serve the same architecture.
    const QJsonArray substitutes = offer.value(QStringLiteral("substitutes")).toArray();
    if (!substitutes.isEmpty())
    {
        row.substituteButton = new QRadioButton(tr("Use a model I already have"), card);
        group->addButton(row.substituteButton);
        cardLayout->addWidget(row.substituteButton);

        row.substituteCombo = new QComboBox(card);
        // Never let a long model path inflate the dialog width.
        row.substituteCombo->setMinimumContentsLength(10);
        row.substituteCombo->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
        for (const QJsonValue &value : substitutes)
        {
            const QJsonObject candidate = value.toObject();
            const QString name = candidate.value(QStringLiteral("name")).toString();
            QString label = shortName(name);
            if (candidate.value(QStringLiteral("lineage_match")).toBool())
                label += tr("  (same %1)").arg(candidate.value(QStringLiteral("lineage")).toString());
            row.substituteCombo->addItem(label, name);
            row.substituteCombo->setItemData(row.substituteCombo->count() - 1,
                                             candidate.value(QStringLiteral("reason")).toString(),
                                             Qt::ToolTipRole);
        }
        row.substituteCombo->setEnabled(false);
        connect(row.substituteButton, &QRadioButton::toggled,
                row.substituteCombo, &QComboBox::setEnabled);
        cardLayout->addWidget(row.substituteCombo);

        auto *count = new QLabel(tr("%n compatible model(s) on this machine", nullptr,
                                    substitutes.size()), card);
        count->setObjectName(QStringLiteral("ModelResolutionReason"));
        cardLayout->addWidget(count);
    }

    // Option 3 -- and the default. Doing nothing must be the thing that happens if the user just
    // presses Apply.
    row.skipButton = new QRadioButton(tr("Skip — leave this unresolved"), card);
    row.skipButton->setChecked(true);
    group->addButton(row.skipButton);
    cardLayout->addWidget(row.skipButton);

    if (download.isEmpty() && substitutes.isEmpty())
    {
        const QJsonArray notes = offer.value(QStringLiteral("notes")).toArray();
        const QString note = notes.isEmpty() ? tr("Nothing found for this model.")
                                             : notes.first().toString();
        auto *empty = new QLabel(note, card);
        empty->setObjectName(QStringLiteral("ModelResolutionReason"));
        empty->setWordWrap(true);
        cardLayout->addWidget(empty);
    }

    layout->addWidget(card);
    rows_.append(row);
}

ModelResolutionDialog::Choice ModelResolutionDialog::choiceFor(const Row &row) const
{
    if (row.downloadButton && row.downloadButton->isChecked())
        return Choice::Download;
    if (row.substituteButton && row.substituteButton->isChecked())
        return Choice::Substitute;
    return Choice::Skip;
}

QJsonObject ModelResolutionDialog::substitutions() const
{
    QJsonObject out;
    for (const Row &row : rows_)
    {
        if (choiceFor(row) != Choice::Substitute || !row.substituteCombo)
            continue;
        const QString chosen = row.substituteCombo->currentData().toString();
        if (!chosen.isEmpty())
            out.insert(row.wanted, chosen);
    }
    return out;
}

QStringList ModelResolutionDialog::downloads() const
{
    QStringList out;
    for (const Row &row : rows_)
    {
        if (choiceFor(row) == Choice::Download && !row.downloadUrl.isEmpty())
            out.append(row.downloadUrl);
    }
    return out;
}

bool ModelResolutionDialog::hasUnresolved() const
{
    for (const Row &row : rows_)
    {
        if (choiceFor(row) == Choice::Skip)
            return true;
    }
    return false;
}

void ModelResolutionDialog::applyTheme()
{
    ThemeManager &theme = ThemeManager::instance();

    // @token@ replace chain, not QString::arg: arg() resolves by the lowest remaining placeholder,
    // so adding a token to an arg-built sheet renumbers every later one.
    QString sheet = QStringLiteral(
        "QDialog { background: @s0@; }"
        "QLabel { color: @mid@; }"
        "QLabel#ModelResolutionHeading { color: @hi@; font-size: 15px; font-weight: 600; }"
        "QLabel#ModelResolutionSubheading { color: @lo@; }"
        "QLabel#ModelResolutionWanted { color: @hi@; font-weight: 600; }"
        "QLabel#ModelResolutionReason { color: @lo@; }"
        "QFrame#ModelResolutionCard { background: @s1@; border: 1px solid @border@; border-radius: 8px; }"
        "QRadioButton { color: @mid@; padding: 2px 0; }"
        "QRadioButton:hover { color: @hi@; }"
        "QRadioButton:focus { color: @hi@; }"
        "QRadioButton:disabled { color: @disabled@; }"
        "QComboBox { background: @s0@; color: @hi@; border: 1px solid @border@;"
        "  border-radius: 5px; padding: 4px 8px; }"
        "QComboBox:disabled { color: @disabled@; border-color: @subtle@; }"
        "QComboBox:focus { border-color: @accent@; }"
        "QPushButton { background: @s2@; color: @hi@; border: 1px solid @border@;"
        "  border-radius: 5px; padding: 6px 16px; }"
        "QPushButton:hover { border-color: @strong@; }"
        "QPushButton:pressed { background: @s1@; }"
        "QPushButton:focus { border-color: @accent@; }"
        "QPushButton:default { background: @accent@; border-color: @accent@; }"
        "QPushButton:default:hover { background: @accenthover@; }");

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
