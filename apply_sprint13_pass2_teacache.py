from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MARKER = "SPELLVISION SPRINT 13 PASS 2 TEACACHE"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".pre_sprint13_pass2_teacache.bak")
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backup written: {backup}")


def patch_catalog(project: Path) -> None:
    catalog_path = project / "python" / "starter_node_catalog.json"
    if not catalog_path.exists():
        print(f"Skipped node catalog; not found: {catalog_path}")
        return

    backup_once(catalog_path)
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    packages = payload.setdefault("packages", [])
    for package in packages:
        if str(package.get("package_name", "")).lower() == "comfyui-teacache":
            print("Node catalog already includes ComfyUI-TeaCache")
            catalog_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return

    packages.append(
        {
            "package_name": "ComfyUI-TeaCache",
            "repo_url": "https://github.com/welltop-cn/ComfyUI-TeaCache.git",
            "install_method": "manager",
            "aliases": [
                "teacache",
                "tea cache",
                "video acceleration",
                "timestep embedding aware cache",
            ],
            "class_name_patterns": [
                "TeaCache",
                "teacache",
            ],
            "model_families": [
                "wan",
                "ltx",
                "hunyuan_video",
                "cogvideox",
                "flux",
            ],
        }
    )
    catalog_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Patched node catalog: {catalog_path}")


def patch_header(project: Path) -> None:
    path = project / "qt_ui" / "ImageGenerationPage.h"
    if not path.exists():
        print(f"Skipped header; not found: {path}")
        return

    text = read_text(path)
    if f"{MARKER} CONTROLS" in text:
        print("ImageGenerationPage.h already has TeaCache members")
        return

    backup_once(path)

    if "class QCheckBox;" not in text:
        text = text.replace("class QComboBox;\n", "class QComboBox;\nclass QCheckBox;\n", 1)

    member_block = f"""
    // --- {MARKER} CONTROLS ---
    QCheckBox *teaCacheEnabledCheck_ = nullptr;
    QComboBox *teaCacheProfileCombo_ = nullptr;
    QComboBox *teaCacheModelTypeCombo_ = nullptr;
    QDoubleSpinBox *teaCacheRelL1Spin_ = nullptr;
    QDoubleSpinBox *teaCacheStartPercentSpin_ = nullptr;
    QDoubleSpinBox *teaCacheEndPercentSpin_ = nullptr;
    QComboBox *teaCacheCacheDeviceCombo_ = nullptr;
    // --- END {MARKER} CONTROLS ---
"""

    anchor = "    QCheckBox *wanVaeTilingCheck_ = nullptr;\n"
    if anchor in text:
        text = text.replace(anchor, anchor + member_block, 1)
    else:
        fallback = "    QDoubleSpinBox *denoiseSpin_ = nullptr;\n"
        if fallback not in text:
            raise RuntimeError("Could not find header insertion point for TeaCache controls")
        text = text.replace(fallback, fallback + member_block, 1)

    write_text(path, text)
    print(f"Patched header: {path}")


def insert_once(text: str, anchor: str, insertion: str, *, after: bool = True, label: str = "anchor") -> str:
    if insertion.strip() in text:
        return text
    if anchor not in text:
        raise RuntimeError(f"Could not find {label}")
    if after:
        return text.replace(anchor, anchor + insertion, 1)
    return text.replace(anchor, insertion + anchor, 1)


