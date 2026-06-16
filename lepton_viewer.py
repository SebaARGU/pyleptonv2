#!/usr/bin/env python3
import argparse
import os
import sys
import time
from datetime import datetime

import cv2
import numpy as np

from lepton.spi import LeptonSPI, LeptonTimeoutError, FRAME_ROWS, FRAME_COLS
from lepton.colormaps import (
    apply_colormap,
    COLORMAP_GRAYSCALE,
    COLORMAP_IRONBLACK,
    COLORMAP_RAINBOW,
    colormap_name,
    list_colormaps,
)
from lepton.radiometry import (
    normalize_frame,
    auto_range,
    raw_to_celsius,
    apply_emissivity,
    get_frame_temperatures,
    EMISSIVITY,
)

try:
    from lepton.i2c import LeptonI2C
    HAVE_I2C = True
except ImportError:
    HAVE_I2C = False


def parse_args():
    parser = argparse.ArgumentParser(
        description="FLIR Lepton thermal camera viewer"
    )
    parser.add_argument(
        "-d", "--device", default="/dev/spidev0.0",
        help="SPI device (default: /dev/spidev0.0)"
    )
    parser.add_argument(
        "--spi-mode", type=int, default=0, choices=[0, 3],
        help="SPI mode (default: 0)"
    )
    parser.add_argument(
        "--spi-speed", type=int, default=16000000,
        help="SPI speed in Hz (default: 16000000)"
    )
    parser.add_argument(
        "-i", "--i2c-bus", type=int, default=1,
        help="I2C bus number (default: 1)"
    )
    parser.add_argument(
        "--no-i2c", action="store_true",
        help="Disable I2C control"
    )
    parser.add_argument(
        "-c", "--capture", type=str, nargs="?", const="snapshot",
        help="Capture single frame and save to PREFIX (default: snapshot)"
    )
    parser.add_argument(
        "--colormap", type=str, default="ironblack",
        choices=["grayscale", "ironblack", "rainbow"],
        help="Colormap for live view (default: ironblack)"
    )
    parser.add_argument(
        "--scale", type=int, default=6,
        help="Display scale factor (default: 6 -> 480x360)"
    )
    parser.add_argument(
        "--temp", action="store_true",
        help="Show temperature overlay"
    )
    parser.add_argument(
        "-o", "--output-dir", default=".",
        help="Directory for saved snapshots (default: current dir)"
    )
    parser.add_argument(
        "--emissivity", type=float, default=1.0,
        help="Emissivity of the scene material 0.01-1.0 (default: 1.0). "
             f"Presets: {', '.join(f'{k}={v}' for k, v in EMISSIVITY.items())}"
    )
    parser.add_argument(
        "--background-temp", type=float, default=20.0,
        help="Reflected background temperature in Celsius (default: 20.0)"
    )
    return parser.parse_args()


def save_snapshot(raw_data, colormap_id, output_dir, prefix):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    raw_path = os.path.join(output_dir, f"{prefix}_{timestamp}.raw")
    with open(raw_path, "wb") as f:
        f.write(raw_data.tobytes())

    vmin, vmax = auto_range(raw_data)
    norm = normalize_frame(raw_data, vmin, vmax)
    rgb = apply_colormap(norm, colormap_id)

    jpg_path = os.path.join(output_dir, f"{prefix}_{timestamp}.jpg")
    cv2.imwrite(jpg_path, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))

    print(f"Saved: {raw_path}")
    print(f"Saved: {jpg_path}")
    return raw_path, jpg_path


