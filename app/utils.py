import subprocess
import sys
from collections.abc import Sequence


def run_no_window(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            startupinfo=startupinfo,
            stdin=subprocess.DEVNULL,
        )

    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
