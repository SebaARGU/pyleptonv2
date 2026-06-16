# Implementation Plan: Python Interface for FLIR Lepton Dev Kit V2

> **Status:** skeleton implemented and reviewed/corrected (see [§ Correction log](#correction-log)).
> Hardware setup guide: `HARDWARE_SETUP.md`.

## Objective

A modular Python module for the FLIR Lepton 2.5 thermal camera (Dev Kit V2, SparkFun SFE-KIT-15948) on Raspberry Pi with direct SPI/I2C connection. The design supports future integration with an optical camera for synchronized capture.

## Architecture

```
requirements.txt          # pip dependencies
setup.py                  # installable package
lepton_viewer.py          # CLI: live view + snapshot capture
lepton/
    __init__.py           # public API exports
    spi.py                # VoSPI capture + frame assembly
    i2c.py                # CCI control (optional: FFC, temperature)
    colormaps.py          # color palettes (grayscale / ironblack / rainbow)
    radiometry.py         # 14-bit → °C conversion + emissivity correction
```

## Module responsibilities

### `lepton/spi.py`

- Opens `/dev/spidevX.Y` (configurable, default `0.0`) — parses path to `open(bus, dev)` for `py-spidev`
- SPI mode 0, 8 bits, 16 MHz (clamped to ≤ 20 MHz per datasheet)
- `LeptonSPI` class with `capture_frame() -> (ndarray[uint16], is_duplicate)`
  - Reads 60 packets of 164 bytes each (VoSPI)
  - Detects not-ready packets (`header[0] & 0x0F == 0x0F`)
  - Verifies `packet[1] == expected row number (0..59)`
  - Converts big-endian to uint16: `pixel = (data[4+2*i] << 8) | data[5+2*i]`
  - Returns numpy array `(60, 80)` uint16
  - Detects duplicate frames by frame checksum

### `lepton/i2c.py`

- Opens `/dev/i2c-1` (configurable), address `0x2A` (7-bit)
- Implements CCI (Command Control Interface) protocol:
  1. Wait for `LEP_I2C_STATUS_REG (0x0002)` bit 0 = 0 (not busy)
  2. Write data length to `LEP_I2C_DATA_LENGTH_REG (0x0006)`
  3. Write data to `LEP_I2C_DATA_BASE (0x0008)`
  4. Write command to `LEP_I2C_COMMAND_REG (0x0004)`
  5. Wait for completion
  6. Read response
- Exposed functions:
  - `run_ffc()` — execute FFC (Flat Field Correction), command `0x0242`
  - `reboot()` — reboot the module, command `0x0804`
  - `get_fpa_temperature_celsius()` — internal sensor temperature
  - `get_aux_temperature_celsius()` — auxiliary temperature

### `lepton/colormaps.py`

- Three 256-entry RGB palettes:
  - `COLORMAP_GRAYSCALE` (0): white → black, linear
  - `COLORMAP_IRONBLACK` (1): white → grey → black → red → orange → yellow
  - `COLORMAP_RAINBOW` (2): blue → cyan → green → yellow → red
- `apply_colormap(frame_8bit, colormap_id) -> ndarray[uint8]` RGB

### `lepton/radiometry.py`

- Converts raw 14-bit to Celsius (TLinear mode):
  - `T_K = raw_value / 100.0`
  - `T_C = T_K - 273.15`
- `apply_emissivity(celsius, emissivity, background_temp)` — emissivity and reflected background correction
- `EMISSIVITY` — dictionary of common material emissivity values
- `auto_range(raw, margin) -> (vmin, vmax)` — dynamic range calculation
- `normalize_frame(raw, vmin, vmax) -> uint8` — normalize to 0–255
- `get_frame_temperatures(celsius) -> dict` — min/max/avg statistics with pixel positions

### `lepton_viewer.py` (main CLI)

```
usage: lepton_viewer.py [-h] [-d SPI_DEVICE] [--spi-mode {0,3}]
                        [--spi-speed HZ] [-i I2C_BUS] [--no-i2c]
                        [-c [PREFIX]] [--colormap {grayscale,ironblack,rainbow}]
                        [--scale N] [--temp] [-o DIR]
                        [--emissivity E] [--background-temp T]

Modes:
  Default:       Live view with OpenCV (480×360, scale 6×)
  --capture, -c  Capture a single frame and save snapshot (raw + jpg)

Live view controls:
  s    Save snapshot (thermal_TIMESTAMP.raw + thermal_TIMESTAMP.jpg)
  f    Run FFC (if I2C available)
  c    Cycle colormap (grayscale → ironblack → rainbow)
  t    Toggle temperature overlay
  r    Reset auto-range
  q    Quit
```

## Dependencies

```bash
pip install spidev numpy opencv-python
# Optional for I2C control:
pip install smbus2
```

## Implementation roadmap

| Step | Files | Description |
|---|---|---|
| 1 | `spi.py`, `colormaps.py` | SPI capture + color palettes |
| 2 | `lepton_viewer.py` | Live view loop with OpenCV |
| 3 | `radiometry.py` | Temperature conversion and normalization |
| 4 | `i2c.py` | I2C control: FFC, temperature, reboot |
| 5 | Emissivity correction | `apply_emissivity()` in `radiometry.py` |
| 6 | Optical camera integration | Future, out of scope for this plan |

## Reference repository mapping

| Source file | Content | Used in |
|---|---|---|
| `software/flirpi/leptsci.c` | SPI driver (mode 0, 16 MHz, VoSPI) | `spi.py` |
| `software/raspberrypi_qt/LeptonThread.cpp` | Capture loop + packet detection | `spi.py` |
| `software/raspberrypi_video/Palettes.cpp` | 3 RGB color palettes | `colormaps.py` |
| `software/raspberrypi_video/Lepton_I2C.cpp` | I2C commands via SDK | `i2c.py` |
| `software/raspberrypi_video/LeptonThread.cpp` | Auto-ranging + colormap mapping | `radiometry.py`, `lepton_viewer.py` |
| `software/beagleboneblack_video/leptonSDKEmb32PUB/LEPTON_I2C_Reg.h` | CCI register addresses | `i2c.py` |

## Correction log

Review of the initial generated code, cross-checked against the C reference (`raspberrypi_qt/LeptonThread.cpp`, `flirpi/leptsci.c`) and the `py-spidev` / `smbus2` APIs.

### `spi.py`
- **Device open:** replaced `open_path("/dev/spidev0.0")` (non-existent in `py-spidev`) with path parsing to `open(bus, dev)`.
- **Speed safety:** clamp to 20 MHz (datasheet maximum); values above are trimmed with a warning.
- **`xfer2`:** removed `speed_hz=` keyword argument (unreliable); speed is set via `max_speed_hz`.
- **Resync:** the capture state machine now mirrors `LeptonThread.cpp`: on out-of-order packet, the entire frame is discarded and restarted from row 0.
- **Performance:** pixel parsing vectorized with numpy (replaced a per-pixel Python double loop).

### `i2c.py`
- **CCI protocol rewritten:** replaced `read/write_i2c_block_data` (8-bit command byte, cannot address Lepton's 16-bit registers) with raw I2C transactions using `smbus2.i2c_msg` / `i2c_rdwr` (repeated-start).
- Only **safe commands** are exposed (ping, status, FPA/aux temperature, FFC, reboot). No writes to non-volatile OEM flash.

### Notes
- The °C conversion (`radiometry.py`) assumes **TLinear** mode (centikelvin). Verify over I2C if the specific sensor is radiometric; if not, the image is valid but absolute temperatures are unreliable.
- Possible future improvement: `--simulate` mode to validate the pipeline without hardware.
- Color palettes in `colormaps.py` are algorithmic approximations. The exact 256-entry tables from `Palettes.cpp` can be ported for pixel-accurate color reproduction.
