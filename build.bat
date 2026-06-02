call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
cd llama.cpp-latest
cmake -B build -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DLLAMA_BUILD_BORINGSSL=ON ^
  -DGGML_CUDA=ON ^
  -DGGML_CUDA_FA_ALL_QUANTS=ON ^
  -DGGML_NATIVE=ON ^
  -DCMAKE_CUDA_ARCHITECTURES=native
cmake --build build -j
cd ..
rmdir /s /q llama.cpp-test
mkdir llama.cpp-test
xcopy "llama.cpp-latest\build\bin\*" "llama.cpp-test" /Y
xcopy "cudart-llama-bin-win-cuda-12.4-x64\*" "llama.cpp-test" /Y