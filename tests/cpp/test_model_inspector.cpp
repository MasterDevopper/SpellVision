// W5 Task 3 -- the inspector, and the user's own picture.
//
// The details card showed a text block, ONE example image and a truncated description. The sidecar
// has carried six pictures, the site's own description, the licence and a per-field `recommended`
// block with a PROVENANCE on every value since the intelligence pass ran, and none of it reached
// the page.
//
// Provenance is the part that is not decoration. The owner's house checkpoint publishes 10 steps
// unanimously across ten example images while `family_operating_points` says 52, and the app
// rendered it at 52 for months. A number shown with no source invites the user to trust both
// equally; "from 10 of 10 example images on the site" and "a family default, not this model" are
// different claims and the inspector says which one it is holding.
//
// The promise most likely to be quietly broken by a later change is the user's own picture
// surviving a refresh, so it is asserted from both ends. THIS file asserts the selection: a
// sidecar carrying a user-overridden image resolves to that image as the cover, ahead of whatever
// the site published, and still does after a refresh has rewritten the rest of the document.
// `tests/test_model_intel_user_picture.py` asserts the other end through the real RefreshJob --
// that the merge keeps the entry AND that the bytes at the path it names are still the user's.
//
// No socket. The panel builds requests and consumes replies; these cases play the worker.

#include <QtTest>

#include <QDir>
#include <QFile>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QSet>
#include <QSignalSpy>
#include <QTemporaryDir>

#include "AppEnvironment.h"
#include "assets/ModelInspectorPanel.h"
#include "assets/ModelIntelSidecar.h"
#include "shell/ProjectRoot.h"

using spellvision::assets::ModelIdentification;
using spellvision::assets::ModelInspectorPanel;
using spellvision::assets::ModelIntel;
using spellvision::assets::ModelIntelRecommendation;

namespace
{

QString fixtureText(const QString &stem)
{
    const QString path = QDir(QDir(spellvision::shell::resolveProjectRoot())
                                  .filePath(QStringLiteral("tests/fixtures/model_library")))
                             .filePath(stem + QStringLiteral(".spellvision.json"));
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return QString();
    return QString::fromUtf8(file.readAll());
}

// Lay a real sidecar down beside a real (empty) weight in a temp dir, rewriting every
// `local_path` so the gallery points at pictures that exist here. The sidecar's SHAPE stays what
// the live library produced; only the drive letters move.
struct Library
{
    QTemporaryDir dir;
    QString weight;
    QString sidecar;
    QStringList pictures;
    QString userPicture;
};

void writeImage(const QString &path, const QColor &colour)
{
    QDir().mkpath(QFileInfo(path).absolutePath());
    QImage image(24, 24, QImage::Format_RGB32);
    image.fill(colour);
    QVERIFY2(image.save(path), qPrintable(path));
}

bool layDown(Library &library, const QString &stem, const QString &weightName)
{
    if (!library.dir.isValid())
        return false;
    const QString root = library.dir.path();
    library.weight = QDir(root).filePath(weightName);
    QFile weightFile(library.weight);
    if (!weightFile.open(QIODevice::WriteOnly))
        return false;
    weightFile.write("not a real weight");
    weightFile.close();

    QJsonObject payload = QJsonDocument::fromJson(fixtureText(stem).toUtf8()).object();
    if (payload.isEmpty())
        return false;

    QJsonObject display = payload.value(QStringLiteral("display")).toObject();
    QJsonArray images = display.value(QStringLiteral("images")).toArray();
    QJsonArray rewritten;
    for (int index = 0; index < images.size(); ++index)
    {
        QJsonObject image = images.at(index).toObject();
        const QString local = QDir(root).filePath(QStringLiteral("previews/%1.jpg").arg(index));
        writeImage(local, QColor::fromHsv((index * 47) % 360, 200, 200));
        image.insert(QStringLiteral("local_path"), local);
        library.pictures << local;
        rewritten.append(image);
    }
    display.insert(QStringLiteral("images"), rewritten);
    payload.insert(QStringLiteral("display"), display);

    library.sidecar = spellvision::assets::modelIntelSidecarPath(library.weight);
    QFile sidecarFile(library.sidecar);
    if (!sidecarFile.open(QIODevice::WriteOnly))
        return false;
    sidecarFile.write(QJsonDocument(payload).toJson());
    sidecarFile.close();

    library.userPicture = QDir(root).filePath(QStringLiteral("my_own_shot.png"));
    writeImage(library.userPicture, QColor(Qt::magenta));
    return true;
}

// What `model_intel_set_user` writes: the user's picture first, marked, and the site's gallery
// behind it with their cover flags cleared. Written here so the "survives a refresh" case can
// re-run a refresh over it.
void markUserCover(const Library &library)
{
    QFile file(library.sidecar);
    QVERIFY(file.open(QIODevice::ReadOnly));
    QJsonObject payload = QJsonDocument::fromJson(file.readAll()).object();
    file.close();

    QJsonObject display = payload.value(QStringLiteral("display")).toObject();
    QJsonArray kept;
    QJsonObject mine;
    mine.insert(QStringLiteral("origin_url"), QString());
    mine.insert(QStringLiteral("local_path"), library.userPicture);
    mine.insert(QStringLiteral("nsfw_level"), 0);
    mine.insert(QStringLiteral("is_cover"), true);
    mine.insert(QStringLiteral("user_override"), true);
    kept.append(mine);
    for (const QJsonValue &value : display.value(QStringLiteral("images")).toArray())
    {
        QJsonObject image = value.toObject();
        image.insert(QStringLiteral("is_cover"), false);
        kept.append(image);
    }
    display.insert(QStringLiteral("images"), kept);
    payload.insert(QStringLiteral("display"), display);

    QFile out(library.sidecar);
    QVERIFY(out.open(QIODevice::WriteOnly));
    out.write(QJsonDocument(payload).toJson());
}

} // namespace

