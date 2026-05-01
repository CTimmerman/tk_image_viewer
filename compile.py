"""Shell languages tend to be less readable than Python."""

import subprocess
from time import strftime

timestamp = strftime("%y%j")  # max 5 digits for Nuitka.
VERSION = f"1.3.0.{timestamp}"


# ================================ cx_Freeze ====================================
# import sys
# from cx_Freeze import setup, Executable

# base = None

# if sys.platform == "win32":
#     base = "Win32GUI"  # Use this option to create a GUI executable on Windows

# executables = [Executable("main.py", base=base)]

# options = {
#     "build_exe": {
#         "packages": [],  # List of packages to include
#         "include_files": [],  # List of additional files to include
#     },
# }

# setup(
#     name="Tk Image Viewer",
#     version=f"{VERSION}",
#     description="Image viewer with a Tk GUI.",
#     options=options,
#     executables=executables
# )


# ============================ Cython ================================
# subprocess.run(
#     [
#         "python",
#         "-m",
#         "pip",
#         "install",
#         "--upgrade",
#         "cython",
#     ],
#     check=False,
#     shell=True,
# )

# # Create main.c
# subprocess.run(
#     [
#         "python",
#         "-m",
#         "cython",
#         "main.py",
#     ],
#     check=False,
#     shell=True,
# )
# # Create tiv.exe
# PYTHON_DIR = r"C:\Users\C\AppData\Local\Python\pythoncore-3.13-64"
# subprocess.run(
#     [
#         "gcc",
#         "-Os",
#         "-I",
#         fr"{PYTHON_DIR}\include",
#         "-o",
#         "tiv.exe",
#         "main.c",
#         "-lpython313",
#         "-lm",
#         "-L",
#         fr"{PYTHON_DIR}\libs",
#         "-municode",  # Avoid "Undefined reference to WinMain"
#     ],
#     check=False,
#     shell=True,
# )
# r'''
# python -m cython bench_serializers.py -o bench3.exe
# bench3.exe
# This version of D:\code\AI\stable-diffusion\diffuers_demo\bench3.exe is not compatible with the version of Windows you're running. Check your computer's system information and then contact the software publisher.
# '''
# python -m cython bench_serializers.py
# echo %PYTHON_DIR%
# set PYTHON_DIR=C:\Users\C\AppData\Local\Python\pythoncore-3.13-64\
# gcc -Os -I %PYTHON_DIR%\include -o bench_serializers.exe bench_serializers.c -lpython313 -lm -L %PYTHON_DIR%\libs -municode


# ============================ MyPyC =================================
# mypyc main.py
# Needs MSVC14 from Visual Studio Build Tools 2022.
# https://visualstudio.microsoft.com/visual-cpp-build-tools/
# build\__native.c(18944): error C2065: 'CPyStatic_Fits___ALL': undeclared identifier


# ============================ Nuitka ================================
subprocess.run(
    [
        "python",
        "-m",
        "nuitka",
        "main.py",
        "--output-dir=dist-nuitka",
        "--standalone",
        "--onefile",  # Unpacks to temp folder on run, but dist folder is 140 MB smaller.
        "--output-filename=tiv.exe",
        "--windows-icon-from-ico=eye.ico",
        "--macos-app-icon=eye.ico",
        "--linux-icon=eye.ico",
        "--assume-yes-for-downloads",
        "--enable-plugin=tk-inter",
        "--remove-output",
        "--deployment",
        "--product-name=Tk Image Viewer",
        f"--product-version={VERSION}",
        f"--file-version={VERSION}",
        "--file-description=Image viewer with a Tk GUI.",
        f'--copyright=2024-{strftime("%Y")} Cees Timmerman',
    ],
    check=False,
    shell=True,
)
