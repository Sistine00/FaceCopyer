@echo off
title FaceCopyer Launcher
echo ============================================
echo   FaceCopyer 1.0.0 - One Click Start
echo   GPU: CUDA 12 (onnxruntime-gpu)
echo ============================================
echo.
cd /d "D:\facefusion\source"
if not exist "D:\facefusion\venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please redeploy.
    pause
    exit /b 1
)
set "PATH=D:\facefusion\venv\Lib\site-packages\nvidia\cuda_runtime\bin;D:\facefusion\venv\Lib\site-packages\nvidia\cublas\bin;D:\facefusion\venv\Lib\site-packages\nvidia\cudnn\bin;D:\facefusion\venv\Lib\site-packages\nvidia\cufft\bin;D:\facefusion\venv\Scripts;%PATH%"
set "FACEFUSION_DISABLE_NSFW=1"
"D:\facefusion\venv\Scripts\python.exe" "D:\facefusion\_port_clean.py"
echo.
echo [INFO] Starting IOPaint occlusion-removal service...
"D:\facefusion\iopaint_venv\Scripts\python.exe" "D:\facefusion\_iopaint_start.py"
echo.
echo [INFO] Starting FaceCopyer, browser will open automatically...
echo [INFO] Close this window or press Ctrl+C to stop.
echo.
"D:\facefusion\venv\Scripts\python.exe" facefusion.py run --open-browser
echo.
echo [DONE] Program exited. Press any key to close.
pause >nul
