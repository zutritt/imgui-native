cmake_minimum_required(VERSION 3.15...3.31)
project(imgui)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_compile_definitions(
  NAPI_VERSION=8
  NAPI_DISABLE_CPP_EXCEPTIONS
)

execute_process(COMMAND node -p "require('node-addon-api').include"
                WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
                OUTPUT_VARIABLE NODE_ADDON_API_DIR)

string(STRIP ${NODE_ADDON_API_DIR} NODE_ADDON_API_DIR)
string(REPLACE "\"" "" NODE_ADDON_API_DIR ${NODE_ADDON_API_DIR})

file(GLOB SOURCE_FILES "lib/*")

add_library(${PROJECT_NAME} SHARED ${SOURCE_FILES} ${CMAKE_JS_SRC})

set_target_properties(${PROJECT_NAME} PROPERTIES PREFIX "" SUFFIX ".node")

target_include_directories(${PROJECT_NAME} PRIVATE
  ${CMAKE_JS_INC}
  ${NODE_ADDON_API_DIR}
)

target_link_libraries(${PROJECT_NAME} PRIVATE ${CMAKE_JS_LIB})
target_compile_features(${PROJECT_NAME} PRIVATE cxx_std_17)

if(MSVC AND CMAKE_JS_NODELIB_DEF AND CMAKE_JS_NODELIB_TARGET)
  execute_process(COMMAND ${CMAKE_AR} /def:${CMAKE_JS_NODELIB_DEF} /out:${CMAKE_JS_NODELIB_TARGET} ${CMAKE_STATIC_LINKER_FLAGS})
endif()