def patch_image_generation_cpp(project: Path) -> None:
    path = project / "qt_ui" / "ImageGenerationPage.cpp"
    if not path.exists():
        print(f"Skipped ImageGenerationPage.cpp; not found: {path}")
        return

    text = read_text(path)
    if f"{MARKER} PAYLOAD" in text:
        print("ImageGenerationPage.cpp already has TeaCache UI/payload patch")
        return

    backup_once(path)

    # 1. Payload fields. Prefer inserting next to existing VAE tiling fields.
    payload_insertion = f"""
        // --- {MARKER} PAYLOAD ---
        const bool teaCacheEnabled = teaCacheEnabledCheck_ && teaCacheEnabledCheck_->isChecked();
        const QString teaCacheProfile = currentComboValue(teaCacheProfileCombo_).trimmed().isEmpty()
            ? QStringLiteral("off")
            : currentComboValue(teaCacheProfileCombo_);
        const QString teaCacheModelType = currentComboValue(teaCacheModelTypeCombo_).trimmed().isEmpty()
            ? QStringLiteral("wan2.1_t2v_14b")
            : currentComboValue(teaCacheModelTypeCombo_);
        const QString teaCacheCacheDevice = currentComboValue(teaCacheCacheDeviceCombo_).trimmed().isEmpty()
            ? QStringLiteral("cpu")
            : currentComboValue(teaCacheCacheDeviceCombo_);
        payload.insert(QStringLiteral("teacache_enabled"), teaCacheEnabled);
        payload.insert(QStringLiteral("teacache_profile"), teaCacheProfile);
        payload.insert(QStringLiteral("teacache_model_type"), teaCacheModelType);
        payload.insert(QStringLiteral("teacache_rel_l1_thresh"), teaCacheRelL1Spin_ ? teaCacheRelL1Spin_->value() : 0.20);
        payload.insert(QStringLiteral("teacache_start_percent"), teaCacheStartPercentSpin_ ? teaCacheStartPercentSpin_->value() : 0.0);
        payload.insert(QStringLiteral("teacache_end_percent"), teaCacheEndPercentSpin_ ? teaCacheEndPercentSpin_->value() : 1.0);
        payload.insert(QStringLiteral("teacache_cache_device"), teaCacheCacheDevice);
        QJsonObject teaCachePayload;
        teaCachePayload.insert(QStringLiteral("enabled"), teaCacheEnabled);
        teaCachePayload.insert(QStringLiteral("profile"), teaCacheProfile);
        teaCachePayload.insert(QStringLiteral("model_type"), teaCacheModelType);
        teaCachePayload.insert(QStringLiteral("rel_l1_thresh"), teaCacheRelL1Spin_ ? teaCacheRelL1Spin_->value() : 0.20);
        teaCachePayload.insert(QStringLiteral("start_percent"), teaCacheStartPercentSpin_ ? teaCacheStartPercentSpin_->value() : 0.0);
        teaCachePayload.insert(QStringLiteral("end_percent"), teaCacheEndPercentSpin_ ? teaCacheEndPercentSpin_->value() : 1.0);
        teaCachePayload.insert(QStringLiteral("cache_device"), teaCacheCacheDevice);
        payload.insert(QStringLiteral("video_acceleration"), teaCachePayload);
        // --- END {MARKER} PAYLOAD ---
"""
    payload_anchor = "        payload.insert(QStringLiteral(\"vae_tiling\"), wanVaeTilingCheck_ ? wanVaeTilingCheck_->isChecked() : false);\n"
    if payload_anchor in text:
        text = insert_once(text, payload_anchor, payload_insertion, after=True, label="VAE tiling payload anchor")
    else:
        fallback = "        payload.insert(QStringLiteral(\"duration_seconds\"), fps > 0 ? static_cast<double>(frames) / static_cast<double>(fps) : 0.0);\n"
        text = insert_once(text, fallback, payload_insertion, after=True, label="video payload anchor")

    # 2. Widget creation.
    widget_insertion = f"""

    // --- {MARKER} WIDGETS ---
    teaCacheEnabledCheck_ = new QCheckBox(QStringLiteral("Enable TeaCache"), advancedCard);
    teaCacheEnabledCheck_->setObjectName(QStringLiteral("CompactFieldLabel"));
    teaCacheEnabledCheck_->setToolTip(QStringLiteral("Use ComfyUI-TeaCache to accelerate supported native video graphs. If the node is missing, SpellVision falls back to normal generation."));

    teaCacheProfileCombo_ = new ClickOnlyComboBox(advancedCard);
    teaCacheProfileCombo_->addItem(QStringLiteral("Off"), QStringLiteral("off"));
    teaCacheProfileCombo_->addItem(QStringLiteral("Safe"), QStringLiteral("safe"));
    teaCacheProfileCombo_->addItem(QStringLiteral("Balanced"), QStringLiteral("balanced"));
    teaCacheProfileCombo_->addItem(QStringLiteral("Fast"), QStringLiteral("fast"));
    teaCacheProfileCombo_->addItem(QStringLiteral("Custom"), QStringLiteral("custom"));
    configureComboBox(teaCacheProfileCombo_);

    teaCacheModelTypeCombo_ = new ClickOnlyComboBox(advancedCard);
    teaCacheModelTypeCombo_->addItem(QStringLiteral("Wan2.1 T2V 14B / Wan2.2 closest"), QStringLiteral("wan2.1_t2v_14b"));
    teaCacheModelTypeCombo_->addItem(QStringLiteral("Wan2.1 T2V 14B retention"), QStringLiteral("wan2.1_t2v_14b_ret_mode"));
    teaCacheModelTypeCombo_->addItem(QStringLiteral("Wan2.1 I2V 480P 14B"), QStringLiteral("wan2.1_i2v_480p_14b"));
    teaCacheModelTypeCombo_->addItem(QStringLiteral("Wan2.1 I2V 720P 14B"), QStringLiteral("wan2.1_i2v_720p_14b"));
    teaCacheModelTypeCombo_->addItem(QStringLiteral("LTX Video"), QStringLiteral("ltxv"));
    teaCacheModelTypeCombo_->addItem(QStringLiteral("Hunyuan Video"), QStringLiteral("hunyuan_video"));
    teaCacheModelTypeCombo_->addItem(QStringLiteral("CogVideoX"), QStringLiteral("cogvideox"));
    configureComboBox(teaCacheModelTypeCombo_);

    teaCacheRelL1Spin_ = new QDoubleSpinBox(advancedCard);
    teaCacheRelL1Spin_->setDecimals(3);
    teaCacheRelL1Spin_->setSingleStep(0.01);
    teaCacheRelL1Spin_->setRange(0.0, 2.0);
    teaCacheRelL1Spin_->setValue(0.20);
    teaCacheRelL1Spin_->setToolTip(QStringLiteral("TeaCache threshold. Lower values preserve quality; higher values may run faster."));
    configureDoubleSpinBox(teaCacheRelL1Spin_);

    teaCacheStartPercentSpin_ = new QDoubleSpinBox(advancedCard);
    teaCacheStartPercentSpin_->setDecimals(2);
    teaCacheStartPercentSpin_->setSingleStep(0.05);
    teaCacheStartPercentSpin_->setRange(0.0, 1.0);
    teaCacheStartPercentSpin_->setValue(0.0);
    configureDoubleSpinBox(teaCacheStartPercentSpin_);

    teaCacheEndPercentSpin_ = new QDoubleSpinBox(advancedCard);
    teaCacheEndPercentSpin_->setDecimals(2);
    teaCacheEndPercentSpin_->setSingleStep(0.05);
    teaCacheEndPercentSpin_->setRange(0.0, 1.0);
    teaCacheEndPercentSpin_->setValue(1.0);
    configureDoubleSpinBox(teaCacheEndPercentSpin_);

    teaCacheCacheDeviceCombo_ = new ClickOnlyComboBox(advancedCard);
    teaCacheCacheDeviceCombo_->addItem(QStringLiteral("CPU cache"), QStringLiteral("cpu"));
    teaCacheCacheDeviceCombo_->addItem(QStringLiteral("CUDA cache"), QStringLiteral("cuda"));
    configureComboBox(teaCacheCacheDeviceCombo_);
    // --- END {MARKER} WIDGETS ---
"""
    widget_anchor = "    wanVaeTilingCheck_->setToolTip(QStringLiteral(\"Request tiled VAE decode where the active native video template supports it.\"));\n"
    if widget_anchor in text:
        text = insert_once(text, widget_anchor, widget_insertion, after=True, label="VAE tiling widget anchor")
    else:
        fallback = "    configureDoubleSpinBox(denoiseSpin_);\n"
        text = insert_once(text, fallback, widget_insertion, after=True, label="denoise widget anchor")

    # 3. Rows.
    rows_insertion = f"""

    // --- {MARKER} ROWS ---
    QWidget *teaCacheEnabledRow = new QWidget(advancedCard);
    auto *teaCacheEnabledLayout = new QHBoxLayout(teaCacheEnabledRow);
    teaCacheEnabledLayout->setContentsMargins(0, 0, 0, 0);
    teaCacheEnabledLayout->addSpacing(78);
    teaCacheEnabledLayout->addWidget(teaCacheEnabledCheck_, 1);
    QWidget *teaCacheProfileRow = makeSettingsRow(advancedCard, QStringLiteral("TeaCache"), teaCacheProfileCombo_);
    QWidget *teaCacheModelTypeRow = makeSettingsRow(advancedCard, QStringLiteral("Cache Type"), teaCacheModelTypeCombo_);
    QWidget *teaCacheRelL1Row = makeSettingsRow(advancedCard, QStringLiteral("Cache L1"), teaCacheRelL1Spin_);
    QWidget *teaCacheStartRow = makeSettingsRow(advancedCard, QStringLiteral("Cache Start"), teaCacheStartPercentSpin_);
    QWidget *teaCacheEndRow = makeSettingsRow(advancedCard, QStringLiteral("Cache End"), teaCacheEndPercentSpin_);
    QWidget *teaCacheDeviceRow = makeSettingsRow(advancedCard, QStringLiteral("Cache Dev"), teaCacheCacheDeviceCombo_);

    for (QWidget *row : {{teaCacheEnabledRow, teaCacheProfileRow, teaCacheModelTypeRow, teaCacheRelL1Row, teaCacheStartRow, teaCacheEndRow, teaCacheDeviceRow}})
    {{
        row->setObjectName(QStringLiteral("AdvancedBodyRow"));
        row->setVisible(isVideoMode());
    }}
    // --- END {MARKER} ROWS ---
"""
    rows_anchor = "    for (QWidget *row : {wanSplitModeRow, wanHighStepsRow, wanLowStepsRow, wanSplitStepRow, wanHighShiftRow, wanLowShiftRow, wanVaeTilingRow})\n"
    if rows_anchor in text:
        text = insert_once(text, rows_anchor, rows_insertion, after=False, label="Wan rows anchor")
    else:
        fallback = "    denoiseRow_->setVisible(usesStrengthControl());\n"
        text = insert_once(text, fallback, rows_insertion, after=True, label="advanced row anchor")

    # 4. Add rows to layout.
    layout_insertion = f"""
    // --- {MARKER} LAYOUT ---
    advancedLayout->addWidget(teaCacheEnabledRow);
    advancedLayout->addWidget(teaCacheProfileRow);
    advancedLayout->addWidget(teaCacheModelTypeRow);
    advancedLayout->addWidget(teaCacheRelL1Row);
    advancedLayout->addWidget(teaCacheStartRow);
    advancedLayout->addWidget(teaCacheEndRow);
    advancedLayout->addWidget(teaCacheDeviceRow);
    // --- END {MARKER} LAYOUT ---
"""
    layout_anchor = "    advancedLayout->addWidget(wanVaeTilingRow);\n"
    if layout_anchor in text:
        text = insert_once(text, layout_anchor, layout_insertion, after=True, label="advanced layout anchor")
    else:
        fallback = "    advancedLayout->addWidget(denoiseRow_);\n"
        text = insert_once(text, fallback, layout_insertion, after=True, label="advanced layout fallback")

    # 5. Profile preset lambda + connections.
    apply_insertion = f"""
    // --- {MARKER} PROFILE PRESETS ---
    auto applyTeaCacheProfilePreset = [this]() {{
        const QString profile = currentComboValue(teaCacheProfileCombo_).trimmed().toLower();
        if (profile == QStringLiteral("off"))
        {{
            if (teaCacheEnabledCheck_)
                teaCacheEnabledCheck_->setChecked(false);
            return;
        }}

        if (teaCacheEnabledCheck_)
            teaCacheEnabledCheck_->setChecked(true);

        if (profile == QStringLiteral("safe"))
        {{
            if (teaCacheRelL1Spin_)
                teaCacheRelL1Spin_->setValue(0.14);
            if (teaCacheStartPercentSpin_)
                teaCacheStartPercentSpin_->setValue(0.0);
            if (teaCacheEndPercentSpin_)
                teaCacheEndPercentSpin_->setValue(1.0);
        }}
        else if (profile == QStringLiteral("balanced"))
        {{
            if (teaCacheRelL1Spin_)
                teaCacheRelL1Spin_->setValue(0.20);
            if (teaCacheStartPercentSpin_)
                teaCacheStartPercentSpin_->setValue(0.0);
            if (teaCacheEndPercentSpin_)
                teaCacheEndPercentSpin_->setValue(1.0);
        }}
        else if (profile == QStringLiteral("fast"))
        {{
            if (teaCacheRelL1Spin_)
                teaCacheRelL1Spin_->setValue(0.30);
            if (teaCacheStartPercentSpin_)
                teaCacheStartPercentSpin_->setValue(0.1);
            if (teaCacheEndPercentSpin_)
                teaCacheEndPercentSpin_->setValue(1.0);
        }}
    }};
    // --- END {MARKER} PROFILE PRESETS ---

"""
    connections_insertion = f"""
    // --- {MARKER} CONNECTIONS ---
    if (teaCacheEnabledCheck_)
        connect(teaCacheEnabledCheck_, &QCheckBox::toggled, this, refreshers);
    if (teaCacheProfileCombo_)
        connect(teaCacheProfileCombo_, &QComboBox::currentTextChanged, this, [applyTeaCacheProfilePreset, refreshers](const QString &) {{ applyTeaCacheProfilePreset(); refreshers(); }});
    if (teaCacheModelTypeCombo_)
        connect(teaCacheModelTypeCombo_, &QComboBox::currentTextChanged, this, refreshers);
    if (teaCacheRelL1Spin_)
        connect(teaCacheRelL1Spin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    if (teaCacheStartPercentSpin_)
        connect(teaCacheStartPercentSpin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    if (teaCacheEndPercentSpin_)
        connect(teaCacheEndPercentSpin_, qOverload<double>(&QDoubleSpinBox::valueChanged), this, refreshers);
    if (teaCacheCacheDeviceCombo_)
        connect(teaCacheCacheDeviceCombo_, &QComboBox::currentTextChanged, this, refreshers);
    // --- END {MARKER} CONNECTIONS ---
"""
    conn_anchor = "    connect(promptEdit_, &QTextEdit::textChanged, this, refreshers);\n"
    text = insert_once(text, conn_anchor, apply_insertion, after=False, label="refreshers connection anchor")
    text = insert_once(text, conn_anchor, connections_insertion, after=False, label="connections anchor")

    # 6. Recipe save/load.
    recipe_save_insertion = f"""
    // --- {MARKER} RECIPE SAVE ---
    advanced.insert(QStringLiteral("teacache_enabled"), teaCacheEnabledCheck_ ? teaCacheEnabledCheck_->isChecked() : false);
    advanced.insert(QStringLiteral("teacache_profile"), currentComboValue(teaCacheProfileCombo_).trimmed().isEmpty() ? QStringLiteral("off") : currentComboValue(teaCacheProfileCombo_));
    advanced.insert(QStringLiteral("teacache_model_type"), currentComboValue(teaCacheModelTypeCombo_).trimmed().isEmpty() ? QStringLiteral("wan2.1_t2v_14b") : currentComboValue(teaCacheModelTypeCombo_));
    advanced.insert(QStringLiteral("teacache_rel_l1_thresh"), teaCacheRelL1Spin_ ? teaCacheRelL1Spin_->value() : 0.20);
    advanced.insert(QStringLiteral("teacache_start_percent"), teaCacheStartPercentSpin_ ? teaCacheStartPercentSpin_->value() : 0.0);
    advanced.insert(QStringLiteral("teacache_end_percent"), teaCacheEndPercentSpin_ ? teaCacheEndPercentSpin_->value() : 1.0);
    advanced.insert(QStringLiteral("teacache_cache_device"), currentComboValue(teaCacheCacheDeviceCombo_).trimmed().isEmpty() ? QStringLiteral("cpu") : currentComboValue(teaCacheCacheDeviceCombo_));
    // --- END {MARKER} RECIPE SAVE ---
"""
    recipe_save_anchor = "    advanced.insert(QStringLiteral(\"vae_tiling\"), wanVaeTilingCheck_ ? wanVaeTilingCheck_->isChecked() : false);\n"
    if recipe_save_anchor in text:
        text = insert_once(text, recipe_save_anchor, recipe_save_insertion, after=True, label="recipe save anchor")

    recipe_load_insertion = f"""
    // --- {MARKER} RECIPE LOAD ---
    if (teaCacheEnabledCheck_ && advanced.contains(QStringLiteral("teacache_enabled")))
        teaCacheEnabledCheck_->setChecked(advanced.value(QStringLiteral("teacache_enabled")).toBool(false));
    if (teaCacheProfileCombo_)
        selectComboValue(teaCacheProfileCombo_, advanced.value(QStringLiteral("teacache_profile")).toString(QStringLiteral("off")));
    if (teaCacheModelTypeCombo_)
        selectComboValue(teaCacheModelTypeCombo_, advanced.value(QStringLiteral("teacache_model_type")).toString(QStringLiteral("wan2.1_t2v_14b")));
    if (teaCacheRelL1Spin_ && advanced.contains(QStringLiteral("teacache_rel_l1_thresh")))
        teaCacheRelL1Spin_->setValue(advanced.value(QStringLiteral("teacache_rel_l1_thresh")).toDouble(teaCacheRelL1Spin_->value()));
    if (teaCacheStartPercentSpin_ && advanced.contains(QStringLiteral("teacache_start_percent")))
        teaCacheStartPercentSpin_->setValue(advanced.value(QStringLiteral("teacache_start_percent")).toDouble(teaCacheStartPercentSpin_->value()));
    if (teaCacheEndPercentSpin_ && advanced.contains(QStringLiteral("teacache_end_percent")))
        teaCacheEndPercentSpin_->setValue(advanced.value(QStringLiteral("teacache_end_percent")).toDouble(teaCacheEndPercentSpin_->value()));
    if (teaCacheCacheDeviceCombo_)
        selectComboValue(teaCacheCacheDeviceCombo_, advanced.value(QStringLiteral("teacache_cache_device")).toString(QStringLiteral("cpu")));
    // --- END {MARKER} RECIPE LOAD ---
"""
    recipe_load_anchor = "    if (wanVaeTilingCheck_ && advanced.contains(QStringLiteral(\"vae_tiling\")))\n        wanVaeTilingCheck_->setChecked(advanced.value(QStringLiteral(\"vae_tiling\")).toBool(false));\n"
    if recipe_load_anchor in text:
        text = insert_once(text, recipe_load_anchor, recipe_load_insertion, after=True, label="recipe load anchor")

    # 7. Asset Intelligence line.
    asset_insertion = f"""
        // --- {MARKER} ASSET INTELLIGENCE ---
        const QString teaCacheState = teaCacheEnabledCheck_ && teaCacheEnabledCheck_->isChecked()
            ? QStringLiteral("%1 / %2 / L1 %3").arg(currentComboValue(teaCacheProfileCombo_).trimmed().isEmpty() ? QStringLiteral("custom") : currentComboValue(teaCacheProfileCombo_), currentComboValue(teaCacheCacheDeviceCombo_).trimmed().isEmpty() ? QStringLiteral("cpu") : currentComboValue(teaCacheCacheDeviceCombo_), teaCacheRelL1Spin_ ? QString::number(teaCacheRelL1Spin_->value(), 'f', 3) : QStringLiteral("0.200"))
            : QStringLiteral("off");
        html += row(QStringLiteral("TeaCache"), teaCacheState);
        // --- END {MARKER} ASSET INTELLIGENCE ---
"""
    asset_anchor = "        html += row(QStringLiteral(\"Wan Shift\"), QStringLiteral(\"high %1 / low %2\").arg(wanHighShiftSpin_ ? QString::number(wanHighShiftSpin_->value(), 'f', 2) : QStringLiteral(\"5.00\"), wanLowShiftSpin_ ? QString::number(wanLowShiftSpin_->value(), 'f', 2) : QStringLiteral(\"5.00\")));\n"
    if asset_anchor in text:
        text = insert_once(text, asset_anchor, asset_insertion, after=True, label="asset intelligence anchor")

    plain_insertion = f"""
        // --- {MARKER} ASSET INTELLIGENCE PLAIN ---
        const QString plainTeaCacheState = teaCacheEnabledCheck_ && teaCacheEnabledCheck_->isChecked()
            ? QStringLiteral("%1 / %2 / L1 %3").arg(currentComboValue(teaCacheProfileCombo_).trimmed().isEmpty() ? QStringLiteral("custom") : currentComboValue(teaCacheProfileCombo_), currentComboValue(teaCacheCacheDeviceCombo_).trimmed().isEmpty() ? QStringLiteral("cpu") : currentComboValue(teaCacheCacheDeviceCombo_), teaCacheRelL1Spin_ ? QString::number(teaCacheRelL1Spin_->value(), 'f', 3) : QStringLiteral("0.200"))
            : QStringLiteral("off");
        plain << QStringLiteral("TeaCache: %1").arg(plainTeaCacheState);
        // --- END {MARKER} ASSET INTELLIGENCE PLAIN ---
"""
    plain_anchor = "        plain << QStringLiteral(\"Wan Shift: high %1 / low %2\").arg(wanHighShiftSpin_ ? QString::number(wanHighShiftSpin_->value(), 'f', 2) : QStringLiteral(\"5.00\"), wanLowShiftSpin_ ? QString::number(wanLowShiftSpin_->value(), 'f', 2) : QStringLiteral(\"5.00\"));\n"
    if plain_anchor in text:
        text = insert_once(text, plain_anchor, plain_insertion, after=True, label="plain asset intelligence anchor")

    write_text(path, text)
    print(f"Patched ImageGenerationPage.cpp: {path}")


