@echo off
setlocal enabledelayedexpansion

:: Resolve script directory (works regardless of how the script is invoked)
set "SCRIPT_DIR=%~dp0"
set "SERVER_URL=http://127.0.0.1:8000"
set "MODEL=Qwen3.8-27B-medium"
set "OUTPUT_FILE=%SCRIPT_DIR%changes_summary.md"

:: Files to append to the request, in order
set "F1=%SCRIPT_DIR%changes.md"
set "F2=%SCRIPT_DIR%README.md"
set "F3=%SCRIPT_DIR%LaunchServer.bat"
set "F4=%SCRIPT_DIR%models.ini"

for %%f in ("%F1%" "%F2%" "%F3%" "%F4%") do if not exist "%%f" (
    echo ERROR: missing file %%f
    exit /b 1
)

echo Server : %SERVER_URL%
echo Model  : %MODEL%
echo Output : %OUTPUT_FILE%
echo.

echo Step 1/3: Fetching upstream changes (fetch_changes.bat)...
call "%SCRIPT_DIR%fetch_changes.bat"
echo.

echo Step 2/3: Building request and querying the server...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%summarize_changes.ps1" -ServerUrl "%SERVER_URL%" -Model "%MODEL%" -Output "%OUTPUT_FILE%" -Dir "%SCRIPT_DIR:~0,-1%"






if errorlevel 1 (
    echo ERROR: request failed. Is the server running with the %MODEL% model loaded?
    exit /b 1
)

echo Step 3/3: Done.

endlocal
