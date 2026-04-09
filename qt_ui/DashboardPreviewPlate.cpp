#include "DashboardPreviewPlate.h"

#include "DashboardSurfaceTokens.h"
#include "ThemeManager.h"

#include <QLinearGradient>
#include <QPaintEvent>
#include <QPainter>
#include <QPainterPath>
#include <QRadialGradient>

namespace
{
QPainterPath wavePath(const QRectF &rect, qreal phase, qreal amplitudeFactor)
{
    const qreal baseY = rect.center().y() + rect.height() * 0.08;
    const qreal amplitude = rect.height() * amplitudeFactor;
    const qreal w = rect.width();

    QPainterPath path;
    path.moveTo(rect.left(), baseY);
    path.cubicTo(rect.left() + w * 0.14, baseY - amplitude,
                 rect.left() + w * 0.22, baseY + amplitude * 0.55,
                 rect.left() + w * 0.36, baseY - amplitude * 0.35 + phase * 4.0);
    path.cubicTo(rect.left() + w * 0.50, baseY + amplitude * 0.92,
                 rect.left() + w * 0.58, baseY - amplitude * 0.78,
                 rect.left() + w * 0.72, baseY + amplitude * 0.18 - phase * 3.0);
    path.cubicTo(rect.left() + w * 0.82, baseY + amplitude * 0.42,
                 rect.right() - w * 0.12, baseY - amplitude * 0.18,
                 rect.right(), baseY + amplitude * 0.15);
    return path;
}

void drawBandBase(QPainter &painter,
                  const QPainterPath &panelPath,
                  const QRectF &rectF,
                  const QColor &a,
                  const QColor &b,
                  const DashboardSurfaceTokens &tokens)
{
    QLinearGradient fill(rectF.topLeft(), rectF.bottomRight());
    fill.setColorAt(0.0, a);
    fill.setColorAt(1.0, b);
    painter.fillPath(panelPath, fill);

    QRadialGradient haze(rectF.center().x(), rectF.center().y() - rectF.height() * 0.14,
                         rectF.width() * 0.62);
    haze.setColorAt(0.0, dashboardWithAlpha(tokens.glowPrimary, 0.016 + tokens.effectMix * 0.016));
    haze.setColorAt(0.50, dashboardWithAlpha(tokens.glowSecondary, 0.006 + tokens.effectMix * 0.007));
    haze.setColorAt(1.0, Qt::transparent);
    painter.fillPath(panelPath, haze);
}
}

DashboardPreviewPlate::DashboardPreviewPlate(QWidget *parent)
    : QWidget(parent)
{
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    setMinimumHeight(52);
}

DashboardPreviewPlate::Style DashboardPreviewPlate::style() const
{
    return style_;
}

void DashboardPreviewPlate::setStyle(Style style)
{
    if (style_ == style)
        return;

    style_ = style;
    update();
}

qreal DashboardPreviewPlate::phase() const
{
    return phase_;
}

void DashboardPreviewPlate::setPhase(qreal phase)
{
    if (qFuzzyCompare(phase_, phase))
        return;

    phase_ = phase;
    update();
}

QColor DashboardPreviewPlate::accentTint() const
{
    return accentTint_;
}

void DashboardPreviewPlate::setAccentTint(const QColor &color)
{
    accentTint_ = color;
    update();
}

