#pragma once

#include <QColor>
#include <QWidget>

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
    Variant variant_ = Variant::Standard;
    int cornerRadius_ = 20;
    qreal glowStrength_ = 1.0;
    QColor accentTint_;
};