class TestModelInspector : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void the_gallery_renders_every_picture_the_sidecar_names();
    void a_picture_the_sidecar_names_but_disk_does_not_have_is_not_a_blank_tile();
    void trigger_words_and_the_licence_line_come_from_the_sidecar();
    void provenance_captions_name_their_source();
    void a_model_with_no_recommended_block_says_so_rather_than_inventing_one();
    void the_family_default_is_never_dressed_up_as_this_models_own_number();
    void a_user_picture_replaces_the_cover();
    void a_user_picture_survives_a_refresh();
    void the_set_user_request_carries_the_model_roots();
    void a_picture_outside_the_roots_is_refused_out_loud();
    void the_headline_is_the_site_name_and_the_subtitle_is_the_file();
    void the_description_is_html_stripped_and_expandable();
};

void TestModelInspector::initTestCase()
{
    spellvision::testenv::applyShippedAppEnvironment();
}

void TestModelInspector::the_gallery_renders_every_picture_the_sidecar_names()
{
    Library library;
    QVERIFY(layDown(library, QStringLiteral("Detailer-KREA2"), QStringLiteral("Detailer-KREA2.safetensors")));
    QCOMPARE(library.pictures.size(), 6);

    ModelInspectorPanel panel;
    panel.showModel(library.weight, QStringLiteral("Detailer-KREA2.safetensors"));
    QCOMPARE(panel.galleryCount(), 6);
    for (int index = 0; index < 6; ++index)
        QCOMPARE(panel.galleryImageAt(index), library.pictures.at(index));

    // A model the site knows nothing about has no gallery, and the strip stays out of the way.
    Library bare;
    QVERIFY(layDown(bare, QStringLiteral("sd3.5_medium_incl_clips_t5xxlfp8scaled"),
                    QStringLiteral("sd3.5_medium.safetensors")));
    ModelInspectorPanel empty;
    empty.showModel(bare.weight, QStringLiteral("sd3.5_medium.safetensors"));
    QCOMPARE(empty.galleryCount(), 0);
}

void TestModelInspector::a_picture_the_sidecar_names_but_disk_does_not_have_is_not_a_blank_tile()
{
    Library library;
    QVERIFY(layDown(library, QStringLiteral("krea2DepthControlnet_v10"),
                    QStringLiteral("krea2DepthControlnet_v10.safetensors")));
    QVERIFY(library.pictures.size() >= 3);
    // A previews folder the user moved, or a refresh killed halfway.
    QVERIFY(QFile::remove(library.pictures.at(1)));

    ModelInspectorPanel panel;
    panel.showModel(library.weight, QStringLiteral("krea2DepthControlnet_v10.safetensors"));
    QCOMPARE(panel.galleryCount(), library.pictures.size() - 1);
    QVERIFY(panel.galleryImageAt(1).isEmpty());
}

