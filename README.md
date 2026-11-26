# Discord Screen-Automation Macro & GUI

A Python desktop macro designed to detect and click Discord embed buttons using OpenCV color template matching, `mss`, `pyautogui`, `pynput`, and a dark-themed **CustomTkinter GUI**.

---

## What's New

### 1. Loop Logic Fix (Strict Alternating Sequence & Smart Modes)
- **Strict Alternating State Machine (`mode = "alternating"`, default)**:
  - **Step 1**: Looks **only** for the bottom-most `assets/close_combat.png` → clicks it → waits `step_delay` (`1.5s` ± jitter) → advances to Step 2.
  - **Step 2**: Looks **only** for the bottom-most `assets/back_to_the_future.png` → clicks it → waits `step_delay` (`1.5s` ± jitter) → returns to Step 1.
  - *Fixes the issue where older `Close Combat` buttons higher up in chat stayed at 1.0000 confidence and hijacked Priority 1.*
- **Bottom-Most Visible Mode (`mode = "bottom_most"`)**:
  - Scans both templates on screen and clicks whichever match has the highest Y-coordinate (the lowest/most recent message on screen).
- **Cursor Nudge / Hover Fix**:
  - Automatically nudges the mouse slightly off the button after clicking so Discord's hover highlights and tooltips do not interfere with subsequent template matches.
- **Inactivity Timeout**:
  - If the expected button isn't detected for 20 seconds, automatically pauses the bot and plays a Windows alert beep via `winsound`.

### 2. Persistent Settings (`settings.json`)
All settings auto-create with defaults on first launch and persist across sessions:
- `mode`: `"alternating"` or `"bottom_most"`
- `step_delay_sec`: default `1.5`
- `delay_jitter_sec`: default `0.2`
- `scan_interval_sec`: default `0.3`
- `confidence_close_combat`: default `0.85`
- `confidence_back_to_future`: default `0.85`
- `click_offset_px`: default `6` (±6px random offset)
- `inactivity_timeout_sec`: default `20.0`
- `debug_mode`: default `false` (read-only live scores without clicking)
- `nudge_cursor_after_click`: default `true`
- `monitor_index`: default `1`

### 3. CustomTkinter Desktop GUI (`gui.py` / `app.py`)
- **Status Bar**: Real-time state badge (`PAUSED` / `RUNNING` / `ALERT`), current expected step (`Next: Close Combat` / `Next: Back To The Future`), Start/Pause [F8], Reset Step, **🔍 Test Screen Now**, and Exit [F9] buttons.
- **🔍 Test Screen Now**: Instantly captures a screenshot (even while paused) and logs the top `raw_score`, `color_diff`, `final_score`, and `(x, y)` coordinates for both templates to diagnose detection without clicking.
- **Inner Cropping & Multi-Scale Vision**: Trims 6px from template borders to remove outer rounded corner background pixels and automatically matches across scales (including normalized height scale) so different Discord zooms match reliably.
- **Settings Panel**: Sliders, inputs, and toggles for all settings. Includes **Save Settings** (applies immediately in real time without restart) and **Reset Defaults**.
- **Live Activity Logs**: Dark-themed scrollable console displaying timestamped detection scores, clicks, waits, and alerts.
- **Always on Top**: Toggleable switch to keep the GUI floating alongside Discord.

---

## Quick Start

### 1. Launch the GUI
```powershell
.\.venv\Scripts\python.exe gui.py
```
*(or `.\.venv\Scripts\python.exe app.py`)*

### 2. Hotkeys (Global)
- **`F8`**: Toggle Start / Pause (synced with GUI button)
- **`F9`**: Exit immediately (synced with GUI button)
- **PyAutoGUI FailSafe**: Slam cursor into any corner of the screen for emergency exit.

### 3. CLI Mode (Headless / Terminal)
You can still run the bot directly in the terminal if preferred:
```powershell
.\.venv\Scripts\python.exe bot.py
```
Or in read-only debug mode:
```powershell
.\.venv\Scripts\python.exe bot.py --debug
```

### 4. Running Tests
```powershell
.\.venv\Scripts\python.exe test_macro.py
```
