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

// One entry of `display.images[]`. `localPath` is the file the previews pass downloaded under
// `<models root>/.spellvision/previews/<sha256>/`; `userOverride` marks the picture the USER
// chose, which no refresh may disturb.
struct ModelIntelImage
{
    QString originUrl;
    QString localPath;
    int width = 0;
    int height = 0;
    int nsfwLevel = 0;
    bool isCover = false;
    bool userOverride = false;
};

// One entry of the `recommended` block: a value, where it came from, and how much of the evidence
// agreed. The provenance is the whole point -- "10 steps, from 10 of this model's own example
// images" and "10 steps, because the family table says so" are different claims, and a number
// shown without which one it is invites the user to trust both equally.
struct ModelIntelRecommendation
{
    QString field;
    QString value;      // as text; the inspector prints it, the cockpit parses it
    QString provenance; // user | site:image-meta-mode | site:trainedWords | card:* | table:family-default
    double confidence = 1.0;
    int agreeing = 0;   // `n`   -- 0 when the source is not a vote
    int total = 0;      // `total`

    // The caption under the value, in the user's words rather than the schema's.
    QString caption() const;
    bool isFromThisModel() const;  // the site's own examples, or the user -- not a family floor
};

// The three states the page has to keep apart. Collapsing the last two is what would stop a user
// telling "we asked the site and it does not know this file" from "nothing has ever looked".
enum class ModelIdentification
{
    NeverAsked,       // no sidecar at all
    NothingFound,     // a sidecar, no sources: the lookup ran and matched nothing
    Identified,       // a site knows this hash
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

    // --- display: what the site says, and what the user overrode ---
    QString displayName; // `display.name.value`; the FILE is never renamed
    bool displayNameIsUserOverride = false;
    QString descriptionHtml;
    QString creator;
    QString licenseName;
    int nsfwLevel = -1; // -1 == the sidecar said nothing
    QStringList triggerWords;
    bool triggerWordsAreUserOverride = false;
    QVector<ModelIntelImage> images;

    // --- recommended: what this model asks to be run at ---
    QVector<ModelIntelRecommendation> recommended;
    ModelIntelRecommendation recommendationFor(const QString &field) const;

    // True when a lookup actually matched something on a site. An identified model with no
    // pictures and no description is still identified, and must not render like one nobody asked
    // about.
    bool identified() const { return present && !sources.isEmpty(); }
    // The first source, or an empty one. The card badges this.
    ModelIntelSource primarySource() const;

    ModelIdentification identification() const;
    // The picture the card shows: the user's own if they set one, else the cover the site gave,
    // else the first image. Empty when there is nothing to show.
    ModelIntelImage coverImage() const;
    QString coverPath() const { return coverImage().localPath; }
};

// The caption under an un-identified card. Two different absences, two different sentences.
QString identificationCaption(ModelIdentification state);

// The highest `nsfw_level` a preview may carry before the page blurs it. From QSettings
// (`models/nsfwPreviewLevel`), defaulting to 2 -- the same ceiling
// `model_intelligence.previews.download_previews` fetches at, so the default setting never blurs
// a picture the refresh was willing to download.
// `description_html` with its tags removed and its whitespace collapsed. The sidecar carries the
// site's HTML verbatim; a QLabel would render a subset of it and swallow the rest.
QString plainTextFromHtml(const QString &html);

int nsfwPreviewCeiling();
bool previewShouldBlur(int imageNsfwLevel, int ceiling);

// `<dir>/<stem>.spellvision.json` for a weight path. Pure string work; touches no disk.
QString modelIntelSidecarPath(const QString &modelPath);

// Read + parse the sidecar beside `modelPath`. A missing or unparseable file yields
// `present == false`, never an error: most of a library has no sidecar until a refresh runs.
ModelIntel readModelIntel(const QString &modelPath);

// The parse alone, so a test can drive a document that is not on disk.
ModelIntel parseModelIntelDocument(const QByteArray &json, const QString &sidecarPath = QString());

} // namespace spellvision::assets
