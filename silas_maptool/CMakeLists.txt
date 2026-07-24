cmake_minimum_required(VERSION 3.20)
project(silas_maptool_native LANGUAGES CXX)

find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(jps_planner_bindings
  vendor/jps3d/bindings.cpp
  vendor/jps3d/src/wrapper.cpp
  vendor/jps3d/src/jps_planner/graph_search.cpp
  vendor/jps3d/src/jps_planner/jps_planner.cpp
)
target_include_directories(jps_planner_bindings PRIVATE vendor/jps3d/include vendor/eigen3)
target_compile_features(jps_planner_bindings PRIVATE cxx_std_14)
target_compile_definitions(jps_planner_bindings PRIVATE EIGEN_MPL2_ONLY)
if(MSVC)
  target_compile_options(jps_planner_bindings PRIVATE /O2 /EHsc /permissive-)
else()
  target_compile_options(jps_planner_bindings PRIVATE -O3 -fvisibility=hidden)
endif()
install(TARGETS jps_planner_bindings LIBRARY DESTINATION silas_maptool RUNTIME DESTINATION silas_maptool)
