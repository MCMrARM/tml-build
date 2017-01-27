cmake_minimum_required(VERSION 2.6.3)

set(CMAKE_SYSTEM_NAME Android)
set(CMAKE_ANDROID_API_MIN 14)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fno-rtti")

if (DEFINED CMAKE_CROSSCOMPILING OR NOT DEFINED CMAKE_ANDROID_ARCH_ABI)
  return()
endif()
if( CMAKE_TOOLCHAIN_FILE )
endif()

# base TML paths
get_filename_component(TML_DEVTOOLS_PATH ${CMAKE_CURRENT_LIST_DIR} DIRECTORY)
set(TML_PACKAGES_PATH ${TML_DEVTOOLS_PATH}/packages)

# get build architecture
set(TML_ARCH ${CMAKE_ANDROID_ARCH_ABI})
message("TML Mod architecture: ${TML_ARCH}")
if (NOT TML_ARCH STREQUAL "armeabi-v7a" AND NOT TML_ARCH STREQUAL "x86")
  message(FATAL_ERROR "Unsupported TML Mod architecture: ${TML_ARCH}")
endif()

# find TML packages
function (find_tml_package pkg)
  string(TOLOWER "${pkg}" pkgp)
  string(TOUPPER "${pkg}" pkgu)
  set(pkgp "${TML_PACKAGES_PATH}/${pkgp}")
  if (IS_DIRECTORY ${pkgp} AND IS_DIRECTORY ${pkgp}/lib/${TML_ARCH}/)
    file(GLOB_RECURSE pkg_libs "${pkgp}/lib/${TML_ARCH}/*.so")

    set(${pkgu}_LIBRARIES ${pkg_libs} PARENT_SCOPE)
    set(${pkgu}_INCLUDE_DIRS "${pkgp}/include/" PARENT_SCOPE)
    #list(APPEND CMAKE_FIND_ROOT_PATH "${CMAKE_CURRENT_LIST_DIR}/../packages/")
  else()
    foreach (arg ${ARGN})
      if (${arg} STREQUAL "REQUIRED")
        set(PKG_REQUIRED TRUE)
      elseif (${arg} STREQUAL "QUIET")
        set(PKG_QUIET TRUE)
      endif()
    endforeach (arg)
    if (PKG_REQUIRED)
      message(FATAL_ERROR "Could NOT find TML package ${pkg}")
    elseif (NOT PKG_QUIET)
      message(STATUS "Could NOT find TML package ${pkg}")
    endif()
  endif()
endfunction()
