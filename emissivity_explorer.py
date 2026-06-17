#!/usr/bin/env python3
"""
Emissivity Explorer — an educational live viewer for the FLIR Lepton.

Shows the thermal image next to a panel that explains, in real time, how
emissivity correction changes a temperature reading. Adjust emissivity and
background temperature with the keyboard and watch the corrected center-spot
value update against the raw (uncorrected) value.

This is a teaching tool, not a measurement tool. Sensor accuracy is +-5C.
"""
import argparse
import time

import cv2
import numpy as np

from lepton.spi import LeptonSPI, LeptonTimeoutError, FRAME_ROWS, FRAME_COLS
from lepton.colormaps import apply_colormap, COLORMAP_IRONBLACK, colormap_name
from lepton.radiometry import (
    raw_to_celsius,
    apply_emissivity,
    auto_range,
    normalize_frame,
    center_box_temp,
    EMISSIVITY,
)

try:
    from lepton.i2c import LeptonI2C
    HAVE_I2C = True
except ImportError:
    HAVE_I2C = False


IMG_W, IMG_H = 480, 360         # thermal image size
PANEL_W = 360                   # educational side panel width
EMISSIVITY_MIN = 0.05
EMISSIVITY_MAX = 1.0
EMISSIVITY_STEP = 0.01

# Presets cycled with the 'm' key: (label, emissivity)
PRESETS = list(EMISSIVITY.items())

# Colors in BGR (OpenCV convention)
C_WHITE = (255, 255, 255)
C_GREY = (180, 180, 180)
C_DIM = (130, 130, 130)
C_RAW = (120, 170, 255)         # orange-ish: raw / uncorrected
C_CORR = (120, 255, 160)        # green: corrected
C_KEY = (255, 220, 120)         # cyan-ish: key hints


def parse_args():
    p = argparse.ArgumentParser(description="Educational emissivity explorer for FLIR Lepton")
    p.add_argument("-d", "--device", default="/dev/spidev0.0", help="SPI device")
    p.add_argument("--spi-speed", type=int, default=16000000, help="SPI speed in Hz")
    p.add_argument("--spi-mode", type=int, default=0, choices=[0, 3], help="SPI mode")
    p.add_argument("-i", "--i2c-bus", type=int, default=1, help="I2C bus number")
    p.add_argument("--no-i2c", action="store_true", help="Disable I2C")
    p.add_argument("--emissivity", type=float, default=0.98, help="Initial emissivity")
    p.add_argument("--background-temp", type=float, default=20.0, help="Background temp (C)")
    return p.parse_args()


def preset_label(emissivity):
    """Return the material name matching the current emissivity, else 'custom'."""
    for name, value in PRESETS:
        if abs(value - emissivity) < 1e-6:
            return name
    return "custom"


