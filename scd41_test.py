"""
ESP32-S3 + SCD41 传感器测试
实时读取 CO2、温度、湿度数据
"""
from machine import Pin, I2C
import time
import struct

import emlearn_trees
import array

model = emlearn_trees.new(10, 100, 100)

# Load the model from the CSV file
with open('model.csv', 'r') as f:
    emlearn_trees.load_model(model, f)

def predict(co2, temp, humidity):
    # Make a prediction using the loaded model
    input_data = array.array('h', [int(co2), int(temp), int(humidity)])
    output = array.array('f', range(model.outputs()))
    model.predict(input_data, output)
    predict_class = 0
    max_prob = output[0]
    for i in range(1, len(output)):
        if output[i] > max_prob:
            max_prob = output[i]
            predict_class = i
    return predict_class, max_prob

class SCD41:
    """SCD41 CO2/温度/湿度传感器驱动"""

    # I2C 地址
    ADDRESS = 0x62

    # 命令
    CMD_START_PERIODIC = 0x21AC  # 使用低功耗模式（更兼容）
    CMD_READ_MEASUREMENT = 0xEC05
    CMD_STOP_PERIODIC = 0x3F86
    CMD_GET_DATA_READY = 0xE4B8

    def __init__(self, i2c):
        self.i2c = i2c
        self._buffer = bytearray(9)

    def _send_command(self, cmd):
        """发送命令到传感器"""
        self.i2c.writeto(self.ADDRESS, bytes([cmd >> 8, cmd & 0xFF]))

    def _crc8(self, data):
        """计算 CRC-8 校验码"""
        crc = 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x31
                else:
                    crc = crc << 1
        return crc & 0xFF

    def start(self):
        """启动周期性测量（低功耗模式）"""
        print("启动 SCD41 周期性测量（低功耗模式）...")
        self._send_command(self.CMD_START_PERIODIC)
        time.sleep(0.02)  # 增加延迟以确保命令被处理

    def stop(self):
        """停止周期性测量"""
        print("停止 SCD41 测量...")
        self._send_command(self.CMD_STOP_PERIODIC)
        time.sleep(0.5)

    def is_data_ready(self):
        """检查数据是否就绪

        返回: True 如果数据已就绪，False 否则
        """
        try:
            self._send_command(self.CMD_GET_DATA_READY)
            time.sleep(0.001)  # 1ms 延迟

            # 读取 3 字节 (2 字节数据 + 1 字节 CRC)
            status = bytearray(3)
            self.i2c.readfrom_into(self.ADDRESS, status)

            # 检查数据就绪位
            data_ready = ((status[0] << 8) | status[1]) & 0x07FF
            return data_ready != 0

        except OSError:
            return False
        except Exception:
            return False

    def read(self):
        """读取测量数据

        返回: (co2_ppm, temperature_c, humidity_percent) 或 None
        """
        try:
            # 首先检查数据是否就绪
            if not self.is_data_ready():
                print("数据未准备好，请稍候...")
                return None

            # 发送读取命令
            self._send_command(self.CMD_READ_MEASUREMENT)
            time.sleep(0.001)  # 等待 1ms

            # 读取 9 字节数据
            self.i2c.readfrom_into(self.ADDRESS, self._buffer)

            # 验证 CRC（每两字节数据后跟一个 CRC 字节）
            for i in range(0, 9, 3):
                if self._crc8(self._buffer[i:i+2]) != self._buffer[i+2]:
                    print("CRC 校验失败")
                    return None

            # 解析数据
            co2 = (self._buffer[0] << 8) | self._buffer[1]
            temp_raw = (self._buffer[3] << 8) | self._buffer[4]
            hum_raw = (self._buffer[6] << 8) | self._buffer[7]

            # 检查数据是否有效（全 0 表示数据未准备好）
            if co2 == 0 and temp_raw == 0 and hum_raw == 0:
                print("数据未准备好，请稍候...")
                return None

            # 转换为实际值
            temperature = -45 + 175 * temp_raw / 65535
            humidity = 100 * hum_raw / 65535

            return co2, temperature, humidity

        except OSError as e:
            if e.errno == 19:  # ENODEV
                print("设备无响应（请检查连接）")
            else:
                print(f"I2C 通信错误: {e}")
            return None
        except Exception as e:
            print(f"读取数据失败: {e}")
            return None


def main():
    """主程序"""

    # 初始化 I2C（根据你的接线调整引脚）
    print("初始化 I2C...")
    i2c = I2C(0, scl=Pin(8), sda=Pin(9), freq=100000)  # 使用 50kHz 更稳定

    # 扫描 I2C 设备
    print("扫描 I2C 设备...")
    devices = i2c.scan()
    if devices:
        print(f"发现设备地址: {[hex(d) for d in devices]}")
    else:
        print("警告: 未发现任何 I2C 设备，请检查接线！")
        return

    # 初始化 SCD41
    sensor = SCD41(i2c)

    # 先停止任何正在进行的测量
    try:
        sensor.stop()
    except:
        pass  # 忽略错误，可能没有正在运行的测量

    # 启动测量
    sensor.start()
    print("等待传感器稳定（35秒）...")
    print("SCD41 低功耗模式首次测量需要较长时间，请耐心等待...")
    time.sleep(35)  # SCD41 低功耗模式首次测量需要约 30-35 秒

    print("\n开始读取数据... 按 Ctrl+C 停止\n")
    print("-" * 60)

    retry_count = 0
    max_retries = 3

    try:
        while True:
            data = sensor.read()

            if data:
                co2, temp, hum = data
                print(f"CO2: {co2:5d} ppm | 温度: {temp:5.1f} °C | 湿度: {hum:5.1f} %")
                pred_class, prob = predict(co2, temp, hum)
                labels = ["优秀", "良好", "一般", "较差", "差"]
                print(f"预测类别: {labels[pred_class]} | 置信度: {prob:.2f}")
                retry_count = 0  # 重置重试计数

            else:
                retry_count += 1
                print(f"读取失败，重试中... ({retry_count}/{max_retries})")

                if retry_count >= max_retries:
                    print("\n连续失败次数过多，尝试重启传感器...")
                    sensor.stop()
                    time.sleep(1)
                    sensor.start()
                    print("等待传感器重新初始化（15秒）...")
                    time.sleep(35)
                    retry_count = 0

            time.sleep(30)  # SCD41 低功耗模式每 30 秒更新一次数据

    except KeyboardInterrupt:
        print("\n\n停止读取")
    finally:
        sensor.stop()
        print("传感器已关闭")


if __name__ == "__main__":
    main()
