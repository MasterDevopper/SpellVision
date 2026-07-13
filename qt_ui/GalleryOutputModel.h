#pragma once

// Home gallery data source. Scans the REAL ComfyUI output directory (chooseComfyOutputPath, where the
// worker actually writes -- NOT the stale {projectRoot}/output the old Home read) for recent renders,
// pairs each media file with its SpellVision .json sidecar (mode / prompt / model / dims / seed), and
// exposes them newest-first as a QAbstractListModel the gallery grid paints. Capped so a huge history
// doesn't stall the scan; thumbnails are pulled lazily by the delegate via ModelThumbnailCache.

#include <QAbstractListModel>
#include <QString>
#include <QVector>

class GalleryOutputModel : public QAbstractListModel
{
    Q_OBJECT

public:
    enum Roles
    {
        ThumbnailPathRole = Qt::UserRole + 1, // image: the file itself; video: a poster still or "" (placeholder)
        TitleRole,                            // caption (prompt snippet, else filename stem)
        SubtitleRole,                         // "model · WxH · seed" style detail line
        ModeIdRole,                           // t2i / i2i / t2v / i2v (routing + badge)
        IsVideoRole,                          // bool
        PathRole,                             // the output media file (open / route target)
        TooltipRole                           // full params for hover
    };

    struct Record
    {
        QString path;
        QString thumbnailPath;
        QString title;
        QString subtitle;
        QString tooltip;
        QString modeId;
        bool isVideo = false;
    };

    explicit GalleryOutputModel(QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = QModelIndex()) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;

    // Re-scan the output directory. Returns the number of records found.
    int reload();
    int outputCount() const { return records_.size(); }
    const Record *recordAt(int row) const;

private:
    static int maxRecords();
    QVector<Record> records_;
};
