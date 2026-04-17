from __future__ import annotations

import importlib
import sys
import types
import unittest
from unittest import mock


class FakeI2C:
    def __init__(self, responses: list[bytes]):
        self.responses = list(responses)
        self.writes = []

    def writeto(self, address: int, payload: bytes) -> None:
        self.writes.append((address, bytes(payload)))

    def readfrom_into(self, address: int, buffer) -> None:
        data = self.responses.pop(0)
        buffer[:] = data


class Scd41DriverTests(unittest.TestCase):
    def import_driver(self):
        machine_module = types.ModuleType("machine")
        machine_module.I2C = object
        with mock.patch.dict(sys.modules, {"machine": machine_module}):
            sys.modules.pop("scd41_driver", None)
            import scd41_driver

            return importlib.reload(scd41_driver)

    def build_measurement_payload(self, module, co2: int, temp_raw: int, hum_raw: int) -> bytes:
        driver = module.SCD41(FakeI2C([]))
        chunks = []
        for value in (co2, temp_raw, hum_raw):
            pair = bytes([value >> 8, value & 0xFF])
            chunks.append(pair + bytes([driver._crc8(pair)]))
        return b"".join(chunks)

    def test_is_data_ready_reads_status_flag(self) -> None:
        module = self.import_driver()
        i2c = FakeI2C([bytes([0x00, 0x01, 0x00])])
        driver = module.SCD41(i2c)
        with mock.patch.object(module.time, "sleep", return_value=None):
            self.assertTrue(driver.is_data_ready())

    def test_read_returns_decoded_measurement(self) -> None:
        module = self.import_driver()
        measurement = self.build_measurement_payload(module, co2=800, temp_raw=20000, hum_raw=30000)
        i2c = FakeI2C([bytes([0x00, 0x01, 0x00]), measurement])
        driver = module.SCD41(i2c)
        with mock.patch.object(module.time, "sleep", return_value=None):
            co2, temperature, humidity = driver.read()
        self.assertEqual(co2, 800)
        self.assertIsInstance(temperature, float)
        self.assertIsInstance(humidity, float)

    def test_read_returns_none_on_crc_error(self) -> None:
        module = self.import_driver()
        bad_measurement = b"\x03\x20\x00" + b"\x00\x00\x00" + b"\x00\x00\x00"
        i2c = FakeI2C([bytes([0x00, 0x01, 0x00]), bad_measurement])
        driver = module.SCD41(i2c)
        with mock.patch.object(module.time, "sleep", return_value=None):
            self.assertIsNone(driver.read())


if __name__ == "__main__":
    unittest.main()
