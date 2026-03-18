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

file(MAKE_DIRECTORY "${CMAKE_SOURCE_DIR}/lib/gen")

add_custom_target(generate_cpp ALL
  COMMAND ${Python3_EXECUTABLE} "${CMAKE_SOURCE_DIR}/gen/main.py"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  COMMENT "Generating bindings"
)

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

file(GLOB_RECURSE SOURCE_FILES "lib/*")

add_library(${PROJECT_NAME} SHARED ${SOURCE_FILES} ${CMAKE_JS_SRC})

set_target_properties(${PROJECT_NAME} PROPERTIES PREFIX "" SUFFIX ".node")

target_include_directories(${PROJECT_NAME} PRIVATE
  ${CMAKE_JS_INC}
  ${NODE_ADDON_API_DIR}
  ${DEAR_BINDINGS_INCLUDE_DIR}
)

target_link_libraries(${PROJECT_NAME} PRIVATE ${CMAKE_JS_LIB} imgui_lib)
target_compile_features(${PROJECT_NAME} PRIVATE cxx_std_17)

add_dependencies(${PROJECT_NAME} generate_cpp)

if(MSVC AND CMAKE_JS_NODELIB_DEF AND CMAKE_JS_NODELIB_TARGET)
  execute_process(COMMAND ${CMAKE_AR} /def:${CMAKE_JS_NODELIB_DEF} /out:${CMAKE_JS_NODELIB_TARGET} ${CMAKE_STATIC_LINKER_FLAGS})
endif()
