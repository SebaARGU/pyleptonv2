"""Shared OpenCV overlay drawing for the Lepton viewers.

All colors are in BGR (OpenCV / imshow / imencode convention).
"""
import cv2

from lepton.spi import FRAME_ROWS, FRAME_COLS
from lepton.radiometry import get_frame_temperatures

# Overlay colors (BGR)
COLOR_COLD = (255, 200, 100)   # light blue -> MIN marker
COLOR_HOT = (60, 60, 255)      # red        -> MAX marker
COLOR_AVG = (80, 220, 80)      # green      -> average
COLOR_WHITE = (255, 255, 255)
COLOR_INFO = (200, 200, 200)


def put_text_shadowed(img, text, pos, scale, color, thickness=1):
    x, y = pos
    cv2.putText(img, text, (x + 1, y + 1),
                cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
    cv2.putText(img, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def draw_overlay(display, celsius_frame, show_temp, center_temp):
    """Draw the center spot meter and (optionally) the min/max/avg panel.

    `display` is a BGR image; `celsius_frame` is the temperature frame resized to
    match `display`; `center_temp` is the precomputed center spot value.
    """
    temps = get_frame_temperatures(celsius_frame)
    h, w = display.shape[:2]

    # Center spot meter (3x3 box) always visible
    cx, cy = w // 2, h // 2
    arm = 14
    box_half = 3 * max(w // FRAME_COLS, 1)
    cv2.rectangle(display, (cx - box_half, cy - box_half),
                  (cx + box_half, cy + box_half), COLOR_WHITE, 1, cv2.LINE_AA)
    cv2.line(display, (cx - arm, cy), (cx + arm, cy), COLOR_WHITE, 1, cv2.LINE_AA)
    cv2.line(display, (cx, cy - arm), (cx, cy + arm), COLOR_WHITE, 1, cv2.LINE_AA)
    put_text_shadowed(display, f"{center_temp:.1f}C", (cx + box_half + 6, cy - 8),
                      0.65, COLOR_WHITE)

    if not show_temp:
        return

    # Top panel: Min / Max / Avg
    panel_h = 68
    overlay = display.copy()
    cv2.rectangle(overlay, (0, 0), (w, panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.45, display, 0.55, 0, display)

    put_text_shadowed(display, f"Min  {temps['min']:.1f} C", (12, 24), 0.7, COLOR_COLD)
    put_text_shadowed(display, f"Max  {temps['max']:.1f} C", (12, 46), 0.7, COLOR_HOT)
    put_text_shadowed(display, f"Avg  {temps['avg']:.1f} C", (12, 68), 0.7, COLOR_AVG)

    if temps["min_pos"]:
        my = int(temps["min_pos"][0] * h / FRAME_ROWS)
        mx = int(temps["min_pos"][1] * w / FRAME_COLS)
        cv2.drawMarker(display, (mx, my), COLOR_COLD, cv2.MARKER_CROSS, 16, 2)
        put_text_shadowed(display, f"{temps['min']:.1f}C", (mx + 8, my - 6), 0.55, COLOR_COLD)

    if temps["max_pos"]:
        my = int(temps["max_pos"][0] * h / FRAME_ROWS)
        mx = int(temps["max_pos"][1] * w / FRAME_COLS)
        cv2.drawMarker(display, (mx, my), COLOR_HOT, cv2.MARKER_CROSS, 16, 2)
        put_text_shadowed(display, f"{temps['max']:.1f}C", (mx + 8, my - 6), 0.55, COLOR_HOT)
