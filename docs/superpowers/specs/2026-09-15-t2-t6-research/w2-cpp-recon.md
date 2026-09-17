# W2 recon — verbatim code map (SpellVision, READ-ONLY)

Repo: `C:\Users\xXste\Code_Projects\SpellVision`. All paths absolute. All snippets verbatim from HEAD (`30d6062`).

---

## 1. The operating-point application path

### 1a. `applyOptimalVideoSamplingDefaults` — `C:\Users\xXste\Code_Projects\SpellVision\qt_ui\ImageGenerationPage_video.cpp:219-278`

```cpp
void ImageGenerationPage::applyOptimalVideoSamplingDefaults()
{
    if (!isVideoMode())
        return;

    const QString family = resolvedVideoFamilyToken().trimmed().toLower();
    // Community-validated operating points; user can still edit Advanced knobs afterward.
    if (family.startsWith(QStringLiteral("wan"))) {
        if (wanSplitCombo_)
            selectComboValue(wanSplitCombo_, QStringLiteral("auto"));
        if (highNoiseStepsSpin_)
            highNoiseStepsSpin_->setValue(14);
        if (lowNoiseStepsSpin_)
            lowNoiseStepsSpin_->setValue(14);
        if (splitStepSpin_)
            splitStepSpin_->setValue(14);
        if (highNoiseShiftSpin_)
            highNoiseShiftSpin_->setValue(5.0);
        if (lowNoiseShiftSpin_)
            lowNoiseShiftSpin_->setValue(5.0);
        if (sampling_->stepsSpin())
            sampling_->stepsSpin()->setValue(28); // high+low when split
        if (sampling_->cfgSpin())
            sampling_->cfgSpin()->setValue(5.0);
        if (sampling_->videoSamplerCombo()) {
            if (!selectComboValue(sampling_->videoSamplerCombo(), QStringLiteral("uni_pc")))
                selectComboValue(sampling_->videoSamplerCombo(), QStringLiteral("euler"));
        }
        if (sampling_->videoSchedulerCombo())
            selectComboValue(sampling_->videoSchedulerCombo(), QStringLiteral("simple"));
        if (readinessHintLabel_)
            readinessHintLabel_->setHint(
                QStringLiteral("WAN defaults applied: split auto · 14/14 · shift 5.0 (editable in Advanced)."));
    } else if (family.startsWith(QStringLiteral("ltx"))) {
        // Full ltx-2.3-22b wants 25–40 steps, CFG 3–5 (native AV path).
        if (sampling_->stepsSpin())
            sampling_->stepsSpin()->setValue(30);
        if (sampling_->cfgSpin())
            sampling_->cfgSpin()->setValue(3.5);
        if (sampling_->videoSamplerCombo())
            selectComboValue(sampling_->videoSamplerCombo(), QStringLiteral("euler"));
        if (frameCountSpin_) {
            // Snap toward (N×8)+1 without fighting user too hard on first pick.
            const int f = frameCountSpin_->value();
            if (f < 49)
                frameCountSpin_->setValue(49);
        }
        if (readinessHintLabel_)
            readinessHintLabel_->setHint(
                QStringLiteral("LTX defaults applied: 30 steps · CFG 3.5 · native AV (editable in Advanced)."));
    } else if (family == QStringLiteral("flux3")) {
        if (fpsSpin_)
            fpsSpin_->setValue(24);
        if (frameCountSpin_ && frameCountSpin_->value() < 120)
            frameCountSpin_->setValue(120);
        if (readinessHintLabel_)
            readinessHintLabel_->setHint(
                QStringLiteral("FLUX.3 BFL API preview: hosted, paid, audio enabled · BFL_API_KEY required."));
    }
    updateVideoStackModeUi();
}
```

Note for the plan: this function is **video-only** (`if (!isVideoMode()) return;`) and keys entirely off `resolvedVideoFamilyToken()` — there is no per-model branch anywhere in it. `readinessHintLabel_->setHint(...)` here is the existing precedent for a one-line "what was applied" caption (see §7).

### 1b. `applySimpleOperatingPointDefaults` — `qt_ui\ImageGenerationPage_video.cpp:281-286`

```cpp
void ImageGenerationPage::applySimpleOperatingPointDefaults()
{
    // Simple starts on the family table. Advanced keeps last-chose knobs.
    updateOperatingPointSelector();
    applyOptimalVideoSamplingDefaults();
}
```

Call sites (only three):
- `qt_ui\ImageGenerationPage_catalog.cpp:1008` — inside `updateDisclosure`, `if (!advanced) applySimpleOperatingPointDefaults();`
- `qt_ui\ImageGenerationPage_catalog.cpp:2140` — inside `restoreSnapshot`, `if (!restoreLastSampling) applySimpleOperatingPointDefaults();`

### 1c. `updateOperatingPointSelector` — `qt_ui\ImageGenerationPage_video.cpp:1068-1156`

```cpp
void ImageGenerationPage::updateOperatingPointSelector()
{
    if (!operatingPointCard_ || !operatingPointButtonRow_ || !operatingPointGroup_)
        return;

    const QString family = isVideoMode()
        ? resolvedVideoFamilyForSelector()
        : modelFamilyByValue_.value(selectedModelPath_).trimmed().toLower();
    applyFamilySamplingChoices(family);
    QJsonArray points;
    QString defaultPoint;
    if (operatingPointsProvider_ && !family.isEmpty())
    {
        const QJsonObject table = operatingPointsProvider_(family);
        points = table.value(QStringLiteral("operating_points")).toArray();
        defaultPoint = table.value(QStringLiteral("default_operating_point")).toString();
    }
    if (family == QStringLiteral("krea2"))
        defaultPoint = krea2OperatingPointForPath(selectedModelPath_);

    // >1 point -> show a selector; <=1 -> hide it entirely (nothing to choose).
    if (points.size() <= 1)
    {
        operatingPointCard_->setVisible(false);
        currentOperatingPoints_ = {};
        currentOperatingPoint_.clear();
        operatingPointFamily_.clear();
        if (family == QStringLiteral("krea2"))
        {
            const bool raw = defaultPoint == QStringLiteral("raw");
            if (sampling_->stepsSpin())
                sampling_->stepsSpin()->setValue(raw ? 52 : 8);
            if (sampling_->cfgSpin())
                sampling_->cfgSpin()->setValue(raw ? 3.5 : 1.0);
            if (sampling_->samplerCombo() && !selectComboValue(sampling_->samplerCombo(), QStringLiteral("er_sde")))
                selectComboByContains(sampling_->samplerCombo(), {QStringLiteral("er_sde")});
            if (sampling_->schedulerCombo() && !selectComboValue(sampling_->schedulerCombo(), QStringLiteral("simple")))
                selectComboByContains(sampling_->schedulerCombo(), {QStringLiteral("simple")});
        }
        return;
    }

    // Rebuild the buttons only when the family (hence the point set) changed.
    if (family != operatingPointFamily_ || operatingPointGroup_->buttons().size() != points.size())
    {
        for (QAbstractButton *b : operatingPointGroup_->buttons())
        {
            operatingPointGroup_->removeButton(b);
            b->deleteLater();
        }
        while (QLayoutItem *item = operatingPointButtonRow_->takeAt(0))
        {
            if (item->widget())
                item->widget()->deleteLater();
            delete item;
        }
        for (const QJsonValue &v : points)
        {
            const QJsonObject point = v.toObject();
            auto *btn = new QPushButton(operatingPointLabel(point), operatingPointCard_);
            btn->setObjectName(QStringLiteral("OperatingPointButton"));
            // Said at the creation site: an operating point is a chip, and this row is rebuilt on
            // every family change, so the role has to be set here rather than once at construction.
            spellvision::kit::setRole(btn, spellvision::style::Role::Chip);
            btn->setCheckable(true);
            btn->setCursor(Qt::PointingHandCursor);
            const QString name = point.value(QStringLiteral("name")).toString();
            btn->setProperty("opName", name);
            operatingPointGroup_->addButton(btn);
            operatingPointButtonRow_->addWidget(btn);
        }
        operatingPointButtonRow_->addStretch(1);
        operatingPointFamily_ = family;
        currentOperatingPoints_ = points;
        // Apply the default point so the visible controls immediately MATCH what will run (no hidden
        // state -- the whole point). The user picks Fast/Quality to switch; a manual control edit after
        // is their override, and re-picking a point resets it. Applies once per family change.
        const QString toSelect = defaultPoint.isEmpty()
                                     ? points.first().toObject().value(QStringLiteral("name")).toString()
                                     : defaultPoint;
        applyOperatingPoint(toSelect);
    }
    else if (!defaultPoint.isEmpty())
    {
        applyOperatingPoint(defaultPoint);
    }

    operatingPointCard_->setVisible(advanced_);
}
```

**This is the one place in the codebase where image mode gets a family default at all** (`modelFamilyByValue_.value(selectedModelPath_)` branch at :1073-1075), and the only *model*-aware branch in it is the krea2 filename hack.

### 1d. `applyOperatingPoint` — `qt_ui\ImageGenerationPage_video.cpp:1174-1254`

