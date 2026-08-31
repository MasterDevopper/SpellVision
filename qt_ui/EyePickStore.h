#pragma once

#include <QHash>
#include <QString>

class EyePickStore
{
public:
    void setProjectRoot(const QString &root);
    [[nodiscard]] QString storePath() const;
    [[nodiscard]] QString markFor(const QString &mediaPath) const;
    void setMark(const QString &mediaPath, const QString &mark); // keep | no | empty
    [[nodiscard]] QHash<QString, QString> marks() const { return marks_; }
    bool load();
    bool save() const;
    bool exportTo(const QString &destPath) const;

    static QString normalizePath(const QString &path);

private:
    QString projectRoot_;
    QHash<QString, QString> marks_;
};
