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
    layout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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
        // Phase 5 correction batch: this page used a stale BLUE palette (blue eyebrows,
        // navy surfaces) that predated the token system + was off the ArcaneGlass identity.
        // Migrated to canonical Doc 16 tokens -- blue -> canonical violet/neutral, and now
        // it theme-switches. The tokens are per-preset so the old ivory ternary is gone.
        const auto &theme = ThemeManager::instance();
        using C = ThemeManager::Color;
        setStyleSheet(QStringLiteral(
            "#ModePage { background: transparent; }"
            "QFrame#ModeHeroCard {"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %1, stop:0.46 %2, stop:1 %3);"
            " border: 1px solid %4; border-radius: 22px; }"
            "QFrame#ModeGlowBand {"
            " min-height: 8px; max-height: 8px; border-radius: 4px;"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %5, stop:1 %6); border: none; }"
            "QLabel#ModeEyebrow { @micro@ letter-spacing: 0.12em; color: %7; }"
            "QLabel#ModeTitle { @display@ color: %8; }"
            "QLabel#ModeSubtitle { @body@ color: %9; }"
            "QLabel#ModeHeroNote { @body@ color: %9; background: %3;"
            " border: 1px solid %10; border-radius: 14px; padding: 10px 12px; }"
            "QFrame#ModeSectionCard {"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 %2, stop:1 %3);"
            " border: 1px solid %10; border-radius: 18px; }"
            "QLabel#ModeSectionCardEyebrow { @caption@ letter-spacing: 0.08em; color: %7; }"
            "QLabel#ModeSectionCardTitle { @heading@ color: %8; }"
            "QLabel#ModeSectionCardBody { @body@ color: %9; }")
            .arg(theme.css(C::Surface2))        // %1  hero bg (top)
            .arg(theme.css(C::Surface1))        // %2  hero bg (mid) / section bg (top)
            .arg(theme.css(C::Surface0))        // %3  hero bg (bottom) / note bg / section bg (bottom)
            .arg(theme.css(C::BorderStrong))    // %4  hero border
            .arg(theme.css(C::AccentHover))     // %5  glow band (start)
            .arg(theme.css(C::AccentSecondary)) // %6  glow band (end)
            .arg(theme.css(C::Accent))          // %7  eyebrows (was blue #8fb2ff/#7fa9ff)
            .arg(theme.css(C::TextHi))          // %8  titles
            .arg(theme.css(C::TextMid))         // %9  subtitle / body / note
            .arg(theme.css(C::Border))          // %10 note + section borders
            .replace(QLatin1String("@display@"), theme.fontCss(ThemeManager::Type::Display))
            .replace(QLatin1String("@heading@"), theme.fontCss(ThemeManager::Type::Heading))
            .replace(QLatin1String("@body@"), theme.fontCss(ThemeManager::Type::Body))
            .replace(QLatin1String("@caption@"), theme.fontCss(ThemeManager::Type::Caption))
            .replace(QLatin1String("@micro@"), theme.fontCss(ThemeManager::Type::Micro)));
    };

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    root->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    auto *hero = new QFrame(this);
    hero->setObjectName(QStringLiteral("ModeHeroCard"));
    auto *heroLayout = new QVBoxLayout(hero);
    heroLayout->setContentsMargins(20, 18, 20, 18);
    heroLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

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
