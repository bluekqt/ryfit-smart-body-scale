# ble/service.py
import asyncio
import time
import threading
from datetime import datetime
from .core import send_cmd_sync, send_cmd_async, update_activity, is_connected, state_machine
from .protocol import make_a1_cmd, make_c0_cmd
from .event_bus import subscribe, emit
from . import constants as const
from models.user_dao import (
    get_user_by_id, get_user_by_slot, add_user,
    get_all_users, delete_user as delete_local_user
)
from models.measurement_dao import add_measurement, record_exists
from models.settings_dao import get_settings
from config import AUTO_C0_COOLDOWN, SYNC_DELAY_SECONDS

# 当前用户上下文
current_user_id = None
current_slot = None
current_mode = None
guest_params = {"height": 170, "age": 30, "gender": "男"}

# 测量状态
request_sent = False
request_time = 0
last_weight = last_fat = last_water = None
last_auto_c0_time = 0
last_measurement_done_time = 0

# 待发送的命令
pending_user = None

# 槽位占用（从秤同步的 B5 信息）
slot_delete_id = {}

# 同步控制
sync_in_progress = False
sync_lock = asyncio.Lock()
first_sync_done = False
sync_mode = False
sync_first_pkt = {}
sync_saved_count = 0

# 事件
a1_event = threading.Event()
a2_event = threading.Event()
last_a2_status = None

# 临时屏蔽 D2 时间戳
suppress_d2_until = 0.0


# ------- 辅助函数 -------
def ensure_fixed_user_exists(slot, info):
    """根据 B5 信息确保本地存在对应的固定用户，若不存在则创建"""
    if not isinstance(slot, int) or slot < 1 or slot > 8:
        return
    # 查本地是否已有该槽位的固定用户
    local = get_user_by_slot(slot)
    if local:
        return
    # 若不存在，则创建一个
    height = info.get('height', 170)
    age = info.get('age', 30)
    gender = info.get('gender', '男')
    name = f"用户P{slot}"
    new_id = add_user(name, height, age, gender, slot, 'fixed')
    print(f"[BLE] 自动创建固定用户: {name} (槽位 {slot})")


def clean_orphaned_fixed_users(scale_slots):
    """删除本地存在但秤上已没有的固定用户"""
    local_users = get_all_users()
    for u in local_users:
        if u['mode'] == 'fixed' and u.get('slot') and u['slot'] != 9:
            if u['slot'] not in scale_slots:
                print(f"[BLE] 清理已缺失的固定用户: {u['name']} (槽位 {u['slot']})")
                delete_local_user(u['id'])


def _update_occupied_slots():
    occupied = set()
    for s in slot_delete_id.keys():
        if isinstance(s, int) and 1 <= s <= 8:
            occupied.add(s)
    from models.user_dao import get_occupied_slots as local_occupied
    for s in local_occupied():
        occupied.add(s)
    emit(const.EVENT_OCCUPIED_SLOTS, occupied_slots=sorted(occupied))


# ------- 用户操作接口 -------
def reset_user_state():
    global current_user_id, current_slot, current_mode, last_weight, last_fat, last_water, request_sent
    current_user_id = None; current_slot = None; current_mode = None
    last_weight = last_fat = last_water = None; request_sent = False
    print("[BLE]   重置用户状态")


def switch_user(slot, height_cm, age, gender, user_id=None, mode=None, force=False):
    global current_user_id, current_slot, current_mode, guest_params, pending_user
    if not force and (slot == current_slot and (user_id is None or str(user_id) == current_user_id)):
        print(f"[BLE]   槽位 {slot} 已活跃，略过")
        return
    current_slot = slot
    if user_id is not None: current_user_id = str(user_id)
    if mode is not None: current_mode = mode
    if slot == 9: guest_params = {"height": height_cm, "age": age, "gender": gender}
    update_activity()

    if state_machine.state == const.STATE_READY:
        _wait_and_send_c0(slot, height_cm, age, gender)
        pending_user = None
        reset_measurement()
    else:
        pending_user = {'slot': slot, 'height': height_cm, 'age': age, 'gender': gender, 'mode': mode}
        print("[BLE] 蓝牙未就绪，切换请求已暂存")


def register_user(slot, height_cm, age, gender, user_id=None, mode=None):
    global pending_user, current_user_id, current_mode, current_slot
    if user_id is not None: current_user_id = str(user_id)
    if mode is not None: current_mode = mode
    current_slot = slot
    update_activity()

    if state_machine.state == const.STATE_READY:
        _wait_and_send_a1_c0(slot, height_cm, age, gender)
        pending_user = None
    else:
        pending_user = {'slot': slot, 'height': height_cm, 'age': age, 'gender': gender, 'mode': mode, 'need_a1': True}
        print("[BLE] 蓝牙未就绪，注册请求已暂存")


