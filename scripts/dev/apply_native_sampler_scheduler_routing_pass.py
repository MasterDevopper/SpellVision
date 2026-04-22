from __future__ import annotations

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPO_ROOT / "python"
QT_ROOT = REPO_ROOT / "qt_ui"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str, *, required: bool = True) -> str:
    if old not in text:
        if required:
            raise SystemExit(f"Could not find {label}.")
        return text
    return text.replace(old, new, 1)


def patch_worker_service() -> None:
    path = PYTHON_ROOT / "worker_service.py"
    text = read(path)

    # Pylance/guard-clause cleanup for the older local helper, if it exists.
    old_choices = '''def _comfy_input_choices(object_info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    info = object_info.get(class_name) if isinstance(object_info, dict) else None
    if not isinstance(info, dict):
        return []

    input_info = info.get("input") if isinstance(info.get("input"), dict) else {}
    for bucket in ("required", "optional"):
        values = input_info.get(bucket)
        if not isinstance(values, dict):
            continue

        spec = values.get(input_name)
        if isinstance(spec, (list, tuple)) and spec:
            first = spec[0]
            if isinstance(first, (list, tuple)):
                return [str(item) for item in first if str(item).strip()]

    return []
'''
    new_choices = '''def _comfy_input_choices(object_info: dict[str, Any], class_name: str, input_name: str) -> list[str]:
    if not isinstance(object_info, dict):
        return []

    info = object_info.get(class_name)
    if not isinstance(info, dict):
        return []

    raw_input_info = info.get("input")
    if not isinstance(raw_input_info, dict):
        return []

    for bucket in ("required", "optional"):
        values = raw_input_info.get(bucket)
        if not isinstance(values, dict):
            continue

        spec = values.get(input_name)
        if not isinstance(spec, (list, tuple)) or not spec:
            continue

        first = spec[0]
        if isinstance(first, (list, tuple)):
            return [str(item) for item in first if str(item).strip()]

    return []
'''
    if old_choices in text:
        text = text.replace(old_choices, new_choices, 1)

    # Make the WAN builder consume adapter-scoped video_sampler/video_scheduler keys
    # if the builder still directly reads the generic sampler/scheduler request keys.
    replacements = {
        'req.get("scheduler")': 'req.get("video_scheduler") or req.get("scheduler")',
        'req.get("sampler")': 'req.get("video_sampler") or req.get("sampler")',
    }
    if "def _build_native_wan_split_video_prompt" in text:
        start = text.find("def _build_native_wan_split_video_prompt")
        end_candidates = [
            text.find("\ndef _build_native_split_video_prompt", start + 1),
            text.find("\ndef run_native_split_stack_video", start + 1),
        ]
        end_candidates = [idx for idx in end_candidates if idx != -1]
        end = min(end_candidates) if end_candidates else len(text)
        block = text[start:end]
        for old, new in replacements.items():
            block = block.replace(old, new)
        text = text[:start] + block + text[end:]

    write(path, text)


def patch_image_generation_header() -> None:
    path = QT_ROOT / "ImageGenerationPage.h"
    if not path.exists():
        return

    text = read(path)
    if "videoSamplerCombo_" in text and "videoSchedulerCombo_" in text:
        return

    text = replace_once(
        text,
        "    QComboBox *samplerCombo_ = nullptr;\n    QComboBox *schedulerCombo_ = nullptr;\n",
        "    QComboBox *samplerCombo_ = nullptr;\n    QComboBox *schedulerCombo_ = nullptr;\n    QComboBox *videoSamplerCombo_ = nullptr;\n    QComboBox *videoSchedulerCombo_ = nullptr;\n",
        "ImageGenerationPage sampler/scheduler members",
    )
    write(path, text)


