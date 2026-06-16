"""
Rutina mínima de arranque seguro para FLIR Lepton 2.x en Raspberry Pi.
Sigue los pasos del ARRANQUE_SEGURO.md: verificación previa, velocidad
conservadora, captura de un frame y lectura de temperatura interna.
"""

import os
import sys

# ── 1. Verificar que los dispositivos existen antes de importar los drivers ──

SPI_DEVICE = "/dev/spidev0.0"
I2C_BUS    = 1

def _check_devices():
    ok = True
    if not os.path.exists(SPI_DEVICE):
        print(f"[ERROR] {SPI_DEVICE} no existe.")
        print("        Habilita SPI con: sudo raspi-config → Interface Options → SPI")
        ok = False
    if not os.path.exists(f"/dev/i2c-{I2C_BUS}"):
        print(f"[AVISO] /dev/i2c-{I2C_BUS} no existe (I2C no disponible — temperatura interna omitida).")
    return ok

if not _check_devices():
    sys.exit(1)

# ── 2. Importar drivers ───────────────────────────────────────────────────────

from lepton.spi import LeptonSPI
from lepton.radiometry import raw_to_celsius, get_frame_temperatures

try:
    from lepton.i2c import LeptonI2C
    _I2C_AVAILABLE = True
except ImportError:
    _I2C_AVAILABLE = False

# ── 3. Arranque ───────────────────────────────────────────────────────────────

# Velocidad conservadora para el primer arranque (ARRANQUE_SEGURO.md §4.1)
SPI_SPEED_HZ = 10_000_000  # 10 MHz; subir a 16 MHz si la imagen es estable

print(f"Abriendo cámara en {SPI_DEVICE} a {SPI_SPEED_HZ // 1_000_000} MHz...")

with LeptonSPI(SPI_DEVICE, speed_hz=SPI_SPEED_HZ) as cam:

    # ── 3a. Temperatura interna por I2C (verifica que la cámara está viva) ──
    if _I2C_AVAILABLE:
        try:
            with LeptonI2C(bus=I2C_BUS) as i2c:
                fpa_c = i2c.get_fpa_temperature_celsius()
                if fpa_c is not None:
                    print(f"Temperatura interna FPA: {fpa_c:.1f} °C  (cámara responde OK)")
        except Exception as e:
            print(f"[AVISO] I2C no respondió: {e}")

    # ── 3b. Capturar un frame (descarta duplicados automáticamente) ──────────
    print("Capturando frame...")
    frame_raw = cam.get_frame()   # ndarray (60, 80) uint16

    # ── 3c. Convertir a °C y mostrar estadísticas ────────────────────────────
    celsius = raw_to_celsius(frame_raw)
    stats   = get_frame_temperatures(celsius)

    min_pos = tuple(int(x) for x in stats['min_pos'])
    max_pos = tuple(int(x) for x in stats['max_pos'])
    print(f"Frame capturado: {frame_raw.shape[1]}x{frame_raw.shape[0]} px")
    print(f"  Min : {stats['min']:.1f} C  en {min_pos}")
    print(f"  Max : {stats['max']:.1f} C  en {max_pos}")
    print(f"  Prom: {stats['avg']:.1f} C")
    print("OK - camara operativa.")
