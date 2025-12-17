@echo off

set PYTHON_PATH=.\venv_win8\Scripts\python.exe

IF NOT EXIST %PYTHON_PATH% (
    echo "Python doesn't exist on this path"
    exit
) 

%PYTHON_PATH% -m nuitka ^
    --onefile ^
    --windows-icon-from-ico=favicon.ico ^
    --include-data-file=favicon.ico=favicon.ico ^
    --enable-plugin=pyside2 ^
    --enable-plugin=numpy ^
    --include-package=cv2 ^
    --windows-console-mode=disable ^
    --output-dir=build ^
    --remove-output ^
    --lto=yes ^
    main.py