TEACACHE_HELPER_BLOCK = '''
# --- SPELLVISION SPRINT 13 PASS 2 TEACACHE WORKER HELPERS ---
def _spellvision_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return default


def _spellvision_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _spellvision_clamped_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, _spellvision_float(value, default)))


def _spellvision_teacache_enabled(req: dict[str, Any]) -> bool:
    if _spellvision_bool(req.get("teacache_enabled"), False):
        return True
    accel = req.get("video_acceleration")
    if isinstance(accel, dict):
        return _spellvision_bool(accel.get("enabled"), False)
    return False


def _spellvision_teacache_settings(req: dict[str, Any]) -> dict[str, Any]:
    accel = req.get("video_acceleration") if isinstance(req.get("video_acceleration"), dict) else {}
    profile = str(req.get("teacache_profile") or accel.get("profile") or "off").strip().lower() or "off"
    model_type = str(req.get("teacache_model_type") or accel.get("model_type") or "wan2.1_t2v_14b").strip() or "wan2.1_t2v_14b"
    cache_device = str(req.get("teacache_cache_device") or accel.get("cache_device") or "cpu").strip().lower() or "cpu"
    if cache_device not in {"cpu", "cuda"}:
        cache_device = "cpu"
    rel_l1 = _spellvision_clamped_float(req.get("teacache_rel_l1_thresh", accel.get("rel_l1_thresh", 0.20)), 0.20, 0.0, 2.0)
    start = _spellvision_clamped_float(req.get("teacache_start_percent", accel.get("start_percent", 0.0)), 0.0, 0.0, 1.0)
    end = _spellvision_clamped_float(req.get("teacache_end_percent", accel.get("end_percent", 1.0)), 1.0, 0.0, 1.0)
    if end < start:
        start, end = end, start
    return {
        "enabled": _spellvision_teacache_enabled(req),
        "profile": profile,
        "model_type": model_type,
        "rel_l1_thresh": rel_l1,
        "start_percent": start,
        "end_percent": end,
        "cache_device": cache_device,
    }


def _spellvision_teacache_class(object_info: dict[str, Any]) -> str | None:
    for class_name in ("TeaCache", "TeaCacheForVidGen", "TeaCacheForImgGen"):
        if class_name in object_info:
            return class_name
    for class_name in object_info:
        if "teacache" in str(class_name).lower().replace("_", ""):
            return str(class_name)
    return None


def _spellvision_choice_casefold(choices: list[str], requested: str) -> str | None:
    normalized_requested = requested.strip().lower().replace("-", "_").replace(" ", "_")
    for choice in choices:
        normalized_choice = str(choice).strip().lower().replace("-", "_").replace(" ", "_")
        if normalized_choice == normalized_requested:
            return str(choice).strip()
    return None


def _spellvision_teacache_model_type(object_info: dict[str, Any], class_name: str, requested: str) -> str:
    choices = _comfy_input_choices(object_info, class_name, "model_type")
    if not choices:
        return requested
    found = _spellvision_choice_casefold(choices, requested)
    if found:
        return found
    wanted = requested.lower().replace("-", "_").replace(" ", "_")
    for choice in choices:
        candidate = str(choice).lower().replace("-", "_").replace(" ", "_")
        if "wan" in wanted and "wan" in candidate and "14" in candidate and "t2v" in candidate:
            return str(choice).strip()
    for choice in choices:
        candidate = str(choice).lower()
        if "wan" in candidate:
            return str(choice).strip()
    return str(choices[0]).strip()


def _spellvision_teacache_metadata(req: dict[str, Any]) -> dict[str, Any]:
    settings = _spellvision_teacache_settings(req)
    return {
        "teacache_enabled": bool(settings.get("enabled")),
        "teacache_applied": bool(req.get("teacache_applied", False)),
        "teacache_available": bool(req.get("teacache_available", False)),
        "teacache_node_count": int(req.get("teacache_node_count") or 0),
        "teacache_profile": settings.get("profile"),
        "teacache_model_type": settings.get("model_type"),
        "teacache_rel_l1_thresh": settings.get("rel_l1_thresh"),
        "teacache_start_percent": settings.get("start_percent"),
        "teacache_end_percent": settings.get("end_percent"),
        "teacache_cache_device": settings.get("cache_device"),
        "teacache_warning": req.get("teacache_warning"),
        "video_acceleration": {
            "backend": "ComfyUI-TeaCache",
            **settings,
            "available": bool(req.get("teacache_available", False)),
            "applied": bool(req.get("teacache_applied", False)),
            "node_count": int(req.get("teacache_node_count") or 0),
            "warning": req.get("teacache_warning"),
        },
    }


def _spellvision_apply_teacache_to_native_video_prompt(
    prompt: dict[str, Any],
    req: dict[str, Any],
    object_info: dict[str, Any],
) -> dict[str, Any]:
    settings = _spellvision_teacache_settings(req)
    if not settings["enabled"] or settings["profile"] == "off":
        req["teacache_applied"] = False
        req["teacache_available"] = bool(_spellvision_teacache_class(object_info))
        req["teacache_node_count"] = 0
        return prompt

    tea_class = _spellvision_teacache_class(object_info)
    req["teacache_available"] = bool(tea_class)
    if not tea_class:
        req["teacache_applied"] = False
        req["teacache_node_count"] = 0
        req["teacache_warning"] = "ComfyUI-TeaCache node is not installed; generated without TeaCache."
        return prompt

    if any(str(node.get("class_type") or "").lower().replace("_", "") == str(tea_class).lower().replace("_", "") for node in prompt.values() if isinstance(node, dict)):
        req["teacache_applied"] = True
        req["teacache_node_count"] = sum(1 for node in prompt.values() if isinstance(node, dict) and str(node.get("class_type") or "").lower().replace("_", "") == str(tea_class).lower().replace("_", ""))
        return prompt

    model_node_ids: list[str] = []
    for node_id, node in list(prompt.items()):
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        if class_type in {"UNETLoader", "DiffusionModelLoader", "LoadDiffusionModel"}:
            model_node_ids.append(str(node_id))

    if not model_node_ids:
        req["teacache_applied"] = False
        req["teacache_node_count"] = 0
        req["teacache_warning"] = "TeaCache enabled, but no native diffusion model loader was found in the generated prompt."
        return prompt

    allowed = _comfy_class_inputs(object_info, tea_class)
    inserted: dict[str, str] = {}
    for model_node_id in model_node_ids:
        tea_node_id = f"tc_{model_node_id}"
        while tea_node_id in prompt:
            tea_node_id = f"tc_{tea_node_id}"
        inputs: dict[str, Any] = {}
        _set_if_allowed(inputs, allowed, ("model",), [model_node_id, 0])
        _set_if_allowed(inputs, allowed, ("model_type",), _spellvision_teacache_model_type(object_info, tea_class, str(settings["model_type"])))
        _set_if_allowed(inputs, allowed, ("rel_l1_thresh",), float(settings["rel_l1_thresh"]))
        _set_if_allowed(inputs, allowed, ("start_percent",), float(settings["start_percent"]))
        _set_if_allowed(inputs, allowed, ("end_percent",), float(settings["end_percent"]))
        _set_if_allowed(inputs, allowed, ("cache_device",), str(settings["cache_device"]))
        _sv_set_default_required_inputs(inputs, object_info, tea_class)
        _add_node(prompt, tea_node_id, tea_class, inputs)
        inserted[model_node_id] = tea_node_id

    # Route downstream model consumers through TeaCache. Leave the TeaCache node's own input untouched.
    for node_id, node in prompt.items():
        if str(node_id).startswith("tc_") or not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for input_name, value in list(inputs.items()):
            if not (isinstance(value, list) and len(value) >= 2):
                continue
            source_id = str(value[0])
            tea_node_id = inserted.get(source_id)
            if not tea_node_id:
                continue
            if input_name not in {"model", "diffusion_model"}:
                continue
            inputs[input_name] = [tea_node_id, value[1]]

    req["teacache_applied"] = bool(inserted)
    req["teacache_node_count"] = len(inserted)
    req["teacache_warning"] = None
    req["video_acceleration_backend"] = "ComfyUI-TeaCache"
    return prompt
# --- END SPELLVISION SPRINT 13 PASS 2 TEACACHE WORKER HELPERS ---
'''


