#include "GlowProgressBar.h"

#include "../ThemeManager.h"

#include <QAbstractAnimation>
#include <QLinearGradient>
#include <QPainter>
#include <QPainterPath>
#include <QVariantAnimation>

#include <cmath>

namespace
{
constexpr qreal kTwoPi = 6.283185307179586;
}

GlowProgressBar::GlowProgressBar(QWidget *parent)
    : QWidget(parent)
{
    // Paint our own surface + glow; let the shell bar show through the rounded corners
    // and around the outer glow.
    setAttribute(Qt::WA_TranslucentBackground);
    setAttribute(Qt::WA_NoSystemBackground);

    // One shared 0..1 phase loop that the animating tiers interpret (Standard = edge wave,
    // Rich = shimmer sweep, Lavish = shimmer + rising bubbles). Started/stopped by
    // updateAnimationRunning(); Minimal never runs it.
    phaseAnim_ = new QVariantAnimation(this);
    phaseAnim_->setStartValue(0.0);
    phaseAnim_->setEndValue(1.0);
    phaseAnim_->setDuration(1600);
    phaseAnim_->setLoopCount(-1);
    connect(phaseAnim_, &QVariantAnimation::valueChanged, this, [this](const QVariant &v) {
        animPhase_ = v.toReal();
        update();
    });

    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this,
            qOverload<>(&QWidget::update));
    // Tier change: (re)evaluate whether the timer should run, then repaint on the new path.
    connect(&ThemeManager::instance(), &ThemeManager::animationQualityChanged, this, [this] {
        updateAnimationRunning();
        update();
    });
}

void GlowProgressBar::setValue(int v)
{
    v = qBound(min_, v, max_);
    if (v == value_)
        return;
    value_ = v;
    updateAnimationRunning();
    update();
}

void GlowProgressBar::setRange(int min, int max)
{
    min_ = min;
    max_ = max;
    updateAnimationRunning();
    update();
}

void GlowProgressBar::setFormat(const QString &format)
{
    if (format_ == format)
        return;
    format_ = format;
    update();
}

void GlowProgressBar::setTextVisible(bool on)
{
    if (textVisible_ == on)
        return;
    textVisible_ = on;
    update();
}

void GlowProgressBar::updateAnimationRunning()
{
    const bool animatingTier =
        ThemeManager::instance().animationQuality() != ThemeManager::AnimationQuality::Minimal;
    const bool active = value_ > min_ && value_ < max_;
    const bool shouldRun = animatingTier && active;

    if (shouldRun && phaseAnim_->state() != QAbstractAnimation::Running)
    {
        phaseAnim_->start();
    }
    else if (!shouldRun && phaseAnim_->state() == QAbstractAnimation::Running)
    {
        phaseAnim_->stop();
        animPhase_ = 0.0;
    }
}

