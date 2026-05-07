# ble/event_bus.py
from collections import defaultdict

_listeners = defaultdict(list)

def subscribe(event, listener):
    """注册对某事件的监听函数"""
    _listeners[event].append(listener)

def unsubscribe(event, listener):
    """取消监听"""
    if listener in _listeners[event]:
        _listeners[event].remove(listener)

def emit(event, **kwargs):
    """触发事件，调用所有监听函数并传入关键字参数"""
    for listener in _listeners.get(event, []):
        try:
            listener(**kwargs)
        except Exception as e:
            print(f"[EventBus] 监听器 {listener} 执行异常: {e}")

def clear():
    """清除所有监听器（主要用于测试或重置）"""
    _listeners.clear()