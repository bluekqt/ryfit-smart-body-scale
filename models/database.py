# models/database.py
import sqlite3
from config import DATABASE_PATH

# ---- 创建数据库表 ----
def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            height INTEGER NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            slot INTEGER,
            mode TEXT DEFAULT 'fixed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 测量记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            weight REAL,
            bmi REAL,
            fat REAL,
            water REAL,
            muscle REAL,
            bone REAL,
            bmr INTEGER,
            sub_fat REAL,
            visceral_fat INTEGER,
            body_age INTEGER,
            measured_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # 全局设置表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    # 初始设置
    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_delete_after_sync', 'false')
    ''')

    conn.commit()
    conn.close()

# ---- 获取数据库连接 ----
def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row    # 允许按列名访问
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ---- 初始化数据库 ----
init_db()