void GlowProgressBar::paintEvent(QPaintEvent *)
{
    const ThemeManager &tm = ThemeManager::instance();
    const ThemeManager::AnimationQuality tier = tm.animationQuality();
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);

    // Reserve a rim so an outer glow is not clipped by the widget edge.
    const qreal pad = 2.5;
    const QRectF track = QRectF(rect()).adjusted(pad, pad, -pad, -pad);
    if (track.width() <= 0 || track.height() <= 0)
        return;
    const qreal radius = track.height() / 2.0;

    QPainterPath trackPath;
    trackPath.addRoundedRect(track, radius, radius);

    // --- inset track: a subtle top->bottom sheen well + faint hairline (every tier) ---
    QLinearGradient well(track.topLeft(), track.bottomLeft());
    well.setColorAt(0.0, tm.color(ThemeManager::Color::Surface0).darker(112));
    well.setColorAt(1.0, tm.color(ThemeManager::Color::Surface1));
    p.fillPath(trackPath, well);
    QPen hairline(tm.color(ThemeManager::Color::BorderSubtle));
    hairline.setWidthF(1.0);
    p.setPen(hairline);
    p.drawPath(trackPath);

    const qreal frac = (max_ > min_) ? qreal(value_ - min_) / qreal(max_ - min_) : 0.0;

    if (frac > 0.0)
    {
        const qreal fillW = qMax(track.height(), track.width() * qMin(frac, 1.0));
        const QRectF fill(track.left(), track.top(), fillW, track.height());
        QPainterPath fillPath;
        fillPath.addRoundedRect(fill, radius, radius);

        // Distinct paint paths — a lower tier does none of a higher tier's work.
        switch (tier)
        {
        case ThemeManager::AnimationQuality::Minimal:
            paintFillMinimal(p, fill, fillPath);
            break;
        case ThemeManager::AnimationQuality::Standard:
            paintFillStandard(p, fill, fillPath, frac);
            break;
        case ThemeManager::AnimationQuality::Rich:
            paintFillRich(p, fill, fillPath, frac);
            break;
        case ThemeManager::AnimationQuality::Lavish:
            paintFillRich(p, fill, fillPath, frac);
            paintLavishExtras(p, fill, fillPath);
            break;
        }
    }

    // --- percentage text (shell shows "%p%" when busy, "" otherwise) — every tier ---
    if (textVisible_ && !format_.isEmpty())
    {
        QString text = format_;
        text.replace(QStringLiteral("%p"), QString::number(int(frac * 100.0 + 0.5)));
        QFont f = font();
        f.setPixelSize(tm.fontSize(ThemeManager::Type::Micro));   // was 9 -> Type::Micro
        f.setWeight(static_cast<QFont::Weight>(tm.fontWeight(ThemeManager::Type::Micro)));
        p.setFont(f);
        p.setPen(tm.color(ThemeManager::Color::TextHi));
        p.drawText(QRectF(rect()), Qt::AlignCenter, text);
    }
}

// MINIMAL — flat gradient fill. No glow, no leading edge, no motion, no timer. The cheap floor.
void GlowProgressBar::paintFillMinimal(QPainter &p, const QRectF &fill, const QPainterPath &fillPath) const
{
    const ThemeManager &tm = ThemeManager::instance();
    QLinearGradient grad(fill.left(), 0, fill.right(), 0);
    grad.setColorAt(0.0, tm.color(ThemeManager::Color::AccentSecondary));
    grad.setColorAt(1.0, tm.color(ThemeManager::Color::Accent));
    p.fillPath(fillPath, grad);
}

// STANDARD — gradient fill + a gentle meniscus at the leading edge (a soft highlight that
// slowly bobs left/right + breathes). Light motion, no outer glow, no full-width shimmer.
void GlowProgressBar::paintFillStandard(QPainter &p, const QRectF &fill, const QPainterPath &fillPath, qreal frac) const
{
    const ThemeManager &tm = ThemeManager::instance();
    QLinearGradient grad(fill.left(), 0, fill.right(), 0);
    grad.setColorAt(0.0, tm.color(ThemeManager::Color::AccentSecondary));
    grad.setColorAt(1.0, tm.color(ThemeManager::Color::Accent));
    p.fillPath(fillPath, grad);

    if (frac < 1.0)
    {
        p.save();
        p.setClipPath(fillPath);
        const qreal breathe = 0.5 + 0.5 * std::sin(animPhase_ * kTwoPi);   // 0..1
        const qreal bob = std::sin(animPhase_ * kTwoPi) * 2.5;              // +/- px near the edge
        const qreal edgeW = 15.0;
        const qreal right = fill.right() + bob;
        QColor tip = tm.color(ThemeManager::Color::AccentTertiary);
        QColor tip0 = tip;
        tip0.setAlpha(0);
        tip.setAlpha(int(55 + 90 * breathe));
        QLinearGradient edge(right - edgeW, 0, right, 0);
        edge.setColorAt(0.0, tip0);
        edge.setColorAt(1.0, tip);
        p.fillRect(QRectF(right - edgeW, fill.top(), edgeW, fill.height()), edge);
        p.restore();
    }
}

