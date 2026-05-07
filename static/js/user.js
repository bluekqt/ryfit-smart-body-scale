// static/js/user.js
// 测量页逻辑

const socket = io({ transports: ['polling'], reconnection: true, reconnectionDelay: 500 });

// 监听蓝牙状态
BleStatus.initSocket(socket);

// 进度提示管理
let measureErrorTimer = null;

function clearMeasureError() {
  if (measureErrorTimer) {
    clearInterval(measureErrorTimer);
    measureErrorTimer = null;
  }
}

function showStatus(msg, hint = '') {
  const statusText = document.getElementById('statusText');
  const statusHint = document.getElementById('statusHint');
  if (statusText) statusText.innerText = msg;
  if (statusHint) statusHint.innerText = hint;
}

// WebSocket 事件
socket.on('measurement_progress', (data) => {
  const phase = data.phase;
  clearMeasureError();

  switch (phase) {
    case 'weighing':
      showStatus('📊 正在分析体成分，请勿下秤…', '');
      break;
    case 'analyzing':
      showStatus('🔬 计算中…', '');
      break;
    case 'done':
      showStatus('✅ 测量完成', '');
      break;
    case 'error':
      showStatus('❌ 测量异常，请重新站上秤', '正在自动重试...');
      let count = 3;
      measureErrorTimer = setInterval(() => {
        count--;
        if (count > 0) {
          const statusHint = document.getElementById('statusHint');
          if (statusHint) statusHint.innerText = `将在 ${count} 秒后自动重试...`;
        } else {
          clearMeasureError();
          showStatus('⏳ 请站上秤，等待测量完成...', '蓝牙已就绪');
        }
      }, 1000);
      break;
  }
});

// 完整测量结果
socket.on('full_result', data => {
  const result = data.result;
  console.log('[user.js] 收到 full_result:', result);
  if (!result || (!isGuest && result.user_id != userId)) return;
  clearMeasureError();
  showResult(result);
  if (!isGuest) loadHistory();
});

// 游客重新站上秤提示
socket.on('guest_need_restand', () => {
  showStatus('请重新站上秤，等待测量完成...', '');
  Modal.show({ message: '已切换游客模式，请重新站上秤', type: 'info', duration: 2000 });
});

// ========== 体脂排名计算 ==========
function getFatRankOfficial(age, gender, fatPercent) {
  const maleMeans = [
    { min: 20, max: 24, mean: 21.4 }, { min: 25, max: 29, mean: 23.7 },
    { min: 30, max: 34, mean: 24.5 }, { min: 35, max: 39, mean: 24.6 },
    { min: 40, max: 44, mean: 24.7 }, { min: 45, max: 49, mean: 24.5 },
    { min: 50, max: 54, mean: 24.3 }, { min: 55, max: 59, mean: 24.0 },
    { min: 60, max: 64, mean: 24.0 }, { min: 65, max: 69, mean: 23.6 },
    { min: 70, max: 74, mean: 23.6 }, { min: 75, max: 79, mean: 23.5 },
    { min: 80, max: 99, mean: 24.0 }
  ];
  const femaleMeans = [
    { min: 20, max: 24, mean: 26.7 }, { min: 25, max: 29, mean: 28.7 },
    { min: 30, max: 34, mean: 29.8 }, { min: 35, max: 39, mean: 30.7 },
    { min: 40, max: 44, mean: 31.4 }, { min: 45, max: 49, mean: 32.0 },
    { min: 50, max: 54, mean: 32.3 }, { min: 55, max: 59, mean: 32.7 },
    { min: 60, max: 64, mean: 33.4 }, { min: 65, max: 69, mean: 33.7 },
    { min: 70, max: 74, mean: 33.7 }, { min: 75, max: 79, mean: 33.1 },
    { min: 80, max: 99, mean: 33.0 }
  ];
  const means = (gender === '男') ? maleMeans : femaleMeans;
  let mean = means[0].mean;
  for (const r of means) {
    if (age >= r.min && age <= r.max) { mean = r.mean; break; }
  }
  const sd = (gender === '男') ? 5.0 : 5.5;
  const z = (fatPercent - mean) / sd;
  const cdf = 0.5 * (1 + erf(z / Math.sqrt(2)));
  const percentile = Math.round((1 - cdf) * 100);
  return Math.max(0, Math.min(100, percentile));
}

