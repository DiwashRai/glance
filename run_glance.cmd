
setlocal
cd /d "%~dp0"

set STATUS="%~dp0\sample_status.json"

start "" pythonw.exe "%~dp0glance.py" -p "%STATUS%"
exit /b 0
