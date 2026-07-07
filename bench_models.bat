@echo off
setlocal enabledelayedexpansion

:: =========================================================================
:: llama-bench batch runner for all models in models.ini
:: Benchmarks: Qwen3.6-35B-A3B, Qwen3.6-27B-Q4, Gemma4-31B-Q3
:: =========================================================================

set "BENCH_EXE=llama.cpp-test\llama-bench.exe"
set "OUTPUT_DIR=%~dp0bench_results"
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /format:list') do set "dt=%%I"
set "TIMESTAMP=%dt:~0,8%_%dt:~8,6%"
set "RESULTS_FILE=%OUTPUT_DIR%\bench_%TIMESTAMP%.md"

:: Common benchmark params (matching models.ini settings)
set "COMMON_ARGS=-r 5 --prio 1 --delay 1 -o md -p 2048 -n 128 -b 2048 -ub 512 -t 8 -ngl 99 -nkvo 0 --flash-attn 1 -ctk q8_0 -ctv q8_0,q5_1 --mmap 1"

:: bench seems to have trouble with model switching, so I only run the main model now
:: its only really for verifying that there was no speed regression with new llama.cpp versions
set "MODEL_LIST=unsloth/Qwen3.6-27B-MTP-GGUF:IQ4_XS"
:: set "MODEL_LIST=%MODEL_LIST%,unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ4_XS"
:: set "MODEL_LIST=%MODEL_LIST%,unsloth/gemma-4-31B-it-GGUF:Q3_K_M"

:: Create output directory
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

%BENCH_EXE% -hf %MODEL_LIST% %COMMON_ARGS% >> "%RESULTS_FILE%" 2>&1
