# models/measurement_dao.py
from .database import get_connection

def add_measurement(user_id, weight, bmi, fat, water, muscle, bone, bmr,
                    sub_fat, visceral_fat, body_age, measured_at):
    """保存一条测量记录"""
    conn = get_connection()
    conn.execute('''
        INSERT INTO measurements
        (user_id, weight, bmi, fat, water, muscle, bone, bmr, sub_fat, visceral_fat, body_age, measured_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, weight, bmi, fat, water, muscle, bone, bmr, sub_fat, visceral_fat, body_age, measured_at))
    conn.commit()
    conn.close()

def get_measurements_for_user(user_id):
    """获取指定用户的所有测量记录，按时间倒序"""
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM measurements WHERE user_id = ? ORDER BY measured_at DESC',
        (int(user_id),)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_measurements():
    """获取所有历史数据"""
    conn = get_connection()
    rows = conn.execute('SELECT * FROM measurements ORDER BY measured_at ASC').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_measurements(user_id, timestamps):
    """删除指定用户、指定时间戳的多条记录"""
    if not timestamps:
        return 0
    conn = get_connection()
    placeholders = ','.join('?' * len(timestamps))
    cursor = conn.execute(
        f'DELETE FROM measurements WHERE user_id = ? AND measured_at IN ({placeholders})',
        [int(user_id)] + list(timestamps)
    )
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted

def delete_all_measurements_for_user(user_id):
    """删除指定用户的所有记录"""
    conn = get_connection()
    cursor = conn.execute('DELETE FROM measurements WHERE user_id = ?', (int(user_id),))
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted

def record_exists(user_id, measured_at):
    """检查是否已有相同用户和时间戳的记录"""
    conn = get_connection()
    row = conn.execute(
        'SELECT 1 FROM measurements WHERE user_id = ? AND measured_at = ?',
        (int(user_id), measured_at)
    ).fetchone()
    conn.close()
    return row is not None

