# pyleptonv2

Python interface for FLIR Lepton thermal camera (Dev Kit V2, 80×60) on Raspberry Pi via SPI/I2C.

## Structure

```
lepton_viewer.py    CLI viewer and snapshot tool
lepton/
  spi.py            VoSPI capture (60 packets of 164 bytes → 80×60 uint16 frame)
  i2c.py            CCI control over I2C (FFC, temperature, reboot, ping)
  colormaps.py      3 palettes: grayscale, ironblack, rainbow
  radiometry.py     TLinear → °C conversion, normalization, auto-range
setup.py            pip-installable package
requirements.txt    spidev, numpy, opencv-python
```

## Requirements

- Raspberry Pi (any model with SPI + I2C)
- SPI and I2C enabled (`raspi-config`)
- Python ≥ 3.8

```bash
pip install -r requirements.txt
```
Optional: `pip install smbus2` for I2C control.

## Wiring

| Lepton | RPi pin |
|--------|---------|
| VIN    | 1 (3.3V) |
| GND    | 6        |
| SDA    | 3        |
| SCL    | 5        |
| CS     | 24 (CE0) |
| MOSI   | 19       |
| MISO   | 21       |
| CLK    | 23       |

See `HARDWARE_SETUP.md` for detailed cabling and first-boot steps.

## Usage

**Live view:**
```bash
python3 lepton_viewer.py
```

**Single snapshot:**
```bash
python3 lepton_viewer.py --capture test
```

**Controls (live view):** `s` save, `f` FFC, `c` colormap, `t` temp overlay, `q` quit.

## Web interface

A browser-based viewer for demos and classrooms. Multiple devices (phones,
laptops) can connect to the same live stream at once — no install on the client
side. Run it on the Pi:

```bash
python3 lepton_web.py
```

Then open `http://<pi-ip>:8000` from any device on the same network. The page
has a live thermal stream plus interactive controls: an emissivity slider with
material presets, background temperature, colormap selector, and an FFC button.
The educational panel shows the correction formula and the raw-vs-corrected
center-spot temperature in real time.

All clients share one capture loop (the SPI sensor is a single resource), so
settings changes are collaborative and visible to everyone — well suited to an
instructor-led demo.

## Deployment (kiosk mode)

`install.sh` sets up the Pi to run the web interface unattended — no keyboard or
monitor needed. It installs dependencies in a virtualenv, enables SPI/I2C,
registers a systemd service that starts on boot, and optionally turns the Pi into
a WiFi access point with a fixed IP.

```bash
# Service only (Pi stays on your existing network)
sudo ./install.sh

# Service + WiFi access point (Pi broadcasts its own network)
sudo ./install.sh --hotspot
```

Edit the variables at the top of `install.sh` first if you want a different
`SSID`, `WIFI_PASS`, `AP_IP`, or `PORT` (defaults: `LeptonCam` / `leptonthermal`
/ `192.168.4.1` / `8000`).

**Reboot after the first install** so the freshly enabled SPI/I2C devices
(`/dev/spidev0.0`, `/dev/i2c-1`) appear:

```bash
sudo reboot
```

**Connecting in hotspot mode:** join the `LeptonCam` WiFi network from your phone
or laptop, then open `http://192.168.4.1:8000`. The Pi serves DHCP, so the device
gets an address automatically.

**Useful commands:**

```bash
systemctl status lepton-web        # service state
sudo systemctl restart lepton-web  # restart after a code change
journalctl -u lepton-web -f        # live logs
sudo ./install.sh --uninstall      # remove service + hotspot
```

> Enabling the hotspot disconnects the Pi from WiFi internet (single radio). The
> installer always installs dependencies first and configures the access point
> last. To get internet back, run `--uninstall` or
> `nmcli connection down lepton-hotspot`.

## Emissivity correction

By default the Lepton assumes emissivity = 1.0 (perfect blackbody). Real materials emit less radiation, which biases absolute temperature readings. Pass `--emissivity` and `--background-temp` to compensate:

```bash
python3 lepton_viewer.py --emissivity 0.98 --background-temp 22 --temp
```

| Material        | Emissivity |
|-----------------|------------|
| Human skin      | 0.98       |
| Plastic         | 0.95       |
| Wood            | 0.94       |
| Glass           | 0.92       |
| Concrete        | 0.95       |
| Water           | 0.96       |
| Oxidized metal  | 0.70       |
| Polished metal  | 0.10       |
| Aluminium       | 0.05       |

Formula applied: `T_real = (T_measured − (1 − ε) × T_background) / ε`

Note: sensor accuracy is ±5°C — emissivity correction improves systematic bias but does not increase absolute accuracy beyond the hardware limit.

## Notes

- Assumes TLinear (radiometric) mode — raw values are centikelvin.
- SPI speed is clamped to 20 MHz (datasheet max).
- I2C is optional; without it FFC and temperature readout are unavailable.
- Frame duplicates (internal ~27 Hz → ~9 Hz effective) are discarded.

## References

- `HARDWARE_SETUP.md` — wiring, first boot, and troubleshooting
- `PLAN.md` — architecture and design decisions
- `FINDINGS.md` — VoSPI and CCI protocol details from the FLIR reference codebase
