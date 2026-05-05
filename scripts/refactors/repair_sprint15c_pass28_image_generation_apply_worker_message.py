from pathlib import Path

path = Path("qt_ui/ImageGenerationPage.cpp")
text = path.read_text(encoding="utf-8")

start_sig = "void ImageGenerationPage::applyWorkerMessage(const QJsonObject &payload)"
next_sig = "void ImageGenerationPage::setWorkspaceTelemetry"

start = text.find(start_sig)
if start < 0:
    raise SystemExit("Could not find applyWorkerMessage start.")

next_start = text.find(next_sig, start)
if next_start < 0:
    raise SystemExit("Could not find setWorkspaceTelemetry marker after applyWorkerMessage.")

replacement = r'''void ImageGenerationPage::applyWorkerMessage(const QJsonObject &payload)
{
    const QString workerType = payload.value(QStringLiteral("type")).toString().trimmed().toLower();
    const QString workerState = payload.value(QStringLiteral("state")).toString().trimmed().toLower();

    const bool terminalWorkerMessage =
        workerState == QStringLiteral("completed") ||
        workerState == QStringLiteral("failed") ||
        workerState == QStringLiteral("cancelled") ||
        workerState == QStringLiteral("canceled") ||
        workerType == QStringLiteral("result") ||
        workerType == QStringLiteral("error") ||
        workerType == QStringLiteral("client_error");

    if (terminalWorkerMessage)
    {
        busy_ = false;
        busyMessage_.clear();
        generateSubmitLocked_ = false;
    }

    spellvision::generation::GenerationStatusController::Bindings bindings;
    bindings.setBusy = [this](bool busy, const QString &message) {
        setBusy(busy, message);
    };
    bindings.routeOutput = [this](const QString &outputPath, const QString &caption) {
        setPreviewImage(outputPath, caption);
    };
    bindings.showProblem = [this](const QString &text) {
        const QString trimmed = text.trimmed();
        if (trimmed.isEmpty())
            return;

        if (!readinessHintLabel_)
            return;

        readinessHintLabel_->setText(trimmed);
        readinessHintLabel_->setToolTip(trimmed);
        readinessHintLabel_->setVisible(true);
    };

    spellvision::generation::GenerationStatusController::applyWorkerPayload(payload, bindings);

    // Pass 28 terminal safety repaint: terminal worker messages must always
    // leave the page able to submit the next generation.
    if (terminalWorkerMessage)
        updatePrimaryActionAvailability();
}

'''

text = text[:start] + replacement + text[next_start:]
path.write_text(text, encoding="utf-8")

print("Repaired ImageGenerationPage::applyWorkerMessage Pass 28 syntax damage.")
