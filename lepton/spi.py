import re
import time
import numpy as np
try:
    import spidev
except ImportError:
    spidev = None


VOSPI_PACKET_SIZE = 164
FRAME_ROWS = 60
FRAME_COLS = 80
VOSPI_FRAME_SIZE = VOSPI_PACKET_SIZE * FRAME_ROWS
PIXEL_DATA_OFFSET = 4
HEADER_NOT_READY = 0x0F

# Maximo absoluto segun el datasheet del Lepton. Nunca lo superamos.
SPI_MAX_SPEED_HZ = 20000000


def _parse_spidev_path(device):
    """'/dev/spidev0.0' -> (0, 0). Acepta tambien una tupla/lista (bus, dev)."""
    if isinstance(device, (tuple, list)):
        return int(device[0]), int(device[1])
    m = re.search(r"spidev(\d+)\.(\d+)", str(device))
    if not m:
        raise ValueError(
            f"No se pudo interpretar el dispositivo SPI: {device!r}. "
            "Usa algo como '/dev/spidev0.0'."
        )
    return int(m.group(1)), int(m.group(2))


class LeptonSPI:
    def __init__(self, device="/dev/spidev0.0", mode=0, speed_hz=16000000, timeout_ms=100):
        if spidev is None:
            raise ImportError("spidev not installed. Run: pip install spidev")

        self.device = device
        self.mode = mode
        # Seguridad: el Lepton tolera hasta 20 MHz; cualquier valor mayor se recorta.
        if speed_hz > SPI_MAX_SPEED_HZ:
            print(f"[SPI] {speed_hz} Hz supera el maximo del Lepton; "
                  f"se limita a {SPI_MAX_SPEED_HZ} Hz")
            speed_hz = SPI_MAX_SPEED_HZ
        self.speed_hz = speed_hz
        self.timeout_ms = timeout_ms
        self._spi = None
        self._last_frame_sum = None

    def open(self):
        bus, dev = _parse_spidev_path(self.device)
        self._spi = spidev.SpiDev()
        self._spi.open(bus, dev)
        self._spi.mode = self.mode
        self._spi.max_speed_hz = self.speed_hz
        self._spi.bits_per_word = 8
        self._spi.lsbfirst = False
        return self

    def close(self):
        if self._spi is not None:
            self._spi.close()
            self._spi = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.close()

    def _read_packet(self):
        # La velocidad ya esta fijada en max_speed_hz; xfer2 solo recibe el buffer.
        tx = [0] * VOSPI_PACKET_SIZE
        rx = self._spi.xfer2(tx)
        return bytearray(rx)

    def _packet_number(self, packet):
        # Header byte[0] con los 4 bits bajos a 0xF => paquete descarte (no listo).
        if (packet[0] & 0x0F) == HEADER_NOT_READY:
            return -1
        return packet[1]

    def capture_frame(self):
        # Replica la maquina de estados de LeptonThread.cpp (raspberrypi_qt):
        # un frame valido son 60 filas consecutivas 0..59. Si se pierde la
        # sincronia se descarta el frame entero y se reinicia desde la fila 0.
        frame = bytearray(VOSPI_FRAME_SIZE)
        resets = 0

        while True:
            row = 0
            errors = 0
            while row < FRAME_ROWS:
                packet = self._read_packet()
                number = self._packet_number(packet)

                if number == -1:
                    time.sleep(0.001)
                    errors += 1
                    if errors > 300:
                        break          # demasiados descartes: reiniciar frame
                    continue

                if number != row:
                    time.sleep(0.001)
                    break              # desincronizado: reiniciar frame

                offset = row * VOSPI_PACKET_SIZE
                frame[offset:offset + VOSPI_PACKET_SIZE] = packet
                row += 1

            if row == FRAME_ROWS:
                break                  # frame completo

            resets += 1
            if resets >= 750:
                # El Lepton necesita ~setup; pausa larga para que re-sincronice.
                resets = 0
                time.sleep(0.75)

        return self._parse_frame(frame)

    def _parse_frame(self, frame):
        raw = np.frombuffer(frame, dtype=np.uint8).reshape(FRAME_ROWS, VOSPI_PACKET_SIZE)
        # Descartar los 4 bytes de cabecera de cada fila y leer 80 pixeles
        # big-endian (MSB primero), igual que leptsci.c / LeptonThread.cpp.
        payload = raw[:, PIXEL_DATA_OFFSET:]
        pixels = payload.reshape(FRAME_ROWS, FRAME_COLS, 2).astype(np.uint16)
        pixels = (pixels[:, :, 0] << 8) | pixels[:, :, 1]

        frame_sum = int(pixels.sum())
        is_duplicate = False
        if self._last_frame_sum is not None and frame_sum == self._last_frame_sum:
            is_duplicate = True
        self._last_frame_sum = frame_sum

        return pixels, is_duplicate

    def get_frame(self):
        while True:
            frame, is_dup = self.capture_frame()
            if not is_dup:
                return frame
