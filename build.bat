@echo off
title 部署助手 - 一键打包 EXE
echo ============================================
echo   部署助手 - 一键打包为 EXE
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [失败] 未找到 Python，请先安装 Python 3.8+ 并勾选 "Add to PATH"
    pause & exit /b 1
)

echo [1/3] 安装依赖（超时 60 秒，失败自动改用国内镜像）...
python -m pip install --upgrade pip --default-timeout 60 --retries 5 >nul 2>nul
python -m pip install --default-timeout 60 --retries 5 -r requirements.txt pyinstaller
if errorlevel 1 (
    echo [提示] 默认源连接失败，改用清华镜像重试...
    python -m pip install --default-timeout 60 --retries 5 ^
      -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt pyinstaller
    if errorlevel 1 (
        echo [提示] 清华镜像失败，改用阿里云镜像重试...
        python -m pip install --default-timeout 60 --retries 5 ^
          -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt pyinstaller
        if errorlevel 1 (echo [失败] 依赖安装失败，请检查网络 & pause & exit /b 1)
    )
)

if not exist icon.ico python make_icon.py

echo [2/3] PyInstaller 打包中（onefile 单文件版，约 1~3 分钟）...
python -m PyInstaller --noconfirm --clean --onefile --noconsole ^
  --name "部署助手" --icon icon.ico ^
  --collect-all customtkinter ^
  --hidden-import win32com --hidden-import win32com.client ^
  --hidden-import win32print --hidden-import win32api --hidden-import win32con ^
  main.py
if errorlevel 1 (
    echo [失败] 打包出错，请查看上方日志
    pause & exit /b 1
)

echo.
echo [3/3] 打包完成！
echo.
echo   可执行文件：dist\部署助手.exe
echo   复制到任意目录双击即可运行（首次运行若被杀毒软件拦截，请添加信任）
echo.
pause
