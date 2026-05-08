// static/js/app.js
// 首页逻辑
// 创建页面专用的 Socket 连接（仅 polling）
window.socket = io({ transports: ['polling'], reconnection: true, reconnectionDelay: 500 });

// 初始化蓝牙状态监听
BleStatus.initSocket(window.socket);

let users = [];
let occupiedSlots = new Set();
let bleReady = false;
let autoDeleteEnabled = false;

// 监听蓝牙状态变化
window.socket.on('ble_state', (data) => {
  bleReady = (data.state === 'ready');
  updateButtonStates();
});

// 槽位占用更新
window.socket.on('occupied_slots_update', (data) => {
  if (data.occupied_slots) {
    occupiedSlots = new Set(data.occupied_slots);
    updateSlotSelect();
    loadData();
  }
});

// 自动跳转
window.socket.on('auto_redirect', (data) => {
  if (window.location.pathname === '/' || window.location.pathname === '') {
    window.location.href = '/user/' + data.user_id + '?auto=1';
  }
});

async function loadData() {
  try {
    users = await API.getUsers();
    // 本地占用
    occupiedSlots.clear();
    users.forEach(u => {
      if (u.mode === 'fixed' && u.slot && u.slot >= 1 && u.slot <= 8) {
        occupiedSlots.add(u.slot);
      }
    });
    // 加载设置
    const settings = await API.getSettings();
    autoDeleteEnabled = settings.auto_delete_after_sync || false;
    document.getElementById('autoDeleteToggle').checked = autoDeleteEnabled;
    renderCards();
    updateSlotSelect();
    window.socket.emit('reset_state');
    updateButtonStates();
  } catch (e) {
    console.error(e);
  }
}

function updateButtonStates() {
  const regBtn = document.getElementById('registerBtn');
  const gearBtn = document.getElementById('gearBtn');
  const guestSubmitBtn = document.getElementById('guestSubmitBtn');
  const isReady = bleReady;

  // 注册按钮：始终可点击，视觉上区分状态
  if (regBtn) {
    regBtn.classList.toggle('btn-disabled', !isReady);
    regBtn.title = isReady ? '注册新用户' : '蓝牙未连接，无法注册';
  }
  // 齿轮按钮：始终可点击
  if (gearBtn) {
    gearBtn.classList.toggle('btn-disabled', !isReady);
    gearBtn.title = isReady ? '设置' : '蓝牙未连接';
  }
  // 游客测量按钮仍然直接禁用，因为它是表单提交
  if (guestSubmitBtn) guestSubmitBtn.disabled = !isReady;
}

function renderCards() {
  const container = document.getElementById('cardContainer');
  let html = '';
  const sorted = [...users].sort((a, b) => (a.slot || 99) - (b.slot || 99));

  if (sorted.length === 0) {
    html += '<div class="empty-state">暂无已注册用户</div>';
  } else {
    html += '<div class="user-grid">';
    sorted.forEach(u => {
      const genderIcon = (u.gender === '女') ? '👩🏻' : '👨🏻';
      const isLocal = u.mode === 'guest_saved';
      const editBtn = `<button class="edit-btn" onclick="event.stopPropagation(); openEditPanel('${u.id}')" title="编辑用户">✎</button>`;

      html += `
        <div class="user-tile" data-uid="${u.id}" data-mode="${u.mode}" data-slot="${u.slot || ''}" onclick="handleCardClick(this)">
          <button class="delete-card-btn" onclick="event.stopPropagation(); confirmDeleteUser('${u.id}', '${u.name}', '${u.mode}', '${u.slot || ''}')">✕</button>
          ${editBtn}
          <div class="icon">${genderIcon}</div>
          <div class="name">${u.name}</div>
          <span class="slot-badge">${isLocal ? '本地用户' : (u.slot ? '用户 ' + u.slot : '')}</span>
        </div>`;
    });
    html += '</div>';
  }

  html += `
    <div class="user-tile guest-tile" onclick="handleCardClick(this)" data-uid="guest">
      <div class="icon">🧍</div>
      <div class="name">游客称重</div>
      <span class="slot-badge" style="background:#B3BEB0;">本地用户</span>
    </div>`;
  container.innerHTML = html;
}

