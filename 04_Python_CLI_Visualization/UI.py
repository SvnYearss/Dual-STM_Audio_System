"""
UI.py  —  Rose Noir Edition
Dual-STM Audio Acquisition System
Requires: pip install rich pyserial
Run:      python UI.py
"""

import time
import os
import threading
import collections
from datetime import datetime

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn, TextColumn
    from rich.table import Table
    from rich.text import Text
    from rich.rule import Rule
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

import main_cli as audio

# ─────────────────────────── THEME ENGINE ───────────────────────────
THEMES = {
    "ROSE_NOIR": {
        "HOT":   "bright_magenta", # #ff80c0
        "MID":   "#e090c0",
        "TEAL":  "#40e8c0",
        "AMBER": "#e0b858",
        "DIM":   "#7a4060",
        "GHOST": "#5a2848",
        "FAIL":  "#ff4060",
        "WHITE": "#ffbbee",
        "TITLE": "ROSE NOIR EDITION"
    },
    "ICE_STATION": {
        "HOT":   "bright_cyan",    # Active states, titles
        "MID":   "#90c0e0",        # Primary text
        "TEAL":  "bright_blue",    # Success, OK
        "AMBER": "white",          # Running (Ice stations use stark white for active)
        "DIM":   "#40607a",        # Labels
        "GHOST": "#28485a",        # Timestamps, borders
        "FAIL":  "#ff4060",        # Errors (Keep red for safety)
        "WHITE": "#eeffff",        # Highlighted values
        "TITLE": "ICE STATION EDITION"
    },
    "CYBER_GREEN": {
        "HOT":   "bright_green", 
        "MID":   "green",        
        "TEAL":  "spring_green1",
        "AMBER": "yellow",       
        "DIM":   "dark_green",   
        "GHOST": "grey50",       
        "FAIL":  "red",          
        "WHITE": "white",        
        "TITLE": "CYBER TERMINAL"
    }
}

# 1. ⚙️ SET YOUR ACTIVE THEME HERE:
ACTIVE_THEME = "ICE_STATION"  # Try changing this to "ROSE_NOIR" or "CYBER_GREEN"

# 2. Extract the palette automatically
_palette = THEMES[ACTIVE_THEME]

# 3. Map to global variables (so the rest of your UI.py code doesn't break!)
HOT   = _palette["HOT"]
MID   = _palette["MID"]
TEAL  = _palette["TEAL"]
AMBER = _palette["AMBER"]
DIM   = _palette["DIM"]
GHOST = _palette["GHOST"]
FAIL  = _palette["FAIL"]
WHITE = _palette["WHITE"]
THEME_TITLE = _palette["TITLE"]

console = Console() if RICH_AVAILABLE else None

# ──────────────────────────── HEADER ────────────────────────────
def render_header(frame: int) -> Panel:
    now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    t = Table.grid(expand=True, padding=(0, 2))
    t.add_column(style=DIM,   no_wrap=True)
    t.add_column(style=MID,   no_wrap=True)
    t.add_column(style=DIM,   no_wrap=True)
    t.add_column(style=WHITE, no_wrap=True)
    t.add_column(style=DIM,   no_wrap=True)
    t.add_column(style=MID,   no_wrap=True)

    t.add_row("PORT",        audio.PORT,
              "BAUD",        f"{audio.BAUD:,} bps",
              "TEAM",        audio.TEAM_ID)
    t.add_row("SAMPLE RATE", f"{audio.OUTPUT_FS} Hz",
              "BIT DEPTH",   f"{audio.BIT_DEPTH}-bit ADC",
              "TIME",        now)
    t.add_row("CONV SOURCE", os.path.basename(audio.CONVERTER_SOURCE),
              "OUTPUT DIR",  os.path.basename(audio.REPO_ROOT),
              "OUTLIER THR", f"±{audio.OUTLIER_THRESHOLD} ADC")

    title_txt = Text()
    title_txt.append("◈  DUAL-STM AUDIO ACQUISITION SYSTEM  ◈",
                      style=f"bold {HOT}")

    return Panel(t, title=title_txt,
                 border_style=DIM, box=box.DOUBLE_EDGE, padding=(0, 1))

