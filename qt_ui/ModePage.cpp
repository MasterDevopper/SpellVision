#include "ModePage.h"

#include "ThemeManager.h"

#include <QFrame>
#include <QGridLayout>
#include <QLabel>
#include <QVBoxLayout>

namespace
{
QFrame *sectionCard(const QString &titleText, const QString &bodyText)
{
    auto *card = new QFrame;
    card->setObjectName(QStringLiteral("ModeSectionCard"));

    auto *layout = new QVBoxLayout(card);
    layout->setContentsMargins(16, 14, 16, 14);
    layout->setSpacing(6);

    auto *title = new QLabel(titleText, card);
    title->setObjectName(QStringLiteral("ModeSectionCardTitle"));
    auto *body = new QLabel(bodyText, card);
    body->setObjectName(QStringLiteral("ModeSectionCardBody"));
    body->setWordWrap(true);

    layout->addWidget(title);
    layout->addWidget(body);
    return card;
}
}

ModePage::ModePage(const QString &title,
                   const QString &subtitle,
                   const QStringList &sectionBullets,
                   QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("ModePage"));

    auto applyTheme = [this]() {
        const auto &theme = ThemeManager::instance();
        setStyleSheet(QStringLiteral(
            "#ModePage { background: transparent; }"
            "QLabel#ModeTitle { font-size: 28px; font-weight: 800; color: %1; }"
            "QLabel#ModeSubtitle { font-size: 13px; color: %2; }"
            "QFrame#ModeSectionCard { background: rgba(18, 25, 39, 0.95); border: 1px solid rgba(120, 138, 172, 0.24); border-radius: 18px; }"
            "QLabel#ModeSectionCardTitle { font-size: 18px; font-weight: 800; color: %1; }"
            "QLabel#ModeSectionCardBody { font-size: 13px; color: %2; }")
            .arg(theme.preset() == ThemeManager::Preset::IvoryHolograph ? QStringLiteral("#132033") : QStringLiteral("#f5f8ff"),
                 theme.preset() == ThemeManager::Preset::IvoryHolograph ? QStringLiteral("#5d7087") : QStringLiteral("#9fb4d2")));
    };

    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, applyTheme);

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(16, 10, 16, 16);
    root->setSpacing(10);

    auto *hero = sectionCard(QStringLiteral("Shell Placeholder"),
                             QStringLiteral("This page is part of the persistent multi-mode workspace. Production controls will replace these placeholders in a later pass."));
    root->addWidget(hero);

    auto *grid = new QGridLayout;
    grid->setHorizontalSpacing(14);
    grid->setVerticalSpacing(14);

    for (int i = 0; i < sectionBullets.size(); ++i)
    {
        auto *card = sectionCard(QStringLiteral("Planned Section %1").arg(i + 1), sectionBullets.at(i));
        grid->addWidget(card, i / 2, i % 2);
    }

    root->addLayout(grid, 1);
}
