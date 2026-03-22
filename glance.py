import argparse
import ctypes
import json
import os
import sys
import tkinter as tk
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from app.types import MonitorMode, MonitorSelection, RenderMethod, StatusFile, StatusRow

DEFAULT_CONFIG_PATH = "config.local.toml"
ALL_CLEAR_TEXT = "✓ clear"
INVALID_PATH_TEXT = "Invalid Path"
STATUS_FIELD_MISSING_TEXT = "Status Field Missing"
STATUS_FIELD_EMPTY_TEXT = "Status Field Is Empty"
STATUS_FIELD_TYPE_TEXT = "Status Field Must Be A List"
STATUS_ROW_TYPE_TEXT = "Status Row Must Have 4 Fields"
LABEL_FG = "#e5e5e5"
BG = "#111111"
COLORS = {0: "#58d68d", 1: "#f4d03f", 2: "#f39c12", 3: "#e74c3c"}
GWL_EXSTYLE = -20
MS_PER_SECOND = 1000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
VALID_MONITOR_MODES: frozenset[MonitorMode] = frozenset({"primary", "all"})
VALID_POSITIONS = {"TL", "TR", "BL", "BR"}
VALID_TICK_STACKS = {"left", "right"}
MONITORINFOF_PRIMARY = 1


@dataclass
class MonitorRect:
    number: int
    left: int
    top: int
    right: int
    bottom: int
    is_primary: bool = False


@dataclass
class AppConfig:
    path: Path = Path("data/status.local.json")
    poll: int = 5
    pos: str = "TR"
    x_offset: int = 20
    y_offset: int = 20
    alpha: float = 0.7
    tick_stack: str = "left"
    click_through: bool = False
    font: str = "JetBrainsMono NF"
    font_size: int = 12
    monitors: MonitorSelection = "primary"


@dataclass(slots=True)
class CliArgs:
    config: Path
    path: Path | None = None
    poll: int | None = None


def parse_cli_args(argv: Sequence[str] | None = None) -> CliArgs:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, type=Path)
    parser.add_argument("-p", "--path", type=Path)
    parser.add_argument("-i", "--poll", type=int)
    ns = parser.parse_args(argv)
    return CliArgs(config=ns.config, path=ns.path, poll=ns.poll)


def main():
    try:
        config = load_app_config(parse_cli_args())
        GlanceApp(config).run()
    except Exception as exc:
        print(exc)
        raise SystemExit(1)


class GlanceApp:
    def __init__(self, config: AppConfig) -> None:
        self.config: AppConfig = config
        self.mtime = None
        self.root = tk.Tk()
        self.root.withdraw()
        monitors = select_monitor_rects(get_monitor_rects(), config.monitors)
        self.windows = [GlanceWindow(self.root, config, monitor) for monitor in monitors]

    def run(self) -> None:
        self.refresh_status()
        self.root.mainloop()

    def refresh_status(self) -> None:
        try:
            mtime = self.config.path.stat().st_mtime
            if self.mtime != mtime:
                done, items = self.read_status()
                self.update_windows(GlanceWindow.render, done, items)
                self.mtime = mtime
        except OSError:
            self.update_windows(GlanceWindow.render_error, INVALID_PATH_TEXT)
        except Exception as exc:
            self.update_windows(GlanceWindow.render_error, str(exc))

        for window in self.windows:
            self.root.update_idletasks()  # commit geometry before bringing to top
            window.root.attributes("-topmost", True)  # pyright: ignore [reportUnknownMemberType]
            window.root.lift()  # pyright: ignore [reportUnknownMemberType]

        self.root.after(self.config.poll * MS_PER_SECOND, self.refresh_status)

    def update_windows(self, render_method: RenderMethod, *args: object) -> None:
        for window in self.windows:
            render_method(window, *args)
            if window.locked:
                window.place()

    def read_status(self) -> tuple[int, list[StatusRow]]:
        with self.config.path.open(encoding="utf-8") as f:
            data = cast(StatusFile, json.load(f))

        if "f" not in data:
            raise ValueError(STATUS_FIELD_MISSING_TEXT)

        rows: list[StatusRow] = []
        done = 0
        for _, symbol, count, severity in data["f"]:
            severity = max(0, min(3, severity))
            if count == 0:
                done += 1
            else:
                rows.append((symbol, str(count), COLORS[severity]))

        return done, rows


