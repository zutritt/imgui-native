cmake_minimum_required(VERSION 3.15...3.31)
project(imgui)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)
option(IMGUI_ENABLE_LTO "Enable link-time optimization for Release builds" ON)

if(MSVC)
  add_compile_options(
    /utf-8
    /EHsc
    /GR-
    /bigobj
  )
  add_compile_options($<$<CONFIG:Release>:/O2>)
  add_compile_definitions(_CRT_SECURE_NO_WARNINGS)
else()
  add_compile_options(
    -fno-exceptions
    -fno-rtti
    -fvisibility=hidden
    -ffunction-sections
    -fdata-sections
  )
  add_compile_options($<$<CONFIG:Release>:-O3>)
  if(APPLE)
    add_link_options($<$<CONFIG:Release>:-Wl,-dead_strip>)
  else()
    add_link_options($<$<CONFIG:Release>:-Wl,--gc-sections>)
  endif()
  if(CMAKE_BUILD_TYPE MATCHES Release AND NOT APPLE)
    add_link_options(-s)
  endif()
endif()

if(IMGUI_ENABLE_LTO)
  include(CheckIPOSupported)
  check_ipo_supported(RESULT IMGUI_IPO_SUPPORTED OUTPUT IMGUI_IPO_ERROR)
  if(IMGUI_IPO_SUPPORTED)
    set(CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE ON)
  else()
    message(WARNING "IPO/LTO not supported by this toolchain: ${IMGUI_IPO_ERROR}")
  endif()
endif()

add_compile_definitions(
  NAPI_VERSION=8
  NAPI_DISABLE_CPP_EXCEPTIONS
)

execute_process(COMMAND node -p "require('node-addon-api').include"
                WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
                OUTPUT_VARIABLE NODE_ADDON_API_DIR)

string(STRIP ${NODE_ADDON_API_DIR} NODE_ADDON_API_DIR)
string(REPLACE "\"" "" NODE_ADDON_API_DIR ${NODE_ADDON_API_DIR})

find_package(Python3 REQUIRED COMPONENTS Interpreter)

file(MAKE_DIRECTORY "${CMAKE_SOURCE_DIR}/lib/gen/bindings")
set(DEAR_BINDINGS_OUTPUT_DIR "${CMAKE_SOURCE_DIR}/lib/gen/bindings")

execute_process(
  COMMAND ${Python3_EXECUTABLE}
    "${CMAKE_SOURCE_DIR}/deps/dear_bindings/dear_bindings.py"
    -o "${DEAR_BINDINGS_OUTPUT_DIR}/dcimgui"
    "${CMAKE_SOURCE_DIR}/deps/imgui/imgui.h"
  RESULT_VARIABLE DEAR_BINDINGS_RESULT
  OUTPUT_VARIABLE DEAR_BINDINGS_OUTPUT
  ERROR_VARIABLE DEAR_BINDINGS_ERROR
)

if(NOT DEAR_BINDINGS_RESULT EQUAL 0)
  message(FATAL_ERROR "Dear Bindings generation failed:\n${DEAR_BINDINGS_ERROR}")
endif()

message(STATUS "Dear Bindings generated successfully")

# Run the Python generator at configure time (same as dear_bindings above).
# It must run before file(GLOB_RECURSE) so the generated .cpp files exist
# when CMake collects source files for the imgui target.
execute_process(
  COMMAND ${Python3_EXECUTABLE} "${CMAKE_SOURCE_DIR}/gen/main.py"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  RESULT_VARIABLE GEN_RESULT
  OUTPUT_VARIABLE GEN_OUTPUT
  ERROR_VARIABLE GEN_ERROR
)

if(NOT GEN_RESULT EQUAL 0)
  message(FATAL_ERROR "Binding generator failed:\n${GEN_ERROR}")
endif()

message(STATUS "Bindings generated successfully")

add_library(imgui_lib STATIC
  deps/imgui/imgui.cpp
  deps/imgui/imgui_demo.cpp
  deps/imgui/imgui_draw.cpp
  deps/imgui/imgui_tables.cpp
  deps/imgui/imgui_widgets.cpp
)

target_include_directories(imgui_lib PUBLIC
  deps/imgui
)

set(DEAR_BINDINGS_INCLUDE_DIR ${CMAKE_SOURCE_DIR}/deps/dear_bindings/src)

# ─── Backend options ────────────────────────────────────────────────────────
# Default build: GLFW platform backend + OpenGL3 renderer backend.
# Other backends must be enabled explicitly (-DIMGUI_BACKEND_SDL2=ON etc.).
# Note: JS also exposes ImplGlfw3 as an alias of ImplGlfw for convenience.
option(IMGUI_BACKEND_GLFW       "Compile with GLFW platform backend"         ON)
option(IMGUI_RENDERER_OPENGL3   "Compile with OpenGL3 renderer backend"      ON)
option(IMGUI_RENDERER_OPENGL2   "Compile with OpenGL2 renderer backend"      OFF)
option(IMGUI_BACKEND_SDL2       "Compile with SDL2 platform backend"         OFF)
option(IMGUI_BACKEND_SDL3       "Compile with SDL3 platform backend"         OFF)