void TestModelInspector::trigger_words_and_the_licence_line_come_from_the_sidecar()
{
    Library library;
    QVERIFY(layDown(library, QStringLiteral("krea2_darkbrush"), QStringLiteral("krea2_darkbrush.safetensors")));

    ModelInspectorPanel panel;
    panel.showModel(library.weight, QStringLiteral("krea2_darkbrush.safetensors"));
    QCOMPARE(panel.triggerWords(), QStringList{QStringLiteral("monochrome ink wash style")});

    // This library's CivitAI answers carry no licence name. "Not stated by the site" and
    // "unknown -- not identified" are different facts, and for a library that may ship
    // commercially the difference is the whole question.
    QCOMPARE(panel.licenceText(), QStringLiteral("Licence: not stated by the site"));

    Library bare;
    QVERIFY(layDown(bare, QStringLiteral("sd3.5_medium_incl_clips_t5xxlfp8scaled"),
                    QStringLiteral("sd3.5_medium.safetensors")));
    ModelInspectorPanel unknown;
    unknown.showModel(bare.weight, QStringLiteral("sd3.5_medium.safetensors"));
    QVERIFY2(unknown.licenceText().contains(QStringLiteral("not been identified")),
             qPrintable(unknown.licenceText()));
    QVERIFY(unknown.licenceText() != panel.licenceText());
}

