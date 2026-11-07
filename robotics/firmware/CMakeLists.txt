# ESP-IDF project for SENTINEL HIVE rover motor controller.
# Build: idf.py set-target esp32 && idf.py build flash monitor
# Host-side unit tests live in test/ and build with plain CMake + g++.

cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(rover-fw)
