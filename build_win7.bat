@echo off
title 部署助手 - 打包 Win7 专用版
echo ============================================
echo   部署助手 - 打包 Windows 7 专用版（Python 3.8 / 32 位）
echo ============================================
echo.
set "PY38=win7build\py38\python.exe"

if not exist "%PY38%" (
    echo [提示] 未找到内置的 Python 3.8 构建环境（win7build\py38）。
    echo         请先准备 Python 3.8 32 位环境放到 win7build\py38，
    echo         或直接使用已有的 dist_win7 目录中的成品。
    pause & exit /b 1
)

set "PATH=%CD%\win7build\py38\Library\bin;%PATH%"

echo [0/3] 生成 Win7 兼容的 API 集存根（解决 api-ms-win-core-sysinfo-l1-2-0.dll 弹窗）...
python "%CD%\win7build\make_apiset_stub.py" 2>nul
if not exist "%CD%\win7build\py38\api-ms-win-core-sysinfo-l1-2-0.dll" (
    echo [失败] 存根生成失败，请检查 python 是否可用 & pause & exit /b 1
)

echo [1/3] 打包目录版（onedir，Win7 上建议优先使用）...
"%PY38%" -m PyInstaller --noconfirm --clean --noconsole ^
  --name "部署助手_Win7" --icon "%CD%\icon.ico" ^
  --collect-all customtkinter --add-data "%CD%\win7build\py38\tcl;tcl" ^
  --add-binary "%CD%\win7build\py38\api-ms-win-core-sysinfo-l1-2-0.dll;." ^
  --hidden-import win32com --hidden-import win32com.client ^
  --hidden-import win32print --hidden-import win32api --hidden-import win32con ^
  --distpath dist_win7 --workpath win7build\bld_onedir --specpath win7build\spec ^
  main.py
if errorlevel 1 (echo [失败] 目录版打包出错 & pause & exit /b 1)

echo [2/3] 打包单文件版（onefile）...
"%PY38%" -m PyInstaller --noconfirm --clean --onefile --noconsole ^
  --name "部署助手_Win7" --icon "%CD%\icon.ico" ^
  --collect-all customtkinter --add-data "%CD%\win7build\py38\tcl;tcl" ^
  --add-binary "%CD%\win7build\py38\api-ms-win-core-sysinfo-l1-2-0.dll;." ^
  --hidden-import win32com --hidden-import win32com.client ^
  --hidden-import win32print --hidden-import win32api --hidden-import win32con ^
  --distpath dist_win7 --workpath win7build\bld_onefile --specpath win7build\spec ^
  main.py
if errorlevel 1 (echo [失败] 单文件版打包出错 & pause & exit /b 1)

echo.
echo [3/3] 完成！Win7 版产物（原 dist\部署助手.exe 不受影响）：
echo    dist_win7\部署助手_Win7.exe            单文件版
echo    dist_win7\部署助手_Win7\               目录版（整个文件夹一起分发）
echo    dist_win7\Windows7通用C运行库_ucrt.msi  Win7 缺运行库时安装
echo.
pause
