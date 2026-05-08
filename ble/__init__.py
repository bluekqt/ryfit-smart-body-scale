# ble/__init__.py
import asyncio
import time
import threading
from .core import (
    start_ble_loop, state_machine, is_connected,
    send_cmd_sync, send_cmd_async, update_activity,
    set_notification_callback, set_on_ready_callback
)
from .session import MeasurementSession
from .slot_manager import SlotManager
from .sync_manager import SyncManager
from .handlers import NotificationHandler
from .protocol import make_c0_cmd, make_a1_cmd
from config import A1_RESPONSE_TIMEOUT, A2_RESPONSE_TIMEOUT

# ---- 全局 emitter（由 app.py 注入） ----
_emit_socket = None

def inject_emitter(emit_func):
    """注入 WebSocket 发射器，供各模块直接推送前端"""
    global _emit_socket
    _emit_socket = emit_func
    # 向各需要推送的模块设置 emitter
    session._emit = emit_func
    slot_manager._emit = emit_func
    state_machine._emit = emit_func
    sync_manager._emit = emit_func

# ---- 全局 FB 应答回调（用于 register_user / delete_slot 的同步等待） ----
_fb_handler = None

def _set_fb_handler(handler):
    global _fb_handler
    _fb_handler = handler

def _call_fb_handler(resp):
    if _fb_handler:
        _fb_handler(resp)

# ---- 全局实例 ----
session = MeasurementSession()
slot_manager = SlotManager()
sync_manager = SyncManager(slot_manager)

# 给 state_machine 也设置 emitter（后面会注入）
state_machine._emit = None

# ---- 注册数据分发回调 ----
def _setup_handlers():
    handler = NotificationHandler(session, slot_manager, sync_manager, _call_fb_handler)
    set_notification_callback(handler.handle)

_setup_handlers()

# ---- 蓝牙就绪回调：优先发送待定 C0，然后同步（避开测量） ----
async def _on_ble_ready():
    # 1. 如果有暂存的 C0，立即发送
    session.send_pending_c0()
    
    # 2. 如果正在测量，等待测量结束
    while session.request_sent:
        await asyncio.sleep(2)
    
    # 3. 启动延迟同步
    await sync_manager.delayed_sync()

# 将就绪回调注册到 core，当蓝牙重新连接并 READY 时会自动执行
set_on_ready_callback(_on_ble_ready)

# ---- 高层 API ----

def switch_user(slot, height_cm, age, gender, user_id=None, mode=None, force=False):
    session.switch_user(slot, height_cm, age, gender, user_id, mode, force)

def register_user(slot, height_cm, age, gender, user_id=None, mode=None):
    """注册用户到秤：发送 A1 激活 + C0 切换"""
    if not is_connected():
        print("[API] 蓝牙未连接，无法注册")
        return
    a1_event = threading.Event()
    def on_fb(resp):
        if resp and resp[0] == 'A1_RESPONSE':
            a1_event.set()
    _set_fb_handler(on_fb)
    send_cmd_sync(make_a1_cmd(slot, height_cm, age, gender))
    if a1_event.wait(timeout=A1_RESPONSE_TIMEOUT):
        print("  收到 A1 应答，继续发送 C0")
    else:
        print("  ⚠ 未收到 A1 应答，仍继续发送 C0")
    _set_fb_handler(None)
    time.sleep(0.5)
    send_cmd_sync(make_c0_cmd(slot, height_cm, age, gender))
    # 更新会话状态
    session.current_slot = slot
    session.current_mode = mode
    if user_id:
        session.current_user_id = str(user_id)
    print(f"[API] 已注册槽位{slot}")

def reset_user_state():
    session.reset()

def reset_measurement():
    session.reset_measurement()

def query_slots():
    send_cmd_sync(bytes.fromhex("A5"))
    print("[API] 已发送 A5")

def delete_slot(slot):
    """删除秤上槽位，返回是否成功"""
    if not is_connected():
        print("[API] 蓝牙未连接，无法删除")
        return False
    a2_event = threading.Event()
    last_status = None
    def on_fb(resp):
        nonlocal last_status
        if resp and resp[0] == 'A2_RESPONSE':
            last_status = resp[1]
            a2_event.set()
    _set_fb_handler(on_fb)
    send_cmd_sync(bytearray([0xA2, slot]))
    print(f"[API] 已发送 A2 删除槽位{slot}，等待应答...")
    if a2_event.wait(timeout=A2_RESPONSE_TIMEOUT) and last_status == 0x00:
        print("  收到 A2 应答，删除成功")
        slot_manager.remove_slot(slot)
        _set_fb_handler(None)
        return True
    elif last_status is not None:
        print(f"  删除失败，状态码: {last_status:02X}")
        _set_fb_handler(None)
        return False
    else:
        print("  ⚠ 未收到 A2 应答")
        _set_fb_handler(None)
        return False

def fetch_history(slot):
    send_cmd_sync(bytearray([0xC1, slot]))
    print(f"[API] 已发送 C1 请求历史")

async def sync_history():
    await sync_manager.start_sync()

async def delayed_sync():
    await sync_manager.delayed_sync()