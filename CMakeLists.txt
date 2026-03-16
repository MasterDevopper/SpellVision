cmake_minimum_required(VERSION 3.21)
project(SpellVision LANGUAGES CXX)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets)

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

add_executable(SpellVision
    qt_ui/main.cpp
    qt_ui/MainWindow.cpp
    qt_ui/MainWindow.h
    qt_ui/QueueManager.cpp
    qt_ui/QueueManager.h
)

spellvision_enable_qt_runtime_deploy(SpellVision)

add_dependencies(SpellVision spellvision_rust)

target_include_directories(SpellVision PRIVATE qt_ui)

target_link_libraries(SpellVision
    PRIVATE
    Qt6::Widgets
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
