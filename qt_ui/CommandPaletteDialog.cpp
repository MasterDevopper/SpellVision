#include "CommandPaletteDialog.h"
#include "ThemeManager.h"

#include <QFontMetrics>
#include <QKeyEvent>
#include <QLineEdit>
#include <QListWidget>
#include <QListWidgetItem>
#include <QPainter>
#include <QShowEvent>
#include <QSignalBlocker>
#include <QStyledItemDelegate>
#include <QVBoxLayout>

#include <algorithm>

namespace
{
// Per-item roles carried on the QListWidgetItem.
constexpr int CmdIndexRole = Qt::UserRole;     // index into commands_; -1 = category header
constexpr int RightTextRole = Qt::UserRole + 1; // dim right-aligned detail (shortcut / "type · family")

// Scale a font by `factor`, robust to either sizing mode: a font set via pixel size reports
// pointSizeF() == -1, so multiplying that would yield a negative point size (Qt warns + ignores it).
QFont scaledFont(const QFont &base, double factor)
{
    QFont f = base;
    const double pt = base.pointSizeF();
    if (pt > 0.0)
    {
        f.setPointSizeF(pt * factor);
    }
    else
    {
        const int px = base.pixelSize();
        if (px > 0)
            f.setPixelSize(qMax(1, qRound(px * factor)));
    }
    return f;
}

// Two-tone row painter: category headers as dim uppercase labels; command rows as a bright title on
// the left with a dim detail on the right, and a soft accent fill + bar on the selected row. Reads
// ThemeManager tokens at paint time so a live theme switch recolors it for free.
class PaletteItemDelegate : public QStyledItemDelegate
{
public:
    using QStyledItemDelegate::QStyledItemDelegate;

    QSize sizeHint(const QStyleOptionViewItem &opt, const QModelIndex &idx) const override
    {
        const int cmdIndex = idx.data(CmdIndexRole).toInt();
        return QSize(opt.rect.width(), cmdIndex < 0 ? 30 : 44);
    }

    void paint(QPainter *p, const QStyleOptionViewItem &opt, const QModelIndex &idx) const override
    {
        const ThemeManager &tm = ThemeManager::instance();
        using C = ThemeManager::Color;
        const QRect r = opt.rect;
        const int cmdIndex = idx.data(CmdIndexRole).toInt();

        p->save();
        p->setRenderHint(QPainter::Antialiasing, true);

        if (cmdIndex < 0)
        {
            // Category header.
            QFont f = scaledFont(opt.font, 0.82);
            f.setBold(true);
            f.setCapitalization(QFont::AllUppercase);
            f.setLetterSpacing(QFont::PercentageSpacing, 110);
            p->setFont(f);
            p->setPen(tm.color(C::TextLo));
            p->drawText(r.adjusted(16, 6, -12, -3), Qt::AlignLeft | Qt::AlignBottom,
                        idx.data(Qt::DisplayRole).toString());
            p->restore();
            return;
        }

        const bool selected = opt.state.testFlag(QStyle::State_Selected);
        if (selected)
        {
            const QRect fill = r.adjusted(6, 3, -6, -3);
            p->setPen(Qt::NoPen);
            p->setBrush(tm.color(C::AccentGlow));
            p->drawRoundedRect(fill, 7, 7);
            p->setBrush(tm.color(C::Accent));
            p->drawRoundedRect(QRect(fill.left() + 1, fill.top() + 5, 3, fill.height() - 10), 2, 2);
        }

        const QString title = idx.data(Qt::DisplayRole).toString();
        const QString right = idx.data(RightTextRole).toString();

        const QFont rf = scaledFont(opt.font, 0.9);
        const QFontMetrics rfm(rf);
        const int rightW = right.isEmpty() ? 0 : rfm.horizontalAdvance(right) + 28;

        const QFont tf = scaledFont(opt.font, 1.03);
        const QFontMetrics tfm(tf);
        p->setFont(tf);
        p->setPen(tm.color(C::TextHi));
        const QRect titleRect = r.adjusted(20, 0, -(rightW + 12), 0);
        p->drawText(titleRect, Qt::AlignLeft | Qt::AlignVCenter,
                    tfm.elidedText(title, Qt::ElideRight, titleRect.width()));

        if (!right.isEmpty())
        {
            p->setFont(rf);
            p->setPen(tm.color(C::TextLo));
            p->drawText(r.adjusted(0, 0, -18, 0), Qt::AlignRight | Qt::AlignVCenter, right);
        }
        p->restore();
    }
};
} // namespace

