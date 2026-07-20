@echo off
setlocal enabledelayedexpansion

:: Resolve script directory (works regardless of how the script is invoked)
set "SCRIPT_DIR=%~dp0"
set "REPO_DIR=%SCRIPT_DIR%llama.cpp-latest"
set "OUTPUT_FILE=%SCRIPT_DIR%changes.md"

echo Script dir: %SCRIPT_DIR%
echo Repo dir  : %REPO_DIR%
echo Output    : %OUTPUT_FILE%

echo.
echo Fetching upstream changes...

cd /d "%REPO_DIR%" || (echo ERROR: Cannot cd to repo directory & goto :end)

:: Fetch latest from upstream without merging
git fetch origin 2>nul

:: Get current branch name
for /f "delims=" %%i in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%i
echo Branch: %BRANCH%

:: Count new upstream commits
for /f "delims=" %%i in ('git rev-list HEAD..origin/%BRANCH% --count') do set AHEAD=%%i

:: Get hashes for display
for /f "delims=" %%i in ('git rev-parse --short HEAD') do set LOCAL_HASH=%%i
for /f "delims=" %%i in ('git rev-parse --short origin/%BRANCH%') do set REMOTE_HASH=%%i

echo Local HEAD: %LOCAL_HASH%
echo Remote   : %REMOTE_HASH% (origin/%BRANCH%)
echo New commits: %AHEAD%

if "%AHEAD%" equ "0" (
    echo.
    echo No new upstream commits. llama.cpp-latest is up to date.
    echo.
    echo # Upstream llama.cpp Changes > "%OUTPUT_FILE%"
    echo. >> "%OUTPUT_FILE%"
    echo **No new commits.** llama.cpp-latest is up to date. >> "%OUTPUT_FILE%"
    echo. >> "%OUTPUT_FILE%"
    echo Last checked: %date% %time% >> "%OUTPUT_FILE%"
    goto :end
)

echo Found %AHEAD% new commit(s) on upstream.
echo Step: Writing header...

:: Build markdown header
echo # Upstream llama.cpp Changes > "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"
echo **%AHEAD% new commit(s)** since local HEAD. >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"
echo Last checked: %date% %time% >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"
echo --- >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"

echo Step: Running git log...
:: Use git log to get commits in range, formatted as markdown
git log HEAD..origin/%BRANCH% --pretty="### %%h - %%s%%n%%n*%%an* - %%ad%%n%%b%%n%%n---" --date=short >> "%OUTPUT_FILE%"
echo Step: git log done.

echo.
echo Done! Written %AHEAD% commit(s) to changes.md

:end
