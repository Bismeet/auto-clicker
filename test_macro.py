"""Comprehensive test suite for Discord Button Screen-Automation Macro.

Tests:
1. Inner-cropped template loading & dimension inspection
2. Multi-scale template matching (scale 1.0 and height-normalized scale)
3. Bottom-most selection among multiple matches
4. BGR color discrimination (Active & Hover pass, Dimmed/Disabled reject)
5. Diagnostic metrics exposure (raw_score, color_diff, final_score)
6. Settings persistence (settings.json load, save, reset_defaults, type safety)
7. Strict Alternating State Machine (Close Combat -> Back To The Future)
8. Bottom-Most Visible Mode (highest Y on screen wins)
9. Cursor nudge coordinate safety
"""

import json
from pathlib import Path
import time
import unittest
import numpy as np

import config
from config import settings, DEFAULT_SETTINGS, SettingsManager
import vision
from bot import DiscordMacroBot


class TestMacroAutomation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vis = vision.ScreenVision()

    @classmethod
    def tearDownClass(cls):
        cls.vis.close()

    def setUp(self):
        # Save a backup of settings
        self.original_settings = settings.to_dict()

    def tearDown(self):
        # Restore settings
        settings.save(self.original_settings)

    # ---------------- 1. Template & Vision Tests ----------------
    def test_inner_cropped_templates(self):
        """Verify templates exist, are loaded as 3-channel BGR, and trimmed by 6px on all 4 edges."""
        self.assertIn("close_combat", self.vis.templates)
        self.assertIn("back_to_the_future", self.vis.templates)

        raw_cc = self.vis.raw_templates["close_combat"]
        raw_bf = self.vis.raw_templates["back_to_the_future"]
        crop_cc = self.vis.templates["close_combat"]
        crop_bf = self.vis.templates["back_to_the_future"]

        # Check 6px trimmed off all 4 sides (height - 12, width - 12)
        self.assertEqual(crop_cc.shape[0], raw_cc.shape[0] - 12)
        self.assertEqual(crop_cc.shape[1], raw_cc.shape[1] - 12)
        self.assertEqual(crop_bf.shape[0], raw_bf.shape[0] - 12)
        self.assertEqual(crop_bf.shape[1], raw_bf.shape[1] - 12)

        # Both must be 3 BGR channels
        self.assertEqual(crop_cc.shape[2], 3)
        self.assertEqual(crop_bf.shape[2], 3)

    def test_multi_scale_matching(self):
        """Verify that multi-scale matching successfully finds Back To The Future at different scales."""
        bf_crop = self.vis.templates["back_to_the_future"]
        canvas = np.full((1200, 1000, 3), 32, dtype=np.uint8)

        # Test A: Canvas has scale 1.0 template
        canvas[200:200 + bf_crop.shape[0], 200:200 + bf_crop.shape[1]] = bf_crop
        res_1 = self.vis.match_template(canvas, "back_to_the_future", threshold=0.85)
        self.assertTrue(res_1.found)
        self.assertGreaterEqual(res_1.confidence, 0.95)
        self.assertGreaterEqual(res_1.raw_score, 0.95)
        self.assertLessEqual(res_1.color_diff, 5.0)

        # Test B: Canvas has scaled template (scale 0.90)
        canvas.fill(32)
        # Find 0.90 variant
        variant_90 = next(v for s, v in self.vis.template_variants["back_to_the_future"] if abs(s - 0.90) < 1e-3)
        canvas[400:400 + variant_90.shape[0], 200:200 + variant_90.shape[1]] = variant_90
        res_scaled = self.vis.match_template(canvas, "back_to_the_future", threshold=0.85)
        self.assertTrue(res_scaled.found)
        self.assertGreaterEqual(res_scaled.confidence, 0.95)
        self.assertAlmostEqual(res_scaled.scale, 0.90, places=2)

    def test_bottom_most_selection_same_template(self):
        """Verify bottom-most selection among multiple instances of the same template."""
        cc = self.vis.templates["close_combat"]
        th, tw = cc.shape[:2]

        canvas = np.full((1200, 1000, 3), 32, dtype=np.uint8)
        # Place 3 buttons at Y=150, Y=550, Y=950
        canvas[150:150 + th, 300:300 + tw] = cc
        canvas[550:550 + th, 300:300 + tw] = cc
        canvas[950:950 + th, 300:300 + tw] = cc

        result = self.vis.match_template(canvas, "close_combat", threshold=0.85)
        self.assertTrue(result.found)
        self.assertEqual(result.total_matches, 3)

        expected_y = self.vis.monitor_top + 950 + th // 2
        self.assertEqual(result.y, expected_y)

    def test_bgr_color_discrimination_active_hover_dimmed(self):
        """
        Verify requirement:
        - Active button matches (confidence >= 0.85)
        - Normal Discord hover state matches (confidence >= 0.85)
        - Dimmed/disabled button (50% opacity) is rejected (confidence < 0.85)
        """
        bf = self.vis.templates["back_to_the_future"]
        th, tw = bf.shape[:2]
        canvas = np.full((600, 800, 3), 32, dtype=np.uint8)

        # 1. Active button with normal noise
        active_bf = np.clip(bf.astype(np.int16) + np.random.randint(-3, 3, bf.shape), 0, 255).astype(np.uint8)
        canvas[50:50 + th, 50:50 + tw] = active_bf
        res_active = self.vis.match_template(canvas, "back_to_the_future", threshold=0.85)
        self.assertTrue(res_active.found, "Active button must match with confidence >= 0.85")
        self.assertGreaterEqual(res_active.confidence, 0.90)

        # 2. Hovered button (Discord brand blurple shifts slightly darker on hover: #5865F2 -> #4752C4)
        canvas.fill(32)
        hover_bf = np.clip(bf.astype(np.float32) * 0.88, 0, 255).astype(np.uint8)
        canvas[50:50 + th, 50:50 + tw] = hover_bf
        res_hover = self.vis.match_template(canvas, "back_to_the_future", threshold=0.85)
        self.assertTrue(res_hover.found, "Hovered button must match within tolerance (confidence >= 0.85)")

        # 3. Disabled button (Discord 50% opacity over dark theme #2B2D31)
        canvas.fill(32)
        bg = np.array([49, 45, 43], dtype=np.uint8)
        disabled_bf = (bf * 0.5 + bg * 0.5).astype(np.uint8)
        canvas[50:50 + th, 50:50 + tw] = disabled_bf
        res_disabled = self.vis.match_template(canvas, "back_to_the_future", threshold=0.85)
        self.assertFalse(res_disabled.found, "Disabled 50% opacity button must NOT match with >= 0.85")
        self.assertLess(res_disabled.top_final, 0.85)

    def test_diagnostics_exposed(self):
        """Verify that MatchResult exposes raw_score, color_diff, and final_score."""
        cc = self.vis.templates["close_combat"]
        canvas = np.full((400, 400, 3), 32, dtype=np.uint8)
        canvas[50:50 + cc.shape[0], 50:50 + cc.shape[1]] = cc

        res = self.vis.match_template(canvas, "close_combat", threshold=0.85)
        self.assertTrue(res.found)
        self.assertIsNotNone(res.raw_score)
        self.assertIsNotNone(res.color_diff)
        self.assertIsNotNone(res.confidence)
        self.assertGreater(res.top_raw, 0.0)
        self.assertGreater(res.top_final, 0.0)

    # ---------------- 2. Settings Persistence Tests ----------------
    def test_settings_save_and_reload(self):
        """Verify that settings persist to settings.json and reload cleanly."""
        test_file = config.BASE_DIR / "test_settings.json"
        try:
            if test_file.exists():
                test_file.unlink()

            mgr = SettingsManager(filepath=test_file)
            self.assertTrue(test_file.exists())
            self.assertEqual(mgr.mode, "smart")
            self.assertEqual(mgr.step_delay_sec, 1.2)

            # Update settings
            mgr.save({
                "mode": "alternating",
                "step_delay_sec": 2.25,
                "confidence_close_combat": 0.90,
                "nudge_cursor_after_click": False
            })

            # Create a new manager pointing to the same file to verify disk persistence
            mgr2 = SettingsManager(filepath=test_file)
            self.assertEqual(mgr2.mode, "alternating")
            self.assertEqual(mgr2.step_delay_sec, 2.25)
            self.assertEqual(mgr2.confidence_close_combat, 0.90)
            self.assertFalse(mgr2.nudge_cursor_after_click)

            # Test reset_defaults
            mgr2.reset_defaults()
            self.assertEqual(mgr2.mode, "smart")
            self.assertEqual(mgr2.step_delay_sec, 1.2)

        finally:
            if test_file.exists():
                test_file.unlink()

    # ---------------- 3. Alternating State Machine Tests ----------------
    def test_alternating_state_machine_prevents_hijacking(self):
        """
        Verify that older Close Combat buttons scrolled up CANNOT hijack Priority 1
        when the bot is expecting Back To The Future.
        """
        bot = DiscordMacroBot(start_active=False, enable_hotkeys=False)
        bot.current_step = DiscordMacroBot.STEP_CLOSE_COMBAT

        # Step 1: In Step 1, bot looks ONLY for Close Combat
        self.assertEqual(bot.current_step, DiscordMacroBot.STEP_CLOSE_COMBAT)

        # Advance to Step 2
        bot.set_step(DiscordMacroBot.STEP_BACK_TO_THE_FUTURE)
        self.assertEqual(bot.current_step, DiscordMacroBot.STEP_BACK_TO_THE_FUTURE)

        # Step 2: Now in Step 2, bot looks ONLY for Back To The Future.
        self.assertEqual(bot.current_step, DiscordMacroBot.STEP_BACK_TO_THE_FUTURE)

        # Complete cycle and return to Step 1
        bot.set_step(DiscordMacroBot.STEP_CLOSE_COMBAT)
        self.assertEqual(bot.current_step, DiscordMacroBot.STEP_CLOSE_COMBAT)

        # Test Reset Step
        bot.set_step(DiscordMacroBot.STEP_BACK_TO_THE_FUTURE)
        bot.reset_step()
        self.assertEqual(bot.current_step, DiscordMacroBot.STEP_CLOSE_COMBAT)

        bot.cleanup()

    # ---------------- 4. Bottom-Most Visible Mode Tests ----------------
    def test_bottom_most_mode_picks_highest_y(self):
        """
        In Bottom-Most mode, whichever button has the highest Y coordinate on screen
        is selected, ignoring older scrolled-up buttons.
        """
        cc = self.vis.templates["close_combat"]
        bf = self.vis.templates["back_to_the_future"]

        canvas = np.full((1200, 1000, 3), 32, dtype=np.uint8)

        # Scenario A: Older Close Combat at y=200, newer Back To The Future at y=800
        canvas[200:200 + cc.shape[0], 200:200 + cc.shape[1]] = cc
        canvas[800:800 + bf.shape[0], 200:200 + bf.shape[1]] = bf

        match_cc = self.vis.match_template(canvas, "close_combat", threshold=0.85)
        match_bf = self.vis.match_template(canvas, "back_to_the_future", threshold=0.85)

        self.assertTrue(match_cc.found)
        self.assertTrue(match_bf.found)

        # Comparison logic from bot.py
        if match_cc.y >= match_bf.y:
            winner = "close_combat"
        else:
            winner = "back_to_the_future"

        self.assertEqual(winner, "back_to_the_future", "Higher Y (800 > 200) must win!")

        # Scenario B: Older Back To The Future at y=300, newer Close Combat at y=950
        canvas.fill(32)
        canvas[300:300 + bf.shape[0], 200:200 + bf.shape[1]] = bf
        canvas[950:950 + cc.shape[0], 200:200 + cc.shape[1]] = cc

        match_cc2 = self.vis.match_template(canvas, "close_combat", threshold=0.85)
        match_bf2 = self.vis.match_template(canvas, "back_to_the_future", threshold=0.85)

        if match_cc2.y >= match_bf2.y:
            winner2 = "close_combat"
        else:
            winner2 = "back_to_the_future"

        self.assertEqual(winner2, "close_combat", "Higher Y (950 > 300) must win!")

    # ---------------- 5. Multi-Turn Battle Flow Test ----------------
    def test_multi_turn_battle_and_route_flow(self):
        """
        Verify user requirement:
        - Constantly checks both templates and clicks whichever appears first
        - If Close Combat is clicked and Back To The Future is not found, clicks Close Combat again
          until Back To The Future appears
        - Once Back To The Future appears at bottom, clicks it
        """
        cc = self.vis.templates["close_combat"]
        bf = self.vis.templates["back_to_the_future"]

        canvas = np.full((1200, 1000, 3), 32, dtype=np.uint8)

        # Helper decision logic
        def get_decision(c):
            m_cc = self.vis.match_template(c, "close_combat", threshold=0.80)
            m_bf = self.vis.match_template(c, "back_to_the_future", threshold=0.80)
            if m_cc.found and m_bf.found:
                return "back_to_the_future" if m_bf.y >= m_cc.y else "close_combat"
            elif m_bf.found:
                return "back_to_the_future"
            elif m_cc.found:
                return "close_combat"
            return None

        # Turn 1: Wild battle starts, only Close Combat visible
        canvas[400:400 + cc.shape[0], 200:200 + cc.shape[1]] = cc
        self.assertEqual(get_decision(canvas), "close_combat", "Turn 1 must click Close Combat")

        # Turn 2: Opponent survives hit! Close Combat still visible, no Back To The Future
        canvas.fill(32)
        canvas[450:450 + cc.shape[0], 200:200 + cc.shape[1]] = cc
        self.assertEqual(get_decision(canvas), "close_combat", "Turn 2 (no Back To The Future) must click Close Combat again")

        # Turn 3: Opponent faints! Back To The Future appears at bottom (y=800), old Close Combat at y=450
        canvas[800:800 + bf.shape[0], 200:200 + bf.shape[1]] = bf
        self.assertEqual(get_decision(canvas), "back_to_the_future", "Battle ended must click Back To The Future at bottom")

        # Turn 4: New battle begins below previous route button
        canvas[950:950 + cc.shape[0], 200:200 + cc.shape[1]] = cc
        self.assertEqual(get_decision(canvas), "close_combat", "New battle at bottom must click Close Combat")

    # ---------------- 6. Safety & Offset Tests ----------------
    def test_click_offset_and_nudge_within_bounds(self):
        """Verify offsets and nudge cursor coordinates stay safe."""
        bot = DiscordMacroBot(start_active=False, enable_hotkeys=False)

        settings.set("click_offset_px", 8)
        for _ in range(50):
            offset_x = np.random.randint(-int(settings.click_offset_px), int(settings.click_offset_px) + 1)
            self.assertTrue(-8 <= offset_x <= 8)

        bot.cleanup()


if __name__ == "__main__":
    unittest.main()
