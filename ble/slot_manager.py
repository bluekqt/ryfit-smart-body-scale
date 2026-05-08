# ble/slot_manager.py
from models.user_dao import get_user_by_slot, add_user, get_all_users, delete_user as delete_local_user


class SlotManager:
    """管理秤上槽位信息，与本地用户数据库对齐"""

    def __init__(self):
        self._slot_info = {}
        self._emit = None          # 由 `inject_emitter` 注入

    # ---------- 槽位数据处理 ----------
    def handle_b5(self, info):
        """处理收到的 B5 槽位信息包，自动创建缺失的固定用户"""
        slot = info.get('slot')
        if not isinstance(slot, int) or slot < 1 or slot > 8:
            return
        self._slot_info[slot] = info
        self._ensure_fixed_user_exists(slot, info)
        self._push_occupied()

    def remove_slot(self, slot):
        """移除本地记录的槽位"""
        self._slot_info.pop(slot, None)
        self._push_occupied()

    def get_scale_slots(self):
        """返回秤上当前存在的槽位列表"""
        return list(self._slot_info.keys())

    def get_slot_info(self, slot):
        return self._slot_info.get(slot)

    # ---------- 本地用户对齐 ----------
    def _ensure_fixed_user_exists(self, slot, info):
        """若本地无该槽位的固定用户，则自动创建"""
        local = get_user_by_slot(slot)
        if local:
            return
        height = info.get('height', 170)
        age = info.get('age', 30)
        gender = info.get('gender', '男')
        name = f"用户P{slot}"
        add_user(name, height, age, gender, slot, 'fixed')
        print(f"[SlotMgr] 自动创建固定用户: {name} (槽位 {slot})")

    def clean_orphaned_fixed_users(self):
        """删除本地存在但秤上已没有的固定用户"""
         # 如果还没收到过任何 B5 数据，不清除
        if not self._slot_info:
            return
        scale_slots = set(self._slot_info.keys())
        local_users = get_all_users()
        for u in local_users:
            if u['mode'] == 'fixed' and u.get('slot') and u['slot'] != 9:
                if u['slot'] not in scale_slots:
                    print(f"[SlotMgr] 清理已缺失的固定用户: {u['name']} (槽位 {u['slot']})")
                    delete_local_user(u['id'])

    def get_occupied_slots(self):
        """返回所有占用的槽位（秤上 + 本地固定用户）"""
        occupied = set(self._slot_info.keys())
        from models.user_dao import get_occupied_slots as local_occupied
        for s in local_occupied():
            occupied.add(s)
        return sorted(occupied)

    def _push_occupied(self):
        if self._emit:
            self._emit('occupied_slots_update', {'occupied_slots': self.get_occupied_slots()})