# ─────────────────────────── PIPELINE ───────────────────────────
def render_pipeline(statuses: dict, frame: int) -> Panel:
    SPIN = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    sp = SPIN[frame % len(SPIN)]

    ICON = {
        audio.State.PENDING: (f"[{GHOST}]○[/]",  GHOST),
        audio.State.RUNNING: (f"[{AMBER}]{sp}[/]", AMBER),
        audio.State.OK:      (f"[{TEAL}]✔[/]",    TEAL),
        audio.State.FAIL:    (f"[{FAIL}]✘[/]",    FAIL),
    }

    t = Table.grid(expand=True, padding=(0, 1))
    t.add_column(width=2,  no_wrap=True)
    t.add_column(width=9,  no_wrap=True)
    t.add_column(no_wrap=True)

    for key, desc in audio.State.STEPS:
        st = statuses.get(key, audio.State.PENDING)
        icon, c = ICON.get(st, ICON[audio.State.PENDING])
        k_s = {audio.State.OK: TEAL, audio.State.RUNNING: AMBER,
               audio.State.FAIL: FAIL, audio.State.PENDING: GHOST}[st]
        d_s = k_s if st != audio.State.RUNNING else f"bold {AMBER}"
        t.add_row(icon, f"[{k_s}]{key}[/]", f"[{d_s}]{desc}[/]")

    return Panel(t, title=f"[bold {HOT}]PIPELINE[/]",
                 border_style=GHOST, box=box.ROUNDED, padding=(0, 1))

# ─────────────────────────── TELEMETRY ──────────────────────────
_WF = ["▁▂▃▄▅▆▇█▇▆▅▄▃▂▁","▂▃▄▅▆▇█▇▆▅▄▃▂▁▂",
       "▃▄▅▆▇█▇▆▅▄▃▂▁▂▃","▄▅▆▇█▇▆▅▄▃▂▁▂▃▄",
       "▅▆▇█▇▆▅▄▃▂▁▂▃▄▅","▆▇█▇▆▅▄▃▂▁▂▃▄▅▆",
       "▇█▇▆▅▄▃▂▁▂▃▄▅▆▇","█▇▆▅▄▃▂▁▂▃▄▅▆▇█"]

def _bar_color(pct: float) -> str:
    if pct <= 0.20: return "#cc1144"
    if pct <  1.00: return "#cc44aa"
    return TEAL

def render_telemetry(state, frame: int) -> Panel:
    with state._lock:
        captured  = state.captured
        speed     = state.speed_bps
        start_ts  = state.start_ts
        recording = state.statuses.get("RECORD") == audio.State.RUNNING

    total     = audio.OUTPUT_FS * audio.SAMPLE_WIDTH_BYTES * state.duration
    pct       = min(captured / max(total, 1), 1.0) if total else 0
    pct_int   = int(pct * 100)
    bc        = _bar_color(pct)
    speed_ok  = speed >= audio.NOMINAL_FS * audio.SAMPLE_WIDTH_BYTES * 0.9

    W = max(console.width - 50, 10)
    bar_w = max(W, 10)
    filled = int(bar_w * pct); empty = bar_w - filled
    bar = Text()
    bar.append("█" * filled, style=f"bold {bc}")
    bar.append("░" * empty,  style=GHOST)

    if start_ts:
        elapsed = time.time() - start_ts
        eta = max((elapsed / pct) - elapsed, 0) if 0 < pct < 1 else 0
        el_s  = f"{elapsed:.1f}s"
        eta_s = f"{eta:.1f}s" if 0 < pct < 1 else "—"
    else:
        el_s = eta_s = "—"

    kbs_s = f"{speed/1024:.1f} kB/s" if speed >= 1024 else f"{speed:.0f} B/s"
    spd_tag = f"[{TEAL}]▲ OK[/]" if speed_ok else f"[{FAIL}]▼ BOTTLENECK[/]"
    wf = _WF[frame % len(_WF)] if recording else ("─" * 17)

    t = Table.grid(expand=True, padding=(0, 1))
    t.add_column(width=12, style=DIM, no_wrap=True)
    t.add_column(no_wrap=True)

    t.add_row("CAPTURED",
        Text.from_markup(f"[bold {bc}]{captured:,}[/] [{GHOST}]/[/] [{MID}]{int(total):,}[/]  [{bc}]({pct_int}%)[/]"))
    t.add_row("PROGRESS", bar)
    t.add_row("ELAPSED",  Text.from_markup(f"[{HOT}]{el_s}[/]  [{GHOST}]ETA[/]  [{HOT}]{eta_s}[/]"))
    t.add_row("SPEED",    Text.from_markup(
        f"[{'bold '+TEAL if speed_ok else FAIL}]{kbs_s}[/]  {spd_tag}  [{AMBER}]{wf}[/]"))
    t.add_row("SAMPLES",  Text.from_markup(
        f"[{WHITE}]{captured // audio.SAMPLE_WIDTH_BYTES:,}[/] [{GHOST}]@ {audio.BIT_DEPTH}-bit[/]"))

    return Panel(t, title=f"[bold {HOT}]LIVE TELEMETRY[/]",
                 border_style=bc, box=box.ROUNDED, padding=(0, 1))

