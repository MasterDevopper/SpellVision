#ifndef SPELLVISION_HOMEMODULEFRAME_H
#define SPELLVISION_HOMEMODULEFRAME_H

#include <QString>
#include <QWidget>

class DashboardGlassPanel;
class QLabel;

class HomeModuleFrame : public QWidget
{
    Q_OBJECT

public:
    explicit HomeModuleFrame(const QString &moduleId,
                             const QString &title,
                             QWidget *content,
                             QWidget *parent = nullptr);

    QString moduleId() const;
    void setCustomizeMode(bool enabled);
    bool isCustomizeMode() const;

signals:
    void moveRequested(const QString &moduleId, int dx, int dy);
    void resizeRequested(const QString &moduleId, int dw, int dh);
    void visibilityRequested(const QString &moduleId, bool visible);

private:
    QString moduleId_;
    DashboardGlassPanel *surface_ = nullptr;
    QWidget *header_ = nullptr;
    QWidget *content_ = nullptr;
    QLabel *titleLabel_ = nullptr;
};

#endif // SPELLVISION_HOMEMODULEFRAME_H
