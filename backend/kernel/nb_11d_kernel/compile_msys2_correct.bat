@echo off
echo ================================================================================
echo NeuroBridge 11D Kernel - MSYS2 Compilation with Correct Python
echo ================================================================================
echo.

cd /d C:\Users\hp\Desktop\energy-kernel\backend\kernel\nb_11d_kernel

:: Get Python paths from current environment
for /f "delims=" %%i in ('python -c "import sys; print(sys.prefix)"') do set PYTHON_DIR=%%i
for /f "delims=" %%i in ('python -c "import sys; print(sys.version_info[0]); print(sys.version_info[1])"') do set PYTHON_VER=%%i

echo Python Directory: %PYTHON_DIR%
echo Python Version: %PYTHON_VER%

:: Get pybind11 path from venv
for /f "delims=" %%i in ('python -c "import pybind11; print(pybind11.get_include())"') do set PYBIND11_INCLUDE=%%i

echo Pybind11 Include: %PYBIND11_INCLUDE%
echo.

:: Clean old files
echo [1/3] Cleaning...
if exist _kernel_compiled.pyd del _kernel_compiled.pyd
if exist *.o del *.o
if exist *.obj del *.obj

:: Compile with correct Python includes
echo [2/3] Compiling...
g++ -O3 -Wall -std=c++17 -c core.cpp -o core.o -fopenmp -DNDEBUG

if errorlevel 1 goto :error

g++ -O3 -Wall -std=c++17 -c bindings.cpp -o bindings.o ^
    -I"%PYBIND11_INCLUDE%" ^
    -I"." ^
    -I"%PYTHON_DIR%\include" ^
    -fopenmp -DNDEBUG

if errorlevel 1 goto :error

:: Link
echo [3/3] Linking...
g++ -shared -o _kernel_compiled.pyd core.o bindings.o ^
    -fopenmp ^
    -Wl,--export-all-symbols ^
    -L"%PYTHON_DIR%\libs" ^
    -lpython%PYTHON_VER%

if errorlevel 1 goto :error

:: Check if created
if exist _kernel_compiled.pyd (
    echo.
    echo ================================================================================
    echo [SUCCESS] Kernel compiled successfully!
    echo ================================================================================
    
    :: Get file info
    for %%A in (_kernel_compiled.pyd) do echo Size: %%~zA bytes
    
    :: Copy to kernel directory
    copy /y _kernel_compiled.pyd ..\_kernel_compiled.pyd
    copy /y _kernel_compiled.pyd ..\_kernel.pyd
    
    echo.
    echo Testing kernel...
    cd ..
    python -c "import sys; sys.path.insert(0, '.'); import _kernel_compiled; k = _kernel_compiled.EnergyPredictor(); r = k.calculate(100, 0.05); print(f'Test result: {r:.2f}'); print('SUCCESS: Native kernel is working!')"
    
    if errorlevel 1 (
        echo.
        echo Test failed. Checking module contents...
        python -c "import sys; sys.path.insert(0, '.'); import _kernel_compiled; print(dir(_kernel_compiled))"
    ) else (
        echo.
        echo ================================================================================
        echo [READY] Native kernel ready! Restart FastAPI to use it.
        echo ================================================================================
    )
    
    cd nb_11d_kernel
    goto :end
)

:error
echo.
echo ================================================================================
echo [ERROR] Compilation failed!
echo ================================================================================
echo.
echo Troubleshooting:
echo 1. Make sure you're in the venv: C:\Users\hp\Desktop\energy-kernel\venv\Scripts\activate
echo 2. Check Python development files: python -m ensurepip
echo 3. Try compiling without OpenMP: Remove -fopenmp flags
echo.

:end
pause