def draw_thermal(raw, emissivity, background_temp):
    """Build the BGR thermal image with the center spot marker."""
    vmin, vmax = auto_range(raw)
    norm = normalize_frame(raw, vmin, vmax)
    bgr = cv2.cvtColor(apply_colormap(norm, COLORMAP_IRONBLACK), cv2.COLOR_RGB2BGR)
    img = cv2.resize(bgr, (IMG_W, IMG_H), interpolation=cv2.INTER_NEAREST)

    cx, cy = IMG_W // 2, IMG_H // 2
    box_half = 3 * (IMG_W // FRAME_COLS)
    cv2.rectangle(img, (cx - box_half, cy - box_half),
                  (cx + box_half, cy + box_half), C_WHITE, 1, cv2.LINE_AA)
    cv2.line(img, (cx - 12, cy), (cx + 12, cy), C_WHITE, 1, cv2.LINE_AA)
    cv2.line(img, (cx, cy - 12), (cx, cy + 12), C_WHITE, 1, cv2.LINE_AA)
    return img


def _text(panel, s, x, y, scale=0.45, color=C_GREY, thick=1):
    cv2.putText(panel, s, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def draw_panel(emissivity, background_temp, t_raw, t_corr, fps_str):
    """Build the educational side panel as a BGR image."""
    panel = np.zeros((IMG_H, PANEL_W, 3), dtype=np.uint8)
    x = 16
    y = 30

    _text(panel, "EMISSIVITY EXPLORER", x, y, 0.6, C_WHITE, 2)
    y += 14
    cv2.line(panel, (x, y), (PANEL_W - 16, y), C_DIM, 1)
    y += 26

    # Current settings
    _text(panel, f"Emissivity  e = {emissivity:.2f}", x, y, 0.55, C_WHITE)
    y += 22
    _text(panel, f"Material      {preset_label(emissivity)}", x, y, 0.5, C_GREY)
    y += 22
    _text(panel, f"Background  T_bg = {background_temp:.0f} C", x, y, 0.5, C_GREY)
    y += 32

    # Formula
    _text(panel, "Correction:", x, y, 0.5, C_KEY)
    y += 22
    _text(panel, "T_real = (T_meas - (1-e)*T_bg) / e", x, y, 0.42, C_GREY)
    y += 30

    # Live numbers
    _text(panel, "Center spot (3x3):", x, y, 0.5, C_KEY)
    y += 24
    _text(panel, f"raw  (e=1.0):   {t_raw:5.1f} C", x, y, 0.5, C_RAW)
    y += 22
    _text(panel, f"corrected:      {t_corr:5.1f} C", x, y, 0.5, C_CORR)
    y += 22
    _text(panel, f"difference:     {t_corr - t_raw:+5.1f} C", x, y, 0.5, C_WHITE)
    y += 34

    # Short explanation
    _text(panel, "e = how well a surface emits IR", x, y, 0.4, C_DIM)
    y += 18
    _text(panel, "vs a blackbody (e=1.0). Real", x, y, 0.4, C_DIM)
    y += 18
    _text(panel, "materials emit less, so raw", x, y, 0.4, C_DIM)
    y += 18
    _text(panel, "readings are biased low.", x, y, 0.4, C_DIM)
    y += 30

    # Controls
    _text(panel, "+/-  emissivity    [ ]  T_bg", x, y, 0.42, C_KEY)
    y += 18
    _text(panel, "m  material    f  FFC    q  quit", x, y, 0.42, C_KEY)

    if fps_str:
        _text(panel, fps_str, PANEL_W - 80, IMG_H - 12, 0.4, C_DIM)
    return panel


def run(args):
    emissivity = max(EMISSIVITY_MIN, min(EMISSIVITY_MAX, args.emissivity))
    background_temp = args.background_temp
    preset_idx = 0

    i2c = None
    if not args.no_i2c and HAVE_I2C:
        try:
            i2c = LeptonI2C(bus=args.i2c_bus).open()
            print(f"[I2C] Connected. FPA temp: {i2c.get_fpa_temperature_celsius():.1f}C")
        except Exception as e:
            print(f"[I2C] Not available: {e}")

    print("[Controls]  +/-:emissivity  [ ]:background  m:material  f:FFC  q:quit")

    with LeptonSPI(device=args.device, mode=args.spi_mode, speed_hz=args.spi_speed) as lepton:
        fps_timer = time.monotonic()
        frame_count = 0
        fps_str = ""

        while True:
            try:
                raw = lepton.get_frame()
            except LeptonTimeoutError:
                continue

            frame_count += 1
            if frame_count % 30 == 0:
                elapsed = time.monotonic() - fps_timer
                fps_str = f"{30 / elapsed:.1f} FPS"
                fps_timer = time.monotonic()

            celsius_raw = raw_to_celsius(raw)
            celsius_corr = apply_emissivity(celsius_raw, emissivity, background_temp)
            t_raw = center_box_temp(celsius_raw)
            t_corr = center_box_temp(celsius_corr)

            img = draw_thermal(raw, emissivity, background_temp)
            panel = draw_panel(emissivity, background_temp, t_raw, t_corr, fps_str)
            window = np.hstack([img, panel])

            cv2.imshow("Lepton Emissivity Explorer", window)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), 27):
                break
            elif key in (ord("+"), ord("=")):
                emissivity = min(EMISSIVITY_MAX, round(emissivity + EMISSIVITY_STEP, 2))
            elif key in (ord("-"), ord("_")):
                emissivity = max(EMISSIVITY_MIN, round(emissivity - EMISSIVITY_STEP, 2))
            elif key == ord("]"):
                background_temp += 1.0
            elif key == ord("["):
                background_temp -= 1.0
            elif key == ord("m"):
                emissivity = PRESETS[preset_idx][1]
                preset_idx = (preset_idx + 1) % len(PRESETS)
            elif key == ord("f") and i2c is not None:
                print("[I2C] Running FFC...")
                i2c.run_ffc()
                time.sleep(2.5)
                print("[I2C] FFC done")

    cv2.destroyAllWindows()
    if i2c is not None:
        i2c.close()


def main():
    args = parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
