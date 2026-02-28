@echo off
chcp 65001 > nul
cd /d "%~dp0"

if "%1"=="" (
    echo 使用方法:
    echo   set-string.bat "file_path" [translation_file]
    echo   get-string.bat "file_path" 
    echo   list-untranslated.bat [數量]
    echo.
    echo 範例:
    echo   set-string.bat "SATranslation/Misc/Cutscene Text/Knuckles/10 Before Sonic Fight/Japanese.txt" tr.txt
    pause
    exit /b 1
)

if "%1"=="list" (
    set limit=10
    if not "%2"=="" set limit=%2
    python csv_translator.py list-untranslated %limit%
    pause
    exit /b 0
)

if "%1"=="get" (
    if "%2"=="" (
        echo 錯誤: 需要提供文件路徑
        pause
        exit /b 1
    )
    python csv_translator.py get-string "%2"
    pause
    exit /b 0
)

if "%2"=="" (
    set translation_file=tr.txt
) else (
    set translation_file=%2
)

python csv_translator.py set-string "%1" "%translation_file%"
pause