# ─────────────────── OUTPUT FORMAT BADGE ROW ────────────────────
def render_format_badges(options: list) -> Panel:
    ALL = ["WAV", "PNG", "CSV", "TXT"]
    t = Table.grid(expand=True, padding=(0, 2))
    t.add_column()
    row = Text()
    for fmt in ALL:
        if fmt in options:
            row.append(f" {fmt} ✔ ", style=f"bold {TEAL} on #1a0818")
        else:
            row.append(f" {fmt}   ", style=f"{GHOST} on #0d0510")
        row.append("  ")
    t.add_row(row)
    return Panel(t, title=f"[bold {HOT}]OUTPUT FORMATS[/]",
                 border_style=GHOST, box=box.ROUNDED, padding=(0, 1))

# ───────────────────── PROCESSING OUTPUT PANEL ──────────────────
def render_processing_output(result: dict) -> Panel:
    """
    Converts the ugly print() lines from process_outputs() into a
    structured, colour-coded panel — split into left (signal) and
    right (files) columns.
    """
    t = Table.grid(expand=True, padding=(0, 1))
    t.add_column(ratio=1)
    t.add_column(ratio=1)

    # ── left column: signal chain stats ──
    left = Table.grid(padding=(0, 1))
    left.add_column(width=15, style=DIM, no_wrap=True)
    left.add_column(no_wrap=True)

    m_rate  = result.get("measured_rate", 0)
    out_rate = result.get("output_rate", audio.OUTPUT_FS)
    n_samp  = result.get("n_samples", 0)
    reject  = result.get("rejected", 0)
    filter_on = result.get("filter_enabled", audio.FILTER_ENABLED)
    hp_hz   = result.get("hp_hz", audio.HIGHPASS_CUTOFF_HZ)
    lp_hz   = result.get("lp_hz", audio.LOWPASS_CUTOFF_HZ)
    notch   = result.get("mains_hz", audio.MAINS_HUM_HZ)
    notch_n = result.get("notch_n", audio.MAINS_NOTCH_HARMONICS)
    spec_on = result.get("spectral", audio.SPECTRAL_DENOISE_ENABLED)
    elapsed = result.get("elapsed", 0)
    mode    = result.get("mode", "—")

    left.add_row("MODE",        Text.from_markup(f"[{HOT}]{mode}[/]"))
    left.add_row("ELAPSED",     Text.from_markup(f"[{WHITE}]{elapsed:.2f}s[/]"))
    left.add_row("MEAS RATE",   Text.from_markup(f"[{AMBER}]{m_rate:,} Hz[/]"))
    left.add_row("OUTPUT RATE", Text.from_markup(f"[{WHITE}]{out_rate:,} Hz[/]"))
    left.add_row("SAMPLES",     Text.from_markup(f"[{WHITE}]{n_samp:,}[/] [{GHOST}]@ {audio.BIT_DEPTH}-bit[/]"))
    left.add_row("DEGLITCH",
        Text.from_markup(f"[{TEAL}]{reject} spikes[/] [{GHOST}]removed[/]") if reject
        else Text.from_markup(f"[{TEAL}]clean[/] [{GHOST}](0 spikes)[/]"))

    if filter_on:
        left.add_row("NOISE FILTER", Text.from_markup(f"[{TEAL}]APPLIED[/]"))
        left.add_row("",
            Text.from_markup(f"[{GHOST}]↳ HP[/] [{AMBER}]{hp_hz:.0f} Hz[/]  [{GHOST}]LP[/] [{AMBER}]{lp_hz:.0f} Hz[/]"))
        left.add_row("",
            Text.from_markup(f"[{GHOST}]↳ Notch[/] [{AMBER}]{notch:.0f} Hz ×{notch_n}[/]  "
                             f"[{GHOST}]Spectral[/] [{'bright_green' if spec_on else FAIL}]{'ON' if spec_on else 'OFF'}[/]"))
    else:
        left.add_row("NOISE FILTER", Text.from_markup(f"[{GHOST}]DISABLED[/]"))

    # ── right column: generated file list + converter info ──
    right = Table.grid(padding=(0, 1))
    right.add_column(width=3,  no_wrap=True)
    right.add_column(no_wrap=True)

    conv_info = result.get("converter_info", "")
    files     = result.get("generated_files", [])
    errors    = result.get("errors", [])

    if conv_info:
        right.add_row("", Text.from_markup(f"[{DIM}]{conv_info}[/]"))

    if files:
        right.add_row("", Text.from_markup(f"[{DIM}]──── Generated Files ────[/]"))
        for f in files:
            right.add_row(
                Text.from_markup(f"[{TEAL}]→[/]"),
                Text.from_markup(f"[{HOT}]{f}[/]"))

    for e in errors:
        right.add_row(
            Text.from_markup(f"[{FAIL}]✘[/]"),
            Text.from_markup(f"[{FAIL}]{e}[/]"))

    if result.get("success"):
        right.add_row("", Text(""))
        right.add_row(
            Text.from_markup(f"[{TEAL}]✔[/]"),
            Text.from_markup(f"[bold {TEAL}]Outputs generated successfully![/]"))

    t.add_row(left, right)
    return Panel(t,
                 title=f"[bold {HOT}]PROCESSING OUTPUT[/]",
                 border_style=TEAL if result.get("success") else AMBER,
                 box=box.ROUNDED, padding=(0, 1))

