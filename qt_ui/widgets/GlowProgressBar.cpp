#include "GlowProgressBar.h"

#include "../ThemeManager.h"

#include <QAbstractAnimation>
#include <QLinearGradient>
#include <QPainter>
#include <QPainterPath>
#include <QVariantAnimation>

GlowProgressBar::GlowProgressBar(QWidget *parent)
    : QWidget(parent)
{
    // Paint our own surface + glow; let the shell bar show through the rounded corners
    // and around the outer glow.
    setAttribute(Qt::WA_TranslucentBackground);
    setAttribute(Qt::WA_NoSystemBackground);

    // Highlight sweep that runs only while a job is mid-flight (see updateShimmerRunning()).
    shimmerAnim_ = new QVariantAnimation(this);
    shimmerAnim_->setStartValue(0.0);
    shimmerAnim_->setEndValue(1.0);
    shimmerAnim_->setDuration(1400);
    shimmerAnim_->setLoopCount(-1);
    connect(shimmerAnim_, &QVariantAnimation::valueChanged, this, [this](const QVariant &v) {
        shimmer_ = v.toReal();
        update();
    });

    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this,
            qOverload<>(&QWidget::update));
}

void GlowProgressBar::setValue(int v)
{
    v = qBound(min_, v, max_);
    if (v == value_)
        return;
    value_ = v;
    updateShimmerRunning();
    update();
}

void GlowProgressBar::setRange(int min, int max)
{
    min_ = min;
    max_ = max;
    updateShimmerRunning();
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

void GlowProgressBar::updateShimmerRunning()
{
    const bool active = value_ > min_ && value_ < max_;
    if (active && shimmerAnim_->state() != QAbstractAnimation::Running)
    {
        shimmerAnim_->start();
    }
    else if (!active && shimmerAnim_->state() == QAbstractAnimation::Running)
    {
        shimmerAnim_->stop();
        shimmer_ = 0.0;
    }
}

void GlowProgressBar::paintEvent(QPaintEvent *)
{
    const ThemeManager &tm = ThemeManager::instance();
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);

    // Reserve a rim so the outer glow is not clipped by the widget edge.
    const qreal pad = 2.5;
    const QRectF track = QRectF(rect()).adjusted(pad, pad, -pad, -pad);
    if (track.width() <= 0 || track.height() <= 0)
        return;
    const qreal radius = track.height() / 2.0;

    QPainterPath trackPath;
    trackPath.addRoundedRect(track, radius, radius);

    // --- inset track: a subtle top->bottom sheen well + faint hairline ---
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

        // --- outer glow: expanding translucent strokes of AccentGlow (cheap soft halo) ---
        const QColor glow = tm.color(ThemeManager::Color::AccentGlow);
        p.setBrush(Qt::NoBrush);
        for (int i = 3; i >= 1; --i)
        {
            QPen gp(QColor(glow.red(), glow.green(), glow.blue(), glow.alpha() / (i + 1)));
            gp.setWidthF(i * 2.0);
            p.setPen(gp);
            p.drawPath(fillPath);
        }

        // --- gradient fill: deep ember/violet -> hero accent, left to right ---
        QLinearGradient grad(fill.left(), 0, fill.right(), 0);
        grad.setColorAt(0.0, tm.color(ThemeManager::Color::AccentSecondary));
        grad.setColorAt(1.0, tm.color(ThemeManager::Color::Accent));
        p.fillPath(fillPath, grad);

        // --- highlight shimmer sweeping across the fill (only while active) ---
        if (shimmerAnim_->state() == QAbstractAnimation::Running)
        {
            p.save();
            p.setClipPath(fillPath);
            const qreal bandW = fill.width() * 0.28 + 22.0;
            const qreal x = -bandW + shimmer_ * (fill.width() + bandW * 2.0);
            QColor edge = tm.color(ThemeManager::Color::TextHi);
            edge.setAlpha(0);
            QColor peak = tm.color(ThemeManager::Color::TextHi);
            peak.setAlpha(72);
            QLinearGradient sh(x, 0, x + bandW, 0);
            sh.setColorAt(0.0, edge);
            sh.setColorAt(0.5, peak);
            sh.setColorAt(1.0, edge);
            p.fillRect(fill, sh);
            p.restore();
        }

        // --- bright leading edge (a luminous cap where the fill ends) ---
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

    // --- percentage text (shell shows "%p%" when busy, "" otherwise) ---
    if (textVisible_ && !format_.isEmpty())
    {
        QString text = format_;
        text.replace(QStringLiteral("%p"), QString::number(int(frac * 100.0 + 0.5)));
        QFont f = font();
        f.setPixelSize(9);
        f.setBold(true);
        p.setFont(f);
        // Legible over both the dark track and the accent fill.
        p.setPen(tm.color(ThemeManager::Color::TextHi));
        p.drawText(QRectF(rect()), Qt::AlignCenter, text);
    }
}