class GlanceWindow:
    def __init__(self, app_root: tk.Tk, config: AppConfig, monitor: MonitorRect) -> None:
        self.config = config
        self.monitor = monitor
        self.font: tuple[str, int] = (config.font, config.font_size)
        self.locked = True
        self.drag_x = 0
        self.drag_y = 0
        self.root: tk.Toplevel = tk.Toplevel(app_root)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)  # pyright: ignore [reportUnknownMemberType]
        self.root.attributes("-alpha", config.alpha)  # pyright: ignore [reportUnknownMemberType]
        self.root.configure(bg=BG)
        self.row = tk.Frame(self.root, bg=BG, padx=8, pady=4)
        self.row.pack()
        self.root.bind("<Button-1>", self.start_drag)
        self.root.bind("<B1-Motion>", self.drag)
        self.root.bind("<Button-3>", lambda _event: app_root.destroy())
        self.place()
        if config.click_through:
            self.set_click_through()

    def render(self, done: int, items: Sequence[StatusRow]) -> None:
        self.clear()
        if done > 0 and not items:
            self.add_label(ALL_CLEAR_TEXT, COLORS[0])
            return

        ticks = "✓" * done
        if self.config.tick_stack == "left" and ticks:
            self.add_label(ticks, COLORS[0], padx=(0, 10))

        self.render_items(items)

        if self.config.tick_stack == "right" and ticks:
            self.add_label(ticks, COLORS[0], padx=(0, 10))

    def render_error(self, message: str) -> None:
        self.clear()
        self.add_label(message, COLORS[3])

    def place(self) -> None:
        self.root.update_idletasks()  # flush tasks to ensure accurate measurements
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = self.monitor.left + self.config.x_offset
        y = self.monitor.top + self.config.y_offset

        if "R" in self.config.pos:
            x = self.monitor.right - width - self.config.x_offset
        if "B" in self.config.pos:
            y = self.monitor.bottom - height - self.config.y_offset

        self.root.geometry(f"+{x}+{y}")

    def set_click_through(self) -> None:
        if os.name != "nt":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT,
            )
        except Exception:
            pass

    def start_drag(self, event: tk.Event) -> None:
        self.drag_x = event.x_root
        self.drag_y = event.y_root
        self.locked = False

    def drag(self, event: tk.Event) -> None:
        dx = event.x_root - self.drag_x
        dy = event.y_root - self.drag_y
        self.drag_x = event.x_root
        self.drag_y = event.y_root
        self.root.geometry(f"+{self.root.winfo_x() + dx}+{self.root.winfo_y() + dy}")

    def clear(self) -> None:
        for widget in self.row.winfo_children():
            widget.destroy()

    def render_items(self, items: Sequence[StatusRow]) -> None:
        for symbol, value, color in items:
            cell = tk.Frame(self.row, bg=BG)
            cell.pack(side="left", padx=(0, 8))
            self.add_label(symbol, LABEL_FG, parent=cell)
            self.add_label(value, color, parent=cell, padx=(4, 0))

    def add_label(
        self, text: str, color: str, parent: tk.Misc | None = None, padx: tuple[int, int] = (0, 0)
    ) -> None:
        tk.Label(
            parent or self.row,
            text=text,
            fg=color,
            bg=BG,
            font=self.font,
        ).pack(side="left", padx=padx)


def load_toml_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}

    with config_path.open("rb") as f:
        config = tomllib.load(f)

    raw_values = config.get("glance", {})
    if not isinstance(raw_values, dict):
        raise ValueError("[glance] must be a TOML table")
    table = cast(dict[str, Any], raw_values)
    return {key.replace("-", "_"): value for key, value in table.items()}


