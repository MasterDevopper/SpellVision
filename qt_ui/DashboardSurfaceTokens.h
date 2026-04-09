#pragma once

#include <QColor>
#include <QString>

class ThemeManager;

struct DashboardSurfaceTokens
{
    QColor pageTop;
    QColor pageMiddle;
    QColor pageBottom;
    QColor heroBackdrop;

    QColor panelBaseA;
    QColor panelBaseB;
    QColor panelRaisedA;
    QColor panelRaisedB;
    QColor panelInsetA;
    QColor panelInsetB;
    QColor utilityA;
    QColor utilityB;

    QColor borderSoft;
    QColor borderStrong;
    QColor borderHero;
    QColor innerHighlight;
    QColor innerHero;
    QColor glowPrimary;
    QColor glowSecondary;
    QColor glowTertiary;

    QColor textPrimary;
    QColor textSecondary;
    QColor textMuted;
    QColor successFill;
    QColor successBorder;

    int radiusHero = 26;
    int radiusPanel = 20;
    int radiusInset = 16;
    int radiusChip = 13;
    int strokeWidth = 1;
    qreal effectMix = 0.68;
    qreal heroGlow = 1.50;
    qreal secondaryGlow = 0.20;
    qreal utilityGlow = 0.15;

    static DashboardSurfaceTokens fromTheme(const ThemeManager &theme);
};

QString dashboardRgba(const QColor &color, qreal alphaMultiplier = 1.0);
QColor dashboardMix(const QColor &a, const QColor &b, qreal t);
QColor dashboardWithAlpha(const QColor &color, qreal alpha);
