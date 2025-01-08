rem needs MSVC14 from Visual Studio Build Tools 2022. https://visualstudio.microsoft.com/visual-cpp-build-tools/
rem build\__native.c(18944): error C2065: 'CPyStatic_Fits___ALL': undeclared identifier
rem mypyc main.py

rem pip install nuitka
nuitka main.py --output-dir=dist-nuitka --standalone --onefile --output-filename=tiv.exe --windows-icon-from-ico=eye.ico --macos-app-icon=eye.ico --linux-icon=eye.ico --assume-yes-for-downloads --enable-plugin=tk-inter --remove-output --deployment
