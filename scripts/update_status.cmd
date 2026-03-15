@echo off
setlocal

for %%I in ("%~dp0..") do set "ROOT=%%~fI"

if not exist "%ROOT%\config.local.toml" (
  copy /y "%ROOT%\config.toml" "%ROOT%\config.local.toml" >nul
)

if not exist "%ROOT%\data\status.local.json" (
  copy /y "%ROOT%\data\status.json" "%ROOT%\data\status.local.json" >nul
)

python.exe "%ROOT%\update_status.py" %*
exit /b %errorlevel%
