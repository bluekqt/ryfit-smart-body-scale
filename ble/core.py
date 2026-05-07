# ble/core.py
import asyncio
import struct
import time
from bleak import BleakClient
from . import constants as const
from .event_bus import emit, subscribe
from .state_machine import BLEStateMachine
from .protocol import make_time_sync, make_ack
from config import (
    BLE_DEVICE_ADDRESS, BLE_CONNECT_TIMEOUT, BLE_RECONNECT_DELAY,
    BLE_HEARTBEAT_INTERVAL, BLE_IDLE_SLEEP_SECONDS
)

state_machine = BLEStateMachine()
ble_client = None
ble_loop = None
_heartbeat_task = None
_idle_monitor_task = None          # 空闲监控任务
_last_user_activity = time.time()
_connection_start_time = None

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

def notification_handler(sender, data):
    from .protocol import (
        parse_d2, parse_packet1, parse_packet2, parse_b5, parse_fb
    )
    raw = bytes(data)
    if len(raw) == 2 and raw[:2] == b'\xFB\xF8':
        emit('time_sync_ok')
        return
    print(f"[BLE]  ← 收到: {raw.hex()}")
    d2 = parse_d2(raw)
    if d2:
        emit('d2_received', weight=d2['weight'])
        return
    p1 = parse_packet1(raw)
    if p1:
        emit('packet1_received', p1=p1)
        if ble_client and ble_client.is_connected:
            asyncio.ensure_future(ble_client.write_gatt_char(const.NOTIFY_UUID, make_ack(raw), response=False))
        return
    p2 = parse_packet2(raw)
    if p2:
        emit('packet2_received', p2=p2)
        if ble_client and ble_client.is_connected:
            asyncio.ensure_future(ble_client.write_gatt_char(const.NOTIFY_UUID, make_ack(raw), response=False))
        return
    b5 = parse_b5(raw)
    if b5:
        emit('slot_info', info=b5)
        if ble_client and ble_client.is_connected:
            asyncio.ensure_future(ble_client.write_gatt_char(const.NOTIFY_UUID, make_ack(raw), response=False))
        return
    fb = parse_fb(raw)
    if fb:
        emit('fb_response', resp=fb)
        if fb[0] in ('A5_RESPONSE', 'A2_RESPONSE'):
            if ble_client and ble_client.is_connected:
                asyncio.ensure_future(ble_client.write_gatt_char(const.NOTIFY_UUID, make_ack(raw), response=False))
        return

async def connect_ble():
    global ble_client, ble_loop, _heartbeat_task, _idle_monitor_task, _connection_start_time
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
            await client.start_notify(const.NOTIFY_UUID, notification_handler)
            print("[BLE] 通知订阅完成")
            await asyncio.sleep(3)

            print("[BLE] 发送时间同步")
            await client.write_gatt_char(const.NOTIFY_UUID, make_time_sync(), response=False)
            sync_ok = asyncio.Event()
            def on_sync_ok():
                sync_ok.set()
            subscribe('time_sync_ok', on_sync_ok)
            try:
                await asyncio.wait_for(sync_ok.wait(), timeout=4.5)
                print("[BLE] 时间同步成功")
            except asyncio.TimeoutError:
                print("[BLE] ⚠ 时间同步未收到应答，假定已就绪")

            state_machine.transition_to(const.STATE_READY)
            _connection_start_time = time.time()

            # 启动首次同步
            from .service import sync_history, first_sync_done
            if not first_sync_done:
                asyncio.create_task(sync_history())

            # 启动心跳
            if _heartbeat_task:
                _heartbeat_task.cancel()
            _heartbeat_task = asyncio.create_task(heartbeat_loop())

            # 启动空闲监控（只更新时间戳，不创建新任务）
            if _idle_monitor_task:
                _idle_monitor_task.cancel()
            _idle_monitor_task = asyncio.create_task(_idle_monitor())
            update_activity()   # 设置初始活动时间

            while ble_client and ble_client.is_connected:
                await asyncio.sleep(1)

            if state_machine.state != const.STATE_SLEEPING:
                from .service import first_sync_done
                first_sync_done = False
                state_machine.transition_to(const.STATE_LOST)
                print("[BLE] 连接丢失，稍后重连...")

        except Exception as e:
            if state_machine.state != const.STATE_SLEEPING:
                from .service import first_sync_done
                first_sync_done = False
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