# models/user_dao.py
from .database import get_connection

def get_all_users():
    """返回所有用户列表，按 slot 排序"""
    conn = get_connection()
    users = conn.execute(
        "SELECT id, name, height, age, gender, slot, mode FROM users ORDER BY slot"
    ).fetchall()
    conn.close()
    return [dict(u) for u in users]

def get_user_by_id(user_id):
    """根据 ID 获取单个用户"""
    conn = get_connection()
    user = conn.execute(
        "SELECT id, name, height, age, gender, slot, mode FROM users WHERE id = ?",
        (int(user_id),)
    ).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_slot(slot):
    """根据槽位号获取固定用户"""
    conn = get_connection()
    user = conn.execute(
        "SELECT id, name, height, age, gender, slot, mode FROM users WHERE slot = ? AND mode = 'fixed'",
        (slot,)
    ).fetchone()
    conn.close()
    return dict(user) if user else None

def add_user(name, height, age, gender, slot, mode='fixed'):
    """添加用户，返回新用户的 ID"""
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO users (name, height, age, gender, slot, mode) VALUES (?, ?, ?, ?, ?, ?)",
        (name, height, age, gender, slot, mode)
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id

def update_user_all(user_id, name, height, age, gender, mode, slot):
    conn = get_connection()
    conn.execute(
        "UPDATE users SET name=?, height=?, age=?, gender=?, mode=?, slot=? WHERE id=?",
        (name, height, age, gender, mode, slot, int(user_id))
    )
    conn.commit()
    conn.close()

def update_user_mode(user_id, mode):
    """ 更新用户的模式 """
    conn = get_connection()
    conn.execute("UPDATE users SET mode = ? WHERE id = ?", (mode, int(user_id)))
    conn.commit()
    conn.close()

def update_user_slot(user_id, slot):
    """更新用户的槽位号"""
    conn = get_connection()
    conn.execute("UPDATE users SET slot = ? WHERE id = ?", (slot, int(user_id)))
    conn.commit()
    conn.close()

def delete_user(user_id):
    """删除用户，返回是否成功"""
    conn = get_connection()
    cursor = conn.execute("DELETE FROM users WHERE id = ?", (int(user_id),))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

def get_occupied_slots():
    """返回已占用的槽位列表"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT slot FROM users WHERE mode = 'fixed' AND slot BETWEEN 1 AND 8"
    ).fetchall()
    conn.close()
    return [row['slot'] for row in rows]