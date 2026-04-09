#include "DashboardMetricChip.h"

#include "DashboardSurfaceTokens.h"
#include "ThemeManager.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QPaintEvent>
#include <QPainter>
#include <QPainterPath>

DashboardMetricChip::DashboardMetricChip(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QHBoxLayout(this);
    layout->setContentsMargins(7, 4, 7, 4);
    layout->setSpacing(5);

    titleLabel_ = new QLabel(this);
    valueLabel_ = new QLabel(this);
    valueLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    valueLabel_->setSizePolicy(QSizePolicy::MinimumExpanding, QSizePolicy::Preferred);

    layout->addWidget(titleLabel_);
    layout->addStretch(1);
    layout->addWidget(valueLabel_);

    setMinimumHeight(28);
    syncLabelStyle();
}

void DashboardMetricChip::setTitle(const QString &title)
{
    if (titleLabel_)
        titleLabel_->setText(title);
}

void DashboardMetricChip::setValue(const QString &value)
{
    if (valueLabel_)
        valueLabel_->setText(value);
}

QString DashboardMetricChip::title() const
{
    return titleLabel_ ? titleLabel_->text() : QString();
}

QString DashboardMetricChip::value() const
{
    return valueLabel_ ? valueLabel_->text() : QString();
}

void DashboardMetricChip::setEmphasized(bool emphasized)
{
    if (emphasized_ == emphasized)
        return;

    emphasized_ = emphasized;
    syncLabelStyle();
    update();
}

bool DashboardMetricChip::isEmphasized() const
{
    return emphasized_;
}

void DashboardMetricChip::paintEvent(QPaintEvent *event)
{
    Q_UNUSED(event)

    syncLabelStyle();

    const DashboardSurfaceTokens tokens = DashboardSurfaceTokens::fromTheme(ThemeManager::instance());

    QColor fillA = emphasized_ ? dashboardMix(tokens.utilityA, tokens.glowPrimary, 0.08) : dashboardMix(tokens.utilityA, QColor(QStringLiteral("#02050a")), 0.16);
    QColor fillB = emphasized_ ? dashboardMix(tokens.utilityB, tokens.glowSecondary, 0.05) : tokens.utilityB;
    QColor border = emphasized_ ? dashboardWithAlpha(tokens.borderStrong, 0.90) : dashboardWithAlpha(tokens.borderSoft, 0.88);

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);

    QRectF rectF = rect().adjusted(1.0, 1.0, -1.0, -1.0);
    QPainterPath path;
    path.addRoundedRect(rectF, tokens.radiusChip, tokens.radiusChip);

    QLinearGradient fill(rectF.topLeft(), rectF.bottomRight());
    fill.setColorAt(0.0, fillA);
    fill.setColorAt(1.0, fillB);
    painter.fillPath(path, fill);

    if (emphasized_)
    {
        QLinearGradient glow(rectF.topLeft(), rectF.topRight());
        glow.setColorAt(0.0, Qt::transparent);
        glow.setColorAt(0.34, dashboardWithAlpha(tokens.glowPrimary, 0.14));
        glow.setColorAt(0.72, dashboardWithAlpha(tokens.glowTertiary, 0.06));
        glow.setColorAt(1.0, Qt::transparent);
        painter.setPen(QPen(QBrush(glow), 1.0));
        painter.drawLine(rectF.left() + 10.0, rectF.top() + 2.0, rectF.right() - 10.0, rectF.top() + 2.0);
    }

    painter.setPen(QPen(border, 1.0));
    painter.drawPath(path);
}

void DashboardMetricChip::syncLabelStyle()
{
    const DashboardSurfaceTokens tokens = DashboardSurfaceTokens::fromTheme(ThemeManager::instance());

    if (titleLabel_)
    {
        titleLabel_->setStyleSheet(QStringLiteral("background: transparent; color: %1; font-size: 8px; font-weight: 700;")
                                       .arg((emphasized_ ? tokens.textSecondary : tokens.textMuted).name()));
    }

    if (valueLabel_)
    {
        valueLabel_->setStyleSheet(QStringLiteral("background: transparent; color: %1; font-size: 8px; font-weight: 800;")
                                       .arg(tokens.textPrimary.name()));
    }
}