function handleCardClick(el) {
  const uid = el.dataset.uid;
  if (uid === 'guest') {
    if (!bleReady) {
      Modal.show({ message: '蓝牙未连接，无法开始游客测量', type: 'warning' });
      return;
    }
    openGuestModal();
  } else {
    window.location.href = '/user/' + uid;
  }
}

function updateSlotSelect() {
  const container = document.getElementById('slotSelect');
  if (!container) return;
  container.innerHTML = '';
  for (let i = 1; i <= 8; i++) {
    const btn = document.createElement('div');
    btn.className = 'slot-option';
    btn.textContent = `P${i}`;
    btn.dataset.slot = i;
    if (occupiedSlots.has(i)) {
      btn.classList.add('occupied');
    } else {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.slot-option.selected').forEach(el => el.classList.remove('selected'));
        btn.classList.add('selected');
        document.getElementById('selectedSlot').value = i;
      });
    }
    container.appendChild(btn);
  }
}

// 本地用户升级
let upgradeUserId = null;
let selectedUpgradeSlot = null;

function openUpgradePanel(uid) {
  if (!bleReady) {
    Modal.show({ message: '蓝牙未连接，无法升级', type: 'warning' });
    return;
  }
  upgradeUserId = uid;
  const container = document.getElementById('upgradeSlotSelect');
  container.innerHTML = '';
  for (let i = 1; i <= 8; i++) {
    const btn = document.createElement('div');
    btn.className = 'slot-option';
    btn.textContent = `P${i}`;
    btn.dataset.slot = i;
    if (occupiedSlots.has(i)) {
      btn.classList.add('occupied');
    } else {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#upgradeSlotSelect .slot-option').forEach(el => el.classList.remove('selected'));
        btn.classList.add('selected');
        selectedUpgradeSlot = i;
      });
    }
    container.appendChild(btn);
  }
  document.getElementById('upgradePanel').style.display = 'flex';
}

let editCurrentUser = null;

function openEditPanel(uid) {
    const user = users.find(u => u.id == uid);
    if (!user) return;

    editCurrentUser = user;
    document.getElementById('editUserId').value = user.id;
    document.getElementById('editName').value = user.name;
    document.getElementById('editHeight').value = user.height;
    document.getElementById('editAge').value = user.age;
    document.getElementById('editGender').value = user.gender;
    document.getElementById('editMode').value = user.mode;

    // 控制槽位选择显示
    const modeSelect = document.getElementById('editMode');
    const slotGroup = document.getElementById('editSlotGroup');
    const modeGroup = document.getElementById('editModeGroup');

    // 固定用户可以选择降级；本地用户可以选择升级
    if (user.mode === 'fixed') {
        modeSelect.disabled = false;
        slotGroup.style.display = 'none';   // 降级不需要选槽位
        modeGroup.style.display = 'block';
    } else {
        modeSelect.value = 'guest_saved';
        modeSelect.disabled = false;
        slotGroup.style.display = 'none';
        modeGroup.style.display = 'block';
    }

    // 监听模式切换
    modeSelect.onchange = function() {
        if (this.value === 'fixed' && user.mode === 'guest_saved') {
            // 本地用户升级时需要选择槽位
            slotGroup.style.display = 'block';
            renderEditSlotSelect();
        } else {
            slotGroup.style.display = 'none';
        }
    };

    document.getElementById('editPanel').style.display = 'flex';
}

function closeEditPanel() {
    document.getElementById('editPanel').style.display = 'none';
}

function renderEditSlotSelect() {
    const container = document.getElementById('editSlotSelect');
    container.innerHTML = '';
    for (let i = 1; i <= 8; i++) {
        const btn = document.createElement('div');
        btn.className = 'slot-option';
        btn.textContent = `P${i}`;
        btn.dataset.slot = i;
        if (occupiedSlots.has(i)) {
            btn.classList.add('occupied');
        } else {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#editSlotSelect .slot-option').forEach(el => el.classList.remove('selected'));
                btn.classList.add('selected');
                document.getElementById('selectedEditSlot').value = i;
            });
        }
        container.appendChild(btn);
    }
}