def _wait_and_send_c0(slot, h, a, gd):
    global last_auto_c0_time
    if request_sent:
        timeout = time.time() + 15
        while request_sent and time.time() < timeout: time.sleep(0.5)
    last_auto_c0_time = time.time()
    time.sleep(0.5)
    send_cmd_sync(make_c0_cmd(slot, h, a, gd))
    print(f"[BLE] 已发送 C0 切换槽位{slot}")


def _wait_and_send_a1_c0(slot, h, a, gd):
    if request_sent:
        timeout = time.time() + 15
        while request_sent and time.time() < timeout: time.sleep(0.5)
    a1_event.clear()
    send_cmd_sync(make_a1_cmd(slot, h, a, gd))
    if a1_event.wait(timeout=2.0):
        print("  收到 A1 应答，继续发送 C0")
    else:
        print("  ⚠ 未收到 A1 应答，仍继续发送 C0")
    time.sleep(0.5)
    send_cmd_sync(make_c0_cmd(slot, h, a, gd))
    print(f"[BLE] 已注册槽位{slot}")


def query_slots():
    send_cmd_sync(bytes.fromhex("A5"))
    print("[BLE] 已发送 A5")


def delete_slot(slot):
    global last_a2_status
    a2_event.clear()
    last_a2_status = None
    send_cmd_sync(bytearray([0xA2, slot]))
    print(f"[BLE] 已发送 A2 删除槽位{slot}，等待应答...")
    if a2_event.wait(timeout=3.0) and last_a2_status == 0x00:
        print("  收到 A2 应答，删除成功")
        if slot in slot_delete_id:
            del slot_delete_id[slot]
            _update_occupied_slots()
        return True
    elif last_a2_status is not None:
        print(f"  删除失败，状态码: {last_a2_status:02X}")
        return False
    else:
        print("  ⚠ 未收到 A2 应答")
        return False


def fetch_history(slot):
    send_cmd_sync(bytearray([0xC1, slot]))
    print(f"[BLE] 已发送 C1 请求历史")


# ------- 同步流程 -------
async def sync_history():
    global sync_in_progress, sync_mode, sync_first_pkt, sync_saved_count, first_sync_done
    if sync_in_progress: return
    sync_in_progress = True
    try:
        sync_mode = True
        sync_first_pkt.clear()
        sync_saved_count = 0
        # A5 查询，B5 已由事件处理器处理（包括自动创建用户）
        await send_cmd_async(bytes.fromhex("A5"))
        await asyncio.sleep(5)

        # 对齐槽位：删除本地多余的固定用户
        scale_slots = set(s for s in slot_delete_id if isinstance(s, int) and 1 <= s <= 8)
        clean_orphaned_fixed_users(scale_slots)
        _update_occupied_slots()

        slots = list(slot_delete_id.keys())
        if not slots:
            print("[BLE] 同步：无已注册槽位")
            return
        print(f"[BLE] 同步：处理 {len(slots)} 个槽位")
        for slot in slots:
            await send_cmd_async(bytearray([0xC1, slot]))
            await asyncio.sleep(20)
            if sync_saved_count > 0 and get_settings().get('auto_delete_after_sync'):
                await send_cmd_async(bytearray([0xC2, slot]))
                print(f"[BLE] 同步：已清空槽位 {slot}")
            else:
                print(f"[BLE] 同步：槽位 {slot} 无新数据或未开启自动清除")
        print(f"[BLE] 同步完成，保存 {sync_saved_count} 条")
    except Exception as e:
        print(f"[BLE] 同步异常: {e}")
    finally:
        sync_mode = False
        sync_first_pkt.clear()
        sync_in_progress = False
        first_sync_done = True


async def delayed_sync():
    await asyncio.sleep(SYNC_DELAY_SECONDS)
    if request_sent: asyncio.create_task(delayed_sync()); return
    if last_measurement_done_time > 0 and (time.time() - last_measurement_done_time < 5):
        asyncio.create_task(delayed_sync()); return
    await sync_history()


