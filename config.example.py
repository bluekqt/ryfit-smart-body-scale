# config.py
import os

# ---- 项目根目录 ----
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# ---- 蓝牙配置 ----
BLE_DEVICE_ADDRESS = "设备的MAC值"
BLE_NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# ---- 数据库 ----
DATABASE_PATH = os.path.join(BASE_DIR, "data.db")

# ---- 文件存储（保留 CSV 作为备份） ----
CSV_BACKUP_DIR = os.path.join(BASE_DIR, "backups")
CSV_BACKUP_FILE = os.path.join(CSV_BACKUP_DIR, "weight_records.csv")

# ---- 蓝牙连接超时设置 ----
BLE_CONNECT_TIMEOUT = 30.0          # bleak 连接超时 (秒)
BLE_RECONNECT_DELAY = 5.0           # 断线重连间隔 (秒)
BLE_HEARTBEAT_INTERVAL = 60         # 心跳间隔 (秒)
BLE_IDLE_SLEEP_SECONDS = 600        # 空闲 10 分钟进入休眠

# ---- 历史同步 ----
SYNC_DELAY_SECONDS = 10             # 连接后延迟同步 (秒)
SYNC_HISTORY_TIMEOUT = 20           # 单个槽位历史数据接收超时 (秒)
SYNC_A5_WAIT = 5                    # A5 后等待 B5 的时间 (秒)

# ---- 自动 C0 检测冷却 ----
AUTO_C0_COOLDOWN = 15               # 两次自动 C0 的最小间隔 (秒)

# ---- 测量超时 ----
MEASUREMENT_TIMEOUT = 10            # 第一包后等待第二包的超时 (秒)

# ---- 操作等待 ----
A2_RESPONSE_TIMEOUT = 3.0           # 删除槽位等待应答 (秒)
A1_RESPONSE_TIMEOUT = 2.0           # 激活槽位等待应答 (秒)

# ---- Flask ----
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000