```cpp
void ImageGenerationPage::applyOperatingPoint(const QString &name)
{
    QJsonObject point;
    for (const QJsonValue &v : currentOperatingPoints_)
    {
        if (v.toObject().value(QStringLiteral("name")).toString() == name)
        {
            point = v.toObject();
            break;
        }
    }
    if (point.isEmpty())
        return;

    currentOperatingPoint_ = name;
    const QJsonObject params = point.value(QStringLiteral("params")).toObject();

    // Write the bundle into the VISIBLE controls -- the user sees exactly what will run, no hidden state.
    if (params.contains(QStringLiteral("steps")) && sampling_->stepsSpin())
        sampling_->stepsSpin()->setValue(params.value(QStringLiteral("steps")).toInt());
    if (params.contains(QStringLiteral("cfg")) && sampling_->cfgSpin())
        sampling_->cfgSpin()->setValue(params.value(QStringLiteral("cfg")).toDouble());
    // Video routes the sampler/scheduler through the VIDEO combos (the ones actually shown + sent for
    // video); image mode uses the image combos. Operating points are video-only today, but guard both.
    QComboBox *samplerTarget = (isVideoMode() && sampling_->videoSamplerCombo()) ? sampling_->videoSamplerCombo() : sampling_->samplerCombo();
    QComboBox *schedulerTarget = (isVideoMode() && sampling_->videoSchedulerCombo()) ? sampling_->videoSchedulerCombo() : sampling_->schedulerCombo();
    if (params.contains(QStringLiteral("sampler")) && samplerTarget)
    {
        const QString s = params.value(QStringLiteral("sampler")).toString();
        if (!s.isEmpty() && !selectComboValue(samplerTarget, s))
            selectComboByContains(samplerTarget, {s});
    }
    if (params.contains(QStringLiteral("scheduler")) && schedulerTarget)
    {
        const QString s = params.value(QStringLiteral("scheduler")).toString();
        if (!s.isEmpty() && !selectComboValue(schedulerTarget, s))
            selectComboByContains(schedulerTarget, {s});
    }
    if (params.contains(QStringLiteral("shift")))
    {
        const double shift = params.value(QStringLiteral("shift")).toDouble();
        if (highNoiseShiftSpin_)
            highNoiseShiftSpin_->setValue(shift);
        if (lowNoiseShiftSpin_)
            lowNoiseShiftSpin_->setValue(shift);
    }

    // LoRA: Fast populates the VISIBLE stack with the declared accel LoRAs (so the user sees what they
    // got -- unlike the API path's silent inject); Quality removes the accel LoRAs the selector added
    // and leaves user-added content LoRAs alone.
    removeOperatingPointLoras();
    const QJsonObject lora = point.value(QStringLiteral("lora")).toObject();
    if (lora.value(QStringLiteral("accel")).toBool(false))
    {
        // The pair is per TASK VARIANT. The dual-noise builder serves t2v and i2v from one graph and
        // already refuses a mixed expert pair as off-model; the accel LoRAs are the same model choice
        // one layer down, and this page used to add the t2v pair on an i2v job. There is deliberately
        // no flat high/low fallback: a point that declares no pair for this command adds nothing here
        // and the worker refuses the render, rather than either side quietly borrowing the other
        // variant's weights.
        const QString task = (mode_ == Mode::ImageToVideo) ? QStringLiteral("i2v") : QStringLiteral("t2v");
        const QJsonObject pair = lora.value(task).toObject();
        const int before = loraStack_.size();
        for (const QString &key : {QStringLiteral("high"), QStringLiteral("low")})
        {
            const QString fn = pair.value(key).toString().trimmed();
            if (fn.isEmpty())
                continue;
            if (!tryAddLoraByCandidate({fn, QFileInfo(fn).completeBaseName()}, 1.0, true))
                addLoraToStack(fn, fn); // fallback: add by filename even if the catalog match missed
        }
        for (int i = before; i < loraStack_.size(); ++i)
            operatingPointLoras_.push_back(loraStack_.at(i).value);
    }

    // Reflect the selection on the buttons + recompute readiness/preview chips.
    if (operatingPointGroup_)
        for (QAbstractButton *b : operatingPointGroup_->buttons())
            b->setChecked(b->property("opName").toString() == name);
    scheduleUiRefresh(0);
}
```

Fields this path writes today: `steps`, `cfg`, `sampler`, `scheduler`, `shift` (→ both `highNoiseShiftSpin_` and `lowNoiseShiftSpin_`), plus accel LoRAs. It writes **no** width/height/frames/fps/clip_skip — those are W2-new.

### 1e. The krea2 filename hack — `qt_ui\ImageGenerationPage_units.h:171-177`

```cpp
inline QString krea2OperatingPointForPath(const QString &path)
{
    const QString hay = QDir::fromNativeSeparators(path).toLower();
    if (hay.contains(QStringLiteral("turbo")))
        return QStringLiteral("turbo");
    return QStringLiteral("raw");
}
```

Its sole call site is `qt_ui\ImageGenerationPage_video.cpp:1085-1086`:

```cpp
    if (family == QStringLiteral("krea2"))
        defaultPoint = krea2OperatingPointForPath(selectedModelPath_);
```

...consumed by the `points.size() <= 1` branch at `:1089-1106` (quoted in full in §1c above). This is **the existing, hardcoded, filename-sniffing precedent for per-model defaults** — W2 replaces it. Note the sibling helper `operatingPointLabel` at `ImageGenerationPage_units.h:160-169`.

---

## 2. How a checkpoint change reaches that code

There is **no `onCheckpointChanged` slot**. The single funnel is `setSelectedModel`.

### 2a. The funnel — `qt_ui\ImageGenerationPage_catalog.cpp:353-376`

```cpp
void ImageGenerationPage::setSelectedModel(const QString &value, const QString &display)
{
    const QString remapped = remapWanTaskVariantPath(value);
    const bool modelChanged = remapped.compare(selectedModelPath_, Qt::CaseInsensitive) != 0;
    const bool taskRemapped = remapped.compare(value.trimmed(), Qt::CaseInsensitive) != 0;
    selectedModelPath_ = remapped;
    selectedModelDisplay_ = display.trimmed().isEmpty() ? resolveSelectedModelDisplay(selectedModelPath_) : display.trimmed();
    if (modelChanged && taskRemapped)
        selectedModelDisplay_ = resolveSelectedModelDisplay(selectedModelPath_);
    if (taskRemapped)
        lastAutoPopulatedModel_.clear();
    if (modelChanged)
        clearGenerationError();
    refreshSelectedModelUi();
    updatePrimaryActionAvailability();
    // A2: resolve the compatible component stack OFF the current signal-handler stack. The worker
    // round-trip runs a nested event loop; calling it inline from a combo-change handler re-enters
    // the UI (with the combo popup possibly still open) and crashes. singleShot(0) runs it clean.
    if (modelChanged && isVideoMode())
        populateVideoComponentControls();
    if (modelChanged && isVideoMode() && componentStackResolver_ && !selectedModelPath_.trimmed().isEmpty())
        QTimer::singleShot(0, this, [this]() { resolveAndApplyVideoComponents(); });
    else if (modelChanged)
        updateOperatingPointSelector();
}
```

**This `else if (modelChanged) updateOperatingPointSelector();` at :374-375 is W2's primary hook point.** Note the `QTimer::singleShot(0, ...)` deferral comment — the async-worker-re-entrancy hazard W2 must respect.

The video branch lands in `resolveAndApplyVideoComponents` — `qt_ui\ImageGenerationPage_catalog.cpp:378-385`:

```cpp
void ImageGenerationPage::resolveAndApplyVideoComponents()
{
    maybeAutoPopulateVideoComponents();            // worker resolve (deferred -> clean stack)
    syncVideoComponentControlsFromSelectedStack(); // apply the stored results + constrain the menus
    updateAssetIntelligenceUi();                   // surface T3 (missing required) in readiness
    updateOperatingPointSelector();                // the resolved family may have changed -> refresh
}
```

### 2b. All callers of `setSelectedModel`

| file:line | trigger |
|---|---|
| `qt_ui\ImageGenerationPage.cpp:1554` | `connect(clearModelButton_, &QPushButton::clicked, this, [this]() { setSelectedModel(QString(), QString()); });` |
| `qt_ui\ImageGenerationPage.cpp:1705` | video primary model combo `currentIndexChanged` (below) |
| `qt_ui\ImageGenerationPage_catalog.cpp:235,243,245,248` | `refreshModelCatalog` re-seat / recents fallback |
| `qt_ui\ImageGenerationPage_catalog.cpp:332` | `showCheckpointPicker` (the Browse dialog) |
| `qt_ui\ImageGenerationPage_catalog.cpp:499` | `applyModelHandoff` |
| `qt_ui\ImageGenerationPage_catalog.cpp:1841` | reset |
| `qt_ui\ImageGenerationPage_catalog.cpp:2073` | `restoreSnapshot` |
| `qt_ui\ImageGenerationPage_video.cpp:378` | `applyVideoFamilyCheckpointIfNeeded` |

### 2c. The image-mode picker — `qt_ui\ImageGenerationPage_catalog.cpp:318-335`

```cpp
void ImageGenerationPage::showCheckpointPicker()
{
    QVector<CatalogEntry> checkpoints;
    checkpoints.reserve(modelDisplayByValue_.size());
    for (auto it = modelDisplayByValue_.constBegin(); it != modelDisplayByValue_.constEnd(); ++it)
        checkpoints.push_back({it.value(), it.key()});

    CatalogPickerDialog dialog(isVideoMode() ? QStringLiteral("Choose Video Model Stack") : QStringLiteral("Choose Checkpoint"),
                                checkpoints,
                                selectedModelPath_,
                                isVideoMode() ? QStringLiteral("image_generation/recent_video_model_stacks") : QStringLiteral("image_generation/recent_checkpoints"),
                                this);
    if (dialog.exec() != QDialog::Accepted)
        return;

    setSelectedModel(dialog.selectedValue(), dialog.selectedDisplay());
    persistRecentSelection(isVideoMode() ? QStringLiteral("image_generation/recent_video_model_stacks") : QStringLiteral("image_generation/recent_checkpoints"), dialog.selectedValue());
    scheduleUiRefresh(0);
}
```

Wired at `qt_ui\ImageGenerationPage.cpp:1553-1555`:

```cpp
    connect(browseModelButton_, &QPushButton::clicked, this, &ImageGenerationPage::showCheckpointPicker);
    connect(clearModelButton_, &QPushButton::clicked, this, [this]() { setSelectedModel(QString(), QString()); });
    connect(refreshModelsButton_, &QPushButton::clicked, this, &ImageGenerationPage::refreshModelCatalog);
```

### 2d. The video primary-model combo — `qt_ui\ImageGenerationPage.cpp:1699-1710`

```cpp
    connect(videoPrimaryModelCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this, [this]() {
        if (syncingVideoComponentControls_ || !isVideoMode())
            return;
        const QString value = videoComponentValue(videoPrimaryModelCombo_);
        if (!value.trimmed().isEmpty() && value.compare(selectedModelPath_, Qt::CaseInsensitive) != 0)
        {
            setSelectedModel(value, comboDisplayValue(videoPrimaryModelCombo_));
            persistRecentSelection(QStringLiteral("image_generation/recent_video_model_stacks"), value);
            return;
        }
        applyVideoComponentOverridesToSelectedStack();
    });
```

### 2e. The video **family** combo — `qt_ui\ImageGenerationPage.cpp:608-617`

```cpp
        connect(videoFamilyCombo_, qOverload<int>(&QComboBox::currentIndexChanged), this, [this]() {
            updateVideoFamilyUi();
            // The stack-mode UI consults resolvedVideoFamily() to decide
            // whether to show WAN advanced rows, so refresh it too.
            updateVideoStackModeUi();
            applyVideoFamilyCheckpointIfNeeded();
            updateOperatingPointSelector(); // family changed -> re-render the fast/quality selector
            applyOptimalVideoSamplingDefaults();
            scheduleUiRefresh(0);
        });
```

### 2f. `modelFamilyByValue_` — where the family string comes from

Populated once per catalog scan, `qt_ui\ImageGenerationPage_catalog.cpp:215-229`:

```cpp
    modelFamilyByValue_.clear();
    modelModalityByValue_.clear();
    modelRoleByValue_.clear();
    modelNoteByValue_.clear();
    modelStackByValue_.clear();
    for (const CatalogEntry &entry : modelEntries)
    {
        modelDisplayByValue_.insert(entry.value, entry.display);
        modelFamilyByValue_.insert(entry.value, entry.family);
        ...
    }
```

Declared `QMap<QString, QString> modelFamilyByValue_;` at `qt_ui\ImageGenerationPage.h:349`. This is the `family` value a `model_recommended_settings` request should carry alongside `selectedModelPath_`.