# ------- 事件处理 -------
def setup_event_handlers():
    from .protocol import is_valid_measurement

    def on_d2_received(weight):
        if suppress_d2_until and time.time() < suppress_d2_until: return
        if weight is None or weight <= 0: return
        if not request_sent and current_slot is not None and state_machine.state == const.STATE_READY:
            emit('measurement_progress', phase=const.PHASE_WEIGHING)

    def on_packet1_received(p1):
        global last_weight, last_fat, last_water, request_sent, request_time, current_user_id, current_slot, current_mode
        if current_mode == 'test' and p1['slot'] != 9: return
        if sync_mode and p1['is_sync']:
            sync_first_pkt[p1['slot']] = (p1['seq'], p1['weight'], p1['fat'], p1['water'], p1['timestamp'])
            return
        emit(const.EVENT_PACKET1, weight=p1['weight'], fat=p1['fat'], water=p1['water'], slot=p1['slot'])
        if not request_sent and state_machine.state == const.STATE_READY:
            if current_mode != 'test' and (current_user_id is None or current_slot != p1['slot']):
                user = get_user_by_slot(p1['slot'])
                if user:
                    current_user_id = str(user['id']); current_slot = p1['slot']; current_mode = 'fixed'
                    emit(const.EVENT_AUTO_REDIRECT, user_id=current_user_id)
            last_weight, last_fat, last_water = p1['weight'], p1['fat'], p1['water']
            request_sent = True; request_time = time.time()
            emit('measurement_progress', phase=const.PHASE_ANALYZING)

    def on_packet2_received(p2):
        global request_sent, last_weight, last_fat, last_water, last_measurement_done_time, sync_saved_count
        if current_mode == 'test' and p2['slot'] != 9: return
        if sync_mode and p2['is_sync'] and p2['slot'] in sync_first_pkt:
            seq, weight, fat, water, ts = sync_first_pkt.pop(p2['slot'])
            if not is_valid_measurement(p2, fat, water): return

            local = get_user_by_slot(p2['slot'])
            if local:
                uid = str(local['id']); name = local['name']; height = local['height']
                age = local['age']; gender = local['gender']
            else:
                b5_info = slot_delete_id.get(p2['slot'], {})
                height = b5_info.get('height', 170); age = b5_info.get('age', 30)
                gender = b5_info.get('gender', '男')
                new_id = add_user(f"用户P{p2['slot']}", height, age, gender, p2['slot'], 'fixed')
                local = get_user_by_id(new_id)
                uid = str(local['id']); name = local['name']
                _update_occupied_slots()
                print(f"[BLE] 自动创建固定用户: {name} (槽位 {p2['slot']})")

            height_m = height / 100.0; bmi_val = round(weight / (height_m ** 2), 1)
            measured_at = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            if not record_exists(int(uid) if uid.isdigit() else 0, measured_at):
                add_measurement(user_id=int(uid), weight=weight, bmi=bmi_val, fat=fat, water=water,
                                muscle=p2['muscle'], bone=p2['bone'], bmr=p2['bmr'],
                                sub_fat=p2['sub_fat'], visceral_fat=p2['visceral_fat'],
                                body_age=p2['body_age'], measured_at=measured_at)
                sync_saved_count += 1
            return

        if request_sent and last_weight is not None and state_machine.state == const.STATE_READY:
            if not is_valid_measurement(p2, last_fat, last_water):
                emit('measurement_progress', phase=const.PHASE_ERROR)
                user = get_user_by_id(current_user_id) if current_user_id else None
                h, a, gen = (170, 30, '男')
                if user: h, a, gen = user['height'], user['age'], user['gender']
                send_cmd_sync(make_c0_cmd(current_slot, h, a, gen))
            else:
                user = get_user_by_id(current_user_id) if current_user_id else None
                if not user: user = {'height': 170, 'name': '游客', 'age': 30, 'gender': '男'}
                h_m = user['height'] / 100.0; bmi = round(last_weight / (h_m ** 2), 1)
                result = {
                    'user_id': current_user_id or 'guest', 'user_name': user.get('name', '游客'),
                    'slot': current_slot or 9, 'type': current_mode or 'test',
                    'weight': last_weight, 'bmi': bmi, 'fat': last_fat, 'water': last_water,
                    'muscle': p2['muscle'], 'bone': p2['bone'], 'bmr': p2['bmr'],
                    'sub_fat': p2['sub_fat'], 'visceral_fat': p2['visceral_fat'],
                    'body_age': p2['body_age'], 'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                emit(const.EVENT_FULL_RESULT, result=result)
                if current_mode != 'test':
                    add_measurement(user_id=int(current_user_id), weight=last_weight, bmi=bmi,
                                    fat=last_fat, water=last_water, muscle=p2['muscle'], bone=p2['bone'],
                                    bmr=p2['bmr'], sub_fat=p2['sub_fat'], visceral_fat=p2['visceral_fat'],
                                    body_age=p2['body_age'], measured_at=result['time'])
                last_measurement_done_time = time.time(); update_activity()
                emit('measurement_progress', phase=const.PHASE_DONE)
            last_weight = last_fat = last_water = None; request_sent = False

    def on_slot_info(info):
        slot = info['slot']
        slot_delete_id[slot] = info
        ensure_fixed_user_exists(slot, info)
        _update_occupied_slots()

    def on_fb_response(resp):
        if resp[0] == 'A1_RESPONSE':
            a1_event.set()
        elif resp[0] == 'A2_RESPONSE':
            global last_a2_status
            last_a2_status = resp[1]
            a2_event.set()

    subscribe('d2_received', on_d2_received)
    subscribe('packet1_received', on_packet1_received)
    subscribe('packet2_received', on_packet2_received)
    subscribe('slot_info', on_slot_info)
    subscribe('fb_response', on_fb_response)


def reset_measurement():
    global request_sent, last_weight, last_fat, last_water, last_auto_c0_time, pending_user, suppress_d2_until
    request_sent = False; last_weight = last_fat = last_water = None
    last_auto_c0_time = time.time(); pending_user = None
    suppress_d2_until = time.time() + 2.0
    emit('measurement_reset')


setup_event_handlers()