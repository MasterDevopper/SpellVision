#pragma once

#include <QString>
#include <QStringList>
#include <QWidget>

class ModePage : public QWidget
{
    Q_OBJECT

public:
    explicit ModePage(const QString &title,
                      const QString &subtitle,
                      const QStringList &sectionBullets,
                      QWidget *parent = nullptr);
};
