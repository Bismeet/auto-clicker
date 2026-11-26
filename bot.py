"""Discord Button Screen-Automation Bot.

Supports:
- Strict Alternating State Machine (Close Combat -> Back To The Future)
- Smart Bottom-Most Visible Mode
- Configurable step delays, jitter, scan intervals, offsets
- Cursor nudge to clear Discord hover highlights
- Windows alert sound & auto-pause on inactivity timeout
- Hotkeys F8 (Toggle Start/Pause) and F9 (Exit)
- PyAutoGUI FailSafe
"""

import argparse
from datetime import datetime
import os
import random
import sys
import threading
import time
from typing import Callable, Optional

import pyautogui
from pynput import keyboard

import config
from config import settings
from vision import ScreenVision, MatchResult


class BotLogger:
    """Central logger with console output and callback dispatch for GUI."""

    def __init__(self):
        self._callbacks = []
        self._lock = threading.Lock()

    def register(self, callback: Callable[[str, str, str], None]):
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def unregister(self, callback: Callable[[str, str, str], None]):
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def log(self, level: str, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lvl = level.upper()
        line = f"[{timestamp}] [{lvl}] {message}"
        print(line, flush=True)

        with self._lock:
            for cb in self._callbacks:
                try:
                    cb(timestamp, lvl, message)
                except Exception:
                    pass


bot_logger = BotLogger()


def log(level: str, message: str):
    bot_logger.log(level, message)


class DiscordMacroBot:
    """Core automation bot controlling scanning, clicking, state machine, and hotkeys."""

    STEP_CLOSE_COMBAT = "close_combat"
    STEP_BACK_TO_THE_FUTURE = "back_to_the_future"

    STATE_PAUSED = "PAUSED"
    STATE_RUNNING = "RUNNING"
    STATE_ALERT = "ALERT"

    def __init__(
        self,
        start_active: bool = False,
        enable_hotkeys: bool = True,
        on_state_change: Optional[Callable[[str], None]] = None,
        on_step_change: Optional[Callable[[str], None]] = None
    ):
        self.vision = ScreenVision(monitor_index=settings.monitor_index)
        pyautogui.FAILSAFE = config.FAILSAFE

        # Bot states
        self.state: str = self.STATE_RUNNING if start_active else self.STATE_PAUSED
        self.current_step: str = self.STEP_CLOSE_COMBAT
        self.exit_requested = threading.Event()
        self.stop_requested = threading.Event()

        # Inactivity tracking
        self.last_button_detected_time: float = time.time()

        # GUI / external notification callbacks
        self.on_state_change = on_state_change
        self.on_step_change = on_step_change

        # Global Hotkey listener
        self.listener: Optional[keyboard.Listener] = None
        if enable_hotkeys:
            self._setup_hotkeys()

    def _setup_hotkeys(self):
        def on_press(key):
            try:
                if key == keyboard.Key.f8:
                    self.toggle_pause()
                elif key == keyboard.Key.f9:
                    self.request_exit("F9 hotkey pressed")
            except Exception as e:
                log("ERROR", f"Error in hotkey handler: {e}")

        self.listener = keyboard.Listener(on_press=on_press)
        self.listener.daemon = True
        self.listener.start()

    def set_state(self, new_state: str):
        if self.state != new_state:
            self.state = new_state
            if self.on_state_change:
                try:
                    self.on_state_change(new_state)
                except Exception:
                    pass

    def set_step(self, new_step: str):
        if self.current_step != new_step:
            self.current_step = new_step
            if self.on_step_change:
                try:
                    self.on_step_change(new_step)
                except Exception:
                    pass

    def reset_step(self):
        """Reset state machine sequence to Step 1 (Close Combat)."""
        self.set_step(self.STEP_CLOSE_COMBAT)
        self.last_button_detected_time = time.time()
        log("INFO", "Sequence reset -> Next: Close Combat")

    def toggle_pause(self):
        if self.state == self.STATE_RUNNING:
            self.set_state(self.STATE_PAUSED)
            log("INFO", ">>> Macro state: PAUSED (Press F8 to resume) <<<")
        else:
            self.last_button_detected_time = time.time()
            self.set_state(self.STATE_RUNNING)
            next_name = "Close Combat" if self.current_step == self.STEP_CLOSE_COMBAT else "Back To The Future"
            log("INFO", f">>> Macro state: RUNNING [Next: {next_name}] <<<")

    def request_exit(self, reason: str = "Exit requested"):
        log("INFO", f"Stopping macro: {reason}")
        self.set_state(self.STATE_PAUSED)
        self.exit_requested.set()
        self.stop_requested.set()

    def nudge_cursor(self, click_x: int, click_y: int):
        """Move cursor off button to clear Discord hover effects."""
        if not settings.nudge_cursor_after_click:
            return

        # Nudge cursor 120-160px horizontally or 50-80px vertically away from button
        dx = random.choice([-1, 1]) * random.randint(120, 160)
        dy = random.choice([-1, 1]) * random.randint(50, 80)

        # Stay safely within monitor bounds and avoid screen corners (pyautogui fail-safe)
        min_x = self.vision.monitor_left + 40
        max_x = self.vision.monitor_left + self.vision.monitor_width - 40
        min_y = self.vision.monitor_top + 40
        max_y = self.vision.monitor_top + self.vision.monitor_height - 40

        nudge_x = max(min_x, min(max_x, click_x + dx))
        nudge_y = max(min_y, min(max_y, click_y + dy))

        try:
            pyautogui.moveTo(nudge_x, nudge_y, duration=random.uniform(0.06, 0.10))
        except Exception:
            pass

    def perform_click(self, label: str, match: MatchResult) -> tuple[int, int]:
        """Click button center with random pixel offset and optionally nudge cursor."""
        if match.x is None or match.y is None:
            return (0, 0)

        offset_px = int(settings.click_offset_px)
        offset_x = random.randint(-offset_px, offset_px)
        offset_y = random.randint(-offset_px, offset_px)
        target_x = match.x + offset_x
        target_y = match.y + offset_y

        matches_info = f" [bottom-most of {match.total_matches} on screen]" if match.total_matches > 1 else ""
        log(
            "CLICK",
            f"Clicking '{label}' at ({target_x}, {target_y}) "
            f"(offset: {offset_x:+d}, {offset_y:+d}){matches_info} "
            f"[final: {match.confidence:.4f}, raw: {match.raw_score:.4f}, diff: {match.color_diff:.1f}, scale: {match.scale}]"
        )

        pyautogui.moveTo(target_x, target_y, duration=random.uniform(0.06, 0.12))
        pyautogui.click()

        # Nudge cursor away if enabled
        if settings.nudge_cursor_after_click:
            self.nudge_cursor(target_x, target_y)

        # Reset inactivity timer
        self.last_button_detected_time = time.time()
        return (target_x, target_y)

    def trigger_inactivity_alert(self, elapsed: float, expected_label: str):
        """Trigger alert beep and auto-pause when expected button is not detected in time."""
        log(
            "WARNING",
            f"Expected button '{expected_label}' not detected for {elapsed:.1f}s "
            f"(>= {settings.inactivity_timeout_sec}s)! Pausing automatically (captcha/shiny/lag)."
        )
        self.set_state(self.STATE_ALERT)

        # Windows alert beep via winsound
        try:
            import winsound
            for _ in range(config.ALERT_BEEP_COUNT):
                winsound.Beep(config.ALERT_BEEP_FREQ, config.ALERT_BEEP_DURATION_MS)
                time.sleep(0.08)
        except Exception as e:
            log("ERROR", f"Failed to play winsound beep: {e}")

        self.last_button_detected_time = time.time()
        log("INFO", "Macro auto-paused by safety timeout. Resolve prompt in Discord and press F8 to resume.")

    def run_tick(self):
        """Execute a single scan tick of the bot loop."""
        now = time.time()

        # Keep monitor updated from settings
        if self.vision.monitor_index != settings.monitor_index:
            try:
                self.vision.set_monitor(settings.monitor_index)
            except Exception as e:
                log("ERROR", f"Failed to switch monitor: {e}")

        frame = self.vision.capture_frame()

        # ----------------- DEBUG MODE -----------------
        if settings.debug_mode:
            res_cc = self.vision.match_template(
                frame, "close_combat", float(settings.confidence_close_combat)
            )
            res_bf = self.vision.match_template(
                frame, "back_to_the_future", float(settings.confidence_back_to_future)
            )

            cc_status = f"MATCH(bottom @ {res_cc.x}, {res_cc.y})" if res_cc.found else "no match"
            bf_status = f"MATCH(bottom @ {res_bf.x}, {res_bf.y})" if res_bf.found else "no match"

            cc_diag = f"raw={res_cc.top_raw:.4f}, diff={res_cc.top_diff:.1f}, final={res_cc.top_final:.4f} at ({res_cc.top_x}, {res_cc.top_y}) [scale={res_cc.top_scale}]"
            bf_diag = f"raw={res_bf.top_raw:.4f}, diff={res_bf.top_diff:.1f}, final={res_bf.top_final:.4f} at ({res_bf.top_x}, {res_bf.top_y}) [scale={res_bf.top_scale}]"

            mode_info = f"Step: {self.current_step}" if settings.mode == "alternating" else "Bottom-Most Mode"
            log(
                "DEBUG",
                f"[{mode_info}] CC: [{cc_status}] {cc_diag} | BF: [{bf_status}] {bf_diag}"
            )

            if res_cc.found or res_bf.found:
                self.last_button_detected_time = now
            else:
                elapsed = now - self.last_button_detected_time
                if elapsed >= float(settings.inactivity_timeout_sec):
                    self.trigger_inactivity_alert(elapsed, "Any Button (Debug)")

            time.sleep(float(settings.scan_interval_sec))
            return

        # ----------------- MODE 1: ALTERNATING (WITH SMART BATTLE RETRY) -----------------
        if settings.mode == "alternating":
            if self.current_step == self.STEP_CLOSE_COMBAT:
                # Step 1: Look for Close Combat
                res = self.vision.match_template(
                    frame, "close_combat", float(settings.confidence_close_combat)
                )
                if res.found:
                    self.perform_click("Close Combat", res)
                    # Advance to Step 2
                    self.set_step(self.STEP_BACK_TO_THE_FUTURE)

                    jitter = random.uniform(-float(settings.delay_jitter_sec), float(settings.delay_jitter_sec))
                    delay = max(0.2, float(settings.step_delay_sec) + jitter)
                    log("WAIT", f"Step 1 complete. Waiting {delay:.2f}s before Step 2 (Back To The Future)...")
                    time.sleep(delay)
                    return

                # If Close Combat not found, check if Back To The Future is on screen (e.g. started on route)
                res_bf_start = self.vision.match_template(
                    frame, "back_to_the_future", float(settings.confidence_back_to_future)
                )
                if res_bf_start.found:
                    self.perform_click("Back To The Future", res_bf_start)
                    self.set_step(self.STEP_CLOSE_COMBAT)
                    jitter = random.uniform(-float(settings.delay_jitter_sec), float(settings.delay_jitter_sec))
                    delay = max(0.2, float(settings.step_delay_sec) + jitter)
                    log("WAIT", f"Route button detected. Clicked Back To The Future. Waiting {delay:.2f}s for battle...")
                    time.sleep(delay)
                    return

                # If neither found: check inactivity timeout
                elapsed = now - self.last_button_detected_time
                if elapsed >= float(settings.inactivity_timeout_sec):
                    self.trigger_inactivity_alert(elapsed, "Close Combat")
                    return

                time.sleep(float(settings.scan_interval_sec))
                return

            else:
                # Step 2: Look for Back To The Future
                res = self.vision.match_template(
                    frame, "back_to_the_future", float(settings.confidence_back_to_future)
                )
                if res.found:
                    self.perform_click("Back To The Future", res)
                    # Return to Step 1
                    self.set_step(self.STEP_CLOSE_COMBAT)

                    jitter = random.uniform(-float(settings.delay_jitter_sec), float(settings.delay_jitter_sec))
                    delay = max(0.2, float(settings.step_delay_sec) + jitter)
                    log("WAIT", f"Battle ended! Clicked Back To The Future. Waiting {delay:.2f}s for next battle...")
                    time.sleep(delay)
                    return

                # Core fix: If Back To The Future is not found, check if Close Combat is still on screen
                # (Wild Pokemon survived hit -> must click Close Combat again until Back To The Future appears)
                res_cc_retry = self.vision.match_template(
                    frame, "close_combat", float(settings.confidence_close_combat)
                )
                if res_cc_retry.found:
                    self.perform_click("Close Combat", res_cc_retry)
                    jitter = random.uniform(-float(settings.delay_jitter_sec), float(settings.delay_jitter_sec))
                    delay = max(0.2, float(settings.step_delay_sec) + jitter)
                    log("WAIT", f"Battle ongoing (no Back To The Future yet). Re-clicked Close Combat. Waiting {delay:.2f}s...")
                    time.sleep(delay)
                    return

                # If neither found: check inactivity timeout
                elapsed = now - self.last_button_detected_time
                if elapsed >= float(settings.inactivity_timeout_sec):
                    self.trigger_inactivity_alert(elapsed, "Back To The Future or Close Combat")
                    return

                time.sleep(float(settings.scan_interval_sec))
                return

        # ----------------- MODE 2: SMART / BOTTOM-MOST VISIBLE (DEFAULT) -----------------
        else:
            # Constantly checks both and clicks whichever appears first / bottom-most
            res_cc = self.vision.match_template(
                frame, "close_combat", float(settings.confidence_close_combat)
            )
            res_bf = self.vision.match_template(
                frame, "back_to_the_future", float(settings.confidence_back_to_future)
            )

            chosen_label = None
            chosen_match = None

            if res_cc.found and res_bf.found:
                # In Discord, higher Y coordinate is the newest/bottom-most message
                if res_bf.y >= res_cc.y:
                    chosen_label = "Back To The Future"
                    chosen_match = res_bf
                    self.set_step(self.STEP_BACK_TO_THE_FUTURE)
                else:
                    chosen_label = "Close Combat"
                    chosen_match = res_cc
                    self.set_step(self.STEP_CLOSE_COMBAT)
            elif res_bf.found:
                chosen_label = "Back To The Future"
                chosen_match = res_bf
                self.set_step(self.STEP_BACK_TO_THE_FUTURE)
            elif res_cc.found:
                chosen_label = "Close Combat"
                chosen_match = res_cc
                self.set_step(self.STEP_CLOSE_COMBAT)

            if chosen_match is not None:
                self.perform_click(chosen_label, chosen_match)
                jitter = random.uniform(-float(settings.delay_jitter_sec), float(settings.delay_jitter_sec))
                delay = max(0.2, float(settings.step_delay_sec) + jitter)
                log("WAIT", f"Clicked {chosen_label}. Waiting {delay:.2f}s for Discord embed to update...")
                time.sleep(delay)
                return

            # If neither found
            elapsed = now - self.last_button_detected_time
            if elapsed >= float(settings.inactivity_timeout_sec):
                self.trigger_inactivity_alert(elapsed, "Either Button (Close Combat / Back To The Future)")
                return

            time.sleep(float(settings.scan_interval_sec))

    def run(self):
        """Run bot loop continuously until exit_requested."""
        log("INFO", "============================================================")
        log("INFO", "       Discord Screen Automation Macro Initialized")
        log("INFO", "============================================================")
        log("INFO", f" Mode        : {settings.mode} (strict sequence)")
        log("INFO", f" Monitor     : Index {settings.monitor_index}")
        log("INFO", f" Hotkeys     : [F8] Toggle Start/Pause | [F9] Exit immediately")
        log("INFO", f" Initial State : {self.state}")
        log("INFO", "============================================================")

        try:
            while not self.exit_requested.is_set():
                if self.state != self.STATE_RUNNING:
                    time.sleep(0.1)
                    continue

                self.run_tick()

        except pyautogui.FailSafeException:
            log("WARNING", "PyAutoGUI FailSafe triggered! Mouse pushed to screen corner. Exiting immediately.")
            self.set_state(self.STATE_PAUSED)
        except KeyboardInterrupt:
            log("INFO", "KeyboardInterrupt detected. Shutting down...")
            self.set_state(self.STATE_PAUSED)
        except Exception as e:
            log("ERROR", f"Unexpected error in main loop: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        log("INFO", "Cleaning up macro resources...")
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        if self.vision:
            try:
                self.vision.close()
            except Exception:
                pass
        log("INFO", "Macro stopped cleanly.")


def main():
    parser = argparse.ArgumentParser(
        description="Discord Button Automation Macro with persistent settings."
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug read-only mode.")
    parser.add_argument(
        "--mode",
        choices=["smart", "bottom_most", "alternating"],
        default=None,
        help="Loop mode: 'smart' (auto battle & route), 'bottom_most', or 'alternating'."
    )
    parser.add_argument("--start-active", action="store_true", help="Start running immediately.")
    args = parser.parse_args()

    if args.debug:
        settings.set("debug_mode", True)
    if args.mode:
        settings.set("mode", args.mode)

    bot = DiscordMacroBot(start_active=args.start_active)
    bot.run()


if __name__ == "__main__":
    main()