set(BACKEND_SOURCES "")
set(BACKEND_DEFINES "")
set(BACKEND_INCLUDES "")
set(BACKEND_LIBS "")

# ── GLFW platform backend ───────────────────────────────────────────────────
if(IMGUI_BACKEND_GLFW)
  set(GLFW_TARGET "")
  find_package(glfw3 CONFIG QUIET)
  find_package(glfw3 QUIET)

  if(TARGET glfw)
    set(GLFW_TARGET glfw)
  elseif(TARGET glfw3::glfw)
    set(GLFW_TARGET glfw3::glfw)
  elseif(TARGET glfw3)
    set(GLFW_TARGET glfw3)
  endif()

  if(NOT GLFW_TARGET)
    message(WARNING "GLFW not found via CMake package — disabling IMGUI_BACKEND_GLFW")
    set(IMGUI_BACKEND_GLFW OFF)
  else()
    message(STATUS "GLFW target: ${GLFW_TARGET}")
  endif()
endif()

if(IMGUI_BACKEND_GLFW)
  list(APPEND BACKEND_SOURCES
    deps/imgui/backends/imgui_impl_glfw.cpp
    "${CMAKE_SOURCE_DIR}/lib/gen/backends/dcimgui_impl_glfw.cpp"
  )
  list(APPEND BACKEND_DEFINES IMGUI_BACKEND_GLFW)
  list(APPEND BACKEND_INCLUDES "${CMAKE_SOURCE_DIR}/deps/imgui/backends")
  list(APPEND BACKEND_LIBS ${GLFW_TARGET})
endif()

# ── OpenGL3 renderer backend ────────────────────────────────────────────────
set(OPENGL_TARGET "")
set(OPENGL_BACKEND_LIBS "")
if(IMGUI_RENDERER_OPENGL3 OR IMGUI_RENDERER_OPENGL2)
  find_package(OpenGL QUIET)
  if(TARGET OpenGL::GL)
    set(OPENGL_TARGET OpenGL::GL)
  elseif(TARGET OpenGL::OpenGL)
    set(OPENGL_TARGET OpenGL::OpenGL)
  endif()

  if(NOT OPENGL_TARGET)
    message(WARNING "OpenGL not found via CMake package — disabling OpenGL backends")
    set(IMGUI_RENDERER_OPENGL3 OFF)
    set(IMGUI_RENDERER_OPENGL2 OFF)
  else()
    set(OPENGL_BACKEND_LIBS ${OPENGL_TARGET})
    if(CMAKE_DL_LIBS)
      list(APPEND OPENGL_BACKEND_LIBS ${CMAKE_DL_LIBS})
    endif()
    message(STATUS "OpenGL target: ${OPENGL_TARGET}")
  endif()
endif()

if(IMGUI_RENDERER_OPENGL3)
  list(APPEND BACKEND_SOURCES
    deps/imgui/backends/imgui_impl_opengl3.cpp
    "${CMAKE_SOURCE_DIR}/lib/gen/backends/dcimgui_impl_opengl3.cpp"
  )
  list(APPEND BACKEND_DEFINES IMGUI_RENDERER_OPENGL3)
  list(APPEND BACKEND_INCLUDES "${CMAKE_SOURCE_DIR}/deps/imgui/backends")
  list(APPEND BACKEND_LIBS ${OPENGL_BACKEND_LIBS})
endif()

# ── OpenGL2 renderer backend ────────────────────────────────────────────────
if(IMGUI_RENDERER_OPENGL2)
  if(OPENGL_TARGET)
    list(APPEND BACKEND_SOURCES
      deps/imgui/backends/imgui_impl_opengl2.cpp
      "${CMAKE_SOURCE_DIR}/lib/gen/backends/dcimgui_impl_opengl2.cpp"
    )
    list(APPEND BACKEND_DEFINES IMGUI_RENDERER_OPENGL2)
    list(APPEND BACKEND_INCLUDES "${CMAKE_SOURCE_DIR}/deps/imgui/backends")
    list(APPEND BACKEND_LIBS ${OPENGL_BACKEND_LIBS})
  else()
    message(WARNING "OpenGL target missing — disabling IMGUI_RENDERER_OPENGL2")
    set(IMGUI_RENDERER_OPENGL2 OFF)
  endif()
endif()

