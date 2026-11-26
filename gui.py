"""CustomTkinter GUI application for Discord Screen-Automation Clicker."""

import sys
import threading
import time
from typing import Optional

import customtkinter as ctk

import config
from config import settings, DEFAULT_SETTINGS
from bot import DiscordMacroBot, bot_logger, log


class MacroApp(ctk.CTk):
    """Main desktop GUI window managing bot lifecycle, live logs, and persistent settings."""

    def __init__(self):
        super().__init__()

        # Window configuration
        self.title("Discord Macro Clicker")
        self.geometry("580x820")
        self.minsize(520, 680)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Bot instance and thread
        self.bot = DiscordMacroBot(
            start_active=False,
            enable_hotkeys=True,
            on_state_change=self._on_bot_state_change,
            on_step_change=self._on_bot_step_change
        )

        # Thread for bot loop
        self.bot_thread = threading.Thread(target=self.bot.run, daemon=True)
        self.bot_thread.start()

        # Build UI layout
        self._build_header()
        self._build_status_bar()
        self._build_settings_panel()
        self._build_console_box()

        # Connect log dispatcher to UI
        bot_logger.register(self._append_log)

        # Initialize UI values with loaded settings
        self._load_settings_into_ui()
        self._update_status_display()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Periodic status sync
        self.after(200, self._poll_bot_status)

    def _build_header(self):
        """Top title and Always-on-Top switch."""
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(12, 4))

        title_label = ctk.CTkLabel(
            header_frame,
            text="⚡ Discord Macro Clicker",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(side="left")

        self.topmost_var = ctk.BooleanVar(value=False)
        self.attributes("-topmost", False)

        def toggle_topmost():
            self.attributes("-topmost", self.topmost_var.get())

        topmost_switch = ctk.CTkSwitch(
            header_frame,
            text="Always on Top",
            variable=self.topmost_var,
            command=toggle_topmost,
            font=ctk.CTkFont(size=12)
        )
        topmost_switch.pack(side="right")

    def _build_status_bar(self):
        """Live badges and primary control buttons."""
        status_card = ctk.CTkFrame(self, corner_radius=10)
        status_card.pack(fill="x", padx=16, pady=8)

        # Badges row
        badge_row = ctk.CTkFrame(status_card, fg_color="transparent")
        badge_row.pack(fill="x", padx=12, pady=(10, 6))

        self.state_badge = ctk.CTkLabel(
            badge_row,
            text="PAUSED",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
            fg_color="#D97706",  # Amber for paused
            corner_radius=6,
            width=110,
            height=28
        )
        self.state_badge.pack(side="left", padx=(0, 8))

        self.step_badge = ctk.CTkLabel(
            badge_row,
            text="Next: Close Combat",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
            fg_color="#2563EB",  # Blue
            corner_radius=6,
            height=28
        )
        self.step_badge.pack(side="left", fill="x", expand=True)

        # Control buttons row
        btn_row = ctk.CTkFrame(status_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(6, 10))

        self.start_pause_btn = ctk.CTkButton(
            btn_row,
            text="Start [F8]",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#10B981",  # Green
            hover_color="#059669",
            command=self._toggle_start_pause,
            height=32
        )
        self.start_pause_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.reset_step_btn = ctk.CTkButton(
            btn_row,
            text="Reset Step",
            font=ctk.CTkFont(size=12),
            fg_color="#374151",
            hover_color="#4B5563",
            command=self._reset_step,
            width=82,
            height=32
        )
        self.reset_step_btn.pack(side="left", padx=3)

        self.test_screen_btn = ctk.CTkButton(
            btn_row,
            text="🔍 Test Screen",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#4F46E5",  # Indigo
            hover_color="#4338CA",
            command=self._test_screen_now,
            width=105,
            height=32
        )
        self.test_screen_btn.pack(side="left", padx=3)

        self.exit_btn = ctk.CTkButton(
            btn_row,
            text="Exit [F9]",
            font=ctk.CTkFont(size=12),
            fg_color="#DC2626",  # Red
            hover_color="#B91C1C",
            command=self._on_close,
            width=75,
            height=32
        )
        self.exit_btn.pack(side="right", padx=(3, 0))

    def _build_settings_panel(self):
        """Scrollable configuration panel mapping to settings.json."""
        container = ctk.CTkFrame(self, corner_radius=10)
        container.pack(fill="both", expand=True, padx=16, pady=4)

        header_row = ctk.CTkFrame(container, fg_color="transparent")
        header_row.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            header_row,
            text="⚙ Settings (settings.json)",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")

        self.save_feedback_label = ctk.CTkLabel(
            header_row,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#10B981"
        )
        self.save_feedback_label.pack(side="right")

        self.scroll_settings = ctk.CTkScrollableFrame(container, height=270, fg_color="transparent")
        self.scroll_settings.pack(fill="both", expand=True, padx=8, pady=4)

        # 1. Mode selector
        self._add_section_label("Execution Mode")
        self.mode_var = ctk.StringVar(value=settings.mode)
        mode_frame = ctk.CTkFrame(self.scroll_settings, fg_color="transparent")
        mode_frame.pack(fill="x", pady=2)

        self.mode_seg = ctk.CTkSegmentedButton(
            mode_frame,
            values=["Smart Auto (Recommended)", "Strict Alternating"],
            command=self._on_mode_changed
        )
        self.mode_seg.set("Strict Alternating" if settings.mode == "alternating" else "Smart Auto (Recommended)")
        self.mode_seg.pack(fill="x", expand=True)

        # 2. Timing Sliders
        self._add_section_label("Timings & Delays")
        self.step_delay_slider, self.step_delay_lbl = self._create_slider_row(
            "Step Delay (sec):", 0.5, 4.0, settings.step_delay_sec, "{:.1f}s", resolution=0.1
        )
        self.jitter_slider, self.jitter_lbl = self._create_slider_row(
            "Delay Jitter (sec):", 0.0, 0.8, settings.delay_jitter_sec, "±{:.2f}s", resolution=0.05
        )
        self.scan_slider, self.scan_lbl = self._create_slider_row(
            "Scan Interval (sec):", 0.1, 1.0, settings.scan_interval_sec, "{:.2f}s", resolution=0.05
        )
        self.timeout_slider, self.timeout_lbl = self._create_slider_row(
            "Inactivity Alert Timeout (sec):", 5.0, 45.0, settings.inactivity_timeout_sec, "{:.0f}s", resolution=1.0
        )

        # 3. Detection Confidence Sliders
        self._add_section_label("Confidence Thresholds")
        self.conf_cc_slider, self.conf_cc_lbl = self._create_slider_row(
            "Close Combat Conf:", 0.60, 0.99, settings.confidence_close_combat, "{:.2f}", resolution=0.01
        )
        self.conf_bf_slider, self.conf_bf_lbl = self._create_slider_row(
            "Back To The Future Conf:", 0.60, 0.99, settings.confidence_back_to_future, "{:.2f}", resolution=0.01
        )

        # 4. Human-like Offsets & Monitor
        self._add_section_label("Clicking & Hardware")
        self.offset_slider, self.offset_lbl = self._create_slider_row(
            "Click Random Offset (px):", 0, 15, settings.click_offset_px, "±{:.0f}px", resolution=1.0
        )

        mon_row = ctk.CTkFrame(self.scroll_settings, fg_color="transparent")
        mon_row.pack(fill="x", pady=2)
        ctk.CTkLabel(mon_row, text="Monitor Index:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.monitor_var = ctk.StringVar(value=str(settings.monitor_index))
        self.monitor_menu = ctk.CTkOptionMenu(
            mon_row,
            values=["0", "1", "2", "3"],
            variable=self.monitor_var,
            width=90,
            height=26
        )
        self.monitor_menu.pack(side="right")

        # 5. Switches
        self._add_section_label("Behaviors")
        self.nudge_var = ctk.BooleanVar(value=settings.nudge_cursor_after_click)
        self.nudge_switch = ctk.CTkSwitch(
            self.scroll_settings,
            text="Nudge cursor away after click (clears Discord hover)",
            variable=self.nudge_var,
            font=ctk.CTkFont(size=12)
        )
        self.nudge_switch.pack(anchor="w", pady=4)

        self.debug_var = ctk.BooleanVar(value=settings.debug_mode)
        self.debug_switch = ctk.CTkSwitch(
            self.scroll_settings,
            text="Debug Mode (read-only live scores, no clicking)",
            variable=self.debug_var,
            font=ctk.CTkFont(size=12)
        )
        self.debug_switch.pack(anchor="w", pady=4)

        # Settings buttons row
        actions_row = ctk.CTkFrame(container, fg_color="transparent")
        actions_row.pack(fill="x", padx=12, pady=(6, 8))

        save_btn = ctk.CTkButton(
            actions_row,
            text="💾 Save Settings",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self._save_settings,
            height=30
        )
        save_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        reset_defaults_btn = ctk.CTkButton(
            actions_row,
            text="Reset Defaults",
            font=ctk.CTkFont(size=12),
            fg_color="#4B5563",
            hover_color="#374151",
            command=self._reset_defaults,
            width=110,
            height=30
        )
        reset_defaults_btn.pack(side="right")

    def _build_console_box(self):
        """Scrollable read-only live console log viewer."""
        console_frame = ctk.CTkFrame(self, corner_radius=10)
        console_frame.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        header_row = ctk.CTkFrame(console_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=12, pady=(6, 4))

        ctk.CTkLabel(
            header_row,
            text="📜 Live Activity Logs",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left")

        clear_btn = ctk.CTkButton(
            header_row,
            text="Clear",
            font=ctk.CTkFont(size=11),
            width=50,
            height=22,
            fg_color="#374151",
            hover_color="#4B5563",
            command=self._clear_logs
        )
        clear_btn.pack(side="right")

        self.log_textbox = ctk.CTkTextbox(
            console_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word",
            fg_color="#111827",
            text_color="#E5E7EB"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log_textbox.configure(state="disabled")

    def _add_section_label(self, title: str):
        lbl = ctk.CTkLabel(
            self.scroll_settings,
            text=title.upper(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#9CA3AF"
        )
        lbl.pack(anchor="w", pady=(8, 2))

    def _create_slider_row(self, label_text: str, from_: float, to: float, current_val: float, val_fmt: str, resolution: float = 0.1):
        row = ctk.CTkFrame(self.scroll_settings, fg_color="transparent")
        row.pack(fill="x", pady=2)

        lbl = ctk.CTkLabel(row, text=label_text, font=ctk.CTkFont(size=12), width=180, anchor="w")
        lbl.pack(side="left")

        val_lbl = ctk.CTkLabel(row, text=val_fmt.format(current_val), font=ctk.CTkFont(size=12, weight="bold"), width=60)
        val_lbl.pack(side="right")

        def on_slider_move(val):
            val_lbl.configure(text=val_fmt.format(val))

        # Calculate number of steps for discrete resolution
        steps = int(round((to - from_) / resolution))
        slider = ctk.CTkSlider(
            row,
            from_=from_,
            to=to,
            number_of_steps=steps,
            command=on_slider_move,
            height=16
        )
        slider.set(current_val)
        slider.pack(side="left", fill="x", expand=True, padx=6)

        return slider, val_lbl

    def _on_mode_changed(self, choice: str):
        mode_val = "alternating" if choice == "Strict Alternating" else "smart"
        settings.set("mode", mode_val)
        self._update_status_display()
        log("INFO", f"Switched mode to '{mode_val}'")

    def _load_settings_into_ui(self):
        """Populate UI controls from config.settings."""
        self.mode_seg.set("Strict Alternating" if settings.mode == "alternating" else "Smart Auto (Recommended)")
        self.step_delay_slider.set(settings.step_delay_sec)
        self.step_delay_lbl.configure(text=f"{settings.step_delay_sec:.1f}s")

        self.jitter_slider.set(settings.delay_jitter_sec)
        self.jitter_lbl.configure(text=f"±{settings.delay_jitter_sec:.2f}s")

        self.scan_slider.set(settings.scan_interval_sec)
        self.scan_lbl.configure(text=f"{settings.scan_interval_sec:.2f}s")

        self.timeout_slider.set(settings.inactivity_timeout_sec)
        self.timeout_lbl.configure(text=f"{settings.inactivity_timeout_sec:.0f}s")

        self.conf_cc_slider.set(settings.confidence_close_combat)
        self.conf_cc_lbl.configure(text=f"{settings.confidence_close_combat:.2f}")

        self.conf_bf_slider.set(settings.confidence_back_to_future)
        self.conf_bf_lbl.configure(text=f"{settings.confidence_back_to_future:.2f}")

        self.offset_slider.set(settings.click_offset_px)
        self.offset_lbl.configure(text=f"±{settings.click_offset_px:.0f}px")

        self.monitor_var.set(str(settings.monitor_index))
        self.nudge_var.set(settings.nudge_cursor_after_click)
        self.debug_var.set(settings.debug_mode)

    def _save_settings(self):
        """Collect UI inputs and save to settings.json, applying immediately."""
        mode_val = "alternating" if self.mode_seg.get() == "Strict Alternating" else "smart"
        updated = {
            "mode": mode_val,
            "step_delay_sec": round(float(self.step_delay_slider.get()), 2),
            "delay_jitter_sec": round(float(self.jitter_slider.get()), 2),
            "scan_interval_sec": round(float(self.scan_slider.get()), 2),
            "inactivity_timeout_sec": round(float(self.timeout_slider.get()), 1),
            "confidence_close_combat": round(float(self.conf_cc_slider.get()), 2),
            "confidence_back_to_future": round(float(self.conf_bf_slider.get()), 2),
            "click_offset_px": int(round(self.offset_slider.get())),
            "monitor_index": int(self.monitor_var.get()),
            "nudge_cursor_after_click": bool(self.nudge_var.get()),
            "debug_mode": bool(self.debug_var.get())
        }

        settings.save(updated)
        self._update_status_display()

        # Temporary visual confirmation
        self.save_feedback_label.configure(text="✓ Saved & Applied!")
        self.after(2000, lambda: self.save_feedback_label.configure(text=""))
        log("INFO", f"Settings saved to settings.json: mode={mode_val}, debug={settings.debug_mode}")

    def _reset_defaults(self):
        """Reset settings to default and refresh UI."""
        settings.reset_defaults()
        self._load_settings_into_ui()
        self._update_status_display()
        self.save_feedback_label.configure(text="✓ Reset to Defaults!")
        self.after(2000, lambda: self.save_feedback_label.configure(text=""))
        log("INFO", "Settings reset to default values.")

    def _toggle_start_pause(self):
        self.bot.toggle_pause()
        self._update_status_display()

    def _reset_step(self):
        self.bot.reset_step()
        self._update_status_display()

    def _test_screen_now(self):
        """Capture one screenshot and log detailed diagnostic scores for both buttons in a worker thread."""
        def _do_test():
            log("INFO", f"=== [TEST SCREEN] Manual Inspection (Monitor {settings.monitor_index}) ===")
            try:
                frame = self.bot.vision.capture_frame()
                res_cc = self.bot.vision.match_template(
                    frame, "close_combat", float(settings.confidence_close_combat)
                )
                res_bf = self.bot.vision.match_template(
                    frame, "back_to_the_future", float(settings.confidence_back_to_future)
                )

                cc_tag = f"MATCH (conf={res_cc.confidence:.4f}, bottom @ {res_cc.x}, {res_cc.y})" if res_cc.found else "NO MATCH"
                bf_tag = f"MATCH (conf={res_bf.confidence:.4f}, bottom @ {res_bf.x}, {res_bf.y})" if res_bf.found else "NO MATCH"

                log(
                    "INFO",
                    f"Close Combat       : [{cc_tag}] raw_score={res_cc.top_raw:.4f}, color_diff={res_cc.top_diff:.1f}, "
                    f"final_score={res_cc.top_final:.4f} at ({res_cc.top_x}, {res_cc.top_y}) [scale={res_cc.top_scale}]"
                )
                log(
                    "INFO",
                    f"Back To The Future : [{bf_tag}] raw_score={res_bf.top_raw:.4f}, color_diff={res_bf.top_diff:.1f}, "
                    f"final_score={res_bf.top_final:.4f} at ({res_bf.top_x}, {res_bf.top_y}) [scale={res_bf.top_scale}]"
                )
                log(
                    "INFO",
                    f"Active Thresholds  : CC: {settings.confidence_close_combat:.2f} | BF: {settings.confidence_back_to_future:.2f} | "
                    f"Expected Step: {self.bot.current_step} | State: {self.bot.state}"
                )
            except Exception as e:
                log("ERROR", f"Screen test failed: {e}")

        threading.Thread(target=_do_test, daemon=True).start()

    def _on_bot_state_change(self, new_state: str):
        self.after(0, self._update_status_display)

    def _on_bot_step_change(self, new_step: str):
        self.after(0, self._update_status_display)

    def _poll_bot_status(self):
        """Periodic sync to catch state changes from hotkeys (F8/F9)."""
        self._update_status_display()
        if not self.bot.exit_requested.is_set():
            self.after(300, self._poll_bot_status)
        else:
            self._on_close()

    def _update_status_display(self):
        state = self.bot.state

        # Update Badge Color and Text
        if state == DiscordMacroBot.STATE_RUNNING:
            self.state_badge.configure(text="RUNNING", fg_color="#10B981")
            self.start_pause_btn.configure(text="Pause [F8]", fg_color="#D97706", hover_color="#B45309")
        elif state == DiscordMacroBot.STATE_ALERT:
            self.state_badge.configure(text="ALERT", fg_color="#DC2626")
            self.start_pause_btn.configure(text="Resume [F8]", fg_color="#10B981", hover_color="#059669")
        else:
            self.state_badge.configure(text="PAUSED", fg_color="#D97706")
            self.start_pause_btn.configure(text="Start [F8]", fg_color="#10B981", hover_color="#059669")

        # Update Step Indicator
        if settings.mode == "alternating":
            if self.bot.current_step == DiscordMacroBot.STEP_CLOSE_COMBAT:
                self.step_badge.configure(text="Alternating: Next CC", fg_color="#4B5563")
            else:
                self.step_badge.configure(text="Alternating: Next BF", fg_color="#2563EB")
        else:
            step_text = "In Battle (CC)" if self.bot.current_step == DiscordMacroBot.STEP_CLOSE_COMBAT else "On Route (BF)"
            self.step_badge.configure(text=f"Smart Auto: {step_text}", fg_color="#7C3AED")

    def _append_log(self, timestamp: str, level: str, message: str):
        def _do_append():
            try:
                self.log_textbox.configure(state="normal")
                # Highlight level
                line = f"[{timestamp}] [{level}] {message}\n"
                self.log_textbox.insert("end", line)
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")
            except Exception:
                pass

        self.after(0, _do_append)

    def _clear_logs(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def _on_close(self):
        """Clean shutdown of bot and window."""
        try:
            bot_logger.unregister(self._append_log)
            self.bot.request_exit("Window closed")
        except Exception:
            pass
        self.destroy()


def main():
    app = MacroApp()
    app.mainloop()


if __name__ == "__main__":
    main()
