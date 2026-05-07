# app.py
import time
import threading
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from flask_socketio import SocketIO
from models.database import init_db
from models.user_dao import (
    get_all_users, get_user_by_id, add_user, delete_user, update_user_slot,
    update_user_mode, update_user_all
)
from models.measurement_dao import (
    get_measurements_for_user,
    delete_measurements,
    delete_all_measurements_for_user,
    add_measurement,
    record_exists
)
from models.settings_dao import get_settings, set_setting
import ble

# ---- 初始化应用 ----
app = Flask(__name__)
socketio = SocketIO(app, async_mode='threading')
init_db()

# ---- 注入 WebSocket 发射器到蓝牙模块 ----
ble.inject_emitter(socketio.emit)

# ---- 首页 ----
@app.route('/')
def index():
    ble.reset_user_state()
    users = get_all_users()
    return render_template('index.html', users=users)

# ---- 测量页面 ----
@app.route('/user/<user_id>')
def user_page(user_id):
    auto_mode = request.args.get('auto') == '1'
    if user_id == 'guest':
        height = request.args.get('height', 170, type=int)
        age = request.args.get('age', 30, type=int)
        gender = request.args.get('gender', '男')
        user = {
            "id": "guest",
            "name": "游客",
            "height": height,
            "age": age,
            "gender": gender,
            "slot": 9,
            "mode": "test"
        }
        if not auto_mode:
            ble.switch_user(9, height, age, gender, mode='test',force=True)
    else:
        user = get_user_by_id(user_id)
        if not user:
            return "用户不存在", 404
        slot = user.get("slot")
        mode = user.get("mode", "fixed")
        if slot and not auto_mode:
            ble.switch_user(
                slot,
                user["height"],
                user["age"],
                user["gender"],
                user_id=user_id,
                mode=mode,
                force=True
            )
    return render_template('user.html', user=user, user_id=user_id, auto_mode=auto_mode)

# ---- 游客快速称重 ----
@app.route('/guest_measure', methods=['POST'])
def guest_measure_page():
    ble.reset_user_state()
    height = request.form.get('height', 170, type=int)
    age = request.form.get('age', 30, type=int)
    gender = request.form.get('gender', '男')
    ble.switch_user(9, height, age, gender, mode='test')
    return redirect(url_for('user_page', user_id='guest',
                            height=height, age=age, gender=gender))

# ---- 添加用户 ----
@app.route('/add_user', methods=['POST'])
def add_user_route():
    name = request.form.get('name', '').strip()
    height = request.form.get('height', 170, type=int)
    age = request.form.get('age', 30, type=int)
    gender = request.form.get('gender', '男')
    mode = request.form.get('mode', 'fixed')

    if not name:
        return jsonify({'success': False, 'error': '姓名不能为空'}), 400

    if mode == 'fixed':
        slot = request.form.get('slot', type=int)
        if not slot or slot < 1 or slot > 8:
            return jsonify({'success': False, 'error': '请选择有效的用户编号（1-8）'}), 400
    else:
        slot = 9

    uid = add_user(name, height, age, gender, slot, mode)

    if mode == 'fixed' and ble.is_connected():
        ble.register_user(slot, height, age, gender, user_id=uid, mode=mode)

    return jsonify({'success': True, 'user_id': uid})

