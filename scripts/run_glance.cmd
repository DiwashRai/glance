@echo off
rem Starts glance (pythonw, so glance itself has no console window), and collects the counts once
rem so the HUD has them straight away. Run it at login; see the README. glance refuses to start a
rem second copy, so running this twice is harmless.
setlocal

for %%I in ("%~dp0..") do set "ROOT=%%~fI"

rem Install or update dependencies first: a git pull may have added one. Fast when up to date.
uv sync --project "%ROOT%" --locked --inexact --quiet || exit /b 1

start "" "%SystemRoot%\System32\wscript.exe" "%ROOT%\scripts\update_status.vbs"
start "" /D "%ROOT%" "%ROOT%\.venv\Scripts\pythonw.exe" "%ROOT%\glance.py"
exit /b 0
