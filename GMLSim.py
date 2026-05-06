"""
GML Control v0.81.0 - Desktop Application
==========================================
Requirements:
    pip install tkintermapview pillow

Run:
    python gml_control.py
"""

import tkinter as tk
from tkinter import messagebox, simpledialog
import time
import threading
import math
import os

try:
    import tkintermapview
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tkintermapview", "pillow"])
    import tkintermapview


# ─────────────────────────────────────────────────────────────
# SIMCONNECT PIPE READER
# ─────────────────────────────────────────────────────────────
class SimConnectReader:
    """Reads telemetry from the C++ SimConnect process via named pipe."""

    PIPE_NAME = r"\\.\pipe\simdata"

    def __init__(self, on_data):
        """on_data(lat, lon, alt, agl, bank, pitch, heading) callback"""
        self._on_data = on_data
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        while self._running:
            try:
                pipe = open(self.PIPE_NAME, "rb", buffering=0)
                print("Connected to SimConnect pipe!")
                buf = b""
                while self._running:
                    chunk = pipe.read(256)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        self._parse(line.decode().strip())
                pipe.close()
            except Exception as e:
                print(f"Pipe error: {e}, retrying in 2s...")
                time.sleep(2)

    def _parse(self, line):
        try:
            parts = line.split(",")
            if len(parts) == 7:
                lat, lon, alt, agl, bank, pitch, heading = map(float, parts)
                self._on_data(lat, lon, alt, agl, bank, pitch, heading)
        except ValueError:
            pass


# ─────────────────────────────────────────────────────────────
# COLOR PALETTE
# ─────────────────────────────────────────────────────────────
BG       = "#f0f0f0"
PANEL_BG = "#e8e8e8"
BTN_BG   = "#d4d4d4"
BORDER   = "#aaaaaa"
DARK_BG  = "#2b2b2b"
GREEN    = "#00cc00"
RED      = "#cc0000"
BLUE     = "#0078d7"
WHITE    = "#ffffff"
TEXT     = "#222222"


