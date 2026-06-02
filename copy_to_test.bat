rmdir /s /q llama.cpp-test
mkdir llama.cpp-test
xcopy "llama.cpp-latest\build\bin\*" "llama.cpp-test" /Y
xcopy "cudart-llama-bin-win-cuda-12.4-x64\*" "llama.cpp-test" /Y