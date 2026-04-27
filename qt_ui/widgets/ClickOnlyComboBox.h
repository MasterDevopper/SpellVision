#pragma once

#include <QComboBox>

class QWheelEvent;

namespace spellvision::widgets
{

class ClickOnlyComboBox final : public QComboBox
{
public:
    explicit ClickOnlyComboBox(QWidget *parent = nullptr);

protected:
    void wheelEvent(QWheelEvent *event) override;
};

} // namespace spellvision::widgets
