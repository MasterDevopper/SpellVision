#pragma once

// SpellVision — Chain Studio persistence (Pass 2).
//
// Persists the Chain model from Pass 1's ChainModel.h. Two surfaces:
//
//  1. The full Chain document  -> JSON file, one per chain.
//     Location follows the convention already in use by ManagerPage,
//     ModelManagerPage, and WorkflowLibraryPage: AppLocalDataLocation
//     with a runtime/cache/ui fallback under projectRoot. Chain files
//     live under <base>/chains/<chainId>.json so they sit beside the
//     existing *_cache.json files without colliding.
//
//  2. The "last active chain" pointer -> QSettings("DarkDuck",
//     "SpellVision"), group "ChainStudio/", key "lastActiveChainId".
//     Mirrors ImageGenerationPage::saveSnapshot()'s namespace pattern
//     exactly. Empty string = no active chain.
//
// Behavior boundaries:
//  - The store NEVER copies or moves media files. It records paths.
//    Variation outputPath / thumbnailPath are written verbatim and
//    must already exist on disk when save() runs; load() returns them
//    as-is even if the file no longer exists (the engine surfaces
//    that as a stale-variation state, not the store).
//  - load() returning std::nullopt is the normal "no such chain" case;
//    save() returning false is a real I/O failure that callers must
//    handle (probably surface to the UI).
//  - Pure: no QObject, no signals, no internal state besides the
//    projectRoot fallback the constructor records.

#include "chain/ChainModel.h"

#include <QJsonObject>
#include <QString>
#include <optional>

namespace spellvision::chain
{

    class ChainStore
    {
    public:
        // projectRoot is the optional fallback location used iff
        // QStandardPaths::AppLocalDataLocation is empty (same fallback
        // pattern as ModelManagerPage::cacheFilePath). Pass "" to skip
        // the fallback and use QDir::current() as the last resort.
        explicit ChainStore(QString projectRoot = QString());

        // -------- JSON round-trip (pure functions) --------
        // toJson / fromJson are static so tests + the Pass 6 harness can
        // round-trip without instantiating a store. They never touch disk.
        static QJsonObject toJson(const Chain &chain);
        static std::optional<Chain> fromJson(const QJsonObject &obj);

        // -------- disk persistence --------
        // save() writes <base>/chains/<chain.id>.json atomically (via
        // QSaveFile). Returns false only on I/O failure.
        bool save(const Chain &chain) const;

        // load() returns nullopt if the file doesn't exist or fails to
        // parse. It does NOT distinguish those two cases at the API
        // surface; the engine treats both as "no chain available".
        std::optional<Chain> load(const QString &chainId) const;

        // -------- pointer (QSettings) --------
        void setLastActiveChainId(const QString &chainId);
        QString lastActiveChainId() const;

        // -------- introspection (used by the harness + future debug UI) --
        QString chainsDir() const; // resolved <base>/chains
        QString chainFilePath(const QString &chainId) const;

    private:
        QString projectRoot_;
    };

} // namespace spellvision::chain