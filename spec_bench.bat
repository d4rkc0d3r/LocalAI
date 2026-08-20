@echo off
setlocal enabledelayedexpansion

set "OUTPUT_DIR=%~dp0bench_results"
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /format:list') do set "dt=%%I"
set "TIMESTAMP=%dt:~0,8%_%dt:~8,6%"
set "RESULTS_FILE=%OUTPUT_DIR%\spec_bench_%TIMESTAMP%.json"

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

python llama.cpp-latest/tools/server/bench/speed-bench/speed_bench.py ^
  --url localhost:8000 ^
  --bench qualitative ^
  --category all ^
  --osl 512 ^
  --concurrency 1 ^
  --limit 2 ^
  --model Muse-Glimmer-30B-Q4-DFlash ^
  --output "%RESULTS_FILE%"