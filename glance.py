
import argparse
import ctypes
import json
import os
import tkinter as tk
import tomllib
from dataclasses import dataclass, fields


DEFAULT_CONFIG_PATH = "config.toml"
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
VALID_MONITOR_MODES = {"primary", "all"}
VALID_POSITIONS = {"TL", "TR", "BL", "BR"}
VALID_TICK_STACKS = {"left", "right"}
MONITORINFOF_PRIMARY = 1


@dataclass
class AppConfig:
    path: str | None = None
    poll: int = 5
    pos: str = "TR"
    x_offset: int = 20
    y_offset: int = 20
    alpha: float = 0.7
    tick_stack: str = "left"
    click_through: bool = False
    font: str = "JetBrainsMono NF"
    font_size: int = 12
    monitors: str | list[int] = "primary"


@dataclass
class AppState:
    mtime: float | None = None


@dataclass
class WindowState:
    locked: bool = True
    drag_x: int = 0
    drag_y: int = 0


@dataclass
class MonitorRect:
    number: int
    left: int
    top: int
    right: int
    bottom: int
    is_primary: bool = False


def parse_cli_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("-p", "--path")
    parser.add_argument("-i", "--poll", type=int)
    return parser.parse_args(argv)


def main():
    config = load_app_config(parse_cli_args())
    GlanceApp(config).run()


def load_app_config(cli_args):
    config = AppConfig()
    apply_config_values(config, load_toml_config(cli_args.config))

    if cli_args.path is not None:
        config.path = cli_args.path
    if cli_args.poll is not None:
        config.poll = cli_args.poll

    validate_config(config)
    return config


