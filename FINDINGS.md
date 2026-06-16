# Technical Findings — LeptonModule Reference Repository

## Repository overview

**LeptonModule** (GroupGets/PureEngineering) contains C/C++ reference code for the FLIR Lepton on Raspberry Pi, BeagleBone Black, Arduino, STM32, and Windows. It does not contain functional Python code. The `pylepton` project (GroupGets) is deprecated (README: *"this software no longer works"*).

## 1. VoSPI Protocol

### SPI configuration

| Parameter | `leptsci.c` (flirpi) | `SPI.cpp` (raspberrypi_video) | `LeptonThread.cpp` (raspberrypi_qt) |
|---|---|---|---|
| Device | `/dev/spidev0.0` | `/dev/spidev0.0` (CS0) / `0.1` (CS1) | `/dev/spidev0.1` |
| SPI mode | 0 (CPOL=0, CPHA=0) | 3 (CPOL=1, CPHA=1) | 0 |
| Speed | 16 MHz | 10 MHz (configurable to 20 MHz) | 16 MHz |
| Bits/word | 8 | 8 | 8 |

Both modes 0 and 3 work. Mode 0 matches the FLIR driver (`leptsci.c`). Speed must be ≤ 20 MHz per specification.

### VoSPI packet structure

Each packet is **164 bytes** = 4 header + 80 pixels (2 bytes each):

```
Byte 0:    [bits 7-4: segment (Lepton 3.x only)] [bits 3-0: flags]
             flags=0x0F → camera not ready, discard packet
Byte 1:    Row number (0-59 for Lepton 2.x)
Byte 2-3:  CRC (not verified in reference examples)
Byte 4-163: 80 pixels, 16-bit big-endian (MSB first)
```

**Full frame:** 60 packets × 164 bytes = **9840 bytes** (Lepton 2.x, 80×60)

### Capture algorithm (from `leptsci.c` and `LeptonThread.cpp`)

```
while row < 60:
    read 164 bytes from SPI
    if (packet[0] & 0x0F) == 0x0F:   # not ready
        sleep 1 ms
        continue
    if packet[1] != row:              # out of sync
        reset scan (row = 0)
        if resets > 750: reboot()
        continue
    extract 80 pixels from packet[4..163]
    row += 1
```

### Pixel extraction

From `leptsci.c` lines 98-100:
```c
for (i = 0; i < 80; i++)
    img[row * 80 + i] = (lepacket[2 * i + 4] << 8) | lepacket[2 * i + 5];
```

Each pixel is 2 bytes, big-endian:
```
pixel[col] = (packet[4 + 2*col] << 8) | packet[5 + 2*col]
```

In Python:
```python
pixels = np.frombuffer(packet[4:], dtype=np.uint16).newbyteorder('B')
```

### Duplicate frame detection

The Lepton outputs at ~27 FPS internally but the scene updates at ~9 FPS. `LeptonThread.cpp` does not detect duplicates explicitly. A simple approach is to compare the current frame checksum against the previous one.

## 2. CCI Protocol (I2C)

### I2C address

From `LEPTON_I2C_Reg.h` line 83:
```c
#define LEP_I2C_DEVICE_ADDRESS  0x2A  // 7-bit address
```
7-bit: `0x2A` — 8-bit write: `0x54`, 8-bit read: `0x55`

### CCI register map

| Address | Name | Description |
|---|---|---|
| `0x0000` | `LEP_I2C_POWER_REG` | Module power on/off |
| `0x0002` | `LEP_I2C_STATUS_REG` | Bit 0: busy (1=busy, 0=ready) |
| `0x0004` | `LEP_I2C_COMMAND_REG` | Write command ID (16-bit) |
| `0x0006` | `LEP_I2C_DATA_LENGTH_REG` | Data length in bytes |
| `0x0008` | `LEP_I2C_DATA_0_REG` | First data word |
| `0x000A..0x0026` | `LEP_I2C_DATA_1..15_REG` | Additional data words |
| `0x0028` | `LEP_I2C_DATA_CRC_REG` | CRC |
| `0xF800` | `LEP_DATA_BUFFER_0` | Large data buffer (1 KB) |
| `0xFC00` | `LEP_DATA_BUFFER_1` | Large data buffer (1 KB) |

