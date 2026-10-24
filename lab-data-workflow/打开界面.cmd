@echo off
setlocal
rem ============================================================================
rem  双击我 = 启动「实验报告生成器」界面（浏览器会自动打开）
rem
rem  · 实验数据放哪儿？默认用 sample\my_sample，找不到就用桌面。
rem    想换目录：把这个 .cmd 拖到你那个目录上再松手；或者双击后在界面里改
rem    「生成到哪个目录」那一栏，再点生成。
rem  · 界面就跑在这个窗口里 —— 关掉窗口（或按 Ctrl+C）就停了。
rem ============================================================================
set "SKILL=%~dp0"
if not exist "%SKILL%ui\server.py" set "SKILL=%~dp0lab-data-workflow\"
if not exist "%SKILL%ui\server.py" (
  echo [!] 找不到 ui\server.py —— 请把本文件放在 lab-data-workflow 目录里再双击
  pause
  exit /b 1
)

set "ROOT=%~1"
if not "%ROOT%"=="" if not exist "%ROOT%" (
  echo [!] 这个目录不存在: %ROOT%
  pause
  exit /b 1
)
if "%ROOT%"=="" if exist "%~dp0sample\my_sample" set "ROOT=%~dp0sample\my_sample"
if "%ROOT%"=="" if exist "%~dp0..\sample\my_sample" set "ROOT=%~dp0..\sample\my_sample"
if "%ROOT%"=="" set "ROOT=%USERPROFILE%\Desktop"

set "PY=py -3"
%PY% -c "import sys" >nul 2>nul || set "PY=python"
%PY% -c "import sys" >nul 2>nul || set "PY=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
%PY% -c "import sys" >nul 2>nul || (
  echo [!] 没找到能用的 Python 3。装一个（勾上 Add to PATH）再双击；
  echo     或者把上面 PY 那行改成你 python.exe 的完整路径。
  pause
  exit /b 1
)

echo.
echo   实验报告界面启动中……
echo   实验目录（会在它下面建 ^<实验^>/实验数据/）: %ROOT%
echo   浏览器会自动打开 http://127.0.0.1:8722/ —— 关掉这个窗口就停。
echo.
%PY% "%SKILL%ui\server.py" --root "%ROOT%" --open
if errorlevel 1 pause
