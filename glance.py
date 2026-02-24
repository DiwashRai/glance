import argparse
import ctypes
import json
import os
import tkinter as tk

COLORS = {0: "#58d68d", 1: "#f4d03f", 2: "#f39c12", 3: "#e74c3c"}
BG = "#111111"
FONT = "JetBrainsMono NF"
FONT_SIZE = 12
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("-p", "--path", required=True)
    p.add_argument("-i", "--poll", type=int, default=5)
    p.add_argument("-o", "--pos", default="TR", choices=["TL", "TR", "BL", "BR"])
    p.add_argument("-x", "--x-offset", type=int, default=20)
    p.add_argument("-y", "--y-offset", type=int, default=20)
    p.add_argument("-a", "--alpha", type=float, default=0.7)
    p.add_argument("-s", "--tick-stack", default="left", choices=["left", "right"])
    p.add_argument("-c", "--click-through", action="store_true")
    a = p.parse_args()
    return (
        a.path,
        max(a.poll, 1),
        a.pos,
        (a.x_offset, a.y_offset),
        min(max(a.alpha, 0.2), 1.0),
        a.tick_stack,
        a.click_through,
    )


def read_status(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    fields = data.get("f")
    if not isinstance(fields, list) or not fields:
        return "none"
    rows, done = [], 0
    for item in fields:
        if not isinstance(item, list) or len(item) < 4:
            return None
        symbol = str(item[1])
        count = int(item[2])
        sev = max(0, min(3, int(item[3])))
        if count == 0:
            done += 1
        else:
            rows.append((symbol, str(count), COLORS[sev]))
    return done, rows


def place_window(win, pos, offset):
    win.update_idletasks()
    w, h = win.winfo_width(), win.winfo_height()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    ox, oy = offset
    x = ox if "L" in pos else sw - w - ox
    y = oy if "T" in pos else sh - h - oy
    win.geometry(f"+{x}+{y}")


def set_click_through(win):
    if os.name != "nt":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT
        )
    except Exception:
        pass


def main():
    path, poll, pos, offset, alpha, tick_stack, click_through = parse_args()
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", alpha)
    root.configure(bg=BG)
    row = tk.Frame(root, bg=BG, padx=8, pady=4) # padding around row
    row.pack()
    state = {"mtime": None, "locked": True, "x": 0, "y": 0}

    def render_error(message):
        for w in row.winfo_children():
            w.destroy()
        tk.Label(
            row, text=message, fg=COLORS[3], bg=BG, font=(FONT, FONT_SIZE)
        ).pack(side="left")

    def render_items(items):
        for symbol, value, color in items:
            cell = tk.Frame(row, bg=BG)
            cell.pack(side="left", padx=(0, 8)) # pad between items
            tk.Label(
                cell,
                text=f"{symbol}:",
                fg="#e5e5e5",
                bg=BG,
                font=(FONT, FONT_SIZE),
            ).pack(side="left")
            tk.Label(
                cell,
                text=value,
                fg=color,
                bg=BG,
                font=(FONT, FONT_SIZE),
            ).pack(side="left", padx=(4, 0)) # pad between symbol and value

    def render(done, items):
        for w in row.winfo_children():
            w.destroy()
        if done > 0 and not items:
            tk.Label(
                row, text="✓ clear", fg=COLORS[0], bg=BG, font=(FONT, FONT_SIZE)
            ).pack(side="left")
            return
        ticks = "✓" * done
        if tick_stack == "left" and ticks:
            tk.Label(row, text=ticks, fg=COLORS[0], bg=BG, font=(FONT, FONT_SIZE)).pack(
                side="left", padx=(0, 10)
            )
        render_items(items)
        if tick_stack == "right" and ticks:
            tk.Label(row, text=ticks, fg=COLORS[0], bg=BG, font=(FONT, FONT_SIZE)).pack(
                side="left", padx=(0, 10)
            )

    def start_drag(e):
        state["x"], state["y"] = e.x_root, e.y_root
        state["locked"] = False

    def drag(e):
        dx, dy = e.x_root - state["x"], e.y_root - state["y"]
        state["x"], state["y"] = e.x_root, e.y_root
        root.geometry(f"+{root.winfo_x() + dx}+{root.winfo_y() + dy}")

    def refresh():
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            render_error("Invalid Path")
            if state["locked"]:
                place_window(root, pos, offset)
            root.after(int(poll * 1000), refresh)
            return
        if state["mtime"] != mtime:
            try:
                parsed = read_status(path)
            except Exception:
                parsed = None
            if parsed == "none":
                render_error("None")
                if state["locked"]:
                    place_window(root, pos, offset)
                state["mtime"] = mtime
            elif parsed is not None:
                done, items = parsed
                render(done, items)
                if state["locked"]:
                    place_window(root, pos, offset)
                state["mtime"] = mtime
        root.after(poll * 1000, refresh)

    root.bind("<Button-1>", start_drag)
    root.bind("<B1-Motion>", drag)
    root.bind("<Button-3>", lambda _e: root.destroy())
    place_window(root, pos, offset)
    if click_through:
        set_click_through(root)
    refresh()
    root.mainloop()


if __name__ == "__main__":
    main()