# ---- 删除用户 ----
@app.route('/delete_user/<user_id>', methods=['POST'])
def delete_user_route(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

    mode = user.get("mode")
    slot = user.get("slot")

    if mode == "fixed" and slot:
        if not ble.delete_slot(slot):
            return jsonify({'success': False, 'error': '秤上删除失败，请重试'}), 500

    ok = delete_user(user_id)
    if not ok:
        return jsonify({'success': False, 'error': '删除失败'}), 500

    deleted_count = delete_all_measurements_for_user(user_id)

    return jsonify({
        'success': True,
        'message': f'用户已删除，已清除 {deleted_count} 条历史记录。'
    })

# ---- API：获取所有用户 ----
@app.route('/api/users')
def api_users():
    users = get_all_users()
    return jsonify({'success': True, 'data': users})

# ---- API：查询秤内槽位 ----
@app.route('/api/query_slots')
def api_query_slots():
    ble.query_slots()
    return jsonify({'success': True})

# ---- API：用户历史记录 ----
@app.route('/api/history/<user_id>')
def api_history(user_id):
    records = get_measurements_for_user(user_id)
    mapped = []
    for r in records:
        mapped.append({
            '时间': r.get('measured_at', ''),
            '体重(kg)': r.get('weight', ''),
            'BMI': r.get('bmi', ''),
            '体脂(%)': r.get('fat', ''),
            '水份(%)': r.get('water', ''),
            '肌肉(%)': r.get('muscle', ''),
            '骨量(%)': r.get('bone', ''),
            '基础代谢(kcal)': r.get('bmr', ''),
            '皮下脂肪(%)': r.get('sub_fat', ''),
            '内脏脂肪': r.get('visceral_fat', ''),
            '身体年龄': r.get('body_age', '')
        })
    return jsonify(mapped)

# ---- 编辑用户信息 ----
@app.route('/api/edit_user', methods=['POST'])
def edit_user():
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': '缺少用户ID'}), 400

    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

    name = data.get('name', user['name']).strip()
    height = data.get('height', user['height'])
    age = data.get('age', user['age'])
    gender = data.get('gender', user['gender'])
    mode = data.get('mode', user['mode'])
    slot = data.get('slot', user['slot'])

    try:
        height = int(height)
        age = int(age)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': '身高和年龄必须是数字'}), 400
    if gender not in ('男', '女'):
        return jsonify({'success': False, 'error': '性别无效'}), 400
    if mode not in ('fixed', 'guest_saved'):
        return jsonify({'success': False, 'error': '无效的用户模式'}), 400

    # 固定用户降级为本地用户
    if user['mode'] == 'fixed' and mode == 'guest_saved':
        if ble.is_connected():
            ble.delete_slot(user['slot'])
        slot = 9
    # 本地用户升级为固定用户
    elif user['mode'] == 'guest_saved' and mode == 'fixed':
        new_slot = data.get('slot')
        if not new_slot or int(new_slot) < 1 or int(new_slot) > 8:
            return jsonify({'success': False, 'error': '请提供有效的槽位（1-8）'}), 400
        new_slot = int(new_slot)
        occupied = [u['slot'] for u in get_all_users() if u['mode'] == 'fixed' and u.get('slot') is not None]
        if new_slot in occupied:
            return jsonify({'success': False, 'error': '该槽位已被占用'}), 400
        if ble.is_connected():
            ble.register_user(new_slot, height, age, gender, user_id=user_id, mode='fixed')
        slot = new_slot
    else:
        pass

    update_user_all(user_id, name, height, age, gender, mode, slot)
    return jsonify({'success': True, 'message': '用户信息已更新'})

# ---- 升级本地用户为固定用户 ----
@app.route('/api/upgrade_user', methods=['POST'])
def upgrade_user():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400

    user_id = data.get('user_id')
    slot = data.get('slot')

    if not user_id or not slot:
        return jsonify({'success': False, 'error': '缺少参数'}), 400

    try:
        slot_int = int(slot)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': '槽位必须是数字'}), 400

    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

    if user.get('mode') != 'guest_saved':
        return jsonify({'success': False, 'error': '仅可升级本地用户'}), 400

    all_users = get_all_users()
    occupied = [u['slot'] for u in all_users if u['mode'] == 'fixed' and u.get('slot') is not None]
    if slot_int in occupied:
        return jsonify({'success': False, 'error': f'槽位 P{slot_int} 已被占用'}), 400

    if ble.is_connected():
        try:
            ble.register_user(slot_int, user['height'], user['age'], user['gender'], user_id=user_id, mode='fixed')
        except Exception as e:
            print(f"[升级] 秤上注册失败: {e}")
            return jsonify({'success': False, 'error': f'秤上注册失败: {str(e)}'}), 500

    update_user_slot(user_id, slot_int)
    update_user_mode(user_id, 'fixed')
    return jsonify({'success': True, 'message': f'已升级为槽位 P{slot_int}'})

# ---- API：删除指定历史记录 ----
@app.route('/api/delete_history', methods=['POST'])
def api_delete_history():
    data = request.get_json()
    user_id = data.get('user_id', '')
    timestamps = data.get('timestamps', [])
    if not user_id or not timestamps:
        return jsonify({'success': False, 'error': '参数无效'}), 400
    try:
        deleted_count = delete_measurements(user_id, timestamps)
        return jsonify({'success': True, 'deleted_count': deleted_count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ---- API：导出 CSV ----
@app.route('/api/export_csv')
def export_csv():
    from models.measurement_dao import get_all_measurements
    from models.user_dao import get_all_users
    import csv, io
    records = get_all_measurements()
    users = {u['id']: u for u in get_all_users()}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        '时间', '用户ID', '用户姓名', '用户编号', '用户类型',
        '体重(kg)', 'BMI', '体脂(%)', '水份(%)', '肌肉(%)',
        '骨量(%)', '基础代谢(kcal)', '皮下脂肪(%)', '内脏脂肪', '身体年龄',
        '身高(cm)', '年龄', '性别'
    ])
    for r in records:
        u = users.get(r['user_id'])
        writer.writerow([
            r['measured_at'], r['user_id'],
            u['name'] if u else '', u.get('slot', '') if u else '', u.get('mode', '') if u else '',
            r['weight'], r['bmi'], r['fat'], r['water'], r['muscle'],
            r['bone'], r['bmr'], r['sub_fat'], r['visceral_fat'], r['body_age'],
            u['height'] if u else '',
            u['age'] if u else '',
            u['gender'] if u else ''
        ])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=weight_records.csv'})

# ---- API：导入 CSV ----
@app.route('/api/import_csv', methods=['POST'])
def import_csv():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未选择文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400

    target_user_id = request.form.get('target_user_id', '')
    if not target_user_id and target_user_id != '0':
        return jsonify({'success': False, 'error': '缺少目标用户ID'}), 400

    create_local = (target_user_id == '0')
    if not create_local:
        if not get_user_by_id(target_user_id):
            return jsonify({'success': False, 'error': '所选用户不存在'}), 400

    import csv, io
    stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
    reader = csv.DictReader(stream)

    required_fields = ['时间', '体重(kg)', 'BMI', '体脂(%)', '水份(%)', '肌肉(%)',
                      '骨量(%)', '基础代谢(kcal)', '皮下脂肪(%)', '内脏脂肪', '身体年龄']
    for field in required_fields:
        if field not in reader.fieldnames:
            return jsonify({'success': False, 'error': f'CSV 缺少字段: {field}'}), 400

    local_name = '导入用户'
    local_height = 170
    local_age = 30
    local_gender = '男'
    if create_local:
        rows = list(reader)
        if rows:
            first = rows[0]
            if first.get('用户姓名'):
                local_name = first.get('用户姓名', local_name).strip()
            if first.get('身高(cm)'):
                try:
                    local_height = int(float(first['身高(cm)']))
                except:
                    pass
            if first.get('年龄'):
                try:
                    local_age = int(float(first['年龄']))
                except:
                    pass
            if first.get('性别'):
                local_gender = first.get('性别', '男')
                local_gender = '男' if '男' in local_gender else local_gender
        target_user_id = str(add_user(local_name, local_height, local_age, local_gender, 9, 'guest_saved'))
        reader = iter(rows)
    else:
        reader = list(reader)

    imported = 0
    skipped = 0
    for row in reader:
        measured_at = row.get('时间', '').strip()
        if not measured_at:
            skipped += 1
            continue
        if record_exists(int(target_user_id) if target_user_id.isdigit() else 0, measured_at):
            skipped += 1
            continue
        try:
            add_measurement(
                user_id=int(target_user_id) if target_user_id.isdigit() else 0,
                weight=float(row.get('体重(kg)', 0)),
                bmi=float(row.get('BMI', 0)),
                fat=float(row.get('体脂(%)', 0)),
                water=float(row.get('水份(%)', 0)),
                muscle=float(row.get('肌肉(%)', 0)),
                bone=float(row.get('骨量(%)', 0)),
                bmr=int(float(row.get('基础代谢(kcal)', 0))),
                sub_fat=float(row.get('皮下脂肪(%)', 0)),
                visceral_fat=int(float(row.get('内脏脂肪', 0))),
                body_age=int(float(row.get('身体年龄', 0))),
                measured_at=measured_at
            )
            imported += 1
        except (ValueError, KeyError):
            skipped += 1

    return jsonify({'success': True, 'imported': imported, 'skipped': skipped})

# ---- 危险操作：重置一切 ----
@app.route('/api/reset_all_slots', methods=['POST'])
def api_reset_all():
    keep_csv = request.get_json().get('keep_csv', False) if request.is_json else False
    import time as t
    for i in range(1, 9):
        ble.delete_slot(i)
        t.sleep(0.3)

    users = get_all_users()
    for u in users:
        delete_user(u['id'])

    set_setting('occupied_slots', '[]')
    socketio.emit('occupied_slots_update', {'occupied_slots': []})
    return jsonify({'success': True, 'message': '重置完成'})

# ---- 危险操作：写入设备码 ----
@app.route('/api/write_devcode', methods=['POST'])
def api_write_devcode():
    data = request.get_json()
    code = data.get('devcode', '').strip().upper()
    if len(code) != 6 or not all(c in '0123456789ABCDEF' for c in code):
        return jsonify({'success': False, 'error': '无效的设备码'}), 400
    if ble.is_connected():
        ble.send_cmd_sync(bytes.fromhex('A1A5' + code))
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': '蓝牙未连接'}), 400

# ---- 设置接口 ----
@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        return jsonify({'success': True, 'data': get_settings()})
    else:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '无效的请求数据'}), 400
        if 'auto_delete_after_sync' in data:
            set_setting('auto_delete_after_sync', data['auto_delete_after_sync'])
        return jsonify({'success': True})