### 2g. Commit 380d8dd — "reapply family operating point on same-family checkpoint change"

```
commit 380d8ddfd4160df34a3c2ada4e49776e31e88c55
Author: MasterDevopper <thedevops112th@gmail.com>
Date:   Wed Sep 9 13:28:42 2026 -0400

    fix(ui): reapply family operating point on same-family checkpoint change

    Persisted 60-step Krea2 leftover stuck because applyOperatingPoint
    only ran when the family string changed. Table default is 52.
```

Diff, `qt_ui/ImageGenerationPage_video.cpp` (then-lines ~1000):

```diff
@@ -1000,8 +1000,7 @@ void ImageGenerationPage::updateOperatingPointSelector()
                                      : defaultPoint;
         applyOperatingPoint(toSelect);
     }
-    else if (family == QStringLiteral("krea2") && !defaultPoint.isEmpty()
-             && defaultPoint != currentOperatingPoint_)
+    else if (!defaultPoint.isEmpty())
     {
         applyOperatingPoint(defaultPoint);
     }
```

It also added the pinning test in `tests/test_first_run_honesty.py` (quoted in §6).

---

## 3. The async worker-request pattern in MainWindow

### 3a. `fetchOperatingPointsAsync` — `C:\Users\xXste\Code_Projects\SpellVision\qt_ui\MainWindow.cpp:3361-3421` (in full)

```cpp
void MainWindow::fetchOperatingPointsAsync(std::function<void()> completion)
{
    if (operatingPointsFetched_)
    {
        if (completion)
            completion();
        return;
    }
    if (completion)
        operatingPointsFetchWaiters_.push_back(std::move(completion));
    if (operatingPointsFetchInFlight_)
        return;

    operatingPointsFetchInFlight_ = true;
    QJsonObject request;
    request.insert(QStringLiteral("command"), QStringLiteral("video_family_contracts"));
    sendWorkerRequestAsync(
        request,
        [this](const QJsonObject &response, const QString &, bool startedOk) {
            operatingPointsFetchInFlight_ = false;
            if (startedOk && response.value(QStringLiteral("ok")).toBool(false))
            {
                operatingPointsByFamily_.clear();
            const QJsonObject families = response.value(QStringLiteral("families")).toObject();
            for (auto it = families.constBegin(); it != families.constEnd(); ++it)
            {
                const QJsonObject fam = it.value().toObject();
                QJsonObject entry;
                entry.insert(QStringLiteral("operating_points"), fam.value(QStringLiteral("operating_points")));
                entry.insert(QStringLiteral("default_operating_point"), fam.value(QStringLiteral("default_operating_point")));
                entry.insert(QStringLiteral("samplers"), fam.value(QStringLiteral("samplers")));
                entry.insert(QStringLiteral("schedulers"), fam.value(QStringLiteral("schedulers")));
                entry.insert(QStringLiteral("default_sampler"), fam.value(QStringLiteral("default_sampler")));
                entry.insert(QStringLiteral("default_scheduler"), fam.value(QStringLiteral("default_scheduler")));
                operatingPointsByFamily_.insert(it.key().toLower(), entry);
            }
            const QJsonObject sampling = response.value(QStringLiteral("sampling")).toObject();
            for (auto sit = sampling.constBegin(); sit != sampling.constEnd(); ++sit)
            {
                const QString skey = sit.key().toLower();
                QJsonObject entry = operatingPointsByFamily_.value(skey);
                const QJsonObject block = sit.value().toObject();
                entry.insert(QStringLiteral("samplers"), block.value(QStringLiteral("samplers")));
                entry.insert(QStringLiteral("schedulers"), block.value(QStringLiteral("schedulers")));
                entry.insert(QStringLiteral("default_sampler"), block.value(QStringLiteral("default_sampler")));
                entry.insert(QStringLiteral("default_scheduler"), block.value(QStringLiteral("default_scheduler")));
                operatingPointsByFamily_.insert(skey, entry);
            }
                operatingPointsFetched_ = true;
            }

            auto waiters = std::move(operatingPointsFetchWaiters_);
            operatingPointsFetchWaiters_.clear();
            for (auto &waiter : waiters)
            {
                if (waiter)
                    waiter();
            }
        },
        12000);
}
```

(The odd indentation on the inner two `for` loops is verbatim in the source.)

### 3b. `operatingPointsForFamily` — `qt_ui\MainWindow.cpp:3423-3429` (in full)

```cpp
QJsonObject MainWindow::operatingPointsForFamily(const QString &family) const
{
    const QString key = family.trimmed().toLower();
    if (key.isEmpty())
        return {};
    return operatingPointsByFamily_.value(key);
}
```

### 3c. Declarations — `qt_ui\MainWindow.h:261-272`

```cpp
    // Phase 3b: the fast/quality operating-point table for a video family. A STATIC table -- fetched
    // once from the video_family_contracts snapshot and cached, so the cockpit can render its selector
    // with no per-change round-trip. Returns {default_operating_point, operating_points:[...]} ({} on
    // an unknown family / worker down -> the cockpit hides the selector).
    void fetchOperatingPointsAsync(std::function<void()> completion = {});
    QJsonObject operatingPointsForFamily(const QString &family) const;
```

### 3d. Cache members — `qt_ui\MainWindow.h:482-486`

```cpp
    // Phase 3b operating-point table cache (single-flight async fetch from video_family_contracts).
    QHash<QString, QJsonObject> operatingPointsByFamily_;
    bool operatingPointsFetched_ = false;
    bool operatingPointsFetchInFlight_ = false;
    std::vector<std::function<void()>> operatingPointsFetchWaiters_;
```

**W2 caveat:** these four members express *one* global single-flight. A per-model cache needs a keyed equivalent (`QHash<QString, QJsonObject> recommendedByModelPath_` + per-key in-flight set + per-key waiter lists), since each model path is its own request.

### 3e. How the page is told the answer arrived — `qt_ui\MainWindow.cpp:2487-2496`

```cpp
    // Phase 3b: the fast/quality operating-point table provider (lazy cached fetch).
    (*slot)->setOperatingPointsProvider(
        [this](const QString &family) { return operatingPointsForFamily(family); });
    const QPointer<ImageGenerationPage> pageGuard(*slot);
    fetchOperatingPointsAsync([pageGuard]() {
        if (pageGuard)
            pageGuard->refreshOperatingPointSelector();
    });
    pageStack_->addWidget(*slot);
    modePages_.insert(modeId, *slot);
    connectGenerationPage(*slot, modeId);
```

Inside `MainWindow::ensureGenerationPageBuilt(const QString &modeId)` (`MainWindow.cpp:2465-...`). The pattern is: **a synchronous `std::function` provider that reads the cache** + **an async fetch whose completion calls a `refresh…()` slot on a `QPointer`-guarded page**.

The page side — `qt_ui\ImageGenerationPage_video.cpp:693-702`:

```cpp
void ImageGenerationPage::setOperatingPointsProvider(std::function<QJsonObject(const QString &)> provider)
{
    operatingPointsProvider_ = std::move(provider);
    updateOperatingPointSelector();
}

void ImageGenerationPage::refreshOperatingPointSelector()
{
    updateOperatingPointSelector();
}
```

Declared `qt_ui\ImageGenerationPage.h:134-137`:

```cpp
    // Phase 3b: MainWindow wires this to the cached fast/quality table. Returns
    // {default_operating_point, operating_points:[...]} for a video family ({} -> no selector).
    void setOperatingPointsProvider(std::function<QJsonObject(const QString &family)> provider);
    void refreshOperatingPointSelector();
```

and the member at `qt_ui\ImageGenerationPage.h:363-372`:

```cpp
    // Phase 3b operating-point selector state.
    std::function<QJsonObject(const QString &)> operatingPointsProvider_;
    QFrame *operatingPointCard_ = nullptr;
    QHBoxLayout *operatingPointButtonRow_ = nullptr;
    QButtonGroup *operatingPointGroup_ = nullptr;
    QJsonArray currentOperatingPoints_;      // the shipped points for the current family
    QString operatingPointFamily_;           // the family the selector is currently built for
    QString currentOperatingPoint_;          // the selected point's name (sent on the request)
    QStringList operatingPointLoras_;         // accel LoRA values the selector added (so Quality removes only those)
```

### 3f. Transport: `sendWorkerRequestAsync` — `qt_ui\MainWindow.cpp:3431-3444` (head)

```cpp
void MainWindow::sendWorkerRequestAsync(
    const QJsonObject &request,
    std::function<void(const QJsonObject &response, const QString &stderrText, bool startedOk)> completion,
    int timeoutMs)
{
    // Native socket for one-shot control commands -- the whole reason worker_client.py was spawned
    // is normalization this request does not need. ~78ms of CPython start per call, on a 1.8s poll
    // timer, for a protocol that is one JSON line each way. Streaming commands still take the
    // subprocess route below.
    if (spellvision::workers::WorkerSocketClient::canHandle(request))
    {
        spellvision::workers::WorkerSocketClient::send(this, request, timeoutMs, std::move(completion));
        return;
    }
```

So: **WorkerSocketClient (native TCP) for any non-streaming `{"command": ...}` request**; `QProcess python/worker_client.py` is the fallback (rest of function, `MainWindow.cpp:3445-3530+`). `model_recommended_settings` is non-streaming and carries `command`, so it takes the socket path.

`WorkerSocketClient::canHandle` — `qt_ui\workers\WorkerSocketClient.cpp:78-90`:

```cpp
bool WorkerSocketClient::canHandle(const QJsonObject &request)
{
    // An "action"-shaped request would need worker_client.py's normalize_outbound_request to turn
    // it into a command. No C++ call site builds one, but guard rather than assume.
    if (request.contains(QStringLiteral("action")))
        return false;

    const QString command = commandOf(request);
    if (command.isEmpty())
        return false;

    return !isStreamingCommand(command);
}
```

Header contract — `qt_ui\workers\WorkerSocketClient.h`:

```cpp
    // Mirrors the completion signature the QProcess path already hands its callers, so this is a
    // drop-in swap: `startedOk` means "the transport came up" (socket connected) exactly as it
    // previously meant "the process started".
    using Completion =
        std::function<void(const QJsonObject &response, const QString &diagnostics, bool startedOk)>;
...
    // Sends `request` and invokes `completion` exactly once (or twice if the first reply is
    // auth_error and retryAttempt is 0). `context` owns the socket, so a destroyed context
    // cancels the call. Safe to invoke from the GUI thread; never blocks.
    static void send(QObject *context, const QJsonObject &request, int timeoutMs, Completion completion);
```

### 3g. The wire contract for `model_recommended_settings` — `docs\SPELLVISION_WORKER_PROTOCOL.md:367-400`

