# ble/constants.py
from config import BLE_DEVICE_ADDRESS, BLE_NOTIFY_UUID

# 设备地址与特征值
DEVICE_ADDRESS = BLE_DEVICE_ADDRESS
NOTIFY_UUID = BLE_NOTIFY_UUID

# 蓝牙状态枚举
STATE_DISCONNECTED = "disconnected"
STATE_CONNECTING = "connecting"
STATE_SYNCING = "syncing"
STATE_READY = "ready"
STATE_LOST = "lost"
STATE_SLEEPING = "sleeping"

# 测量阶段
PHASE_WEIGHING = "weighing"
PHASE_ANALYZING = "analyzing"
PHASE_DONE = "done"
PHASE_ERROR = "error"

# 事件类型
EVENT_BLE_STATE = "ble_state"
EVENT_STATUS = "status"
EVENT_PACKET1 = "packet1"
EVENT_FULL_RESULT = "full_result"
EVENT_SLOT_INFO = "slot_info"
EVENT_OCCUPIED_SLOTS = "occupied_slots_update"
EVENT_AUTO_REDIRECT = "auto_redirect"
EVENT_GUEST_RESTAND = "guest_need_restand"