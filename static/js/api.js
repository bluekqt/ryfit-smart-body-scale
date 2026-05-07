// static/js/api.js
// 封装后端 REST API，统一处理返回格式
const API = {
  async get(url) {
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok || data.success === false) {
      throw new Error(data.error || '请求失败');
    }
    return data.data !== undefined ? data.data : data;
  },

  async post(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok || data.success === false) {
      throw new Error(data.error || '请求失败');
    }
    return data.data !== undefined ? data.data : data;
  },

  // 常用接口
  getSettings: () => API.get('/api/settings'),
  updateSettings: (settings) => API.post('/api/settings', settings),
  getUsers: () => API.get('/api/users'),
  addUser: (formData) => fetch('/add_user', { method: 'POST', body: formData, headers: { 'X-Requested-With': 'XMLHttpRequest' } }).then(r => r.json()),
  deleteUser: (id) => API.post('/delete_user/' + id, {}),
  getMeasurements: (userId) => API.get('/api/history/' + userId),
  deleteMeasurements: (userId, timestamps) => API.post('/api/delete_history', { user_id: userId, timestamps }),
  getBLEStatus: () => fetch('/api/ble_status').then(r => r.json()),
  forceSwitch: (payload) => API.post('/api/force_switch', payload),
  wakeBLE: () => API.post('/api/wake_ble', {}),
  resetAll: (keep_csv) => API.post('/api/reset_all_slots', { keep_csv })
};