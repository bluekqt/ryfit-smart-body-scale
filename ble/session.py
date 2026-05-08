# ble/session.py
import time
from datetime import datetime
from . import constants as const
from .core import send_cmd_sync, update_activity, is_connected, state_machine
from .protocol import make_c0_cmd, is_valid_measurement
from models.user_dao import get_user_by_slot, get_user_by_id
from models.measurement_dao import add_measurement
from config import (
    SUPPRESS_D2_AFTER_C0, AUTO_C0_COOLDOWN
)

class MeasurementSession:
    """管理一次完整的测量会话"""

    def __init__(self):
        self._emit = None        # 由 `inject_emitter` 注入
        self.reset()
        self.pending_c0 = None   # 待发送的 C0 参数 (slot, height, age, gender) 或 None

    def reset(self):
        """重置所有状态到初始值"""
        self.current_user_id = None
        self.current_slot = None
        self.current_mode = None
        self.guest_params = {"height": 170, "age": 30, "gender": "男"}

        self.request_sent = False
        self.request_time = 0
        self.last_weight = None
        self.last_fat = None
        self.last_water = None

        self.last_auto_c0_time = 0
        self.suppress_d2_until = 0.0
        self.pending_c0 = None

    def switch_user(self, slot, height_cm, age, gender, user_id=None, mode=None, force=False):
        """切换当前测量用户"""
        if not force and (slot == self.current_slot and (user_id is None or str(user_id) == self.current_user_id)):
            print(f"[Session] 槽位 {slot} 已活跃，略过")
            return

        self.current_slot = slot
        if user_id is not None:
            self.current_user_id = str(user_id)
        if mode is not None:
            self.current_mode = mode

        if slot == 9:
            self.guest_params = {"height": height_cm, "age": age, "gender": gender}

        update_activity()

        if state_machine.state == const.STATE_READY:
            self._send_c0(height_cm, age, gender)
            self.reset_measurement()
        else:
            # 蓝牙未就绪，暂存切换请求
            self.pending_c0 = (slot, height_cm, age, gender)
            print("[Session] 蓝牙未就绪，切换请求已暂存")

    def send_pending_c0(self):
        """当蓝牙就绪后调用，发送暂存的 C0 请求"""
        if self.pending_c0 is None:
            return
        if state_machine.state != const.STATE_READY:
            return
        slot, height_cm, age, gender = self.pending_c0
        print(f"[Session] 蓝牙就绪，补发暂存的 C0 (槽位{slot})")
        self.pending_c0 = None
        self._send_c0(height_cm, age, gender)
        self.reset_measurement()

    def reset_measurement(self):
        """重置测量相关标志，准备接收新数据"""
        self.request_sent = False
        self.last_weight = None
        self.last_fat = None
        self.last_water = None
        self.last_auto_c0_time = time.time()
        self.suppress_d2_until = time.time() + SUPPRESS_D2_AFTER_C0
        if self._emit:
            self._emit('measurement_reset', {})

    def _send_c0(self, height_cm, age, gender):
        """向秤发送 C0 切换用户"""
        if not is_connected() or self.current_slot is None:
            return
        now = time.time()
        if now - self.last_auto_c0_time < AUTO_C0_COOLDOWN:
            return
        self.last_auto_c0_time = now
        cmd = make_c0_cmd(self.current_slot, height_cm, age, gender)
        send_cmd_sync(cmd)
        print(f"[Session] 已发送 C0 切换槽位{self.current_slot}")

    def _get_user_params(self):
        """获取当前用户的 (height, age, gender)，失败返回 None"""
        if self.current_slot == 9:
            return (self.guest_params['height'],
                    self.guest_params['age'],
                    self.guest_params['gender'])
        # 固定用户
        if self.current_user_id:
            user = get_user_by_id(self.current_user_id)
            if user:
                return (user['height'], user['age'], user['gender'])
        return None

    def handle_d2(self, weight):
        """处理实时体重数据 D2，并可能在空闲时自动发送 C0"""
        if self.suppress_d2_until and time.time() < self.suppress_d2_until:
            return
        if weight is None or weight <= 0:
            return

        # 空闲自动 C0：如果槽位有效且未在测量，且能获取到用户参数，则发送
        if not self.request_sent and self.current_slot is not None \
                and state_machine.state == const.STATE_READY:
            params = self._get_user_params()
            if params:
                now = time.time()
                if now - self.last_auto_c0_time >= AUTO_C0_COOLDOWN:
                    print("[Session] 自动补发 C0（D2 触发）")
                    self._send_c0(*params)
                    self.reset_measurement()
                    return   # 马上就会开始新的称重流程

        if not self.request_sent and self.current_slot is not None and state_machine.state == const.STATE_READY:
            if self._emit:
                self._emit(const.EVENT_MEASUREMENT_PROGRESS, {'phase': const.PHASE_WEIGHING, 'weight': weight})

    def handle_packet1(self, p1):
        """处理第一包数据"""
        if self.current_mode == 'test' and p1['slot'] != 9:
            return

        if self._emit:
            self._emit(const.EVENT_PACKET1, {'weight': p1['weight'], 'fat': p1['fat'], 'water': p1['water'], 'slot': p1['slot']})

        if not self.request_sent and state_machine.state == const.STATE_READY:
            # 自动识别固定用户
            if self.current_mode != 'test' and (self.current_user_id is None or self.current_slot != p1['slot']):
                user = get_user_by_slot(p1['slot'])
                if user:
                    self.current_user_id = str(user['id'])
                    self.current_slot = p1['slot']
                    self.current_mode = 'fixed'
                    if self._emit:
                        self._emit(const.EVENT_AUTO_REDIRECT, {'user_id': self.current_user_id})

            self.last_weight = p1['weight']
            self.last_fat = p1['fat']
            self.last_water = p1['water']
            self.request_sent = True
            self.request_time = time.time()
            # 不再发射 analyzing 事件

    def handle_packet2(self, p2):
        """处理第二包数据"""
        if self.current_mode == 'test' and p2['slot'] != 9:
            return

        if not self.request_sent or self.last_weight is None or state_machine.state != const.STATE_READY:
            return

        if not is_valid_measurement(p2, self.last_fat, self.last_water):
            if self._emit:
                self._emit(const.EVENT_MEASUREMENT_PROGRESS, {'phase': const.PHASE_ERROR})
            return

        user = get_user_by_id(self.current_user_id) if self.current_user_id else None
        if not user:
            user = {'height': 170, 'name': '游客', 'age': 30, 'gender': '男'}
        h_m = user['height'] / 100.0
        bmi = round(self.last_weight / (h_m ** 2), 1)

        result = {
            'user_id': self.current_user_id or 'guest',
            'user_name': user.get('name', '游客'),
            'slot': self.current_slot or 9,
            'type': self.current_mode or 'test',
            'weight': self.last_weight,
            'bmi': bmi,
            'fat': self.last_fat,
            'water': self.last_water,
            'muscle': p2['muscle'],
            'bone': p2['bone'],
            'bmr': p2['bmr'],
            'sub_fat': p2['sub_fat'],
            'visceral_fat': p2['visceral_fat'],
            'body_age': p2['body_age'],
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        if self._emit:
            self._emit(const.EVENT_FULL_RESULT, {'result': result})

        if self.current_mode != 'test' and self.current_user_id:
            add_measurement(
                user_id=int(self.current_user_id),
                weight=self.last_weight,
                bmi=bmi,
                fat=self.last_fat,
                water=self.last_water,
                muscle=p2['muscle'],
                bone=p2['bone'],
                bmr=p2['bmr'],
                sub_fat=p2['sub_fat'],
                visceral_fat=p2['visceral_fat'],
                body_age=p2['body_age'],
                measured_at=result['time']
            )

        if self._emit:
            self._emit(const.EVENT_MEASUREMENT_PROGRESS, {'phase': const.PHASE_DONE})

        self.request_sent = False
        self.last_weight = None
        self.last_fat = None
        self.last_water = None
        update_activity()

    def get_current_slot(self):
        return self.current_slot