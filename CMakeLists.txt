cmake_minimum_required(VERSION 3.21)
project(SpellVision LANGUAGES CXX)

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

find_package(Qt6 REQUIRED COMPONENTS Widgets Svg Multimedia MultimediaWidgets Concurrent Network)

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

qt_add_executable(SpellVision
    qt_ui/main.cpp

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
    qt_ui/generation/CockpitInspector.cpp
    qt_ui/generation/CockpitInspector.h
    qt_ui/generation/SamplingController.cpp
    qt_ui/generation/SamplingController.h
    qt_ui/assets/ModelStackState.cpp
    qt_ui/assets/ModelStackState.h

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
    qt_ui/workers/WorkerResponseParser.cpp
    qt_ui/workers/WorkerResponseParser.h

    qt_ui/workers/WorkerCommandRunner.cpp
    qt_ui/workers/WorkerCommandRunner.h

    qt_ui/workers/WorkerProcessController.cpp
    qt_ui/workers/WorkerProcessController.h

    qt_ui/workers/WorkerQueueController.cpp
    qt_ui/workers/WorkerQueueController.h
    qt_ui/workers/WorkerSubmissionPolicy.cpp
    qt_ui/workers/WorkerSubmissionPolicy.h
    qt_ui/shell/FirstRunDialog.cpp
    qt_ui/shell/FirstRunDialog.h
    qt_ui/shell/RuntimeProfile.cpp
    qt_ui/shell/RuntimeProfile.h
    qt_ui/shell/SecureCredentialStore.cpp
    qt_ui/shell/SecureCredentialStore.h
    qt_ui/shell/MainWindowTrayController.cpp
    qt_ui/shell/MainWindowTrayController.h
    qt_ui/shell/QueueUiPresenter.cpp
    qt_ui/shell/QueueUiPresenter.h
    qt_ui/shell/ShellNavigationController.cpp
    qt_ui/shell/ShellNavigationController.h
    qt_ui/workflows/WorkflowLaunchController.cpp
    qt_ui/workflows/WorkflowLaunchController.h
    qt_ui/preview/MediaPreviewController.cpp
    qt_ui/preview/MediaPreviewController.h

    qt_ui/preview/ImagePreviewController.cpp
    qt_ui/preview/ImagePreviewController.h
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

target_include_directories(SpellVision PRIVATE qt_ui)
# libwebp public headers (webp/decode.h) — the webpdecoder target doesn't export its include dir.
target_include_directories(SpellVision PRIVATE ${libwebp_SOURCE_DIR}/src)

target_link_libraries(SpellVision
    PRIVATE
    Qt6::Widgets
    Qt6::Svg
    Qt6::Multimedia
    Qt6::MultimediaWidgets
    Qt6::Concurrent
    Qt6::Network
    webpdecoder   # libwebp decode-only (native WebP thumbnails)
)

add_executable(test_worker_submission_policy
    tests/test_worker_submission_policy.cpp
    qt_ui/workers/WorkerSubmissionPolicy.cpp
    qt_ui/workers/WorkerSubmissionPolicy.h
)
target_include_directories(test_worker_submission_policy PRIVATE qt_ui)
target_link_libraries(test_worker_submission_policy PRIVATE Qt6::Core)

if(WIN32)
    target_link_libraries(SpellVision PRIVATE
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
