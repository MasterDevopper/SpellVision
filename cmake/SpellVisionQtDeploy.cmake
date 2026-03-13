function(spellvision_enable_qt_runtime_deploy target_name)
    if(NOT WIN32)
        return()
    endif()

    if(NOT TARGET ${target_name})
        message(FATAL_ERROR "spellvision_enable_qt_runtime_deploy: target '${target_name}' does not exist")
    endif()

    get_target_property(_target_type ${target_name} TYPE)
    if(NOT _target_type STREQUAL "EXECUTABLE")
        message(STATUS "Qt runtime deploy skipped for non-executable target '${target_name}'")
        return()
    endif()

    set(_qt_bin_hints)

    if(DEFINED Qt6_DIR)
        get_filename_component(_qt_cmake_dir "${Qt6_DIR}" ABSOLUTE)
        get_filename_component(_qt_prefix "${_qt_cmake_dir}/../../.." ABSOLUTE)
        list(APPEND _qt_bin_hints "${_qt_prefix}/bin")
    endif()

    foreach(_prefix IN LISTS CMAKE_PREFIX_PATH)
        if(EXISTS "${_prefix}/bin")
            list(APPEND _qt_bin_hints "${_prefix}/bin")
        endif()
    endforeach()

    find_program(WINDEPLOYQT_EXECUTABLE
        NAMES windeployqt windeployqt.exe
        HINTS ${_qt_bin_hints})

    if(NOT WINDEPLOYQT_EXECUTABLE)
        message(WARNING "windeployqt not found; Qt runtime will not be auto-deployed for ${target_name}")
        return()
    endif()

    add_custom_command(TARGET ${target_name} POST_BUILD
        COMMAND "${WINDEPLOYQT_EXECUTABLE}"
                --dir "$<TARGET_FILE_DIR:${target_name}>"
                --$<IF:$<CONFIG:Debug>,debug,release>
                "$<TARGET_FILE:${target_name}>"
        COMMENT "Running windeployqt for ${target_name}"
        VERBATIM)
endfunction()