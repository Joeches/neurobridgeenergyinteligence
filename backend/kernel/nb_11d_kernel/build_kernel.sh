#!/bin/bash
# NeuroBridge 11D Kernel - Production Build Script (UCRT64)

echo "[BUILD] Starting Static Compilation for 11D Kernel..."

# Define Paths
PYTHON_INC="/ucrt64/include/python3.11"
PYTHON_LIB="/ucrt64/lib"
OUTPUT_PATH="venv/Lib/site-packages/nb_11d_kernel.pyd"
SOURCE="src/kernel.cpp"

# Compilation with Static Linking Flags
g++ -shared -O3 -march=native -o $OUTPUT_PATH $SOURCE \
    -static-libgcc -static-libstdc++ \
    -Wl,-Bstatic,--whole-archive -lwinpthread \
    -Wl,--no-whole-archive \
    -I$PYTHON_INC -L$PYTHON_LIB -lpython311

if [ $? -eq 0 ]; then
    echo "✅ Success: $OUTPUT_PATH created."
    # Strip debug symbols to reduce binary size for production
    strip $OUTPUT_PATH
    echo "[INFO] Binary stripped for production deployment."
else
    echo "❌ Error: Compilation failed."
    exit 1
fi