TOML_COERCER = {
    "path": Path,
}


def load_app_config(cli_args: CliArgs) -> AppConfig:
    config = AppConfig()
    valid_fields = set(AppConfig.__dataclass_fields__)
    for key, value in load_toml_config(cli_args.config).items():
        if key not in valid_fields:
            raise ValueError(f"Unknown config option: {key}")

        coercer = TOML_COERCER.get(key)
        if coercer is not None:
            value = coercer(value)

        setattr(config, key, value)

    if cli_args.path is not None:
        config.path = cli_args.path
    if cli_args.poll is not None:
        config.poll = cli_args.poll

    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    if not config.path.exists():
        raise ValueError(f"Status file does not exist: {config.path}")

    if not config.path.is_file():
        raise ValueError(f"Status path is not a file: {config.path}")

    if config.pos not in VALID_POSITIONS:
        raise ValueError(f"Position must be one of: {sorted(VALID_POSITIONS)}")

    if config.tick_stack not in VALID_TICK_STACKS:
        raise ValueError(f"Tick stack must be one of: {sorted(VALID_TICK_STACKS)}")

    if isinstance(config.monitors, str):
        monitor_mode = config.monitors.strip().lower()
        if monitor_mode not in VALID_MONITOR_MODES:
            raise ValueError("Monitors must be 'primary', 'all', or a list of ints")
        config.monitors = monitor_mode
    else:
        config.monitors = [int(monitor) for monitor in config.monitors]
        if not config.monitors:
            raise ValueError("Monitors list must not be empty")

    config.poll = max(int(config.poll), 1)
    config.alpha = min(max(float(config.alpha), 0.2), 1.0)
    config.x_offset = int(config.x_offset)
    config.y_offset = int(config.y_offset)
    config.font_size = max(int(config.font_size), 1)


def get_monitor_rects() -> list[MonitorRect]:
    if os.name != "nt":
        return [get_fallback_monitor_rect()]

    user32 = ctypes.windll.user32
    monitors: list[MonitorRect] = []

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", ctypes.c_ulong),
        ]

    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.POINTER(RECT),
        ctypes.c_double,
    )

    def callback(hmonitor: int, _hdc: int, _rect: object, _data: float) -> int:
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
        rect = info.rcMonitor
        monitors.append(
            MonitorRect(
                number=0,
                left=rect.left,
                top=rect.top,
                right=rect.right,
                bottom=rect.bottom,
                is_primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
            )
        )
        return 1

    user32.EnumDisplayMonitors(0, 0, callback_type(callback), 0)
    if not monitors:
        return [get_fallback_monitor_rect()]

    monitors.sort(key=lambda monitor: (monitor.left, monitor.top))
    return [
        MonitorRect(
            number=index,
            left=monitor.left,
            top=monitor.top,
            right=monitor.right,
            bottom=monitor.bottom,
            is_primary=monitor.is_primary,
        )
        for index, monitor in enumerate(monitors, start=1)
    ]


def get_fallback_monitor_rect() -> MonitorRect:
    root = tk.Tk()
    root.withdraw()
    monitor = MonitorRect(
        number=1,
        left=0,
        top=0,
        right=root.winfo_screenwidth(),
        bottom=root.winfo_screenheight(),
        is_primary=True,
    )
    root.destroy()
    return monitor


def select_monitor_rects(
    monitors: list[MonitorRect], selection: MonitorSelection
) -> list[MonitorRect]:
    if selection == "all":
        return monitors
    if selection == "primary":
        return [monitor for monitor in monitors if monitor.is_primary] or [monitors[0]]
    selected = [monitor for monitor in monitors if monitor.number in selection]
    selected_numbers = {monitor.number for monitor in selected}
    missing_numbers = [number for number in selection if number not in selected_numbers]
    if missing_numbers:
        raise ValueError(f"No monitors matched {missing_numbers}")
    return selected


if __name__ == "__main__":
    main()
