#pragma once

// The Home gallery model. Deliberately exposes the SAME UserRole+N ints ModelCardModel does, so
// ModelCardDelegate + ModelCardView paint/host it UNMODIFIED -- one grid, one delegate, one cache.
// Maps an output render onto the card contract: name band = filename (ext stripped), type badge =
// Image/Video, family line = source mode (T2I/T2V/…), preview = the media path (the generalized
// ModelThumbnailCache turns a video into a poster). Also feeds ModelCardView's optional overlay-label
// roles so the hover actions read "Open" / "To I2I" instead of "Load Model" / "Inspect".

#include <QAbstractListModel>
#include <QHash>
#include <QString>
#include <QStringList>
#include <QVector>

class OutputCardModel : public QAbstractListModel
{
    Q_OBJECT

public:
    struct Output
    {
        QString path;         // the media file (open / route target)
        QString strippedName; // filename, extension stripped
        QString fullName;     // filename (tooltip)
        QString subtitle;     // model · WxH · seed (tooltip detail)
        QString modeId;       // t2i / i2i / t2v / i2v
        bool isVideo = false;
    };

    explicit OutputCardModel(QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = QModelIndex()) const override;
    QVariant data(const QModelIndex &index, int role) const override;

    // Re-scan the real output roots (chooseComfyOutputPath) + sidecars, newest-first. Returns count.
    int reload();
    int outputCount() const { return outputs_.size(); }
    const Output *outputAt(int row) const;
    void setPickMarks(const QHash<QString, QString> &marks);
    void setPickFilter(const QString &filter); // all | keep | no | unmarked
    void setNameNeedle(const QString &needle);
    void setExtraRoots(const QStringList &roots);
    QStringList extraRoots() const { return extraRoots_; }

    void noteThumbnailReady(const QString &previewPathKey);

private:
    static int maxRecords();
    bool acceptsPickFilter(const QString &path) const;
    QVector<Output> outputs_;
    QHash<QString, int> pathToRow_;
    QHash<QString, QString> pickMarks_;
    QString pickFilter_ = QStringLiteral("all");
    QString nameNeedle_;
    QStringList extraRoots_;
};
