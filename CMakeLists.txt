cmake_minimum_required(VERSION 3.18)
project(structquery LANGUAGES C CXX)

# Indri 5.21 is pre-C++11 code; it builds cleanly as gnu++11/14 but not as C++17
# (it uses `register`, dynamic exception specs, std::auto_ptr-era idioms).
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

set(INDRI_DIR "${CMAKE_CURRENT_SOURCE_DIR}/third_party/indri")
if(NOT EXISTS "${INDRI_DIR}/src/QueryEnvironment.cpp")
  message(FATAL_ERROR "Bundled Indri source not found at ${INDRI_DIR}")
endif()

find_package(Threads REQUIRED)
find_package(ZLIB REQUIRED)
include(CheckIncludeFileCXX)
check_include_file_cxx("ext/atomicity.h" HAVE_EXT_ATOMICITY_H)

# The same translation units Indri's own makefiles build into libindri.a.
file(GLOB INDRI_SOURCES CONFIGURE_DEPENDS
  "${INDRI_DIR}/src/*.cpp" "${INDRI_DIR}/src/*.c"
  "${INDRI_DIR}/contrib/antlr/src/*.cpp"
  "${INDRI_DIR}/contrib/lemur/src/*.cpp" "${INDRI_DIR}/contrib/lemur/src/*.c"
  "${INDRI_DIR}/contrib/xpdf/src/*.cc" "${INDRI_DIR}/contrib/xpdf/src/*.cpp"
  "${INDRI_DIR}/contrib/xpdf/src/*.c")

add_library(indri_static STATIC ${INDRI_SOURCES})
set_target_properties(indri_static PROPERTIES
  CXX_STANDARD 11 CXX_STANDARD_REQUIRED ON CXX_EXTENSIONS ON
  C_VISIBILITY_PRESET hidden CXX_VISIBILITY_PRESET hidden)
target_include_directories(indri_static PUBLIC
  "${INDRI_DIR}/include"
  "${INDRI_DIR}/contrib/lemur/include"
  "${INDRI_DIR}/contrib/antlr/include"
  "${INDRI_DIR}/contrib/xpdf/include")
target_include_directories(indri_static PRIVATE
  "${INDRI_DIR}/contrib/lemur/include/lemur")
# Mirrors the DEFS that Indri's ./configure emits on Linux/macOS.
target_compile_definitions(indri_static PUBLIC
  PACKAGE_NAME="Indri" PACKAGE_TARNAME="indri" PACKAGE_VERSION="5.21"
  PACKAGE_STRING="Indri 5.21" PACKAGE_BUGREPORT="project@lemurproject.org"
  INDRI_STANDALONE=1 HAVE_LIBM=1 HAVE_LIBPTHREAD=1 HAVE_LIBZ=1
  HAVE_NAMESPACES= ISNAN_IN_NAMESPACE_STD= STDC_HEADERS=1
  HAVE_SYS_TYPES_H=1 HAVE_SYS_STAT_H=1 HAVE_STDLIB_H=1 HAVE_STRING_H=1
  HAVE_MEMORY_H=1 HAVE_STRINGS_H=1 HAVE_INTTYPES_H=1 HAVE_STDINT_H=1
  HAVE_UNISTD_H=1 HAVE_FSEEKO=1 HAVE_MKSTEMP=1 NDEBUG=1)
if(HAVE_EXT_ATOMICITY_H)
  target_compile_definitions(indri_static PUBLIC HAVE_EXT_ATOMICITY_H=1 P_NEEDS_GNU_CXX_NAMESPACE=1)
endif()
target_compile_options(indri_static PRIVATE -w)   # third-party code: silence its warnings
target_link_libraries(indri_static PUBLIC ZLIB::ZLIB Threads::Threads)

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)
pybind11_add_module(_structquery MODULE src/_structquery.cpp)
# Indri headers are not C++17-clean; pybind11 needs at least C++11/14.
set_target_properties(_structquery PROPERTIES CXX_STANDARD 14 CXX_STANDARD_REQUIRED ON CXX_EXTENSIONS ON)
target_compile_options(_structquery PRIVATE -Wno-deprecated-declarations -Wno-deprecated)
target_link_libraries(_structquery PRIVATE indri_static)

install(TARGETS _structquery LIBRARY DESTINATION structquery)
