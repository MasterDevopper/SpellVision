#pragma once

#include <QColor>
#include <QRectF>
#include <QWidget>

class QPainter;
class QPainterPath;

class DashboardGlassPanel : public QWidget
{
public:
    enum class Variant
    {
        Standard,
        Raised,
        Hero,
        Inset,
        Utility
    };

    explicit DashboardGlassPanel(QWidget *parent = nullptr);

    Variant variant() const;
    void setVariant(Variant variant);

    int cornerRadius() const;
    void setCornerRadius(int radius);

    qreal glowStrength() const;
    void setGlowStrength(qreal strength);

    QColor accentTint() const;
    void setAccentTint(const QColor &color);

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    // The opaque path, used by MatteInstrument for every panel and by Hybrid for everything that is
    // not the hero. Deliberately a separate function rather than a flag threaded through the glass
    // stack: they are different materials, not one material at a lower setting.
    void paintMatte(QPainter &painter,
                    const QPainterPath &path,
                    const QRectF &bounds,
                    const QColor &fillA,
                    const QColor &fillB,
                    const QColor &border) const;

    Variant variant_ = Variant::Standard;
    int cornerRadius_ = 12;
    qreal glowStrength_ = 0.85;
    QColor accentTint_;
};
