@echo off

set PYTHON_PATH=.\venv_win8\Scripts\python.exe

IF NOT EXIST %PYTHON_PATH% (
    echo "Python doesn't exist on this path"
    exit
) 

%PYTHON_PATH% -m nuitka ^
    --onefile ^
    --lto=yes ^
    --python-flag=-O ^
    --python-flag=no_docstrings ^
    --windows-icon-from-ico=favicon.ico ^
    --include-data-file=favicon.ico=favicon.ico ^
    --enable-plugin=pyside2 ^
    --include-package=cv2 ^
    --windows-console-mode=disable ^
    --output-dir=build ^
    --remove-output ^
    main.py

