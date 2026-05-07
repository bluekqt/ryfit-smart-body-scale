# ble/state_machine.py
from . import constants as const
from .event_bus import emit

class BLEStateMachine:
    """管理蓝牙连接状态，确保状态转换合法，并推送事件"""

    def __init__(self):
        self._state = const.STATE_DISCONNECTED
        self._allow_auto_reconnect = True       # 休眠后设为 False，唤醒后恢复

    @property
    def state(self):
        return self._state

    @property
    def can_auto_reconnect(self):
        return self._allow_auto_reconnect and self._state != const.STATE_SLEEPING

    def transition_to(self, new_state):
        if new_state == self._state:
            return
        # 记录旧状态用于日志（可选）
        self._state = new_state
        # 推送状态变化事件
        emit(const.EVENT_BLE_STATE, state=new_state)
        # 某些状态变化需要特殊处理
        if new_state == const.STATE_SLEEPING:
            self._allow_auto_reconnect = False
        elif new_state == const.STATE_DISCONNECTED:
            # 断开连接时不改变 auto_reconnect 标志，由唤醒 API 控制
            pass

    def enter_sleeping(self):
        self.transition_to(const.STATE_SLEEPING)

    def wake_up(self):
        """从休眠状态唤醒，允许自动重连并重置状态"""
        self._allow_auto_reconnect = True
        self.transition_to(const.STATE_DISCONNECTED)