# ══════════════════════════════════════════════════════════════
# NAVIGATION MAP WINDOW
# ══════════════════════════════════════════════════════════════
class NavMapWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Navigation Map")
        self.geometry("860x640")
        self.minsize(600, 460)
        self.configure(bg="#1a1a1a")

        self._zoom = 2
        self._waypoint_index = 1
        self._total_waypoints = 40
        self._north_up = True
        self._crosshair_lat = 20.0
        self._crosshair_lon = 10.0
        self._heading = 0.0
        self._aircraft_marker = None

        self._build()

    def _build(self):
        # ── Map area ──
        map_container = tk.Frame(self, bg="#1a1a1a")
        map_container.pack(fill="both", expand=True)

        DARK_TILES = "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"

        self.map_widget = tkintermapview.TkinterMapView(
            map_container, corner_radius=0
        )
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_tile_server(DARK_TILES, max_zoom=19)
        self.map_widget.set_position(self._crosshair_lat, self._crosshair_lon)
        self.map_widget.set_zoom(self._zoom)

        # ── Speed / Alt overlay (top-left) ──
        self.speed_label = tk.Label(self.map_widget, text="0 kts",
                                    bg="#cccccc", fg="#111111",
                                    font=("Segoe UI", 16, "bold"),
                                    relief="flat", padx=6, pady=2, width=7, anchor="w")
        self.speed_label.place(x=6, y=10)

        self.alt_label = tk.Label(self.map_widget, text="0 ft",
                                  bg="#cccccc", fg="#111111",
                                  font=("Segoe UI", 16, "bold"),
                                  relief="flat", padx=6, pady=2, width=7, anchor="w")
        self.alt_label.place(x=6, y=52)

        # ── Vertical scale bar (left edge) ──
        self.scale_canvas = tk.Canvas(self.map_widget, width=30, bg="#1a1a1a",
                                      highlightthickness=0)
        self.scale_canvas.place(x=6, y=100, relheight=0.6)
        self._draw_scale_bar()

        # ── Bank arrow indicator ──
        self.arrow_label = tk.Label(self.map_widget, text="",
                                    bg="#1a1a1a", fg="#00aa00",
                                    font=("Arial", 28, "bold"))
        self.arrow_label.place(x=32, rely=0.45, anchor="w")

        # ── Overlay canvas (dashed line + crosshair) ──
        self.overlay = tk.Canvas(self.map_widget, bg="", highlightthickness=0)
        self.overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.map_widget.bind("<Configure>", self._on_resize)
        self._draw_overlays()

        # ── Bottom bar ──
        bottom = tk.Frame(self, bg="#2a2a2a", height=80)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        self.wp_counter = tk.Label(bottom, text=f"{self._waypoint_index} / {self._total_waypoints}",
                                   bg="#2a2a2a", fg=WHITE,
                                   font=("Segoe UI", 13))
        self.wp_counter.pack(pady=(4, 2))

        btn_row = tk.Frame(bottom, bg="#2a2a2a")
        btn_row.pack()

        btn_style = dict(font=("Segoe UI", 24, "bold"), width=3, height=1,
                         relief="raised", bd=2, cursor="hand2")

        tk.Button(btn_row, text="－", bg=BTN_BG, fg=TEXT,
                  command=self._zoom_out, **btn_style).pack(side="left", padx=2)
        tk.Button(btn_row, text="＋", bg=BTN_BG, fg=TEXT,
                  command=self._zoom_in, **btn_style).pack(side="left", padx=2)

        tk.Label(btn_row, text="", bg="#2a2a2a", width=4).pack(side="left")

        tk.Button(btn_row, text="⊕", bg="#a8c8e8", fg="#1a3a5a",
                  command=self._center_map,
                  font=("Segoe UI", 22, "bold"), width=3, height=1,
                  relief="raised", bd=2, cursor="hand2").pack(side="left", padx=2)

        self.orient_btn = tk.Button(btn_row, text="N↑", bg="#a8c8e8", fg="#1a3a5a",
                                    command=self._toggle_orientation,
                                    font=("Segoe UI", 16, "bold"), width=3, height=1,
                                    relief="raised", bd=2, cursor="hand2")
        self.orient_btn.pack(side="left", padx=2)

        tk.Label(bottom, text="🗺 mapbox", bg="#2a2a2a", fg="#555555",
                 font=("Segoe UI", 7)).place(x=4, rely=1.0, anchor="sw", y=-2)

    # ── Scale bar ──
    def _draw_scale_bar(self):
        self.scale_canvas.delete("all")
        h = self.scale_canvas.winfo_reqheight() or 300
        ticks = 14
        for i in range(ticks):
            y = int(i * h / (ticks - 1))
            color = "#cc0000" if i == 0 else "#888888"
            width = 20 if i == 0 else 14
            self.scale_canvas.create_line(6, y, 6 + width, y, fill=color, width=2)

    # ── Overlay (dashed line + crosshair) ──
    def _draw_overlays(self):
        self.overlay.delete("all")
        w = self.map_widget.winfo_width() or 800
        h = self.map_widget.winfo_height() or 500
        cx = w // 2

        dash_len = 12
        gap = 8
        y = 0
        while y < h:
            self.overlay.create_line(cx, y, cx, min(y + dash_len, h),
                                     fill="white", width=1, dash=(dash_len, gap))
            y += dash_len + gap

        arm = 22
        self.overlay.create_line(cx - arm, h // 2, cx + arm, h // 2,
                                  fill="#4488cc", width=2)
        self.overlay.create_line(cx, h // 2 - arm, cx, h // 2 + arm,
                                  fill="#4488cc", width=2)
        self.overlay.create_oval(cx - arm - 5, h // 2 - 4, cx - arm + 3, h // 2 + 4,
                                  fill="#cc2222", outline="")
        self.overlay.create_oval(cx + arm - 3, h // 2 - 4, cx + arm + 5, h // 2 + 4,
                                  fill="#4488cc", outline="")

        self.overlay.lift()
        self.speed_label.lift()
        self.alt_label.lift()
        self.scale_canvas.lift()
        self.arrow_label.lift()

    def _on_resize(self, event):
        self._draw_overlays()
        h = event.height
        self.scale_canvas.config(height=int(h * 0.6))
        self._draw_scale_bar()

    # ── Zoom / center / orientation ──
    def _zoom_in(self):
        self._zoom = min(22, self._zoom + 1)
        self.map_widget.set_zoom(self._zoom)

    def _zoom_out(self):
        self._zoom = max(1, self._zoom - 1)
        self.map_widget.set_zoom(self._zoom)

    def _center_map(self):
        self.map_widget.set_position(self._crosshair_lat, self._crosshair_lon)

    def _toggle_orientation(self):
        self._north_up = not self._north_up
        self.orient_btn.config(text="N↑" if self._north_up else "T↑")

    # ── Pitch indicator on scale bar ──
    def _update_pitch_indicator(self, pitch):
        self.scale_canvas.delete("pitch_line")
        h = self.scale_canvas.winfo_height() or 300
        clamped = max(-30, min(30, pitch))
        y = int(((-clamped + 30) / 60.0) * h)
        # Red V shape: two lines meeting at a point on the right, opening to the left
        tip_x = 28
        arm = 10
        self.scale_canvas.create_line(
            0, y - arm, tip_x, y,
            fill="#ff2222", width=2, tags="pitch_line"
        )
        self.scale_canvas.create_line(
            0, y + arm, tip_x, y,
            fill="#ff2222", width=2, tags="pitch_line"
        )

    # ── Heading to cardinal ──
    def _heading_to_cardinal(self, heading):
        dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"]
        return dirs[int((heading + 22.5) / 45) % 8]

    # ── Aircraft marker ──
    def _update_aircraft_marker(self, lat, lon, heading):
        if self._aircraft_marker:
            try:
                self._aircraft_marker.delete()
            except Exception:
                pass
        self._aircraft_marker = self.map_widget.set_marker(
            lat, lon,
            text=f"✈ {int(heading)}°",
            marker_color_circle="#0055ff",
            marker_color_outside="#003399"
        )

    # ── Main update entry point called from GMLControl ──
    def update_from_sim(self, lat, lon, alt_ft, agl_ft, bank, pitch, heading):
        """Update all nav map components from live sim data."""

        self._crosshair_lat = lat
        self._crosshair_lon = lon
        self._heading = heading

        # Alt: yellow when low AGL
        if agl_ft < 1000:
            self.alt_label.config(text=f"{agl_ft} ft", bg="#ffcc00")
        else:
            self.alt_label.config(text=f"{alt_ft} ft", bg="#cccccc")

        # Move map to aircraft position
        self.map_widget.set_position(lat, lon)

        # Bank arrow
        if bank > 5:
            self.arrow_label.config(text="↙", fg="#cc0000")
        elif bank < -5:
            self.arrow_label.config(text="↘", fg="#cc0000")
        else:
            self.arrow_label.config(text="→", fg="#00aa00")

        # Pitch indicator on scale bar
        self._update_pitch_indicator(pitch)

        # Orientation button label
        if self._north_up:
            self.orient_btn.config(text="N↑")
        else:
            cardinal = self._heading_to_cardinal(heading)
            self.orient_btn.config(text=cardinal)

        # Aircraft marker on map
        self._update_aircraft_marker(lat, lon, heading)


