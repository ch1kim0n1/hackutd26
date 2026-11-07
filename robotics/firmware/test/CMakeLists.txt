cmake_minimum_required(VERSION 3.16)
project(rover-fw-tests CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Host build of the portable core only — hal_espidf.cpp and main.cpp are
# ESP-IDF-only and intentionally excluded.
add_executable(rover_tests
    ../main/rover_types.cpp
    ../main/rover_json.cpp
    ../main/rover_protocol.cpp
    ../main/rover_controller.cpp
    rover_tests.cpp
)
target_include_directories(rover_tests PRIVATE ../main)
if(MSVC)
    target_compile_options(rover_tests PRIVATE /W4)
else()
    target_compile_options(rover_tests PRIVATE -Wall -Wextra -Wpedantic)
endif()

enable_testing()
add_test(NAME rover_tests COMMAND rover_tests)

# Scripted telemetry simulator — prints JSON telemetry lines for evidence.
add_executable(rover_sim
    ../main/rover_types.cpp
    ../main/rover_json.cpp
    ../main/rover_protocol.cpp
    ../main/rover_controller.cpp
    sim.cpp
)
target_include_directories(rover_sim PRIVATE ../main)
