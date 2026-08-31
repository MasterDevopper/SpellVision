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
    layout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                               ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                               ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                               ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
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
} // namespace

ModePage::ModePage(const QString &title,
                   const QString &subtitle,
                   const QStringList &sectionBullets,
                   QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("ModePage"));

    auto applyTheme = [this]() {
        // @token@ replace — %10 via chained QString::arg corrupts disabled/border styles.
        // Density matches cockpit cards (~14px), not marketing 22px pills.
        const auto &theme = ThemeManager::instance();
        using C = ThemeManager::Color;
        setStyleSheet(QStringLiteral(
            "#ModePage { background: transparent; }"
            "QFrame#ModeHeroCard {"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 @s2@, stop:0.46 @s1@, stop:1 @s0@);"
            " border: 1px solid @bds@; border-radius: 14px; }"
            "QFrame#ModeGlowBand {"
            " min-height: 6px; max-height: 6px; border-radius: 3px;"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @accH@, stop:1 @acc2@); border: none; }"
            "QLabel#ModeEyebrow { @micro@ letter-spacing: 0.12em; color: @acc@; }"
            "QLabel#ModeTitle { @display@ color: @hi@; }"
            "QLabel#ModeSubtitle { @body@ color: @mid@; }"
            "QLabel#ModeHeroNote { @body@ color: @mid@; background: @s0@;"
            " border: 1px solid @bd@; border-radius: 10px; padding: 10px 12px; }"
            "QFrame#ModeSectionCard {"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 @s1@, stop:1 @s0@);"
            " border: 1px solid @bd@; border-radius: 14px; }"
            "QLabel#ModeSectionCardEyebrow { @caption@ letter-spacing: 0.08em; color: @acc@; }"
            "QLabel#ModeSectionCardTitle { @heading@ color: @hi@; }"
            "QLabel#ModeSectionCardBody { @body@ color: @mid@; }")
            .replace(QLatin1String("@s0@"), theme.css(C::Surface0))
            .replace(QLatin1String("@s1@"), theme.css(C::Surface1))
            .replace(QLatin1String("@s2@"), theme.css(C::Surface2))
            .replace(QLatin1String("@hi@"), theme.css(C::TextHi))
            .replace(QLatin1String("@mid@"), theme.css(C::TextMid))
            .replace(QLatin1String("@acc@"), theme.css(C::Accent))
            .replace(QLatin1String("@acc2@"), theme.css(C::AccentSecondary))
            .replace(QLatin1String("@accH@"), theme.css(C::AccentHover))
            .replace(QLatin1String("@bd@"), theme.css(C::Border))
            .replace(QLatin1String("@bds@"), theme.css(C::BorderStrong))
            .replace(QLatin1String("@display@"), theme.fontCss(ThemeManager::Type::Display))
            .replace(QLatin1String("@heading@"), theme.fontCss(ThemeManager::Type::Heading))
            .replace(QLatin1String("@body@"), theme.fontCss(ThemeManager::Type::Body))
            .replace(QLatin1String("@caption@"), theme.fontCss(ThemeManager::Type::Caption))
            .replace(QLatin1String("@micro@"), theme.fontCss(ThemeManager::Type::Micro)));
    };

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Card),
                             ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    root->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    auto *hero = new QFrame(this);
    hero->setObjectName(QStringLiteral("ModeHeroCard"));
    auto *heroLayout = new QVBoxLayout(hero);
    heroLayout->setContentsMargins(18, 16, 18, 16);
    heroLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

    auto *glowBand = new QFrame(hero);
    glowBand->setObjectName(QStringLiteral("ModeGlowBand"));

    auto *eyebrow = new QLabel(QStringLiteral("Coming soon"), hero);
    eyebrow->setObjectName(QStringLiteral("ModeEyebrow"));

    auto *titleLabel = new QLabel(title, hero);
    titleLabel->setObjectName(QStringLiteral("ModeTitle"));
    titleLabel->setWordWrap(true);

    auto *subtitleLabel = new QLabel(subtitle, hero);
    subtitleLabel->setObjectName(QStringLiteral("ModeSubtitle"));
    subtitleLabel->setWordWrap(true);

    auto *noteLabel = new QLabel(
        QStringLiteral("This surface is intentionally staged — not disabled chrome. "
                       "When it ships, controls land here in place. Use Create modes and Flows for live work."),
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
    grid->setHorizontalSpacing(12);
    grid->setVerticalSpacing(12);

    for (int i = 0; i < sectionBullets.size(); ++i) {
        auto *card = sectionCard(
            QStringLiteral("Planned"),
            QStringLiteral("%1 · area %2").arg(title).arg(i + 1),
            sectionBullets.at(i));
        grid->addWidget(card, i / 2, i % 2);
    }

    root->addLayout(grid, 1);

    applyTheme();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, applyTheme);
}
