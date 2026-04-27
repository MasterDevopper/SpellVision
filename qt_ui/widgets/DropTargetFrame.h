#pragma once

#include <QFrame>
#include <functional>

class QDragEnterEvent;
class QDropEvent;

namespace spellvision::widgets
{

class DropTargetFrame final : public QFrame
{
public:
    explicit DropTargetFrame(QWidget *parent = nullptr);

    std::function<void(const QString &)> onFileDropped;

protected:
    void dragEnterEvent(QDragEnterEvent *event) override;
    void dropEvent(QDropEvent *event) override;
};

} // namespace spellvision::widgets
