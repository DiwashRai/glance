@echo off
rem Starts glance v2 (pythonw, so glance itself has no console window). Run it at login; see
rem the README. glance refuses to start a second copy, so running this twice is harmless.
setlocal

for %%I in ("%~dp0..") do set "ROOT=%%~fI"

rem Install or update dependencies first: a git pull may have added one. Fast when up to date.
uv sync --project "%ROOT%" --locked --inexact --quiet || exit /b 1

start "" /D "%ROOT%" "%ROOT%\.venv\Scripts\pythonw.exe" "%ROOT%\glance_v2.py"
exit /b 0
