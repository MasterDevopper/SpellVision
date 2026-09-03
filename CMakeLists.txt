cmake_minimum_required(VERSION 3.21)
project(SpellVision VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

option(SPELLVISION_DEPLOY_NO_TRANSLATIONS "Skip Qt translations during deployment" ON)
option(SPELLVISION_DEPLOY_FAST_DEV "Use a lighter dev deployment pass" ON)

if(WIN32)
    if(NOT DEFINED Qt6_DIR AND DEFINED ENV{Qt6_DIR})
        set(Qt6_DIR "$ENV{Qt6_DIR}" CACHE PATH "Path to Qt6Config.cmake directory")
    endif()

    if(NOT DEFINED CMAKE_PREFIX_PATH AND DEFINED ENV{CMAKE_PREFIX_PATH})
        set(CMAKE_PREFIX_PATH "$ENV{CMAKE_PREFIX_PATH}" CACHE STRING "CMake prefix path")
    endif()
endif()

find_package(Qt6 REQUIRED COMPONENTS Widgets Svg Multimedia MultimediaWidgets Concurrent Network Test)

# --- libwebp (BSD-3-Clause): native WebP decode for model thumbnails ---------------------------------
# Qt 6.10.2 ships no WebP image plugin and the "Qt Image Formats" add-on isn't offered for 6.10.2 in the
# Maintenance Tool (only 6.10.3+/6.11.1 list it). ~94% of Civitai model previews are WebP (often misnamed
# .jpeg), so we decode them ourselves instead of shelling out to a Python venv's Pillow. Decoder only —
# encoder, tools, mux and extras are disabled to keep the build slim.
include(FetchContent)
set(WEBP_BUILD_ANIM_UTILS OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_CWEBP OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_DWEBP OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_GIF2WEBP OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_IMG2WEBP OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_VWEBP OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_WEBPINFO OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_WEBPMUX OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_LIBWEBPMUX OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_EXTRAS OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_WEBP_JS OFF CACHE BOOL "" FORCE)
set(WEBP_LINK_STATIC ON CACHE BOOL "" FORCE)
FetchContent_Declare(
    libwebp
    GIT_REPOSITORY https://github.com/webmproject/libwebp.git
    GIT_TAG v1.5.0            # pinned release, not HEAD
    GIT_SHALLOW TRUE
)
FetchContent_MakeAvailable(libwebp)

include(cmake/SpellVisionQtDeploy.cmake)

# ---------------------------------------------------------------------------
# SpellVisionCore -- everything except main()
# ---------------------------------------------------------------------------
#
# The UI's decision logic used to be reachable only by launching the GUI: every source sat
# inline in qt_add_executable, so nothing could link it. 63k lines of C++ had one test as a
# result, and two defects in the last pass lived on this side -- a seed spin box that could not
# express a value the worker had just been taught to honour, and a "random (-1)" sentinel no
# builder implemented. Both were unit-testable; neither was reachable by a unit test.
#
# A STATIC library rather than OBJECT: qt_add_library drives AUTOMOC correctly for it, and the
# app keeps its own qt_add_executable so Qt's plugin-import finalizer still runs against the
# executable target where it belongs.
#
# Link libraries and include dirs are PUBLIC so the test binaries inherit exactly what the app
# builds against. A test that compiled against different flags than the app would be testing a
# different program.
qt_add_library(SpellVisionCore STATIC
    qt_ui/MainWindow.h
    qt_ui/MainWindow.cpp

    qt_ui/HomePage.h
    qt_ui/HomePage.cpp
    qt_ui/OutputCardModel.h
    qt_ui/OutputCardModel.cpp
    qt_ui/HomeDashboardTypes.h
    qt_ui/HomeDashboardSettings.h
    qt_ui/HomeDashboardSettings.cpp
    qt_ui/HomeDashboardModuleRegistry.h
    qt_ui/HomeDashboardModuleRegistry.cpp
    qt_ui/HomeDashboardPage.h
    qt_ui/HomeDashboardPage.cpp
    qt_ui/HomeModuleBase.h
    qt_ui/HomeModuleBase.cpp
    qt_ui/HomeModuleFrame.h
    qt_ui/HomeModuleFrame.cpp

    qt_ui/DashboardSurfaceTokens.h
    qt_ui/DashboardSurfaceTokens.cpp
    qt_ui/DashboardGlassPanel.h
    qt_ui/DashboardGlassPanel.cpp
    qt_ui/DashboardPreviewPlate.h
    qt_ui/DashboardPreviewPlate.cpp
    qt_ui/DashboardMetricChip.h
    qt_ui/DashboardMetricChip.cpp

    qt_ui/ModePage.h
    qt_ui/ModePage.cpp
    qt_ui/T2VHistoryPage.h
    qt_ui/T2VHistoryPage.cpp
    qt_ui/history/HistoryRowLabels.cpp
    qt_ui/ManagerPage.h
    qt_ui/ManagerPage.cpp
    qt_ui/TrainPage.h
    qt_ui/TrainPage.cpp
    qt_ui/ImageGenerationPage.h
    qt_ui/ImageGenerationPage_preview.cpp
    qt_ui/ImageGenerationPage_video.cpp
    qt_ui/ImageGenerationPage_catalog.cpp
    qt_ui/generation/CockpitWidgetKit.cpp
    qt_ui/generation/CockpitWidgetKit.h

    qt_ui/generation/GenerationRequestBuilder.cpp
    qt_ui/generation/GenerationRequestBuilder.h
    qt_ui/generation/VideoGenerationPolicy.cpp
    qt_ui/generation/VideoGenerationPolicy.h
    qt_ui/generation/VideoReadinessPresenter.cpp
    qt_ui/generation/VideoReadinessPresenter.h

    qt_ui/generation/GenerationModeState.cpp
    qt_ui/generation/GenerationModeState.h

    qt_ui/generation/GenerationResultRouter.cpp
    qt_ui/generation/GenerationResultRouter.h



    qt_ui/generation/OutputPathHelpers.cpp
    qt_ui/generation/OutputPathHelpers.h
    qt_ui/generation/GenerationStatusController.cpp
    qt_ui/generation/GenerationStatusController.h
    qt_ui/generation/ErrorPillLabel.cpp
    qt_ui/generation/ErrorPillLabel.h
    qt_ui/generation/CockpitInspector.cpp
    qt_ui/generation/CockpitInspector.h
    qt_ui/generation/SamplingController.cpp
    qt_ui/generation/UpscaleController.cpp
    qt_ui/generation/SamplingController.h
    qt_ui/assets/ModelStackState.cpp
    qt_ui/assets/ModelStackState.h

    qt_ui/assets/FamilyLicense.cpp
    qt_ui/assets/FamilyLicense.h
    qt_ui/assets/FamilyLicenseTable.h   # GENERATED from python/model_registry.py


    qt_ui/assets/LoraStackController.cpp
    qt_ui/assets/LoraStackController.h

    qt_ui/assets/CatalogPickerDialog.cpp
    qt_ui/assets/CatalogPickerDialog.h
    qt_ui/assets/AssetCatalogScanner.cpp
    qt_ui/assets/AssetCatalogScanner.h

    qt_ui/assets/ModelSidecar.cpp
    qt_ui/assets/ModelSidecar.h
    qt_ui/assets/ModelOverlayStore.cpp
    qt_ui/assets/ModelOverlayStore.h
    qt_ui/assets/ModelThumbnailCache.cpp
    qt_ui/assets/ModelThumbnailCache.h
    qt_ui/assets/ModelCardModel.cpp
    qt_ui/assets/ModelCardModel.h
    qt_ui/assets/ModelCardDelegate.cpp
    qt_ui/assets/ModelCardDelegate.h
    qt_ui/assets/ModelCardView.cpp
    qt_ui/assets/ModelCardView.h

    qt_ui/widgets/DropTargetFrame.cpp
    qt_ui/widgets/DropTargetFrame.h
    qt_ui/widgets/ClickOnlyComboBox.cpp
    qt_ui/widgets/ClickOnlyComboBox.h

    qt_ui/widgets/SectionCardWidgets.cpp
    qt_ui/widgets/SectionCardWidgets.h

    qt_ui/widgets/GlowProgressBar.cpp
    qt_ui/widgets/GlowProgressBar.h

    qt_ui/widgets/ElidingLabel.cpp
    qt_ui/widgets/ElidingLabel.h
    qt_ui/workers/WorkerResponseParser.cpp
    qt_ui/workers/WorkerResponseParser.h

    qt_ui/workers/WorkerCommandRunner.cpp
    qt_ui/workers/WorkerCommandRunner.h

    qt_ui/workers/WorkerProcessController.cpp
    qt_ui/workers/WorkerProcessController.h

    qt_ui/workers/WorkerQueueController.cpp
    qt_ui/workers/WorkerQueueController.h
    qt_ui/workers/WorkerSocketClient.cpp
    qt_ui/workers/WorkerSocketClient.h
    qt_ui/workers/WorkerRequestBuilder.cpp
    qt_ui/workers/WorkerRequestBuilder.h
    qt_ui/workers/WorkerSubmissionPolicy.cpp
    qt_ui/workers/WorkerSubmissionPolicy.h
    qt_ui/shell/FirstRunDialog.cpp
    qt_ui/shell/FirstRunDialog.h
    qt_ui/shell/GpuMemoryProbe.cpp
    qt_ui/shell/GpuMemoryProbe.h
    qt_ui/shell/ProjectRoot.cpp
    qt_ui/shell/AppVersion.cpp
    qt_ui/shell/WorkerFailureDialog.cpp
    qt_ui/shell/WorkerFailureDialog.h
    qt_ui/shell/ProjectRoot.h
    qt_ui/shell/RuntimeProfile.cpp
    qt_ui/shell/RuntimeProfile.h
    qt_ui/shell/SecureCredentialStore.cpp
    qt_ui/shell/SecureCredentialStore.h
    qt_ui/shell/MainWindowTrayController.cpp
    qt_ui/shell/MainWindowTrayController.h
    qt_ui/shell/QueueUiPresenter.cpp
    qt_ui/shell/QueueUiPresenter.h

    qt_ui/shell/TelemetryPresenter.cpp
    qt_ui/shell/TelemetryPresenter.h
    qt_ui/shell/ShellNavigationController.cpp
    qt_ui/shell/ShellNavigationController.h
    qt_ui/workflows/CivitaiVariantDialog.cpp
    qt_ui/workflows/CivitaiVariantDialog.h
    qt_ui/workflows/ModelResolutionDialog.cpp
    qt_ui/workflows/ModelResolutionDialog.h
    qt_ui/workflows/WorkflowLaunchController.cpp
    qt_ui/workflows/WorkflowLaunchController.h
    qt_ui/preview/MediaPreviewController.cpp
    qt_ui/preview/MediaPreviewController.h

    qt_ui/preview/ImagePreviewController.cpp
    qt_ui/preview/ImagePreviewController.h
    qt_ui/preview/AspectCap.cpp
    qt_ui/preview/AspectCap.h
    qt_ui/preview/PreviewFileSettler.cpp
    qt_ui/preview/PreviewFileSettler.h
    qt_ui/ImageGenerationPage.cpp
    qt_ui/WorkflowImportDialog.h
    qt_ui/WorkflowImportDialog.cpp

    qt_ui/CustomTitleBar.h
    qt_ui/CustomTitleBar.cpp
    qt_ui/QueueManager.h
    qt_ui/QueueManager.cpp
    qt_ui/QueueTableModel.h
    qt_ui/QueueTableModel.cpp
    qt_ui/QueueFilterProxyModel.h
    qt_ui/QueueFilterProxyModel.cpp
    qt_ui/CommandPaletteDialog.h
    qt_ui/CommandPaletteDialog.cpp
    qt_ui/ThemeManager.h
    qt_ui/ThemeManager.cpp
    qt_ui/SettingsPage.h
    qt_ui/SettingsPage.cpp

    qt_ui/WorkflowLibraryPage.h
    qt_ui/WorkflowLibraryPage.cpp
    qt_ui/ModelManagerPage.h
    qt_ui/ModelManagerPage.cpp
    qt_ui/DatasetGenerationPage.h
    qt_ui/DatasetGenerationPage.cpp
    qt_ui/InspirationPage.h
    qt_ui/InspirationPage.cpp
    qt_ui/EyePickStore.h
    qt_ui/EyePickStore.cpp
    qt_ui/Gen3DPage.h
    qt_ui/Gen3DPage.cpp

    # --- CHAIN STUDIO PASS 1+2 CMAKE REGISTRATION ---
    qt_ui/chain/ChainModel.h
    qt_ui/chain/ChainStore.h
    qt_ui/chain/ChainStore.cpp
    # --- CHAIN STUDIO PASS 3 CMAKE REGISTRATION ---
    qt_ui/chain/ChainCompletionWatcher.h
    qt_ui/chain/ChainCompletionWatcher.cpp
    # --- CHAIN STUDIO PASS 4 CMAKE REGISTRATION ---
    qt_ui/chain/ChainEngine.h
    qt_ui/chain/ChainEngine.cpp
    # --- CHAIN STUDIO PASS 5 CMAKE REGISTRATION ---
    qt_ui/chain/ChainThumbnailer.h
    qt_ui/chain/ChainThumbnailer.cpp
    # --- CHAIN STUDIO PASS 6 SELF-TEST ---
    qt_ui/chain/ChainSelfTest.h
    qt_ui/chain/ChainSelfTest.cpp
    # --- CHAIN STUDIO PASS 7A CMAKE REGISTRATION ---
    qt_ui/chain/ChainStudioPage.h
    qt_ui/chain/ChainStudioPage.cpp
    # --- CHAIN STUDIO PASS 7B RAIL CMAKE REGISTRATION ---
    qt_ui/chain/ChainRailWidget.h
    qt_ui/chain/ChainRailWidget.cpp
    # --- CHAIN STUDIO PASS 7C CANVAS CMAKE REGISTRATION ---
    qt_ui/chain/ChainCanvasWidget.h
    qt_ui/chain/ChainCanvasWidget.cpp
    # --- CHAIN STUDIO PASS 7D1 CONFIG PANEL CMAKE REGISTRATION ---
    qt_ui/chain/ChainConfigPanelWidget.h
    qt_ui/chain/ChainConfigPanelWidget.cpp
    # --- CHAIN STUDIO PASS 7D2 DIALOG BAR CMAKE REGISTRATION ---
    qt_ui/chain/ChainDialogBarWidget.h
    qt_ui/chain/ChainDialogBarWidget.cpp

    # --- CHARACTER + COMIC STUDIOS ---
    qt_ui/studios/CharacterStudioPage.h
    qt_ui/studios/CharacterStudioPage.cpp
    qt_ui/studios/ComicStudioPage.h
    qt_ui/studios/ComicStudioPage.cpp
    qt_ui/studios/ConceptReferencePage.h
    qt_ui/studios/ConceptReferencePage.cpp
    qt_ui/studios/ConceptReferencePacks.h
)

target_include_directories(SpellVisionCore PUBLIC qt_ui)
# libwebp public headers (webp/decode.h) -- the webpdecoder target doesn't export its include dir.
target_include_directories(SpellVisionCore PUBLIC ${libwebp_SOURCE_DIR}/src)

# The one place the version is spelled: project(VERSION) above. Every consumer -- the About box,
# the update check, the window title -- reads QCoreApplication::applicationVersion(), which
# main() sets from this define. A second spelling anywhere is a version that will drift.
target_compile_definitions(SpellVisionCore PUBLIC SPELLVISION_VERSION="${PROJECT_VERSION}")

target_link_libraries(SpellVisionCore
    PUBLIC
    Qt6::Widgets
    Qt6::Svg
    Qt6::Multimedia
    Qt6::MultimediaWidgets
    Qt6::Concurrent
    Qt6::Network
    webpdecoder   # libwebp decode-only (native WebP thumbnails)
)

if(WIN32)
    target_link_libraries(SpellVisionCore PUBLIC
        user32
        ws2_32
        ntdll
        advapi32
        bcrypt
        crypt32
        kernel32
        userenv
        dwmapi
    )
endif()

qt_add_executable(SpellVision
    qt_ui/main.cpp
)

if(WIN32)
    target_sources(SpellVision PRIVATE qt_ui/icons/SpellVision.rc)
endif()

# Rail glyphs are loaded from disk at runtime (see loadRailIcon in MainWindow.cpp),
# so they have to land next to the exe or a deployed build falls back to a
# text-only rail. CONFIGURE_DEPENDS re-runs the glob when an icon is added.
file(GLOB SPELLVISION_RAIL_ICONS CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/qt_ui/icons/*.svg")

add_custom_command(TARGET SpellVision POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:SpellVision>/icons"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_SOURCE_DIR}/qt_ui/icons/SpellVision.ico"
        "${CMAKE_SOURCE_DIR}/qt_ui/icons/SpellVision.png"
        "${CMAKE_SOURCE_DIR}/qt_ui/icons/SpellVision_Dark.ico"
        "${CMAKE_SOURCE_DIR}/qt_ui/icons/SpellVision_Dark.png"
        "${CMAKE_SOURCE_DIR}/qt_ui/icons/SpellVision_Light.ico"
        "${CMAKE_SOURCE_DIR}/qt_ui/icons/SpellVision_Light.png"
        "$<TARGET_FILE_DIR:SpellVision>/icons"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${SPELLVISION_RAIL_ICONS}
        "$<TARGET_FILE_DIR:SpellVision>/icons"
    COMMENT "Copy brand + rail icons next to SpellVision.exe"
)

spellvision_enable_qt_runtime_deploy(SpellVision)


target_link_libraries(SpellVision PRIVATE SpellVisionCore)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
#
# enable_testing() + add_test() were both missing, so this executable was BUILT on every configure
# and never RUN by anything. 63k lines of C++ had one test and it did not execute. Registering it
# with ctest is what makes `ctest` -- and therefore CI -- able to fail on it.
enable_testing()

add_executable(test_worker_submission_policy tests/test_worker_submission_policy.cpp)
target_link_libraries(test_worker_submission_policy PRIVATE SpellVisionCore)
add_test(NAME worker_submission_policy COMMAND test_worker_submission_policy)

# Doc 30's 7-surface x 4-state responsive matrix. Doc 28 lists it as a release gate and records that
# it "is defined and has never been executed" -- it was a manual owner-eyes table because nothing
# could construct a page outside the running app. Every clause of its pass predicate is a geometry,
# visibility or message-handler assertion, so it is a test.
qt_add_executable(test_responsive_matrix tests/cpp/test_responsive_matrix.cpp)
target_link_libraries(test_responsive_matrix PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME responsive_matrix COMMAND test_responsive_matrix)

# Decision logic, not widgets. An unregistered worker message type was discarded twice -- once by
# worker_client, which reported ok TRUE, and again here, where client_warning had no case at all.
qt_add_executable(test_worker_response_parser tests/cpp/test_worker_response_parser.cpp)
target_link_libraries(test_worker_response_parser PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME worker_response_parser COMMAND test_worker_response_parser)

# The last hop of "an upscale either happens or is reported": a worker note left as the job's
# terminal message has to become the caption beside the image, not be replaced by a cheerful
# default. The controller had no test, so "the user is told" was an assumption.
qt_add_executable(test_generation_status tests/cpp/test_generation_status.cpp)
target_link_libraries(test_generation_status PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME generation_status COMMAND test_generation_status)

# The cockpit's upscale group. Two rules live in it: one switch (a checkbox beside a method list
# meant "off" was sayable twice), and Advanced revealing the raw knobs without changing what would
# be generated.
qt_add_executable(test_upscale_controller tests/cpp/test_upscale_controller.cpp)
target_link_libraries(test_upscale_controller PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME upscale_controller COMMAND test_upscale_controller)

# The LAST hop from that controller to the worker: GenerationRequestBuilder::build is pure and
# static and had no test, which is how the upscale keys spent their whole life fenced to image modes
# without anything noticing when the premise for the fence stopped being true.
qt_add_executable(test_generation_request_upscale tests/cpp/test_generation_request_upscale.cpp)
target_link_libraries(test_generation_request_upscale PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME generation_request_upscale COMMAND test_generation_request_upscale)

# A history row's mode-dependent columns. The rule existed twice -- once in Python with no caller and
# only a test, once hand-rolled in the page with no test. This is where it lives now.
qt_add_executable(test_history_row_labels tests/cpp/test_history_row_labels.cpp)
target_link_libraries(test_history_row_labels PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME history_row_labels COMMAND test_history_row_labels)

# The cockpit's sampling row. Two defects that live entirely inside the widget -- a stale dropdown
# and a seed clamped on its way out -- which the Python sweeps structurally cannot see, because the
# value is corrected before any request exists to inspect.
qt_add_executable(test_sampling_controller tests/cpp/test_sampling_controller.cpp)
target_link_libraries(test_sampling_controller PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME sampling_controller COMMAND test_sampling_controller)

# "Find the project root" was written by hand four times and the copies disagreed on how far to
# walk. The merged resolver is tested on a fixture tree rather than the real repo -- a test that
# asserted against this checkout would pass at any depth and could not catch the divergence.
# The 320 lines that decide what the worker receives. They were private members of MainWindow --
# functions of their arguments declared inside a QMainWindow -- so every default, every key that
# carries the model and the five-way command stamping were reachable only by rendering something.
qt_add_executable(test_worker_request_builder tests/cpp/test_worker_request_builder.cpp)
target_link_libraries(test_worker_request_builder PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME worker_request_builder COMMAND test_worker_request_builder)

qt_add_executable(test_project_root tests/cpp/test_project_root.cpp)
target_link_libraries(test_project_root PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME project_root COMMAND test_project_root)

# comfyHost was a hardcoded 127.0.0.1 reading no environment, while comfyPort right below it read
# its own -- so the app could be pointed at another machine's PORT and never at another machine,
# while the worker happily honoured COMFY_API_URL and generated somewhere else. The Python half of
# this pair checks that the C++ SOURCE names the same variables in the same order; this checks that
# the resolved BEHAVIOUR matches, which a source check cannot.
qt_add_executable(test_comfy_endpoint_profile tests/cpp/test_comfy_endpoint_profile.cpp)
target_link_libraries(test_comfy_endpoint_profile PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME comfy_endpoint_profile COMMAND test_comfy_endpoint_profile)

# The socket client presents the worker's per-launch session secret, read from a user-only file.
# Python proves the worker enforces it and that worker_client.py presents it; this proves the
# transport that carries every one-shot UI command does too. A reader that silently returned ""
# would have the app answering every queue poll with an auth_error.
qt_add_executable(test_worker_session_secret tests/cpp/test_worker_session_secret.cpp)
target_link_libraries(test_worker_session_secret PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME worker_session_secret COMMAND test_worker_session_secret)

# Version comparison drives "is an update available"; a wrong compare reports either a phantom
# update forever or never reports one. Pure function, table-driven.
qt_add_executable(test_app_version tests/cpp/test_app_version.cpp)
target_link_libraries(test_app_version PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME app_version COMMAND test_app_version)

# The canvas hugs the picture (preview/AspectCap). Drives the real ImagePreviewController against a
# synthetic stack and asserts convergence, no oscillation, and growth when the parent grows -- the
# last being what a naive maximum-size cap gets wrong.
qt_add_executable(test_canvas_aspect tests/cpp/test_canvas_aspect.cpp)
target_link_libraries(test_canvas_aspect PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME canvas_aspect COMMAND test_canvas_aspect)

# The LoRA stack row fits the card width it actually gets (215px at a half-screen window). Four
# full-word buttons clipped there, and the responsive matrix skips scroll-area children by design.
qt_add_executable(test_lora_stack_row tests/cpp/test_lora_stack_row.cpp)
target_link_libraries(test_lora_stack_row PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME lora_stack_row COMMAND test_lora_stack_row)

# The error pill beside Generate elides to the row it gets; the full text stays one hover or click
# away. A 280px cap showed "module 'worker_service' has no attribute 'res" and nothing else.
qt_add_executable(test_action_row_pill tests/cpp/test_action_row_pill.cpp)
target_link_libraries(test_action_row_pill PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME action_row_pill COMMAND test_action_row_pill)

# "Queue: N" counts outstanding work, not tray rows. A single failed render read as "Queue: 1".
qt_add_executable(test_queue_tally tests/cpp/test_queue_tally.cpp)
target_link_libraries(test_queue_tally PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME queue_tally COMMAND test_queue_tally)

# A page never opens with Generate blocked by a size the app could have chosen: two of the four
# generation pages opened at 0x0 behind "Choose a canvas size to generate."
qt_add_executable(test_canvas_size_default tests/cpp/test_canvas_size_default.cpp)
target_link_libraries(test_canvas_size_default PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME canvas_size_default COMMAND test_canvas_size_default)

# A value whose length the UI does not control elides and keeps its full text a hover away. The
# fixture name has NO break opportunity in it: wrap is not elision, and the old row test passed only
# because every name it used contained a hyphen.
qt_add_executable(test_eliding_label tests/cpp/test_eliding_label.cpp)
target_link_libraries(test_eliding_label PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME eliding_label COMMAND test_eliding_label)

# The bottom bar describes the page you are looking at. "Model:" showed the last-run model because
# its writer was never called on a mode change, and the page name had three writers that disagreed.
qt_add_executable(test_telemetry_presenter tests/cpp/test_telemetry_presenter.cpp)
target_link_libraries(test_telemetry_presenter PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME telemetry_presenter COMMAND test_telemetry_presenter)

# Doc 28 section 2 "Non-commercial surfaced". The licence answer used to be two family names
# hardcoded in C++ and matched as substrings, which badged animagine and would have gone silent for
# any third non-commercial family. Now generated from python/model_registry.py; this asserts the
# generated table reached the binary, that every alias answers like its key, that the decoy corpus
# is NOT badged, and that the gate has no state that blocks a render.
qt_add_executable(test_family_license tests/cpp/test_family_license.cpp)
target_link_libraries(test_family_license PRIVATE SpellVisionCore Qt6::Test)
add_test(NAME family_license COMMAND test_family_license)

# qt_add_executable makes a WIN32 (GUI subsystem) binary by default, which on Windows means the
# process has no console and everything QtTest prints is discarded. A failing case then reports
# nothing but an exit code -- ctest --output-on-failure shows an empty block -- which is exactly the
# "you cannot see why" shape this pass keeps finding. These are console programs; say so.
#
# Saying so was NOT sufficient, which took a deliberately failed assertion to discover. The binaries
# are console subsystem (dumpbin confirms CUI) and still printed zero bytes to stdout AND stderr:
# ctest logged "<end of output>" under a failure it had correctly detected. Qt routes its logging to
# the debugger rather than to the streams when it cannot see an attached console, and ctest runs
# every test through a pipe -- so the whole suite could tell you THAT a case failed and never which
# one. The environment block below is the other half of the fix.
set_target_properties(test_responsive_matrix test_worker_response_parser test_sampling_controller
                      test_project_root test_worker_request_builder test_comfy_endpoint_profile
                      test_worker_session_secret test_app_version test_canvas_aspect
                      test_lora_stack_row test_action_row_pill test_queue_tally test_canvas_size_default
                      test_family_license test_eliding_label test_telemetry_presenter
                      PROPERTIES WIN32_EXECUTABLE FALSE)

if(WIN32)
    # The app gets its Qt DLLs from windeployqt; the test executables do not, so ctest has to put
    # Qt's bin on PATH or they exit 127 before running a single case.
    #
    # QT_ASSUME_STDERR_HAS_CONSOLE makes QtTest write its results to the streams instead of to the
    # debugger. Without it every one of these tests reported a bare exit code and ctest's
    # --output-on-failure printed an empty block, so a red run named no case, no expected value and
    # no line. Verified by breaking an assertion on purpose: before, "<end of output>"; after, the
    # failing case with its actual, its expected and its file and line.
    # Every test in this directory, asked of CMake rather than retyped. The list used to be
    # hand-maintained, which meant a new test that anyone forgot to add to it exited 0xc0000135 --
    # a missing-DLL code, before main() -- and ctest printed nothing at all. A test that cannot
    # start looks exactly like a test that fails, and neither says why. Verified on
    # generation_status, which failed that way until this became a query.
    #
    # Deferred to the end of the directory rather than run here, so a test added BELOW this block is
    # covered too. Querying in place would have swapped a list that drifts for an ordering that
    # drifts, which is the same defect wearing a different hat.
    function(sv_apply_qt_test_environment)
        get_property(sv_qt_tests DIRECTORY PROPERTY TESTS)
        set_tests_properties(${sv_qt_tests} PROPERTIES
            ENVIRONMENT "PATH=$<TARGET_FILE_DIR:Qt6::Core>;$ENV{PATH};QT_ASSUME_STDERR_HAS_CONSOLE=1;QT_FORCE_STDERR_LOGGING=1")
    endfunction()
    cmake_language(DEFER CALL sv_apply_qt_test_environment)
endif()

