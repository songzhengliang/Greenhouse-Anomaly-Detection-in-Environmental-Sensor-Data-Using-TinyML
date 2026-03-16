
from machine import Pin, I2C
import time

def send_cmd(i2c, cmd):
    i2c.writeto(0x62, bytes([cmd >> 8, cmd & 0xFF]))

i2c = I2C(0, scl=Pin(9), sda=Pin(8), freq=50000)
print('设备:', [hex(d) for d in i2c.scan()])

# 1. 尝试 wake_up 命令
print('\n--- 尝试唤醒 (wake_up 0x36F6) ---')
try:
    send_cmd(i2c, 0x36F6)
    time.sleep(0.03)  # 30ms
    print('  唤醒命令已发送')
except Exception as e:
    print(f'  {e}')

time.sleep(1)
print('  扫描:', [hex(d) for d in i2c.scan()])

# 2. 停止
try:
    send_cmd(i2c, 0x3F86)
    time.sleep(0.5)
except: pass

# 3. 读固件版本（验证更多通信）
print('\n--- 读取固件版本 ---')
try:
    # get_sensor_variant 不存在于 SCD41，但我们可以用其他命令
    # 读温度偏移
    send_cmd(i2c, 0x2318)
    time.sleep(0.001)
    raw = i2c.readfrom(0x62, 3)
    offset = ((raw[0] << 8) | raw[1]) * 175.0 / 65535
    print(f'  温度偏移: {offset:.2f}C  原始: {raw.hex()}')
except Exception as e:
    print(f'  {e}')

# 4. 执行自检（等足够久）
print('\n--- 自检 (perform_self_test 0x3639) ---')
print('  等待 10 秒...')
try:
    send_cmd(i2c, 0x3639)
    time.sleep(10)
    # 尝试多次读取
    for i in range(5):
        try:
            result = i2c.readfrom(0x62, 3)
            status = (result[0] << 8) | result[1]
            print(f'  原始: {result.hex()}')
            break
        except Exception as e:
            print(f'  读取尝试 #{i+1}: {e}')
            time.sleep(1)
except Exception as e:
    print(f'  发送失败: {e}')

# 5. 唤醒后重试单次测量
print('\n--- 唤醒后重试测量 ---')
try:
    send_cmd(i2c, 0x36F6)  # wake_up
    time.sleep(0.03)
except: pass

try:
    send_cmd(i2c, 0x3F86)  # stop
    time.sleep(0.5)
except: pass

print('  发送单次测量...')
send_cmd(i2c, 0x219D)

for s in range(25):
    time.sleep(1)
    try:
        send_cmd(i2c, 0xE4B8)
        time.sleep(0.002)
        st = i2c.readfrom(0x62, 3)
        val = ((st[0] << 8) | st[1]) & 0x07FF
        print(val)
        if val != 0:
            print(f'  [{s+1}s] 就绪! val=0x{val:03X}')
            send_cmd(i2c, 0xEC05)
            time.sleep(0.002)
            buf = i2c.readfrom(0x62, 9)
            co2 = (buf[0] << 8) | buf[1]
            t = -45 + 175 * ((buf[3] << 8) | buf[4]) / 65535
            h = 100 * ((buf[6] << 8) | buf[7]) / 65535
            print(f'  CO2={co2}ppm  T={t:.1f}C  H={h:.1f}%')
            break
        elif s % 5 == 0:
            print(f'  [{s}s] 未就绪 raw={st.hex()}')
    except Exception as e:
        print(f'  [{s}s] err: {e}')
else:
    print('  FAIL')

print('\n=== 最终判断 ===')
print('如果自检状态非 0x0000 或所有测量都失败:')
print('  这个 SCD41 的测量单元（红外光源/光电二极管）')
print('  很可能已损坏，需要更换传感器模块。')