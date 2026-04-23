from machine import I2C
import time


class SCD41:
    """Minimal SCD41 CO2/temperature/humidity driver for MicroPython."""

    ADDRESS = 0x62
    CMD_START_LOW_POWER_PERIODIC = 0x21AC
    CMD_START_STANDARD_PERIODIC = 0x21B1
    CMD_MEASURE_SINGLE_SHOT = 0x219D
    CMD_READ_MEASUREMENT = 0xEC05
    CMD_STOP_PERIODIC = 0x3F86
    CMD_GET_DATA_READY = 0xE4B8
    CMD_WAKE_UP = 0x36F6

    def __init__(self, i2c):
        self.i2c = i2c
        self._buffer = bytearray(9)

    def _send_command(self, cmd):
        self.i2c.writeto(self.ADDRESS, bytes([cmd >> 8, cmd & 0xFF]))

    def _crc8(self, data):
        crc = 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x31
                else:
                    crc = crc << 1
        return crc & 0xFF

    def wake_up(self):
        self._send_command(self.CMD_WAKE_UP)
        time.sleep(0.03)

    def start(self, low_power=True):
        command = self.CMD_START_LOW_POWER_PERIODIC if low_power else self.CMD_START_STANDARD_PERIODIC
        self._send_command(command)
        time.sleep(0.02)

    def start_low_power(self):
        self.start(low_power=True)

    def start_standard_periodic(self):
        self.start(low_power=False)

    def start_single_shot(self):
        self._send_command(self.CMD_MEASURE_SINGLE_SHOT)
        time.sleep(0.02)

    def stop(self):
        self._send_command(self.CMD_STOP_PERIODIC)
        time.sleep(0.5)

    def data_ready_status(self):
        try:
            self._send_command(self.CMD_GET_DATA_READY)
            time.sleep(0.002)
            status = bytearray(3)
            self.i2c.readfrom_into(self.ADDRESS, status)
            if self._crc8(status[:2]) != status[2]:
                return None
            return ((status[0] << 8) | status[1]) & 0x07FF
        except Exception:
            return None

    def is_data_ready(self):
        status = self.data_ready_status()
        return status is not None and status != 0

    def read(self):
        return self.read_measurement(require_ready=True)

    def read_measurement(self, require_ready=True):
        try:
            if require_ready and not self.is_data_ready():
                return None

            self._send_command(self.CMD_READ_MEASUREMENT)
            time.sleep(0.001)
            self.i2c.readfrom_into(self.ADDRESS, self._buffer)

            for index in range(0, 9, 3):
                if self._crc8(self._buffer[index:index + 2]) != self._buffer[index + 2]:
                    return None

            co2 = (self._buffer[0] << 8) | self._buffer[1]
            temp_raw = (self._buffer[3] << 8) | self._buffer[4]
            hum_raw = (self._buffer[6] << 8) | self._buffer[7]

            if co2 == 0 and temp_raw == 0 and hum_raw == 0:
                return None

            temperature = -45 + 175 * temp_raw / 65535
            humidity = 100 * hum_raw / 65535
            return co2, temperature, humidity
        except Exception:
            return None

    def read_latest(self):
        return self.read_measurement(require_ready=False)