```json
{
  "command": "model_recommended_settings",
  "path": "D:/AI_ASSETS/models/checkpoints/krea2_base.safetensors",
  "family": "krea2"
}
```
```json
{
  "type": "model_recommended_settings",
  "ok": true,
  "path": "D:/AI_ASSETS/models/checkpoints/krea2_base.safetensors",
  "family": "krea2",
  "settings": {
    "steps": {
      "value": 28,
      "provenance": "table:family-default",
      "confidence": 1.0,
      "n": null,
      "total": null
    }
  },
  "warnings": []
}
```

Field vocabulary — `python\model_intelligence\recommended.py:36-39`:

```python
FIELDS = (
    "steps", "cfg", "guidance", "shift", "sampler", "scheduler", "clip_skip",
    "width", "height", "frames", "fps", "lora_strength", "prompt_prefix",
)
```

Provenance ranking (best→worst) — `python\model_intelligence\recommended.py:~20-32`:

```python
    "user",
    "site:image-meta-mode",
    "site:trainedWords",
    "card:frontmatter",
    "card:snippet-regex",
    "card:prose-regex",
    "table:family-default",
)

_RANK = {name: index for index, name in enumerate(PROVENANCE_ORDER)}
```

Two blockers the plan must schedule (documented at `docs\SPELLVISION_WORKER_PROTOCOL.md:217` and `.superpowers\sdd\2026-09-16-w1-model-intelligence\task-9-brief.md:361-369`):
1. The command is currently classified `DIAGNOSTIC`, not `USER_FACING` — the ratchet requires the literal to appear in `qt_ui/` before promotion. W2 must move it.
2. It is `LOCAL_TRUSTED` only, and the protocol doc says: *"When W2/W5 promote them to USER_FACING, the caller must send its configured roots with every request."*

---

## 4. Where the sampling widgets live

`C:\Users\xXste\Code_Projects\SpellVision\qt_ui\generation\SamplingController.h` (in full):

```cpp
#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>

class QCheckBox;
class QComboBox;
class QDoubleSpinBox;
class QSpinBox;
class QWidget;

namespace spellvision::generation
{

class SamplingController final : public QObject
{
public:
    explicit SamplingController(QObject *parent = nullptr);

    void create(QWidget *parent);
    void applyFamilyChoices(const QJsonObject &table, bool videoMode);

    QComboBox *samplerCombo() const { return samplerCombo_; }
    QComboBox *schedulerCombo() const { return schedulerCombo_; }
    QComboBox *videoSamplerCombo() const { return videoSamplerCombo_; }
    QComboBox *videoSchedulerCombo() const { return videoSchedulerCombo_; }
    QSpinBox *stepsSpin() const { return stepsSpin_; }
    QDoubleSpinBox *cfgSpin() const { return cfgSpin_; }
    QSpinBox *seedSpin() const { return seedSpin_; }
    QCheckBox *seedRandomCheck() const { return seedRandomCheck_; }

    QString imageSampler() const;
    QString imageScheduler() const;
    QString videoSampler() const;
    QString videoScheduler() const;
    int steps() const;
    double cfg() const;
    int draftSeed() const;

private:
    QComboBox *samplerCombo_ = nullptr;
    QComboBox *schedulerCombo_ = nullptr;
    QComboBox *videoSamplerCombo_ = nullptr;
    QComboBox *videoSchedulerCombo_ = nullptr;
    QSpinBox *stepsSpin_ = nullptr;
    QDoubleSpinBox *cfgSpin_ = nullptr;
    QSpinBox *seedSpin_ = nullptr;
    QCheckBox *seedRandomCheck_ = nullptr;
};

} // namespace spellvision::generation
```

**There are no setters.** Every write today is done by the caller reaching through the raw-pointer accessors (`sampling_->stepsSpin()->setValue(...)`). W2 either continues that or adds typed setters here.

### "Auto" vs an explicit pick

Represented as a **combo item whose `userData` is the literal string `"auto"`, always at index 0**. `qt_ui\generation\SamplingController.cpp:56-62`:

```cpp
QComboBox *makeAutoCombo(QWidget *parent)
{
    auto *combo = new spellvision::widgets::ClickOnlyComboBox(parent);
    combo->addItem(QStringLiteral("Auto / family default"), QStringLiteral("auto"));
    configureCombo(combo);
    return combo;
}
```

Rebuild semantics — `SamplingController.cpp:64-84`:

```cpp
void rebuildSamplingCombo(QComboBox *combo, const QJsonArray &values, const QString &keep)
{
    if (!combo)
        return;
    const QString current = combo->currentData().toString();
    const QSignalBlocker blocker(combo);
    combo->clear();
    combo->addItem(QStringLiteral("Auto / family default"), QStringLiteral("auto"));
    for (const QJsonValue &value : values)
    {
        const QString name = value.toString().trimmed();
        if (name.isEmpty() || name.compare(QLatin1String("auto"), Qt::CaseInsensitive) == 0)
            continue;
        combo->addItem(name, name);
    }
    const QString want = current.isEmpty() ? keep : current;
    if (want.isEmpty())
        return;
    const int idx = combo->findData(want);
    if (idx >= 0)
        combo->setCurrentIndex(idx);
}
```

Read-out — `SamplingController.cpp:86-92`:

```cpp
QString comboValue(const QComboBox *combo, const QString &fallback = QStringLiteral("auto"))
{
    if (!combo)
        return fallback;
    const QString data = combo->currentData().toString().trimmed();
    return data.isEmpty() ? combo->currentText().trimmed() : data;
}
```

And the family-table application — `SamplingController.cpp:140-158`:

```cpp
void SamplingController::applyFamilyChoices(const QJsonObject &table, bool videoMode)
{
    const QJsonArray samplers = table.value(QStringLiteral("samplers")).toArray();
    const QJsonArray schedulers = table.value(QStringLiteral("schedulers")).toArray();
    // An empty table used to return early, leaving the PREVIOUS family's samplers on screen. So
    // switching to a family that offers no choice -- cogvideox returns an empty table, and it is
    // right to -- showed sdxl's list, and picking one of those sent a sampler this family has never
    // heard of. Rebuilding with nothing leaves "Auto / family default", which is the honest answer.
    //
    // The two lists are handled independently on purpose: LTX has samplers and DELIBERATELY no
    // schedulers, because both its templates drive sigmas through ManualSigmas. Requiring both to
    // be non-empty would put it back in the stale case it was carved out of.
    QComboBox *sampler = videoMode ? videoSamplerCombo_ : samplerCombo_;
    QComboBox *scheduler = videoMode ? videoSchedulerCombo_ : schedulerCombo_;
    rebuildSamplingCombo(sampler, samplers, table.value(QStringLiteral("default_sampler")).toString());
    rebuildSamplingCombo(scheduler, schedulers, table.value(QStringLiteral("default_scheduler")).toString());
}
```

**Important W2 constraint, stated in the existing test at `tests/cpp/test_sampling_controller.cpp`:** *"'Auto / family default' stays selected, and that is right: the concrete default belongs to the worker's resolver, so the cockpit showing a name would be a second place for it to live."* Making a per-model sampler the *visible selection* directly contradicts that comment — the plan needs to reconcile it (and the test `theComboKeepsAutoAndOffersTheFamilysSamplers` will need updating, since it asserts `QCOMPARE(controller_->imageSampler(), QStringLiteral("auto"))`).

Construction defaults — `SamplingController.cpp:99-139` (steps 28, cfg 7.0, seed random on):

```cpp
void SamplingController::create(QWidget *parent)
{
    samplerCombo_ = makeAutoCombo(parent);
    schedulerCombo_ = makeAutoCombo(parent);
    videoSamplerCombo_ = makeAutoCombo(parent);
    videoSchedulerCombo_ = makeAutoCombo(parent);

    stepsSpin_ = new QSpinBox(parent);
    stepsSpin_->setRange(1, 200);
    stepsSpin_->setValue(28);
    configureSpin(stepsSpin_);

    cfgSpin_ = new QDoubleSpinBox(parent);
    cfgSpin_->setDecimals(1);
    cfgSpin_->setSingleStep(0.5);
    cfgSpin_->setRange(0.0, 30.0);
    cfgSpin_->setValue(7.0);
    configureDouble(cfgSpin_);
```

**There is no clip-skip widget anywhere in `qt_ui/`.** Grep for `clipSkip|clip_skip|Clip Skip` returns only `python\model_intelligence\meta_parse.py:113-115` and `recommended.py:37`. W2 must create it.

---

## 5. Canvas size defaults

### 5a. `ensureCanvasSizeDefault` — `qt_ui\ImageGenerationPage_catalog.cpp:1650-1673` (in full)

```cpp
void ImageGenerationPage::ensureCanvasSizeDefault()
{
    if (!widthSpin_ || !heightSpin_)
        return;
    if (widthSpin_->value() >= 64 && heightSpin_->value() >= 64)
        return;

    // Two of the four generation pages opened with "Choose a canvas size to generate." on
    // 2026-09-02: the spin boxes start at 0 and only a preset or a saved value ever set them, so a
    // fresh I2I (even one reached through "Prep for I2I") and a fresh T2V were dead on arrival.
    QSize size = isVideoMode() ? QSize(832, 480) : QSize(1024, 1024);
    if (inputImageEdit_)
    {
        const QString inputPath = inputImageEdit_->text().trimmed();
        if (!inputPath.isEmpty())
        {
            const QSize source = QImageReader(inputPath).size();
            // Video keyframes stay within 1280 on the long edge; images within 2048.
            const QSize fromInput = snapCanvas(source, 16, isVideoMode() ? 1280 : 2048);
            if (fromInput.isValid())
                size = fromInput;
        }
    }
    widthSpin_->setValue(size.width());
    heightSpin_->setValue(size.height());
}
```

Its helper, `qt_ui\ImageGenerationPage_catalog.cpp:1638-1648`:

```cpp
{
    if (source.isEmpty())
        return {};
    if (source.width() > maxSide || source.height() > maxSide)
        source = source.scaled(maxSide, maxSide, Qt::KeepAspectRatio);
    const auto snap = [multiple](int v) { return std::max(64, qRound(double(v) / multiple) * multiple); };
    return QSize(snap(source.width()), snap(source.height()));
}
} // namespace
```

**Note the early-out at :1654-1655** — an explicit size is never overridden. W2's per-model `width`/`height` will collide with this rule; the plan must say which wins (the existing test `an_explicit_size_is_not_overridden_by_an_input` pins the input-image side of it).

The blocking readiness message it defends against, `qt_ui\ImageGenerationPage_catalog.cpp:1692-1693`:

```cpp
    if ((widthSpin_ && widthSpin_->value() < 64) || (heightSpin_ && heightSpin_->value() < 64))
        return QStringLiteral("Choose a canvas size to generate.");
```

### 5b. The width/height/frames/fps widgets — `qt_ui\ImageGenerationPage.cpp:1787-1812`

