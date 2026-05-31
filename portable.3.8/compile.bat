@echo off

set PYTHON_PATH=.\venv_win8\Scripts\python.exe

IF NOT EXIST %PYTHON_PATH% (
    echo "Error: Python environment not found at path: %PYTHON_PATH%"
    exit /B 1
) 

echo "сборка"

%PYTHON_PATH% -m nuitka ^
    --onefile ^
    --onefile-tempdir-spec="%%CACHE_DIR%%/ProSportsAnalyzer/App/1.8.1" ^
    --onefile-cache-mode=cached ^
    --lto=yes ^
    --python-flag=-O ^
    --python-flag=no_docstrings ^
    --python-flag=no_site ^
    --windows-icon-from-ico=favicon.ico ^
    --include-data-file=favicon.ico=favicon.ico ^
    --include-data-file=ffmpeg.exe=ffmpeg.exe ^
    --enable-plugin=pyside2 ^
    --include-package=cv2 ^
    --windows-console-mode=disable ^
    --msvc=latest ^
    --deployment ^
    --nofollow-import-to=tkinter ^
    --nofollow-import-to=unittest ^
    --nofollow-import-to=matplotlib ^
    --output-dir=build ^
    --remove-output ^
    main.py

if %ERRORLEVEL% NEQ 0 (
    echo "Ошибка при компиляции приложения!"
    exit /B %ERRORLEVEL%
)

echo "cборка успешно завершена"
pause