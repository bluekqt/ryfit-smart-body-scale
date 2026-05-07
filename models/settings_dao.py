# models/settings_dao.py
from .database import get_connection

def get_settings():
    """返回所有设置项（字典）"""
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    result = {}
    for row in rows:
        key = row['key']
        val = row['value']
        # 将布尔值字符串转换为 Python bool
        if val in ('true', 'false'):
            result[key] = val == 'true'
        else:
            # 尝试转为整数，否则保留字符串
            try:
                result[key] = int(val)
            except ValueError:
                result[key] = val
    return result

def set_setting(key, value):
    """更新单个设置项"""
    conn = get_connection()
    # 统一将值转为字符串存储
    if isinstance(value, bool):
        value_str = 'true' if value else 'false'
    else:
        value_str = str(value)
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value_str)
    )
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    """获取单个设置项的值"""
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    if row is None:
        return default
    val = row['value']
    if val in ('true', 'false'):
        return val == 'true'
    try:
        return int(val)
    except ValueError:
        return val