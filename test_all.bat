@echo off
echo ========================================
echo NEUROBRIDGE 11D - QUICK TEST SUITE
echo ========================================

echo.
echo [1] Testing Health Check...
curl -s http://127.0.0.1:8000/api/v1/health | findstr "healthy"
if %errorlevel%==0 (echo ✅ Health Check PASSED) else (echo ❌ Health Check FAILED)

echo.
echo [2] Testing Kernel Status...
curl -s http://127.0.0.1:8000/api/v1/kernel/status | findstr "native"
if %errorlevel%==0 (echo ✅ Kernel Status PASSED) else (echo ❌ Kernel Status FAILED)

echo.
echo [3] Testing Token Status...
curl -s http://127.0.0.1:8000/api/v1/token/status | findstr "success"
if %errorlevel%==0 (echo ✅ Token Status PASSED) else (echo ❌ Token Status FAILED)

echo.
echo [4] Testing Energy Status...
curl -s http://127.0.0.1:8000/api/v1/energy/status | findstr "ACTIVE"
if %errorlevel%==0 (echo ✅ Energy Status PASSED) else (echo ❌ Energy Status FAILED)

echo.
echo [5] Testing NASA Telemetry...
curl -s http://127.0.0.1:8000/api/v1/nasa-telemetry | findstr "ghi_wm2"
if %errorlevel%==0 (echo ✅ NASA Telemetry PASSED) else (echo ❌ NASA Telemetry FAILED)

echo.
echo [6] Testing GEE Heatmap...
curl -s "http://127.0.0.1:8000/api/v1/gee-heatmap?lat=9.0765&lon=7.3986" | findstr "vegetation_health"
if %errorlevel%==0 (echo ✅ GEE Heatmap PASSED) else (echo ❌ GEE Heatmap FAILED)

echo.
echo ========================================
echo TEST COMPLETE
echo ========================================
pause