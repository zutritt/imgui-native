cmake_minimum_required(VERSION 3.15...3.31)
project(imgui)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION ON)

add_compile_options(
  -O3
  -fno-exceptions
  -fno-rtti
  -fvisibility=hidden
  -flto=auto
  -ffunction-sections
  -fdata-sections
)

add_link_options(
  -O3
  -Wl,--gc-sections
  -Wl,-z,now
  -flto=auto
)

if(CMAKE_BUILD_TYPE MATCHES Release)
  add_link_options(-s)
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
option(IMGUI_BACKEND_GLFW       "Compile with GLFW platform backend"         ON)
option(IMGUI_RENDERER_OPENGL3   "Compile with OpenGL3 renderer backend"      ON)
option(IMGUI_RENDERER_OPENGL2   "Compile with OpenGL2 renderer backend"      OFF)
option(IMGUI_BACKEND_SDL2       "Compile with SDL2 platform backend"         OFF)
option(IMGUI_BACKEND_SDL3       "Compile with SDL3 platform backend"         OFF)
option(IMGUI_RENDERER_SDLRENDERER2 "Compile with SDL2 renderer backend"     OFF)
option(IMGUI_RENDERER_SDLRENDERER3 "Compile with SDL3 renderer backend"     OFF)

set(BACKEND_SOURCES "")
set(BACKEND_DEFINES "")
set(BACKEND_INCLUDES "")
set(BACKEND_LIBS "")

# ── GLFW platform backend ───────────────────────────────────────────────────
if(IMGUI_BACKEND_GLFW)
  find_package(glfw3 QUIET)
  if(NOT glfw3_FOUND)
    # Fallback: look for the library directly (system install or deps-opengl-raub)
    find_library(GLFW_LIB NAMES glfw glfw3
      PATHS
        "${CMAKE_SOURCE_DIR}/node_modules/deps-opengl-raub/bin-linux"
        /usr/lib /usr/local/lib
    )
    find_path(GLFW_INCLUDE NAMES GLFW/glfw3.h
      PATHS
        "${CMAKE_SOURCE_DIR}/node_modules/deps-opengl-raub/include"
        /usr/include /usr/local/include
    )
    if(GLFW_LIB AND GLFW_INCLUDE)
      add_library(glfw3_imported UNKNOWN IMPORTED)
      set_target_properties(glfw3_imported PROPERTIES
        IMPORTED_LOCATION "${GLFW_LIB}"
        INTERFACE_INCLUDE_DIRECTORIES "${GLFW_INCLUDE}"
      )
      set(GLFW_TARGET glfw3_imported)
      message(STATUS "GLFW found: ${GLFW_LIB}")
    else()
      message(WARNING "GLFW not found — disabling IMGUI_BACKEND_GLFW")
      set(IMGUI_BACKEND_GLFW OFF)
    endif()
  else()
    set(GLFW_TARGET glfw)
    message(STATUS "GLFW found via find_package")
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
if(IMGUI_RENDERER_OPENGL3)
  # imgui_impl_opengl3 uses a bundled GL loader; on Linux it needs libGL and libdl.
  find_library(OPENGL_LIB NAMES GL
    PATHS
      "${CMAKE_SOURCE_DIR}/node_modules/deps-opengl-raub/bin-linux"
      /usr/lib /usr/local/lib
  )
  if(NOT OPENGL_LIB)
    message(WARNING "libGL not found — disabling IMGUI_RENDERER_OPENGL3")
    set(IMGUI_RENDERER_OPENGL3 OFF)
  else()
    message(STATUS "OpenGL found: ${OPENGL_LIB}")
  endif()
endif()

if(IMGUI_RENDERER_OPENGL3)
  list(APPEND BACKEND_SOURCES
    deps/imgui/backends/imgui_impl_opengl3.cpp
    "${CMAKE_SOURCE_DIR}/lib/gen/backends/dcimgui_impl_opengl3.cpp"
  )
  list(APPEND BACKEND_DEFINES IMGUI_RENDERER_OPENGL3)
  list(APPEND BACKEND_INCLUDES "${CMAKE_SOURCE_DIR}/deps/imgui/backends")
  list(APPEND BACKEND_LIBS ${OPENGL_LIB} dl)
endif()

# ── OpenGL2 renderer backend ────────────────────────────────────────────────
if(IMGUI_RENDERER_OPENGL2)
  if(NOT OPENGL_LIB)
    find_library(OPENGL_LIB NAMES GL
      PATHS "${CMAKE_SOURCE_DIR}/node_modules/deps-opengl-raub/bin-linux" /usr/lib)
  endif()
  if(OPENGL_LIB)
    list(APPEND BACKEND_SOURCES
      deps/imgui/backends/imgui_impl_opengl2.cpp
      "${CMAKE_SOURCE_DIR}/lib/gen/backends/dcimgui_impl_opengl2.cpp"
    )
    list(APPEND BACKEND_DEFINES IMGUI_RENDERER_OPENGL2)
    list(APPEND BACKEND_INCLUDES "${CMAKE_SOURCE_DIR}/deps/imgui/backends")
    list(APPEND BACKEND_LIBS ${OPENGL_LIB} dl)
  else()
    message(WARNING "libGL not found — disabling IMGUI_RENDERER_OPENGL2")
    set(IMGUI_RENDERER_OPENGL2 OFF)
  endif()
