#pragma once

#include <QWidget>

class QLabel;

class DashboardMetricChip : public QWidget
{
public:
    explicit DashboardMetricChip(QWidget *parent = nullptr);

    void setTitle(const QString &title);
    void setValue(const QString &value);
    QString title() const;
    QString value() const;

    void setEmphasized(bool emphasized);
    bool isEmphasized() const;

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    void syncLabelStyle();

    QLabel *titleLabel_ = nullptr;
    QLabel *valueLabel_ = nullptr;
    bool emphasized_ = false;
};
