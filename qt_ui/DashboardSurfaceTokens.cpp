#include "DashboardSurfaceTokens.h"

#include "ThemeManager.h"

#include <QtGlobal>

namespace
{
qreal clamp01(qreal value)
{
    return qBound(0.0, value, 1.0);
}
}

QString dashboardRgba(const QColor &color, qreal alphaMultiplier)
{
    const int alpha = qBound(0, static_cast<int>(color.alphaF() * alphaMultiplier * 255.0), 255);
    return QStringLiteral("rgba(%1,%2,%3,%4)")
        .arg(color.red())
        .arg(color.green())
        .arg(color.blue())
        .arg(alpha);
}

QColor dashboardMix(const QColor &a, const QColor &b, qreal t)
{
    t = clamp01(t);
    return QColor(
        static_cast<int>(a.red() + (b.red() - a.red()) * t),
        static_cast<int>(a.green() + (b.green() - a.green()) * t),
        static_cast<int>(a.blue() + (b.blue() - a.blue()) * t),
        static_cast<int>(a.alpha() + (b.alpha() - a.alpha()) * t));
}

QColor dashboardWithAlpha(const QColor &color, qreal alpha)
{
    QColor copy = color;
    copy.setAlphaF(clamp01(alpha));
    return copy;
}

DashboardSurfaceTokens DashboardSurfaceTokens::fromTheme(const ThemeManager &theme)
{
    DashboardSurfaceTokens tokens;

    // Phase 3: derive from the canonical Doc 16 color() tokens (not the legacy accessors),
    // so the whole dashboard switches with themeChanged. Post-reconcile these tokens hold
    // the same ArcaneGlass values the legacy accessors did, so this is identity-preserving
    // on ArcaneGlass and re-colors on any other theme. NB: ThemeManager surface0()/surface1()
    // map to canonical Surface1/Surface2. `border` reproduces the old borderToneColor()
    // (mix of elevated surface + accent, scaled by effectsWeight) from canonical tokens.
    const qreal mix = clamp01(theme.effectsWeight() / 100.0);
    const QColor accent = theme.color(ThemeManager::Color::Accent);
    const QColor accent2 = theme.color(ThemeManager::Color::AccentSecondary);
    const QColor accent3 = theme.color(ThemeManager::Color::AccentTertiary);
    const QColor surface0 = theme.color(ThemeManager::Color::Surface1);
    const QColor surface1 = theme.color(ThemeManager::Color::Surface2);
    const QColor border = dashboardMix(surface1, accent, 0.18 + mix * 0.24);
    const QColor nearBlack(QStringLiteral("#03060d"));
    const QColor deepNavy(QStringLiteral("#071120"));

    tokens.effectMix = mix;
    tokens.heroGlow = 1.50 + mix * 0.16;
    tokens.secondaryGlow = 0.20 + mix * 0.02;
    tokens.utilityGlow = 0.15 + mix * 0.02;

    // pageTop is the HERO LIGHT SOURCE (the "violet eye-glow"): accent-lifted so the top of the page
    // gradient reads as a lit region instead of a flat dark field. Was a near-invisible accent2 tint
    // (~1%); now a real accent glow. Cross-theme safe -- on the light Ivory theme this is a light-violet
    // lift, on dark themes a deep-violet glow. The Home page radials this stop out to the dark edges.
    tokens.pageTop = dashboardMix(surface0, accent, 0.14 + mix * 0.06);
    tokens.pageMiddle = dashboardMix(surface1, deepNavy, 0.56 + mix * 0.06);
    tokens.pageBottom = dashboardMix(surface1, nearBlack, 0.84 - mix * 0.02);
    tokens.heroBackdrop = dashboardWithAlpha(dashboardMix(surface0, accent, 0.056 + mix * 0.026), 0.17 + mix * 0.038);

    // GLASS TRANSMISSIVITY (depth pass): the panels were ~0.90-0.99 opaque -- they occluded the
    // background, so the glass read flat. Drop the fill alpha so the (now accent-glowing) backdrop shows
    // through, with a tier ladder raised > base > inset > utility (more transparent = more recessed = a
    // real elevation cue). DARK THEMES ONLY: on the light Ivory theme the panels are light and float over
    // a dark backdrop, so thinning them would muddy the panel AND drop dark-on-light text below AA at the
    // dark page edges (verified) -- Ivory keeps its near-opaque panels.
    const qreal surfaceLuma = 0.2126 * surface0.red() + 0.7152 * surface0.green() + 0.0722 * surface0.blue();
    const bool darkUi = surfaceLuma < 128.0;
    const qreal aRaisedA = darkUi ? 0.90 : 0.986, aRaisedB = darkUi ? 0.88 : 0.982;
    const qreal aBaseA   = darkUi ? 0.82 : 0.972, aBaseB   = darkUi ? 0.80 : 0.968;
    const qreal aInsetA  = darkUi ? 0.76 : 0.925, aInsetB  = darkUi ? 0.74 : 0.915;
    const qreal aUtilA   = darkUi ? 0.74 : 0.900, aUtilB   = darkUi ? 0.72 : 0.892;

    tokens.panelBaseA = dashboardWithAlpha(dashboardMix(surface0, accent, 0.018 + mix * 0.014), aBaseA);
    tokens.panelBaseB = dashboardWithAlpha(dashboardMix(surface1, nearBlack, 0.50), aBaseB);

    tokens.panelRaisedA = dashboardWithAlpha(dashboardMix(surface0, accent2, 0.040 + mix * 0.022), aRaisedA);
    tokens.panelRaisedB = dashboardWithAlpha(dashboardMix(surface1, deepNavy, 0.40 + mix * 0.05), aRaisedB);

    tokens.panelInsetA = dashboardWithAlpha(dashboardMix(surface1, accent3, 0.026 + mix * 0.018), aInsetA);
    tokens.panelInsetB = dashboardWithAlpha(dashboardMix(surface0, nearBlack, 0.42), aInsetB);

    tokens.utilityA = dashboardWithAlpha(dashboardMix(surface0, accent3, 0.012 + mix * 0.010), aUtilA);
    tokens.utilityB = dashboardWithAlpha(dashboardMix(surface1, nearBlack, 0.56), aUtilB);

    tokens.borderSoft = dashboardWithAlpha(dashboardMix(border, accent, 0.050 + mix * 0.016), 0.030 + mix * 0.012);
    tokens.borderStrong = dashboardWithAlpha(dashboardMix(border, accent2, 0.085 + mix * 0.022), 0.066 + mix * 0.022);
    tokens.borderHero = dashboardWithAlpha(dashboardMix(border, accent2, 0.15 + mix * 0.045), 0.10 + mix * 0.040);

    const QColor textHi = theme.color(ThemeManager::Color::TextHi);
    tokens.innerHighlight = dashboardWithAlpha(dashboardMix(textHi, accent3, 0.05), 0.016 + mix * 0.015);
    tokens.innerHero = dashboardWithAlpha(dashboardMix(textHi, accent2, 0.07), 0.026 + mix * 0.018);

    tokens.glowPrimary = dashboardWithAlpha(accent, 0.075 + mix * 0.085);
    tokens.glowSecondary = dashboardWithAlpha(accent2, 0.052 + mix * 0.068);
    tokens.glowTertiary = dashboardWithAlpha(accent3, 0.040 + mix * 0.050);

    tokens.textPrimary = theme.color(ThemeManager::Color::TextHi);
    tokens.textSecondary = theme.color(ThemeManager::Color::TextMid);
    tokens.textMuted = theme.color(ThemeManager::Color::TextLo);

    // Success/ready is a SEMANTIC role -> read from the semantic token (cyan in
    // ArcaneGlass), not the decorative tertiary accent (now violet).
    const QColor success = theme.color(ThemeManager::Color::Success);
    tokens.successFill = dashboardWithAlpha(success, 0.07 + mix * 0.05);
    tokens.successBorder = dashboardWithAlpha(dashboardMix(success, accent, 0.24), 0.15 + mix * 0.06);

    tokens.radiusHero = 26;
    tokens.radiusPanel = 20;
    tokens.radiusInset = 16;
    tokens.radiusChip = 13;
    tokens.strokeWidth = 1;

    return tokens;
}