# ── SDL2 platform backend ───────────────────────────────────────────────────
if(IMGUI_BACKEND_SDL2)
  set(SDL2_TARGET "")
  find_package(SDL2 CONFIG QUIET)
  find_package(SDL2 QUIET)

  if(TARGET SDL2::SDL2)
    set(SDL2_TARGET SDL2::SDL2)
  elseif(TARGET SDL2::SDL2-static)
    set(SDL2_TARGET SDL2::SDL2-static)
  endif()

  if(NOT SDL2_TARGET)
    message(WARNING "SDL2 not found via CMake package — disabling IMGUI_BACKEND_SDL2")
    set(IMGUI_BACKEND_SDL2 OFF)
  else()
    message(STATUS "SDL2 target: ${SDL2_TARGET}")
  endif()
endif()

if(IMGUI_BACKEND_SDL2)
  list(APPEND BACKEND_SOURCES
    deps/imgui/backends/imgui_impl_sdl2.cpp
    "${CMAKE_SOURCE_DIR}/lib/gen/backends/dcimgui_impl_sdl2.cpp"
  )
  list(APPEND BACKEND_DEFINES IMGUI_BACKEND_SDL2)
  list(APPEND BACKEND_INCLUDES "${CMAKE_SOURCE_DIR}/deps/imgui/backends")
  list(APPEND BACKEND_LIBS ${SDL2_TARGET})
endif()

# ── SDL3 platform backend ───────────────────────────────────────────────────
if(IMGUI_BACKEND_SDL3)
  set(SDL3_TARGET "")
  find_package(SDL3 CONFIG QUIET)
  find_package(SDL3 QUIET)

  if(TARGET SDL3::SDL3)
    set(SDL3_TARGET SDL3::SDL3)
  elseif(TARGET SDL3::SDL3-static)
    set(SDL3_TARGET SDL3::SDL3-static)
  endif()

  if(NOT SDL3_TARGET)
    message(WARNING "SDL3 not found via CMake package — disabling IMGUI_BACKEND_SDL3")
    set(IMGUI_BACKEND_SDL3 OFF)
  else()
    message(STATUS "SDL3 target: ${SDL3_TARGET}")
  endif()
endif()

if(IMGUI_BACKEND_SDL3)
  list(APPEND BACKEND_SOURCES
    deps/imgui/backends/imgui_impl_sdl3.cpp
    "${CMAKE_SOURCE_DIR}/lib/gen/backends/dcimgui_impl_sdl3.cpp"
  )
  list(APPEND BACKEND_DEFINES IMGUI_BACKEND_SDL3)
  list(APPEND BACKEND_INCLUDES "${CMAKE_SOURCE_DIR}/deps/imgui/backends")
  list(APPEND BACKEND_LIBS ${SDL3_TARGET})
endif()

message(STATUS "Active backends: ${BACKEND_DEFINES}")

file(GLOB_RECURSE SOURCE_FILES
  "lib/*.cpp" "lib/*.h"
  "lib/gen/*.cpp" "lib/gen/*.h"
  "lib/gen/napi/*.cpp" "lib/gen/napi/*.h"
  "lib/gen/backend_napi/*.cpp" "lib/gen/backend_napi/*.h"
)

# Generated C backend wrappers under lib/gen/backends are compiled only via
# BACKEND_SOURCES when the corresponding backend is enabled.
list(FILTER SOURCE_FILES EXCLUDE REGEX "lib/gen/backends/.*\\.cpp$")

add_library(${PROJECT_NAME} SHARED ${SOURCE_FILES} ${BACKEND_SOURCES} ${CMAKE_JS_SRC})

set_target_properties(${PROJECT_NAME} PROPERTIES PREFIX "" SUFFIX ".node")

target_include_directories(${PROJECT_NAME} PRIVATE
  ${CMAKE_JS_INC}
  ${NODE_ADDON_API_DIR}
  ${DEAR_BINDINGS_INCLUDE_DIR}
  "${DEAR_BINDINGS_OUTPUT_DIR}"
  "${CMAKE_SOURCE_DIR}/lib/gen/napi"
  "${CMAKE_SOURCE_DIR}/lib/gen/backends"
  "${CMAKE_SOURCE_DIR}/lib/gen/backend_napi"
  ${BACKEND_INCLUDES}
)

target_compile_definitions(${PROJECT_NAME} PRIVATE ${BACKEND_DEFINES})
target_link_libraries(${PROJECT_NAME} PRIVATE ${CMAKE_JS_LIB} imgui_lib ${BACKEND_LIBS})
target_compile_features(${PROJECT_NAME} PRIVATE cxx_std_17)

set_source_files_properties(
  "${DEAR_BINDINGS_OUTPUT_DIR}/dcimgui.cpp"
  "${DEAR_BINDINGS_OUTPUT_DIR}/dcimgui.h"
  PROPERTIES GENERATED TRUE
)

if(MSVC AND CMAKE_JS_NODELIB_DEF AND CMAKE_JS_NODELIB_TARGET)
  execute_process(COMMAND ${CMAKE_AR} /def:${CMAKE_JS_NODELIB_DEF} /out:${CMAKE_JS_NODELIB_TARGET} ${CMAKE_STATIC_LINKER_FLAGS})
endif()
