# ble/core.py
import asyncio
import struct
import time
from bleak import BleakClient
from . import constants as const
from .protocol import make_time_sync, make_ack
from config import (
    BLE_DEVICE_ADDRESS, BLE_CONNECT_TIMEOUT, BLE_RECONNECT_DELAY,
    BLE_HEARTBEAT_INTERVAL, BLE_IDLE_SLEEP_SECONDS
)

# 连接状态机
from .state_machine import BLEStateMachine
state_machine = BLEStateMachine()

ble_client = None
ble_loop = None
_heartbeat_task = None
_idle_monitor_task = None
_last_user_activity = time.time()
_connection_start_time = None

# 数据接收回调
_notification_callback = None

# 时间同步事件（本地 asyncio.Event）
_time_sync_event = None

# 蓝牙就绪回调（外部注册，用于触发同步等）
_on_ready_callback = None

def set_notification_callback(callback):
    """注册数据接收回调。callback 接收 bytes 参数"""
    global _notification_callback
    _notification_callback = callback

def set_on_ready_callback(callback):
    """注册蓝牙连接就绪后的回调（异步函数）"""
    global _on_ready_callback
    _on_ready_callback = callback

def update_activity():
    """用户操作时调用，重置空闲计时器。线程安全，仅更新时间戳"""
    global _last_user_activity
    _last_user_activity = time.time()

async def _idle_monitor():
    """每 10 秒检查一次，若超过 BLE_IDLE_SLEEP_SECONDS 无操作则休眠"""
    while True:
        await asyncio.sleep(10)
        if state_machine.state != const.STATE_READY:
            continue
        elapsed = time.time() - _last_user_activity
        if elapsed >= BLE_IDLE_SLEEP_SECONDS:
            print(f"[BLE] 空闲 {elapsed:.0f} 秒，进入休眠")
            state_machine.enter_sleeping()
            _stop_connection()
            break

def _stop_connection():
    """断开蓝牙并清理所有后台任务"""
    global ble_client, _heartbeat_task, _idle_monitor_task, _connection_start_time
    if _heartbeat_task:
        _heartbeat_task.cancel()
        _heartbeat_task = None
    if _idle_monitor_task:
        _idle_monitor_task.cancel()
        _idle_monitor_task = None
    if ble_client:
        try:
            asyncio.ensure_future(ble_client.disconnect())
        except:
            pass
        ble_client = None
    _connection_start_time = None

async def heartbeat_loop():
    while ble_client and ble_client.is_connected:
        await asyncio.sleep(BLE_HEARTBEAT_INTERVAL)
        if ble_client and ble_client.is_connected:
            try:
                now = int(time.time())
                await ble_client.write_gatt_char(
                    const.NOTIFY_UUID,
                    b'\xFA\xF8' + struct.pack('<I', now),
                    response=False
                )
                if _connection_start_time:
                    elapsed = time.time() - _connection_start_time
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    print(f"[BLE] ♥ 心跳：发送时间同步（已连接 {mins}分{secs}秒）")
                else:
                    print("[BLE] ♥ 心跳：发送时间同步")
            except Exception as e:
                print(f"[BLE] 心跳发送失败: {e}")
                break

def _internal_notification_handler(sender, data):
    """内部通知处理——转发给外部注册的回调，并处理时间同步应答"""
    global _notification_callback, _time_sync_event
    raw = bytes(data)
    # 时间同步应答
    if len(raw) == 2 and raw[:2] == b'\xFB\xF8':
        if _time_sync_event:
            _time_sync_event.set()
        # 也传给外部回调（如需要）
        if _notification_callback:
            _notification_callback(raw)
        return
    print(f"[BLE]  ← 收到: {raw.hex()}")
    if _notification_callback:
        _notification_callback(raw)

async def connect_ble():
    global ble_client, ble_loop, _heartbeat_task, _idle_monitor_task, _connection_start_time, _time_sync_event
    ble_loop = asyncio.get_running_loop()
    while True:
        if not state_machine.can_auto_reconnect:
            state_machine.transition_to(const.STATE_SLEEPING)
            await asyncio.sleep(2)
            continue
        try:
            state_machine.transition_to(const.STATE_DISCONNECTED)
            client = BleakClient(BLE_DEVICE_ADDRESS, timeout=BLE_CONNECT_TIMEOUT)
            await client.connect()
            ble_client = client
            state_machine.transition_to(const.STATE_CONNECTING)
            print("[BLE] 蓝牙已连接，订阅通知...")
            await client.start_notify(const.NOTIFY_UUID, _internal_notification_handler)
            print("[BLE] 通知订阅完成")
            await asyncio.sleep(3)

            # 发送时间同步并等待应答
            _time_sync_event = asyncio.Event()
            print("[BLE] 发送时间同步")
            await client.write_gatt_char(const.NOTIFY_UUID, make_time_sync(), response=False)
            try:
                await asyncio.wait_for(_time_sync_event.wait(), timeout=4.5)
                print("[BLE] 时间同步成功")
            except asyncio.TimeoutError:
                print("[BLE] ⚠ 时间同步未收到应答，假定已就绪")
            _time_sync_event = None

            state_machine.transition_to(const.STATE_READY)
            _connection_start_time = time.time()

            # 启动心跳
            if _heartbeat_task:
                _heartbeat_task.cancel()
            _heartbeat_task = asyncio.create_task(heartbeat_loop())

            # 启动空闲监控
            if _idle_monitor_task:
                _idle_monitor_task.cancel()
            _idle_monitor_task = asyncio.create_task(_idle_monitor())
            update_activity()

            # 调用就绪回调（例如启动历史同步）
            if _on_ready_callback:
                asyncio.create_task(_on_ready_callback())

            while ble_client and ble_client.is_connected:
                await asyncio.sleep(1)

            # 连接丢失处理
            if state_machine.state != const.STATE_SLEEPING:
                state_machine.transition_to(const.STATE_LOST)
                print("[BLE] 连接丢失，稍后重连...")

        except Exception as e:
            if state_machine.state != const.STATE_SLEEPING:
                state_machine.transition_to(const.STATE_LOST)
                print(f"[BLE] 连接异常: {e}")
            ble_client = None
            await asyncio.sleep(BLE_RECONNECT_DELAY)
        finally:
            _stop_connection()

def start_ble_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(connect_ble())

def is_connected():
    return ble_client is not None and ble_client.is_connected

async def send_cmd_async(cmd):
    if ble_client and ble_client.is_connected:
        print(f"[BLE]  → 发送: {cmd.hex()}")
        await ble_client.write_gatt_char(const.NOTIFY_UUID, cmd, response=False)

def send_cmd_sync(cmd):
    if ble_client and ble_loop and ble_client.is_connected:
        print(f"[BLE]  → 发送: {cmd.hex()}")
        asyncio.run_coroutine_threadsafe(
            ble_client.write_gatt_char(const.NOTIFY_UUID, cmd, response=False),
            ble_loop
        )