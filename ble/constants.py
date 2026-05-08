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

# 测量阶段（驱动前端 UI）
PHASE_IDLE = "idle"             # 等待上秤
PHASE_WEIGHING = "weighing"     # 正在称重（D2 实时数据）
PHASE_ANALYZING = "analyzing"   # 正在分析（收到 Packet1 后）
PHASE_DONE = "done"             # 测量完成（有效 Packet2）
PHASE_ERROR = "error"           # 测量失败（无效 Packet2）

# 事件类型（WebSocket 推送用）
EVENT_BLE_STATE = "ble_state"
EVENT_MEASUREMENT_PROGRESS = "measurement_progress"
EVENT_PACKET1 = "packet1"
EVENT_FULL_RESULT = "full_result"
EVENT_SLOT_INFO = "slot_info"
EVENT_OCCUPIED_SLOTS = "occupied_slots_update"
EVENT_AUTO_REDIRECT = "auto_redirect"
EVENT_GUEST_RESTAND = "guest_need_restand"