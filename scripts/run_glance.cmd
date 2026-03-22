
@echo off
setlocal

for %%I in ("%~dp0..") do set "ROOT=%%~fI"

if not exist "%ROOT%\config.local.toml" (
  copy /y "%ROOT%\config.toml" "%ROOT%\config.local.toml" >nul
)

if not exist "%ROOT%\data\status.local.json" (
  copy /y "%ROOT%\data\status.json" "%ROOT%\data\status.local.json" >nul
)

start "" "%SystemRoot%\System32\wscript.exe" "%ROOT%\scripts\update_status.vbs"

start "" /D "%ROOT%" pythonw.exe "%ROOT%\glance.py" --config "%ROOT%\config.local.toml"
exit /b 0
