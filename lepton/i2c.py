import struct
import time

try:
    import smbus2
    from smbus2 import i2c_msg
except ImportError:
    smbus2 = None
    i2c_msg = None


LEP_I2C_ADDR = 0x2A

LEP_I2C_STATUS_REG = 0x0002
LEP_I2C_COMMAND_REG = 0x0004
LEP_I2C_DATA_LENGTH_REG = 0x0006
LEP_I2C_DATA_BASE = 0x0008

LEP_CID_SYS_PING = 0x0200
LEP_CID_SYS_FPA_TEMPERATURE_KELVIN = 0x0214
LEP_CID_SYS_AUX_TEMPERATURE_KELVIN = 0x0210
LEP_CID_SYS_FFC_SHUTTER_MODE_OBJ = 0x023C
FLR_CID_SYS_RUN_FFC = 0x0242
LEP_CID_OEM_REBOOT = 0x0804

LEP_STATUS_BUSY = 0x0001


class LeptonCCIError(Exception):
    pass


class LeptonI2C:
    def __init__(self, bus=1, address=LEP_I2C_ADDR):
        busn = bus
        self.address = address

        self._bb = None
        self._busn = busn

    def open(self):
        if smbus2 is None:
            raise ImportError("smbus2 not installed. Run: pip install smbus2")

        self._bb = smbus2.SMBus(self._busn)
        if not self._ping():
            self._bb.close()
            self._bb = None
            raise LeptonCCIError("Lepton not responding on I2C bus")
        return self

    def close(self):
        if self._bb is not None:
            self._bb.close()
            self._bb = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.close()

    # El CCI del Lepton usa direcciones de registro de 16 bits, que la API
    # SMBus (command byte de 8 bits) NO puede direccionar. Usamos transacciones
    # I2C crudas (i2c_rdwr) con repeated-start: escribir [reg_hi, reg_lo] y,
    # para lectura, encadenar un mensaje de read.
    @staticmethod
    def _reg_bytes(reg):
        return [(reg >> 8) & 0xFF, reg & 0xFF]

    def _read_block(self, reg, length):
        w = i2c_msg.write(self.address, self._reg_bytes(reg))
        r = i2c_msg.read(self.address, length)
        self._bb.i2c_rdwr(w, r)
        return list(r)

    def _write_block(self, reg, data):
        payload = self._reg_bytes(reg) + list(data)
        w = i2c_msg.write(self.address, payload)
        self._bb.i2c_rdwr(w)

    def _read16(self, reg):
        data = self._read_block(reg, 2)
        return (data[0] << 8) | data[1]

    def _write16(self, reg, value):
        self._write_block(reg, [(value >> 8) & 0xFF, value & 0xFF])

    def _wait_not_busy(self, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self._read16(LEP_I2C_STATUS_REG)
            if not (status & LEP_STATUS_BUSY):
                return
            time.sleep(0.001)
        raise LeptonCCIError("I2C command timeout (busy)")

    def _send_command(self, command, tx_words=None):
        self._wait_not_busy()

        if tx_words:
            data_len = len(tx_words) * 2
            self._write16(LEP_I2C_DATA_LENGTH_REG, data_len)
            tx_bytes = []
            for word in tx_words:
                tx_bytes.append((word >> 8) & 0xFF)
                tx_bytes.append(word & 0xFF)
            self._write_block(LEP_I2C_DATA_BASE, tx_bytes)
        else:
            self._write16(LEP_I2C_DATA_LENGTH_REG, 0)

        self._write16(LEP_I2C_COMMAND_REG, command)
        self._wait_not_busy()

    def _read_response(self, num_words=1):
        data_len = self._read16(LEP_I2C_DATA_LENGTH_REG)
        if data_len == 0:
            return None

        num_bytes = min(data_len, num_words * 2)
        rx_bytes = self._read_block(LEP_I2C_DATA_BASE, num_bytes)

        words = []
        for i in range(0, len(rx_bytes), 2):
            if i + 1 < len(rx_bytes):
                words.append((rx_bytes[i] << 8) | rx_bytes[i + 1])
        return words

    def _ping(self):
        try:
            self._send_command(LEP_CID_SYS_PING)
            return True
        except Exception:
            return False

    def run_ffc(self):
        self._send_command(FLR_CID_SYS_RUN_FFC)

    def reboot(self):
        self._send_command(LEP_CID_OEM_REBOOT)

    def get_fpa_temperature_kelvin(self):
        self._send_command(LEP_CID_SYS_FPA_TEMPERATURE_KELVIN)
        words = self._read_response(1)
        if words:
            return words[0] / 100.0
        return None

    def get_fpa_temperature_celsius(self):
        kelvin = self.get_fpa_temperature_kelvin()
        if kelvin is not None:
            return kelvin - 273.15
        return None

    def get_aux_temperature_kelvin(self):
        self._send_command(LEP_CID_SYS_AUX_TEMPERATURE_KELVIN)
        words = self._read_response(1)
        if words:
            return words[0] / 100.0
        return None