```cpp
    widthSpin_ = new QSpinBox(quickControlsCard);
    widthSpin_->setRange(0, 8192);
    widthSpin_->setSingleStep(64);
    widthSpin_->setSpecialValueText(QStringLiteral("—"));
    widthSpin_->setValue(0);
    configureSpinBox(widthSpin_);

    heightSpin_ = new QSpinBox(quickControlsCard);
    heightSpin_->setRange(0, 8192);
    heightSpin_->setSingleStep(64);
    heightSpin_->setSpecialValueText(QStringLiteral("—"));
    heightSpin_->setValue(0);
    configureSpinBox(heightSpin_);

    frameCountSpin_ = new QSpinBox(quickControlsCard);
    frameCountSpin_->setRange(1, 2400);
    frameCountSpin_->setSingleStep(8);
    frameCountSpin_->setValue(81);
    frameCountSpin_->setToolTip(QStringLiteral("Total frames requested from the video workflow."));
    configureSpinBox(frameCountSpin_);

    fpsSpin_ = new QSpinBox(quickControlsCard);
    fpsSpin_->setRange(1, 120);
    fpsSpin_->setValue(16);
    fpsSpin_->setToolTip(QStringLiteral("Playback frames per second for the generated clip."));
    configureSpinBox(fpsSpin_);
```

### 5c. Other writers of width/height

**The Aspect combo (this is the "Portrait / Landscape orientation control")** — `qt_ui\ImageGenerationPage.cpp:1909-1930`. There is **no** separate Portrait/Landscape toggle; orientation is expressed only through these five named presets, and the combo sits in Simple mode (it is deliberately *not* gated by `advanced_`, unlike `widthRow_`/`heightRow_`):

```cpp
    auto *aspectPresetCombo = new ClickOnlyComboBox(quickControlsCard);
    aspectPresetCombo->addItem(QStringLiteral("Custom"), QString());
    aspectPresetCombo->addItem(QStringLiteral("Portrait 768×1024"), QStringLiteral("768x1024"));
    aspectPresetCombo->addItem(QStringLiteral("Square 1:1"), QStringLiteral("1024x1024"));
    aspectPresetCombo->addItem(QStringLiteral("Portrait 3:4"), QStringLiteral("1024x1344"));
    aspectPresetCombo->addItem(QStringLiteral("Landscape 3:2"), QStringLiteral("1216x832"));
    aspectPresetCombo->addItem(QStringLiteral("Wide 16:9"), QStringLiteral("1344x768"));
    configureComboBox(aspectPresetCombo);
    connect(aspectPresetCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this, aspectPresetCombo](int index) {
        const QString value = aspectPresetCombo->itemData(index, Qt::UserRole).toString();
        if (value.isEmpty() || !widthSpin_ || !heightSpin_)
            return;

        const QStringList parts = value.split(QLatin1Char('x'));
        if (parts.size() != 2)
            return;

        widthSpin_->setValue(parts.at(0).toInt());
        heightSpin_->setValue(parts.at(1).toInt());
    });

    QWidget *aspectRow = makeStackedField(quickControlsCard, QStringLiteral("Aspect"), aspectPresetCombo);
```

