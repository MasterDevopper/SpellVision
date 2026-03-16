#include "QueueManager.h"
#include <QUuid>

QueueManager::QueueManager(QObject* parent)
    : QObject(parent)
{
}

void QueueManager::addItem(const QueueItem& item)
{
    items.append(item);
    emit queueChanged();
}

void QueueManager::removeItem(QString id)
{
    for(int i=0;i<items.size();i++)
    {
        if(items[i].id == id)
        {
            items.remove(i);
            break;
        }
    }

    emit queueChanged();
}

void QueueManager::moveUp(QString id)
{
    for(int i=1;i<items.size();i++)
    {
        if(items[i].id == id)
        {
            items.swapItemsAt(i,i-1);
            break;
        }
    }

    emit queueChanged();
}

void QueueManager::moveDown(QString id)
{
    for(int i=0;i<items.size()-1;i++)
    {
        if(items[i].id == id)
        {
            items.swapItemsAt(i,i+1);
            break;
        }
    }

    emit queueChanged();
}

void QueueManager::moveTop(QString id)
{
    for(int i=0;i<items.size();i++)
    {
        if(items[i].id == id)
        {
            QueueItem item = items.takeAt(i);
            items.prepend(item);
            break;
        }
    }

    emit queueChanged();
}

void QueueManager::moveBottom(QString id)
{
    for(int i=0;i<items.size();i++)
    {
        if(items[i].id == id)
        {
            QueueItem item = items.takeAt(i);
            items.append(item);
            break;
        }
    }

    emit queueChanged();
}

void QueueManager::duplicate(QString id)
{
    for(const QueueItem& item : items)
    {
        if(item.id == id)
        {
            QueueItem copy = item;
            copy.id = QUuid::createUuid().toString();
            copy.retry_count = 0;
            items.append(copy);
            break;
        }
    }

    emit queueChanged();
}

void QueueManager::cancelAll()
{
    items.clear();
    emit queueChanged();
}