endif()

# ── SDL2 platform backend ───────────────────────────────────────────────────
if(IMGUI_BACKEND_SDL2)
  find_package(SDL2 QUIET)
  if(NOT SDL2_FOUND)
    find_library(SDL2_LIB NAMES SDL2)
    find_path(SDL2_INCLUDE NAMES SDL2/SDL.h SDL.h)
    if(SDL2_LIB AND SDL2_INCLUDE)
      add_library(SDL2_imported UNKNOWN IMPORTED)
      set_target_properties(SDL2_imported PROPERTIES
        IMPORTED_LOCATION "${SDL2_LIB}"
        INTERFACE_INCLUDE_DIRECTORIES "${SDL2_INCLUDE}"
      )
      set(SDL2_TARGET SDL2_imported)
    else()
      message(WARNING "SDL2 not found — disabling IMGUI_BACKEND_SDL2")
      set(IMGUI_BACKEND_SDL2 OFF)
    endif()
  else()
    set(SDL2_TARGET SDL2::SDL2)
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

# ── SDL2 renderer backend ───────────────────────────────────────────────────
if(IMGUI_RENDERER_SDLRENDERER2)
  if(NOT SDL2_TARGET)
    message(WARNING "SDL2 not configured — disabling IMGUI_RENDERER_SDLRENDERER2")
    set(IMGUI_RENDERER_SDLRENDERER2 OFF)
  else()
    list(APPEND BACKEND_SOURCES
      deps/imgui/backends/imgui_impl_sdlrenderer2.cpp
      "${CMAKE_SOURCE_DIR}/lib/gen/backends/dcimgui_impl_sdlrenderer2.cpp"
    )
    list(APPEND BACKEND_DEFINES IMGUI_RENDERER_SDLRENDERER2)
    list(APPEND BACKEND_INCLUDES "${CMAKE_SOURCE_DIR}/deps/imgui/backends")
    list(APPEND BACKEND_LIBS ${SDL2_TARGET})
  endif()
endif()

# ── SDL3 platform backend ───────────────────────────────────────────────────
if(IMGUI_BACKEND_SDL3)
  find_package(SDL3 QUIET)
  if(NOT SDL3_FOUND)
    find_library(SDL3_LIB NAMES SDL3)
    find_path(SDL3_INCLUDE NAMES SDL3/SDL.h)
    if(SDL3_LIB AND SDL3_INCLUDE)
      add_library(SDL3_imported UNKNOWN IMPORTED)
      set_target_properties(SDL3_imported PROPERTIES
        IMPORTED_LOCATION "${SDL3_LIB}"
        INTERFACE_INCLUDE_DIRECTORIES "${SDL3_INCLUDE}"
      )
      set(SDL3_TARGET SDL3_imported)
    else()
      message(WARNING "SDL3 not found — disabling IMGUI_BACKEND_SDL3")
      set(IMGUI_BACKEND_SDL3 OFF)
    endif()
  else()
    set(SDL3_TARGET SDL3::SDL3)
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

# ── SDL3 renderer backend ───────────────────────────────────────────────────
if(IMGUI_RENDERER_SDLRENDERER3)
  if(NOT SDL3_TARGET)
    message(WARNING "SDL3 not configured — disabling IMGUI_RENDERER_SDLRENDERER3")
    set(IMGUI_RENDERER_SDLRENDERER3 OFF)
  else()
    list(APPEND BACKEND_SOURCES
      deps/imgui/backends/imgui_impl_sdlrenderer3.cpp
      "${CMAKE_SOURCE_DIR}/lib/gen/backends/dcimgui_impl_sdlrenderer3.cpp"
    )
    list(APPEND BACKEND_DEFINES IMGUI_RENDERER_SDLRENDERER3)
    list(APPEND BACKEND_INCLUDES "${CMAKE_SOURCE_DIR}/deps/imgui/backends")
    list(APPEND BACKEND_LIBS ${SDL3_TARGET})
  endif()
endif()

message(STATUS "Active backends: ${BACKEND_DEFINES}")

file(GLOB_RECURSE SOURCE_FILES
  "lib/*.cpp" "lib/*.h"
  "lib/gen/*.cpp" "lib/gen/*.h"
  "lib/gen/napi/*.cpp" "lib/gen/napi/*.h"
  "lib/gen/backend_napi/*.cpp" "lib/gen/backend_napi/*.h"
)

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
