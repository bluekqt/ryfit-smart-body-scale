# ble/__init__.py
from .core import start_ble_loop, state_machine, is_connected, send_cmd_sync, send_cmd_async, update_activity
from .service import (
    switch_user, register_user, reset_user_state,
    query_slots, delete_slot, fetch_history,
    sync_history, delayed_sync,
    pending_user,reset_measurement
)
from .protocol import make_c0_cmd, make_a1_cmd
from .event_bus import emit, subscribe
