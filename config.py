"""Configuration and persistent settings manager for the Discord button automation clicker."""

from copy import deepcopy
import json
from pathlib import Path
import threading
from typing import Any, Dict

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
SETTINGS_FILE = BASE_DIR / "settings.json"

# Asset Paths
PATH_CLOSE_COMBAT = ASSETS_DIR / "close_combat.png"
PATH_BACK_TO_THE_FUTURE = ASSETS_DIR / "back_to_the_future.png"

# Audio Alert Settings (Windows winsound)
ALERT_BEEP_FREQ = 1000
ALERT_BEEP_DURATION_MS = 400
ALERT_BEEP_COUNT = 3

# Hotkey Controls
HOTKEY_TOGGLE = "F8"
HOTKEY_EXIT = "F9"

# Safety
FAILSAFE = True

# Default persistent settings
DEFAULT_SETTINGS: Dict[str, Any] = {
    "mode": "smart",                    # "smart" (auto battle & route), "alternating", or "bottom_most"
    "step_delay_sec": 1.2,              # Delay after successful click before looking for next button
    "delay_jitter_sec": 0.2,            # Random variation (+/- jitter) added to step_delay
    "scan_interval_sec": 0.25,          # Interval between screen scans when waiting
    "confidence_close_combat": 0.80,    # Template match threshold for Close Combat
    "confidence_back_to_future": 0.80,  # Template match threshold for Back To The Future
    "click_offset_px": 6,               # Random +/- pixel offset from button center
    "inactivity_timeout_sec": 20.0,     # Timeout before auto-pausing with alert beep
    "debug_mode": False,                # Read-only live scoring mode (no clicks)
    "nudge_cursor_after_click": True,   # Move mouse away after click to clear hover highlights
    "monitor_index": 1                  # mss monitor index (1 = primary monitor)
}


class SettingsManager:
    """Thread-safe persistent settings manager backed by settings.json."""

    def __init__(self, filepath: Path = SETTINGS_FILE):
        self._filepath = Path(filepath)
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = deepcopy(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> Dict[str, Any]:
        """Load settings from settings.json, creating it with defaults if missing."""
        with self._lock:
            if not self._filepath.exists():
                self._data = deepcopy(DEFAULT_SETTINGS)
                self._write_file_unlocked(self._data)
                return deepcopy(self._data)

            try:
                with open(self._filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)

                # Ensure all default keys exist
                merged = deepcopy(DEFAULT_SETTINGS)
                if isinstance(loaded, dict):
                    for k, default_val in DEFAULT_SETTINGS.items():
                        if k in loaded:
                            # Cast types according to default_val type
                            try:
                                if isinstance(default_val, bool):
                                    merged[k] = bool(loaded[k])
                                elif isinstance(default_val, int):
                                    merged[k] = int(loaded[k])
                                elif isinstance(default_val, float):
                                    merged[k] = float(loaded[k])
                                elif isinstance(default_val, str):
                                    merged[k] = str(loaded[k])
                                else:
                                    merged[k] = loaded[k]
                            except (ValueError, TypeError):
                                merged[k] = default_val

                self._data = merged
                # Re-save to guarantee complete schema if any keys were missing
                self._write_file_unlocked(self._data)
            except Exception as e:
                # If corrupted, fall back to defaults
                self._data = deepcopy(DEFAULT_SETTINGS)
                self._write_file_unlocked(self._data)

            return deepcopy(self._data)

    def save(self, new_data: Dict[str, Any] = None) -> None:
        """Save settings dictionary to settings.json."""
        with self._lock:
            if new_data is not None:
                # Update known keys with type checking
                for k, default_val in DEFAULT_SETTINGS.items():
                    if k in new_data:
                        val = new_data[k]
                        try:
                            if isinstance(default_val, bool):
                                self._data[k] = bool(val)
                            elif isinstance(default_val, int):
                                self._data[k] = int(val)
                            elif isinstance(default_val, float):
                                self._data[k] = float(val)
                            elif isinstance(default_val, str):
                                self._data[k] = str(val)
                            else:
                                self._data[k] = val
                        except (ValueError, TypeError):
                            pass
            self._write_file_unlocked(self._data)

    def reset_defaults(self) -> Dict[str, Any]:
        """Reset all settings to default values and save to disk."""
        with self._lock:
            self._data = deepcopy(DEFAULT_SETTINGS)
            self._write_file_unlocked(self._data)
            return deepcopy(self._data)

    def _write_file_unlocked(self, data: Dict[str, Any]) -> None:
        try:
            self._filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[SettingsManager] Error saving {self._filepath}: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """Get copy of settings dictionary."""
        with self._lock:
            return deepcopy(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._write_file_unlocked(self._data)

    # Dynamic attribute access for convenience: e.g. settings.step_delay_sec
    def __getattr__(self, name: str) -> Any:
        if name in DEFAULT_SETTINGS:
            with self._lock:
                return self._data.get(name, DEFAULT_SETTINGS[name])
        raise AttributeError(f"'SettingsManager' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        elif name in DEFAULT_SETTINGS:
            self.set(name, value)
        else:
            super().__setattr__(name, value)


# Global singleton settings manager
settings = SettingsManager()

# Backward-compatibility properties
CONFIDENCE_THRESHOLD = settings.confidence_close_combat
CONFIDENCE_CLOSE_COMBAT = settings.confidence_close_combat
CONFIDENCE_BACK_TO_THE_FUTURE = settings.confidence_back_to_future
MONITOR_INDEX = settings.monitor_index