void DashboardPreviewPlate::paintEvent(QPaintEvent *event)
{
    Q_UNUSED(event)

    const DashboardSurfaceTokens tokens = DashboardSurfaceTokens::fromTheme(ThemeManager::instance());
    const int radius = style_ == Style::HeroBand ? tokens.radiusHero - 6 : tokens.radiusInset - 2;

    QColor bandA = tokens.panelInsetA;
    QColor bandB = tokens.panelInsetB;
    QColor lineA = tokens.glowPrimary;
    QColor lineB = tokens.glowTertiary;
    qreal amplitude = 0.16;

    switch (style_)
    {
    case Style::SoftBand:
        amplitude = 0.13;
        break;
    case Style::HeroBand:
        bandA = dashboardMix(tokens.panelRaisedA, tokens.glowPrimary, 0.07);
        bandB = dashboardMix(tokens.panelBaseB, QColor(QStringLiteral("#04070e")), 0.22);
        amplitude = 0.16;
        break;
    case Style::WidePreview:
        amplitude = 0.13;
        bandA = dashboardMix(tokens.panelInsetA, tokens.glowSecondary, 0.07);
        lineB = dashboardWithAlpha(tokens.glowSecondary, 0.82);
        break;
    case Style::SmallPreview:
        amplitude = 0.095;
        bandA = dashboardMix(tokens.panelInsetA, tokens.glowPrimary, 0.04);
        break;
    case Style::HorizonBand:
        amplitude = 0.07;
        bandA = dashboardMix(tokens.panelInsetA, tokens.glowSecondary, 0.06);
        lineA = dashboardMix(tokens.glowPrimary, tokens.glowSecondary, 0.36);
        lineB = dashboardWithAlpha(tokens.glowSecondary, 0.82);
        break;
    case Style::ContourBand:
        amplitude = 0.085;
        bandA = dashboardMix(tokens.panelInsetA, tokens.glowTertiary, 0.08);
        lineA = dashboardMix(tokens.glowTertiary, tokens.glowPrimary, 0.32);
        lineB = tokens.glowPrimary;
        break;
    case Style::DataShimmer:
        amplitude = 0.04;
        bandA = dashboardMix(tokens.panelInsetA, tokens.glowPrimary, 0.04);
        lineA = dashboardMix(tokens.glowSecondary, QColor(QStringLiteral("#6fd6ff")), 0.34);
        lineB = dashboardWithAlpha(tokens.glowSecondary, 0.82);
        break;
    }

    if (accentTint_.isValid())
    {
        lineA = dashboardMix(lineA, accentTint_, 0.48);
        lineB = dashboardMix(lineB, accentTint_, 0.35);
    }

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);

    QRectF rectF = rect().adjusted(1.0, 1.0, -1.0, -1.0);
    QPainterPath panelPath;
    panelPath.addRoundedRect(rectF, radius, radius);

    drawBandBase(painter, panelPath, rectF, bandA, bandB, tokens);

    painter.setClipPath(panelPath);
    const QRectF bandBounds = rectF.adjusted(10.0, 8.0, -10.0, -10.0);

    if (style_ == Style::DataShimmer)
    {
        QLinearGradient scan(bandBounds.topLeft(), bandBounds.bottomRight());
        scan.setColorAt(0.0, dashboardWithAlpha(lineA, 0.020));
        scan.setColorAt(0.42, dashboardWithAlpha(lineB, 0.040));
        scan.setColorAt(1.0, dashboardWithAlpha(lineA, 0.016));
        painter.fillRect(bandBounds, scan);

        painter.setPen(QPen(dashboardWithAlpha(lineA, 0.032), 1.0));
        const qreal stepX = qMax(12.0, bandBounds.width() / 10.0);
        for (qreal x = bandBounds.left(); x < bandBounds.right(); x += stepX)
            painter.drawLine(QPointF(x, bandBounds.top()), QPointF(x, bandBounds.bottom()));

        painter.setPen(QPen(dashboardWithAlpha(lineB, 0.045), 1.0));
        const qreal stepY = qMax(10.0, bandBounds.height() / 5.0);
        for (qreal y = bandBounds.top(); y < bandBounds.bottom(); y += stepY)
            painter.drawLine(QPointF(bandBounds.left(), y), QPointF(bandBounds.right(), y));

        QLinearGradient pulse(bandBounds.left(), bandBounds.top(), bandBounds.right(), bandBounds.top());
        pulse.setColorAt(0.0, Qt::transparent);
        pulse.setColorAt(0.50, dashboardWithAlpha(lineA, 0.14));
        pulse.setColorAt(1.0, Qt::transparent);
        painter.setPen(QPen(QBrush(pulse), 1.2));
        painter.drawLine(QPointF(bandBounds.left(), bandBounds.top() + bandBounds.height() * 0.42 + phase_ * 2.0),
                         QPointF(bandBounds.right(), bandBounds.top() + bandBounds.height() * 0.42 + phase_ * 2.0));
    }
    else if (style_ == Style::ContourBand)
    {
        for (int i = 0; i < 3; ++i)
        {
            const qreal shift = i * 4.5;
            QPainterPath contour = wavePath(bandBounds.adjusted(0.0, shift, 0.0, shift), phase_ + i * 0.12, amplitude - i * 0.012);
            painter.setPen(QPen(dashboardWithAlpha(i == 0 ? lineA : lineB, i == 0 ? 0.11 : 0.035), i == 0 ? 0.82 : 0.64));
            painter.drawPath(contour);
        }
    }
    else
    {
        const QPainterPath wave = wavePath(bandBounds, phase_, amplitude);

        QPainterPath fillWave = wave;
        fillWave.lineTo(bandBounds.right(), rectF.bottom());
        fillWave.lineTo(bandBounds.left(), rectF.bottom());
        fillWave.closeSubpath();

        QLinearGradient waveFill(rectF.left(), bandBounds.top(), rectF.left(), rectF.bottom());
        waveFill.setColorAt(0.0, dashboardWithAlpha(lineA, 0.00));
        waveFill.setColorAt(style_ == Style::HeroBand ? 0.34 : 0.42, dashboardWithAlpha(lineA, style_ == Style::HeroBand ? 0.030 : 0.020));
        waveFill.setColorAt(1.0, dashboardWithAlpha(lineB, style_ == Style::HeroBand ? 0.060 : 0.046));
        painter.fillPath(fillWave, waveFill);

        if (style_ == Style::HorizonBand)
        {
            painter.setPen(QPen(dashboardWithAlpha(lineA, 0.11), 0.82));
            painter.drawPath(wave);
            painter.setPen(QPen(dashboardWithAlpha(lineB, 0.026), 0.62));
            painter.drawLine(QPointF(bandBounds.left(), bandBounds.center().y() + bandBounds.height() * 0.12),
                             QPointF(bandBounds.right(), bandBounds.center().y() + bandBounds.height() * 0.12));
        }
        else
        {
            painter.setPen(QPen(dashboardWithAlpha(lineA, style_ == Style::HeroBand ? 0.15 : 0.09), style_ == Style::HeroBand ? 0.94 : 0.76));
            painter.drawPath(wave);
        }
    }

    painter.setClipping(false);
    painter.setPen(QPen(dashboardWithAlpha(tokens.borderSoft, 0.30), 0.74));
    painter.drawPath(panelPath);
}