`aspectPresetCombo` is a **local**, not a member — there is no `aspectPresetCombo_`. If W2 needs to re-sync the Aspect label to a model-recommended `width`/`height`, the combo must first be promoted to a member. It is added to the layout at `qt_ui\ImageGenerationPage.cpp:1980`: `samplerSchedulerLayout_->addWidget(aspectRow);` — i.e. it lives in the **Sampler & Scheduler** card, not the Output tab (the card's own hint text at `:850` says "Sampler, scheduler and aspect").

**Snapshot restore** — `qt_ui\ImageGenerationPage_catalog.cpp:2090-2101`:

```cpp
    if (widthSpin_ && settings.contains(QStringLiteral("width")))
        widthSpin_->setValue(settings.value(QStringLiteral("width")).toInt());
    if (heightSpin_ && settings.contains(QStringLiteral("height")))
        heightSpin_->setValue(settings.value(QStringLiteral("height")).toInt());
    // A saved 0x0 (a page that was never sized) restores as 0x0; give it its default now.
    ensureCanvasSizeDefault();
    if (frameCountSpin_)
        frameCountSpin_->setValue(settings.value(QStringLiteral("frames"), 81).toInt());
    if (fpsSpin_)
        fpsSpin_->setValue(settings.value(QStringLiteral("fps"), 16).toInt());
```

**The Simple/Advanced restore gate** — `qt_ui\ImageGenerationPage_catalog.cpp:2056-2062` + `:2078-2087` + `:2139-2140`. This is the existing "Simple must start on the OP, Advanced keeps last-chose" mechanism and is exactly what W2 extends:

```cpp
void ImageGenerationPage::restoreSnapshot()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    // Last-chose sampler/steps/CFG are Advanced memory. Simple must start on the family OP
    // (krea2 raw ≠ turbo). Reading the global toggle — this page group does not store it.
    const bool restoreLastSampling = settings.value(QStringLiteral("ui/advancedMode"), false).toBool();
    const QString group = QStringLiteral("ImageGenerationPage/%1").arg(modeKey());
    settings.beginGroup(group);
```
```cpp
    if (restoreLastSampling) {
        if (sampling_->samplerCombo() && settings.contains(QStringLiteral("sampler")))
            selectComboValue(sampling_->samplerCombo(), settings.value(QStringLiteral("sampler")).toString());
        if (sampling_->schedulerCombo() && settings.contains(QStringLiteral("scheduler")))
            selectComboValue(sampling_->schedulerCombo(), settings.value(QStringLiteral("scheduler")).toString());
        if (sampling_->stepsSpin() && settings.contains(QStringLiteral("steps")))
            sampling_->stepsSpin()->setValue(settings.value(QStringLiteral("steps")).toInt());
        if (sampling_->cfgSpin() && settings.contains(QStringLiteral("cfg")))
            sampling_->cfgSpin()->setValue(settings.value(QStringLiteral("cfg")).toDouble());
    }
```
```cpp
    if (!restoreLastSampling)
        applySimpleOperatingPointDefaults();
    settings.endGroup();
}
```

---

## 6. The Advanced/Simple disclosure mechanism

Rule text, `C:\Users\xXste\Code_Projects\SpellVision\CLAUDE.md:34`:

> - **Rule: Advanced *reveals in place*. It never *relocates* controls to a different screen.** Muscle memory must survive the upgrade.

Also `brain\Decisions\ADR-003 Simple Advanced disclosure.md:11`, `brain\Product\UX Principles.md:20`, `docs\design\13_simple_advanced_disclosure_phase7.md:6,80`.

The single gate is `ImageGenerationPage::updateDisclosure(bool advanced)` in `qt_ui\ImageGenerationPage_catalog.cpp:923-1016`. `advanced_` is a member; there is exactly one writer, the first line of this function.

### Example 1 — plain gate, Output tab knobs — `ImageGenerationPage_catalog.cpp:923-941`

```cpp
void ImageGenerationPage::updateDisclosure(bool advanced)
{
    advanced_ = advanced;

    // Phase 7 step 2: Output-tab raw knobs are Advanced-only (Width / Height / Batch / Prefix);
    // Preset (Quality) stays Simple. HIDE-not-delete -- the rows keep their values and the request
    // builder reads by member (draft.width = widthSpin_->value(), never visibility-gated), so a
    // value set in Advanced still drives generation in Simple. These rows carry NO existing
    // visibility guard, so the gate is a plain setVisible(advanced) (rows that DO have a mode/family
    // guard must AND with it -- handled per-row as later tabs are added).
    if (widthRow_)
        widthRow_->setVisible(advanced);
    if (heightRow_)
        heightRow_->setVisible(advanced);
    if (batchRow_)
        batchRow_->setVisible(advanced);
    if (prefixRow_)
        prefixRow_->setVisible(advanced);
```

### Example 2 — AND-composed gates, Sampling tab — `ImageGenerationPage_catalog.cpp:969-986`

```cpp
    // Phase 7 step 3: Sampling-tab raw knobs are Advanced-only. Aspect + Frames/FPS stay Simple
    // (untouched here). GUARD COMPOSITION -- AND the disclosure gate with the row's existing
    // mode guard so disclosure can never reveal a row the mode already hides (image sampler stays
    // hidden in video; video sampler stays hidden in image).
    if (stepsRow_)
        stepsRow_->setVisible(advanced);
    if (cfgRow_)
        cfgRow_->setVisible(advanced);
    if (seedRow_)
        seedRow_->setVisible(advanced);
    if (samplerRow_)
        samplerRow_->setVisible(advanced && image);
    if (schedulerRow_)
        schedulerRow_->setVisible(advanced && image);
    if (videoSamplerRow_)
        videoSamplerRow_->setVisible(advanced && !image);
    if (videoSchedulerRow_)
        videoSchedulerRow_->setVisible(advanced && !image);
```

### Example 3 — the Speed chip row (the operating-point card) — `ImageGenerationPage_catalog.cpp:1004-1013`

```cpp
    if (operatingPointCard_)
        operatingPointCard_->setVisible(advanced && currentOperatingPoints_.size() > 1);

    if (!advanced)
        applySimpleOperatingPointDefaults();

    refreshAdvancedOverrideNotice();

    qWarning().noquote() << QStringLiteral("[disclosure] page=%1 advanced=%2")
                                .arg(modeKey(), advanced ? QStringLiteral("true") : QStringLiteral("false"));
}
```

### Example 4 — "reveals in place" as a *product* fix, not a visibility fix — `ImageGenerationPage_catalog.cpp:944-965`

```cpp
    // Phase (c): the upscale TIER is an intent-level control, so it stays in Simple; Advanced
    // reveals the method / exact scale / model below it, in the same card. Before this the whole
    // group was Advanced-only, which meant Simple offered no upscale at all -- and "reveals in
    // place" cannot be satisfied by a control that is not there in the first place.
...
    const bool isFlux3 = isVideoMode()
        && resolvedVideoFamilyToken() == QStringLiteral("flux3");
    if (upscaleRow_)
        upscaleRow_->setVisible(!isFlux3);
    if (upscale_)
        upscale_->setAdvanced(advanced);
```

Also `qt_ui\generation\UpscaleController.h:25` restates the rule for a sub-controller, and the Advanced tab itself is hidden wholesale in Simple — `ImageGenerationPage_catalog.cpp:1000-1002`:

```cpp
    if (cockpitInspector_)
        cockpitInspector_->setTabVisible(CockpitInspector::Advanced, advanced && !image);
```

### Where the rule is enforced/tested

**There is no C++ disclosure test.** Enforcement is three Python static-source tests:

`C:\Users\xXste\Code_Projects\SpellVision\tests\test_first_run_honesty.py:242-265` — the three operating-point pins, including the one commit 380d8dd added:

```python
def test_same_family_checkpoint_change_reapplies_operating_point() -> None:
    """Live Krea2 stayed at 60 steps (table default 52) because
    applyOperatingPoint ran only when operatingPointFamily_ changed."""
    body = definition_body("updateOperatingPointSelector", qualifier="ImageGenerationPage")
    assert "else if (!defaultPoint.isEmpty())" in body
    assert "applyOperatingPoint(defaultPoint)" in body
    assert 'else if (family == QStringLiteral("krea2")' not in body


def test_krea2_hidden_selector_uses_table_sampler() -> None:
    """krea2_image table sampler is er_sde (render comparison 2026-08-28).
    Hidden selector (<=1 point) hardcoded euler."""
    body = definition_body("updateOperatingPointSelector", qualifier="ImageGenerationPage")
    hidden = body.split("points.size() <= 1", 1)[1].split("return;", 1)[0]
    assert "er_sde" in hidden
    assert 'QStringLiteral("euler")' not in hidden


def test_simple_mode_hides_operating_point_selector() -> None:
    """Simple auto-applies family+variant defaults. Speed card is Advanced-only."""
    body = definition_body("updateOperatingPointSelector", qualifier="ImageGenerationPage")
    assert "operatingPointCard_->setVisible(advanced_)" in body
    disc = definition_body("updateDisclosure", qualifier="ImageGenerationPage")
    assert "operatingPointCard_" in disc
```

`tests\test_first_run_honesty.py:440-446` — the Simple-vs-restore ordering pin:

```python
def test_simple_restore_does_not_clobber_operating_point() -> None:
    """Live T7: restoreSnapshot wrote last-chose steps after OP apply, so Simple was not OP."""
    restore = definition_body("restoreSnapshot", qualifier="ImageGenerationPage")
    assert "ui/advancedMode" in restore
    assert "applySimpleOperatingPointDefaults" in restore
    disclose = definition_body("updateDisclosure", qualifier="ImageGenerationPage")
    assert "applySimpleOperatingPointDefaults" in disclose
```

`tests\test_surface_honesty.py:~30-78` — the "the two sides AGREE" upscale disclosure test (it reads `ImageGenerationPage_catalog.cpp` and scans for the `upscaleRow_->setVisible` line). Its docstring is worth quoting in the plan as a style precedent for W2's own test:

> That is why this test checks the two sides AGREE rather than checking for the mode fence -- a test that pins one of the two valid answers turns a correct change into a red build and teaches nothing about the rule.

**W2 will break `test_krea2_hidden_selector_uses_table_sampler` and `test_same_family_checkpoint_change_reapplies_operating_point` if it removes the krea2 branch. Both must be rewritten in the same change.**

---

## 7. Where a provenance caption could go

### 7a. The Sampling tab is assembled here — `qt_ui\ImageGenerationPage.cpp:2298-2333`

```cpp
    // Sampling tab <- steps/cfg + seed/frames/fps (moved out of QuickControls) + sampler card.
    QVBoxLayout *samplingTab = cockpitInspector_->tabContentLayout(CockpitInspector::Sampling);

    // Phase 3b: the Speed (fast/quality) selector sits at the TOP of the Sampling tab -- it DRIVES the
    // steps/cfg/sampler/scheduler/shift below it, so it lives above them. Rendered generically per the
    // resolved video family's shipped operating points (hidden when <=1). Video-only.
    operatingPointCard_ = createCard(QStringLiteral("OperatingPointCard"));
    setSurface(operatingPointCard_, svstyle::Surface::Panel);
    {
        auto *opLayout = new QHBoxLayout(operatingPointCard_);
        opLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                                     ThemeManager::instance().spacing(ThemeManager::Spacing::Tight),
                                     ThemeManager::instance().spacing(ThemeManager::Spacing::Snug),
                                     ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
        opLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
        auto *speedLabel = new QLabel(QStringLiteral("Speed"), operatingPointCard_);
        speedLabel->setObjectName(QStringLiteral("OperatingPointLabel"));
        opLayout->addWidget(speedLabel);
        operatingPointGroup_ = new QButtonGroup(this);
        operatingPointGroup_->setExclusive(true);
        operatingPointButtonRow_ = new QHBoxLayout;
        operatingPointButtonRow_->setContentsMargins(0, 0, 0, 0);
        operatingPointButtonRow_->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
        opLayout->addLayout(operatingPointButtonRow_, 1);
        // USER clicks apply the bundle (buttonClicked, not toggled -- programmatic setChecked won't fire).
        connect(operatingPointGroup_, &QButtonGroup::buttonClicked, this, [this](QAbstractButton *b) {
            applyOperatingPoint(b->property("opName").toString());
        });
    }
    operatingPointCard_->setVisible(false);
    samplingTab->addWidget(operatingPointCard_);

    moveRowWidgets(stepsCfgLayout_, samplingTab);
    moveRowWidgets(seedBatchLayout_, samplingTab);
    samplingTab->addWidget(samplerSchedulerCard);
    samplingTab->addStretch(1);
```

**The container for a one-line provenance caption is `samplingTab` (a `QVBoxLayout*` from `cockpitInspector_->tabContentLayout(CockpitInspector::Sampling)`).** Insert a `QLabel` immediately after `samplingTab->addWidget(operatingPointCard_);` (line 2327) and before `moveRowWidgets(stepsCfgLayout_, samplingTab);` — that puts it above steps/CFG, matching the "the thing that drives them lives above them" comment. It must be added **before** the `addStretch(1)` at :2332.

The inspector API — `qt_ui\generation\CockpitInspector.h:26-43`:

```cpp
    enum Tab
    {
        Model = 0,
        Sampling = 1,
        Output = 2,
        Advanced = 3
    };

    explicit CockpitInspector(QWidget *parent = nullptr);

    // Content layout of a tab body — callers reparent relocated controls here.
    QVBoxLayout *tabContentLayout(Tab tab) const;
    QLabel *readinessLabel() const { return readinessText_; }

    // Phase 7: show/hide a whole tab (its tab-bar button). Hiding the currently-selected tab moves
    // selection to the first visible tab so the body never goes blank.
    void setTabVisible(Tab tab, bool visible);
```

### 7b. The existing one-line-caption precedents

**`readinessHintLabel_`** — already used by `applyOptimalVideoSamplingDefaults` to say "WAN defaults applied: …". `qt_ui\ImageGenerationPage.cpp:1375-1379`:

```cpp
    // ErrorPillLabel elides a message to the width the row gives it and keeps the full text one
    // hover or click away; a plain QLabel with a 280px cap cut the error mid-word.
    readinessHintLabel_ = new spellvision::generation::ErrorPillLabel(canvasCard_);
    readinessHintLabel_->setObjectName(QStringLiteral("ReadinessHint"));
    readinessHintLabel_->setVisible(false);
```

**`advancedOverrideLabel_`** — the closest structural analogue: a short label whose *tooltip carries the detail*. `qt_ui\ImageGenerationPage.cpp:1381-1398`:

```cpp
    // Simple mode hides these controls but does NOT clear them -- that is the hide-not-delete rule,
    // and it is right: a value set in Advanced must still drive generation. The gap it leaves is
    // that four of those values change the OUTPUT and nothing in Simple reveals them.
    //
    // The worst is a pinned seed. Uncheck Random in Advanced, switch to Simple, and every
    // generation returns the same image with no visible cause and no reachable control -- the user
    // has to guess that Advanced exists. Batch is the same shape (N images per click). Presets do
    // not reset any of the four: applyPreset writes steps/cfg/width/height/sampler/scheduler and
    // touches seed, batch, embeddings and upscale zero times.
    //
    // So it is stated rather than discarded. Naming the override keeps both modes true at once:
    // Advanced still governs, and Simple stops lying about what it is about to do.
    advancedOverrideLabel_ = new QLabel(canvasCard_);
    advancedOverrideLabel_->setObjectName(QStringLiteral("AdvancedOverrideHint"));
    advancedOverrideLabel_->setWordWrap(false);
    advancedOverrideLabel_->setMaximumWidth(320);
    advancedOverrideLabel_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
    advancedOverrideLabel_->setVisible(false);
```

Both sit in the action row — `qt_ui\ImageGenerationPage.cpp:1446-1461`:

```cpp
    actionRow_ = new QWidget(canvasCard_);
    auto *actionRowLayout = new QHBoxLayout(actionRow_);
    actionRowLayout->setContentsMargins(0, 0, 0, 0);
    actionRowLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
...
    actionRowLayout->addStretch(1);
    actionRowLayout->addWidget(advancedOverrideLabel_, 0, Qt::AlignVCenter);
    actionRowLayout->addWidget(readinessHintLabel_, 0, Qt::AlignVCenter);
    actionRowLayout->addWidget(generateButton_);
```

And the writer pattern to copy, `refreshAdvancedOverrideNotice` — `qt_ui\ImageGenerationPage_catalog.cpp:1016-1063`:

```cpp
{
    if (!advancedOverrideLabel_)
        return;

    // Advanced shows every one of these controls, so there is nothing to disclose.
    if (advanced_)
    {
        advancedOverrideLabel_->setVisible(false);
        return;
    }

    QStringList overrides;
...
    if (overrides.isEmpty())
    {
        advancedOverrideLabel_->setVisible(false);
        return;
    }

    const QString summary = overrides.join(QStringLiteral(", "));
    advancedOverrideLabel_->setText(QStringLiteral("Advanced: %1").arg(summary));
    // The tooltip carries the remedy. The label stays short because it shares the action row with
    // the readiness hint and the Generate button, and this row must not wrap at half-screen.
    advancedOverrideLabel_->setToolTip(
        QStringLiteral("These Advanced settings are in force and will affect this generation:\n%1\n\n"
                       "Switch to Advanced to see or change them.")
            .arg(summary));
    advancedOverrideLabel_->setVisible(true);
}
```

Declared at `qt_ui\ImageGenerationPage.h:535`:
```cpp
    QLabel *advancedOverrideLabel_ = nullptr; // Simple-mode notice; see refreshAdvancedOverrideNotice
```

Recommendation for the plan: a `provenanceCaptionLabel_` built next to `operatingPointCard_` in `samplingTab` (§7a), written by a `refreshRecommendedSettingsCaption()` modelled line-for-line on `refreshAdvancedOverrideNotice` (short text, detail in the tooltip, `setVisible(false)` when empty).

---

## 8. Existing C++ tests for this area

### 8a. `tests\cpp\test_sampling_controller.cpp` — main test bodies

Header comment (states exactly what class of defect these tests exist for — reuse this framing):

```cpp
// The cockpit's sampling row: two ways a control said yes and the value never left it.
//
// 1. A family that offers no samplers left the PREVIOUS family's list on screen. applyFamilyChoices
//    returned early on an empty table, so switching to a family with nothing to offer showed sdxl's
//    five samplers, and picking one sent a name that family has never heard of.
//
// 2. draftSeed() clamped with qMax(1, ...). The spin box had been widened to accept 0 -- 0 is a
//    seed, ComfyUI's KSampler declares it as the minimum, and every builder honours it through
//    resolve_seed -- and this clamp turned every 0 the user typed back into 1 on the way out.
//
// The second is the one the Python sweeps structurally cannot see: the value is corrected inside
// the widget, before any request exists to inspect.
```

Fixture (this is the harness W2's test copies):

```cpp
class SamplingControllerTest : public QObject
{
    Q_OBJECT

private slots:
    void init();
    void cleanup();

    void aFamilyWithNoChoicesClearsTheStaleList();
    void aFamilyWithSamplersButNoSchedulersKeepsItsSamplers();
    void theComboKeepsAutoAndOffersTheFamilysSamplers();
    void aDeliberateChoiceSurvivesAFamilySwitchOnlyIfTheFamilyOffersIt();
    void aStatedSeedOfZeroSurvives();
    void aStatedSeedIsNotOtherwiseAltered();
    void randomSeedsCanIncludeZero();

private:
    QWidget *host_ = nullptr;
    SamplingController *controller_ = nullptr;

    static QJsonObject table(const QStringList &samplers, const QStringList &schedulers,
                             const QString &defaultSampler = QString())
    {
        QJsonArray a, b;
        for (const QString &s : samplers) a.append(s);
        for (const QString &s : schedulers) b.append(s);
        QJsonObject o{{QStringLiteral("samplers"), a}, {QStringLiteral("schedulers"), b}};
        if (!defaultSampler.isEmpty())
            o.insert(QStringLiteral("default_sampler"), defaultSampler);
        return o;
    }
};

void SamplingControllerTest::init()
{
    host_ = new QWidget;
    controller_ = new SamplingController(host_);
    controller_->create(host_);
}

void SamplingControllerTest::cleanup()
{
    delete host_;
    host_ = nullptr;
    controller_ = nullptr;
}
```

The two bodies W2 most directly touches:

```cpp
void SamplingControllerTest::theComboKeepsAutoAndOffersTheFamilysSamplers()
{
    // "Auto / family default" stays selected, and that is right: the concrete default belongs to
    // the worker's resolver, so the cockpit showing a name would be a second place for it to live.
    // What the combo must do is OFFER the family's samplers -- and offer only those.
    controller_->applyFamilyChoices(
        table({"euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde", "ddim"},
              {"normal", "karras"}, QStringLiteral("dpmpp_2m")), false);

    QCOMPARE(controller_->imageSampler(), QStringLiteral("auto"));
    QCOMPARE(controller_->samplerCombo()->count(), 6);  // auto + five
    QVERIFY(controller_->samplerCombo()->findData(QStringLiteral("dpmpp_2m")) > 0);
    QVERIFY(controller_->samplerCombo()->findData(QStringLiteral("res_multistep")) < 0);
}

void SamplingControllerTest::aDeliberateChoiceSurvivesAFamilySwitchOnlyIfTheFamilyOffersIt()
{
    controller_->applyFamilyChoices(
        table({"euler", "dpmpp_2m", "ddim"}, {"normal", "karras"}), false);
    controller_->samplerCombo()->setCurrentIndex(
        controller_->samplerCombo()->findData(QStringLiteral("dpmpp_2m")));
    QCOMPARE(controller_->imageSampler(), QStringLiteral("dpmpp_2m"));

    // Same sampler offered by the next family: keep it, the user asked for it.
    controller_->applyFamilyChoices(table({"euler", "dpmpp_2m"}, {"simple"}), false);
    QCOMPARE(controller_->imageSampler(), QStringLiteral("dpmpp_2m"));

    // Not offered by the next family: fall back to auto rather than send a name this family has
    // never heard of, which is what the stale list used to make possible.
    controller_->applyFamilyChoices(table({"res_multistep", "euler"}, {"simple"}), false);
    QCOMPARE(controller_->imageSampler(), QStringLiteral("auto"));
}
```

Also relevant (a per-model sampler must not resurrect the stale-list bug):

```cpp
void SamplingControllerTest::aFamilyWithNoChoicesClearsTheStaleList()
{
    controller_->applyFamilyChoices(table({"euler", "dpmpp_2m", "ddim"}, {"normal", "karras"}), false);
    QVERIFY(controller_->samplerCombo()->count() > 1);

    // cogvideox returns an empty table, and it is right to: the family is unrouted and has no
    // sampler to offer. Showing the previous family's list is worse than showing none.
    controller_->applyFamilyChoices(table({}, {}), false);
    QCOMPARE(controller_->samplerCombo()->count(), 1);  // "Auto / family default" only
    QCOMPARE(controller_->samplerCombo()->itemData(0).toString(), QStringLiteral("auto"));
}
```

Tail:
```cpp
QTEST_MAIN(SamplingControllerTest)
#include "test_sampling_controller.moc"
```

### 8b. `tests\cpp\test_canvas_size_default.cpp` — main test bodies

Header + the widget-finding helper (note: it finds the spin boxes **by their range and special-value text**, not by object name — a pattern W2's test can reuse for steps/CFG):

```cpp
// A page never opens with Generate blocked by a size the app could have chosen.
...
// The width/height spin boxes start at 0 and only a preset or a saved value ever set them, so on
// 2026-09-02 a fresh I2I (reached through "Prep for I2I", input already staged) and a fresh T2V
// both opened with "Choose a canvas size to generate." and a dead Generate. Two of the four
// generation pages. The rule: when width or height is unset, an i2i / i2v page takes the size of
// the image it was given, and any page takes its family's default. An explicit size is never
// overridden.
```
```cpp
// The two canvas spin boxes: range 0..8192 with the em-dash special value, in creation order.
CanvasSpins canvasSpins(ImageGenerationPage &page)
{
    CanvasSpins spins;
    for (QSpinBox *box : page.findChildren<QSpinBox *>())
    {
        if (box->maximum() != 8192 || box->specialValueText() != QStringLiteral("—"))
            continue;
        if (!spins.width)
            spins.width = box;
        else if (!spins.height)
            spins.height = box;
    }
    return spins;
}
```

The QSettings isolation (**W2's test needs this verbatim** — `restoreSnapshot` reads `ui/advancedMode` from the real store):

```cpp
    void initTestCase()
    {
        // The page restores its last size from QSettings; the test must see an empty store, not
        // the developer's saved 1080x1920.
        QCoreApplication::setOrganizationName(QStringLiteral("DarkDuckTest"));
        QCoreApplication::setApplicationName(QStringLiteral("SpellVisionCanvasSizeTest"));
        QSettings settings;
        settings.clear();
        settings.sync();
    }
```

The data-driven four-mode sweep (the exact shape W2 wants — "every generation page starts on the model's settings"):

```cpp
    void every_generation_page_opens_with_a_canvas_size_data()
    {
        QTest::addColumn<int>("mode");
        QTest::newRow("t2i") << static_cast<int>(ImageGenerationPage::Mode::TextToImage);
        QTest::newRow("i2i") << static_cast<int>(ImageGenerationPage::Mode::ImageToImage);
        QTest::newRow("t2v") << static_cast<int>(ImageGenerationPage::Mode::TextToVideo);
        QTest::newRow("i2v") << static_cast<int>(ImageGenerationPage::Mode::ImageToVideo);
    }

    void every_generation_page_opens_with_a_canvas_size()
    {
        QFETCH(int, mode);
        ImageGenerationPage page(static_cast<ImageGenerationPage::Mode>(mode));
        const CanvasSpins spins = canvasSpins(page);
        QVERIFY2(spins.width && spins.height, "canvas spin boxes not found");
        QVERIFY2(spins.width->value() >= 64 && spins.height->value() >= 64,
                 qPrintable(QStringLiteral("page opened at %1x%2 -- Generate would be blocked")
                                .arg(spins.width->value()).arg(spins.height->value())));
    }

    void a_video_page_defaults_to_a_landscape_video_canvas()
    {
        ImageGenerationPage page(ImageGenerationPage::Mode::TextToVideo);
        const CanvasSpins spins = canvasSpins(page);
        QVERIFY(spins.width && spins.height);
        QCOMPARE(spins.width->value(), 832);
        QCOMPARE(spins.height->value(), 480);
    }
```

The explicit-size-wins pin W2's width/height work must not break:

```cpp
    void an_explicit_size_is_not_overridden_by_an_input()
    {
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const QString portrait = writePng(dir, QStringLiteral("portrait.png"), QSize(720, 1280));

        ImageGenerationPage page(ImageGenerationPage::Mode::ImageToImage);
        const CanvasSpins spins = canvasSpins(page);
        QVERIFY(spins.width && spins.height);
        spins.width->setValue(1024);
        spins.height->setValue(1024);

        page.useImageAsInput(portrait);
        QCOMPARE(spins.width->value(), 1024);
        QCOMPARE(spins.height->value(), 1024);
    }
};

QTEST_MAIN(CanvasSizeDefaultTest)
#include "test_canvas_size_default.moc"
```

Note: `ImageGenerationPage page(Mode::…)` constructs directly, with no `MainWindow`, so `operatingPointsProvider_` is null in these tests. W2's test can inject a fake per-model provider the same way `setOperatingPointsProvider` does.

### 8c. CMakeLists entries — `C:\Users\xXste\Code_Projects\SpellVision\CMakeLists.txt`

Registration template (`:479-484`):

```cmake
# The cockpit's sampling row. Two defects that live entirely inside the widget -- a stale dropdown
# and a seed clamped on its way out -- which the Python sweeps structurally cannot see, because the
# value is corrected before any request exists to inspect.
qt_add_executable(test_sampling_controller tests/cpp/test_sampling_controller.cpp)
target_link_libraries(test_sampling_controller PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME sampling_controller COMMAND test_sampling_controller)
```

and (`:565-569`):

```cmake
# A page never opens with Generate blocked by a size the app could have chosen: two of the four
# generation pages opened at 0x0 behind "Choose a canvas size to generate."
qt_add_executable(test_canvas_size_default tests/cpp/test_canvas_size_default.cpp)
target_link_libraries(test_canvas_size_default PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME canvas_size_default COMMAND test_canvas_size_default)
```

**Second required edit** — the new target MUST be added to the `WIN32_EXECUTABLE FALSE` list at `CMakeLists.txt:627-634`, or the test runs as a GUI subsystem binary and ctest prints nothing on failure:

```cmake
set_target_properties(test_responsive_matrix test_worker_response_parser test_sampling_controller
                      test_project_root test_worker_request_builder test_comfy_endpoint_profile
                      test_worker_session_secret test_worker_socket_frames test_app_version test_canvas_aspect
                      test_lora_stack_row test_action_row_pill test_queue_tally test_canvas_size_default
                      test_family_license test_eliding_label test_telemetry_presenter test_sv_fonts
                      test_sv_style test_shell_layout test_bottom_telemetry test_worker_queue_controller
                      test_runtime_probe test_image_preview_controller
                      PROPERTIES WIN32_EXECUTABLE FALSE)
```

The Windows PATH/console env block that follows (`:636-660`) is **already automatic** — it queries `DIRECTORY PROPERTY TESTS` via `cmake_language(DEFER CALL sv_apply_qt_test_environment)`, so a new `add_test` needs no third edit:

```cmake
    function(sv_apply_qt_test_environment)
        get_property(sv_qt_tests DIRECTORY PROPERTY TESTS)
        set_tests_properties(${sv_qt_tests} PROPERTIES
            ENVIRONMENT "PATH=$<TARGET_FILE_DIR:Qt6::Core>;$ENV{PATH};QT_ASSUME_STDERR_HAS_CONSOLE=1;QT_FORCE_STDERR_LOGGING=1")
    endfunction()
    cmake_language(DEFER CALL sv_apply_qt_test_environment)
```

---

## 9. The studios' checkpoint pickers

**Answer: no. None of the four route through `applyOperatingPoint` or `updateOperatingPointSelector`.** Grep for `applyOperatingPoint|operatingPoint|operatingPointsProvider_` over `qt_ui/studios/*` and `qt_ui/DatasetGenerationPage.*` returns **zero hits**. They are entirely separate code paths with hardcoded steps/cfg.

### 9a. CharacterStudioPage — `qt_ui\studios\CharacterStudioPage.cpp:2163-2173`

```cpp
    CatalogPickerDialog dlg(QStringLiteral("Choose checkpoint"), entries, selectedModelPath_,
                            QStringLiteral("characterStudio/recentModels"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    selectedModelPath_ = dlg.selectedValue();
    selectedModelDisplay_ = dlg.selectedDisplay();
    selectedModelFamily_ = dlg.selectedFamily();
    persistRecentSelection(QStringLiteral("characterStudio/recentModels"), selectedModelPath_);
    refreshModelStackLabels();
    saveProjectState();
}
```

No sampling widgets at all. Steps/CFG are **literals in the request payloads**, four separate hardcodings:

`CharacterStudioPage.cpp:1258-1259`:
```cpp
        payload.insert(QStringLiteral("steps"), 52);
        payload.insert(QStringLiteral("cfg"), 3.5);
```
`CharacterStudioPage.cpp:1468-1471`:
```cpp
    payload.insert(QStringLiteral("steps"), 52);
    payload.insert(QStringLiteral("cfg"), 3.5);
    payload.insert(QStringLiteral("model"), selectedModelPath_.trimmed());
    payload.insert(QStringLiteral("model_family"), selectedModelFamily_);
```
`CharacterStudioPage.cpp:1544-1545`: `steps 30`, `cfg 4.5`.
`CharacterStudioPage.cpp:1995-1996`: `steps 30`, `cfg 5.0`.

(52/3.5 is the krea2 "raw" operating point, copy-pasted.) Canvas size is also literal — `CharacterStudioPage.cpp:1455-1467`:

```cpp
    int w = 832;
    int h = 1216;
    if (aspectCombo_) {
        if (aspectCombo_->currentIndex() == 1) {
            w = 1024;
            h = 1024;
        } else if (aspectCombo_->currentIndex() == 2) {
            w = 768;
            h = 1344;
        }
    }
    payload.insert(QStringLiteral("width"), w);
    payload.insert(QStringLiteral("height"), h);
```

Header members — `qt_ui\studios\CharacterStudioPage.h:208-213`:
```cpp
    QString selectedModelPath_;
    QString selectedModelDisplay_;
...
    QString selectedModelFamily_;
```
and `CharacterStudioPage.h:258`: `// Advanced-only widgets (revealed in place)`.

### 9b. ComicStudioPage — `qt_ui\studios\ComicStudioPage.cpp:1432-1442`

```cpp
    CatalogPickerDialog dlg(QStringLiteral("Choose checkpoint"), entries, selectedModelPath_,
                            QStringLiteral("comicStudio/recentModels"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    selectedModelPath_ = dlg.selectedValue();
    selectedModelDisplay_ = dlg.selectedDisplay();
    selectedModelFamily_ = dlg.selectedFamily();
    persistRecentSelection(QStringLiteral("comicStudio/recentModels"), selectedModelPath_);
    refreshModelStackLabels();
    saveProject();
}
```

This is the only studio with its **own** sampling widgets — `ComicStudioPage.cpp:521-531`:

```cpp
    samplerHintCombo_ = new QComboBox(advancedBlock_);
    samplerHintCombo_->addItem(QStringLiteral("euler"), QStringLiteral("euler"));
    samplerHintCombo_->addItem(QStringLiteral("dpmpp_2m"), QStringLiteral("dpmpp_2m"));
    samplerHintCombo_->addItem(QStringLiteral("uni_pc"), QStringLiteral("uni_pc"));
    stepsSpin_ = new QSpinBox(advancedBlock_);
    stepsSpin_->setRange(4, 80);
    stepsSpin_->setValue(28);
    cfgSpin_ = new QDoubleSpinBox(advancedBlock_);
    cfgSpin_->setRange(1.0, 15.0);
    cfgSpin_->setSingleStep(0.5);
    cfgSpin_->setValue(5.0);
```

Note: **not** a `SamplingController`, and **no "Auto" entry** in `samplerHintCombo_`. Read back at `ComicStudioPage.cpp:1342-1343`:

```cpp
    const int steps = stepsSpin_ ? stepsSpin_->value() : 28;
    const double cfg = cfgSpin_ ? cfgSpin_->value() : 5.0;
```

It has its own hardcoded-default override notice — `ComicStudioPage.cpp:170-178`:

```cpp
    if (stepsSpin_ && stepsSpin_->value() != 28)
        overrides << QStringLiteral("%1 steps").arg(stepsSpin_->value());

    if (cfgSpin_ && !qFuzzyCompare(cfgSpin_->value() + 1.0, 5.0 + 1.0))
        overrides << QStringLiteral("cfg %1").arg(cfgSpin_->value(), 0, 'f', 1);

    if (samplerHintCombo_ && samplerHintCombo_->currentIndex() > 0)
        overrides << QStringLiteral("sampler %1")
                         .arg(spellvision::generation::comboStoredValue(samplerHintCombo_));
```

**This literal `28` / `5.0` "is it an override?" comparison breaks the moment defaults become per-model** — W2 must make it compare against the applied recommendation, not a constant.

Header — `qt_ui\studios\ComicStudioPage.h:167-168`:
```cpp
    QSpinBox *stepsSpin_ = nullptr;
    QDoubleSpinBox *cfgSpin_ = nullptr;
```

### 9c. ConceptReferencePage — `qt_ui\studios\ConceptReferencePage.cpp:751-761`

```cpp
    CatalogPickerDialog dlg(QStringLiteral("Choose checkpoint"), entries, selectedModelPath_,
                            QStringLiteral("conceptReference/recentModels"), this);
    if (dlg.exec() != QDialog::Accepted)
        return;
    selectedModelPath_ = dlg.selectedValue();
    selectedModelDisplay_ = dlg.selectedDisplay();
    selectedModelFamily_ = dlg.selectedFamily();
    persistRecentSelection(QStringLiteral("conceptReference/recentModels"), selectedModelPath_);
    refreshModelCatalog();
    saveProject();
}
```

No steps/cfg/sampler widgets at all (grep for `stepsSpin_|cfgSpin_|sampler` in `ConceptReferencePage.cpp` returns nothing). It only forwards `model_family` — `ConceptReferencePage.cpp:669`:

```cpp
        payload.insert(QStringLiteral("model_family"), selectedModelFamily_);
```

### 9d. DatasetGenerationPage — no checkpoint picker at all

Grep for `CatalogPickerDialog|selectedModel|stepsSpin|cfgSpin|sampler|Family` in `qt_ui\DatasetGenerationPage.cpp` returns exactly one line, `:110`:

```cpp
        QStringLiteral("Expand prompts into many T2I jobs. Requires a checkpoint (uses current T2I model if set)."),
```

Its only widgets are `qt_ui\DatasetGenerationPage.h:45-48`:
```cpp
    QSpinBox *imagesPerPromptSpin_ = nullptr;
    QSpinBox *seedStartSpin_ = nullptr;
    QSpinBox *datasetWidthSpin_ = nullptr;
    QSpinBox *datasetHeightSpin_ = nullptr;
```

So it inherits whatever the T2I page selected, and has its own width/height that W2's per-model canvas default would not reach.

### 9e. The shared picker

All four studios (and the cockpit) use `spellvision::assets::CatalogPickerDialog`, and all four read back `dlg.selectedFamily()`. **That accessor is the natural place to also surface the model path for a per-model fetch**, and the three studios' picker bodies are byte-identical apart from the recents key and the trailing save call — a good candidate for one shared `applyRecommendedSettingsForModel(path, family)` helper rather than three copies.

---

## Summary of W2 impact surface (line-anchored)

| What | Where |
|---|---|
| Primary hook: model changed | `ImageGenerationPage_catalog.cpp:374-375` (`else if (modelChanged) updateOperatingPointSelector();`) |
| Secondary hook: video resolved | `ImageGenerationPage_catalog.cpp:384` |
| Hack to delete | `ImageGenerationPage_units.h:171-177` + `ImageGenerationPage_video.cpp:1085-1106` |
| Apply function to extend | `ImageGenerationPage_video.cpp:1174-1254` |
| Family-only defaults to replace | `ImageGenerationPage_video.cpp:219-278` |
| MainWindow pattern to copy | `MainWindow.cpp:3361-3429`, members `MainWindow.h:482-486`, wiring `MainWindow.cpp:2487-2496` |
| Transport | `MainWindow.cpp:3431-3444` → `WorkerSocketClient::send` |
| Widgets | `SamplingController.h` (no setters), `ImageGenerationPage.cpp:1787-1812` (w/h/frames/fps), **no clip-skip widget exists** |
| Canvas default to reconcile | `ImageGenerationPage_catalog.cpp:1650-1673` |
| Aspect combo (needs promoting to member) | `ImageGenerationPage.cpp:1909-1930` |
| Simple/Advanced gate | `ImageGenerationPage_catalog.cpp:923-1016` |
| Caption container | `ImageGenerationPage.cpp:2299` (`samplingTab`), insert after `:2327` |
| Caption writer to model on | `ImageGenerationPage_catalog.cpp:1016-1063` |
| Tests that will go red | `tests/test_first_run_honesty.py:242-265`, `tests/cpp/test_sampling_controller.cpp` (`theComboKeepsAutoAndOffersTheFamilysSamplers`) |
| CMake edits needed | `CMakeLists.txt` add_test block + `:627-634` `WIN32_EXECUTABLE FALSE` list |
| Ratchet promotion | `model_recommended_settings` DIAGNOSTIC → USER_FACING; caller must send configured roots (`docs/SPELLVISION_WORKER_PROTOCOL.md:217`, `.superpowers/sdd/2026-09-16-w1-model-intelligence/task-9-brief.md:361-369`) |
| Studios: all separate, hardcoded | `CharacterStudioPage.cpp:1258,1468,1544,1995`; `ComicStudioPage.cpp:170-178,521-531,1342-1343`; `ConceptReferencePage.cpp:669`; `DatasetGenerationPage.cpp:110` |