// RICH — gradient fill + soft outer glow + sweeping shimmer + bright leading-edge cap.
void GlowProgressBar::paintFillRich(QPainter &p, const QRectF &fill, const QPainterPath &fillPath, qreal frac) const
{
    const ThemeManager &tm = ThemeManager::instance();

    // outer glow: expanding translucent strokes of AccentGlow (cheap soft halo)
    const QColor glow = tm.color(ThemeManager::Color::AccentGlow);
    p.setBrush(Qt::NoBrush);
    for (int i = 3; i >= 1; --i)
    {
        QPen gp(QColor(glow.red(), glow.green(), glow.blue(), glow.alpha() / (i + 1)));
        gp.setWidthF(i * 2.0);
        p.setPen(gp);
        p.drawPath(fillPath);
    }

    // gradient fill
    QLinearGradient grad(fill.left(), 0, fill.right(), 0);
    grad.setColorAt(0.0, tm.color(ThemeManager::Color::AccentSecondary));
    grad.setColorAt(1.0, tm.color(ThemeManager::Color::Accent));
    p.fillPath(fillPath, grad);

    // sweeping highlight shimmer — only while the phase loop is running (mid-job)
    if (phaseAnim_->state() == QAbstractAnimation::Running)
    {
        p.save();
        p.setClipPath(fillPath);
        const qreal bandW = fill.width() * 0.28 + 22.0;
        const qreal x = -bandW + animPhase_ * (fill.width() + bandW * 2.0);
        QColor e = tm.color(ThemeManager::Color::TextHi);
        e.setAlpha(0);
        QColor peak = tm.color(ThemeManager::Color::TextHi);
        peak.setAlpha(72);
        QLinearGradient sh(x, 0, x + bandW, 0);
        sh.setColorAt(0.0, e);
        sh.setColorAt(0.5, peak);
        sh.setColorAt(1.0, e);
        p.fillRect(fill, sh);
        p.restore();
    }

    // bright leading-edge cap (a luminous surface where the fill ends)
    if (frac < 1.0)
    {
        p.save();
        p.setClipPath(fillPath);
        const qreal edgeW = 11.0;
        QColor tip = tm.color(ThemeManager::Color::AccentTertiary);
        QColor tip0 = tip;
        tip0.setAlpha(0);
        tip.setAlpha(210);
        QLinearGradient edge(fill.right() - edgeW, 0, fill.right(), 0);
        edge.setColorAt(0.0, tip0);
        edge.setColorAt(1.0, tip);
        p.fillRect(QRectF(fill.right() - edgeW, fill.top(), edgeW, fill.height()), edge);
        p.restore();
    }
}

// LAVISH extras — rising, fading bubbles inside the fill (drawn on top of the Rich path).
// Deterministic from animPhase_ (no RNG): fixed per-bubble x / phase / speed.
void GlowProgressBar::paintLavishExtras(QPainter &p, const QRectF &fill, const QPainterPath &fillPath) const
{
    if (phaseAnim_->state() != QAbstractAnimation::Running)
        return;

    static const struct { qreal x, phase, speed, size; } kBubbles[] = {
        {0.16, 0.00, 0.85, 1.7}, {0.34, 0.55, 1.05, 1.2}, {0.52, 0.22, 0.72, 2.0},
        {0.70, 0.78, 0.95, 1.4}, {0.86, 0.40, 1.15, 1.1},
    };

    p.save();
    p.setClipPath(fillPath);
    p.setPen(Qt::NoPen);
    const QColor base = ThemeManager::instance().color(ThemeManager::Color::AccentTertiary);
    for (const auto &b : kBubbles)
    {
        const qreal t = std::fmod(animPhase_ * b.speed + b.phase, 1.0); // 0 (bottom) .. 1 (top)
        const qreal bx = fill.left() + fill.width() * b.x;
        if (bx > fill.right() - 2.0)
            continue; // bubble's column not filled yet
        const qreal by = fill.bottom() - t * fill.height();
        QColor c = base;
        c.setAlpha(int(160 * (1.0 - t))); // fade as it rises
        p.setBrush(c);
        p.drawEllipse(QPointF(bx, by), b.size, b.size);
    }
    p.restore();
}