CommandPaletteDialog::CommandPaletteDialog(QWidget *parent)
    : QDialog(parent)
{
    setWindowFlags(Qt::FramelessWindowHint | Qt::Dialog);
    setModal(true);

    setMinimumWidth(820);
    setMaximumWidth(1180);
    resize(940, 460);

    setObjectName(QStringLiteral("CommandPaletteDialog"));
    applyThemeStyling();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &CommandPaletteDialog::applyThemeStyling);

    auto *layout = new QVBoxLayout(this);
    const int pad = ThemeManager::instance().spacing(ThemeManager::Spacing::Card);
    layout->setContentsMargins(pad, pad, pad, pad);
    layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    searchBox_ = new QLineEdit(this);
    searchBox_->setPlaceholderText(QStringLiteral("Search commands, models…"));
    searchBox_->setClearButtonEnabled(true);

    resultsList_ = new QListWidget(this);
    resultsList_->setMinimumHeight(320);
    resultsList_->setUniformItemSizes(false);
    resultsList_->setSpacing(0);
    resultsList_->setSelectionMode(QAbstractItemView::SingleSelection);
    resultsList_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    resultsList_->setItemDelegate(new PaletteItemDelegate(resultsList_));
    resultsList_->setFocusPolicy(Qt::NoFocus); // keep typing focus on the search box

    layout->addWidget(searchBox_);
    layout->addWidget(resultsList_, 1);

    connect(searchBox_, &QLineEdit::textChanged, this, &CommandPaletteDialog::filterCommands);
    connect(searchBox_, &QLineEdit::returnPressed, this, &CommandPaletteDialog::activateCurrent);
    connect(resultsList_, &QListWidget::itemClicked, this, &CommandPaletteDialog::activateItem);
    connect(resultsList_, &QListWidget::itemActivated, this, &CommandPaletteDialog::activateItem);

    searchBox_->setFocus();
}

void CommandPaletteDialog::applyThemeStyling()
{
    const auto &theme = ThemeManager::instance();
    using C = ThemeManager::Color;
    // The result rows are painted by PaletteItemDelegate, so item backgrounds stay transparent here
    // (the delegate owns the selected-row fill); the stylesheet only frames the dialog, the input, and
    // the list viewport.
    setStyleSheet(QStringLiteral(
                      "#CommandPaletteDialog { background: %1; border: 1px solid %2; border-radius: 12px; }"
                      "QLineEdit { font-size: 13px; min-height: 38px; background: %3; color: %4;"
                      " border: 1px solid %2; border-radius: 9px; padding: 7px 12px; }"
                      "QListWidget { font-size: 12px; background: %5; color: %4; border: 1px solid %6;"
                      " border-radius: 9px; outline: none; padding: 4px; }"
                      "QListWidget::item { background: transparent; border: none; }"
                      "QListWidget::item:selected { background: transparent; }")
                      .arg(theme.css(C::Surface3))     // %1 dialog bg
                      .arg(theme.css(C::BorderStrong)) // %2 dialog + input border
                      .arg(theme.css(C::Surface0))     // %3 input bg
                      .arg(theme.css(C::TextHi))       // %4 text
                      .arg(theme.css(C::Surface1))     // %5 list bg
                      .arg(theme.css(C::Border)));     // %6 list border
}

void CommandPaletteDialog::setCommands(const QVector<Command> &commands, const QString &placeholder)
{
    commands_ = commands;
    backHandler_ = nullptr; // a submode caller re-arms this via setBackHandler() after setCommands()
    if (!placeholder.isEmpty())
        searchBox_->setPlaceholderText(placeholder);
    {
        const QSignalBlocker block(searchBox_);
        searchBox_->clear();
    }
    updateResults(QString());
    searchBox_->setFocus();
}

void CommandPaletteDialog::setBackHandler(std::function<void()> onBack)
{
    backHandler_ = std::move(onBack);
}

void CommandPaletteDialog::filterCommands(const QString &text)
{
    updateResults(text);
}

int CommandPaletteDialog::fuzzyScore(const QString &query, const QString &text)
{
    if (query.isEmpty())
        return 0;
    const QString q = query.toLower();
    const QString t = text.toLower();

    int qi = 0;
    int score = 0;
    int run = 0;
    bool prevSep = true; // start of string is a word boundary
    for (int ti = 0; ti < t.size() && qi < q.size(); ++ti)
    {
        const QChar c = t.at(ti);
        const bool isSep = (c == QLatin1Char(' ') || c == QLatin1Char('-') || c == QLatin1Char('_') ||
                            c == QLatin1Char('.') || c == QLatin1Char('/') || c == QLatin1Char(':'));
        if (c == q.at(qi))
        {
            int bonus = 1;
            if (prevSep)
                bonus += 4; // matched at the start of a word
            run += 1;
            bonus += run; // reward consecutive runs
            score += bonus;
            ++qi;
        }
        else
        {
            run = 0;
        }
        prevSep = isSep;
    }
    if (qi < q.size())
        return -1; // not every query char matched, in order
    if (t.startsWith(q))
        score += 6; // prefix match
    score += qMax(0, 10 - (t.size() - q.size()) / 4); // tighter match => higher
    return score;
}