class GlanceApp:
    def __init__(self, config):
        self.config = config
        self.state = AppState()
        self.root = tk.Tk()
        self.root.withdraw()
        monitors = select_monitor_rects(get_monitor_rects(), config.monitors)
        self.windows = [
            GlanceWindow(self.root, config, monitor) for monitor in monitors
        ]

    def run(self):
        self.refresh_status()
        self.root.mainloop()

    def refresh_status(self):
        try:
            mtime = os.path.getmtime(self.config.path)
            if self.state.mtime != mtime:
                done, items = self.read_status()
                for window in self.windows:
                    window.render(done, items)
                self.state.mtime = mtime
                for window in self.windows:
                    if window.state.locked:
                        window.place()
        except OSError:
            for window in self.windows:
                window.render_error(INVALID_PATH_TEXT)
                if window.state.locked:
                    window.place()
        except Exception as exc:
            for window in self.windows:
                window.render_error(str(exc))
                if window.state.locked:
                    window.place()

        self.root.after(self.config.poll * MS_PER_SECOND, self.refresh_status)

    def read_status(self):
        with open(self.config.path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "f" not in data:
            raise ValueError(STATUS_FIELD_MISSING_TEXT)

        fields = data["f"]
        if not isinstance(fields, list):
            raise ValueError(STATUS_FIELD_TYPE_TEXT)
        if not fields:
            raise ValueError(STATUS_FIELD_EMPTY_TEXT)

        rows = []
        done = 0
        for item in fields:
            if not isinstance(item, list) or len(item) < 4:
                raise ValueError(STATUS_ROW_TYPE_TEXT)
            symbol = str(item[1])
            count = int(item[2])
            severity = max(0, min(3, int(item[3])))
            if count == 0:
                done += 1
            else:
                rows.append((symbol, str(count), COLORS[severity]))

        return done, rows


class GlanceWindow:
    def __init__(self, app_root, config, monitor):
        self.config = config
        self.monitor = monitor
        self.state = WindowState()
        self.font = (config.font, config.font_size)
        self.root = tk.Toplevel(app_root)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", config.alpha)
        self.root.configure(bg=BG)
        self.row = tk.Frame(self.root, bg=BG, padx=8, pady=4)
        self.row.pack()
        self.root.bind("<Button-1>", self.start_drag)
        self.root.bind("<B1-Motion>", self.drag)
        self.root.bind("<Button-3>", lambda _event: app_root.destroy())
        self.place()
        if config.click_through:
            self.set_click_through()

    def render(self, done, items):
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

    def render_error(self, message):
        self.clear()
        self.add_label(message, COLORS[3])

    def place(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = self.monitor.left + self.config.x_offset
        y = self.monitor.top + self.config.y_offset

        if "R" in self.config.pos:
            x = self.monitor.right - width - self.config.x_offset
        if "B" in self.config.pos:
            y = self.monitor.bottom - height - self.config.y_offset

        self.root.geometry(f"+{x}+{y}")

    def set_click_through(self):
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

    def start_drag(self, event):
        self.state.drag_x = event.x_root
        self.state.drag_y = event.y_root
        self.state.locked = False

    def drag(self, event):
        dx = event.x_root - self.state.drag_x
        dy = event.y_root - self.state.drag_y
        self.state.drag_x = event.x_root
        self.state.drag_y = event.y_root
        self.root.geometry(f"+{self.root.winfo_x() + dx}+{self.root.winfo_y() + dy}")

    def clear(self):
        for widget in self.row.winfo_children():
            widget.destroy()

    def render_items(self, items):
        for symbol, value, color in items:
            cell = tk.Frame(self.row, bg=BG)
            cell.pack(side="left", padx=(0, 8))
            self.add_label(f"{symbol}:", LABEL_FG, parent=cell)
            self.add_label(value, color, parent=cell, padx=(4, 0))

    def add_label(self, text, color, parent=None, padx=(0,0)):
        tk.Label(
            parent or self.row,
            text=text,
            fg=color,
            bg=BG,
            font=self.font,
        ).pack(side="left", padx=padx)


# ---- Helpers -----------------------------------------------------------------------------------


def apply_config_values(config, values):
    valid_fields = {field.name for field in fields(AppConfig)}
    for key, value in values.items():
        if key not in valid_fields:
            raise ValueError(f"Unknown config option: {key}")
        setattr(config, key, value)


def load_toml_config(config_path):
    if not os.path.exists(config_path):
        return {}

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    raw_values = config.get("glance", {})
    if not isinstance(raw_values, dict):
        raise ValueError("[glance] must be a TOML table")

    return {key.replace("-", "_"): value for key, value in raw_values.items()}


def validate_config(config):
    if not config.path:
        raise ValueError("Path Missing")
    if config.pos not in VALID_POSITIONS:
        raise ValueError(f"Position must be one of: {sorted(VALID_POSITIONS)}")
    if config.tick_stack not in VALID_TICK_STACKS:
        raise ValueError(
            f"Tick stack must be one of: {sorted(VALID_TICK_STACKS)}"
        )
    if isinstance(config.monitors, str):
        config.monitors = config.monitors.strip().lower()
        if config.monitors not in VALID_MONITOR_MODES:
            config.monitors = parse_monitor_list(config.monitors)
    elif isinstance(config.monitors, list):
        config.monitors = [int(monitor) for monitor in config.monitors]
        if not config.monitors:
            raise ValueError("Monitors list must not be empty")
    else:
        raise ValueError("Monitors must be 'primary', 'all', or a list of ints")

    config.poll = max(int(config.poll), 1)
    config.alpha = min(max(float(config.alpha), 0.2), 1.0)
    config.x_offset = int(config.x_offset)
    config.y_offset = int(config.y_offset)
    config.font_size = max(int(config.font_size), 1)


def parse_monitor_list(value):
    monitors = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not monitors:
        raise ValueError("Monitors list must not be empty")
    return monitors


def get_monitor_rects():
    if os.name != "nt":
        return [get_fallback_monitor_rect()]

    user32 = ctypes.windll.user32
    monitors = []

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

    def callback(hmonitor, _hdc, _rect, _data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
        rect = info.rcMonitor
        monitors.append(
            MonitorRect(
                number=len(monitors) + 1,
                left=rect.left,
                top=rect.top,
                right=rect.right,
                bottom=rect.bottom,
                is_primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
            )
        )
        return 1

    user32.EnumDisplayMonitors(0, 0, callback_type(callback), 0)
    return monitors or [get_fallback_monitor_rect()]


def get_fallback_monitor_rect():
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


def select_monitor_rects(monitors, selection):
    if selection == "all":
        return monitors
    if selection == "primary":
        return [monitor for monitor in monitors if monitor.is_primary] or [monitors[0]]
    selected = [monitor for monitor in monitors if monitor.number in selection]
    if not selected:
        raise ValueError(f"No monitors matched {selection}")
    return selected


if __name__ == "__main__":
    main()
