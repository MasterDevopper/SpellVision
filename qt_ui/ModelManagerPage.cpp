#include "ModelManagerPage.h"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGridLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QTreeWidget>
#include <QTreeWidgetItem>
#include <QGroupBox>
#include <QProgressBar>
#include <QScrollArea>
#include <QApplication>
#include <QTimer>

ModelManagerPage::ModelManagerPage(QWidget *parent)
    : QWidget(parent)
{
    buildUi();
}

void ModelManagerPage::buildUi()
{
    if (!parent())
        return;

    auto *mainLayout = new QVBoxLayout(this);
    
    // Search and filter
    auto *searchLayout = new QHBoxLayout();
    auto *searchLabel = new QLabel(QStringLiteral("Search Models:"));
    searchModelEdit_ = new QLineEdit();
    searchModelEdit_->setPlaceholderText(QStringLiteral("Filter models..."));
    
    searchLayout->addWidget(searchLabel);
    searchLayout->addWidget(searchModelEdit_);
    
    // Action buttons
    auto *buttonLayout = new QHBoxLayout();
    refreshButton_ = new QPushButton(QStringLiteral("Refresh"));
    installButton_ = new QPushButton(QStringLiteral("Install"));
    removeButton_ = new QPushButton(QStringLiteral("Remove"));
    downloadButton_ = new QPushButton(QStringLiteral("Download"));
    scanButton_ = new QPushButton(QStringLiteral("Scan Models"));
    
    buttonLayout->addWidget(refreshButton_);
    buttonLayout->addWidget(installButton_);
    buttonLayout->addWidget(removeButton_);
    buttonLayout->addWidget(downloadButton_);
    buttonLayout->addWidget(scanButton_);
    
    // Model list
    auto *modelsGroup = new QGroupBox(QStringLiteral("Installed Models"));
    auto *modelsLayout = new QVBoxLayout(modelsGroup);
    
    modelsTree_ = new QTreeWidget();
    modelsTree_->setHeaderLabels(QStringList() << QStringLiteral("Name") << QStringLiteral("Type") << QStringLiteral("Size") << QStringLiteral("Status"));
    modelsTree_->setColumnWidth(0, 200);
    modelsTree_->setColumnWidth(1, 100);
    modelsTree_->setColumnWidth(2, 100);
    modelsTree_->setColumnWidth(3, 100);
    
    // Add sample models
    QTreeWidgetItem *item1 = new QTreeWidgetItem(modelsTree_);
    item1->setText(0, QStringLiteral("Stable Diffusion XL"));
    item1->setText(1, QStringLiteral("Checkpoint"));
    item1->setText(2, QStringLiteral("5.2 GB"));
    item1->setText(3, QStringLiteral("Installed"));
    
    QTreeWidgetItem *item2 = new QTreeWidgetItem(modelsTree_);
    item2->setText(0, QStringLiteral("Lora - Anime Style"));
    item2->setText(1, QStringLiteral("LoRA"));
    item2->setText(2, QStringLiteral("1.1 GB"));
    item2->setText(3, QStringLiteral("Installed"));
    
    QTreeWidgetItem *item3 = new QTreeWidgetItem(modelsTree_);
    item3->setText(0, QStringLiteral("ControlNet Canny"));
    item3->setText(1, QStringLiteral("ControlNet"));
    item3->setText(2, QStringLiteral("256 MB"));
    item3->setText(3, QStringLiteral("Installed"));
    
    modelsLayout->addWidget(modelsTree_);
    
    // Model details
    modelDetailsGroup_ = new QGroupBox(QStringLiteral("Model Details"));
    auto *detailsLayout = new QVBoxLayout(modelDetailsGroup_);
    
    modelDetailsLabel_ = new QLabel(QStringLiteral("Select a model to view details"));
    modelDetailsLabel_->setWordWrap(true);
    modelDetailsLabel_->setStyleSheet(QStringLiteral("background-color: #182030; padding: 10px; border-radius: 4px;"));
    
    detailsLayout->addWidget(modelDetailsLabel_);
    
    // Scan progress
    scanProgress_ = new QProgressBar();
    scanProgress_->setMinimum(0);
    scanProgress_->setMaximum(100);
    scanProgress_->setValue(0);
    scanProgress_->setHidden(true);
    
    // Main layout
    mainLayout->addLayout(searchLayout);
    mainLayout->addLayout(buttonLayout);
    mainLayout->addWidget(modelsGroup);
    mainLayout->addWidget(modelDetailsGroup_);
    mainLayout->addWidget(scanProgress_);
    
    // Connect signals
    if (refreshButton_)
    {
        connect(refreshButton_, &QPushButton::clicked, this, &ModelManagerPage::refreshModelList);
    }
    
    if (installButton_)
    {
        connect(installButton_, &QPushButton::clicked, this, &ModelManagerPage::installModel);
    }
    
    if (removeButton_)
    {
        connect(removeButton_, &QPushButton::clicked, this, &ModelManagerPage::removeModel);
    }
    
    if (downloadButton_)
    {
        connect(downloadButton_, &QPushButton::clicked, this, &ModelManagerPage::downloadModel);
    }
    
    if (scanButton_)
    {
        connect(scanButton_, &QPushButton::clicked, this, &ModelManagerPage::scanModels);
    }
    
    if (modelsTree_)
    {
        connect(modelsTree_, &QTreeWidget::itemSelectionChanged, this, &ModelManagerPage::updateModelDetails);
    }
}