# ---- 蓝牙状态 API ----
@app.route('/api/ble_status')
def api_ble_status():
    return jsonify({'state': ble.state_machine.state})

# ---- 唤醒蓝牙 API ----
@app.route('/api/wake_ble', methods=['POST'])
def api_wake_ble():
    ble.state_machine.wake_up()
    ble.update_activity()
    return jsonify({'success': True, 'message': '正在重新连接...'})

# ---- 强制切换 API（再次测量） ----
@app.route('/api/force_switch', methods=['POST'])
def force_switch_user():
    data = request.get_json()
    user_id = data.get('user_id', '')
    if not user_id:
        return jsonify({'success': False, 'error': '缺少用户ID'}), 400

    if user_id == 'guest':
        height = data.get('height', 170)
        age = data.get('age', 30)
        gender = data.get('gender', '男')
        user = {"slot": 9, "height": height, "age": age, "gender": gender, "mode": "test"}
    else:
        user = get_user_by_id(user_id)
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404

    if not ble.is_connected():
        return jsonify({'success': False, 'error': '蓝牙未连接'}), 503

    ble.reset_measurement()

    slot = user.get("slot")
    time.sleep(0.2)
    ble.send_cmd_sync(ble.make_c0_cmd(
        slot,
        user["height"],
        user["age"],
        user["gender"]
    ))
    ble.update_activity()
    return jsonify({'success': True, 'message': 'C0 已发送'})

