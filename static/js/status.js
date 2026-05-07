// static/js/status.js
// 蓝牙状态统一管理（用于所有页面）
const BleStatus = (() => {
  let currentState = 'disconnected';
  let pollTimer = null;

  // 更新所有页面上的状态文字
  function updateUI(state) {
    currentState = state;
    document.querySelectorAll('.ble-status-text').forEach(el => {
      el.className = 'ble-status-text ' + state;
      switch (state) {
        case 'disconnected': el.textContent = '🔌 蓝牙未连接,请尝试激活设备'; break;
        case 'connecting':
        case 'syncing':
          el.textContent = '⏳ 数据同步准备中'; break;
        case 'ready': el.textContent = '🟢 蓝牙已就绪'; break;
        case 'lost': el.textContent = '🔌 蓝牙断开'; break;
        case 'sleeping':
          el.innerHTML = '💤 长时间未使用,已休眠 <button onclick="BleStatus.wake()" style="margin-left:6px;font-size:12px;color:#fff;padding:2px 8px;background:#DFB064;border:none;border-radius:8px;">唤醒</button>';
          break;
      }
    });

    // 测量页特有的元素（如果存在）
    const remeasureBtn = document.getElementById('remeasureBtn');
    if (remeasureBtn) remeasureBtn.disabled = (state !== 'ready');

    const statusText = document.getElementById('statusText');
    const statusHint = document.getElementById('statusHint');
    if (state === 'ready') {
      if (statusText) statusText.innerText = '⏳ 请站上秤，等待测量完成...';
      if (statusHint) statusHint.innerText = '蓝牙已连接';
    } else {
      if (statusText) statusText.innerText = '当前仅可查看历史记录';
      if (statusHint) statusHint.innerText = '🔌 蓝牙未连接';
    }
  }

  // 从 API 获取最新状态并更新 UI（兜底）
  async function fetchAndUpdate() {
    try {
      const resp = await fetch('/api/ble_status');
      const data = await resp.json();
      if (data && data.state) {
        updateUI(data.state);
      }
    } catch (e) {
      // 静默忽略
    }
  }

  // 启动轮询（每 3 秒）
  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    fetchAndUpdate();                 // 立即执行一次
    pollTimer = setInterval(fetchAndUpdate, 3000);
  }

  // 监听 WebSocket 推送（首页和测量页调用）
  function initSocket(socket) {
    if (!socket) return;
    socket.on('ble_state', (data) => {
      updateUI(data.state);
    });
    // 主动请求一次状态
    socket.emit('get_ble_state');
  }

  // 唤醒设备
  async function wake() {
    try {
      await API.wakeBLE();
      Modal.show({ message: '正在唤醒设备,请稍候...', type: 'info', closable: false });
      const timer = setInterval(async () => {
        const data = await API.getBLEStatus();
        if (data.state === 'ready') {
          clearInterval(timer);
          Modal.hide();
          Modal.show({ message: '设备已唤醒', type: 'success', duration: 2000 });
        }
      }, 2000);
    } catch (e) {
      Modal.show({ message: '唤醒失败', type: 'error', duration: 2000 });
    }
  }

  //  DOM 加载完成后再启动轮询，确保元素存在
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startPolling);
  } else {
    startPolling();
  }

  return { updateUI, initSocket, wake, getState: () => currentState };
})();