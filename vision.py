"""Vision module for fast screen capture, inner cropping, multi-scale, and BGR color template matching."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple, Dict
import ctypes
import os
import sys
import threading

import cv2
import mss
import numpy as np

import config


def enable_windows_dpi_awareness():
    """Ensure Windows treats the process as DPI-aware for accurate coordinates."""
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def ensure_desktop_access():
    """Ensure the calling thread is attached to the active user desktop on Windows."""
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass


@dataclass
class MatchResult:
    """Result of template matching on a frame with full diagnostic metrics."""
    found: bool
    x: Optional[int] = None           # Screen X coordinate of button center (bottom-most match)
    y: Optional[int] = None           # Screen Y coordinate of button center (bottom-most match)
    confidence: float = 0.0          # Final score of selected match (raw * color_factor)
    raw_score: float = 0.0           # Raw OpenCV TM_CCOEFF_NORMED correlation score
    color_diff: float = 0.0          # Mean Absolute Error (MAE) in BGR color
    scale: float = 1.0               # Scale factor of the matched template variant
    total_matches: int = 0           # Total number of distinct matches >= threshold

    # Diagnostic peak metrics across entire screen (even if below threshold)
    top_final: float = 0.0           # Highest final score anywhere on screen
    top_raw: float = 0.0             # Raw correlation at peak
    top_diff: float = 0.0            # Color difference at peak
    top_x: int = 0                   # Screen X coordinate at peak
    top_y: int = 0                   # Screen Y coordinate at peak
    top_scale: float = 1.0           # Scale of top match

    @property
    def top_conf(self) -> float:
        """Alias for backward compatibility."""
        return self.top_final


class ScreenVision:
    """Handles screen capture via mss and inner-cropped, multi-scale BGR template matching."""

    CROP_MARGIN = 6  # Pixels to trim from each of the 4 edges of raw templates

    def __init__(self, monitor_index: int = config.settings.monitor_index):
        enable_windows_dpi_awareness()
        ensure_desktop_access()

        self.monitor_index = monitor_index
        self._grab_lock = threading.Lock()
        self._sct = mss.MSS()

        if self.monitor_index >= len(self._sct.monitors):
            raise ValueError(
                f"Invalid MONITOR_INDEX {self.monitor_index}. "
                f"Available monitors: 0 to {len(self._sct.monitors) - 1}."
            )

        self.monitor = self._sct.monitors[self.monitor_index]
        self.monitor_left = self.monitor["left"]
        self.monitor_top = self.monitor["top"]
        self.monitor_width = self.monitor["width"]
        self.monitor_height = self.monitor["height"]

        # Load and inner-crop templates in memory
        self.raw_templates = {
            "close_combat": self._load_template(config.PATH_CLOSE_COMBAT, "Close Combat"),
            "back_to_the_future": self._load_template(config.PATH_BACK_TO_THE_FUTURE, "Back To The Future")
        }

        # Inner-cropped base templates (removes rounded corners and outer Discord background)
        self.templates = {
            k: self._inner_crop(img) for k, img in self.raw_templates.items()
        }

        # Multi-scale precomputed variants
        self.template_variants: Dict[str, List[Tuple[float, np.ndarray]]] = self._build_scale_variants()

    def set_monitor(self, monitor_index: int):
        """Update active monitor index and boundaries."""
        if monitor_index >= len(self._sct.monitors):
            raise ValueError(
                f"Invalid MONITOR_INDEX {monitor_index}. "
                f"Available monitors: 0 to {len(self._sct.monitors) - 1}."
            )
        self.monitor_index = monitor_index
        self.monitor = self._sct.monitors[self.monitor_index]
        self.monitor_left = self.monitor["left"]
        self.monitor_top = self.monitor["top"]
        self.monitor_width = self.monitor["width"]
        self.monitor_height = self.monitor["height"]

    def _load_template(self, path: Path, label: str) -> np.ndarray:
        if not path.is_file():
            raise FileNotFoundError(f"Template image for '{label}' not found at: {path}")

        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Failed to decode template image for '{label}' from: {path}")

        return img

    def _inner_crop(self, img: np.ndarray) -> np.ndarray:
        """Trim 6 pixels off all 4 edges to keep solid button interior and text."""
        m = self.CROP_MARGIN
        h, w = img.shape[:2]
        if h > 2 * m + 10 and w > 2 * m + 10:
            return img[m:-m, m:-m].copy()
        return img.copy()

    def _build_scale_variants(self) -> Dict[str, List[Tuple[float, np.ndarray]]]:
        """Precompute multi-scale variants for fast template matching."""
        cc = self.templates["close_combat"]
        bf = self.templates["back_to_the_future"]

        cc_h = cc.shape[0]
        bf_h = bf.shape[0]

        variants: Dict[str, List[Tuple[float, np.ndarray]]] = {}

        # Close Combat scales: 1.0 first, then common Discord zoom variations
        cc_scales = [1.0, 0.95, 0.90, 0.85, 1.05, 1.10, 1.15]
        variants["close_combat"] = self._generate_variants(cc, cc_scales)

        # Back To The Future scales: 1.0 first (exact user screen scale), then common zoom variations
        bf_scales = [1.0, 0.95, 0.90, 0.85, 1.05, 1.10, 1.15]
        variants["back_to_the_future"] = self._generate_variants(bf, bf_scales)
        return variants

    def _generate_variants(self, base_img: np.ndarray, scales: List[float]) -> List[Tuple[float, np.ndarray]]:
        result = []
        for s in scales:
            if abs(s - 1.0) < 1e-4:
                result.append((1.0, base_img))
            else:
                w = max(10, int(round(base_img.shape[1] * s)))
                h = max(10, int(round(base_img.shape[0] * s)))
                interp = cv2.INTER_AREA if s < 1.0 else cv2.INTER_LINEAR
                resized = cv2.resize(base_img, (w, h), interpolation=interp)
                result.append((round(s, 3), resized))
        return result

    def capture_frame(self) -> np.ndarray:
        """Capture the configured monitor screen in 3-channel BGR format with thread safety and auto-recovery."""
        ensure_desktop_access()
        with self._grab_lock:
            try:
                sct_img = self._sct.grab(self.monitor)
            except Exception:
                # Re-initialize mss context if HDC resource was busy or closed
                try:
                    self._sct.close()
                except Exception:
                    pass
                self._sct = mss.MSS()
                sct_img = self._sct.grab(self.monitor)

            frame_bgr = np.ascontiguousarray(np.array(sct_img)[:, :, :3])
            return frame_bgr

    @staticmethod
    def evaluate_color_penalty(patch: np.ndarray, template: np.ndarray) -> Tuple[float, float, float]:
        """
        Evaluate color difference and contrast between screen patch and template.
        
        Returns:
            (color_diff, contrast_ratio, color_factor)
            
        - Allows normal active Discord buttons and hover state color shifts (color_diff <= 22).
        - Rejects dimmed/disabled buttons (50% opacity / contrast < 0.70 / color_diff > 30).
        """
        diff = float(np.mean(np.abs(patch.astype(np.float32) - template.astype(np.float32))))

        std_p = float(np.std(patch))
        std_t = float(np.std(template))
        contrast_ratio = float(std_p / max(1.0, std_t))

        # Color difference factor (full tolerance up to 22.0)
        if diff <= 22.0:
            color_factor = 1.0
        else:
            color_factor = max(0.05, 1.0 - ((diff - 22.0) / 25.0))

        # Text contrast penalty (disabled buttons have ~50% contrast)
        if contrast_ratio < 0.70:
            contrast_factor = max(0.20, contrast_ratio / 0.85)
            color_factor = min(color_factor, contrast_factor)

        return diff, contrast_ratio, color_factor

    def match_template(
        self,
        frame_bgr: np.ndarray,
        template_name: str,
        threshold: float = config.CONFIDENCE_THRESHOLD
    ) -> MatchResult:
        """
        Match a template using inner-cropped multi-scale matching and color verification.
        
        If multiple matches exceed the threshold, selects the match with the highest Y coordinate
        (bottom-most on screen).
        
        Returns detailed raw_score, color_diff, and final_score for diagnostics.
        """
        if template_name not in self.template_variants:
            raise KeyError(f"Unknown template name: {template_name}")

        variants = self.template_variants[template_name]
        fh, fw = frame_bgr.shape[:2]

        global_best_peak = {
            "top_final": -1.0,
            "top_raw": 0.0,
            "top_diff": 0.0,
            "top_x": 0,
            "top_y": 0,
            "top_scale": 1.0
        }

        all_matches_above_threshold: List[dict] = []

        # Iterate through scales (ordered with primary/normalized scale first)
        for scale, templ in variants:
            th, tw = templ.shape[:2]
            if fh < th or fw < tw:
                continue

            res = cv2.matchTemplate(frame_bgr, templ, cv2.TM_CCOEFF_NORMED)

            # Peak location for this scale
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            raw_peak = float(max(0.0, max_val))
            px, py = max_loc

            patch_peak = frame_bgr[py:py + th, px:px + tw]
            diff_peak, _, factor_peak = self.evaluate_color_penalty(patch_peak, templ)
            final_peak = raw_peak * factor_peak

            screen_px = int(self.monitor_left + px + tw // 2)
            screen_py = int(self.monitor_top + py + th // 2)

            if final_peak > global_best_peak["top_final"]:
                global_best_peak["top_final"] = final_peak
                global_best_peak["top_raw"] = raw_peak
                global_best_peak["top_diff"] = diff_peak
                global_best_peak["top_x"] = screen_px
                global_best_peak["top_y"] = screen_py
                global_best_peak["top_scale"] = scale

            # Search candidates meeting raw correlation threshold
            # Use a slightly lower gate so color factor can evaluate
            raw_gate = max(0.65, threshold * 0.80)
            y_indices, x_indices = np.where(res >= raw_gate)

            scale_candidates: List[dict] = []
            for cy, cx in zip(y_indices, x_indices):
                raw_score = float(res[cy, cx])
                patch = frame_bgr[cy:cy + th, cx:cx + tw]
                diff, _, factor = self.evaluate_color_penalty(patch, templ)
                final_score = raw_score * factor

                if final_score >= threshold:
                    scale_candidates.append({
                        "x": int(cx),
                        "y": int(cy),
                        "tw": tw,
                        "th": th,
                        "scale": scale,
                        "raw_score": raw_score,
                        "color_diff": diff,
                        "final_score": final_score
                    })

            if scale_candidates:
                # Group / Non-Maximum Suppression within this scale
                scale_candidates.sort(key=lambda c: c["final_score"], reverse=True)
                min_dist_x = max(10, tw // 2)
                min_dist_y = max(10, th // 2)

                distinct = []
                for cand in scale_candidates:
                    if not any(
                        abs(cand["x"] - d["x"]) < min_dist_x and abs(cand["y"] - d["y"]) < min_dist_y
                        for d in distinct
                    ):
                        distinct.append(cand)

                all_matches_above_threshold.extend(distinct)

                # Early exit optimization: if high-confidence matches found on primary scale, stop
                if any(m["final_score"] >= threshold for m in distinct):
                    break

        # If no matches above threshold found across any scale
        if not all_matches_above_threshold:
            return MatchResult(
                found=False,
                top_final=max(0.0, global_best_peak["top_final"]),
                top_raw=global_best_peak["top_raw"],
                top_diff=global_best_peak["top_diff"],
                top_x=global_best_peak["top_x"],
                top_y=global_best_peak["top_y"],
                top_scale=global_best_peak["top_scale"]
            )

        # Select match with highest Y coordinate (bottom-most on screen)
        bottom_match = max(all_matches_above_threshold, key=lambda m: m["y"])

        center_x = int(self.monitor_left + bottom_match["x"] + bottom_match["tw"] // 2)
        center_y = int(self.monitor_top + bottom_match["y"] + bottom_match["th"] // 2)

        return MatchResult(
            found=True,
            x=center_x,
            y=center_y,
            confidence=bottom_match["final_score"],
            raw_score=bottom_match["raw_score"],
            color_diff=bottom_match["color_diff"],
            scale=bottom_match["scale"],
            total_matches=len(all_matches_above_threshold),
            top_final=max(global_best_peak["top_final"], bottom_match["final_score"]),
            top_raw=bottom_match["raw_score"],
            top_diff=bottom_match["color_diff"],
            top_x=center_x,
            top_y=center_y,
            top_scale=bottom_match["scale"]
        )

    def close(self):
        """Release capture resources."""
        try:
            self._sct.close()
        except Exception:
            pass
