#!/usr/bin/env python3
"""
Launch the Lepton thermal camera web interface.

Serves a browser page (live MJPEG stream + interactive emissivity controls)
over the local network. Open http://<pi-ip>:8000 from any device.
"""
import argparse

import uvicorn

from lepton.camera import CaptureManager
from lepton.web import create_app


def main():
    p = argparse.ArgumentParser(description="Lepton thermal camera web server")
    p.add_argument("-d", "--device", default="/dev/spidev0.0", help="SPI device")
    p.add_argument("--spi-speed", type=int, default=16000000, help="SPI speed in Hz")
    p.add_argument("--spi-mode", type=int, default=0, choices=[0, 3], help="SPI mode")
    p.add_argument("-i", "--i2c-bus", type=int, default=1, help="I2C bus number")
    p.add_argument("--no-i2c", action="store_true", help="Disable I2C control")
    p.add_argument("--emissivity", type=float, default=0.98, help="Initial emissivity")
    p.add_argument("--background-temp", type=float, default=20.0, help="Background temp (C)")
    p.add_argument("--colormap", default="ironblack",
                   choices=["grayscale", "ironblack", "rainbow"], help="Initial colormap")
    p.add_argument("--host", default="0.0.0.0", help="Listen address")
    p.add_argument("--port", type=int, default=8000, help="Listen port")
    args = p.parse_args()

    manager = CaptureManager(
        device=args.device,
        spi_mode=args.spi_mode,
        spi_speed=args.spi_speed,
        i2c_bus=args.i2c_bus,
        use_i2c=not args.no_i2c,
        colormap=args.colormap,
        emissivity=args.emissivity,
        background_temp=args.background_temp,
    )
    manager.start()

    app = create_app(manager)
    print(f"[Web] Open http://<pi-ip>:{args.port} from any device on the network")
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        manager.stop()


if __name__ == "__main__":
    main()
