#include "TelemetryPresenter.h"

#include "ShellNavigationController.h"

#include <QFileInfo>

namespace spellvision::shell
{

QString TelemetryPresenter::pageLabelText(const QString &modeId)
{
    return ShellNavigationController::pageContextForMode(modeId);
}

QString TelemetryPresenter::shortAssetName(const QString &value)
{
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty())
        return QString();
    const QFileInfo info(trimmed);
    const QString baseName = info.completeBaseName().trimmed();
    if (!baseName.isEmpty())
        return baseName;
    const QString fileName = info.fileName().trimmed();
    return fileName.isEmpty() ? trimmed : fileName;
}

TelemetryChip TelemetryPresenter::assetChip(const QString &caption, bool hasSlot, const QString &value)
{
    TelemetryChip chip;
    if (!hasSlot)
    {
        // Flows, History, Models, Runtime, Settings... "Model: none" on a page that has no model to
        // choose is a false statement about the user's choices, and it is indistinguishable from a
        // generation page where they have chosen nothing. The bar already hides ETA and LoRA when
        // the window is narrow, so a hidden chip is existing behaviour, not a new shape.
        chip.visible = false;
        return chip;
    }

    const QString shortName = shortAssetName(value);
    if (shortName.isEmpty())
    {
        chip.text = QStringLiteral("%1: not selected").arg(caption);
        chip.toolTip = QStringLiteral("No %1 chosen on this page yet.").arg(caption.toLower());
        return chip;
    }

    chip.text = QStringLiteral("%1: %2").arg(caption, shortName);
    chip.toolTip = value.trimmed();
    return chip;
}

} // namespace spellvision::shell
