from pathlib import Path

cpp_path = Path("qt_ui/T2VHistoryPage.cpp")
h_path = Path("qt_ui/T2VHistoryPage.h")

cpp = cpp_path.read_text(encoding="utf-8")
h = h_path.read_text(encoding="utf-8")

# Ensure header slot/member exist.
if "void prepareSelectedLtxRequeueDraft();" not in h:
    h = h.replace(
        "    void copySelectedMetadataPath();\n",
        "    void copySelectedMetadataPath();\n"
        "    void prepareSelectedLtxRequeueDraft();\n",
        1,
    )

if "QPushButton *requeueButton_ = nullptr;" not in h:
    h = h.replace(
        "    QPushButton *copyMetadataPathButton_ = nullptr;\n",
        "    QPushButton *copyMetadataPathButton_ = nullptr;\n"
        "    QPushButton *requeueButton_ = nullptr;\n",
        1,
    )

h_path.write_text(h, encoding="utf-8")

# Construct the button directly after Copy Metadata Path.
if "requeueButton_ = new QPushButton(QStringLiteral(\"Prepare Requeue\"), details);" not in cpp:
    cpp = cpp.replace(
        "    copyMetadataPathButton_ = new QPushButton(QStringLiteral(\"Copy Metadata Path\"), details);\n"
        "    copyMetadataPathButton_->setObjectName(QStringLiteral(\"HistoryActionButton\"));\n",
        "    copyMetadataPathButton_ = new QPushButton(QStringLiteral(\"Copy Metadata Path\"), details);\n"
        "    copyMetadataPathButton_->setObjectName(QStringLiteral(\"HistoryActionButton\"));\n"
        "    requeueButton_ = new QPushButton(QStringLiteral(\"Prepare Requeue\"), details);\n"
        "    requeueButton_->setObjectName(QStringLiteral(\"HistoryActionButton\"));\n",
        1,
    )

# Connect the button.
if "connect(requeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::prepareSelectedLtxRequeueDraft);" not in cpp:
    cpp = cpp.replace(
        "    connect(copyMetadataPathButton_, &QPushButton::clicked, this, &T2VHistoryPage::copySelectedMetadataPath);\n",
        "    connect(copyMetadataPathButton_, &QPushButton::clicked, this, &T2VHistoryPage::copySelectedMetadataPath);\n"
        "    connect(requeueButton_, &QPushButton::clicked, this, &T2VHistoryPage::prepareSelectedLtxRequeueDraft);\n",
        1,
    )

# Add it to the existing copy action row.
if "copyActions->addWidget(requeueButton_);" not in cpp:
    cpp = cpp.replace(
        "    copyActions->addWidget(copyPromptButton_);\n"
        "    copyActions->addWidget(copyMetadataPathButton_);\n",
        "    copyActions->addWidget(copyPromptButton_);\n"
        "    copyActions->addWidget(copyMetadataPathButton_);\n"
        "    copyActions->addWidget(requeueButton_);\n",
        1,
    )

# Enable only for LTX rows.
if "const bool selectedItemIsLtx" not in cpp:
    cpp = cpp.replace(
        "    copyPromptButton_->setEnabled(!item.promptPreview.isEmpty());\n"
        "    copyMetadataPathButton_->setEnabled(!item.metadataPath.isEmpty());\n",
        "    copyPromptButton_->setEnabled(!item.promptPreview.isEmpty());\n"
        "    copyMetadataPathButton_->setEnabled(!item.metadataPath.isEmpty());\n"
        "    const bool selectedItemIsLtx = item.runtimeSummary.contains(QStringLiteral(\"LTX registry\"), Qt::CaseInsensitive)\n"
        "        || item.stackSummary.contains(QStringLiteral(\"LTX\"), Qt::CaseInsensitive)\n"
        "        || item.lowModelName.contains(QStringLiteral(\"ltx\"), Qt::CaseInsensitive);\n"
        "    requeueButton_->setEnabled(selectedItemIsLtx);\n",
        1,
    )

# Disable on empty details.
if "requeueButton_->setEnabled(false);" not in cpp:
    cpp = cpp.replace(
        "    copyMetadataPathButton_->setEnabled(false);\n",
        "    copyMetadataPathButton_->setEnabled(false);\n"
        "    requeueButton_->setEnabled(false);\n",
        1,
    )

cpp_path.write_text(cpp, encoding="utf-8")

print("Repaired visible Prepare Requeue button wiring for current T2VHistoryPage layout.")
