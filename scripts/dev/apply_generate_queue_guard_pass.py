from __future__ import annotations

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
HEADER = REPO_ROOT / "qt_ui" / "ImageGenerationPage.h"
CPP = REPO_ROOT / "qt_ui" / "ImageGenerationPage.cpp"

METHOD_DECLS = '''    QString generationPayloadFingerprint(const QJsonObject &payload) const;
    bool shouldBlockDuplicateGenerate(const QJsonObject &payload);
    void lockGenerateSubmissionBriefly(const QString &message = QString());
'''

MEMBERS = '''    bool generateSubmitLocked_ = false;
    QString lastGenerateFingerprint_;
    qint64 lastGenerateSubmittedAtMs_ = 0;
'''

METHODS = r'''
QString ImageGenerationPage::generationPayloadFingerprint(const QJsonObject &payload) const
{
    QJsonObject stable;
    const QStringList keys = {
        QStringLiteral("mode"),
        QStringLiteral("model"),
        QStringLiteral("model_display"),
        QStringLiteral("model_family"),
        QStringLiteral("video_family"),
        QStringLiteral("backend_kind"),
        QStringLiteral("stack_kind"),
        QStringLiteral("workflow_profile_path"),
        QStringLiteral("compiled_prompt_path"),
        QStringLiteral("prompt"),
        QStringLiteral("negative_prompt"),
        QStringLiteral("sampler"),
        QStringLiteral("scheduler"),
        QStringLiteral("steps"),
        QStringLiteral("cfg"),
        QStringLiteral("seed"),
        QStringLiteral("width"),
        QStringLiteral("height"),
        QStringLiteral("frames"),
        QStringLiteral("fps"),
        QStringLiteral("video_model_stack"),
        QStringLiteral("model_stack"),
        QStringLiteral("loras"),
    };

    for (const QString &key : keys)
    {
        if (payload.contains(key))
            stable.insert(key, payload.value(key));
    }

    return QString::fromUtf8(QJsonDocument(stable).toJson(QJsonDocument::Compact));
}

bool ImageGenerationPage::shouldBlockDuplicateGenerate(const QJsonObject &payload)
{
    const qint64 now = QDateTime::currentMSecsSinceEpoch();
    const QString fingerprint = generationPayloadFingerprint(payload);

    if (generateSubmitLocked_)
        return true;

    constexpr qint64 duplicateWindowMs = 10000;
    if (!lastGenerateFingerprint_.isEmpty() &&
        lastGenerateFingerprint_ == fingerprint &&
        lastGenerateSubmittedAtMs_ > 0 &&
        now - lastGenerateSubmittedAtMs_ < duplicateWindowMs)
    {
        return true;
    }

    lastGenerateFingerprint_ = fingerprint;
    lastGenerateSubmittedAtMs_ = now;
    return false;
}

void ImageGenerationPage::lockGenerateSubmissionBriefly(const QString &message)
{
    generateSubmitLocked_ = true;
    if (readinessHintLabel_)
    {
        const QString text = message.trimmed().isEmpty()
                                 ? QStringLiteral("Submitting generation request…")
                                 : message.trimmed();
        readinessHintLabel_->setText(text);
        readinessHintLabel_->setToolTip(text);
        readinessHintLabel_->setVisible(true);
    }

    updatePrimaryActionAvailability();

    QTimer::singleShot(1800, this, [this]() {
        generateSubmitLocked_ = false;
        updatePrimaryActionAvailability();
    });
}

'''


def patch_header() -> None:
    text = HEADER.read_text(encoding="utf-8")

    if "generationPayloadFingerprint" not in text:
        marker = "    void applyActionReadinessStyle(QPushButton *button, bool enabled, const QString &tooltip);\n"
        if marker not in text:
            raise SystemExit("Could not find applyActionReadinessStyle declaration in ImageGenerationPage.h")
        text = text.replace(marker, marker + METHOD_DECLS, 1)

    if "generateSubmitLocked_" not in text:
        marker = "    QString busyMessage_;\n"
        if marker not in text:
            raise SystemExit("Could not find busyMessage_ member in ImageGenerationPage.h")
        text = text.replace(marker, marker + "\n" + MEMBERS, 1)

    HEADER.write_text(text, encoding="utf-8")


def patch_cpp() -> None:
    text = CPP.read_text(encoding="utf-8")

    if "generationPayloadFingerprint" not in text:
        marker = "void ImageGenerationPage::applyTheme()"
        if marker not in text:
            raise SystemExit("Could not find applyTheme marker in ImageGenerationPage.cpp")
        text = text.replace(marker, METHODS + marker, 1)

    old_connect = "connect(generateButton_, &QPushButton::clicked, this, [this]() { emit generateRequested(buildRequestPayload()); });"
    new_connect = '''connect(generateButton_, &QPushButton::clicked, this, [this]() {
        const QJsonObject payload = buildRequestPayload();
        if (shouldBlockDuplicateGenerate(payload))
        {
            const QString message = QStringLiteral("Duplicate generate ignored; request is already submitting or was just queued.");
            if (readinessHintLabel_)
            {
                readinessHintLabel_->setText(message);
                readinessHintLabel_->setToolTip(message);
                readinessHintLabel_->setVisible(true);
            }
            return;
        }

        lockGenerateSubmissionBriefly(QStringLiteral("Submitting generation request…"));
        emit generateRequested(payload);
    });'''

    if old_connect in text:
        text = text.replace(old_connect, new_connect, 1)
    elif "shouldBlockDuplicateGenerate(payload)" not in text:
        pattern = re.compile(
            r'connect\(generateButton_,\s*&QPushButton::clicked,\s*this,\s*\[this\]\(\)\s*\{\s*emit\s+generateRequested\(buildRequestPayload\(\)\);\s*\}\);',
            re.DOTALL,
        )
        text, count = pattern.subn(new_connect, text, count=1)
        if count != 1:
            raise SystemExit("Could not patch generate button connection in ImageGenerationPage.cpp")

    if "Submitting generation request" not in text.split("QString ImageGenerationPage::readinessBlockReason() const", 1)[-1].split("void ImageGenerationPage::applyActionReadinessStyle", 1)[0]:
        old = '''    if (busy_)
        return busyMessage_.isEmpty() ? QStringLiteral("Generation in progress.") : busyMessage_;

'''
        new = '''    if (busy_)
        return busyMessage_.isEmpty() ? QStringLiteral("Generation in progress.") : busyMessage_;

    if (generateSubmitLocked_)
        return QStringLiteral("Submitting generation request…");

'''
        if old not in text:
            raise SystemExit("Could not find busy_ readiness block in ImageGenerationPage.cpp")
        text = text.replace(old, new, 1)

    CPP.write_text(text, encoding="utf-8")


def main() -> None:
    patch_header()
    patch_cpp()
    print("Applied Generate Queue Guard pass to ImageGenerationPage.")


if __name__ == "__main__":
    main()
