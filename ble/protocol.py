# ble/protocol.py
import struct
import time
from datetime import datetime
from . import constants as const

def make_time_sync():
    """构造时间同步指令 FA F8 + Unix 时间戳（小端序）"""
    now = int(time.time())
    return b'\xFA\xF8' + struct.pack('<I', now)

def make_a1_cmd(slot, height_cm, age, gender):
    """构造 A1 激活槽位指令"""
    h = max(0, min(255, 2 * height_cm - 200))
    gen = 0x01 if gender == "男" else 0x00
    return bytearray([0xA1, slot, h, age, gen])

def make_c0_cmd(slot, height_cm, age, gender):
    """构造 C0 切换/创建用户指令"""
    h = max(0, min(255, 2 * height_cm - 200))
    gen = 0x01 if gender == "男" else 0x00
    return bytearray([0xC0, slot, h, age, gen])

# -------- 数据包解析器（纯函数，不修改任何全局状态） ----------

def parse_d2(data):
    """解析 D2 实时重量包，返回字典或 None"""
    try:
        if len(data) < 4 or data[0] != 0xD2:
            return None
        weight = int(data[1:3].hex(), 16) / 10.0
        return {'weight': weight}
    except:
        return None

def parse_packet1(data):
    """解析第一数据包（体重/体脂/水分），返回字段集合或 None"""
    try:
        if len(data) < 14 or not (data[2] & 0x01):
            return None
        weight = int(data[8:10].hex(), 16) / 10.0
        fat = int(data[10:12].hex(), 16) / 10.0
        water = int(data[12:14].hex(), 16) / 10.0
        slot = data[3]
        seq = data[2]
        ts = struct.unpack('<I', data[4:8])[0] if data[0] == 0xD1 else None
        return {
            'type': 'packet1',
            'weight': weight,
            'fat': fat,
            'water': water,
            'slot': slot,
            'seq': seq,
            'timestamp': ts,
            'is_sync': data[0] == 0xD1
        }
    except:
        return None

def parse_packet2(data):
    """解析第二数据包（详细体成分），返回字段集合或 None"""
    try:
        if len(data) < 14 or (data[2] & 0x01):
            return None
        muscle = struct.unpack('>H', data[4:6])[0] / 10.0
        bone = struct.unpack('>H', data[6:8])[0] / 10.0
        bmr = struct.unpack('>H', data[8:10])[0]
        sub_fat = struct.unpack('>H', data[10:12])[0] / 10.0
        visceral = data[12]
        body_age = data[13]
        slot = data[3]
        seq = data[2]
        return {
            'type': 'packet2',
            'muscle': muscle,
            'bone': bone,
            'bmr': bmr,
            'sub_fat': sub_fat,
            'visceral_fat': visceral,
            'body_age': body_age,
            'slot': slot,
            'seq': seq,
            'is_sync': data[0] == 0xD1
        }
    except:
        return None

def parse_b5(data):
    """解析 B5 包，返回槽位信息或 None"""
    try:
        if len(data) < 7 or data[0] != 0xB5:
            return None
        slot = data[3]
        height_code = data[4]
        age = data[5]
        gender = "男" if data[6] == 0x01 else "女"
        height_cm = (height_code + 200) // 2
        return {'slot': slot, 'height': height_cm, 'age': age, 'gender': gender}
    except:
        return None

def parse_fb(data):
    """解析 FB 类应答，返回 (类型, 状态) 或 None"""
    if len(data) < 3:
        return None
    cmd = data[:2]
    status = data[2] if len(data) > 2 else 0
    if cmd == b'\xFB\xF8':
        return ('TIME_SYNC_OK', None)
    if cmd == b'\xFB\xA5':
        count = data[3] if len(data) > 3 else 0
        return ('A5_RESPONSE', count)
    if cmd == b'\xFB\xA2':
        return ('A2_RESPONSE', status)
    if cmd == b'\xFB\xC0':
        return ('C0_RESPONSE', status)
    if cmd == b'\xFB\xA1':
        return ('A1_RESPONSE', status)
    return None

def is_valid_measurement(packet2, packet1_fat, packet1_water):
    """判断测量数据是否有效（基于第二包和第一包的体脂/水分）"""
    if packet2 is None:
        return False
    if (packet2.get('muscle', 0) <= 0 and
        packet2.get('bone', 0) <= 0 and
        packet2.get('bmr', 0) <= 0 and
        packet1_fat is not None and packet1_fat <= 0.0 and
        packet1_water is not None and packet1_water <= 0.0):
        return False
    return True

def make_ack(data):
    """构造 FA 确认包（前3字节）"""
    return b'\xFA' + bytes(data[:3])