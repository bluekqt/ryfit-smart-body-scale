# ble/sync_manager.py
import asyncio
import time
from datetime import datetime
from .core import send_cmd_async
from .protocol import is_valid_measurement
from models.user_dao import get_user_by_slot, get_user_by_id, add_user
from models.measurement_dao import add_measurement, record_exists
from models.settings_dao import get_settings
from config import SYNC_DELAY_SECONDS, SYNC_HISTORY_TIMEOUT, SYNC_A5_WAIT

class SyncManager:
    """管理历史数据同步流程"""

    def __init__(self, slot_manager):
        self.slot_manager = slot_manager
        self.sync_in_progress = False
        self.first_sync_done = False
        self._sync_first_pkt = {}       # slot: (seq, weight, fat, water, timestamp)
        self._sync_saved_count = 0
        self._lock = asyncio.Lock()
        self._emit = None               # 由 inject_emitter 注入，用于推送同步事件

    # ---------- 供外部调用的处理函数 ----------
    def handle_sync_packet1(self, p1):
        """处理同步模式下的 packet1"""
        if not self.sync_in_progress or not p1.get('is_sync'):
            return
        self._sync_first_pkt[p1['slot']] = (
            p1['seq'], p1['weight'], p1['fat'], p1['water'], p1['timestamp']
        )

    def handle_sync_packet2(self, p2):
        """处理同步模式下的 packet2，配对并存储"""
        if not self.sync_in_progress or not p2.get('is_sync'):
            return
        slot = p2['slot']
        if slot not in self._sync_first_pkt:
            return
        seq, weight, fat, water, ts = self._sync_first_pkt.pop(slot)
        if not is_valid_measurement(p2, fat, water):
            return

        # 获取或创建本地用户
        local = get_user_by_slot(slot)
        if local:
            uid = str(local['id'])
            name = local['name']
            height = local['height']
            age = local['age']
            gender = local['gender']
        else:
            b5_info = self.slot_manager.get_slot_info(slot) or {}
            height = b5_info.get('height', 170)
            age = b5_info.get('age', 30)
            gender = b5_info.get('gender', '男')
            new_id = add_user(f"用户P{slot}", height, age, gender, slot, 'fixed')
            local = get_user_by_id(new_id)
            uid = str(local['id'])
            name = local['name']
            # 更新槽位信息
            self.slot_manager.handle_b5({'slot': slot, 'height': height, 'age': age, 'gender': gender})

        height_m = height / 100.0
        bmi_val = round(weight / (height_m ** 2), 1)
        measured_at = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

        if not record_exists(int(uid) if uid.isdigit() else 0, measured_at):
            add_measurement(
                user_id=int(uid),
                weight=weight,
                bmi=bmi_val,
                fat=fat,
                water=water,
                muscle=p2['muscle'],
                bone=p2['bone'],
                bmr=p2['bmr'],
                sub_fat=p2['sub_fat'],
                visceral_fat=p2['visceral_fat'],
                body_age=p2['body_age'],
                measured_at=measured_at
            )
            self._sync_saved_count += 1

    # ---------- 同步主流程 ----------
    async def start_sync(self):
        """执行一次完整的历史同步"""
        if self.sync_in_progress:
            return
        async with self._lock:
            self.sync_in_progress = True
            try:
                self._sync_first_pkt.clear()
                self._sync_saved_count = 0

                # 发送 A5 查询槽位，最多重试 2 次
                slots = []
                for attempt in range(1, 3):
                    await send_cmd_async(bytes.fromhex("A5"))
                    await asyncio.sleep(SYNC_A5_WAIT)
                    slots = self.slot_manager.get_scale_slots()
                    if slots:
                        break
                    print(f"[Sync] 未收到槽位信息，重试第 {attempt} 次...")
                else:
                    print("[Sync] 同步：无已注册槽位，跳过")
                    return

                # 清理本地孤立用户（仅在收到有效槽位信息后）
                self.slot_manager.clean_orphaned_fixed_users()

                print(f"[Sync] 同步：处理 {len(slots)} 个槽位")
                for slot in slots:
                    await send_cmd_async(bytearray([0xC1, slot]))
                    await asyncio.sleep(SYNC_HISTORY_TIMEOUT)

                    settings = get_settings()
                    if self._sync_saved_count > 0 and settings.get('auto_delete_after_sync'):
                        await send_cmd_async(bytearray([0xC2, slot]))
                        print(f"[Sync] 同步：已清空槽位 {slot}")
                    else:
                        print(f"[Sync] 同步：槽位 {slot} 无新数据或未开启自动清除")

                print(f"[Sync] 同步完成，保存 {self._sync_saved_count} 条")
            except Exception as e:
                print(f"[Sync] 同步异常: {e}")
            finally:
                self.sync_in_progress = False
                self._sync_first_pkt.clear()
                self.first_sync_done = True

    async def delayed_sync(self):
        """延迟一段时间后开始同步，若正在测量则推迟"""
        await asyncio.sleep(SYNC_DELAY_SECONDS)
        await self.start_sync()