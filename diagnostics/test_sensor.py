from machine import Pin, I2C
import time

class scd41:
    ADDRESS = 0x62
    CMD_START_PERIODIC = 0x21AC
    CMD_READ_MEASUREMENT = 0xEC05
    CMD_STOP_PERIODIC = 0x3F86
    CMD_GET_DATA_READY = 0xE4B8
    i2c:I2C

    def __init__(self, i2c):
        self.i2c = i2c
        self._buffer = bytearray(9)

    def sendcmd(self, cmd):
        self.i2c.writeto(self.ADDRESS, bytes([cmd >> 8, cmd & 0xFF]))
    


if __name__ == "__main__":
    print("init I2C")
    i2c = I2C(0, scl=Pin(8), sda=Pin(9), freq=50000)    

    print("扫描 I2C 设备...")
    devices = i2c.scan()
    if devices:
        print(f"发现设备地址: {[hex(d) for d in devices]}")
    else:
        print("警告: 未发现任何 I2C 设备，请检查接线！")
            