# ──────────────────────────── LOG ───────────────────────────────
def render_log(log_lines: list) -> Panel:
    t = Table.grid(expand=True, padding=(0, 1))
    t.add_column(width=14, style=GHOST, no_wrap=True)
    t.add_column(no_wrap=True)
    if not log_lines:
        t.add_row("", Text.from_markup(f"[{GHOST}]Waiting for events…[/]"))
    for ts, msg, style in log_lines:
        t.add_row(f"[{GHOST}]{ts}[/]", Text.from_markup(f"[{style}]{msg}[/]"))
    return Panel(t, title=f"[bold {HOT}]EVENT LOG[/]",
                 border_style=GHOST, box=box.ROUNDED, padding=(0, 1))

# ─────────────────── CAPTURE-PHASE FULL LAYOUT ──────────────────
def make_capture_layout(state, frame: int) -> Table:
    with state._lock:
        statuses  = dict(state.statuses)
        log_lines = list(state.log)

    root = Table.grid(expand=True, padding=0)
    root.add_column()
    root.add_row(render_header(frame))

    mid = Table.grid(expand=True, padding=0)
    mid.add_column(ratio=2)
    mid.add_column(ratio=3)
    mid.add_row(render_pipeline(statuses, frame),
                render_telemetry(state, frame))
    root.add_row(mid)
    root.add_row(render_log(log_lines))
    return root

# ──────────────────── ACQUISITION STATE OBJECT ──────────────────
class State:
    STEPS = [
        ("INIT",    "Initialising serial port"),
        ("CONNECT", "Handshaking with STM32"),
        ("RECORD",  "Acquiring audio stream"),
        ("STOP",    "Sending stop command"),
        ("COMPILE", "Compiling C converter"),
        ("CONVERT", "Running WAV conversion"),
        ("DONE",    "Pipeline complete"),
    ]
    PENDING = "pending"; RUNNING = "running"; OK = "ok"; FAIL = "fail"

    def __init__(self, duration: float, options: list):
        self.statuses  = {k: self.PENDING for k, _ in self.STEPS}
        self.captured  = 0
        self.speed_bps = 0.0
        self.log       = collections.deque(maxlen=6)
        self.start_ts  = None
        self.end_ts    = None
        self.duration  = duration
        self.options   = options
        self.error_msg = ""
        self._lock     = threading.Lock()

    def set(self, key, status):
        with self._lock: self.statuses[key] = status

    def add_log(self, msg, style=GHOST):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with self._lock: self.log.append((ts, msg, style))

    def update_capture(self, captured, speed):
        with self._lock: self.captured = captured; self.speed_bps = speed

