@echo off
setlocal enabledelayedexpansion

rem Compare the two latest SPEED-Bench runs (spec_bench_*.json) in bench_results.
rem Usage: tools/server/bench/speed-bench/speed_bench_compare.py
rem   --baseline  older run   --speculative newer run

set "OUTPUT_DIR=%~dp0bench_results"

set "NEWER="
set "OLDER="
set /a COUNT=0
for /f "delims=" %%F in ('dir /b /o-d "%OUTPUT_DIR%\spec_bench_*.json" 2^>nul') do (
  set /a COUNT+=1
  if !COUNT! EQU 1 set "NEWER=%%F"
  if !COUNT! EQU 2 set "OLDER=%%F"
)

if not defined NEWER (
  echo No spec_bench_*.json results found in %OUTPUT_DIR%
  exit /b 1
)
if not defined OLDER (
  echo Only one spec_bench_*.json result found - nothing to compare.
  exit /b 1
)

echo Comparing:
echo   baseline   : %OLDER%
echo   speculative: %NEWER%
echo.

python llama.cpp-latest\tools\server\bench\speed-bench\speed_bench_compare.py ^
  --baseline "%OUTPUT_DIR%\%OLDER%" ^
  --speculative "%OUTPUT_DIR%\%NEWER%"
