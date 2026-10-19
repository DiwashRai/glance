import subprocess
from collections.abc import Sequence


def run_no_window(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Runs a command without flashing up a console window: glance and the collector have none."""
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
        startupinfo=startupinfo,
        stdin=subprocess.DEVNULL,
    )
