@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
set "ONTIME_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%ONTIME_PY%" goto bundled
python run_ontime.py %*
exit /b %errorlevel%
:bundled
"%ONTIME_PY%" run_ontime.py %*
exit /b %errorlevel%
