#pragma once

#include <QWidget>

class QVariantAnimation;

// A premium, theme-reactive progress bar for the shell status strip.
//
// Custom-painted because a QProgressBar stylesheet cannot express a glow or an animated
// shimmer: a rounded inset track, an AccentSecondary->Accent gradient fill with a soft
// outer glow and a bright leading edge, plus a subtle highlight shimmer that sweeps across
// the fill while a job is in progress. Reads canonical ThemeManager tokens (repaints on
// themeChanged), so it switches with the theme.
//
// Exposes an int `value` property + the small slice of the QProgressBar API the shell uses
// (setRange/setValue/setFormat/setTextVisible), so the existing bottom-bar QPropertyAnimation
// on "value" drives it unchanged.
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
    void updateShimmerRunning();

    int value_ = 0;
    int min_ = 0;
    int max_ = 100;
    QString format_;
    bool textVisible_ = true;
    qreal shimmer_ = 0.0;                       // 0..1 sweep phase while active
    QVariantAnimation *shimmerAnim_ = nullptr;
};