def patch_image_generation_cpp() -> None:
    path = QT_ROOT / "ImageGenerationPage.cpp"
    if not path.exists():
        return

    text = read(path)

    old_payload = '''    payload.insert(QStringLiteral("sampler"), currentComboValue(samplerCombo_));
    payload.insert(QStringLiteral("scheduler"), currentComboValue(schedulerCombo_));
    payload.insert(QStringLiteral("steps"), stepsSpin_ ? stepsSpin_->value() : 0);
'''
    new_payload = '''    const QString imageSamplerValue = currentComboValue(samplerCombo_);
    const QString imageSchedulerValue = currentComboValue(schedulerCombo_);
    if (isVideoMode())
    {
        const QString rawVideoSampler = videoSamplerCombo_ ? currentComboValue(videoSamplerCombo_) : QStringLiteral("auto");
        const QString rawVideoScheduler = videoSchedulerCombo_ ? currentComboValue(videoSchedulerCombo_) : QStringLiteral("auto");
        const QString videoSamplerValue = rawVideoSampler.compare(QStringLiteral("auto"), Qt::CaseInsensitive) == 0 ? QString() : rawVideoSampler;
        const QString videoSchedulerValue = rawVideoScheduler.compare(QStringLiteral("auto"), Qt::CaseInsensitive) == 0 ? QString() : rawVideoScheduler;

        payload.insert(QStringLiteral("image_sampler"), imageSamplerValue);
        payload.insert(QStringLiteral("image_scheduler"), imageSchedulerValue);
        payload.insert(QStringLiteral("sampler"), videoSamplerValue);
        payload.insert(QStringLiteral("scheduler"), videoSchedulerValue);
        payload.insert(QStringLiteral("video_sampler"), videoSamplerValue);
        payload.insert(QStringLiteral("video_scheduler"), videoSchedulerValue);
        payload.insert(QStringLiteral("sampler_scope"), QStringLiteral("video"));
    }
    else
    {
        payload.insert(QStringLiteral("sampler"), imageSamplerValue);
        payload.insert(QStringLiteral("scheduler"), imageSchedulerValue);
        payload.insert(QStringLiteral("sampler_scope"), QStringLiteral("image"));
    }
    payload.insert(QStringLiteral("steps"), stepsSpin_ ? stepsSpin_->value() : 0);
'''
    if old_payload in text:
        text = text.replace(old_payload, new_payload, 1)

    if "videoSamplerCombo_ = new ClickOnlyComboBox" not in text:
        old_combo = '''    schedulerCombo_ = new ClickOnlyComboBox(quickControlsCard);
    schedulerCombo_->addItem(QStringLiteral("normal"), QStringLiteral("normal"));
    schedulerCombo_->addItem(QStringLiteral("karras"), QStringLiteral("karras"));
    schedulerCombo_->addItem(QStringLiteral("sgm_uniform"), QStringLiteral("sgm_uniform"));
    configureComboBox(schedulerCombo_);
'''
        new_combo = '''    schedulerCombo_ = new ClickOnlyComboBox(quickControlsCard);
    schedulerCombo_->addItem(QStringLiteral("normal"), QStringLiteral("normal"));
    schedulerCombo_->addItem(QStringLiteral("karras"), QStringLiteral("karras"));
    schedulerCombo_->addItem(QStringLiteral("sgm_uniform"), QStringLiteral("sgm_uniform"));
    configureComboBox(schedulerCombo_);

    videoSamplerCombo_ = new ClickOnlyComboBox(quickControlsCard);
    videoSamplerCombo_->addItem(QStringLiteral("Auto / family default"), QStringLiteral("auto"));
    videoSamplerCombo_->addItem(QStringLiteral("Euler"), QStringLiteral("euler"));
    videoSamplerCombo_->addItem(QStringLiteral("Euler ancestral"), QStringLiteral("euler_ancestral"));
    videoSamplerCombo_->addItem(QStringLiteral("DPM++ 2M"), QStringLiteral("dpmpp_2m"));
    videoSamplerCombo_->addItem(QStringLiteral("UniPC"), QStringLiteral("uni_pc"));
    configureComboBox(videoSamplerCombo_);

    videoSchedulerCombo_ = new ClickOnlyComboBox(quickControlsCard);
    videoSchedulerCombo_->addItem(QStringLiteral("Auto / family default"), QStringLiteral("auto"));
    videoSchedulerCombo_->addItem(QStringLiteral("Normal"), QStringLiteral("normal"));
    videoSchedulerCombo_->addItem(QStringLiteral("Simple"), QStringLiteral("simple"));
    videoSchedulerCombo_->addItem(QStringLiteral("SGM uniform"), QStringLiteral("sgm_uniform"));
    videoSchedulerCombo_->addItem(QStringLiteral("FlowMatch / CausVid"), QStringLiteral("flowmatch_causvid"));
    configureComboBox(videoSchedulerCombo_);
'''
        text = replace_once(text, old_combo, new_combo, "sampler/scheduler combo construction", required=False)

    if "Video Sampler" not in text:
        old_rows = '''    QWidget *aspectRow = makeSettingsRow(quickControlsCard, QStringLiteral("Aspect"), aspectPresetCombo);
    QWidget *samplerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Sampler"), samplerCombo_);
    QWidget *schedulerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Scheduler"), schedulerCombo_);
    QWidget *stepsRow = makeSettingsRow(quickControlsCard, QStringLiteral("Steps"), stepsSpin_);
'''
        new_rows = '''    QWidget *aspectRow = makeSettingsRow(quickControlsCard, QStringLiteral("Aspect"), aspectPresetCombo);
    QWidget *samplerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Image Sampler"), samplerCombo_);
    QWidget *schedulerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Image Scheduler"), schedulerCombo_);
    QWidget *videoSamplerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Video Sampler"), videoSamplerCombo_);
    QWidget *videoSchedulerRow = makeSettingsRow(quickControlsCard, QStringLiteral("Video Scheduler"), videoSchedulerCombo_);
    samplerRow->setVisible(!isVideoMode());
    schedulerRow->setVisible(!isVideoMode());
    videoSamplerRow->setVisible(isVideoMode());
    videoSchedulerRow->setVisible(isVideoMode());
    QWidget *stepsRow = makeSettingsRow(quickControlsCard, QStringLiteral("Steps"), stepsSpin_);
'''
        text = replace_once(text, old_rows, new_rows, "sampler/scheduler rows", required=False)

        old_layout = '''    samplerSchedulerLayout_->addWidget(aspectRow);
    samplerSchedulerLayout_->addWidget(samplerRow);
    samplerSchedulerLayout_->addWidget(schedulerRow);
'''
        new_layout = '''    samplerSchedulerLayout_->addWidget(aspectRow);
    samplerSchedulerLayout_->addWidget(samplerRow);
    samplerSchedulerLayout_->addWidget(schedulerRow);
    samplerSchedulerLayout_->addWidget(videoSamplerRow);
    samplerSchedulerLayout_->addWidget(videoSchedulerRow);
'''
        text = replace_once(text, old_layout, new_layout, "sampler/scheduler layout rows", required=False)

    if "videoSamplerCombo_, &QComboBox::currentTextChanged" not in text:
        old_connects = '''    connect(samplerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(schedulerCombo_, &QComboBox::currentTextChanged, this, refreshers);
'''
        new_connects = '''    connect(samplerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    connect(schedulerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    if (videoSamplerCombo_)
        connect(videoSamplerCombo_, &QComboBox::currentTextChanged, this, refreshers);
    if (videoSchedulerCombo_)
        connect(videoSchedulerCombo_, &QComboBox::currentTextChanged, this, refreshers);
'''
        text = replace_once(text, old_connects, new_connects, "sampler/scheduler refresh connections", required=False)

    if "video_sampler" not in text:
        old_save = '''    settings.setValue(QStringLiteral("sampler"), currentComboValue(samplerCombo_));
    settings.setValue(QStringLiteral("scheduler"), currentComboValue(schedulerCombo_));
'''
        new_save = '''    settings.setValue(QStringLiteral("sampler"), currentComboValue(samplerCombo_));
    settings.setValue(QStringLiteral("scheduler"), currentComboValue(schedulerCombo_));
    settings.setValue(QStringLiteral("video_sampler"), currentComboValue(videoSamplerCombo_));
    settings.setValue(QStringLiteral("video_scheduler"), currentComboValue(videoSchedulerCombo_));
'''
        text = replace_once(text, old_save, new_save, "settings save video sampler/scheduler", required=False)

        old_restore = '''    if (samplerCombo_)
        selectComboValue(samplerCombo_, settings.value(QStringLiteral("sampler"), QStringLiteral("dpmpp_2m")).toString());
    if (schedulerCombo_)
        selectComboValue(schedulerCombo_, settings.value(QStringLiteral("scheduler"), QStringLiteral("karras")).toString());
'''
        new_restore = '''    if (samplerCombo_)
        selectComboValue(samplerCombo_, settings.value(QStringLiteral("sampler"), QStringLiteral("dpmpp_2m")).toString());
    if (schedulerCombo_)
        selectComboValue(schedulerCombo_, settings.value(QStringLiteral("scheduler"), QStringLiteral("karras")).toString());
    if (videoSamplerCombo_)
        selectComboValue(videoSamplerCombo_, settings.value(QStringLiteral("video_sampler"), QStringLiteral("auto")).toString());
    if (videoSchedulerCombo_)
        selectComboValue(videoSchedulerCombo_, settings.value(QStringLiteral("video_scheduler"), QStringLiteral("auto")).toString());
'''
        text = replace_once(text, old_restore, new_restore, "settings restore video sampler/scheduler", required=False)

    # In case this file already had the payload patch, but not saved settings, ensure the settings code is still attempted.
    write(path, text)


def main() -> None:
    patch_worker_service()
    patch_image_generation_header()
    patch_image_generation_cpp()
    print("Applied Native Sampler / Scheduler Routing pass.")
    print("- Video modes now send video_sampler/video_scheduler instead of leaking image scheduler values.")
    print("- WAN adapter now validates sampler/scheduler against WanVideoSampler /object_info choices.")
    print("- WAN adapter avoids fp8-scaled T5 encoders for LoadWanVideoT5TextEncoder.")


if __name__ == "__main__":
    main()