# Patch audio.State so render_pipeline() can use it
audio.State = State

# ─────────────────────────── MENU ───────────────────────────────
def render_menu_table() -> Table:
    t = Table(title="", box=box.SIMPLE, show_header=False, expand=False)
    t.add_column("Key",    style=f"bold {HOT}",  width=4)
    t.add_column("Action", style=MID)
    t.add_row("1", "Manual Recording Mode")
    t.add_row("2", "Distance Trigger Mode")
    t.add_row("q", "Quit Program")
    return t

# ──────────────────── OUTPUT PREFERENCES ────────────────────────
# ──────────────────── OUTPUT PREFERENCES ────────────────────────
def get_output_preferences() -> list:
    console.print() # Breathing room
    console.rule(f"[bold {HOT}]◈ OUTPUT CONFIGURATION ◈[/]", style=GHOST)
    console.print() # Breathing room
    
    options = []
    fmts = [("WAV",  "Generate .WAV audio file"),
            ("PNG",  "Generate .PNG waveform plot"),
            ("CSV",  "Generate .CSV raw data file")]
            
    for tag, label in fmts:
        # The :<28 ensures the labels are padded with spaces so the (y/n) stack perfectly
        prompt = f"  [{HOT}]>[/] [{MID}]{label:<28}[/] [{GHOST}](y/n)[/] [{HOT}]»[/] "
        
        ans = console.input(prompt).strip().lower()
        if ans == "y":
            options.append(tag)
            
    # Print a clean summary of what was selected
    selected = ", ".join(options) if options else "None"
    console.print(f"  [{DIM}]└─ Targets:[/] [{TEAL}]{selected}[/]\n")
    
    return options

# ──────────────────── CAPTURE WITH LIVE UI ──────────────────────
def capture_with_live_ui(ser, duration: float, mode_name: str,
                          options: list) -> tuple:
    """
    Replaces capture_for_duration() in UI.py.
    Runs the serial capture in a background thread and renders the
    full Rose Noir live layout at ~12 fps.
    Returns (raw_data, measured_rate, elapsed)
    """
    import collections as _col

    state = State(duration, options)
    raw_chunks = []
    result_box = {}

    def worker():
        # INIT
        state.set("INIT", State.RUNNING)
        state.add_log("Opening serial port…", GHOST)

        # CONNECT
        state.set("INIT", State.OK)
        state.set("CONNECT", State.RUNNING)
        state.add_log("Sending 'M' to Processing STM…", AMBER)

        import serial as _serial
        ser.reset_input_buffer()
        time.sleep(0.05)
        got_ack, seen = audio.send_command_and_wait_for_ack(ser, b"M")
        if got_ack:
            state.add_log("Processing STM acknowledged manual start.", TEAL)
        else:
            state.add_log("No ACK:M — continuing capture anyway.", AMBER)
        ser.reset_input_buffer()
        state.set("CONNECT", State.OK)

        # RECORD
        state.set("RECORD", State.RUNNING)
        state.start_ts = time.time()
        deadline = state.start_ts + duration
        byte_goal = int(audio.OUTPUT_FS * audio.SAMPLE_WIDTH_BYTES * duration)
        speed_buf = _col.deque(maxlen=12)

        while time.time() < deadline:
            remaining = deadline - time.time()
            want = int(audio.NOMINAL_FS * audio.SAMPLE_WIDTH_BYTES
                       * min(0.05, max(0.001, remaining)))
            t0    = time.perf_counter()
            chunk = ser.read(max(audio.SAMPLE_WIDTH_BYTES, min(8192, want)))
            dt    = time.perf_counter() - t0
            if chunk:
                raw_chunks.append(chunk)
                if dt > 0:
                    speed_buf.append(len(chunk) / dt)
                captured = sum(len(c) for c in raw_chunks)
                state.update_capture(captured,
                    sum(speed_buf)/len(speed_buf) if speed_buf else 0)

        state.end_ts = time.time()
        elapsed = state.end_ts - state.start_ts
        raw_data = b"".join(raw_chunks)
        captured_final = sum(len(c) for c in raw_chunks)
        state.add_log(
            f"Captured {captured_final:,} bytes in {elapsed:.2f}s", TEAL)
        state.set("RECORD", State.OK)

        # STOP
        state.set("STOP", State.RUNNING)
        ser.write(b"S"); ser.flush()
        state.set("STOP", State.OK)
        state.add_log("Sent 'S' — STM halted.", TEAL)

        result_box["raw_data"] = raw_data
        result_box["elapsed"]  = elapsed
        result_box["n_samples"]= len(raw_data) // audio.SAMPLE_WIDTH_BYTES
        result_box["measured_rate"] = audio.measured_sample_rate(
            result_box["n_samples"], elapsed)
        state.set("DONE", State.OK)
        state.add_log("Recording phase complete.", HOT)

    worker_t = threading.Thread(target=worker, daemon=True)
    worker_t.start()

    frame = 0
    with Live(make_capture_layout(state, frame), console=console,
              refresh_per_second=12, screen=False) as live:
        while worker_t.is_alive():
            live.update(make_capture_layout(state, frame))
            frame += 1
            time.sleep(0.08)
        frame += 1
        live.update(make_capture_layout(state, frame))

    return (result_box.get("raw_data", b""),
            result_box.get("measured_rate", audio.NOMINAL_FS),
            result_box.get("elapsed", duration))