void ModelManagerPage::refreshModelList()
{
    if (!modelDetailsLabel_ || !scanProgress_)
        return;

    modelDetailsLabel_->setText(QStringLiteral("Refreshing model list..."));
    scanProgress_->setHidden(false);
    scanProgress_->setValue(25);
    
    QTimer::singleShot(1000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(50);
    });
    
    QTimer::singleShot(2000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(75);
    });
    
    QTimer::singleShot(3000, this, [this]() {
        if (scanProgress_)
        {
            scanProgress_->setValue(100);
            scanProgress_->setHidden(true);
        }
        if (modelDetailsLabel_)
            modelDetailsLabel_->setText(QStringLiteral("Model list refreshed successfully"));
    });
}

void ModelManagerPage::installModel()
{
    if (!modelDetailsLabel_ || !scanProgress_)
        return;

    modelDetailsLabel_->setText(QStringLiteral("Installing model..."));
    scanProgress_->setHidden(false);
    scanProgress_->setValue(20);
    
    QTimer::singleShot(1000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(40);
    });
    
    QTimer::singleShot(2000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(60);
    });
    
    QTimer::singleShot(3000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(80);
    });
    
    QTimer::singleShot(4000, this, [this]() {
        if (scanProgress_)
        {
            scanProgress_->setValue(100);
            scanProgress_->setHidden(true);
        }
        if (modelDetailsLabel_)
            modelDetailsLabel_->setText(QStringLiteral("Model installed successfully"));
        emit modelInstalled(QStringLiteral("new_model.pt"));
    });
}

void ModelManagerPage::removeModel()
{
    if (!modelDetailsLabel_ || !scanProgress_)
        return;

    modelDetailsLabel_->setText(QStringLiteral("Removing model..."));
    scanProgress_->setHidden(false);
    scanProgress_->setValue(30);
    
    QTimer::singleShot(1000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(60);
    });
    
    QTimer::singleShot(2000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(90);
    });
    
    QTimer::singleShot(3000, this, [this]() {
        if (scanProgress_)
        {
            scanProgress_->setValue(100);
            scanProgress_->setHidden(true);
        }
        if (modelDetailsLabel_)
            modelDetailsLabel_->setText(QStringLiteral("Model removed successfully"));
        emit modelRemoved(QStringLiteral("removed_model.pt"));
    });
}

void ModelManagerPage::downloadModel()
{
    if (!modelDetailsLabel_ || !scanProgress_)
        return;

    modelDetailsLabel_->setText(QStringLiteral("Downloading model..."));
    scanProgress_->setHidden(false);
    scanProgress_->setValue(10);
    
    QTimer::singleShot(1000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(30);
    });
    
    QTimer::singleShot(2000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(50);
    });
    
    QTimer::singleShot(3000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(70);
    });
    
    QTimer::singleShot(4000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(90);
    });
    
    QTimer::singleShot(5000, this, [this]() {
        if (scanProgress_)
        {
            scanProgress_->setValue(100);
            scanProgress_->setHidden(true);
        }
        if (modelDetailsLabel_)
            modelDetailsLabel_->setText(QStringLiteral("Model downloaded successfully"));
    });
}

void ModelManagerPage::scanModels()
{
    if (!modelDetailsLabel_ || !scanProgress_)
        return;

    modelDetailsLabel_->setText(QStringLiteral("Scanning models..."));
    scanProgress_->setHidden(false);
    scanProgress_->setValue(0);
    
    QTimer::singleShot(1000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(25);
    });
    
    QTimer::singleShot(2000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(50);
    });
    
    QTimer::singleShot(3000, this, [this]() {
        if (scanProgress_)
            scanProgress_->setValue(75);
    });
    
    QTimer::singleShot(4000, this, [this]() {
        if (scanProgress_)
        {
            scanProgress_->setValue(100);
            scanProgress_->setHidden(true);
        }
        if (modelDetailsLabel_)
            modelDetailsLabel_->setText(QStringLiteral("Model scan complete"));
    });
}

void ModelManagerPage::updateModelDetails()
{
    if (!modelsTree_ || !modelDetailsLabel_)
        return;

    QTreeWidgetItem *current = modelsTree_->currentItem();
    if (current)
    {
        QString details = QString(
            "Name: %1\n"
            "Type: %2\n"
            "Size: %3\n"
            "Status: %4\n"
            "Last Modified: Today\n"
            "Location: /models/%1\n"
            "Description: This is a sample model description for %1"
        ).arg(current->text(0)).arg(current->text(1)).arg(current->text(2)).arg(current->text(3));
        
        modelDetailsLabel_->setText(details);
    }
}
