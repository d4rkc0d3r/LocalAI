:: git clone https://github.com/ggml-org/llama.cpp.git llama.cpp-latest
cd llama.cpp-latest
git fetch
git pull

:: Apply local patch: add cached token count to the per-request log line
:: (idempotent: skips if already applied, warns if context no longer matches after a pull)
python ..\apply_cached_tokens_patch.py