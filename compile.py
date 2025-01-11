"""Shell languages tend to be less readable than Python."""

import subprocess
from time import strftime

timestamp = strftime("%y%j")  # max 5 digits for Nuitka.

# mypyc main.py
# Needs MSVC14 from Visual Studio Build Tools 2022.
# https://visualstudio.microsoft.com/visual-cpp-build-tools/
# build\__native.c(18944): error C2065: 'CPyStatic_Fits___ALL': undeclared identifier

# pip install nuitka
subprocess.run(
    [
        "nuitka",
        "main.py",
        "--output-dir=dist-nuitka",
        "--standalone",
        "--onefile",
        "--output-filename=tiv.exe",
        "--windows-icon-from-ico=eye.ico",
        "--macos-app-icon=eye.ico",
        "--linux-icon=eye.ico",
        "--assume-yes-for-downloads",
        "--enable-plugin=tk-inter",
        "--remove-output",
        "--deployment",
        '--product-name="Tk Image Viewer"',
        f"--product-version=1.0.0.{timestamp}",
        f"--file-version=1.0.0.{timestamp}",
        '--file-description="Image viewer with a Tk GUI."',
        f'--copyright="2024-{strftime("%Y")} Cees Timmerman"',
    ],
    check=False,
    shell=True,
)
