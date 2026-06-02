easy install with vulkan backend on windows with
```
winget install llama.cpp
```

models get automatically dl'd from hugging face when used with llama-cli or llama-server. if you want to load them first just run these each to start a default interactive session with the models:
```
llama-cli -hf unsloth/Qwen3.6-27B-GGUF:Q4_K_S
llama-cli -hf unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q3_K_M
llama-cli -hf unsloth/gemma-4-31B-it-GGUF:Q3_K_M
```

My hardware is a 4090 with 24GB of VRAM. This is my main gpu so it needs to run windows, unity & maybe a browser as well as the models. This means I have more like 20GB for the models to work with.

kv cache quantization reddit thread: https://www.reddit.com/r/LocalLLaMA/comments/1mhlj69/whats_the_verdict_on_using_quantized_kv_cache/n71q12e/  
even more kv cache tests: https://www.reddit.com/r/LocalLLaMA/comments/1tp9d1w/kv_cache_quant_benchmarks_q5_q6_are_underrated/  
said k needs 8_0 and v is fine with 5_1. in my own test v5_1 was slower token generation speed so I just go with 8_0 for v too.
turns out you need to rebuild llama.cpp with `-DGGML_CUDA_FA_ALL_QUANTS=ON` for it to work at full speed.

slightly lower context window on dense since that eats way more vram with kv cache.
I personally use the qwen moe 35B since its more than twice the token generation speed. ~110 tok/s vs ~43 tok/s with simple hi message.

3bit weights + 8bit kv cache leave quite a bit of slack in vram for desktop & browsers n stuff

## Model Quant Impact Resources
qwen3.6 seems pretty resistant to even 3bit quants: https://kaitchup.substack.com/p/summary-of-qwen36-gguf-evals-updating

https://quanteval.ai/leaderboards.html

## models.ini file for coding
```ini
[*]
flash-attn = on ;needs to be on for kv quant to work
cache-type-k = q8_0
cache-type-v = q8_0
jinja = true
no-mmproj = true ;vision support eats around 1gb of vram so disable it for more context length instead
temp = 0.6 ;qwen3.6 sampling params for coding
top-p = 0.95
top-k = 20
min-p = 0.00
n-gpu-layers = all

[Qwen3.6-35B-A3B]
ctx-size = 200000
hf = unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q3_K_M

[Qwen3.6-27B-Q4]
ctx-size = 140000
hf = unsloth/Qwen3.6-27B-GGUF:Q4_K_S

[Gemma4-31B-Q3]
ctx-size = 100000
hf = unsloth/gemma-4-31B-it-GGUF:Q3_K_M
temp = 1.0
top-p = 0.95
top-k = 64
min-p = 0.05
```

run server with:  
`llama-server --port 8000 --models-preset ".\models.ini" --timeout 600 --models-max 1 --sleep-idle-seconds 300`

no-mmproj for no vision support saving some vram

can use normal chat interface in browser by going to:
`127.0.0.1:8000`

or use in VSCode with extension "Copilot for llama-server LLMs"  
add to settings.json:
```json
"llamaCopilot.endpoints": {
	"local": {
		"url": "http://localhost:8000"
	}
}
```

then in chat model picker click gear wheel "Manage Language Models" and now Llama Server should show up with both qwen and the gemma model

it works well in agent mode then

rant:  
man do I love to just install a random 500 dl extension...  
but chat still only supports ollama api instead of openai or rather it supports openai api now too but you cant add a model with that yet in the ui????  
and llama-server only does openai api and not ollama api  
I think there is a way now to add custom endpoints but I haven't figured out yet how to do it, so extension it is for now.

# MTP (Multi-Token Prediction) adventures

First MTP tests with version b9209 CUDA 12.4
works fine except for crash when dense model gets woken up from sleep again. updated to b9253 and it doesn't crash anymore on wake up.

MTP does eat some vram (so less context budget) but especially for the 27B model the speedup is very significant. 35B moe has less speedup but also a bit more vram overhead so its just a bit better for basically no tradeoff.

# Building with CUDA 12.4
needs prerequisites:
- Git
  - verify with `git --version`
- CUDA 12.4 toolkit
  - verify with `nvcc --version`
- Visual Studio 2022 Build Tools with Desktop development with C++ workload
  - verify with `cl` in `x64 Native Tools Command Prompt for VS 2022`
  - you might need to adjust the path to `vcvars64.bat` in `build.bat`
- [CMake](https://cmake.org/download/)
  - verify with `cmake --version`
- ninja build system
  - `winget install Ninja-build.Ninja`
  - verify with `ninja --version`
- cudart-llama-bin-win-cuda-12.4-x64.dll
  - download from any llama.cpp release like: https://github.com/ggml-org/llama.cpp/releases/download/b9479/cudart-llama-bin-win-cuda-12.4-x64.zip

then just run `pull_from_github.bat` => `build.bat`  
afterwards `bench_models.bat` to to check for any speed regressions before copying the files to the main `llama.cpp-CUDA` folder for regular use.

# Token Prefill and Decode Speeds

As a test I asked the models to "review this script" with CreateAV3ToggleMenu.cs attached. All data points are a single run each.  
Input token count is 8.8k for Qwen3.6 and 10.6k for Gemma4.  
Output token count is 5.5k to 7k for Qwen3.6 and 2k for Gemma4.  

| Model | Backend | Version | Prefill Speed | Decode Speed |
| :--- | :--- | :---| ---: | ---: |
| **Qwen3.6-27B-Q4** | Vulkan | | 1,186 t/s | 35.9 t/s |
| | CUDA | b9209 | 1,982 t/s | 37.1 t/s |
| | CUDA | b9253 | 2,146 t/s | 37.0 t/s |
| **Qwen3.6-27B-Q3-MTP** | CUDA | b9209 | 1,774 t/s | 59.7 t/s |
| | CUDA | b9253 | 1,778 t/s | 59.5 t/s |
| **Qwen3.6-35B-A3B-Q3** | Vulkan | | 3,189 t/s | 102.0 t/s |
| | CUDA | b9209 | 3,946 t/s | 113.0 t/s |
| | CUDA | b9253 | 4,680 t/s | 113.6 t/s |
| **Qwen3.6-35B-A3B-Q3-MTP** | CUDA | b9209 | 3,710 t/s | 135.0 t/s |
| | CUDA | b9253 | 3,869 t/s | 131.7 t/s |
| **Gemma4-31B-Q3** | Vulkan | | 877 t/s | 27.9 t/s |
| | CUDA | b9209 | 1,409 t/s | 33.8 t/s |
| | CUDA | b9253 | 1,450 t/s | 30.5 t/s |
| **Gemma4-26B-A4B-Q4** | CUDA | b9209 | 5,500 t/s | 90.0 t/s |
| | CUDA | b9253 | 5,329 t/s | 90.1 t/s |

### CUDA Performance Delta over Vulkan

| Model | Prefill | Decode |
| :--- | :---: | :---: |
| **Qwen3.6-27B-Q4** | +67.1% | +3.3% |
| **Qwen3.6-35B-A3B-Q3** | +23.7% | +10.8% |
| **Gemma4-31B-Q3** | +60.7% | +21.2% |

### MTP Performance Delta with Version b9209 CUDA

| Model | Prefill | Decode |
| :--- | :---: | :---: |
| **Qwen3.6-27B-Q3-MTP** | -10.5% | +61.2% |
| **Qwen3.6-35B-A3B-Q3-MTP** | -5.9% | +19.5% |