# Hardware Setup — FLIR Lepton 2.x on Raspberry Pi

Step-by-step guide for wiring and first boot of the FLIR Lepton (80×60, Dev Kit V2) on Raspberry Pi.

> **Safety summary**
> - SPI capture is read-only. I2C commands used (ping, temperature, FFC) are documented by FLIR and safe.
> - The only real risk is electrical: the Lepton runs at **3.3 V**.
> - Always connect and disconnect with the **Raspberry Pi powered off**.

---

## 1. Risk reference

| Action | Risk | Reason |
|---|---|---|
| SPI capture | None | Read-only; MOSI sends zeros which the Lepton ignores |
| I2C commands used (ping, temperature, FFC) | None | Documented by FLIR; FFC only moves the internal shutter |
| SPI speed ≤ 20 MHz | None | Within specification; clamped in software |
| Applying 5 V to data lines | **Damages device** | Lepton is 3.3 V |
| Hot-plugging (connecting while Pi is on) | Risk | Current spikes / latch-up |
| ESD | Risk | Handle with ESD precautions |
| Pointing at sun or extreme heat sources | Risk | Can damage the microbolometer |

Commands that write to non-volatile OEM flash are not used, so factory calibration is never altered.

---

## 2. Wiring (Pi powered off)

Power off and unplug the Raspberry Pi before connecting any wires.

| Lepton (breakout) | RPi physical pin | Function |
|---|---|---|
| GND | 6 | Common ground |
| VIN (3.3 V) | 1 | Power — **not** pin 2 or 4 (5 V) |
| SDA | 3 | I2C data (GPIO2) |
| SCL | 5 | I2C clock (GPIO3) |
| CS | 24 | Chip Select → `/dev/spidev0.0` (GPIO8 / CE0) |
| MOSI | 19 | GPIO10 (unused by Lepton) |
| MISO | 21 | Video data (GPIO9) — required |
| CLK | 23 | SPI clock (GPIO11 / SCLK) |

```
        Raspberry Pi 40-pin header (top view)
   3V3  (1) (2)  5V        <-- use pin 1, not 2 or 4
   SDA  (3) (4)  5V
   SCL  (5) (6)  GND
        (7) (8)
   GND  (9) (10)
        ...
  MOSI (19) (20) GND
  MISO (21) (22)
   CLK (23) (24) CS (CE0)
```

Verify VIN goes to pin 1 (3.3 V) before powering on. Connecting VIN to 5 V will damage the module.

---

## 3. Software configuration

Power on the Pi and open a terminal.

### 3.1 Enable SPI and I2C

```bash
sudo raspi-config
# Interface Options -> SPI  -> Enable
# Interface Options -> I2C  -> Enable
# Finish -> reboot
sudo reboot
```

After reboot, verify the devices exist:

```bash
ls /dev/spidev0.*   # expected: /dev/spidev0.0
ls /dev/i2c-1       # expected: /dev/i2c-1
```

### 3.2 Verify camera responds on I2C

```bash
sudo apt install -y i2c-tools
sudo i2cdetect -y 1
```

Address `2a` must appear in the grid. If it does not, power off and check SDA, SCL, VIN, and GND before continuing.

### 3.3 Install Python dependencies

```bash
cd ~/pyleptonv2
pip install -r requirements.txt
# On managed environments (PEP 668):
#   python3 -m venv .venv && source .venv/bin/activate
#   pip install -r requirements.txt
```

---

## 4. First run

### 4.1 Single frame capture

```bash
python3 lepton_viewer.py --capture test --spi-speed 10000000
```

Saves `test_TIMESTAMP.raw` and `.jpg` and prints temperature statistics. A recognizable image confirms SPI capture is working.

### 4.2 Live view

Start at a conservative speed, then increase if stable:

```bash
python3 lepton_viewer.py --spi-speed 10000000
python3 lepton_viewer.py --spi-speed 16000000 --temp
```

**Live view controls:**

| Key | Action |
|---|---|
| `s` | Save snapshot (`.raw` + `.jpg`) |
| `f` | Run FFC (shutter recalibration) |
| `c` | Cycle colormap (grayscale → ironblack → rainbow) |
| `t` | Toggle temperature overlay |
| `r` | Reset auto-range |
| `q` / `Esc` | Quit |

---

## 4.3 Unattended deployment (web service + hotspot)

To run the web interface automatically on boot — headless, no keyboard or monitor —
use the installer. It creates a virtualenv, enables SPI/I2C, registers a systemd
service, and (with `--hotspot`) turns the Pi into a WiFi access point.

```bash
cd ~/pyleptonv2
sudo ./install.sh --hotspot
sudo reboot          # required so SPI/I2C devices appear
```

After reboot, join the `LeptonCam` WiFi (password `leptonthermal`) and open
`http://192.168.4.1:8000`. Change `SSID`, `WIFI_PASS`, `AP_IP`, or `PORT` at the
top of `install.sh` before running.

| Command | Action |
|---|---|
| `systemctl status lepton-web` | Check the service |
| `sudo systemctl restart lepton-web` | Restart after a change |
| `journalctl -u lepton-web -f` | Live logs |
| `sudo ./install.sh --uninstall` | Remove service + hotspot (restores WiFi internet) |

> The hotspot uses the Pi's only WiFi radio, so internet over WiFi is unavailable
> while it is active. Install dependencies before enabling the hotspot (the
> installer does this automatically).

---

## 5. Troubleshooting

| Symptom | Likely cause | Solution |
|---|---|---|
| `Can't open device /dev/spidev0.0` | SPI not enabled or wrong CS pin | `raspi-config` → SPI; try `-d /dev/spidev0.1` |
| `i2cdetect` does not show `2a` | I2C wiring or power issue | Power off and check SDA/SCL/VIN/GND |
| Striped or garbled image | SPI speed too high or sync loss | Lower `--spi-speed` to 10 MHz |
| Washed-out image after a while | FFC needed | Press `f` or wait for automatic FFC |
| Temperature readings out of range | Sensor not in TLinear mode | Image is valid; absolute °C values unreliable |
| `Lepton not responding on I2C` | Wrong bus or address | Confirm bus 1 and address `0x2a` |

---

## 6. Best practices

- Connect and disconnect only with the Pi powered off.
- Discharge static before handling the module.
- Do not point the camera at the sun or extreme heat sources.
- Allow FFC periodically (automatic, or press `f`) to maintain image quality.
- SPI speed is clamped in software to 20 MHz.

---

## 7. References

- `README.md` — usage and API overview.
- `PLAN.md` — module architecture and design decisions.
- `FINDINGS.md` — VoSPI and CCI protocol details extracted from FLIR reference code.
- FLIR Lepton 2.5 datasheet (SPI ≤ 20 MHz, I2C address `0x2A`).