async function saveEditUser() {
    const userId = document.getElementById('editUserId').value;
    const name = document.getElementById('editName').value.trim();
    const height = parseInt(document.getElementById('editHeight').value);
    const age = parseInt(document.getElementById('editAge').value);
    const gender = document.getElementById('editGender').value;
    const mode = document.getElementById('editMode').value;
    let slot = editCurrentUser.slot;

    if (!name) {
        Modal.show({ message: '请输入姓名', type: 'warning' });
        return;
    }

    // 如果是本地用户升级为固定用户，需要槽位
    if (editCurrentUser.mode === 'guest_saved' && mode === 'fixed') {
        const newSlot = document.getElementById('selectedEditSlot').value;
        if (!newSlot) {
            Modal.show({ message: '请选择一个空闲槽位', type: 'warning' });
            return;
        }
        slot = parseInt(newSlot);
    }

    // 警告提示
    const confirmed = await Modal.confirm({
        message: '⚠️ 修改身高/年龄/性别后，历史记录的分析图表将使用新数据重新计算，可能导致过去的数据看起来不准确。\n\n是否继续？',
        confirmText: '确认修改',
        cancelText: '取消',
        type: 'warning'
    });
    if (!confirmed) return;

    try {
        const res = await fetch('/api/edit_user', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, name, height, age, gender, mode, slot })
        });
        const data = await res.json();
        if (data.success) {
            Modal.show({ message: data.message, type: 'success', duration: 2000 });
            closeEditPanel();
            loadData();
        } else {
            Modal.show({ message: data.error || '编辑失败', type: 'error' });
        }
    } catch (e) {
        Modal.show({ message: '请求出错', type: 'error' });
    }
}

function closeUpgradePanel() {
  document.getElementById('upgradePanel').style.display = 'none';
  selectedUpgradeSlot = null;
}

async function confirmUpgrade() {
  const selectedEl = document.querySelector('#upgradeSlotSelect .slot-option.selected');
  const slot = selectedEl ? parseInt(selectedEl.dataset.slot) : null;

  console.log('[升级] 当前参数:', { upgradeUserId, slot });

  if (!upgradeUserId) {
    Modal.show({ message: '用户ID获取失败', type: 'error' });
    return;
  }
  if (!slot) {
    Modal.show({ message: '请选择一个空闲槽位', type: 'warning' });
    return;
  }

  closeUpgradePanel();
  Modal.show({ message: '⏳ 正在升级用户...', type: 'info', closable: false });

  try {
    const res = await fetch('/api/upgrade_user', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: String(upgradeUserId), slot: slot })
    });
    const data = await res.json();
    console.log('[升级] 服务器返回:', data);
    if (data.success) {
      Modal.show({ message: data.message, type: 'success', duration: 2000 });
      loadData();
    } else {
      Modal.show({ message: data.error || '升级失败', type: 'error' });
    }
  } catch (e) {
    Modal.show({ message: '请求出错', type: 'error' });
  }
}

// 齿轮菜单
function toggleGearMenu(e) {
  if (!bleReady) {
    Modal.show({ message: '蓝牙未连接', type: 'warning' });
    return;
  }
  e.stopPropagation();
  document.getElementById('gearDropdown').classList.toggle('active');
}

function toggleAutoDelete(e) {
  e.stopPropagation();
  const cb = document.getElementById('autoDeleteToggle');
  cb.checked = !cb.checked;
  setAutoDelete(cb.checked);
}

async function setAutoDelete(val) {
  try {
    await API.updateSettings({ auto_delete_after_sync: val });
    autoDeleteEnabled = val;
  } catch (e) {
    Modal.show({ message: '设置保存失败', type: 'error' });
  }
}