void CommandPaletteDialog::updateResults(const QString &query)
{
    resultsList_->clear();

    const QString q = query.trimmed();
    const bool searching = !q.isEmpty();

    auto addCommandRow = [this, searching](int cmdIndex) {
        const Command &c = commands_.at(cmdIndex);
        QString right;
        if (!c.subtitle.isEmpty())
            right = c.subtitle; // model rows: "LoRA · sdxl"
        else if (!c.shortcut.isEmpty())
            right = c.shortcut; // commands with a keycap hint
        else if (searching && !c.category.isEmpty())
            right = c.category; // flat search keeps the group context visible
        auto *item = new QListWidgetItem(c.title, resultsList_);
        item->setData(CmdIndexRole, cmdIndex);
        item->setData(RightTextRole, right);
        item->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
    };

    if (searching)
    {
        struct Row
        {
            int index;
            int score;
        };
        QVector<Row> rows;
        for (int i = 0; i < commands_.size(); ++i)
        {
            const Command &c = commands_.at(i);
            int s = fuzzyScore(q, c.title);
            s = qMax(s, fuzzyScore(q, c.subtitle));
            s = qMax(s, fuzzyScore(q, c.category));
            s = qMax(s, fuzzyScore(q, c.keywords)); // aliases: "t2v" -> Text to Video, etc.
            if (s >= 0)
                rows.push_back({i, s});
        }
        std::stable_sort(rows.begin(), rows.end(), [](const Row &a, const Row &b) { return a.score > b.score; });
        for (const Row &row : rows)
            addCommandRow(row.index);
    }
    else
    {
        // Grouped: emit a header each time the category changes (MainWindow builds commands contiguous
        // per category, so headers stay unique and in first-appearance order).
        QString lastCat;
        for (int i = 0; i < commands_.size(); ++i)
        {
            const Command &c = commands_.at(i);
            if (!c.category.isEmpty() && c.category != lastCat)
            {
                auto *header = new QListWidgetItem(c.category, resultsList_);
                header->setData(CmdIndexRole, -1);
                header->setFlags(Qt::NoItemFlags); // not selectable; keyboard nav skips it
                lastCat = c.category;
            }
            addCommandRow(i);
        }
    }

    if (resultsList_->count() == 0)
    {
        auto *empty = new QListWidgetItem(QStringLiteral("No matching commands"), resultsList_);
        empty->setData(CmdIndexRole, -1);
        empty->setFlags(Qt::NoItemFlags);
        return;
    }

    // Select the first selectable row.
    for (int i = 0; i < resultsList_->count(); ++i)
    {
        QListWidgetItem *it = resultsList_->item(i);
        if (it && it->flags().testFlag(Qt::ItemIsSelectable))
        {
            resultsList_->setCurrentRow(i);
            break;
        }
    }
}

void CommandPaletteDialog::keyPressEvent(QKeyEvent *event)
{
    const auto moveSelection = [this](int delta) {
        const int n = resultsList_->count();
        if (n == 0)
            return;
        int row = resultsList_->currentRow();
        if (row < 0)
            row = (delta > 0) ? -1 : n;
        for (int i = row + delta; i >= 0 && i < n; i += delta)
        {
            QListWidgetItem *it = resultsList_->item(i);
            if (it && it->flags().testFlag(Qt::ItemIsSelectable))
            {
                resultsList_->setCurrentRow(i);
                resultsList_->scrollToItem(it);
                return;
            }
        }
    };

    switch (event->key())
    {
    case Qt::Key_Up:
        moveSelection(-1);
        return;
    case Qt::Key_Down:
        moveSelection(1);
        return;
    case Qt::Key_Escape:
        if (backHandler_)
        {
            // Copy before invoking: the handler calls setCommands(), which reassigns backHandler_.
            const auto back = backHandler_;
            back();
            return;
        }
        reject();
        return;
    default:
        break;
    }
    QDialog::keyPressEvent(event);
}

void CommandPaletteDialog::showEvent(QShowEvent *event)
{
    QDialog::showEvent(event);
    searchBox_->setFocus();
    searchBox_->selectAll();
}

void CommandPaletteDialog::activateCurrent()
{
    activateItem(resultsList_ ? resultsList_->currentItem() : nullptr);
}

void CommandPaletteDialog::activateItem(QListWidgetItem *item)
{
    if (!item)
        return;
    const int index = item->data(CmdIndexRole).toInt();
    if (index < 0 || index >= commands_.size())
        return; // header / placeholder

    // Copy the command before running it: a keepOpen action calls setCommands(), which reassigns
    // commands_ and would invalidate a reference into it.
    const Command cmd = commands_.at(index);
    if (cmd.action)
        cmd.action();
    if (!cmd.keepOpen)
        accept();
}