# ══════════════════════════════════════════════════════════════
# MAIN GML CONTROL WINDOW
# ══════════════════════════════════════════════════════════════
class GMLControl(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GML Control v0.81.0")
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.configure(bg=BG)

        # App state
        self.connected      = False
        self.timer_running  = False
        self.timer_seconds  = 0
        self._timer_thread  = None
        self.features       = [{"name": "test", "lat": 39.0, "lon": -98.0, "enabled": True, "marker": None}]
        self.waypoints      = []
        self.selected_feat  = None
        self.active_tab     = "features"
        self._nav_window    = None

        # Launch the SimConnect C++ process
        import subprocess
        # self._sim_process = subprocess.Popen(r"main.exe")

        # Kill sim process when app closes
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # SimConnect pipe reader
        self._sim_reader = SimConnectReader(on_data=self._on_sim_data)

        self._build_ui()
        self._draw_feature_markers()
        self._draw_waypoint_markers()

    # ──────────────────────────────────────────────
    # SIMCONNECT CALLBACKS
    # ──────────────────────────────────────────────
    def _on_sim_data(self, lat, lon, alt, agl, bank, pitch, heading):
        """Called from background pipe thread — schedule UI update on main thread."""
        self.after(0, self._update_telemetry, lat, lon, alt, agl, bank, pitch, heading)

    def _update_telemetry(self, lat, lon, alt, agl, bank, pitch, heading):
        """Update all UI components with latest sim data (runs on main thread)."""
        alt_ft = int(alt)
        agl_ft = int(agl)

        # Main window labels
        self.alt_label.config(text=f"{alt_ft} ft")
        self.map_widget.set_position(lat, lon)

        # Nav map window (if open)
        if self._nav_window and self._nav_window.winfo_exists():
            self._nav_window.update_from_sim(lat, lon, alt_ft, agl_ft, bank, pitch, heading)

    def _on_close(self):
        self._sim_reader.stop()
        if hasattr(self, "_sim_process") and self._sim_process.poll() is None:
            self._sim_process.terminate()
        self.destroy()

    # ──────────────────────────────────────────────
    # BUILD UI
    # ──────────────────────────────────────────────
    def _build_ui(self):
        self._build_topnav()

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True)

        self._build_left_panel(main)
        self._build_map_area(main)

        self._build_bottom_bar()

    # ── Top nav ──
    def _build_topnav(self):
        nav = tk.Frame(self, bg=BG, relief="raised", bd=1)
        nav.pack(fill="x")

        self._nav_buttons = {}
        buttons = [("⛓  Connect", self._toggle_connect, True),
                   ("Map",          lambda: self._nav_click("Map"), False),
                   ("Ground Check", lambda: self._nav_click("Ground Check"), False),
                   ("Status",       lambda: self._nav_click("Status"), False)]

        for label, cmd, is_connect in buttons:
            b = tk.Button(nav, text=label, command=cmd,
                          bg=BTN_BG,
                          fg=RED if is_connect else TEXT,
                          relief="raised", bd=1,
                          padx=8, pady=2, cursor="hand2",
                          font=("Segoe UI", 9, "bold" if is_connect else "normal"))
            b.pack(side="left", padx=2, pady=2)
            self._nav_buttons[label] = b
            if label == "Map":
                b.config(bg=BLUE, fg=WHITE)

        self._hamburger_btn = tk.Button(nav, text="☰",
                                        command=self._show_hamburger_menu,
                                        bg=BTN_BG, fg=TEXT, relief="raised", bd=1,
                                        padx=10, pady=2, cursor="hand2",
                                        font=("Segoe UI", 13))
        self._hamburger_btn.pack(side="right", padx=4, pady=2)

    def _nav_click(self, name):
        for lbl, b in self._nav_buttons.items():
            if lbl in ("Map", "Ground Check", "Status"):
                b.config(bg=BTN_BG, fg=TEXT)
        self._nav_buttons[name].config(bg=BLUE, fg=WHITE)

    # ── Hamburger dropdown ──
    def _show_hamburger_menu(self):
        menu = tk.Menu(self, tearoff=0, bg=BG, fg=TEXT,
                       font=("Segoe UI", 10),
                       activebackground=BLUE, activeforeground=WHITE)
        menu.add_command(label="⚙  Options",        command=self._open_options)
        menu.add_separator()
        menu.add_command(label="🗺  Navigation Map", command=self._open_nav_map)

        btn = self._hamburger_btn
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height()
        menu.tk_popup(x, y)

    def _open_options(self):
        dlg = tk.Toplevel(self)
        dlg.title("Options")
        dlg.geometry("300x200")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text="Options", bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(pady=(16, 6))
        tk.Label(dlg, text="No configurable options yet.", bg=BG, fg="#666",
                 font=("Segoe UI", 9)).pack()
        tk.Button(dlg, text="Close", command=dlg.destroy,
                  bg=BTN_BG, fg=TEXT, relief="raised", bd=1,
                  padx=12, cursor="hand2").pack(pady=20)

    def _open_nav_map(self):
        if self._nav_window and self._nav_window.winfo_exists():
            self._nav_window.lift()
            self._nav_window.focus_force()
            return
        self._nav_window = NavMapWindow(self)

    # ── Left panel ──
    def _build_left_panel(self, parent):
        panel = tk.Frame(parent, bg=BG, width=280, relief="sunken", bd=1)
        panel.pack(side="left", fill="y")
        panel.pack_propagate(False)

        # Operator / Plan
        info = tk.Frame(panel, bg=PANEL_BG, pady=4)
        info.pack(fill="x", padx=2, pady=2)

        for lbl, attr, default in [("Operator", "operator_var", ""),
                                    ("Plan",     "plan_var",     "PLAN0001")]:
            row = tk.Frame(info, bg=PANEL_BG)
            row.pack(fill="x", padx=4, pady=1)
            tk.Label(row, text=lbl, width=7, anchor="w",
                     bg=PANEL_BG, fg=TEXT, font=("Segoe UI", 9)).pack(side="left")
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            tk.Entry(row, textvariable=var, relief="sunken", bd=1,
                     font=("Segoe UI", 9), width=18).pack(side="left")

        # Transport bar
        transport = tk.Frame(panel, bg=PANEL_BG, pady=4)
        transport.pack(fill="x", padx=2, pady=2)

        ctrl_row = tk.Frame(transport, bg=PANEL_BG)
        ctrl_row.pack(fill="x", padx=4)

        for sym, cmd in [("■", self._stop_timer), ("▶", self._start_timer)]:
            tk.Button(ctrl_row, text=sym, command=cmd,
                      bg=BTN_BG, relief="raised", bd=1,
                      width=2, font=("Segoe UI", 11), cursor="hand2").pack(side="left", padx=2)

        self.timer_label = tk.Label(ctrl_row, text="0:00:00",
                                    bg=PANEL_BG, fg=GREEN,
                                    font=("Courier New", 20, "bold"))
        self.timer_label.pack(side="left", padx=6)

        speed_frame = tk.Frame(ctrl_row, bg=PANEL_BG)
        speed_frame.pack(side="left")
        self.speed_label = tk.Label(speed_frame, text="0 kts",
                                    bg="#d8d8d8", fg=TEXT,
                                    font=("Courier New", 9), relief="sunken", bd=1, width=7)
        self.speed_label.pack()
        self.alt_label = tk.Label(speed_frame, text="0 ft",
                                  bg="#d8d8d8", fg=TEXT,
                                  font=("Courier New", 9), relief="sunken", bd=1, width=7)
        self.alt_label.pack()

        self.status_badge = tk.Label(transport, text="Not Connected",
                                     bg="#c8c8c8", fg=TEXT,
                                     font=("Segoe UI", 8), relief="sunken", bd=1, padx=4)
        self.status_badge.pack(pady=2)

        # Tabs
        tabs = tk.Frame(panel, bg=PANEL_BG)
        tabs.pack(fill="x", padx=2)
        self.tab_btns = {}
        for name in ("Features", "Waypoints"):
            b = tk.Button(tabs, text=name,
                          bg=BG if name == "Features" else BTN_BG,
                          fg=TEXT, relief="raised", bd=1,
                          font=("Segoe UI", 9), cursor="hand2",
                          command=lambda n=name: self._switch_tab(n))
            b.pack(side="left", padx=1)
            self.tab_btns[name] = b

        # Feature toolbar
        ftbar = tk.Frame(panel, bg=PANEL_BG, pady=2)
        ftbar.pack(fill="x", padx=2)
        for sym, cmd in [("＋", self._add_feature_dialog),
                          ("－", self._remove_feature),
                          ("Clear", self._clear_features),
                          ("Edit...", self._edit_feature),
                          ("🔍", self._search_features)]:
            tk.Button(ftbar, text=sym, command=cmd,
                      bg=BTN_BG, fg=TEXT, relief="raised", bd=1,
                      font=("Segoe UI", 9), cursor="hand2", padx=4).pack(side="left", padx=1)

        # List frames
        self.list_frame = tk.Frame(panel, bg=WHITE, relief="sunken", bd=1)
        self.list_frame.pack(fill="both", expand=True, padx=2, pady=2)

        self.feat_frame = tk.Frame(self.list_frame, bg=WHITE)
        self.feat_frame.pack(fill="both", expand=True)

        feat_scroll = tk.Scrollbar(self.feat_frame)
        feat_scroll.pack(side="right", fill="y")
        self.feat_listbox = tk.Listbox(self.feat_frame, yscrollcommand=feat_scroll.set,
                                       bg=WHITE, fg=TEXT, selectbackground="#cce8ff",
                                       relief="flat", bd=0, font=("Segoe UI", 10),
                                       activestyle="none")
        self.feat_listbox.pack(fill="both", expand=True)
        feat_scroll.config(command=self.feat_listbox.yview)
        self.feat_listbox.bind("<<ListboxSelect>>", self._on_feat_select)
        self.feat_listbox.bind("<Double-1>", lambda e: self._toggle_feature_enabled())

        self.wp_frame = tk.Frame(self.list_frame, bg=WHITE)
        wp_scroll = tk.Scrollbar(self.wp_frame)
        wp_scroll.pack(side="right", fill="y")
        self.wp_listbox = tk.Listbox(self.wp_frame, yscrollcommand=wp_scroll.set,
                                     bg=WHITE, fg=TEXT, selectbackground="#fff3cc",
                                     relief="flat", bd=0, font=("Segoe UI", 10),
                                     activestyle="none")
        self.wp_listbox.pack(fill="both", expand=True)
        wp_scroll.config(command=self.wp_listbox.yview)

        self._refresh_features_list()
        self._refresh_waypoints_list()

    def _switch_tab(self, name):
        self.active_tab = name.lower()
        for n, b in self.tab_btns.items():
            b.config(bg=BG if n == name else BTN_BG)
        if name == "Features":
            self.wp_frame.pack_forget()
            self.feat_frame.pack(fill="both", expand=True)
        else:
            self.feat_frame.pack_forget()
            self.wp_frame.pack(fill="both", expand=True)

    # ── Map area ──
    def _build_map_area(self, parent):
        container = tk.Frame(parent, bg="#000000")
        container.pack(side="left", fill="both", expand=True)

        GOOGLE_SAT = "https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga"

        self.map_widget = tkintermapview.TkinterMapView(
            container, corner_radius=0
        )
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_tile_server(GOOGLE_SAT, max_zoom=22)
        self.map_widget.set_position(20, 0)
        self.map_widget.set_zoom(2)

        self.map_widget.add_right_click_menu_command(
            label="Add Waypoint Here",
            command=self._add_waypoint_at,
            pass_coords=True)
        self.map_widget.add_right_click_menu_command(
            label="Add Feature Here",
            command=self._add_feature_at,
            pass_coords=True)

        self.coords_label = tk.Label(container, text="Lat: 0.000   Lon: 0.000",
                                     bg="black", fg="#aaaaaa",
                                     font=("Courier New", 9))
        self.coords_label.place(relx=1.0, rely=1.0, anchor="se", x=-4, y=-4)
        self.map_widget.bind("<Motion>", self._on_map_motion)

    # ── Bottom bar ──
    def _build_bottom_bar(self):
        bar = tk.Frame(self, bg=DARK_BG, height=22)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        tk.Label(bar, text="▲   C A M E R A S   ▼",
                 bg=DARK_BG, fg="#888888",
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=8)

    # ──────────────────────────────────────────────
    # TIMER
    # ──────────────────────────────────────────────
    def _start_timer(self):
        if self.timer_running:
            return
        self.timer_running = True
        self._timer_thread = threading.Thread(target=self._run_timer, daemon=True)
        self._timer_thread.start()

    def _stop_timer(self):
        self.timer_running = False
        self.timer_seconds = 0
        self.timer_label.config(text="0:00:00")

    def _run_timer(self):
        while self.timer_running:
            time.sleep(1)
            if not self.timer_running:
                break
            self.timer_seconds += 1
            h = self.timer_seconds // 3600
            m = (self.timer_seconds % 3600) // 60
            s = self.timer_seconds % 60
            self.timer_label.config(text=f"{h}:{m:02d}:{s:02d}")

    # ──────────────────────────────────────────────
    # CONNECT / DISCONNECT
    # ──────────────────────────────────────────────
    def _toggle_connect(self):
        if not self.connected:
            self.connected = True
            self._sim_reader.start()
            self.status_badge.config(text="Connected", bg="#90ee90", fg="#006000")
            self._nav_buttons["⛓  Connect"].config(fg="#006600")
            self._start_timer()
        else:
            self.connected = False
            self._sim_reader.stop()
            self.status_badge.config(text="Not Connected", bg="#c8c8c8", fg=TEXT)
            self._nav_buttons["⛓  Connect"].config(fg=RED)
            self._stop_timer()
            self.speed_label.config(text="0 kts")
            self.alt_label.config(text="0 ft")

    # ──────────────────────────────────────────────
    # FEATURES
    # ──────────────────────────────────────────────
    def _refresh_features_list(self):
        self.feat_listbox.delete(0, "end")
        for f in self.features:
            chk = "☑" if f["enabled"] else "☐"
            self.feat_listbox.insert("end", f"  {chk}  {f['name']}")

    def _draw_feature_markers(self):
        for f in self.features:
            if f.get("marker"):
                try: f["marker"].delete()
                except Exception: pass
            if f["enabled"]:
                f["marker"] = self.map_widget.set_marker(
                    f["lat"], f["lon"], text=f["name"],
                    marker_color_circle="#e74c3c",
                    marker_color_outside="#cc0000")
            else:
                f["marker"] = None

    def _on_feat_select(self, event):
        sel = self.feat_listbox.curselection()
        if sel:
            self.selected_feat = sel[0]
            f = self.features[sel[0]]
            self.map_widget.set_position(f["lat"], f["lon"])

    def _toggle_feature_enabled(self):
        if self.selected_feat is not None:
            f = self.features[self.selected_feat]
            f["enabled"] = not f["enabled"]
            self._refresh_features_list()
            self._draw_feature_markers()

    def _add_feature_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Add Feature")
        dlg.geometry("260x200")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        fields = {}
        for label, default in [("Name", ""), ("Latitude", "0.0"), ("Longitude", "0.0")]:
            row = tk.Frame(dlg, bg=BG)
            row.pack(fill="x", padx=12, pady=4)
            tk.Label(row, text=label, width=9, anchor="w", bg=BG,
                     font=("Segoe UI", 9)).pack(side="left")
            var = tk.StringVar(value=default)
            tk.Entry(row, textvariable=var, relief="sunken", bd=1,
                     font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True)
            fields[label] = var

        def do_add():
            name = fields["Name"].get().strip() or "Feature"
            try:
                lat = float(fields["Latitude"].get())
                lon = float(fields["Longitude"].get())
            except ValueError:
                messagebox.showerror("Error", "Invalid lat/lon", parent=dlg)
                return
            self.features.append({"name": name, "lat": lat, "lon": lon,
                                   "enabled": True, "marker": None})
            self._refresh_features_list()
            self._draw_feature_markers()
            dlg.destroy()

        btns = tk.Frame(dlg, bg=BG)
        btns.pack(pady=8)
        tk.Button(btns, text="Cancel", command=dlg.destroy, bg=BTN_BG,
                  relief="raised", bd=1, padx=8, cursor="hand2").pack(side="left", padx=4)
        tk.Button(btns, text="Add", command=do_add, bg=BLUE, fg=WHITE,
                  relief="raised", bd=1, padx=8, cursor="hand2").pack(side="left", padx=4)

    def _add_feature_at(self, coords):
        lat, lon = coords
        name = simpledialog.askstring("Add Feature",
                                      f"Name for feature at\n{lat:.4f}, {lon:.4f}:",
                                      initialvalue="Feature")
        if name is not None:
            self.features.append({"name": name or "Feature", "lat": lat, "lon": lon,
                                   "enabled": True, "marker": None})
            self._refresh_features_list()
            self._draw_feature_markers()

    def _remove_feature(self):
        if self.selected_feat is not None and self.selected_feat < len(self.features):
            f = self.features.pop(self.selected_feat)
            if f.get("marker"):
                try: f["marker"].delete()
                except: pass
            self.selected_feat = None
            self._refresh_features_list()
        else:
            messagebox.showinfo("Info", "Select a feature first.")

    def _clear_features(self):
        if messagebox.askyesno("Clear", "Clear all features?"):
            for f in self.features:
                if f.get("marker"):
                    try: f["marker"].delete()
                    except: pass
            self.features.clear()
            self.selected_feat = None
            self._refresh_features_list()

    def _edit_feature(self):
        if self.selected_feat is None or self.selected_feat >= len(self.features):
            messagebox.showinfo("Info", "Select a feature first.")
            return
        f = self.features[self.selected_feat]
        dlg = tk.Toplevel(self)
        dlg.title("Edit Feature")
        dlg.geometry("260x200")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        fields = {}
        for label, default in [("Name", f["name"]), ("Latitude", str(f["lat"])),
                                ("Longitude", str(f["lon"]))]:
            row = tk.Frame(dlg, bg=BG)
            row.pack(fill="x", padx=12, pady=4)
            tk.Label(row, text=label, width=9, anchor="w", bg=BG,
                     font=("Segoe UI", 9)).pack(side="left")
            var = tk.StringVar(value=default)
            tk.Entry(row, textvariable=var, relief="sunken", bd=1,
                     font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True)
            fields[label] = var

        def do_save():
            try:
                lat = float(fields["Latitude"].get())
                lon = float(fields["Longitude"].get())
            except ValueError:
                messagebox.showerror("Error", "Invalid lat/lon", parent=dlg)
                return
            if f.get("marker"):
                try: f["marker"].delete()
                except: pass
            f["name"] = fields["Name"].get().strip() or f["name"]
            f["lat"] = lat
            f["lon"] = lon
            f["marker"] = None
            self._refresh_features_list()
            self._draw_feature_markers()
            dlg.destroy()

        btns = tk.Frame(dlg, bg=BG)
        btns.pack(pady=8)
        tk.Button(btns, text="Cancel", command=dlg.destroy, bg=BTN_BG,
                  relief="raised", bd=1, padx=8, cursor="hand2").pack(side="left", padx=4)
        tk.Button(btns, text="Save", command=do_save, bg=BLUE, fg=WHITE,
                  relief="raised", bd=1, padx=8, cursor="hand2").pack(side="left", padx=4)

    def _search_features(self):
        q = simpledialog.askstring("Search Features", "Feature name:")
        if not q:
            return
        for i, f in enumerate(self.features):
            if q.lower() in f["name"].lower():
                self.feat_listbox.selection_clear(0, "end")
                self.feat_listbox.selection_set(i)
                self.feat_listbox.see(i)
                self.selected_feat = i
                self.map_widget.set_position(f["lat"], f["lon"])
                return
        messagebox.showinfo("Search", f'No feature matching "{q}".')

    # ──────────────────────────────────────────────
    # WAYPOINTS
    # ──────────────────────────────────────────────
    def _refresh_waypoints_list(self):
        self.wp_listbox.delete(0, "end")
        if not self.waypoints:
            self.wp_listbox.insert("end", "  Right-click map to add waypoints")
            return
        for i, wp in enumerate(self.waypoints):
            self.wp_listbox.insert(
                "end", f"  {i+1}.  {wp['name']}   ({wp['lat']:.4f}, {wp['lon']:.4f})")

    def _draw_waypoint_markers(self):
        for wp in self.waypoints:
            if wp.get("marker"):
                try: wp["marker"].delete()
                except: pass
            wp["marker"] = self.map_widget.set_marker(
                wp["lat"], wp["lon"], text=wp["name"],
                marker_color_circle="#f39c12",
                marker_color_outside="#e67e22")
        if hasattr(self, "_wp_path") and self._wp_path:
            try: self._wp_path.delete()
            except: pass
        self._wp_path = None
        if len(self.waypoints) >= 2:
            coords = [(wp["lat"], wp["lon"]) for wp in self.waypoints]
            self._wp_path = self.map_widget.set_path(coords, color="#f39c12", width=2)

    def _add_waypoint_at(self, coords):
        lat, lon = coords
        name = simpledialog.askstring(
            "Add Waypoint",
            f"Name for waypoint at\n{lat:.4f}, {lon:.4f}:",
            initialvalue=f"WP{len(self.waypoints)+1}")
        if name is not None:
            self.waypoints.append({"name": name or f"WP{len(self.waypoints)+1}",
                                    "lat": lat, "lon": lon, "marker": None})
            self._refresh_waypoints_list()
            self._draw_waypoint_markers()

    # ──────────────────────────────────────────────
    # MAP UTILS
    # ──────────────────────────────────────────────
    def _on_map_motion(self, event):
        try:
            coords = self.map_widget.convert_canvas_coords_to_decimal_coords(event.x, event.y)
            if coords:
                self.coords_label.config(
                    text=f"Lat: {coords[0]:>8.4f}   Lon: {coords[1]:>9.4f}")
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = GMLControl()
    app.mainloop()