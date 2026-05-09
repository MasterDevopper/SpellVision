from pathlib import Path
import re

# --------------------------------------------------------------------
# Sprint 15C Pass 29P v4
# Complete preferred-output bridge:
# 1. ImageGenerationPage ltxOutputVariantEdit_ -> draft.ltxOutputVariant
# 2. GenerationRequestBuilder draft.ltxOutputVariant -> backend aliases
# 3. worker_service accepts ltx_output_variant aliases defensively
# --------------------------------------------------------------------

# ----------------------------
# 1. ImageGenerationPage.cpp
# ----------------------------
page_path = Path("qt_ui/ImageGenerationPage.cpp")
page = page_path.read_text(encoding="utf-8")

if "Sprint 15C Pass 29P v4: copy preferred LTX output variant into generation draft" not in page:
    assignment = '''    // Sprint 15C Pass 29P v4: copy preferred LTX output variant into generation draft.
    if (ltxOutputVariantEdit_)
        draft.ltxOutputVariant = ltxOutputVariantEdit_->text().trimmed();
'''

    # Prefer inserting after nearby LTX component draft assignments.
    patterns = [
        r'(\s*draft\.ltxVisionEncoderName\s*=\s*[^;]+;\s*\n)',
        r'(\s*draft\.ltxVideoVaeName\s*=\s*[^;]+;\s*\n)',
        r'(\s*draft\.ltxAudioVaeName\s*=\s*[^;]+;\s*\n)',
        r'(\s*draft\.ltxTextProjectionName\s*=\s*[^;]+;\s*\n)',
    ]

    inserted = False
    for pattern in patterns:
        match = re.search(pattern, page)
        if match:
            page = page[:match.end()] + assignment + page[match.end():]
            inserted = True
            break

    if not inserted:
        raise SystemExit("Could not find an LTX draft assignment insertion point in ImageGenerationPage.cpp.")

page_path.write_text(page, encoding="utf-8")


# ----------------------------
# 2. GenerationRequestBuilder.cpp
# ----------------------------
builder_path = Path("qt_ui/generation/GenerationRequestBuilder.cpp")
builder = builder_path.read_text(encoding="utf-8")

if "QString ltxPreferredOutputRole = ltxOutputVariant.trimmed().toLower();" not in builder:
    needle = '''    const QString ltxOutputVariant = draft.ltxOutputVariant.trimmed().isEmpty()
                                         ? QStringLiteral("distilled")
                                         : draft.ltxOutputVariant.trimmed();

'''
    replacement = '''    const QString ltxOutputVariant = draft.ltxOutputVariant.trimmed().isEmpty()
                                         ? QStringLiteral("distilled")
                                         : draft.ltxOutputVariant.trimmed();

    QString ltxPreferredOutputRole = ltxOutputVariant.trimmed().toLower();
    ltxPreferredOutputRole.replace(QStringLiteral("-"), QStringLiteral("_"));
    ltxPreferredOutputRole.replace(QStringLiteral(" "), QStringLiteral("_"));

    if (ltxPreferredOutputRole == QStringLiteral("d") ||
        ltxPreferredOutputRole == QStringLiteral("output_d") ||
        ltxPreferredOutputRole == QStringLiteral("ltx_distilled") ||
        ltxPreferredOutputRole == QStringLiteral("distilled_output"))
    {
        ltxPreferredOutputRole = QStringLiteral("distilled");
    }
    else if (ltxPreferredOutputRole == QStringLiteral("f") ||
             ltxPreferredOutputRole == QStringLiteral("output_f") ||
             ltxPreferredOutputRole == QStringLiteral("ltx_full") ||
             ltxPreferredOutputRole == QStringLiteral("full_output"))
    {
        ltxPreferredOutputRole = QStringLiteral("full");
    }
    else if (ltxPreferredOutputRole != QStringLiteral("distilled") &&
             ltxPreferredOutputRole != QStringLiteral("full"))
    {
        ltxPreferredOutputRole = QStringLiteral("full");
    }

'''
    if needle not in builder:
        raise SystemExit("Could not find ltxOutputVariant block in GenerationRequestBuilder.cpp.")
    builder = builder.replace(needle, replacement, 1)

if "Sprint 15C Pass 29P v4: send preferred LTX output aliases" not in builder:
    insert_after = '''    payload.insert(QStringLiteral("ltx_text_projection_name"), ltxTextProjectionName);
'''
    insert_block = '''
    // Sprint 15C Pass 29P v4: send preferred LTX output aliases.
    payload.insert(QStringLiteral("ltx_output_variant"), ltxPreferredOutputRole);
    payload.insert(QStringLiteral("ltx_preferred_output"), ltxPreferredOutputRole);
    payload.insert(QStringLiteral("video_preferred_output"), ltxPreferredOutputRole);
    payload.insert(QStringLiteral("video_output_preference"), ltxPreferredOutputRole);
    payload.insert(QStringLiteral("primary_output_role"), ltxPreferredOutputRole);
'''
    if insert_after not in builder:
        raise SystemExit("Could not find ltx_text_projection_name insertion point in GenerationRequestBuilder.cpp.")
    builder = builder.replace(insert_after, insert_after + insert_block, 1)

builder_path.write_text(builder, encoding="utf-8")


# ----------------------------
# 3. worker_service.py
# ----------------------------
worker_path = Path("python/worker_service.py")
worker = worker_path.read_text(encoding="utf-8")

if 'or req.get("ltx_output_variant")' not in worker:
    needle = '''            req.get("ltx_preferred_output")
'''
    replacement = '''            req.get("ltx_preferred_output")
            or req.get("ltx_output_variant")
            or req.get("video_output_variant")
            or req.get("preferred_output_variant")
'''
    if needle not in worker:
        raise SystemExit("Could not find ltx_preferred_output alias block in worker_service.py.")
    worker = worker.replace(needle, replacement, 1)

worker_path.write_text(worker, encoding="utf-8")

print("Applied Sprint 15C Pass 29P v4: completed LTX preferred-output bridge.")
