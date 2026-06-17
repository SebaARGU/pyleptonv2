"""Single-producer capture manager shared by all web clients.

The SPI camera is one hardware resource, so a single background thread owns the
LeptonSPI (and optional LeptonI2C) handles. It continuously captures frames,
renders a JPEG, and computes temperature statistics under the current settings.
Web clients read the latest JPEG/stats; they never touch the hardware directly.
"""
import threading
import time

import cv2
import numpy as np

from lepton.spi import LeptonSPI, LeptonTimeoutError, FRAME_ROWS, FRAME_COLS
from lepton.colormaps import (
    apply_colormap,
    COLORMAP_GRAYSCALE,
    COLORMAP_IRONBLACK,
    COLORMAP_RAINBOW,
    colormap_name,
)
from lepton.radiometry import (
    raw_to_celsius,
    apply_emissivity,
    auto_range,
    normalize_frame,
    get_frame_temperatures,
    center_box_temp,
)
from lepton.overlay import draw_overlay

try:
    from lepton.i2c import LeptonI2C
    HAVE_I2C = True
except ImportError:
    HAVE_I2C = False


COLORMAP_IDS = {
    "grayscale": COLORMAP_GRAYSCALE,
    "ironblack": COLORMAP_IRONBLACK,
    "rainbow": COLORMAP_RAINBOW,
}

DISPLAY_W, DISPLAY_H = 480, 360


class CaptureManager:
    def __init__(self, device="/dev/spidev0.0", spi_mode=0, spi_speed=16000000,
                 i2c_bus=1, use_i2c=True, colormap="ironblack",
                 emissivity=0.98, background_temp=20.0, jpeg_quality=80):
        self.device = device
        self.spi_mode = spi_mode
        self.spi_speed = spi_speed
        self.i2c_bus = i2c_bus
        self.use_i2c = use_i2c and HAVE_I2C
        self.jpeg_quality = jpeg_quality

        self._lock = threading.Lock()
        self._settings = {
            "emissivity": float(emissivity),
            "background_temp": float(background_temp),
            "colormap": colormap if colormap in COLORMAP_IDS else "ironblack",
        }
        self._ffc_requested = False

        self._latest_jpeg = None
        self._stats = {
            "min": None, "max": None, "avg": None, "center": None,
            "fps": 0.0, "fpa_temp": None, **self._settings,
        }
        self._frame_event = threading.Event()

        self._thread = None
        self._running = False
        self._i2c = None

    # ── public API ───────────────────────────────────────────────────────────
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def update_settings(self, emissivity=None, background_temp=None, colormap=None):
        with self._lock:
            if emissivity is not None:
                self._settings["emissivity"] = max(0.05, min(1.0, float(emissivity)))
            if background_temp is not None:
                self._settings["background_temp"] = float(background_temp)
            if colormap is not None and colormap in COLORMAP_IDS:
                self._settings["colormap"] = colormap

    def request_ffc(self):
        with self._lock:
            self._ffc_requested = True

    def get_stats(self):
        with self._lock:
            return dict(self._stats)

    def get_latest_jpeg(self):
        with self._lock:
            return self._latest_jpeg

    def wait_for_frame(self, timeout=2.0):
        """Block until a new frame is ready; returns the latest JPEG."""
        self._frame_event.wait(timeout)
        self._frame_event.clear()
        return self.get_latest_jpeg()

    # ── capture loop ───────────────────────────────────────────────────────────
    def _run(self):
        if self.use_i2c:
            try:
                self._i2c = LeptonI2C(bus=self.i2c_bus).open()
                print(f"[I2C] Connected. FPA temp: "
                      f"{self._i2c.get_fpa_temperature_celsius():.1f}C")
            except Exception as e:
                print(f"[I2C] Not available: {e}")
                self._i2c = None

        with LeptonSPI(device=self.device, mode=self.spi_mode,
                       speed_hz=self.spi_speed) as lepton:
            fps_timer = time.monotonic()
            frame_count = 0
            fps = 0.0

            while self._running:
                self._maybe_run_ffc()

                try:
                    raw = lepton.get_frame()
                except LeptonTimeoutError:
                    time.sleep(0.1)
                    continue

                frame_count += 1
                if frame_count % 15 == 0:
                    now = time.monotonic()
                    fps = 15 / (now - fps_timer)
                    fps_timer = now

                with self._lock:
                    emissivity = self._settings["emissivity"]
                    background_temp = self._settings["background_temp"]
                    colormap = self._settings["colormap"]

                jpeg, stats = self._render(raw, emissivity, background_temp, colormap, fps)

                with self._lock:
                    self._latest_jpeg = jpeg
                    self._stats = stats
                self._frame_event.set()

        if self._i2c is not None:
            self._i2c.close()

    def _maybe_run_ffc(self):
        with self._lock:
            requested = self._ffc_requested
            self._ffc_requested = False
        if requested and self._i2c is not None:
            print("[I2C] Running FFC...")
            try:
                self._i2c.run_ffc()
                time.sleep(2.5)
                print("[I2C] FFC done")
            except Exception as e:
                print(f"[I2C] FFC failed: {e}")

    def _render(self, raw, emissivity, background_temp, colormap, fps):
        cmap_id = COLORMAP_IDS[colormap]
        vmin, vmax = auto_range(raw)
        norm = normalize_frame(raw, vmin, vmax)
        bgr = cv2.cvtColor(apply_colormap(norm, cmap_id), cv2.COLOR_RGB2BGR)

        celsius = apply_emissivity(raw_to_celsius(raw), emissivity, background_temp)
        center_temp = center_box_temp(celsius)

        display = cv2.resize(bgr, (DISPLAY_W, DISPLAY_H), interpolation=cv2.INTER_NEAREST)
        celsius_big = cv2.resize(celsius, (DISPLAY_W, DISPLAY_H),
                                 interpolation=cv2.INTER_NEAREST)
        draw_overlay(display, celsius_big, True, center_temp)

        ok, buf = cv2.imencode(".jpg", display,
                               [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        jpeg = buf.tobytes() if ok else None

        temps = get_frame_temperatures(celsius)
        # raw (uncorrected) center for the educational raw-vs-corrected comparison
        center_raw = center_box_temp(raw_to_celsius(raw))

        fpa_temp = None
        if self._i2c is not None:
            try:
                fpa_temp = self._i2c.get_fpa_temperature_celsius()
            except Exception:
                fpa_temp = None

        stats = {
            "min": round(temps["min"], 1),
            "max": round(temps["max"], 1),
            "avg": round(temps["avg"], 1),
            "center": round(center_temp, 1),
            "center_raw": round(center_raw, 1),
            "fps": round(fps, 1),
            "fpa_temp": round(fpa_temp, 1) if fpa_temp is not None else None,
            "emissivity": emissivity,
            "background_temp": background_temp,
            "colormap": colormap,
        }
        return jpeg, stats
