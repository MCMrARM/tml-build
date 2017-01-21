#!/usr/bin/python3

import sys
import os.path
import argparse
from inspect import getsourcefile
import subprocess
import yaml
import re
import numbers
import zipfile
import shutil

class color:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    CYAN = '\033[36m'
    LIGHT_YELLOW = '\033[93m'

    STATUS = BOLD + LIGHT_YELLOW
    INFO = CYAN
    WARNING = LIGHT_YELLOW
    ERROR = BOLD + RED

enable_color_printing = False
def color_print(c, text):
    if enable_color_printing:
        print(c + text + color.RESET)
    else:
        print(text)

def fatal_error(msg):
    color_print(color.ERROR, msg)
    sys.exit(1)

# parse args
parser = argparse.ArgumentParser()
parser.add_argument("-p", "--path", default="", help="Use the specific source path")
parser.add_argument("-o", "--out", default="", help="Use the specific path for the resulting package")
parser.add_argument("-b", "--build-dir", help="Use the specific temporary build dir path")
parser.add_argument("-ndk", "--ndk-path", help="Specify the Android NDK path")
parser.add_argument("-cmake", "--cmake-path", default="cmake", help="Specify the CMake path")
parser.add_argument("-c", "--color", action="store_true", help="Force enable color output")
args = parser.parse_args()

source_dir = os.path.abspath(args.path)
output_pkg_path = os.path.abspath(args.out)
build_dir = os.path.abspath(args.build_dir) if args.build_dir is not None else os.path.join(source_dir, "build")
cmake_exec = args.cmake_path
if args.color:
    enable_color_printing = True

# validate paths
source_cmake_lists = os.path.join(source_dir, "CMakeLists.txt")
if not os.path.isfile(source_cmake_lists):
    fatal_error("CMakeLists.txt not found in the source directory")
if not os.path.isdir(build_dir):
    os.makedirs(build_dir)

# parse package.yaml
package_yaml_path = os.path.join(source_dir, "package.yaml")
if not os.path.isfile(package_yaml_path):
    fatal_error("package.yaml not found in the source directory")
package_yaml_file = open(package_yaml_path)
package_yaml = yaml.safe_load(package_yaml_file)
package_yaml_file.close()

# delete unknown properties
def verify_properties(d, recognized_properties, string_properties):
    unknown_properties = []
    for prop in d:
        if prop not in recognized_properties:
            unknown_properties.append(prop)
    for prop in unknown_properties:
        color_print(color.WARNING, "Property \"" + prop + "\" is not recognized in package.yaml")
        del d[prop]
    for prop in string_properties:
        if prop in d and not isinstance(d[prop], str):
            if isinstance(d[prop], numbers.Number):
                d[prop] = str(d[prop])
                continue
            color_print(color.WARNING, "Property \"" + prop + "\" must be a string in package.yaml")
            del d[prop]
package_yaml_string_properties = ["id", "name", "author", "version"]
package_yaml_recognized_properties = package_yaml_string_properties + ["code", "dependencies"]
verify_properties(package_yaml, package_yaml_recognized_properties, package_yaml_string_properties)

# validate package.yaml
if "id" not in package_yaml:
    fatal_error("No package id specified in package.yaml")
version_regexp = re.compile("^\d+(\.\d+(\.\d+)?)?$")
if "version" not in package_yaml or not version_regexp.match(package_yaml["version"]):
    fatal_error("Invalid package version in package.yaml")
package_yaml_native_libs = []
code_string_properties = ["loader", "type", "path", "name"]
if "code" in package_yaml:
    if not isinstance(package_yaml["code"], list):
        fatal_error("Invalid code property in package.yaml (not a list)")
    for code in package_yaml["code"]:
        verify_properties(code, code_string_properties, code_string_properties)
        loader = False
        path = False
        if "type" in code:
            loader = code["type"]
        elif "loader" in code:
            loader = code["loader"]
        if "name" in code:
            path = code["name"]
        elif "path" in code:
            path = code["path"]
        if not loader or not path:
            fatal_error("Invalid code entry in package.yaml (no loader name or file path)")

        if loader == "native":
            package_yaml_native_libs.append(path)

# find tml toolchain file
tml_tool_dir = os.path.dirname(os.path.abspath(getsourcefile(lambda:0)))
tml_dir = os.path.dirname(tml_tool_dir)
tml_cmake_dir = os.path.join(tml_dir, "cmake")
tml_cmake_toolchain = os.path.join(tml_cmake_dir, "tml.toolchain.cmake")
if not os.path.isfile(tml_cmake_toolchain):
    fatal_error("TML CMake toolchain not found")

# check if cmake is installed
try:
    subprocess.check_output([cmake_exec, "--version"])
except OSError:
    fatal_error("CMake not found")