function erf(x) {
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741;
  const a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const sign = (x >= 0) ? 1 : -1;
  x = Math.abs(x);
  const t = 1.0 / (1.0 + p * x);
  const y = 1.0 - ((((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x));
  return sign * y;
}

// ========== 体脂排名分级配置 ==========
function getFatRankLevel(fatRank) {
  if (fatRank >= 90) return { level: '优秀', class: 'rank-excellent' };
  if (fatRank >= 70) return { level: '良好', class: 'rank-good' };
  if (fatRank >= 30) return { level: '标准', class: 'rank-normal' };
  return { level: '建议关注', class: 'rank-attention' };
}

// ========== 星级生成引擎（与条形图区间完全对齐） ==========
function getStarInfo(val, ranges, direction = 'mid') {
  const v = Number(val);
  if (!ranges) return { stars: '⭐⭐⭐⭐⭐', cls: 'stars-5' };

  let count = 3;
  if (direction === 'low') {
    if (v <= ranges[1]) count = 5;
    else if (v <= ranges[2]) count = 4;
    else if (v <= ranges[3]) count = 3;
    else count = 2;
  } else if (direction === 'high') {
    if (v >= ranges[2]) count = 5;
    else if (v >= ranges[1]) count = 4;
    else if (v >= ranges[0]) count = 3;
    else count = 2;
  } else {
    if (v >= ranges[1] && v <= ranges[2]) count = 5;
    else if ((v >= ranges[0] && v < ranges[1]) || (v > ranges[2] && v <= ranges[3])) count = 4;
    else if ((v < ranges[0] && v >= 0) || (v > ranges[3] && v <= ranges[4])) count = 3;
    else count = 2;
  }
  return { stars: '⭐'.repeat(count), cls: `stars-${count}` };
}

// ========== 分析图表 ==========
function drawAnalysis(result, bmi, calcBmr) {
  const container = document.getElementById('barCharts');
  const isMale = userCfg.gender === '男';

  const muscleStdLow = isMale ? 44 : 38;
  const muscleStdHigh = isMale ? 52 : 46;
  const waterStdLow = isMale ? 53 : 48;
  const waterStdHigh = isMale ? 58 : 55;
  const boneStdLow = isMale ? 4.6 : 4.0;
  const boneStdHigh = isMale ? 5.2 : 4.9;
  const subFatStdHigh = isMale ? 22 : 28;
  const bmrStdLow = isMale ? 1500 : 1200;
  const bmrStdHigh = isMale ? 1700 : 1400;

  const items = [
    { label: '体重', value: result.weight, ranges: [0, 50, 80, 100, 120], unit: 'kg', float: 1, direction: 'mid' },
    { label: 'BMI', value: bmi, ranges: [10, 18.5, 24, 28, 35], unit: '', float: 1, direction: 'mid' },
    { label: '体脂率', value: result.fat, ranges: isMale ? [8, 14, 24, 30, 40] : [8, 21, 28, 35, 45], unit: '%', float: 1, direction: 'low' },
    { label: '肌肉比例', value: result.muscle, ranges: [30, muscleStdLow, muscleStdHigh, 60, 70], unit: '%', float: 1, direction: 'high' },
    { label: '身体年龄', value: result.body_age, ranges: [0, userCfg.age - 5, userCfg.age + 5, userCfg.age + 15, userCfg.age + 25], unit: '岁', float: 0, direction: 'mid' },
    { label: '皮下脂肪', value: result.sub_fat, ranges: [5, 10, subFatStdHigh, 30, 40], unit: '%', float: 1, direction: 'low' },
    { label: '内脏脂肪', value: result.visceral_fat, ranges: [0, 9, 14, 15, 20], unit: '', float: 0, direction: 'low' },
    { label: '基础代谢', value: calcBmr, ranges: [1000, bmrStdLow, bmrStdHigh, 2000, 2500], unit: 'kcal', float: 0, direction: 'high' },
    { label: '骨量', value: result.bone, ranges: [2, boneStdLow, boneStdHigh, 6, 7], unit: '%', float: 1, direction: 'mid' },
    { label: '水含量', value: result.water, ranges: [40, waterStdLow, waterStdHigh, 65, 70], unit: '%', float: 1, direction: 'mid' }
  ];

  const labelsMap = {
    mid: ['偏低', '标准', '偏高', '过高'],
    low: ['优秀', '良好', '注意', '警示'],
    high: ['不足', '标准', '良好', '优秀']
  };

  const tooltipMap = {
    mid: ['低于标准范围', '处于健康区间', '略超标准范围', '超出健康阈值'],
    low: ['极佳状态', '安全区间', '略高于理想值', '已超警戒线'],
    high: ['低于标准水平', '处于基准线', '优于平均水平', '表现优异']
  };

  let html = '';
  items.forEach(item => {
    const val = Number(item.value);
    const r = item.ranges;
    const totalRange = r[4] - r[0];
    if (totalRange <= 0) return;

    const seg1 = ((r[1] - r[0]) / totalRange) * 100;
    const seg2 = ((r[2] - r[1]) / totalRange) * 100;
    const seg3 = ((r[3] - r[2]) / totalRange) * 100;
    const seg4 = ((r[4] - r[3]) / totalRange) * 100;
    const pos = Math.max(0, Math.min(100, ((val - r[0]) / totalRange) * 100));

    const labels = labelsMap[item.direction];
    const tips = tooltipMap[item.direction];

    html += `
            <div class="bar-item">
                <div class="bar-title">
                    <strong>${item.label}</strong>
                    <span class="value">${item.float ? val.toFixed(1) : Math.round(val)} ${item.unit}</span>
                </div>
                <div class="bar-track">
                    <div class="bar-segment seg-low" style="width: ${seg1}%" data-tooltip="${tips[0]}">${labels[0]}</div>
                    <div class="bar-segment seg-std" style="width: ${seg2}%" data-tooltip="${tips[1]}">${labels[1]}</div>
                    <div class="bar-segment seg-high" style="width: ${seg3}%" data-tooltip="${tips[2]}">${labels[2]}</div>
                    <div class="bar-segment seg-over" style="width: ${seg4}%" data-tooltip="${tips[3]}">${labels[3]}</div>
                    <div class="bar-indicator" style="left: ${pos}%"></div>
                </div>
            </div>`;
  });
  container.innerHTML = html;
}

// 显示分析报告
function showResult(result) {
  document.getElementById('statusArea').style.display = 'none';
  document.getElementById('analysisArea').style.display = 'block';

  const h = userCfg.height, a = userCfg.age, g = userCfg.gender;
  const bmi = result.weight / Math.pow(h / 100, 2);
  const calcBmr = g === '男' ?
    Math.round(10 * result.weight + 6.25 * h - 5 * a + 5) :
    Math.round(10 * result.weight + 6.25 * h - 5 * a - 161);

  const fatRank = getFatRankOfficial(a, g, result.fat);
  const rankInfo = getFatRankLevel(fatRank);
  const isMale = g === '男';
  const fatStar = getStarInfo(fatRank >= 90 ? 100 : fatRank >= 70 ? 80 : fatRank >= 30 ? 50 : 10, [0, 70, 90, 95, 100], 'high');

  document.getElementById('summaryCards').innerHTML = `
        <div class="data-item" data-tooltip="体重测量值，单位：千克">
            <div class="val">${result.weight} kg</div>
            <div class="stars ${getStarInfo(result.weight, [0, 50, 80, 100, 120], 'mid').cls}">${getStarInfo(result.weight, [0, 50, 80, 100, 120], 'mid').stars}</div>
            <div class="label">体重</div>
        </div>
        <div class="data-item" data-tooltip="BMI = 体重(kg) / 身高(m)²">
            <div class="val">${bmi.toFixed(1)}</div>
            <div class="stars ${getStarInfo(bmi, [10, 18.5, 24, 28, 35], 'mid').cls}">${getStarInfo(bmi, [10, 18.5, 24, 28, 35], 'mid').stars}</div>
            <div class="label">BMI</div>
        </div>
        <div class="data-item" data-tooltip="体脂率基于BIA生物电阻抗法估算">
            <div class="val">${result.fat}%</div>
            <div class="stars ${getStarInfo(result.fat, isMale ? [8, 14, 24, 30, 40] : [8, 21, 28, 35, 45], 'low').cls}">${getStarInfo(result.fat, isMale ? [8, 14, 24, 30, 40] : [8, 21, 28, 35, 45], 'low').stars}</div>
            <div class="label">体脂率</div>
        </div>
        <div class="data-item" data-tooltip="身体年龄基于多项体成分综合估算">
            <div class="val">${result.body_age} 岁</div>
            <div class="stars ${getStarInfo(result.body_age, [0, a - 5, a + 5, a + 15, a + 25], 'mid').cls}">${getStarInfo(result.body_age, [0, a - 5, a + 5, a + 15, a + 25], 'mid').stars}</div>
            <div class="label">身体年龄</div>
        </div>
        <div class="data-item ${rankInfo.class}" data-tooltip="同龄同性别参考数据">
            <div class="val">${rankInfo.level}</div>
            <div class="stars ${fatStar.cls}">${fatStar.stars}</div>
            <div class="label">体脂排名</div>
        </div>
        <div class="data-item" data-tooltip="Mifflin-St Jeor公式校准计算">
            <div class="val">${calcBmr} kcal</div>
            <div class="stars ${getStarInfo(calcBmr, isMale ? [1000, 1500, 1700, 2000, 2500] : [800, 1200, 1400, 1800, 2200], 'high').cls}">${getStarInfo(calcBmr, isMale ? [1000, 1500, 1700, 2000, 2500] : [800, 1200, 1400, 1800, 2200], 'high').stars}</div>
            <div class="label">基础代谢</div>
        </div>
        <div class="data-item" data-tooltip="骨骼肌占体重比例">
            <div class="val">${result.muscle}%</div>
            <div class="stars ${getStarInfo(result.muscle, [30, isMale ? 44 : 38, isMale ? 52 : 46, 60, 70], 'high').cls}">${getStarInfo(result.muscle, [30, isMale ? 44 : 38, isMale ? 52 : 46, 60, 70], 'high').stars}</div>
            <div class="label">肌肉比例</div>
        </div>
        <div class="data-item" data-tooltip="皮下脂肪厚度参考">
            <div class="val">${result.sub_fat}%</div>
            <div class="stars ${getStarInfo(result.sub_fat, [5, 10, isMale ? 22 : 28, 30, 40], 'low').cls}">${getStarInfo(result.sub_fat, [5, 10, isMale ? 22 : 28, 30, 40], 'low').stars}</div>
            <div class="label">皮下脂肪</div>
        </div>
        <div class="data-item" data-tooltip="内脏脂肪等级">
            <div class="val">${result.visceral_fat}级</div>
            <div class="stars ${getStarInfo(result.visceral_fat, [0, 9, 14, 15, 20], 'low').cls}">${getStarInfo(result.visceral_fat, [0, 9, 14, 15, 20], 'low').stars}</div>
            <div class="label">内脏脂肪</div>
        </div>
        <div class="data-item" data-tooltip="身体总水分占比">
            <div class="val">${result.water}%</div>
            <div class="stars ${getStarInfo(result.water, [40, isMale ? 53 : 48, isMale ? 58 : 55, 65, 70], 'mid').cls}">${getStarInfo(result.water, [40, isMale ? 53 : 48, isMale ? 58 : 55, 65, 70], 'mid').stars}</div>
            <div class="label">水含量</div>
        </div>
    `;
  drawAnalysis(result, bmi, calcBmr);
}

// 历史记录加载
async function loadHistory() {
  try {
    const data = await API.getMeasurements(userId);
    const tbody = document.querySelector('#historyTable tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!data.length) { tbody.innerHTML = '<tr><td colspan="12">暂无记录</td></tr>'; return; }
    data.sort((a, b) => b.时间.localeCompare(a.时间));
    data.forEach(r => {
      const row = document.createElement('tr');
      row.style.cursor = 'pointer';
      row.dataset.weight = r['体重(kg)'] || '';
      row.dataset.fat = r['体脂(%)'] || '';
      row.dataset.water = r['水份(%)'] || '';
      row.dataset.muscle = r['肌肉(%)'] || '';
      row.dataset.bone = r['骨量(%)'] || '';
      row.dataset.bmr = r['基础代谢(kcal)'] || '';
      row.dataset.subFat = r['皮下脂肪(%)'] || '';
      row.dataset.visceral = r['内脏脂肪'] || '';
      row.dataset.bodyAge = r['身体年龄'] || '';
      row.dataset.time = r['时间'] || '';
      row.onclick = () => showResultFromTable(row);
      row.innerHTML = `
        <td><input type="checkbox" data-timestamp="${r['时间']}" onchange="updateDeleteButtonState()"></td>
        <td>${r['时间'] || ''}</td>
        <td>${r['体重(kg)'] || ''}</td>
        <td>${r['BMI'] || ''}</td>
        <td>${r['体脂(%)'] || ''}</td>
        <td>${r['水份(%)'] || ''}</td>
        <td>${r['肌肉(%)'] || ''}</td>
        <td>${r['骨量(%)'] || ''}</td>
        <td title="分析页已按公式校准">${r['基础代谢(kcal)'] || ''}</td>
        <td>${r['皮下脂肪(%)'] || ''}</td>
        <td>${r['内脏脂肪'] || ''}</td>
        <td>${r['身体年龄'] || ''}</td>
      `;
      row.querySelector('input[type="checkbox"]').addEventListener('click', e => {
        e.stopPropagation();
        updateDeleteButtonState();
      });
      tbody.appendChild(row);
    });
    updateDeleteButtonState();
  } catch (e) {
    console.error(e);
    Modal.show({ message: '加载历史记录失败', type: 'error' });
  }
}

function showResultFromTable(row) {
  document.querySelectorAll('#historyTable tbody tr').forEach(tr => tr.style.background = '');
  row.style.background = '#E8E5DE';
  const ds = row.dataset;
  const h = userCfg.height, a = userCfg.age, g = userCfg.gender;
  const weight = parseFloat(ds.weight);
  const calcBmr = g === '男' ?
    Math.round(10 * weight + 6.25 * h - 5 * a + 5) :
    Math.round(10 * weight + 6.25 * h - 5 * a - 161);
  showResult({
    weight, fat: parseFloat(ds.fat), water: parseFloat(ds.water),
    muscle: parseFloat(ds.muscle), bone: parseFloat(ds.bone),
    bmr: calcBmr, sub_fat: parseFloat(ds.subFat),
    visceral_fat: parseInt(ds.visceral), body_age: parseInt(ds.bodyAge),
    time: ds.time
  });
}


// ========== 全选 / 删除按钮状态 ==========
function toggleSelectAll() {
  const selectAll = document.getElementById('selectAllCheckbox');
  document.querySelectorAll('#historyTable tbody input[type="checkbox"]').forEach(cb => cb.checked = selectAll.checked);
  updateDeleteButtonState();
}

function updateDeleteButtonState() {
  const checkedCount = Array.from(document.querySelectorAll('#historyTable tbody input[type="checkbox"]')).filter(cb => cb.checked).length;
  document.getElementById('deleteSelectedBtn').disabled = (checkedCount === 0);
}

async function confirmDelete() {
  const checkboxes = document.querySelectorAll('#historyTable tbody input[type="checkbox"]:checked');
  if (checkboxes.length === 0) return;
  const confirmed = await Modal.confirm({ message: `确定要删除选中的 ${checkboxes.length} 条记录吗？`, type: 'danger' });
  if (confirmed) {
    const timestamps = Array.from(checkboxes).map(cb => cb.dataset.timestamp);
    try {
      await API.deleteMeasurements(userId, timestamps);
      loadHistory();
      Modal.show({ message: '删除成功', type: 'success', duration: 1500 });
    } catch (e) {
      Modal.show({ message: '删除失败', type: 'error' });
    }
  }
}

// 再次测量
async function requestRemeasure() {
  const data = await API.getBLEStatus();
  if (data.state !== 'ready') {
    Modal.show({ message: '蓝牙未连接，无法开始测量', type: 'warning' });
    return;
  }
  document.getElementById('analysisArea').style.display = 'none';
  document.getElementById('statusArea').style.display = 'block';

  // 先提示请上秤
  showStatus('⏳ 请站上秤，等待测量完成...', '蓝牙已就绪');

  // 2 秒内如果体重稳定，秤会自动进入测量，提示会由 measurement_progress 更新
  // 如果 2 秒后仍未进入测量，说明确实还没站上，保持当前提示即可
  let measuring = false;
  const handler = (data) => {
    if (data.phase === 'weighing') {
      measuring = true;
      socket.off('measurement_progress', handler);
    }
  };
  
  socket.on('measurement_progress', handler);

  socket.on('measurement_reset', () => {
    clearMeasureError();
    showStatus('⏳ 请站上秤，等待测量完成...', '蓝牙已就绪');
  });

  setTimeout(() => {
    if (!measuring) {
      showStatus('⏳ 请站上秤，等待测量完成...', '蓝牙已就绪');
    }
    socket.off('measurement_progress', handler);
  }, 2000);

  if (isGuest) {
    await API.forceSwitch({ user_id: 'guest', height: userCfg.height, age: userCfg.age, gender: userCfg.gender });
  } else {
    await API.forceSwitch({ user_id: userId });
  }
}

// 自动跳转时加载最新记录
async function loadHistoryAndShowLatest() {
  try {
    const data = await API.getMeasurements(userId);
    if (data.length > 0) {
      data.sort((a, b) => b.时间.localeCompare(a.时间));
      const latest = data[0];
      showResult({
        weight: parseFloat(latest['体重(kg)']), fat: parseFloat(latest['体脂(%)']),
        water: parseFloat(latest['水份(%)']), muscle: parseFloat(latest['肌肉(%)']),
        bone: parseFloat(latest['骨量(%)']), bmr: parseInt(latest['基础代谢(kcal)']),
        sub_fat: parseFloat(latest['皮下脂肪(%)']), visceral_fat: parseInt(latest['内脏脂肪']),
        body_age: parseInt(latest['身体年龄']), time: latest['时间']
      });
    }
  } catch (e) { console.error(e); }
}

// 初始化
if (!isGuest) {
  loadHistory();
  if (autoMode) loadHistoryAndShowLatest();
}