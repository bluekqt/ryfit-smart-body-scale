import asyncio
import struct
import time
from datetime import datetime
from bleak import BleakClient

# ================= 配置 =================
DEVICE_ADDRESS = "YOUR_SCALE_MAC_ADDRESS"
NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# 自定义指令序列（可自由修改）
COMMANDS = [
    ("时间同步", b'\xFA\xF8' + struct.pack('<I', int(time.time())), 0.5),
    # ("切换槽位 c0 01 8c 21 01", bytes([0xC0, 0x01, 0x8C, 0x21, 0x01]), 1.0),
    # ("删除槽位 A2 01", bytes([0xA2, 0x01]), 1.0),
    # ("查询历史 C1 01", bytes([0xC1, 0x01]), 3.0),
    # ("删除记录 C2 01", bytes([0xC2, 0x01]), 2.0),
    # ("再次查询历史 C1 01", bytes([0xC1, 0x01]), 3.0),
    ("查询槽位 A5", b'\xA5', 3.0),
]
# =========================================


def log(direction, data):
    now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{now}] {direction}: {data.hex(' ').upper()}")


async def main():
    print("=" * 50)
    print("自动确认 + 自定义指令测试 (修正版)")
    print(f"目标设备: {DEVICE_ADDRESS}")
    print("指令序列:")
    for i, (desc, _, _) in enumerate(COMMANDS, 1):
        print(f"  {i}. {desc}")
    input("按回车开始...")

    acked_prefixes = set()       # 存储 bytes 类型的前缀
    received_count = 0

    def notify_handler(sender, data):
        nonlocal received_count, acked_prefixes
        received_count += 1
        log("收到", data)

        # 只对长度>=3的包发送确认，且确保前缀是 bytes 类型
        if len(data) >= 3:
            prefix = bytes(data[:3])   # 转为 bytes（可哈希）
            if prefix not in acked_prefixes:
                acked_prefixes.add(prefix)
                ack = b'\xFA' + prefix
                asyncio.ensure_future(client.write_gatt_char(
                    NOTIFY_UUID, ack, response=False))
                log("发送", ack)
                print("  → 自动发送 FA 确认")

    async with BleakClient(DEVICE_ADDRESS, timeout=30.0) as client:
        await client.start_notify(NOTIFY_UUID, notify_handler)
        print("已连接，等待稳定...")
        await asyncio.sleep(3)

        for desc, cmd, wait in COMMANDS:
            print(f"\n>>> {desc}")
            log("发送", cmd)
            await client.write_gatt_char(NOTIFY_UUID, cmd, response=False)
            await asyncio.sleep(wait)

        print("\n所有指令已发送，继续监听 10 秒...")
        await asyncio.sleep(10)

    print(
        f"\n会话结束。共收到 {received_count} 个数据包，发送 {len(acked_prefixes)} 次 FA 确认。")

if __name__ == "__main__":
    asyncio.run(main())