### CCI command flow

```
1. Poll STATUS_REG bit 0 == 0   (not busy)
2. If input data:
   - Write DATA_LENGTH_REG = number_of_bytes
   - Write data to DATA_0_REG..DATA_N_REG
   Else: DATA_LENGTH_REG = 0
3. Write COMMAND_REG with command ID
4. Poll STATUS_REG bit 0 == 0   (command complete)
5. Read DATA_LENGTH_REG to get response length
6. Read DATA_0_REG..DATA_N_REG for response
```

### Command IDs

| ID | Macro | Description |
|---|---|---|
| `0x0200` | `LEP_CID_SYS_PING` | Ping (device present) |
| `0x0204` | `LEP_CID_SYS_CAM_STATUS` | Camera status |
| `0x0208` | `LEP_CID_SYS_FLIR_SERIAL_NUMBER` | FLIR serial number |
| `0x020C` | `LEP_CID_SYS_CAM_UPTIME` | Uptime |
| `0x0210` | `LEP_CID_SYS_AUX_TEMPERATURE_KELVIN` | Auxiliary temperature |
| `0x0214` | `LEP_CID_SYS_FPA_TEMPERATURE_KELVIN` | FPA temperature (×100 K) |
| `0x0218` | `LEP_CID_SYS_TELEMETRY_ENABLE_STATE` | Enable frame telemetry |
| `0x022C` | `LEP_CID_SYS_SCENE_STATISTICS` | Scene statistics |
| `0x023C` | `LEP_CID_SYS_FFC_SHUTTER_MODE_OBJ` | FFC shutter mode config |
| `0x0242` | `FLR_CID_SYS_RUN_FFC` | **Run FFC now** |
| `0x0804` | `LEP_CID_OEM_REBOOT` | **Reboot module** |

## 3. Color Palettes

Three palettes defined in `Palettes.cpp`, each with 256 RGB entries (768 integers):

### `colormap_grayscale`
Linear gradient: white (entry 0) → black (entry 255).

### `colormap_ironblack` (default)
```
entries 0-127:   White → Black (descending greyscale)
entries 128-159: Black → Dark red
entries 160-191: Red → Orange
entries 192-223: Orange → Yellow
entries 224-255: Yellow → Bright yellow/white
```

### `colormap_rainbow`
```
entries 0-42:    Dark blue → Blue
entries 43-85:   Blue → Cyan
entries 86-128:  Cyan → Green
entries 129-170: Green → Yellow
entries 171-213: Yellow → Orange
entries 214-255: Orange → Red
```

### Pixel-to-color mapping

From `mainwindow.cpp` lines 51-57:
```cpp
diff = max_value - min_value + 1;
scaledValue = 256 * (baseValue - minValue) / diff;
color = colormap[scaledValue];  // RGB triplet
```

The raw range [min, max] is normalized to [0, 255] and used as a palette index.

## 4. Radiometry

### Lepton 2.5 specification

| Parameter | Value |
|---|---|
| ADC resolution | 14-bit (in 16-bit container) |
| Frame rate | 8.6 Hz (commercial) / 27 Hz (internal) |
| Radiometric accuracy | ±5°C (high gain @ 25°C ambient) |
| Range (high gain) | -10°C to +140°C |
| Range (low gain) | up to +400°C |

### TLinear mode

When **TLinear** is enabled (default on Lepton 2.5 and 3.5):
- Pixel value represents temperature in centikelvin (K × 100)
- Typical C reference values: `rangeMin=30000` (26.85°C), `rangeMax=32000` (46.85°C)

**Conversion formula:**
```python
T_kelvin  = raw_pixel / 100.0
T_celsius = T_kelvin - 273.15
```

