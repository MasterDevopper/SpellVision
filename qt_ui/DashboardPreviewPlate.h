#pragma once

#include <QColor>
#include <QWidget>

class DashboardPreviewPlate : public QWidget
{
public:
    enum class Style
    {
        SoftBand,
        HeroBand,
        WidePreview,
        SmallPreview,
        HorizonBand,
        ContourBand,
        DataShimmer
    };

    explicit DashboardPreviewPlate(QWidget *parent = nullptr);

    Style style() const;
    void setStyle(Style style);

    qreal phase() const;
    void setPhase(qreal phase);

    QColor accentTint() const;
    void setAccentTint(const QColor &color);

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    Style style_ = Style::SoftBand;
    qreal phase_ = 0.0;
    QColor accentTint_;
};