# ---- WebSocket 事件 ----
@socketio.on('connect')
def handle_connect():
    socketio.emit('ble_state', {'state': ble.state_machine.state})

@socketio.on('get_ble_state')
def handle_get_ble_state():
    socketio.emit('ble_state', {'state': ble.state_machine.state})

@socketio.on('reset_state')
def handle_reset_state():
    ble.reset_user_state()

@socketio.on('select_user')
def handle_select_user(user_id, extra_params=None):
    if user_id == 'guest':
        height = extra_params.get('height', 170) if extra_params else 170
        age = extra_params.get('age', 30) if extra_params else 30
        gender = extra_params.get('gender', '男') if extra_params else '男'
        if ble.is_connected():
            ble.switch_user(9, height, age, gender, mode='test', force=True)
            socketio.emit('status', '已切换游客模式，请上秤')
            socketio.emit('guest_need_restand', {})
    else:
        user = get_user_by_id(user_id)
        if user and ble.is_connected():
            ble.switch_user(
                user.get("slot"),
                user["height"],
                user["age"],
                user["gender"],
                user_id=user_id,
                mode=user.get("mode", "fixed"),
                force=True
            )
            socketio.emit('status', f'已切换用户：{user["name"]}')

# ---- 启动 ----
if __name__ == '__main__':
    import logging
    from werkzeug.serving import WSGIRequestHandler

    # 自定义请求处理器：只在出现错误时打印请求日志
    class QuietHandler(WSGIRequestHandler):
        def log_request(self, code='-', size='-'):
            # 只输出错误状态码的日志（4xx, 5xx），成功的不输出
            if isinstance(code, int) and code >= 400:
                super().log_request(code, size)
            # 否则什么都不做

    threading.Thread(target=ble.start_ble_loop, daemon=True).start()
    print("蓝牙后台线程已启动")
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True, request_handler=QuietHandler)