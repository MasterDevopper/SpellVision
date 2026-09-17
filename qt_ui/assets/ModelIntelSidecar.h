#pragma once

// W5 — the reader for `<stem>.spellvision.json`, the sidecar `python/model_intelligence` writes
// beside every weight it identifies.
//
// This is a SECOND sidecar reader in this directory, and that is deliberate rather than an
// oversight. `ModelSidecar.h` reads `<stem>.metadata.json`, the frozen import-time schema the
// download lane writes; this reads the identity/display/recommended document the intelligence
// pass writes, which carries hashes, the classifier's kind, quantisation, the site the metadata
// came from, the gallery and per-field provenance. Merging them would mean one struct whose
// fields are half-populated depending on which file happened to exist, and a consumer that cannot
// tell which half it is holding — which is the shape that made `detectType` guess from a path
// substring in the first place.
//
// Three absences are three different facts and the struct keeps them apart:
//   * no sidecar at all           -> present == false          ("we never asked")
//   * a sidecar with no sources   -> present, identified()==false ("we asked; the site did not know")
//   * a sidecar with sources      -> identified()               ("this is what the site says")
// Collapsing the first two is what would let the page show a model as anonymous when the truth is
// that nothing has ever run over it.

#include <QByteArray>
#include <QString>
#include <QStringList>
#include <QVector>

namespace spellvision::assets
{

// `identity.sources[]` — where the metadata came from. `site` is the raw token ("civitai",
// "huggingface"); `siteLabel()` is what the card shows.
struct ModelIntelSource
{
    QString site;
    QString url;
    qint64 modelId = 0;
    qint64 versionId = 0;

    QString siteLabel() const;
};

struct ModelIntel
{
    bool present = false; // a `<stem>.spellvision.json` existed and parsed
    QString sidecarPath;
    QString schema;

    // --- identity ---
    QString fileName;
    QString sha256;
    QString kind;         // the ten-value tab vocabulary; "other" when undetermined
    QString family;       // "" when undetermined — the real library still writes "unknown" here
    QString baseModel;
    QString quantisation; // nvfp4 / int8 / fp8 / bf16 / fp32 / "" when the pass could not tell
    qint64 size = 0;
    QVector<ModelIntelSource> sources;

    // True when a lookup actually matched something on a site. An identified model with no
    // pictures and no description is still identified, and must not render like one nobody asked
    // about.
    bool identified() const { return present && !sources.isEmpty(); }
    // The first source, or an empty one. The card badges this.
    ModelIntelSource primarySource() const;
};

// `<dir>/<stem>.spellvision.json` for a weight path. Pure string work; touches no disk.
QString modelIntelSidecarPath(const QString &modelPath);

// Read + parse the sidecar beside `modelPath`. A missing or unparseable file yields
// `present == false`, never an error: most of a library has no sidecar until a refresh runs.
ModelIntel readModelIntel(const QString &modelPath);

// The parse alone, so a test can drive a document that is not on disk.
ModelIntel parseModelIntelDocument(const QByteArray &json, const QString &sidecarPath = QString());

} // namespace spellvision::assets
