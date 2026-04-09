#include "ModePage.h"

#include "ThemeManager.h"

#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QVBoxLayout>

namespace
{
QFrame *sectionCard(const QString &eyebrowText,
                    const QString &titleText,
                    const QString &bodyText)
{
    auto *card = new QFrame;
    card->setObjectName(QStringLiteral("ModeSectionCard"));

    auto *layout = new QVBoxLayout(card);
    layout->setContentsMargins(16, 14, 16, 14);
    layout->setSpacing(6);

    auto *eyebrow = new QLabel(eyebrowText, card);
    eyebrow->setObjectName(QStringLiteral("ModeSectionCardEyebrow"));

    auto *title = new QLabel(titleText, card);
    title->setObjectName(QStringLiteral("ModeSectionCardTitle"));

    auto *body = new QLabel(bodyText, card);
    body->setObjectName(QStringLiteral("ModeSectionCardBody"));
    body->setWordWrap(true);

    layout->addWidget(eyebrow);
    layout->addWidget(title);
    layout->addWidget(body);
    layout->addStretch(1);
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
        const bool ivory = theme.preset() == ThemeManager::Preset::IvoryHolograph;

        setStyleSheet(QStringLiteral(
            "#ModePage { background: transparent; }"
            "QFrame#ModeHeroCard {"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(28, 38, 68, 0.98), stop:0.46 rgba(16, 23, 40, 0.96), stop:1 rgba(8, 12, 22, 0.99));"
            " border: 1px solid rgba(156, 174, 224, 0.28);"
            " border-radius: 22px;"
            "}"
            "QFrame#ModeGlowBand {"
            " min-height: 8px; max-height: 8px; border-radius: 4px;"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(166,124,255,0.86), stop:0.52 rgba(92,154,255,0.54), stop:1 rgba(255,255,255,0.10));"
            " border: none;"
            "}"
            "QLabel#ModeEyebrow { font-size: 11px; font-weight: 800; letter-spacing: 0.12em; color: #8fb2ff; }"
            "QLabel#ModeTitle { font-size: 30px; font-weight: 850; color: %1; }"
            "QLabel#ModeSubtitle { font-size: 13px; color: %2; }"
            "QLabel#ModeHeroNote {"
            " font-size: 11px; color: %2;"
            " background: rgba(10, 15, 26, 0.58);"
            " border: 1px solid rgba(152, 170, 212, 0.22);"
            " border-radius: 14px;"
            " padding: 10px 12px;"
            "}"
            "QFrame#ModeSectionCard {"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(18, 25, 39, 0.95), stop:1 rgba(10, 15, 26, 0.98));"
            " border: 1px solid rgba(126, 146, 190, 0.22);"
            " border-radius: 18px;"
            "}"
            "QLabel#ModeSectionCardEyebrow { font-size: 10px; font-weight: 800; letter-spacing: 0.08em; color: #7fa9ff; }"
            "QLabel#ModeSectionCardTitle { font-size: 18px; font-weight: 800; color: %1; }"
            "QLabel#ModeSectionCardBody { font-size: 13px; color: %2; }")
            .arg(ivory ? QStringLiteral("#132033") : QStringLiteral("#f5f8ff"),
                 ivory ? QStringLiteral("#5d7087") : QStringLiteral("#9fb4d2")));
    };

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(16, 10, 16, 16);
    root->setSpacing(12);

    auto *hero = new QFrame(this);
    hero->setObjectName(QStringLiteral("ModeHeroCard"));
    auto *heroLayout = new QVBoxLayout(hero);
    heroLayout->setContentsMargins(20, 18, 20, 18);
    heroLayout->setSpacing(8);

    auto *glowBand = new QFrame(hero);
    glowBand->setObjectName(QStringLiteral("ModeGlowBand"));

    auto *eyebrow = new QLabel(QStringLiteral("Workspace"), hero);
    eyebrow->setObjectName(QStringLiteral("ModeEyebrow"));

    auto *titleLabel = new QLabel(title, hero);
    titleLabel->setObjectName(QStringLiteral("ModeTitle"));
    titleLabel->setWordWrap(true);

    auto *subtitleLabel = new QLabel(subtitle, hero);
    subtitleLabel->setObjectName(QStringLiteral("ModeSubtitle"));
    subtitleLabel->setWordWrap(true);

    auto *noteLabel = new QLabel(
        QStringLiteral("This shell is staged for the premium SpellVision workstation. The structure below keeps room for production controls, review surfaces, and manager hooks without wasting vertical space."),
        hero);
    noteLabel->setObjectName(QStringLiteral("ModeHeroNote"));
    noteLabel->setWordWrap(true);

    heroLayout->addWidget(glowBand);
    heroLayout->addWidget(eyebrow);
    heroLayout->addWidget(titleLabel);
    heroLayout->addWidget(subtitleLabel);
    heroLayout->addWidget(noteLabel);
    root->addWidget(hero);

    auto *grid = new QGridLayout;
    grid->setHorizontalSpacing(14);
    grid->setVerticalSpacing(14);

    for (int i = 0; i < sectionBullets.size(); ++i)
    {
        auto *card = sectionCard(
            QStringLiteral("Planned Section %1").arg(i + 1),
            QStringLiteral("%1 Block").arg(title),
            sectionBullets.at(i));
        grid->addWidget(card, i / 2, i % 2);
    }

    root->addLayout(grid, 1);

    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, applyTheme);
}