# ──────────────────── PROCESSING LIVE PANEL ─────────────────────
def show_processing_live(raw_data: bytes, options: list,
                          mode_name: str, measured_rate: int,
                          elapsed: float):
    """
    Wraps audio.process_outputs() and intercepts its print() calls
    to build structured result data for render_processing_output().
    """
    import io
    from contextlib import redirect_stdout

    result = {
        "mode": mode_name, "elapsed": elapsed,
        "measured_rate": measured_rate,
        "output_rate": audio.OUTPUT_FS,
        "hp_hz": audio.HIGHPASS_CUTOFF_HZ,
        "lp_hz": audio.LOWPASS_CUTOFF_HZ,
        "mains_hz": audio.MAINS_HUM_HZ,
        "notch_n": audio.MAINS_NOTCH_HARMONICS,
        "spectral": audio.SPECTRAL_DENOISE_ENABLED,
        "filter_enabled": audio.FILTER_ENABLED,
        "generated_files": [], "errors": [], "success": False,
        "n_samples": 0, "rejected": 0, "converter_info": "",
    }

    console.print(Panel(
        Text.from_markup(f"[{AMBER}]Processing signal pipeline…[/]"),
        border_style=AMBER, box=box.ROUNDED, padding=(0, 2)))

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            audio.process_outputs(raw_data, options, mode_name, measured_rate)
        output_text = buf.getvalue()
    except Exception as exc:
        result["errors"].append(str(exc))
        console.print(render_processing_output(result))
        return

    # Parse captured print() output into structured fields
    for line in output_text.splitlines():
        ls = line.strip()
        if ls.startswith("Decoded samples:"):
            try:
                result["n_samples"] = int(ls.split()[2].replace(",",""))
            except: pass
        elif "Deglitched" in ls:
            try:
                result["rejected"] = int(ls.split()[1])
            except: pass
        elif ls.startswith("Converted"):
            result["converter_info"] = ls
        elif ls.startswith("-> Generated"):
            fname = ls.replace("-> Generated", "").strip()
            result["generated_files"].append(fname)
        elif "failed" in ls.lower() or "error" in ls.lower():
            result["errors"].append(ls)
        elif ls == "Outputs generated successfully!":
            result["success"] = True

    if not result["errors"]:
        result["success"] = True

    console.print(render_processing_output(result))

