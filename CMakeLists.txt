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

find_package(Qt6 REQUIRED COMPONENTS Widgets Svg Multimedia MultimediaWidgets Concurrent)

include(cmake/SpellVisionQtDeploy.cmake)

add_custom_target(spellvision_rust ALL
    COMMAND cargo build --manifest-path ${CMAKE_SOURCE_DIR}/rust/Cargo.toml
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/rust
    COMMENT "Building Rust core"
)

if(WIN32)
    set(RUST_LIB_PATH ${CMAKE_SOURCE_DIR}/rust/target/debug/spellvision_core.lib)
else()
    set(RUST_LIB_PATH ${CMAKE_SOURCE_DIR}/rust/target/debug/libspellvision_core.a)
endif()

add_library(spellvision_core STATIC IMPORTED GLOBAL)
set_target_properties(spellvision_core PROPERTIES
    IMPORTED_LOCATION ${RUST_LIB_PATH}
)

qt_add_executable(SpellVision
    qt_ui/main.cpp

    qt_ui/MainWindow.h
    qt_ui/MainWindow.cpp

    qt_ui/HomePage.h
    qt_ui/HomePage.cpp
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
    qt_ui/ManagerPage.h
    qt_ui/ManagerPage.cpp
    qt_ui/ImageGenerationPage.h
    qt_ui/preview/MediaPreviewController.cpp
    qt_ui/preview/MediaPreviewController.h
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
)

spellvision_enable_qt_runtime_deploy(SpellVision)

add_dependencies(SpellVision spellvision_rust)

target_include_directories(SpellVision PRIVATE qt_ui)

target_link_libraries(SpellVision
    PRIVATE
    Qt6::Widgets
    Qt6::Svg
    Qt6::Multimedia
    Qt6::MultimediaWidgets
    Qt6::Concurrent
    spellvision_core
)

if(WIN32)
    target_link_libraries(SpellVision PRIVATE
        user32
        ws2_32
        ntdll
        advapi32
        bcrypt
        kernel32
        userenv
    )
endif()