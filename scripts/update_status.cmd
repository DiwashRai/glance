@echo off
rem Collects the counts once, with glance's own environment (run_glance.cmd sets it up).
setlocal

for %%I in ("%~dp0..") do set "ROOT=%%~fI"

pushd "%ROOT%"
"%ROOT%\.venv\Scripts\python.exe" update_status.py %*
set "RC=%errorlevel%"
popd

exit /b %RC%
