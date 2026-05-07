# ble/state_machine.py
from . import constants as const

class BLEStateMachine:
    """管理蓝牙连接状态，确保状态转换合法，并推送事件"""

    def __init__(self):
        self._state = const.STATE_DISCONNECTED
        self._allow_auto_reconnect = True
        self._emit = None          # 由 `inject_emitter` 注入

    @property
    def state(self):
        return self._state

    @property
    def can_auto_reconnect(self):
        return self._allow_auto_reconnect and self._state != const.STATE_SLEEPING

    def transition_to(self, new_state):
        if new_state == self._state:
            return
        self._state = new_state
        if self._emit:
            self._emit('ble_state', {'state': new_state})
        if new_state == const.STATE_SLEEPING:
            self._allow_auto_reconnect = False
        elif new_state == const.STATE_DISCONNECTED:
            pass

    def enter_sleeping(self):
        self.transition_to(const.STATE_SLEEPING)

    def wake_up(self):
        self._allow_auto_reconnect = True
        self.transition_to(const.STATE_DISCONNECTED)