void TestModelInspector::provenance_captions_name_their_source()
{
    // The owner's house checkpoint. Ten of ten example images agree on 10 steps and CFG 1; the
    // canvas size is a family default. Both numbers appear, and they do NOT read the same.
    Library library;
    QVERIFY(layDown(library, QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4"),
                    QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4.safetensors")));

    ModelInspectorPanel panel;
    panel.showModel(library.weight, QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4.safetensors"));

    const QStringList lines = panel.recommendedLines();
    QVERIFY(!lines.isEmpty());

    const QString steps = lines.value(0);
    QVERIFY2(steps.startsWith(QStringLiteral("Steps: 10")), qPrintable(steps));
    QVERIFY2(steps.contains(QStringLiteral("from 10 of 10 example images on the site")), qPrintable(steps));

    QString width;
    for (const QString &line : lines)
    {
        if (line.startsWith(QStringLiteral("Width")))
            width = line;
    }
    QVERIFY2(!width.isEmpty(), qPrintable(lines.join(QLatin1Char('|'))));
    QVERIFY2(width.contains(QStringLiteral("a family default, not this model")), qPrintable(width));

    // The rendered captions, straight off the entries.
    const ModelIntel &intel = panel.intel();
    QCOMPARE(intel.recommendationFor(QStringLiteral("steps")).value, QStringLiteral("10"));
    QCOMPARE(intel.recommendationFor(QStringLiteral("cfg")).value, QStringLiteral("1"));
    QVERIFY(intel.recommendationFor(QStringLiteral("steps")).isFromThisModel());
    QVERIFY(!intel.recommendationFor(QStringLiteral("width")).isFromThisModel());

    // A trigger-word prefix is a third provenance, and it says so in its own words.
    Library lora;
    QVERIFY(layDown(lora, QStringLiteral("krea2_darkbrush"), QStringLiteral("krea2_darkbrush.safetensors")));
    ModelInspectorPanel loraPanel;
    loraPanel.showModel(lora.weight, QStringLiteral("krea2_darkbrush.safetensors"));
    QVERIFY2(loraPanel.recommendedLines().join(QLatin1Char('|'))
                 .contains(QStringLiteral("the trigger words the site lists")),
             qPrintable(loraPanel.recommendedLines().join(QLatin1Char('|'))));
}

void TestModelInspector::a_model_with_no_recommended_block_says_so_rather_than_inventing_one()
{
    Library library;
    QVERIFY(layDown(library, QStringLiteral("sd3.5_medium_incl_clips_t5xxlfp8scaled"),
                    QStringLiteral("sd3.5_medium.safetensors")));

    ModelInspectorPanel panel;
    panel.showModel(library.weight, QStringLiteral("sd3.5_medium.safetensors"));

    // This sidecar DOES carry a block -- entirely family defaults, because CivitAI does not know
    // the file. Every line says so, and none of them claims to be this model's own answer.
    const QStringList lines = panel.recommendedLines();
    QVERIFY(!lines.isEmpty());
    for (const QString &line : lines)
    {
        QVERIFY2(line.contains(QStringLiteral("a family default, not this model")), qPrintable(line));
    }
    for (const ModelIntelRecommendation &entry : panel.intel().recommended)
        QVERIFY2(!entry.isFromThisModel(), qPrintable(entry.field));
}

void TestModelInspector::the_family_default_is_never_dressed_up_as_this_models_own_number()
{
    ModelIntelRecommendation site;
    site.field = QStringLiteral("steps");
    site.provenance = QStringLiteral("site:image-meta-mode");
    site.agreeing = 10;
    site.total = 10;

    ModelIntelRecommendation weak = site;
    weak.provenance = QStringLiteral("site:image-meta-weak");
    weak.agreeing = 1;
    weak.total = 4;

    ModelIntelRecommendation table = site;
    table.provenance = QStringLiteral("table:family-default");
    table.agreeing = 0;
    table.total = 0;

    ModelIntelRecommendation mine = site;
    mine.provenance = QStringLiteral("user");

    QCOMPARE(site.caption(), QStringLiteral("from 10 of 10 example images on the site"));
    QCOMPARE(weak.caption(), QStringLiteral("from only 1 of 4 example images"));
    QCOMPARE(table.caption(), QStringLiteral("a family default, not this model"));
    QCOMPARE(mine.caption(), QStringLiteral("you set this"));

    // Four sources, four sentences. No two of them read alike, which is the only reason the
    // caption is worth printing.
    const QStringList captions{site.caption(), weak.caption(), table.caption(), mine.caption()};
    QCOMPARE(QSet<QString>(captions.cbegin(), captions.cend()).size(), 4);

    QVERIFY(site.isFromThisModel());
    QVERIFY(weak.isFromThisModel());
    QVERIFY(mine.isFromThisModel());
    QVERIFY(!table.isFromThisModel());
}

void TestModelInspector::a_user_picture_replaces_the_cover()
{
    Library library;
    QVERIFY(layDown(library, QStringLiteral("Detailer-KREA2"), QStringLiteral("Detailer-KREA2.safetensors")));

    ModelInspectorPanel panel;
    panel.showModel(library.weight, QStringLiteral("Detailer-KREA2.safetensors"));
    // Before: the site's own cover.
    QCOMPARE(panel.coverPath(), library.pictures.at(0));

    markUserCover(library);
    panel.applyWorkerReply(QJsonObject{
        {QStringLiteral("type"), QStringLiteral("model_intel_set_user")},
        {QStringLiteral("ok"), true},
        {QStringLiteral("changed"), QJsonArray{QStringLiteral("picture")}}});

    QCOMPARE(panel.coverPath(), library.userPicture);
    QVERIFY2(panel.statusText().contains(QStringLiteral("cover")), qPrintable(panel.statusText()));
    // The site's pictures are still in the gallery, behind the user's -- the strip holds six, the
    // same ceiling `download_previews` fetches at.
    QCOMPARE(panel.galleryCount(), 6);
    QCOMPARE(panel.galleryImageAt(0), library.userPicture);
    QCOMPARE(panel.galleryImageAt(1), library.pictures.at(0));
}

void TestModelInspector::a_user_picture_survives_a_refresh()
{
    Library library;
    QVERIFY(layDown(library, QStringLiteral("Detailer-KREA2"), QStringLiteral("Detailer-KREA2.safetensors")));
    markUserCover(library);

    ModelInspectorPanel panel;
    panel.showModel(library.weight, QStringLiteral("Detailer-KREA2.safetensors"));
    QCOMPARE(panel.coverPath(), library.userPicture);

    // A refresh runs and the site has published NEW pictures.
    //
    // The refreshed document is written in the SHAPE A REFRESH PRODUCES, not in the shape that
    // would make this case easy: the site's fresh picture comes first and carries `is_cover`,
    // because that is what `build_payload` writes for a freshly downloaded gallery, and the only
    // thing still distinguishing the user's entry is `user_override`. A cover resolver that reads
    // `is_cover` and stops -- which is what every obvious implementation does -- hands back the
    // site's picture here and the user's choice is gone without a word.
    const QString fresh = QDir(library.dir.path()).filePath(QStringLiteral("previews/fresh.jpg"));
    {
        QFile file(library.sidecar);
        QVERIFY(file.open(QIODevice::ReadOnly));
        QJsonObject payload = QJsonDocument::fromJson(file.readAll()).object();
        file.close();

        QJsonObject display = payload.value(QStringLiteral("display")).toObject();
        const QJsonArray before = display.value(QStringLiteral("images")).toArray();
        QJsonObject mine = before.at(0).toObject();
        QVERIFY(mine.value(QStringLiteral("user_override")).toBool());
        mine.insert(QStringLiteral("is_cover"), false);

        writeImage(fresh, QColor(Qt::darkGreen));
        QJsonArray after;
        after.append(QJsonObject{{QStringLiteral("origin_url"), QStringLiteral("https://image.civitai.example/new.jpeg")},
                                 {QStringLiteral("local_path"), fresh},
                                 {QStringLiteral("nsfw_level"), 1},
                                 {QStringLiteral("is_cover"), true},
                                 {QStringLiteral("user_override"), false}});
        after.append(mine);
        display.insert(QStringLiteral("images"), after);
        // And the site renamed the model while it was at it.
        display.insert(QStringLiteral("name"), QJsonObject{
            {QStringLiteral("value"), QStringLiteral("[KREA 2] Detail Slider v1.1")},
            {QStringLiteral("user_override"), false}});
        payload.insert(QStringLiteral("display"), display);

        QFile out(library.sidecar);
        QVERIFY(out.open(QIODevice::WriteOnly));
        out.write(QJsonDocument(payload).toJson());
    }

    panel.applyWorkerReply(QJsonObject{
        {QStringLiteral("type"), QStringLiteral("model_intel_refresh")},
        {QStringLiteral("ok"), true}});

    // The refresh landed -- the headline moved, and the site's new picture is in the gallery...
    QCOMPARE(panel.headlineText(), QStringLiteral("[KREA 2] Detail Slider v1.1"));
    QCOMPARE(panel.galleryCount(), 2);
    QCOMPARE(panel.galleryImageAt(0), fresh);
    // ...and the user's picture is STILL the cover, although the fresh one is the entry the
    // document marks as cover and sits first in the list.
    QCOMPARE(panel.coverPath(), library.userPicture);
    QCOMPARE(panel.intel().coverImage().userOverride, true);
    QCOMPARE(panel.intel().coverImage().isCover, false);
}

void TestModelInspector::the_set_user_request_carries_the_model_roots()
{
    Library library;
    QVERIFY(layDown(library, QStringLiteral("Detailer-KREA2"), QStringLiteral("Detailer-KREA2.safetensors")));

    ModelInspectorPanel panel;
    panel.setModelRoots({library.dir.path()});
    panel.showModel(library.weight, QStringLiteral("Detailer-KREA2.safetensors"));

    QSignalSpy spy(&panel, &ModelInspectorPanel::workerRequested);
    panel.requestUserPicture(library.userPicture);
    QCOMPARE(spy.count(), 1);

    const QJsonObject request = spy.at(0).at(0).toJsonObject();
    QCOMPARE(request.value(QStringLiteral("command")).toString(), QStringLiteral("model_intel_set_user"));
    QCOMPARE(request.value(QStringLiteral("path")).toString(), library.weight);
    QCOMPARE(request.value(QStringLiteral("picture")).toString(), library.userPicture);
    // Without `roots` the worker performs NO location check -- it documents that honestly, and
    // closing the gap is this caller's job. A request that forgets them is not safer, it is
    // unchecked.
    const QJsonArray roots = request.value(QStringLiteral("roots")).toArray();
    QCOMPARE(roots.size(), 1);
    QCOMPARE(roots.at(0).toString(), library.dir.path());
}

void TestModelInspector::a_picture_outside_the_roots_is_refused_out_loud()
{
    Library library;
    QVERIFY(layDown(library, QStringLiteral("Detailer-KREA2"), QStringLiteral("Detailer-KREA2.safetensors")));

    ModelInspectorPanel panel;
    panel.setModelRoots({library.dir.path()});
    panel.showModel(library.weight, QStringLiteral("Detailer-KREA2.safetensors"));
    const QString coverBefore = panel.coverPath();

    panel.requestUserPicture(QStringLiteral("C:/Windows/System32/config/SAM"));
    // The worker's answer, verbatim.
    panel.applyWorkerReply(QJsonObject{
        {QStringLiteral("type"), QStringLiteral("model_intel_set_user")},
        {QStringLiteral("ok"), false},
        {QStringLiteral("error"), QStringLiteral("picture is outside the model roots named by this request")}});

    // The refusal is on screen. Silence here would leave the cover unchanged with no reason
    // given, which reads as a broken button rather than as a rule.
    QCOMPARE(panel.statusText(), QStringLiteral("picture is outside the model roots named by this request"));
    QCOMPARE(panel.coverPath(), coverBefore);

    // A worker that never answered is also said out loud, and is not mistaken for a refusal.
    panel.applyWorkerReply(QJsonObject{
        {QStringLiteral("type"), QStringLiteral("model_intel_set_user")},
        {QStringLiteral("ok"), false}});
    QVERIFY(!panel.statusText().isEmpty());
}

void TestModelInspector::the_headline_is_the_site_name_and_the_subtitle_is_the_file()
{
    Library library;
    QVERIFY(layDown(library, QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4"),
                    QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4.safetensors")));

    ModelInspectorPanel panel;
    panel.showModel(library.weight, QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4.safetensors"));

    QVERIFY2(panel.headlineText().startsWith(QStringLiteral("Lox")), qPrintable(panel.headlineText()));
    QVERIFY(!panel.headlineText().contains(QStringLiteral("safetensors")));

    // The weight on disk still has its name: the rename is a display, not a move.
    QVERIFY(QFileInfo::exists(library.weight));
    QCOMPARE(QFileInfo(library.weight).fileName(),
             QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4.safetensors"));

    // A weight with no sidecar falls back to the filename rather than to nothing.
    QTemporaryDir bare;
    QVERIFY(bare.isValid());
    const QString lonely = QDir(bare.path()).filePath(QStringLiteral("nobody_looked.safetensors"));
    QFile file(lonely);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.close();
    ModelInspectorPanel empty;
    empty.showModel(lonely, QStringLiteral("nobody_looked.safetensors"));
    QCOMPARE(empty.headlineText(), QStringLiteral("nobody_looked.safetensors"));
    QVERIFY(!empty.canOpenOnSite());
}

void TestModelInspector::the_description_is_html_stripped_and_expandable()
{
    QCOMPARE(spellvision::assets::plainTextFromHtml(QStringLiteral("<p>Check BF16 Changelog</p>")),
             QStringLiteral("Check BF16 Changelog"));
    QCOMPARE(spellvision::assets::plainTextFromHtml(
                 QStringLiteral("<p>one</p><p>two</p><br/><b>three</b>")),
             QStringLiteral("one two three"));
    QCOMPARE(spellvision::assets::plainTextFromHtml(QStringLiteral("Tom &amp; Jerry &lt;3")),
             QStringLiteral("Tom & Jerry <3"));

    Library library;
    QVERIFY(layDown(library, QStringLiteral("loxsUtopicWorldKrea2_v20Quants_nvfp4"),
                    QStringLiteral("lox.safetensors")));
    ModelInspectorPanel panel;
    panel.showModel(library.weight, QStringLiteral("lox.safetensors"));
    QCOMPARE(panel.descriptionText(), QStringLiteral("Check BF16 Changelog"));
    QVERIFY(!panel.descriptionText().contains(QLatin1Char('<')));
}

QTEST_MAIN(TestModelInspector)
#include "test_model_inspector.moc"