def _put_text_shadowed(img, text, pos, scale, color, thickness=1):
    x, y = pos
    cv2.putText(img, text, (x + 1, y + 1),
                cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
    cv2.putText(img, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def draw_overlay(display, celsius_frame, show_temp):
    temps = get_frame_temperatures(celsius_frame)
    h, w = display.shape[:2]

    # ── Cruceta central siempre visible ─────────────────────────────────────
    cx, cy = w // 2, h // 2
    arm = 14
    cv2.line(display, (cx - arm, cy), (cx + arm, cy), (255, 255, 255), 1, cv2.LINE_AA)
    cv2.line(display, (cx, cy - arm), (cx, cy + arm), (255, 255, 255), 1, cv2.LINE_AA)
    cv2.circle(display, (cx, cy), 4, (255, 255, 255), 1, cv2.LINE_AA)

    # Temperatura del centro
    center_row = int(FRAME_ROWS / 2)
    center_col = int(FRAME_COLS / 2)
    center_temp = celsius_frame[center_row, center_col]
    _put_text_shadowed(display, f"{center_temp:.1f}C", (cx + 10, cy - 8), 0.65, (255, 255, 255))

    if not show_temp:
        return

    # ── Panel superior: Min / Max / Avg ─────────────────────────────────────
    panel_h = 68
    overlay = display.copy()
    cv2.rectangle(overlay, (0, 0), (w, panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.45, display, 0.55, 0, display)

    _put_text_shadowed(display, f"Min  {temps['min']:.1f} C", (12, 24), 0.7, (100, 200, 255))
    _put_text_shadowed(display, f"Max  {temps['max']:.1f} C", (12, 46), 0.7, (60,  60,  255))
    _put_text_shadowed(display, f"Avg  {temps['avg']:.1f} C", (12, 68), 0.7, (80, 220,  80))

    # ── Marcador MIN (azul claro) con etiqueta ───────────────────────────────
    if temps["min_pos"]:
        my = int(temps["min_pos"][0] * h / FRAME_ROWS)
        mx = int(temps["min_pos"][1] * w / FRAME_COLS)
        cv2.drawMarker(display, (mx, my), (100, 200, 255), cv2.MARKER_CROSS, 16, 2)
        _put_text_shadowed(display, f"{temps['min']:.1f}C", (mx + 8, my - 6), 0.55, (100, 200, 255))

    # ── Marcador MAX (rojo) con etiqueta ────────────────────────────────────
    if temps["max_pos"]:
        my = int(temps["max_pos"][0] * h / FRAME_ROWS)
        mx = int(temps["max_pos"][1] * w / FRAME_COLS)
        cv2.drawMarker(display, (mx, my), (60, 60, 255), cv2.MARKER_CROSS, 16, 2)
        _put_text_shadowed(display, f"{temps['max']:.1f}C", (mx + 8, my - 6), 0.55, (60, 60, 255))


def run_live_view(args):
    cmap_id = {
        "grayscale": COLORMAP_GRAYSCALE,
        "ironblack": COLORMAP_IRONBLACK,
        "rainbow": COLORMAP_RAINBOW,
    }[args.colormap]

    scale = args.scale
    disp_w = FRAME_COLS * scale
    disp_h = FRAME_ROWS * scale

    i2c = None
    if not args.no_i2c and HAVE_I2C:
        try:
            i2c = LeptonI2C(bus=args.i2c_bus).open()
            print(f"[I2C] Connected. FPA temp: {i2c.get_fpa_temperature_celsius():.1f}C")
        except Exception as e:
            print(f"[I2C] Not available: {e}")

    show_temp = args.temp
    cmap_cycle = [COLORMAP_GRAYSCALE, COLORMAP_IRONBLACK, COLORMAP_RAINBOW]
    cmap_idx = cmap_cycle.index(cmap_id)

    emissivity = args.emissivity
    background_temp = args.background_temp
    if emissivity != 1.0:
        print(f"[Radiometry] Emissivity: {emissivity}, Background: {background_temp} C")

    print(f"[SPI] Opening {args.device} (mode {args.spi_mode}, {args.spi_speed} Hz)")
    print("[Controls]  s:snapshot  f:FFC  c:colormap  t:temp  r:auto-range  q:quit")

    with LeptonSPI(
        device=args.device,
        mode=args.spi_mode,
        speed_hz=args.spi_speed,
    ) as lepton:
        frame_count = 0
        fps_timer = time.monotonic()
        fps_str = ""

        last_display = None

        while True:
            try:
                raw = lepton.get_frame()
            except LeptonTimeoutError:
                if last_display is not None:
                    overlay = last_display.copy()
                    cv2.rectangle(overlay, (0, 0), (disp_w, disp_h), (0, 0, 0), -1)
                    cv2.addWeighted(overlay, 0.55, last_display, 0.45, 0, last_display)
                    _put_text_shadowed(last_display, "SIGNAL LOST",
                                       (disp_w // 2 - 90, disp_h // 2),
                                       0.9, (0, 60, 255), 2)
                    _put_text_shadowed(last_display, "check SPI wiring",
                                       (disp_w // 2 - 80, disp_h // 2 + 30),
                                       0.55, (200, 200, 200))
                    cv2.imshow("Lepton Thermal Camera", last_display)
                    cv2.waitKey(500)
                continue
            frame_count += 1

            if frame_count % 30 == 0:
                elapsed = time.monotonic() - fps_timer
                fps_str = f"{30 / elapsed:.1f} FPS"
                fps_timer = time.monotonic()

            vmin, vmax = auto_range(raw)
            norm = normalize_frame(raw, vmin, vmax)
            rgb = apply_colormap(norm, cmap_id)

            celsius = apply_emissivity(raw_to_celsius(raw), emissivity, background_temp)

            display = cv2.resize(rgb, (disp_w, disp_h), interpolation=cv2.INTER_NEAREST)
            celsius_big = cv2.resize(celsius, (disp_w, disp_h), interpolation=cv2.INTER_NEAREST)
            draw_overlay(display, celsius_big, show_temp)

            info = f"{colormap_name(cmap_id)}  |  {fps_str}"
            _put_text_shadowed(display, info, (8, disp_h - 10), 0.5, (200, 200, 200))

            last_display = display.copy()
            cv2.imshow("Lepton Thermal Camera", display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q") or key == 27:
                break
            elif key == ord("s"):
                save_snapshot(
                    raw, cmap_id, args.output_dir, "thermal"
                )
            elif key == ord("f") and i2c is not None:
                print("[I2C] Running FFC...")
                i2c.run_ffc()
                time.sleep(2.5)
                print("[I2C] FFC done")
            elif key == ord("c"):
                cmap_idx = (cmap_idx + 1) % len(cmap_cycle)
                cmap_id = cmap_cycle[cmap_idx]
                print(f"[Color] Switched to {colormap_name(cmap_id)}")
            elif key == ord("t"):
                show_temp = not show_temp
                print(f"[Temp] Overlay {'ON' if show_temp else 'OFF'}")
            elif key == ord("r"):
                print("[Range] Auto-range reset")

    cv2.destroyAllWindows()
    if i2c is not None:
        i2c.close()


def run_capture(args):
    cmap = {
        "grayscale": COLORMAP_GRAYSCALE,
        "ironblack": COLORMAP_IRONBLACK,
        "rainbow": COLORMAP_RAINBOW,
    }[args.colormap]

    print(f"[SPI] Capturing one frame from {args.device}...")
    with LeptonSPI(
        device=args.device,
        mode=args.spi_mode,
        speed_hz=args.spi_speed,
    ) as lepton:
        raw = lepton.get_frame()

    prefix = args.capture if args.capture else "snapshot"
    save_snapshot(raw, cmap, args.output_dir, prefix)

    celsius = apply_emissivity(raw_to_celsius(raw), args.emissivity, args.background_temp)
    temps = get_frame_temperatures(celsius)
    print(f"  Min: {temps['min']:.1f}C  Max: {temps['max']:.1f}C  Avg: {temps['avg']:.1f}C")


def main():
    args = parse_args()

    if args.capture:
        run_capture(args)
    else:
        try:
            run_live_view(args)
        except KeyboardInterrupt:
            pass
        except ImportError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
