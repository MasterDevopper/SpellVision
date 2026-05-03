#pragma once

#include <QList>
#include <QString>
#include <QWidget>

class QComboBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QTableWidget;
class QTableWidgetItem;

class T2VHistoryPage : public QWidget
{
    Q_OBJECT

public:
    explicit T2VHistoryPage(QWidget *parent = nullptr);

    void setProjectRoot(const QString &projectRoot);
    void refreshHistory();

protected:
    void showEvent(QShowEvent *event) override;

signals:
    void ltxRequeueSubmitted(const QString &promptId, const QString &primaryOutputPath);

private slots:
    void handleSelectionChanged();
    void openSelectedVideo();
    void revealSelectedVideo();
    void copySelectedPrompt();
    void copySelectedMetadataPath();
    void prepareSelectedLtxRequeueDraft();
    void validateSelectedLtxRequeueDraft();
    void submitSelectedLtxRequeueDraft();
    void scheduleRefreshAfterLtxRequeueSubmit(const QJsonObject &response);
    void applyFilters();

private:
    struct VideoHistoryItem
    {
        QString historyId;
        QString jobId;
        QString command;
        QString promptPreview;
        QString outputPath;
        QString metadataPath;
        QString finishedAt;
        QString durationLabel;
        QString resolution;
        QString stackSummary;
        QString lowModelName;
        QString highModelName;
        QString runtimeSummary;
        QString metadataStatus;
        QString outputContractStatus;
        QString outputContractWarnings;
        qint64 outputFileSizeBytes = 0;
        bool outputExists = false;
        bool metadataExists = false;
        bool outputContractOk = false;
    };

    QString historyIndexPath() const;
    QList<VideoHistoryItem> loadHistoryItems();
    QList<VideoHistoryItem> loadLtxRegistryHistoryItems() const;
    void mergeLtxRegistryHistoryItems(QList<VideoHistoryItem> &items) const;
    void populateTable();
    bool itemMatchesFilters(const VideoHistoryItem &item) const;
    QString activeContractFilter() const;
    void updateDetailsForItem(const VideoHistoryItem &item);
    void updateEmptyDetails();
    int selectedRow() const;
    const VideoHistoryItem *selectedItem() const;
    QString formatFileSize(qint64 bytes) const;
    QString formatFinishedAt(const QString &isoText) const;
    QString compactText(const QString &text, int maxChars) const;
    void applyTheme();

    QString projectRoot_;
    QList<VideoHistoryItem> items_;
    QList<int> visibleItemIndexes_;
    QString loadErrorText_;

    QLabel *summaryLabel_ = nullptr;
    QLabel *detailsTitleLabel_ = nullptr;
    QLabel *detailsBodyLabel_ = nullptr;
    QLabel *detailsStatusLabel_ = nullptr;
    QLabel *emptyStateLabel_ = nullptr;
    QTableWidget *table_ = nullptr;
    QLineEdit *searchEdit_ = nullptr;
    QComboBox *contractFilterCombo_ = nullptr;
    QPushButton *refreshButton_ = nullptr;
    QPushButton *openVideoButton_ = nullptr;
    QPushButton *revealFolderButton_ = nullptr;
    QPushButton *copyPromptButton_ = nullptr;
    QPushButton *copyMetadataPathButton_ = nullptr;
    QPushButton *requeueButton_ = nullptr;
    QPushButton *validateRequeueButton_ = nullptr;
    QPushButton *submitRequeueButton_ = nullptr;
    QString validatedRequeueDraftPath_;
};
