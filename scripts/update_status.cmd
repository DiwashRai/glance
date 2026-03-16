@echo off
setlocal

for %%I in ("%~dp0..") do set "ROOT=%%~fI"

if not exist "%ROOT%\config.local.toml" (
  copy /y "%ROOT%\config.toml" "%ROOT%\config.local.toml" >nul
)

if not exist "%ROOT%\data\status.local.json" (
  copy /y "%ROOT%\data\status.json" "%ROOT%\data\status.local.json" >nul
)

pushd "%ROOT%"
python.exe update_status.py %*
set "RC=%errorlevel%"
popd

exit /b %RC%