# ───────────────────────── MANUAL MODE ──────────────────────────
def manual_recording_mode():
    console.rule(f"[bold {HOT}]Manual Recording Mode[/]")
    try:
        duration = float(console.input(
            f"[{DIM}]Enter recording duration (seconds):[/] ").strip())
    except ValueError:
        console.print(f"[{FAIL}]Invalid duration.[/]"); return

    options = get_output_preferences()

    try:
        with audio.serial.Serial(audio.PORT, audio.BAUD, timeout=0.02) as ser:
            console.input(
                f"\n[{GHOST}]Press Enter to START recording…[/]")
            raw_data, measured_rate, elapsed = capture_with_live_ui(
                ser, duration, "Manual Mode", options)
            console.print(
                f"[{TEAL}]Recording complete.[/] Captured"
                f" [{WHITE}]{len(raw_data):,}[/] bytes in"
                f" [{HOT}]{elapsed:.2f}s[/].")

        show_processing_live(raw_data, options,
                             "Manual Mode", measured_rate, elapsed)

    except Exception as exc:
        console.print() # Add a blank line for breathing room
        console.rule(f"[{FAIL}]ERROR[/]", style=FAIL)
        console.print(f"\n[{FAIL}]Serial/processing error:[/] {exc}\n")
        console.input(f"[{GHOST}]Press Enter to return to menu...[/]")
        console.print()
        return_to_menu_countdown(seconds=2)
        console.print()
        console.rule(f"[bold {HOT}][/]")
        console.rule(f"[bold {HOT}]RETURN TO MENU[/]")
        console.rule(f"[bold {HOT}][/]")
        console.print()
        console.print()