async function confirmResetAll() {
  const confirmed = await Modal.confirm({
    message: '⚠️ 此操作将：\n1. 清除秤上所有已注册用户\n2. 删除本地全部用户信息\n3. 清空所有测量历史记录\n请务必提前备份数据！',
    confirmText: '清除所有',
    cancelText: '取消',
    type: 'danger'
  });
  if (!confirmed) return;

  Modal.show({ message: '⏳ 正在清除所有数据…', type: 'info', closable: false });
  try {
    await API.resetAll(false);   // 不保留 CSV（已全部清空）
    Modal.show({ message: ' 所有数据已清除', type: 'success', duration: 3000 });
    loadData();
  } catch (e) {
    Modal.show({ message: '操作失败', type: 'error' });
  }
}

// 数据管理面板相关
function openDataManager() {
  document.getElementById('dataManagerPanel').style.display = 'flex';
}
function closeDataManager() {
  document.getElementById('dataManagerPanel').style.display = 'none';
}

// 保存数据未CSV
function exportCSV() {
  window.open('/api/export_csv', '_blank');
}
let importFile = null;

// 文件选择后，弹出用户选择面板
function handleImportCSV(event) {
  const file = event.target.files[0];
  if (!file) return;
  importFile = file;
  // 渲染已有用户列表
  const list = document.getElementById('importUserList');
  list.innerHTML = '';
  users.forEach(u => {
    const item = document.createElement('div');
    item.className = 'user-select-item';
    item.innerHTML = `👤 ${u.name} (${u.slot == 9 ? '本地' : '槽位 ' + u.slot})`;
    item.onclick = () => doImport(u.id);
    list.appendChild(item);
  });
  document.getElementById('importUserPanel').style.display = 'flex';
  // 清除文件输入，以便可以重复选择同一个文件
  event.target.value = '';
}

// 创建本地用户并导入
async function confirmImportLocal() {
  closeImportUserPanel();
  if (!importFile) return;
  await doImport('0');   // 0 表示创建本地用户
}

// 执行导入
async function doImport(targetUserId) {
  closeImportUserPanel();
  Modal.show({ message: '⏳ 正在导入，请稍候…', type: 'info', closable: false });
  try {
    const formData = new FormData();
    formData.append('file', importFile);
    formData.append('target_user_id', targetUserId);
    const res = await fetch('/api/import_csv', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.success) {
      Modal.show({ message: ` 导入完成！成功 ${data.imported} 条，跳过 ${data.skipped} 条。`, type: 'success', duration: 4000 });
      loadData();
    } else {
      Modal.show({ message: '导入失败：' + (data.error || '未知错误'), type: 'error' });
    }
  } catch (e) {
    Modal.show({ message: '请求出错', type: 'error' });
  } finally {
    importFile = null;
  }
}

function closeImportUserPanel() {
  document.getElementById('importUserPanel').style.display = 'none';
}

// 注册弹窗
function openRegisterModal() {
  if (!bleReady) {
    Modal.show({ message: '蓝牙未连接，无法注册新用户', type: 'warning' });
    return;
  }

  const regBtn = document.getElementById('registerBtn');

  // 如果按钮已经被禁用，说明正在查询中，避免重复点击
  if (regBtn.style.pointerEvents === 'none') return;

  // 禁用按钮并添加悬浮提示
  regBtn.style.pointerEvents = 'none';
  regBtn.classList.add('btn-disabled');
  regBtn.title = '正在读取秤上槽位信息，请稍候...';

  // 发送 A5 查询
  fetch('/api/query_slots');

  let resolved = false;
  const onOccupiedUpdate = (data) => {
    if (resolved) return;
    resolved = true;
    window.socket.off('occupied_slots_update', onOccupiedUpdate);
    // 恢复按钮
    regBtn.style.pointerEvents = '';
    regBtn.classList.remove('btn-disabled');
    regBtn.title = '需要蓝牙连接';
    // 打开注册弹窗，此时 occupiedSlots 已是最新
    document.getElementById('registerModal').style.display = 'flex';
    updateSlotSelect();
  };

  window.socket.on('occupied_slots_update', onOccupiedUpdate);

  // 超时保护：3秒后如果还没收到更新，恢复按钮并仍然打开弹窗（可能槽位数据不是最新）
  setTimeout(() => {
    if (!resolved) {
      window.socket.off('occupied_slots_update', onOccupiedUpdate);
      regBtn.style.pointerEvents = '';
      regBtn.classList.remove('btn-disabled');
      regBtn.title = '需要蓝牙连接';
      document.getElementById('registerModal').style.display = 'flex';
      updateSlotSelect();
      console.warn('槽位查询超时，显示的槽位状态可能不是最新');
    }
  }, 3000);
}

