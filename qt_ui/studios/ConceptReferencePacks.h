#pragma once

// Concept-reference prompt packs for multi-view / image-to-3D adherence.
// Shared by ConceptReferencePage and Character Studio concept stages.
// Goal: lighting, background, and angle discipline that multi-view models accept.

#include <QString>
#include <QStringList>

namespace spellvision::studios
{

enum class ConceptAssetType {
    CharacterBody = 0,
    Clothing,
    Building,
    Prop,
};

enum class ConceptContentMode {
    Sfw = 0,  // Anatomically correct form WITHOUT genitals (game-safe body)
    Nsfw,     // Allow full anatomical detail when requested
};

enum class ConceptViewMode {
    HeroFront = 0,   // Single locked hero orthographic front
    TurnaroundSheet, // Multi-angle sheet in one image
    AngleFront,
    AngleBack,
    AngleLeft,
    AngleRight,
    AngleThreeQuarter,
};

struct ConceptPromptPack {
    QString positiveScaffold; // always-on adherence scaffold (appended after user subject)
    QString negativeScaffold; // always-on negatives
    QString subjectHint;      // placeholder / tip for the subject field
    QString checklistHtml;    // short readiness bullets for the UI
};

inline QString conceptAssetTypeId(ConceptAssetType t)
{
    switch (t) {
    case ConceptAssetType::CharacterBody: return QStringLiteral("character_body");
    case ConceptAssetType::Clothing: return QStringLiteral("clothing");
    case ConceptAssetType::Building: return QStringLiteral("building");
    case ConceptAssetType::Prop: return QStringLiteral("prop");
    }
    return QStringLiteral("character_body");
}

inline QString conceptAssetTypeLabel(ConceptAssetType t)
{
    switch (t) {
    case ConceptAssetType::CharacterBody: return QStringLiteral("Character body");
    case ConceptAssetType::Clothing: return QStringLiteral("Clothing");
    case ConceptAssetType::Building: return QStringLiteral("Building");
    case ConceptAssetType::Prop: return QStringLiteral("Prop");
    }
    return QStringLiteral("Character body");
}

inline QString conceptViewModeLabel(ConceptViewMode v)
{
    switch (v) {
    case ConceptViewMode::HeroFront: return QStringLiteral("Hero front (lock)");
    case ConceptViewMode::TurnaroundSheet: return QStringLiteral("Turnaround sheet");
    case ConceptViewMode::AngleFront: return QStringLiteral("Angle · front");
    case ConceptViewMode::AngleBack: return QStringLiteral("Angle · back");
    case ConceptViewMode::AngleLeft: return QStringLiteral("Angle · left");
    case ConceptViewMode::AngleRight: return QStringLiteral("Angle · right");
    case ConceptViewMode::AngleThreeQuarter: return QStringLiteral("Angle · 3/4");
    }
    return QStringLiteral("Hero front");
}

// Shared multi-view adherence core (all asset types).
inline QString multiViewLightingScaffold()
{
    return QStringLiteral(
        "even soft studio lighting, no harsh shadows, no rim-light drama, "
        "neutral three-point balanced fill, high clarity, sharp silhouette");
}

inline QString multiViewBackgroundScaffold()
{
    return QStringLiteral(
        "pure seamless solid light-gray studio background, empty void behind subject, "
        "no ground plane texture, no environment props, no gradient backdrop art");
}

inline QString multiViewNegativeCore()
{
    return QStringLiteral(
        "busy background, cluttered scene, environment, landscape, room interior, "
        "text, watermark, logo, UI, border, frame, collage of different characters, "
        "inconsistent design, different outfits across views, color shift between views, "
        "dramatic cinematic lighting, hard shadows, bloom, lens flare, depth of field bokeh, "
        "motion blur, lowres, blurry, jpeg artifacts, cropped limbs, cut off head, "
        "extra limbs, deformed hands, bad anatomy, duplicate subject, crowd");
}

inline QString contentModePositive(ConceptContentMode mode, ConceptAssetType asset)
{
    if (asset != ConceptAssetType::CharacterBody)
        return {};

    if (mode == ConceptContentMode::Sfw) {
        // Anatomically correct massing for meshers, without genitals / explicit anatomy.
        // Avoid "smooth genital region" phrasing that pushes models into body-suits.
        return QStringLiteral(
            "anatomically correct humanoid proportions, clean game-character body, "
            "bare skin with simplified non-detailed crotch (no genitals), "
            "non-sexualized anatomy, tasteful SFW body, natural torso massing suitable for clothing fit, "
            "not wearing a full-body suit");
    }
    return QStringLiteral(
        "anatomically correct detailed body, accurate pelvic anatomy when visible, "
        "full anatomical fidelity for adult character reference");
}

inline QString contentModeNegative(ConceptContentMode mode, ConceptAssetType asset)
{
    if (asset != ConceptAssetType::CharacterBody)
        return {};

    if (mode == ConceptContentMode::Sfw) {
        return QStringLiteral(
            "nude genitals, penis, vagina, genitalia, pubic hair, explicit nudity, "
            "sexual pose, pornographic, NSFW, erotic, lingerie focus, nipple detail, "
            "bodysuit, catsuit, unitard, zentai, full body suit, latex suit");
    }
    // NSFW still rejects junk that breaks multi-view.
    return QStringLiteral(
        "censored bars, mosaic censor, pixelation, cartoonish Barbie crotch when detail requested");
}

inline QString viewAngleScaffold(ConceptViewMode view)
{
    switch (view) {
    case ConceptViewMode::HeroFront:
        return QStringLiteral(
            "single subject, orthographic front view, upright A-pose or relaxed T-pose, "
            "full body in frame with small margin, centered, facing camera, locked hero reference");
    case ConceptViewMode::TurnaroundSheet:
        return QStringLiteral(
            "character design turnaround sheet, multiple consistent orthographic views of THE SAME subject, "
            "front view, back view, left profile, right profile, optional 3/4, "
            "identical design clothing and proportions across every panel, "
            "even spacing, clean model sheet layout, no story poses");
    case ConceptViewMode::AngleFront:
        return QStringLiteral(
            "orthographic front view only, same identity as locked hero, upright, full body, centered");
    case ConceptViewMode::AngleBack:
        return QStringLiteral(
            "orthographic back view only, same identity as locked hero, upright, full body, "
            "show rear silhouette and rear clothing/hair accurately, no invented details");
    case ConceptViewMode::AngleLeft:
        return QStringLiteral(
            "orthographic left profile view only, same identity as locked hero, upright, full body, true side silhouette");
    case ConceptViewMode::AngleRight:
        return QStringLiteral(
            "orthographic right profile view only, same identity as locked hero, upright, full body, true side silhouette");
    case ConceptViewMode::AngleThreeQuarter:
        return QStringLiteral(
            "clean three-quarter view, same identity as locked hero, upright, full body, "
            "readable form for mesh generation, no extreme perspective");
    }
    return {};
}

inline ConceptPromptPack buildConceptPromptPack(ConceptAssetType asset,
                                                ConceptContentMode content,
                                                ConceptViewMode view)
{
    ConceptPromptPack pack;

    QString assetPos;
    QString assetNeg;
    QString hint;

    switch (asset) {
    case ConceptAssetType::CharacterBody:
        assetPos = QStringLiteral(
            "single full-body character concept, isolated figure, bare skin or simple undergarments only, "
            "NO bodysuit, NO catsuit, NO full-coverage unitard, NO latex suit, NO armor skin, "
            "clear limb separation, readable silhouette, game-ready concept art");
        assetNeg = QStringLiteral(
            "bodysuit, catsuit, unitard, full body suit, spandex suit, latex suit, zentai, "
            "skintight full coverage suit, outfit focus, heavy armor covering form, cape covering legs, "
            "seated pose, action pose, weapon held in front of body, group shot, portrait crop");
        hint = QStringLiteral("e.g. tall elf ranger, short stocky dwarf smith, athletic android…");
        break;
    case ConceptAssetType::Clothing:
        assetPos = QStringLiteral(
            "clean garment product sheet, clothing item only, no mannequin head preferred, "
            "flat or ghost mannequin display, isolated apparel, game asset clothing concept, "
            "clear seams and material read, orthographic friendly");
        assetNeg = QStringLiteral(
            "person face, full character portrait, busy fashion runway, multiple outfits, "
            "wrinkled pile of clothes, hanger clutter, store interior");
        hint = QStringLiteral("e.g. weathered leather longcoat, plate pauldrons set, silk kimono…");
        break;
    case ConceptAssetType::Building:
        assetPos = QStringLiteral(
            "single architectural structure concept, isolated building, clear massing, "
            "readable roofline and openings, game environment kitbash-friendly, "
            "orthographic or slight isometric, no interior clutter cutaway unless requested");
        assetNeg = QStringLiteral(
            "city skyline, multiple buildings, people, vehicles, foggy atmosphere plate, "
            "matte painting landscape, extreme wide establishing shot");
        hint = QStringLiteral("e.g. timber fantasy tavern, modular sci-fi hangar bay…");
        break;
    case ConceptAssetType::Prop:
        assetPos = QStringLiteral(
            "single prop / weapon / tool product concept, object only, centered, "
            "clear silhouette, game item sheet, orthographic friendly, high material readability");
        assetNeg = QStringLiteral(
            "hand holding object, character wielding, environment scene, multiple items, "
            "inventory UI grid, text labels");
        hint = QStringLiteral("e.g. ornate longsword, wooden crate, brass lantern…");
        break;
    }

    const QString contentPos = contentModePositive(content, asset);
    const QString contentNeg = contentModeNegative(content, asset);
    const QString viewPos = viewAngleScaffold(view);

    QStringList posParts;
    posParts << assetPos << multiViewLightingScaffold() << multiViewBackgroundScaffold() << viewPos;
    if (!contentPos.isEmpty())
        posParts << contentPos;

    QStringList negParts;
    negParts << multiViewNegativeCore() << assetNeg;
    if (!contentNeg.isEmpty())
        negParts << contentNeg;

    pack.positiveScaffold = posParts.join(QStringLiteral(", "));
    pack.negativeScaffold = negParts.join(QStringLiteral(", "));
    pack.subjectHint = hint;
    pack.checklistHtml = QStringLiteral(
        "<b>Multi-view readiness</b><ul>"
        "<li>Even studio light — no dramatic rim/cinematic contrast</li>"
        "<li>Solid empty background — never a room or landscape</li>"
        "<li>One subject identity locked across every angle</li>"
        "<li>Upright pose; avoid action crouches that hide the silhouette</li>"
        "<li>Full subject in frame with margin (no crops)</li>"
        "</ul>");

    return pack;
}

inline QString composeConceptPositivePrompt(const QString &userSubject,
                                            const ConceptPromptPack &pack)
{
    const QString subject = userSubject.trimmed();
    if (subject.isEmpty())
        return pack.positiveScaffold;
    return subject + QStringLiteral(", ") + pack.positiveScaffold;
}

inline int conceptDefaultWidth(ConceptViewMode view)
{
    return view == ConceptViewMode::TurnaroundSheet ? 1216 : 896;
}

inline int conceptDefaultHeight(ConceptViewMode view)
{
    return view == ConceptViewMode::TurnaroundSheet ? 832 : 1152;
}

} // namespace spellvision::studios
