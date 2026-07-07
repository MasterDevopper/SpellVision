#pragma once

#include <QWidget>

class QVariantAnimation;

// A premium, theme-reactive progress bar for the shell status strip.
//
// Custom-painted because a QProgressBar stylesheet cannot express a glow, a shimmer, or the
// tiered animation quality below. It reads two orthogonal global settings from ThemeManager:
//   - the color TOKENS (repaints on themeChanged) -> switches with the theme;
//   - the AnimationQuality tier (repaints on animationQualityChanged) -> Minimal/Standard/
//     Rich/Lavish select CLEANLY-SEPARATED paint paths (a lower tier pays zero cost for
//     effects it doesn't show; Minimal runs NO animation timer at all).
//
// Exposes an int `value` property + the slice of the QProgressBar API the shell uses
// (setRange/setValue/setFormat/setTextVisible), so the bottom-bar QPropertyAnimation on
// "value" drives it unchanged.
class GlowProgressBar : public QWidget
{
    Q_OBJECT
    Q_PROPERTY(int value READ value WRITE setValue)

public:
    explicit GlowProgressBar(QWidget *parent = nullptr);

    int value() const { return value_; }
    void setRange(int min, int max);       // kept 0..100 by the shell
    void setFormat(const QString &format);  // "%p%" shows the percentage; "" hides text
    void setTextVisible(bool on);

public slots:
    void setValue(int v);

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    // Starts/stops the shared phase animation. Runs ONLY for an animating tier
    // (Standard/Rich/Lavish) AND while a job is mid-flight (value strictly between
    // min and max). Minimal never runs it -> genuinely static, zero idle cost.
    void updateAnimationRunning();

    // Cleanly-separated per-tier fill paint paths.
    void paintFillMinimal(QPainter &p, const QRectF &fill, const QPainterPath &fillPath) const;
    void paintFillStandard(QPainter &p, const QRectF &fill, const QPainterPath &fillPath, qreal frac) const;
    void paintFillRich(QPainter &p, const QRectF &fill, const QPainterPath &fillPath, qreal frac) const;
    void paintLavishExtras(QPainter &p, const QRectF &fill, const QPainterPath &fillPath) const;

    int value_ = 0;
    int min_ = 0;
    int max_ = 100;
    QString format_;
    bool textVisible_ = true;
    qreal animPhase_ = 0.0;                     // 0..1 loop phase (Standard/Rich/Lavish only)
    QVariantAnimation *phaseAnim_ = nullptr;
};
