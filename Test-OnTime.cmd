@echo off
setlocal
cd /d "%~dp0"
set "ONTIME_NODE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
if exist "%ONTIME_NODE%" goto bundled
where node >nul 2>nul
if errorlevel 1 goto missing
node --test tests/*.test.mjs
goto done
:bundled
"%ONTIME_NODE%" --test tests/*.test.mjs
goto done
:missing
echo Node.js 22 or later is required. See README.md.
:done
if errorlevel 1 pause
endlocal