# run cmake
def run_cmake(my_build_dir, my_source_dir, cmake_params):
    if not os.path.isdir(my_build_dir):
        os.makedirs(my_build_dir)
    if subprocess.Popen([cmake_exec] + cmake_params + [my_source_dir], cwd=my_build_dir).wait() != 0:
        fatal_error("Failed to run CMake to generate build files")
    if subprocess.Popen([cmake_exec, "--build", "."], cwd=my_build_dir).wait() != 0:
        fatal_error("Failed to compile")
    cmakefiles_path = os.path.join(my_build_dir, "CMakeFiles")
    with open(os.path.join(cmakefiles_path, "TargetDirectories.txt")) as f:
        built_target_dirs = [l.strip().rpartition(os.path.sep)[2] for l in f.readlines()]
    all_target_dirs = [d for d in os.listdir(cmakefiles_path)
                       if os.path.isdir(os.path.join(cmakefiles_path, d)) and d.endswith(".dir")]
    for dir in all_target_dirs:
        if dir not in built_target_dirs:
            color_print(color.INFO, "Deleting old build target: " + dir[:-4] if dir.endswith(".dir") else dir)
            print("Running clean script")
            target_dir = os.path.join(cmakefiles_path, dir)
            clean_script_path = os.path.join(target_dir, "cmake_clean.cmake")
            if subprocess.Popen([cmake_exec, "-P", clean_script_path], cwd=my_build_dir).wait() != 0:
                color_print(color.WARNING, "Failed to run clean script")
            print("Deleting directory " + target_dir)
            shutil.rmtree(target_dir)

    build_files = os.listdir(my_build_dir)
    return [i for i in build_files if i.endswith('.so')]

global_cmake_params = ["-DCMAKE_TOOLCHAIN_FILE=" + tml_cmake_toolchain, "-DCMAKE_BUILD_TYPE=Release"]
if args.ndk_path is not None:
    global_cmake_params.append("-DCMAKE_ANDROID_NDK=" + os.path.abspath(args.ndk_path))
color_print(color.STATUS, "- Compiling for armeabi-v7a")
arm_build_dir = os.path.join(build_dir, "arm")
arm_libs = run_cmake(arm_build_dir, source_dir, global_cmake_params + ["-DCMAKE_ANDROID_ARCH_ABI=armeabi-v7a"])
print("Built libraries:", arm_libs)
color_print(color.STATUS, "- Compiling for x86")
x86_build_dir = os.path.join(build_dir, "x86")
x86_libs = run_cmake(x86_build_dir, source_dir, global_cmake_params + ["-DCMAKE_ANDROID_ARCH_ABI=x86"])
print("Built libraries:", x86_libs)

# add code section if not here
if "code" not in package_yaml:
    code = []
    for lib in (x86_libs if len(arm_libs) == 0 else arm_libs):
        if lib not in arm_libs:
            color_print(color.WARNING, "Library \"" + lib + "\" is not compiled for the ARM architecture")
        if lib not in x86_libs:
            color_print(color.WARNING, "Library \"" + lib + "\" is not compiled for the X86 architecture")
        shortname = lib
        if shortname.startswith("lib") and shortname.endswith(".so"):
            shortname = shortname[3:][:-3]
        code.append({
            "name": shortname,
            "type": "native"
        })
    package_yaml["code"] = code
# TODO: check if package_yaml_native_libs exist

# package
def pack_dir(zip_file, zip_path, dir_path):
    if not os.path.isdir(dir_path):
        return
    if zip_path.endswith("/"):
        zip_path = zip_path[:-1]
    for f in os.listdir(dir_path):
        if os.path.isdir(zip_path + "/" + f):
            pack_dir(zip_file, zip_path + "/" + f, os.path.join(dir_path, f))
        else:
            zip_file.write(os.path.join(dir_path, f), zip_path + "/" + f)
color_print(color.STATUS, "- Packaging")
if os.path.isdir(output_pkg_path):
    output_pkg_path = os.path.join(output_pkg_path, package_yaml["id"] + ".tbp")
output_pkg = zipfile.ZipFile(output_pkg_path, 'w', zipfile.ZIP_DEFLATED)
output_pkg.writestr("package.yaml", yaml.dump(package_yaml))
for lib in arm_libs:
    output_pkg.write(os.path.join(arm_build_dir, lib), "native/armeabi-v7a/" + lib)
for lib in x86_libs:
    output_pkg.write(os.path.join(x86_build_dir, lib), "native/x86/" + lib)
pack_dir(output_pkg, "native/", os.path.join(source_dir, "native"))
pack_dir(output_pkg, "assets/", os.path.join(source_dir, "assets"))
pack_dir(output_pkg, "resource_pack/", os.path.join(source_dir, "resource_pack"))
output_pkg.close()
color_print(color.BOLD + color.GREEN, "- Success!")