function closeRegisterModal() { document.getElementById('registerModal').style.display = 'none'; }

document.getElementById('registerForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const name = formData.get('name').trim();
  if (!name) { Modal.show({ message: '请输入姓名', type: 'warning' }); return; }
  const mode = formData.get('mode');
  if (mode === 'fixed') {
    const slot = document.getElementById('selectedSlot').value;
    if (!slot) { Modal.show({ message: '请选择一个空闲编号', type: 'warning' }); return; }
    formData.set('slot', slot);
  }
  try {
    const result = await API.addUser(formData);
    if (result.success) {
      closeRegisterModal();
      window.location.href = '/user/' + result.user_id;
    } else {
      Modal.show({ message: result.error || '注册失败', type: 'error' });
    }
  } catch (err) {
    Modal.show({ message: '请求出错', type: 'error' });
  }
});

document.querySelectorAll('input[name="mode"]').forEach(radio => {
  radio.addEventListener('change', () => {
    document.getElementById('slotArea').style.display = (radio.value === 'fixed') ? 'block' : 'none';
  });
});

// 游客弹窗
function openGuestModal() { document.getElementById('guestModal').style.display = 'flex'; }
function closeGuestModal() { document.getElementById('guestModal').style.display = 'none'; }

// 开发者面板
document.getElementById('titleText').addEventListener('click', (e) => {
  if (e.shiftKey) openDangerModal();
});
function openDangerModal() { document.getElementById('dangerModal').style.display = 'flex'; }
function closeDangerModal() { document.getElementById('dangerModal').style.display = 'none'; }

async function confirmWriteDevCode() {
  const code = document.getElementById('newDevCode').value.trim();
  if (code.length !== 6 || !/^[0-9A-Fa-f]{6}$/.test(code)) {
    Modal.show({ message: '请输入6位有效的十六进制设备码', type: 'warning' });
    return;
  }
  const confirmed = await Modal.confirm({
    message: `确定要将设备码写入为 ${code.toUpperCase()} 吗？`,
    type: 'danger'
  });
  if (!confirmed) return;
  try {
    const resp = await fetch('/api/write_devcode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ devcode: code.toUpperCase() })
    });
    const data = await resp.json();
    if (data.success) {
      Modal.show({ message: '设备码已写入', type: 'success' });
      closeDangerModal();
    } else {
      Modal.show({ message: '写入失败', type: 'error' });
    }
  } catch (e) {
    Modal.show({ message: '请求出错', type: 'error' });
  }
}

// 删除用户
let deleteUserId = null;
async function confirmDeleteUser(uid, name, mode, slot) {
  deleteUserId = uid;
  const isFixedInScale = (mode === 'fixed' && slot);
  if (isFixedInScale && !bleReady) {
    Modal.show({ message: '蓝牙未连接，无法删除秤内用户数据', type: 'warning' });
    return;
  }
  let message = `确定要删除用户 ${name} 吗？\n\n⚠️ 删除后，该用户的所有测量历史将被永久清除。`;
  if (isFixedInScale) {
    message = `确定要删除用户 ${name} ( 编号0${slot}) 吗？\n\n⚠️ 该操作将删除用户设备内数据和本地数据。\n请自行备份数据！`;
  }
  const confirmed = await Modal.confirm({ message, type: 'danger' });
  if (confirmed) proceedDeleteUser();
}

async function proceedDeleteUser() {
  try {
    const data = await API.deleteUser(deleteUserId);
    if (data.success) {
      loadData();
      Modal.show({ message: data.message || '用户已删除', type: 'success', duration: 2000 });
    } else {
      Modal.show({ message: data.error || '删除失败', type: 'error' });
    }
  } catch (e) {
    Modal.show({ message: '请求出错', type: 'error' });
  }
}

// 启动
loadData();