def _patch_function_returns(text: str, function_names: tuple[str, ...]) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    replacements = 0
    target_names = set(function_names)
    i = 0
    while i < len(lines):
        matched_name = None
        for name in target_names:
            if lines[i].startswith(f"def {name}("):
                matched_name = name
                break
        if matched_name is None:
            i += 1
            continue

        j = i + 1
        while j < len(lines):
            if lines[j].startswith("def ") or lines[j].startswith("class "):
                break
            if lines[j].strip() == "return prompt":
                newline = "\n" if lines[j].endswith("\n") else ""
                lines[j] = "    return _spellvision_apply_teacache_to_native_video_prompt(prompt, req, object_info)" + newline
                replacements += 1
            j += 1
        i = j

    return "".join(lines), replacements

def patch_worker(project: Path) -> None:
    path = project / "python" / "worker_service.py"
    if not path.exists():
        print(f"Skipped worker_service.py; not found: {path}")
        return

    text = read_text(path)
    if f"{MARKER} WORKER HELPERS" in text and "_spellvision_apply_teacache_to_native_video_prompt(prompt, req, object_info)" in text:
        print("worker_service.py already has TeaCache worker patch")
        return

    backup_once(path)

    if f"{MARKER} WORKER HELPERS" not in text:
        anchor = "\nclass WorkerTCPHandler(socketserver.StreamRequestHandler):"
        if anchor not in text:
            raise RuntimeError("Could not find WorkerTCPHandler anchor in worker_service.py")
        text = text.replace(anchor, "\n\n" + TEACACHE_HELPER_BLOCK + anchor, 1)

    text, replacements = _patch_function_returns(text, ("_build_native_wan_core_video_prompt", "_build_native_wan_split_video_prompt"))
    if replacements == 0:
        print("Warning: no native WAN prompt function returns were patched. TeaCache helper was still installed.")

    metadata_anchor = "    queue_metadata_write(metadata_output, data)\n"
    metadata_insertion = "    if isinstance(req, dict):\n        data.update(_spellvision_teacache_metadata(req))\n"
    if metadata_anchor in text and metadata_insertion.strip() not in text:
        text = text.replace(metadata_anchor, metadata_insertion + metadata_anchor, 1)

    write_text(path, text)
    print(f"Patched worker_service.py: {path} ({replacements} native prompt return path(s) routed through TeaCache postprocessor)")


def main() -> int:
    if len(sys.argv) > 2:
        print("Usage: python apply_sprint13_pass2_teacache.py [project_root]")
        return 2

    project = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else Path.cwd().resolve()
    if not (project / "qt_ui").exists() or not (project / "python").exists():
        print(f"Project root does not look like SpellVision: {project}")
        return 1

    patch_catalog(project)
    patch_header(project)
    patch_image_generation_cpp(project)
    patch_worker(project)

    print("\nNext checks:")
    print("  python -m py_compile .\\python\\worker_service.py")
    print("  python -m py_compile .\\python\\worker_client.py")
    print("  .\\scripts\\dev\\run_ui.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
