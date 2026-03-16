# RGB版本 - 彩虹/单色闪烁测试
from machine import Pin
from neopixel import NeoPixel
import time

# 改成你板子的实际RGB引脚（常见 48 或 38）
RGB_PIN = 48
NUM_LEDS = 1          # 一般板载只有一个灯

np = NeoPixel(Pin(RGB_PIN), NUM_LEDS)

print("开始RGB LED彩虹循环... 按 Ctrl+C 停止")

colors = [
    # (64, 0, 0),    # 红
    # (0, 64, 0),    # 绿
    # (0, 0, 64),    # 蓝
    # (64, 64, 0),   # 黄
    # (0, 64, 64),   # 青
    # (64, 0, 64),   # 紫
    # (20, 20, 20),  # 白（偏暗）

    (10, 10, 10),  # 白（偏暗）
    (20, 20, 20),  # 白（偏暗）
    (30, 30, 30),  # 白（偏暗）
    (40, 40, 40),  # 白（偏暗）
    (50, 50, 50),  # 白（偏暗）
]

try:
    while True:
        for color in colors:
            np[0] = color
            np.write()
            time.sleep(0.8)  # 每个颜色显示0.8秒
except KeyboardInterrupt:
    np[0] = (0, 0, 0)
    np.write()
    print("\nRGB已关闭")