# ble/handlers.py
from .protocol import (
    parse_d2, parse_packet1, parse_packet2, parse_b5, parse_fb, make_ack
)
from .core import send_cmd_sync

class NotificationHandler:
    """数据包分发器（同步调用）"""

    def __init__(self, session, slot_manager, sync_manager, fb_callback=None):
        self.session = session
        self.slot_manager = slot_manager
        self.sync_manager = sync_manager
        self._fb_callback = fb_callback    # FB 应答回调，替代事件总线

    def handle(self, raw: bytes):
        """蓝牙通知入口，由 core 在接收线程中同步调用"""
        # D2 实时重量
        d2 = parse_d2(raw)
        if d2:
            self.session.handle_d2(d2['weight'])
            return

        # Packet1
        p1 = parse_packet1(raw)
        if p1:
            if p1.get('is_sync'):
                self.sync_manager.handle_sync_packet1(p1)
            else:
                self.session.handle_packet1(p1)
            self._ack(raw)
            return

        # Packet2
        p2 = parse_packet2(raw)
        if p2:
            if p2.get('is_sync'):
                self.sync_manager.handle_sync_packet2(p2)
            else:
                self.session.handle_packet2(p2)
            self._ack(raw)
            return

        # B5 槽位信息
        b5 = parse_b5(raw)
        if b5:
            self.slot_manager.handle_b5(b5)
            self._ack(raw)
            return

        # FB 应答类
        fb = parse_fb(raw)
        if fb:
            resp_type, value = fb
            if resp_type == 'A5_RESPONSE':
                # value 为 B5 包数量
                self.slot_manager.on_a5_response(value)
            # 调用外部 FB 回调（用于同步等待 A1/A2 等）
            if self._fb_callback:
                self._fb_callback(fb)
            # 需要 ACK 的 FB 类型
            if resp_type in ('A5_RESPONSE', 'A2_RESPONSE', 'A1_RESPONSE', 'C0_RESPONSE'):
                self._ack(raw)

    def _ack(self, raw):
        """发送 FA 确认"""
        send_cmd_sync(make_ack(raw))