### Emissivity correction

Real materials have emissivity ε < 1.0. The correction accounts for both material emissivity and reflected background radiation:

```python
T_real = (T_measured - (1 - ε) * T_background) / ε
```

This is a software correction only. For systems with an optical window, characterization of window transmission (τ_Win) and window temperature (T_Win) is also required (see FLIR doc 102-PS245-76).

### Accuracy vs. temperature (datasheet)

| Ambient | Scene 10°C | 50°C | 100°C |
|---|---|---|---|
| 0°C | ±5°C | ±5°C | ±5°C |
| 30°C | ±5°C | ±3°C | ±4°C |
| 60°C | ±6°C | ±3°C | ±3°C |

## 5. Pin mapping (Raspberry Pi)

Based on `SPI.cpp`, `LeptonThread.cpp`, and `leptsci.c`:

| Lepton signal | RPi pin | Notes |
|---|---|---|
| CS (Chip Select) | GPIO8 (CE0) → `/dev/spidev0.0` | Or GPIO7 (CE1) → `0.1` |
| MOSI | GPIO10 (MOSI) | Unused by Lepton (output-only device) |
| MISO | GPIO9 (MISO) | **Required** — video data |
| SCLK | GPIO11 (SCLK) | SPI clock |
| SDA (I2C) | GPIO2 (SDA) | `/dev/i2c-1` |
| SCL (I2C) | GPIO3 (SCL) | `/dev/i2c-1` |
| VIN | 3.3 V | Breakout regulates internally |
| GND | GND | Common ground |

SPI and I2C must be enabled via `raspi-config` before use.

## 6. Existing Python ecosystem

### PyLepton (`groupgets/pylepton`)
- **Deprecated**: README states *"this software no longer works"*
- SPI capture only, no I2C control
- Assumes 12-bit data (not 14-bit radiometric)
- Lepton 2.x only (80×60); does not handle 4-segment Lepton 3.x
- Breaks on recent Raspbian kernels

#### Reusable technique: batch reads with raw `ioctl`

`pylepton` bypasses `spidev` and talks directly to the kernel: it builds the `spi_ioc_transfer` struct manually and issues `SPI_IOC_MESSAGE` via `fcntl.ioctl`. This reads **multiple VoSPI rows in a single syscall** instead of one `xfer2()` per packet.

The kernel accepts an array of `spi_ioc_transfer` descriptors in a single `ioctl`. Sending N descriptors together reads all 60 rows in ~3 syscalls instead of 60.

Default `spidev` buffer size is 4096 bytes: `4096 / 164 ≈ 24` rows per `ioctl`. To increase:

```bash
echo 65536 > /sys/module/spidev/parameters/bufsiz
```

This technique is documented as a reference. The current `spi.py` uses `xfer2()` per packet (60 syscalls/frame at ~9 FPS = ~540 syscalls/s), which is sufficient in practice. Batching is an option if CPU overhead or sync loss becomes a problem.

## 7. Key reference files

| File | Path | Relevant lines |
|---|---|---|
| Main SPI driver | `software/flirpi/leptsci.c` | 47-104 (full capture) |
| Qt capture (no SDK) | `software/raspberrypi_qt/LeptonThread.cpp` | 13-162 (robust loop) |
| Qt capture (with SDK) | `software/raspberrypi_video/LeptonThread.cpp` | 107-274 (Lepton 3.x support) |
| Color palettes | `software/raspberrypi_video/Palettes.cpp` | 1-25 (3 palettes) |
| I2C via SDK | `software/raspberrypi_video/Lepton_I2C.cpp` | 1-32 (FFC, reboot) |
| I2C registers | `software/beagleboneblack_video/leptonSDKEmb32PUB/LEPTON_I2C_Reg.h` | 79-131 (addresses) |
| Framebuffer viewer | `software/flirpi/fblept.c` | 30-104 (colormap + render) |