# ─────────────────────── DISTANCE MODE ──────────────────────────
def distance_trigger_mode():
    console.rule(f"[bold {HOT}]Distance Trigger Mode[/]")
    options = get_output_preferences()
    while True:
        raw_threshold = console.input(
            f"[{DIM}]Trigger distance cm "
            f"({audio.DISTANCE_TRIGGER_MIN_CM}-{audio.DISTANCE_TRIGGER_MAX_CM}, "
            f"default {audio.DISTANCE_TRIGGER_DEFAULT_CM}):[/] "
        ).strip()
        if raw_threshold == "":
            threshold_cm = audio.DISTANCE_TRIGGER_DEFAULT_CM
            break
        try:
            threshold_cm = int(raw_threshold)
        except ValueError:
            console.print(f"[{FAIL}]Enter a whole number in cm.[/]")
            continue
        if audio.DISTANCE_TRIGGER_MIN_CM <= threshold_cm <= audio.DISTANCE_TRIGGER_MAX_CM:
            break
        console.print(
            f"[{FAIL}]Use {audio.DISTANCE_TRIGGER_MIN_CM}-{audio.DISTANCE_TRIGGER_MAX_CM} cm.[/]"
        )

    console.print(f"\n[{MID}]Recording starts while the ultrasonic sensor is within {threshold_cm} cm.[/]")
    console.print(f"[{GHOST}]Press Ctrl+C to exit distance mode.[/]\n")

    try:
        with audio.serial.Serial(audio.PORT, audio.BAUD, timeout=0.05) as ser:
            ser.reset_input_buffer()
            configured, config_seen = audio.configure_distance_threshold(ser, threshold_cm)
            if configured:
                console.print(f"[{TEAL}]Distance trigger threshold set to {threshold_cm} cm.[/]")
            else:
                console.print(f"[{AMBER}]Warning: distance threshold was not acknowledged.[/]")
                if config_seen:
                    console.print(f"[{GHOST}]Received before distance mode: {config_seen!r}[/]")

            got_ack, seen = audio.send_command_and_wait_for_ack(ser, b"D")
            if got_ack:
                console.print(f"[{TEAL}]Processing STM acknowledged distance mode.[/]")
            else:
                console.print(f"[{AMBER}]Warning: no ACK:D from Processing STM.[/]")

            trigger_num = 0
            while True:
                with console.status(
                        f"[{HOT}]Waiting for proximity trigger…[/]"):
                    first = b""
                    while len(first) < audio.SAMPLE_WIDTH_BYTES:
                        first = ser.read(audio.SAMPLE_WIDTH_BYTES)

                trigger_num += 1
                console.rule(
                    f"[bold {TEAL}]Trigger #{trigger_num} detected[/]")
                chunks = [first]
                rec_start = time.monotonic()
                last_t    = rec_start

                with console.status(
                        f"[{TEAL}]Recording until object leaves {threshold_cm} cm…[/]"):
                    while True:
                        chunk = ser.read(8192)
                        if chunk:
                            chunks.append(chunk); last_t = time.monotonic()
                        else:
                            break

                raw_data = b"".join(chunks)
                elapsed  = max(0.001, last_t - rec_start)
                m_rate   = audio.measured_sample_rate(
                    len(raw_data) // audio.SAMPLE_WIDTH_BYTES, elapsed)
                console.print(
                    f"[{TEAL}]Object left.[/] Captured [{WHITE}]{len(raw_data):,}[/] bytes.")
                show_processing_live(raw_data, options,
                                     f"Distance Trigger {trigger_num}",
                                     m_rate, elapsed)
                console.print()

    except KeyboardInterrupt:
        console.print()
        console.rule(f"[{AMBER}]ABORTED[/]", style=AMBER)
        console.print(f"\n[{AMBER}]Exiting Distance Trigger Mode.[/]\n")
        try:
            with audio.serial.Serial(audio.PORT, audio.BAUD, timeout=1) as ser:
                ser.write(b"S")
        except Exception: pass
        console.input(f"[{GHOST}]Press Enter to return to menu...[/]")
        
    except Exception as exc:
        console.print()
        console.rule(f"[{FAIL}]ERROR[/]", style=FAIL)
        console.print(f"\n[{FAIL}]Serial/processing error:[/] {exc}\n")
        console.input(f"[{GHOST}]Press Enter to return to menu...[/]")
        console.print()
        return_to_menu_countdown(seconds=2)
        console.print()
        console.rule(f"[bold {HOT}][/]")
        console.rule(f"[bold {HOT}]RETURN TO MENU[/]")
        console.rule(f"[bold {HOT}][/]")
        console.print()
        console.print()

# ─────────────────────────── RETURN TO MENU ───────────────────────────
def return_to_menu_countdown(seconds=5):
    """Displays a smooth, auto-erasing countdown bar."""
    console.print() # Add a little breathing room
    
    # Calculate smooth steps (10 frames per second)
    total_steps = seconds * 10 
    
    with Progress(
        TextColumn(f"[{GHOST}]Auto-returning to menu in...[/]"),
        BarColumn(style="grey23", complete_style=DIM),
        TextColumn(f"[{HOT}]{{task.remaining:.1f}}s[/]"),
        console=console,
        transient=True, # 🌟 This makes the bar vanish when finished!
        expand=False
    ) as progress:
        task = progress.add_task("Wait", total=total_steps)
        
        for _ in range(total_steps):
            time.sleep(0.1)
            progress.advance(task)

# ──────────────────────────── MAIN ──────────────────────────────
def main():
    if not RICH_AVAILABLE:
        print("Rich not installed. Falling back to standard CLI.")
        print("pip install rich")
        audio.main(); return

    console.clear()

    # Splash
    frame = 0
    splash = Panel(
        Align.center(Text.from_markup(
            f"\n[bold {HOT}]DUAL-STM AUDIO ACQUISITION SYSTEM[/]\n"
            f"[{GHOST}]v2.0  •  12-bit ADC @ 44.1 kHz[/]\n"
        )),
        border_style=GHOST, box=box.DOUBLE_EDGE, padding=(1, 6))
    console.print(Align.center(splash))
    time.sleep(1.0)
    console.clear()

    while True:
        console.print(render_header(frame))
        frame += 3

        console.print(render_menu_table())
        choice = console.input(
            f"[{DIM}]Enter choice:[/] [{HOT}]>[/] ").strip().lower()

        if choice == "1":
            manual_recording_mode()
        elif choice == "2":
            distance_trigger_mode()
        elif choice == "q":
            try:
                with audio.serial.Serial(audio.PORT, audio.BAUD, timeout=1) as ser:
                    ser.write(b"S")
            except Exception: pass
            console.print(f"\n[{TEAL}]Exiting program. Goodbye![/]")
            break
        else:
            console.print()
            console.rule(f"[{FAIL}]INVALID INPUT[/]", style=FAIL)
            console.print(f"\n[{FAIL}]Please type 1, 2, or q.[/]\n")
            console.print()
            return_to_menu_countdown(seconds=2)


if __name__ == "__main__":
    main()
